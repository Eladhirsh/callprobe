"""Read-only endpoint discovery; never generates tokens or downloads models."""
from __future__ import annotations

import math
from urllib.parse import urlsplit

import httpx

from .client import probe_server_version


def validate_endpoint(endpoint: str, timeout: float) -> str:
    """Reject ambiguous/auth-bearing base URLs without echoing their contents."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be a positive finite number')
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        raise ValueError('endpoint must be a valid HTTP(S) API base URL') from None
    if parts.scheme not in ('http', 'https') or not parts.hostname or port == 0:
        raise ValueError('endpoint must be a valid HTTP(S) API base URL')
    if parts.username is not None or parts.password is not None or parts.query or parts.fragment:
        raise ValueError('endpoint must not contain credentials, query parameters, or a fragment; '
                         'use --api-key or API_KEY/OPENAI_API_KEY for authentication')
    if any(ch.isspace() or ord(ch) < 32 for ch in endpoint):
        raise ValueError('endpoint must be a valid HTTP(S) API base URL')
    return endpoint.rstrip('/')


def check_endpoint(endpoint: str, model: str, *, api_key: str | None = None,
                   timeout: float = 5.0, transport: httpx.BaseTransport | None = None) -> dict:
    """A catalog match verifies discovery only, never tool-calling support.

    Catalog absence is inconclusive: some providers restrict model listing or
    accept aliases not listed. No redirects, retries, or completion requests.
    Exception strings and response bodies are deliberately absent from reports.
    """
    endpoint = validate_endpoint(endpoint, timeout)
    if not model.strip():
        raise ValueError('model must not be blank')
    checks = []
    report = {'checks': checks, 'server': {'name': None, 'version': None},
              'model_listed': None, 'generation_tested': False}

    def add(name, status, message):
        checks.append({'name': name, 'status': status, 'message': message})

    headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}
    try:
        with httpx.Client(timeout=timeout, headers=headers, transport=transport,
                          follow_redirects=False) as client:
            response = client.get(f'{endpoint}/models')
    except httpx.TimeoutException:
        add('models', 'fail', 'Model discovery timed out. Check the server and --timeout.')
        return report
    except httpx.TransportError:
        add('models', 'fail', 'Could not connect to model discovery. Check the server, API base URL, network, and TLS configuration.')
        return report
    except (httpx.InvalidURL, ValueError):
        add('models', 'fail', 'The endpoint or authentication settings could not form a valid HTTP request.')
        return report

    status = response.status_code
    if status in (401, 403):
        add('models', 'fail', f'Model discovery returned HTTP {status}. Check the API key and its model-listing permissions.')
    elif status in (404, 405):
        add('models', 'warning', f'Model discovery returned HTTP {status}. Confirm the API base path; this provider may not support GET /models.')
    elif 300 <= status < 400:
        add('models', 'fail', 'Model discovery redirected. Use the final API base URL; redirects are not followed.')
    elif not 200 <= status < 300:
        add('models', 'fail', f'Model discovery returned HTTP {status}. Check provider availability or rate limits.')
    else:
        try:
            body = response.json()
        except ValueError:
            body = None
        data = body.get('data') if isinstance(body, dict) else None
        if (not isinstance(data, list) or any(not isinstance(item, dict)
                or not isinstance(item.get('id'), str) or not item['id'].strip() for item in data)):
            add('models', 'fail', 'Model discovery returned an unexpected response. Check that the URL is an OpenAI-compatible API base, usually ending in /v1.')
        else:
            listed = model in {item['id'] for item in data}
            report['model_listed'] = listed
            add('models', 'pass' if listed else 'warning',
                'Requested model is listed by the endpoint.' if listed else
                'Requested model is not in this catalog. Confirm its exact ID or alias with the provider; catalogs may be incomplete.')
            name, version = probe_server_version(endpoint, timeout=timeout)
            report['server'] = {'name': name, 'version': version}
    return report


def render_doctor(report: dict) -> str:
    lines = ['SETUP CHECK: no model generation, downloads, or tool execution.']
    for check in report['checks']:
        lines.append(f"{check['status'].upper():7} {check['name']}: {check['message']}")
    server = report.get('server', {})
    if server.get('name'):
        lines.append(f"server: {server['name']} ({server['version'] or 'version unknown'})")
    lines.append('Tool-calling support and model quality remain untested; run a small suite next.')
    return '\n'.join(lines)
