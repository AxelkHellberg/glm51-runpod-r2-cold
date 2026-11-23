from unittest.mock import Mock

import pytest

from glm51_runpod_r2_cold.r2_storage import R2Storage


def make_storage(keys: list[str]) -> R2Storage:
    storage = object.__new__(R2Storage)
    storage.bucket = "offline-test-bucket"
    storage.client = Mock()
    storage.client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": key} for key in keys]}
    ]
    return storage


def test_partial_deletion_raises_with_failed_key_and_reason() -> None:
    storage = make_storage(["cache/a", "cache/b"])
    storage.client.delete_objects.return_value = {
        "Deleted": [{"Key": "cache/a"}],
        "Errors": [{"Key": "cache/b", "Code": "AccessDenied", "Message": "Access denied"}],
    }

    with pytest.raises(RuntimeError, match=r"cache/b.*AccessDenied.*Access denied"):
        storage.delete_prefix("cache/")


def test_all_failed_deletions_are_reported() -> None:
    storage = make_storage(["cache/a", "cache/b"])
    storage.client.delete_objects.return_value = {
        "Errors": [
            {"Key": "cache/a", "Code": "AccessDenied", "Message": "Access denied"},
            {"Key": "cache/b", "Code": "InternalError", "Message": "Try again later"},
        ]
    }

    with pytest.raises(RuntimeError) as exc:
        storage.delete_prefix("cache/")

    message = str(exc.value)
    assert "cache/a" in message
    assert "AccessDenied" in message
    assert "cache/b" in message
    assert "InternalError" in message


def test_error_stops_later_batches() -> None:
    storage = make_storage([f"cache/{index}" for index in range(2001)])
    storage.client.delete_objects.side_effect = [
        {"Deleted": [{"Key": f"cache/{index}"} for index in range(1000)]},
        {"Errors": [{"Key": "cache/1000", "Code": "AccessDenied", "Message": "Access denied"}]},
        {"Deleted": [{"Key": "cache/2000"}]},
    ]

    with pytest.raises(RuntimeError, match="cache/1000"):
        storage.delete_prefix("cache/")

    assert storage.client.delete_objects.call_count == 2


def test_successful_deletion_respects_batch_limit() -> None:
    keys = [f"cache/{index}" for index in range(1001)]
    storage = make_storage(keys)
    storage.client.delete_objects.side_effect = [
        {"Deleted": [{"Key": key} for key in keys[:1000]]},
        {"Deleted": [{"Key": keys[1000]}], "Errors": []},
    ]

    assert storage.delete_prefix("cache/") == 1001
    calls = storage.client.delete_objects.call_args_list
    assert [len(call.kwargs["Delete"]["Objects"]) for call in calls] == [1000, 1]
    assert all(call.kwargs["Bucket"] == "offline-test-bucket" for call in calls)


def test_empty_prefix_does_not_send_delete_request() -> None:
    storage = make_storage([])

    assert storage.delete_prefix("cache/") == 0
    storage.client.delete_objects.assert_not_called()


def test_request_failure_is_preserved() -> None:
    storage = make_storage(["cache/a"])
    failure = OSError("offline connection failure")
    storage.client.delete_objects.side_effect = failure

    with pytest.raises(OSError) as exc:
        storage.delete_prefix("cache/")

    assert exc.value is failure
