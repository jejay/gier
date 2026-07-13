"""Block analyzer for explicit ``{``-delimited languages.

A small, language-agnostic tokenizer plus a "block matcher" that finds every
``{`` which begins a code block (control-flow statement, class/struct/enum/
namespace declaration, or a ``type name(...)`` definition) and pairs it with
its matching ``}``. The closing brace is, by definition, the last character of
the block.

Supported (via the same heuristic): C, C++, Objective-C, Java, Kotlin,
JavaScript, TypeScript, C#, Go, Rust, Swift, Scala, Dart, PHP, and friends.

The heuristic is intentionally simple and will have false positives/negatives
on unusual constructs (e.g. it may treat a C++ ``new Foo() { ... }`` object
initializer as a block, and skips bare/label blocks). It is tuned for typical
function/method/class/control-flow structure.
"""

from __future__ import annotations

from .output import format_blocks

# Block-introducing keywords and how their declaration is rendered.
_CONTROL = {
    "if", "else", "for", "while", "do", "switch", "try", "catch", "finally",
    "case", "default", "guard", "where", "foreach", "select", "loop", "when",
    "match",
}
_CLASSY = {
    "class", "struct", "interface", "enum", "union", "namespace", "protocol",
    "record", "extension", "trait", "impl", "module", "object", "actor",
}
_FUNCY = {"fn", "func", "function", "fun", "def", "sub"}

# Declaration-starting keywords. When one of these begins a new line
# (previous significant token on a different line, at paren depth 0), we start a
# fresh statement. This matters for languages without statement-terminating
# semicolons (Kotlin, Go, Rust, Swift, ...), where otherwise a top-level
# `package`/`import`/`annotation` would merge with the following `fun`/`class`.
_DECL_STARTERS = (
    _CONTROL
    | _CLASSY
    | _FUNCY
    | {
        "package", "import", "val", "var", "let", "const", "type",
        "trait", "impl", "mod", "namespace", "record", "protocol",
        "extension", "actor", "object", "struct", "interface", "enum",
        "class", "fun", "fn", "func", "function", "def", "sub",
    }
)


# --------------------------------------------------------------------------
# Tokenizer
# --------------------------------------------------------------------------
def tokenize(source: str) -> list[tuple[str, int, int, str]]:
    """Tokenize ``source`` into ``(text, line, col, kind)`` tuples.

    Whitespace and comments are skipped; strings/char/template literals are
    consumed as a single ``skip`` token so that braces inside them do not
    disturb brace accounting. A ``#`` at the start of a line (C/C++/Obj-C
    preprocessor, or a shebang) is skipped to end of (possibly continued) line
    so source line numbers are preserved.
    """
    tokens: list[tuple[str, int, int, str]] = []
    i, n = 0, len(source)
    line, col = 1, 1

    def emit(text: str, kind: str) -> None:
        nonlocal i, line, col
        tokens.append((text, line, col, kind))
        for ch in text:
            if ch == "\n":
                line += 1
                col = 1
            else:
                col += 1
        i += len(text)

    while i < n:
        c = source[i]
        if c == "\n":
            line += 1
            col = 1
            i += 1
            continue
        if c in " \t\r\f\v":
            col += 1
            i += 1
            continue
        # Preprocessor directive / shebang: skip to end of (continued) line.
        if c == "#" and col == 1:
            while i < n:
                ch = source[i]
                if ch == "\\" and i + 1 < n and source[i + 1] == "\n":
                    emit(source[i : i + 2], "skip")
                    continue
                if ch == "\n":
                    emit(ch, "skip")
                    break
                emit(ch, "skip")
            continue
        # Line comment.
        if c == "/" and i + 1 < n and source[i + 1] == "/":
            j = source.find("\n", i)
            if j == -1:
                j = n
            emit(source[i:j], "skip")
            continue
        # Block comment.
        if c == "/" and i + 1 < n and source[i + 1] == "*":
            k = i + 2
            while k + 1 < n and not (source[k] == "*" and source[k + 1] == "/"):
                k += 1
            emit(source[i : min(k + 2, n)], "skip")
            continue
        # String / char / template literal.
        if c in "\"'`":
            j = i + 1
            while j < n:
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == c:
                    j += 1
                    break
                j += 1
            emit(source[i:j], "skip")
            continue
        # Identifier / keyword.
        if c.isalpha() or c == "_" or c == "$":
            j = i
            while j < n and (source[j].isalnum() or source[j] in "_$"):
                j += 1
            emit(source[i:j], "word")
            continue
        # Number.
        if c.isdigit():
            j = i
            while j < n and (source[j].isalnum() or source[j] in "._"):
                j += 1
            emit(source[i:j], "word")
            continue
        # Structural single characters.
        if c in "{}()[];:,=<>":
            emit(c, "op")
            continue
        # Any other single character (operators, dots, etc.).
        emit(c, "op")

    return tokens


# --------------------------------------------------------------------------
# Block matching helpers
# --------------------------------------------------------------------------
def _strip_enclosing(header: list[tuple]) -> list[tuple]:
    """Drop the outermost ``(...)`` parameter/condition list and the outermost
    ``<...>`` generic/template list from a header's token list.

    Stripping first ``(`` to last ``)`` (rather than only the innermost pair)
    handles nested parentheses such as ``if (!full())``.
    """
    toks = list(header)
    # Strip the outermost ( ... ) group (params / condition).
    lparens = [i for i, t in enumerate(toks) if t[0] == "("]
    rparens = [i for i, t in enumerate(toks) if t[0] == ")"]
    if lparens and rparens and lparens[0] < rparens[-1]:
        del toks[lparens[0] : rparens[-1] + 1]
    # Strip the outermost < ... > group (templates / generics).
    lts = [i for i, t in enumerate(toks) if t[0] == "<"]
    gts = [i for i, t in enumerate(toks) if t[0] == ">"]
    if lts and gts and lts[0] < gts[-1]:
        del toks[lts[0] : gts[-1] + 1]
    return toks


