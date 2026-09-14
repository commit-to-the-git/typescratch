"""AST node definitions for TypeScratch.

The grammar (informally):

    program       := (extension | target)*

    extension     := 'extension' EXT_NAME
    target        := sprite | backdrop
    sprite        := 's' STRING [sprite_attrs]
    backdrop      := 'b' STRING [backdrop_attrs]
    sprite_attrs  := ('xy=' NUM ',' NUM | 'dir=' NUM | 'size=' NUM
                      | 'visible=' BOOL | 'rot=' ROT | 'img=' PATH | 'costume=' NAME)*
    backdrop_attrs:= ('img=' PATH | 'costume=' NAME)*

    script        := hat '{' statement* '}'
    hat           := 'when' hat_kind hat_args?

    statement     := block_call
                   | var_assign
                   | var_modify
                   | list_op
                   | 'if' expr block ('else' block)?
                   | 'repeat' expr block
                   | 'repeatUntil' expr block
                   | 'forever' block
                   | 'while' expr block
                   | 'wait' expr
                   | 'stop' STOP_ARG
                   | 'def' NAME '(' params ')' block        # custom block definition
                   | custom_call

    block_call    := NAME ('.' NAME)? '(' args? ')' post?  # e.g. say(...)(2), pen.Down, goto(1,2)
                   | NAME '.' NAME                          # argument-less form: pen.Down, nextCostume
                   | NAME                                    # argument-less: show, hide

    var_assign    := NAME '=' expr
    var_modify    := NAME ('+=' | '-=' | '*=' | '/=') expr

    list_op       := NAME '.' ('add' | 'delete' | 'insert' | 'replace') '(' args ')'

    expr          := or_expr
    or_expr       := and_expr (('or') and_expr)*
    and_expr      := not_expr ('and' not_expr)*
    not_expr      := 'not' not_expr | compare
    compare       := add (('>' | '<' | '=') add)?
    add           := mul (('+' | '-') mul)*
    mul           := unary (('*' | '/' | 'mod') unary)*
    unary         := '-' unary | atom
    atom          := NUM | STRING | NAME | '(' expr ')' | func_call | builtin
    func_call     := NAME '(' args? ')'

Strings in the .tysh source can be written *without* quotes (because
"Scratch has no strings, only text").  Where a string vs an identifier
is ambiguous (e.g. arguments to `say`), the lexer yields a single TEXT
token whose interpretation is context-sensitive in the parser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

@dataclass
class Program:
    extensions: List[str] = field(default_factory=list)
    targets: List["Target"] = field(default_factory=list)

    def __repr__(self):
        return f"Program(ext={self.extensions}, targets={len(self.targets)})"


@dataclass
class Target:
    kind: str                     # 'sprite' or 'stage'
    name: str
    x: float = 0.0
    y: float = 0.0
    direction: float = 90.0
    size: float = 100.0
    visible: bool = True
    rotation_style: str = "all around"  # all around | left-right | don't rotate
    img: Optional[str] = None
    costumes: List[Dict[str, Any]] = field(default_factory=list)  # {name, path, is_default}
    sounds: List[Dict[str, Any]] = field(default_factory=list)
    scripts: List["Script"] = field(default_factory=list)
    custom_blocks: List["CustomBlockDef"] = field(default_factory=list)


@dataclass
class Script:
    hat: "Hat"
    body: List["Statement"] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Hats
# ---------------------------------------------------------------------------

@dataclass
class Hat:
    kind: str            # gf | spr | key | backdrop | receive | greater_than | clicked_clone | broadcast
    args: List[Any] = field(default_factory=list)
    line: int = 0


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

class Statement:
    line: int = 0


@dataclass
class BlockCall(Statement):
    """A built-in block call: e.g. say(...) , goto(x,y), pen.Down.

    `namespace` is None for global blocks (say, goto, move, ...).
    `method`  is the block name.
    `args`    is the list of expressions / atoms inside the parens.
    `post`    is the optional trailing paren group, e.g. the seconds in
              `say(Hello, World!)(2)`.
    """
    namespace: Optional[str]
    method: str
    args: List[Any]
    post: Optional[List[Any]] = None
    line: int = 0


@dataclass
class VarAssign(Statement):
    name: str
    value: Any
    line: int = 0


@dataclass
class VarModify(Statement):
    name: str
    op: str          # '+=' | '-=' | '*=' | '/='
    value: Any
    line: int = 0


@dataclass
class ListOp(Statement):
    list_name: str
    op: str          # 'add' | 'delete' | 'insert' | 'replace' | 'show' | 'hide'
    args: List[Any]
    line: int = 0


@dataclass
class IfStatement(Statement):
    cond: Any
    then_body: List[Statement]
    else_body: Optional[List[Statement]] = None
    line: int = 0


@dataclass
class RepeatStatement(Statement):
    times: Any
    body: List[Statement]
    line: int = 0


@dataclass
class RepeatUntilStatement(Statement):
    cond: Any
    body: List[Statement]
    line: int = 0


@dataclass
class WaitUntilStatement(Statement):
    """`waitUntil (cond)` - control_wait_until."""
    cond: Any
    line: int = 0


@dataclass
class ForeverStatement(Statement):
    body: List[Statement]
    line: int = 0


@dataclass
class WhileStatement(Statement):
    """Syntactic sugar: `while (c) { ... }` -> `repeatUntil(not c) { ... }`."""
    cond: Any
    body: List[Statement]
    line: int = 0


@dataclass
class ForEachStatement(Statement):
    """`forEach (var) in (number) { ... }` - hidden control_for_each block.

    Iterates `var` from 1 to `count`, running the body once per value.
    `var_name` is the variable to use as the loop counter.
    """
    var_name: str
    count: Any
    body: List[Statement]
    line: int = 0


@dataclass
class AllAtOnceStatement(Statement):
    """`allAtOnce { ... }` - hidden control_all_at_once block.

    Runs the body without yielding to the screen refresh between blocks
    (similar to a warp-mode custom block).
    """
    body: List[Statement]
    line: int = 0


@dataclass
class WaitStatement(Statement):
    secs: Any
    line: int = 0


@dataclass
class StopStatement(Statement):
    kind: str       # 'all' | 'this script' | 'other scripts in sprite' | 'other scripts in stage'
    line: int = 0


@dataclass
class BroadcastStatement(Statement):
    msg: Any
    wait: bool = False
    line: int = 0


@dataclass
class CustomBlockDef(Statement):
    """`def MyBlock(name, age) { ... }` - defines a custom block."""
    name: str
    params: List[Dict[str, str]]   # [{name, type}] type in {string|bool|number}
    body: List[Statement]
    warp: bool = False             # run without screen refresh
    line: int = 0


@dataclass
class CustomBlockCall(Statement):
    """A call to a user-defined custom block."""
    name: str
    args: List[Any]
    line: int = 0


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------

@dataclass
class NumberLit:
    value: float
    line: int = 0


@dataclass
class StringLit:
    value: str
    line: int = 0


@dataclass
class ColorLit:
    value: str    # like "#ff0000"
    line: int = 0


@dataclass
class VarRef:
    name: str
    line: int = 0


@dataclass
class ListRef:
    name: str
    index: Any
    line: int = 0


@dataclass
class BinOp:
    op: str          # '+','-','*','/','mod','>','<','=','and','or'
    left: Any
    right: Any
    line: int = 0


@dataclass
class UnaryOp:
    op: str          # 'not' or '-'
    operand: Any
    line: int = 0


@dataclass
class FuncCall:
    """Operator-like reporter: pickRandom(1,10), join(a,b), abs(x), ..."""
    name: str
    args: List[Any]
    line: int = 0


@dataclass
class BuiltinRef:
    """Direct references to Scratch reporters that have no arguments:
    answer, mouseX, mouseY, timer, loudness, daysSince2000, username,
    x, y, direction, size, costumeName, backdropName, volume, etc.
    """
    name: str
    line: int = 0


@dataclass
class BareRef:
    """A bare identifier used in expression context.

    Resolved at codegen time:
      * if the name matches a declared variable in the current target -> VarRef
      * if the name matches a builtin reporter (e.g. "answer", "mouseX") -> BuiltinRef
      * if the name matches a current custom-block parameter -> ArgumentRef
      * otherwise -> StringLit (literal text)
    """
    name: str
    line: int = 0


@dataclass
class ArgumentRef:
    """Reference to a custom block parameter (an argument_reporter block)."""
    name: str
    arg_id: str = ""  # filled in by codegen
    line: int = 0


@dataclass
class ListReporterRef:
    """A list reporter reference like `inventory.item(1)`, `inventory.length`,
    `inventory.contains(thing)`, `inventory.itemNum(thing)`, `inventory.contents`.

    Resolved at codegen time into the appropriate data_* block.
    """
    list_name: str
    method: str     # 'item' | 'length' | 'contains' | 'itemNum' | 'contents'
    args: List[Any]
    line: int = 0


@dataclass
class TernaryExpr:
    """Ternary expression: [if (cond) true_val else false_val]

    Desugared at codegen time into if/else that sets a temp variable.
    """
    cond: Any
    true_expr: Any
    false_expr: Any
    line: int = 0


@dataclass
class SoundImport:
    """sound name from "path.wav" - imports a sound file."""
    name: str
    path: str
    line: int = 0


@dataclass
class CostumeImport:
    """costume name from "path.png" - imports a costume file."""
    name: str
    path: str
    line: int = 0


@dataclass
class LocalVarDecl:
    """private x = value - declares a local variable inside a custom block."""
    name: str
    value: Any
    line: int = 0
