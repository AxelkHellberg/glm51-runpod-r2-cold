from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import ACTIVE_POD_STATE_FILENAME, LIVE_ACTION_ACK_FILENAME, LIVE_ENDPOINT_STATE_FILENAME
from .paths import ensure_state_dir


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def active_pod_state_path() -> Path:
    return ensure_state_dir() / ACTIVE_POD_STATE_FILENAME


def endpoint_state_path() -> Path:
    return ensure_state_dir() / LIVE_ENDPOINT_STATE_FILENAME


def live_action_ack_path() -> Path:
    return ensure_state_dir() / LIVE_ACTION_ACK_FILENAME


def load_active_pod_state() -> dict[str, Any] | None:
    return _read_json(active_pod_state_path())


def write_active_pod_state(payload: dict[str, Any]) -> None:
    _write_json(active_pod_state_path(), payload)


def clear_active_pod_state() -> None:
    active_pod_state_path().unlink(missing_ok=True)


def load_endpoint_state() -> dict[str, Any] | None:
    return _read_json(endpoint_state_path())


def write_endpoint_state(payload: dict[str, Any]) -> None:
    _write_json(endpoint_state_path(), payload)


def clear_endpoint_state() -> None:
    endpoint_state_path().unlink(missing_ok=True)


def write_live_action_ack(value: str) -> None:
    path = live_action_ack_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.strip() + "\n", encoding="utf-8")


def read_live_action_ack() -> str | None:
    path = live_action_ack_path()
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def clear_live_action_ack() -> None:
    live_action_ack_path().unlink(missing_ok=True)

