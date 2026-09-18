from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
import json,re
from typing import Callable,Any
from .common import new_id,utc_now
_SAFE_NAME=re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{1,80}$")
@dataclass
class CapabilityProposal:
    proposal_id:str; name:str; description:str; source:str; tests:str; permission:str; version:str="0.1.0"; status:str="proposed"; created_at:str=""; test_result:str=""
class CapabilityLearner:
    def __init__(self,root:str|Path):
        self.root=Path(root);self.proposals=self.root/"proposals";self.installed=self.root/"installed";self.proposals.mkdir(parents=True,exist_ok=True);self.installed.mkdir(parents=True,exist_ok=True)
    def propose(self,*,name:str,description:str,source:str,tests:str="",permission:str="READ",version:str="0.1.0")->CapabilityProposal:
        if not _SAFE_NAME.match(name):raise ValueError("Invalid capability name.")
        p=CapabilityProposal(new_id("cap_"),name,description[:4000],source,tests,permission.upper(),version,created_at=utc_now());self._save(p);return p
    def _path(self,pid:str)->Path:return self.proposals/f"{pid}.json"
    def _save(self,p):self._path(p.proposal_id).write_text(json.dumps(asdict(p),ensure_ascii=False,indent=2),encoding="utf-8")
    def load(self,pid:str)->CapabilityProposal:return CapabilityProposal(**json.loads(self._path(pid).read_text(encoding="utf-8")))
    def list(self)->list[dict[str,Any]]:
        out=[]
        for p in self.proposals.glob("*.json"):
            try:out.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:pass
        return sorted(out,key=lambda x:x.get("created_at",""),reverse=True)
    def installed_list(self)->list[dict[str,Any]]:
        out=[]
        for manifest in self.installed.glob("*/*/manifest.json"):
            try:
                data=json.loads(manifest.read_text(encoding="utf-8"));data["path"]=str(manifest.parent);out.append(data)
            except Exception:pass
        return sorted(out,key=lambda x:(x.get("name",""),x.get("version","")))

    def test(self,pid:str,sandbox_runner:Callable[[str,str],dict[str,Any]])->CapabilityProposal:
        p=self.load(pid);result=sandbox_runner(p.source,p.tests);p.test_result=json.dumps(result,ensure_ascii=False,default=str)[:16000];p.status="tested" if result.get("ok") else "test_failed";self._save(p);return p
    def approve_install(self,pid:str,*,approved:bool)->Path:
        if not approved:raise PermissionError("Human approval is required to install a learned capability.")
        p=self.load(pid)
        if p.status!="tested":raise RuntimeError("Capability must pass sandbox testing before installation.")
        target=self.installed/p.name/p.version;target.mkdir(parents=True,exist_ok=True);(target/"capability.py").write_text(p.source,encoding="utf-8");(target/"manifest.json").write_text(json.dumps({"name":p.name,"version":p.version,"permission":p.permission,"installed_at":utc_now()},indent=2),encoding="utf-8");p.status="installed";self._save(p);return target
    def uninstall(self,name:str,version:str,*,approved:bool=False)->None:
        if not approved:raise PermissionError("Capability uninstall requires approval.")
        import shutil;target=self.installed/name/version
        if target.exists():shutil.rmtree(target)
