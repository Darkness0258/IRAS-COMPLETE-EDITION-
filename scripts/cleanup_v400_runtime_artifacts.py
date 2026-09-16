from __future__ import annotations

"""Remove validation/runtime cache artifacts without touching user state.

v4 validation intentionally runs compileall and pytest, both of which can leave
local caches in an existing development checkout. Those files are not release
content and should not make the next validation run fail. Virtual environments,
.git, node_modules, and all user state are left untouched.
"""

from pathlib import Path
import os
import shutil

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "env", "node_modules"}
CACHE_DIRS = {"__pycache__", ".pytest_cache"}
CACHE_SUFFIXES = {".pyc", ".pyo"}


def main() -> None:
    removed_dirs = 0
    removed_files = 0

    for current, dirnames, filenames in os.walk(ROOT, topdown=True):
        current_path = Path(current)

        # Prune large/private trees before os.walk descends into them.
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]

        for name in list(dirnames):
            if name not in CACHE_DIRS:
                continue
            target = current_path / name
            shutil.rmtree(target, ignore_errors=True)
            removed_dirs += 1
            dirnames.remove(name)

        for name in filenames:
            path = current_path / name
            if path.suffix.lower() not in CACHE_SUFFIXES:
                continue
            try:
                path.unlink()
                removed_files += 1
            except FileNotFoundError:
                pass

    print(
        "IRAS validation cache cleanup:",
        f"directories={removed_dirs}",
        f"files={removed_files}",
    )


if __name__ == "__main__":
    main()
