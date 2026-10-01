"""Describe an intentionally changed contract; this is not a matched CI gate."""
import json
from pathlib import Path
root=Path(__file__).resolve().parent
manifest=json.loads((root/'manifest.json').read_text())
assert len(manifest['runs'])==6 and all(r['exit']==0 for r in manifest['runs'])
variants={v:[] for v in ('nested','flat')}
rounds=[]
for entry in manifest['runs']:
    run=json.loads((root/entry['result']).read_text())
    assert len(run['results'])==18 and len({r['task_id'] for r in run['results']})==18
    assert run['config']['callprobe_version']=='0.9.0rc1'
    variants[entry['variant']].append(run)
    rounds.append({'file':entry['result'],'successes':sum(r['success'] for r in run['results'])})
metrics={}
for name,runs in variants.items():
    rows=[r for run in runs for r in run['results']]
    metrics[name]={'observations':len(rows),**{k:sum(bool(r[k]) for r in rows) for k in ('success','selection_ok','schema_ok','args_ok','error','truncated')}}
by_task=[]
for tid in variants['nested'][0]['config']['task_ids']:
    row={'task':tid}
    for name,runs in variants.items():
        rows=[r for run in runs for r in run['results'] if r['task_id']==tid]
        row[name]=sum(r['success'] for r in rows)
    by_task.append(row)
report={'metrics':metrics,'rounds':rounds,'tasks':by_task,'note':'Different suite hashes by design. Descriptive contract experiment, not a matched regression gate. Three temperature-zero repeats are not independent samples.'}
(root/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
