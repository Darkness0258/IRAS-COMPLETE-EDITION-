from __future__ import annotations

from pathlib import Path

from iras.models import PermissionLevel
from iras.tools.base import Tool


class BrowserSession:
    def __init__(self):
        self.pw = None
        self.browser = None
        self.page = None

    def _ensure(self):
        if self.page:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Install browser support: pip install -e '.[browser]' then 'playwright install chromium'"
            ) from exc
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=False)
        self.page = self.browser.new_page()

    def navigate(self, url):
        self._ensure()
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return {"url": self.page.url, "title": self.page.title()}

    def current(self):
        self._ensure()
        return {"url": self.page.url, "title": self.page.title()}

    def text(self, max_chars=30000):
        self._ensure()
        return self.page.locator("body").inner_text()[: max(1, min(int(max_chars), 100000))]

    def click(self, selector):
        self._ensure()
        self.page.locator(selector).first.click(timeout=15000)
        return {"url": self.page.url, "selector": selector}

    def fill(self, selector, text):
        self._ensure()
        self.page.locator(selector).first.fill(str(text), timeout=15000)
        return {"filled": selector}

    def wait_text(self, text, timeout=15000):
        self._ensure()
        timeout = max(500, min(int(timeout), 60000))
        self.page.get_by_text(str(text), exact=False).first.wait_for(
            state="visible",
            timeout=timeout,
        )
        return {"visible": True, "text": str(text), "url": self.page.url}

    def upload(self, selector, path):
        self._ensure()
        target = Path(path).expanduser().resolve()
        if not target.is_file():
            raise FileNotFoundError(target)
        self.page.locator(selector).first.set_input_files(str(target), timeout=15000)
        return {"uploaded": str(target), "selector": selector}

    def new_tab(self, url=""):
        self._ensure()
        self.page = self.browser.new_page()
        if url:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return {"url": self.page.url, "title": self.page.title(), "tabs": len(self.browser.contexts[0].pages)}

    def tabs(self):
        self._ensure()
        pages = self.browser.contexts[0].pages
        return [
            {"index": index, "url": page.url, "title": page.title(), "active": page is self.page}
            for index, page in enumerate(pages)
        ]

    def switch_tab(self, index):
        self._ensure()
        pages = self.browser.contexts[0].pages
        index = int(index)
        if index < 0 or index >= len(pages):
            raise IndexError("Browser tab index is out of range.")
        self.page = pages[index]
        self.page.bring_to_front()
        return {"index": index, "url": self.page.url, "title": self.page.title()}

    def back(self):
        self._ensure()
        self.page.go_back(wait_until="domcontentloaded", timeout=30000)
        return {"url": self.page.url, "title": self.page.title()}

    def forward(self):
        self._ensure()
        self.page.go_forward(wait_until="domcontentloaded", timeout=30000)
        return {"url": self.page.url, "title": self.page.title()}

    def shot(self, path="screenshots/browser.png"):
        self._ensure()
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(target), full_page=True)
        return str(target)

    def close(self):
        if self.browser:
            self.browser.close()
        if self.pw:
            self.pw.stop()
        self.pw = self.browser = self.page = None
        return {"closed": True}


def make_tools(session):
    return [
        Tool(
            "browser_navigate",
            "Navigate the interactive browser to a URL.",
            {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            session.navigate,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "browser_current",
            "Read the current browser URL and page title.",
            {"type": "object", "properties": {}},
            session.current,
            PermissionLevel.READ,
        ),
        Tool(
            "browser_text",
            "Read visible text from the current interactive browser page.",
            {"type": "object", "properties": {"max_chars": {"type": "integer"}}},
            session.text,
            PermissionLevel.READ,
        ),
        Tool(
            "browser_click",
            "Click one DOM element using a selector. State-changing and approval-gated.",
            {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]},
            session.click,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "browser_fill",
            "Fill a DOM field in the interactive browser.",
            {"type": "object", "properties": {"selector": {"type": "string"}, "text": {"type": "string"}}, "required": ["selector", "text"]},
            session.fill,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "browser_wait_text",
            "Wait for visible DOM text as semantic navigation verification.",
            {"type": "object", "properties": {"text": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["text"]},
            session.wait_text,
            PermissionLevel.READ,
        ),
        Tool(
            "browser_upload",
            "Upload a local file through a file-input selector.",
            {"type": "object", "properties": {"selector": {"type": "string"}, "path": {"type": "string"}}, "required": ["selector", "path"]},
            session.upload,
            PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            "browser_new_tab",
            "Open a new browser tab, optionally navigating it to a URL.",
            {"type": "object", "properties": {"url": {"type": "string"}}},
            session.new_tab,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "browser_tabs",
            "List open browser tabs.",
            {"type": "object", "properties": {}},
            session.tabs,
            PermissionLevel.READ,
        ),
        Tool(
            "browser_switch_tab",
            "Switch to an existing browser tab by index.",
            {"type": "object", "properties": {"index": {"type": "integer"}}, "required": ["index"]},
            session.switch_tab,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "browser_back",
            "Navigate the current tab backward.",
            {"type": "object", "properties": {}},
            session.back,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "browser_forward",
            "Navigate the current tab forward.",
            {"type": "object", "properties": {}},
            session.forward,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "browser_screenshot",
            "Save a screenshot of the current browser page.",
            {"type": "object", "properties": {"path": {"type": "string"}}},
            session.shot,
            PermissionLevel.READ,
        ),
        Tool(
            "browser_close",
            "Close the interactive browser session.",
            {"type": "object", "properties": {}},
            session.close,
            PermissionLevel.SAFE_ACTION,
        ),
    ]
