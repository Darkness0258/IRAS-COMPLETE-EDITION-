from iras.tools.web import _validate_public

def test_private_blocked():
    try:_validate_public('http://127.0.0.1:8000')
    except PermissionError:return
    assert False
