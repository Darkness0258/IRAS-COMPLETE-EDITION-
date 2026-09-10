from __future__ import annotations
import httpx
class NodeClient:
    def __init__(self,url,token): self.url=url.rstrip('/'); self.token=token
    def invoke(self,name,arguments):
        r=httpx.post(self.url+'/invoke',headers={'Authorization':f'Bearer {self.token}'},json={'name':name,'arguments':arguments},timeout=90); r.raise_for_status(); return r.json()
