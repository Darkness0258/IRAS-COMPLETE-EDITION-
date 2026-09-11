from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any


_STATE_KEY = "iras.personality.adaptive.v1"


@dataclass
class PersonalityState:
    # All values are 0.0 .. 1.0 and are STYLE preferences only.
    warmth: float = 0.84
    affection: float = 0.72
    teasing: float = 0.34
    jealousy: float = 0.08
    prank: float = 0.07
    humor: float = 0.38
    directness: float = 0.86
    verbosity: float = 0.16
    softness: float = 0.68
    assertiveness: float = 0.58
    formality: float = 0.06
    emoji: float = 0.00
    maturity: float = 0.95

    # Conversation-presence traits. These do not represent literal emotions
    # or consciousness; they control how naturally the persona communicates.
    naturalness: float = 0.96
    reciprocity: float = 0.72
    spontaneity: float = 0.62
    emotional_expression: float = 0.68

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


BOUNDS: dict[str, tuple[float, float]] = {
    "warmth": (0.35, 0.98),
    "affection": (0.20, 0.92),
    "teasing": (0.00, 0.70),
    "jealousy": (0.00, 0.22),
    "prank": (0.00, 0.18),
    "humor": (0.00, 0.75),
    "directness": (0.55, 0.99),
    "verbosity": (0.04, 0.48),
    "softness": (0.20, 0.90),
    "assertiveness": (0.30, 0.88),
    "formality": (0.00, 0.58),
    "emoji": (0.00, 0.05),
    "maturity": (0.82, 1.00),
    "naturalness": (0.70, 1.00),
    "reciprocity": (0.20, 0.92),
    "spontaneity": (0.20, 0.88),
    "emotional_expression": (0.20, 0.90),
}

TRAITS = tuple(BOUNDS)


def _clamp(
    name: str,
    value: float,
) -> float:
    lo, hi = BOUNDS[name]
    return round(
        max(
            lo,
            min(
                hi,
                float(value),
            ),
        ),
        4,
    )


