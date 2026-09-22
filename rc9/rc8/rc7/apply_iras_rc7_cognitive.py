from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MARKER = "IRAS_RC7_COGNITIVE_CORE"
HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / "payload"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=check)


def backup_file(root: Path, backup: Path, relative: str) -> None:
    src = root / relative
    if src.exists():
        dst = backup / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def replace_once(path: Path, old: str, new: str, *, sentinel: str = "") -> bool:
    text = path.read_text(encoding="utf-8")
    if sentinel and sentinel in text:
        return False
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Patch anchor mismatch in {path}: expected 1 occurrence, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def patch_runtime(root: Path) -> None:
    path = root / "src/iras/v5/runtime.py"
    replace_once(
        path,
        "from .automation_engine import AutomationEngine\n",
        "from .automation_engine import AutomationEngine\nfrom .cognitive_core import CognitiveCore\n",
        sentinel="from .cognitive_core import CognitiveCore",
    )
    replace_once(
        path,
        "        self.goals = GoalHierarchy(self.db)\n        self.migrations = MigrationManager(self.db)\n",
        "        self.goals = GoalHierarchy(self.db)\n        self.cognition = CognitiveCore(self.db, self.bus)\n        self.cognition.bind_goal_provider(lambda: self.goals.next_actions(20))\n        self.migrations = MigrationManager(self.db)\n",
        sentinel="self.cognition = CognitiveCore",
    )
    replace_once(
        path,
        '        self.bus.subscribe("monitor.changed", self._notify_monitor_change)\n        self.bus.subscribe("monitor.error", self._notify_monitor_error)\n',
        '        self.bus.subscribe("monitor.changed", self._notify_monitor_change)\n        self.bus.subscribe("monitor.error", self._notify_monitor_error)\n        self.bus.subscribe("automation.finished", self._learn_automation_outcome)\n',
        sentinel='subscribe("automation.finished"',
    )
    anchor = "    def submit_scheduled_prompt(self, prompt: str, row: dict[str, Any]) -> Any:\n"
    method = '''    def _learn_automation_outcome(self, event) -> None:
        payload = dict(getattr(event, "payload", {}) or {})
        automation_id = str(payload.get("automation_id") or "unknown")
        ok = bool(payload.get("ok"))
        source = str(payload.get("source") or "automation")
        error = str(payload.get("error") or "").strip()
        summary = f"Automation {automation_id} {'succeeded' if ok else 'failed'} via {source}."
        if error:
            summary += " Error: " + error[:1500]
        try:
            self.cognition.learn_outcome(summary, success=ok, source="automation")
        except Exception:
            pass

'''
    replace_once(path, anchor, method + anchor, sentinel="def _learn_automation_outcome")
    replace_once(
        path,
        '        self.monitoring.start(poll_seconds=float(os.getenv("IRAS_V5_MONITOR_POLL_SECONDS", "15")))\n        self._started = True\n',
        '        self.cognition.start(\n            interval_seconds=float(os.getenv("IRAS_V5_COGNITION_TICK_SECONDS", "10"))\n        )\n        self.monitoring.start(poll_seconds=float(os.getenv("IRAS_V5_MONITOR_POLL_SECONDS", "15")))\n        self._started = True\n',
        sentinel="IRAS_V5_COGNITION_TICK_SECONDS",
    )
    replace_once(
        path,
        "        self.scheduler.stop()\n        self.automations.stop()\n        self.monitoring.stop()\n",
        "        self.scheduler.stop()\n        self.automations.stop()\n        self.cognition.stop()\n        self.monitoring.stop()\n",
        sentinel="self.cognition.stop()",
    )
    replace_once(
        path,
        '            "automation_worker_active": self.automations.running,\n            "monitors": len(self.monitoring.list()),\n',
        '            "automation_worker_active": self.automations.running,\n            "cognitive_core": self.cognition.status(),\n            "cognitive_core_running": self.cognition.running,\n            "monitors": len(self.monitoring.list()),\n',
        sentinel='"cognitive_core_running"',
    )


