#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil

from glm51_runpod_r2_cold.config import load_app_config
from glm51_runpod_r2_cold.constants import PROJECT_CONFIRMATION_VALUE
from glm51_runpod_r2_cold.r2_storage import R2Storage
from glm51_runpod_r2_cold.runpod_api import RunpodAPI
from glm51_runpod_r2_cold.state import clear_active_pod_state, clear_endpoint_state, clear_live_action_ack
from glm51_runpod_r2_cold.workflow import find_project_pods


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delete only this project's resources.")
    parser.add_argument("--confirm", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.confirm != PROJECT_CONFIRMATION_VALUE:
        raise SystemExit(f"Refusing to continue. Re-run with --confirm {PROJECT_CONFIRMATION_VALUE}")

    config = load_app_config()
    deleted_pods = 0
    deleted_objects = 0
    with RunpodAPI(config.runpod.api_key or "") as api:
        for pod in find_project_pods(api.list_pods(), config.runpod.pod_name_prefix):
            try:
                api.stop_pod(pod["id"])
            except Exception:  # noqa: BLE001
                pass
            api.delete_pod(pod["id"])
            deleted_pods += 1

    if all([config.r2.account_id, config.r2.bucket, config.r2.access_key_id, config.r2.secret_access_key]):
        r2 = R2Storage(
            account_id=config.r2.account_id,
            bucket=config.r2.bucket,
            access_key_id=config.r2.access_key_id,
            secret_access_key=config.r2.secret_access_key,
        )
        deleted_objects = r2.delete_prefix(config.r2_prefix_base)

    clear_active_pod_state()
    clear_endpoint_state()
    clear_live_action_ack()
    if config.state_dir.exists():
        shutil.rmtree(config.state_dir, ignore_errors=True)
    print(f"Deleted {deleted_pods} Pod(s) and {deleted_objects} R2 object(s) under {config.r2_prefix_base}.")


if __name__ == "__main__":
    main()
