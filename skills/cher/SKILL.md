---
name: chier
description: >-
  Use chier ("code-hierarchy") to print a file's entire block tree on one line,
  or to answer "what function/method/class encloses line N?" via -p/-c line
  queries. Use it for usage introspection of the ENCLOSING scope of an observed
  behavior — a stack frame, a log line, a breakpoint — and to read whole-file
  structure at a glance. Companion to gier; chier takes a file + line, gier
  takes a regex + files.
---

# chier — Code HIERarchy

`chier` is the companion to `gier`. Where `gier` greps, `chier` answers
questions about *structure*:

* **No query** → print a file's whole block tree as a single line.
* **`-p LINE`** → print the chain of blocks that *enclose* `LINE` (root first).
* **`-c LINE`** → like `-p`, plus the source of that enclosing block.

Its superpower for **usage introspection** is the line query: given a line number
you observed somewhere (a stack trace, a log statement, a breakpoint), `chier`
tells you *which function / method / class that line lives in* — i.e. the scope
of the behavior you are investigating. This skill climbs from easy to hard using
**source files that ship in this repo** (`examples/` and `test-repos/...`).

## The one-minute mental model

```
chier PATH [PATH ...]
chier (-p|-c) LINE PATH
```

* Language is detected from the file extension (unknown → Python).
* A block is `[<level>]<decl>{<start>,<start_col>~<end>,<end_col>}`, joined by
  `>` (child) / `|` (sibling) / `<` (ascend) markers — same syntax as `gier`.
