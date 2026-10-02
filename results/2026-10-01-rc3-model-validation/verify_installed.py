"""Exercise an installed wheel against a scripted HTTP endpoint, not an LLM."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import yaml
import callprobe


def main():
    destination = Path(sys.argv[1]).resolve()
    repo = Path(__file__).resolve().parents[2]
    assert not Path(callprobe.__file__).resolve().is_relative_to(repo)
    spec = importlib.util.spec_from_file_location('selftest_agent', repo / 'scripts/selftest_agent.py')
    agent = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = agent
    spec.loader.exec_module(agent)
    env = {k:v for k,v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME', 'API_KEY', 'OPENAI_API_KEY')}
    with tempfile.TemporaryDirectory(prefix='callprobe-installed-check-') as temporary:
        root = Path(temporary)
        def cli(*args):
            return subprocess.run([sys.executable, '-m', 'callprobe.cli', *args], cwd=root,
                                  env=env, text=True, capture_output=True)
        proc = cli('init', '--example', 'mail-sandbox', '--out', 'suite')
        assert proc.returncode == 0, proc.stderr
        tasks = yaml.safe_load((root/'suite/tasks.yaml').read_text())['tasks']
        with agent.ScriptedServer(tasks) as server:
            proc = cli('sweep', '--models', 'synthetic-baseline', 'synthetic-candidate', 'unavailable',
                       '--suite', 'suite', '--endpoint', server.endpoint, '--out', 'sweep', '--junit')
            assert proc.returncode == 1, proc.stderr
            assert (server.accepted, server.rejected) == (36, 18)
        manifest = json.loads((root/'sweep/manifest.json').read_text())
        assert manifest['status'] == 'failed'
        assert manifest['leaderboard']['models'] == ['synthetic-baseline', 'synthetic-candidate']
        checks = []
        for entry, failures, errors in zip(manifest['models'], [0,4,0], [0,0,18]):
            tree = ET.parse(root/'sweep'/entry['junit_file'])
            assert len(tree.findall('.//testcase')) == 18
            assert len(tree.findall('.//failure')) == failures
            assert len(tree.findall('.//error')) == errors
            checks.append({'model':entry['model'], 'cases':18, 'failures':failures, 'errors':errors})
        report = {'label':'Scripted endpoint, not real-model accuracy evidence', 'version':callprobe.__version__,
                  'requests':54, 'accepted':36, 'rejected':18, 'passed':True, 'checks':checks}
        destination.write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
