#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

import httpx

from glm51_runpod_r2_cold.config import load_app_config
from glm51_runpod_r2_cold.console import live_action_ready, manual_step_required, print_json
from glm51_runpod_r2_cold.r2_storage import R2Storage
from glm51_runpod_r2_cold.runpod_api import RunpodAPI, pod_state_snapshot
from glm51_runpod_r2_cold.state import read_live_action_ack, write_active_pod_state, write_endpoint_state, write_live_action_ack
from glm51_runpod_r2_cold.workflow import choose_reusable_pod, find_project_pods, generate_pod_name, missing_env, required_env_for_live


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or reuse the project Runpod Pod.")
    parser.add_argument("--plan", action="store_true", help="Print the exact Pod payload without creating anything.")
    parser.add_argument("--live-action-ack", default="", help="Set to DONE after reviewing the LIVE ACTION READY gate.")
    return parser.parse_args()


def _r2_manifest_exists(config) -> bool | None:
    if not all([config.r2.account_id, config.r2.bucket, config.r2.access_key_id, config.r2.secret_access_key]):
        return None
    r2 = R2Storage(
        account_id=config.r2.account_id,
        bucket=config.r2.bucket,
        access_key_id=config.r2.access_key_id,
        secret_access_key=config.r2.secret_access_key,
    )
    return r2.object_exists(config.manifest_key)


def _redact_payload(payload: dict) -> dict:
    redacted = json.loads(json.dumps(payload))
    sensitive_env_keys = {
        "RUNPOD_API_KEY",
        "HF_TOKEN",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
    }
    env = redacted.get("env") or {}
    for key in sensitive_env_keys:
        if key in env and env[key]:
            env[key] = "***REDACTED***"
    if redacted.get("containerRegistryAuthId"):
        redacted["containerRegistryAuthId"] = "***REDACTED***"
    return redacted


def _manual_private_registry_step() -> None:
    manual_step_required(
        explanation="Live deployment cannot proceed until the private container image and Runpod registry auth are set up.",
        steps=[
            "Build the image locally with `make build IMAGE_NAME=<your-private-image-ref>`.",
            "Push that image to your private registry.",
            "Create or confirm a Runpod container registry auth that can pull that image.",
            "Update `.env` with the exact private image reference and the Runpod registry auth ID.",
        ],
        needed_after=[
            "In `.env`: RUNPOD_IMAGE_NAME=<your-private-image-ref>",
            "In `.env`: RUNPOD_CONTAINER_REGISTRY_AUTH_ID=<runpod-registry-auth-id>",
        ],
    )


def _create_pod_with_capacity_fallback(api: RunpodAPI, payload: dict, preferred_cloud_type: str) -> tuple[dict, str]:
    attempted_cloud_types = [preferred_cloud_type]
    if preferred_cloud_type == "COMMUNITY":
        attempted_cloud_types.append("SECURE")

    last_exc: Exception | None = None
    for cloud_type in attempted_cloud_types:
        candidate_payload = json.loads(json.dumps(payload))
        candidate_payload["cloudType"] = cloud_type
        try:
            return api.create_pod(candidate_payload), cloud_type
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            detail = (exc.response.text or "").lower()
            if cloud_type == "COMMUNITY" and "no instances currently available" in detail:
                continue
            raise
    assert last_exc is not None
    raise last_exc


def main() -> None:
    args = parse_args()
    config = load_app_config()
    payload = config.pod_payload()
    manifest_exists = _r2_manifest_exists(config)

    if args.plan:
        print_json(
            {
                "mode": config.mode_name,
                "manifest_exists_in_r2": manifest_exists,
                "payload": _redact_payload(payload),
                "cold_start_path": "restore-from-r2" if manifest_exists else "download-from-huggingface-then-optional-mirror",
            }
        )
        return

    missing = missing_env(config, required_env_for_live(config))
    if "RUNPOD_IMAGE_NAME" in missing:
        _manual_private_registry_step()
    if missing:
        raise SystemExit(f"Missing required live values: {', '.join(missing)}")
    if not config.live_deploy:
        raise SystemExit("LIVE_DEPLOY must be set to 1 before any live provisioning.")

    ack_value = args.live_action_ack.strip() or (read_live_action_ack() or "")
    if not config.live_action_ack_is_valid(ack_value):
        cache_state = "R2 restore" if manifest_exists else "fresh Hugging Face download followed by optional R2 mirror"
        live_action_ready(
            summary=(
                "This will create one on-demand Runpod Pod for glm51-runpod-r2-cold and pull the configured image. "
                f"The bootstrap path is: {cache_state}. Re-run with `make live-up LIVE_ACTION_ACK=DONE` after review."
            ),
            hardware=[
                f"Cloud type: {config.runpod.cloud_type}",
                f"GPU request: {config.runpod.gpu_count}x {', '.join(config.runpod.gpu_type_ids)}",
                f"Container disk: {config.runpod.container_disk_in_gb} GB temporary",
                "Persistent Runpod storage: none",
                f"Image: {config.runpod.image_name}",
                (
                    f"Registry auth: {config.runpod.container_registry_auth_id}"
                    if config.runpod.container_registry_auth_id
                    else "Registry auth: none (public image)"
                ),
                f"Exposed ports: {', '.join(config.runpod.ports)}",
            ],
        )
    write_live_action_ack(ack_value)

    with RunpodAPI(config.runpod.api_key or "") as api:
        existing_pod = choose_reusable_pod(find_project_pods(api.list_pods(), config.runpod.pod_name_prefix))
        if existing_pod:
            if existing_pod.get("desiredStatus") == "EXITED":
                existing_pod = api.start_pod(existing_pod["id"])
            snapshot = pod_state_snapshot(existing_pod, proxy_port=config.vllm.port)
            write_active_pod_state(snapshot)
            write_endpoint_state({"base_url": snapshot["proxy_base_url"], "pod_id": snapshot["pod_id"]})
            print_json({"reused": True, "pod": snapshot})
            return

        payload["name"] = generate_pod_name(config.runpod.pod_name_prefix)
        pod, used_cloud_type = _create_pod_with_capacity_fallback(api, payload, config.runpod.cloud_type)
        snapshot = pod_state_snapshot(pod, proxy_port=config.vllm.port)
        snapshot["cloud_type"] = used_cloud_type
        write_active_pod_state(snapshot)
        write_endpoint_state({"base_url": snapshot["proxy_base_url"], "pod_id": snapshot["pod_id"]})
        print(
            json.dumps(
                {"reused": False, "pod": snapshot, "payload_name": payload["name"], "cloud_type_used": used_cloud_type},
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
