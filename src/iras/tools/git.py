from __future__ import annotations

import re
import subprocess
from iras.models import PermissionLevel
from iras.tools.base import Tool

_READ_ONLY = {'status', 'log', 'diff', 'show', 'rev-parse', 'ls-files', 'ls-tree', 'describe', 'grep'}
_SYSTEM = {'add', 'commit', 'merge', 'checkout', 'switch', 'restore', 'pull', 'fetch', 'tag', 'mv', 'rm', 'stash'}
_BLOCKED = {'config', 'daemon', 'shell', 'credential', 'credential-store', 'credential-cache', 'filter-branch'}


def _clean_args(arguments):
    args = [str(item) for item in (arguments or [])]
    if not args or len(args) > 64:
        raise ValueError('git_command requires 1..64 arguments.')
    for arg in args:
        if any(ch in arg for ch in ('\x00', '\r', '\n')):
            raise ValueError('Invalid control character in Git argument.')
        lowered = arg.lower()
        if lowered in {'-c', '--config-env'} or lowered.startswith(('-c=', '--config-env=', '--exec-path')):
            raise PermissionError('Per-command Git configuration/exec-path overrides are blocked.')
        if arg.startswith('!'):
            raise PermissionError('Git shell aliases are blocked.')
    return args


def _subcommand(args):
    for arg in args:
        if not arg.startswith('-'):
            return arg.lower()
    return ''


def _git(repo, args):
    clean = _clean_args(args)
    cp = subprocess.run(['git', '--no-pager', *clean], cwd=repo, capture_output=True, text=True, timeout=120, errors='replace', shell=False)
    return {'returncode': cp.returncode, 'stdout': cp.stdout[-30000:], 'stderr': cp.stderr[-30000:]}


def git_status(repo='.'):
    return _git(repo, ['status', '--short', '--branch'])


def git_log(repo='.', limit=10):
    return _git(repo, ['log', '--oneline', '--decorate', f'-{min(max(int(limit), 1), 100)}'])


def git_diff(repo='.', staged=False):
    return _git(repo, ['diff', *(['--cached'] if staged else [])])


def git_command(repo, arguments):
    args = _clean_args(arguments)
    command = _subcommand(args)
    if command in _BLOCKED:
        raise PermissionError(f'git {command} is blocked in the generic Git tool.')
    if command not in _READ_ONLY | _SYSTEM | {'push', 'branch', 'reset', 'clean'}:
        raise PermissionError(f'git subcommand {command!r} is not in the IRAS allowlist.')
    return _git(repo, args)


def classify(a):
    args = _clean_args(a.get('arguments', []))
    command = _subcommand(args)
    joined = ' '.join(args).lower()
    if command in _BLOCKED:
        return PermissionLevel.CRITICAL
    if command in _READ_ONLY:
        return PermissionLevel.READ
    if command == 'push' and '--force' in joined or '--force-with-lease' in joined:
        return PermissionLevel.CRITICAL
    if command in {'reset', 'clean'}:
        return PermissionLevel.CRITICAL
    if command == 'branch' and re.search(r'(^|\s)-(d|D)\b', joined):
        return PermissionLevel.CRITICAL
    if command in _SYSTEM | {'push', 'branch'}:
        return PermissionLevel.SYSTEM_ACTION
    return PermissionLevel.CRITICAL


TOOLS = [
    Tool('git_status', 'Show repository status.', {'type': 'object', 'properties': {'repo': {'type': 'string'}}, 'required': ['repo']}, git_status, PermissionLevel.READ),
    Tool('git_log', 'Show recent Git commits.', {'type': 'object', 'properties': {'repo': {'type': 'string'}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}}, 'required': ['repo']}, git_log, PermissionLevel.READ),
    Tool('git_diff', 'Show Git changes.', {'type': 'object', 'properties': {'repo': {'type': 'string'}, 'staged': {'type': 'boolean'}}, 'required': ['repo']}, git_diff, PermissionLevel.READ),
    Tool('git_command', 'Run an allowlisted Git subcommand. Per-command config, credential helpers, shell aliases, and other command-execution escape hatches are blocked; mutating/publishing commands are elevated dynamically.', {'type': 'object', 'properties': {'repo': {'type': 'string'}, 'arguments': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'maxItems': 64}}, 'required': ['repo', 'arguments']}, git_command, PermissionLevel.READ, classify),
]
