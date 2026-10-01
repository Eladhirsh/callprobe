"""Bounded local experiment using the published CLI. Never repair or overwrite results."""
import json, subprocess, sys, time, urllib.request
from pathlib import Path
from importlib.metadata import version
root=Path(__file__).resolve().parent
names=['qwen2.5:7b','llama3.2:3b','hermes3:8b','phi4-mini:latest','granite3.3:8b','command-r7b:latest','llama3.1:8b','mistral-nemo:latest','qwen3:8b']
with urllib.request.urlopen('http://127.0.0.1:11434/api/tags') as r: models=json.load(r)['models']
with urllib.request.urlopen('http://127.0.0.1:11434/api/version') as r: server=json.load(r)
assert not (root/'manifest.json').exists(), 'refusing to overwrite a previous matrix'
manifest={'package':version('callprobe'),'server':server,'planned_observations':972,'models':[next(m for m in models if m['name']==n) for n in names],'runs':[],'status':'running'}
def save(): (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
save()
for i,model in enumerate(names):
    for variant in (['nested','flat'] if i%2==0 else ['flat','nested']):
        stem=f'{i+1:02d}-{variant}'
        outfile=root/f'{stem}.json'
        assert not outfile.exists()
        cmd=[sys.executable,'-m','callprobe.cli','run','--suite',str(root/variant),
             '--model',model,'--pad','0,2,4','--repeats','1','--temperature','0',
             '--max-tokens','4096','--retries','0','--concurrency','1','--out',str(outfile)]
        entry={'model':model,'variant':variant,'file':outfile.name,'command':cmd,'status':'running','start':time.time()}
        manifest['runs'].append(entry);save()
        print(f'START {stem} {model}',flush=True)
        try:
            with (root/f'{stem}.log').open('w') as log:
                p=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
            entry['exit']=p.returncode
            entry['status']='complete' if p.returncode==0 else 'failed'
        except subprocess.TimeoutExpired:
            entry['status']='timeout'
        entry['duration_seconds']=round(time.time()-entry['start'],2)
        if outfile.exists():
            run=json.loads(outfile.read_text());rows=run['results']
            entry.update(observations=len(rows),successes=sum(r['success'] for r in rows),errors=sum(bool(r.get('error')) for r in rows),truncated=sum(r['truncated'] for r in rows))
            if len(rows)!=54 or entry['errors']: entry['status']='incomplete_or_errors'
        save();print(json.dumps({k:v for k,v in entry.items() if k!='command'}),flush=True)
manifest['status']='complete' if all(r['status']=='complete' for r in manifest['runs']) else 'finished_with_failures'
save()
