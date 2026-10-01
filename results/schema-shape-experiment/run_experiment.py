"""Run paired blocks with the PyPI-installed interpreter; never repair responses."""
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
from importlib.metadata import version
root=Path(__file__).resolve().parent
order=['nested','flat','flat','nested','nested','flat']
with urllib.request.urlopen('http://127.0.0.1:11434/api/tags') as r:
    model=next(m for m in json.load(r)['models'] if m['name']=='qwen2.5:7b')
manifest={'package':version('callprobe'),'model':model,'order':order,'runs':[]}
for i,variant in enumerate(order,1):
    outfile=root/f'{i:02d}-{variant}.json'
    if outfile.exists(): raise SystemExit(f'refusing to overwrite {outfile}')
    cmd=[sys.executable,'-m','callprobe.cli','run','--suite',str(root/variant),
         '--model','qwen2.5:7b','--pad','0','--repeats','1','--temperature','0',
         '--max-tokens','4096','--retries','0','--concurrency','1','--out',str(outfile)]
    print(f'{i}/6: {variant}',flush=True)
    proc=subprocess.run(cmd,capture_output=True,text=True)
    (root/f'{i:02d}-{variant}.log').write_text(proc.stdout+proc.stderr)
    manifest['runs'].append({'variant':variant,'result':outfile.name,'command':cmd,'exit':proc.returncode})
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if proc.returncode: raise SystemExit(proc.returncode)
    run=json.loads(outfile.read_text())
    errors=sum(bool(r.get('error')) for r in run['results'])
    print(f'{i}/6 completed: {len(run["results"])} observations, {errors} request errors',flush=True)
    if errors: raise SystemExit('request errors: inspect evidence before continuing')
