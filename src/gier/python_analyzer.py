"""Block analyzer for Python, based on the standard-library ``ast`` module.

For every compound statement it reports its declaration (keyword plus name for
``def``/``class``, with parameters/arguments and their brackets stripped), the
1-based position of the first character of the declaration keyword, and the
1-based position of the last character of the last line of code contained in
the block.
"""

from __future__ import annotations

import ast
import re

from .output import format_blocks

_KW_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\b")


def _first_word(line: str, col: int) -> str:
    """Return the first identifier starting at/after column ``col`` on ``line``."""
    m = _KW_RE.match(line[col:])
    return m.group(1) if m else ""


def _if_keyword(node: ast.If, src_lines: list[str]) -> str:
    word = _first_word(src_lines[node.lineno - 1], node.col_offset)
    return "elif" if word == "elif" else "if"


def _except_keyword(node: ast.ExceptHandler, src_lines: list[str]) -> str:
    word = _first_word(src_lines[node.lineno - 1], node.col_offset)
    return "except*" if word == "except*" else "except"


def _find_keyword_line(
    src_lines: list[str], from_line: int, to_line: int, indent: int, keyword: str
) -> int | None:
    """Find the 1-based line in ``[from_line + 1, to_line]`` whose (stripped)
    content begins with ``<keyword>:`` at exactly ``indent`` columns, skipping
    blank and comment-only lines.

    Used to locate the ``else:`` / ``finally:`` headers of a compound statement,
    which have no dedicated AST node.
    """
    pat = re.compile(r"^" + re.escape(keyword) + r"\b")
    for ln in range(from_line + 1, to_line + 1):
        if ln - 1 >= len(src_lines):
            break
        raw = src_lines[ln - 1]
        # Drop an inline comment before matching so "# else:" is ignored.
        code = raw.split("#", 1)[0]
        if not code.strip():
            continue
        if (len(raw) - len(raw.lstrip())) != indent:
            continue
        if pat.match(code.strip()):
            return ln
    return None


def _body_end_line(node) -> int:
    """Last source line of a node's *main* body (before any orelse/finalbody)."""
    body = getattr(node, "body", None)
    if body:
        last = body[-1]
        el = getattr(last, "end_lineno", None)
        if el is not None:
            return el
    return getattr(node, "end_lineno", None) or node.lineno


def _uses_body_scope(node) -> bool:
    """True for statement forms whose trailing clauses (elif/else for ``if``,
    except/else/finally for ``try``, and the ``else`` of ``for``/``while``) are
    separate *sibling* blocks rather than part of this block's own extent.
    """
    if isinstance(node, ast.If):
        return True
    if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
        return True
    if isinstance(node, ast.Try):
        return True
    if hasattr(ast, "TryStar") and isinstance(node, ast.TryStar):
        return True
    return False


def _node_end(node, src_lines: list[str]):
    """End position (end_lineno, end_col_offset) of a block.

    For statements with same-level trailing clauses the block ends at the end
    of its own primary ``body`` (the clause is reported as a separate block).
    For everything else the end is the whole construct, which correctly
    includes any *nested* child blocks.
    """
    if _uses_body_scope(node) and getattr(node, "body", None):
        last = node.body[-1]
        el = getattr(last, "end_lineno", None)
        ec = getattr(last, "end_col_offset", None)
        if el is not None and ec is not None:
            return el, ec
    return getattr(node, "end_lineno", None), getattr(node, "end_col_offset", None)


def _add_case(case, src_lines: list[str], add) -> None:
    """Add a `case` header entry for one arm of a `match` statement.

    Works across Python versions: 3.10-3.13 expose a ``MatchCase`` node with
    its own position; 3.14+ expose a ``match_case`` whose position lives on the
    ``pattern`` node (just after the ``case`` keyword), so we locate it in the
    source.
    """
    if getattr(case, "lineno", None) is not None:
        lineno, col = case.lineno, case.col_offset
    else:
        pat = case.pattern
        line = src_lines[pat.lineno - 1]
        m = re.search(r"(?<![A-Za-z0-9_])case\b", line)
        col = m.start() if m else pat.col_offset - len("case ")
        lineno = pat.lineno
    body = getattr(case, "body", None) or []
    if body:
        el, ec = _stmt_end(body[-1], lineno, src_lines)
    else:
        el = lineno
        ec = len(src_lines[lineno - 1]) if 0 <= lineno - 1 < len(src_lines) else col
    add(lineno, col, el, ec, "case")


def _stmt_end(stmt, fallback_line: int, src_lines: list[str]):
    el = getattr(stmt, "end_lineno", None)
    ec = getattr(stmt, "end_col_offset", None)
    if el is None:
        el = fallback_line
    if ec is None:
        el = fallback_line
        line = src_lines[fallback_line - 1] if 0 <= fallback_line - 1 < len(src_lines) else ""
        ec = len(line)
    return el, ec


