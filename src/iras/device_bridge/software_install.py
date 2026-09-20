from __future__ import annotations

import hashlib
import ipaddress
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
import uuid
from urllib.parse import unquote, urljoin, urlparse

import httpx


_PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-]{1,199}$")
_RECEIPT_RE = re.compile(r"^[a-f0-9]{24}$")
_ALLOWED_DIRECT_EXTENSIONS = {".exe", ".msi"}
_MAX_DIRECT_BYTES = 750 * 1024 * 1024


def _require_windows() -> None:
    import os
    if os.name != "nt":
        raise RuntimeError("Software installation tools are Windows-only.")


def _winget_path() -> str:
    _require_windows()
    path = shutil.which("winget") or shutil.which("winget.exe")
    if not path:
        raise FileNotFoundError("WinGet (winget.exe) is not installed or is not on PATH.")
    return str(Path(path).resolve())


def _run(argv: list[str], *, timeout: float = 90.0) -> dict:
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=max(1.0, min(float(timeout), 600.0)),
        shell=False,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-50000:],
        "stderr": completed.stderr[-20000:],
        "argv": argv[1:],
    }


def manager_status() -> dict:
    path = _winget_path()
    result = _run([path, "--version"], timeout=20)
    return {
        "ready": result["returncode"] == 0,
        "manager": "winget",
        "path": path,
        "version": (result["stdout"] or result["stderr"]).strip()[:200],
    }


def search(query: str, *, source: str = "winget", count: int = 20) -> dict:
    query = " ".join(str(query or "").split())
    if not query:
        raise ValueError("Software search query is required.")
    if len(query) > 300:
        raise ValueError("Software search query is too long.")
    source = str(source or "winget").strip().casefold()
    if source not in {"winget", "msstore"}:
        raise ValueError("Software source must be 'winget' or 'msstore'.")
    count = max(1, min(int(count), 50))
    path = _winget_path()
    result = _run([
        path, "search", "--query", query, "--source", source, "--count", str(count),
        "--accept-source-agreements", "--disable-interactivity",
    ], timeout=60)
    return {"query": query, "source": source, **result}


def show(package_id: str, *, source: str = "winget") -> dict:
    package_id = str(package_id or "").strip()
    if not _PACKAGE_ID_RE.fullmatch(package_id):
        raise ValueError("A valid exact WinGet package ID is required.")
    source = str(source or "winget").strip().casefold()
    if source not in {"winget", "msstore"}:
        raise ValueError("Software source must be 'winget' or 'msstore'.")
    path = _winget_path()
    result = _run([
        path, "show", "--id", package_id, "--exact", "--source", source,
        "--accept-source-agreements", "--disable-interactivity",
    ], timeout=60)
    return {"package_id": package_id, "source": source, **result}


def list_installed(query: str = "", *, package_id: str = "") -> dict:
    query = " ".join(str(query or "").split())
    package_id = str(package_id or "").strip()
    path = _winget_path()
    argv = [path, "list", "--accept-source-agreements", "--disable-interactivity"]
    if package_id:
        if not _PACKAGE_ID_RE.fullmatch(package_id):
            raise ValueError("A valid exact WinGet package ID is required.")
        argv.extend(["--id", package_id, "--exact"])
    elif query:
        argv.extend(["--query", query[:300]])
    result = _run(argv, timeout=60)
    return {"query": query, "package_id": package_id, **result}


def install(package_id: str, *, source: str = "winget", version: str = "", scope: str = "") -> dict:
    package_id = str(package_id or "").strip()
    if not _PACKAGE_ID_RE.fullmatch(package_id):
        raise ValueError("Installation requires an exact WinGet package ID.")
    source = str(source or "winget").strip().casefold()
    if source not in {"winget", "msstore"}:
        raise ValueError("Software source must be 'winget' or 'msstore'.")
    version = str(version or "").strip()
    if version and (len(version) > 80 or not re.fullmatch(r"[A-Za-z0-9._+\-]+", version)):
        raise ValueError("Invalid package version.")
    scope = str(scope or "").strip().casefold()
    if scope and scope not in {"user", "machine"}:
        raise ValueError("scope must be 'user' or 'machine'.")
    path = _winget_path()
    argv = [
        path, "install", "--id", package_id, "--exact", "--source", source,
        "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity",
    ]
    if version:
        argv.extend(["--version", version])
    if scope:
        argv.extend(["--scope", scope])
    result = _run(argv, timeout=600)
    verification = list_installed(package_id=package_id)
    verified = verification.get("returncode") == 0 and package_id.casefold() in str(verification.get("stdout") or "").casefold()
    return {
        "package_id": package_id,
        "source": source,
        "version_requested": version or None,
        "scope": scope or None,
        "verified_installed": bool(verified),
        "verification": verification,
        **result,
    }



