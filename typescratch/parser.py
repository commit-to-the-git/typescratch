"""Parser for TypeScratch (.tysh) source.

Turns a token stream into a Program AST.  See ast_nodes.py for the
grammar sketch.
"""

from __future__ import annotations

from typing import List, Optional, Any

from . import ast_nodes as A
from . import blocks as B
from .errors import CompileError, did_you_mean
from .lexer import tokenize, Token


class Parser:
    def __init__(self, tokens: List[Token], filename: str = "<tysh>"):
        self.toks = tokens
        self.pos = 0
        self.filename = filename
        # Per-target scope of variables/lists known to exist (used to
        # resolve BareName -> VarRef vs StringLit in expressions).
        self.current_vars: set = set()
        self.current_lists: set = set()

    # ---- token helpers ----
    def peek(self, off=0) -> Token:
        i = self.pos + off
        if i >= len(self.toks):
            return self.toks[-1]
        return self.toks[i]

    def next(self) -> Token:
        t = self.toks[self.pos]
        if self.pos < len(self.toks) - 1:
            self.pos += 1
        return t

    def at(self, *types) -> bool:
        return self.peek().type in types

    def eat(self, ttype: str, what: Optional[str] = None) -> Token:
        t = self.peek()
        if t.type != ttype:
            self.err(f"expected {what or ttype}, got {t.type} ({t.value!r})", t)
        return self.next()

    def skip_eol(self) -> None:
        while self.at("EOL"):
            self.next()

    def err(self, msg: str, t: Optional[Token] = None) -> None:
        t = t or self.peek()
        raise CompileError(msg, t.line, t.col, None, self.filename)

    def _is_at_line_start(self) -> bool:
        """True if the current token is the first non-EOL token on its line."""
        cur = self.peek()
        if self.pos == 0:
            return True
        # Walk backwards looking for the previous non-EOL token on the same line.
        # If we find one on the same line, we're NOT at line start.
        # EOL tokens have a newline value; their line is the line BEFORE the newline.
        # The current token's line is where it appears.
        i = self.pos - 1
        while i >= 0:
            prev = self.toks[i]
            if prev.type == "EOL":
                # prev.line is the line of the newline character.
                # If prev.line < cur.line, then cur is on a new line.
                if prev.line < cur.line:
                    return True
                # else keep looking back
                i -= 1
                continue
            # non-EOL token
            if prev.line < cur.line:
                return True
            return False
        return True

    # ---- entry ----
    def parse_program(self) -> A.Program:
        program = A.Program()
        # We accumulate sprite/backdrop targets.  The "stage" target is
        # created on demand when the first backdrop is declared or when
        # any target needs to hold stage-scoped variables.
        stage: Optional[A.Target] = None
        current_sprite: Optional[A.Target] = None

        self.skip_eol()
        while not self.at("EOF"):
            t = self.peek()

            if t.type == "EXTENSION":
                self.next()
                # extension name can be one or more bare words
                # (also numbers, so "LEGO WeDo 2" works)
                name_parts: List[str] = []
                while self.at("NAME", "TEXT", "NUM"):
                    name_parts.append(str(self.next().value))
                if not name_parts:
                    self.err("expected extension name after 'extension'")
                ext = " ".join(name_parts)
                if ext not in program.extensions:
                    program.extensions.append(ext)
                self.skip_eol()
                continue

            # Sprite declarator: `s "name"` (only at top level / start of line)
            if t.type == "NAME" and t.value == "s" and self._is_at_line_start():
                self.next()
                # sprite name (quoted or bare)
                sname = self._read_name_or_string()
                sprite = A.Target(kind="sprite", name=sname)
                self._parse_target_attrs(sprite, allow_stage_attrs=False)

                # Check for "steals" keyword: s "Enemy" steals "Player"
                if self.at("STEALS_KW"):
                    self.next()
                    stolen_name = self._read_name_or_string()
                    # Find the stolen sprite and copy its stuff
                    stolen = None
                    for t2 in program.targets:
                        if t2.kind == "sprite" and t2.name == stolen_name:
                            stolen = t2
                            break
                    if stolen is None:
                        from .errors import ForgotOops
                        raise ForgotOops(
                            f'Cannot steal from "{stolen_name}" - sprite not found',
                            t.line
                        )
                    # Copy scripts, custom blocks, list decls, scope vars, etc.
                    import copy
                    sprite.scripts = copy.deepcopy(stolen.scripts)
                    sprite.custom_blocks = copy.deepcopy(stolen.custom_blocks)
                    # Copy list declarations
                    if hasattr(stolen, "_list_decls"):
                        sprite._list_decls = copy.deepcopy(stolen._list_decls)
                    if hasattr(stolen, "_scope_vars"):
                        sprite._scope_vars = copy.deepcopy(stolen._scope_vars)
                    if hasattr(stolen, "_sound_imports"):
                        sprite._sound_imports = copy.deepcopy(stolen._sound_imports)
                    if hasattr(stolen, "_costume_imports"):
                        sprite._costume_imports = copy.deepcopy(stolen._costume_imports)
                    # Copy attributes (but keep the new sprite's own name)
                    saved_name = sprite.name
                    sprite.x = stolen.x
                    sprite.y = stolen.y
                    sprite.direction = stolen.direction
                    sprite.size = stolen.size
                    sprite.visible = stolen.visible
                    sprite.rotation_style = stolen.rotation_style
                    # Don't steal img (costume) - each sprite gets its own
                    sprite.name = saved_name

                # body: scripts / defs / list decls belonging to this sprite
                self.skip_eol()
                self._parse_sprite_body(sprite)
                program.targets.append(sprite)
                current_sprite = sprite
                continue

            # Backdrop declarator: `b "name"` (only at top level / start of line)
            if t.type == "NAME" and t.value == "b" and self._is_at_line_start():
                self.next()
                bname = self._read_name_or_string()
                # Find or create the stage target
                stage = next((tg for tg in program.targets if tg.kind == "stage"), None)
                if stage is None:
                    stage = A.Target(kind="stage", name="Stage")
                    program.targets.insert(0, stage)
                # Add this backdrop as a costume to the stage
                backdrop_target = A.Target(kind="backdrop", name=bname)
                self._parse_target_attrs(backdrop_target, allow_stage_attrs=True)
                # Attach as costume to the stage
                stage.costumes.append({
                    "name": bname,
                    "path": backdrop_target.img,
                })
                self.skip_eol()
                continue

            if t.type == "DEF":
                # Top-level def - belongs to current sprite, or last sprite
                if current_sprite is None:
                    self.err("custom block def with no sprite context")
                self._parse_def(current_sprite)
                continue

            # List declarator: `list Name [= ...]`
            if t.type == "NAME" and t.value == "list" and self._is_at_line_start():
                if current_sprite is None:
                    self.err("list decl with no sprite context")
                self._parse_list_decl(current_sprite)
                self.skip_eol()
                continue

            # Sound import: sound name from "path.wav"
            if t.type == "SOUND_KW" and self._is_at_line_start():
                if current_sprite is None:
                    self.err("sound import with no sprite context")
                self._parse_sound_import(current_sprite)
                self.skip_eol()
                continue

            # Costume import: costume name from "path.png"
            if t.type == "COSTUME_KW" and self._is_at_line_start():
                if current_sprite is None:
                    self.err("costume import with no sprite context")
                self._parse_costume_import(current_sprite)
                self.skip_eol()
                continue

            # Variable scope declarations:
            #   a Score = 0   -> for all sprites (stored on stage)
            #   o Score = 0   -> for this sprite only
            if t.type == "NAME" and t.value in ("a", "o") and self._is_at_line_start():
                if self.peek(1).type in ("NAME", "TEXT"):
                    scope = t.value  # "a" = all sprites, "o" = this sprite only
                    self.next()
                    var_name = self._read_name_or_string()
                    self.eat("ASSIGN", "'='")
                    val = self._parse_expr()
                    self.current_vars.add(var_name)
                    # Store the scope info on the VarAssign
                    from . import ast_nodes as A2
                    assign = A2.VarAssign(name=var_name, value=val, line=t.line)
                    assign.scope = scope  # "a" or "o"
                    if not hasattr(current_sprite, "_var_scope_decls"):
                        current_sprite._var_scope_decls = []
                    current_sprite._var_scope_decls.append(assign)
                    # Also add it to the body of the first script (or a synthetic one)
                    # Actually, we need to handle this at codegen time
                    # For now, store it as a top-level variable declaration
                    if not hasattr(current_sprite, "_scope_vars"):
                        current_sprite._scope_vars = []
                    current_sprite._scope_vars.append({"name": var_name, "value": val, "scope": scope})
                    self.skip_eol()
                    continue

            self.err(f"unexpected top-level token {t.type} ({t.value!r})")

        # Make sure there's always a stage
        if not any(tg.kind == "stage" for tg in program.targets):
            stage = A.Target(kind="stage", name="Stage")
            program.targets.insert(0, stage)
        return program

    # ---- names / strings ----
    def _read_name_or_string(self) -> str:
        t = self.peek()
        if t.type == "STRING":
            self.next()
            return t.value
        if t.type in ("NAME", "TEXT", "TRUE", "FALSE"):
            self.next()
            return t.value
        self.err(f"expected name or string, got {t.type}")

    def _read_signed_number(self) -> float:
        """Read an optional '-' followed by a NUM token."""
        sign = 1.0
        if self.at("MINUS"):
            self.next()
            sign = -1.0
        t = self.eat("NUM", "number")
        return sign * float(t.value)

    # ---- target attributes ----
    def _parse_target_attrs(self, target: A.Target, allow_stage_attrs: bool) -> None:
        """Read attribute pairs until end of line."""
        while True:
            t = self.peek()
            if t.type == "EOL" or t.type == "EOF":
                break
            if t.type != "ASSIGN_ATTR":
                break
            attr = t.value.rstrip("=")
            self.next()

            if attr == "xy":
                # expect [-]NUM, [-]NUM
                x = self._read_signed_number()
                self.eat("COMMA", "','")
                y = self._read_signed_number()
                target.x = x
                target.y = y
            elif attr == "dir":
                target.direction = self._read_signed_number()
            elif attr == "size":
                target.size = self._read_signed_number()
            elif attr == "visible":
                v = self._read_name_or_string()
                target.visible = (v.lower() in ("true", "1", "yes"))
            elif attr == "rot":
                # rotation style can be multi-word: "all around",
                # "left right", "don't rotate"
                parts = [self._read_name_or_string()]
                while self.at("NAME", "TEXT"):
                    nxt = self.peek().value
                    # stop if it's a known attribute prefix or a target keyword
                    if nxt in ("xy", "dir", "size", "visible", "rot", "img",
                               "costume", "warp", "s", "b", "when", "def",
                               "list", "extension"):
                        break
                    parts.append(self.next().value)
                target.rotation_style = " ".join(parts)
            elif attr == "img":
                p = self.eat("PATH", "path").value
                target.img = p
            elif attr == "costume":
                target.costumes.append({"name": self._read_name_or_string()})
            elif attr == "warp":
                # only meaningful on def - ignore here
                self._read_name_or_string()
            else:
                self.err(f"unknown attribute {attr!r}")

    # ---- sprite body: scripts / defs / lists ----
    def _parse_sprite_body(self, sprite: A.Target) -> None:
        """Parse scripts, defs, and list decls belonging to a sprite."""
        old_vars = set(self.current_vars)
        old_lists = set(self.current_lists)
        # Pre-scan: collect variable names from `Var = ...` patterns
        # so we can resolve BareName -> VarRef in expressions.
        self.current_vars = self._collect_vars(sprite, start_pos=self.pos)
        self.current_lists = self._collect_lists(sprite, start_pos=self.pos)

        while True:
            self.skip_eol()
            t = self.peek()
            if t.type == "EOF" or t.type == "EXTENSION":
                break
            # Stop at top-level `s "..."` or `b "..."` (next sprite/backdrop)
            if t.type == "NAME" and t.value in ("s", "b") and self._is_at_line_start():
                if self.peek(1).type in ("STRING", "NAME", "TEXT"):
                    break
            # Variable scope declarations inside sprite body too
            if t.type == "NAME" and t.value in ("a", "o") and self._is_at_line_start():
                if self.peek(1).type in ("NAME", "TEXT"):
                    scope = t.value
                    self.next()
                    var_name = self._read_name_or_string()
                    self.eat("ASSIGN", "'='")
                    val = self._parse_expr()
                    self.current_vars.add(var_name)
                    if not hasattr(sprite, "_scope_vars"):
                        sprite._scope_vars = []
                    sprite._scope_vars.append({"name": var_name, "value": val, "scope": scope})
                    continue
            if t.type == "WHEN":
                sprite.scripts.append(self._parse_script())
                continue
            if t.type == "DEF":
                self._parse_def(sprite)
                continue
            if t.type == "NAME" and t.value == "list" and self._is_at_line_start():
                self._parse_list_decl(sprite)
                continue
            # Sound import: sound name from "path.wav"
            if t.type == "SOUND_KW" and self._is_at_line_start():
                self._parse_sound_import(sprite)
                continue
            # Costume import: costume name from "path.png"
            if t.type == "COSTUME_KW" and self._is_at_line_start():
                self._parse_costume_import(sprite)
                continue
            # otherwise: stop - we're at the next target / eof
            break

        self.current_vars = old_vars
        self.current_lists = old_lists

    def _collect_vars(self, sprite: A.Target, start_pos: int) -> set:
        """Pre-scan from start_pos to the end of this sprite's body and
        collect every NAME that is the target of an `=`/`+=`/etc. assignment
        or a `list` declaration.  Used to resolve BareName."""
        names: set = set()
        i = start_pos
        depth = 0  # brace depth
        # We stop at the next S_KW/B_KW/EXTENSION at depth 0
        while i < len(self.toks):
            t = self.toks[i]
            if t.type == "EOF":
                break
            if depth == 0 and t.type in ("S_KW", "B_KW", "EXTENSION"):
                break
            if t.type == "LBRACE":
                depth += 1
            elif t.type == "RBRACE":
                depth -= 1
                if depth < 0:
                    break
            elif depth == 0 and t.type == "NAME":
                # look ahead: is the next non-EOL token = or += etc?
                j = i + 1
                while j < len(self.toks) and self.toks[j].type == "EOL":
                    j += 1
                if j < len(self.toks) and self.toks[j].type in (
                    "ASSIGN", "PLUS_EQ", "MINUS_EQ", "STAR_EQ", "SLASH_EQ"
                ):
                    names.add(t.value)
            i += 1
        return names

    def _collect_lists(self, sprite: A.Target, start_pos: int) -> set:
        """Pre-scan for `list NAME` declarations at any depth in this sprite."""
        names: set = set()
        i = start_pos
        depth = 0
        while i < len(self.toks):
            t = self.toks[i]
            if t.type == "EOF":
                break
            # Stop at top-level s/b/extension (next target)
            if depth == 0 and t.type == "EXTENSION":
                break
            if depth == 0 and t.type == "NAME" and t.value in ("s", "b"):
                # Check line start + next token is name
                # (we approximate - just check next token)
                j = i + 1
                while j < len(self.toks) and self.toks[j].type == "EOL":
                    j += 1
                if j < len(self.toks) and self.toks[j].type in ("STRING", "NAME", "TEXT"):
                    break
            if t.type == "LBRACE":
                depth += 1
            elif t.type == "RBRACE":
                depth -= 1
                if depth < 0:
                    break
            elif t.type == "NAME" and t.value == "list":
                # check it's at line start (declarator form)
                # next non-EOL should be NAME
                j = i + 1
                while j < len(self.toks) and self.toks[j].type == "EOL":
                    j += 1
                if j < len(self.toks) and self.toks[j].type in ("NAME", "STRING"):
                    names.add(self.toks[j].value)
            i += 1
        return names

    # ---- scripts / hats ----
    def _parse_script(self) -> A.Script:
        self.eat("WHEN", "'when'")
        hat = self._parse_hat()
        self.skip_eol()
        self.eat("LBRACE", "'{'")
        body = self._parse_block_body()
        self.eat("RBRACE", "'}'")
        return A.Script(hat=hat, body=body)

    def _parse_hat(self) -> A.Hat:
        t = self.peek()
        line = t.line
        if t.type not in ("NAME", "TEXT", "LBRACKET"):
            self.err("expected hat kind after 'when' (gf, spr, key, backdrop, I, ...)")
        # Special: `when [property] > [value]` form (without "greater" word)
        if t.type == "LBRACKET":
            return self._parse_greater_than_hat(line)
        kind = self.next().value

        if kind == "gf":
            self._expect_word("clicked")
            return A.Hat(kind="gf", line=line)
        if kind == "spr":
            self._expect_word("clicked")
            return A.Hat(kind="spr", line=line)
        if kind == "stage":
            self._expect_word("clicked")
            return A.Hat(kind="stage_clicked", line=line)
        if kind == "clicked":
            return A.Hat(kind="spr", line=line)
        if kind == "key":
            self.eat("LBRACKET", "'['")
            key = self._read_bracket_text()
            self.eat("RBRACKET", "']'")
            self._expect_word("pressed")
            return A.Hat(kind="key", args=[key], line=line)
        if kind == "backdrop":
            self._expect_word("switches")
            self._expect_word("to")
            self.eat("LBRACKET", "'['")
            bname = self._read_bracket_text()
            self.eat("RBRACKET", "']'")
            return A.Hat(kind="backdrop", args=[bname], line=line)
        if kind == "I":
            self._expect_word("receive")
            self.eat("LBRACKET", "'['")
            msg = self._read_bracket_text()
            self.eat("RBRACKET", "']'")
            return A.Hat(kind="receive", args=[msg], line=line)
        if kind == "greater":
            return self._parse_greater_than_hat(line)
        if kind == "cloned":
            return A.Hat(kind="cloned", line=line)

        # ---- Extension hats ----
        # These are looked up by name in B.HAT_BLOCKS.  We support
        # several common arg patterns:
        #   when <kind> [arg]                  -> args = [arg]
        #   when <kind> [arg] pressed          -> args = [arg]
        #   when <kind> [arg] connected        -> args = [arg]
        #   when <kind> <NUM>                  -> args = [num]
        #   when <kind> [field] [arg]          -> args = [field, arg]
        #   when <kind> > <NUM>                -> args = [num]   (video_motion)
        if kind in B.HAT_BLOCKS:
            return self._parse_extension_hat(kind, line)

        suggestion = did_you_mean(kind, B.HAT_BLOCKS.keys())
        self.err(f'"{kind}" is not valid TypeScratch syntax{suggestion}', t)

    def _parse_extension_hat(self, kind: str, line: int) -> A.Hat:
        """Parse the arguments of an extension hat block.

        Reads tokens until LBRACE, collecting bracketed values and bare
        numbers as args.  Words like 'pressed', 'connected', 'in order'
        are skipped (they're just labels in Scratch's block text)."""
        args: List[Any] = []

        while not self.at("LBRACE", "EOF", "EOL"):
            t = self.peek()
            if t.type == "LBRACKET":
                self.next()
                val = self._read_bracket_text()
                self.eat("RBRACKET", "']'")
                args.append(val)
            elif t.type == "NUM":
                args.append(self.next().value)
                try:
                    args[-1] = float(args[-1]) if "." in args[-1] else int(args[-1])
                except Exception:
                    pass
            elif t.type == "GT":
                # `when video_motion > 50` - skip the >, the next NUM is the arg
                self.next()
            elif t.type in ("NAME", "TEXT"):
                # skip filler words like "pressed", "connected", "in order"
                word = self.next().value
                # if it's not a filler word, treat as a string arg
                if word.lower() not in ("pressed", "connected", "in", "order", "pressed", "key"):
                    # only add as arg if we haven't already got one
                    # (this avoids double-counting)
                    if not args or not isinstance(args[-1], str) or args[-1] != word:
                        # Don't add - it's likely a label
                        pass
            else:
                self.next()

        return A.Hat(kind=kind, args=args, line=line)

    def _parse_greater_than_hat(self, line: int) -> A.Hat:
        """Parse `when [property] > [value]` (with optional leading 'greater')."""
        self.eat("LBRACKET", "'['")
        what = self._read_bracket_text()
        self.eat("RBRACKET", "']'")
        self.eat("GT", "'>'")
        self.eat("LBRACKET", "'['")
        val = self._read_bracket_text()
        self.eat("RBRACKET", "']'")
        return A.Hat(kind="greater_than", args=[what, val], line=line)

    def _parse_ternary_value(self):
        """Parse a single value for a ternary expression.

        This is like _parse_atom but stops at 'else' (doesn't consume it
        as part of a bare string).
        """
        t = self.peek()
        if t.type == "ELSE":
            self.err("expected a value before 'else' in ternary")
        if t.type == "STRING":
            self.next()
            return A.StringLit(value=t.value, line=t.line)
        if t.type == "NUM":
            self.next()
            val = float(t.value) if "." in t.value else int(t.value)
            return A.NumberLit(value=val, line=t.line)
        if t.type == "HEXCOLOR":
            self.next()
            return A.ColorLit(value=t.value, line=t.line)
        if t.type == "LPAREN":
            self.next()
            self.skip_eol()
            expr = self._parse_expr()
            self.skip_eol()
            self.eat("RPAREN", "')'")
            return expr
        if t.type in ("NAME", "TEXT"):
            # Parse a single bare name or function call, but DON'T
            # accumulate following words (since "else" could be next)
            name = self.next().value
            if self.at("LPAREN"):
                args = self._parse_paren_args()
                return A.FuncCall(name=name, args=args, line=t.line)
            return A.BareRef(name=name, line=t.line)
        self.err(f"unexpected token in ternary value: {t.type} ({t.value!r})")

    def _read_bracket_text(self) -> str:
        """Read text inside [ ] - can be multi-word.  Returns the joined string.

        Also accepts operator-like tokens (<, >, =, +, -, *, /) so that
        bracket contents like [<] or [>=] work as field values."""
        parts: List[str] = []
        # Accept most token types except the closing bracket
        accept_types = {
            "NAME", "TEXT", "NUM", "STRING", "TRUE", "FALSE",
            "AND", "OR", "NOT", "MOD", "WAIT", "STOP", "BROADCAST",
            "IF", "ELSE", "REPEAT", "REPEAT_UNTIL", "FOREVER", "WHILE",
            "WHEN", "DEF", "EXTENSION",
            "GT", "LT", "ASSIGN", "EQ_EQ",
            "PLUS", "MINUS", "STAR", "SLASH",
        }
        while self.peek().type in accept_types:
            tok = self.next()
            parts.append(str(tok.value))
        return " ".join(parts) if parts else ""

    def _expect_word(self, word: str) -> None:
        t = self.peek()
        if (t.type in ("NAME", "TEXT")) and t.value == word:
            self.next()
            return
        self.err(f"expected {word!r}", t)

    # ---- block body ----
    def _parse_block_body(self) -> List[A.Statement]:
        """Parse statements until RBRACE."""
        body: List[A.Statement] = []
        while True:
            self.skip_eol()
            if self.at("RBRACE", "EOF"):
                break
            stmt = self._parse_statement()
            if stmt is not None:
                body.append(stmt)
        return body

    # ---- statements ----
    def _parse_statement(self) -> Optional[A.Statement]:
        t = self.peek()
        line = t.line

        if t.type == "IF":
            return self._parse_if()
        if t.type == "REPEAT":
            return self._parse_repeat()
        if t.type == "REPEAT_UNTIL":
            return self._parse_repeat_until()
        if t.type == "FOREVER":
            return self._parse_forever()
        if t.type == "WHILE":
            return self._parse_while()
        if t.type == "FOR_EACH":
            return self._parse_for_each()
        if t.type == "ALL_AT_ONCE":
            return self._parse_all_at_once()
        if t.type == "WAIT":
            self.next()
            secs = self._parse_expr()
            return A.WaitStatement(secs=secs, line=line)
        if t.type == "WAIT_UNTIL":
            self.next()
            cond = self._parse_expr()
            return A.WaitUntilStatement(cond=cond, line=line)
        if t.type == "STOP":
            self.next()
            # `stop all`  or  `stop(all)`  or  `stop this script`
            if self.at("LPAREN"):
                self.next()
                kind = self._read_name_or_string()
                self.eat("RPAREN", "')'")
            else:
                # could be a bare word or a multi-word "this script"
                parts = []
                while self.at("NAME", "TEXT"):
                    parts.append(self.next().value)
                kind = " ".join(parts) if parts else "all"
            return A.StopStatement(kind=kind, line=line)
        if t.type == "BROADCAST":
            self.next()
            msg: Any
            if self.at("LBRACKET"):
                self.next()
                msg = self._parse_expr()
                self.eat("RBRACKET", "']'")
            elif self.at("LPAREN"):
                args = self._parse_paren_args()
                if not args:
                    self.err("broadcast() requires a message argument", t)
                msg = args[0]
            else:
                msg = self._parse_expr()
            wait = False
            if self.at("AND") or (self.at("NAME", "TEXT") and self.peek().value == "and"):
                self.next()
                if not (self.at("WAIT") or (self.at("NAME", "TEXT") and self.peek().value == "wait")):
                    self.err("expected 'wait' after 'and' in 'broadcast(...) and wait'")
                self.next()
                wait = True
            return A.BroadcastStatement(msg=msg, wait=wait, line=line)

        # private x = value  (local variable inside a custom block)
        if t.type == "PRIVATE_KW":
            self.next()
            var_name = self._read_name_or_string()
            self.eat("ASSIGN", "'='")
            val = self._parse_expr()
            self.current_vars.add(var_name)
            return A.LocalVarDecl(name=var_name, value=val, line=line)
        if t.type == "DEF":
            # def at statement level (inside a script - unusual but allowed)
            # We need a sprite context; create a dummy def container
            self.err("def at statement level - use def at sprite level instead")

        # otherwise: block_call, var_assign, var_modify, list_op, custom_call
        return self._parse_simple_statement()

    def _parse_if(self) -> A.IfStatement:
        t = self.eat("IF", "'if'")
        cond = self._parse_expr()
        self.skip_eol()
        self.eat("LBRACE", "'{'")
        then_body = self._parse_block_body()
        self.eat("RBRACE", "'}'")
        else_body = None
        self.skip_eol()
        # check for else or elif
        if self.at("ELSE"):
            self.next()
            self.skip_eol()
            # else if -> nested if
            if self.at("IF"):
                else_body = [self._parse_if()]
            else:
                self.eat("LBRACE", "'{'")
                else_body = self._parse_block_body()
                self.eat("RBRACE", "'}'")
        elif self.at("ELIF"):
            # elif -> nested if (parse the elif as an if statement)
            else_body = [self._parse_if_elif()]
        return A.IfStatement(cond=cond, then_body=then_body, else_body=else_body, line=t.line)

    def _parse_if_elif(self) -> A.IfStatement:
        """Parse an elif clause as a nested if statement."""
        t = self.eat("ELIF", "'elif'")
        cond = self._parse_expr()
        self.skip_eol()
        self.eat("LBRACE", "'{'")
        then_body = self._parse_block_body()
        self.eat("RBRACE", "'}'")
        else_body = None
        self.skip_eol()
        # elif can chain to another elif or else
        if self.at("ELSE"):
            self.next()
            self.skip_eol()
            if self.at("IF"):
                else_body = [self._parse_if()]
            else:
                self.eat("LBRACE", "'{'")
                else_body = self._parse_block_body()
                self.eat("RBRACE", "'}'")
        elif self.at("ELIF"):
            else_body = [self._parse_if_elif()]
        return A.IfStatement(cond=cond, then_body=then_body, else_body=else_body, line=t.line)

    def _parse_repeat(self) -> A.RepeatStatement:
        t = self.eat("REPEAT", "'repeat'")
        times = self._parse_expr()
        self.skip_eol()
        self.eat("LBRACE", "'{'")
        body = self._parse_block_body()
        self.eat("RBRACE", "'}'")
        return A.RepeatStatement(times=times, body=body, line=t.line)

    def _parse_repeat_until(self) -> A.RepeatUntilStatement:
        t = self.eat("REPEAT_UNTIL", "'repeatUntil'")
        cond = self._parse_expr()
        self.skip_eol()
        self.eat("LBRACE", "'{'")
        body = self._parse_block_body()
        self.eat("RBRACE", "'}'")
        return A.RepeatUntilStatement(cond=cond, body=body, line=t.line)

    def _parse_forever(self) -> A.ForeverStatement:
        t = self.eat("FOREVER", "'forever'")
        self.skip_eol()
        self.eat("LBRACE", "'{'")
        body = self._parse_block_body()
        self.eat("RBRACE", "'}'")
        return A.ForeverStatement(body=body, line=t.line)

    def _parse_while(self) -> A.WhileStatement:
        t = self.eat("WHILE", "'while'")
        cond = self._parse_expr()
        self.skip_eol()
        self.eat("LBRACE", "'{'")
        body = self._parse_block_body()
        self.eat("RBRACE", "'}'")
        return A.WhileStatement(cond=cond, body=body, line=t.line)

    def _parse_for_each(self) -> A.ForEachStatement:
        """`forEach (var) in (count) { ... }` - hidden control_for_each.

        Two syntaxes are accepted:
            forEach (var) in (count) { ... }   - var and count each in own parens
            forEach (var in count) { ... }      - all in one paren group
        """
        t = self.eat("FOR_EACH", "'forEach'")
        self.eat("LPAREN", "'('")
        var_name = self._read_name_or_string()
        # Two possible forms:
        #   (var) in (count)  -> next token is RPAREN
        #   (var in count)    -> next token is "in"
        if self.at("RPAREN"):
            # Form 1: (var) in (count)
            self.eat("RPAREN", "')'")
            in_tok = self.peek()
            if not (in_tok.type in ("NAME", "TEXT") and in_tok.value == "in"):
                self.err("expected 'in' in forEach (var) in (count)", in_tok)
            self.next()
            self.eat("LPAREN", "'('")
            count = self._parse_expr()
            self.eat("RPAREN", "')'")
        else:
            # Form 2: (var in count)
            in_tok = self.peek()
            if not (in_tok.type in ("NAME", "TEXT") and in_tok.value == "in"):
                self.err("expected 'in' in forEach (var in count)", in_tok)
            self.next()
            count = self._parse_expr()
            self.eat("RPAREN", "')'")
        self.skip_eol()
        self.eat("LBRACE", "'{'")
        body = self._parse_block_body()
        self.eat("RBRACE", "'}'")
        # Ensure the var is declared
        self.current_vars.add(var_name)
        return A.ForEachStatement(var_name=var_name, count=count, body=body, line=t.line)

    def _parse_all_at_once(self) -> A.AllAtOnceStatement:
        """`allAtOnce { ... }` - hidden control_all_at_once."""
        t = self.eat("ALL_AT_ONCE", "'allAtOnce'")
        self.skip_eol()
        self.eat("LBRACE", "'{'")
        body = self._parse_block_body()
        self.eat("RBRACE", "'}'")
        return A.AllAtOnceStatement(body=body, line=t.line)

    # ---- simple statement: block_call / var_assign / var_modify / list_op ----
    def _parse_simple_statement(self) -> A.Statement:
        t = self.peek()
        line = t.line
        if t.type not in ("NAME", "TEXT"):
            self.err(f"expected a statement, got {t.type} ({t.value!r})")
        first = self.next().value

        # variable assignment:  NAME = expr
        if self.at("ASSIGN"):
            self.next()
            val = self._parse_expr()
            self.current_vars.add(first)
            return A.VarAssign(name=first, value=val, line=line)

        # variable modify:  NAME += expr  (etc)
        for tt, op in (("PLUS_EQ", "+="), ("MINUS_EQ", "-="),
                       ("STAR_EQ", "*="), ("SLASH_EQ", "/=")):
            if self.at(tt):
                self.next()
                val = self._parse_expr()
                self.current_vars.add(first)
                return A.VarModify(name=first, op=op, value=val, line=line)

        # increment/decrement:  NAME++  NAME--
        if self.at("PLUS_PLUS"):
            self.next()
            self.current_vars.add(first)
            return A.VarModify(name=first, op="+=", value=A.NumberLit(1), line=line)
        if self.at("MINUS_MINUS"):
            self.next()
            self.current_vars.add(first)
            return A.VarModify(name=first, op="-=", value=A.NumberLit(1), line=line)

        # namespace access:  NAME . NAME (...)
        if self.at("DOT"):
            self.next()
            method_tok = self.peek()
            if method_tok.type not in ("NAME", "TEXT"):
                self.err(f"expected method name after '.', got {method_tok.type}")
            method = self.next().value

            # list op:  listname.add(...) delete(...) insert(...) ...
            # show / hide are argument-less
            if first in self.current_lists or method in (
                "add", "delete", "insert", "replace", "show", "hide"
            ):
                if method in ("show", "hide"):
                    # no parens
                    return A.ListOp(list_name=first, op=method, args=[], line=line)
                args = self._parse_paren_args()
                # If there's a second arg in delete, it's an index
                return A.ListOp(list_name=first, op=method, args=args, line=line)

            # otherwise: namespace call (e.g. pen.Down, pen.Up, control.Wait, ...)
            args = self._parse_paren_args_maybe()
            post = self._parse_post_parens()
            return A.BlockCall(namespace=first, method=method, args=args, post=post, line=line)

        # block call with parens:  NAME(args) (post)?
        if self.at("LPAREN"):
            args = self._parse_paren_args()
            post = self._parse_post_parens()
            # Special: `ask(...) and wait` -> the askAndWait block
            if first == "ask" and self.at("AND"):
                self.next()
                # `wait` is a keyword (WAIT) or a bare NAME
                if not (self.at("WAIT") or (self.at("NAME", "TEXT") and self.peek().value == "wait")):
                    self.err("expected 'wait' after 'and' in 'ask(...) and wait'")
                self.next()
                return A.BlockCall(namespace=None, method="askAndWait",
                                   args=args, post=None, line=line)
            # if first is a known custom block name, emit CustomBlockCall
            # (we check this in codegen by looking up the target's custom_blocks)
            return A.BlockCall(namespace=None, method=first, args=args, post=post, line=line)

        # bare block (no args):  show, hide, nextCostume, pen.Down (already handled above)
        # If there is a trailing post parens like `()(2)`, capture it.
        post = self._parse_post_parens()
        return A.BlockCall(namespace=None, method=first, args=[], post=post, line=line)

    # ---- helpers for parens ----
    def _parse_paren_args(self) -> List[Any]:
        """Parse (expr, expr, ...) - returns list of arg expressions."""
        self.eat("LPAREN", "'('")
        args: List[Any] = []
        self.skip_eol()
        if not self.at("RPAREN"):
            args.append(self._parse_expr())
            while self.at("COMMA"):
                self.next()
                self.skip_eol()
                args.append(self._parse_expr())
        self.skip_eol()
        self.eat("RPAREN", "')'")
        return args

    def _parse_paren_args_maybe(self) -> List[Any]:
        """Parse args if next is LPAREN, else empty list."""
        if self.at("LPAREN"):
            return self._parse_paren_args()
        return []

    def _parse_post_parens(self) -> Optional[List[Any]]:
        """Optional second/third paren group, e.g. the seconds in say(...)(2)."""
        if self.at("LPAREN"):
            return self._parse_paren_args()
        return None

    # ---- expressions ----
    def _parse_expr(self) -> Any:
        return self._parse_or()

    def _parse_or(self) -> Any:
        left = self._parse_and()
        while self.at("OR"):
            t = self.next()
            right = self._parse_and()
            left = A.BinOp(op="or", left=left, right=right, line=t.line)
        return left

    def _parse_and(self) -> Any:
        left = self._parse_not()
        while self.at("AND"):
            t = self.next()
            right = self._parse_not()
            left = A.BinOp(op="and", left=left, right=right, line=t.line)
        return left

    def _parse_not(self) -> Any:
        # Only treat NOT as the operator if the next token can start an
        # expression. If NOT is followed by ) , } or EOF, it's the word
        # "not" being used as text (e.g. say(not)).
        if self.at("NOT"):
            next_tok = self.peek(1)
            if next_tok.type not in ("RPAREN", "COMMA", "RBRACE", "EOF", "EOL"):
                t = self.next()
                operand = self._parse_not()
                return A.UnaryOp(op="not", operand=operand, line=t.line)
        return self._parse_compare()

    def _parse_compare(self) -> Any:
        left = self._parse_add()
        if self.at("GT", "LT", "EQ_EQ", "ASSIGN", "GTE", "LTE", "NEQ"):
            t = self.next()
            op_map = {">": ">", "<": "<", "==": "=", "=": "=", ">=": ">=", "<=": "<=", "!=": "!="}
            op = op_map[t.value]
            right = self._parse_add()
            return A.BinOp(op=op, left=left, right=right, line=t.line)
        return left

    def _parse_add(self) -> Any:
        left = self._parse_mul()
        while self.at("PLUS", "MINUS", "AMP"):
            t = self.next()
            right = self._parse_mul()
            if t.type == "AMP":
                # & is join (string concatenation)
                left = A.FuncCall(name="join", args=[left, right], line=t.line)
            else:
                left = A.BinOp(op=t.value, left=left, right=right, line=t.line)
        return left

    def _parse_mul(self) -> Any:
        left = self._parse_unary()
        while self.at("STAR", "SLASH", "MOD", "FLOOR_DIV"):
            t = self.next()
            right = self._parse_unary()
            if t.type == "FLOOR_DIV":
                # // is floor division: round(a / b)
                div = A.BinOp(op="/", left=left, right=right, line=t.line)
                left = A.FuncCall(name="round", args=[div], line=t.line)
            else:
                left = A.BinOp(op=t.value, left=left, right=right, line=t.line)
        return left

    def _parse_unary(self) -> Any:
        if self.at("MINUS"):
            t = self.next()
            operand = self._parse_unary()
            return A.UnaryOp(op="-", operand=operand, line=t.line)
        return self._parse_atom()

    def _parse_atom(self) -> Any:
        t = self.peek()

        if t.type == "NUM":
            self.next()
            val = float(t.value) if "." in t.value else int(t.value)
            return A.NumberLit(value=val, line=t.line)

        if t.type == "STRING":
            self.next()
            return A.StringLit(value=t.value, line=t.line)

        if t.type == "HEXCOLOR":
            self.next()
            return A.ColorLit(value=t.value, line=t.line)

        if t.type == "TRUE":
            self.next()
            return A.StringLit(value="true", line=t.line)
        if t.type == "FALSE":
            self.next()
            return A.StringLit(value="false", line=t.line)

        if t.type == "LPAREN":
            self.next()
            self.skip_eol()
            expr = self._parse_expr()
            self.skip_eol()
            self.eat("RPAREN", "')'")
            return expr

        if t.type == "LBRACKET":
            # [expr] - used for menu choices, but also a grouping
            self.next()
            self.skip_eol()
            # Check for ternary: [if (cond) x else y]
            if self.at("IF"):
                self.next()
                cond = self._parse_expr()
                # Parse true_expr - but stop at ELSE
                # We need to parse a single atom for the true value
                # because _parse_expr would consume "else" as a bare word
                true_expr = self._parse_ternary_value()
                # expect "else"
                if not self.at("ELSE"):
                    self.err("expected 'else' in ternary [if (cond) x else y]")
                self.next()
                false_expr = self._parse_ternary_value()
                self.skip_eol()
                self.eat("RBRACKET", "']'")
                return A.TernaryExpr(cond=cond, true_expr=true_expr, false_expr=false_expr, line=t.line)
            expr = self._parse_expr()
            self.skip_eol()
            self.eat("RBRACKET", "']'")
            return expr

        if t.type in ("NAME", "TEXT", "SOUND_KW", "COSTUME_KW", "PRIVATE_KW",
                       "STEALS_KW",
                       # Keywords are also valid as bare words in expressions
                       # so that say(and), say(or), say(not), say(if), etc. work
                       "AND", "OR", "NOT", "MOD", "WAIT", "WAIT_UNTIL", "STOP",
                       "BROADCAST", "IF", "ELSE", "ELIF", "REPEAT", "REPEAT_UNTIL",
                       "FOREVER", "WHILE", "WHEN", "DEF", "TRUE", "FALSE",
                       "FOR_EACH", "ALL_AT_ONCE", "EXTENSION"):
            # Accumulate consecutive bare words into a string.
            # If the next token is LPAREN, this is a function call.
            # If the next token is DOT, this is namespace access.
            first_tok = t
            name = self.next().value

            # function call?
            if self.at("LPAREN"):
                args = self._parse_paren_args()
                return A.FuncCall(name=name, args=args, line=first_tok.line)

            # namespace access (e.g. music.Tempo, translate.To, gdx.Force)
            # We treat these as BuiltinRef-style reporters that codegen
            # will look up in the REPORTERS table.
            if self.at("DOT"):
                self.next()
                prop_tok = self.peek()
                if prop_tok.type not in ("NAME", "TEXT"):
                    self.err("expected name after '.'", prop_tok)
                prop = self.next().value

                # If `name` is a declared list, this is a list reporter:
                #   <list>.item(n)        -> data_itemoflist
                #   <list>.length         -> data_lengthoflist
                #   <list>.contains(x)    -> data_listcontainsitem
                #   <list>.itemNum(x)     -> data_itemnumoflist
                #   <list>.contents       -> data_listcontents
                if name in self.current_lists and prop in (
                    "item", "length", "contains", "itemNum", "contents",
                    "itemNumber", "asString",
                ):
                    args = self._parse_paren_args_maybe()
                    return A.ListReporterRef(
                        list_name=name, method=prop, args=args, line=first_tok.line
                    )

                # Could be namespace.prop(args) - a reporter with args
                if self.at("LPAREN"):
                    args = self._parse_paren_args()
                    return A.FuncCall(name=f"{name}.{prop}", args=args, line=first_tok.line)
                # Bare namespace.prop - a no-arg reporter like music.Tempo,
                # translate.ViewerLanguage, gdx.Force, etc.
                return A.BuiltinRef(name=f"{name}.{prop}", line=first_tok.line)

            # bare word - accumulate following NAME/TEXT/NUM into a string.
            # Also accept operator-like keywords (AND, OR, NOT, MOD) and
            # statement keywords (WAIT, STOP, BROADCAST, IF, ELSE, REPEAT,
            # FOREVER, WHILE, WHEN, DEF, TRUE, FALSE) as text continuation,
            # so that `say(This is not a joke)` parses as one string.
            WORD_LIKE = ("NAME", "TEXT", "NUM", "AND", "OR", "NOT", "MOD",
                         "WAIT", "WAIT_UNTIL", "STOP", "BROADCAST", "IF", "ELSE", "ELIF",
                         "REPEAT", "REPEAT_UNTIL", "FOREVER", "WHILE", "WHEN",
                         "FOR_EACH", "ALL_AT_ONCE",
                         "DEF", "TRUE", "FALSE", "EXTENSION",
                         "SOUND_KW", "COSTUME_KW", "PRIVATE_KW", "STEALS_KW")
            words = [name]
            while self.at(*WORD_LIKE):
                words.append(str(self.next().value))
            if len(words) == 1:
                # single bare name - ambiguous, decide in codegen
                return A.BareRef(name=name, line=first_tok.line)

            # Check for "X pressed" pattern → keyPressed(X)
            # This lets users write `if up arrow pressed {` instead of
            # `if keyPressed(up arrow) {`.
            joined = " ".join(words)
            if joined.endswith(" pressed") and len(words) >= 2:
                key_name = " ".join(words[:-1])
                return A.FuncCall(name="keyPressed",
                                  args=[A.StringLit(value=key_name, line=first_tok.line)],
                                  line=first_tok.line)

            # multiple words - definitely a string literal
            return A.StringLit(value=joined, line=first_tok.line)

        self.err(f"unexpected token in expression: {t.type} ({t.value!r})")

    # ---- custom block defs ----
    def _parse_def(self, sprite: A.Target) -> None:
        t = self.eat("DEF", "'def'")
        name = self._read_name_or_string()
        # params: (name:type, name:type, ...)
        params: List[dict] = []
        if self.at("LPAREN"):
            self.next()
            self.skip_eol()
            while not self.at("RPAREN"):
                pname = self._read_name_or_string()
                ptype = "string"
                if self.at("COLON"):  # not in lexer - skip
                    pass
                # accept optional ":type" via NAME
                # (since we have no colon token, accept "name type" form)
                if self.at("NAME", "TEXT") and self.peek().value in (
                    "string", "number", "bool", "boolean"
                ):
                    ptype_tok = self.next()
                    ptype = "boolean" if ptype_tok.value == "bool" else ptype_tok.value
                params.append({"name": pname, "type": ptype})
                if self.at("COMMA"):
                    self.next()
                    self.skip_eol()
                else:
                    break
            self.eat("RPAREN", "')'")
        # optional warp=true|false
        warp = False
        if self.at("ASSIGN_ATTR") and self.peek().value == "warp=":
            self.next()
            v = self._read_name_or_string()
            warp = v.lower() in ("true", "1", "yes")
        self.skip_eol()
        self.eat("LBRACE", "'{'")
        body = self._parse_block_body()
        self.eat("RBRACE", "'}'")
        sprite.custom_blocks.append(A.CustomBlockDef(
            name=name, params=params, body=body, warp=warp, line=t.line
        ))

    # ---- list declarations ----
    def _parse_sound_import(self, sprite: A.Target) -> None:
        """Parse: sound name from "path.wav" """
        self.next()  # consume 'sound'
        name = self._read_name_or_string()
        # expect "from"
        if not (self.at("NAME", "TEXT") and self.peek().value == "from"):
            self.err("expected 'from' in: sound name from \"path.wav\"")
        self.next()
        path_tok = self.peek()
        if path_tok.type == "STRING":
            path = self.next().value
        elif path_tok.type == "PATH":
            path = self.next().value
        elif path_tok.type in ("NAME", "TEXT"):
            path = self.next().value
        else:
            self.err("expected file path after 'from'")
        if not hasattr(sprite, "_sound_imports"):
            sprite._sound_imports = []
        sprite._sound_imports.append({"name": name, "path": path})

    def _parse_costume_import(self, sprite: A.Target) -> None:
        """Parse: costume name from "path.png" """
        self.next()  # consume 'costume'
        name = self._read_name_or_string()
        if not (self.at("NAME", "TEXT") and self.peek().value == "from"):
            self.err("expected 'from' in: costume name from \"path.png\"")
        self.next()
        path_tok = self.peek()
        if path_tok.type == "STRING":
            path = self.next().value
        elif path_tok.type == "PATH":
            path = self.next().value
        elif path_tok.type in ("NAME", "TEXT"):
            path = self.next().value
        else:
            self.err("expected file path after 'from'")
        if not hasattr(sprite, "_costume_imports"):
            sprite._costume_imports = []
        sprite._costume_imports.append({"name": name, "path": path})

    def _parse_list_decl(self, sprite: A.Target) -> None:
        # The "list" keyword has already been peeked but not consumed.
        list_tok = self.peek()
        if list_tok.type == "NAME" and list_tok.value == "list":
            self.next()
        else:
            self.err("expected 'list'", list_tok)
        name = self._read_name_or_string()
        self.current_lists.add(name)
        # optional = [a, b, c]
        initial: List[Any] = []
        if self.at("ASSIGN"):
            self.next()
            self.eat("LBRACKET", "'['")
            self.skip_eol()
            while not self.at("RBRACKET"):
                initial.append(self._parse_expr())
                if self.at("COMMA"):
                    self.next()
                    self.skip_eol()
                else:
                    break
            self.eat("RBRACKET", "']'")
        # store on the target as a special variable-like entry
        # we'll turn it into a Scratch list in codegen
        if not hasattr(sprite, "_list_decls"):
            sprite._list_decls = []
        sprite._list_decls.append({"name": name, "initial": initial})


def parse_source(src: str, filename: str = "<tysh>") -> A.Program:
    toks = tokenize(src, filename)
    return Parser(toks, filename).parse_program()
