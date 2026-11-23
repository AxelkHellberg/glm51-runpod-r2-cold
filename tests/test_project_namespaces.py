from unittest.mock import Mock

import pytest

from glm51_runpod_r2_cold.r2_storage import R2Storage
from glm51_runpod_r2_cold.runpod_api import pod_matches_prefix
from glm51_runpod_r2_cold.workflow import find_project_pods, generate_pod_name


def test_project_pod_selection_excludes_names_in_neighboring_namespaces() -> None:
    prefix = "example-r2-cold"
    pods = [
        {"id": "configured", "name": prefix},
        {"id": "generated", "name": generate_pod_name(prefix)},
        {"id": "neighbor", "name": "example-r2-colder-20261123210000"},
        {"id": "similar", "name": "example-r2-cold2-20261123210000"},
        {"id": "missing"},
    ]

    assert [pod["id"] for pod in find_project_pods(pods, prefix)] == ["configured", "generated"]


@pytest.mark.parametrize("prefix", ["", " ", "\t\n"])
def test_blank_pod_prefix_cannot_select_any_pod(prefix: str) -> None:
    assert not pod_matches_prefix({"name": "example-r2-cold-20261123210000"}, prefix)


@pytest.mark.parametrize("prefix", ["example/r2-cold", "example/r2-cold/", "example/r2-cold///"])
def test_r2_cleanup_deletes_only_the_requested_directory(prefix: str) -> None:
    keys = [
        "example/r2-cold/model/weights.bin",
        "example/r2-cold/model/manifest.json",
        "example/r2-colder/model/weights.bin",
        "example/r2-cold2/model/weights.bin",
        "example/r2-cold-backup/model/weights.bin",
        "example/r2-cold.json",
    ]
    storage = object.__new__(R2Storage)
    storage.bucket = "offline-test-bucket"
    storage.client = Mock()
    paginator = storage.client.get_paginator.return_value
    # S3 Prefix is a raw string prefix, not a directory selector.
    paginator.paginate.side_effect = lambda **kwargs: [
        {"Contents": [{"Key": key} for key in keys if key.startswith(kwargs["Prefix"])]}
    ]
    storage.client.delete_objects.return_value = {}

    assert storage.delete_prefix(prefix) == 2
    assert storage.client.delete_objects.call_args.kwargs["Delete"]["Objects"] == [
        {"Key": "example/r2-cold/model/weights.bin"},
        {"Key": "example/r2-cold/model/manifest.json"},
    ]


@pytest.mark.parametrize("prefix", ["", " ", "\t\n", "/", "///", " /// "])
def test_r2_cleanup_rejects_blank_or_root_prefix_before_any_client_call(prefix: str) -> None:
    storage = object.__new__(R2Storage)
    storage.bucket = "offline-test-bucket"
    storage.client = Mock()
    storage.client.get_paginator.return_value.paginate.return_value = []

    with pytest.raises(ValueError, match="nonempty directory"):
        storage.delete_prefix(prefix)

    assert storage.client.mock_calls == []
