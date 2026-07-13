"""Shared output formatter for all language analyzers.

Given a list of blocks, each ``(start_line, start_col, level, decl,
end_line, end_col)`` with 1-based columns, render the single-line description
used by every analyzer:

    <level>:<decl>{<start_line>,<start_col>~<end_line>,<end_col>}

Blocks are ordered by source position and separated by relative indentation
markers (``>`` child, ``|`` sibling, ``<`` ascended levels).
"""

from __future__ import annotations


def format_blocks(blocks: list[tuple]) -> str:
    if not blocks:
        return ""
    # Sort by source position (pre-order / source order).
    blocks = sorted(blocks, key=lambda b: (b[0], b[1]))

    parts: list[str] = []
    prev_level: int | None = None
    for start_line, start_col, level, decl, end_line, end_col in blocks:
        if prev_level is None:
            marker = ""
        elif level == prev_level + 1:
            marker = ">"
        elif level == prev_level:
            marker = "|"
        elif level < prev_level:
            marker = "<" * (prev_level - level)
        else:  # level > prev_level (only ever by 1 in well-formed code)
            marker = ">" * (level - prev_level)
        parts.append(f"{marker}{level}/{decl}{{{start_line},{start_col}~{end_line},{end_col}}}")
        prev_level = level

    return "".join(parts)
