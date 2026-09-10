from iras.security.audit import AuditLogger

def test_redaction(tmp_path):
    p=tmp_path/'a.jsonl'; a=AuditLogger(p); a.record('x',{'api_key':'secret','authorization':'Bearer abcdefghijk'}); s=p.read_text(); assert 'secret' not in s and 'abcdefghijk' not in s
