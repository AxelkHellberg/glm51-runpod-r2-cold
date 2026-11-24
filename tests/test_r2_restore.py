from pathlib import Path
from unittest.mock import Mock

import pytest

from glm51_runpod_r2_cold import bootstrap
from glm51_runpod_r2_cold.r2_storage import R2Storage
from test_config_and_server import make_config


def make_storage(payloads: dict[str, bytes]) -> R2Storage:
    storage = R2Storage.__new__(R2Storage)
    storage.bucket = "offline-test-bucket"
    storage.client = Mock()

    def download_file(bucket: str, key: str, destination: str) -> None:
        assert bucket == storage.bucket
        Path(destination).write_bytes(payloads[key])

    storage.client.download_file.side_effect = download_file
    return storage


@pytest.mark.parametrize("actual", [b"x", b"too many bytes"])
def test_restore_rejects_incorrect_file_size(tmp_path: Path, actual: bytes) -> None:
    storage = make_storage({"model/files/weights.bin": actual})
    manifest = {"files": [{"relative_path": "weights.bin", "size_bytes": 8}]}

    with pytest.raises(RuntimeError, match=r"weights\.bin.*expected 8 bytes"):
        storage.download_manifest_tree(manifest, "model/files", tmp_path)


def test_restore_checks_nested_and_empty_files(tmp_path: Path) -> None:
    storage = make_storage({"model/files/nested/weights.bin": b"weights", "model/files/empty": b""})
    manifest = {"files": [
        {"relative_path": "nested/weights.bin", "size_bytes": 7},
        {"relative_path": "empty", "size_bytes": 0},
    ]}

    storage.download_manifest_tree(manifest, "model/files", tmp_path)

    assert (tmp_path / "nested/weights.bin").read_bytes() == b"weights"
    assert (tmp_path / "empty").read_bytes() == b""
    assert storage.client.download_file.call_count == 2


@pytest.mark.parametrize("size", [None, -1, 1.5, "8", True])
def test_invalid_size_is_rejected_before_any_download(tmp_path: Path, size: object) -> None:
    storage = make_storage({"model/files/config.json": b"{}", "model/files/weights.bin": b"weights"})
    manifest = {"files": [
        {"relative_path": "config.json", "size_bytes": 2},
        {"relative_path": "weights.bin", "size_bytes": size},
    ]}

    with pytest.raises(ValueError, match=r"weights\.bin.*size_bytes"):
        storage.download_manifest_tree(manifest, "model/files", tmp_path)

    storage.client.download_file.assert_not_called()


@pytest.mark.parametrize("manifest", [{}, {"files": []}])
def test_empty_manifest_is_rejected(tmp_path: Path, manifest: dict) -> None:
    storage = make_storage({})

    with pytest.raises(ValueError, match="nonempty files list"):
        storage.download_manifest_tree(manifest, "model/files", tmp_path)

    storage.client.download_file.assert_not_called()


def test_incomplete_restore_does_not_mark_model_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = make_config()
    config.model_root_base = tmp_path / "models"
    storage = make_storage({f"{config.artifact_prefix}/weights.bin": b"x"})
    storage.read_json = Mock(return_value={"files": [{"relative_path": "weights.bin", "size_bytes": 8}]})
    monkeypatch.setattr(bootstrap, "_build_r2_client", lambda config: storage)
    download = Mock()
    monkeypatch.setattr(bootstrap, "_download_from_huggingface", download)

    with pytest.raises(RuntimeError, match=r"weights\.bin.*expected 8 bytes"):
        bootstrap.ensure_model_ready(config)

    assert not config.completion_marker_path.exists()
    download.assert_not_called()
