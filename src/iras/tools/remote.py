from __future__ import annotations
import os,re
from urllib.parse import urlparse
import httpx
from iras.models import PermissionLevel
from iras.tools.base import Tool


def remote_invoke(node_url, token_env, tool_name, arguments=None):
    u=urlparse(node_url)
    if u.scheme not in {'http','https'} or not u.hostname: raise ValueError('node_url must be http/https.')
    if not token_env.startswith('IRAS_SECRET_'): raise ValueError('token_env must start with IRAS_SECRET_.')
    token=os.getenv(token_env)
    if not token: raise RuntimeError(f'Secret environment variable {token_env} is not configured.')
    r=httpx.post(node_url.rstrip('/')+'/invoke',headers={'Authorization':f'Bearer {token}'},json={'name':tool_name,'arguments':arguments or {}},timeout=90)
    if r.status_code>=400: raise RuntimeError(f'Node HTTP {r.status_code}: {r.text[:1000]}')
    return r.json()

TOOLS=[Tool(
    'remote_invoke',
    'Invoke a tool on an authenticated IRAS node running on a computer/server the user owns or is authorized to control. Token is read from an IRAS_SECRET_* environment variable. Requires local approval.',
    {'type':'object','properties':{'node_url':{'type':'string'},'token_env':{'type':'string'},'tool_name':{'type':'string'},'arguments':{'type':'object'}},'required':['node_url','token_env','tool_name']},
    remote_invoke,PermissionLevel.SYSTEM_ACTION
)]
