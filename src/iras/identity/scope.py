"""Whose things she may use right now: each person's own memory.

The cloud server sets the scope for one chat request, from the same "who is talking" hint
(see iras.identity.context). It runs one request at a time, so a plain module value is safe.
Everything else (the Memory screen, scheduled jobs) does not read it.

  nobody named   only shared things. Before anyone is taught, everything is shared, so a
                 single-user setup works exactly as before.
  a person       shared things, plus that person's own. Never anyone else's.
  a guest        nothing remembered: not read, not saved.

Two memories, two ways of saying "mine":
  facts (key and value, in her prompt)   the key is stored as  p:<person_id>:<key>
  semantic memory (the Memory screen)    the namespace is      person:<person_id>
Nothing in the database changes shape. Old things stay shared until you claim them for a person.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

FACT_PREFIX = "p:"
NAMESPACE_PREFIX = "person:"
SYSTEM_FACT_PREFIX = "iras."  # her own settings (for example the personality). Never claimed, never hidden.
SHARED_NAMESPACE = "shared"  # for things the whole household may know
SEARCH_SPREAD = 5  # ask for more rows than needed, because some are dropped for being someone else's


@dataclass(frozen=True)
class Scope:
    kind: str = ""  # "" nobody named, "person" or "guest"
    person_id: str = ""


NOBODY = Scope()
_current: Scope = NOBODY


def current() -> Scope:
    return _current


def from_hint(hint: dict | None) -> Scope:
    """The scope for a "who is talking" hint (as built by iras.identity.context.hint)."""
    if not hint:
        return NOBODY
    if hint.get("kind") == "guest":
        return Scope("guest")
    if hint.get("kind") == "person" and hint.get("person_id"):
        return Scope("person", str(hint["person_id"]))
    return NOBODY


def set_current(scope: Scope) -> Scope:
    """Set the scope and return the one it replaced, so it can be put back."""
    global _current
    previous, _current = _current, scope
    return previous


@contextmanager
def use(scope: Scope):
    previous = set_current(scope)
    try:
        yield scope
    finally:
        set_current(previous)


# ---------- facts ----------
def own_key(person_id: str, key: str) -> str:
    return f"{FACT_PREFIX}{person_id}:{key}"


def split_key(key: str) -> tuple[str, str]:
    """A stored key -> (owner, plain key). Owner is "" for a shared fact."""
    if key.startswith(FACT_PREFIX):
        owner, sep, bare = key[len(FACT_PREFIX):].partition(":")
        if sep and owner:
            return owner, bare
    return "", key


def visible_facts(rows: list[dict], scope: Scope | None = None) -> list[dict]:
    """The facts this scope may see, with plain keys. A person's own facts are marked private."""
    scope = scope or current()
    if scope.kind == "guest":
        return []
    out = []
    for row in rows:
        owner, bare = split_key(str(row.get("key", "")))
        if owner and not (scope.kind == "person" and owner == scope.person_id):
            continue  # someone else's, or nobody is named
        out.append({**row, "key": bare, "private": True} if owner else row)
    return out


def remember_fact(store, key: str, value: str) -> str:
    """Save a fact for the current scope. Returns the key as it was stored."""
    scope = current()
    if scope.kind == "guest":
        raise PermissionError("A guest cannot save memories.")
    if key.startswith(FACT_PREFIX):
        raise ValueError(f'Keys starting with "{FACT_PREFIX}" are reserved.')
    stored = own_key(scope.person_id, key) if scope.kind == "person" else key
    store.remember(stored, value)
    return stored


def search_facts(store, query: str, limit: int = 10) -> list[dict]:
    """Facts this scope may see that match the query. Facts that belong to a person say so."""
    limit = max(1, min(int(limit), 100))
    rows = visible_facts(store.search_facts(query, min(limit * SEARCH_SPREAD, 500)))
    return rows[:limit]


def prompt_facts(store, limit: int) -> list[dict]:
    """The newest facts this scope may see, for her prompt."""
    if not limit:
        return []
    rows = store.all_facts(min(limit * SEARCH_SPREAD, 500))
    return visible_facts(rows)[:limit]


# ---------- semantic memory (the Memory screen) ----------
def own_namespace(person_id: str) -> str:
    return f"{NAMESPACE_PREFIX}{person_id}"


