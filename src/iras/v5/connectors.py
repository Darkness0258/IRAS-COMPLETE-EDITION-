from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from typing import Any

from .common import SQLiteDB, utc_now


@dataclass(frozen=True)
class ConnectorManifest:
    connector_id: str
    display_name: str
    capabilities: tuple[str, ...]
    required_secrets: tuple[str, ...] = ()
    read_only_default: bool = True


class FixtureConnectorAdapter:
    """Offline-safe adapter used by local acceptance tests and demos only."""

    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = dict(responses or {})
        self.calls: list[dict[str, Any]] = []

    def __getattr__(self, name: str):
        capability = name.replace("_", ".")
        def invoke(**kwargs: Any):
            self.calls.append({"capability": capability, "arguments": dict(kwargs)})
            value = self.responses.get(capability, {"ok": True, "capability": capability, "arguments": dict(kwargs)})
            return value(**kwargs) if callable(value) else value
        return invoke


class ConnectorRegistry:
    """First-class connector lifecycle with symbolic secrets and fail-closed auth.

    Adapters are injected at runtime. Authentication material is referenced only by
    vault names; secret values never appear in manifests, status payloads or prompts.
    A connector cannot be attached or invoked unless its persisted authorization is
    valid and its required symbolic credentials are present.
    """

    AUTH_STATES = {
        "disconnected", "configured", "authorizing", "authorized", "connected",
        "refreshing", "expired", "error", "revoked",
    }

    def __init__(self, db: SQLiteDB | None = None, vault: Any = None):
        self.manifests: dict[str, ConnectorManifest] = {}
        self.adapters: dict[str, Any] = {}
        self.db = db
        self.vault = vault
        for manifest in self.builtin_manifests():
            self.register_manifest(manifest)
        if self.db:
            self.db.execute("""CREATE TABLE IF NOT EXISTS v5_connector_auth(
                connector_id TEXT PRIMARY KEY,state TEXT NOT NULL,account_label TEXT,
                scopes_json TEXT NOT NULL,secret_refs_json TEXT NOT NULL,expires_at TEXT,
                refreshed_at TEXT,last_error TEXT,updated_at TEXT NOT NULL)""")

    @staticmethod
    def builtin_manifests() -> list[ConnectorManifest]:
        return [
            ConnectorManifest("gmail", "Gmail", ("mail.read", "mail.send"), ("gmail.oauth",)),
            ConnectorManifest("calendar", "Calendar", ("calendar.read", "calendar.write"), ("calendar.oauth",)),
            ConnectorManifest("drive", "Drive", ("files.read", "files.write"), ("drive.oauth",)),
            ConnectorManifest("github", "GitHub", ("repos.read", "issues.write", "pulls.write"), ("github.token",)),
            ConnectorManifest("supabase", "Supabase", ("database.read", "database.write"), ("supabase.url", "supabase.key")),
            ConnectorManifest("discord", "Discord", ("messages.read", "messages.send"), ("discord.token",)),
            ConnectorManifest("slack", "Slack", ("messages.read", "messages.send"), ("slack.oauth",)),
            ConnectorManifest("notion", "Notion", ("pages.read", "pages.write"), ("notion.token",)),
        ]

    def register_manifest(self, manifest: ConnectorManifest) -> None:
        self.manifests[manifest.connector_id] = manifest

    @staticmethod
    def _expired(expires_at: str | None) -> bool:
        raw = str(expires_at or "").strip()
        if not raw:
            return False
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt <= datetime.now(timezone.utc)
        except ValueError:
            return True

    def configure(
        self,
        connector_id: str,
        *,
        secret_refs: dict[str, str] | None = None,
        scopes: list[str] | None = None,
        account_label: str = "",
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        self.set_auth_state(
            connector_id,
            state="configured",
            account_label=account_label,
            scopes=scopes,
            secret_refs=secret_refs,
            expires_at=expires_at,
        )
        return self.status(connector_id)

    def authorize(
        self,
        connector_id: str,
        *,
        scopes: list[str] | None = None,
        account_label: str = "",
        secret_refs: dict[str, str] | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        current = self.auth_state(connector_id)
        refs = dict(secret_refs if secret_refs is not None else current.get("secret_refs") or {})
        self._validate_refs(connector_id, refs)
        missing = self.credential_readiness(connector_id, refs=refs)["missing"]
        if missing:
            raise RuntimeError("Connector credentials are not ready: " + ", ".join(missing))
        if self._expired(expires_at):
            self.set_auth_state(
                connector_id, state="expired", account_label=account_label or current.get("account_label", ""),
                scopes=scopes if scopes is not None else current.get("scopes", []), secret_refs=refs,
                expires_at=expires_at, last_error="Credential expiry is in the past.",
            )
            raise PermissionError("Connector authorization is expired.")
        self.set_auth_state(
            connector_id,
            state="authorized",
            account_label=account_label or current.get("account_label", ""),
            scopes=scopes if scopes is not None else current.get("scopes", []),
            secret_refs=refs,
            expires_at=expires_at if expires_at is not None else current.get("expires_at"),
        )
        return self.status(connector_id)

    def attach(self, connector_id: str, adapter: Any) -> None:
        if connector_id not in self.manifests:
            raise KeyError(connector_id)
        self._assert_authorized(connector_id)
        self.adapters[connector_id] = adapter
        current = self.auth_state(connector_id)
        self.set_auth_state(
            connector_id,
            state="connected",
            account_label=current.get("account_label", ""),
            scopes=current.get("scopes", []),
            secret_refs=current.get("secret_refs", {}),
            expires_at=current.get("expires_at"),
        )

    def connect_builtin(self, connector_id: str) -> dict[str, Any]:
        self._assert_authorized(connector_id)
        if self.vault is None:
            raise RuntimeError("A secret vault is required for built-in connectors.")
        from .connector_adapters import build_builtin_adapter
        adapter = build_builtin_adapter(connector_id, self.vault, self.auth_state(connector_id))
        self.attach(connector_id, adapter)
        return self.status(connector_id)

    def detach(self, connector_id: str) -> None:
        self.adapters.pop(connector_id, None)
        current = self.auth_state(connector_id)
        next_state = "authorized" if current.get("state") in {"connected", "authorized"} and not self._expired(current.get("expires_at")) else "disconnected"
        self.set_auth_state(
            connector_id,
            state=next_state,
            account_label=current.get("account_label", ""),
            scopes=current.get("scopes", []),
            secret_refs=current.get("secret_refs", {}),
            expires_at=current.get("expires_at"),
            last_error=current.get("last_error", ""),
        )

    def _validate_refs(self, connector_id: str, refs: dict[str, str]) -> None:
        manifest = self.manifests[connector_id]
        allowed = set(manifest.required_secrets)
        if any(str(v) not in allowed for v in refs.values()):
            raise ValueError("Connector secret references must name declared symbolic secrets.")

    def set_auth_state(
        self,
        connector_id: str,
        *,
        state: str,
        account_label: str = "",
        scopes: list[str] | None = None,
        secret_refs: dict[str, str] | None = None,
        expires_at: str | None = None,
        last_error: str = "",
    ) -> None:
        if connector_id not in self.manifests:
            raise KeyError(connector_id)
        state = str(state or "").strip().lower()
        if state not in self.AUTH_STATES:
            raise ValueError(f"Unsupported connector authorization state: {state}")
        if not self.db:
            return
        refs = dict(secret_refs or {})
        self._validate_refs(connector_id, refs)
        self.db.execute(
            """INSERT INTO v5_connector_auth(connector_id,state,account_label,scopes_json,secret_refs_json,expires_at,refreshed_at,last_error,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(connector_id) DO UPDATE SET
            state=excluded.state,account_label=excluded.account_label,scopes_json=excluded.scopes_json,
            secret_refs_json=excluded.secret_refs_json,expires_at=excluded.expires_at,refreshed_at=excluded.refreshed_at,
            last_error=excluded.last_error,updated_at=excluded.updated_at""",
            (
                connector_id, state, account_label[:240], json.dumps(scopes or []), json.dumps(refs),
                expires_at, utc_now(), last_error[:2000], utc_now(),
            ),
        )

    def auth_state(self, connector_id: str) -> dict[str, Any]:
        if connector_id not in self.manifests:
            raise KeyError(connector_id)
        row = self.db.execute("SELECT * FROM v5_connector_auth WHERE connector_id=?", (connector_id,), fetch="one") if self.db else None
        if not row:
            return {
                "state": "connected" if connector_id in self.adapters else "disconnected",
                "account_label": "", "scopes": [], "secret_refs": {}, "expires_at": None, "last_error": "",
            }
        row["scopes"] = json.loads(row.pop("scopes_json") or "[]")
        row["secret_refs"] = json.loads(row.pop("secret_refs_json") or "{}")
        if self._expired(row.get("expires_at")) and row.get("state") in {"authorized", "connected", "refreshing"}:
            row["state"] = "expired"
        return row

    def credential_readiness(self, connector_id: str, *, refs: dict[str, str] | None = None) -> dict[str, Any]:
        manifest = self.manifests[connector_id]
        configured = dict(refs if refs is not None else self.auth_state(connector_id).get("secret_refs") or {})
        # Built-ins use their declared symbolic vault names by default. An
        # explicit mapping may rename argument slots, but raw secret values are
        # never stored in connector state.
        configured_names = set(configured.values()) if configured else set(manifest.required_secrets)
        present_names = set(self.vault.list()) if self.vault is not None else set()
        present, missing = [], []
        for name in manifest.required_secrets:
            if name in configured_names and name in present_names:
                present.append(name)
            else:
                missing.append(name)
        return {"present": present, "missing": missing, "ready": not missing}

    def _assert_authorized(self, connector_id: str) -> dict[str, Any]:
        auth = self.auth_state(connector_id)
        if self._expired(auth.get("expires_at")):
            if self.db:
                self.set_auth_state(
                    connector_id, state="expired", account_label=auth.get("account_label", ""),
                    scopes=auth.get("scopes", []), secret_refs=auth.get("secret_refs", {}),
                    expires_at=auth.get("expires_at"), last_error="Authorization expired.",
                )
            raise PermissionError(f"Connector authorization expired: {connector_id}")
        if auth.get("state") not in {"authorized", "connected"}:
            raise PermissionError(f"Connector is not authorized: {connector_id}")
        readiness = self.credential_readiness(connector_id)
        if not readiness["ready"]:
            raise RuntimeError("Connector credentials are not ready: " + ", ".join(readiness["missing"]))
        return auth

    def status(self, connector_id: str) -> dict[str, Any]:
        manifest = self.manifests[connector_id]
        auth = self.auth_state(connector_id)
        return {
            **asdict(manifest),
            "connected": connector_id in self.adapters,
            "authorization": auth,
            "credentials": self.credential_readiness(connector_id),
        }

    def list(self) -> list[dict[str, Any]]:
        return [self.status(m.connector_id) for m in self.manifests.values()]

    def invoke(self, connector_id: str, capability: str, **kwargs: Any) -> Any:
        manifest = self.manifests.get(connector_id)
        if not manifest:
            raise KeyError(connector_id)
        if capability not in manifest.capabilities:
            raise PermissionError(f"Connector capability not declared: {capability}")
        self._assert_authorized(connector_id)
        adapter = self.adapters.get(connector_id)
        if adapter is None:
            raise RuntimeError(f"Connector is not connected: {connector_id}")
        fn = getattr(adapter, capability.replace(".", "_"), None)
        if not callable(fn):
            raise RuntimeError(f"Adapter does not implement {capability}")
        return fn(**kwargs)
