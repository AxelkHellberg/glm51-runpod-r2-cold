from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from .constants import RUNPOD_API_BASE_URL, RUNPOD_PROXY_TEMPLATE


class RunpodAPI:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=RUNPOD_API_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RunpodAPI":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        if response.is_error:
            detail = response.text.strip()
            message = f"{response.status_code} error for {method} {path}"
            if detail:
                message = f"{message}: {detail}"
            raise httpx.HTTPStatusError(message, request=response.request, response=response)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def list_pods(self) -> list[dict[str, Any]]:
        return self._request("GET", "/pods")

    def get_pod(self, pod_id: str, *, timeout: float | None = None) -> dict[str, Any]:
        if timeout is not None:
            return self._request("GET", f"/pods/{pod_id}", timeout=timeout)
        return self._request("GET", f"/pods/{pod_id}")

    def create_pod(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/pods", json=payload)

    def stop_pod(self, pod_id: str) -> dict[str, Any]:
        return self._request("POST", f"/pods/{pod_id}/stop")

    def start_pod(self, pod_id: str) -> dict[str, Any]:
        return self._request("POST", f"/pods/{pod_id}/start")

    def delete_pod(self, pod_id: str) -> None:
        self._request("DELETE", f"/pods/{pod_id}")

    def list_container_registry_auths(self) -> list[dict[str, Any]]:
        return self._request("GET", "/containerregistryauth")

    def get_container_registry_auth(self, auth_id: str) -> dict[str, Any]:
        return self._request("GET", f"/containerregistryauth/{auth_id}")


def pod_matches_prefix(pod: dict[str, Any], prefix: str) -> bool:
    name = (pod.get("name") or "").strip()
    return bool(name) and name.startswith(prefix)


def pod_proxy_url(pod_id: str, port: int = 8000) -> str:
    return RUNPOD_PROXY_TEMPLATE.format(pod_id=pod_id, port=port)


def pod_state_snapshot(pod: dict[str, Any], proxy_port: int = 8000) -> dict[str, Any]:
    pod_id = pod["id"]
    return {
        "pod_id": pod_id,
        "name": pod.get("name"),
        "desired_status": pod.get("desiredStatus"),
        "cost_per_hr": pod.get("costPerHr"),
        "gpu_display_name": ((pod.get("machine") or {}).get("gpuDisplayName") or ((pod.get("gpu") or {}).get("displayName"))),
        "public_ip": pod.get("publicIp"),
        "proxy_base_url": pod_proxy_url(pod_id, port=proxy_port),
        "updated_at": datetime.now(UTC).isoformat(),
    }
