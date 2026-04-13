from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .constants import LIVE_ACTION_ACK_VALUE, MODE_NAME, MODEL_ID_DEFAULT, PROJECT_NAME, RUNPOD_PROXY_TEMPLATE
from .paths import CONFIG_DIR, REPO_ROOT, STATE_DIR


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _flag(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip() == "1"


def _nullable_int(value: str | None, default: int | None) -> int | None:
    if value is None or value == "":
        return default
    if value.lower() == "null":
        return None
    return int(value)


def model_slug(model_id: str) -> str:
    return model_id.replace("/", "--")


@dataclass(slots=True)
class RunpodSettings:
    api_key: str | None
    cloud_type: str
    gpu_type_ids: list[str]
    gpu_count: int
    data_center_ids: list[str]
    pod_name_prefix: str
    image_name: str | None
    container_registry_auth_id: str | None
    compute_type: str
    container_disk_in_gb: int
    volume_in_gb: int | None
    support_public_ip: bool
    interruptible: bool
    global_networking: bool
    gpu_type_priority: str
    data_center_priority: str
    ports: list[str]


@dataclass(slots=True)
class R2Settings:
    account_id: str | None
    bucket: str | None
    access_key_id: str | None
    secret_access_key: str | None

    @property
    def endpoint_url(self) -> str | None:
        if not self.account_id:
            return None
        return f"https://{self.account_id}.r2.cloudflarestorage.com"


@dataclass(slots=True)
class BootstrapSettings:
    auto_mirror_to_r2: bool
    completion_marker_dirname: str
    completion_marker_suffix: str


@dataclass(slots=True)
class VLLMSettings:
    host: str
    port: int
    served_model_name: str
    tensor_parallel_size: int
    tool_call_parser: str
    reasoning_parser: str
    enable_auto_tool_choice: bool


@dataclass(slots=True)
class AppConfig:
    repo_root: Path
    state_dir: Path
    project_name: str
    mode_name: str
    model_id: str
    model_slug: str
    model_root_base: Path
    r2_prefix_base: str
    live_deploy: bool
    runpod: RunpodSettings
    r2: R2Settings
    bootstrap: BootstrapSettings
    vllm: VLLMSettings
    hf_token: str | None

    @property
    def model_root(self) -> Path:
        return self.model_root_base / self.model_slug

    @property
    def completion_marker_path(self) -> Path:
        return self.model_root_base / self.bootstrap.completion_marker_dirname / f"{self.model_slug}{self.bootstrap.completion_marker_suffix}"

    @property
    def manifest_key(self) -> str:
        return f"{self.r2_prefix_base}/{self.model_slug}/manifest.json"

    @property
    def artifact_prefix(self) -> str:
        return f"{self.r2_prefix_base}/{self.model_slug}/files"

    @property
    def proxy_base_url(self) -> str | None:
        state = None
        from .state import load_active_pod_state

        state = load_active_pod_state()
        if not state:
            return None
        pod_id = state.get("pod_id")
        if not pod_id:
            return None
        return RUNPOD_PROXY_TEMPLATE.format(pod_id=pod_id, port=self.vllm.port)

    def live_action_ack_is_valid(self, value: str | None) -> bool:
        return (value or "").strip() == LIVE_ACTION_ACK_VALUE

    def pod_env(self) -> dict[str, str]:
        env = {
            "AUTO_MIRROR_TO_R2": "1" if self.bootstrap.auto_mirror_to_r2 else "0",
            "MODEL_ID": self.model_id,
            "R2_ACCOUNT_ID": self.r2.account_id or "",
            "R2_BUCKET": self.r2.bucket or "",
            "R2_ACCESS_KEY_ID": self.r2.access_key_id or "",
            "R2_SECRET_ACCESS_KEY": self.r2.secret_access_key or "",
        }
        if self.hf_token:
            env["HF_TOKEN"] = self.hf_token
        return env

    def pod_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cloudType": self.runpod.cloud_type,
            "computeType": self.runpod.compute_type,
            "containerDiskInGb": self.runpod.container_disk_in_gb,
            "env": self.pod_env(),
            "gpuCount": self.runpod.gpu_count,
            "gpuTypeIds": self.runpod.gpu_type_ids,
            "gpuTypePriority": self.runpod.gpu_type_priority,
            "imageName": self.runpod.image_name,
            "interruptible": self.runpod.interruptible,
            "name": self.runpod.pod_name_prefix,
            "ports": self.runpod.ports,
            "supportPublicIp": self.runpod.support_public_ip,
        }
        if self.runpod.volume_in_gb is not None:
            payload["volumeInGb"] = self.runpod.volume_in_gb
        if self.runpod.container_registry_auth_id:
            payload["containerRegistryAuthId"] = self.runpod.container_registry_auth_id
        if self.runpod.data_center_ids:
            payload["dataCenterIds"] = self.runpod.data_center_ids
            payload["dataCenterPriority"] = self.runpod.data_center_priority
        if self.runpod.global_networking:
            payload["globalNetworking"] = True
        return payload


