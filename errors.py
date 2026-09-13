"""Errors and debug logging for TypeScratch.

Error types:

* SyntaxOops - syntax errors (missing braces, unknown tokens, etc.)
* ForgotOops - using something that was never defined (variable, custom
  block, broadcast, list)
* ArgumentOops - calling a custom block with the wrong number of arguments
* TypeMismatchOops - using a non-boolean where a boolean is expected
  (currently just a placeholder; Scratch has no real types)

All of these are subclasses of ``CompileError`` so existing
``except CompileError`` code still works.

The ``Debug`` logger is controlled by the ``--debug`` CLI flag.
"""

from __future__ import annotations

import sys
import difflib
from dataclasses import dataclass
from typing import Optional


class CompileError(Exception):
    """Base class for all TypeScratch compilation errors.

    Carries line/column info and a source snippet.
    """

    error_type = "CompileError"

    def __init__(self, message: str, line: int = 0, col: int = 0,
                 snippet: Optional[str] = None, file: Optional[str] = None):
        self.message = message
        self.line = line
        self.col = col
        self.snippet = snippet
        self.file = file
        loc = ""
        if line:
            loc = f" at line {line}"
            if col:
                loc += f":{col}"
        if file:
            loc += f" ({file})"
        etype = self.error_type
        text = f"{etype}{loc}: {message}"
        if snippet:
            text += f"\n  >> {snippet}"
        super().__init__(text)


class SyntaxOops(CompileError):
    """A syntax error - the source code is malformed."""
    error_type = "SyntaxOops"


class ForgotOops(CompileError):
    """You forgot to define something.

    Raised when you use a variable, custom block, broadcast, or list
    that was never declared anywhere in the project.
    """
    error_type = "ForgotOops"


class ArgumentOops(CompileError):
    """A custom block was called with the wrong number of arguments."""
    error_type = "ArgumentOops"


class TypeMismatchOops(CompileError):
    """A value of the wrong type was used (e.g. non-boolean in a condition).

    Scratch doesn't have real types, but this catches obvious mistakes
    like putting a string where a boolean is expected.
    """
    error_type = "TypeMismatchOops"


def did_you_mean(name: str, candidates) -> str:
    """Return a ', Did you mean "X"?' string if there's a close match, else ''."""
    matches = difflib.get_close_matches(name, list(candidates), n=1, cutoff=0.5)
    if matches:
        return f', Did you mean "{matches[0]}"?'
    return ""


def _fmt(msg: str) -> None:
    sys.stderr.write(msg.rstrip() + "\n")
    sys.stderr.flush()


class Debug:
    """A tiny logger - either prints to stderr or stays silent."""

    def __init__(self, enabled: bool = False, stream=sys.stderr):
        self.enabled = enabled
        self.stream = stream

    def section(self, name: str) -> None:
        if not self.enabled:
            return
        _fmt(f"\n=== {name} ===")

    def line(self, msg: str) -> None:
        if not self.enabled:
            return
        _fmt(f"  {msg}")

    def dump(self, label: str, obj) -> None:
        if not self.enabled:
            return
        import json
        try:
            text = json.dumps(obj, indent=2, default=str)
        except Exception:
            text = repr(obj)
        _fmt(f"-- {label} --")
        for line in text.splitlines():
            _fmt(f"  {line}")
