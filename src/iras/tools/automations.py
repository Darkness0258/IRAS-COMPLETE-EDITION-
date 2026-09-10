from __future__ import annotations
from datetime import datetime,timezone
from iras.models import PermissionLevel
from iras.tools.base import Tool

def make_tools(store):
    def schedule_prompt(next_run,prompt,interval_seconds=None):
        datetime.fromisoformat(next_run.replace('Z','+00:00')); return {'id':store.add(next_run,prompt,interval_seconds)}
    def list_schedules(): return store.list()
    def cancel_schedule(id): return store.cancel(int(id))
    return [
      Tool('schedule_prompt','Schedule a future local IRAS prompt. next_run must be ISO-8601; interval_seconds may repeat (minimum 60).',{'type':'object','properties':{'next_run':{'type':'string'},'prompt':{'type':'string'},'interval_seconds':{'type':'integer','minimum':60}},'required':['next_run','prompt']},schedule_prompt,PermissionLevel.SAFE_ACTION),
      Tool('list_schedules','List local scheduled IRAS prompts.',{'type':'object','properties':{}},list_schedules,PermissionLevel.READ),
      Tool('cancel_schedule','Cancel a scheduled prompt.',{'type':'object','properties':{'id':{'type':'integer'}},'required':['id']},cancel_schedule,PermissionLevel.SAFE_ACTION),
    ]
