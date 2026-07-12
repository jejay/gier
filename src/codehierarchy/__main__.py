"""Command-line interface for ``codehierarchy``.

Usage
-----
    python -m codehierarchy PATH [PATH ...]
    python -m codehierarchy < FILE.py

Reads one or more Python files (or stdin) and prints, for each, a single line
describing its block structure (see ``codehierarchy.core``). A trailing newline
is always emitted.
"""

import sys

from .core import analyze


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    paths = argv

    if not paths:
        source = sys.stdin.read()
        try:
            sys.stdout.write(analyze(source) + "\n")
        except SyntaxError as exc:
            print(f"codehierarchy: syntax error: {exc}", file=sys.stderr)
            return 1
        return 0

    rc = 0
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                source = fh.read()
        except OSError as exc:
            print(f"codehierarchy: cannot read {path}: {exc}", file=sys.stderr)
            rc = 1
            continue
        try:
            sys.stdout.write(analyze(source) + "\n")
        except SyntaxError as exc:
            print(f"codehierarchy: syntax error in {path}: {exc}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
