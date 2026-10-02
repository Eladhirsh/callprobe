"""Reproduce the local-model experiment using an installed callprobe Python.

Run from a checkout with the named model digests already installed:
  /path/to/installed/python run_validation.py /path/to/new/output
Never downloads models or executes the proposed tools. Output must be new.
"""
import hashlib
import importlib.resources
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone
import urllib.request

MODELS = ['qwen2.5:7b', 'llama3.2:3b', 'hermes3:8b', 'granite3.3:8b',
          'llama3.1:8b', 'mistral-nemo:latest', 'command-r7b:latest', 'phi4-mini:latest', 'qwen3:8b']
ENDPOINT = 'http://127.0.0.1:11434'

def fetch(path):
    with urllib.request.urlopen(ENDPOINT + path, timeout=10) as response:
        return json.load(response)

def identity():
    return {m['name']: {k: m[k] for k in ('name', 'digest', 'size')} | {
        'quantization': m['details'].get('quantization_level'),
        'parameter_size': m['details'].get('parameter_size'),
    } for m in fetch('/api/tags')['models'] if m['name'] in MODELS}

def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = {k:v for k,v in os.environ.items() if k not in ('API_KEY','OPENAI_API_KEY','PYTHONPATH','PYTHONHOME')}
    def cli(*args):
        return [sys.executable, '-m', 'callprobe.cli', *args]
    before = identity()
    if set(before) != set(MODELS):
        raise RuntimeError('All nine named models must already be installed')
    (out/'models-before.json').write_text(json.dumps(before, indent=2)+'\n')
    (out/'server.json').write_text(json.dumps(fetch('/api/version'),indent=2)+'\n')
    core = importlib.resources.files('callprobe')/'suites'/'core'
    shutil.copytree(str(core), out/'core-suite')
    subprocess.run(cli('init','--example','mail-sandbox','--out',str(out/'mail-suite')),check=True,env=env)
    from callprobe import __version__
    manifest = {'version': __version__, 'models': MODELS, 'started_at': datetime.now(timezone.utc).isoformat(),
                'planned_requests':1386,'experiments':[], 'status':'running'}
    def save():
        (out/'experiment.json').write_text(json.dumps(manifest,indent=2)+'\n')
    save()
    for suite,pads,repeats in [('core','0',2),('mail','0,2,4',1)]:
        command = cli('sweep','--models',*MODELS,'--suite',str(out/f'{suite}-suite'),
                      '--out',str(out/suite),'--endpoint',ENDPOINT+'/v1','--pad',pads,
                      '--repeats',str(repeats),'--max-tokens','4096','--request-timeout','180','--timeout','3600')
        entry={'suite':suite,'pads':pads,'repeats':repeats,'command':command,'status':'running'}
        manifest['experiments'].append(entry);save()
        with (out/f'{suite}.log').open('w') as log:
            status=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
        entry.update(status='complete' if status==0 else 'failed',returncode=status);save()
        print(f'{suite}: finished, exit {status}',flush=True)
    after=identity()
    (out/'models-after.json').write_text(json.dumps(after,indent=2)+'\n')
    manifest.update(finished_at=datetime.now(timezone.utc).isoformat(),models_unchanged=before==after,
                    status='complete' if all(e['returncode']==0 for e in manifest['experiments']) else 'failed')
    save()
    hashes={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in out.rglob('*.json')}
    (out/'checksums.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print('All experiments finished',flush=True)

if __name__=='__main__':
    main()
