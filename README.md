# codehierarchy

A small tool that recognizes the **code-block structure** of a source file and
prints it as a single line.

For every compound statement it reports:

* the **declaration** (the keyword — plus the name for ``def``/``class``/function
  definitions — with parameters/arguments and their brackets stripped),
* the 1-based ``(line, column)`` of the **first** character of the declaration
  keyword,
* the 1-based ``(line, column)`` of the **last** character of the last line of
  code contained in that block (the closing ``}`` for curly-brace languages).

## Design principles

**Simplicity is the core design principle.** The tool should be easy to *use*
and easy to *understand by reading its code*. It is intentionally a small,
heuristic block matcher — not a real language parser.

From that follows:

* Minor quirks with unusual syntax or coding styles are **acceptable**. The
tool is tuned for typical function / method / class / control-flow structure,
not for every legal program.
* A **small, well-localized, easy-to-understand change** that targets a
particular language or syntax style and makes a *large* difference in output
quality **is warranted** — even if it is language-specific. Such fixes should
read clearly (a short comment explaining the *why* is enough).
* Conversely, broad machinery added to chase every edge case is **not** — it
works against the principle. Prefer a clear heuristic over a clever one.

## Output format

```
<level>/<decl>{<start_line>,<start_col>~<end_line>,<end_col>}
```

Blocks are emitted in source order and separated by a relative indentation
marker:

| marker | meaning                                                        |
|--------|----------------------------------------------------------------|
| `>`    | next block is a **child** of the previous one (one level deeper) |
| `|`    | next block is a **sibling** of the previous one (same level)      |
| `<`    | next block is at a **higher** level; the number of `<` is the number of hierarchy levels ascended |

The whole output is exactly one line terminated by a single Unix newline.

### Example (Python)

Given a file whose `def abcd` starts at line 21, an `if` (child) at line 46,
a `for` (sibling) at line 52, and another top-level `if` at line 63:

```
0/def abcd{21,1~61,20}>1/if{46,5~48,16}|1/for{52,5~59,18}<0/if{63,1~69,13}
```

See `sample.py` for a file that reproduces exactly this output.

### Example (C)

```c
int main() {
    if (x > 0) {
        for (int i = 0; i < 10; i++) {
            printf("%d\n", i);
        }
    }
}
```

```
0/int main{1,1~5,1}>1/if{2,5~4,3}>2/for{3,9~4,3}
```

## Supported languages

The language is detected from the file extension:

* **Python** (`.py`/`.pyw`/`.pyi`) — parsed with the `ast` module.
* **Curly-brace languages** — a tokenizer + simple block matcher pairs every
  block-introducing `{` with its closing `}`: C, C++, Objective-C, Java,
  Kotlin, JavaScript, TypeScript, C#, Go, Rust, Swift, Scala, Dart, PHP, and
  friends.

Block types captured for curly languages include functions/methods
(`void foo`, `fn main`, `func bar`, `fun baz`, `def qux` …),
classes/structs/interfaces/enums/namespaces (`class Foo`, `struct Bar` …), and
control flow (`if`/`elif`/`else`/`for`/`while`/`switch`/`try`/`catch`/
`finally`/`match`/`when` …). Arrow-function blocks are labeled `(arrow)`.

## Usage

```bash
# analyze a file (one line printed per file); language from extension
uv run codehierarchy file.py
uv run codehierarchy file.c

# multiple files
uv run codehierarchy a.py b.c c.java

# path query: chain of enclosing blocks ('>' only) to a line
uv run codehierarchy -p 47 file.py

# code query: path plus the enclosing block's source
uv run codehierarchy -c 47 file.py

# code query, ignoring blocks shorter than 10 lines (merge into parent)
uv run codehierarchy -c 47 -N 10 file.py

# code query, collapsing blocks longer than 3 lines to 'line:code'
uv run codehierarchy -c 47 -M 3 file.py
```

Exit status is non-zero if a file cannot be read or (for Python) contains a
syntax error.

## Query options

``-p LINE`` / ``--path-query LINE`` and ``-c LINE`` / ``--code-query LINE`` take
a 1-based ``LINE`` number and print the chain of nested blocks (root first,
separated only by ``>``) that enclose that line -- i.e. the block path to the
deepest block containing it, with no siblings or ascents. ``-c`` additionally
prints the source of the innermost enclosing block on the following lines.

Two length filters refine ``-c``:

* ``-N`` / ``--min-block-length`` (default ``5``) -- a block shorter than
  ``N`` lines is not reported on its own; it is merged into its parent, so the
  parent's path and source (which include the small block) are shown instead.
* ``-M`` / ``--max-block-length`` (default ``99999``) -- a block longer than
  ``M`` lines is not printed verbatim; as a fallback only the queried line is
  printed, as ``[line-number]:[code line]`` (a single line indicating the
  block source overflows the threshold).

## Tests

The suite in ``tests/`` exercises both the library helpers and the CLI using
real-world files from ``test-repos/`` (a cloned repo is skipped when absent):

```bash
uv run python -m unittest discover -s tests -t . -v
```

## Library use

```python
from codehierarchy import analyze

description = analyze(open("file.c").read(), path="file.c")
```

## How it works

* **Python** — parsed with the standard-library `ast` module; every compound
  statement contributes a block. `else`/`finally` clauses (which have no
  dedicated AST node for their header) are located by scanning the source. A
  block's end uses its own body so sibling clauses (`elif`/`else`/`except`/
  `finally`/loop-`else`) get distinct, physically-consistent extents, while
  nested child blocks remain within their parent's extent.
* **Curly-brace languages** — a small tokenizer (skipping strings, comments
  and preprocessor lines) feeds a block matcher. Each `{` whose header looks
  like a declaration (control-flow keyword, class/struct/enum/namespace, or a
  `type name(...)` definition) opens a block; the matching `}` closes it. The
  block's last character is, by definition, that `}`. Indentation level is the
  brace-nesting depth.

This is a deliberately *simple* heuristic and will have false
positives/negatives on unusual constructs (e.g. it may treat a C++
`new Foo() { ... }` object initializer as a block, and skips bare/label
blocks). It is tuned for typical function/method/class/control-flow structure.
