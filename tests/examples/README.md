# gier example golden files

Each `*.txt` file in this directory is a self-contained, human-readable example
of running **`gier` for real**. Open any of them to read:

* **`name:`** / **`repo:`** / **`about:`** — what the example shows and why a
  developer working in that repository might run it.
* **`command:`** — the exact `uv run gier ...` command (copy-paste runnable).
* **`=== output ===`** — the complete, verbatim stdout produced by that command.

## Format

```
name: short title
repo: which pinned test-repo
about: one-line description of why a developer would run this
command: uv run gier "pattern" test-repos/PATH/TO/FILE

=== output ===
<EXACT gier stdout, verbatim, until end of file>
```

The output section is everything after the `=== output ===` line, verbatim.

## How to explore

Just open a file. For example, `imgui-void-fns.txt` shows the full command and
the full list of `void ImGui::*` functions `gier` found in `imgui.cpp`.

## How the tests use them

`tests/test_examples.py` discovers every `*.txt` here, shells out to the exact
`command:` string (via `uv run gier`), and asserts the captured stdout equals
the stored `=== output ===` section. So the files are both the documentation
*and* the expected-result fixtures -- if `gier`'s output changes, the test
fails and you can see exactly what differed.

## Adding / refreshing an example

* **Add:** drop a new `<slug>.txt` following the format above.
* **Refresh:** after an intentional change to `gier`, re-run the `command:` and
  replace the text under `=== output ===` with the new stdout.
