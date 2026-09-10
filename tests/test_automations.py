from iras.memory.store import MemoryStore
from iras.automations.store import AutomationStore
from datetime import datetime,timezone,timedelta

def test_schedule(tmp_path):
    m=MemoryStore(tmp_path/'m.db'); s=AutomationStore(m); when=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(); i=s.add(when,'hello'); assert s.due()[0]['id']==i; s.finish(s.due()[0],'ok'); assert s.list()[0]['enabled']==0
