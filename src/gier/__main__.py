"""Command-line interface for ``gier``.

This module provides two commands:

``chier`` -- Code HIERarchy. Recognizes the code-block hierarchy of source
files and prints it as a single line (see ``gier.output``). A trailing
newline is always emitted.

``gier`` -- Grep code HIERarchy. Instead of querying a line number, it matches
a regular expression against the file's lines and, for each match, prints the
enclosing block hierarchy in the style of a ``chier`` code query.

chier
-----
    uv run chier PATH [PATH ...]
    uv run chier (-p|-c) LINE PATH

The language is detected from each file's extension (unknown extensions
default to Python). The tool operates on files; standard input is not read.

Query options take a 1-based ``LINE`` number:

* ``-p``/``--path-query``  -- print the chain of nested blocks (root first,
  separated by ``>``) that enclose that line.
* ``-c``/``--code-query``  -- like ``-p``, but also print the source of the
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

gier
----
    uv run gier [-iHh] [-M N] [-N N] PATTERN FILE [.. [FILE]]

For each FILE (expanded with ``glob.glob(..., recursive=True)``; the Python
glob syntax such as ``**/*.py`` is supported) every line matching PATTERN
yields a finding: the enclosing block path plus the block's source, formatted
exactly like a ``chier -c`` query. ``-i``/``-H``/``-h`` act like in GNU grep; ``-N``/``-M`` filter the code
block as in ``chier``; ``--color=auto|always|never`` highlights the matched
text (``auto`` colors only when stdout is a terminal).
"""

import glob
import os
import re
import sys

from .core import analyze, analyze_blocks, block_path, effective_block, block_len
from .output import format_blocks


CHIER_HELP = """chier \u2014 Code HIERarchy
Print a file's code-block hierarchy as a single line, or query the block path
to a given line. A hierarchy-aware, token-friendly companion to grep, built for
coding agents and LLMs that need to know *where* code lives \u2014 not just
that it exists.

Usage:
  chier PATH [PATH ...]
  chier (-p|-c) LINE PATH

Options:
  -p, --path-query LINE     print the chain of nested blocks enclosing LINE
  -c, --code-query LINE     like -p, but also print the block's source
  -N, --min-block-length N  merge blocks shorter than N lines into their parent (default 5)
  -M, --max-block-length N  collapse blocks longer than N lines to 'LINE:CODE' (default 99999)
      --exclude-fp-objects  treat object/collection literals as objects, not blocks
      --help                show this help and exit

The language is detected from each file's extension. Exit status is non-zero
if a file cannot be read or (for Python) fails to parse.
"""


GIER_HELP = """gier \u2014 Grep code HIERarchy
gier is grep with code block hierarchy awareness.

Search files for a Python regular expression and, for every hit, print the
enclosing block's hierarchy. A smarter replacement for grep, tuned first for
agentic / LLM code inspection yet just as handy for humans. Each match comes
with the function, method, or class it lives in; matches outside any block
(docstrings, imports, top-level code) fall back to classic grep output.

Usage:
  gier [-iHh] [-M N] [-N N] PATTERN FILE [.. [FILE]]

Options:
  -i, --ignore-case        case-insensitive match
  -H, --with-filename      always prefix matches with FILE:
  -h, --no-filename        never prefix (overrides -H and the auto rule)
  -N, --min-block-length N merge blocks shorter than N lines into their parent (default 5)
  -M, --max-block-length N collapse blocks longer than N lines to 'LINE:CODE' (default 20)
      --color[=WHEN]        color the matched text; WHEN is auto (default),
                            always, or never
      --format[=FMT]        output format (default md); md wraps each block's
                            source in a fenced code block with no separator
                            between findings, plain keeps the classic '--'
                            separator and prints source unfenced
      --help               show this help and exit

FILE arguments are expanded with Python's glob (recursive=True), so '**/*.py'
works; a literal path simply globs to itself. The file name is shown
automatically when more than one file matches.

Exit status: 0 if any match, 1 if none, 2 on error.
"""


# --------------------------------------------------------------------------- #
# chier
# --------------------------------------------------------------------------- #

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


_FORMATS = ("md", "plain")


def _parse_format(flag: str, value: str) -> str:
    v = value.strip().lower()
    if v in _FORMATS:
        return v
    raise SystemExit(f"{flag} must be one of {', '.join(_FORMATS)} (got {value!r})")


