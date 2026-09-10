from __future__ import annotations
from pathlib import Path
import shutil
from iras.models import PermissionLevel
from iras.tools.base import Tool

def P(p): return Path(p).expanduser().resolve()
def list_directory(path='.', include_hidden=False):
    p=P(path)
    if not p.is_dir(): raise NotADirectoryError(p)
    out=[]
    for x in sorted(p.iterdir(), key=lambda z:z.name.lower()):
        if not include_hidden and x.name.startswith('.'): continue
        out.append({'name':x.name,'type':'dir' if x.is_dir() else 'file','size':x.stat().st_size if x.is_file() else None})
    return out[:1000]
def read_text(path,max_chars=30000):
    p=P(path)
    if not p.is_file(): raise FileNotFoundError(p)
    return p.read_text(encoding='utf-8',errors='replace')[:max_chars]
def write_text(path,content,append=False):
    p=P(path); p.parent.mkdir(parents=True,exist_ok=True); mode='a' if append else 'w';
    with p.open(mode,encoding='utf-8') as f: f.write(content)
    return {'path':str(p),'bytes':p.stat().st_size}
def make_directory(path): p=P(path); p.mkdir(parents=True,exist_ok=True); return str(p)
def copy_path(source,destination):
    s,d=P(source),P(destination)
    if s.is_dir(): shutil.copytree(s,d,dirs_exist_ok=True)
    else: d.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(s,d)
    return str(d)
def move_path(source,destination): d=P(destination); d.parent.mkdir(parents=True,exist_ok=True); return str(shutil.move(str(P(source)),str(d)))
def delete_path(path):
    p=P(path)
    if p.is_dir(): shutil.rmtree(p)
    elif p.exists(): p.unlink()
    else: raise FileNotFoundError(p)
    return {'deleted':str(p)}

OBJ={'type':'object','properties':{}}
TOOLS=[
 Tool('list_directory','List a local directory.',{'type':'object','properties':{'path':{'type':'string'},'include_hidden':{'type':'boolean'}},'required':['path']},list_directory,PermissionLevel.READ),
 Tool('read_text','Read a local text file.',{'type':'object','properties':{'path':{'type':'string'},'max_chars':{'type':'integer'}},'required':['path']},read_text,PermissionLevel.READ),
 Tool('write_text','Create or overwrite/append a text file.',{'type':'object','properties':{'path':{'type':'string'},'content':{'type':'string'},'append':{'type':'boolean'}},'required':['path','content']},write_text,PermissionLevel.SYSTEM_ACTION),
 Tool('make_directory','Create a directory.',{'type':'object','properties':{'path':{'type':'string'}},'required':['path']},make_directory,PermissionLevel.SAFE_ACTION),
 Tool('copy_path','Copy a file or directory.',{'type':'object','properties':{'source':{'type':'string'},'destination':{'type':'string'}},'required':['source','destination']},copy_path,PermissionLevel.SYSTEM_ACTION),
 Tool('move_path','Move or rename a file or directory.',{'type':'object','properties':{'source':{'type':'string'},'destination':{'type':'string'}},'required':['source','destination']},move_path,PermissionLevel.SYSTEM_ACTION),
 Tool('delete_path','Permanently delete a file or directory. Destructive.',{'type':'object','properties':{'path':{'type':'string'}},'required':['path']},delete_path,PermissionLevel.CRITICAL),
]
