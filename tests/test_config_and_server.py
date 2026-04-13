from pathlib import Path

from glm51_runpod_r2_cold.config import (
    AppConfig,
    BootstrapSettings,
    R2Settings,
    RunpodSettings,
    VLLMSettings,
    model_slug,
)
from glm51_runpod_r2_cold.server import build_vllm_command


def make_config(*, registry_auth: str | None = None, volume_in_gb: int | None = None) -> AppConfig:
    return AppConfig(
        repo_root=Path("/repo"),
        state_dir=Path("/repo/.state"),
        project_name="glm51-runpod-r2-cold",
        mode_name="r2-cold",
        model_id="zai-org/GLM-5.1-FP8",
        model_slug="zai-org--GLM-5.1-FP8",
        model_root_base=Path("/workspace/models"),
        r2_prefix_base="glm51-runpod-r2-cold/r2-cold",
        live_deploy=False,
        runpod=RunpodSettings(
            api_key="test-key",
            cloud_type="COMMUNITY",
            gpu_type_ids=["NVIDIA H200"],
            gpu_count=8,
            data_center_ids=[],
            pod_name_prefix="glm51-runpod-r2-cold-r2-cold",
            image_name="ghcr.io/example/glm51-runpod-r2-cold:latest",
            container_registry_auth_id=registry_auth,
            compute_type="GPU",
            container_disk_in_gb=1000,
            volume_in_gb=volume_in_gb,
            support_public_ip=True,
            interruptible=False,
            global_networking=False,
            gpu_type_priority="custom",
            data_center_priority="availability",
            ports=["8000/http", "22/tcp"],
        ),
        r2=R2Settings(
            account_id="account",
            bucket="bucket",
            access_key_id="access",
            secret_access_key="secret",
        ),
        bootstrap=BootstrapSettings(
            auto_mirror_to_r2=True,
            completion_marker_dirname=".completion",
            completion_marker_suffix=".json",
        ),
        vllm=VLLMSettings(
            host="0.0.0.0",
            port=8000,
            served_model_name="glm-5.1-fp8",
            tensor_parallel_size=8,
            tool_call_parser="glm47",
            reasoning_parser="glm45",
            enable_auto_tool_choice=True,
        ),
        hf_token="hf-test",
    )


def test_model_slug_replaces_slashes() -> None:
    assert model_slug("zai-org/GLM-5.1-FP8") == "zai-org--GLM-5.1-FP8"


def test_pod_payload_omits_optional_fields_when_unset() -> None:
    payload = make_config().pod_payload()
    assert "volumeInGb" not in payload
    assert "containerRegistryAuthId" not in payload


def test_pod_payload_includes_optional_fields_when_present() -> None:
    payload = make_config(registry_auth="auth-123", volume_in_gb=20).pod_payload()
    assert payload["volumeInGb"] == 20
    assert payload["containerRegistryAuthId"] == "auth-123"


def test_build_vllm_command_matches_expected_serving_shape() -> None:
    command = build_vllm_command(make_config())
    assert command == [
        "vllm",
        "serve",
        "/workspace/models/zai-org--GLM-5.1-FP8",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--tensor-parallel-size",
        "8",
        "--served-model-name",
        "glm-5.1-fp8",
        "--tool-call-parser",
        "glm47",
        "--reasoning-parser",
        "glm45",
        "--enable-auto-tool-choice",
    ]
