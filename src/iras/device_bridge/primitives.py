from __future__ import annotations

"""Reusable deterministic Windows UI primitives built on fresh observations."""

import time
from typing import Any


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _element_text(element: dict) -> str:
    return " ".join(
        str(element.get(key) or "")
        for key in ("label", "name", "value", "automation_id", "role")
    )


class VerifiedUIPrimitives:
    def __init__(self, ui: Any, computer: Any):
        self.ui = ui
        self.computer = computer

    @staticmethod
    def find_in_observation(
        observation: dict,
        text: str,
        *,
        exact: bool = False,
        role: str = "",
        interactive_only: bool = False,
    ) -> list[dict]:
        wanted = _norm(text)
        wanted_role = _norm(role)
        matches = []
        for element in observation.get("elements", []) or []:
            if not wanted:
                continue
            if exact:
                # Exact matching applies to individual semantic fields. Including
                # the role in one concatenated string made a button labelled
                # "Settings" become "settings button", which could never match
                # exactly. Keep role as a separate filter below.
                semantic_fields = (
                    element.get("label"),
                    element.get("name"),
                    element.get("value"),
                    element.get("automation_id"),
                )
                matched = any(_norm(value) == wanted for value in semantic_fields if value not in (None, ""))
            else:
                haystack = _norm(_element_text(element))
                matched = wanted in haystack
            if not matched:
                continue
            if wanted_role and wanted_role != _norm(element.get("role")):
                continue
            if interactive_only and not bool(element.get("interactive", True)):
                continue
            matches.append(element)
        return matches

    def observe(self, *, vision: str = "auto", scope: str = "foreground", max_elements: int = 180) -> dict:
        return self.computer.observe(vision=vision, scope=scope, max_elements=max_elements)

    def find_text(
        self,
        text: str,
        *,
        exact: bool = False,
        role: str = "",
        vision: str = "auto",
        scope: str = "foreground",
    ) -> dict:
        observation = self.observe(vision=vision, scope=scope)
        matches = self.find_in_observation(observation, text, exact=exact, role=role)
        return {
            "found": bool(matches),
            "ambiguous": len(matches) > 1,
            "count": len(matches),
            "matches": matches[:12],
            "observation_id": observation.get("observation_id"),
            "foreground": observation.get("foreground"),
        }

    def wait_text(
        self,
        text: str,
        *,
        timeout: float = 8.0,
        interval: float = 0.35,
        exact: bool = False,
        role: str = "",
        vision: str = "auto",
    ) -> dict:
        deadline = time.monotonic() + max(0.5, min(float(timeout), 30.0))
        attempts = 0
        last = None
        while time.monotonic() < deadline:
            attempts += 1
            last = self.find_text(text, exact=exact, role=role, vision=vision)
            if last["found"]:
                last["attempts"] = attempts
                return last
            time.sleep(max(0.05, min(float(interval), 1.0)))
        return {**(last or {"found": False, "matches": []}), "attempts": attempts}

    def _unique_target(self, observation: dict, text: str, *, exact: bool, role: str, interactive_only: bool = True) -> dict:
        matches = self.find_in_observation(
            observation,
            text,
            exact=exact,
            role=role,
            interactive_only=interactive_only,
        )
        if not matches:
            raise RuntimeError(f"No visible element matched {text!r}.")
        if len(matches) != 1:
            raise RuntimeError(f"{text!r} matched {len(matches)} visible elements; refusing to guess.")
        return matches[0]

    def click_text(
        self,
        text: str,
        *,
        exact: bool = False,
        role: str = "",
        vision: str = "auto",
        verify_text: str = "",
    ) -> dict:
        observation = self.observe(vision=vision)
        target = self._unique_target(observation, text, exact=exact, role=role)
        result = self.computer.action(
            observation_id=str(observation.get("observation_id") or ""),
            action="click",
            element_id=str(target.get("element_id") or ""),
            verify=False,
        )
        verified = None
        if verify_text:
            verified = self.wait_text(verify_text, timeout=8.0, vision=vision)
            if not verified.get("found"):
                raise RuntimeError(
                    f"Click was delivered, but fresh observations did not prove {verify_text!r}. The click was not replayed."
                )
        return {"action": result, "target": target, "verified": verified}

    def type_into_text(
        self,
        target_text: str,
        text: str,
        *,
        replace: bool = True,
        exact: bool = False,
        role: str = "",
        vision: str = "auto",
    ) -> dict:
        observation = self.observe(vision=vision)
        target = self._unique_target(observation, target_text, exact=exact, role=role)
        result = self.computer.action(
            observation_id=str(observation.get("observation_id") or ""),
            action="type_into",
            element_id=str(target.get("element_id") or ""),
            text=str(text),
            replace=bool(replace),
            verify=False,
        )
        return {"action": result, "target": target, "reobserve_required": True}

    def scroll_until_text(
        self,
        text: str,
        *,
        amount: int = -620,
        max_steps: int = 6,
        vision: str = "auto",
    ) -> dict:
        max_steps = max(1, min(int(max_steps), 12))
        for step in range(max_steps + 1):
            observation = self.observe(vision=vision)
            matches = self.find_in_observation(observation, text)
            if matches:
                return {"found": True, "step": step, "matches": matches[:8], "observation_id": observation.get("observation_id")}
            if step >= max_steps:
                break
            # One scroll consumes this observation; the next loop always starts
            # from a fresh observation and therefore cannot replay the action.
            self.computer.action(
                observation_id=str(observation.get("observation_id") or ""),
                action="scroll",
                amount=int(amount),
                verify=False,
            )
        return {"found": False, "step": max_steps, "matches": []}

    def open_app_verified(self, app: str, *, timeout: float = 10.0) -> dict:
        try:
            result = self.ui.app_control(app, "focus")
            mode = "focused"
        except RuntimeError:
            result = self.ui.catalog.launch(app)
            mode = "launched"
        wanted = _norm(app)
        deadline = time.monotonic() + max(1.0, min(float(timeout), 20.0))
        while time.monotonic() < deadline:
            foreground = self.computer._foreground()
            if wanted in _norm(foreground.get("title")) or (
                app.casefold() == "explorer" and "file explorer" in _norm(foreground.get("title"))
            ):
                return {"verified": True, "mode": mode, "foreground": foreground, "result": result}
            time.sleep(0.2)
        raise RuntimeError(f"{app!r} was opened/focused but Windows did not verify it as the foreground app.")
