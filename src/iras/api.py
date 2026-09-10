from __future__ import annotations
from fastapi import FastAPI,Header,HTTPException
from pydantic import BaseModel
import uvicorn
from iras.bootstrap import build_runtime
from iras.config import Settings
from iras.models import PermissionLevel

settings=Settings.load(); runtime=build_runtime(settings,approval_callback=None,hard_cap=PermissionLevel.SAFE_ACTION); app=FastAPI(title='IRAS Local API',version='1.0.0')
class ChatIn(BaseModel): message:str

def auth(authorization:str|None):
    if settings.api_token and settings.api_token!='change-me-before-remote-use':
        if authorization!=f'Bearer {settings.api_token}': raise HTTPException(401,'Invalid token')
@app.get('/health')
def health(): return {'ok':True,'provider':settings.provider,'model':settings.model}
@app.get('/tools')
def tools(authorization:str|None=Header(default=None)): auth(authorization); return runtime.registry.describe()
@app.post('/chat')
def chat(body:ChatIn,authorization:str|None=Header(default=None)): auth(authorization); return {'response':runtime.agent.handle(body.message)}
def main(): uvicorn.run(app,host='127.0.0.1',port=8765)
