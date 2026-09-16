from __future__ import annotations

import fnmatch
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile

from iras.models import PermissionLevel
from iras.remote_access import is_sensitive_path
from iras.tools.base import Tool


def P(p):
    return Path(p).expanduser().resolve()


def _read_permission(args):
    return PermissionLevel.CRITICAL if is_sensitive_path(args.get("path")) else PermissionLevel.READ


def _write_permission(args):
    paths = [args.get("path"), args.get("source"), args.get("destination")]
    return PermissionLevel.CRITICAL if any(is_sensitive_path(value) for value in paths if value) else PermissionLevel.SYSTEM_ACTION


def list_directory(path='.', include_hidden=False):
    p = P(path)
    if not p.is_dir():
        raise NotADirectoryError(p)
    out = []
    for x in sorted(p.iterdir(), key=lambda z: z.name.lower()):
        if not include_hidden and x.name.startswith('.'):
            continue
        is_link = x.is_symlink()
        size = None
        if not is_link and x.is_file():
            try:
                size = x.stat().st_size
            except OSError:
                pass
        out.append({'name': x.name, 'type': 'symlink' if is_link else ('dir' if x.is_dir() else 'file'), 'size': size})
        if len(out) >= 1000:
            break
    return out


def read_text(path, max_chars=30000):
    p = P(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    max_chars = max(1, min(int(max_chars), 100000))
    return p.read_text(encoding='utf-8', errors='replace')[:max_chars]


def read_text_range(path, start_line=1, end_line=200):
    p = P(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    if p.stat().st_size > 5_000_000:
        raise ValueError('read_text_range refuses files larger than 5 MB.')
    start_line = max(1, int(start_line))
    end_line = max(start_line, min(int(end_line), start_line + 999))
    lines = p.read_text(encoding='utf-8', errors='replace').splitlines()
    return {
        'path': str(p),
        'start_line': start_line,
        'end_line': min(end_line, len(lines)),
        'total_lines': len(lines),
        'content': '\n'.join(lines[start_line - 1:end_line]),
    }


def search_text(root, query, pattern='*', regex=False, case_sensitive=False, max_matches=120, max_files=600):
    directory = P(root)
    if not directory.is_dir():
        raise NotADirectoryError(directory)
    query = str(query or '')
    if not query or len(query) > 1000:
        raise ValueError('query is required and must be <= 1000 characters.')
    pattern = str(pattern or '*')[:200]
    max_matches = max(1, min(int(max_matches), 500))
    max_files = max(1, min(int(max_files), 3000))
    compiled = re.compile(query, 0 if case_sensitive else re.IGNORECASE) if regex else None
    needle = query if case_sensitive else query.lower()
    matches = []
    scanned = 0
    for candidate in directory.rglob('*'):
        if scanned >= max_files or len(matches) >= max_matches:
            break
        try:
            if candidate.is_symlink() or is_sensitive_path(candidate):
                continue
            if not candidate.is_file() or not fnmatch.fnmatch(candidate.name, pattern):
                continue
            if candidate.stat().st_size > 2_000_000:
                continue
        except OSError:
            continue
        scanned += 1
        try:
            text = candidate.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            found = bool(compiled.search(line)) if compiled else needle in (line if case_sensitive else line.lower())
            if found:
                matches.append({'path': str(candidate), 'relative_path': str(candidate.relative_to(directory)), 'line': line_no, 'text': line[:1200]})
                if len(matches) >= max_matches:
                    break
    return {'root': str(directory), 'matches': matches, 'match_count': len(matches), 'files_scanned': scanned, 'truncated': scanned >= max_files or len(matches) >= max_matches}


def file_info(path, sha256=True):
    p = P(path)
    if not p.exists():
        raise FileNotFoundError(p)
    st = p.stat()
    out = {'path': str(p), 'type': 'dir' if p.is_dir() else 'file', 'size': st.st_size if p.is_file() else None, 'modified': st.st_mtime, 'is_symlink': p.is_symlink()}
    if sha256 and p.is_file():
        if st.st_size > 100_000_000:
            raise ValueError('Hashing is limited to files <= 100 MB.')
        h = hashlib.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        out['sha256'] = h.hexdigest()
    return out


def _atomic_write(p: Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=p.name + '.', suffix='.iras-tmp', dir=str(p.parent))
    temp_path = Path(temp)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, p)
    finally:
        temp_path.unlink(missing_ok=True)


def write_text(path, content, append=False):
    p = P(path)
    text = str(content)
    if len(text.encode('utf-8')) > 2_000_000:
        raise ValueError('write_text payload is limited to 2 MB.')
    if append:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('a', encoding='utf-8') as f:
            f.write(text)
    else:
        _atomic_write(p, text)
    return {'path': str(p), 'bytes': p.stat().st_size, 'atomic': not bool(append)}


def make_directory(path):
    p = P(path)
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def copy_path(source, destination):
    s, d = P(source), P(destination)
    if s.is_dir():
        for child in s.rglob('*'):
            if child.is_symlink():
                raise PermissionError('copy_path refuses directory trees containing symlinks.')
        shutil.copytree(s, d, dirs_exist_ok=True, symlinks=False)
    else:
        if s.is_symlink():
            raise PermissionError('copy_path refuses symbolic links.')
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    return str(d)


def move_path(source, destination):
    d = P(destination)
    d.parent.mkdir(parents=True, exist_ok=True)
    return str(shutil.move(str(P(source)), str(d)))


def delete_path(path):
    p = P(path)
    if p.is_dir():
        shutil.rmtree(p)
    elif p.exists():
        p.unlink()
    else:
        raise FileNotFoundError(p)
    return {'deleted': str(p)}


TOOLS = [
    Tool('list_directory', 'List a local directory.', {'type': 'object', 'properties': {'path': {'type': 'string'}, 'include_hidden': {'type': 'boolean'}}, 'required': ['path']}, list_directory, PermissionLevel.READ),
    Tool('read_text', 'Read a local text file. Sensitive credential/key paths require CRITICAL approval.', {'type': 'object', 'properties': {'path': {'type': 'string'}, 'max_chars': {'type': 'integer', 'minimum': 1, 'maximum': 100000}}, 'required': ['path']}, read_text, PermissionLevel.READ, _read_permission),
    Tool('read_text_range', 'Read a bounded line range from a local text/code file.', {'type': 'object', 'properties': {'path': {'type': 'string'}, 'start_line': {'type': 'integer', 'minimum': 1}, 'end_line': {'type': 'integer', 'minimum': 1}}, 'required': ['path']}, read_text_range, PermissionLevel.READ, _read_permission),
    Tool('search_text', 'Recursively search bounded local text/code files. Sensitive credential paths are skipped.', {'type': 'object', 'properties': {'root': {'type': 'string'}, 'query': {'type': 'string', 'maxLength': 1000}, 'pattern': {'type': 'string', 'maxLength': 200}, 'regex': {'type': 'boolean'}, 'case_sensitive': {'type': 'boolean'}, 'max_matches': {'type': 'integer', 'minimum': 1, 'maximum': 500}, 'max_files': {'type': 'integer', 'minimum': 1, 'maximum': 3000}}, 'required': ['root', 'query']}, search_text, PermissionLevel.READ),
    Tool('file_info', 'Inspect local file metadata and optionally compute SHA-256.', {'type': 'object', 'properties': {'path': {'type': 'string'}, 'sha256': {'type': 'boolean'}}, 'required': ['path']}, file_info, PermissionLevel.READ, _read_permission),
    Tool('write_text', 'Create or overwrite/append a text file. Non-append writes are atomic.', {'type': 'object', 'properties': {'path': {'type': 'string'}, 'content': {'type': 'string', 'maxLength': 2000000}, 'append': {'type': 'boolean'}}, 'required': ['path', 'content']}, write_text, PermissionLevel.SYSTEM_ACTION, _write_permission),
    Tool('make_directory', 'Create a directory.', {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']}, make_directory, PermissionLevel.SAFE_ACTION),
    Tool('copy_path', 'Copy a file or directory without following directory-tree symlinks.', {'type': 'object', 'properties': {'source': {'type': 'string'}, 'destination': {'type': 'string'}}, 'required': ['source', 'destination']}, copy_path, PermissionLevel.SYSTEM_ACTION, _write_permission),
    Tool('move_path', 'Move or rename a file or directory.', {'type': 'object', 'properties': {'source': {'type': 'string'}, 'destination': {'type': 'string'}}, 'required': ['source', 'destination']}, move_path, PermissionLevel.SYSTEM_ACTION, _write_permission),
    Tool('delete_path', 'Permanently delete a file or directory. Destructive.', {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']}, delete_path, PermissionLevel.CRITICAL),
]
