# chier & gier — structure-aware code search for agents

`chier` (Code HIERarchy) and `gier` (Grep code HIERarchy) are small, fast
code-inspection tools that answer a question plain `grep` can't: **what block
of code does this live in?** They are built for coding agents and LLMs that
need structural context — the enclosing function, class, and control flow —
rather than a bare line ripped out of its surroundings.

* **`chier`** prints a file's block structure as a single compact line, or
  answers *"what encloses line N?"* as a path of nested blocks.
* **`gier`** greps a pattern and, for every hit, prints the enclosing block —
  so an agent gets `file:line:code` **and** the function or class it sits in.

Both speak every language `chier` understands (Python, C, C++, Java, Kotlin,
JavaScript, TypeScript, C#, Go, Rust, Swift, Scala, Dart, PHP, …), detect the
language from the file extension, and need no real parser — just a deliberately
simple, tolerant block matcher.

## Why structure-aware search?

A flat `grep` result tells a model *that* a symbol exists, but not *where* it
belongs. `gier` closes that gap: each match arrives wrapped in its enclosing
block path and source, so the model immediately sees the function, method, or
class a snippet lives in — without you writing a line of tree-sitter. Output
stays terse and token-friendly (one line per block, or a single `line:code`
fallback for huge blocks), which keeps agent context windows small.

## Output format

Every block is described by one line:

```
<level>/<decl>{<start_line>,<start_col>~<end_line>,<end_col>}
```

Blocks are separated by relative markers: `>` child, `|` sibling, `<` ascended
levels. The whole description is exactly one line, terminated by a single
newline.

### Example (Python)

```
0/def abcd{21,1~61,20}>1/if{46,5~48,16}|1/for{52,5~59,18}<0/if{63,1~69,13}
```

This reads: `def abcd` (line 21) contains an `if` (46) and a sibling `for`
(52); back at the top level, another `if` (63).

## chier — Code HIERarchy

```bash
uv run chier PATH [PATH ...]
uv run chier (-p|-c) LINE PATH
```

Options:

* `-p LINE` / `--path-query LINE` — print the chain of nested blocks enclosing
  `LINE` (root first, `>`-separated).
* `-c LINE` / `--code-query LINE` — like `-p`, plus the block's source.
* `-N N` / `--min-block-length N` (default `5`) — blocks shorter than `N` lines
  merge into their parent, so you get the enclosing scope, not a one-liner.
* `-M N` / `--max-block-length N` (default `99999`) — blocks longer than `N`
  lines collapse to a single `LINE:CODE` line, keeping output compact.
* `--exclude-fp-objects` — by default a `{` after `= : , [ return` is treated
  as a block (capturing closures that look like object literals); pass this to
  revert to the stricter heuristic.
* `--help` — show usage and exit.

## gier — Grep code HIERarchy

```bash
uv run gier [-iHh] [-M N] [-N N] PATTERN FILE [.. [FILE]]
```

For each `FILE` (expanded with Python's `glob`, so `**/*.py` works) every line
matching the compiled `PATTERN` yields a finding:

* **inside a block** → the enclosing block path plus its source, exactly like a
  `chier -c` query;
* **outside any block** (docstring, import, top-level statement) → a classic
  grep line `path:line:code`.

Options:

* `-i` / `--ignore-case` — case-insensitive (compiled with `re.IGNORECASE`;
  `re.MULTILINE` is always set).
* `-H` / `--with-filename` — always prefix `path:`.
* `-h` / `--no-filename` — never prefix (overrides `-H` and the auto rule).
* `-N N` / `--min-block-length N` (default `5`) and `-M N` /
  `--max-block-length N` (default `20`) — filter the code block; `-M` defaults
  to `20` so large blocks stay token-friendly for agents.
* `--help` — show usage and exit.

The file name is printed (as `path:`) when `-H` is given, or automatically
when the globs resolve to more than one file. Findings are separated by a `--`
line (only between findings, never after the last). Exit status: `0` match,
`1` none, `2` error.

## Library use

```python
from codehierarchy import analyze

description = analyze(open("file.c").read(), path="file.c")
```

## How it works

* **Python** — the `ast` module turns each compound statement into a block;
  `else`/`finally` headers are recovered by scanning the source.
* **Curly-brace languages** — a tiny tokenizer (skipping strings, comments,
  preprocessor lines) feeds a block matcher that pairs each declaration-`{`
  with its closing `}`.

This is a deliberately *simple* heuristic. It trades perfect precision for
small, readable code and good recall on ordinary function / method / class /
control-flow structure — exactly what an agent needs to orient itself in a
codebase.

## Tests

The suite in ``tests/`` exercises both the library helpers and the CLI using
real-world files from ``test-repos/`` (a cloned repo is skipped when absent):

```bash
uv run python -m unittest discover -s tests -t . -v
```
