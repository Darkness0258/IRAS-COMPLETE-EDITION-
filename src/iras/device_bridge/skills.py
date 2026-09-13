from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Any


SCHEMA_VERSION = 1
ALLOWED_SEMANTIC_ACTIONS = {
    "click",
    "double_click",
    "focus",
    "type_into",
    "press",
}
UNSAFE_APP_TOKENS = {
    "powershell",
    "pwsh",
    "cmd",
    "command prompt",
    "windows terminal",
    "terminal",
    "regedit",
    "registry editor",
    "mmc",
    "computer management",
    "group policy",
    "task scheduler",
    "wsl",
    "bash",
    "python",
    "python3",
    "services",
    "group policy editor",
    "local security policy",
    "anaconda prompt",
    "developer command prompt",
    "native tools command prompt",
}
COORDINATE_KEYS = {
    "x",
    "y",
    "left",
    "top",
    "right",
    "bottom",
    "bounds",
    "rect",
    "bounding_rectangle",
    "rectangle",
    "center",
    "point",
    "coordinates",
    "actual_x",
    "actual_y",
}
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_STORE_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _safe_app(app: str) -> bool:
    normalized = _norm(app)
    if not normalized:
        return False
    return not any(token in normalized for token in UNSAFE_APP_TOKENS)


def _strip_coordinates(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): _strip_coordinates(v)
            for k, v in value.items()
            if _norm(str(k)).replace(" ", "_") not in COORDINATE_KEYS
        }
    if isinstance(value, list):
        return [_strip_coordinates(item) for item in value]
    return value


def semantic_elements(observation: Any) -> list[dict[str, Any]]:
    """Return UIA-like dictionaries without ever exposing coordinate fields."""
    found: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            lowered = {str(k).casefold(): k for k in value}
            if any(
                key in lowered
                for key in (
                    "name",
                    "automation_id",
                    "automationid",
                    "role",
                    "control_type",
                    "controltype",
                )
            ):
                cleaned = _strip_coordinates(value)
                found.append(cleaned)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(observation)
    return found


def _element_value(element: dict[str, Any], *names: str) -> str:
    lowered = {str(k).casefold(): v for k, v in element.items()}
    for name in names:
        value = lowered.get(name.casefold())
        if value is not None:
            return str(value)
    return ""


