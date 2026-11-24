#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time

from glm51_runpod_r2_cold.config import load_app_config
from glm51_runpod_r2_cold.console import print_json
from glm51_runpod_r2_cold.runpod_api import RunpodAPI, pod_state_snapshot
from glm51_runpod_r2_cold.server import wait_for_http_ready
from glm51_runpod_r2_cold.state import load_active_pod_state, write_active_pod_state, write_endpoint_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wait for the Pod and API endpoint to become ready.")
    parser.add_argument("--timeout-seconds", type=int, default=5400)
    parser.add_argument("--poll-interval-seconds", type=int, default=20)
    args = parser.parse_args()
    if args.timeout_seconds <= 0 or args.poll_interval_seconds <= 0:
        parser.error("Timeout and poll interval must be positive.")
    return args


def main() -> None:
    args = parse_args()
    config = load_app_config()
    state = load_active_pod_state()
    if not state or not state.get("pod_id"):
        raise SystemExit("No active Pod state was found. Run `make live-up` first.")

    pod_id = state["pod_id"]
    base_url = state["proxy_base_url"]
    deadline = time.monotonic() + args.timeout_seconds
    with RunpodAPI(config.runpod.api_key or "") as api:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            pod = api.get_pod(pod_id, timeout=min(30.0, remaining))
            snapshot = pod_state_snapshot(pod, proxy_port=config.vllm.port)
            write_active_pod_state(snapshot)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if snapshot.get("desired_status") == "RUNNING":
                models = wait_for_http_ready(base_url, timeout_seconds=remaining)
                if time.monotonic() >= deadline:
                    break
                endpoint_state = {"base_url": base_url, "models": models, "pod_id": pod_id}
                write_endpoint_state(endpoint_state)
                print_json(endpoint_state)
                return
            time.sleep(min(args.poll_interval_seconds, remaining))
    raise SystemExit("Timed out while waiting for the Pod and API endpoint to become ready.")


if __name__ == "__main__":
    main()

