from __future__ import annotations

import base64
import json
from urllib.parse import quote, urlsplit
from typing import Any

import httpx


class _BaseAdapter:
    def __init__(self, *, timeout: float = 20.0):
        self.timeout = max(2.0, min(float(timeout), 60.0))

    def _request(self, method: str, url: str, *, headers: dict[str, str] | None = None,
                 params: dict[str, Any] | None = None, json_body: Any = None,
                 content: bytes | None = None) -> Any:
        with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
            response = client.request(
                method, url, headers=headers, params=params, json=json_body, content=content
            )
            response.raise_for_status()
            if not response.content:
                return {"ok": True, "status": response.status_code}
            ctype = response.headers.get("content-type", "")
            if "json" in ctype:
                return response.json()
            return {"status": response.status_code, "text": response.text[:30000]}


class _BearerAdapter(_BaseAdapter):
    def __init__(self, token: str, **kwargs: Any):
        super().__init__(**kwargs)
        if not token:
            raise ValueError("Connector token is required.")
        self.token = token

    def _headers(self, **extra: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json", **extra}


class GmailAdapter(_BearerAdapter):
    BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

    def mail_read(self, query: str = "", max_results: int = 20) -> Any:
        return self._request(
            "GET", self.BASE + "/messages", headers=self._headers(),
            params={"q": query, "maxResults": max(1, min(int(max_results), 100))}
        )

    def mail_send(self, raw_rfc822_base64url: str) -> Any:
        if not raw_rfc822_base64url:
            raise ValueError("raw_rfc822_base64url is required.")
        return self._request(
            "POST", self.BASE + "/messages/send", headers=self._headers(),
            json_body={"raw": raw_rfc822_base64url}
        )


class CalendarAdapter(_BearerAdapter):
    BASE = "https://www.googleapis.com/calendar/v3/calendars"

    def calendar_read(self, calendar_id: str = "primary", time_min: str = "", time_max: str = "", max_results: int = 50) -> Any:
        params: dict[str, Any] = {
            "singleEvents": "true", "orderBy": "startTime",
            "maxResults": max(1, min(int(max_results), 250)),
        }
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        return self._request(
            "GET", f"{self.BASE}/{quote(calendar_id, safe='')}/events",
            headers=self._headers(), params=params
        )

    def calendar_write(self, event: dict[str, Any], calendar_id: str = "primary") -> Any:
        return self._request(
            "POST", f"{self.BASE}/{quote(calendar_id, safe='')}/events",
            headers=self._headers(), json_body=dict(event or {})
        )


class DriveAdapter(_BearerAdapter):
    def files_read(self, query: str = "", page_size: int = 50) -> Any:
        params: dict[str, Any] = {
            "pageSize": max(1, min(int(page_size), 100)),
            "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,size,webViewLink)",
        }
        if query:
            params["q"] = query
        return self._request(
            "GET", "https://www.googleapis.com/drive/v3/files",
            headers=self._headers(), params=params
        )

    def files_write(self, name: str, content_base64: str = "", mime_type: str = "text/plain") -> Any:
        if not name:
            raise ValueError("name is required.")
        metadata = json.dumps({"name": name}).encode("utf-8")
        data = base64.b64decode(content_base64) if content_base64 else b""
        boundary = "iras-drive-boundary"
        body = (
            b"--" + boundary.encode() + b"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            + metadata
            + b"\r\n--" + boundary.encode() + b"\r\nContent-Type: " + mime_type.encode("ascii", "ignore")
            + b"\r\n\r\n" + data + b"\r\n--" + boundary.encode() + b"--\r\n"
        )
        return self._request(
            "POST", "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers=self._headers(**{"Content-Type": f"multipart/related; boundary={boundary}"}),
            content=body,
        )


class GitHubAdapter(_BearerAdapter):
    BASE = "https://api.github.com"

    def _headers(self, **extra: str) -> dict[str, str]:
        return super()._headers(**{"X-GitHub-Api-Version": "2022-11-28", **extra})

    def repos_read(self, per_page: int = 30, visibility: str = "all") -> Any:
        return self._request(
            "GET", self.BASE + "/user/repos", headers=self._headers(),
            params={"per_page": max(1, min(int(per_page), 100)), "visibility": visibility}
        )

    def issues_write(self, owner: str, repo: str, title: str, body: str = "") -> Any:
        return self._request(
            "POST", f"{self.BASE}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/issues",
            headers=self._headers(), json_body={"title": title, "body": body}
        )

    def pulls_write(self, owner: str, repo: str, title: str, head: str, base: str, body: str = "") -> Any:
        return self._request(
            "POST", f"{self.BASE}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/pulls",
            headers=self._headers(), json_body={"title": title, "head": head, "base": base, "body": body}
        )


class SupabaseAdapter(_BaseAdapter):
    def __init__(self, url: str, key: str, **kwargs: Any):
        super().__init__(**kwargs)
        parsed = urlsplit(str(url or "").rstrip("/"))
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Supabase connector URL must be HTTPS.")
        self.base = str(url).rstrip("/") + "/rest/v1"
        self.key = key
        if not key:
            raise ValueError("Supabase key is required.")

    def _headers(self, **extra: str) -> dict[str, str]:
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Accept": "application/json", **extra}

    @staticmethod
    def _table(table: str) -> str:
        if not table or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in table):
            raise ValueError("Unsafe Supabase table name.")
        return table

    def database_read(self, table: str, select: str = "*", filters: dict[str, str] | None = None, limit: int = 100) -> Any:
        params: dict[str, Any] = {"select": select, "limit": max(1, min(int(limit), 1000))}
        for key, value in (filters or {}).items():
            if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in key):
                raise ValueError("Unsafe Supabase filter column.")
            params[key] = value
        return self._request("GET", f"{self.base}/{self._table(table)}", headers=self._headers(), params=params)

    def database_write(self, table: str, rows: list[dict[str, Any]] | dict[str, Any], upsert: bool = False) -> Any:
        headers = self._headers(**{"Content-Type": "application/json", "Prefer": "return=representation" + (",resolution=merge-duplicates" if upsert else "")})
        return self._request("POST", f"{self.base}/{self._table(table)}", headers=headers, json_body=rows)


