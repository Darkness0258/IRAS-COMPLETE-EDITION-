from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import math
import os
import re
import threading
import time
from typing import Any, Callable

from .common import EventBus, SQLiteDB, new_id, utc_now


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{2,}")
_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "into", "have", "has",
    "are", "was", "were", "you", "your", "its", "not", "but", "can", "will", "would",
    "should", "could", "about", "when", "where", "what", "which", "while", "then", "than",
    "there", "their", "them", "they", "our", "out", "all", "any", "some", "more", "most",
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _tokens(text: str, *, limit: int = 48) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in _TOKEN_RE.findall(str(text or "").lower()):
        if raw in _STOPWORDS or raw in seen:
            continue
        seen.add(raw)
        out.append(raw[:80])
        if len(out) >= max(1, int(limit)):
            break
    return out


class FuzzyLogicEngine:
    """Small deterministic fuzzy-logic engine used by the cognitive layer."""

    @staticmethod
    def truth(value: float) -> float:
        return _clamp(value)

    @staticmethod
    def fuzzy_and(*values: float) -> float:
        values = tuple(values)
        return min((_clamp(v) for v in values), default=0.0)

    @staticmethod
    def fuzzy_or(*values: float) -> float:
        values = tuple(values)
        return max((_clamp(v) for v in values), default=0.0)

    @staticmethod
    def fuzzy_not(value: float) -> float:
        return 1.0 - _clamp(value)

    @staticmethod
    def weighted(values: dict[str, float], weights: dict[str, float]) -> float:
        numerator = 0.0
        denominator = 0.0
        for key, weight in weights.items():
            w = max(0.0, float(weight))
            numerator += _clamp(values.get(key, 0.0)) * w
            denominator += w
        return _clamp(numerator / denominator) if denominator else 0.0

    def willingness(
        self,
        *,
        confidence: float,
        utility: float,
        urgency: float,
        risk: float,
        novelty: float = 0.5,
    ) -> float:
        """Return a graded willingness value instead of a binary decision."""
        positive = self.weighted(
            {
                "confidence": confidence,
                "utility": utility,
                "urgency": urgency,
                "novelty": novelty,
            },
            {"confidence": 0.30, "utility": 0.35, "urgency": 0.25, "novelty": 0.10},
        )
        safety = self.fuzzy_not(risk)
        return _clamp((positive * 0.72) + (self.fuzzy_and(positive, safety) * 0.28))


