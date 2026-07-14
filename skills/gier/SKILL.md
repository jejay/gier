---
name: gier
description: >-
  Use gier ("grep with code-block hierarchy awareness") to find where a function
  or variable is USED — its call sites, read/write points, and the enclosing
  control flow — across a single file or a recursive glob. Prefer it over plain
  grep whenever you need the enclosing function/class/method and its surrounding
  context, not just a bare line number. Best for usage introspection: "who calls
  X?", "where is variable Y read/written?", "under what condition is this branch
  taken?" — not just "where is X declared?".
---

# gier — Grep code HIERarchy

`gier` is `grep` that, for every match, also reports **the code block the match
lives in** (the enclosing function, method, class, and control flow) plus that
block's source. That single fact is what separates it from grep: instead of a
line number, you get *where the code lives and what surrounds it*.

This skill is a learning curve from easy to hard. Every example uses a **source
file that actually ships in this repo** (`examples/` for the small teaching
files, `test-repos/<lang>/...` for real-world code), and every example is
oriented at **usage introspection** — what calls something, where a variable is
touched, *why/when* a branch runs — rather than merely locating a declaration
and dumping its body.

## The one-minute mental model

```
gier [-iHh] [-M N] [-N N] PATTERN FILE [.. [FILE]]
```

* For each file (expanded with Python `glob`, so `**/*.py` works), every line
  matching the regex `PATTERN` becomes a *finding*.
* A finding is either:
  * **inside a block** → the enclosing block's hierarchy path + its source, or
  * **outside any block** (a docstring, import, top-level comment) → classic
    `[]:line:code` grep output.
* Two length filters shape the block:
  * `-N N` (default `5`): blocks *shorter* than `N` lines merge into their
    parent. So a 2-line `if` is swallowed by the function — you see the
    function, not a one-liner.
  * `-M N` (default `20`): blocks *longer* than `N` lines collapse to a single
    `blockpath:line:code` line, so huge functions stay compact.

### Block-path syntax (you must be able to read this)

A block is written `[<level>]<decl>{<start_line>,<start_col>~<end_line>,<end_col>}`.
Blocks are joined by a relative marker showing the relationship to the previous
block:

| marker | meaning |
|--------|---------|
| `>`  | next block is a **child** (one level deeper) |
| `|`  | next block is a **sibling** (same level) |
| `<`  | next block is **higher**; `<` count = levels ascended |

Example: `[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick{35,9~67,9}` reads
"module `sim` ⊃ `impl World` ⊃ `fn tick`".

---

## Level 1 — The basics: find a symbol, see its home

You know a method name and want to know *where it lives*. Plain grep gives you a
line; `gier` gives you the enclosing class **and** the method body.

```text
$ gier "def withdraw" examples/toy.py
[0]class BankAccount{1,1~30,31}>[1]def withdraw{14,5~19,19}
```4 spaces unindented
def withdraw(self, amount):
    if amount <= 0 or amount > self.balance:
        return False
    self.balance -= amount
    self.history.append(("withdraw", amount))
    return True
```
```

Read it: the match is inside `[0]class BankAccount` → `[1]def withdraw`. The
`toy.py` file has no other `withdraw`, so there is exactly one finding. Note
the `if` (2 lines) was merged into `def withdraw` by the default `-N 5` — that
is the length filter doing its job: you get the *method*, not a lone `if`.

> This level is the entry point, but it is also the "half-useful" case: the
> pattern is the declaration itself, and the output is its body. The interesting
> introspection starts at Level 2.

---

## Level 2 — Usage introspection: search for a CALL or a VARIABLE

This is the point of the tool. Instead of grepping for a *definition*, grep for
a *use* of something, and let `gier` show you **which function each use lives
in** and **the surrounding context**.

### 2a. "Who calls this private function?" (the call-funnel)

`git_remote_create_with_opts()` is the private core of libgit2's remote-creation
API. Search for its *call* (not its name as a definition) and `gier` prints every
public wrapper that bottoms out in it — so you learn the shape of the whole API
in one shot:

