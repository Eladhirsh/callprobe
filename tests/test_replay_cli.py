"""Offline application recordings become ordinary, protected Run artifacts."""
import json
from pathlib import Path

import pytest

from callprobe import cli
from callprobe.models import Run


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx
    def fail(*args, **kwargs):
        raise AssertionError('replay must stay offline')
    monkeypatch.setattr(cli, 'ChatClient', fail)
    monkeypatch.setattr(cli, 'probe_server_version', fail)
    monkeypatch.setattr(httpx, 'Client', fail)
    monkeypatch.setattr(httpx, 'get', fail)


@pytest.fixture
def inputs(tmp_path, capsys):
    suite = tmp_path / 'suite'
    assert cli.main(['init', '--example', 'support', '--out', str(suite)]) == 0
    capsys.readouterr()
    data = {
        'schema_version': 1,
        'config': {'model': 'recorded-model', 'pads': [0], 'repeats': 1,
                   'temperature': 0.0, 'max_tokens': 4096},
        'records': [{'task_id': 'status-by-id', 'completion': {'calls': [{
            'name': 'get_order', 'arguments': {'path': {'order_id': 'ORD-448120'}},
        }]}}],
    }
    source = tmp_path / 'recordings.json'
    source.write_text(json.dumps(data))
    return source, suite, tmp_path / 'results.json', data


def replay(source, suite, out, *extra):
    return cli.main(['replay', str(source), '--suite', str(suite), '--out', str(out), *extra])


def test_partial_replay_then_report_and_explain(inputs, capsys):
    source, suite, out, _ = inputs
    before = source.read_bytes()
    assert replay(source, suite, out) == 0
    captured = capsys.readouterr()
    assert 'OFFLINE REPLAY' in captured.out
    assert '1/1/6 INCOMPLETE (5 missing)' in captured.out
    run = Run.model_validate_json(out.read_text())
    assert run.results[0].success
    assert run.config.endpoint == 'recorded://local'
    assert source.read_bytes() == before
    assert cli.main(['report', str(out), '--format', 'json']) == 0
    assert json.loads(capsys.readouterr().out)['n'] == 1
    assert cli.main(['explain', str(out), '--suite', str(suite)]) == 0
    capsys.readouterr()
    assert cli.main(['compare', str(out), str(out), '--fail-on-regression']) == 2


@pytest.mark.parametrize('alias', ['same', 'symlink', 'hardlink'])
@pytest.mark.parametrize('protected', ['source', 'tasks.yaml', 'tools.yaml', 'suite.yaml', 'distractors.yaml'])
def test_never_overwrites_evidence_even_with_force(inputs, alias, protected):
    source, suite, out, _ = inputs
    target = source if protected == 'source' else suite / protected
    before = target.read_bytes()
    if alias == 'same':
        out = target
    elif alias == 'symlink':
        out.symlink_to(target)
    else:
        out.hardlink_to(target)
    assert replay(source, suite, out, '--force') == 2
    assert target.read_bytes() == before


def test_requires_force_to_replace_previous_output(inputs):
    source, suite, out, _ = inputs
    out.write_text('previous result')
    assert replay(source, suite, out) == 2
    assert out.read_text() == 'previous result'
    assert replay(source, suite, out, '--force') == 0
    assert Run.model_validate_json(out.read_text()).results[0].success


@pytest.mark.parametrize('bad', ['json', 'duplicate', 'unknown', 'bad_payload', 'unknown_selection'])
def test_bad_recordings_preserve_output_and_input(inputs, capsys, bad):
    source, suite, out, data = inputs
    if bad == 'duplicate':
        data['records'] *= 2
    elif bad == 'unknown':
        data['records'][0]['task_id'] = 'PRIVATE_UNKNOWN_TASK'
    elif bad == 'unknown_selection':
        data['config']['selected_task_ids'] = ['PRIVATE_UNKNOWN_TASK']
    elif bad == 'bad_payload':
        data['records'][0]['completion'] = 'PRIVATE_RESPONSE'
    source.write_text('PRIVATE_BROKEN_JSON' if bad == 'json' else json.dumps(data))
    before = source.read_bytes()
    out.write_text('previous result')
    assert replay(source, suite, out, '--force') == 2
    assert out.read_text() == 'previous result' and source.read_bytes() == before
    captured = capsys.readouterr()
    assert 'PRIVATE_' not in captured.out + captured.err


def test_atomic_write_failure_preserves_existing_output(inputs, monkeypatch):
    source, suite, out, _ = inputs
    out.write_text('previous result')
    def fail(*args, **kwargs):
        raise OSError('simulated replace failure')
    monkeypatch.setattr(Path, 'replace', fail)
    assert replay(source, suite, out, '--force') == 2
    assert out.read_text() == 'previous result'
    assert not list(out.parent.glob('.results.json.*'))


def test_targeted_request_error_stays_error_and_debug_scope(inputs, capsys):
    source, suite, out, data = inputs
    data['config']['selected_task_ids'] = ['policy-is-not-a-refund']
    data['records'] = [{'task_id': 'policy-is-not-a-refund', 'completion': {'error': ''}}]
    source.write_text(json.dumps(data))
    assert replay(source, suite, out) == 0
    run = Run.model_validate_json(out.read_text())
    assert run.results[0].error == '' and not run.results[0].success
    captured = capsys.readouterr()
    assert 'TARGETED DEBUG RUN' in captured.out and '0/1/1' in captured.out
