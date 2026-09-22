from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlsplit
import hashlib
import ipaddress
import json
import os
import re
import socket
import threading
import time


def _env_bool(name: str, default: bool) -> bool:
    return str(os.getenv(name, str(default))).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(high, value))


_WEB_SYSTEM_ACTIONS = {
    "click_text", "click_role", "click_selector", "fill_label", "fill_placeholder",
    "fill_selector", "select_label", "check_label", "press", "upload",
    "download_selector", "download_text",
}
_WEB_CRITICAL_ACTIONS = {"submit"}
_HIGH_IMPACT_TARGET = re.compile(
    r"\b(?:buy|purchase|checkout|place[- _]?order|pay|transfer|wire|send[- _]?money|"
    r"delete|remove[- _]?account|close[- _]?account|publish|post|send|submit|"
    r"change[- _]?password|reset[- _]?password|grant|authorize|confirm[- _]?order|subscribe)\b",
    re.I,
)


def web_action_risk(steps: list[dict[str, Any]] | dict[str, Any]) -> str:
    """Classify a bounded web action plan for ToolRegistry permission resolution."""
    rows = steps if isinstance(steps, list) else [steps]
    level = "read"
    for row in rows:
        if not isinstance(row, dict):
            return "critical"
        action = str(row.get("action") or "").strip().lower()
        if action in _WEB_CRITICAL_ACTIONS:
            return "critical"
        if action in {"click_text", "click_role", "click_selector"}:
            target = " ".join(str(row.get(k) or "") for k in ("text", "name", "selector"))
            if _HIGH_IMPACT_TARGET.search(target):
                return "critical"
        if action == "press" and str(row.get("key") or "").strip().lower() in {"enter", "numpadenter"}:
            return "critical"
        if action in _WEB_SYSTEM_ACTIONS:
            level = "system"
    return level


@dataclass(slots=True)
class WebDownload:
    path: str
    filename: str
    size: int
    sha256: str
    source_url: str
    created_at: float


