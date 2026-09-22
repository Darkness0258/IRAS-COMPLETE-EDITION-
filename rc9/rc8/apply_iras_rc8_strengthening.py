from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

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
        "from .cognitive_core import CognitiveCore\n",
        "from .cognitive_core import CognitiveCore\nfrom .strengthening_core import RC8StrengtheningCore\n",
        sentinel="from .strengthening_core import RC8StrengtheningCore",
    )
    replace_once(
        path,
        "        self.cognition = CognitiveCore(self.db, self.bus)\n        self.cognition.bind_goal_provider(lambda: self.goals.next_actions(20))\n        self.migrations = MigrationManager(self.db)\n",
        "        self.cognition = CognitiveCore(self.db, self.bus)\n        self.cognition.bind_goal_provider(lambda: self.goals.next_actions(20))\n        self.strengthening = RC8StrengtheningCore(self.db, self.bus)\n        self.strengthening.context.bind_memory_provider(lambda query, limit: self.cognition.recall(query, limit=limit, hops=2))\n        self.strengthening.interop.bind_secret_resolver(self.vault.get)\n        self.migrations = MigrationManager(self.db)\n",
        sentinel="self.strengthening = RC8StrengtheningCore",
    )
    replace_once(
        path,
        '            "cognitive_core_running": self.cognition.running,\n            "monitors": len(self.monitoring.list()),\n',
        '            "cognitive_core_running": self.cognition.running,\n            "rc8_strengthening": self.strengthening.status(),\n            "monitors": len(self.monitoring.list()),\n',
        sentinel='"rc8_strengthening"',
    )


