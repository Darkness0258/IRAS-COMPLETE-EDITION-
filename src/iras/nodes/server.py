from __future__ import annotations
from fastapi import FastAPI,Header,HTTPException
from pydantic import BaseModel
import uvicorn
from iras.bootstrap import build_runtime
from iras.config import Settings
from iras.models import PermissionLevel
s=Settings.load(); cap=PermissionLevel(max(0,min(s.node_max_permission_level,2))); rt=build_runtime(s,None,cap); app=FastAPI(title='IRAS Node',version='1.0.0')
class Invoke(BaseModel): name:str; arguments:dict={}
def auth(a):
    if not s.node_token or s.node_token=='change-me-before-remote-use': raise HTTPException(503,'Set a strong IRAS_NODE_TOKEN before using node execution.')
    if a!=f'Bearer {s.node_token}': raise HTTPException(401,'Invalid node token')
@app.get('/health')
def health(): return {'ok':True,'max_permission':cap.name}
@app.post('/invoke')
def invoke(body:Invoke,authorization:str|None=Header(default=None)):
    auth(authorization); r=rt.registry.execute(body.name,body.arguments); return {'ok':r.ok,'output':r.output,'error':r.error,'permission':r.permission.name}
def main(): uvicorn.run(app,host='127.0.0.1',port=8770)