class FullWebAccess:
    """Persistent, permissioned Playwright operator for the authorized public web.

    This class intentionally separates *reach* from *authority*: it can browse the
    public web broadly and maintain an IRAS-owned signed-in browser profile, but the
    ToolRegistry still decides whether an interaction is READ, SYSTEM_ACTION, or
    CRITICAL. Private/local address space remains closed unless the owner explicitly
    opts in with IRAS_WEB_ALLOW_PRIVATE/IRAS_WEB_ALLOW_LOCALHOST.
    """

    SEARCH_ENGINES = {
        "bing": "https://www.bing.com/search?q={query}",
        "google": "https://www.google.com/search?q={query}",
        "duckduckgo": "https://duckduckgo.com/?q={query}",
    }

    CHALLENGE_PATTERNS = {
        "captcha": (
            "captcha",
            "verify you are human",
            "i am human",
            "human verification",
        ),
        "mfa": (
            "two-factor authentication",
            "two factor authentication",
            "verification code",
            "authentication code",
            "security code",
            "one-time code",
            "one time code",
        ),
        "anti_bot": (
            "checking your browser",
            "cloudflare ray id",
            "unusual traffic",
            "automated queries",
        ),
    }

    def __init__(self, state_dir: str | Path, *, bus: Any = None):
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.profile_root = self.state_dir / "profiles"
        self.download_dir = self.state_dir / "downloads"
        self.screenshot_dir = self.state_dir / "screenshots"
        for directory in (self.profile_root, self.download_dir, self.screenshot_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self.policy_path = self.state_dir / "policy.json"
        self.download_log = self.state_dir / "downloads.jsonl"
        self.bus = bus
        self._pw = None
        self._context = None
        self._profile = "owner"
        self._headless = True
        self._tabs: dict[str, Any] = {}
        self._page_ids: dict[int, str] = {}
        self._counter = 0
        self._lock = threading.RLock()
        self._policy = self._load_policy()

    @property
    def available(self) -> bool:
        try:
            import playwright.sync_api  # noqa: F401
            return True
        except Exception:
            return False

    @property
    def running(self) -> bool:
        return self._context is not None

    def _load_policy(self) -> dict[str, Any]:
        default = {"domain_rules": {}}
        if not self.policy_path.exists():
            return default
        try:
            data = json.loads(self.policy_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return default
            rules = data.get("domain_rules")
            data["domain_rules"] = rules if isinstance(rules, dict) else {}
            return data
        except Exception:
            return default

    def _save_policy(self) -> None:
        tmp = self.policy_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._policy, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.policy_path)

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        value = str(domain or "").strip().lower().rstrip(".")
        value = re.sub(r"^https?://", "", value).split("/", 1)[0]
        if ":" in value and not value.startswith("["):
            value = value.split(":", 1)[0]
        if not value or len(value) > 253:
            raise ValueError("A valid domain is required.")
        return value

    def set_domain_rule(self, domain: str, rule: str) -> dict[str, str]:
        domain = self._normalize_domain(domain)
        rule = str(rule or "").strip().lower()
        if rule not in {"allow", "deny", "inherit"}:
            raise ValueError("Domain rule must be allow, deny, or inherit.")
        rules = self._policy.setdefault("domain_rules", {})
        if rule == "inherit":
            rules.pop(domain, None)
        else:
            rules[domain] = rule
        self._save_policy()
        return {"domain": domain, "rule": rule}

    def domain_rules(self) -> dict[str, str]:
        return dict(self._policy.get("domain_rules") or {})

    def _domain_rule(self, host: str) -> str:
        host = str(host or "").lower().rstrip(".")
        best = "inherit"
        best_len = -1
        for domain, rule in self.domain_rules().items():
            if host == domain or host.endswith("." + domain):
                if len(domain) > best_len:
                    best = str(rule)
                    best_len = len(domain)
        return best

    @staticmethod
    def _unsafe_ip(ip: ipaddress._BaseAddress) -> bool:
        return bool(
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )

    def _host_addresses(self, host: str) -> list[ipaddress._BaseAddress]:
        try:
            return [ipaddress.ip_address(host)]
        except ValueError:
            pass
        try:
            rows = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError(f"Could not resolve web host: {host}") from exc
        out: list[ipaddress._BaseAddress] = []
        for row in rows:
            raw = row[4][0]
            try:
                ip = ipaddress.ip_address(raw)
            except ValueError:
                continue
            if ip not in out:
                out.append(ip)
        if not out:
            raise ValueError(f"Could not resolve web host: {host}")
        return out

    def validate_url(self, url: str) -> str:
        candidate = str(url or "").strip()
        if not candidate:
            raise ValueError("Web URL is required.")
        if "://" not in candidate:
            candidate = "https://" + candidate
        try:
            parsed = urlsplit(candidate)
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("Web URL is invalid.") from exc
        scheme = parsed.scheme.lower()
        if scheme not in {"https", "http"}:
            raise ValueError("Only public HTTP(S) web navigation is supported.")
        if scheme == "http" and not _env_bool("IRAS_WEB_ALLOW_HTTP", True):
            raise ValueError("Plain HTTP is disabled by IRAS_WEB_ALLOW_HTTP.")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("URLs must not contain embedded credentials.")
        host = (parsed.hostname or "").strip().lower()
        if not host:
            raise ValueError("Web URL must include a host.")

        rule = self._domain_rule(host)
        if rule == "deny":
            raise PermissionError(f"Web domain is denied by owner policy: {host}")

        is_localhost = host in {"localhost", "localhost.localdomain", "127.0.0.1", "::1"}
        if is_localhost:
            if not _env_bool("IRAS_WEB_ALLOW_LOCALHOST", True):
                raise PermissionError("Localhost browsing is disabled.")
            return candidate

        if not _env_bool("IRAS_WEB_ALLOW_PRIVATE", False):
            for ip in self._host_addresses(host):
                if self._unsafe_ip(ip):
                    raise PermissionError(
                        f"Private/local/reserved web target is blocked: {host} -> {ip}"
                    )
        return candidate

    def _publish(self, topic: str, **payload: Any) -> None:
        if self.bus is not None:
            try:
                self.bus.publish(topic, **payload)
            except Exception:
                pass

    def _route_request(self, route: Any, request: Any) -> None:
        """Block obvious local/private or owner-denied requests, including subresources.

        Full DNS validation is performed for top-level navigation. For every subresource
        we additionally block direct private IPs, localhost, embedded credentials and
        explicit owner deny-rules without resolving every CDN hostname.
        """
        try:
            parsed = urlsplit(str(request.url or ""))
            scheme = parsed.scheme.lower()
            if scheme in {"data", "blob", "about"}:
                route.continue_()
                return
            if scheme not in {"http", "https"}:
                route.abort()
                return
            if parsed.username is not None or parsed.password is not None:
                route.abort()
                return
            host = (parsed.hostname or "").lower()
            if not host or self._domain_rule(host) == "deny":
                route.abort()
                return
            if host in {"localhost", "localhost.localdomain", "127.0.0.1", "::1"}:
                if not _env_bool("IRAS_WEB_ALLOW_LOCALHOST", True):
                    route.abort()
                    return
            else:
                try:
                    ip = ipaddress.ip_address(host)
                except ValueError:
                    ip = None
                if ip is not None and self._unsafe_ip(ip) and not _env_bool("IRAS_WEB_ALLOW_PRIVATE", False):
                    route.abort()
                    return
            route.continue_()
        except Exception:
            route.abort()

    def start(self, *, headless: bool | None = None, profile: str = "owner") -> dict[str, Any]:
        with self._lock:
            if self._context is not None:
                return self.status()
            if not self.available:
                raise RuntimeError(
                    "Playwright is unavailable. Install browser support and run: playwright install chromium"
                )
            from playwright.sync_api import sync_playwright

            profile = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(profile or "owner"))[:80] or "owner"
            headless = _env_bool("IRAS_WEB_HEADLESS", True) if headless is None else bool(headless)
            self._profile = profile
            self._headless = headless
            self._pw = sync_playwright().start()
            kwargs: dict[str, Any] = {
                "user_data_dir": str(self.profile_root / profile),
                "headless": headless,
                "accept_downloads": True,
                "viewport": {"width": 1440, "height": 960},
            }
            channel = str(os.getenv("IRAS_WEB_BROWSER_CHANNEL", "")).strip()
            if channel:
                kwargs["channel"] = channel
            self._context = self._pw.chromium.launch_persistent_context(**kwargs)
            self._context.route("**/*", self._route_request)
            self._context.set_default_timeout(_env_int("IRAS_WEB_ACTION_TIMEOUT_MS", 20000, 1000, 120000))
            self._context.set_default_navigation_timeout(_env_int("IRAS_WEB_NAV_TIMEOUT_MS", 45000, 3000, 180000))
            self._context.on("page", self._register_page)
            for page in list(self._context.pages):
                self._register_page(page)
            if not self._tabs:
                self._register_page(self._context.new_page())
            self._publish("web.started", profile=profile, headless=headless)
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._context is not None:
                try:
                    self._context.close()
                except Exception:
                    pass
            if self._pw is not None:
                try:
                    self._pw.stop()
                except Exception:
                    pass
            self._context = self._pw = None
            self._tabs.clear()
            self._page_ids.clear()
            self._publish("web.stopped", profile=self._profile)
            return {"stopped": True}

    def _ensure(self) -> None:
        if self._context is None:
            self.start(profile=os.getenv("IRAS_WEB_PROFILE", "owner"))

    def _register_page(self, page: Any) -> str:
        key = id(page)
        existing = self._page_ids.get(key)
        if existing:
            return existing
        self._counter += 1
        tab_id = f"web-{self._counter}"
        self._tabs[tab_id] = page
        self._page_ids[key] = tab_id
        return tab_id

    def _refresh_tabs(self) -> None:
        if self._context is None:
            return
        live = set(id(p) for p in self._context.pages if not p.is_closed())
        for tab_id, page in list(self._tabs.items()):
            if id(page) not in live or page.is_closed():
                self._tabs.pop(tab_id, None)
                self._page_ids.pop(id(page), None)
        for page in self._context.pages:
            if not page.is_closed():
                self._register_page(page)

    def _page(self, tab_id: str | None = None):
        self._ensure()
        self._refresh_tabs()
        if tab_id:
            page = self._tabs.get(str(tab_id))
            if page is None:
                raise KeyError(f"Unknown web tab: {tab_id}")
            return page
        if self._tabs:
            return list(self._tabs.values())[-1]
        return self.new_tab()[1]

    def status(self) -> dict[str, Any]:
        self._refresh_tabs()
        return {
            "available": self.available,
            "running": self.running,
            "profile": self._profile,
            "headless": self._headless,
            "tab_count": len(self._tabs),
            "download_count": len(self.downloads(limit=10000)),
            "public_http_enabled": _env_bool("IRAS_WEB_ALLOW_HTTP", True),
            "private_network_enabled": _env_bool("IRAS_WEB_ALLOW_PRIVATE", False),
            "localhost_enabled": _env_bool("IRAS_WEB_ALLOW_LOCALHOST", True),
            "max_download_mb": _env_int("IRAS_WEB_MAX_DOWNLOAD_MB", 1024, 1, 16384),
            "domain_rules": self.domain_rules(),
            "authority": "ToolRegistry / Remote / Master Control remain final",
        }

    def new_tab(self, url: str = "") -> tuple[str, Any]:
        self._ensure()
        page = self._context.new_page()
        tab_id = self._register_page(page)
        if url:
            self.navigate(url, tab_id=tab_id)
        return tab_id, page

    def tabs(self) -> list[dict[str, Any]]:
        self._ensure()
        self._refresh_tabs()
        out = []
        for tab_id, page in self._tabs.items():
            out.append({
                "tab_id": tab_id,
                "url": page.url,
                "title": self._safe_title(page),
                "active": page is list(self._tabs.values())[-1],
            })
        return out

    def switch_tab(self, tab_id: str) -> dict[str, Any]:
        page = self._page(tab_id)
        page.bring_to_front()
        # Reinsert so default-page selection follows the newly active tab.
        self._tabs.pop(tab_id, None)
        self._tabs[tab_id] = page
        return {"tab_id": tab_id, "url": page.url, "title": self._safe_title(page)}

    def close_tab(self, tab_id: str) -> dict[str, Any]:
        page = self._page(tab_id)
        page.close()
        self._tabs.pop(tab_id, None)
        self._page_ids.pop(id(page), None)
        return {"closed": tab_id}

    @staticmethod
    def _safe_title(page: Any) -> str:
        try:
            return str(page.title())[:1000]
        except Exception:
            return ""

    def navigate(self, url: str, *, tab_id: str | None = None, wait: str = "domcontentloaded", timeout_ms: int | None = None) -> dict[str, Any]:
        url = self.validate_url(url)
        page = self._page(tab_id)
        timeout = timeout_ms or _env_int("IRAS_WEB_NAV_TIMEOUT_MS", 45000, 3000, 180000)
        response = page.goto(url, wait_until=wait, timeout=timeout)
        result = {
            "ok": True,
            "url": page.url,
            "title": self._safe_title(page),
            "status": getattr(response, "status", None),
            "challenge": self.challenge(tab_id=tab_id),
        }
        self._publish("web.navigated", url=page.url, title=result["title"])
        return result

    def search(self, query: str, *, engine: str = "", tab_id: str | None = None) -> dict[str, Any]:
        query = str(query or "").strip()
        if not query:
            raise ValueError("Search query is required.")
        engine = str(engine or os.getenv("IRAS_WEB_DEFAULT_SEARCH", "bing")).strip().lower()
        template = self.SEARCH_ENGINES.get(engine)
        if template is None:
            raise ValueError(f"Unsupported search engine: {engine}")
        result = self.navigate(template.format(query=quote_plus(query)), tab_id=tab_id)
        result.update({"query": query, "engine": engine})
        return result

    def extract(self, selector: str = "body", *, tab_id: str | None = None, limit: int = 60000) -> dict[str, Any]:
        page = self._page(tab_id)
        limit = max(1, min(int(limit), 200000))
        text = page.locator(selector or "body").first.inner_text()[:limit]
        return {"url": page.url, "selector": selector or "body", "text": text}

    def snapshot(self, *, tab_id: str | None = None, text_limit: int = 40000, item_limit: int = 120) -> dict[str, Any]:
        page = self._page(tab_id)
        text_limit = max(1000, min(int(text_limit), 100000))
        item_limit = max(10, min(int(item_limit), 400))
        script = """
        (itemLimit) => {
          const clean = v => String(v || '').replace(/\\s+/g, ' ').trim().slice(0, 500);
          const visible = el => {
            const s = getComputedStyle(el); const r = el.getBoundingClientRect();
            return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0;
          };
          const links = [...document.querySelectorAll('a[href]')].filter(visible).slice(0,itemLimit).map((a,i)=>({
            index:i,text:clean(a.innerText||a.getAttribute('aria-label')),href:a.href
          }));
          const buttons = [...document.querySelectorAll('button,[role="button"],input[type="submit"],input[type="button"]')].filter(visible).slice(0,itemLimit).map((b,i)=>({
            index:i,text:clean(b.innerText||b.value||b.getAttribute('aria-label')),type:b.getAttribute('type')||'',disabled:!!b.disabled
          }));
          const fields = [...document.querySelectorAll('input,textarea,select')].filter(visible).slice(0,itemLimit).map((f,i)=>({
            index:i,tag:f.tagName.toLowerCase(),type:(f.getAttribute('type')||'').toLowerCase(),name:clean(f.getAttribute('name')),label:clean(f.getAttribute('aria-label')),placeholder:clean(f.getAttribute('placeholder')),disabled:!!f.disabled,checked:!!f.checked
          }));
          const forms = [...document.querySelectorAll('form')].slice(0,Math.min(itemLimit,50)).map((f,i)=>({
            index:i,action:f.action||'',method:(f.method||'get').toLowerCase(),text:clean(f.innerText).slice(0,700)
          }));
          return {links,buttons,fields,forms};
        }
        """
        structure = page.evaluate(script, item_limit)
        body = page.locator("body").inner_text()[:text_limit]
        return {
            "url": page.url,
            "title": self._safe_title(page),
            "text": body,
            "links": structure.get("links", []),
            "buttons": structure.get("buttons", []),
            "fields": structure.get("fields", []),
            "forms": structure.get("forms", []),
            "challenge": self.challenge(tab_id=tab_id),
        }

    def session_status(self) -> dict[str, Any]:
        self._ensure()
        cookies = self._context.cookies()
        domains: dict[str, int] = {}
        for cookie in cookies:
            domain = str(cookie.get("domain") or "").lstrip(".")
            if domain:
                domains[domain] = domains.get(domain, 0) + 1
        return {
            "profile": self._profile,
            "persistent": True,
            "cookie_domain_counts": dict(sorted(domains.items())),
            "cookie_values_exposed": False,
        }

    def click_selector(self, selector: str, *, tab_id: str | None = None) -> dict[str, Any]:
        page = self._page(tab_id)
        page.locator(selector).first.click()
        self._refresh_tabs()
        return {"clicked": selector, "url": page.url}

    def click_text(self, text: str, *, exact: bool = False, tab_id: str | None = None) -> dict[str, Any]:
        page = self._page(tab_id)
        page.get_by_text(str(text), exact=bool(exact)).first.click()
        self._refresh_tabs()
        return {"clicked_text": str(text), "url": page.url}

    def click_role(self, role: str, name: str, *, exact: bool = False, tab_id: str | None = None) -> dict[str, Any]:
        page = self._page(tab_id)
        page.get_by_role(str(role), name=str(name), exact=bool(exact)).first.click()
        self._refresh_tabs()
        return {"clicked_role": str(role), "name": str(name), "url": page.url}

    def fill_selector(self, selector: str, value: str, *, tab_id: str | None = None) -> dict[str, Any]:
        self._page(tab_id).locator(selector).first.fill(str(value))
        return {"filled": selector}

    def fill_label(self, label: str, value: str, *, exact: bool = False, tab_id: str | None = None) -> dict[str, Any]:
        self._page(tab_id).get_by_label(str(label), exact=bool(exact)).first.fill(str(value))
        return {"filled_label": str(label)}

    def fill_placeholder(self, placeholder: str, value: str, *, exact: bool = False, tab_id: str | None = None) -> dict[str, Any]:
        self._page(tab_id).get_by_placeholder(str(placeholder), exact=bool(exact)).first.fill(str(value))
        return {"filled_placeholder": str(placeholder)}

    def select_label(self, label: str, value: str, *, tab_id: str | None = None) -> dict[str, Any]:
        selected = self._page(tab_id).get_by_label(str(label)).first.select_option(str(value))
        return {"label": str(label), "selected": selected}

    def check_label(self, label: str, *, checked: bool = True, tab_id: str | None = None) -> dict[str, Any]:
        locator = self._page(tab_id).get_by_label(str(label)).first
        locator.check() if checked else locator.uncheck()
        return {"label": str(label), "checked": bool(checked)}

    def press(self, key: str, *, selector: str = "", tab_id: str | None = None) -> dict[str, Any]:
        page = self._page(tab_id)
        if selector:
            page.locator(selector).first.press(str(key))
        else:
            page.keyboard.press(str(key))
        return {"key": str(key), "selector": selector}

    def scroll(self, *, direction: str = "down", pixels: int = 900, tab_id: str | None = None) -> dict[str, Any]:
        page = self._page(tab_id)
        pixels = max(1, min(abs(int(pixels)), 20000))
        direction = str(direction or "down").lower()
        dx = dy = 0
        if direction == "down": dy = pixels
        elif direction == "up": dy = -pixels
        elif direction == "right": dx = pixels
        elif direction == "left": dx = -pixels
        else: raise ValueError("direction must be up, down, left, or right")
        page.mouse.wheel(dx, dy)
        return {"direction": direction, "pixels": pixels}

    def wait_text(self, text: str, *, timeout_ms: int = 20000, tab_id: str | None = None) -> dict[str, Any]:
        page = self._page(tab_id)
        page.get_by_text(str(text), exact=False).first.wait_for(state="visible", timeout=max(500, min(int(timeout_ms), 120000)))
        return {"visible": True, "text": str(text), "url": page.url}

    def wait_load_state(self, state: str = "domcontentloaded", *, timeout_ms: int = 45000, tab_id: str | None = None) -> dict[str, Any]:
        state = str(state or "domcontentloaded")
        if state not in {"load", "domcontentloaded", "networkidle"}:
            raise ValueError("Unsupported load state.")
        page = self._page(tab_id)
        page.wait_for_load_state(state, timeout=max(1000, min(int(timeout_ms), 180000)))
        return {"state": state, "url": page.url}

    def back(self, *, tab_id: str | None = None) -> dict[str, Any]:
        page = self._page(tab_id)
        page.go_back(wait_until="domcontentloaded")
        return {"url": page.url, "title": self._safe_title(page)}

    def forward(self, *, tab_id: str | None = None) -> dict[str, Any]:
        page = self._page(tab_id)
        page.go_forward(wait_until="domcontentloaded")
        return {"url": page.url, "title": self._safe_title(page)}

    def reload(self, *, tab_id: str | None = None) -> dict[str, Any]:
        page = self._page(tab_id)
        page.reload(wait_until="domcontentloaded")
        return {"url": page.url, "title": self._safe_title(page)}

    @staticmethod
    def _sensitive_upload_path(path: Path) -> bool:
        lowered = [part.lower() for part in path.parts]
        name = path.name.lower()
        if any(part in {".ssh", ".aws", ".kube", ".gnupg"} for part in lowered):
            return True
        if name in {".env", ".npmrc", ".pypirc", "credentials", "credentials.json", "id_rsa", "id_ed25519"}:
            return True
        if any(token in name for token in ("private_key", "private-key", "secret_key", "secret-key", "api_key", "api-key")):
            return True
        if path.suffix.lower() in {".pem", ".p12", ".pfx", ".key"}:
            return True
        return False

    def upload(self, selector: str, path: str | Path, *, tab_id: str | None = None) -> dict[str, Any]:
        target = Path(path).expanduser().resolve()
        if not target.is_file():
            raise FileNotFoundError(str(target))
        if self._sensitive_upload_path(target) and not _env_bool("IRAS_WEB_ALLOW_SENSITIVE_UPLOADS", False):
            raise PermissionError("Sensitive credential/key files are blocked from web upload by default.")
        self._page(tab_id).locator(selector).first.set_input_files(str(target))
        return {"uploaded": str(target), "selector": selector}

    @staticmethod
    def _safe_filename(name: str) -> str:
        name = Path(str(name or "download.bin")).name
        name = re.sub(r"[^A-Za-z0-9._()\[\] -]+", "_", name).strip(" .")
        return name[:180] or "download.bin"

    def _unique_download_path(self, name: str) -> Path:
        base = self.download_dir / self._safe_filename(name)
        if not base.exists():
            return base
        stem, suffix = base.stem, base.suffix
        for index in range(1, 10000):
            candidate = base.with_name(f"{stem}-{index}{suffix}")
            if not candidate.exists():
                return candidate
        raise RuntimeError("Could not allocate a unique download filename.")

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _save_download(self, download: Any, filename: str = "") -> dict[str, Any]:
        target = self._unique_download_path(filename or download.suggested_filename)
        download.save_as(str(target))
        size = target.stat().st_size
        max_bytes = _env_int("IRAS_WEB_MAX_DOWNLOAD_MB", 1024, 1, 16384) * 1024 * 1024
        if size > max_bytes:
            try: target.unlink()
            except OSError: pass
            raise RuntimeError(f"Download exceeded IRAS_WEB_MAX_DOWNLOAD_MB ({max_bytes // (1024*1024)} MB).")
        record = WebDownload(
            path=str(target), filename=target.name, size=size, sha256=self._sha256(target),
            source_url=str(getattr(download, "url", "")), created_at=time.time(),
        )
        with self.download_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        self._publish("web.downloaded", path=record.path, size=record.size, sha256=record.sha256)
        return asdict(record)

    def download_selector(self, selector: str, *, filename: str = "", tab_id: str | None = None) -> dict[str, Any]:
        page = self._page(tab_id)
        with page.expect_download(timeout=_env_int("IRAS_WEB_NAV_TIMEOUT_MS", 45000, 3000, 180000)) as info:
            page.locator(selector).first.click()
        return self._save_download(info.value, filename)

    def download_text(self, text: str, *, filename: str = "", exact: bool = False, tab_id: str | None = None) -> dict[str, Any]:
        page = self._page(tab_id)
        with page.expect_download(timeout=_env_int("IRAS_WEB_NAV_TIMEOUT_MS", 45000, 3000, 180000)) as info:
            page.get_by_text(str(text), exact=bool(exact)).first.click()
        return self._save_download(info.value, filename)

    def downloads(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not self.download_log.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            for line in self.download_log.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict): rows.append(item)
        except OSError:
            return []
        return rows[-max(1, min(int(limit), 10000)):][::-1]

    def screenshot(self, *, name: str = "", full_page: bool = True, tab_id: str | None = None) -> dict[str, Any]:
        page = self._page(tab_id)
        if not name:
            name = f"web-{int(time.time())}.png"
        target = self.screenshot_dir / self._safe_filename(name)
        if target.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            target = target.with_suffix(".png")
        page.screenshot(path=str(target), full_page=bool(full_page))
        return {"path": str(target), "url": page.url}

    def challenge(self, *, tab_id: str | None = None) -> dict[str, Any]:
        if self._context is None:
            return {"detected": False, "types": []}
        page = self._page(tab_id)
        try:
            sample = (page.locator("body").inner_text() or "")[:50000].lower()
        except Exception:
            sample = ""
        types = [name for name, patterns in self.CHALLENGE_PATTERNS.items() if any(p in sample for p in patterns)]
        return {
            "detected": bool(types),
            "types": types,
            "instruction": (
                "User intervention is required for CAPTCHA/MFA/anti-bot challenges; IRAS will not bypass them."
                if types else ""
            ),
        }

    def submit(self, selector: str, *, approved: bool, tab_id: str | None = None) -> dict[str, Any]:
        if not approved:
            raise PermissionError("Consequential web submission requires CRITICAL authorization.")
        challenge = self.challenge(tab_id=tab_id)
        if challenge.get("detected"):
            raise PermissionError(challenge["instruction"])
        page = self._page(tab_id)
        page.locator(selector).first.click()
        self._refresh_tabs()
        self._publish("web.submitted", url=page.url, selector=selector)
        return {"submitted": selector, "url": page.url}

    def login(
        self,
        url: str,
        *,
        username: str,
        password: str,
        username_selector: str,
        password_selector: str,
        submit_selector: str,
        tab_id: str | None = None,
    ) -> dict[str, Any]:
        page = self._page(tab_id)
        self.navigate(url, tab_id=tab_id)
        before = self.challenge(tab_id=tab_id)
        if before.get("detected"):
            return {"ok": False, "url": page.url, "challenge": before, "credentials_exposed": False}
        page.locator(username_selector).first.fill(str(username))
        page.locator(password_selector).first.fill(str(password))
        page.locator(submit_selector).first.click()
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        after = self.challenge(tab_id=tab_id)
        return {
            "ok": not after.get("detected"),
            "url": page.url,
            "title": self._safe_title(page),
            "challenge": after,
            "credentials_exposed": False,
            "persistent_profile": self._profile,
        }

    def batch(self, steps: list[dict[str, Any]], *, approved: bool = False) -> dict[str, Any]:
        if not isinstance(steps, list) or not steps:
            raise ValueError("At least one web step is required.")
        if len(steps) > 50:
            raise ValueError("A web batch is limited to 50 steps.")
        results = []
        for index, raw in enumerate(steps):
            if not isinstance(raw, dict):
                raise ValueError(f"Web step {index} must be an object.")
            action = str(raw.get("action") or "").strip().lower()
            args = {k: v for k, v in raw.items() if k != "action"}
            if action == "search": out = self.search(**args)
            elif action == "navigate": out = self.navigate(**args)
            elif action == "snapshot": out = self.snapshot(**args)
            elif action == "extract": out = self.extract(**args)
            elif action == "click_text": out = self.click_text(**args)
            elif action == "click_role": out = self.click_role(**args)
            elif action == "click_selector": out = self.click_selector(**args)
            elif action == "fill_label": out = self.fill_label(**args)
            elif action == "fill_placeholder": out = self.fill_placeholder(**args)
            elif action == "fill_selector": out = self.fill_selector(**args)
            elif action == "select_label": out = self.select_label(**args)
            elif action == "check_label": out = self.check_label(**args)
            elif action == "press": out = self.press(**args)
            elif action == "scroll": out = self.scroll(**args)
            elif action == "wait_text": out = self.wait_text(**args)
            elif action == "wait_load_state": out = self.wait_load_state(**args)
            elif action == "upload": out = self.upload(**args)
            elif action == "download_selector": out = self.download_selector(**args)
            elif action == "download_text": out = self.download_text(**args)
            elif action == "back": out = self.back(**args)
            elif action == "forward": out = self.forward(**args)
            elif action == "reload": out = self.reload(**args)
            elif action == "new_tab": out = {"tab_id": self.new_tab(**args)[0]}
            elif action == "switch_tab": out = self.switch_tab(**args)
            elif action == "close_tab": out = self.close_tab(**args)
            elif action == "screenshot": out = self.screenshot(**args)
            elif action == "challenge": out = self.challenge(**args)
            elif action == "submit": out = self.submit(approved=approved, **args)
            else:
                raise ValueError(f"Unsupported web batch action: {action}")
            results.append({"index": index, "action": action, "result": out})
        return {"ok": True, "steps": results, "final": self.status()}
