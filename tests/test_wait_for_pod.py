import argparse
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from glm51_runpod_r2_cold.runpod_api import RunpodAPI


@pytest.fixture
def wait_script():
    path = Path(__file__).parents[1] / "scripts" / "wait_for_pod.py"
    spec = importlib.util.spec_from_file_location("wait_for_pod_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Clock:
    def __init__(self):
        self.elapsed = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.elapsed += seconds


def arrange_wait(monkeypatch, module, *, timeout, interval, responses, endpoint_cost=0):
    clock = Clock()
    requests = []
    endpoint_calls = []
    saved_endpoints = []
    responses = iter(responses)

    class FakeAPI:
        def __init__(self, api_key):
            assert api_key == "fake-key"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get_pod(self, pod_id, **kwargs):
            requests.append((pod_id, kwargs))
            status, cost = next(responses)
            clock.elapsed += cost
            return {"id": pod_id, "desiredStatus": status}

    def wait_for_http_ready(base_url, timeout_seconds):
        endpoint_calls.append((base_url, timeout_seconds))
        clock.elapsed += endpoint_cost
        return {"data": [{"id": "test-model"}]}

    monkeypatch.setattr(module, "parse_args", lambda: argparse.Namespace(
        timeout_seconds=timeout, poll_interval_seconds=interval,
    ))
    monkeypatch.setattr(module, "time", clock)
    monkeypatch.setattr(module, "RunpodAPI", FakeAPI)
    monkeypatch.setattr(module, "load_app_config", lambda: SimpleNamespace(
        runpod=SimpleNamespace(api_key="fake-key"), vllm=SimpleNamespace(port=8000),
    ))
    monkeypatch.setattr(module, "load_active_pod_state", lambda: {
        "pod_id": "test-pod", "proxy_base_url": "https://example.invalid",
    })
    monkeypatch.setattr(module, "write_active_pod_state", lambda state: None)
    monkeypatch.setattr(module, "write_endpoint_state", saved_endpoints.append)
    monkeypatch.setattr(module, "print_json", lambda state: None)
    monkeypatch.setattr(module, "wait_for_http_ready", wait_for_http_ready)
    return clock, requests, endpoint_calls, saved_endpoints


@pytest.mark.parametrize("timeout,request_timeout", [(3, 3), (100, 30)])
def test_endpoint_receives_only_budget_left_after_pod_request(
    monkeypatch, wait_script, timeout, request_timeout,
):
    clock, requests, endpoint_calls, saved = arrange_wait(
        monkeypatch, wait_script, timeout=timeout, interval=20,
        responses=[("RUNNING", 0.75)], endpoint_cost=1,
    )

    wait_script.main()

    assert requests == [("test-pod", {"timeout": request_timeout})]
    assert endpoint_calls == [("https://example.invalid", timeout - 0.75)]
    assert len(saved) == 1
    assert clock.elapsed == 1.75


def test_slow_pod_request_cannot_begin_endpoint_polling_after_expiry(monkeypatch, wait_script):
    _, _, endpoint_calls, saved = arrange_wait(
        monkeypatch, wait_script, timeout=10, interval=2, responses=[("RUNNING", 11)],
    )

    with pytest.raises(SystemExit, match="Timed out"):
        wait_script.main()

    assert endpoint_calls == []
    assert saved == []


def test_pod_requests_consume_the_total_polling_budget(monkeypatch, wait_script):
    clock, requests, endpoint_calls, saved = arrange_wait(
        monkeypatch, wait_script, timeout=10, interval=4,
        responses=[("CREATED", 3)] * 4,
    )

    with pytest.raises(SystemExit, match="Timed out"):
        wait_script.main()

    assert requests == [("test-pod", {"timeout": 10}), ("test-pod", {"timeout": 3})]
    assert clock.elapsed == 10
    assert clock.sleeps == [4]
    assert endpoint_calls == []
    assert saved == []


def test_final_sleep_is_capped_and_no_pod_request_starts_at_deadline(monkeypatch, wait_script):
    clock, requests, _, _ = arrange_wait(
        monkeypatch, wait_script, timeout=5, interval=20,
        responses=[("CREATED", 1), ("RUNNING", 0)],
    )

    with pytest.raises(SystemExit, match="Timed out"):
        wait_script.main()

    assert len(requests) == 1
    assert clock.sleeps == [4]
    assert clock.elapsed == 5


def test_exact_deadline_does_not_allow_another_pod_request(monkeypatch, wait_script):
    _, requests, endpoint_calls, _ = arrange_wait(
        monkeypatch, wait_script, timeout=10, interval=10,
        responses=[("CREATED", 0), ("RUNNING", 0)],
    )

    with pytest.raises(SystemExit, match="Timed out"):
        wait_script.main()

    assert len(requests) == 1
    assert endpoint_calls == []


def test_late_endpoint_response_is_not_recorded_as_ready(monkeypatch, wait_script):
    _, _, _, saved = arrange_wait(
        monkeypatch, wait_script, timeout=10, interval=2,
        responses=[("RUNNING", 1)], endpoint_cost=10,
    )

    with pytest.raises(SystemExit, match="Timed out"):
        wait_script.main()

    assert saved == []


@pytest.mark.parametrize("option", ["--timeout-seconds", "--poll-interval-seconds"])
@pytest.mark.parametrize("value", ["0", "-1"])
def test_cli_rejects_nonpositive_timing_values(monkeypatch, wait_script, option, value):
    monkeypatch.setattr("sys.argv", ["wait_for_pod.py", option, value])

    with pytest.raises(SystemExit) as exc:
        wait_script.parse_args()

    assert exc.value.code == 2


@pytest.mark.parametrize("override,expected", [(2.5, 2.5), (None, 7.0)])
def test_get_pod_uses_override_or_existing_client_timeout(monkeypatch, override, expected):
    requests = []
    client_class = httpx.Client

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "test-pod"})

    def make_client(**kwargs):
        return client_class(**kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr("glm51_runpod_r2_cold.runpod_api.httpx.Client", make_client)
    with RunpodAPI("fake-key", timeout=7.0) as api:
        if override is None:
            pod = api.get_pod("test-pod")
        else:
            pod = api.get_pod("test-pod", timeout=override)

    assert pod == {"id": "test-pod"}
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/pods/test-pod")
    assert requests[0].extensions["timeout"] == {
        "connect": expected, "read": expected, "write": expected, "pool": expected,
    }