def available_upgrades(*, package_id: str = "", source: str = "winget") -> dict:
    package_id = str(package_id or "").strip()
    source = str(source or "winget").strip().casefold()
    if source not in {"winget", "msstore"}:
        raise ValueError("Software source must be 'winget' or 'msstore'.")
    path = _winget_path()
    argv = [path, "upgrade", "--source", source, "--accept-source-agreements", "--disable-interactivity"]
    if package_id:
        if not _PACKAGE_ID_RE.fullmatch(package_id):
            raise ValueError("A valid exact WinGet package ID is required.")
        argv.extend(["--id", package_id, "--exact"])
    result = _run(argv, timeout=90)
    return {"package_id": package_id, "source": source, **result}


def upgrade(package_id: str = "", *, source: str = "winget", all_packages: bool = False) -> dict:
    package_id = str(package_id or "").strip()
    source = str(source or "winget").strip().casefold()
    if source not in {"winget", "msstore"}:
        raise ValueError("Software source must be 'winget' or 'msstore'.")
    if bool(all_packages):
        if package_id:
            raise ValueError("Do not combine an exact package ID with all_packages=true.")
    elif not _PACKAGE_ID_RE.fullmatch(package_id):
        raise ValueError("Update requires an exact WinGet package ID unless all_packages=true is explicitly requested.")
    path = _winget_path()
    argv = [path, "upgrade"]
    if all_packages:
        argv.append("--all")
    else:
        argv.extend(["--id", package_id, "--exact"])
    argv.extend([
        "--source", source, "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity",
    ])
    result = _run(argv, timeout=600)
    verification = available_upgrades(package_id=package_id, source=source) if package_id else available_upgrades(source=source)
    installed = list_installed(package_id=package_id) if package_id else None
    return {
        "package_id": package_id or None,
        "source": source,
        "all_packages": bool(all_packages),
        "verification": verification,
        "installed_state": installed,
        **result,
    }


def uninstall(package_id: str, *, source: str = "winget") -> dict:
    package_id = str(package_id or "").strip()
    if not _PACKAGE_ID_RE.fullmatch(package_id):
        raise ValueError("Uninstall requires an exact WinGet package ID.")
    source = str(source or "winget").strip().casefold()
    if source not in {"winget", "msstore"}:
        raise ValueError("Software source must be 'winget' or 'msstore'.")
    before = list_installed(package_id=package_id)
    before_present = before.get("returncode") == 0 and package_id.casefold() in str(before.get("stdout") or "").casefold()
    if not before_present:
        raise ValueError(f"Package {package_id!r} is not currently installed according to WinGet.")
    path = _winget_path()
    result = _run([
        path, "uninstall", "--id", package_id, "--exact", "--source", source,
        "--accept-source-agreements", "--disable-interactivity",
    ], timeout=600)
    after = list_installed(package_id=package_id)
    still_present = after.get("returncode") == 0 and package_id.casefold() in str(after.get("stdout") or "").casefold()
    return {
        "package_id": package_id,
        "source": source,
        "verified_removed": not still_present,
        "before": before,
        "verification": after,
        **result,
    }

def _validate_public_https(url: str) -> str:
    current = str(url or "").strip()
    parsed = urlparse(current)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("Direct installer URLs must use HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Credentials embedded in installer URLs are not allowed.")
    if len(current) > 4096:
        raise ValueError("Installer URL exceeds the safety limit.")
    for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise PermissionError("Private/local installer destinations are blocked.")
    return current


def _safe_filename(url: str, content_disposition: str = "") -> str:
    name = ""
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", str(content_disposition or ""), re.IGNORECASE)
    if match:
        name = unquote(match.group(1).strip().strip('"'))
    if not name:
        name = unquote(Path(urlparse(url).path).name)
    name = re.sub(r"[^A-Za-z0-9._+\- ]+", "_", name).strip(" .")
    if not name:
        raise ValueError("The installer URL does not provide a usable filename.")
    ext = Path(name).suffix.casefold()
    if ext not in _ALLOWED_DIRECT_EXTENSIONS:
        raise ValueError("Direct web installation supports only signed .exe and .msi installers.")
    return name[:180]


