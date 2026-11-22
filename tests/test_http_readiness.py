from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx
import pytest

from glm51_runpod_r2_cold import server


@dataclass
class Clock:
    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(time, "sleep", clock.sleep)
    return clock


def install_client(monkeypatch, clock, responses):
    calls = []
    pending = iter(responses)

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, **kwargs):
            calls.append((url, kwargs.get("timeout")))
            delay, result = next(pending)
            clock.now += delay
            if isinstance(result, Exception):
                raise result
            return httpx.Response(
                result,
                request=httpx.Request("GET", url),
                json={"data": [{"id": "glm-5.1-fp8"}]},
            )

    monkeypatch.setattr(server.httpx, "Client", Client)
    return calls


def test_request_time_consumes_polling_budget(monkeypatch, clock):
    calls = install_client(monkeypatch, clock, [(4, 503), (4, 503)])

    with pytest.raises(RuntimeError, match="did not become ready"):
        server.wait_for_http_ready("https://offline.invalid", timeout_seconds=5, interval_seconds=3)

    assert clock.now == 5
    assert clock.sleeps == [1]
    assert len(calls) == 1


def test_each_request_receives_its_remaining_budget(monkeypatch, clock):
    calls = install_client(monkeypatch, clock, [(2, 200), (1, 200)])

    result = server.wait_for_http_ready("https://offline.invalid", timeout_seconds=5)

    assert result == {"data": [{"id": "glm-5.1-fp8"}]}
    assert calls == [
        ("https://offline.invalid/health", 5),
        ("https://offline.invalid/v1/models", 3),
    ]
    assert clock.sleeps == []


def test_request_phase_budget_keeps_existing_thirty_second_limit(monkeypatch, clock):
    calls = install_client(monkeypatch, clock, [(0, 200), (0, 200)])

    server.wait_for_http_ready("https://offline.invalid", timeout_seconds=100)

    assert [timeout for _, timeout in calls] == [30, 30]


def test_late_health_success_does_not_start_models_request(monkeypatch, clock):
    calls = install_client(monkeypatch, clock, [(6, 200), (0, 200)])

    with pytest.raises(RuntimeError, match="did not become ready"):
        server.wait_for_http_ready("https://offline.invalid", timeout_seconds=5)

    assert len(calls) == 1
    assert clock.sleeps == []


def test_models_success_at_deadline_is_not_reported_ready(monkeypatch, clock):
    calls = install_client(monkeypatch, clock, [(2, 200), (3, 200)])

    with pytest.raises(RuntimeError, match="did not become ready"):
        server.wait_for_http_ready("https://offline.invalid", timeout_seconds=5)

    assert len(calls) == 2
    assert clock.sleeps == []


def test_retry_can_succeed_within_remaining_budget(monkeypatch, clock):
    calls = install_client(monkeypatch, clock, [(1, 503), (1, 200), (1, 200)])

    result = server.wait_for_http_ready("https://offline.invalid", timeout_seconds=8, interval_seconds=2)

    assert result["data"][0]["id"] == "glm-5.1-fp8"
    assert clock.now == 5
    assert clock.sleeps == [2]
    assert [timeout for _, timeout in calls] == [8, 5, 4]


def test_final_transport_error_remains_the_timeout_cause(monkeypatch, clock):
    error = httpx.ConnectError("offline fixture")
    install_client(monkeypatch, clock, [(1, error)])

    with pytest.raises(RuntimeError, match="offline fixture") as raised:
        server.wait_for_http_ready("https://offline.invalid", timeout_seconds=2, interval_seconds=3)

    assert raised.value.__cause__ is error
    assert clock.now == 2


@pytest.mark.parametrize("argument", ["timeout_seconds", "interval_seconds"])
@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_invalid_budgets_are_rejected_before_constructing_a_client(monkeypatch, argument, value):
    def unexpected_client(**kwargs):
        raise AssertionError("invalid parameters must not create a client")

    monkeypatch.setattr(server.httpx, "Client", unexpected_client)
    with pytest.raises(ValueError, match=argument):
        server.wait_for_http_ready("https://offline.invalid", **{argument: value})
