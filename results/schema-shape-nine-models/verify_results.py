"""Verify complete identity coverage, provenance, and frozen suite hashes."""
import itertools, json
from pathlib import Path
from callprobe.loader import load_suite
from callprobe.models import Run
root=Path(__file__).resolve().parent
m=json.loads((root/'manifest.json').read_text())
assert m['status']!='running' and len(m['runs'])==18
suites={v:load_suite(str(root/v)) for v in ('flat','nested')}
total=errors=truncated=0
for e in m['runs']:
    run=Run.model_validate_json((root/e['file']).read_text())
    cfg=run.config;suite=suites[e['variant']]
    assert cfg.model==e['model'] and cfg.suite_hash==suite.hash
    assert cfg.callprobe_version=='0.9.0rc1' and cfg.scoring_version==3
    assert cfg.pads==[0,2,4] and cfg.repeats==1 and cfg.max_tokens==4096 and cfg.temperature==0
    assert cfg.server_version==m['server']['version']
    planned=set(itertools.product([t.id for t in suite.tasks],[0,2,4],[0]))
    actual=[(r.task_id,r.pad,r.repeat) for r in run.results]
    assert len(actual)==len(set(actual)) and set(actual)==planned
    assert e['observations']==len(actual)
    total+=len(actual);errors+=sum(bool(r.error) for r in run.results);truncated+=sum(r.truncated for r in run.results)
assert total==m['planned_observations']==972
print(f'Verified {total} unique planned observations across 18 blocks; {errors} errors, {truncated} truncations')
