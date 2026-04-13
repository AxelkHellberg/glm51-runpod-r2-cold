#!/usr/bin/env python3
from __future__ import annotations

from botocore.exceptions import BotoCoreError, ClientError

from glm51_runpod_r2_cold.config import load_app_config
from glm51_runpod_r2_cold.console import print_report_line
from glm51_runpod_r2_cold.r2_storage import R2Storage
from glm51_runpod_r2_cold.runpod_api import RunpodAPI
from glm51_runpod_r2_cold.workflow import missing_env, required_env_for_doctor


def main() -> None:
    config = load_app_config()
    failures: list[str] = []
    warnings: list[str] = []

    required_missing = missing_env(config, required_env_for_doctor(config))
    if required_missing:
        failures.append(f"Missing required values: {', '.join(required_missing)}")

    print_report_line("Mode", "OK", config.mode_name)
    print_report_line("Model", "OK", config.model_id)
    print_report_line("Disk plan", "OK", f"containerDiskInGb={config.runpod.container_disk_in_gb}, volumeInGb={config.runpod.volume_in_gb}")

    if config.runpod.cloud_type not in {"COMMUNITY", "SECURE"}:
        failures.append("RUNPOD_CLOUD_TYPE must be COMMUNITY or SECURE.")
    else:
        print_report_line("Runpod cloud", "OK", config.runpod.cloud_type)

    if config.runpod.api_key:
        try:
            with RunpodAPI(config.runpod.api_key) as api:
                pods = api.list_pods()
                print_report_line("Runpod API", "OK", f"Authenticated. Visible pods: {len(pods)}")
                if config.runpod.container_registry_auth_id:
                    auth = api.get_container_registry_auth(config.runpod.container_registry_auth_id)
                    print_report_line(
                        "Registry auth",
                        "OK",
                        f"{auth['id']} ({auth.get('name', 'unnamed')})",
                    )
                else:
                    print_report_line("Registry auth", "WARN", "Not set. Live deploy assumes the image is publicly pullable.")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"Runpod API check failed: {exc}")
    else:
        failures.append("RUNPOD_API_KEY is required for live preflight.")

    if all([config.r2.account_id, config.r2.bucket, config.r2.access_key_id, config.r2.secret_access_key]):
        try:
            r2 = R2Storage(
                account_id=config.r2.account_id,
                bucket=config.r2.bucket,
                access_key_id=config.r2.access_key_id,
                secret_access_key=config.r2.secret_access_key,
            )
            r2.head_bucket()
            print_report_line("R2 bucket", "OK", config.r2.bucket)
            manifest_exists = r2.object_exists(config.manifest_key)
            if manifest_exists:
                print_report_line("R2 manifest", "OK", config.manifest_key)
            else:
                warnings.append(
                    "No R2 cache manifest exists yet. The first cold run will need a full Hugging Face download and optional mirror."
                )
                print_report_line("R2 manifest", "WARN", "Missing")
        except (BotoCoreError, ClientError, Exception) as exc:  # noqa: BLE001
            failures.append(f"R2 access check failed: {exc}")
    else:
        failures.append("R2 credentials are required for live preflight.")

    if config.runpod.image_name:
        print_report_line("Image name", "OK", config.runpod.image_name)
    else:
        failures.append("RUNPOD_IMAGE_NAME is required.")

    if warnings:
        for warning in warnings:
            print_report_line("Warning", "WARN", warning)

    if failures:
        for failure in failures:
            print_report_line("Failure", "FAIL", failure)
        raise SystemExit(1)

    print_report_line("Preflight", "OK", "All required checks passed.")


if __name__ == "__main__":
    main()