def patch_tools(root: Path) -> None:
    path = root / "src/iras/tools/v5.py"
    helper_anchor = "def _connector_permission(args: dict[str, Any]) -> PermissionLevel:\n"
    helper = '''def _rc8_context_ingest_permission(args: dict[str, Any]) -> PermissionLevel:
    return PermissionLevel.SYSTEM_ACTION if bool(args.get("trusted")) else PermissionLevel.SAFE_ACTION


def _rc8_mcp_permission(args: dict[str, Any]) -> PermissionLevel:
    return PermissionLevel.SYSTEM_ACTION if str(args.get("method") or "").strip() == "tools/call" else PermissionLevel.READ


'''
    replace_once(path, helper_anchor, helper + helper_anchor, sentinel="def _rc8_context_ingest_permission")

    anchor = '    add(Tool("v5_cognition_tick", "Run one bounded cognitive cycle now: inspect goals, consolidate learning and form intentions.", _schema(), lambda: v5.cognition.tick(), PermissionLevel.SAFE_ACTION))\n'
    block = anchor + '''

    # RC8 production strengthening ------------------------------------------------------------
    add(Tool("v5_rc8_status", "Inspect RC8 durability, context, eval, interoperability, webhook, provenance and trace status.", _schema(), lambda: v5.strengthening.status(), PermissionLevel.READ))

    # Durable execution / crash-resume checkpoints
    add(Tool("v5_rc8_durable_list", "List durable long-horizon execution journals.", _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 1000}}), lambda limit=100: v5.strengthening.durable.list(limit), PermissionLevel.READ))
    add(Tool("v5_rc8_durable_create", "Create an idempotent crash-resume execution journal. This does not itself grant tool authority.", _schema({"objective": {"type": "string", "minLength": 1, "maxLength": 12000}, "run_key": _str(200), "metadata": _obj()}, ["objective"]), lambda objective, run_key="", metadata=None: v5.strengthening.durable.create(objective, run_key=run_key, metadata=metadata or {}), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_rc8_durable_checkpoint", "Persist a durable execution checkpoint with an optional idempotency key.", _schema({"run_id": _str(100), "name": _str(240), "input_data": _obj(), "output": {}, "status": _str(40), "error": _str(4000), "idempotency_key": _str(240)}, ["run_id", "name"]), lambda run_id, name, input_data=None, output=None, status="succeeded", error="", idempotency_key="": v5.strengthening.durable.checkpoint(run_id, name, input_data=input_data or {}, output=output, status=status, error=error, idempotency_key=idempotency_key), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_rc8_durable_recovery", "Build a recovery plan from the last durable checkpoint without replaying side effects.", _schema({"run_id": _str(100)}, ["run_id"]), lambda run_id: v5.strengthening.durable.recovery_plan(run_id), PermissionLevel.READ))
    add(Tool("v5_rc8_durable_resume", "Resume a paused/waiting durable journal. Real actions remain behind their existing permission gates.", _schema({"run_id": _str(100)}, ["run_id"]), lambda run_id: v5.strengthening.durable.resume(run_id), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_rc8_durable_set_status", "Mark durable work running/paused/waiting/succeeded/failed/cancelled.", _schema({"run_id": _str(100), "status": {"type": "string", "enum": ["running", "paused", "waiting", "succeeded", "failed", "cancelled"]}, "result": {}, "error": _str(4000)}, ["run_id", "status"]), lambda run_id, status, result=None, error="": v5.strengthening.durable.set_status(run_id, status, result=result, error=error), PermissionLevel.SYSTEM_ACTION))

    # Provenance and context engineering
    add(Tool("v5_rc8_guard_inspect", "Inspect external text for provenance risk, prompt-injection indicators and taint.", _schema({"text": {"type": "string", "minLength": 1, "maxLength": 200000}, "source": _str(80), "trusted": {"type": "boolean"}}, ["text"]), lambda text, source="external", trusted=False: v5.strengthening.guard.inspect(text, source=source, trusted=trusted), PermissionLevel.READ))
    add(Tool("v5_rc8_guard_memory", "Check whether external text should be admitted to durable memory or quarantined.", _schema({"text": {"type": "string", "minLength": 1, "maxLength": 200000}, "source": _str(80), "trusted": {"type": "boolean"}}, ["text"]), lambda text, source="external", trusted=False: v5.strengthening.guard.memory_admission(text, source=source, trusted=trusted), PermissionLevel.READ))
    add(Tool("v5_rc8_guard_action", "Check whether a proposed high-impact action is semantically aligned with the current objective. Advisory only; normal permission gates remain final.", _schema({"objective": {"type": "string", "minLength": 1, "maxLength": 12000}, "action": _str(200), "arguments": _obj()}, ["objective", "action"]), lambda objective, action, arguments=None: v5.strengthening.guard.action_preflight(objective, action, arguments or {}), PermissionLevel.READ))
    add(Tool("v5_rc8_context_list", "List provenance-labelled context items.", _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 2000}, "include_quarantined": {"type": "boolean"}}), lambda limit=200, include_quarantined=True: v5.strengthening.context.list(limit, include_quarantined=include_quarantined), PermissionLevel.READ))
    add(Tool("v5_rc8_context_ingest", "Ingest context with explicit provenance/trust and automatic quarantine for suspicious external instructions.", _schema({"text": {"type": "string", "minLength": 1, "maxLength": 200000}, "source": _str(80), "priority": {"type": "number", "minimum": 0, "maximum": 1}, "trusted": {"type": "boolean"}, "provenance": _obj()}, ["text"]), lambda text, source="external", priority=.5, trusted=False, provenance=None: v5.strengthening.context.ingest(text, source=source, priority=priority, trusted=trusted, provenance=provenance or {}), PermissionLevel.SAFE_ACTION, permission_resolver=_rc8_context_ingest_permission))
    add(Tool("v5_rc8_context_compile", "Compile the most relevant, trusted context into a bounded token budget; quarantined items are excluded by default.", _schema({"query": {"type": "string", "minLength": 1, "maxLength": 12000}, "budget_tokens": {"type": "integer", "minimum": 256, "maximum": 200000}, "include_quarantined": {"type": "boolean"}, "memory_limit": {"type": "integer", "minimum": 1, "maximum": 50}}, ["query"]), lambda query, budget_tokens=6000, include_quarantined=False, memory_limit=12: v5.strengthening.context.compile(query, budget_tokens=budget_tokens, include_quarantined=include_quarantined, memory_limit=memory_limit), PermissionLevel.READ))

    # End-to-end evals and regression gates
    add(Tool("v5_rc8_eval_cases", "List deterministic end-to-end eval cases.", _schema({"suite": _str(120)}), lambda suite="": v5.strengthening.evals.cases(suite), PermissionLevel.READ))
    add(Tool("v5_rc8_eval_add", "Add a deterministic regression case for exact/contains/regex/json-subset/truthy evaluation.", _schema({"suite": _str(120), "name": _str(200), "evaluator": {"type": "string", "enum": ["exact", "contains", "regex", "json_subset", "truthy"]}, "expected": {}, "weight": {"type": "number", "minimum": 0.01, "maximum": 100}}, ["suite", "name", "evaluator"]), lambda suite, name, evaluator, expected=None, weight=1: v5.strengthening.evals.add_case(suite, name, evaluator=evaluator, expected=expected, weight=weight), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_rc8_eval_record", "Evaluate one candidate output against a stored regression case.", _schema({"case_id": _str(100), "actual": {}, "candidate": _str(160)}, ["case_id"]), lambda case_id, actual=None, candidate="current": v5.strengthening.evals.evaluate(case_id, actual, candidate=candidate), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_rc8_eval_summary", "Summarize latest scores for one eval suite/candidate.", _schema({"suite": _str(120), "candidate": _str(160)}, ["suite"]), lambda suite, candidate="current": v5.strengthening.evals.summary(suite, candidate=candidate), PermissionLevel.READ))
    add(Tool("v5_rc8_eval_gate", "Require a minimum regression score before promoting a candidate capability/model/workflow.", _schema({"suite": _str(120), "candidate": _str(160), "min_score": {"type": "number", "minimum": 0, "maximum": 1}, "require_all_evaluated": {"type": "boolean"}}, ["suite"]), lambda suite, candidate="current", min_score=.9, require_all_evaluated=True: v5.strengthening.evals.gate(suite, candidate=candidate, min_score=min_score, require_all_evaluated=require_all_evaluated), PermissionLevel.READ))

    # MCP 2026-07-28 + A2A v1.0 interoperability
    add(Tool("v5_rc8_interop_list", "List explicitly registered MCP/A2A endpoints. Credentials remain symbolic vault references.", _schema({"kind": {"type": "string", "enum": ["", "mcp", "a2a"]}}), lambda kind="": v5.strengthening.interop.list(kind), PermissionLevel.READ))
    add(Tool("v5_rc8_interop_register", "Register one fixed HTTPS MCP or A2A endpoint with an optional vault credential reference.", _schema({"kind": {"type": "string", "enum": ["mcp", "a2a"]}, "name": _str(160), "base_url": _str(2000), "auth_ref": _str(200), "metadata": _obj()}, ["kind", "name", "base_url"]), lambda kind, name, base_url, auth_ref="", metadata=None: v5.strengthening.interop.register(kind=kind, name=name, base_url=base_url, auth_ref=auth_ref, metadata=metadata or {}), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_rc8_mcp_call", "Call a bounded method on an explicitly registered MCP 2026-07-28 endpoint. tools/call is state-changing and receives stronger approval.", _schema({"endpoint_id": _str(100), "method": {"type": "string", "enum": ["server/discover", "tools/list", "tools/call", "resources/list", "resources/read", "prompts/list", "prompts/get"]}, "name": _str(240), "params": _obj(), "timeout": {"type": "number", "minimum": 2, "maximum": 60}}, ["endpoint_id", "method"]), lambda endpoint_id, method, name="", params=None, timeout=20: v5.strengthening.interop.mcp_call(endpoint_id, method=method, name=name, params=params or {}, timeout=timeout), PermissionLevel.READ, permission_resolver=_rc8_mcp_permission))
    add(Tool("v5_rc8_a2a_discover", "Fetch the public Agent Card from an explicitly registered A2A v1.0 endpoint.", _schema({"endpoint_id": _str(100), "timeout": {"type": "number", "minimum": 2, "maximum": 60}}, ["endpoint_id"]), lambda endpoint_id, timeout=20: v5.strengthening.interop.a2a_discover(endpoint_id, timeout=timeout), PermissionLevel.READ))
    add(Tool("v5_rc8_a2a_send", "Delegate text work to an explicitly registered A2A v1.0 agent. External delegation requires system-action approval.", _schema({"endpoint_id": _str(100), "text": {"type": "string", "minLength": 1, "maxLength": 12000}, "timeout": {"type": "number", "minimum": 2, "maximum": 180}}, ["endpoint_id", "text"]), lambda endpoint_id, text, timeout=60: v5.strengthening.interop.a2a_send(endpoint_id, text, timeout=timeout), PermissionLevel.SYSTEM_ACTION))

    # Secure anywhere/event ingress
    add(Tool("v5_rc8_webhook_list", "List secure automation webhook endpoints without revealing tokens.", _schema(), lambda: v5.strengthening.webhooks.list(), PermissionLevel.READ))
    add(Tool("v5_rc8_webhook_create", "Create a replay-protected webhook secret for remote event automation. The token is returned once.", _schema({"name": _str(160), "event_name": _str(160)}, ["name"]), lambda name, event_name="webhook.received": v5.strengthening.webhooks.create(name, event_name=event_name), PermissionLevel.CRITICAL))
    add(Tool("v5_rc8_webhook_rotate", "Rotate a webhook token; the replacement token is returned once.", _schema({"hook_id": _str(100)}, ["hook_id"]), lambda hook_id: v5.strengthening.webhooks.rotate(hook_id), PermissionLevel.CRITICAL))
    add(Tool("v5_rc8_webhook_disable", "Disable one external automation webhook.", _schema({"hook_id": _str(100)}, ["hook_id"]), lambda hook_id: v5.strengthening.webhooks.disable(hook_id), PermissionLevel.SYSTEM_ACTION))

    # Structured observability
    add(Tool("v5_rc8_trace_recent", "Read the structured RC8 event timeline.", _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 2000}}), lambda limit=200: v5.strengthening.traces.recent(limit), PermissionLevel.READ))
    add(Tool("v5_rc8_trace_summary", "Summarize recent event topics for debugging and agent evals.", _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 2000}}), lambda limit=1000: v5.strengthening.traces.summary(limit), PermissionLevel.READ))
'''
    replace_once(path, anchor, block, sentinel='"v5_rc8_status"')