```text
$ gier "git_remote_create_with_opts\(" test-repos/C/libgit2/src/libgit2/remote.c
[0]int git_remote_create_with_opts{208,1~320,1}:208:int git_remote_create_with_opts(git_remote **out, const char *url, const git_remote_create_options *opts)
[0]int git_remote_create{322,1~345,1}:340:	error = git_remote_create_with_opts(out, url, &opts);
[0]int git_remote_create_with_fetchspec{347,1~361,1}
```
int git_remote_create_with_fetchspec(git_remote **out, git_repository *repo, const char *name, const char *url, const char *fetch)
{
	int error;
	git_remote_create_options opts = GIT_REMOTE_CREATE_OPTIONS_INIT;
	...
	return git_remote_create_with_opts(out, url, &opts);
}
```
[0]int git_remote_create_anonymous{363,1~370,1}
```
int git_remote_create_anonymous(git_remote **out, git_repository *repo, const char *url)
{
	git_remote_create_options opts = GIT_REMOTE_CREATE_OPTIONS_INIT;
	opts.repository = repo;
	return git_remote_create_with_opts(out, url, &opts);
}
```
[0]int git_remote_create_detached{372,1~375,1}
```
int git_remote_create_detached(git_remote **out, const char *url)
{
	return git_remote_create_with_opts(out, url, NULL);
}
```
```

The private core (113 lines) collapses to one `blockpath:line:code` line, but
**each public caller is printed whole**. You can now answer: *"Every
`git_remote_create_*` variant is a thin wrapper that builds options and delegates
to `git_remote_create_with_opts`."* That is usage introspection grep cannot give
you.

### 2b. "Where is this variable read/written?" (the variable trace)

`state->again` is zlib's non-blocking "try again" flag. Trace it and `gier` shows
every set/test site *with the enclosing function*, so the state machine is
legible:

```text
$ gier -N 5 -M 80 "state->again" test-repos/C/zlib/gzread.c
[]:15:   no data has been read. Either way, state->again is set true to indicate a
[0]local int gz_load{18,1~47,1}
```
local int gz_load(gz_statep state, unsigned char *buf, unsigned len, unsigned *have) {
    ...
    state->again = 0;
    ...
    if (ret < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            state->again = 1;
            if (*have != 0)
                return 0;
        }
        ...
    }
    ...
}
```
[0]int ZEXPORT gzread{396,1~436,1}>[1]if{422,5~432,5}>[2]if{425,9~431,9}
```8 spaces unindented
if (state->again) {
    /* non-blocking input stalled after some input was read, but no
       uncompressed bytes were produced -- let the application know
       this isn't EOF */
    gz_error(state, Z_ERRNO, zstrerror());
    return -1;
}
```
```

Note the two distinct stories: `gz_load` **sets** `again` (0 on entry, 1 on a
non-blocking stall), while `gzread` **tests** it to decide whether a short read
is EOF or a retry. Following the variable across functions *is* the
introspection.

### 2c. "Where is this helper actually fired?" (helper + its lone call site)

Home Assistant builds a teardown signal in one tiny helper and fires it from
exactly one place. Search for the *call* and `gier` shows both the helper and
the loop that invokes it:

```text
$ gier "signal_discovered_config_entry_removed\(" test-repos/Python/core/homeassistant/config_entries.py
[0]def signal_discovered_config_entry_removed{211,1~215,76}
```
def signal_discovered_config_entry_removed(
    discovery_domain: str,
) -> SignalType[ConfigEntry]:
    """Format signal."""
    return SignalType(f"{discovery_domain}_discovered_config_entry_removed")
```
[0]class ConfigEntries{2121,1~2980,76}>[1]async def async_remove{2240,5~2252,54}>[2]for{2245,9~2250,13}
```8 spaces unindented
for discovery_domain in entry.discovery_keys:
    async_dispatcher_send_internal(
        self.hass,
        signal_discovered_config_entry_removed(discovery_domain),
        entry,
    )
```
```

---

## Level 3 — Rare searches: crank `-N`/`-M` for full context

When you deliberately search for something you *expect* to appear only a few
times (2–3 hits), you usually want to see the **whole enclosing function**, not a
collapsed `blockpath:line:code` line. Raise both `-N` and `-M` so `gier` prints
every enclosing block in full.

