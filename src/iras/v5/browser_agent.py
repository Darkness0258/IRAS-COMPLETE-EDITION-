from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import time
from typing import Any


@dataclass
class BrowserWorkflowResult:
    ok: bool
    url: str = ""
    title: str = ""
    text: str = ""
    downloads: list[str] = field(default_factory=list)
    error: str = ""


class DedicatedBrowserAgent:
    """Playwright-backed browser worker with persistent auth state support.

    Browser automation stays in its own context and exposes narrow operations;
    callers decide which actions are permitted.
    """

    def __init__(self, state_dir: str | Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._pw = self._browser = self._context = None

    @property
    def available(self) -> bool:
        try:
            import playwright.sync_api  # noqa: F401
            return True
        except Exception:
            return False

    def start(self, *, headless: bool = True, profile: str = "default"):
        if self._context is not None:
            return
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        state = self.state_dir / f"{profile}.json"
        kwargs = {"accept_downloads": True}
        if state.exists():
            kwargs["storage_state"] = str(state)
        self._context = self._browser.new_context(**kwargs)

    def stop(self, *, profile: str = "default"):
        if self._context:
            try:
                self._context.storage_state(path=str(self.state_dir / f"{profile}.json"))
            except Exception:
                pass
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self._pw = self._browser = self._context = None

    def _page(self):
        if self._context is None:
            raise RuntimeError("Browser agent is not started.")
        pages = self._context.pages
        return pages[-1] if pages else self._context.new_page()

    def navigate(self, url: str, *, wait: str = "domcontentloaded", timeout_ms: int = 30000) -> BrowserWorkflowResult:
        if not url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise ValueError("Browser navigation requires HTTPS (localhost allowed for development).")
        page = self._page()
        try:
            page.goto(url, wait_until=wait, timeout=timeout_ms)
            return BrowserWorkflowResult(True, url=page.url, title=page.title(), text=page.locator("body").inner_text()[:30000])
        except Exception as exc:
            return BrowserWorkflowResult(False, url=url, error=f"{type(exc).__name__}: {exc}")

    def fill(self, selector: str, value: str) -> None:
        self._page().locator(selector).fill(value)

    def click(self, selector: str) -> None:
        self._page().locator(selector).click()

    def extract(self, selector: str = "body", *, limit: int = 30000) -> str:
        return self._page().locator(selector).inner_text()[:limit]

    def tabs(self) -> list[dict[str, str]]:
        if self._context is None:
            return []
        return [{"url": p.url, "title": p.title()} for p in self._context.pages]
