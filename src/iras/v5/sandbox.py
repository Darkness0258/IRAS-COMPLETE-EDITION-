from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any


@dataclass
class SandboxResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    backend: str


class SandboxRunner:
    """Docker-first isolated execution. Local fallback is opt-in only."""

    def __init__(self, *, docker_image: str = "python:3.13-slim", allow_local_fallback: bool = False):
        self.docker_image=docker_image; self.allow_local_fallback=allow_local_fallback

    @property
    def docker_available(self)->bool: return shutil.which("docker") is not None

    def run_python(self, source:str, tests:str="", *, timeout:int=60)->dict[str,Any]:
        with tempfile.TemporaryDirectory(prefix="iras-sandbox-") as td:
            root=Path(td); (root/"capability.py").write_text(source,encoding="utf-8")
            harness=tests or "import capability\nprint('import-ok')\n"
            (root/"test_capability.py").write_text(harness,encoding="utf-8")
            if self.docker_available:
                cmd=["docker","run","--rm","--network","none","--read-only","--pids-limit","128","--memory","256m",
                     "-v",f"{root}:/work:ro","-w","/work",self.docker_image,"python","test_capability.py"]
                backend="docker"
            elif self.allow_local_fallback:
                code = "import sys; sys.path.insert(0, %r); exec(open(%r, encoding=\"utf-8\").read(), {\"__name__\":\"__main__\"})" % (str(root), str(root / "test_capability.py"))
                cmd=["python","-I","-c",code]; backend="local-isolated-process"
            else:
                return {"ok":False,"stdout":"","stderr":"Docker sandbox unavailable and local fallback disabled.","returncode":127,"backend":"unavailable"}
            try:
                p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,shell=False,cwd=root if backend.startswith("local") else None,
                                 env={"PYTHONIOENCODING":"utf-8"} if backend.startswith("local") else None)
                return {"ok":p.returncode==0,"stdout":p.stdout[-20000:],"stderr":p.stderr[-10000:],"returncode":p.returncode,"backend":backend}
            except subprocess.TimeoutExpired:
                return {"ok":False,"stdout":"","stderr":"Sandbox timed out.","returncode":124,"backend":backend}
