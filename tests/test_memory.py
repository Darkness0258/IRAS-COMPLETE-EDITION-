from iras.memory.store import MemoryStore

def test_memory(tmp_path):
    m=MemoryStore(tmp_path/'m.db'); m.add_message('user','hello'); assert m.recent_messages(1)[0]['content']=='hello'; m.remember('project','IRAS'); assert m.search_facts('IRAS')[0]['key']=='project'
