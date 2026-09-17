from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable


@dataclass(frozen=True)
class ConnectorManifest:
    connector_id: str
    display_name: str
    capabilities: tuple[str, ...]
    required_secrets: tuple[str, ...] = ()
    read_only_default: bool = True


class ConnectorRegistry:
    """First-class service connector registry.

    Adapters are injected at runtime; secrets are referenced by symbolic vault
    names and are never embedded in manifests or prompts.
    """

    def __init__(self):
        self.manifests: dict[str, ConnectorManifest] = {}
        self.adapters: dict[str, Any] = {}
        for manifest in self.builtin_manifests():
            self.register_manifest(manifest)

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

    def attach(self, connector_id: str, adapter: Any) -> None:
        if connector_id not in self.manifests:
            raise KeyError(connector_id)
        self.adapters[connector_id] = adapter

    def list(self) -> list[dict[str, Any]]:
        return [{**asdict(m), "connected": m.connector_id in self.adapters} for m in self.manifests.values()]

    def invoke(self, connector_id: str, capability: str, **kwargs: Any) -> Any:
        manifest = self.manifests.get(connector_id)
        if not manifest:
            raise KeyError(connector_id)
        if capability not in manifest.capabilities:
            raise PermissionError(f"Connector capability not declared: {capability}")
        adapter = self.adapters.get(connector_id)
        if adapter is None:
            raise RuntimeError(f"Connector is not connected: {connector_id}")
        fn = getattr(adapter, capability.replace(".", "_"), None)
        if not callable(fn):
            raise RuntimeError(f"Adapter does not implement {capability}")
        return fn(**kwargs)
