"""
Text extraction helpers for tbr.

  extract_readable(html, selector=None) -> str
      Best-effort "reader mode": pick the densest text container and return
      clean paragraph text. Falls back to specific selectors when given.

  extract_links(html, base_url) -> list[(text, absolute_url)]
      Harvest <a href> pairs, deduplicated, absolutised.
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

# Elements whose content we treat as prose blocks
BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
         "pre", "td", "dd", "dt", "section", "article"}
SKIP_PARENTS = {"script", "style", "noscript", "head", "title", "iframe",
                "svg", "template", "form", "button", "select", "nav",
                "header", "footer", "aside", "option", "noscript"}


def _clean_text(s):
    lines = [re.sub(r"[ \t\u3000]+", " ", ln).strip() for ln in s.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def _node_text(el):
    """Get text of an element as kept paragraphs (block tags -> newline)."""
    parts = []
    for child in el.descendants:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag) and child.name in BLOCK:
            parts.append("\n")
    return _clean_text("".join(parts))


def _selector_extract(html, selector):
    soup = BeautifulSoup(html, "html.parser")
    try:
        sel = soup.select(selector)
    except Exception:
        return None
    if not sel:
        return None
    parts = []
    for node in sel:
        t = _node_text(node)
        if t:
            parts.append(t)
    return _clean_text("\n\n".join(parts)) if parts else None


def _strip_fluff(soup):
    for bad in soup.findAll(SKIP_PARENTS):
        bad.decompose()
    for bad in soup(["script", "style"]):
        bad.decompose()
    for comment in soup.findAll(text=lambda t: isinstance(t, Comment)):
        comment.extract()
    # drop whitespace-only strings
    return soup


def _density_score(el):
    """Number of meaningful characters in an element."""
    txt = el.get_text(" ", strip=True)
    return len(txt)


def extract_readable(html, selector=None):
    if selector:
        got = _selector_extract(html, selector)
        if got:
            return got

    soup = BeautifulSoup(html, "html.parser")
    _strip_fluff(soup)
    body = soup.body or soup
    if body is None:
        return ""

    # Find the candidate element (div/section/article) with the highest text
    # density that is a plausible main-content container. We pick the block
    # element with the most text whose own text (excluding children) is still
    # substantial — effectively the deepest dense container.
    best = None
    best_score = -1
    for el in body.find_all(["div", "section", "article", "main"]):
        score = _density_score(el)
        # an element containing >90% of body is probably the page wrapper, skip
        if score > best_score and score < _density_score(body) * 0.95:
            best = el
            best_score = score
        elif score > best_score and score == _density_score(body):
            best = el
            best_score = score

    # Prefer the densest descendant; if none qualifies, fall back directly.
    result = _node_text(best) if best is not None else _node_text(body)
    return _clean_text(result) if result else ""


# ------------------------------------------------------------------ links
def extract_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue
        text = " ".join(a.get_text().split())
        abs_url = urljoin(base_url, href)
        key = (text, abs_url)
        if key in seen:
            continue
        seen.add(key)
        links.append((text, abs_url))
    return links
