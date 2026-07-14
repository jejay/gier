# gier — grep with code block hierarchy awareness

**gier is grep with code block hierarchy awareness.** `chier` is its small companion.

`gier` is a KISS command-line tool that tells you *which code block* a piece of
code lives in — the enclosing function, class, and control flow — instead of
just a bare line like plain `grep`. It grew out of watching coding agents (and
people) poke around with `grep` and wish they could see the surrounding block
hierarchy at a glance; the hope is simply that your friendly coding agent finds
it useful. `chier` is the companion you reach for when you want the whole-file
hierarchy or a direct "what encloses line N?" query.

## Install

```
uv tool install gier
```

This installs both `gier` and `chier` onto your `uv` tool path, so you can run
them directly (no `uv run` needed):

```
gier "def " "src/**/*.py"
chier -c 47 file.py
```

If you prefer pip: `pip install gier`.

## The block-path syntax

This is the little language both tools speak, so it is worth knowing by heart.
A block is written as:

```
[<level>]<decl>{<start_line>,<start_col>~<end_line>,<end_col>}
```

* **`[<level>]`** — the 0-based nesting depth, wrapped in square brackets and
  followed directly by the declaration. `0` is the top level (outermost).
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
[0]def abcd{21,1~61,20}>[1]if{46,5~48,16}|[1]for{52,5~59,18}<[0]if{63,1~69,13}
```

Read left to right: top-level `def abcd` (line 21) has an `if` child (line 46)
and a sibling `for` (line 52); then we ascend back to the top level for another
`if` (line 63). The whole description is exactly one line — one tidy record per
file, or per match — which is what makes it easy for an agent to parse.

## gier — Grep code HIERarchy

```bash
gier [-iHh] [-M N] [-N N] PATTERN FILE [.. [FILE]]
```

For each `FILE` (expanded with Python's `glob`, so `**/*.py` works) every line
matching the compiled `PATTERN` yields a finding:

* **inside a block** → the enclosing block's hierarchy plus its source, exactly
  like a `chier -c` query;
* **outside any block** (docstring, import, top-level statement) → a classic
  grep line, but with the (empty) root block path written as `[]`, i.e.
  `[]:line:code` (or `path:[]:line:code` when the file name is shown).

Options:

* `-i` / `--ignore-case` — case-insensitive (`re.IGNORECASE`; `re.MULTILINE` is
  always set).
* `-H` / `--with-filename` — always prefix `path:`.
* `-h` / `--no-filename` — never prefix (overrides `-H` and the auto rule).
* `-N N` / `--min-block-length N` (default `5`) and `-M N` /
  `--max-block-length N` (default `20`) — filter the code block; `-M` defaults
  to `20` so big blocks stay compact for agents, collapsing long blocks to a
  single `blockpath:line:code` line.
* `--color[=WHEN]` (default `auto`) — highlight the matched text. `WHEN` is
  `auto` (color only when stdout is an interactive terminal), `always`, or
  `never`. Only the matched text is colored, never the filename, line number,
  or block-path metadata.
* `--format[=FMT]` (default `md`) — choose the output format. `md` wraps each
  block's source in a fenced code block and prints no separator between
  findings (the closing fence delimits them); `plain` restores the classic
  `--` separator between findings and prints source unfenced. In `md` mode,
  multi-line fenced blocks have their common leading indentation removed and
  the opening fence records how much — e.g. `` ```4 spaces unindented `` or
  `` ```1 tab unindented `` — so the shortened block still lines up with the
  real source for copy/search. Single-line blocks, and blocks with no common
  indent (or a mixed space/tab indent), are left verbatim.
* `--help` — show usage.

The file name is printed (as `path:`) when `-H` is given, or automatically when
the globs resolve to more than one file. In the default `md` format the block
path line is followed by a fenced code block containing the source, and
findings are not separated by any line; with `--format=plain` findings are
separated by a `--` line (only between findings, never after the last). Exit
status: `0` match, `1` none, `2` error.

## chier — Code HIERarchy

```bash
chier PATH [PATH ...]
chier (-p|-c) LINE PATH
```

* `-p LINE` / `--path-query LINE` — print the chain of nested blocks enclosing
  `LINE` (root first, `>`-separated).
* `-c LINE` / `--code-query LINE` — like `-p`, plus the block's source.
* `-N N` / `--min-block-length N` (default `5`) — blocks shorter than `N` lines
  merge into their parent, so you get the enclosing scope, not a one-liner.
* `-M N` / `--max-block-length N` (default `99999`) — blocks longer than `N`
  lines collapse to a single `blockpath:line:code` line.
* `--exclude-fp-objects` — by default a `{` after `= : , [ return` is treated as
  a block (capturing closures that look like object literals); pass this to
  revert to the stricter heuristic.
* `--help` — show usage.

## Worked example: Rust control flow

The repository ships two small, **deliberately non-compiling** Rust files under
`examples/` that exist purely to show off `gier`/`chier` on realistic-looking
control flow. They do **not** need to compile — they are dummies, and the tools
never parse them as a real compiler would (recall: the analyzer is a tiny
tokenizer, not a full Rust front-end).

* `examples/space_sim.rs` — the longer one: a `mod` containing structs, `impl`
  blocks, an `async fn`, a labeled `'sim:` loop, `match` arms with guards,
  `if let` / `while let`, a `loop`, and closure-style `=>` arms.
* `examples/state_machine.rs` — the shorter one: two `enum`s, an `impl` with a
  `match` (including a guard), a nested arm block, and `matches!`.

### Whole-file hierarchy with `chier`

Run `chier` on a file with no query to get the entire block tree on one line:

```bash
$ chier examples/space_sim.rs
[0]mod sim{5,1~82,1}>[1]struct Body{8,5~12,5}|[1]impl Body{14,5~24,5}>[2]fn step{15,9~18,9}|[2]fn kinetic->f64{20,9~23,9}<[1]struct World{26,5~28,5}|[1]impl World{30,5~68,5}>[2]fn new->Self{31,9~33,9}>[3]World{32,13~32,44}<[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13}>[4]if{42,17~62,17}>[5]match{44,21~61,21}>[6](arrow){45,25~52,25}>[7]while{49,29~51,29}<[6](arrow){53,25~59,25}>[7]if{55,29~57,29}<<<[4]else if{62,19~64,17}<<<[1]fn gravity->Result{70,5~72,5}|[1]fn integrate_star,SimError>{74,5~81,5}>[2]match{75,9~78,9}
```

(The real output is a single line with no wrapping; it is shown wrapped here
only for the docs.) Reading it with the marker table above:

* `[0]mod sim{5,1~82,1}` — top level; the module spans lines 5–82.
* `>[1]struct Body{8,5~12,5}` — `>` means "child": `struct Body` nests inside
  `mod sim`.
* `|[1]impl Body{14,5~24,5}` — `|` means "sibling": another level-1 block next
  to `struct Body`.
* `>[2]fn step{15,9~18,9}|[2]fn kinetic->f64{20,9~23,9}` — two `fn`s inside
  `impl Body`, siblings of each other.
* `<[1]struct World{26,5~28,5}` — `<` means "ascend"; one `<` = up one level
  back to level 1.
* `>[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13} … >[7]while{49,29~51,29}` —
  the deep `async fn tick` → `for` → `if` → `match` → `=>` arm → `while let`
  chain. The `fn tick` name comes out as `fn tick,SimError>` because the
  heuristic strips the *first* `(` to the *last* `)` of the header, so the
  `Result<(), SimError>` return type bleeds in; that is a known, documented
  limitation of a non-parser.
* `<<<[4]else if{62,19~64,17}` — three `<` means "climb three levels" from the
  nested `while`/`if` back up to the `else if`.

The short file reads just as neatly:

```bash
$ chier examples/state_machine.rs
[0]enum State{4,1~8,1}>[1]Idle,Running{5,5~6,26}<[0]enum Event{10,1~14,1}|[0]impl State{16,1~33,1}>[1]fn advance->State{17,5~28,5}>[2]match{18,9~27,9}>[3](arrow){19,14~19,70}|[3]State::Running{20,14~20,37}|[3]if{20,40~23,13}>[4]State::Running{22,17~22,46}<[3]State::Running{24,14~24,34}<<[1]fn is_active->bool{30,5~32,5}>[2]matches!(self,State::Running{31,9~31,44}
```

### `gier`: grep with the enclosing block

Every `gier` command below is run on `examples/space_sim.rs`.

**1. A plain search shows the enclosing block + its source.**

```bash
$ gier "while" examples/space_sim.rs
```
~~~
[]:3:// flow (match guards, if-let, while-let, labeled loops, closures, async fn).
[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13}>[4]if{42,17~62,17}>[5]match{44,21~61,21}>[6](arrow){45,25~52,25}
```
                        Kind::Star if b.mass > 1e3 => continue 'sim,
                        Kind::Star => integrate_star(b, dt)?,
                        Kind::Planet => {
                            let pull = gravity(b)?;
                            while let Some(force) = pull.next() {
                                apply(force, b);
                            }
                        }
```
~~~

Two findings; in the default `md` format the second finding's source is wrapped
in a fenced code block, and the leading comment (a plain grep line, outside any
block) is not fenced:
* **Line 3** is the file's leading comment — it lives *outside* any `{…}` block,
  so `gier` falls back to classic `[]:line:code` grep output
  (`[]:3:// flow (…)`). This is the "no block" branch.
* **Line 49** is the `while let` inside the `Kind::Planet` arm. Notice the path
  stops at `>[6](arrow)` and does **not** include a `>[7]while` even though line 49
  is literally a `while`. That is the **`-N`** filter (default `5`): blocks
  shorter than 5 lines are merged into their parent, so the 3-line `while`
  (49–51) is swallowed by its enclosing `=>` arm.

**2. Multiple hits, each its own fenced record.**

```bash
$ gier "match" examples/space_sim.rs
```
~~~
[]:3:// flow (match guards, if-let, while-let, labeled loops, closures, async fn).
[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13}>[4]if{42,17~62,17}>[5]match{44,21~61,21}
```20 spaces unindented
match body.classify() {
    Kind::Star if b.mass > 1e3 => continue 'sim,
    Kind::Star => integrate_star(b, dt)?,
    Kind::Planet => {
        let pull = gravity(b)?;
        while let Some(force) = pull.next() {
            apply(force, b);
        }
    }
    Kind::Comet => loop {
        let d = drift(b);
        if d < 1.0 {
            break 'sim;
        }
        b.step(dt * 0.5);
    },
    _ => (),
}
```
[0]mod sim{5,1~82,1}>[1]fn integrate_star,SimError>{74,5~81,5}
```4 spaces unindented
fn integrate_star(b: &mut Body, dt: f64) -> Result<(), SimError> {
    let factor = match b.vel {
        (0.0, 0.0) => 1.0,
        _ => 2.0,
    };
    b.step(dt * factor);
    Ok(())
}
```
~~~

Three matches (the comment plus two `match` lines). The first `match` is the
18-line block at line 44, printed in full; the second is the small
`fn integrate_star` block.

**3. The `-M` filter collapses long blocks to a single `blockpath:line:code` line.**

```bash
$ gier -M 10 "match" examples/space_sim.rs
```
~~~
[]:3:// flow (match guards, if-let, while-let, labeled loops, closures, async fn).
[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13}>[4]if{42,17~62,17}>[5]match{44,21~61,21}:44:                    match body.classify() {
[0]mod sim{5,1~82,1}>[1]fn integrate_star,SimError>{74,5~81,5}
```4 spaces unindented
fn integrate_star(b: &mut Body, dt: f64) -> Result<(), SimError> {
    let factor = match b.vel {
        (0.0, 0.0) => 1.0,
        _ => 2.0,
    };
    b.step(dt * factor);
    Ok(())
}
```
~~~

Same search, but with `-M 10` the 18-line `match` (longer than 10) is no longer
dumped verbatim — it collapses to a single `` `blockpath:line:code` `` line
`[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13}>[4]if{42,17~62,17}>[5]match{44,21~61,21}:44: match body.classify() {`. (`gier`'s default `-M` is `20`, so the 18-line
block is normally kept whole, as in example 2; here we lowered it to 10 to
force the collapse.)

**4. Case-insensitive search, with `-M` and `-N` both firing.**

```bash
$ gier -i "ok" examples/space_sim.rs
```
~~~
2:// it only exists to show off gier/chier on realistic-looking Rust control
[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick,SimError>{35,9~67,9}:66:            Ok(())
[0]mod sim{5,1~82,1}:71:        Ok((0..3).map(move |i| b.pos.0 / (i as f64 + 1.0)))
[0]mod sim{5,1~82,1}>[1]fn integrate_star,SimError>{74,5~81,5}
```4 spaces unindented
fn integrate_star(b: &mut Body, dt: f64) -> Result<(), SimError> {
    let factor = match b.vel {
        (0.0, 0.0) => 1.0,
        _ => 2.0,
        };
        b.step(dt * factor);
        Ok(())
    }
```
~~~

Three `Ok(..)` hits, each demonstrating a different path through the filters:

* **Line 66** lives in `fn tick` (33 lines). That is longer than `-M 20` (the
  `gier` default), so the block collapses to a single `blockpath:line:code` line
  `[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick,SimError>{35,9~67,9}:66: Ok(())`.
* **Line 71** is inside the 3-line `fn gravity`; `-N 5` merges that short `fn`
  into its parent `mod sim`, and `mod sim` (78 lines) is then itself collapsed
  by `-M 20` → `[0]mod sim{5,1~82,1}:71: Ok(..)`.
* **Line 78** is in `fn integrate_star` (8 lines); shorter than `-M 20` and not
  a short child, so its source is printed in full.

**5. A match with no enclosing block is plain grep.**

```bash
$ gier "toy" examples/space_sim.rs
[]:1:// A toy space simulation. It is intentionally *not* a compiling program --
```

Line 1 is a top-level comment, outside any block — pure `[]:line:code`
output, no hierarchy.

### `chier`: direct hierarchy queries

Fewer flags, same block language — mostly "what encloses line N?".

**1. Path only: `-p` prints the enclosing chain (root first).**

```bash
$ chier -p 49 examples/space_sim.rs
[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13}>[4]if{42,17~62,17}>[5]match{44,21~61,21}>[6](arrow){45,25~52,25}>[7]while{49,29~51,29}
```

That is the full ancestry of line 49 (the `while let`): `mod sim → impl World →
fn tick → for → if → match → => arm → while`.

**2. Path + source: `-c` adds the block's source.**

```bash
$ chier -c 49 examples/space_sim.rs
[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13}>[4]if{42,17~62,17}>[5]match{44,21~61,21}>[6](arrow){45,25~52,25}
                        Kind::Star if b.mass > 1e3 => continue 'sim,
                        Kind::Star => integrate_star(b, dt)?,
                        Kind::Planet => {
                            let pull = gravity(b)?;
                            while let Some(force) = pull.next() {
                                apply(force, b);
                            }
                        }
```

Same query, and again the 3-line `while` is merged into its `=>` arm by the
default `-N 5`, so the printed source is the whole `Kind::Planet` arm.

**3. `-M` collapses long source to a single `blockpath:line:code` line.**

```bash
$ chier -c 55 -M 5 examples/space_sim.rs
[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13}>[4]if{42,17~62,17}>[5]match{44,21~61,21}>[6](arrow){53,25~59,25}:55:                            if d < 1.0 {
```

Line 55 is inside the `Kind::Comet` `=>` arm (the `(arrow)` at level 6, 7
lines). With `-M 5` that 7-line block is longer than 5, so it collapses to a
single `blockpath:line:code` line: `[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13}>[4]if{42,17~62,17}>[5]match{44,21~61,21}>[6](arrow){53,25~59,25}:55: if d < 1.0 {`.

**4. `-N` changes how small blocks are reported (the guard example).**

```bash
$ chier -c 20 examples/state_machine.rs        # -N defaults to 5
[0]impl State{16,1~33,1}>[1]fn advance->State{17,5~28,5}>[2]match{18,9~27,9}
        match (self, input) {
            (State::Idle, Event::Start) => State::Running { count: 0 },
            (State::Running { count }, Event::Tick) if count < 10 => {
                let next = count + 1;
                State::Running { count: next }
            }
            (State::Running { .. }, Event::Tick) => State::Done,
            (State::Done, Event::Reset) => State::Idle,
            _ => self,
        }
```

```bash
$ chier -c 20 -N 1 examples/state_machine.rs   # nothing is merged
[0]impl State{16,1~33,1}>[1]fn advance->State{17,5~28,5}>[2]match{18,9~27,9}>[3]State::Running{20,14~20,37}
            (State::Running { count }, Event::Tick) if count < 10 => {
```

Both query line 20 (the `if count < 10` guard inside the `match`). With the
default `-N 5` the small guard block merges into the `match`, so you see the
whole `match`; with `-N 1` nothing merges, so the reported block is the tiny
`State::Running { … }` arm header itself.

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

## Snapshot tests & browser

``tests/examples/`` holds *golden* specs -- one ``.txt`` per example that
records the exact ``uv run gier …`` command and its full expected output (see
``tests/examples/README.md``). Those same files double as browsable pages:

```bash
python tools/snapshot_server.py --port 8080
# from this machine:  http://127.0.0.1:8080/
# from your laptop:    http://<this-machine-ip>:8080/
```

By default it binds to ``0.0.0.0`` (all interfaces), so it is reachable from
another machine on the same network. Pass ``--host 127.0.0.1`` to restrict it
to the local machine only.

The server renders each snapshot and, by parsing the spec, links straight to
the source on GitHub at the pinned commit: the file (from the command's
``test-repos/…`` argument) and every matched line / block header (parsed out of
the gier output) deep-links to ``#L<line>`` on the blob. It is pure stdlib
(``http.server``), so it needs no extra dependencies.