def _parse_int(flag: str, value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise SystemExit(f"{flag} requires an integer")
    if n < 1:
        raise SystemExit(f"{flag} must be >= 1")
    return n


# ANSI SGR sequences used when --color highlights a match.
ANSI_MATCH = "\x1b[1;31m"  # bold red, like GNU grep's default match color
ANSI_RESET = "\x1b[0m"


def colorize_match(text: str, regex: "re.Pattern") -> str:
    """Wrap every regex match in ``text`` with the match-color ANSI codes.

    Only the matched text is colored (never the filename, line number, or the
    rest of the line), mirroring GNU grep's default behavior.
    """
    parts: list[str] = []
    last = 0
    for m in regex.finditer(text):
        s, e = m.span()
        if s == e:
            continue  # ignore zero-width matches
        parts.append(text[last:s])
        parts.append(ANSI_MATCH)
        parts.append(text[s:e])
        parts.append(ANSI_RESET)
        last = e
    parts.append(text[last:])
    return "".join(parts)


def _code_for_line(blocks: list[tuple], source: str, query_line: int, min_length: int, max_length: int) -> tuple[str, list[str], bool]:
    """Return ``(block_path_str, code_lines, in_block)`` for a ``chier -c``-style query.

    Shared by ``chier`` (code query) and ``gier``. ``block_path_str`` is the
    ancestry chain (root first) of the block containing ``query_line``, merged
    past blocks shorter than ``min_length``. ``code_lines`` are the source
    lines of that block, or -- when the block is longer than ``max_length`` --
    a single ``[line-number]:[code line]`` line. ``in_block`` is ``False`` when
    ``query_line`` is not enclosed by any block (e.g. a module-level docstring
    or import), so the caller can skip such matches.
    """
    path_blocks, target = effective_block(blocks, query_line, min_length)
    code: list[str] = []
    if target is not None:
        lines = source.splitlines()
        lo = target[0] - 1
        hi = min(target[4], len(lines))
        code = lines[lo:hi]
        if code and block_len(target) > max_length:
            q = query_line - 1
            code = [f"{query_line}:{lines[q]}"] if 0 <= q < len(lines) else []
    return format_blocks(path_blocks), code, target is not None, target


def _common_leading_indent(lines: list[str]) -> str:
    """Longest whitespace prefix shared by every non-blank line.

    Blank (whitespace-only) lines are ignored, so an interior blank line does
    not stop a block from being dedented. The result is itself whitespace-only.
    """
    wss: list[str] = []
    for ln in lines:
        if ln.strip() == "":
            continue
        i = 0
        while i < len(ln) and ln[i] in " \t":
            i += 1
        wss.append(ln[:i])
    if not wss:
        return ""
    common = wss[0]
    for ws in wss[1:]:
        n = min(len(common), len(ws))
        k = 0
        while k < n and common[k] == ws[k]:
            k += 1
        common = common[:k]
    return common


def _format_md_code_block(code: list[str], source: str) -> str:
    """Wrap ``code`` in a markdown fence, dedenting a common leading indent.

    Only multi-line blocks (more than one source line) are dedented. The
    removed indentation is reported in the opening fence -- e.g.
    `` ```4 spaces unindented `` or `` ```1 tab unindented `` -- so that
    copy/search operations on the shortened block still line up with the real
    source. Pure-space and pure-tab indentation are handled; a mixed or absent
    common indent is left untouched. CRLF line endings from ``source`` are
    preserved.
    """
    ending = "\r\n" if "\r\n" in source else "\n"
    if len(code) <= 1:
        # single line of source: not a multi-line block, leave as-is
        return f"```{ending}{ending.join(code)}{ending}```"
    indent = _common_leading_indent(code)
    if not indent:
        return f"```{ending}{ending.join(code)}{ending}```"
    has_space = " " in indent
    has_tab = "\t" in indent
    if has_space and has_tab:
        # Mixed space/tab indent: only pure space / pure tab is handled.
        return f"```{ending}{ending.join(code)}{ending}```"
    n = len(indent)
    if has_space:
        note = f"{n} space{'s' if n != 1 else ''} unindented"
    else:
        note = f"{n} tab{'s' if n != 1 else ''} unindented"
    dedented = [(ln[len(indent):] if ln.startswith(indent) else ln) for ln in code]
    return f"```{note}{ending}{ending.join(dedented)}{ending}```"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--help" in argv:
        print(CHIER_HELP)
        return 0
    try:
        paths, path_query, code_query, min_length, max_length, allow_fp_objects = _parse_args(argv)
    except SystemExit as exc:
        print(f"chier: {exc}", file=sys.stderr)
        return 2

    if not paths:
        print("chier: no input file given", file=sys.stderr)
        return 2

    if path_query is not None and code_query is not None:
        print(
            "chier: use at most one of -p/--path-query, -c/--code-query",
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
        print(f"chier: cannot read {path}: {exc}", file=sys.stderr)
        return 1
    try:
        blocks = analyze_blocks(source, path=path, allow_fp_objects=allow_fp_objects)
    except SyntaxError as exc:
        print(f"chier: syntax error in {path}: {exc}", file=sys.stderr)
        return 1

    if code_query is not None:
        block_path_str, code, _, target = _code_for_line(blocks, source, query_line, min_length, max_length)
        collapsed = target is not None and block_len(target) > max_length
        if collapsed and code:
            # Collapsed by -M: squash onto a single line as blockpath:line:code
            # (no fence, no separate code section).
            sys.stdout.write(f"{block_path_str}:{code[0]}\n")
        else:
            sys.stdout.write(block_path_str + "\n")
            if code:
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
            print(f"chier: cannot read {path}: {exc}", file=sys.stderr)
            rc = 1
            continue
        try:
            sys.stdout.write(analyze(source, path=path, allow_fp_objects=allow_fp_objects) + "\n")
        except SyntaxError as exc:
            print(f"chier: syntax error in {path}: {exc}", file=sys.stderr)
            rc = 1
    return rc


# --------------------------------------------------------------------------- #
# gier
# --------------------------------------------------------------------------- #

def _is_glob(pattern: str) -> bool:
    """Whether ``pattern`` uses Python glob syntax (so an empty match is fine)."""
    return any(c in "*?[" for c in pattern)


def _compile_pattern(pattern: str, ignore_case: bool) -> "re.Pattern":
    """Compile a gier search pattern.

    ``re.MULTILINE`` is always set so ``^``/``$`` anchor to line boundaries;
    ``re.IGNORECASE`` is added for ``-i``.
    """
    flags = re.MULTILINE | (re.IGNORECASE if ignore_case else 0)
    return re.compile(pattern, flags)


def _parse_gier_args(argv: list[str]) -> tuple[str, list[str], bool, bool, bool, int, int, str, str]:
    ignore_case = False
    with_filename = False
    no_filename = False
    min_length = 5
    max_length = 20
    color_mode = "auto"
    fmt = "md"  # default: markdown code ticks, no '--' separator between findings
    i = 0
    positional: list[str] = []
    while i < len(argv):
        a = argv[i]
        if a == "--":
            positional = argv[i + 1:]
            break
        if a.startswith("--"):
            if a == "--ignore-case":
                ignore_case = True
            elif a == "--with-filename":
                with_filename = True
            elif a == "--no-filename":
                no_filename = True
            elif a in ("--min-block-length", "--max-block-length"):
                if i + 1 >= len(argv):
                    raise SystemExit(f"{a} requires a number")
                if a == "--min-block-length":
                    min_length = _parse_int(a, argv[i + 1])
                else:
                    max_length = _parse_int(a, argv[i + 1])
                i += 1
            elif a.startswith("--min-block-length="):
                min_length = _parse_int("--min-block-length", a.split("=", 1)[1])
            elif a.startswith("--max-block-length="):
                max_length = _parse_int("--max-block-length", a.split("=", 1)[1])
            elif a in ("--format", "--colour-format"):
                if i + 1 >= len(argv):
                    raise SystemExit(f"{a} requires a value ({'/'.join(_FORMATS)})")
                fmt = _parse_format(a, argv[i + 1])
                i += 1
            elif a.startswith("--format=") or a.startswith("--colour-format="):
                fmt = _parse_format("--format", a.split("=", 1)[1])
            elif a in ("--color", "--colour"):
                color_mode = "always"  # bare --color behaves like --color=always
            elif a.startswith("--color=") or a.startswith("--colour="):
                val = a.split("=", 1)[1]
                if val not in ("auto", "always", "never"):
                    raise SystemExit(
                        f"gier: --color must be auto, always or never (got {val!r})"
                    )
                color_mode = val
            else:
                raise SystemExit(f"unknown option {a}")
            i += 1
            continue
        if a.startswith("-") and a != "-":
            # Short flags; boolean flags may be combined (e.g. -ih), and -M/-N
            # may carry their value attached (-M3) or as the next argument.
            j = 1
            while j < len(a):
                ch = a[j]
                if ch == "i":
                    ignore_case = True
                elif ch == "H":
                    with_filename = True
                elif ch == "h":
                    no_filename = True
                elif ch in "MN":
                    rest = a[j + 1:]
                    if rest:
                        val = rest
                    else:
                        if i + 1 >= len(argv):
                            raise SystemExit(f"-{ch} requires a number")
                        i += 1
                        val = argv[i]
                    if ch == "M":
                        max_length = _parse_int(f"-{ch}", val)
                    else:
                        min_length = _parse_int(f"-{ch}", val)
                    break
                else:
                    raise SystemExit(f"unknown option -{ch}")
                j += 1
            i += 1
            continue
        positional.append(a)
        i += 1
    if len(positional) < 2:
        raise SystemExit("usage: gier [-iHh] [-M N] [-N N] PATTERN FILE [.. [FILE]]")
    pattern, files = positional[0], positional[1:]
    return pattern, files, ignore_case, with_filename, no_filename, min_length, max_length, color_mode, fmt


def gier_main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--help" in argv:
        print(GIER_HELP)
        return 0
    try:
        pattern, files, ignore_case, with_filename, no_filename, min_length, max_length, color_mode, fmt = _parse_gier_args(argv)
    except SystemExit as exc:
        print(f"gier: {exc}", file=sys.stderr)
        return 2

    if color_mode == "always":
        color_on = True
    elif color_mode == "never":
        color_on = False
    else:  # "auto": color only when writing to an interactive terminal
        color_on = sys.stdout.isatty()

    try:
        regex = _compile_pattern(pattern, ignore_case)
    except re.error as exc:
        print(f"gier: invalid pattern: {exc}", file=sys.stderr)
        return 2

    # Each FILE is expanded with one recursive glob. A bare file path simply
    # globs to itself; a glob pattern (e.g. ``**/*.py``) expands to all matches.
    all_files: list[str] = []
    for f in files:
        matches = glob.glob(f, recursive=True)
        if not matches and not _is_glob(f):
            print(f"gier: {f}: No such file or directory", file=sys.stderr)
            return 2
        all_files.extend(matches)
    if not all_files:
        print("gier: no input files", file=sys.stderr)
        return 2

    if no_filename:
        show_name = False
    elif with_filename:
        show_name = True
    else:
        # GNU grep behavior: show the file name when more than one file matched.
        show_name = len(all_files) > 1

    findings: list[str] = []
    rc = 1
    had_error = False
    for path in all_files:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                source = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            print(f"gier: {path}: {exc}", file=sys.stderr)
            had_error = True
            continue
        try:
            blocks = analyze_blocks(source, path=path)
        except SyntaxError:
            # Python source that fails to parse: report no block hierarchy for
            # this file rather than failing the whole run.
            blocks = []
        lines = source.splitlines()
        for lineno, line in enumerate(lines, start=1):
            if regex.search(line):
                prefix = f"{path}:" if show_name else ""
                block_path_str, code, in_block, target = _code_for_line(
                    blocks, source, lineno, min_length, max_length
                )
                matched = colorize_match(line, regex) if color_on else line
                if in_block:
                    collapsed = target is not None and block_len(target) > max_length
                    if color_on:
                        if collapsed:
                            # Block collapsed to a single "LINE:CODE" record.
                            code = [f"{lineno}:{matched}"]
                        else:
                            idx = lineno - target[0]
                            if 0 <= idx < len(code):
                                code = code[:idx] + [matched] + code[idx + 1:]
                    if collapsed:
                        # Collapsed by -M: squash onto a single line as
                        # blockpath:line:code -- no fence, no separator. This
                        # applies in every format variant.
                        finding = f"{prefix}{block_path_str}:{code[0]}\n"
                    else:
                        if fmt == "md":
                            # Markdown format: wrap the block's source in a
                            # fenced code block, dedenting any common leading
                            # indent (reported in the opening fence so
                            # copy/search still line up). The file name is
                            # never fenced (it is just a plain grep line when a
                            # match falls outside any block).
                            source_block = _format_md_code_block(code, source)
                        else:
                            source_block = "\n".join(code)
                        finding = f"{prefix}{block_path_str}\n{source_block}\n"
                else:
                    # No enclosing block (e.g. a module-level docstring or
                    # import): fall back to classic grep output, one
                    # "path:line:code" line. The file name follows -h/-H and
                    # the number of files found, exactly like the block
                    # findings.
                    finding = f"{prefix}{lineno}:{matched}\n"
                findings.append(finding)
                rc = 0

    if findings:
        if fmt == "md":
            # Markdown format: no inter-finding separator -- each block's
            # source is its own fenced code block, which delimits findings.
            out = "".join(findings)
        else:
            # Plain format: findings are separated by a "--" line (only
            # *between* findings, never after the last one), and only when
            # there is more than one finding, so a single match has no
            # separator at all.
            out = "".join(f + "--\n" for f in findings[:-1]) + findings[-1]
        sys.stdout.write(out)
    return 2 if had_error else rc


def _devnull_stdout() -> None:
    """Redirect stdout to /dev/null so a closed pipe does not crash on exit."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except Exception:
        pass


def _cli_entry(fn) -> int:
    try:
        return fn()
    except BrokenPipeError:
        _devnull_stdout()
        return 0


def chier_cli() -> int:
    return _cli_entry(main)


def gier_cli() -> int:
    return _cli_entry(gier_main)


if __name__ == "__main__":
    raise SystemExit(chier_cli())
