from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = (2026, 9, 20, 0, 0, 0)
SKIP_DIRS = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "build", "dist", ".idea", ".vscode",
}
SKIP_NAMES = {".env", ".DS_Store"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def allowed(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in rel.parts):
        return False
    if path.name in SKIP_NAMES or path.suffix.lower() in SKIP_SUFFIXES:
        return False
    return path.is_file()


def package(output: Path) -> str:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    top = "IRAS-v5.0.0-RC5"
    files = sorted((p for p in ROOT.rglob("*") if allowed(p)), key=lambda p: p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(f"{top}/{rel}", FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if path.suffix.lower() in {".ps1", ".sh"} or path.name in {"gradlew"} else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.create_system = 3
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic IRAS v5.0.0 RC5 source release ZIP")
    parser.add_argument("output", nargs="?", default=str(ROOT.parent / "IRAS-v5.0.0-RC5-COMPLETE-ALL-FEATURES.zip"))
    args = parser.parse_args()
    out = Path(args.output)
    digest = package(out)
    print(f"PACKAGE: {out}")
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    main()
