from pathlib import Path
from unittest.mock import Mock

import pytest

from glm51_runpod_r2_cold import bootstrap
from glm51_runpod_r2_cold.config import AppConfig
from test_config_and_server import make_config


def local_config(tmp_path: Path) -> AppConfig:
    config = make_config()
    config.model_root_base = tmp_path / "models"
    config.r2.account_id = None
    return config


def write_marker(config: AppConfig) -> None:
    config.completion_marker_path.parent.mkdir(parents=True, exist_ok=True)
    config.completion_marker_path.write_text("{}\n", encoding="utf-8")


@pytest.mark.parametrize("empty_root", [False, True], ids=["missing-root", "empty-root"])
def test_stale_completion_marker_rebuilds_missing_model(tmp_path, monkeypatch, empty_root):
    config = local_config(tmp_path)
    write_marker(config)
    if empty_root:
        config.model_root.mkdir(parents=True)

    def download(current_config):
        assert not current_config.completion_marker_path.exists()
        (current_config.model_root / "config.json").write_text("{}\n", encoding="utf-8")

    download_mock = Mock(side_effect=download)
    monkeypatch.setattr(bootstrap, "_download_from_huggingface", download_mock)
    result = bootstrap.ensure_model_ready(config)

    assert result["source"] == "huggingface"
    download_mock.assert_called_once_with(config)
    assert config.completion_marker_path.exists()
    assert (config.model_root / "config.json").exists()


def test_valid_local_completion_reuses_populated_model_root(tmp_path, monkeypatch):
    config = local_config(tmp_path)
    config.model_root.mkdir(parents=True)
    model_config = config.model_root / "config.json"
    model_config.write_text("{}\n", encoding="utf-8")
    write_marker(config)
    download_mock = Mock(side_effect=AssertionError("No download should occur"))
    monkeypatch.setattr(bootstrap, "_download_from_huggingface", download_mock)

    result = bootstrap.ensure_model_ready(config)

    assert result["source"] == "local"
    assert model_config.exists()
    download_mock.assert_not_called()


def test_failed_rebuild_invalidates_stale_marker_before_partial_download(tmp_path, monkeypatch):
    config = local_config(tmp_path)
    write_marker(config)

    def fail_download(current_config):
        assert not current_config.completion_marker_path.exists()
        (current_config.model_root / "partial-shard").write_text("incomplete", encoding="utf-8")
        raise RuntimeError("download interrupted")

    monkeypatch.setattr(bootstrap, "_download_from_huggingface", fail_download)
    with pytest.raises(RuntimeError, match="download interrupted"):
        bootstrap.ensure_model_ready(config)
    assert not config.completion_marker_path.exists()

    def finish_download(current_config):
        assert not (current_config.model_root / "partial-shard").exists()
        (current_config.model_root / "config.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(bootstrap, "_download_from_huggingface", finish_download)
    assert bootstrap.ensure_model_ready(config)["source"] == "huggingface"
    assert config.completion_marker_path.exists()


def test_unmarked_populated_model_root_still_rebuilds(tmp_path, monkeypatch):
    config = local_config(tmp_path)
    config.model_root.mkdir(parents=True)
    partial = config.model_root / "partial-shard"
    partial.write_text("incomplete", encoding="utf-8")

    def download(current_config):
        assert not partial.exists()
        (current_config.model_root / "config.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(bootstrap, "_download_from_huggingface", download)
    assert bootstrap.ensure_model_ready(config)["source"] == "huggingface"


def test_stale_marker_can_restore_model_from_r2(tmp_path, monkeypatch):
    config = make_config()
    config.model_root_base = tmp_path / "models"
    write_marker(config)
    manifest = {"files": [{"relative_path": "config.json"}]}
    r2_client = Mock()
    r2_client.read_json.return_value = manifest

    def restore(current_manifest, artifact_prefix, target_root):
        assert not config.completion_marker_path.exists()
        (target_root / "config.json").write_text("{}\n", encoding="utf-8")

    r2_client.download_manifest_tree.side_effect = restore
    monkeypatch.setattr(bootstrap, "_build_r2_client", Mock(return_value=r2_client))
    monkeypatch.setattr(
        bootstrap,
        "_download_from_huggingface",
        Mock(side_effect=AssertionError("No download should occur")),
    )

    result = bootstrap.ensure_model_ready(config)

    assert result["source"] == "r2"
    r2_client.download_manifest_tree.assert_called_once_with(manifest, config.artifact_prefix, config.model_root)
    assert config.completion_marker_path.exists()
