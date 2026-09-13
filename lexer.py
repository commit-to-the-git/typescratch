"""Lexer for TypeScratch (.tysh) source.

Tokens:
    EXTENSION  'extension'
    WHEN       'when'
    IF ELSE REPEAT REPEAT_UNTIL FOREVER WHILE WAIT STOP DEF
    BROADCAST  'broadcast'
    AND OR NOT MOD
    TRUE FALSE
    S_KW       's'      (sprite declarator)
    B_KW       'b'      (backdrop declarator)
    LIST_KW    'list'   (list declarator)

    NAME       identifier  (letters, digits, _, -, !, ?)
    NUM        number (int or float)
    HEXCOLOR   #rrggbb
    STRING     "..." or '...'
    PATH       bare path (used after img=)

    LBRACE RBRACE LPAREN RPAREN LBRACKET RBRACKET
    COMMA  DOT
    PLUS MINUS STAR SLASH  GT LT
    ASSIGN (=)  EQ_EQ (==)  PLUS_EQ (+=)  MINUS_EQ (-=)  STAR_EQ (*=)  SLASH_EQ (/=)
    ASSIGN_ATTR   'xy=' 'dir=' 'size=' 'visible=' 'rot=' 'img=' 'costume=' 'warp='

    EOL  EOF

Strings in the .tysh source can be written *without* quotes - any
bare identifier (NAME) is treated as a potential string word in the
parser.  Use quotes only when you need a string that contains
operator-like characters (commas inside a single arg, parentheses,
etc.) or to force string interpretation of a name that is also a
declared variable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .errors import CompileError


@dataclass
class Token:
    type: str
    value: str
    line: int
    col: int

    def __repr__(self):
        return f"Tok({self.type},{self.value!r}@{self.line}:{self.col})"


KEYWORDS = {
    "extension": "EXTENSION",
    "when": "WHEN",
    "if": "IF",
    "else": "ELSE",
    "elif": "ELIF",
    "repeat": "REPEAT",
    "repeatUntil": "REPEAT_UNTIL",
    "forever": "FOREVER",
    "while": "WHILE",
    "forEach": "FOR_EACH",
    "foreach": "FOR_EACH",
    "allAtOnce": "ALL_AT_ONCE",
    "wait": "WAIT",
    "waitUntil": "WAIT_UNTIL",
    "stop": "STOP",
    "def": "DEF",
    "broadcast": "BROADCAST",
    "and": "AND",
    "or": "OR",
    "not": "NOT",
    "mod": "MOD",
    "true": "TRUE",
    "false": "FALSE",
    "sound": "SOUND_KW",
    "costume": "COSTUME_KW",
    "private": "PRIVATE_KW",
}

# Attribute prefixes that bind tightly to '='
ATTR_PREFIXES = ("xy", "dir", "size", "visible", "rot", "img", "costume", "warp")

# Characters allowed inside an identifier (besides letters and digits).
# Note: `-` is NOT included so that `X--` and `X++` work as decrement/increment.
# Use `_` or camelCase for multi-word identifiers.
IDENT_EXTRA = "_!?':"
# `'` is allowed so that names like "don't" work as bare text.  The lexer
# only treats `'` as a string-quote when it appears at the start of an
# expression (see is_string_start below).
# `:` is allowed so that names like "micro:bit" work as a single token.

# Characters that stop a bare-text/PATH scan.
STOP_CHARS = set(",(){}[]<>=+-*/# \n\r\t.")


def tokenize(src: str, filename: str = "<tysh>") -> List[Token]:
    tokens: List[Token] = []
    i = 0
    line = 1
    col = 1
    n = len(src)
    expecting_path = False  # set after img=

    def err(msg, ln, cl):
        raise CompileError(msg, ln, cl, _snippet(src, ln), filename)

    while i < n:
        c = src[i]

        # --- after img=, read a path until whitespace or newline ---
        if expecting_path:
            # skip whitespace (but not newlines - allow path on same line only)
            if c in " \t":
                i += 1
                col += 1
                continue
            if c == "\n":
                err("img= attribute requires a path on the same line", line, col)
            j = i
            while j < n and src[j] not in " \n\r\t":
                j += 1
            tokens.append(Token("PATH", src[i:j], line, col))
            col += j - i
            i = j
            expecting_path = False
            continue

        # --- newline ---
        if c == "\n":
            tokens.append(Token("EOL", c, line, col))
            i += 1
            line += 1
            col = 1
            continue

        # --- whitespace ---
        if c in " \t\r":
            i += 1
            col += 1
            continue

        # --- line comment ---
        # Comments start with // but // is also floor division.
        # Rule: // is a comment ONLY if the previous token on this line
        # was an EOL (i.e. only whitespace before us on this line).
        # Otherwise it's floor division.
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            # Check the previous token - if it's EOL (or no tokens yet),
            # this is a comment.  If it's anything else, it's floor div.
            prev_tok = tokens[-1] if tokens else None
            is_comment = (prev_tok is None or prev_tok.type == "EOL")
            if is_comment:
                while i < n and src[i] != "\n":
                    i += 1
                continue
            # It's floor division - fall through to operator handling

        # --- braces / parens / brackets / comma / dot ---
        simple = {
            "{": "LBRACE", "}": "RBRACE",
            "(": "LPAREN", ")": "RPAREN",
            "[": "LBRACKET", "]": "RBRACKET",
            ",": "COMMA", ".": "DOT",
        }
        if c in simple:
            tokens.append(Token(simple[c], c, line, col))
            i += 1; col += 1; continue

        # --- operators with possible = ---
        if c == "+":
            if i + 1 < n and src[i + 1] == "=":
                tokens.append(Token("PLUS_EQ", "+=", line, col)); i += 2; col += 2; continue
            if i + 1 < n and src[i + 1] == "+":
                tokens.append(Token("PLUS_PLUS", "++", line, col)); i += 2; col += 2; continue
            tokens.append(Token("PLUS", "+", line, col)); i += 1; col += 1; continue
        if c == "-":
            if i + 1 < n and src[i + 1] == "=":
                tokens.append(Token("MINUS_EQ", "-=", line, col)); i += 2; col += 2; continue
            if i + 1 < n and src[i + 1] == "-":
                tokens.append(Token("MINUS_MINUS", "--", line, col)); i += 2; col += 2; continue
            tokens.append(Token("MINUS", "-", line, col)); i += 1; col += 1; continue
        if c == "*":
            if i + 1 < n and src[i + 1] == "=":
                tokens.append(Token("STAR_EQ", "*=", line, col)); i += 2; col += 2; continue
            tokens.append(Token("STAR", "*", line, col)); i += 1; col += 1; continue
        if c == "/":
            if i + 1 < n and src[i + 1] == "=":
                tokens.append(Token("SLASH_EQ", "/=", line, col)); i += 2; col += 2; continue
            # Check for // (floor division) - only if previous token is expression-like
            if i + 1 < n and src[i + 1] == "/":
                tokens.append(Token("FLOOR_DIV", "//", line, col)); i += 2; col += 2; continue
            tokens.append(Token("SLASH", "/", line, col)); i += 1; col += 1; continue
        if c == ">":
            if i + 1 < n and src[i + 1] == "=":
                tokens.append(Token("GTE", ">=", line, col)); i += 2; col += 2; continue
            tokens.append(Token("GT", ">", line, col)); i += 1; col += 1; continue
        if c == "<":
            if i + 1 < n and src[i + 1] == "=":
                tokens.append(Token("LTE", "<=", line, col)); i += 2; col += 2; continue
            tokens.append(Token("LT", "<", line, col)); i += 1; col += 1; continue
        if c == "!":
            if i + 1 < n and src[i + 1] == "=":
                tokens.append(Token("NEQ", "!=", line, col)); i += 2; col += 2; continue
            tokens.append(Token("BANG", "!", line, col)); i += 1; col += 1; continue
        if c == "&":
            tokens.append(Token("AMP", "&", line, col)); i += 1; col += 1; continue
        if c == "=":
            if i + 1 < n and src[i + 1] == "=":
                tokens.append(Token("EQ_EQ", "==", line, col)); i += 2; col += 2; continue
            tokens.append(Token("ASSIGN", "=", line, col)); i += 1; col += 1; continue

        # --- hex color ---
        if c == "#":
            j = i + 1
            while j < n and src[j] in "0123456789abcdefABCDEF":
                j += 1
            if j - i == 7:
                tokens.append(Token("HEXCOLOR", src[i:j], line, col))
                col += j - i; i = j; continue
            err("invalid hex color (expected #rrggbb)", line, col)

        # --- quoted string ---
        # Only treat ' or " as a string-quote when it's at the start of
        # an expression - i.e., the previous non-EOL token is one of:
        #   LPAREN, COMMA, LBRACKET, ASSIGN, PLUS_EQ, MINUS_EQ, STAR_EQ,
        #   SLASH_EQ, GT, LT, ASSIGN_ATTR, EOL, or no previous token.
        # Otherwise ' is part of an identifier (e.g. `don't`).
        prev_meaningful = None
        for k in range(len(tokens) - 1, -1, -1):
            if tokens[k].type != "EOL":
                prev_meaningful = tokens[k]
                break
        is_string_start = (
            prev_meaningful is None
            or prev_meaningful.type in (
                "LPAREN", "COMMA", "LBRACKET", "ASSIGN", "PLUS_EQ",
                "MINUS_EQ", "STAR_EQ", "SLASH_EQ", "GT", "LT",
                "ASSIGN_ATTR", "AND", "OR", "NOT", "PLUS", "MINUS",
                "STAR", "SLASH", "MOD", "EQ_EQ", "DOT",
            )
        )
        if c == '"' or (c == "'" and is_string_start):
            quote = c
            start_line, start_col = line, col
            j = i + 1
            buf = []
            while j < n and src[j] != quote:
                if src[j] == "\\" and j + 1 < n:
                    nxt = src[j + 1]
                    buf.append({"n": "\n", "t": "\t", "r": "\r",
                                 '"': '"', "'": "'", "\\": "\\"}.get(nxt, nxt))
                    j += 2
                else:
                    buf.append(src[j])
                    j += 1
            if j >= n:
                err("unterminated string literal", start_line, start_col)
            tokens.append(Token("STRING", "".join(buf), start_line, start_col))
            i = j + 1
            col += (j - i) + 2
            continue

        # --- number ---
        if c.isdigit():
            j = i
            while j < n and (src[j].isdigit() or src[j] == "."):
                j += 1
            tokens.append(Token("NUM", src[i:j], line, col))
            col += j - i
            i = j
            continue

        # --- identifier / keyword ---
        if c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] in IDENT_EXTRA):
                j += 1
            # Consume trailing dots that are NOT namespace separators.
            # A dot is a namespace separator only if it's followed by an
            # identifier char (so `pen.Down` stays as NAME + DOT + NAME,
            # but `Hmm...` becomes NAME "Hmm...").
            while j < n and src[j] == ".":
                # find the end of the dot run
                k = j
                while k < n and src[k] == ".":
                    k += 1
                if k < n and (src[k].isalpha() or src[k] == "_"):
                    # dot is a namespace separator - stop
                    break
                # dots are trailing text - consume them
                j = k
            word = src[i:j]

            # attribute assignment prefix?  word=
            if word in ATTR_PREFIXES and j < n and src[j] == "=":
                tokens.append(Token("ASSIGN_ATTR", word + "=", line, col))
                col += j - i + 1
                i = j + 1
                if word == "img":
                    expecting_path = True
                continue

            if word in KEYWORDS:
                tokens.append(Token(KEYWORDS[word], word, line, col))
            else:
                tokens.append(Token("NAME", word, line, col))
            col += j - i
            i = j
            continue

        # --- fallback: bare text ---
        # anything not handled above is eaten as TEXT until a stop char.
        j = i
        while j < n and src[j] not in STOP_CHARS:
            j += 1
        if j == i:
            err(f"unexpected character {c!r}", line, col)
        text = src[i:j].rstrip()
        tokens.append(Token("TEXT", text, line, col))
        col += j - i
        i = j

    tokens.append(Token("EOF", "", line, col))
    return tokens


def _snippet(src, ln):
    lines = src.splitlines()
    if 1 <= ln <= len(lines):
        return lines[ln - 1]
    return None
