from __future__ import annotations

from dataclasses import dataclass, asdict
import base64
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


@dataclass
class SkillManifest:
    skill_id: str
    version: str
    description: str
    permissions: list[str]
    entrypoint: str
    publisher: str = ""


class SkillMarketplace:
    """Signed skill package store.

    RC3 signatures authenticate both the manifest and every package file. This
    prevents a valid manifest signature from being reused with modified skill code.
    """

    SIGNATURE_FORMAT = "iras-skill-ed25519-sha256-v2"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _file_hashes(files: dict[str, str] | None = None) -> dict[str, str]:
        result: dict[str, str] = {}
        for name, content in sorted((files or {}).items()):
            result[str(name)] = hashlib.sha256(str(content).encode("utf-8")).hexdigest()
        return result

    @staticmethod
    def _payload(m: SkillManifest, files: dict[str, str] | None = None) -> bytes:
        package = {
            "format": SkillMarketplace.SIGNATURE_FORMAT,
            "manifest": asdict(m),
            "files_sha256": SkillMarketplace._file_hashes(files),
        }
        return json.dumps(package, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

    @staticmethod
    def verify_signature(
        m: SkillManifest,
        signature_b64: str,
        public_key_b64: str,
        files: dict[str, str] | None = None,
    ) -> bool:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
            key.verify(base64.b64decode(signature_b64), SkillMarketplace._payload(m, files))
            return True
        except Exception:
            return False

    def install(
        self,
        m: SkillManifest,
        files: dict[str, str],
        *,
        signature_b64: str,
        public_key_b64: str,
        approved: bool = False,
    ) -> str:
        if not approved:
            raise PermissionError("Skill installation requires explicit approval.")
        if not files or m.entrypoint not in files:
            raise ValueError("Signed skill package must include its declared entrypoint.")
        if not self.verify_signature(m, signature_b64, public_key_b64, files):
            raise ValueError("Invalid skill package signature.")
        target = (self.root / m.skill_id / m.version).resolve()
        if self.root.resolve() not in target.parents:
            raise ValueError("Unsafe skill path")
        if target.exists():
            raise FileExistsError(f"Skill version is already installed: {m.skill_id} {m.version}")
        target.mkdir(parents=True, exist_ok=False)
        try:
            for name, content in files.items():
                p = (target / name).resolve()
                if target not in p.parents:
                    raise ValueError("Skill file escaped package root")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(str(content), encoding="utf-8")
            (target / "manifest.json").write_text(
                json.dumps(
                    {
                        **asdict(m),
                        "signature_format": self.SIGNATURE_FORMAT,
                        "files_sha256": self._file_hashes(files),
                        "publisher_public_key": public_key_b64,
                        "signature_b64": signature_b64,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return str(target)

    def verify_installed(self, skill_id: str, version: str) -> dict[str, Any]:
        target = (self.root / skill_id / version).resolve()
        if self.root.resolve() not in target.parents:
            raise ValueError("Unsafe skill path")
        manifest_path = target / "manifest.json"
        if not manifest_path.is_file():
            return {"skill_id": skill_id, "version": version, "integrity_ok": False, "reason": "manifest_missing"}
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        hashes = dict(data.get("files_sha256") or {})
        files: dict[str, str] = {}
        for name, expected in hashes.items():
            path = (target / name).resolve()
            if target not in path.parents or not path.is_file():
                return {"skill_id": skill_id, "version": version, "integrity_ok": False, "reason": f"file_missing:{name}"}
            content = path.read_text(encoding="utf-8")
            actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if actual != expected:
                return {"skill_id": skill_id, "version": version, "integrity_ok": False, "reason": f"hash_mismatch:{name}"}
            files[name] = content
        try:
            manifest = SkillManifest(
                skill_id=str(data["skill_id"]), version=str(data["version"]),
                description=str(data.get("description") or ""), permissions=list(data.get("permissions") or []),
                entrypoint=str(data["entrypoint"]), publisher=str(data.get("publisher") or ""),
            )
        except Exception as exc:
            return {"skill_id": skill_id, "version": version, "integrity_ok": False, "reason": f"manifest_invalid:{exc}"}
        signature_ok = self.verify_signature(
            manifest, str(data.get("signature_b64") or ""),
            str(data.get("publisher_public_key") or ""), files,
        )
        return {
            "skill_id": skill_id, "version": version, "integrity_ok": bool(signature_ok),
            "signature_format": data.get("signature_format"),
            "reason": "ok" if signature_ok else "signature_invalid",
        }

    def list(self) -> list[dict[str, Any]]:
        out = []
        for p in self.root.glob("*/*/manifest.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                d["path"] = str(p.parent)
                integrity = self.verify_installed(str(d.get("skill_id") or p.parent.parent.name), str(d.get("version") or p.parent.name))
                d["integrity_ok"] = bool(integrity.get("integrity_ok"))
                d["integrity_reason"] = integrity.get("reason")
                out.append(d)
            except Exception:
                pass
        return out

    def uninstall(self, skill_id: str, version: str, *, approved: bool = False) -> None:
        if not approved:
            raise PermissionError("Skill uninstall requires approval.")
        target = (self.root / skill_id / version).resolve()
        if self.root.resolve() not in target.parents:
            raise ValueError("Unsafe skill path")
        if target.exists():
            shutil.rmtree(target)