def _authenticode(path: Path) -> dict:
    _require_windows()
    ps = shutil.which("powershell.exe") or shutil.which("powershell")
    if not ps:
        raise FileNotFoundError("Windows PowerShell is required for Authenticode verification.")
    escaped = str(path).replace("'", "''")
    script = (
        f"$s=Get-AuthenticodeSignature -LiteralPath '{escaped}'; "
        "$o=[ordered]@{Status=[string]$s.Status;StatusMessage=[string]$s.StatusMessage;"
        "SignerSubject=if($s.SignerCertificate){[string]$s.SignerCertificate.Subject}else{''};"
        "SignerThumbprint=if($s.SignerCertificate){[string]$s.SignerCertificate.Thumbprint}else{''}};"
        "$o|ConvertTo-Json -Compress"
    )
    result = _run([ps, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script], timeout=45)
    if result["returncode"] != 0:
        raise RuntimeError("Authenticode verification failed: " + (result["stderr"] or result["stdout"])[:1000])
    try:
        data = json.loads(result["stdout"].strip().splitlines()[-1])
    except Exception as exc:
        raise RuntimeError("Could not parse Authenticode verification output.") from exc
    return {
        "status": str(data.get("Status") or ""),
        "status_message": str(data.get("StatusMessage") or ""),
        "signer_subject": str(data.get("SignerSubject") or ""),
        "signer_thumbprint": str(data.get("SignerThumbprint") or ""),
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_root() -> Path:
    root = Path.home() / ".iras" / "installer-cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def prepare_url(url: str) -> dict:
    _require_windows()
    current = _validate_public_https(url)
    cache = _cache_root()
    receipt_id = uuid.uuid4().hex[:24]
    temp_path = cache / f"{receipt_id}.download"
    final_path: Path | None = None
    digest = hashlib.sha256()
    total = 0
    content_type = ""
    headers = {"User-Agent": "IRAS-SoftwareInstaller/5.0"}
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=15.0), follow_redirects=False, headers=headers) as client:
        response = None
        for _ in range(6):
            current = _validate_public_https(current)
            with client.stream("GET", current) as streamed:
                if streamed.status_code in {301, 302, 303, 307, 308}:
                    location = str(streamed.headers.get("location") or "").strip()
                    if not location:
                        raise RuntimeError("Installer redirect did not include a location.")
                    current = urljoin(current, location)
                    continue
                if streamed.status_code >= 400:
                    raise RuntimeError(f"Installer download returned HTTP {streamed.status_code}.")
                filename = _safe_filename(current, streamed.headers.get("content-disposition", ""))
                final_path = cache / f"{receipt_id}-{filename}"
                declared = streamed.headers.get("content-length")
                if declared:
                    try:
                        if int(declared) > _MAX_DIRECT_BYTES:
                            raise ValueError("Installer exceeds the 750 MiB direct-download limit.")
                    except ValueError as exc:
                        if "750 MiB" in str(exc):
                            raise
                content_type = str(streamed.headers.get("content-type") or "")
                with temp_path.open("wb") as fh:
                    for chunk in streamed.iter_bytes(1024 * 1024):
                        total += len(chunk)
                        if total > _MAX_DIRECT_BYTES:
                            raise ValueError("Installer exceeds the 750 MiB direct-download limit.")
                        digest.update(chunk)
                        fh.write(chunk)
                response = streamed
                break
        else:
            raise RuntimeError("Too many installer redirects.")
    if final_path is None or response is None:
        raise RuntimeError("Installer download did not complete.")
    temp_path.replace(final_path)
    try:
        signature = _authenticode(final_path)
        receipt = {
            "receipt_id": receipt_id,
            "url": current,
            "original_url": str(url),
            "path": str(final_path),
            "filename": final_path.name,
            "extension": final_path.suffix.casefold(),
            "bytes": total,
            "content_type": content_type,
            "sha256": digest.hexdigest(),
            "signature": signature,
            "signature_valid": signature.get("status", "").casefold() == "valid",
            "prepared_at": time.time(),
        }
        (cache / f"{receipt_id}.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return receipt
    except Exception:
        try:
            final_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _load_receipt(receipt_id: str) -> tuple[dict, Path, Path]:
    rid = str(receipt_id or "").strip().casefold()
    if not _RECEIPT_RE.fullmatch(rid):
        raise ValueError("Invalid installer receipt ID.")
    cache = _cache_root()
    receipt_path = cache / f"{rid}.json"
    if not receipt_path.is_file():
        raise FileNotFoundError("Installer receipt was not found or has expired from the cache.")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    installer = Path(str(receipt.get("path") or "")).resolve()
    try:
        installer.relative_to(cache.resolve())
    except ValueError as exc:
        raise PermissionError("Installer receipt points outside the IRAS cache.") from exc
    if not installer.is_file():
        raise FileNotFoundError("Prepared installer file is missing.")
    return receipt, installer, receipt_path


def install_prepared(receipt_id: str) -> dict:
    _require_windows()
    receipt, installer, receipt_path = _load_receipt(receipt_id)
    current_hash = _file_sha256(installer)
    if current_hash.casefold() != str(receipt.get("sha256") or "").casefold():
        raise PermissionError("Prepared installer hash changed after verification; installation refused.")
    signature = _authenticode(installer)
    if signature.get("status", "").casefold() != "valid":
        raise PermissionError("Direct installer does not have a currently valid Authenticode signature; installation refused.")
    ext = installer.suffix.casefold()
    if ext == ".msi":
        msiexec = shutil.which("msiexec.exe") or shutil.which("msiexec")
        if not msiexec:
            raise FileNotFoundError("msiexec.exe was not found.")
        result = _run([msiexec, "/i", str(installer), "/passive", "/norestart"], timeout=600)
        launched = False
        pid = None
    elif ext == ".exe":
        process = subprocess.Popen([str(installer)], shell=False)
        result = {"returncode": None, "stdout": "", "stderr": "", "argv": []}
        launched = True
        pid = process.pid
    else:
        raise ValueError("Prepared installer type is no longer supported.")
    receipt["installed_or_launched_at"] = time.time()
    receipt["last_signature"] = signature
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return {
        "receipt_id": receipt_id,
        "installer": str(installer),
        "sha256": current_hash,
        "signature": signature,
        "interactive_launched": launched,
        "pid": pid,
        **result,
    }