def patch_cloud_api(root: Path) -> None:
    path = root / "src/iras/cloud_api.py"
    model_anchor = '''class TTSIn(BaseModel):
'''
    model = '''class AutomationWebhookIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


'''
    replace_once(path, model_anchor, model + model_anchor, sentinel="class AutomationWebhookIn")

    auth_anchor = '''def _device_authorized(
'''
    route = '''@app.post("/v1/automation-hooks/{hook_id}")
def receive_automation_hook(
    hook_id: str,
    body: AutomationWebhookIn,
    authorization: str | None = Header(default=None),
):
    raw = str(authorization or "").strip()
    token = raw[7:].strip() if raw.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Missing webhook bearer token.")
    try:
        return v5_runtime.strengthening.webhooks.receive(
            hook_id,
            token,
            event_id=body.event_id,
            payload=body.payload,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Webhook not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


'''
    replace_once(path, auth_anchor, route + auth_anchor, sentinel='@app.post("/v1/automation-hooks/{hook_id}")')


def write_files(root: Path) -> None:
    mapping = {
        "src/iras/v5/strengthening_core.py": PAYLOAD / "strengthening_core.py",
        "tests/test_v500_rc8_strengthening.py": PAYLOAD / "test_v500_rc8_strengthening.py",
        "docs/V5_0_RC8_STRENGTHENING.md": PAYLOAD / "V5_0_RC8_STRENGTHENING.md",
    }
    for relative, source in mapping.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply cumulative IRAS RC8 production strengthening overlay")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo).expanduser().resolve()
    required = [
        root / "src/iras/v5/runtime.py",
        root / "src/iras/tools/v5.py",
        root / "src/iras/cloud_api.py",
        root / "src/iras/v5/cognitive_core.py",
        root / "src/iras/v5/automation_engine.py",
    ]
    if not all(p.exists() for p in required):
        print("ERROR: RC8 requires cumulative RC6 + RC7 to be present first.", file=sys.stderr)
        return 2
    runtime_text = (root / "src/iras/v5/runtime.py").read_text(encoding="utf-8")
    if "self.strengthening = RC8StrengtheningCore" in runtime_text:
        print("IRAS RC8 strengthening overlay is already applied.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = root / ".iras_rc8_backup" / stamp
    for relative in ("src/iras/v5/runtime.py", "src/iras/tools/v5.py", "src/iras/cloud_api.py"):
        backup_file(root, backup, relative)

    try:
        patch_runtime(root)
        patch_tools(root)
        patch_cloud_api(root)
        write_files(root)
    except Exception as exc:
        print(f"ERROR: RC8 patch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"Backups are in: {backup}", file=sys.stderr)
        return 4

    compile_targets = [
        "src/iras/v5/strengthening_core.py",
        "src/iras/v5/runtime.py",
        "src/iras/tools/v5.py",
        "src/iras/cloud_api.py",
        "tests/test_v500_rc8_strengthening.py",
    ]
    result = run([sys.executable, "-m", "py_compile", *compile_targets], root, check=False)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        print(f"ERROR: RC8 syntax validation failed. Backups are in: {backup}", file=sys.stderr)
        return result.returncode or 5

    if args.test:
        targets = ["tests/test_v500_rc8_strengthening.py"]
        if (root / "tests/test_v500_rc7_cognitive_core.py").exists():
            targets.insert(0, "tests/test_v500_rc7_cognitive_core.py")
        if (root / "tests/test_v500_rc6_automation_voice.py").exists():
            targets.insert(0, "tests/test_v500_rc6_automation_voice.py")
        result = run([sys.executable, "-m", "pytest", *targets, "-q"], root, check=False)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode != 0:
            print(f"ERROR: targeted RC6/RC7/RC8 tests failed. Backups are in: {backup}", file=sys.stderr)
            return result.returncode

    print("IRAS RC8 strengthening overlay applied successfully.")
    print(f"Backup: {backup}")
    print("Next: .\\run-v500-validation.ps1")
    print("Added: durable checkpoints, context compiler, provenance guard, eval gates, MCP/A2A client interoperability, signed webhook ingress, structured traces.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
