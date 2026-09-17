from __future__ import annotations
import base64,json,os
from pathlib import Path
from typing import Any


class EncryptedSync:
    """End-to-end encrypted state bundle. The sync transport only sees ciphertext."""
    @staticmethod
    def new_key()->str:
        return base64.urlsafe_b64encode(os.urandom(32)).decode()
    @staticmethod
    def encrypt(payload:dict[str,Any],key_b64:str)->bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key=base64.urlsafe_b64decode(key_b64); nonce=os.urandom(12); data=json.dumps(payload,ensure_ascii=False,separators=(",",":"),default=str).encode()
        return b"IRAS5\0"+nonce+AESGCM(key).encrypt(nonce,data,b"iras-v5-sync")
    @staticmethod
    def decrypt(blob:bytes,key_b64:str)->dict[str,Any]:
        if not blob.startswith(b"IRAS5\0"): raise ValueError("Invalid IRAS sync bundle")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key=base64.urlsafe_b64decode(key_b64); nonce=blob[6:18]; plain=AESGCM(key).decrypt(nonce,blob[18:],b"iras-v5-sync")
        return json.loads(plain.decode())