class SlackAdapter(_BearerAdapter):
    BASE = "https://slack.com/api"

    def messages_read(self, channel: str, limit: int = 50) -> Any:
        return self._request("GET", self.BASE + "/conversations.history", headers=self._headers(), params={"channel": channel, "limit": max(1, min(int(limit), 100))})

    def messages_send(self, channel: str, text: str) -> Any:
        return self._request("POST", self.BASE + "/chat.postMessage", headers=self._headers(**{"Content-Type": "application/json"}), json_body={"channel": channel, "text": text})


class DiscordAdapter(_BearerAdapter):
    BASE = "https://discord.com/api/v10"

    def _headers(self, **extra: str) -> dict[str, str]:
        # Discord bot credentials are stored as the token value, never exposed.
        return {"Authorization": f"Bot {self.token}", "Accept": "application/json", **extra}

    def messages_read(self, channel_id: str, limit: int = 50) -> Any:
        return self._request("GET", f"{self.BASE}/channels/{quote(channel_id, safe='')}/messages", headers=self._headers(), params={"limit": max(1, min(int(limit), 100))})

    def messages_send(self, channel_id: str, content: str) -> Any:
        return self._request("POST", f"{self.BASE}/channels/{quote(channel_id, safe='')}/messages", headers=self._headers(**{"Content-Type": "application/json"}), json_body={"content": content})


class NotionAdapter(_BearerAdapter):
    BASE = "https://api.notion.com/v1"

    def _headers(self, **extra: str) -> dict[str, str]:
        return super()._headers(**{"Notion-Version": "2022-06-28", **extra})

    def pages_read(self, page_id: str) -> Any:
        return self._request("GET", f"{self.BASE}/pages/{quote(page_id, safe='')}", headers=self._headers())

    def pages_write(self, parent_page_id: str, properties: dict[str, Any], children: list[dict[str, Any]] | None = None) -> Any:
        body: dict[str, Any] = {"parent": {"page_id": parent_page_id}, "properties": properties}
        if children:
            body["children"] = children
        return self._request("POST", self.BASE + "/pages", headers=self._headers(**{"Content-Type": "application/json"}), json_body=body)


def build_builtin_adapter(connector_id: str, vault: Any, auth: dict[str, Any]) -> Any:
    refs = dict(auth.get("secret_refs") or {})

    def secret(name: str) -> str:
        ref = refs.get(name, name)
        return vault.get(ref)

    cid = str(connector_id)
    if cid == "gmail":
        return GmailAdapter(secret("gmail.oauth"))
    if cid == "calendar":
        return CalendarAdapter(secret("calendar.oauth"))
    if cid == "drive":
        return DriveAdapter(secret("drive.oauth"))
    if cid == "github":
        return GitHubAdapter(secret("github.token"))
    if cid == "supabase":
        return SupabaseAdapter(secret("supabase.url"), secret("supabase.key"))
    if cid == "slack":
        return SlackAdapter(secret("slack.oauth"))
    if cid == "discord":
        return DiscordAdapter(secret("discord.token"))
    if cid == "notion":
        return NotionAdapter(secret("notion.token"))
    raise KeyError(connector_id)
