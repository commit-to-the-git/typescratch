"""TypeScratch - a small programming language that compiles to Scratch 3 (.sb3) files.

Library usage:

    import typescratch

    # Compile a .tysh file to a .sb3 next to it
    typescratch.file("C:/Users/pc/Desktop/thing.tysh")

    # Or specify the output path explicitly
    typescratch.file("thing.tysh", out="thing.sb3")

    # Compile from a source string
    src = '''
    s "Sprite1"
    when gf clicked {
      say(Hello, World!)(2)
    }
    '''
    sb3_bytes = typescratch.source(src)         # returns bytes
    typescratch.source(src, out="out.sb3")      # writes to file

    # Lower-level: compile and return (project_json, assets_dict)
    project, assets = typescratch.compile_source(src)

CLI usage:

    typescratch build thing.tysh                 # writes thing.sb3
    typescratch build thing.tysh --out out.sb3
    typescratch build thing.tysh --debug         # verbose AST/block dump
"""

from __future__ import annotations

import os
import sys
from typing import Optional, Tuple, Dict, Any

from .errors import (
    CompileError, SyntaxOops, ForgotOops, ArgumentOops, TypeMismatchOops, Debug,
    did_you_mean,
)
from .lexer import tokenize
from .parser import Parser
from .codegen import Codegen
from .sb3 import write_sb3, write_sb3_bytes


__version__ = "1.6.2"


def compile_source(src: str, filename: str = "<tysh>", debug: bool = False,
                   asset_root: Optional[str] = None
                   ) -> Tuple[dict, Dict[str, bytes]]:
    """Compile a TypeScratch source string to (project_json, assets_dict).

    `asset_root` is the base directory for resolving relative `img=` paths.
    If None, defaults to the directory of `filename` (or cwd).
    """
    dbg = Debug(enabled=debug)

    # Preprocess: handle `fuse "file.tysh"` directives
    src = _preprocess_fuse(src, filename, dbg)

    dbg.section("Tokens")
    toks = tokenize(src, filename)
    for t in toks:
        dbg.line(f"{t.line:>4}:{t.col:<3} {t.type:<14} {t.value!r}")

    dbg.section("AST")
    program = Parser(toks, filename).parse_program()
    dbg.line(repr(program))
    for tgt in program.targets:
        dbg.line(f"  target {tgt.kind} {tgt.name!r} scripts={len(tgt.scripts)} "
                 f"custom={len(tgt.custom_blocks)} costumes={len(tgt.costumes)}")
        for s in tgt.scripts:
            dbg.line(f"    hat={s.hat.kind} body={len(s.body)} stmts")

    if asset_root is None:
        if filename and filename != "<tysh>":
            asset_root = os.path.dirname(os.path.abspath(filename))
        else:
            asset_root = os.getcwd()

    cg = Codegen(program, debug=dbg, asset_root=asset_root)
    project, assets = cg.generate()
    return project, assets


def _preprocess_fuse(src: str, filename: str, dbg: Debug) -> str:
    """Handle `fuse "file.tysh"` directives by inlining file contents.

    The fuse directive must be on its own line.  The file path is relative
    to the directory of the source file.
    """
    import re
    base_dir = os.path.dirname(os.path.abspath(filename)) if filename != "<tysh>" else os.getcwd()

    lines = src.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        # Match: fuse "file.tysh" or fuse 'file.tysh'
        m = re.match(r'^fuse\s+["\']([^"\']+)["\']\s*$', stripped)
        if m:
            fuse_path = m.group(1)
            if not os.path.isabs(fuse_path):
                fuse_path = os.path.join(base_dir, fuse_path)
            if os.path.isfile(fuse_path):
                dbg.line(f"Fusing: {fuse_path}")
                with open(fuse_path, "r", encoding="utf-8") as f:
                    fused_content = f.read()
                # Recursively process fuse directives in the fused file
                fused_content = _preprocess_fuse(fused_content, fuse_path, dbg)
                result.append(f"// === fused from {m.group(1)} ===")
                result.extend(fused_content.split("\n"))
                result.append(f"// === end fuse ===")
            else:
                from .errors import ForgotOops
                raise ForgotOops(f'Cannot fuse file "{m.group(1)}" - file not found')
        else:
            result.append(line)

    return "\n".join(result)


def source(src: str, out: Optional[str] = None, debug: bool = False,
           filename: str = "<tysh>") -> bytes:
    """Compile a TypeScratch source string and return the .sb3 bytes.

    If `out` is given, also write to that file path.
    """
    project, assets = compile_source(src, filename=filename, debug=debug)
    sb3_bytes = write_sb3_bytes(project, assets)
    if out:
        with open(out, "wb") as f:
            f.write(sb3_bytes)
    return sb3_bytes


def file(path: str, out: Optional[str] = None, debug: bool = False) -> str:
    """Compile a .tysh file to a .sb3 file.

    Returns the output file path.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"TypeScratch source file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if out is None:
        # default: same name, .sb3 extension, next to input
        base, _ = os.path.splitext(path)
        out = base + ".sb3"
    source(src, out=out, debug=debug, filename=path)
    return out


# Friendly alias - `typescratch.compile("out.sb3")` after `typescratch.file("in.tysh")`
# Actually the user wanted `typescratch.file(...)` then `typescratch.compile(...)`.
# Let me support both styles:

def compile(out_path: str, src_path: Optional[str] = None, debug: bool = False) -> str:
    """Compile a .tysh source to a specific .sb3 output path.

    If `src_path` is None, looks for a .tysh file with the same basename
    as `out_path` (e.g. for `out.sb3`, looks for `out.tysh` in the same dir).
    """
    if src_path is None:
        base, _ = os.path.splitext(out_path)
        for ext in (".tysh", ".ts", ".tsh"):
            candidate = base + ext
            if os.path.isfile(candidate):
                src_path = candidate
                break
        if src_path is None:
            raise FileNotFoundError(
                f"no source file found for output {out_path!r} "
                f"(looked for {base}.tysh)"
            )
    return file(src_path, out=out_path, debug=debug)


__all__ = [
    "file",
    "source",
    "compile",
    "compile_source",
    "CompileError",
    "SyntaxOops",
    "ForgotOops",
    "ArgumentOops",
    "TypeMismatchOops",
    "did_you_mean",
    "__version__",
]