def _is_word(t: str) -> bool:
    return t.isalnum() or t in ("_", "$") or (t and all(ch.isalnum() or ch in "_$" for ch in t))


def _join(texts: list[str]) -> str:
    """Join declaration tokens, spacing words apart but not operators.

    Yields ``MyClass::method`` and ``area:number`` instead of ``MyClass : :
    method`` / ``area : number``.
    """
    out: list[str] = []
    last: str | None = None
    for t in texts:
        if last is None:
            out.append(t)
        elif _is_word(last) and _is_word(t):
            out.append(" " + t)
        else:
            out.append(t)
        last = t
    return "".join(out)


def _compute_decl(core_texts: list[str]) -> str:
    for i, t in enumerate(core_texts):
        if t in _CLASSY:
            return _join(core_texts[i:])
    for i, t in enumerate(core_texts):
        if t in _FUNCY:
            return _join(core_texts[i:])
    for i, t in enumerate(core_texts):
        if t in _CONTROL:
            # Control-flow declarations are just the keyword(s): "if",
            # "else if", "for", "match", ... never the condition/expression.
            j = i
            while j < len(core_texts) and core_texts[j] in _CONTROL:
                j += 1
            return " ".join(core_texts[i:j])
    return _join(core_texts)


def _is_block(core_texts: list[str], prev_text: str | None) -> tuple[bool, bool]:
    """Return ``(is_block, is_arrow)``.

    Object/collection initializers (``= {``, ``: {``, ``, {``, ``[ {``,
    ``return {``) and arrow-function object literals (``=> ({``) are rejected.
    A plain ``=> {`` arrow function is accepted and flagged as an arrow block.
    """
    if prev_text in ("=", ":", ",", "[", "return"):
        return False, False
    if not core_texts:
        return False, False
    is_arrow = False
    for k in range(len(core_texts) - 1):
        if core_texts[k] == "=" and core_texts[k + 1] == ">":
            is_arrow = True
            if prev_text == "(":
                return False, False  # arrow returning an object literal
            break
    return True, is_arrow


# --------------------------------------------------------------------------
# Analyzer
# --------------------------------------------------------------------------
def curly_blocks(source: str, language: str | None = None) -> list[tuple]:
    raw = tokenize(source)
    toks = [t for t in raw if t[3] != "skip"]
    n = len(toks)

    blocks: list[tuple] = []
    depth = 0
    paren = 0  # parenthesis depth, so ';' inside for/if headers doesn't split
    in_for_header = False  # a 'for' header may use ';' as a clause separator
    stmt_start = None  # (line, col) of the first token of the current statement
    header: list[tuple] = []  # tokens of the current statement

    p = 0
    while p < n:
        text, line, col, kind = toks[p]
        if kind == "op" and text == "{":
            prev_text = toks[p - 1][0] if p > 0 else None
            if stmt_start is not None and header:
                core = _strip_enclosing(header)
                core_texts = [t[0] for t in core]
                ok, is_arrow = _is_block(core_texts, prev_text)
                if ok:
                    decl = "(arrow)" if is_arrow else _compute_decl(core_texts)
                    level = depth
                    # Find the matching '}'.
                    d = 1
                    q = p + 1
                    end_line, end_col = line, col
                    while q < n:
                        tt = toks[q][0]
                        if tt == "{":
                            d += 1
                        elif tt == "}":
                            d -= 1
                            if d == 0:
                                end_line, end_col = toks[q][1], toks[q][2]
                                break
                        q += 1
                    blocks.append(
                        (stmt_start[0], stmt_start[1], level, decl, end_line, end_col)
                    )
            depth += 1
            stmt_start = None
            header = []
            in_for_header = False
        elif kind == "op" and text == "}":
            depth = max(0, depth - 1)
            stmt_start = None
            header = []
            in_for_header = False
        elif kind == "op" and text == "(":
            paren += 1
            if stmt_start is not None:
                header.append((text, line, col, kind))
        elif kind == "op" and text == ")":
            paren = max(0, paren - 1)
            if stmt_start is not None:
                header.append((text, line, col, kind))
        elif kind == "op" and text == ";":
            if paren == 0 and not in_for_header:
                stmt_start = None
                header = []
        elif kind == "word":
            # A declaration keyword at the start of a new line begins a fresh
            # statement (see _DECL_STARTERS). Guard with paren == 0 so we don't
            # split a multi-line expression such as `val x = foo(\n  when (...)`.
            if (
                text in _DECL_STARTERS
                and paren == 0
                and (p == 0 or toks[p - 1][1] != line)
            ):
                stmt_start = None
                header = []
                in_for_header = False
            if stmt_start is None:
                stmt_start = (line, col)
                header = [(text, line, col, kind)]
                in_for_header = text == "for"
            else:
                header.append((text, line, col, kind))
        else:  # other operator tokens are part of the statement header
            if stmt_start is not None:
                header.append((text, line, col, kind))
        p += 1

    return blocks


def analyze_curly(source: str, language: str | None = None) -> str:
    """Return the single-line block-structure description of ``source``."""
    return format_blocks(curly_blocks(source, language))