def resolve_semantic_target(
    observation: Any,
    locator: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Resolve a learned semantic locator against a *fresh* UI observation.

    Matching order deliberately favors Automation ID, then name+role, then
    name alone. No screen coordinates are persisted or used for matching.
    """
    automation_id = _norm(locator.get("automation_id", ""))
    name = _norm(locator.get("name", ""))
    role = _norm(locator.get("role", ""))
    occurrence = max(1, int(locator.get("occurrence", 1) or 1))

    candidates: list[tuple[int, dict[str, Any]]] = []
    for element in semantic_elements(observation):
        element_id = _norm(
            _element_value(element, "automation_id", "automationid")
        )
        element_name = _norm(_element_value(element, "name"))
        element_role = _norm(
            _element_value(
                element,
                "role",
                "control_type",
                "controltype",
            )
        )

        identity_score = 0
        if automation_id and element_id == automation_id:
            identity_score += 100
        if name and element_name == name:
            identity_score += 60
        elif name and name in element_name:
            identity_score += 25

        # Role is only a discriminator. It is never sufficient identity by
        # itself, otherwise a missing "User Settings" button could silently
        # resolve to an unrelated Button.
        if identity_score == 0:
            continue

        score = identity_score
        if role and element_role == role:
            score += 20
        elif role and role in element_role:
            score += 8

        candidates.append((score, element))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    same_score = [
        element for score, element in candidates if score == candidates[0][0]
    ]
    index = min(occurrence - 1, len(same_score) - 1)
    chosen = same_score[index]
    resolved_id = _element_value(chosen, "automation_id", "automationid")
    resolved_name = _element_value(chosen, "name")
    resolved_role = _element_value(
        chosen,
        "role",
        "control_type",
        "controltype",
    )

    return {
        "target": resolved_id or resolved_name,
        "name": resolved_name,
        "automation_id": resolved_id,
        "role": resolved_role,
        "occurrence": occurrence,
    }


def render_parameters(value: Any, parameters: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return PLACEHOLDER_RE.sub(
            lambda match: str(parameters.get(match.group(1), match.group(0))),
            value,
        )
    if isinstance(value, dict):
        return {
            key: render_parameters(val, parameters)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [render_parameters(item, parameters) for item in value]
    return value


def _template_regex(template: str) -> re.Pattern[str]:
    parts: list[str] = []
    cursor = 0
    for match in PLACEHOLDER_RE.finditer(template):
        parts.append(re.escape(template[cursor:match.start()]))
        name = match.group(1)
        parts.append(fr"(?P<{name}>.+?)")
        cursor = match.end()
    parts.append(re.escape(template[cursor:]))
    return re.compile(r"^\s*" + "".join(parts) + r"\s*$", re.IGNORECASE)


def _token_score(left: str, right: str) -> float:
    a = set(re.findall(r"[a-z0-9]+", _norm(left)))
    b = set(re.findall(r"[a-z0-9]+", _norm(right)))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(slots=True)
class LearnedStep:
    app: str
    action: str
    locator: dict[str, Any]
    text: str = ""
    key: str = ""
    replace: bool = False
    expected_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _strip_coordinates(
            {
                "app": self.app,
                "action": self.action,
                "locator": self.locator,
                "text": self.text,
                "key": self.key,
                "replace": self.replace,
                "expected_state": self.expected_state,
            }
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearnedStep":
        return cls(
            app=str(data.get("app", "")),
            action=str(data.get("action", "")),
            locator=dict(data.get("locator") or {}),
            text=str(data.get("text", "")),
            key=str(data.get("key", "")),
            replace=bool(data.get("replace", False)),
            expected_state=dict(data.get("expected_state") or {}),
        )

    def is_safe(self) -> bool:
        return (
            _safe_app(self.app)
            and self.action in ALLOWED_SEMANTIC_ACTIONS
            and bool(
                self.locator.get("name")
                or self.locator.get("automation_id")
            )
        )


@dataclass(slots=True)
class LearnedSkill:
    skill_id: str
    app: str
    intent_template: str
    parameters: list[str]
    steps: list[LearnedStep]
    successes: int = 1
    failures: int = 0
    consecutive_failures: int = 0
    confidence: float = 0.67
    status: str = "active"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "app": self.app,
            "intent_template": self.intent_template,
            "parameters": list(self.parameters),
            "steps": [step.to_dict() for step in self.steps],
            "successes": self.successes,
            "failures": self.failures,
            "consecutive_failures": self.consecutive_failures,
            "confidence": round(float(self.confidence), 4),
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearnedSkill":
        return cls(
            skill_id=str(data.get("skill_id", "")),
            app=str(data.get("app", "")),
            intent_template=str(data.get("intent_template", "")),
            parameters=[str(item) for item in data.get("parameters", [])],
            steps=[
                LearnedStep.from_dict(item)
                for item in data.get("steps", [])
                if isinstance(item, dict)
            ],
            successes=max(0, int(data.get("successes", 1))),
            failures=max(0, int(data.get("failures", 0))),
            consecutive_failures=max(
                0, int(data.get("consecutive_failures", 0))
            ),
            confidence=float(data.get("confidence", 0.5)),
            status=str(data.get("status", "active")),
            created_at=str(data.get("created_at") or _now()),
            updated_at=str(data.get("updated_at") or _now()),
        )

    def is_safe(self) -> bool:
        return (
            _safe_app(self.app)
            and bool(self.steps)
            and all(step.is_safe() and _norm(step.app) == _norm(self.app) for step in self.steps)
        )


class PersistentSkillStore:
    def __init__(
        self,
        path: str | Path | None = None,
        *,
        database_url: str | None = None,
        namespace: str | None = None,
    ):
        configured = os.getenv("IRAS_SKILL_STORE", "").strip()
        if path is None:
            if configured:
                path = configured
            else:
                data_dir = Path(os.getenv("IRAS_DATA_DIR", "data"))
                path = data_dir / "app_skills.json"
        self.path = Path(path)
        self.database_url = str(
            database_url
            if database_url is not None
            else os.getenv("IRAS_SKILL_DATABASE_URL", "")
        ).strip()
        self.namespace = (
            str(
                namespace
                if namespace is not None
                else os.getenv("IRAS_SKILL_NAMESPACE", "default")
            ).strip()
            or "default"
        )

    def _db_connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "Postgres-backed learned skills require psycopg; install the "
                "cloud optional dependency."
            ) from exc
        return psycopg.connect(
            self.database_url,
            connect_timeout=10,
        )

    def _ensure_db(self, conn) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS iras_app_skills_v1 (
                namespace TEXT NOT NULL,
                skill_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(namespace, skill_id)
            )
            """
        )

    def _read_db(self) -> dict[str, Any]:
        with self._db_connect() as conn:
            self._ensure_db(conn)
            rows = conn.execute(
                "SELECT payload FROM iras_app_skills_v1 "
                "WHERE namespace=%s ORDER BY updated_at DESC",
                (self.namespace,),
            ).fetchall()
        skills = []
        for row in rows:
            raw = row[0]
            if isinstance(raw, dict):
                item = raw
            else:
                try:
                    item = json.loads(str(raw))
                except json.JSONDecodeError:
                    continue
            if isinstance(item, dict):
                skills.append(item)
        return {"schema_version": SCHEMA_VERSION, "skills": skills}

    def _write_db(self, payload: dict[str, Any]) -> None:
        desired = {
            str(item.get("skill_id", "")): item
            for item in payload.get("skills", [])
            if isinstance(item, dict) and item.get("skill_id")
        }
        with self._db_connect() as conn:
            self._ensure_db(conn)
            existing = {
                str(row[0])
                for row in conn.execute(
                    "SELECT skill_id FROM iras_app_skills_v1 WHERE namespace=%s",
                    (self.namespace,),
                ).fetchall()
            }
            for skill_id in existing - set(desired):
                conn.execute(
                    "DELETE FROM iras_app_skills_v1 "
                    "WHERE namespace=%s AND skill_id=%s",
                    (self.namespace, skill_id),
                )
            for skill_id, item in desired.items():
                conn.execute(
                    """
                    INSERT INTO iras_app_skills_v1
                        (namespace, skill_id, payload, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(namespace, skill_id) DO UPDATE SET
                        payload=EXCLUDED.payload,
                        updated_at=EXCLUDED.updated_at
                    """,
                    (
                        self.namespace,
                        skill_id,
                        json.dumps(item, ensure_ascii=False, sort_keys=True),
                        str(item.get("updated_at") or _now()),
                    ),
                )

    def _read(self) -> dict[str, Any]:
        with _STORE_LOCK:
            if self.database_url:
                return self._read_db()
            if not self.path.exists():
                return {"schema_version": SCHEMA_VERSION, "skills": []}
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {"schema_version": SCHEMA_VERSION, "skills": []}
            if not isinstance(raw, dict):
                return {"schema_version": SCHEMA_VERSION, "skills": []}
            raw.setdefault("schema_version", SCHEMA_VERSION)
            raw.setdefault("skills", [])
            return raw

    def _write(self, payload: dict[str, Any]) -> None:
        with _STORE_LOCK:
            if self.database_url:
                self._write_db(payload)
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            temp.replace(self.path)

    def all(self, include_demoted: bool = False) -> list[LearnedSkill]:
        result: list[LearnedSkill] = []
        for item in self._read().get("skills", []):
            if not isinstance(item, dict):
                continue
            skill = LearnedSkill.from_dict(item)
            if not skill.is_safe():
                continue
            if skill.status == "demoted" and not include_demoted:
                continue
            result.append(skill)
        result.sort(key=lambda item: (item.status != "active", -item.confidence, item.app))
        return result

    def get(self, skill_id: str) -> LearnedSkill | None:
        for skill in self.all(include_demoted=True):
            if skill.skill_id == skill_id:
                return skill
        return None

    def _save_skill(self, skill: LearnedSkill) -> None:
        if not skill.is_safe():
            raise ValueError("Refusing to persist an unsafe or non-semantic app skill.")
        payload = self._read()
        items = [item for item in payload.get("skills", []) if isinstance(item, dict)]
        replaced = False
        for index, item in enumerate(items):
            if str(item.get("skill_id", "")) == skill.skill_id:
                items[index] = skill.to_dict()
                replaced = True
                break
        if not replaced:
            items.append(skill.to_dict())
        payload["schema_version"] = SCHEMA_VERSION
        payload["skills"] = items
        self._write(payload)

    def learn_verified(
        self,
        intent_template: str,
        steps: list[LearnedStep | dict[str, Any]],
        parameters: list[str] | None = None,
    ) -> LearnedSkill | None:
        parsed: list[LearnedStep] = []
        for item in steps:
            step = item if isinstance(item, LearnedStep) else LearnedStep.from_dict(item)
            if not step.is_safe():
                return None
            parsed.append(step)
        if not parsed:
            return None
        apps = {_norm(step.app) for step in parsed}
        if len(apps) != 1:
            # Cross-app persistence is intentionally deferred to v3.6.
            return None
        app = parsed[0].app
        if not _safe_app(app):
            return None
        template = " ".join(str(intent_template or "").strip().split())
        if not template:
            return None
        params = list(parameters or dict.fromkeys(PLACEHOLDER_RE.findall(template)))
        identity = f"{_norm(app)}\n{_norm(template)}"
        skill_id = "skill_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
        existing = self.get(skill_id)
        if existing:
            existing.steps = parsed
            existing.parameters = params
            existing.updated_at = _now()
            existing.status = "active"
            existing.consecutive_failures = 0
            self._save_skill(existing)
            return existing
        skill = LearnedSkill(
            skill_id=skill_id,
            app=app,
            intent_template=template,
            parameters=params,
            steps=parsed,
        )
        self._save_skill(skill)
        return skill

    def find(self, command: str, app: str = "") -> dict[str, Any] | None:
        command = " ".join(str(command or "").strip().split())
        wanted_app = _norm(app)
        best: tuple[float, LearnedSkill, dict[str, str]] | None = None
        for skill in self.all(include_demoted=False):
            if wanted_app and _norm(skill.app) != wanted_app:
                continue
            parameters: dict[str, str] = {}
            exact_template = _template_regex(skill.intent_template).match(command)
            if exact_template:
                parameters = {
                    key: value.strip()
                    for key, value in exact_template.groupdict().items()
                }
                score = 1.0
            else:
                score = _token_score(command, skill.intent_template)
            score *= 0.55 + 0.45 * max(0.0, min(1.0, skill.confidence))
            if best is None or score > best[0]:
                best = (score, skill, parameters)
        if best is None or best[0] < 0.34:
            return None
        score, skill, parameters = best
        rendered_steps = [
            render_parameters(step.to_dict(), parameters)
            for step in skill.steps
        ]
        return {
            "skill_id": skill.skill_id,
            "app": skill.app,
            "intent_template": skill.intent_template,
            "parameters": parameters,
            "confidence": skill.confidence,
            "match_score": round(score, 4),
            "steps": rendered_steps,
        }

    def adapt_step(
        self,
        skill_id: str,
        step_index: int,
        resolved: dict[str, Any],
    ) -> LearnedSkill | None:
        skill = self.get(skill_id)
        if not skill or not (0 <= step_index < len(skill.steps)):
            return None
        step = skill.steps[step_index]
        previous = dict(step.locator)
        updated = {
            "name": str(resolved.get("name", "")),
            "automation_id": str(resolved.get("automation_id", "")),
            "role": str(resolved.get("role", "")),
            "occurrence": int(resolved.get("occurrence", 1) or 1),
        }
        # Preserve parameterized semantic fields. A validation performed for
        # contact=Hamza must not permanently turn {contact} into Hamza.
        for key in ("name", "automation_id", "role"):
            old_value = str(previous.get(key, ""))
            if PLACEHOLDER_RE.search(old_value):
                updated[key] = old_value
        step.locator = updated
        skill.updated_at = _now()
        self._save_skill(skill)
        return skill

    @staticmethod
    def _confidence(successes: int, failures: int) -> float:
        # Beta(1,1) posterior mean: bounded, monotonic and easy to inspect.
        return (successes + 1.0) / (successes + failures + 2.0)

    def record_success(self, skill_id: str) -> LearnedSkill | None:
        skill = self.get(skill_id)
        if not skill:
            return None
        skill.successes += 1
        skill.consecutive_failures = 0
        skill.confidence = self._confidence(skill.successes, skill.failures)
        if skill.confidence >= 0.45:
            skill.status = "active"
        skill.updated_at = _now()
        self._save_skill(skill)
        return skill

    def record_failure(self, skill_id: str) -> LearnedSkill | None:
        skill = self.get(skill_id)
        if not skill:
            return None
        skill.failures += 1
        skill.consecutive_failures += 1
        skill.confidence = self._confidence(skill.successes, skill.failures)
        if skill.consecutive_failures >= 2 or skill.confidence < 0.35:
            skill.status = "demoted"
        skill.updated_at = _now()
        self._save_skill(skill)
        return skill

    def delete(self, skill_id: str) -> bool:
        payload = self._read()
        items = [item for item in payload.get("skills", []) if isinstance(item, dict)]
        kept = [item for item in items if str(item.get("skill_id", "")) != skill_id]
        if len(kept) == len(items):
            return False
        payload["skills"] = kept
        self._write(payload)
        return True

    def inspect(self, skill_id: str) -> dict[str, Any] | None:
        skill = self.get(skill_id)
        return deepcopy(skill.to_dict()) if skill else None
