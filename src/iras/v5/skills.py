from __future__ import annotations
from dataclasses import dataclass,asdict
import base64,json
from pathlib import Path
from typing import Any


@dataclass
class SkillManifest:
    skill_id:str
    version:str
    description:str
    permissions:list[str]
    entrypoint:str
    publisher:str=""


class SkillMarketplace:
    def __init__(self,root:str|Path): self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
    @staticmethod
    def _payload(manifest:SkillManifest)->bytes:
        return json.dumps(asdict(manifest),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    @staticmethod
    def verify_signature(manifest:SkillManifest,signature_b64:str,public_key_b64:str)->bool:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            key=Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64)); key.verify(base64.b64decode(signature_b64),SkillMarketplace._payload(manifest)); return True
        except Exception: return False
    def install(self,manifest:SkillManifest,files:dict[str,str],*,signature_b64:str,public_key_b64:str,approved:bool=False)->str:
        if not approved: raise PermissionError("Skill installation requires explicit approval.")
        if not self.verify_signature(manifest,signature_b64,public_key_b64): raise ValueError("Invalid skill signature.")
        target=(self.root/manifest.skill_id/manifest.version).resolve()
        if self.root.resolve() not in target.parents: raise ValueError("Unsafe skill path")
        target.mkdir(parents=True,exist_ok=True)
        for name,content in files.items():
            p=(target/name).resolve()
            if target not in p.parents: raise ValueError("Skill file escaped package root")
            p.parent.mkdir(parents=True,exist_ok=True); p.write_text(content,encoding="utf-8")
        (target/"manifest.json").write_text(json.dumps(asdict(manifest),indent=2),encoding="utf-8")
        return str(target)