def _maybe_add_else(node, src_lines: list[str], add) -> None:
    if not node.orelse:
        return
    # An `elif` puts an `If` node at the head of orelse; only a plain `else`
    # has a non-If first statement.
    if isinstance(node, ast.If) and isinstance(node.orelse[0], ast.If):
        return
    indent = node.col_offset
    from_line = _body_end_line(node)
    to_line = node.end_lineno
    ln = _find_keyword_line(src_lines, from_line, to_line, indent, "else")
    if ln is None:
        return
    el, ec = _stmt_end(node.orelse[-1], ln, src_lines)
    add(ln, indent, el, ec, "else")


def _add_try_else_finally(try_node, src_lines: list[str], add) -> None:
    indent = try_node.col_offset
    from_line = _body_end_line(try_node)
    for h in try_node.handlers:
        hl = getattr(h, "end_lineno", None)
        if hl and hl > from_line:
            from_line = hl
    to_line = try_node.end_lineno

    if try_node.orelse:
        ln = _find_keyword_line(src_lines, from_line, to_line, indent, "else")
        if ln is not None:
            el, ec = _stmt_end(try_node.orelse[-1], ln, src_lines)
            add(ln, indent, el, ec, "else")
            from_line = el
    if try_node.finalbody:
        ln = _find_keyword_line(src_lines, from_line, to_line, indent, "finally")
        if ln is not None:
            el, ec = _stmt_end(try_node.finalbody[-1], ln, src_lines)
            add(ln, indent, el, ec, "finally")


def python_blocks(source: str) -> list[tuple]:
    """Return the raw block list for ``source``.

    Each block is ``(start_line, start_col, level, decl, end_line, end_col)``
    with 1-based columns, ready to be rendered by ``output.format_blocks``.
    """
    tree = ast.parse(source)
    src_lines = source.splitlines()
    # (lineno, col_offset, end_lineno, end_col_offset, decl)
    raw: list[tuple[int, int, int, int, str]] = []

    def add(node, decl: str) -> None:
        sl, sc = node.lineno, node.col_offset
        el, ec = _node_end(node, src_lines)
        if el is None or ec is None:
            el = sl
            ec = len(src_lines[sl - 1]) if 0 <= sl - 1 < len(src_lines) else sc
        raw.append((sl, sc, el, ec, decl))

    def add_synthetic(lineno, indent, end_lineno, end_col_offset, decl) -> None:
        raw.append((lineno, indent, end_lineno, end_col_offset, decl))

    def visit(node) -> None:
        if isinstance(node, ast.FunctionDef):
            add(node, f"def {node.name}")
        elif isinstance(node, ast.AsyncFunctionDef):
            add(node, f"async def {node.name}")
        elif isinstance(node, ast.ClassDef):
            add(node, f"class {node.name}")
        elif isinstance(node, ast.If):
            add(node, _if_keyword(node, src_lines))
            _maybe_add_else(node, src_lines, add_synthetic)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            add(node, "async for" if isinstance(node, ast.AsyncFor) else "for")
            _maybe_add_else(node, src_lines, add_synthetic)
        elif isinstance(node, ast.While):
            add(node, "while")
            _maybe_add_else(node, src_lines, add_synthetic)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            add(node, "async with" if isinstance(node, ast.AsyncWith) else "with")
        elif isinstance(node, ast.Try):
            add(node, "try")
            _add_try_else_finally(node, src_lines, add_synthetic)
        elif hasattr(ast, "TryStar") and isinstance(node, ast.TryStar):
            add(node, "try")
            _add_try_else_finally(node, src_lines, add_synthetic)
        elif isinstance(node, ast.ExceptHandler):
            add(node, _except_keyword(node, src_lines))
        elif hasattr(ast, "Match") and isinstance(node, ast.Match):
            add(node, "match")
            for case in node.cases:
                _add_case(case, src_lines, add_synthetic)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)

    if not raw:
        return ""

    # Map each distinct indentation (col_offset) to an integer level.
    indents = sorted({r[1] for r in raw})
    level_of = {ind: i for i, ind in enumerate(indents)}

    blocks = []
    for sl, sc, el, ec, decl in raw:
        level = level_of[sc]
        # 1-based start column = col_offset + 1; 1-based end column =
        # end_col_offset (exclusive 0-based) == last character position.
        blocks.append((sl, sc + 1, level, decl, el, ec))

    return blocks


def analyze_python(source: str) -> str:
    """Return the single-line block-structure description of ``source``."""
    return format_blocks(python_blocks(source))
