from __future__ import annotations
import json,uuid
from iras.models import ProviderReply,ToolCall
from iras.providers.base import Provider
class DemoProvider(Provider):
    def complete(self,messages,tools):
        last=messages[-1]
        if last['role']=='tool':
            return ProviderReply('Done. Tool result: '+str(last.get('content',''))[:500],[],{'role':'assistant','content':'Done.'})
        text=str(last.get('content','')).strip(); low=text.lower()
        if low in {'tools','show tools','list tools'}:
            names=', '.join(t['function']['name'] for t in tools); s='Available tools: '+names; return ProviderReply(s,[],{'role':'assistant','content':s})
        mapping=[('list ','list_directory','path'),('read ','read_text','path'),('run ','run_shell','command')]
        for prefix,name,arg in mapping:
            if low.startswith(prefix):
                val=text[len(prefix):].strip(); tc=ToolCall('demo-'+uuid.uuid4().hex[:8],name,{arg:val}); am={'role':'assistant','content':'','tool_calls':[{'id':tc.id,'type':'function','function':{'name':name,'arguments':json.dumps(tc.arguments)}}]}; return ProviderReply('',[tc],am)
        s='IRAS core is online. Connect an OpenAI-compatible or Ollama model for natural reasoning. Demo commands: tools, list PATH, read FILE, run COMMAND.'
        return ProviderReply(s,[],{'role':'assistant','content':s})
