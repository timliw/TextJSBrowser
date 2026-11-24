"""
tbr — a Linux text browser.

Fetches a URL and renders it as plain text in the terminal, like lynx/w3m
but with a real JavaScript engine available. Two fetch engines:

  js   (default)  Headless Camoufox (Firefox-based stealth browser).
                  Executes JavaScript and defeats Cloudflare-style bot
                  checks, surfacing content JS-heavy/paywalled pages.
  plain           Fast no-JS fetch: a plain HTTP GET + HTML parse. Use
                  --no-js for static pages or when you want to bypass a
                  site's JS to get raw HTML text fast.

Usage:
  tbr <url>                 render main readable text
  tbr <url> -j              same, force js engine
  tbr <url> --no-js         fast plain fetch (bypass JS)
  tbr <url> --links         list page links (numbered) instead of text
  tbr <url> --title         print only the title
  tbr <url> -o out.txt      write result to file
  tbr <url> -s 關鍵字         print only matching lines (grep the output)
  tbr <url> --json          structured {title, url, text, links...} JSON
  tbr --engine js <url>     explicit engine as subcommand

Selector override examples:
  tbr URL -c '.articlebody,.yd_text2,#content'   use a CSS selector
"""
import argparse, json, re, sys, warnings
from urllib.parse import urljoin, urlparse

import requests
warnings.filterwarnings("ignore")  # host uses MITM cert; we bypass via verify=False

from extract import extract_readable, extract_links

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


# ---------------------------------------------------------------- plain engine
def fetch_plain(url, timeout=25):
    """No-JS engine: plain HTTP GET, returns raw HTML (no JS executed)."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.6"})
    r = s.get(url, timeout=timeout, verify=False)
    r.raise_for_status()
    return r.url, r.content


# ------------------------------------------------------------------ js engine
def fetch_js(url, timeout=45):
    """JS engine: headless Camoufox renders the page (runs JavaScript)."""
    from camoufox.sync_api import Camoufox
    from paths import require_camoufox_bin
    with Camoufox(headless=True, executable_path=require_camoufox_bin(),
                  i_know_what_im_doing=True) as browser:
        ctx = browser.new_context(ignore_https_errors=True,
                                  locale="zh-TW", timezone_id="Asia/Taipei")
        page = ctx.new_page()
        page.set_default_timeout(int(timeout * 1000))
        kwargs = dict(wait_until="domcontentloaded")
        try:
            page.goto(url, **kwargs)
        except Exception:
            page.goto(url, wait_until="commit")
        # give Cloudflare bot-check time to clear; stop as soon as real text shows
        for _ in range(20):
            page.wait_for_timeout(1000)
            try:
                t = page.title() or ""
                body = page.evaluate("document.body ? document.body.innerText : ''") or ""
            except Exception:
                t, body = "", ""
            if "請稍候" not in t and "安全驗證" not in body and "Just a moment" not in t:
                break
        html = page.content()
        url = page.url
        return url, html.encode("utf-8")


# ------------------------------------------------------------------- dispatch
def fetch(url, engine):
    if engine == "plain":
        return fetch_plain(url)
    return fetch_js(url)


def main(argv=None):
    p = argparse.ArgumentParser(description="tbr — Linux text browser",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__)
    p.add_argument("url", help="URL to open")
    p.add_argument("-j", "--js", action="store_true", help="use js engine (default for CF sites)")
    p.add_argument("--no-js", dest="no_js", action="store_true",
                   help="fast no-JS plain fetch (bypass JavaScript)")
    p.add_argument("--engine", choices=["js", "plain"], default=None,
                   help="explicit engine (overrides -j / --no-js)")
    p.add_argument("-l", "--links", action="store_true", help="list links instead of text")
    p.add_argument("--title", action="store_true", help="print only the title")
    p.add_argument("-c", "--css", default=None, help="CSS selector for main content")
    p.add_argument("-o", "--output", default=None, help="write output to file")
    p.add_argument("-s", "--search", default=None, help="keep only lines containing text")
    p.add_argument("--json", dest="as_json", action="store_true", help="emit JSON")
    p.add_argument("--max-links", type=int, default=100, help="max links to list")
    args = p.parse_args(argv)

    engine = args.engine or ("plain" if (args.no_js and not args.js) else "js")

    try:
        final_url, raw = fetch(args.url, engine)
    except Exception as e:
        sys.stderr.write(f"tbr: fetch failed ({engine} engine): {e}\n")
        return 2
    if not raw:
        sys.stderr.write("tbr: empty response\n")
        return 3

    title = None
    m = re.search(rb"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    if m:
        title = re.sub(r"\s+", " ", m.group(1).decode("utf-8", "ignore")).strip()

    html = raw.decode("utf-8", "ignore")

    if args.links:
        links = extract_links(html, final_url)
        # filters for paragraph links in gray text
        stripped = []
        for text, href in links:
            t = text.strip()
            if not t or href.startswith("javascript:"):
                continue
            stripped.append((t, href))
        if args.as_json:
            out = {"title": title, "url": final_url,
                   "links": [{"text": t, "href": h} for t, h in stripped[:args.max_links]]}
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0
        for i, (t, h) in enumerate(stripped[:args.max_links], 1):
            print(f"{i:>4}. {t}")
            print(f"     {h}")
        return 0

    text = extract_readable(html, selector=args.css)

    if args.title:
        print(title or final_url)
    elif args.as_json:
        print(json.dumps({"title": title, "url": final_url, "text": text,
                          "engine": engine}, ensure_ascii=False, indent=2))
    else:
        header = f"# {title}" if title else f"# {final_url}"
        buf = header + "\n" + ("=" * len(header)) + "\n\n" + text + "\n"

        if args.search:
            q = args.search
            lines = [ln for ln in buf.splitlines() if q in ln]
            buf = "\n".join(lines) + "\n"

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(buf)
        else:
            sys.stdout.write(buf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