def load_app_config() -> AppConfig:
    load_dotenv(REPO_ROOT / ".env", override=False)

    merged = _deep_merge(
        _read_yaml(CONFIG_DIR / "defaults.yaml"),
        _read_yaml(CONFIG_DIR / "modes" / f"{MODE_NAME}.yaml"),
    )

    project_cfg = merged["project"]
    runpod_cfg = merged["runpod"]
    bootstrap_cfg = merged["bootstrap"]
    vllm_cfg = merged["vllm"]

    effective_model_id = os.getenv("MODEL_ID", MODEL_ID_DEFAULT).strip() or MODEL_ID_DEFAULT
    effective_model_slug = model_slug(effective_model_id)

    runpod_data_center_ids = _csv_list(os.getenv("RUNPOD_DATA_CENTER_IDS"))
    data_center_priority = "custom" if runpod_data_center_ids else runpod_cfg["data_center_priority"]

    runpod = RunpodSettings(
        api_key=os.getenv("RUNPOD_API_KEY"),
        cloud_type=(os.getenv("RUNPOD_CLOUD_TYPE") or runpod_cfg["cloud_type"]).upper(),
        gpu_type_ids=_csv_list(os.getenv("RUNPOD_GPU_TYPE_IDS")) or list(runpod_cfg["gpu_type_ids"]),
        gpu_count=int(os.getenv("RUNPOD_GPU_COUNT", runpod_cfg["gpu_count"])),
        data_center_ids=runpod_data_center_ids,
        pod_name_prefix=os.getenv("RUNPOD_POD_NAME", project_cfg["pod_name_prefix"]),
        image_name=os.getenv("RUNPOD_IMAGE_NAME"),
        container_registry_auth_id=os.getenv("RUNPOD_CONTAINER_REGISTRY_AUTH_ID"),
        compute_type=runpod_cfg["compute_type"],
        container_disk_in_gb=int(runpod_cfg["container_disk_in_gb"]),
        volume_in_gb=_nullable_int(None, runpod_cfg["volume_in_gb"]),
        support_public_ip=bool(runpod_cfg["support_public_ip"]),
        interruptible=bool(runpod_cfg["interruptible"]),
        global_networking=bool(runpod_cfg["global_networking"]),
        gpu_type_priority=runpod_cfg["gpu_type_priority"],
        data_center_priority=data_center_priority,
        ports=list(runpod_cfg["ports"]),
    )

    r2 = R2Settings(
        account_id=os.getenv("R2_ACCOUNT_ID"),
        bucket=os.getenv("R2_BUCKET"),
        access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
        secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
    )

    bootstrap = BootstrapSettings(
        auto_mirror_to_r2=_flag(os.getenv("AUTO_MIRROR_TO_R2"), bool(bootstrap_cfg["auto_mirror_to_r2_default"])),
        completion_marker_dirname=bootstrap_cfg["completion_marker_dirname"],
        completion_marker_suffix=bootstrap_cfg["completion_marker_suffix"],
    )

    vllm = VLLMSettings(
        host=vllm_cfg["host"],
        port=int(vllm_cfg["port"]),
        served_model_name=vllm_cfg["served_model_name"],
        tensor_parallel_size=int(vllm_cfg["tensor_parallel_size"]),
        tool_call_parser=vllm_cfg["tool_call_parser"],
        reasoning_parser=vllm_cfg["reasoning_parser"],
        enable_auto_tool_choice=bool(vllm_cfg["enable_auto_tool_choice"]),
    )

    return AppConfig(
        repo_root=REPO_ROOT,
        state_dir=STATE_DIR,
        project_name=project_cfg.get("name", PROJECT_NAME),
        mode_name=project_cfg.get("mode", MODE_NAME),
        model_id=effective_model_id,
        model_slug=effective_model_slug,
        model_root_base=Path(project_cfg["model_root_base"]),
        r2_prefix_base=project_cfg["r2_prefix"],
        live_deploy=_flag(os.getenv("LIVE_DEPLOY"), False),
        runpod=runpod,
        r2=r2,
        bootstrap=bootstrap,
        vllm=vllm,
        hf_token=os.getenv("HF_TOKEN"),
    )
