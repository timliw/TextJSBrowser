"""
Smoke tests for tbr. No network, no browser — exercises the pure HTML->text
and link-extraction paths so CI can run them quickly.
Run: python smoke_test.py
"""
import sys

from nav import build_flow
from extract import extract_readable, extract_links

HTML = """
<html><head><title>Test Page</title></head>
<body>
  <nav>
    <a href="/home">Home</a>
    <a href="/about">About</a>
  </nav>
  <article>
    <h1>Article Title</h1>
    <p>First    paragraph with some interesting content.</p>
    <p>Second paragraph here.
       <a href="/next">Next page</a> follows.</p>
  </article>
  <footer><a href="/contact">Contact</a></footer>
</body></html>
"""


def test_readable():
    text = extract_readable(HTML)
    assert "First paragraph with some interesting content." in text, text
    assert "Second paragraph here." in text, text
    # nav/footer links stripped from readable output
    assert "Home" not in text, text
    assert "Contact" not in text, text
    print("  extract_readable  OK")


def test_links():
    links = list(extract_links(HTML, "https://example.com/base"))
    hrefs = [h for _, h in links]
    assert "https://example.com/home" in hrefs, hrefs
    assert "https://example.com/next" in hrefs, hrefs
    print("  extract_links     OK")


def test_build_flow():
    page = build_flow(HTML, "https://example.com/base", width=80)
    texts = ["".join(s.text for s in line) for line in page.lines]
    joined = "\n".join(texts)
    assert "Article Title" in joined, joined
    assert "First" in joined and "interesting content" in joined, joined
    assert any(s.kind == "link" and s.href.endswith("/next") for line in page.lines for s in line), joined
    assert all(0 <= lk.row < len(page.lines) for lk in page.links), "out-of-range link row"
    # nav/footer links are stripped for readability; the in-article /next link stays
    assert len(page.links) >= 1 and all(lk.href.endswith("/next") for lk in page.links), \
        f"expected in-article /next link, got {[(l.text,l.href) for l in page.links]}"
    print("  build_flow        OK (links:", len(page.links), ", lines:", len(page.lines), ")")


def main():
    print("Running smoke tests...")
    test_readable()
    test_links()
    test_build_flow()
    print("All smoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
