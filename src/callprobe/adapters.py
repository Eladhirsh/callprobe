"""Offline normalization of completed provider responses for recording APIs."""

from __future__ import annotations

from typing import Any

from .client import Completion, parse_completion
from .recordings import _validate_completion


def parse_ollama_completion(body: dict[str, Any], latency_ms: float = 0.0) -> Completion:
    """Normalize one full, non-streaming Ollama ``/api/chat`` response.

    Pass a decoded JSON object (or an SDK response's ``model_dump()``), collected
    with ``stream=False``. Individual stream chunks are not full decisions, even
    when a terminal chunk says done. This function does not aggregate chunks,
    make requests, execute tools, or use server duration as client latency.
    ``latency_ms`` is the caller's measured elapsed request time; omitted means
    unknown/zero, as in parse_completion. Malformed/error envelopes raise a
    generic ValueError rather than turning into successful empty completions.
    """
    try:
        if not isinstance(body, dict) or 'error' in body or body.get('done') is not True:
            raise ValueError('expected a completed response')
        if body.get('done_reason') in ('load', 'unload'):
            raise ValueError('model lifecycle response is not a decision')
        message = body.get('message')
        if not isinstance(message, dict) or message.get('role') != 'assistant':
            raise ValueError('expected an assistant message')
        calls = message.get('tool_calls')
        if calls is not None:
            if not isinstance(calls, list):
                raise ValueError('expected tool calls')
            for call in calls:
                if not isinstance(call, dict) or not isinstance(call.get('function'), dict):
                    raise ValueError('expected a function call')
                if not isinstance(call['function'].get('arguments'), dict):
                    raise ValueError('expected native object arguments')
        completion = parse_completion({
            'choices': [{
                'message': {
                    'content': message.get('content'),
                    'reasoning': message.get('thinking'),
                    'tool_calls': calls,
                },
                'finish_reason': body.get('done_reason'),
            }],
            'usage': {
                'prompt_tokens': body.get('prompt_eval_count'),
                'completion_tokens': body.get('eval_count'),
            },
        }, latency_ms=latency_ms)
        _validate_completion(completion, 0)
    except (AttributeError, TypeError, ValueError, IndexError, KeyError, OverflowError):
        raise ValueError('invalid completed Ollama chat response') from None
    completion.raw = body
    return completion
