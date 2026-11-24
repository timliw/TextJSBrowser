"""
tbr interactive browser — a text-mode browser like lynx/w3m but with a real
JS engine (Camoufox) so Cloudflare-protected sites work.

A cursor (pointer) sits on a line of the document. Up/Down move it; the view
follows it. When the cursor is on a link, Enter opens that link.

Keys:
  Up / Down        move the pointer up / down one line
  j / k            move pointer down / up (vim-style)
  PgUp / PgDn / Space  move pointer a page at a time
  Home / End / g   jump pointer to top / bottom
  Enter            open the link under the pointer
  Tab / Shift+Tab  jump pointer to next / previous link
  n / p            jump pointer to next / previous link
  Left / b         go back to previous page
  f                forward in history
  u / o            open URL prompt
  r                reload current page
  q                quit
"""
import argparse
import curses
import sys

from nav import build_flow
from session import FetchSession

KEY_BTAB = getattr(curses, "KEY_BTAB", 353)


class Browser:
    def __init__(self, engine, session, start_url):
        self.engine = engine
        self.session = session
        self.start_url = start_url
        self.history = []        # list of {url, page}
        self.hpos = -1
        self.cursor = 0          # doc line the pointer sits on
        self.top = 0             # scroll offset (first visible doc line)
        self.focus = -1          # active link under the cursor
        self.width = 100
        self.height = 20
        self.status = ""
        self.error = ""

    # ------------------------------------------------------------- loading
    def load(self, url, add_history=True):
        self.status = f"Loading {url} ..."
        try:
            final_url, raw = self.session.fetch(url)
        except Exception as e:
            self.error = f"fetch error: {e}"
            self.status = f"Error loading {url}"
            return
        html = raw.decode("utf-8", "ignore")
        f_url = (final_url and final_url) or url
        page = build_flow(html, f_url, self.width)
        if add_history:
            if self.hpos < len(self.history) - 1:
                self.history = self.history[: self.hpos + 1]
            self.history.append({"url": url, "page": page})
            self.hpos = len(self.history) - 1
        self._move_to_entry()
        self.error = ""
        self.status = f"{len(page.links)} links | {page.title}"

    def _move_to_entry(self):
        p = self.page()
        # start the pointer at the main content (dense prose block)
        self.cursor = p.content_start if p else 0
        self._refresh_focus()
        self._center_cursor()

    def back(self):
        if self.hpos > 0:
            self.hpos -= 1
            self._move_to_entry()
            self.status = self._entry_status()

    def forward(self):
        if self.hpos < len(self.history) - 1:
            self.hpos += 1
            self._move_to_entry()
            self.status = self._entry_status()

    def _entry_status(self):
        p = self.page()
        return f"{len(p.links)} links | {p.title}" if p else ""

    def page(self):
        if 0 <= self.hpos < len(self.history):
            return self.history[self.hpos]["page"]
        return None

    # -------------------------------------------------------------- cursor
    def _nlines(self):
        p = self.page()
        return len(p.lines) if p else 0

    def move_cursor(self, d):
        """Move pointer by d lines (clamped), keeping it in view."""
        n = self._nlines()
        if n == 0:
            return
        self.cursor = max(0, min(n - 1, self.cursor + d))
        self._refresh_focus()
        self._center_cursor()

    def goto_cursor(self, idx):
        n = self._nlines()
        if n == 0:
            return
        self.cursor = max(0, min(n - 1, idx))
        self._refresh_focus()
        self._center_cursor()

    def focus_link_index(self, direction=1):
        """Move pointer to the next/previous link in document order."""
        page = self.page()
        if not page or not page.links:
            return
        n = len(page.links)
        row = self.cursor
        if direction > 0:
            # next link strictly after the cursor line, or later on the same
            # line (advancing past the current focus)
            i = None
            for j, lk in enumerate(page.links):
                if lk.row > row or (lk.row == row and j > self.focus):
                    i = j
                    break
            if i is None:
                i = 0  # wrap to the first link
        else:
            i = None
            for j in range(n - 1, -1, -1):
                if page.links[j].row < row or \
                   (page.links[j].row == row and j < self.focus):
                    i = j
                    break
            if i is None:
                i = n - 1  # wrap to the last link
        lk = page.links[i]
        self.goto_cursor(lk.row)
        self.focus = i

    def _refresh_focus(self):
        """Set `focus` to the link on the current cursor line (or -1)."""
        page = self.page()
        if not page or not page.links:
            self.focus = -1
            return
        for i, lk in enumerate(page.links):
            if lk.row == self.cursor:
                self.focus = i
                return
        self.focus = -1

    def _center_cursor(self):
        """Scroll so the cursor is roughly centered in the viewport."""
        n = self._nlines()
        vh = self.height
        if n <= vh:
            self.top = 0
            return
        target = self.cursor - vh // 2
        self.top = max(0, min(n - vh, target))

    # -------------------------------------------------------------- drawing
    def scroll_pct(self):
        """Percentage of the way down the page (0-100)."""
        page = self.page()
        if not page or not page.lines:
            return 0
        n = len(page.lines)
        if n <= self.height:
            return 100
        frac = self.top / max(1, n - self.height)
        return max(0, min(100, round(frac * 100)))

    def draw_main(self, win, h, row_offset=1):
        """Draw the page body onto `win` from `row_offset`.

        A gutter column at the left marks the cursor line with `>`; the link
        under the cursor (if any) is highlighted (reverse). Drawn directly on
        the same window as header/status to avoid an overlapping-window wipe.
        """
        page = self.page()
        w = self.width
        if page is None:
            try:
                win.addnstr(row_offset, 0, "Nothing to display. Press u to open a URL.", w)
            except curses.error:
                pass
            return

        nlines = len(page.lines)
        gutter = 1                       # left column reserved for the pointer
        sb_col = w - 1                   # right-edge vertical scrollbar column

        # scrollbar thumb
        sb_rows = h
        thumb_len = max(2, round(sb_rows * min(1.0, h / max(1, nlines))))
        if nlines <= h:
            thumb_top = 0
        else:
            frac = self.top / max(1, nlines - h)
            thumb_top = min(sb_rows - thumb_len, round(frac * (sb_rows - thumb_len)))

        for screen_row in range(h):
            doc_row = self.top + screen_row
            # right-edge scrollbar
            is_thumb = thumb_top <= screen_row < thumb_top + thumb_len
            try:
                win.addch(row_offset + screen_row, sb_col,
                          "│" if is_thumb else "·",
                          curses.A_REVERSE if is_thumb else curses.A_DIM)
            except curses.error:
                pass
            # pointer gutter
            here = (doc_row == self.cursor)
            try:
                win.addch(row_offset + screen_row, 0,
                          ">" if here else "·",
                          curses.A_REVERSE if here else curses.A_DIM)
            except curses.error:
                pass
            if doc_row >= nlines:
                continue
            body_col = gutter
            model_col = 0
            for seg in page.lines[doc_row]:
                if body_col >= sb_col:
                    break
                attr = curses.A_BOLD if seg.kind == "link" else curses.A_NORMAL
                if seg.kind == "link" and self.focus >= 0 and \
                   self.focus < len(page.links) and \
                   page.links[self.focus].row == doc_row and \
                   page.links[self.focus].col == model_col:
                    attr = curses.A_REVERSE | curses.A_BOLD
                shown = seg.text[: max(0, sb_col - body_col)]
                try:
                    win.addnstr(row_offset + screen_row, body_col, shown,
                                sb_col - body_col, attr)
                except curses.error:
                    pass
                body_col += seg.width
                model_col += seg.width

    # --------------------------------------------------------------- input
    def handle(self, ch):
        page = self.page()
        hpage = max(1, self.height - 1)

        if ch in (ord("q"), 27):            # q / ESC
            return False

        # --- pointer movement: Up/Down move the cursor line by line
        if ch in (curses.KEY_DOWN, ord("j")):
            self.move_cursor(1)
        elif ch in (curses.KEY_UP, ord("k")):
            self.move_cursor(-1)
        elif ch in (curses.KEY_NPAGE, ord(" "), 12):   # PgDn/Space/Ctrl-L
            self.goto_cursor(self.cursor + hpage)
        elif ch == curses.KEY_PPAGE:
            self.goto_cursor(self.cursor - hpage)
        elif ch in (curses.KEY_HOME, ord("g")):
            self.goto_cursor(0)
        elif ch == curses.KEY_END:
            self.goto_cursor(self._nlines())

        # --- jump pointer to next/previous link
        elif ch == KEY_BTAB or ch == ord("p"):
            self.focus_link_index(-1)
        elif ch in (9, ord("n"), ord("l")):   # Tab / n / l
            self.focus_link_index(1)

        # --- open / history
        elif ch in (ord("\n"), 10, 13, curses.KEY_ENTER):
            if page and 0 <= self.focus < len(page.links):
                self.load(page.links[self.focus].href)
            elif page:
                self.status = "No link under the cursor on this line."
        elif ch in (curses.KEY_LEFT, ord("b")):
            self.back()
        elif ch == ord("f"):
            self.forward()

        # --- reload / url
        elif ch == ord("r"):
            if page:
                self.load(page.url, add_history=False)
        elif ch in (ord("u"), ord("o")):
            return "url"

        return True


