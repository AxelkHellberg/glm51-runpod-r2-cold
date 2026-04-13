from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable

from .config import AppConfig
from .runpod_api import pod_matches_prefix


def required_env_for_doctor(config: AppConfig) -> list[str]:
    required = [
        "RUNPOD_API_KEY",
        "RUNPOD_IMAGE_NAME",
        "R2_ACCOUNT_ID",
        "R2_BUCKET",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
    ]
    return required


def required_env_for_live(config: AppConfig) -> list[str]:
    return required_env_for_doctor(config)


def config_value_map(config: AppConfig) -> dict[str, str | None]:
    return {
        "RUNPOD_API_KEY": config.runpod.api_key,
        "RUNPOD_IMAGE_NAME": config.runpod.image_name,
        "RUNPOD_CONTAINER_REGISTRY_AUTH_ID": config.runpod.container_registry_auth_id,
        "R2_ACCOUNT_ID": config.r2.account_id,
        "R2_BUCKET": config.r2.bucket,
        "R2_ACCESS_KEY_ID": config.r2.access_key_id,
        "R2_SECRET_ACCESS_KEY": config.r2.secret_access_key,
    }


def missing_env(config: AppConfig, required_keys: Iterable[str]) -> list[str]:
    values = config_value_map(config)
    return [key for key in required_keys if not values.get(key)]


def generate_pod_name(prefix: str) -> str:
    return f"{prefix}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"


def find_project_pods(pods: list[dict], prefix: str) -> list[dict]:
    return [pod for pod in pods if pod_matches_prefix(pod, prefix)]


def choose_reusable_pod(pods: list[dict]) -> dict | None:
    if not pods:
        return None
    status_rank = {"RUNNING": 0, "EXITED": 1, "CREATED": 2, "STARTING": 3}
    sorted_pods = sorted(
        pods,
        key=lambda pod: (
            status_rank.get(pod.get("desiredStatus"), 99),
            pod.get("lastStartedAt") or "",
            pod.get("id") or "",
        ),
    )
    return sorted_pods[0]
