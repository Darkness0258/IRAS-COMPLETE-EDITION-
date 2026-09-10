from __future__ import annotations
import os
import httpx
from iras.models import PermissionLevel
from iras.tools.base import Tool
from iras.tools.web import _validate_public


def classify(args):
    method=str(args.get('method','GET')).upper()
    if method=='DELETE': return PermissionLevel.CRITICAL
    if method in {'POST','PUT','PATCH'}: return PermissionLevel.SYSTEM_ACTION
    return PermissionLevel.READ


def api_request(url, method='GET', headers=None, json_body=None, auth_env=None, auth_scheme='Bearer', max_chars=30000):
    _validate_public(url)
    method=method.upper()
    if method not in {'GET','HEAD','POST','PUT','PATCH','DELETE'}: raise ValueError('Unsupported HTTP method.')
    clean_headers={str(k):str(v) for k,v in (headers or {}).items() if str(k).lower() not in {'authorization','cookie','proxy-authorization'}}
    if auth_env:
        if not auth_env.startswith('IRAS_SECRET_'): raise ValueError('auth_env must start with IRAS_SECRET_.')
        token=os.getenv(auth_env)
        if not token: raise RuntimeError(f'Secret environment variable {auth_env} is not configured.')
        clean_headers['Authorization']=f'{auth_scheme} {token}'.strip()
    with httpx.Client(timeout=45,follow_redirects=False,headers={'User-Agent':'IRAS/1.0',**clean_headers}) as c:
        r=c.request(method,url,json=json_body)
    return {'status':r.status_code,'content_type':r.headers.get('content-type'),'location':r.headers.get('location'),'text':r.text[:max_chars]}

TOOLS=[Tool(
    'api_request',
    'Call an authorized PUBLIC internet API. For authentication, reference a secret environment variable named IRAS_SECRET_*; raw Authorization/Cookie headers are blocked. Mutating methods require elevated approval.',
    {'type':'object','properties':{
        'url':{'type':'string'},'method':{'type':'string','enum':['GET','HEAD','POST','PUT','PATCH','DELETE']},
        'headers':{'type':'object','additionalProperties':{'type':'string'}},'json_body':{'type':'object'},
        'auth_env':{'type':'string'},'auth_scheme':{'type':'string'},'max_chars':{'type':'integer'}
    },'required':['url']},
    api_request,PermissionLevel.READ,classify
)]
