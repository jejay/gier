#!/usr/bin/env python3
"""Clone the test repositories listed in ``test-repositories.yml``.

Each repository entry pins a specific commit (``commit: <sha>``) so the
fixtures are fully reproducible. Cloning fetches *only* that one commit -- a
shallow, single-commit fetch by SHA -- instead of the whole repository, so
even very large repos (godot, bitcoin, duckdb, aspnetcore, ...) stay small on
disk and on the network.

Repos are installed under ``./test-repos/<LANGUAGE>/<repo>/`` and are
git-ignored (see ``.gitignore``). Git-LFS smudging is skipped. Re-running is a
no-op for repos already at the pinned commit.

On the first run (or whenever an entry has no ``commit`` yet) the currently
checked-out commit is recorded back into ``test-repositories.yml``, which is
what makes later runs deterministic.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPOS_FILE = os.path.join(ROOT, "test-repositories.yml")
DEST = os.path.join(ROOT, "test-repos")


def parse_repos(path: str) -> list[dict]:
    """Parse the simple language-grouped layout of ``test-repositories.yml``.

    Each entry is ``{"lang": ..., "url": ..., "commit": ...}``; ``commit`` is
    ``None`` when the entry has not been pinned yet.
    """
    repos: list[dict] = []
    lang: str | None = None
    cur: dict | None = None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            if not line.startswith(" "):
                lang = line.split(":", 1)[0].strip()
                continue
            stripped = line.strip()
            if stripped.startswith("- "):
                cur = {"lang": lang, "url": None, "commit": None}
                repos.append(cur)
                rest = stripped[2:].strip()
                cur["url"] = rest[4:].strip() if rest.startswith("url:") else rest
            elif cur is not None and stripped.startswith("commit:"):
                cur["commit"] = stripped[len("commit:"):].strip()
    return repos


def dump_repos(repos: list[dict], path: str) -> None:
    """Write the repos back, grouped by language, with pinned commits."""
    by_lang: dict[str, list[dict]] = {}
    order: list[str] = []
    for r in repos:
        by_lang.setdefault(r["lang"], []).append(r)
        if r["lang"] not in order:
            order.append(r["lang"])
    lines: list[str] = []
    for lang in order:
        lines.append(f"{lang}:")
        for r in by_lang[lang]:
            lines.append(f"  - url: {r['url']}")
            if r.get("commit"):
                lines.append(f"    commit: {r['commit']}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip("\n") + "\n")


def repo_name(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


def run(cmd: list[str], cwd: str | None = None, check: bool = True):
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def current_commit(dest: str) -> str | None:
    try:
        return run(["git", "rev-parse", "HEAD"], cwd=dest).stdout.strip()
    except subprocess.CalledProcessError:
        return None


def efficient_clone(url: str, dest: str, commit: str) -> None:
    """Clone exactly one pinned commit by SHA (no full history, no branch tip).

    Falls back to a plain shallow clone of the default branch if the server
    rejects fetching a commit directly by its SHA.
    """
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    run(["git", "init", dest])
    run(["git", "remote", "add", "origin", url], cwd=dest)
    try:
        run(["git", "fetch", "--depth", "1", "origin", commit], cwd=dest)
    except subprocess.CalledProcessError:
        shutil.rmtree(dest)
        run(["git", "clone", "--depth", "1", url, dest])
        if current_commit(dest) != commit:
            run(["git", "fetch", "--depth", "1", "origin", commit], cwd=dest)
    run(["git", "checkout", "--force", commit], cwd=dest)


def shallow_clone(url: str, dest: str) -> None:
    """Original behavior: shallow clone of the default branch tip."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    run(["git", "clone", "--depth", "1", url, dest])


def sync_repo(entry: dict) -> None:
    url = entry["url"]
    commit = entry.get("commit")
    name = repo_name(url)
    dest = os.path.join(DEST, entry["lang"], name)

    if os.path.isdir(dest):
        head = current_commit(dest)
        if commit and head == commit:
            print(f"skip (at {commit[:8]}): {entry['lang']}/{name}")
        elif commit:
            print(f"update -> {commit[:8]}: {entry['lang']}/{name}")
            try:
                run(["git", "fetch", "--depth", "1", "origin", commit], cwd=dest)
            except subprocess.CalledProcessError:
                run(["git", "fetch", "--depth", "1", "origin"], cwd=dest)
            run(["git", "checkout", "--force", commit], cwd=dest)
        else:
            print(f"keep (recording {head[:8]}): {entry['lang']}/{name}")
        return

    if commit:
        print(f"clone {commit[:8]}: {entry['lang']}/{name} <- {url}")
        efficient_clone(url, dest, commit)
    else:
        print(f"clone tip: {entry['lang']}/{name} <- {url}")
        shallow_clone(url, dest)


def main() -> int:
    if not os.path.isfile(REPOS_FILE):
        print(f"setup_test_repos: missing {REPOS_FILE}", file=sys.stderr)
        return 1

    os.environ["GIT_LFS_SKIP_SMUDGE"] = "1"
    repos = parse_repos(REPOS_FILE)
    changed = False

    for entry in repos:
        sync_repo(entry)
        dest = os.path.join(DEST, entry["lang"], repo_name(entry["url"]))
        head = current_commit(dest)
        if head and entry.get("commit") != head:
            entry["commit"] = head
            changed = True

    if changed:
        dump_repos(repos, REPOS_FILE)
        pinned = sum(1 for r in repos if r.get("commit"))
        print(f"\nPinned {pinned} commits into {REPOS_FILE}")

    print(f"\nDone. Repos under {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
