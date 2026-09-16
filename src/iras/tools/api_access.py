from __future__ import annotations
import json
import os
import re
import httpx
from iras.models import PermissionLevel
from iras.tools.base import Tool
from iras.tools.web import _validate_public, _bounded_response_bytes, _decode_response, _is_textual_content_type


def classify(args):
    method = str(args.get('method', 'GET')).upper()
    if method == 'DELETE': return PermissionLevel.CRITICAL
    if method in {'POST', 'PUT', 'PATCH'}: return PermissionLevel.SYSTEM_ACTION
    return PermissionLevel.READ


def _clean_headers(headers):
    blocked = {'authorization', 'cookie', 'proxy-authorization', 'host', 'content-length', 'transfer-encoding', 'connection'}
    clean = {}
    for key, value in (headers or {}).items():
        name, text = str(key), str(value)
        if name.lower() in blocked:
            continue
        if '\r' in name or '\n' in name or '\r' in text or '\n' in text:
            raise ValueError('HTTP header names/values may not contain CR/LF characters.')
        if len(name) > 128 or len(text) > 4096:
            raise ValueError('HTTP header is too large.')
        clean[name] = text
    if len(clean) > 40:
        raise ValueError('Too many HTTP headers.')
    return clean


def api_request(url, method='GET', headers=None, json_body=None, auth_env=None, auth_scheme='Bearer', max_chars=30000):
    _validate_public(url)
    method = str(method or 'GET').upper()
    if method not in {'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE'}:
        raise ValueError('Unsupported HTTP method.')
    max_chars = max(1, min(int(max_chars), 100000))
    clean_headers = _clean_headers(headers)
    if auth_env:
        if not re.fullmatch(r'IRAS_SECRET_[A-Z0-9_]{1,96}', str(auth_env)):
            raise ValueError('auth_env must be an IRAS_SECRET_* environment variable name.')
        token = os.getenv(auth_env)
        if not token:
            raise RuntimeError(f'Secret environment variable {auth_env} is not configured.')
        scheme = str(auth_scheme or 'Bearer').strip()
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9._-]{0,31}', scheme):
            raise ValueError('Invalid authentication scheme.')
        clean_headers['Authorization'] = f'{scheme} {token}'.strip()
    if json_body is not None:
        encoded = json.dumps(json_body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        if len(encoded) > 256_000:
            raise ValueError('JSON request body exceeds the 256 KB safety limit.')
    with httpx.Client(
        timeout=httpx.Timeout(45.0, connect=10.0),
        follow_redirects=False,
        headers={'User-Agent': 'IRAS/4.3', **clean_headers},
    ) as client:
        with client.stream(method, url, json=json_body) as response:
            raw = _bounded_response_bytes(response, max_bytes=2_000_000)
            status = response.status_code
            content_type = response.headers.get('content-type')
            location = response.headers.get('location')
            final_url = str(response.url)
    if not _is_textual_content_type(content_type):
        raise ValueError(f"api_request only accepts text/JSON/XML responses, not {content_type or 'binary data'!r}.")
    text_raw = _decode_response(response, raw)
    return {
        'status': status,
        'content_type': content_type,
        'location': location,
        'url': final_url,
        'text': text_raw[:max_chars],
        'truncated': len(text_raw) > max_chars,
        'bytes': len(raw),
    }


TOOLS = [Tool(
    'api_request',
    'Call an authorized PUBLIC internet API with bounded request/response sizes. For authentication, reference a secret environment variable named IRAS_SECRET_*; raw Authorization/Cookie headers are blocked. Mutating methods require elevated approval.',
    {'type': 'object', 'properties': {
        'url': {'type': 'string', 'maxLength': 4096},
        'method': {'type': 'string', 'enum': ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE']},
        'headers': {'type': 'object', 'additionalProperties': {'type': 'string'}},
        'json_body': {'type': 'object'},
        'auth_env': {'type': 'string', 'maxLength': 112},
        'auth_scheme': {'type': 'string', 'maxLength': 32},
        'max_chars': {'type': 'integer', 'minimum': 1, 'maximum': 100000},
    }, 'required': ['url']},
    api_request, PermissionLevel.READ, classify
)]
