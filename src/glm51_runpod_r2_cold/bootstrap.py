from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from huggingface_hub import snapshot_download

from .config import AppConfig
from .r2_storage import R2Storage


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
        return
    if path.exists():
        shutil.rmtree(path)


def _clean_incomplete_model_root(model_root: Path) -> None:
    if not model_root.exists():
        return
    for child in model_root.iterdir():
        _remove_path(child)


def _write_completion_marker(config: AppConfig, source: str, manifest: dict[str, Any] | None) -> None:
    marker_path = config.completion_marker_path
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "completed_at": datetime.now(UTC).isoformat(),
        "model_id": config.model_id,
        "model_root": str(config.model_root),
        "source": source,
        "manifest_key": config.manifest_key if manifest else None,
        "file_count": manifest.get("file_count") if manifest else None,
        "total_size_bytes": manifest.get("total_size_bytes") if manifest else None,
    }
    marker_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _remove_hf_metadata(model_root: Path) -> None:
    for path in (
        model_root / ".cache",
        model_root / ".cache" / "huggingface",
        model_root / ".cache" / "huggingface-home",
    ):
        if path.exists():
            _remove_path(path)


def _download_from_huggingface(config: AppConfig) -> None:
    model_root = config.model_root
    model_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    snapshot_download(
        repo_id=config.model_id,
        local_dir=str(model_root),
        token=config.hf_token,
        resume_download=True,
    )
    _remove_hf_metadata(model_root)


def _build_r2_client(config: AppConfig) -> R2Storage:
    return R2Storage(
        account_id=config.r2.account_id or "",
        bucket=config.r2.bucket or "",
        access_key_id=config.r2.access_key_id or "",
        secret_access_key=config.r2.secret_access_key or "",
    )


def ensure_model_ready(config: AppConfig) -> dict[str, Any]:
    model_root = config.model_root
    if config.completion_marker_path.exists() and model_root.is_dir() and any(model_root.iterdir()):
        return {"source": "local", "manifest": None, "model_root": str(config.model_root)}

    # Invalidate a stale marker before rebuilding, including if a retry fails
    # after leaving partial files in the model directory.
    config.completion_marker_path.unlink(missing_ok=True)
    _clean_incomplete_model_root(model_root)
    model_root.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] | None = None
    source = "huggingface"
    r2_client: R2Storage | None = None
    if all([config.r2.account_id, config.r2.bucket, config.r2.access_key_id, config.r2.secret_access_key]):
        r2_client = _build_r2_client(config)
        manifest = r2_client.read_json(config.manifest_key)

    if manifest:
        source = "r2"
        r2_client.download_manifest_tree(manifest, config.artifact_prefix, model_root)
    else:
        _download_from_huggingface(config)
        if r2_client and config.bootstrap.auto_mirror_to_r2:
            manifest = r2_client.upload_model_tree(
                source_root=model_root,
                manifest_key=config.manifest_key,
                artifact_prefix=config.artifact_prefix,
                model_id=config.model_id,
                exclude_paths=[config.completion_marker_path, model_root / ".cache"],
            )

    _write_completion_marker(config, source=source, manifest=manifest)
    return {"source": source, "manifest": manifest, "model_root": str(model_root)}

