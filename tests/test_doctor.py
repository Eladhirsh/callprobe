import json

import httpx
import pytest

from callprobe import cli, doctor


@pytest.fixture(autouse=True)
def no_metadata_network(monkeypatch):
    monkeypatch.setattr(doctor, 'probe_server_version', lambda *a, **kw: (None, None))


def check(handler, **kwargs):
    return doctor.check_endpoint('https://example.test/prefix/v1/', 'wanted',
                                 transport=httpx.MockTransport(handler), **kwargs)


def test_catalog_request_preserves_base_path_and_uses_only_get(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == 'GET'
        assert request.url == 'https://example.test/prefix/v1/models'
        assert request.headers['Authorization'] == 'Bearer private-key'
        assert request.content == b''
        return httpx.Response(200, json={'data': [{'id': 'wanted'}]})

    monkeypatch.setattr(doctor, 'probe_server_version', lambda *a, **kw: ('llama.cpp', 'b11339-81e39ad34'))
    report = check(handler, api_key='private-key')
    assert len(requests) == 1
    assert report['checks'][0]['status'] == 'pass'
    assert report['model_listed'] is True
    assert report['generation_tested'] is False
    assert report['server']['name'] == 'llama.cpp'
    assert 'private-key' not in json.dumps(report)
    assert 'remain untested' in doctor.render_doctor(report)


@pytest.mark.parametrize('data', [[], [{'id': 'different'}]])
def test_absent_model_is_inconclusive(data):
    report = check(lambda request: httpx.Response(200, json={'data': data}))
    assert report['checks'][0]['status'] == 'warning'
    assert report['model_listed'] is False
    assert 'incomplete' in report['checks'][0]['message']


@pytest.mark.parametrize('status,expected', [(401, 'fail'), (403, 'fail'), (404, 'warning'),
                                           (405, 'warning'), (429, 'fail'), (500, 'fail'), (302, 'fail')])
def test_status_diagnostics_never_follow_retry_or_echo_response(status, expected, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={'Location': 'https://secret-host.invalid/token'},
                              text='PRIVATE response body')

    def forbidden(*args, **kwargs):
        pytest.fail('metadata should not be probed after unsuccessful model discovery')

    monkeypatch.setattr(doctor, 'probe_server_version', forbidden)
    report = check(handler)
    assert len(calls) == 1
    assert report['checks'][0]['status'] == expected
    assert report['model_listed'] is None
    assert 'PRIVATE' not in json.dumps(report)
    assert 'secret-host' not in json.dumps(report)


@pytest.mark.parametrize('body', [None, [], {}, {'data': None}, {'data': [{}]},
                                  {'data': [{'id': 1}]}, {'data': [{'id': ''}]}, {'data': ['wanted']}])
def test_malformed_catalog_is_not_reported_as_success(body):
    report = check(lambda request: httpx.Response(200, json=body))
    assert report['checks'][0]['status'] == 'fail'
    assert report['model_listed'] is None


def test_html_page_suggests_api_base_without_echoing_it():
    report = check(lambda request: httpx.Response(200, text='<html>PRIVATE</html>'))
    assert report['checks'][0]['status'] == 'fail'
    assert '/v1' in report['checks'][0]['message']
    assert 'PRIVATE' not in json.dumps(report)


@pytest.mark.parametrize('exception,fragment', [(httpx.ConnectError, 'Could not connect'),
                                               (httpx.ReadTimeout, 'timed out')])
def test_transport_errors_omit_sensitive_exception_text(exception, fragment):
    def handler(request):
        raise exception('PRIVATE URL and key', request=request)
    report = check(handler)
    assert fragment in report['checks'][0]['message']
    assert 'PRIVATE' not in json.dumps(report)


@pytest.mark.parametrize('endpoint', ['file:///private', 'http://', 'http://[broken',
                                      'http://example.test:bad/v1', 'http://example.test:0/v1',
                                      'http://user:PRIVATE@example.test/v1',
                                      'https://example.test/v1?token=PRIVATE',
                                      'https://example.test/v1#PRIVATE', 'https://example.test/\nPRIVATE'])
def test_invalid_endpoint_fails_before_io_without_echoing_it(endpoint):
    def forbidden(request):
        pytest.fail('invalid endpoint accessed network')
    with pytest.raises(ValueError) as exc:
        doctor.check_endpoint(endpoint, 'm', transport=httpx.MockTransport(forbidden))
    assert 'PRIVATE' not in str(exc.value)


@pytest.mark.parametrize('timeout', [0, -1, float('nan'), float('inf')])
def test_invalid_timeout_fails_before_io(timeout):
    with pytest.raises(ValueError, match='positive finite'):
        check(lambda request: pytest.fail('invalid timeout accessed network'), timeout=timeout)


def test_cli_validates_packaged_suite_and_reports_json(monkeypatch, capsys):
    def endpoint(url, model, **kwargs):
        assert model == 'wanted'
        assert kwargs['api_key'] == 'env-key'
        return {'checks': [{'name': 'models', 'status': 'pass', 'message': 'listed'}],
                'server': {'name': None, 'version': None}, 'model_listed': True, 'generation_tested': False}
    monkeypatch.setenv('API_KEY', 'env-key')
    monkeypatch.setattr(cli, 'check_endpoint', endpoint)
    assert cli.main(['doctor', '--model', 'wanted', '--format', 'json']) == 0
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report['status'] == 'pass'
    assert report['checks'][0]['name'] == 'suite'
    assert '50 tasks' in report['checks'][0]['message']
    assert report['generation_tested'] is False
    assert 'env-key' not in output.out and not output.err


@pytest.mark.parametrize('status,exit_code', [('warning', 0), ('fail', 1)])
def test_cli_discovery_exit_codes_and_explicit_key_precedence(monkeypatch, capsys, status, exit_code):
    def endpoint(url, model, **kwargs):
        assert kwargs['api_key'] == 'explicit'
        return {'checks': [{'name': 'models', 'status': status, 'message': 'diagnostic'}],
                'server': {'name': None, 'version': None}, 'model_listed': None, 'generation_tested': False}
    monkeypatch.setenv('API_KEY', 'environment')
    monkeypatch.setattr(cli, 'check_endpoint', endpoint)
    assert cli.main(['doctor', '--model', 'wanted', '--api-key', 'explicit', '--format', 'json']) == exit_code
    assert json.loads(capsys.readouterr().out)['status'] == status


@pytest.mark.parametrize('empty', [False, True])
def test_invalid_suite_stops_before_network(monkeypatch, capsys, empty):
    suite, label = cli._resolve_suite(None)
    suite = suite.model_copy(deep=True)
    if empty:
        suite.tasks = []
    else:
        monkeypatch.setattr(cli, 'validate_suite', lambda suite: ['invalid expectation'])
    monkeypatch.setattr(cli, '_resolve_suite', lambda arg: (suite, label))
    monkeypatch.setattr(cli, 'check_endpoint', lambda *a, **kw: pytest.fail('invalid suite accessed network'))
    assert cli.main(['doctor', '--model', 'wanted', '--format', 'json']) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'fail'
    assert len(report['checks']) == 1


def test_cli_blank_model_and_missing_suite_fail_before_network(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, 'check_endpoint', lambda *a, **kw: pytest.fail('invalid input accessed network'))
    assert cli.main(['doctor', '--model', ' ']) == 2
    assert 'model must not be blank' in capsys.readouterr().err
    assert cli.main(['doctor', '--model', 'wanted', '--suite', str(tmp_path / 'missing')]) == 2
    assert capsys.readouterr().err


def test_real_http_discovery_and_metadata_never_generate_or_forward_auth_to_root(monkeypatch, capsys):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from callprobe.client import probe_server_version

    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.command, self.path, self.headers.get('Authorization')))
            status, body = 404, {}
            if self.path == '/prefix/v1/models':
                status, body = 200, {'data': [{'id': 'wanted'}]}
            elif self.path == '/props':
                status, body = 200, {'build_info': 'b11339-81e39ad34', 'total_slots': 1,
                                     'default_generation_settings': {}, 'chat_template': 'template'}
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_POST(self):
            requests.append((self.command, self.path, None))
            self.send_error(405)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(doctor, 'probe_server_version', probe_server_version)
    monkeypatch.setenv('OPENAI_API_KEY', 'private-local-key')
    monkeypatch.delenv('API_KEY', raising=False)
    try:
        assert cli.main(['doctor', '--model', 'wanted', '--endpoint',
                         f'http://127.0.0.1:{server.server_port}/prefix/v1', '--format', 'json']) == 0
        output = capsys.readouterr().out
        report = json.loads(output)
        assert report['server'] == {'name': 'llama.cpp', 'version': 'b11339-81e39ad34'}
        assert report['status'] == 'pass' and report['generation_tested'] is False
        assert 'private-local-key' not in output
        assert requests == [('GET', '/prefix/v1/models', 'Bearer private-local-key'),
                            ('GET', '/api/version', None), ('GET', '/props', None)]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def config_discovery(monkeypatch):
    calls = []
    def endpoint(url, model, **kwargs):
        calls.append((url, model, kwargs))
        return {'checks': [{'name': 'models', 'status': 'pass', 'message': 'listed'}],
                'server': {'name': None, 'version': None}, 'model_listed': True,
                'generation_tested': False}
    def forbidden(*args, **kwargs):
        pytest.fail('doctor must not generate or write run results')
    monkeypatch.setattr(cli, 'check_endpoint', endpoint)
    monkeypatch.setattr(cli, 'ChatClient', forbidden)
    monkeypatch.setattr(cli, '_write_run', forbidden)
    return calls