### 3a. "When is a block marked invalid?" (3 hits, full callers)

```text
$ gier -N 200 -M 200 "InvalidBlockFound\(" test-repos/C++/bitcoin/src/validation.cpp
[0]void Chainstate::InvalidBlockFound{2000,1~2009,1}
```
void Chainstate::InvalidBlockFound(CBlockIndex* pindex, const BlockValidationState& state)
{
    AssertLockHeld(cs_main);
    if (state.GetResult() != BlockValidationResult::BLOCK_MUTATED) {
        pindex->nStatus |= BLOCK_FAILED_VALID;
        m_blockman.m_dirty_blockindex.insert(pindex);
        setBlockIndexCandidates.erase(pindex);
        InvalidChainFound(pindex);
    }
}
```
[0]bool Chainstate::ConnectTip{3025,1~3128,1}
```
bool Chainstate::ConnectTip(...) {
    ...
    bool rv = ConnectBlock(*block_to_connect, state, pindexNew, view);
    ...
    if (!rv) {
        if (state.IsInvalid())
            InvalidBlockFound(pindexNew, state);   // <-- caller 1
        ...
    }
    ...
}
```
[0]bool ChainstateManager::AcceptBlock{4314,1~4419,1}
```
bool ChainstateManager::AcceptBlock(...) {
    ...
    if (!CheckBlock(block, state, params.GetConsensus()) || ...) {
        if (Assume(state.IsInvalid())) {
            ActiveChainstate().InvalidBlockFound(pindex, state);   // <-- caller 2
        }
        ...
    }
    ...
}
```
```

(Output above is trimmed; with `-N 200 -M 200` the two callers `ConnectTip` and
`AcceptBlock` are printed **whole**, not collapsed.) You now have both call
sites in front of you, each in the exact context that decides *when* a block is
flagged invalid.

### 3b. "What does connect() actually delegate to?" (2–3 hits, everything whole)

```text
$ gier -N 500 -M 500 "git_remote_connect_ext\(" test-repos/C/libgit2/src/libgit2/remote.c
[0]int git_remote_connect_ext{932,1~985,1}
```
int git_remote_connect_ext(...) { /* the real transport-setup work */ }
```
[0]int git_remote_connect{987,1~1006,1}
```
int git_remote_connect(...)
{
    ...
    return git_remote_connect_ext(remote, direction, &opts);   // delegate
}
```
[0]static int connect_or_reset_options{1251,1~1261,1}
```
static int connect_or_reset_options(...)
{
    if (!git_remote_connected(remote))
        return git_remote_connect_ext(remote, direction, opts);  // delegate
    ...
}
```
```

Because the matches are rare, `-N 500 -M 500` guarantees you see the full body of
every enclosing function — the connect path is now completely legible.

**Rule of thumb:** *expect 2–3 hits → set `-N` and `-M` comfortably above the
size of the enclosing function* (e.g. `-N 200 -M 200` or higher) so nothing
collapses.

---

## Level 4 — Cross-cutting questions: multiple files & recursive globs

`gier` expands each file argument with `glob.glob(..., recursive=True)`. When
more than one file matches, the file name is auto-prefixed (`path:`), and you can
force it with `-H`.

### 4a. Two explicit files (`-H` forces the prefix)

```text
$ gier -H "MarkIniSettingsDirty\(" test-repos/C++/imgui/imgui.cpp test-repos/C++/imgui/imgui_widgets.cpp
test-repos/C++/imgui/imgui.cpp:[0]static int ImGui::UpdateWindowManualResize{7000,1~7204,1}:7197:        MarkIniSettingsDirty(window);
test-repos/C++/imgui/imgui.cpp:[0]bool ImGui::Begin{7504,1~8308,1}>[1]if{7673,5~8222,5}>[2]if{7768,9~7786,9}>[3]if{7779,13~7785,13}
```12 spaces unindented
if (window->WantCollapseToggle)
{
    window->Collapsed = !window->Collapsed;
    if (!window->Collapsed)
        use_current_size_for_scrollbar_y = true;
    MarkIniSettingsDirty(window);
}
```
```

