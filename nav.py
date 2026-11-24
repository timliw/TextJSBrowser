"""
Build a terminal-renderable page model from HTML: wrapped lines with inline
link segments, so a TUI can scroll lines and Tab between links.
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

def extract_title(html, fallback_url=""):
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if m:
        t = re.sub(r"\s+", " ", m.group(1)).strip()
        return t
    return fallback_url

try:
    from wcwidth import wcwidth as _wc
except Exception:
    def _wc(ch):
        if ch in "\t\n\r":
            return 0
        o = ord(ch)
        return 2 if (0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0xA4CF or
                     0xAC00 <= o <= 0xD7A3 or 0xF900 <= o <= 0xFAFF or
                     0xFE30 <= o <= 0xFE4F or 0xFF00 <= o <= 0xFF60 or
                     0xFFE0 <= o <= 0xFFE6 or 0x20000 <= o <= 0x3FFFD) else 1

BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
         "pre", "td", "dd", "dt", "section", "article", "ul", "ol", "table"}
SKIP_PARENTS = {"script", "style", "noscript", "head", "title", "iframe",
                "svg", "template", "button", "select", "option", "nav",
                "header", "footer", "aside", "form", "object", "embed"}


class Seg:
    __slots__ = ("kind", "text", "href", "width")
    def __init__(self, kind, text, href=None):
        self.kind = kind            # 'text' or 'link'
        self.text = text
        self.href = href
        self.width = sum(_wc(c) for c in text)


class Link:
    __slots__ = ("text", "href", "row", "col")
    def __init__(self, text, href, row, col):
        self.text = text
        self.href = href
        self.row = row
        self.col = col


class Page:
    def __init__(self, title, url, lines, links):
        self.title = title
        self.url = url
        self.lines = lines          # list[list[Seg]]
        self.links = links          # list[Link] in display order
        self.content_start = _find_content_start(lines)


def _find_content_start(lines):
    """Return the line index where the main prose begins (skip nav/blank junk).

    Nav/menu links are short single labels; the chapter heading/breadcrumb and
    the prose paragraphs are the first substantive (>= MIN_SUB chars) lines on
    a reading page. We anchor at the first such line, backed up two lines so a
    standalone chapter title right before it isn't cut.
    """
    n = len(lines)
    if n == 0:
        return 0
    MIN_SUB = 12  # a real prose/breadcrumb line holds at least this many chars
    for i, line in enumerate(lines):
        ln = sum(len(s.text) for s in line if s.text.strip())
        if ln >= MIN_SUB:
            return max(0, i - 2)
    return 0


def _wrap_text(seg_text, lines, width):
    """Append a plain text token to the line list, wrapping at `width`."""
    last = lines[-1]
    cur = ""
    cur_col = sum(s.width for s in last) if last else 0
    for ch in seg_text:
        if ch == "\n":
            if cur:
                last.append(Seg("text", cur))
                cur = ""
                cur_col = 0
            lines.append([])
            last = lines[-1]
            continue
        w = _wc(ch)
        if cur_col + w > width and cur:
            last.append(Seg("text", cur))
            cur = ""
            cur_col = 0
            lines.append([])
            last = lines[-1]
        cur += ch
        cur_col += w
    if cur:
        last.append(Seg("text", cur))


def build_flow(html, base_url, width):
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body or soup
    title = extract_title(html, base_url)
    lines = [[]]
    links = []

    def walk(node):
        for child in getattr(node, "children", []):
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                _wrap_text(str(child), lines, width)
            elif isinstance(child, Tag):
                name = child.name.lower()
                if name in SKIP_PARENTS:
                    continue
                if name in BLOCK and lines[-1]:
                    # block boundary after existing content = paragraph break
                    lines.append([])
                if name == "br":
                    lines.append([])
                elif name == "a":
                    href = child.get("href")
                    if href:
                        text = " ".join(child.get_text(" ", strip=True).split())
                        if not text:
                            text = href
                        # keep the whole link on one line
                        last_line_col = sum(s.width for s in lines[-1])
                        link_w = sum(_wc(c) for c in text)
                        if last_line_col + link_w > width and lines[-1]:
                            lines.append([])
                        row = len(lines) - 1
                        col = sum(s.width for s in lines[-1])
                        lines[-1].append(Seg("link", text, urljoin(base_url, href)))
                        links.append(Link(text, urljoin(base_url, href), row, col))
                    # don't recurse into <a> (text already taken)
                else:
                    walk(child)

    walk(body)

    # Reading layout: drop blank lines entirely so prose is continuous (a wall
    # of text like a book) — separate paragraphs are still visually distinct
    # via their leading full-width indent \u3000\u3000. Nav/list links stay on
    # their own lines because they carry text. This removes the white-space
    # gaps that made the page feel like it "flashes to black" when scrolling.
    # NOTE: must remap Link.row afterwards, else link coordinates point past
    # the compressed line array (JS-rendered links near the page bottom would
    # never be reachable by the cursor/Tab).
    old_new = {}
    compressed = []
    for old, line in enumerate(lines):
        if any(s.text.strip() for s in line):
            old_new[old] = len(compressed)
            compressed.append(line)
    lines = compressed
    # remap every link's row to its post-compression line index
    for lk in links:
        if lk.row in old_new:
            lk.row = old_new[lk.row]
        else:
            # link sat on a line that got dropped (shouldn't happen: a link
            # line always carries text) — pin it to a sane nearby line
            lk.row = old_new[min(old_new, key=lambda k: abs(k - lk.row))]

    return Page(title, base_url, lines, links)
