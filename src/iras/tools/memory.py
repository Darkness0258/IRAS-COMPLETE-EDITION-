from __future__ import annotations
from iras.models import PermissionLevel
from iras.tools.base import Tool

def make_tools(store):
    def remember_fact(key,value): store.remember(key,value); return {'remembered':key}
    def search_memory(query,limit=10): return store.search_facts(query,limit)
    return [
      Tool('remember_fact','Store a durable user/project fact in IRAS local memory.',{'type':'object','properties':{'key':{'type':'string'},'value':{'type':'string'}},'required':['key','value']},remember_fact,PermissionLevel.SAFE_ACTION),
      Tool('search_memory','Search durable IRAS facts.',{'type':'object','properties':{'query':{'type':'string'},'limit':{'type':'integer'}},'required':['query']},search_memory,PermissionLevel.READ),
    ]
