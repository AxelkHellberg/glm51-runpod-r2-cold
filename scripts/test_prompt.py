#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

import httpx

from glm51_runpod_r2_cold.config import load_app_config
from glm51_runpod_r2_cold.state import load_endpoint_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a test chat completion request to the live Pod.")
    parser.add_argument("--prompt", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_app_config()
    endpoint = load_endpoint_state()
    if not endpoint or not endpoint.get("base_url"):
        raise SystemExit("No live endpoint information is available. Run `make live-up` first.")

    payload = {
        "model": config.vllm.served_model_name,
        "messages": [{"role": "user", "content": args.prompt}],
        "temperature": 0.2,
    }
    with httpx.Client(timeout=180.0) as client:
        response = client.post(f"{endpoint['base_url']}/v1/chat/completions", json=payload)
        response.raise_for_status()
        body = response.json()
    message = body["choices"][0]["message"]
    print(json.dumps({"response": message.get("content"), "raw": body}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