class HybridReasoner:
    """Combines deductive fuzzy rules with lightweight inductive pattern learning."""

    def __init__(self, fuzzy: FuzzyLogicEngine | None = None):
        self.fuzzy = fuzzy or FuzzyLogicEngine()

    def deduct(
        self,
        facts: dict[str, float],
        rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized = {str(k): _clamp(v) for k, v in (facts or {}).items()}
        conclusions: dict[str, dict[str, Any]] = {}
        for index, rule in enumerate(rules or []):
            conditions = rule.get("if") or {}
            if not isinstance(conditions, dict) or not conditions:
                continue
            memberships: list[float] = []
            for key, requirement in conditions.items():
                actual = normalized.get(str(key), 0.0)
                if isinstance(requirement, dict):
                    minimum = _clamp(requirement.get("min", 0.5))
                    maximum = _clamp(requirement.get("max", 1.0))
                    if maximum < minimum:
                        minimum, maximum = maximum, minimum
                    if actual < minimum:
                        membership = 0.0
                    elif maximum <= minimum:
                        membership = 1.0
                    else:
                        membership = _clamp((actual - minimum) / (maximum - minimum))
                else:
                    threshold = _clamp(requirement)
                    membership = 1.0 if actual >= threshold else _clamp(actual / max(threshold, 1e-6))
                memberships.append(membership)
            activation = self.fuzzy.fuzzy_and(*memberships)
            weight = _clamp(rule.get("weight", 1.0))
            confidence = _clamp(activation * weight)
            conclusion = str(rule.get("then") or "").strip()
            if not conclusion or confidence <= 0:
                continue
            previous = conclusions.get(conclusion)
            candidate = {
                "conclusion": conclusion,
                "confidence": round(confidence, 4),
                "rule_index": index,
                "mode": "deductive",
            }
            if previous is None or confidence > float(previous["confidence"]):
                conclusions[conclusion] = candidate
        return sorted(conclusions.values(), key=lambda x: float(x["confidence"]), reverse=True)

    def induce(self, examples: list[dict[str, Any]], *, min_support: int = 2) -> list[dict[str, Any]]:
        """Learn transparent feature -> outcome hypotheses from examples.

        Each example may contain ``features`` as a list[str] or dict[str, truth], and
        ``outcome`` as a label. This is intentionally interpretable rather than a
        hidden classifier.
        """
        outcome_counts: dict[str, int] = defaultdict(int)
        feature_outcomes: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        feature_support: dict[str, float] = defaultdict(float)
        total = 0
        for example in examples or []:
            outcome = str(example.get("outcome") or "").strip()
            if not outcome:
                continue
            raw_features = example.get("features") or {}
            if isinstance(raw_features, dict):
                features = {str(k): _clamp(v) for k, v in raw_features.items()}
            else:
                features = {str(x): 1.0 for x in raw_features if str(x).strip()}
            if not features:
                continue
            total += 1
            outcome_counts[outcome] += 1
            for feature, strength in features.items():
                feature_support[feature] += strength
                feature_outcomes[feature][outcome] += strength
        hypotheses: list[dict[str, Any]] = []
        if total == 0:
            return hypotheses
        for feature, support in feature_support.items():
            if support < float(min_support):
                continue
            outcomes = feature_outcomes[feature]
            if not outcomes:
                continue
            outcome, matched = max(outcomes.items(), key=lambda x: x[1])
            precision = matched / max(support, 1e-6)
            coverage = support / max(total, 1)
            confidence = _clamp((precision * 0.75) + (min(1.0, coverage) * 0.25))
            hypotheses.append(
                {
                    "hypothesis": f"{feature} -> {outcome}",
                    "feature": feature,
                    "outcome": outcome,
                    "support": round(support, 3),
                    "precision": round(precision, 4),
                    "confidence": round(confidence, 4),
                    "mode": "inductive",
                }
            )
        return sorted(hypotheses, key=lambda x: (float(x["confidence"]), float(x["support"])), reverse=True)


@dataclass(slots=True)
class CognitiveIntention:
    intention_id: str
    title: str
    objective: str
    drive: str
    priority: float
    confidence: float
    willingness: float
    status: str
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class CognitiveCore:
    """Persistent, continuous, learning-oriented cognitive substrate for IRAS.

    This is a software analogue of selected biological properties, not a claim of
    consciousness. Memory has no application-level item cap; practical capacity is
    bounded by the configured SQLite/PostgreSQL storage. Concept neurons and weighted
    synapses provide associative recall. The background loop creates *intentions*, not
    authority: external state changes still go through IRAS permissions/automation.
    """

    BIOLOGICAL_REFERENCE_SIGNAL_SPEED_MPS = 75.0
    DEFAULT_DRIVES = {
        "completion": 0.78,
        "reliability": 0.86,
        "learning": 0.82,
        "curiosity": 0.58,
        "creativity": 0.55,
        "efficiency": 0.60,
    }

    def __init__(self, db: SQLiteDB, bus: EventBus | None = None):
        self.db = db
        self.bus = bus or EventBus()
        self.fuzzy = FuzzyLogicEngine()
        self.reasoner = HybridReasoner(self.fuzzy)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._goal_provider: Callable[[], list[dict[str, Any]]] | None = None
        self._lock = threading.RLock()
        self._last_tick: str | None = None
        self._last_tick_ms = 0
        self._ensure_schema()
        self._ensure_drives()

    def _ensure_schema(self) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS v5_cognitive_memory(
                memory_id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                kind TEXT NOT NULL,
                source TEXT NOT NULL,
                importance REAL NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_accessed TEXT,
                access_count INTEGER NOT NULL DEFAULT 0
            )""",
            """CREATE TABLE IF NOT EXISTS v5_cognitive_neurons(
                neuron_id TEXT PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                activation REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_fired TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS v5_cognitive_memory_neurons(
                memory_id TEXT NOT NULL,
                neuron_id TEXT NOT NULL,
                weight REAL NOT NULL,
                PRIMARY KEY(memory_id,neuron_id)
            )""",
            """CREATE TABLE IF NOT EXISTS v5_cognitive_synapses(
                src_neuron TEXT NOT NULL,
                dst_neuron TEXT NOT NULL,
                weight REAL NOT NULL,
                reinforcements INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(src_neuron,dst_neuron)
            )""",
            """CREATE TABLE IF NOT EXISTS v5_cognitive_intentions(
                intention_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                objective TEXT NOT NULL,
                drive TEXT NOT NULL,
                priority REAL NOT NULL,
                confidence REAL NOT NULL,
                willingness REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS v5_cognitive_drives(
                name TEXT PRIMARY KEY,
                value REAL NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS v5_cognitive_learning(
                learning_id TEXT PRIMARY KEY,
                memory_id TEXT,
                reward REAL NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
        ]
        for sql in statements:
            self.db.execute(sql)
        for sql in (
            "CREATE INDEX IF NOT EXISTS idx_v5_cog_memory_created ON v5_cognitive_memory(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_v5_cog_neuron_token ON v5_cognitive_neurons(token)",
            "CREATE INDEX IF NOT EXISTS idx_v5_cog_intention_status ON v5_cognitive_intentions(status,priority)",
        ):
            try:
                self.db.execute(sql)
            except Exception:
                pass

    def _ensure_drives(self) -> None:
        now = utc_now()
        for name, value in self.DEFAULT_DRIVES.items():
            try:
                self.db.execute(
                    "INSERT INTO v5_cognitive_drives(name,value,updated_at) VALUES(?,?,?)",
                    (name, float(value), now),
                )
            except Exception:
                pass

    def bind_goal_provider(self, provider: Callable[[], list[dict[str, Any]]] | None) -> None:
        self._goal_provider = provider

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def drives(self) -> dict[str, float]:
        rows = self.db.execute("SELECT name,value FROM v5_cognitive_drives ORDER BY name", fetch="all") or []
        return {str(row["name"]): _clamp(row["value"]) for row in rows}

    def set_drive(self, name: str, value: float) -> dict[str, Any]:
        name = str(name or "").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", name):
            raise ValueError("Drive name must be a simple identifier.")
        value = _clamp(value)
        existing = self.db.execute("SELECT name FROM v5_cognitive_drives WHERE name=?", (name,), fetch="one")
        if existing:
            self.db.execute(
                "UPDATE v5_cognitive_drives SET value=?,updated_at=? WHERE name=?",
                (value, utc_now(), name),
            )
        else:
            self.db.execute(
                "INSERT INTO v5_cognitive_drives(name,value,updated_at) VALUES(?,?,?)",
                (name, value, utc_now()),
            )
        self.bus.publish("cognition.drive_changed", name=name, value=value)
        return {"name": name, "value": value}

    def _neuron_for(self, token: str) -> str:
        row = self.db.execute(
            "SELECT neuron_id FROM v5_cognitive_neurons WHERE token=?",
            (token,),
            fetch="one",
        )
        if row:
            return str(row["neuron_id"])
        neuron_id = new_id("neu_")
        try:
            self.db.execute(
                "INSERT INTO v5_cognitive_neurons(neuron_id,token,activation,created_at,last_fired) VALUES(?,?,0,?,NULL)",
                (neuron_id, token, utc_now()),
            )
            return neuron_id
        except Exception:
            row = self.db.execute(
                "SELECT neuron_id FROM v5_cognitive_neurons WHERE token=?",
                (token,),
                fetch="one",
            )
            if not row:
                raise
            return str(row["neuron_id"])

    def remember(
        self,
        text: str,
        *,
        kind: str = "experience",
        source: str = "agent",
        importance: float = 0.5,
        confidence: float = 0.8,
    ) -> dict[str, Any]:
        text = str(text or "").strip()
        if not text:
            raise ValueError("Memory text is required.")
        if len(text) > 100000:
            raise ValueError("One cognitive memory item is limited to 100000 characters.")
        memory_id = new_id("mem_")
        now = utc_now()
        importance = _clamp(importance)
        confidence = _clamp(confidence)
        self.db.execute(
            """INSERT INTO v5_cognitive_memory(
                memory_id,text,kind,source,importance,confidence,created_at,updated_at,last_accessed,access_count
            ) VALUES(?,?,?,?,?,?,?,?,NULL,0)""",
            (memory_id, text, str(kind)[:80], str(source)[:160], importance, confidence, now, now),
        )
        tokens = _tokens(text)
        neuron_ids: list[str] = []
        for index, token in enumerate(tokens):
            neuron_id = self._neuron_for(token)
            neuron_ids.append(neuron_id)
            positional = 1.0 - min(index, 20) * 0.015
            weight = _clamp((0.55 + importance * 0.30 + confidence * 0.15) * positional)
            self.db.execute(
                "INSERT INTO v5_cognitive_memory_neurons(memory_id,neuron_id,weight) VALUES(?,?,?)",
                (memory_id, neuron_id, weight),
            )
        # Strengthen a bounded co-occurrence neighborhood. Memory size is unbounded;
        # per-item fan-out is bounded so learning cost remains predictable.
        local = neuron_ids[:24]
        for i, src in enumerate(local):
            for dst in local[i + 1 :]:
                self._strengthen_synapse(src, dst, 0.035 + importance * 0.035)
                self._strengthen_synapse(dst, src, 0.035 + importance * 0.035)
        self.bus.publish(
            "cognition.memory_created",
            memory_id=memory_id,
            kind=str(kind)[:80],
            source=str(source)[:160],
            neuron_count=len(neuron_ids),
        )
        return {
            "memory_id": memory_id,
            "kind": str(kind)[:80],
            "importance": importance,
            "confidence": confidence,
            "neuron_count": len(neuron_ids),
        }

    def _strengthen_synapse(self, src: str, dst: str, delta: float) -> None:
        row = self.db.execute(
            "SELECT weight,reinforcements FROM v5_cognitive_synapses WHERE src_neuron=? AND dst_neuron=?",
            (src, dst),
            fetch="one",
        )
        if row:
            weight = _clamp(float(row.get("weight") or 0.0) + float(delta))
            self.db.execute(
                """UPDATE v5_cognitive_synapses
                   SET weight=?,reinforcements=?,updated_at=? WHERE src_neuron=? AND dst_neuron=?""",
                (weight, int(row.get("reinforcements") or 0) + 1, utc_now(), src, dst),
            )
        else:
            self.db.execute(
                """INSERT INTO v5_cognitive_synapses(src_neuron,dst_neuron,weight,reinforcements,updated_at)
                   VALUES(?,?,?,?,?)""",
                (src, dst, _clamp(delta), 1, utc_now()),
            )

    def propagate(self, seed: str | list[str], *, hops: int = 2, decay: float = 0.62, limit: int = 40) -> list[dict[str, Any]]:
        seeds = _tokens(seed if isinstance(seed, str) else " ".join(seed), limit=24)
        if not seeds:
            return []
        frontier: dict[str, float] = {}
        token_by_neuron: dict[str, str] = {}
        for token in seeds:
            row = self.db.execute(
                "SELECT neuron_id,token FROM v5_cognitive_neurons WHERE token=?",
                (token,),
                fetch="one",
            )
            if row:
                neuron_id = str(row["neuron_id"])
                frontier[neuron_id] = 1.0
                token_by_neuron[neuron_id] = str(row["token"])
        activations = dict(frontier)
        for _ in range(max(0, min(int(hops), 6))):
            next_frontier: dict[str, float] = {}
            for src, source_activation in frontier.items():
                rows = self.db.execute(
                    """SELECT s.dst_neuron,s.weight,n.token
                       FROM v5_cognitive_synapses s
                       JOIN v5_cognitive_neurons n ON n.neuron_id=s.dst_neuron
                       WHERE s.src_neuron=? ORDER BY s.weight DESC LIMIT 24""",
                    (src,),
                    fetch="all",
                ) or []
                for row in rows:
                    dst = str(row["dst_neuron"])
                    score = _clamp(source_activation * float(row.get("weight") or 0.0) * float(decay))
                    if score <= 0.01:
                        continue
                    token_by_neuron[dst] = str(row.get("token") or "")
                    if score > next_frontier.get(dst, 0.0):
                        next_frontier[dst] = score
                    if score > activations.get(dst, 0.0):
                        activations[dst] = score
            frontier = next_frontier
            if not frontier:
                break
        now = utc_now()
        for neuron_id, activation in sorted(activations.items(), key=lambda x: x[1], reverse=True)[:64]:
            try:
                self.db.execute(
                    "UPDATE v5_cognitive_neurons SET activation=?,last_fired=? WHERE neuron_id=?",
                    (_clamp(activation), now, neuron_id),
                )
            except Exception:
                pass
        return [
            {"neuron_id": neuron_id, "token": token_by_neuron.get(neuron_id, ""), "activation": round(score, 4)}
            for neuron_id, score in sorted(activations.items(), key=lambda x: x[1], reverse=True)[: max(1, min(int(limit), 200))]
        ]

    def recall(self, query: str, *, limit: int = 10, hops: int = 2) -> list[dict[str, Any]]:
        activations = self.propagate(query, hops=hops, limit=80)
        if not activations:
            return []
        scores: dict[str, float] = defaultdict(float)
        for neuron in activations:
            rows = self.db.execute(
                "SELECT memory_id,weight FROM v5_cognitive_memory_neurons WHERE neuron_id=?",
                (neuron["neuron_id"],),
                fetch="all",
            ) or []
            for row in rows:
                scores[str(row["memory_id"])] += float(neuron["activation"]) * float(row.get("weight") or 0.0)
        results: list[dict[str, Any]] = []
        for memory_id, associative_score in sorted(scores.items(), key=lambda x: x[1], reverse=True)[: max(1, min(int(limit) * 3, 150))]:
            row = self.db.execute(
                "SELECT * FROM v5_cognitive_memory WHERE memory_id=?",
                (memory_id,),
                fetch="one",
            )
            if not row:
                continue
            importance = _clamp(row.get("importance") or 0.0)
            confidence = _clamp(row.get("confidence") or 0.0)
            final_score = associative_score * (0.55 + importance * 0.25 + confidence * 0.20)
            row["score"] = round(final_score, 4)
            results.append(row)
        results.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
        results = results[: max(1, min(int(limit), 100))]
        now = utc_now()
        for row in results:
            self.db.execute(
                """UPDATE v5_cognitive_memory SET last_accessed=?,access_count=access_count+1
                   WHERE memory_id=?""",
                (now, row["memory_id"]),
            )
        return results

    def reinforce(self, memory_id: str, reward: float, *, note: str = "") -> dict[str, Any]:
        row = self.db.execute(
            "SELECT importance,confidence FROM v5_cognitive_memory WHERE memory_id=?",
            (memory_id,),
            fetch="one",
        )
        if not row:
            raise KeyError(memory_id)
        reward = max(-1.0, min(1.0, float(reward)))
        importance = _clamp(float(row.get("importance") or 0.0) + reward * 0.08)
        confidence = _clamp(float(row.get("confidence") or 0.0) + reward * 0.12)
        self.db.execute(
            "UPDATE v5_cognitive_memory SET importance=?,confidence=?,updated_at=? WHERE memory_id=?",
            (importance, confidence, utc_now(), memory_id),
        )
        links = self.db.execute(
            "SELECT neuron_id,weight FROM v5_cognitive_memory_neurons WHERE memory_id=?",
            (memory_id,),
            fetch="all",
        ) or []
        for link in links:
            new_weight = _clamp(float(link.get("weight") or 0.0) + reward * 0.06)
            self.db.execute(
                "UPDATE v5_cognitive_memory_neurons SET weight=? WHERE memory_id=? AND neuron_id=?",
                (new_weight, memory_id, link["neuron_id"]),
            )
        learning_id = new_id("learn_")
        self.db.execute(
            "INSERT INTO v5_cognitive_learning(learning_id,memory_id,reward,note,created_at) VALUES(?,?,?,?,?)",
            (learning_id, memory_id, reward, str(note or "")[:4000], utc_now()),
        )
        self.bus.publish("cognition.learned", memory_id=memory_id, reward=reward)
        return {
            "learning_id": learning_id,
            "memory_id": memory_id,
            "reward": reward,
            "importance": importance,
            "confidence": confidence,
        }

    def learn_outcome(
        self,
        summary: str,
        *,
        success: bool,
        source: str = "outcome",
        importance: float = 0.7,
    ) -> dict[str, Any]:
        memory = self.remember(
            summary,
            kind="successful_outcome" if success else "failed_outcome",
            source=source,
            importance=importance,
            confidence=0.90 if success else 0.75,
        )
        learned = self.reinforce(memory["memory_id"], 0.75 if success else -0.45, note="outcome feedback")
        return {"memory": memory, "learning": learned}

    def reason(
        self,
        question: str,
        *,
        facts: dict[str, float] | None = None,
        rules: list[dict[str, Any]] | None = None,
        examples: list[dict[str, Any]] | None = None,
        memory_limit: int = 8,
    ) -> dict[str, Any]:
        memories = self.recall(question, limit=memory_limit)
        deductions = self.reasoner.deduct(facts or {}, rules or [])
        inductions = self.reasoner.induce(examples or [])
        memory_confidence = 0.0
        if memories:
            memory_confidence = sum(_clamp(m.get("confidence") or 0.0) for m in memories) / len(memories)
        logical_confidence = max(
            [float(x.get("confidence") or 0.0) for x in deductions + inductions] or [0.0]
        )
        confidence = self.fuzzy.fuzzy_or(memory_confidence * 0.72, logical_confidence)
        return {
            "question": str(question)[:12000],
            "mode": "hybrid_inductive_deductive_fuzzy",
            "deductions": deductions,
            "inductions": inductions,
            "memory_evidence": memories,
            "confidence": round(confidence, 4),
        }

    def create_intention(
        self,
        title: str,
        objective: str,
        *,
        drive: str = "completion",
        priority: float = 0.5,
        confidence: float = 0.7,
        risk: float = 0.15,
        novelty: float = 0.5,
    ) -> dict[str, Any]:
        title = str(title or "").strip()
        objective = str(objective or "").strip()
        if not title or not objective:
            raise ValueError("Intention title and objective are required.")
        drives = self.drives()
        drive_strength = drives.get(str(drive).strip().lower(), 0.5)
        priority = _clamp(priority)
        confidence = _clamp(confidence)
        willingness = self.fuzzy.willingness(
            confidence=confidence,
            utility=self.fuzzy.fuzzy_or(priority, drive_strength),
            urgency=priority,
            risk=_clamp(risk),
            novelty=_clamp(novelty),
        )
        intention_id = new_id("intent_")
        now = utc_now()
        self.db.execute(
            """INSERT INTO v5_cognitive_intentions(
                intention_id,title,objective,drive,priority,confidence,willingness,status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,'proposed',?,?)""",
            (
                intention_id,
                title[:240],
                objective[:12000],
                str(drive)[:80],
                priority,
                confidence,
                willingness,
                now,
                now,
            ),
        )
        payload = {
            "intention_id": intention_id,
            "title": title[:240],
            "objective": objective[:12000],
            "drive": str(drive)[:80],
            "priority": priority,
            "confidence": confidence,
            "willingness": willingness,
            "status": "proposed",
            "created_at": now,
            "updated_at": now,
        }
        self.bus.publish("cognition.intention_created", **payload)
        return payload

    def intentions(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if status:
            return self.db.execute(
                """SELECT * FROM v5_cognitive_intentions WHERE status=?
                   ORDER BY willingness DESC,priority DESC,created_at DESC LIMIT ?""",
                (str(status), max(1, min(int(limit), 500))),
                fetch="all",
            ) or []
        return self.db.execute(
            """SELECT * FROM v5_cognitive_intentions
               ORDER BY willingness DESC,priority DESC,created_at DESC LIMIT ?""",
            (max(1, min(int(limit), 500)),),
            fetch="all",
        ) or []

    def resolve_intention(self, intention_id: str, status: str) -> dict[str, Any]:
        status = str(status or "").strip().lower()
        if status not in {"accepted", "completed", "dismissed", "failed"}:
            raise ValueError("status must be accepted, completed, dismissed, or failed")
        self.db.execute(
            "UPDATE v5_cognitive_intentions SET status=?,updated_at=? WHERE intention_id=?",
            (status, utc_now(), intention_id),
        )
        row = self.db.execute(
            "SELECT * FROM v5_cognitive_intentions WHERE intention_id=?",
            (intention_id,),
            fetch="one",
        )
        if not row:
            raise KeyError(intention_id)
        self.bus.publish("cognition.intention_resolved", intention_id=intention_id, status=status)
        return row

    def create_idea(self, topic: str, *, limit: int = 6) -> dict[str, Any]:
        memories = self.recall(topic, limit=max(2, min(int(limit), 12)), hops=3)
        concepts = []
        for neuron in self.propagate(topic, hops=3, limit=16):
            token = str(neuron.get("token") or "").strip()
            if token and token not in concepts:
                concepts.append(token)
        blend = concepts[:5]
        if memories:
            basis = [str(m.get("text") or "")[:220] for m in memories[:3]]
        else:
            basis = []
        idea_id = new_id("idea_")
        idea = {
            "idea_id": idea_id,
            "topic": str(topic)[:1000],
            "concept_blend": blend,
            "memory_basis": basis,
            "creation_brief": (
                f"Explore {topic} by recombining " + ", ".join(blend)
                if blend else f"Explore a new approach to {topic}."
            ),
            "created_at": utc_now(),
        }
        self.bus.publish("cognition.idea_created", **idea)
        return idea

    def _recent_equivalent_intention(self, objective: str) -> bool:
        row = self.db.execute(
            """SELECT intention_id FROM v5_cognitive_intentions
               WHERE objective=? AND status IN ('proposed','accepted')
               ORDER BY created_at DESC LIMIT 1""",
            (str(objective)[:12000],),
            fetch="one",
        )
        return bool(row)

    def tick(self) -> dict[str, Any]:
        started = time.perf_counter()
        created: list[dict[str, Any]] = []
        drives = self.drives()
        goals: list[dict[str, Any]] = []
        if self._goal_provider is not None:
            try:
                goals = list(self._goal_provider() or [])[:20]
            except Exception:
                goals = []
        # Completion/reliability drives create candidate intentions from real pending goals.
        for goal in goals[:3]:
            title = str(goal.get("title") or goal.get("name") or "Advance pending goal")[:240]
            item_id = str(goal.get("item_id") or goal.get("goal_id") or "")
            objective = f"Review and advance goal '{title}'"
            if item_id:
                objective += f" ({item_id})"
            if self._recent_equivalent_intention(objective):
                continue
            priority = self.fuzzy.fuzzy_or(drives.get("completion", 0.5), float(goal.get("progress") or 0.0) * 0.5)
            intention = self.create_intention(
                f"Advance: {title}",
                objective,
                drive="completion",
                priority=priority,
                confidence=drives.get("reliability", 0.7),
                risk=0.08,
                novelty=0.25,
            )
            if intention["willingness"] >= 0.55:
                created.append(intention)
            else:
                self.resolve_intention(intention["intention_id"], "dismissed")
        # Learning is continuous but bounded: create one consolidation intention only when
        # enough experiences exist and no equivalent proposal is pending.
        counts = self.db.execute(
            "SELECT COUNT(*) AS n FROM v5_cognitive_memory",
            fetch="one",
        ) or {"n": 0}
        memory_count = int(counts.get("n") or 0)
        learning_objective = "Consolidate recent experiences into reusable lessons and identify one improvement opportunity."
        if memory_count >= 5 and drives.get("learning", 0.0) >= 0.55 and not self._recent_equivalent_intention(learning_objective):
            intention = self.create_intention(
                "Consolidate learning",
                learning_objective,
                drive="learning",
                priority=drives.get("learning", 0.7),
                confidence=0.78,
                risk=0.03,
                novelty=drives.get("curiosity", 0.5),
            )
            if intention["willingness"] >= 0.55:
                created.append(intention)
            else:
                self.resolve_intention(intention["intention_id"], "dismissed")
        self._last_tick = utc_now()
        self._last_tick_ms = int((time.perf_counter() - started) * 1000)
        self.bus.publish("cognition.tick", created=len(created), memory_count=memory_count)
        return {
            "created_intentions": created,
            "memory_count": memory_count,
            "goal_candidates": len(goals),
            "tick_ms": self._last_tick_ms,
            "at": self._last_tick,
        }

    def start(self, *, interval_seconds: float = 10.0) -> None:
        if self.running:
            return
        interval_seconds = max(2.0, min(float(interval_seconds), 3600.0))
        self._stop.clear()

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception as exc:
                    self.bus.publish("cognition.error", error=f"{type(exc).__name__}: {exc}"[:1000])
                self._stop.wait(interval_seconds)

        self._thread = threading.Thread(target=loop, name="iras-v5-cognition", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, Any]:
        def count(table: str) -> int:
            row = self.db.execute(f"SELECT COUNT(*) AS n FROM {table}", fetch="one") or {"n": 0}
            return int(row.get("n") or 0)

        intention_rows = self.db.execute(
            "SELECT status,COUNT(*) AS n FROM v5_cognitive_intentions GROUP BY status",
            fetch="all",
        ) or []
        return {
            "running": self.running,
            "continuous": True,
            "memory_policy": "no_application_item_cap_storage_bounded",
            "memory_items": count("v5_cognitive_memory"),
            "concept_neurons": count("v5_cognitive_neurons"),
            "synapses": count("v5_cognitive_synapses"),
            "learning_events": count("v5_cognitive_learning"),
            "intentions": {str(r["status"]): int(r["n"]) for r in intention_rows},
            "drives": self.drives(),
            "reasoning": ["inductive", "deductive", "fuzzy"],
            "learning": "reinforcement_plus_associative",
            "biological_reference_signal_speed_mps": self.BIOLOGICAL_REFERENCE_SIGNAL_SPEED_MPS,
            "actual_signal_transport": "native software/hardware speed; not artificially delayed",
            "last_tick": self._last_tick,
            "last_tick_ms": self._last_tick_ms,
        }