def namespace_owner(namespace: str) -> str:
    return namespace[len(NAMESPACE_PREFIX):] if str(namespace or "").startswith(NAMESPACE_PREFIX) else ""


def readable_namespace(namespace: str, scope: Scope | None = None) -> bool:
    scope = scope or current()
    if scope.kind == "guest":
        return False
    owner = namespace_owner(namespace)
    return not owner or (scope.kind == "person" and owner == scope.person_id)


def search_memories(memory, query: str, namespace: str = "", limit: int = 10) -> list[dict]:
    limit = max(1, min(int(limit), 50))
    scope = current()
    if scope.kind == "guest":
        return []
    if namespace:
        return memory.search(query, namespace=namespace, limit=limit) if readable_namespace(namespace, scope) else []
    rows = memory.search(query, namespace=None, limit=min(limit * SEARCH_SPREAD, 100))
    return [r for r in rows if readable_namespace(str(r.get("namespace", "")), scope)][:limit]


def remember_memory(memory, text: str, namespace: str = "default", kind: str = "note", source: str = "agent") -> str:
    """Save a memory for the current scope. With a person talking, a memory is theirs unless it is
    said to be for the household (namespace "shared")."""
    scope = current()
    namespace = namespace or "default"
    if scope.kind == "guest":
        raise PermissionError("A guest cannot save memories.")
    if namespace_owner(namespace) and not (scope.kind == "person" and namespace_owner(namespace) == scope.person_id):
        raise PermissionError("That memory belongs to someone else.")
    if scope.kind == "person" and namespace == "default":
        namespace = own_namespace(scope.person_id)
    return memory.remember(text, namespace=namespace, kind=kind, source=source)


def forget_memory(memory, memory_id: str) -> dict:
    """Delete one memory, but only one this scope may see."""
    scope = current()
    row = memory.db.execute("SELECT namespace FROM v5_semantic_memory WHERE memory_id=?", (memory_id,), fetch="one")
    if row is None or not readable_namespace(str(dict(row).get("namespace", "")), scope):
        raise PermissionError("I cannot find that memory in what you may use.")
    memory.forget(memory_id)
    return {"forgotten": memory_id}


# ---------- giving old things to a person, and taking them back ----------
def claim_facts(store, person_id: str) -> int:
    """Make the shared facts (not her own settings) belong to a person. Returns how many."""
    moved = 0
    for row in store.all_facts(500):
        key = str(row.get("key", ""))
        if split_key(key)[0] or key.startswith(SYSTEM_FACT_PREFIX):
            continue
        store.remember(own_key(person_id, key), row.get("value", ""))
        store.forget_fact(key)
        moved += 1
    return moved


def share_facts(store, person_id: str) -> int:
    """Make a person's facts shared again. Returns how many."""
    moved = 0
    for row in store.all_facts(500):
        owner, bare = split_key(str(row.get("key", "")))
        if owner != person_id:
            continue
        store.remember(bare, row.get("value", ""))
        store.forget_fact(str(row["key"]))
        moved += 1
    return moved


def claim_memories(memory, person_id: str) -> int:
    """Make the shared memories ("default") belong to a person. Returns how many."""
    n = memory.db.execute("SELECT COUNT(*) AS n FROM v5_semantic_memory WHERE namespace=?", ("default",), fetch="one")
    memory.db.execute("UPDATE v5_semantic_memory SET namespace=? WHERE namespace=?", (own_namespace(person_id), "default"))
    return int(dict(n).get("n", 0)) if n else 0


def share_memories(memory, person_id: str) -> int:
    n = memory.db.execute("SELECT COUNT(*) AS n FROM v5_semantic_memory WHERE namespace=?", (own_namespace(person_id),), fetch="one")
    memory.db.execute("UPDATE v5_semantic_memory SET namespace=? WHERE namespace=?", ("default", own_namespace(person_id)))
    return int(dict(n).get("n", 0)) if n else 0


def claim(store, memory, person_id: str) -> dict[str, Any]:
    return {"person_id": person_id, "facts": claim_facts(store, person_id), "memories": claim_memories(memory, person_id)}


def share(store, memory, person_id: str) -> dict[str, Any]:
    return {"person_id": person_id, "facts": share_facts(store, person_id), "memories": share_memories(memory, person_id)}
