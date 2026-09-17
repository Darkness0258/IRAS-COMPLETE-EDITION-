from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from iras.security.secret_store import protect_secret, unprotect_secret


class SecretVault:
    """Capability-named secret vault.

    Windows uses DPAPI. Non-Windows persistent storage requires an explicit
    32-byte IRAS_VAULT_MASTER_KEY (URL-safe base64) and AES-GCM. Secret values
    never appear in list/status APIs; agents should receive only symbolic refs.
    """

    def __init__(self, path: str | Path, *, master_key: str | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.master_key = str(master_key if master_key is not None else os.getenv("IRAS_VAULT_MASTER_KEY", "")).strip()
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def _load(self) -> dict[str, str]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data):
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _encrypt(self, value: str) -> str:
        if os.name == "nt":
            return protect_secret(value)
        if not self.master_key:
            raise RuntimeError("Secure non-Windows vault storage requires IRAS_VAULT_MASTER_KEY.")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = base64.urlsafe_b64decode(self.master_key.encode("ascii"))
        if len(key) != 32:
            raise ValueError("IRAS_VAULT_MASTER_KEY must decode to exactly 32 bytes.")
        nonce = os.urandom(12)
        cipher = AESGCM(key).encrypt(nonce, value.encode("utf-8"), b"iras-v5-vault")
        return "aesgcm:" + base64.urlsafe_b64encode(nonce + cipher).decode("ascii")

    def _decrypt(self, value: str) -> str:
        if value.startswith("dpapi:") or value.startswith("plain64:"):
            return unprotect_secret(value)
        if not value.startswith("aesgcm:"):
            raise RuntimeError("Unsupported vault encoding.")
        if not self.master_key:
            raise RuntimeError("IRAS_VAULT_MASTER_KEY is required to decrypt this vault.")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = base64.urlsafe_b64decode(self.master_key.encode("ascii"))
        raw = base64.urlsafe_b64decode(value[7:].encode("ascii"))
        return AESGCM(key).decrypt(raw[:12], raw[12:], b"iras-v5-vault").decode("utf-8")

    def set(self, name: str, value: str) -> None:
        if not name or any(x in name for x in "\r\n\0"):
            raise ValueError("Invalid secret name")
        data = self._load()
        data[name] = self._encrypt(value)
        self._save(data)

    def get(self, name: str) -> str:
        data = self._load()
        if name not in data:
            raise KeyError(name)
        return self._decrypt(data[name])

    def delete(self, name: str) -> None:
        data = self._load(); data.pop(name, None); self._save(data)

    def list(self) -> list[str]:
        return sorted(self._load())

    def reference(self, name: str) -> dict[str, str]:
        if name not in self._load():
            raise KeyError(name)
        return {"secret_ref": name}

    @property
    def backend(self) -> str:
        if os.name == "nt":
            return "windows-dpapi"
        return "aes-gcm" if self.master_key else "locked-no-master-key"
