import httpx
import pytest

from callprobe.client import ChatClient

OK_BODY = {
    "choices": [{"message": {"content": "hi"}}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
}


def _client(handler, retries=3):
    transport = httpx.MockTransport(handler)
    client = ChatClient("http://fake/v1", transport=transport, retries=retries)
    client._backoff = lambda attempt, retry_after: 0.0  # skip real sleeps in tests
    return client


def test_retries_on_500_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json=OK_BODY)

    client = _client(handler)
    completion = client.complete("m", [], [])
    assert calls["n"] == 3
    assert completion.error is None
    assert completion.content == "hi"


def test_retries_on_429_then_gives_up():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, json={"error": "slow down"})

    client = _client(handler, retries=2)
    completion = client.complete("m", [], [])
    assert calls["n"] == 3  # 1 initial attempt + 2 retries
    assert completion.error is not None


def test_does_not_retry_other_4xx():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    client = _client(handler, retries=3)
    completion = client.complete("m", [], [])
    assert calls["n"] == 1
    assert completion.error is not None


def test_retries_on_connection_error():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json=OK_BODY)

    client = _client(handler)
    completion = client.complete("m", [], [])
    assert calls["n"] == 2
    assert completion.error is None


def test_honors_retry_after_header():
    seen = {}

    def handler(request):
        seen["n"] = seen.get("n", 0) + 1
        if seen["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={})
        return httpx.Response(200, json=OK_BODY)

    transport = httpx.MockTransport(handler)
    client = ChatClient("http://fake/v1", transport=transport, retries=1)
    waits = []
    client._backoff = lambda attempt, retry_after: waits.append(retry_after) or 0.0
    completion = client.complete("m", [], [])
    assert completion.error is None
    assert waits == ["0"]


@pytest.mark.parametrize("body", [
    [], None, {}, {"choices": []}, {"choices": [None]},
    {"choices": [{"message": "private response text"}]},
    {"choices": [{"message": {}}], "usage": {"prompt_tokens": "invalid"}},
    {"choices": [{"message": {"tool_calls": ["invalid"]}}]},
    {"choices": [{"message": {"content": 42}}]},
    {"choices": [{"message": {"tool_calls": {"bad": "shape"}}} ]},
])
def test_malformed_success_response_is_request_error_and_next_request_survives(body):
    responses = iter([body, OK_BODY])
    calls = []
    def handler(request):
        calls.append(request)
        import json
        return httpx.Response(200, content=json.dumps(next(responses)))
    client = _client(handler)
    try:
        malformed = client.complete("m", [], [])
        assert malformed.error.startswith("invalid chat completion response")
        assert "private response text" not in malformed.error
        assert malformed.calls == []
        assert client.complete("m", [], []).content == "hi"
        assert len(calls) == 2  # Malformed payloads are not transient retries.
    finally:
        client.close()


@pytest.mark.parametrize("retry_after", ["inf", "-inf", "NaN", "1e999", "invalid"])
def test_invalid_retry_after_uses_finite_backoff(monkeypatch, retry_after):
    responses = iter([
        httpx.Response(429, headers={"Retry-After": retry_after}, json={}),
        httpx.Response(200, json=OK_BODY),
    ])
    client = ChatClient("http://fake/v1", retries=1,
                        transport=httpx.MockTransport(lambda request: next(responses)))
    waits = []
    monkeypatch.setattr("callprobe.client.random.uniform", lambda low, high: 0.125)
    monkeypatch.setattr("callprobe.client.time.sleep", waits.append)
    try:
        assert client.complete("m", [], []).error is None
        assert waits == [0.125]
    finally:
        client.close()
