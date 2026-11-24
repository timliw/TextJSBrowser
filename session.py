"""
Persistent fetch session for the tbr interactive browser.

Unlike tbr.py (which launches a fresh browser per page), this keeps ONE
Camoufox browser + context alive so navigating link-to-link is fast and a
Cloudflare-cleared cookie persists across pages on the same site.
"""
import os
import warnings

import requests
from paths import require_camoufox_bin

warnings.filterwarnings("ignore")  # host uses MITM cert; we bypass via verify=False

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


class FetchSession:
    def __init__(self, engine="js"):
        self.engine = engine
        self._browser = None
        self._ctx = None
        self._camoufox = None

    # ---- js engine --------------------------------------------------------
    def _ensure_browser(self):
        if self._browser is not None:
            return
        from camoufox.sync_api import Camoufox
        self._camoufox = Camoufox(headless=True,
                                  executable_path=require_camoufox_bin(),
                                  i_know_what_im_doing=True)
        self._browser = self._camoufox.__enter__()
        self._ctx = self._browser.new_context(
            ignore_https_errors=True, locale="zh-TW", timezone_id="Asia/Taipei")

    def fetch_js(self, url, timeout=45):
        self._ensure_browser()
        page = self._ctx.new_page()
        try:
            page.set_default_timeout(int(timeout * 1000))
            try:
                page.goto(url, wait_until="domcontentloaded")
            except Exception:
                page.goto(url, wait_until="commit")
            # let Cloudflare clear; stop as soon as real text shows
            for _ in range(20):
                page.wait_for_timeout(1000)
                try:
                    t = page.title() or ""
                    body = page.evaluate(
                        "document.body ? document.body.innerText : ''") or ""
                except Exception:
                    t, body = "", ""
                if "請稍候" not in t and "安全驗證" not in body and "Just a moment" not in t:
                    break
            html = page.content()
            return page.url, html.encode("utf-8")
        finally:
            try:
                page.close()
            except Exception:
                pass

    # ---- plain engine -----------------------------------------------------
    def fetch_plain(self, url, timeout=25):
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.6"})
        r = s.get(url, timeout=timeout, verify=False)
        r.raise_for_status()
        return r.url, r.content

    def fetch(self, url):
        if self.engine == "plain":
            return self.fetch_plain(url)
        return self.fetch_js(url)

    def close(self):
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._camoufox is not None:
                self._camoufox.__exit__(None, None, None)
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