def run(stdscr, engine, start_url):
    curses.curs_set(0)
    curses.use_default_colors()
    stdscr.keypad(True)

    with FetchSession(engine) as session:
        br = Browser(engine, session, start_url)

        def redraw():
            h, w = stdscr.getmaxyx()
            br.height = h - 2
            br.width = w - 1
            stdscr.erase()
            # header
            p = br.page()
            title = p.title if p else start_url
            try:
                stdscr.addnstr(0, 0, f" {title}", w - 1, curses.A_REVERSE | curses.A_BOLD)
            except curses.error:
                pass
            # main body — on stdscr directly (no overlapping window)
            br.draw_main(stdscr, br.height, row_offset=1)
            # status bar: scroll % + cursor line + active link text
            st = br.error or br.status or f"{len(p.links)} links" if p else (br.error or br.status)
            focus_txt = ""
            if p and 0 <= br.focus < len(p.links):
                focus_txt = f"  LINK:[{p.links[br.focus].text[:18]}]"
            nav = f"[{br.hpos+1}/{len(br.history)}] {br.scroll_pct()}% line{br.cursor}"
            line = f" {st}{focus_txt}  {nav}  Up/Dn:move Enter:open L:back u:url q:quit"
            try:
                stdscr.addnstr(h - 1, 0, line[: w - 2], w - 2, curses.A_REVERSE)
            except curses.error:
                pass
            stdscr.refresh()

        br.load(start_url)
        redraw()

        while True:
            c = stdscr.getch()
            if c == -1:
                continue
            if c == -2:   # KEY_RESIZE
                redraw()
                continue
            result = br.handle(c)
            if result is False:
                break
            if result == "url":
                curses.echo()
                curses.curs_set(1)
                stdscr.move(0, 0)
                stdscr.clrtoeol()
                stdscr.addstr(0, 0, "URL: ")
                stdscr.refresh()
                try:
                    new = stdscr.getstr(0, 5, 400).decode("utf-8", "ignore")
                except Exception:
                    new = ""
                curses.noecho()
                curses.curs_set(0)
                if new.strip():
                    br.load(new.strip())
            redraw()
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="tbrowse", description="tbr interactive text browser")
    p.add_argument("url", nargs="?", default="https://example.com",
                   help="start URL (default: example.com)")
    p.add_argument("--engine", choices=["js", "plain"], default="js")
    a = p.parse_args(argv)
    try:
        curses.wrapper(run, a.engine, a.url)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
