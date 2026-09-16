from __future__ import annotations

from pathlib import Path

from iras.device_bridge.verifiers import SemanticVerifier


class _Computer:
    def _foreground(self):
        return {"title": "Notes - Notepad"}

    def verify(self, **kwargs):
        return {"verified": kwargs.get("target") == "Hello"}


class _Executor:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.computer = _Computer()

    def _path(self, value, must_exist=True):
        path = Path(value).resolve()
        path.relative_to(self.root)
        return path


def test_semantic_verifier_files_foreground_and_text(tmp_path):
    target = tmp_path / "x.txt"
    target.write_text("x", encoding="utf-8")
    verifier = SemanticVerifier(_Executor(tmp_path))
    assert verifier.verify("file_exists", str(target))["verified"]
    assert verifier.verify("foreground_title_contains", "Notepad")["verified"]
    assert verifier.verify("screen_text", "Hello")["verified"]
