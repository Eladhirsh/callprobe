"""Cross-check public comparison reports against independent raw-case pairing."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(sys.argv[1]).resolve()
    checks = []
    for suite in ('core', 'mail'):
        directory = root / suite
        baseline = directory / '01-result.json'
        if not baseline.is_file():
            raise SystemExit(f'Missing comparison baseline: {baseline}')
        a = json.loads(baseline.read_text())
        config = a['config']
        expected = {(task, pad, repeat) for task in config['task_ids']
                    for pad in config['pads'] for repeat in range(config['repeats'])}
        key = lambda r: (r['task_id'], r['pad'], r['repeat'])
        before = {key(r):r for r in a['results']}
        if not a.get('finished_at') or before.keys() != expected or len(before) != len(a['results']):
            raise SystemExit(f'Incomplete or invalid comparison baseline: {baseline}')
        for candidate in sorted(directory.glob('*-result.json')):
            b = json.loads(candidate.read_text())
            if not b.get('finished_at'):
                continue
            after = {key(r):r for r in b['results']}
            assert before.keys() == after.keys()
            pairs = [(before[k], after[k]) for k in sorted(before)
                     if before[k]['error'] is None and after[k]['error'] is None]
            regressions = [{'task_id':y['task_id'], 'pad':y['pad'], 'repeat':y['repeat']}
                           for x,y in pairs if x['success'] and not y['success']]
            errors = any(r['error'] is not None for r in [*before.values(), *after.values()])
            expected_pass = not (regressions or errors or not pairs)
            digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
            hashes = (digest(baseline), digest(candidate))
            outputs = {}
            for format in ('json', 'markdown'):
                proc = subprocess.run([sys.executable, '-m', 'callprobe.cli', 'compare', str(baseline),
                                       str(candidate), '--fail-on-regression', '--format', format],
                                      capture_output=True, text=True)
                assert proc.returncode == (0 if expected_pass else 1), proc.stderr
                assert not proc.stderr, proc.stderr
                outputs[format] = proc.stdout
            gate = json.loads(outputs['json'])['gate']
            assert gate['passed'] == expected_pass
            assert gate['matched_cases'] == len(pairs)
            assert gate['regressions'] == regressions
            if pairs:
                delta = sum(int(y['success']) - int(x['success']) for x,y in pairs) / len(pairs)
                assert gate['success_delta'] == delta
            assert hashes == (digest(baseline), digest(candidate))
            output = root / 'comparisons'
            output.mkdir(exist_ok=True)
            prefix = f'{suite}-01-vs-{candidate.name[:2]}'
            (output / f'{prefix}.json').write_text(outputs['json'])
            (output / f'{prefix}.md').write_text(outputs['markdown'])
            checks.append({'suite':suite, 'baseline':a['config']['model'], 'candidate':b['config']['model'],
                           'gate_passed':expected_pass, 'matched_cases':len(pairs),
                           'regressions':len(regressions), 'report_verified':True})
    (root / 'comparison-checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    print(f'Passed {len(checks)} comparison report checks; expected model regressions remain failing gates.')


if __name__ == '__main__':
    main()
