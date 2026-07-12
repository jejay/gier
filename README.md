# codehierarchy

A small Python tool that recognizes the **code-block structure** of a Python
file and prints it as a single line.

For every compound statement it reports:

* the **declaration** (the keyword — plus the name for `def`/`class` — with
  parameters/arguments and their brackets stripped),
* the 1-based `(line, column)` of the **first** character of the declaration
  keyword,
* the 1-based `(line, column)` of the **last** character of the last line of
  code contained in that block.

## Output format

```
<level>:<decl>{<start_line>,<start_col>~<end_line>,<end_col>}
```

Blocks are emitted in source order and separated by a relative indentation
marker:

| marker | meaning                                                        |
|--------|----------------------------------------------------------------|
| `>`    | next block is a **child** of the previous one (one level deeper) |
| `|`    | next block is a **sibling** of the previous one (same level)      |
| `<`    | next block is at a **higher** level; the number of `<` is the number of hierarchy levels ascended |

The whole output is exactly one line terminated by a single Unix newline.

### Example

Given a file whose `def abcd` starts at line 21, an `if` (child) at line 46,
a `for` (sibling) at line 52, and another top-level `if` at line 63, the output is:

```
0:def abcd{21,1~61,20}>1:if{46,5~48,16}|1:for{52,5~59,18}<0:if{63,1~69,13}
```

See `sample.py` for a file that reproduces exactly this output.

## Supported block types

`def` / `async def`, `class`, `if` / `elif` / `else`, `for` / `async for`
(including `for … else`), `while` (including `while … else`), `with` /
`async with`, `try` / `except` / `except*` / `else` / `finally`, and
`match` / `case`.

## Usage

```bash
# analyze a file (one line printed per file)
uv run codehierarchy file.py

# read from stdin
cat file.py | uv run python -m codehierarchy

# multiple files
uv run codehierarchy a.py b.py c.py
```

Exit status is non-zero if a file cannot be read or contains a syntax error.

## Library use

```python
from codehierarchy import analyze

description = analyze(open("file.py").read())
```

## How it works

The source is parsed with the standard-library `ast` module. Every compound
statement node contributes a block; `else`/`finally` clauses (which have no
dedicated AST node for their header) are located by scanning the source. Block
extents come from each node's `end_lineno`/`end_col_offset`, which the parser
computes across the full subtree, so a block's end reflects the deepest line of
code it contains. Indentation levels are derived from each header's column.
