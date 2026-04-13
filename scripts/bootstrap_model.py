#!/usr/bin/env python3
from __future__ import annotations

from glm51_runpod_r2_cold.bootstrap import ensure_model_ready
from glm51_runpod_r2_cold.config import load_app_config
from glm51_runpod_r2_cold.console import print_json


def main() -> None:
    config = load_app_config()
    required = {
        "R2_ACCOUNT_ID": config.r2.account_id,
        "R2_BUCKET": config.r2.bucket,
        "R2_ACCESS_KEY_ID": config.r2.access_key_id,
        "R2_SECRET_ACCESS_KEY": config.r2.secret_access_key,
        "MODEL_ID": config.model_id,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise SystemExit(f"Missing required bootstrap values: {', '.join(missing)}")
    print_json(ensure_model_ready(config))


if __name__ == "__main__":
    main()