* Two filters apply to `-c` (and to `gier`'s blocks):
  * `-N N` (default `5`): blocks shorter than `N` lines merge into their parent.
  * `-M N` (default `99999`): blocks longer than `N` lines collapse to one
    `blockpath:line:code` line.
* `--exclude-fp-objects`: treat `{` after `= : , [ return` as an object/collection
  literal (not a block) — useful when closures look like object literals.

---

## Level 1 — Whole-file hierarchy at a glance

No query: `chier` prints the entire block tree on one line.

```text
$ chier examples/toy.py
[0]class BankAccount{1,1~30,31}>[1]def __init__{2,5~5,25}|[1]def deposit{7,5~12,19}>[2]if{8,9~9,24}<[1]def withdraw{14,5~19,19}>[2]if{15,9~16,24}<[1]def statement{21,5~30,31}>[2]for{24,9~28,44}>[3]if{25,13~26,44}|[3]else{27,13~28,44}
```

Read left to right: `[0]class BankAccount` is the root; each `>[1]…` is a method
inside it (siblings joined by `|`); the `>[2]if` / `>[2]for` are the control-flow
blocks inside each method.

A deeper, real-world file shows the same markers at greater nesting:

```text
$ chier examples/space_sim.rs
[0]mod sim{5,1~82,1}>[1]struct Body{8,5~12,5}|[1]impl Body{14,5~24,5}>[2]fn step{15,9~18,9}|[2]fn kinetic->f64{20,9~23,9}<[1]struct World{26,5~28,5}|[1]impl World{30,5~68,5}>[2]fn new->Self{31,9~33,9}>[3]World{32,13~32,44}<[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13}>[4]if{42,17~62,17}>[5]match{44,21~61,21}>[6](arrow){45,25~52,25}>[7]while{49,29~51,29}<[6](arrow){53,25~59,25}>[7]if{55,29~57,29}<<<[4]else if{62,19~64,17}<<<[1]fn gravity->Result{70,5~72,5}|[1]fn integrate_star,SimError>{74,5~81,5}>[2]match{75,9~78,9}
```

`mod sim → impl World → fn tick → for → if → match → (arrow) → while` — the full
ancestry of the deepest line, read straight off one line.

---

## Level 2 — "What encloses this line?" (path query, `-p`)

You have a line number (say, `49` — the `while let` in `space_sim.rs`) and want
its ancestry without the source:

```text
$ chier -p 49 examples/space_sim.rs
[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13}>[4]if{42,17~62,17}>[5]match{44,21~61,21}>[6](arrow){45,25~52,25}>[7]while{49,29~51,29}
```

That is the full chain: `mod sim → impl World → fn tick → for → if → match → => arm → while`.
This is the fastest possible "what function am I in?" answer — pure usage
introspection of the *enclosing scope*.

---

## Level 3 — Path + source (`-c`)

Add the block's source so you can read the enclosing function/method itself:

```text
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

The 3-line `while` was merged into its `=> arm` by the default `-N 5`, so the
printed source is the whole `Kind::Planet` arm — exactly the context you need
to understand the line.

Another real repo, real line — Bitcoin's `ConnectTip` body around line 3057:

```text
$ chier -c 3057 test-repos/C++/bitcoin/src/validation.cpp
[0]bool Chainstate::ConnectTip{3025,1~3128,1}
bool Chainstate::ConnectTip(
    BlockValidationState& state,
    CBlockIndex* pindexNew,
    std::shared_ptr<const CBlock> block_to_connect,
    std::vector<ConnectedBlock>& connected_blocks,
    DisconnectedBlockTransactions& disconnectpool)
{
    AssertLockHeld(cs_main);
    ...
```

Given a line inside the 1000-line `validation.cpp`, `chier` immediately tells you
it is inside `Chainstate::ConnectTip` — no scrolling required.

---

## Level 4 — `-N` and `-M`: tune what "the enclosing block" means

These two flags are what turn `chier` from "show me the line's block" into "show
me the scope I actually care about."

### 4a. `-N` merges tiny control-flow into the function

By default `-N 5` merges a short `if`/`for` into its parent. With `-N 1`,
*nothing* merges, so you see the most specific block — here the tiny guard arm:

```text
$ chier -c 20 examples/state_machine.rs        # default -N 5
[0]impl State{16,1~33,1}>[1]fn advance->State{17,5~28,5}>[2]match{18,9~27,9}
        match (self, input) {
            (State::Idle, Event::Start) => State::Running { count: 0 },
            (State::Running { count }, Event::Tick) if count < 10 => {
                let next = count + 1;
                State::Running { count: next }
            }
            ...
        }

$ chier -c 20 -N 1 examples/state_machine.rs   # nothing merged
[0]impl State{16,1~33,1}>[1]fn advance->State{17,5~28,5}>[2]match{18,9~27,9}>[3]State::Running{20,14~20,37}
            (State::Running { count }, Event::Tick) if count < 10 => {
```

Same query line (20, the `if count < 10` guard): with the default you get the
whole `match`; with `-N 1` you get the exact arm header. **Use `-N` to choose
between "the function" and "the branch."**

### 4b. `-M` collapses a long block to one line

The `Kind::Comet` arm in `space_sim.rs` is 7 lines. With `-M 5` it collapses to a
single `blockpath:line:code` line, which is handy when the enclosing block is
huge and you only want the path:

```text
$ chier -c 55 -M 5 examples/space_sim.rs
[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13}>[4]if{42,17~62,17}>[5]match{44,21~61,21}>[6](arrow){53,25~59,25}:55:                            if d < 1.0 {
```

---

## Level 5 — Real-world usage introspection & edge cases

### 5a. From a stack frame to the enclosing function

You get `validation.cpp:3057` in a crash. Don't open the file — ask `chier`:

```text
$ chier -c 3057 test-repos/C++/bitcoin/src/validation.cpp
[0]bool Chainstate::ConnectTip{3025,1~3128,1}
bool Chainstate::ConnectTip( ... ) { ... }
```

Now you know the failure is inside `Chainstate::ConnectTip`, and you can jump
straight to the relevant block. This is the canonical `chier` workflow: **line
number in, enclosing scope out.**

### 5b. Multiple files

`chier` accepts several paths and prints one tree (or one query result) per file:

```text
$ chier examples/toy.py examples/space_sim.rs
[0]class BankAccount{1,1~30,31}>...
[0]mod sim{5,1~82,1}>...
```

### 5c. Closures that look like object literals (`--exclude-fp-objects`)

In some languages a `{` after `=`, `:`, `,`, `[` or `return` is an object/collection
literal, not a block — but by default `chier` treats it as a block to catch
inline closures. If that over-reports, pass `--exclude-fp-objects` to revert to
the stricter heuristic. (Rarely needed; the default is what makes `chier`
useful for agentic code reading.)

---

## Cheat-sheet

| Goal | Command |
|------|---------|
| Whole-file tree on one line | `chier FILE` |
| Ancestry of a line (path only) | `chier -p LINE FILE` |
| Ancestry + enclosing source | `chier -c LINE FILE` |
| See the function, not a tiny branch | `chier -c LINE FILE` (default `-N 5`) |
| See the exact tiny branch | `chier -c LINE FILE -N 1` |
| Collapse a huge block to one line | `chier -c LINE FILE -M 5` |
| Trees for several files | `chier FILE1 FILE2 …` |
| Stricter block heuristic | `chier -c LINE FILE --exclude-fp-objects` |

Exit status is non-zero if a file cannot be read (or, for Python, fails to parse).
