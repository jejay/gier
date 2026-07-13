# gier — grep with code block hierarchy awareness

**gier is grep with code block hierarchy awareness.** `chier` is its small companion.

`gier` is a KISS command-line tool that tells you *which code block* a piece of
code lives in — the enclosing function, class, and control flow — instead of
just a bare line like plain `grep`. It is built agentic-first (for coding
agents and LLMs that need structural context), yet human-friendly enough to use
by hand. `chier` is the companion you reach for when you want the whole-file
hierarchy or a direct "what encloses line N?" query.

Both detect the language from the file extension and understand Python,
C, C++, Java, Kotlin, JavaScript, TypeScript, C#, Go, Rust, Swift, Scala,
Dart, PHP, and friends — with no real parser, just a deliberately simple,
tolerant block matcher.

## The block-path syntax

This is the little language both tools speak, so it is worth knowing by heart.
A block is written as:

```
<level>/<decl>{<start_line>,<start_col>~<end_line>,<end_col>}
```

* **`/`** divides the **level** from the **declaration**.
* **`<level>`** — 0-based nesting depth. `0` is the top level (outermost).
* **`<decl>`** — the declaration: the keyword, plus the name for
  `def`/`class`/function definitions, with parameters and their brackets
  stripped. Examples: `def abcd`, `class Foo`, `if`, `for`, `while`,
  `void foo`, `fn main`, `int main`, `(arrow)`, `object:Foo`, `const o=`.
* **`{` … `}`** wrap the coordinates.
* **`<start_line>,<start_col>`** — the first character of the declaration
  (1-based line and column).
* **`~`** separates start from end.
* **`<end_line>,<end_col>`** — the last character of the block's last line
  (for curly-brace languages, that is the closing `}`).

When several blocks are reported together, they are joined by a **relative
marker** that describes the relationship to the *previous* block:

| marker | meaning |
|--------|---------|
| `>`  | next block is a **child** (one level deeper) |
| `|`  | next block is a **sibling** (same level) |
| `<`  | next block is **higher**; the count of `<` is the number of levels ascended |

### Example (Python)

```
0/def abcd{21,1~61,20}>1/if{46,5~48,16}|1/for{52,5~59,18}<0/if{63,1~69,13}
```

Read left to right: top-level `def abcd` (line 21) has an `if` child (line 46)
and a sibling `for` (line 52); then we ascend back to the top level for another
`if` (line 63). The whole description is exactly one line — one tidy record per
file, or per match — which is what makes it easy for an agent to parse.

## gier — Grep code HIERarchy

```bash
uv run gier [-iHh] [-M N] [-N N] PATTERN FILE [.. [FILE]]
```

For each `FILE` (expanded with Python's `glob`, so `**/*.py` works) every line
matching the compiled `PATTERN` yields a finding:

* **inside a block** → the enclosing block's hierarchy plus its source, exactly
  like a `chier -c` query;
* **outside any block** (docstring, import, top-level statement) → a classic
  grep line `path:line:code`.

Options:

* `-i` / `--ignore-case` — case-insensitive (`re.IGNORECASE`; `re.MULTILINE` is
  always set).
* `-H` / `--with-filename` — always prefix `path:`.
* `-h` / `--no-filename` — never prefix (overrides `-H` and the auto rule).
* `-N N` / `--min-block-length N` (default `5`) and `-M N` /
  `--max-block-length N` (default `20`) — filter the code block; `-M` defaults
  to `20` so big blocks stay compact for agents.
* `--help` — show usage.

The file name is printed (as `path:`) when `-H` is given, or automatically when
the globs resolve to more than one file. Findings are separated by a `--` line
(only between findings, never after the last). Exit status: `0` match, `1` none,
`2` error.

## chier — Code HIERarchy

```bash
uv run chier PATH [PATH ...]
uv run chier (-p|-c) LINE PATH
```

* `-p LINE` / `--path-query LINE` — print the chain of nested blocks enclosing
  `LINE` (root first, `>`-separated).
* `-c LINE` / `--code-query LINE` — like `-p`, plus the block's source.
* `-N N` / `--min-block-length N` (default `5`) — blocks shorter than `N` lines
  merge into their parent, so you get the enclosing scope, not a one-liner.
* `-M N` / `--max-block-length N` (default `99999`) — blocks longer than `N`
  lines collapse to a single `LINE:CODE` line.
* `--exclude-fp-objects` — by default a `{` after `= : , [ return` is treated as
  a block (capturing closures that look like object literals); pass this to
  revert to the stricter heuristic.
* `--help` — show usage.

## Library use

```python
from gier import analyze

description = analyze(open("file.c").read(), path="file.c")
```

## How it works

* **Python** — the `ast` module turns each compound statement into a block;
  `else`/`finally` headers are recovered by scanning the source.
* **Curly-brace languages** — a tiny tokenizer (skipping strings, comments,
  preprocessor lines) feeds a block matcher that pairs each declaration-`{`
  with its closing `}`.

True to KISS, this is a deliberately *simple* heuristic: good recall on ordinary
function / method / class / control-flow hierarchy, small readable code, and no
pretense of being a full parser.

## Tests

The suite in ``tests/`` exercises both the library helpers and the CLI using
real-world files from ``test-repos/`` (a cloned repo is skipped when absent):

```bash
uv run python -m unittest discover -s tests -t . -v
```
