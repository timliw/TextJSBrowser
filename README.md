# tbr — Terminal Text Browser

A text-mode web browser for Linux. Renders web pages as plain text in your
terminal — like `lynx` / `w3m` — but with a **real JavaScript engine** under
the hood, so it also works on modern, Cloudflare-protected sites.

Two interfaces come out of the box:

- **`tbrowse`** — an interactive, pointer-driven TUI browser (scroll with
  Up/Down, jump between links, open them, go back/forward).
- **`tbr`** — a one-shot CLI that renders a single URL to text (for scripting,
  pipes, and quick checks).

## Why a real JS engine?

Many sites today — including the example below — sit behind Cloudflare's bot
check. A plain HTTP fetch returns an HTML challenge (`Just a moment...`) with
no content. `tbrowse`/`tbr` therefore drive a **stealth headless browser
(Camoufox)** that executes the page's JavaScript, passes the bot check, and
renders the real content as text. There's also a fast **no-JS** engine for
plain static pages.

Real example — a Cloudflare-protected novel chapter:

```bash
tbrowse "https://www.google.com"
```

Opens directly onto the chapter text, lets you Tab between links, and Enter on
`Next Page` follows to the next chapter. Plain `curl`/`requests` can't read that
page at all — `tbrowse` can.

## Features

- **Interactive TUI** — a `>` pointer cursor you move with Up/Down; the view
  follows and centers it. Links are bold, the link under the cursor is
  highlighted; Enter opens it.
- **Cloudflare / JS support** — default `js` engine runs the page's JavaScript
  via stealth Camoufox, defeating bot checks.
- **Fast no-JS mode** — `--engine plain` for static pages (instant, no browser).
- **History** — back/forward like a real browser (`Left` / `f`).
- **Scroll indicators** — a right-edge scrollbar and a `%` read position.
- **Content anchoring** — opens on the article body, skipping nav/boilerplate.
- **Reader-friendly layout** — prose rendered as continuous text.
- **Persistent session** — one browser stays open across navigation, so
  link-to-link jumps are fast and a site's cookies persist across pages.
- **One-shot CLI** — `tbr <url>` for scripts, `--links`, `--title`, grep with
  `-s`, `-o` to a file, `--json` output, CSS-selector override via `-c`.

## Requirements

- Linux
- Python 3.9+ (developed on 3.14)
- A Camoufox browser install (the js engine needs it; see Install)

## Install

```bash
git clone <your-repo-url>
cd textbrowser

# 1. virtualenv + dependencies
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 2. install the Camoufox browser (needed only for the js engine)
./venv/bin/python -m camoufox fetch

# 3. run it
./tbrowse "https://www.google.com"     # interactive TUI
./tbr     "https://www.google.com"     # one-shot to text
```

`tbrowse` and `tbr` are little shell wrappers that call the venv Python — they
work from anywhere, no install step required (just keep them alongside
`browse.py` / `tbr.py`).

### Browser location

The Camoufox executable is located automatically (env
`CAMOUFOX_BIN` → `~/.cache/camoufox/browsers/*/*/camoufox-bin` → other common
cache dirs). If your browser lives somewhere unusual, set:

```bash
export CAMOUFOX_BIN=/path/to/camoufox-bin
```

## Usage

### Interactive browser — `tbrowse`

```
Up / Down        move the pointer (">" cursor) up / down one line
j / k            move pointer down / up (vim-style)
PgUp / PgDn      move pointer a page     Space  page down
Home / End / g   jump pointer to top / bottom
Enter            open the link under the pointer
Tab / Shift+Tab  jump pointer to next / previous link
n / p            jump pointer to next / previous link
Left / b         go back to previous page
f                forward in history
u / o            prompt for a URL
r                reload current page
q / ESC          quit
```

### One-shot CLI — `tbr`

```
tbr <url>                 render main readable text (js engine)
tbr <url> --no-js         fast plain fetch, bypass JS
tbr <url> --links         list page links (numbered)
tbr <url> --title         print only the title
tbr <url> -s keyword         keep only lines containing text
tbr <url> -o out.txt      write result to a file
tbr <url> --json          structured JSON {title, url, text, links}
tbr <url> -c '.articlebody,#content'   use a CSS selector for main text
tbr <url> -j              force the js engine
```

## Project layout

```
tbr.py       one-shot CLI + the two fetch engines
browse.py    interactive TUI browser (curses)
session.py   persistent fetch session (shared Camoufox across pages)
nav.py       HTML -> wrapped lines with inline, selectable link segments
extract.py   readable-text extraction & link harvesting (BeautifulSoup)
paths.py     portable Camoufox binary discovery
tbr, tbrowse shell launchers
```

## A note on the `js` engine

The Camoufox browser is a real, fully-fledged browser — using it on third-party
sites is subject to each site's terms of service. This project is provided as
a personal reading tool; please respect robots/ToS and don't use it to scrape
services that prohibit automated access.

## License

[MIT](./LICENSE).

_This project is for legitimate personal reading use. It is not affiliated
with twkan.com or Cloudflare._
