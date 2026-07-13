"""Command-line interface for ``codehierarchy``.

Usage
-----
    python -m codehierarchy PATH [PATH ...]
    python -m codehierarchy (-p|-c) LINE PATH

Reads one or more files and prints, for each, a single line describing its
block structure (see ``codehierarchy.output``). A trailing newline is always
emitted.

The language is detected from each file's extension (unknown extensions
default to Python). The tool operates on files; standard input is not read.

Query options take a 1-based ``LINE`` number:

* ``-p``/``--path-query``  -- print the chain of nested blocks (root first,
  separated by ``>``) that enclose that line.
* ``-c``/``--code-query``  -- like ``-b``, but also print the source of the
  innermost enclosing block afterwards.

For ``-c`` two length filters apply:

* ``-N``/``--min-block-length`` (default 5) -- blocks shorter than ``N`` lines
  are not treated as their own block; they are merged into their parent, so
  the parent's path and source are reported instead.
* ``-M``/``--max-block-length`` (default 99999) -- blocks longer than ``M``
  lines are not printed verbatim; their source is collapsed to one
  ``[line-number]:[code line]`` per line.

By default a ``{`` after ``=``, ``:``, ``,``, ``[`` or ``return`` is treated
as a block even though it may be an object/collection literal -- this catches
inline functions that look like object literals (e.g. Swift closures,
switch-case blocks) at the cost of some false-positive objects. Pass
``--exclude-fp-objects`` to revert to the stricter heuristic that rejects
those object/collection literals.
"""

import sys

from .core import analyze, analyze_blocks, block_path, effective_block, block_len
from .output import format_blocks


def _parse_args(argv: list[str]) -> tuple[list[str], int | None, int | None, int, int, bool]:
    paths: list[str] = []
    path_query: int | None = None
    code_query: int | None = None
    min_length: int = 5
    max_length: int = 99999
    allow_fp_objects: bool = True
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-p", "--path-query"):
            if i + 1 >= len(argv):
                raise SystemExit("--path-query/-p requires a line number")
            path_query = _parse_line("--path-query/-p", argv[i + 1])
            i += 2
            continue
        if a in ("-c", "--code-query"):
            if i + 1 >= len(argv):
                raise SystemExit("--code-query/-c requires a line number")
            code_query = _parse_line("--code-query/-c", argv[i + 1])
            i += 2
            continue
        if a in ("-N", "--min-block-length"):
            if i + 1 >= len(argv):
                raise SystemExit("--min-block-length/-N requires a number")
            min_length = _parse_int("--min-block-length/-N", argv[i + 1])
            i += 2
            continue
        if a in ("-M", "--max-block-length"):
            if i + 1 >= len(argv):
                raise SystemExit("--max-block-length/-M requires a number")
            max_length = _parse_int("--max-block-length/-M", argv[i + 1])
            i += 2
            continue
        if a in ("--exclude-fp-objects",):
            allow_fp_objects = False
            i += 1
            continue
        if a.startswith("--path-query="):
            path_query = _parse_line("--path-query/-p", a.split("=", 1)[1])
            i += 1
            continue
        if a.startswith("--code-query="):
            code_query = _parse_line("--code-query", a.split("=", 1)[1])
            i += 1
            continue
        if a.startswith("--min-block-length="):
            min_length = _parse_int("--min-block-length", a.split("=", 1)[1])
            i += 1
            continue
        if a.startswith("--max-block-length="):
            max_length = _parse_int("--max-block-length", a.split("=", 1)[1])
            i += 1
            continue
        if a.startswith("--exclude-fp-objects="):
            allow_fp_objects = not _parse_bool("--exclude-fp-objects", a.split("=", 1)[1])
            i += 1
            continue
        paths.append(a)
        i += 1
    return paths, path_query, code_query, min_length, max_length, allow_fp_objects


def _parse_line(flag: str, value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise SystemExit(f"{flag} requires an integer line number")
    if n < 1:
        raise SystemExit(f"{flag} line number must be >= 1")
    return n


def _parse_bool(flag: str, value: str) -> bool:
    v = value.strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    raise SystemExit(f"{flag} requires a boolean (true/false)")


def _parse_int(flag: str, value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise SystemExit(f"{flag} requires an integer")
    if n < 1:
        raise SystemExit(f"{flag} must be >= 1")
    return n


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        paths, path_query, code_query, min_length, max_length, allow_fp_objects = _parse_args(argv)
    except SystemExit as exc:
        print(f"codehierarchy: {exc}", file=sys.stderr)
        return 2

    if not paths:
        print("codehierarchy: no input file given", file=sys.stderr)
        return 2

    if path_query is not None and code_query is not None:
        print(
            "codehierarchy: use at most one of -p/--path-query, -c/--code-query",
            file=sys.stderr,
        )
        return 2

    query_line = code_query if code_query is not None else path_query
    if query_line is None:
        return _run_normal(paths, allow_fp_objects)

    # Query mode: print the block path to the block containing `query_line`.
    path = paths[0]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            source = fh.read()
    except OSError as exc:
        print(f"codehierarchy: cannot read {path}: {exc}", file=sys.stderr)
        return 1
    try:
        blocks = analyze_blocks(source, path=path, allow_fp_objects=allow_fp_objects)
    except SyntaxError as exc:
        print(f"codehierarchy: syntax error in {path}: {exc}", file=sys.stderr)
        return 1

    if code_query is not None:
        path_blocks, target = effective_block(blocks, query_line, min_length)
        sys.stdout.write(format_blocks(path_blocks) + "\n")
        if target is not None:
            lines = source.splitlines()
            lo = target[0] - 1
            hi = min(target[4], len(lines))
            code = lines[lo:hi]
            if code:
                if block_len(target) > max_length:
                    # Fallback: the block overflows the threshold, so print only
                    # the queried line (with its number) instead of the full
                    # block source.
                    q = query_line - 1
                    code = [f"{query_line}:{lines[q]}"] if 0 <= q < len(lines) else []
                sys.stdout.write("\n".join(code) + "\n")
        return 0

    # Path-only query.
    path_blocks = block_path(blocks, query_line)
    sys.stdout.write(format_blocks(path_blocks) + "\n")
    return 0


def _run_normal(paths: list[str], allow_fp_objects: bool = False) -> int:
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
            sys.stdout.write(analyze(source, path=path, allow_fp_objects=allow_fp_objects) + "\n")
        except SyntaxError as exc:
            print(f"codehierarchy: syntax error in {path}: {exc}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
