"""Recorded experimental controls, error denominators and offline CLI behavior."""
import json
from pathlib import Path

import pytest

from callprobe import cli
from callprobe.contracts import compare_contracts, render_contracts
from callprobe.loader import load_suite
from callprobe.models import Run

ARCHIVE = Path(__file__).resolve().parents[1] / 'results/schema-shape-nine-models'


@pytest.fixture
def experiment():
    return (Run.model_validate_json((ARCHIVE / '03-nested.json').read_text()),
            Run.model_validate_json((ARCHIVE / '03-flat.json').read_text()),
            load_suite(ARCHIVE / 'nested'), load_suite(ARCHIVE / 'flat'))


def test_real_experiment_preserves_regressions(experiment):
    report = compare_contracts(*experiment)
    assert report['informational'] is True
    assert report['coverage_a']['passed'] == 13
    assert report['coverage_b']['passed'] == 38
    assert report['paired']['scored_pairs'] == 54
    assert len(report['improved']) == 27
    assert len(report['regressed']) == 2
    assert len(report['changed_expectations']) > 0
    assert sum(m['scored_pairs'] for m in report['by_pad'].values()) == 54
    assert sum(m['scored_pairs'] for m in report['by_category'].values()) == 54
    for markdown in (True, False):
        rendered = render_contracts(report, markdown)
        assert 'regressed (2)' in rendered
        assert 'not a CI gate' in rendered
        assert 'not proven' in rendered


def test_errors_excluded_from_both_paired_denominators(experiment):
    a, b, sa, sb = experiment
    a.results[0].error = 'timeout'
    b.results[1].error = 'server error'
    report = compare_contracts(a, b, sa, sb)
    assert report['paired']['scored_pairs'] == 52
    assert len(report['excluded']) == 2
    assert report['coverage_a']['scored'] == 53
    assert report['coverage_b']['errors'] == 1
    assert report['excluded'][0]['error_a'] or report['excluded'][0]['error_b']


def test_all_errors_are_na(experiment):
    for result in experiment[0].results:
        result.error = 'unavailable'
    report = compare_contracts(*experiment)
    assert report['paired']['delta'] is None
    assert report['coverage_a']['success'] is None
    assert not report['regressed']
    assert 'n/a' in render_contracts(report)


@pytest.mark.parametrize('field,value', [
    ('model', 'another'), ('endpoint', 'http://other'), ('temperature', 1),
    ('max_tokens', 33), ('quantization', 'different'), ('server_name', 'different'),
    ('server_version', 'different'), ('scoring_version', 999),
    ('scoring_version', None), ('selected_task_ids', []),
    ('task_ids', ['incomplete']), ('suite_hash', 'bad'),
    ('pads', [0, 0]), ('pads', [-1]), ('pads', [10000]), ('repeats', 0),
])
def test_rejects_invalid_controls(experiment, field, value):
    setattr(experiment[0].config, field, value)
    with pytest.raises(ValueError):
        compare_contracts(*experiment)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'unexpected', 'model', 'category', 'repeat'])
def test_rejects_bad_observations(experiment, change):
    a = experiment[0]
    if change == 'missing':
        a.results.pop()
    elif change == 'duplicate':
        a.results[-1] = a.results[0].model_copy(deep=True)
    elif change == 'unexpected':
        a.results[0].task_id = 'unknown'
    elif change == 'model':
        a.results[0].model = 'unknown'
    elif change == 'category':
        a.results[0].category = 'depth' if a.results[0].category != 'depth' else 'args'
    else:
        a.results[0].repeat = 123456789
    with pytest.raises(ValueError):
        compare_contracts(*experiment)


@pytest.mark.parametrize('change', ['messages', 'type', 'tool', 'also_acceptable', 'tools', 'distractors', 'exclude_distractors'])
def test_rejects_changed_task_controls(experiment, change):
    suite = experiment[3]
    task = suite.tasks[0]
    if change == 'messages':
        task.messages[0]['content'] += ' New instruction.'
    elif change in ('type', 'tool', 'also_acceptable'):
        setattr(task.expect, change, {'type': 'no_call', 'tool': 'unknown', 'also_acceptable': ['unknown']}[change])
    elif change == 'tools':
        suite.bundles[task.bundle].tools.reverse()
    elif change == 'distractors':
        suite.distractors.reverse()
    else:
        task.exclude_distractors.append('unknown')
    with pytest.raises(ValueError):
        compare_contracts(*experiment)


