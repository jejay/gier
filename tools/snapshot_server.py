#!/usr/bin/env python3
"""Serve the gier snapshot (golden) specs as a browsable website.

Each spec under ``tests/examples/<slug>.txt`` records a ``uv run gier ...``
command and its full expected output. This tiny server renders them as web
pages so a human can read the output and click through to the exact source
file -- and even the matched line -- on GitHub, at the commit the
``test-repos`` are pinned to.

The GitHub URL is derived by parsing the spec:

* the **file** comes from the command's ``test-repos/...`` argument;
* the **commit** and **remote** come from ``git`` inside that cloned repo
  (``test-repos`` are shallow-cloned at a pinned SHA, so ``HEAD`` *is* the
  pinned commit);
* the **line** is parsed out of the gier output itself -- every squashed
  ``blockpath:LINE:code`` finding and every ``LINE:code`` grep-fallback line
  (and every block-path header's start line) becomes a deep link to
  ``#L<line>`` on the GitHub blob.

No external dependencies: pure stdlib :mod:`http.server`.
"""

from __future__ import annotations

import html
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
EXAMPLES_DIR = os.path.join(REPO_ROOT, "tests", "examples")
OUT_MARKER = "=== output ==="

# --- output parsing ------------------------------------------------------- #

# A squashed finding: "blockpath:LINE:code" (block-path ends with '}').
SQUASHED_RE = re.compile(r"^(?P<path>\S+):(?P<line>\d+):(?P<rest>.*)$")
# A single-file grep fallback: "LINE:code".
GREP_RE = re.compile(r"^(?P<line>\d+):(?P<rest>.*)$")
# A block-path header line (no trailing match): capture the innermost start.
BLOCK_RE = re.compile(r"\{(\d+),\d+~\d+,\d+\}")
FENCE_RE = re.compile(r"^\s*```")


def parse_spec(text: str) -> dict:
    """Parse a spec file into ``{name, repo, about, command, output}``."""
    name = repo = about = command = None
    for line in text.split("\n"):
        if line.startswith("name:"):
            name = line[5:].strip()
        elif line.startswith("repo:"):
            repo = line[5:].strip()
        elif line.startswith("about:"):
            about = line[6:].strip()
        elif line.startswith("command:"):
            command = line[8:].strip()
    idx = text.index(OUT_MARKER)
    raw = text[idx + len(OUT_MARKER):]
    if raw.startswith("\n"):
        raw = raw[1:]
    return {"name": name, "repo": repo, "about": about,
            "command": command, "output": raw}


def load_specs() -> list[dict]:
    specs: list[dict] = []
    if not os.path.isdir(EXAMPLES_DIR):
        return specs
    for fn in sorted(os.listdir(EXAMPLES_DIR)):
        if not fn.endswith(".txt"):
            continue
        with open(os.path.join(EXAMPLES_DIR, fn), encoding="utf-8") as fh:
            spec = parse_spec(fh.read())
        spec["slug"] = fn[:-4]
        specs.append(spec)
    return specs


def target_files(command: str) -> list[str]:
    """Positional args of the command that look like test-repos paths."""
    return [tok for tok in command.split() if tok.startswith("test-repos/")]


# --- git -> github -------------------------------------------------------- #