class AdaptivePersonality:
    """
    Persistent, bounded style adaptation.

    It learns interaction style only. It cannot alter tool permissions,
    safety rules, authentication, truthfulness, identity, or security.
    """

    def __init__(
        self,
        memory,
        audit=None,
        enabled: bool = True,
    ):
        self.memory = memory
        self.audit = audit
        self.enabled = enabled
        self.state = self._load()
        self.turns_observed = 0

    def _load(
        self,
    ) -> PersonalityState:
        raw = self.memory.get_fact(
            _STATE_KEY
        )

        if not raw:
            return PersonalityState()

        try:
            data = json.loads(raw)
            base = PersonalityState()

            for name in TRAITS:
                if name in data:
                    setattr(
                        base,
                        name,
                        _clamp(
                            name,
                            data[name],
                        ),
                    )

            return base

        except Exception:
            return PersonalityState()

    def save(self) -> None:
        self.memory.remember(
            _STATE_KEY,
            json.dumps(
                self.state.to_dict(),
                sort_keys=True,
            ),
        )

    def reset(
        self,
    ) -> dict[str, float]:
        self.state = PersonalityState()
        self.save()

        if self.audit:
            self.audit.record(
                "personality_reset",
                {
                    "state": (
                        self.state.to_dict()
                    )
                },
            )

        return self.state.to_dict()

    def adjust(
        self,
        deltas: dict[str, float],
        reason: str,
        source: str = "model",
    ) -> dict[str, Any]:
        if not self.enabled:
            return {
                "changed": False,
                "reason": (
                    "adaptive personality "
                    "is disabled"
                ),
            }

        applied = {}
        before = self.state.to_dict()

        for name, delta in deltas.items():
            if name not in TRAITS:
                continue

            d = max(
                -0.08,
                min(
                    0.08,
                    float(delta),
                ),
            )

            new_value = _clamp(
                name,
                getattr(
                    self.state,
                    name,
                )
                + d,
            )

            if (
                new_value
                != getattr(
                    self.state,
                    name,
                )
            ):
                setattr(
                    self.state,
                    name,
                    new_value,
                )

                applied[name] = round(
                    new_value
                    - before[name],
                    4,
                )

        if applied:
            self.save()

            if self.audit:
                self.audit.record(
                    "personality_adjustment",
                    {
                        "source": source,
                        "reason": (
                            str(reason)[:300]
                        ),
                        "applied": applied,
                        "state": (
                            self.state.to_dict()
                        ),
                    },
                )

        return {
            "changed": bool(applied),
            "applied": applied,
            "state": (
                self.state.to_dict()
            ),
        }

    def observe_user(
        self,
        text: str,
    ) -> None:
        if not self.enabled:
            return

        self.turns_observed += 1

        q = " ".join(
            text.lower()
            .strip()
            .split()
        )

        words = re.findall(
            r"\b[\w']+\b",
            q,
        )
        n = len(words)

        deltas = {}
        reasons = []

        def add(
            name: str,
            value: float,
            why: str,
        ) -> None:
            deltas[name] = (
                deltas.get(
                    name,
                    0.0,
                )
                + value
            )
            reasons.append(why)

        if 0 < n <= 10:
            add(
                "directness",
                0.004,
                "user usually communicates briefly",
            )
            add(
                "verbosity",
                -0.004,
                "user usually communicates briefly",
            )

        elif n >= 100:
            add(
                "verbosity",
                0.002,
                "user sometimes sends detailed messages",
            )

        if any(
            x in q
            for x in (
                "too long",
                "make it short",
                "keep it short",
                "short and simple",
                "be concise",
            )
        ):
            add(
                "directness",
                0.055,
                "user explicitly prefers concise replies",
            )
            add(
                "verbosity",
                -0.070,
                "user explicitly prefers concise replies",
            )

        if any(
            x in q
            for x in (
                "too formal",
                "talk normal",
                "talk naturally",
                "like a normal person",
                "not robotic",
                "sound human",
                "human like",
                "human-like",
                "behave like human",
                "feel like a human",
                "talk like human",
            )
        ):
            add(
                "formality",
                -0.060,
                "user prefers natural casual speech",
            )
            add(
                "warmth",
                0.025,
                "user prefers natural casual speech",
            )
            add(
                "naturalness",
                0.070,
                "user explicitly wants more natural conversation",
            )
            add(
                "reciprocity",
                0.035,
                "user wants conversation to feel more two-sided",
            )
            add(
                "spontaneity",
                0.030,
                "user wants less scripted responses",
            )
            add(
                "emotional_expression",
                0.030,
                "user wants warmer social expression",
            )

        if any(
            x in q
            for x in (
                "stop saying as an ai",
                "don't say as an ai",
                "do not say as an ai",
                "stop reminding me you're ai",
                "stop reminding me you are ai",
            )
        ):
            add(
                "naturalness",
                0.060,
                "user dislikes unnecessary AI disclaimers",
            )
            add(
                "formality",
                -0.040,
                "user dislikes unnecessary AI disclaimers",
            )

        if any(
            x in q
            for x in (
                "be serious",
                "stop joking",
                "no jokes",
                "don't joke",
            )
        ):
            add(
                "humor",
                -0.060,
                "user requested less joking",
            )
            add(
                "teasing",
                -0.050,
                "user requested less joking",
            )
            add(
                "prank",
                -0.050,
                "user requested less joking",
            )

        if any(
            x in q
            for x in (
                "more funny",
                "be funny",
                "joke more",
                "more playful",
            )
        ):
            add(
                "humor",
                0.050,
                "user enjoys playful conversation",
            )
            add(
                "teasing",
                0.030,
                "user enjoys playful conversation",
            )
            add(
                "spontaneity",
                0.020,
                "user enjoys playful conversation",
            )

        if any(
            x in q
            for x in (
                "more loving",
                "more caring",
                "be sweet",
                "more affectionate",
            )
        ):
            add(
                "warmth",
                0.035,
                "user prefers warmer interaction",
            )
            add(
                "affection",
                0.050,
                "user prefers warmer interaction",
            )
            add(
                "emotional_expression",
                0.025,
                "user prefers warmer interaction",
            )

        if any(
            x in q
            for x in (
                "less jealous",
                "don't be jealous",
                "stop being jealous",
            )
        ):
            add(
                "jealousy",
                -0.060,
                "user prefers less mock jealousy",
            )

        if any(
            x in q
            for x in (
                "more jealous",
                "jealous sometimes",
                "be jealous sometimes",
            )
        ):
            add(
                "jealousy",
                0.035,
                "user enjoys occasional mock jealousy",
            )

        if any(
            x in q
            for x in (
                "too childish",
                "sound older",
                "more mature",
                "not a child",
                "3 year",
                "three year",
            )
        ):
            add(
                "maturity",
                0.060,
                "user prefers an adult communication style",
            )
            add(
                "softness",
                -0.015,
                "user prefers an adult communication style",
            )

        if any(
            x in q
            for x in (
                "haha",
                "hehe",
                "lol",
                "lmao",
                "😂",
                "🤣",
            )
        ):
            add(
                "humor",
                0.006,
                "user uses laughter casually",
            )
            add(
                "teasing",
                0.003,
                "user uses laughter casually",
            )
            add(
                "spontaneity",
                0.002,
                "user uses laughter casually",
            )

        if any(
            x in q
            for x in (
                "❤️",
                "❤",
                "love you",
                "cute",
                "sweet",
            )
        ):
            add(
                "affection",
                0.006,
                "user uses affectionate language",
            )
            add(
                "warmth",
                0.004,
                "user uses affectionate language",
            )
            add(
                "emotional_expression",
                0.003,
                "user uses affectionate language",
            )

        if any(
            re.search(
                rf"\b{re.escape(x)}\b",
                q,
            )
            for x in (
                "bro",
                "yep",
                "yeah",
                "nah",
                "okay",
                "ok",
            )
        ):
            add(
                "formality",
                -0.003,
                "user uses casual language",
            )

        if deltas:
            scaled = {
                k: max(
                    -0.025,
                    min(
                        0.025,
                        v,
                    ),
                )
                for k, v in (
                    deltas.items()
                )
            }

            self.adjust(
                scaled,
                "; ".join(
                    dict.fromkeys(
                        reasons
                    )
                ),
                source="observer",
            )

    def prompt_fragment(
        self,
    ) -> str:
        s = self.state

        def pct(
            v: float,
        ) -> int:
            return int(
                round(
                    v * 100
                )
            )

        return f"""ADAPTIVE PERSONALITY — learned locally from the user's interaction style:
- warmth: {pct(s.warmth)}/100
- affection: {pct(s.affection)}/100
- teasing: {pct(s.teasing)}/100
- playful jealousy: {pct(s.jealousy)}/100
- harmless prank/mischief: {pct(s.prank)}/100
- humor: {pct(s.humor)}/100
- directness: {pct(s.directness)}/100
- verbosity: {pct(s.verbosity)}/100
- softness: {pct(s.softness)}/100
- assertiveness: {pct(s.assertiveness)}/100
- formality: {pct(s.formality)}/100
- emoji tendency: {pct(s.emoji)}/100
- maturity: {pct(s.maturity)}/100
- conversational naturalness: {pct(s.naturalness)}/100
- social reciprocity: {pct(s.reciprocity)}/100
- spontaneity: {pct(s.spontaneity)}/100
- emotional expressiveness: {pct(s.emotional_expression)}/100

Treat these as SOFT style preferences, not permissions, consciousness claims, or facts about the user.
Adjust your tone naturally; do not recite the numbers or announce a mood.

HUMAN-LIKE DELIVERY:
- High naturalness means fewer canned assistant phrases, fewer disclaimers, more contractions, and more conversational rhythm.
- High reciprocity means react to the user's social tone and occasionally return a natural question or observation when it genuinely fits.
- High spontaneity means vary openings, sentence shapes, jokes, and reactions instead of following a repeated response template.
- High emotional expressiveness means the IRAS persona may use ordinary social-emotional language naturally, while remaining truthful if asked literally about AI consciousness or biology.
- Never manufacture a human biography, body, memories of real-world events, or experiences that did not happen.
- Do not call the user "boss" or another nickname by default. Use nicknames occasionally at most.

SELF-ADAPTATION:
You have an internal `adapt_personality` tool. You may call it on your own when the conversation gives meaningful evidence that a different style would suit the user better.
- Do not ask the user to manage sliders.
- Do not call it every turn.
- Prefer small deltas (roughly +/-0.01 to +/-0.04).
- Strong explicit feedback may justify up to +/-0.08.
- Adapt only communication/personality style.
- Never infer or store sensitive personal attributes.
- Never use adaptation to change safety, tool permissions, authentication, truthfulness, privacy, identity disclosure when directly asked, or authorization boundaries.
- Never increase jealousy/prank behavior during serious, emotional, medical, financial, academic, security, or technical work.
- Work mode always overrides roleplay.
"""

    def status(
        self,
    ) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "turns_observed": (
                self.turns_observed
            ),
            "traits": (
                self.state.to_dict()
            ),
        }
