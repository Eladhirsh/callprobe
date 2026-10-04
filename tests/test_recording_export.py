import json
from pathlib import Path

import pytest

from callprobe.client import Completion
from callprobe.loader import load_suite
from callprobe.models import Call, RunConfig
from callprobe.recording_io import read_recordings, recordings_to_json
from callprobe.recordings import RecordedCompletion, score_recordings
from callprobe.report import summarize


def config(**updates):
    values = dict(model='application-model', endpoint='https://PRIVATE_ENDPOINT/v1',
                  suite='PRIVATE_PATH', pads=[0], repeats=3, temperature=0,
                  max_tokens=64, notes='PRIVATE_NOTES', quantization='q4')
    values.update(updates)
    return RunConfig(**values)


def test_export_round_trip_preserves_evidence_and_scores(tmp_path, monkeypatch):
    import httpx
    def no_network(*args, **kwargs):
        raise AssertionError('export must remain offline')
    monkeypatch.setattr(httpx, 'Client', no_network)
    suite = load_suite(Path(__file__).resolve().parents[1] / 'src/callprobe/suites/core')
    task = next(t for t in suite.tasks if t.expect.tool)
    records = [
        RecordedCompletion(task.id, Completion(
            calls=[Call(name=task.expect.tool, arguments={'text': 'café', 'nested': [1, True, None]}),
                   Call(name='second_call', raw_arguments='{bad', parse_error='parse failed')],
            content='final response', reasoning='recorded reasoning',
            prompt_tokens=12, completion_tokens=3, latency_ms=4.5,
            finish_reason='length', raw={'PRIVATE_BODY': object()},
        )),
        RecordedCompletion(task.id, Completion(error='', latency_ms=12), repeat=1),
        RecordedCompletion(task.id, Completion(), repeat=2),
    ]
    cfg = config(selected_task_ids=[task.id])
    before = cfg.model_dump()
    payload = recordings_to_json(cfg, iter(records))
    assert 'PRIVATE_' not in payload
    assert cfg.model_dump() == before
    assert 'PRIVATE_BODY' in records[0].completion.raw
    path = tmp_path / 'recordings.json'
    path.write_text(payload, encoding='utf-8')
    read_config, read_records = read_recordings(path, suite_label='core')
    for original, restored in zip(records, read_records):
        assert original.task_id == restored.task_id
        assert original.pad == restored.pad and original.repeat == restored.repeat
        assert vars(restored.completion) == dict(vars(original.completion), raw={})
    original_run = score_recordings(suite, cfg, records)
    restored_run = score_recordings(suite, read_config, read_records)
    assert [r.model_dump() for r in restored_run.results] == [r.model_dump() for r in original_run.results]
    original_summary = summarize(original_run)
    original_summary['endpoint'] = 'recorded://local'
    assert summarize(restored_run) == original_summary
    assert read_config.endpoint == 'recorded://local'
    assert read_config.quantization == 'q4'
    assert read_config.selected_task_ids == [task.id]


@pytest.mark.parametrize('arguments', [
    {'x': (1, 2)}, {1: 'PRIVATE_VALUE'}, {'x': float('nan')},
    {'x': float('inf')}, {'x': b'PRIVATE_BYTES'}, {'x': {'PRIVATE_SET'}},
])
def test_export_rejects_non_json_evidence_without_coercion_or_value_leak(arguments):
    call = Call(name='tool').model_copy(update={'arguments': arguments})
    with pytest.raises(ValueError, match='valid v1 document') as caught:
        recordings_to_json(config(), [RecordedCompletion('t', Completion(calls=[call]))])
    assert 'PRIVATE' not in str(caught.value)


def test_export_rejects_recursive_arguments():
    arguments = {}
    arguments['self'] = arguments
    call = Call(name='tool').model_copy(update={'arguments': arguments})
    with pytest.raises(ValueError, match='valid v1 document'):
        recordings_to_json(config(), [RecordedCompletion('t', Completion(calls=[call]))])


@pytest.mark.parametrize('records', [
    [], ['PRIVATE_PAYLOAD'], [RecordedCompletion('t', 'PRIVATE_PAYLOAD')],
    [RecordedCompletion('t', Completion(content=[]))],
    [RecordedCompletion('t', Completion(), repeat=True)],
    [RecordedCompletion('', Completion())],
])
def test_export_rejects_invalid_records(records):
    with pytest.raises(ValueError) as caught:
        recordings_to_json(config(), records)
    assert 'PRIVATE' not in str(caught.value)


@pytest.mark.parametrize('updates', [{'pads': []}, {'repeats': 0}, {'temperature': float('nan')}])
def test_export_validates_config(updates):
    with pytest.raises(ValueError, match='valid v1 document'):
        recordings_to_json(config().model_copy(update=updates), [RecordedCompletion('t', Completion())])


def test_export_does_not_invent_coverage_or_validate_against_an_unknown_suite(tmp_path):
    records = [RecordedCompletion('external-task', Completion(), repeat=999_999)]
    cfg = config(repeats=1_000_000)
    payload = recordings_to_json(cfg, records)
    doc = json.loads(payload)
    assert len(doc['records']) == 1
    assert doc['records'][0]['repeat'] == 999_999
    assert doc['config']['repeats'] == 1_000_000
    assert len(payload) < 2000