def patch_tools(root: Path) -> None:
    path = root / "src/iras/tools/v5.py"
    anchor = '    add(Tool("v5_voice_barge_in", "Interrupt current IRAS speech output.", _schema(), lambda: {"interrupted": v5.voice.barge_in()}, PermissionLevel.SAFE_ACTION))\n'
    addition = anchor + '''
    # RC7 cognitive core ---------------------------------------------------------------------
    add(Tool("v5_cognition_status", "Inspect continuous cognitive state, associative memory, neurons, drives and intentions.", _schema(), lambda: v5.cognition.status(), PermissionLevel.READ))
    add(Tool("v5_cognition_drives", "Read persistent cognitive drive strengths.", _schema(), lambda: v5.cognition.drives(), PermissionLevel.READ))
    add(Tool("v5_cognition_set_drive", "Adjust one persistent cognitive drive. This changes internal goal weighting but grants no external authority.", _schema({"name": {"type": "string", "minLength": 2, "maxLength": 64}, "value": {"type": "number", "minimum": 0, "maximum": 1}}, ["name", "value"]), lambda name, value: v5.cognition.set_drive(name, value), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_cognition_remember", "Store a persistent cognitive memory with associative concept-neuron links.", _schema({"text": {"type": "string", "minLength": 1, "maxLength": 100000}, "kind": _str(80), "source": _str(160), "importance": {"type": "number", "minimum": 0, "maximum": 1}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}}, ["text"]), lambda text, kind="experience", source="agent", importance=.5, confidence=.8: v5.cognition.remember(text, kind=kind, source=source, importance=importance, confidence=confidence), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_cognition_recall", "Associatively recall cognitive memories by propagating activation through concept neurons.", _schema({"query": {"type": "string", "minLength": 1, "maxLength": 12000}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}, "hops": {"type": "integer", "minimum": 0, "maximum": 6}}, ["query"]), lambda query, limit=10, hops=2: v5.cognition.recall(query, limit=limit, hops=hops), PermissionLevel.READ))
    add(Tool("v5_cognition_propagate", "Inspect concept-neuron signal propagation and activation strengths.", _schema({"seed": {"type": "string", "minLength": 1, "maxLength": 12000}, "hops": {"type": "integer", "minimum": 0, "maximum": 6}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}, ["seed"]), lambda seed, hops=2, limit=40: v5.cognition.propagate(seed, hops=hops, limit=limit), PermissionLevel.READ))
    add(Tool("v5_cognition_reason", "Run hybrid deductive + inductive reasoning with fuzzy confidence and associative memory evidence.", _schema({"question": {"type": "string", "minLength": 1, "maxLength": 12000}, "facts": _obj(), "rules": {"type": "array", "items": _obj(), "maxItems": 200}, "examples": {"type": "array", "items": _obj(), "maxItems": 1000}, "memory_limit": {"type": "integer", "minimum": 1, "maximum": 50}}, ["question"]), lambda question, facts=None, rules=None, examples=None, memory_limit=8: v5.cognition.reason(question, facts=facts or {}, rules=rules or [], examples=examples or [], memory_limit=memory_limit), PermissionLevel.READ))
    add(Tool("v5_cognition_learn", "Learn from an observed outcome and reinforce or weaken associated cognitive memory.", _schema({"summary": {"type": "string", "minLength": 1, "maxLength": 100000}, "success": {"type": "boolean"}, "source": _str(160), "importance": {"type": "number", "minimum": 0, "maximum": 1}}, ["summary", "success"]), lambda summary, success, source="outcome", importance=.7: v5.cognition.learn_outcome(summary, success=success, source=source, importance=importance), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_cognition_intentions", "List self-generated internal intentions. Intentions do not grant tool authority.", _schema({"status": _str(32), "limit": {"type": "integer", "minimum": 1, "maximum": 500}}), lambda status="", limit=100: v5.cognition.intentions(status=status or None, limit=limit), PermissionLevel.READ))
    add(Tool("v5_cognition_create_intention", "Create an internal intention using fuzzy willingness scoring.", _schema({"title": {"type": "string", "minLength": 1, "maxLength": 240}, "objective": {"type": "string", "minLength": 1, "maxLength": 12000}, "drive": _str(80), "priority": {"type": "number", "minimum": 0, "maximum": 1}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}, "risk": {"type": "number", "minimum": 0, "maximum": 1}, "novelty": {"type": "number", "minimum": 0, "maximum": 1}}, ["title", "objective"]), lambda title, objective, drive="completion", priority=.5, confidence=.7, risk=.15, novelty=.5: v5.cognition.create_intention(title, objective, drive=drive, priority=priority, confidence=confidence, risk=risk, novelty=novelty), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_cognition_resolve_intention", "Accept, complete, dismiss or fail one internal intention.", _schema({"intention_id": _str(100), "status": {"type": "string", "enum": ["accepted", "completed", "dismissed", "failed"]}}, ["intention_id", "status"]), lambda intention_id, status: v5.cognition.resolve_intention(intention_id, status), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_cognition_create_idea", "Create a novel idea brief by recombining associated concepts and memories.", _schema({"topic": {"type": "string", "minLength": 1, "maxLength": 12000}, "limit": {"type": "integer", "minimum": 2, "maximum": 12}}, ["topic"]), lambda topic, limit=6: v5.cognition.create_idea(topic, limit=limit), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_cognition_tick", "Run one bounded cognitive cycle now: inspect goals, consolidate learning and form intentions.", _schema(), lambda: v5.cognition.tick(), PermissionLevel.SAFE_ACTION))
'''
    replace_once(path, anchor, addition, sentinel='"v5_cognition_status"')


