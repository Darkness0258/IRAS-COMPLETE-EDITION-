import httpx
import pytest

from iras.providers.openrouter import OpenRouterProvider


def test_openrouter_requires_key():
    with pytest.raises(ValueError):
        OpenRouterProvider('', 'openrouter/free')


def test_openrouter_headers():
    p = OpenRouterProvider('secret-key', 'openrouter/free')
    headers = p._headers()
    assert headers['Authorization'] == 'Bearer secret-key'
    assert headers['HTTP-Referer'].startswith('https://')
    assert headers['X-Title'] == 'IRAS'


def test_openrouter_payload_includes_tools():
    p = OpenRouterProvider('secret-key', 'openrouter/free')
    payload = p._payload(
        [{'role': 'user', 'content': 'hello'}],
        [{'type': 'function', 'function': {'name': 'x', 'parameters': {'type': 'object'}}}],
    )
    assert payload['model'] == 'openrouter/free'
    assert payload['tool_choice'] == 'auto'
    assert payload['tools']
