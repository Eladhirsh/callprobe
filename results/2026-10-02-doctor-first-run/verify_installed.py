"""Exercise first-run setup through an installed wheel and local Ollama.

Usage: /path/to/installed/python verify_installed.py NEW_DIRECTORY
Requires qwen2.5:7b already installed. Makes six completion requests; doctor
checks themselves only discover models. No tool execution or downloads.
"""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=False)
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME', 'API_KEY', 'OPENAI_API_KEY')}
    commands = []

    def cli(name, *args, expected=0):
        result = subprocess.run([sys.executable, '-m', 'callprobe.cli', *map(str, args)],
                                cwd=root, env=env, capture_output=True, text=True, timeout=600)
        (root / f'{name}.stdout.txt').write_text(result.stdout)
        (root / f'{name}.stderr.txt').write_text(result.stderr)
        commands.append({'name': name, 'args': list(map(str, args)), 'returncode': result.returncode})
        (root / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        assert result.returncode == expected, (name, result.stderr)
        print(name, result.returncode, flush=True)
        return result.stdout

    cli('version', '--version')
    cli('init', 'init', '--example', 'support', '--out', 'support')
    cli('validate', 'validate', '--suite', 'support')
    common = ['--suite', 'support', '--model', 'qwen2.5:7b', '--endpoint', 'http://127.0.0.1:11434/v1']
    report = json.loads(cli('doctor', 'doctor', *common, '--format', 'json'))
    assert report['status'] == 'pass' and report['model_listed'] is True
    assert report['generation_tested'] is False and report['server']['name'] == 'ollama'
    missing = json.loads(cli('missing-model', 'doctor', '--model', 'callprobe-deliberately-absent-model',
                             '--endpoint', 'http://127.0.0.1:11434/v1', '--format', 'json'))
    assert missing['status'] == 'warning' and missing['model_listed'] is False
    assert missing['generation_tested'] is False
    cli('unsafe-url', 'doctor', '--model', 'qwen2.5:7b', '--endpoint',
        'http://redacted:do-not-echo@localhost:11434/v1', expected=2)
    assert 'do-not-echo' not in (root / 'unsafe-url.stderr.txt').read_text()
    experiment = [*common, '--pad', '0', '--repeats', '1', '--max-tokens', '4096', '--retries', '0', '--request-timeout', '180']
    plan = json.loads(cli('dry-run', 'run', *experiment, '--dry-run', '--format', 'json'))
    assert plan['total_requests'] == 6
    cli('run', 'run', *experiment, '--out', 'baseline.json')
    saved = json.loads((root / 'baseline.json').read_text())
    assert len(saved['results']) == 6 and all(r['error'] is None for r in saved['results'])
    cli('explain', 'explain', 'baseline.json', '--suite', 'support', '--format', 'json')
    cli('junit', 'report', 'baseline.json', '--out', 'results.xml')
    cli('self-compare', 'compare', 'baseline.json', 'baseline.json', '--fail-on-regression')
    print(json.dumps({'observations': 6, 'successes': sum(r['success'] for r in saved['results']),
                      'truncated': sum(r['truncated'] for r in saved['results'])}))


if __name__ == '__main__':
    main()
