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


@pytest.mark.parametrize("version", [None, 42, {}, ["0.1"], True, "", "  "])
def test_version_probe_does_not_record_malformed_metadata(monkeypatch, version):
    from callprobe.client import probe_server_version
    monkeypatch.setattr("callprobe.client.httpx.get", lambda *args, **kwargs:
                        httpx.Response(200, json={"version": version},
                                       request=httpx.Request("GET", "http://fake/api/version")))
    assert probe_server_version("http://fake/v1") == (None, None)


def test_version_probe_prefers_ollama_and_stops(monkeypatch):
    from callprobe.client import probe_server_version
    urls = []
    def get(url, **kwargs):
        urls.append(url)
        return httpx.Response(200, json={'version': '0.34.2'}, request=httpx.Request('GET', url))
    monkeypatch.setattr('callprobe.client.httpx.get', get)
    assert probe_server_version('http://localhost:11434/v1') == ('ollama', '0.34.2')
    assert urls == ['http://localhost:11434/api/version']


def test_version_probe_recognizes_llama_cpp_properties(monkeypatch):
    from callprobe.client import probe_server_version
    urls = []
    def get(url, **kwargs):
        urls.append(url)
        assert kwargs['timeout'] == 0.25
        body = {'build_info': 'b11339-81e39ad34', 'default_generation_settings': {},
                'chat_template': '{{ messages }}', 'total_slots': 1,
                'model_path': '/private/model.gguf'}
        return httpx.Response(404 if url.endswith('/api/version') else 200,
                              json=body, request=httpx.Request('GET', url))
    monkeypatch.setattr('callprobe.client.httpx.get', get)
    assert probe_server_version('http://localhost:18080/v1', timeout=0.25) == ('llama.cpp', 'b11339-81e39ad34')
    assert urls == ['http://localhost:18080/api/version', 'http://localhost:18080/props']


@pytest.mark.parametrize('change', [
    {'build_info': 'an arbitrary server'}, {'build_info': None}, {'build_info': 42},
    {'default_generation_settings': []}, {'chat_template': None},
    {'total_slots': True}, {'total_slots': 0}, {'total_slots': '1'},
])
def test_version_probe_does_not_guess_from_invalid_llama_properties(monkeypatch, change):
    from callprobe.client import probe_server_version
    props = {'build_info': 'b11339-81e39ad34', 'default_generation_settings': {},
             'chat_template': '{{ messages }}', 'total_slots': 1, **change}
    def get(url, **kwargs):
        return httpx.Response(200, json={} if url.endswith('/api/version') else props,
                              request=httpx.Request('GET', url))
    monkeypatch.setattr('callprobe.client.httpx.get', get)
    assert probe_server_version('http://fake/v1') == (None, None)


def test_version_probe_unavailable_metadata_is_nonfatal(monkeypatch):
    from callprobe.client import probe_server_version
    def get(url, **kwargs):
        raise httpx.ReadTimeout('metadata unavailable')
    monkeypatch.setattr('callprobe.client.httpx.get', get)
    assert probe_server_version('http://fake/v1') == (None, None)


def _with_field(field, value):
    body = {'choices': [{'message': {}}]}
    if field == 'finish_reason':
        body['choices'][0][field] = value
    elif field == 'usage':
        body[field] = value
    elif field == 'arguments':
        body['choices'][0]['message']['tool_calls'] = [
            {'function': {'name': 'test_tool', 'arguments': value}},
        ]
    else:
        body['choices'][0]['message'][field] = value
    return body


@pytest.mark.parametrize('field', ['content', 'reasoning', 'reasoning_content',
                                    'finish_reason', 'usage', 'arguments'])
@pytest.mark.parametrize('value', [False, 0, []])
def test_falsey_invalid_provider_values_are_request_errors(field, value):
    from callprobe.client import parse_completion
    from callprobe.models import Bundle, Expectation, Task
    from callprobe.scoring import score
    body = _with_field(field, value)
    with pytest.raises(ValueError):
        parse_completion(body, 0)
    client = _client(lambda request: httpx.Response(200, json=body))
    try:
        completion = client.complete('m', [], [])
    finally:
        client.close()
    assert completion.error.startswith('invalid chat completion response')
    task = Task(id='abstain', category='abstain', bundle='b', messages=[],
                expect=Expectation(type='no_call'))
    result = score(task, Bundle(name='b', tools=[]), completion, model='m', pad=0, repeat=0)
    assert result.error is not None and not result.success


@pytest.mark.parametrize('field', ['content', 'reasoning', 'reasoning_content', 'finish_reason'])
def test_empty_object_text_is_not_an_abstention(field):
    from callprobe.client import parse_completion
    with pytest.raises(ValueError):
        parse_completion(_with_field(field, {}), 0)


def test_invalid_shadowed_reasoning_is_still_rejected():
    from callprobe.client import parse_completion
    for first, second in [('valid', False), (False, 'valid')]:
        body = {'choices': [{'message': {'reasoning': first, 'reasoning_content': second}}]}
        with pytest.raises(ValueError):
            parse_completion(body, 0)


@pytest.mark.parametrize('value', [None, ''])
def test_null_and_empty_text_remain_compatible(value):
    from callprobe.client import parse_completion
    body = {'choices': [{'message': {'content': value, 'reasoning': value,
                                     'reasoning_content': value}, 'finish_reason': value}],
            'usage': None}
    completion = parse_completion(body, 12.5)
    assert completion.content == completion.reasoning == completion.finish_reason == ''
    assert completion.prompt_tokens == completion.completion_tokens == 0
    assert completion.latency_ms == 12.5 and completion.error is None


@pytest.mark.parametrize('primary,secondary,expected', [
    ('primary', 'secondary', 'primary'), ('', 'secondary', 'secondary'),
    (None, 'secondary', 'secondary'),
])
def test_reasoning_precedence_is_unchanged(primary, secondary, expected):
    from callprobe.client import parse_completion
    body = {'choices': [{'message': {'reasoning': primary, 'reasoning_content': secondary}}]}
    assert parse_completion(body, 0).reasoning == expected


@pytest.mark.parametrize('arguments', [None, '', '{}', {}])
def test_empty_arguments_supported_representations_remain_compatible(arguments):
    from callprobe.client import parse_completion
    completion = parse_completion(_with_field('arguments', arguments), 0)
    assert completion.calls[0].arguments == {}
    assert completion.calls[0].parse_error is None


def test_malformed_json_arguments_still_produce_call_parse_failure():
    from callprobe.client import parse_completion
    completion = parse_completion(_with_field('arguments', '{broken'), 0)
    assert completion.error is None
    assert completion.calls[0].parse_error
    assert completion.calls[0].raw_arguments == '{broken'


def test_invalid_text_does_not_retry_or_leak_and_next_response_succeeds():
    responses = iter([_with_field('content', {'PRIVATE_KEY': 'PRIVATE_VALUE'}), OK_BODY])
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=next(responses))
    client = _client(handler)
    try:
        completion = client.complete('m', [], [])
        assert completion.error and 'PRIVATE' not in completion.error
        assert client.complete('m', [], []).content == 'hi'
        assert len(requests) == 2
    finally:
        client.close()
