"""Offline report command, protected input evidence and file writes."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from callprobe import cli

ARCHIVE = Path(__file__).resolve().parents[1] / 'results/schema-shape-nine-models/03-flat.json'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError('report must be offline')
    monkeypatch.setattr(cli, 'ChatClient', fail)
    monkeypatch.setattr(cli, 'probe_server_version', fail)


def test_stdout_is_clean_xml(capsys):
    assert cli.main(['report', str(ARCHIVE), '--format', 'junit']) == 0
    output = capsys.readouterr()
    root = ET.fromstring(output.out)
    assert len(root.findall('.//testcase')) == 54
    assert len(root.findall('.//failure')) == 16
    assert not output.err


def test_file_output_and_explicit_overwrite(tmp_path, capsys):
    out = tmp_path / 'reports' / 'junit.xml'
    args = ['report', str(ARCHIVE), '--out', str(out)]
    assert cli.main(args) == 0
    original = out.read_bytes()
    assert ET.fromstring(original).find('.//testsuite') is not None
    assert not capsys.readouterr().out
    assert cli.main(args) == 2
    assert out.read_bytes() == original
    assert cli.main(args + ['--force']) == 0
    assert out.read_bytes() == original


@pytest.mark.parametrize('format', ['junit', 'text', 'json'])
@pytest.mark.parametrize('alias', ['same', 'symlink', 'hardlink'])
def test_never_overwrites_source_even_with_force(tmp_path, alias, format):
    source = tmp_path / 'source.json'
    source.write_bytes(ARCHIVE.read_bytes())
    out = tmp_path / 'alias.xml'
    if alias == 'same':
        out = source
    elif alias == 'symlink':
        out.symlink_to(source)
    else:
        out.hardlink_to(source)
    before = source.read_bytes()
    assert cli.main(['report', str(source), '--out', str(out), '--force', '--format', format]) == 2
    assert source.read_bytes() == before


def test_bad_input_does_not_replace_report(tmp_path):
    source = tmp_path / 'bad.json'
    source.write_text('{not json')
    out = tmp_path / 'report.xml'
    out.write_text('previous report')
    assert cli.main(['report', str(source), '--out', str(out), '--force']) == 2
    assert out.read_text() == 'previous report'


def test_write_failure_preserves_existing_report(tmp_path, monkeypatch):
    out = tmp_path / 'report.xml'
    out.write_text('previous report')
    def fail(*args, **kwargs):
        raise OSError('simulated write failure')
    monkeypatch.setattr(Path, 'replace', fail)
    assert cli.main(['report', str(ARCHIVE), '--out', str(out), '--force']) == 2
    assert out.read_text() == 'previous report'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['report.xml']


@pytest.mark.parametrize('format', ['text', 'json'])
def test_saved_summaries_use_recorded_scores_without_raw_evidence(tmp_path, capsys, format):
    data = json.loads(ARCHIVE.read_text())
    data['config']['endpoint'] = 'https://PRIVATE_TOKEN@example.test/v1?key=PRIVATE_KEY'
    data['config']['notes'] = 'PRIVATE_NOTES'
    data['results'][0]['response_text'] = 'PRIVATE_RESPONSE'
    source = tmp_path / 'saved.json'
    source.write_text(json.dumps(data))
    before = source.read_bytes()
    assert cli.main(['report', str(source), '--format', format]) == 0
    output = capsys.readouterr()
    assert not output.err and 'PRIVATE_' not in output.out
    assert source.read_bytes() == before
    if format == 'json':
        summary = json.loads(output.out)
        assert summary['n'] == 54 and summary['unique_tasks_scored'] == 18
        assert summary['coverage'] == '54/54/54'
        assert summary['cost']['successes'] == 38
        assert 'endpoint' not in summary
    else:
        assert 'observations scored 54' in output.out
        assert 'unique tasks scored 18' in output.out
        assert '54/54/54 (scored/recorded/planned)' in output.out
        assert 'endpoint' not in output.out


@pytest.mark.parametrize('format', ['text', 'json'])
def test_summary_export_marks_incomplete_coverage(tmp_path, capsys, format):
    data = json.loads(ARCHIVE.read_text())
    data['results'].pop()
    source = tmp_path / 'partial.json'
    source.write_text(json.dumps(data))
    assert cli.main(['report', str(source), '--format', format]) == 0
    output = capsys.readouterr().out
    assert '53/53/54 INCOMPLETE (1 missing)' in output


def test_summary_json_all_errors_is_valid_json_with_null_cost(tmp_path, capsys):
    data = json.loads(ARCHIVE.read_text())
    for row in data['results']:
        row['error'] = ''
    source = tmp_path / 'errors.json'
    source.write_text(json.dumps(data))
    assert cli.main(['report', str(source), '--format', 'json']) == 0
    output = capsys.readouterr().out
    assert 'Infinity' not in output and 'NaN' not in output
    summary = json.loads(output)
    assert summary['n'] == summary['unique_tasks_scored'] == 0
    assert summary['errors'] == 54 and summary['total_requests'] == 54
    assert summary['cost']['tokens_per_success'] is None


@pytest.mark.parametrize('format', ['text', 'json'])
def test_summary_output_requires_explicit_force(tmp_path, capsys, format):
    out = tmp_path / 'nested' / ('summary.' + format)
    args = ['report', str(ARCHIVE), '--format', format, '--out', str(out)]
    assert cli.main(args) == 0
    before = out.read_bytes()
    assert not capsys.readouterr().out
    assert cli.main(args) == 2
    assert out.read_bytes() == before
    assert cli.main(args + ['--force']) == 0
    assert out.read_bytes() == before


@pytest.mark.parametrize('format', ['text', 'json'])
def test_summary_retains_targeted_scope_and_legacy_unknown_plan(tmp_path, capsys, format):
    data = json.loads(ARCHIVE.read_text())
    task = data['results'][0]['task_id']
    data['config']['selected_task_ids'] = [task]
    data['results'] = [r for r in data['results'] if r['task_id'] == task]
    source = tmp_path / 'targeted.json'
    source.write_text(json.dumps(data))
    assert cli.main(['report', str(source), '--format', format]) == 0
    output = capsys.readouterr().out
    if format == 'text':
        assert 'TARGETED DEBUG RUN' in output
    else:
        assert json.loads(output)['scope']['targeted'] is True
    data['config'].pop('selected_task_ids')
    data['config'].pop('task_ids')
    source.write_text(json.dumps(data))
    assert cli.main(['report', str(source), '--format', format]) == 0
    assert 'planned unknown' in capsys.readouterr().out


@pytest.mark.parametrize('format', ['junit', 'text', 'json'])
def test_invalid_saved_fields_do_not_echo_evidence_values(tmp_path, capsys, format):
    data = json.loads(ARCHIVE.read_text())
    data['config']['repeats'] = 'PRIVATE_INVALID_VALUE'
    source = tmp_path / 'invalid.json'
    source.write_text(json.dumps(data))
    assert cli.main(['report', str(source), '--format', format]) == 2
    output = capsys.readouterr()
    assert not output.out
    assert 'PRIVATE_INVALID_VALUE' not in output.err
    assert 'config.repeats' in output.err
