"""Each person's own memory.

With a known person talking she uses shared things and that person's own, never anyone else's.
A guest gets nothing remembered. With nobody named, only shared things. Nothing in the database
changes shape, and a single-user setup behaves exactly as before.
"""
import sqlite3
import types

import pytest

from iras.core.agent import IRASAgent
from iras.identity import scope
from iras.identity.scope import Scope
from iras.memory.store import MemoryStore
from iras.tools.memory import make_tools
from iras.v5.semantic_memory import SemanticMemory

ALICE, BOB = "per_alice", "per_bob"
A, B, GUEST, NOBODY = Scope("person", ALICE), Scope("person", BOB), Scope("guest"), Scope()


class FakeDB:
    """Same call style as the project's SQLiteDB: execute(sql, params, fetch=None|"one"|"all")."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql, params=(), fetch=None):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        if fetch == "one":
            row = cur.fetchone()
            return dict(row) if row else None
        if fetch == "all":
            return [dict(r) for r in cur.fetchall()]
        return None


@pytest.fixture()
def facts(tmp_path):
    return MemoryStore(tmp_path / "facts.db")


@pytest.fixture()
def memories():
    return SemanticMemory(FakeDB())


@pytest.fixture(autouse=True)
def nobody():
    previous = scope.set_current(NOBODY)
    yield
    scope.set_current(previous)


def keys(rows):
    return sorted(r["key"] for r in rows)


# ---------- the scope itself ----------
def test_a_hint_becomes_a_scope():
    assert scope.from_hint(None) == NOBODY and scope.from_hint({}) == NOBODY
    assert scope.from_hint({"kind": "guest"}) == GUEST
    assert scope.from_hint({"kind": "person", "person_id": ALICE}) == A
    assert scope.from_hint({"kind": "person"}) == NOBODY  # a person with no id is nobody
    assert scope.from_hint({"kind": "wizard", "person_id": ALICE}) == NOBODY


def test_the_scope_is_put_back():
    with scope.use(A):
        assert scope.current() == A
        with scope.use(GUEST):
            assert scope.current() == GUEST
        assert scope.current() == A
    assert scope.current() == NOBODY
    with pytest.raises(RuntimeError):
        with scope.use(B):
            raise RuntimeError("the request failed")
    assert scope.current() == NOBODY


# ---------- facts ----------
@pytest.mark.parametrize("key,expected", [
    ("user.name", ("", "user.name")),
    ("p:per_alice:user.name", ("per_alice", "user.name")),
    ("p:per_alice:a:b", ("per_alice", "a:b")),
    ("p:", ("", "p:")),
    ("p::x", ("", "p::x")),
    ("p:abc", ("", "p:abc")),
    ("iras.personality.adaptive.v1", ("", "iras.personality.adaptive.v1")),
])
def test_keys_are_split_into_owner_and_name(key, expected):
    assert scope.split_key(key) == expected
    owner, bare = expected
    if owner:
        assert scope.own_key(owner, bare) == key


def seed_facts(store):
    store.remember("household.wifi", "blue-door")
    store.remember(scope.own_key(ALICE, "user.name"), "Alice")
    store.remember(scope.own_key(BOB, "user.name"), "Bob")
    store.remember("iras.personality.adaptive.v1", "{}")


def test_each_person_sees_shared_and_their_own_facts(facts):
    seed_facts(facts)
    assert [(r["key"], r["value"]) for r in scope.visible_facts(facts.all_facts(100), A) if r["key"] == "user.name"] == [("user.name", "Alice")]
    assert [(r["key"], r["value"]) for r in scope.visible_facts(facts.all_facts(100), B) if r["key"] == "user.name"] == [("user.name", "Bob")]
    assert "household.wifi" in keys(scope.visible_facts(facts.all_facts(100), A))
    assert all(r.get("private") for r in scope.visible_facts(facts.all_facts(100), A) if r["key"] == "user.name")


def test_nobody_named_sees_only_shared_and_a_guest_sees_none(facts):
    seed_facts(facts)
    assert keys(scope.visible_facts(facts.all_facts(100), NOBODY)) == ["household.wifi", "iras.personality.adaptive.v1"]
    assert scope.visible_facts(facts.all_facts(100), GUEST) == []


def test_a_single_user_setup_is_unchanged(facts):
    facts.remember("user.name", "Hamza")
    facts.remember("user.preferred_title", "sir")
    rows = facts.all_facts(100)
    assert scope.visible_facts(rows, NOBODY) == rows  # same rows, same fields, nothing added


def test_saving_a_fact_follows_the_scope(facts):
    scope.remember_fact(facts, "colour", "blue")  # nobody named: shared, as before
    with scope.use(A):
        assert scope.remember_fact(facts, "colour", "green") == "p:per_alice:colour"
    with scope.use(B):
        scope.remember_fact(facts, "colour", "red")
    assert facts.get_fact("colour") == "blue"
    assert facts.get_fact("p:per_alice:colour") == "green" and facts.get_fact("p:per_bob:colour") == "red"
    with scope.use(A):
        assert sorted(r["value"] for r in scope.search_facts(facts, "colour")) == ["blue", "green"]
    with scope.use(B):
        assert sorted(r["value"] for r in scope.search_facts(facts, "colour")) == ["blue", "red"]


def test_a_guest_saves_and_finds_nothing(facts):
    facts.remember("household.wifi", "blue-door")
    with scope.use(GUEST):
        with pytest.raises(PermissionError, match="guest"):
            scope.remember_fact(facts, "x", "y")
        assert scope.search_facts(facts, "wifi") == []
        assert scope.prompt_facts(facts, 10) == []
    assert facts.get_fact("x") is None


def test_reserved_keys_cannot_reach_another_persons_space(facts):
    for current in (NOBODY, A):
        with scope.use(current):
            with pytest.raises(ValueError, match="reserved"):
                scope.remember_fact(facts, "p:per_bob:user.name", "Mallory")
    assert facts.get_fact("p:per_bob:user.name") is None


def test_other_peoples_facts_do_not_crowd_out_yours(facts):
    for i in range(40):
        facts.remember(scope.own_key(BOB, f"k{i}"), "bob")
    facts.remember(scope.own_key(ALICE, "mine"), "alice")
    facts.remember("shared.thing", "everyone")
    with scope.use(A):
        got = keys(scope.prompt_facts(facts, 5))
    assert "mine" in got and "shared.thing" in got and not any(k.startswith("k") for k in got)


def test_the_prompt_limit_is_respected(facts):
    for i in range(30):
        facts.remember(f"shared.{i}", "x")
    with scope.use(NOBODY):
        assert len(scope.prompt_facts(facts, 7)) == 7
    assert scope.prompt_facts(facts, 0) == []


def test_claiming_and_sharing_facts(facts):
    seed_facts(facts)
    facts.remember("user.preferred_title", "sir")
    assert scope.claim_facts(facts, ALICE) == 2  # household.wifi and user.preferred_title. Not her own settings.
    assert facts.get_fact("iras.personality.adaptive.v1") == "{}"
    assert facts.get_fact("household.wifi") is None and facts.get_fact("p:per_alice:household.wifi") == "blue-door"
    assert facts.get_fact("p:per_bob:user.name") == "Bob"  # someone else's is not touched
    assert scope.claim_facts(facts, ALICE) == 0  # nothing left to claim
    assert scope.share_facts(facts, ALICE) == 3  # user.name, household.wifi, user.preferred_title
    assert facts.get_fact("user.name") == "Alice" and facts.get_fact("p:per_alice:user.name") is None
    assert facts.get_fact("p:per_bob:user.name") == "Bob"


# ---------- the model's fact tools ----------
def tool(store, name):
    return {t.name: t for t in make_tools(store)}[name].handler


def test_the_fact_tools_follow_the_scope(facts):
    remember, search = tool(facts, "remember_fact"), tool(facts, "search_memory")
    remember(key="food", value="pizza")  # nobody named
    with scope.use(A):
        assert remember(key="food", value="pasta") == {"remembered": "food"}
        assert sorted(r["value"] for r in search(query="food")) == ["pasta", "pizza"]
    with scope.use(B):
        assert [r["value"] for r in search(query="food")] == ["pizza"]  # Alice's pasta stays hers
    with scope.use(GUEST):
        assert search(query="food") == []
        with pytest.raises(PermissionError):
            remember(key="food", value="x")


# ---------- semantic memory (the Memory screen) ----------
def seed_memories(m):
    m.remember("the wifi is blue-door", namespace="default")
    m.remember("alice likes jazz", namespace=scope.own_namespace(ALICE))
    m.remember("bob likes rock", namespace=scope.own_namespace(BOB))
    m.remember("the project is called iras", namespace="project:iras")


def texts(rows):
    return sorted(r["text"] for r in rows)


def test_searching_memories_follows_the_scope(memories):
    seed_memories(memories)
    with scope.use(A):
        assert texts(scope.search_memories(memories, "likes")) == ["alice likes jazz"]
        assert texts(scope.search_memories(memories, "the")) == ["the project is called iras", "the wifi is blue-door"]
        assert scope.search_memories(memories, "likes", namespace=scope.own_namespace(BOB)) == []  # asked for directly: still no
        assert texts(scope.search_memories(memories, "likes", namespace=scope.own_namespace(ALICE))) == ["alice likes jazz"]
    with scope.use(B):
        assert texts(scope.search_memories(memories, "likes")) == ["bob likes rock"]
    with scope.use(NOBODY):
        assert scope.search_memories(memories, "likes") == []  # nobody named: nobody's private memories
        assert texts(scope.search_memories(memories, "wifi")) == ["the wifi is blue-door"]
    with scope.use(GUEST):
        assert scope.search_memories(memories, "wifi") == []


def test_saving_a_memory_follows_the_scope(memories):
    with scope.use(NOBODY):
        scope.remember_memory(memories, "shared by default")
    with scope.use(A):
        scope.remember_memory(memories, "alice default")  # a person's memory is theirs
        scope.remember_memory(memories, "everyone may know", namespace="shared")
        scope.remember_memory(memories, "about the project", namespace="project:iras")
        with pytest.raises(PermissionError, match="someone else"):
            scope.remember_memory(memories, "sneaky", namespace=scope.own_namespace(BOB))
    with scope.use(GUEST):
        with pytest.raises(PermissionError, match="guest"):
            scope.remember_memory(memories, "hi")
    rows = memories.db.execute("SELECT text, namespace FROM v5_semantic_memory", fetch="all")
    spaces = {r["text"]: r["namespace"] for r in rows}
    assert spaces == {"shared by default": "default", "alice default": "person:per_alice", "everyone may know": "shared", "about the project": "project:iras"}


def test_forgetting_only_what_you_may_see(memories):
    mine = memories.remember("mine", namespace=scope.own_namespace(ALICE))
    his = memories.remember("his", namespace=scope.own_namespace(BOB))
    shared = memories.remember("ours", namespace="default")
    with scope.use(A):
        with pytest.raises(PermissionError):
            scope.forget_memory(memories, his)
        with pytest.raises(PermissionError):
            scope.forget_memory(memories, "mem_does_not_exist")
        assert scope.forget_memory(memories, mine) == {"forgotten": mine}
        assert scope.forget_memory(memories, shared) == {"forgotten": shared}
    with scope.use(GUEST):
        with pytest.raises(PermissionError):
            scope.forget_memory(memories, his)
    left = [r["text"] for r in memories.db.execute("SELECT text FROM v5_semantic_memory", fetch="all")]
    assert left == ["his"]


def test_claiming_and_sharing_memories(memories):
    seed_memories(memories)
    assert scope.claim_memories(memories, ALICE) == 1  # only the "default" one
    rows = {r["text"]: r["namespace"] for r in memories.db.execute("SELECT text, namespace FROM v5_semantic_memory", fetch="all")}
    assert rows["the wifi is blue-door"] == "person:per_alice" and rows["bob likes rock"] == "person:per_bob" and rows["the project is called iras"] == "project:iras"
    assert scope.share_memories(memories, ALICE) == 2
    rows = {r["text"]: r["namespace"] for r in memories.db.execute("SELECT text, namespace FROM v5_semantic_memory", fetch="all")}
    assert rows["the wifi is blue-door"] == "default" and rows["alice likes jazz"] == "default" and rows["bob likes rock"] == "person:per_bob"


def test_listing_the_newest_memories_needs_no_words(memories):
    seed_memories(memories)
    assert len(memories.recent()) == 4 and memories.search("") == []  # search needs words, listing does not
    assert [r["text"] for r in memories.recent(namespace="default")] == ["the wifi is blue-door"]
    assert len(memories.recent(limit=2)) == 2
    assert all("metadata" in r and "metadata_json" not in r for r in memories.recent())


def test_the_model_memory_tools_are_scoped():
    from iras.tools import v5 as v5tools
    import inspect

    source = inspect.getsource(v5tools)
    assert "people_scope.search_memories(v5.semantic_memory" in source
    assert "people_scope.remember_memory(v5.semantic_memory" in source
    assert "people_scope.forget_memory(v5.semantic_memory" in source
    assert "v5.semantic_memory.forget(memory_id)" not in source  # no way around the check


# ---------- her prompt ----------
class Reply:
    text = "ok"
    tool_calls = []
    assistant_message = {"role": "assistant", "content": "ok"}


class Provider:
    model = last_model = "fake/model"

    def __init__(self):
        self.seen = []

    def complete(self, messages, tools):
        self.seen.append(messages)
        return Reply()


class Quiet:
    def record(self, *a, **k):
        pass

    def schemas(self, names=None):
        return []

    def execute(self, name, args):
        raise AssertionError("no tool was expected")


def agent_with(facts):
    provider = Provider()
    return IRASAgent(provider, Quiet(), facts, Quiet(), smart_tools=True, context_fact_limit=10, context_message_limit=8), provider


def prompt_text(messages):
    return "\n".join(m["content"] for m in messages if m["role"] == "system")


def test_her_prompt_shows_only_what_this_person_may_see(facts):
    seed_facts(facts)
    agent, _ = agent_with(facts)
    with scope.use(A):
        text = prompt_text(agent._base_messages("hello"))
        assert "Alice" in text and "household.wifi" in text and "Bob" not in text
    with scope.use(B):
        text = prompt_text(agent._base_messages("hello"))
        assert "Bob" in text and "household.wifi" in text and "Alice" not in text
    with scope.use(NOBODY):
        text = prompt_text(agent._base_messages("hello"))
        assert "household.wifi" in text and "Alice" not in text and "Bob" not in text
    with scope.use(GUEST):
        assert "household.wifi" not in prompt_text(agent._base_messages("hello"))


def test_her_personality_setting_never_reaches_the_prompt(facts):
    seed_facts(facts)
    agent, _ = agent_with(facts)
    assert "iras.personality" not in prompt_text(agent._base_messages("hello"))


def test_the_name_she_is_asked_to_use_belongs_to_whoever_asked(facts):
    agent, _ = agent_with(facts)
    with scope.use(A):
        agent.handle("please call me boss")
    with scope.use(B):
        agent.handle("call me sir")
    with scope.use(GUEST):
        agent.handle("call me master")  # a guest's title is not saved, and chat still works
    assert facts.get_fact("p:per_alice:user.preferred_title") == "boss"
    assert facts.get_fact("p:per_bob:user.preferred_title") == "sir"
    assert facts.get_fact("user.preferred_title") is None

    def remembered(messages):  # only the block of remembered facts: her general guidance also says "boss" and "sir"
        return "\n".join(m["content"] for m in messages if m["role"] == "system" and m["content"].startswith("Relevant durable local memory"))

    with scope.use(A):
        block = remembered(agent._base_messages("hi"))
        assert '"boss"' in block and '"sir"' not in block and "user.preferred_title" in block
    with scope.use(B):
        block = remembered(agent._base_messages("hi"))
        assert '"sir"' in block and '"boss"' not in block


# ---------- the server ----------
@pytest.fixture()
def cloud(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    try:
        from iras import cloud_api
    except ImportError as exc:
        pytest.skip(f"the cloud server cannot load in this environment ({exc})")
    return cloud_api


def test_a_chat_request_sets_the_scope_for_its_own_time_only(cloud, monkeypatch):
    fake_agent = types.SimpleNamespace(context_messages_override=None, speaker_context=None, context_message_limit=12)
    monkeypatch.setattr(cloud, "runtime", types.SimpleNamespace(agent=fake_agent))
    monkeypatch.setattr(cloud, "cloud_state", types.SimpleNamespace(messages=lambda *a, **k: []))
    hint = {"kind": "person", "person_id": ALICE, "hide_memory": False, "message": "x"}
    with cloud._cloud_thread_scope("t1", hint):
        assert scope.current() == A
    assert scope.current() == NOBODY
    with cloud._cloud_thread_scope("t1", {"kind": "guest", "hide_memory": True, "message": "x"}):
        assert scope.current() == GUEST
    with pytest.raises(RuntimeError):
        with cloud._cloud_thread_scope("t1", hint):
            raise RuntimeError("the request failed")
    assert scope.current() == NOBODY
    with cloud._cloud_thread_scope("t1"):
        assert scope.current() == NOBODY


def test_the_identity_routes_move_memories(tmp_path):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from iras.identity import routes

    calls = []

    class Ops:
        def claim(self, person_id):
            calls.append(("claim", person_id))
            return {"person_id": person_id, "facts": 2, "memories": 3}

        def share(self, person_id):
            calls.append(("share", person_id))
            return {"person_id": person_id, "facts": 1, "memories": 0}

    def authorize(header):
        if header != "Bearer ok":
            raise HTTPException(status_code=401, detail="no")

    db = FakeDB()
    app = FastAPI()
    routes.register_identity_routes(app, authorize, lambda: db, memory_ops=Ops())
    client = TestClient(app)
    client.headers.update({"Authorization": "Bearer ok"})
    pid = client.post("/v1/identity/people", json={"name": "Alice"}).json()["person"]["person_id"]
    assert client.post(f"/v1/identity/people/{pid}/claim-memory").json() == {"person_id": pid, "facts": 2, "memories": 3}
    assert client.post(f"/v1/identity/people/{pid}/share-memory").json()["facts"] == 1
    assert calls == [("claim", pid), ("share", pid)]
    assert client.post("/v1/identity/people/per_nobody/claim-memory").status_code == 404
    assert client.post(f"/v1/identity/people/{pid}/claim-memory", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert calls == [("claim", pid), ("share", pid)]  # nothing moved for the refused or unknown ones

    bare = FastAPI()
    routes.register_identity_routes(bare, authorize, lambda: db)  # a server without the memory part
    c2 = TestClient(bare)
    c2.headers.update({"Authorization": "Bearer ok"})
    assert c2.post(f"/v1/identity/people/{pid}/claim-memory").status_code == 503


def test_the_memory_list_address_lists_when_there_are_no_words():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "src" / "iras" / "cloud_api.py").read_text(encoding="utf-8")
    assert "semantic_memory.recent(namespace=namespace or None, limit=limit)" in text


def test_both_stores_can_forget_one_fact():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src" / "iras" / "memory"
    assert "def forget_fact" in (root / "store.py").read_text(encoding="utf-8")
    assert "def forget_fact" in (root / "postgres_store.py").read_text(encoding="utf-8")
