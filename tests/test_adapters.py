import copy
from pathlib import Path

import pytest

from callprobe.adapters import parse_ollama_completion
from callprobe.loader import load_suite
from callprobe.models import RunConfig
from callprobe.recording_io import read_recordings, recordings_to_json
from callprobe.recordings import RecordedCompletion, score_recordings


def response():
    return {
        'model': 'native-model', 'done': True, 'done_reason': 'stop',
        'message': {
            'role': 'assistant', 'content': 'Checking.', 'thinking': 'Recorded thought.',
            'tool_calls': [{'function': {
                'name': 'get_order_status', 'arguments': {'order_id': 'ORD-448120'},
            }}],
        },
        'prompt_eval_count': 23, 'eval_count': 9,
        'total_duration': 999000000, 'load_duration': 200000000,
    }


def test_native_fields_and_all_calls_preserved_without_mutation(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, 'Client', lambda *a, **k: pytest.fail('no network'))
    body = response()
    body['message']['tool_calls'] *= 2
    before = copy.deepcopy(body)
    result = parse_ollama_completion(body, latency_ms=123.5)
    assert len(result.calls) == 2
    assert all(c.name == 'get_order_status' for c in result.calls)
    assert result.calls[0].arguments == {'order_id': 'ORD-448120'}
    assert result.content == 'Checking.'
    assert result.reasoning == 'Recorded thought.'
    assert (result.prompt_tokens, result.completion_tokens) == (23, 9)
    assert result.finish_reason == 'stop'
    assert result.latency_ms == 123.5  # not the server's total_duration
    assert result.raw is body
    assert body == before


@pytest.mark.parametrize('calls', [None, []])
def test_native_abstention_and_missing_usage(calls):
    result = parse_ollama_completion({
        'done': True, 'message': {'role': 'assistant', 'content': 'No action.', 'tool_calls': calls},
    })
    assert result.calls == []
    assert result.content == 'No action.'
    assert (result.prompt_tokens, result.completion_tokens, result.latency_ms) == (0, 0, 0)


@pytest.mark.parametrize('change', [
    lambda b: b.update(done=False),
    lambda b: b.update(done=1),
    lambda b: b.pop('done'),
    lambda b: b.update(error='private-provider-error'),
    lambda b: b.update(error=''),
    lambda b: b.update(message=[]),
    lambda b: b['message'].update(role='user'),
    lambda b: b['message'].update(content=False),
    lambda b: b['message'].update(thinking=[]),
    lambda b: b.update(done_reason=False),
    lambda b: b.update(done_reason='load'),
    lambda b: b.update(done_reason='unload'),
    lambda b: b.update(prompt_eval_count=-1),
    lambda b: b.update(eval_count=True),
    lambda b: b['message'].update(tool_calls={}),
    lambda b: b['message'].update(tool_calls=[None]),
    lambda b: b['message']['tool_calls'][0].update(function=[]),
    lambda b: b['message']['tool_calls'][0]['function'].update(arguments='{}'),
    lambda b: b['message']['tool_calls'][0]['function'].update(arguments=None),
    lambda b: b['message']['tool_calls'][0]['function'].update(name=False),
])
def test_malformed_native_responses_are_generic_errors(change):
    body = response()
    change(body)
    with pytest.raises(ValueError, match='^invalid completed Ollama chat response$'):
        parse_ollama_completion(body)


@pytest.mark.parametrize('latency', [-1, float('nan'), float('inf'), True, '12'])
def test_invalid_caller_latency_rejected(latency):
    with pytest.raises(ValueError, match='^invalid completed Ollama chat response$'):
        parse_ollama_completion(response(), latency_ms=latency)


@pytest.mark.parametrize('finish_reason', ['stop', 'length'])
@pytest.mark.parametrize('call_count', [0, 1, 2])
def test_native_decisions_survive_recording_export_and_replay(tmp_path, finish_reason, call_count):
    suite_path = Path(__file__).resolve().parents[1] / 'src/callprobe/suites/core'
    suite = load_suite(suite_path)
    config = RunConfig(model='native-model', endpoint='recorded://local', suite=str(suite_path),
                       pads=[0], repeats=1, temperature=0, max_tokens=4096)
    body = response()
    body['done_reason'] = finish_reason
    body['message']['tool_calls'] *= call_count
    record = RecordedCompletion('select-status-direct', parse_ollama_completion(body, 123.5))
    direct = score_recordings(suite, config, [record])
    output = tmp_path / 'recordings.json'
    output.write_text(recordings_to_json(config, [record]))
    replay_config, records = read_recordings(output, suite_label=str(suite_path))
    replayed = score_recordings(suite, replay_config, records)
    assert replayed.results == direct.results
    result = direct.results[0]
    assert result.truncated == (finish_reason == 'length')
    assert result.success == (call_count == 1 and finish_reason != 'length')
    assert result.prompt_tokens == 23
    assert result.completion_tokens == 9
