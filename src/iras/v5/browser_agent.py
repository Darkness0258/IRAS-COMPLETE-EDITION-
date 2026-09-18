from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
from typing import Any
from urllib.parse import urlsplit


@dataclass
class BrowserWorkflowResult:
    ok: bool
    url: str = ""
    title: str = ""
    text: str = ""
    downloads: list[str] = field(default_factory=list)
    error: str = ""


class DedicatedBrowserAgent:
    """Playwright browser worker with persistent profiles, tabs and downloads."""

    def __init__(self,state_dir:str|Path):
        self.state_dir=Path(state_dir); self.state_dir.mkdir(parents=True,exist_ok=True)
        self.download_dir=self.state_dir/"downloads"; self.download_dir.mkdir(exist_ok=True)
        self._pw=self._browser=self._context=None; self._profile="default"; self._tabs:dict[str,Any]={}; self._counter=0

    @property
    def available(self)->bool:
        try: import playwright.sync_api; return True
        except Exception: return False

    def start(self,*,headless:bool=True,profile:str="default"):
        if self._context is not None: return
        from playwright.sync_api import sync_playwright
        self._profile=profile; self._pw=sync_playwright().start(); self._browser=self._pw.chromium.launch(headless=headless)
        state=self.state_dir/f"{profile}.json"; kwargs={"accept_downloads":True}
        if state.exists(): kwargs["storage_state"]=str(state)
        self._context=self._browser.new_context(**kwargs)
        page=self._context.new_page(); self._counter+=1; self._tabs[f"tab-{self._counter}"]=page

    def stop(self):
        if self._context:
            try: self._context.storage_state(path=str(self.state_dir/f"{self._profile}.json"))
            except Exception: pass
            self._context.close()
        if self._browser: self._browser.close()
        if self._pw: self._pw.stop()
        self._pw=self._browser=self._context=None; self._tabs.clear()

    def _page(self,tab_id:str|None=None):
        if self._context is None: raise RuntimeError("Browser agent is not started.")
        if tab_id:
            page=self._tabs.get(tab_id)
            if page is None: raise KeyError(tab_id)
            return page
        if self._tabs: return list(self._tabs.values())[-1]
        return self.new_tab()[1]

    def new_tab(self,url:str="")->tuple[str,Any]:
        if self._context is None: raise RuntimeError("Browser agent is not started.")
        page=self._context.new_page(); self._counter+=1; tid=f"tab-{self._counter}"; self._tabs[tid]=page
        if url: self.navigate(url,tab_id=tid)
        return tid,page

    def close_tab(self,tab_id:str)->None:
        page=self._tabs.pop(tab_id); page.close()

    @staticmethod
    def _validate_url(url:str)->str:
        candidate=str(url or "").strip()
        if not candidate:
            raise ValueError("Browser navigation URL is required.")
        try:
            parsed=urlsplit(candidate)
            _=parsed.port  # Force invalid-port validation.
        except ValueError as exc:
            raise ValueError("Browser navigation URL is invalid.") from exc
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Browser navigation URLs must not contain embedded credentials.")
        host=(parsed.hostname or "").lower()
        if not host:
            raise ValueError("Browser navigation URL must include a host.")
        is_loopback=host in {"localhost","127.0.0.1","::1"}
        if parsed.scheme.lower() == "https":
            return candidate
        if parsed.scheme.lower() == "http" and is_loopback:
            return candidate
        raise ValueError("Browser navigation requires HTTPS (localhost allowed for development).")

    def navigate(self,url:str,*,tab_id:str|None=None,wait:str="domcontentloaded",timeout_ms:int=30000)->BrowserWorkflowResult:
        url=self._validate_url(url)
        page=self._page(tab_id)
        try:
            page.goto(url,wait_until=wait,timeout=timeout_ms)
            return BrowserWorkflowResult(True,url=page.url,title=page.title(),text=page.locator("body").inner_text()[:30000])
        except Exception as exc: return BrowserWorkflowResult(False,url=url,error=f"{type(exc).__name__}: {exc}")

    def fill(self,selector:str,value:str,*,tab_id:str|None=None)->None: self._page(tab_id).locator(selector).fill(value)
    def click(self,selector:str,*,tab_id:str|None=None)->None: self._page(tab_id).locator(selector).click()
    def upload(self,selector:str,path:str|Path,*,tab_id:str|None=None)->None:
        p=Path(path).expanduser().resolve()
        if not p.is_file(): raise FileNotFoundError(str(p))
        self._page(tab_id).locator(selector).set_input_files(str(p))
    def extract(self,selector:str="body",*,tab_id:str|None=None,limit:int=30000)->str: return self._page(tab_id).locator(selector).inner_text()[:limit]
    def verify(self,*,url_contains:str="",text_contains:str="",selector:str="",tab_id:str|None=None)->dict[str,Any]:
        p=self._page(tab_id); checks=[]
        if url_contains: checks.append(("url",url_contains in p.url))
        if text_contains: checks.append(("text",text_contains in p.locator("body").inner_text()))
        if selector: checks.append(("selector",p.locator(selector).count()>0))
        return {"ok":all(v for _,v in checks) if checks else True,"checks":dict(checks),"url":p.url,"title":p.title()}
    def submit(self,selector:str,*,approved:bool,tab_id:str|None=None)->None:
        if not approved: raise PermissionError("Consequential browser submission requires explicit approval.")
        self.click(selector,tab_id=tab_id)
    def tabs(self)->list[dict[str,str]]:
        return [{"tab_id":tid,"url":p.url,"title":p.title()} for tid,p in self._tabs.items() if not p.is_closed()]
