"""Run the frozen core/mail suites against an already-running llama.cpp server.

Use an installed CallProbe Python and a new output directory. No model downloads
or proposed tool executions. The server must already serve qwen2.5:7b on port 18080.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone
import urllib.request


def props():
    with urllib.request.urlopen('http://127.0.0.1:18080/props', timeout=5) as response:
        data = json.load(response)
    return {key: data[key] for key in ('build_info', 'model_alias', 'model_ftype', 'total_slots',
                                      'default_generation_settings', 'chat_template_caps')} | {
        'chat_template_sha256': hashlib.sha256(data['chat_template'].encode()).hexdigest()}


def main():
    root = Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=False)
    previous = Path(__file__).resolve().parents[1] / '2026-10-01-rc3-model-validation/evidence'
    for suite in ('core', 'mail'):
        shutil.copytree(previous / f'{suite}-suite', root / f'{suite}-suite')
    before = props()
    (root/'server-before.json').write_text(json.dumps(before, indent=2)+'\n')
    env = {k:v for k,v in os.environ.items() if k not in ('API_KEY','OPENAI_API_KEY','PYTHONPATH','PYTHONHOME')}
    manifest = {'started_at': datetime.now(timezone.utc).isoformat(), 'status':'running',
                'planned_observations':154, 'experiments':[]}
    def save():
        (root/'experiment.json').write_text(json.dumps(manifest, indent=2)+'\n')
    save()
    for suite, pads, repeats in [('core', '0', 2), ('mail', '0,2,4', 1)]:
        command = [sys.executable, '-m', 'callprobe.cli', 'sweep', '--models', 'qwen2.5:7b',
                   '--endpoint', 'http://127.0.0.1:18080/v1', '--suite', str(root/f'{suite}-suite'),
                   '--out', str(root/suite), '--pad', pads, '--repeats', str(repeats),
                   '--max-tokens', '4096', '--request-timeout', '180', '--timeout', '3600', '--junit']
        entry = {'suite':suite, 'command':command, 'status':'running'}
        manifest['experiments'].append(entry)
        save()
        with (root/f'{suite}.log').open('w') as log:
            status = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
        entry.update(status='complete' if status==0 else 'failed', returncode=status)
        save()
        print(suite, 'exit', status, flush=True)
    after = props()
    (root/'server-after.json').write_text(json.dumps(after, indent=2)+'\n')
    manifest.update(finished_at=datetime.now(timezone.utc).isoformat(), server_configuration_unchanged=before==after,
                    status='complete' if all(e['returncode']==0 for e in manifest['experiments']) else 'failed')
    save()
    return 0 if manifest['status']=='complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
