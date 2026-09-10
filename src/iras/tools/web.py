from __future__ import annotations
import ipaddress,socket,webbrowser
from urllib.parse import urlparse
import httpx
from iras.models import PermissionLevel
from iras.tools.base import Tool

def _validate_public(url):
    u=urlparse(url)
    if u.scheme not in {'http','https'} or not u.hostname: raise ValueError('Only http/https URLs are allowed.')
    for info in socket.getaddrinfo(u.hostname,u.port or (443 if u.scheme=='https' else 80),type=socket.SOCK_STREAM):
        ip=ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise PermissionError('Private/local network destinations are blocked by http_get.')
def http_get(url,max_chars=30000):
    _validate_public(url)
    with httpx.Client(timeout=30,follow_redirects=False,headers={'User-Agent':'IRAS/1.0'}) as c:
        r=c.get(url); text=r.text[:max_chars]
    return {'status':r.status_code,'content_type':r.headers.get('content-type'),'location':r.headers.get('location'),'text':text}
def open_url(url):
    if urlparse(url).scheme not in {'http','https'}: raise ValueError('Only http/https URLs are allowed.')
    return {'opened':bool(webbrowser.open(url)),'url':url}
TOOLS=[
 Tool('http_get','Fetch text from a PUBLIC internet URL. Private/local IPs are blocked.',{'type':'object','properties':{'url':{'type':'string'},'max_chars':{'type':'integer'}},'required':['url']},http_get,PermissionLevel.READ),
 Tool('open_url','Open an http/https URL in the user default browser.',{'type':'object','properties':{'url':{'type':'string'}},'required':['url']},open_url,PermissionLevel.SAFE_ACTION),
]