def test_config_relative_suite_and_output_are_independent_of_cwd(tmp_path, monkeypatch, capsys, config_discovery):
    folder = tmp_path / 'config'
    folder.mkdir()
    suite = folder / 'suite'
    assert cli.main(['init', '--example', 'support', '--out', str(suite)]) == 0
    capsys.readouterr()
    output = folder / 'existing.json'
    output.write_text('preserve me')
    config = folder / 'run.yaml'
    config.write_text('model: configured\nendpoint: https://example.test/prefix/v1\nsuite: suite\nout: existing.json\nrequest_timeout: 1200\nretries: 99\n')
    before = config.read_bytes()
    monkeypatch.chdir(tmp_path)
    assert cli.main(['doctor', '--config', str(config), '--format', 'json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert '6 tasks' in report['checks'][0]['message']
    assert report['generation_tested'] is False
    assert config_discovery[0][:2] == ('https://example.test/prefix/v1', 'configured')
    assert config_discovery[0][2]['timeout'] == 5.0
    assert output.read_text() == 'preserve me' and config.read_bytes() == before


def test_explicit_discovery_flags_override_file_and_cli_suite_uses_cwd(tmp_path, monkeypatch, capsys, config_discovery):
    folder = tmp_path / 'config'
    folder.mkdir()
    config = folder / 'run.yaml'
    config.write_text('model: configured\nendpoint: https://example.test/v1\nsuite: missing\n')
    assert cli.main(['init', '--example', 'support', '--out', str(tmp_path / 'cli-suite')]) == 0
    capsys.readouterr()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('API_KEY', 'env-value')
    assert cli.main(['doctor', '--config', str(config), '--model', 'explicit',
                     '--endpoint', 'http://localhost:7777/v1', '--suite', 'cli-suite',
                     '--timeout', '0.25', '--api-key', 'explicit-key', '--format', 'json']) == 0
    assert config_discovery == [('http://localhost:7777/v1', 'explicit',
                                {'api_key': 'explicit-key', 'timeout': 0.25})]
    output = capsys.readouterr().out
    assert '6 tasks' in output and 'explicit-key' not in output


def test_config_missing_discovery_fields_uses_defaults(tmp_path, capsys, config_discovery):
    config = tmp_path / 'run.yaml'
    config.write_text('model: configured\nout: never-created.json\n')
    assert cli.main(['doctor', '--config', str(config), '--format', 'json']) == 0
    assert '50 tasks' in capsys.readouterr().out
    assert config_discovery[0][:2] == (cli.RUN_DEFAULTS['endpoint'], 'configured')
    assert not (tmp_path / 'never-created.json').exists()


@pytest.mark.parametrize('text', [
    'model: first\nmodel: second\n',
    'model: configured\napi_key: PRIVATE_KEY\n',
    'model: configured\nunknown: PRIVATE_VALUE\n',
    'model: configured\nrepeats: false\n',
    'model: configured\nrequest_timeout: 0\n',
    'model: [PRIVATE_MODEL]\n',
])
def test_bad_config_rejected_before_network_even_with_overrides(tmp_path, capsys, config_discovery, text):
    config = tmp_path / 'bad.yaml'
    config.write_text(text)
    assert cli.main(['doctor', '--config', str(config), '--model', 'override']) == 2
    assert not config_discovery
    assert 'PRIVATE' not in capsys.readouterr().err


def test_missing_model_and_missing_config_stop_before_network(tmp_path, capsys, config_discovery):
    config = tmp_path / 'run.yaml'
    config.write_text('repeats: 2\n')
    assert cli.main(['doctor', '--config', str(config)]) == 2
    assert '--model is required' in capsys.readouterr().err
    assert cli.main(['doctor']) == 2
    assert '--model is required' in capsys.readouterr().err
    assert cli.main(['doctor', '--config', str(tmp_path / 'missing'), '--model', 'm']) == 2
    assert not config_discovery


def test_explicit_blank_model_does_not_fall_back_to_config(tmp_path, capsys, config_discovery):
    config = tmp_path / 'run.yaml'
    config.write_text('model: configured\n')
    assert cli.main(['doctor', '--config', str(config), '--model', ' ']) == 2
    assert 'model must not be blank' in capsys.readouterr().err
    assert not config_discovery
