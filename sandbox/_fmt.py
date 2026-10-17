"""Tiny ANSI/box-drawing helpers for the sandbox CLI."""

import os
import shutil
import sys

_ENABLED = sys.stdout.isatty() and os.getenv("NO_COLOR", "") == ""


def set_color(enabled: bool) -> None:
    global _ENABLED
    _ENABLED = enabled


def _w(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _ENABLED else s


def bold(s): return _w("1", s)
def dim(s): return _w("2", s)
def red(s): return _w("31", s)
def green(s): return _w("32", s)
def yellow(s): return _w("33", s)
def blue(s): return _w("34", s)
def magenta(s): return _w("35", s)
def cyan(s): return _w("36", s)


def width(default: int = 84) -> int:
    return max(60, min(shutil.get_terminal_size((default, 24)).columns, 110))


def banner(title: str, lines: list[str]) -> str:
    w = width()
    inner = w - 4
    out = [f"╭─ {bold(title)} " + "─" * max(0, inner - len(title) - 2) + "╮"]
    for line in lines:
        plain = _strip(line)
        out.append("│ " + line + " " * max(0, inner - len(plain)) + " │")
    out.append("╰" + "─" * (w - 2) + "╯")
    return "\n".join(out)


def section(idx: str, title: str, note: str = "") -> str:
    w = width()
    head = f"── [{idx}] {bold(title)} " + (f"{dim('· ' + note)} " if note else "")
    plain = _strip(head)
    return head + "─" * max(0, w - len(plain))


def box(text: str, indent: str = "  ") -> str:
    w = width() - len(indent)
    out = []
    for line in text.splitlines() or [""]:
        while len(line) > w:
            out.append(indent + line[:w])
            line = line[w:]
        out.append(indent + line)
    return "\n".join(out)


def table(headers: list[str], rows: list[list[str]], aligns: list[str] | None = None) -> str:
    cols = len(headers)
    aligns = aligns or ["l"] * cols
    widths = [len(_strip(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(_strip(cell)))
    sep = "  "
    head = sep.join(_pad(h, widths[i], aligns[i]) for i, h in enumerate(headers))
    out = [bold(head), dim(sep.join("─" * w for w in widths))]
    for row in rows:
        out.append(sep.join(_pad(c, widths[i], aligns[i]) for i, c in enumerate(row)))
    return "\n".join(out)


def _pad(s: str, w: int, align: str) -> str:
    pad = w - len(_strip(s))
    if align == "r":
        return " " * pad + s
    if align == "c":
        left = pad // 2
        return " " * left + s + " " * (pad - left)
    return s + " " * pad


def _strip(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] == "\033":
            while i < len(s) and s[i] != "m":
                i += 1
        else:
            out.append(s[i])
        i += 1
    return "".join(out)
