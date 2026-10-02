"""Offline report command, protected input evidence and file writes."""
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


@pytest.mark.parametrize('alias', ['same', 'symlink', 'hardlink'])
def test_never_overwrites_source_even_with_force(tmp_path, alias):
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
    assert cli.main(['report', str(source), '--out', str(out), '--force']) == 2
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
