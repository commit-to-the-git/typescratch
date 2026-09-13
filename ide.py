"""TypeScratch IDE - a terminal-based code editor with syntax highlighting.

Run with: typescratch ide [file.tysh]
     or:  python -m typescratch ide [file.tysh]

Features:
  - Syntax highlighting (keywords, strings, numbers, comments, colors)
  - Auto-indentation (matches the previous line's indent, adds extra after {)
  - Compile button (F5): compiles to .sb3
  - Verify button (F6): checks syntax without compiling
  - Status bar with line/column info
  - Save (Ctrl+S), Open (Ctrl+O), Quit (Ctrl+Q)
  - Line numbers
"""

import os
import sys
import curses
import curses.ascii
from typing import List, Optional, Tuple

from . import __version__
from .errors import CompileError, SyntaxOops, ForgotOops, ArgumentOops


# Syntax highlighting color pairs
COLOR_COMMENT = 1
COLOR_KEYWORD = 2
COLOR_STRING = 3
COLOR_NUMBER = 4
COLOR_BRACE = 5
COLOR_OPERATOR = 6
COLOR_COLOR = 7
COLOR_NORMAL = 8
COLOR_STATUS = 9
COLOR_ERROR = 10
COLOR_LOGO = 11

# Keywords for highlighting
KEYWORDS = {
    "when", "if", "else", "elif", "repeat", "repeatUntil", "forever",
    "while", "forEach", "foreach", "allAtOnce", "wait", "waitUntil",
    "stop", "def", "broadcast", "and", "or", "not", "mod", "true", "false",
    "extension", "list",
}


