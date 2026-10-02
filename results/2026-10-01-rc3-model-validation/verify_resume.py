"""Check complete recorded runs resume unchanged with network access disabled."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import patch

from callprobe import cli


def main():
    root = Path(sys.argv[1]).resolve()
    checks = []
    for path in sorted(root.glob('*/*-result.json')):
        original = path.read_bytes()
        saved = json.loads(original)
        config = saved['config']
        expected = len(config['task_ids']) * len(config['pads']) * config['repeats']
        if len(saved['results']) != expected or any(r.get('error') is not None for r in saved['results']):
            continue  # Error observations intentionally need real requests on resume.
        with tempfile.TemporaryDirectory(prefix='callprobe-resume-check-') as tmp:
            output = Path(tmp) / 'resumed.json'
            args = ['run', '--model', config['model'], '--endpoint', config['endpoint'],
                    '--suite', str(root / f'{path.parent.name}-suite'),
                    '--pad', ','.join(map(str, config['pads'])), '--repeats', str(config['repeats']),
                    '--temperature', str(config['temperature']), '--max-tokens', str(config['max_tokens']),
                    '--request-timeout', str(config['request_timeout']), '--retries', '0',
                    '--resume', str(path), '--out', str(output), '--quiet']
            capture = io.StringIO()
            with patch.object(cli, 'probe_server_version', return_value=(config['server_name'], config['server_version'])), \
                 patch.object(cli.ChatClient, 'complete', side_effect=AssertionError('unexpected model call')) as calls, \
                 patch.object(socket.socket, 'connect', side_effect=AssertionError('unexpected network access')) as network, \
                 contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                status = cli.main(args)
                assert status == 0, capture.getvalue()
                resumed = json.loads(output.read_text())
                assert resumed['results'] == saved['results']
                assert resumed['started_at'] == saved['started_at']
                assert calls.call_count == network.call_count == 0
                gate = cli.main(['compare', str(path), str(output), '--fail-on-regression'])
                assert gate == 0, capture.getvalue()
            assert path.read_bytes() == original
            checks.append({'file':str(path.relative_to(root)), 'observations':expected,
                           'raw_sha256':hashlib.sha256(original).hexdigest(),
                           'model_calls':0, 'network_connections':0,
                           'unchanged_results':True, 'comparison_gate':'PASS'})
    report = {'note':'Completed error-free runs only. Server identity is stubbed to recorded metadata; socket connections and model calls are blocked.',
              'checks':checks}
    (root / 'resume-checks.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Passed {len(checks)} offline resume/comparison checks ({sum(c["observations"] for c in checks)} preserved observations)')


if __name__ == '__main__':
    main()
