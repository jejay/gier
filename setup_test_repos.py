#!/usr/bin/env python3
"""Clone the test repositories listed in ``test-repositories.yml``.

Repos are installed under ``./test-repos/<LANGUAGE>/<repo>/``. The whole
``test-repos/`` tree is git-ignored (see ``.gitignore``), so the cloned
sub-repositories are never tracked by this project's git.

Clones are shallow (``--depth 1``) and Git-LFS smudging is skipped so large
binary assets (e.g. Godot) are not downloaded. Re-running is a no-op for repos
that are already cloned.
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPOS_FILE = os.path.join(ROOT, "test-repositories.yml")
DEST = os.path.join(ROOT, "test-repos")


def parse_yaml(path: str) -> dict[str, list[str]]:
    """Minimal parser for the simple ``key:\\n  - url`` layout of the file."""
    languages: dict[str, list[str]] = {}
    current: str | None = None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            if not line.startswith(" "):
                key = line.split(":", 1)[0].strip()
                current = key
                languages.setdefault(current, [])
            else:
                item = line.strip()
                if item.startswith("- "):
                    languages[current].append(item[2:].strip())
    return languages


def repo_name(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


def main() -> int:
    if not os.path.isfile(REPOS_FILE):
        print(f"setup_test_repos: missing {REPOS_FILE}", file=sys.stderr)
        return 1

    languages = parse_yaml(REPOS_FILE)
    os.makedirs(DEST, exist_ok=True)
    total = sum(len(v) for v in languages.values())
    done = 0

    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}

    for lang, urls in languages.items():
        lang_dir = os.path.join(DEST, lang)
        os.makedirs(lang_dir, exist_ok=True)
        for url in urls:
            name = repo_name(url)
            target = os.path.join(lang_dir, name)
            done += 1
            if os.path.isdir(os.path.join(target, ".git")):
                print(f"[{done}/{total}] skip (already cloned): {lang}/{name}")
                continue
            print(f"[{done}/{total}] cloning {lang}/{name}")
            print(f"           <- {url}")
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", url, target],
                    check=True,
                    env=env,
                )
            except subprocess.CalledProcessError as exc:
                print(f"[{done}/{total}] FAILED {lang}/{name}: {exc}", file=sys.stderr)

    print(f"\nDone. Cloned repos under {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
