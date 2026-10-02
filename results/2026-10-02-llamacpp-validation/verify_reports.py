"""Verify archived observations through an installed CLI, without model requests.

Usage: /path/to/installed/python verify_reports.py NEW_OUTPUT_DIRECTORY
The raw recordings and suite snapshots are never rewritten.
"""
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index(run):
    records = run['results']
    indexed = {(r['task_id'], r['pad'], r['repeat']): r for r in records}
    config = run['config']
    planned = {(task, pad, repeat) for task in config['task_ids']
               for pad in config['pads'] for repeat in range(config['repeats'])}
    assert len(indexed) == len(records) and set(indexed) == planned
    assert all(r['model'] == config['model'] for r in records)
    return indexed


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    evidence = ROOT / 'evidence'
    previous = ROOT.parent / '2026-10-01-rc3-model-validation/evidence'
    paths = [base / suite / '01-result.json' for base in (evidence, previous)
             for suite in ('core', 'mail')]
    hashes = {str(p.relative_to(ROOT.parent)): digest(p) for p in paths}
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME', 'API_KEY', 'OPENAI_API_KEY')}

    def cli(args, name, expected_code=0):
        result = subprocess.run([sys.executable, '-m', 'callprobe.cli', *map(str, args)],
                                cwd=output, env=env, capture_output=True, text=True, timeout=60)
        (output / name).write_text(result.stdout)
        assert result.returncode == expected_code, (args, result.returncode, result.stderr)
        assert not result.stderr, result.stderr
        return result.stdout

    summary = {}
    for suite in ('core', 'mail'):
        source = evidence / suite / '01-result.json'
        baseline = previous / suite / '01-result.json'
        run, old = json.loads(source.read_text()), json.loads(baseline.read_text())
        after, before = index(run), index(old)
        assert set(after) == set(before)
        assert run['config']['server_name'] == 'llama.cpp'
        assert run['config']['server_version'] == 'b11339-81e39ad34'
        for setting in ('suite_hash', 'scoring_version', 'pads', 'repeats', 'temperature', 'max_tokens'):
            assert run['config'][setting] == old['config'][setting], setting
        for path in (evidence / f'{suite}-suite').rglob('*'):
            if path.is_file():
                assert path.read_bytes() == (previous / f'{suite}-suite' / path.relative_to(evidence / f'{suite}-suite')).read_bytes()
        records = list(after.values())
        errors = sum(r['error'] is not None for r in records)
        passes = sum(r['error'] is None and r['success'] for r in records)
        truncated = sum(r.get('truncated', False) for r in records)
        junit = ET.fromstring(cli(['report', source, '--format', 'junit'], f'{suite}.xml')).find('testsuite')
        assert int(junit.attrib['tests']) == len(records)
        assert int(junit.attrib['errors']) == errors
        assert int(junit.attrib['failures']) == len(records) - errors - passes
        assert len(junit.findall('testcase')) == len(records)
        explained = json.loads(cli(['explain', source, '--suite', evidence / f'{suite}-suite', '--format', 'json'], f'{suite}-explain.json'))
        groups = defaultdict(list)
        for r in records:
            groups[(r['task_id'], r['pad'])].append(r)
        eligible = {key: group for key, group in groups.items() if sum(r['error'] is None for r in group) >= 2}
        mixed = {key for key, group in eligible.items() if len({r['success'] for r in group if r['error'] is None}) > 1}
        if eligible:
            variation = explained['repeat_variation']
            assert variation['groups_examined'] == len(eligible)
            assert {(r['task_id'], r['pad']) for r in variation['mixed_groups']} == mixed
        else:
            assert 'repeat_variation' not in explained
        pairs = [(before[k], after[k]) for k in sorted(before) if before[k]['error'] is None and after[k]['error'] is None]
        regressions = [{'task_id': b['task_id'], 'pad': b['pad'], 'repeat': b['repeat']}
                       for a, b in pairs if a['success'] and not b['success']]
        delta = sum(int(b['success']) - int(a['success']) for a, b in pairs) / len(pairs)
        assert errors == 0 and all(r['error'] is None for r in before.values())
        comparison = json.loads(cli(['compare', baseline, source, '--fail-on-regression', '--format', 'json'], f'{suite}-compare.json', int(bool(regressions))))
        gate = comparison['gate']
        assert gate['regressions'] == regressions and gate['matched_cases'] == len(pairs)
        assert gate['success_delta'] == delta and gate['passed'] == (not regressions)
        markdown = cli(['compare', baseline, source, '--fail-on-regression', '--format', 'markdown'], f'{suite}-compare.md', int(bool(regressions)))
        assert '| Server | ollama | llama.cpp |' in markdown
        assert run['config']['endpoint'] not in markdown
        by_pad = {str(pad): sum(r['success'] and r['error'] is None for r in records if r['pad'] == pad)
                  for pad in run['config']['pads']}
        summary[suite] = dict(observations=len(records), passes=passes, request_errors=errors,
                              truncated=truncated, passes_by_pad=by_pad, mixed_repeat_groups=len(mixed),
                              baseline_passes=sum(r['success'] for r in before.values()),
                              regressed_observations=len(regressions), success_delta=delta)
    assert hashes == {str(p.relative_to(ROOT.parent)): digest(p) for p in paths}
    (output / 'verification.json').write_text(json.dumps({'verified': True, 'raw_sha256': hashes, 'suites': summary}, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
