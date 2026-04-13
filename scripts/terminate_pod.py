#!/usr/bin/env python3
from __future__ import annotations

from glm51_runpod_r2_cold.config import load_app_config
from glm51_runpod_r2_cold.runpod_api import RunpodAPI
from glm51_runpod_r2_cold.state import clear_active_pod_state, clear_endpoint_state, load_active_pod_state
from glm51_runpod_r2_cold.workflow import choose_reusable_pod, find_project_pods


def main() -> None:
    config = load_app_config()
    tracked_state = load_active_pod_state()
    pod_id = tracked_state.get("pod_id") if tracked_state else None

    with RunpodAPI(config.runpod.api_key or "") as api:
        target_id = pod_id
        if not target_id:
            existing = choose_reusable_pod(find_project_pods(api.list_pods(), config.runpod.pod_name_prefix))
            target_id = existing["id"] if existing else None
        if not target_id:
            clear_active_pod_state()
            clear_endpoint_state()
            print("No matching project Pod exists.")
            return
        try:
            api.stop_pod(target_id)
        except Exception:  # noqa: BLE001
            pass
        api.delete_pod(target_id)

    clear_active_pod_state()
    clear_endpoint_state()
    print(f"Deleted Pod {target_id}.")


if __name__ == "__main__":
    main()