def init_colors():
    curses.start_color()
    if curses.COLORS < 8:
        return False
    curses.init_pair(COLOR_COMMENT, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(COLOR_KEYWORD, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(COLOR_STRING, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(COLOR_NUMBER, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
    curses.init_pair(COLOR_BRACE, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(COLOR_OPERATOR, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(COLOR_COLOR, curses.COLOR_BLUE, curses.COLOR_BLACK)
    curses.init_pair(COLOR_NORMAL, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(COLOR_STATUS, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(COLOR_ERROR, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(COLOR_LOGO, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    return True


class IDE:
    def __init__(self, stdscr, filename: Optional[str] = None):
        self.stdscr = stdscr
        self.filename = filename or "untitled.tysh"
        self.lines: List[str] = [""]
        self.cursor_y = 0
        self.cursor_x = 0
        self.scroll_y = 0
        self.scroll_x = 0
        self.modified = False
        self.status_msg = ""
        self.status_is_error = False
        self.show_logo = True
        self.has_colors = False

        if filename and os.path.isfile(filename):
            self.load_file(filename)

    def load_file(self, filename: str):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
            self.lines = content.split("\n")
            if not self.lines:
                self.lines = [""]
            self.filename = filename
            self.modified = False
            self.set_status(f"Loaded {filename}")
        except Exception as e:
            self.set_status(f"Error loading: {e}", error=True)

    def save_file(self):
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                f.write("\n".join(self.lines))
            self.modified = False
            self.set_status(f"Saved {self.filename}")
        except Exception as e:
            self.set_status(f"Error saving: {e}", error=True)

    def set_status(self, msg: str, error: bool = False):
        self.status_msg = msg
        self.status_is_error = error

    def get_indent(self, line: str) -> str:
        """Get the leading whitespace of a line."""
        indent = ""
        for ch in line:
            if ch in " \t":
                indent += ch
            else:
                break
        return indent

    def insert_char(self, ch: str):
        line = self.lines[self.cursor_y]
        self.lines[self.cursor_y] = line[:self.cursor_x] + ch + line[self.cursor_x:]
        self.cursor_x += 1
        self.modified = True

    def insert_newline(self):
        line = self.lines[self.cursor_y]
        before = line[:self.cursor_x]
        after = line[self.cursor_x:]
        self.lines[self.cursor_y] = before
        self.lines.insert(self.cursor_y + 1, after)
        self.cursor_y += 1
        # Auto-indent
        indent = self.get_indent(before)
        # Add extra indent if line ends with {
        stripped = before.rstrip()
        if stripped.endswith("{"):
            indent += "  "
        self.lines[self.cursor_y] = indent + after
        self.cursor_x = len(indent)
        self.modified = True

    def delete_char(self):
        if self.cursor_x > 0:
            line = self.lines[self.cursor_y]
            self.lines[self.cursor_y] = line[:self.cursor_x - 1] + line[self.cursor_x:]
            self.cursor_x -= 1
            self.modified = True
        elif self.cursor_y > 0:
            prev_line = self.lines[self.cursor_y - 1]
            curr_line = self.lines[self.cursor_y]
            self.cursor_x = len(prev_line)
            self.lines[self.cursor_y - 1] = prev_line + curr_line
            del self.lines[self.cursor_y]
            self.cursor_y -= 1
            self.modified = True

    def move_cursor(self, dy: int, dx: int):
        self.cursor_y = max(0, min(len(self.lines) - 1, self.cursor_y + dy))
        self.cursor_x = max(0, min(len(self.lines[self.cursor_y]), self.cursor_x + dx))

    def get_text(self) -> str:
        return "\n".join(self.lines)

    def compile(self):
        """Compile the current code to .sb3."""
        from . import source
        text = self.get_text()
        out_path = os.path.splitext(self.filename)[0] + ".sb3"
        try:
            import io
            import contextlib
            stderr_capture = io.StringIO()
            with contextlib.redirect_stderr(stderr_capture):
                sb3 = source(text, out=out_path, filename=self.filename)
            warnings = stderr_capture.getvalue().strip()
            size = os.path.getsize(out_path)
            msg = f"Compiled: {out_path} ({size} bytes)"
            if warnings:
                msg += " | " + warnings.split("\n")[0]
            self.set_status(msg)
        except (SyntaxOops, ForgotOops, ArgumentOops, CompileError) as e:
            self.set_status(str(e), error=True)
        except Exception as e:
            self.set_status(f"Error: {e}", error=True)

    def verify(self):
        """Check syntax without compiling."""
        from . import compile_source
        text = self.get_text()
        try:
            import io
            import contextlib
            stderr_capture = io.StringIO()
            with contextlib.redirect_stderr(stderr_capture):
                project, assets = compile_source(text, filename=self.filename)
            warnings = stderr_capture.getvalue().strip()
            blocks = sum(len(t.get("blocks", {})) for t in project["targets"])
            targets = len(project["targets"])
            msg = f"OK: {targets} targets, {blocks} blocks"
            if warnings:
                msg += " | " + warnings.split("\n")[0]
            self.set_status(msg)
        except (SyntaxOops, ForgotOops, ArgumentOops, CompileError) as e:
            self.set_status(str(e), error=True)
        except Exception as e:
            self.set_status(f"Error: {e}", error=True)

    def draw_line(self, y: int, line_num: int, line: str, max_width: int):
        """Draw a single line with syntax highlighting."""
        # Line number
        ln = f"{line_num + 1:4d} "
        self.stdscr.addstr(y, 0, ln, curses.color_pair(COLOR_STATUS))

        # Syntax highlight the line content
        x = len(ln) - self.scroll_x
        if x < 0:
            # Line is scrolled past
            line = line[-x:]
            x = len(ln)
        else:
            line = line[self.scroll_x:]

        i = 0
        while i < len(line) and x < max_width:
            ch = line[i]

            # Comment: // at start of line (after whitespace only)
            if ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                # Check if this is a comment (start of line after whitespace)
                prefix = line[:i]
                if prefix.strip() == "":
                    rest = line[i:min(len(line), i + max_width - x)]
                    if self.has_colors:
                        self.stdscr.addstr(y, x, rest, curses.color_pair(COLOR_COMMENT))
                    else:
                        self.stdscr.addstr(y, x, rest)
                    break
                else:
                    # Floor division operator
                    if self.has_colors:
                        self.stdscr.addstr(y, x, "//", curses.color_pair(COLOR_OPERATOR))
                    else:
                        self.stdscr.addstr(y, x, "//")
                    x += 2
                    i += 2
                    continue

            # String: "..."
            if ch == '"':
                end = line.find('"', i + 1)
                if end == -1:
                    end = len(line)
                else:
                    end += 1
                s = line[i:min(end, i + max_width - x)]
                if self.has_colors:
                    self.stdscr.addstr(y, x, s, curses.color_pair(COLOR_STRING))
                else:
                    self.stdscr.addstr(y, x, s)
                x += len(s)
                i = end
                continue

            # Hex color: #rrggbb
            if ch == '#' and i + 6 < len(line):
                hexpart = line[i:i + 7]
                if all(c in '0123456789abcdefABCDEF' for c in hexpart[1:]):
                    s = hexpart[:min(7, max_width - x)]
                    if self.has_colors:
                        self.stdscr.addstr(y, x, s, curses.color_pair(COLOR_COLOR))
                    else:
                        self.stdscr.addstr(y, x, s)
                    x += len(s)
                    i += 7
                    continue

            # Number
            if ch.isdigit():
                j = i
                while j < len(line) and (line[j].isdigit() or line[j] == '.'):
                    j += 1
                s = line[i:min(j, i + max_width - x)]
                if self.has_colors:
                    self.stdscr.addstr(y, x, s, curses.color_pair(COLOR_NUMBER))
                else:
                    self.stdscr.addstr(y, x, s)
                x += len(s)
                i = j
                continue

            # Keyword / identifier
            if ch.isalpha() or ch == '_':
                j = i
                while j < len(line) and (line[j].isalnum() or line[j] in "_!?':"):
                    j += 1
                word = line[i:j]
                s = word[:max_width - x]
                if word in KEYWORDS:
                    color = COLOR_KEYWORD
                elif self.has_colors:
                    color = COLOR_NORMAL
                else:
                    color = None
                if color is not None:
                    self.stdscr.addstr(y, x, s, curses.color_pair(color))
                else:
                    self.stdscr.addstr(y, x, s)
                x += len(s)
                i = j
                continue

            # Braces
            if ch in "{}":
                if self.has_colors:
                    self.stdscr.addstr(y, x, ch, curses.color_pair(COLOR_BRACE) | curses.A_BOLD)
                else:
                    self.stdscr.addstr(y, x, ch)
                x += 1
                i += 1
                continue

            # Operators
            if ch in "+-*/%<>=!&|":
                if self.has_colors:
                    self.stdscr.addstr(y, x, ch, curses.color_pair(COLOR_OPERATOR))
                else:
                    self.stdscr.addstr(y, x, ch)
                x += 1
                i += 1
                continue

            # Default
            try:
                self.stdscr.addstr(y, x, ch)
            except curses.error:
                pass
            x += 1
            i += 1

    def draw_logo(self, y: int):
        """Draw the ASCII art logo."""
        logo = [
            " ______              ____             __      __ ",
            "/_  __/_ _____  ___ / __/__________ _/ /_____/ / ",
            " / / / // / _ \\/ -_)\\ \\/ __/ __/ _ `/ __/ __/ _ \\",
            "/_/  \\_, / .__/\\__/___/\\__/_/  \\_,_/\\__/\\__/_//_/",
            "    /___/_/                                       ",
        ]
        for i, line in enumerate(logo):
            if y + i < curses.LINES - 2:
                try:
                    self.stdscr.addstr(y + i, 2, line, curses.color_pair(COLOR_LOGO) | curses.A_BOLD)
                except curses.error:
                    pass
        tagline = f"  v{__version__}  -  Press any key to start, or 'q' to quit"
        if y + len(logo) + 1 < curses.LINES - 2:
            try:
                self.stdscr.addstr(y + len(logo) + 1, 2, tagline, curses.color_pair(COLOR_NORMAL))
            except curses.error:
                pass

    def draw(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()

        # Adjust scroll
        if self.cursor_y < self.scroll_y:
            self.scroll_y = self.cursor_y
        if self.cursor_y >= self.scroll_y + h - 2:
            self.scroll_y = self.cursor_y - h + 3
        if self.cursor_x < self.scroll_x:
            self.scroll_x = self.cursor_x
        if self.cursor_x >= self.scroll_x + w - 6:
            self.scroll_x = self.cursor_x - w + 7

        # Draw logo screen if showing
        if self.show_logo:
            self.draw_logo(2)
            self.stdscr.refresh()
            return

        # Draw lines
        line_num_width = 5
        max_width = w - line_num_width
        visible_lines = h - 2  # minus status bar and border

        for i in range(visible_lines):
            line_idx = self.scroll_y + i
            if line_idx >= len(self.lines):
                break
            self.draw_line(i, line_idx, self.lines[line_idx], max_width + line_num_width)

        # Draw status bar
        status = f" {self.filename}"
        if self.modified:
            status += " *"
        status += f"  |  Line {self.cursor_y + 1}, Col {self.cursor_x + 1}"
        status += f"  |  F5=Compile  F6=Verify  Ctrl+S=Save  Ctrl+Q=Quit"
        status = status[:w - 1]
        try:
            self.stdscr.addstr(h - 2, 0, status.ljust(w - 1), curses.color_pair(COLOR_STATUS))
        except curses.error:
            pass

        # Draw message bar
        msg = self.status_msg[:w - 1]
        if self.status_is_error:
            try:
                self.stdscr.addstr(h - 1, 0, msg.ljust(w - 1), curses.color_pair(COLOR_ERROR) | curses.A_BOLD)
            except curses.error:
                pass
        else:
            try:
                self.stdscr.addstr(h - 1, 0, msg.ljust(w - 1), curses.color_pair(COLOR_NORMAL))
            except curses.error:
                pass

        # Position cursor
        cursor_screen_y = self.cursor_y - self.scroll_y
        cursor_screen_x = self.cursor_x - self.scroll_x + line_num_width
        if 0 <= cursor_screen_y < h - 2 and cursor_screen_x < w:
            self.stdscr.move(cursor_screen_y, cursor_screen_x)

        self.stdscr.refresh()

    def run(self):
        self.has_colors = init_colors()
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)

        while True:
            self.draw()

            if self.show_logo:
                ch = self.stdscr.getch()
                if ch == ord('q') or ch == ord('Q'):
                    break
                self.show_logo = False
                continue

            ch = self.stdscr.getch()

            # Special keys
            if ch == curses.KEY_UP:
                self.move_cursor(-1, 0)
            elif ch == curses.KEY_DOWN:
                self.move_cursor(1, 0)
            elif ch == curses.KEY_LEFT:
                self.move_cursor(0, -1)
            elif ch == curses.KEY_RIGHT:
                self.move_cursor(0, 1)
            elif ch == curses.KEY_HOME or ch == 1:  # Ctrl+A
                self.cursor_x = 0
            elif ch == curses.KEY_END or ch == 5:  # Ctrl+E
                self.cursor_x = len(self.lines[self.cursor_y])
            elif ch == curses.KEY_PPAGE:  # Page Up
                self.move_cursor(-(curses.LINES - 4), 0)
            elif ch == curses.KEY_NPAGE:  # Page Down
                self.move_cursor(curses.LINES - 4, 0)
            elif ch == curses.KEY_BACKSPACE or ch == 127 or ch == 8:
                self.delete_char()
            elif ch == curses.KEY_ENTER or ch == 10 or ch == 13:
                self.insert_newline()
            elif ch == 9:  # Tab
                self.insert_char("  ")
            elif ch == curses.KEY_F0 + 5:  # F5 = Compile
                self.compile()
            elif ch == curses.KEY_F0 + 6:  # F6 = Verify
                self.verify()
            elif ch == 19:  # Ctrl+S = Save
                self.save_file()
            elif ch == 15:  # Ctrl+O = Open (just save status)
                self.set_status("Ctrl+O not implemented yet - use command line to open files")
            elif ch == 17:  # Ctrl+Q = Quit
                if self.modified:
                    self.set_status("Unsaved changes! Press Ctrl+Q again to quit without saving, or Ctrl+S to save first.")
                    ch2 = self.stdscr.getch()
                    if ch2 == 17:  # Ctrl+Q again
                        break
                else:
                    break
            elif ch == 12:  # Ctrl+L = toggle logo
                self.show_logo = True
            elif 32 <= ch <= 126:  # Printable ASCII
                self.insert_char(chr(ch))
            # Ignore other keys


def run_ide(filename: Optional[str] = None):
    """Launch the TypeScratch IDE."""
    try:
        import curses as _curses_test
    except ImportError:
        print("TypeScratch IDE requires the 'curses' module.")
        print("On Windows, install it with:  pip install windows-curses")
        print("On Linux/Mac, it's built into Python.")
        sys.exit(1)

    def main(stdscr):
        ide = IDE(stdscr, filename)
        ide.run()

    curses.wrapper(main)


# CLI entry point for `typescratch ide`
def main():
    filename = sys.argv[2] if len(sys.argv) > 2 else None
    run_ide(filename)


if __name__ == "__main__":
    main()