def test_timeout_disclosed_but_not_rejected(experiment):
    experiment[0].config.request_timeout = None
    experiment[1].config.request_timeout = 300
    report = compare_contracts(*experiment)
    assert report['request_timeout_a'] is None
    assert any('timeouts differ' in w for w in report['warnings'])


def test_markdown_escapes_external_content(experiment):
    report = compare_contracts(*experiment)
    report['settings']['model'] = '<script>evil</script>\n# heading'
    report['regressed'][0]['task_id'] = '[link](https://bad)'
    rendered = render_contracts(report, markdown=True)
    assert '<script>' not in rendered
    assert '[link](https://bad)' not in rendered
    assert '&lt;script&gt;' in rendered


@pytest.fixture
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('offline command contacted a model')
    monkeypatch.setattr(cli, 'ChatClient', forbidden)
    monkeypatch.setattr(cli, 'probe_server_version', forbidden)


def test_demo_and_cli_offline(tmp_path, capsys, offline):
    out = tmp_path / 'contract demo'
    assert cli.main(['demo', '--contracts', '--out', str(out)]) == 0
    capsys.readouterr()
    for shape, name in [('nested', 'baseline'), ('flat', 'candidate')]:
        assert (out / f'{name}.json').read_bytes() == (ARCHIVE / f'03-{shape}.json').read_bytes()
        for source in (ARCHIVE / shape).glob('*.yaml'):
            assert (out / shape / source.name).read_bytes() == source.read_bytes()
    args = ['compare-contracts', str(out / 'baseline.json'), str(out / 'candidate.json'),
            '--suite-a', str(out / 'nested'), '--suite-b', str(out / 'flat')]
    assert cli.main(args + ['--format', 'json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(report['regressed']) == 2
    for fmt in ('text', 'markdown'):
        assert cli.main(args + ['--format', fmt]) == 0
        assert 'not a CI gate' in capsys.readouterr().out
    assert cli.main(['compare', str(out / 'baseline.json'), str(out / 'candidate.json'),
                     '--fail-on-regression']) == 2
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        cli.main(args + ['--fail-on-regression'])
    assert exc.value.code == 2
    assert cli.main(args[:-1] + [str(out / 'nested')]) == 2
    assert 'hash' in capsys.readouterr().err


def test_demo_preflight_checks_every_directory(tmp_path, offline):
    (tmp_path / 'flat').mkdir()
    protected = tmp_path / 'flat/tasks.yaml'
    protected.write_text('user data')
    assert cli.main(['demo', '--contracts', '--out', str(tmp_path)]) == 2
    assert not (tmp_path / 'baseline.json').exists()
    assert protected.read_text() == 'user data'


def test_large_repeat_plan_is_checked_without_expansion(experiment):
    experiment[0].config.repeats = 10**12
    with pytest.raises(ValueError, match='missing observations'):
        compare_contracts(*experiment)


def test_real_timeout_and_truncation_coverage():
    a, b = [Run.model_validate_json((ARCHIVE / f'04-{shape}.json').read_text())
            for shape in ('nested', 'flat')]
    report = compare_contracts(a, b, load_suite(ARCHIVE / 'nested'), load_suite(ARCHIVE / 'flat'))
    assert report['coverage_a']['recorded'] == 54
    assert report['coverage_a']['errors'] == 3
    assert report['coverage_a']['truncations'] == 2
    assert report['paired']['scored_pairs'] == 51
    assert len(report['improved']) == 3
    assert len(report['regressed']) == 1
    assert len(report['excluded']) == 3


def test_comparison_does_not_modify_recorded_evidence(experiment):
    before = [item.model_dump_json() for item in experiment]
    report = compare_contracts(*experiment)
    assert report['changed_tools']
    assert [item.model_dump_json() for item in experiment] == before
