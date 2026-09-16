from __future__ import annotations

"""Small OS-backed secret protection helper.

On Windows IRAS uses DPAPI with the current user's profile, so copied config files
cannot be decrypted by another Windows account or machine. Other platforms use a
clearly marked base64 fallback because the v4 remote bridge is Windows-first and
we do not want to pretend plain local test storage is encrypted.
"""

import base64
import ctypes
from ctypes import wintypes
import os


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _blob_from_bytes(data: bytes) -> tuple[_DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DATA_BLOB(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    return blob, buffer


def _bytes_from_blob(blob: _DATA_BLOB) -> bytes:
    if not blob.pbData or not blob.cbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def _dpapi_protect(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source, _source_buffer = _blob_from_bytes(data)
    output = _DATA_BLOB()
    # CRYPTPROTECT_UI_FORBIDDEN keeps background bridge startup non-interactive.
    ok = crypt32.CryptProtectData(
        ctypes.byref(source),
        "IRAS secret",
        None,
        None,
        None,
        0x1,
        ctypes.byref(output),
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), "CryptProtectData failed")
    try:
        return _bytes_from_blob(output)
    finally:
        if output.pbData:
            kernel32.LocalFree(output.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source, _source_buffer = _blob_from_bytes(data)
    output = _DATA_BLOB()
    description = wintypes.LPWSTR()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(source),
        ctypes.byref(description),
        None,
        None,
        None,
        0x1,
        ctypes.byref(output),
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), "CryptUnprotectData failed")
    try:
        return _bytes_from_blob(output)
    finally:
        if output.pbData:
            kernel32.LocalFree(output.pbData)
        if description:
            kernel32.LocalFree(description)


def protect_secret(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    raw = text.encode("utf-8")
    if os.name == "nt":
        protected = _dpapi_protect(raw)
        return "dpapi:" + base64.urlsafe_b64encode(protected).decode("ascii")
    return "plain64:" + base64.urlsafe_b64encode(raw).decode("ascii")


def unprotect_secret(value: str) -> str:
    encoded = str(value or "").strip()
    if not encoded:
        return ""
    if encoded.startswith("dpapi:"):
        raw = base64.urlsafe_b64decode(encoded[6:].encode("ascii"))
        if os.name != "nt":
            raise RuntimeError("A Windows DPAPI secret cannot be decrypted on this platform.")
        return _dpapi_unprotect(raw).decode("utf-8")
    if encoded.startswith("plain64:"):
        raw = base64.urlsafe_b64decode(encoded[8:].encode("ascii"))
        return raw.decode("utf-8")
    # Backward compatibility: older device-bridge config stored the token in
    # plaintext. Callers should immediately rewrite it through protect_secret.
    return encoded


def protection_backend() -> str:
    return "windows-dpapi" if os.name == "nt" else "plain-test-fallback"
