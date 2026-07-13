"""Language dispatch for ``gier``.

``analyze`` detects the language from the file extension (or an explicit
``--language`` override) and forwards to the appropriate analyzer:

* ``.py`` / ``.pyw`` / ``.pyi`` -> Python (AST based)
* curly-brace languages (C, C++, Objective-C, Java, Kotlin, JavaScript,
  TypeScript, C#, Go, Rust, Swift, Scala, Dart, PHP, ...) -> token based

The output format is identical for every language.
"""

from __future__ import annotations

import os

from .curly_analyzer import curly_blocks
from .python_analyzer import python_blocks
from .output import format_blocks

# Map file extensions to a language key.
EXT_LANG = {
    ".py": "python", ".pyw": "python", ".pyi": "python",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".c++": "cpp",
    ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp", ".h++": "cpp",
    ".java": "java",
    ".kt": "kotlin", ".kts": "kotlin",
    ".m": "objc", ".mm": "objcpp",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".swift": "swift",
    ".scala": "scala", ".sc": "scala",
    ".dart": "dart",
    ".php": "php",
}


def detect_language(path: str | None, language: str | None) -> str:
    """Resolve the language key from an explicit override or the file path.

    Falls back to ``"python"`` when the extension is unknown, since the tool
    originated as a Python analyzer.
    """
    if language:
        return language
    if path:
        ext = os.path.splitext(path)[1].lower()
        if ext in EXT_LANG:
            return EXT_LANG[ext]
    return "python"


def analyze_blocks(source: str, path: str | None = None, language: str | None = None, allow_fp_objects: bool = True) -> list[tuple]:
    """Return the raw block list for ``source``.

    Each block is ``(start_line, start_col, level, decl, end_line, end_col)``
    with 1-based columns. Dispatches on the detected language.

    ``allow_fp_objects`` only affects curly-brace languages. By default
    (``True``) a ``{`` after ``=``, ``:``, ``,``, ``[`` or ``return`` is treated
    as a block even though it may be an object/collection literal -- this also
    catches inline functions that look like object literals. Pass ``False`` to
    restore the stricter behavior that rejects those literals.
    """
    lang = detect_language(path, language)
    if lang == "python":
        return python_blocks(source)
    return curly_blocks(source, lang, allow_fp_objects=allow_fp_objects)


def analyze(source: str, path: str | None = None, language: str | None = None, allow_fp_objects: bool = True) -> str:
    """Return the single-line block-structure description of ``source``."""
    return format_blocks(analyze_blocks(source, path, language, allow_fp_objects=allow_fp_objects))


def block_path(blocks: list[tuple], line: int) -> list[tuple]:
    """Return the ancestry chain (root first) of the innermost block that
    contains ``line`` (1-based), or ``[]`` when no block contains it.

    ``line`` is taken to belong to the deepest (most-nested) block whose span
    covers it; its ancestors are found by walking up to the nearest preceding
    block at a lower level, which is the correct parent under a source-order
    (pre-order) traversal.
    """
    containing = [b for b in blocks if b[0] <= line <= b[4]]
    if not containing:
        return []
    innermost = max(containing, key=lambda b: b[2])
    idx = blocks.index(innermost)
    chain = [idx]
    cur = idx
    while True:
        parent = None
        for j in range(cur - 1, -1, -1):
            if blocks[j][2] < blocks[cur][2]:
                parent = j
                break
        if parent is None:
            break
        chain.append(parent)
        cur = parent
    chain.reverse()
    return [blocks[i] for i in chain]


def block_len(block: tuple) -> int:
    """Number of source lines a block spans (end_line - start_line + 1)."""
    return block[4] - block[0] + 1


def effective_block(blocks: list[tuple], line: int, min_length: int = 1) -> tuple[list[tuple], tuple | None]:
    """Resolve the block to report for a code query at ``line``.

    Returns ``(path_blocks, target)`` where ``target`` is the innermost block
    containing ``line`` after climbing past any blocks shorter than
    ``min_length`` -- a short block is treated as part of its parent, so the
    parent's path and source are reported instead. ``path_blocks`` is the
    ancestry chain (root first) of ``target``.

    Returns ``([], None)`` when no block contains ``line``.
    """
    chain = block_path(blocks, line)
    if not chain:
        return [], None
    i = len(chain) - 1
    while i > 0 and block_len(chain[i]) < min_length:
        i -= 1
    effective = chain[: i + 1]
    return effective, effective[-1]
