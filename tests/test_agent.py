from iras.bootstrap import build_runtime
from iras.config import Settings
from pathlib import Path

def settings(tmp_path):
    return Settings('demo','demo','','http://x',30,1,True,'','',1,'edge','x','whisper_local','base.en',1,tmp_path/'data',tmp_path/'logs',4,'IRAS')
def test_demo_agent(tmp_path):
    rt=build_runtime(settings(tmp_path),lambda r:True); out=rt.agent.handle('tools'); assert 'read_text' in out
def test_demo_read(tmp_path):
    f=tmp_path/'a.txt'; f.write_text('abc'); rt=build_runtime(settings(tmp_path),lambda r:True); out=rt.agent.handle('read '+str(f)); assert 'abc' in out
