from __future__ import annotations

import math
import os
import time
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


def wait_for_http_ready(base_url: str, timeout_seconds: float = 5400, interval_seconds: float = 15) -> dict[str, Any]:
    """Poll within a monotonic budget, accounting for requests and sleeps.

    HTTPX limits individual transport phases, so an in-flight request can still
    overrun this budget. Late responses are never reported as ready.
    """
    for name, value in (("timeout_seconds", timeout_seconds), ("interval_seconds", interval_seconds)):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and greater than zero.")

    deadline = time.monotonic() + timeout_seconds
    last_error = None
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                health_response = client.get(f"{base_url}/health", timeout=min(30.0, remaining))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if health_response.status_code == 200:
                    models_response = client.get(f"{base_url}/v1/models", timeout=min(30.0, remaining))
                    models_response.raise_for_status()
                    models = models_response.json()
                    if time.monotonic() < deadline:
                        return models
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval_seconds, remaining))
        if last_error:
            raise RuntimeError(f"Service did not become ready before timeout: {last_error}") from last_error
        raise RuntimeError("Service did not become ready before timeout.")
