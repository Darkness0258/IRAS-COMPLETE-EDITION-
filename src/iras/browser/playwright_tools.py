from __future__ import annotations
from pathlib import Path
from iras.models import PermissionLevel
from iras.tools.base import Tool

class BrowserSession:
    def __init__(self): self.pw=None; self.browser=None; self.page=None
    def _ensure(self):
        if self.page: return
        try: from playwright.sync_api import sync_playwright
        except ImportError as e: raise RuntimeError("Install browser support: pip install -e '.[browser]' then 'playwright install chromium'") from e
        self.pw=sync_playwright().start(); self.browser=self.pw.chromium.launch(headless=False); self.page=self.browser.new_page()
    def navigate(self,url): self._ensure(); self.page.goto(url,wait_until='domcontentloaded',timeout=30000); return {'url':self.page.url,'title':self.page.title()}
    def text(self,max_chars=30000): self._ensure(); return self.page.locator('body').inner_text()[:max_chars]
    def click(self,selector): self._ensure(); self.page.locator(selector).first.click(timeout=15000); return {'url':self.page.url}
    def fill(self,selector,text): self._ensure(); self.page.locator(selector).first.fill(text); return {'filled':selector}
    def shot(self,path='screenshots/browser.png'): self._ensure(); p=Path(path).resolve(); p.parent.mkdir(parents=True,exist_ok=True); self.page.screenshot(path=str(p),full_page=True); return str(p)
    def close(self):
        if self.browser: self.browser.close()
        if self.pw: self.pw.stop()
        self.pw=self.browser=self.page=None; return {'closed':True}

def make_tools(session):
    return [
      Tool('browser_navigate','Navigate the interactive browser to a URL.',{'type':'object','properties':{'url':{'type':'string'}},'required':['url']},session.navigate,PermissionLevel.SAFE_ACTION),
      Tool('browser_text','Read visible text from the current interactive browser page.',{'type':'object','properties':{'max_chars':{'type':'integer'}}},session.text,PermissionLevel.READ),
      Tool('browser_click','Click an element in the interactive browser. This may trigger actions and requires approval.',{'type':'object','properties':{'selector':{'type':'string'}},'required':['selector']},session.click,PermissionLevel.SYSTEM_ACTION),
      Tool('browser_fill','Fill a field in the interactive browser.',{'type':'object','properties':{'selector':{'type':'string'},'text':{'type':'string'}},'required':['selector','text']},session.fill,PermissionLevel.SYSTEM_ACTION),
      Tool('browser_screenshot','Save a screenshot of the current browser page.',{'type':'object','properties':{'path':{'type':'string'}}},session.shot,PermissionLevel.READ),
      Tool('browser_close','Close the interactive browser session.',{'type':'object','properties':{}},session.close,PermissionLevel.SAFE_ACTION),
    ]
