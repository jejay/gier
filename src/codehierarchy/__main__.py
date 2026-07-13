"""Command-line interface for ``codehierarchy``.

Usage
-----
    python -m codehierarchy [--language LANG] PATH [PATH ...]
    python -m codehierarchy [--language LANG] < FILE
    python -m codehierarchy (-q|-s) LINE PATH      # block path to a line

Reads one or more files (or stdin) and prints, for each, a single line
Describing its block structure (see ``codehierarchy.output``). A trailing
newline is always emitted.

The language is detected from each file's extension, or forced with
``--language`` (useful for stdin). Unknown extensions default to Python.

Query options ``-q``/``--long-query`` and ``-s``/``--short-query`` take a
1-based ``LINE`` number. They print the chain of nested blocks (root first,
separated by ``>``) that enclose that line. ``-q`` additionally prints the
source of the innermost enclosing block on the following line(s).
"""

import sys

from .core import analyze, analyze_blocks, block_path
from .output import format_blocks


def _parse_args(argv: list[str]) -> tuple[list[str], str | None, int | None, int | None]:
    paths: list[str] = []
    language: str | None = None
    long_query: int | None = None
    short_query: int | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-q", "--long-query"):
            if i + 1 >= len(argv):
                raise SystemExit("--long-query/-q requires a line number")
            long_query = _parse_line("--long-query/-q", argv[i + 1])
            i += 2
            continue
        if a in ("-s", "--short-query"):
            if i + 1 >= len(argv):
                raise SystemExit("--short-query/-s requires a line number")
            short_query = _parse_line("--short-query/-s", argv[i + 1])
            i += 2
            continue
        if a.startswith("--long-query="):
            long_query = _parse_line("--long-query", a.split("=", 1)[1])
            i += 1
            continue
        if a.startswith("--short-query="):
            short_query = _parse_line("--short-query", a.split("=", 1)[1])
            i += 1
            continue
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
    return paths, language, long_query, short_query


def _parse_line(flag: str, value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise SystemExit(f"{flag} requires an integer line number")
    if n < 1:
        raise SystemExit(f"{flag} line number must be >= 1")
    return n


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        paths, language, long_query, short_query = _parse_args(argv)
    except SystemExit as exc:
        print(f"codehierarchy: {exc}", file=sys.stderr)
        return 2

    if long_query is not None and short_query is not None:
        print(
            "codehierarchy: use at most one of -q/--long-query, -s/--short-query",
            file=sys.stderr,
        )
        return 2

    query_line = long_query if long_query is not None else short_query
    if query_line is None:
        return _run_normal(paths, language)

    # Query mode: print the block path to the block containing `query_line`.
    if not paths:
        source = sys.stdin.read()
        path = None
    else:
        path = paths[0]
        try:
            with open(path, "r", encoding="utf-8") as fh:
                source = fh.read()
        except OSError as exc:
            print(f"codehierarchy: cannot read {path}: {exc}", file=sys.stderr)
            return 1
    try:
        blocks = analyze_blocks(source, path=path, language=language)
    except SyntaxError as exc:
        where = f" in {path}" if path else ""
        print(f"codehierarchy: syntax error{where}: {exc}", file=sys.stderr)
        return 1

    path_blocks = block_path(blocks, query_line)
    sys.stdout.write(format_blocks(path_blocks) + "\n")
    if long_query is not None and path_blocks:
        inner = path_blocks[-1]
        lines = source.splitlines()
        lo = inner[0] - 1
        hi = min(inner[4], len(lines))
        code = lines[lo:hi]
        if code:
            sys.stdout.write("\n".join(code) + "\n")
    return 0


def _run_normal(paths: list[str], language: str | None) -> int:
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
