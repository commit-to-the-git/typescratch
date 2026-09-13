"""CLI entry point for TypeScratch.

Usage:
    typescratch build <file.tysh> [--out <out.sb3>] [--debug]
    typescratch run <file.tysh> [--debug]
    typescratch ide [file.tysh]
    typescratch decompile <file.sb3> [--out <file.tysh>]
    typescratch fmt <file.tysh>
    typescratch meow
    typescratch version
    typescratch help
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import __version__, file as _file
from .errors import CompileError


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="typescratch",
        description="Compile .tysh source files to Scratch 3 (.sb3) files.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="Compile a .tysh file to .sb3")
    p_build.add_argument("source", help="path to .tysh source file")
    p_build.add_argument("--out", "-o", default=None, help="output .sb3 path")
    p_build.add_argument("--debug", action="store_true", help="verbose debug output")

    p_run = sub.add_parser("run", help="Alias for build")
    p_run.add_argument("source")
    p_run.add_argument("--out", "-o", default=None)
    p_run.add_argument("--debug", action="store_true")

    p_ide = sub.add_parser("ide", help="Launch the TypeScratch IDE")
    p_ide.add_argument("source", nargs="?", default=None, help="optional .tysh file to open")

    p_decompile = sub.add_parser("decompile", help="Decompile a .sb3 file to .tysh")
    p_decompile.add_argument("source", help="path to .sb3 file")
    p_decompile.add_argument("--out", "-o", default=None, help="output .tysh path")

    p_fmt = sub.add_parser("fmt", help="Format a .tysh file (auto-indent)")
    p_fmt.add_argument("source", help="path to .tysh file")
    p_fmt.add_argument("--out", "-o", default=None, help="output path (default: in-place)")

    sub.add_parser("meow", help="Print the Scratch Cat in ASCII art")

    p_install = sub.add_parser("install", help="Install a package from GitHub")
    p_install.add_argument("repo", help="github user/repo or user/repo@tag")

    p_uninstall = sub.add_parser("uninstall", help="Remove an installed package")
    p_uninstall.add_argument("name", help="package name")

    sub.add_parser("list", help="List installed packages")

    sub.add_parser("version", help="Print version")

    args = parser.parse_args(argv)

    if args.cmd == "version":
        print(f"TypeScratch v{__version__}")
        return 0

    if args.cmd == "ide":
        from .ide import run_ide
        run_ide(args.source)
        return 0

    if args.cmd == "decompile":
        from .decompiler import decompile_to_file
        try:
            out = decompile_to_file(args.source, args.out)
            print(f"OK: decompiled to {out}", file=sys.stderr)
            return 0
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

    if args.cmd == "fmt":
        return _format_file(args.source, args.out)

    if args.cmd == "meow":
        return _meow()

    if args.cmd == "install":
        from .package_manager import install
        return install(args.repo)

    if args.cmd == "uninstall":
        from .package_manager import uninstall
        return uninstall(args.name)

    if args.cmd == "list":
        from .package_manager import list_packages
        return list_packages()

    if args.cmd in ("build", "run"):
        try:
            out_path = _file(args.source, out=args.out, debug=args.debug)
            print(f"OK: wrote {out_path}", file=sys.stderr)
            return 0
        except CompileError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"internal error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return 3

    parser.print_help()
    return 1


def _format_file(path: str, out: Optional[str] = None) -> int:
    """Format a .tysh file with proper indentation."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    formatted = []
    indent = 0
    for line in lines:
        stripped = line.strip()
        # Decrease indent for closing braces
        if stripped.startswith("}"):
            indent = max(0, indent - 1)
        # Add the line with proper indent
        if stripped:
            formatted.append("  " * indent + stripped + "\n")
        else:
            formatted.append("\n")
        # Increase indent after opening braces
        # Count opening and closing braces on this line
        opens = stripped.count("{") - stripped.count("}")
        if opens > 0 and not stripped.startswith("}"):
            indent += opens

    out_path = out or path
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(formatted)
    print(f"OK: formatted {path}" + (f" -> {out_path}" if out else " (in-place)"), file=sys.stderr)
    return 0


def _meow() -> int:
    """Print the Scratch Cat in ASCII art."""
    import os
    meow_path = os.path.join(os.path.dirname(__file__), "meow.txt")
    try:
        with open(meow_path, "r") as f:
            print(f.read())
    except FileNotFoundError:
        print("Meow! 🐱")
    return 0


if __name__ == "__main__":
    sys.exit(main())