def write_new_files(root: Path) -> None:
    files = {
        "src/iras/v5/cognitive_core.py": PAYLOAD / "cognitive_core.py",
        "tests/test_v500_rc7_cognitive_core.py": PAYLOAD / "test_v500_rc7_cognitive_core.py",
        "docs/V5_0_RC7_COGNITIVE_CORE.md": PAYLOAD / "V5_0_RC7_COGNITIVE_CORE.md",
    }
    for relative, source in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply IRAS RC7 candidate cognitive core")
    parser.add_argument("--repo", default=".", help="IRAS repository root")
    parser.add_argument("--test", action="store_true", help="run targeted RC6 + RC7 tests")
    args = parser.parse_args()
    root = Path(args.repo).expanduser().resolve()
    required = [
        root / "src/iras/v5/runtime.py",
        root / "src/iras/tools/v5.py",
        root / "src/iras/v5/automation_engine.py",
    ]
    if not all(path.exists() for path in required):
        print("ERROR: RC7 requires the RC6 automation + wake voice update first.", file=sys.stderr)
        return 2
    runtime_text = (root / "src/iras/v5/runtime.py").read_text(encoding="utf-8")
    if "self.automations = AutomationEngine" not in runtime_text:
        print("ERROR: RC6 runtime marker not found. Apply RC6 first.", file=sys.stderr)
        return 3
    if "self.cognition = CognitiveCore" in runtime_text:
        print("IRAS RC7 cognitive core is already applied.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = root / ".iras_rc7_backup" / stamp
    for relative in ("src/iras/v5/runtime.py", "src/iras/tools/v5.py"):
        backup_file(root, backup, relative)

    try:
        patch_runtime(root)
        patch_tools(root)
        write_new_files(root)
    except Exception as exc:
        print(f"ERROR: RC7 patch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"Backups are in: {backup}", file=sys.stderr)
        return 4

    compile_targets = [
        "src/iras/v5/cognitive_core.py",
        "src/iras/v5/runtime.py",
        "src/iras/tools/v5.py",
        "tests/test_v500_rc7_cognitive_core.py",
    ]
    result = run([sys.executable, "-m", "py_compile", *compile_targets], root, check=False)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        print(f"ERROR: RC7 syntax validation failed. Backups are in: {backup}", file=sys.stderr)
        return result.returncode or 5

    if args.test:
        targets = ["tests/test_v500_rc7_cognitive_core.py"]
        if (root / "tests/test_v500_rc6_automation_voice.py").exists():
            targets.insert(0, "tests/test_v500_rc6_automation_voice.py")
        result = run([sys.executable, "-m", "pytest", *targets, "-q"], root, check=False)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode != 0:
            print(f"ERROR: targeted RC6/RC7 tests failed. Backups are in: {backup}", file=sys.stderr)
            return result.returncode

    print("IRAS RC7 cognitive core applied successfully.")
    print(f"Backup: {backup}")
    print("Next validation: .\\run-v500-validation.ps1")
    print("Cognition: continuous intentions + scalable associative memory + hybrid reasoning + fuzzy learning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
