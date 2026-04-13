from __future__ import annotations

import os
from typing import Any

import httpx

from .config import AppConfig


def build_vllm_command(config: AppConfig) -> list[str]:
    command = [
        "vllm",
        "serve",
        str(config.model_root),
        "--host",
        config.vllm.host,
        "--port",
        str(config.vllm.port),
        "--tensor-parallel-size",
        str(config.vllm.tensor_parallel_size),
        "--served-model-name",
        config.vllm.served_model_name,
        "--tool-call-parser",
        config.vllm.tool_call_parser,
        "--reasoning-parser",
        config.vllm.reasoning_parser,
    ]
    if config.vllm.enable_auto_tool_choice:
        command.append("--enable-auto-tool-choice")
    return command


def exec_vllm(config: AppConfig) -> None:
    command = build_vllm_command(config)
    os.execvp(command[0], command)


def wait_for_http_ready(base_url: str, timeout_seconds: int = 5400, interval_seconds: int = 15) -> dict[str, Any]:
    deadline = httpx.Timeout(timeout=30.0)
    with httpx.Client(timeout=deadline, follow_redirects=True) as client:
        elapsed = 0
        last_error = None
        while elapsed <= timeout_seconds:
            try:
                health_response = client.get(f"{base_url}/health")
                if health_response.status_code == 200:
                    models_response = client.get(f"{base_url}/v1/models")
                    models_response.raise_for_status()
                    return models_response.json()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            if elapsed >= timeout_seconds:
                break
            import time

            time.sleep(interval_seconds)
            elapsed += interval_seconds
        if last_error:
            raise RuntimeError(f"Service did not become ready before timeout: {last_error}") from last_error
        raise RuntimeError("Service did not become ready before timeout.")
