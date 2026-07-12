"""Command-line interface for ``codehierarchy``.

Usage
-----
    python -m codehierarchy [--language LANG] PATH [PATH ...]
    python -m codehierarchy [--language LANG] < FILE

Reads one or more files (or stdin) and prints, for each, a single line
describing its block structure (see ``codehierarchy.output``). A trailing
newline is always emitted.

The language is detected from each file's extension, or forced with
``--language`` (useful for stdin). Unknown extensions default to Python.
"""

import sys

from .core import analyze


def _parse_args(argv: list[str]) -> tuple[list[str], str | None]:
    paths: list[str] = []
    language: str | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-l", "--language"):
            if i + 1 >= len(argv):
                raise SystemExit("--language requires an argument")
            language = argv[i + 1]
            i += 2
            continue
        if a.startswith("--language="):
            language = a.split("=", 1)[1]
            i += 1
            continue
        paths.append(a)
        i += 1
    return paths, language


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        paths, language = _parse_args(argv)
    except SystemExit as exc:
        print(f"codehierarchy: {exc}", file=sys.stderr)
        return 2

    if not paths:
        source = sys.stdin.read()
        try:
            sys.stdout.write(analyze(source, path=None, language=language) + "\n")
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
            sys.stdout.write(analyze(source, path=path, language=language) + "\n")
        except SyntaxError as exc:
            print(f"codehierarchy: syntax error in {path}: {exc}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