(The second file, `imgui_widgets.cpp`, simply contributes no matches — `gier`
only prints findings.)

### 4b. Recursive glob across a whole package

"Find every caller of `compileModule` anywhere in the Svelte compiler":

```text
$ gier "compileModule\(" "test-repos/JavaScript/svelte/packages/svelte/src/**/*.js"
test-repos/JavaScript/svelte/packages/svelte/src/compiler/index.js:[0]function compileModule{69,1~76,1}
```
export function compileModule(source, options) {
	source = remove_bom(source);
	...
	return transform_module(analysis, source, validated);
}
```
```

The `**/*.js` glob sweeps the whole `src/` tree; each finding is prefixed with
its file. This is how you answer "where is this used across the codebase?" in one
command.

### 4c. Case-insensitive, recursive

```text
$ gier -i "todo" "test-repos/Python/yt-dlp/yt_dlp/extractor/**/*.py"
```

`-i` turns on `re.IGNORECASE` (and `re.MULTILINE` is always on, so `^`/`$` anchor
to lines).

---

## Level 5 — Reading the hierarchy & advanced knobs

### 5a. Multiple matches, nested paths

Searching `match` in the Rust teaching file yields several findings at different
depths; the block path tells you *exactly how deep* each one is:

```text
$ gier "match" examples/space_sim.rs
[0]mod sim{5,1~82,1}>[1]impl World{30,5~68,5}>[2]fn tick,SimError>{35,9~67,9}>[3]for{41,14~65,13}>[4]if{42,17~62,17}>[5]match{44,21~61,21}
```20 spaces unindented
match body.classify() {
    ...
}
```
[0]mod sim{5,1~82,1}>[1]fn integrate_star,SimError>{74,5~81,5}
```4 spaces unindented
fn integrate_star(b: &mut Body, dt: f64) -> Result<(), SimError> {
    let factor = match b.vel { ... };
    ...
}
```
```

The first `match` sits 5 levels deep (`mod → impl → fn → for → if → match`);
the second is directly in `fn integrate_star`. That depth *is* the answer to
"what is this match nested inside?"

### 5b. `-M` collapses long blocks; `-N` merges short ones

* `-M N`: any block longer than `N` lines collapses to `blockpath:line:code`.
  Useful to keep a 4000-line class from flooding the screen.
* `-N N`: any block shorter than `N` lines merges into its parent. **This is the
  key introspection knob**: with the default `-N 5` a one-line `if` is absorbed
  into the function, so you see *the function a line belongs to* rather than the
  tiny branch.

### 5c. Output formats & color

* `--format=md` (default): each block's source in a fenced code block, no
  separator between findings. Multi-line blocks have their common indentation
  stripped and reported in the fence (e.g. ```` ```4 spaces unindented ````).
* `--format=plain`: classic `--` separator between findings, source unfenced.
* `--color=auto|always|never`: highlight only the matched text.

### 5d. "Which function is this line in?" (path-only usage introspection)

If you only need the enclosing chain (no source), `gier` is overkill — but the
block path it prints *is* that answer. For a direct "what encloses line N?"
query, see the companion **chier** skill (`chier -p N FILE`).

---

## Cheat-sheet

| Goal | Command |
|------|---------|
| Find a symbol + its enclosing block | `gier "PATTERN" FILE` |
| Find every **caller** of a function | `gier "funcname\(" FILE` |
| Trace a **variable** read/write | `gier "some->var" FILE` |
| Rare (2–3 hit) search, full context | `gier -N 200 -M 200 "PATTERN" FILE` |
| Usage across a whole tree | `gier "PATTERN" "test-repos/lang/repo/**/*.ext"` |
| Force file-name prefix | `gier -H "PATTERN" FILE...` |
| Case-insensitive | `gier -i "pattern" FILE` |
| Keep big blocks compact | `gier -M 10 "PATTERN" FILE` |
| See the function, not tiny branches | `gier -N 5 "PATTERN" FILE` (default) |

Exit status: `0` match, `1` none, `2` error.