def _git(repo_root: str, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", repo_root, *args],
            capture_output=True, text=True, timeout=10,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception:
        return ""


def _repo_root(abspath: str) -> str | None:
    cur = os.path.dirname(abspath)
    while cur and cur != os.path.dirname(cur):
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        cur = os.path.dirname(cur)
    return None


def _normalize_origin(origin: str) -> str | None:
    if not origin:
        return None
    o = origin.strip()
    if o.startswith("git@"):
        o = o[4:].replace(":", "/", 1)
    o = o.replace(".git", "")
    if o.startswith("ssh://"):
        o = o[6:]
    if o.startswith("//"):
        o = o[2:]
    if o.startswith("http://"):
        o = "https://" + o[len("http://"):]
    if not o.startswith("http"):
        o = "https://" + o
    return o.rstrip("/")


def github_info(file_token: str) -> dict | None:
    """Return ``{base, sha, short, rel}`` for a ``test-repos/...`` path, or None."""
    abspath = os.path.join(REPO_ROOT, file_token)
    if not os.path.exists(abspath):
        return None
    top = _repo_root(abspath)
    if not top:
        return None
    rel = os.path.relpath(abspath, top)
    sha = _git(top, "rev-parse", "HEAD")
    origin = _git(top, "remote", "get-url", "origin")
    base = _normalize_origin(origin)
    if not base or not sha:
        return None
    return {
        "base": f"{base}/blob/{sha}/{rel}",
        "sha": sha,
        "short": sha[:12],
        "rel": rel,
    }


# --- rendering ------------------------------------------------------------ #

CSS = """
* { box-sizing: border-box; }
body { font-family: system-ui, sans-serif; margin: 0; padding: 2rem;
       background: #0f1117; color: #d7dce5; line-height: 1.5; }
a { color: #7aa2f7; }
h1 { margin-top: 0; }
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.command { background: #161922; border: 1px solid #2a2f3a; padding: .6rem .8rem;
           border-radius: 6px; display: inline-block; white-space: pre-wrap; }
pre.output { background: #11141c; border: 1px solid #2a2f3a; border-radius: 6px;
            padding: 1rem; overflow-x: auto; font-size: 13px; }
pre.output a.match { display: block; color: inherit; text-decoration: none;
                     border-left: 3px solid transparent; padding-left: 4px; }
pre.output a.match:hover { background: #1b2030; border-left-color: #7aa2f7; }
.meta { color: #8b93a7; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: .5rem .75rem; border-bottom: 1px solid #232834;
         vertical-align: top; }
th { color: #8b93a7; font-weight: 600; }
.ghlink { background: #1f6feb; color: #fff; padding: .4rem .8rem; border-radius: 6px;
          text-decoration: none; display: inline-block; margin: .5rem 0; }
"""


def _render_output(output: str, blob_base: str | None) -> str:
    # Each token is paired with a flag: is it a block-level <a class="match">?
    # Such an anchor already forces a line break (its CSS is display: block),
    # so the literal "\n" that follows it inside the <pre> would otherwise
    # render as an extra blank line. We therefore suppress the separator that
    # would follow a block anchor and let the block break do the work.
    out: list[tuple[str, bool]] = []
    in_fence = False
    for ln in output.split("\n"):
        if FENCE_RE.match(ln):
            in_fence = not in_fence
            out.append((html.escape(ln), False))
            continue
        esc = html.escape(ln)
        line_no = None
        if not in_fence:
            m = SQUASHED_RE.match(ln)
            if m:
                line_no = int(m.group("line"))
            else:
                m = GREP_RE.match(ln)
                if m:
                    line_no = int(m.group("line"))
                else:
                    found = BLOCK_RE.findall(ln)
                    if found:
                        line_no = int(found[-1])
        if line_no is not None and blob_base:
            href = html.escape(f"{blob_base}#L{line_no}", quote=True)
            out.append((f'<a class="match" href="{href}">{esc}</a>', True))
        else:
            out.append((esc, False))
    # Join, but never insert a "\n" right after a block anchor: its display
    # break already separates it from the next line.
    chunks: list[str] = []
    for i, (token, is_block) in enumerate(out):
        if i > 0 and not out[i - 1][1]:
            chunks.append("\n")
        chunks.append(token)
    return "".join(chunks)


def render_index(specs: list[dict]) -> str:
    rows = []
    for s in specs:
        cmd = html.escape(s["command"] or "")
        rows.append(
            "<tr>"
            f"<td><a href=\"/example/{s['slug']}\">{html.escape(s['name'] or s['slug'])}</a></td>"
            f"<td class=\"meta\">{html.escape(s['repo'] or '')}</td>"
            f"<td>{html.escape(s['about'] or '')}</td>"
            f"<td><code class=\"command\">{cmd}</code></td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>gier snapshot tests</title><style>{CSS}</style></head>
<body>
<h1>gier snapshot tests</h1>
<p class="meta">Each row is a real <code>uv run gier ...</code> command over a
pinned test repo, with its full expected output. Click a name to read the
output; match lines and block headers link straight to the source on GitHub
at the pinned commit.</p>
<table>
<tr><th>example</th><th>repo</th><th>what / why</th><th>command</th></tr>
{''.join(rows)}
</table>
</body></html>"""


def render_example(spec: dict) -> str:
    name = html.escape(spec["name"] or spec["slug"])
    repo = html.escape(spec["repo"] or "")
    about = html.escape(spec["about"] or "")
    command = html.escape(spec["command"] or "")
    files = target_files(spec["command"] or "")
    info = github_info(files[0]) if files else None
    if info:
        gh = (f'<a class="ghlink" href="{html.escape(info["base"], quote=True)}">'
              f'View {html.escape(info["rel"])} on GitHub '
              f'@{html.escape(info["short"])}</a>'
              f'<div class="meta">commit {html.escape(info["sha"])}</div>')
        blob_base = info["base"]
    else:
        gh = '<div class="meta">GitHub link unavailable (test repo not cloned).</div>'
        blob_base = None
    rendered = _render_output(spec["output"] or "", blob_base)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{name} - gier snapshot</title><style>{CSS}</style></head>
<body>
<p><a href="/">&larr; all snapshots</a></p>
<h1>{name}</h1>
<p class="meta">{repo}</p>
<p>{about}</p>
<p class="meta">command:</p>
<code class="command">{command}</code>
{gh}
<pre class="output">{rendered}</pre>
</body></html>"""


# --- server --------------------------------------------------------------- #

class SnapshotHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", ""):
            self._send(200, render_index(load_specs()))
        elif path.startswith("/example/"):
            slug = path[len("/example/"):].strip("/")
            specs = {s["slug"]: s for s in load_specs()}
            if slug not in specs:
                self._send(404, "<h1>404</h1><p>unknown example</p>")
                return
            self._send(200, render_example(specs[slug]))
        else:
            self._send(404, "<h1>404</h1>")

    def _send(self, code: int, body: str):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        return


def create_server(host: str = "0.0.0.0", port: int = 8080) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), SnapshotHandler)


def main(argv: list[str] | None = None):
    import argparse
    import socket
    ap = argparse.ArgumentParser(description="Serve gier snapshot tests as a website.")
    ap.add_argument(
        "--host", default="0.0.0.0",
        help="interface to bind (default 0.0.0.0 = all interfaces, so it is "
             "reachable from other machines on the network)",
    )
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args(argv)
    server = create_server(args.host, args.port)
    # 0.0.0.0 listens on every interface; tell the user how to reach it.
    lan = "<this-machine-ip>"
    if args.host in ("0.0.0.0", ""):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            lan = s.getsockname()[0]
            s.close()
        except Exception:
            pass
    print(f"Serving gier snapshot tests on {args.host}:{args.port}", flush=True)
    if args.host in ("0.0.0.0", ""):
        print(f"  from this machine:  http://127.0.0.1:{args.port}/", flush=True)
        print(f"  from your laptop:    http://{lan}:{args.port}/", flush=True)
    else:
        print(f"  open: http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
