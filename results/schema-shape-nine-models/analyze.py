"""Summarize matched task/pad observations across deliberately different contracts."""
import json
from pathlib import Path
root=Path(__file__).resolve().parent
manifest=json.loads((root/'manifest.json').read_text())
models={m['name']:{} for m in manifest['models']}
for entry in manifest['runs']:
    path=root/entry['file']
    if not path.exists() or entry['status']=='running': continue
    run=json.loads(path.read_text());rows=run['results']
    keys=[(r['task_id'],r['pad'],r['repeat']) for r in rows]
    assert len(set(keys))==len(keys), 'duplicate observations'
    cfg=run['config'];assert cfg['callprobe_version']=='0.9.0rc1' and cfg['scoring_version']==3
    assert cfg['pads']==[0,2,4] and cfg['repeats']==1 and cfg['temperature']==0
    models[entry['model']][entry['variant']]={'run':run,'entry':entry}
summary=[]
for model,variants in models.items():
    if len(variants)!=2: continue
    row={'model':model,'variants':{}}
    keyed={}
    for variant,value in variants.items():
        results=value['run']['results'];scored=[r for r in results if not r['error']]
        keyed[variant]={(r['task_id'],r['pad'],r['repeat']):r for r in results}
        row['variants'][variant]={'recorded':len(results),'scored':len(scored),'expected':54,'errors':len(results)-len(scored),'truncated':sum(r['truncated'] for r in results),'success':sum(r['success'] for r in scored),'selection':sum(r['selection_ok'] for r in scored),'schema':sum(r['schema_ok'] for r in scored),'args':sum(r['args_ok'] for r in scored),'by_pad':{str(p):{'scored':sum(r['pad']==p for r in scored),'success':sum(r['pad']==p and r['success'] for r in scored)} for p in [0,2,4]}}
    same=set(keyed['nested'])&set(keyed['flat'])
    valid=[k for k in same if not keyed['nested'][k]['error'] and not keyed['flat'][k]['error']]
    row['paired_scored']=len(valid)
    row['paired_nested_success']=sum(keyed['nested'][k]['success'] for k in valid)
    row['paired_flat_success']=sum(keyed['flat'][k]['success'] for k in valid)
    row['improved']=[{'task':k[0],'pad':k[1]} for k in sorted(valid) if not keyed['nested'][k]['success'] and keyed['flat'][k]['success']]
    row['regressed']=[{'task':k[0],'pad':k[1]} for k in sorted(valid) if keyed['nested'][k]['success'] and not keyed['flat'][k]['success']]
    summary.append(row)
(root/'summary.json').write_text(json.dumps({'status':manifest['status'],'models':summary},indent=2)+'\n')
for r in summary:
    n,f=r['variants']['nested'],r['variants']['flat']
    print(f"{r['model']}: nested {n['success']}/{n['scored']} -> flat {f['success']}/{f['scored']}; improved {len(r['improved'])}, regressed {len(r['regressed'])}; errors {n['errors']+f['errors']}, truncated {n['truncated']+f['truncated']}")
