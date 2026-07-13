"""Extensive tests for ``gier``.

These exercise both the library helpers in ``gier.core`` and the
command-line interface (``gier.__main__.main``), using real-world
source files cloned under ``test-repos/``. Tests that need a cloned repo are
skipped when that repo is absent, so the suite stays green without it.

Run with::

    uv run python -m unittest discover -s tests -t . -v
"""

import contextlib
import io
import os
import re
import unittest

from gier import core
from gier import __main__ as cli

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(REPO_ROOT, "sample.py")
TEST_REPOS = os.path.join(REPO_ROOT, "test-repos")

# One block entry in a path line: ``(marker)[level]decl{s,c~e,c}``.
BLOCK_RE = re.compile(r"([><|]*?)\[(\d+)\](.+?)\{(\d+),(\d+)~(\d+),(\d+)\}")


def parse_path(line: str) -> list[dict]:
    out = []
    for m in BLOCK_RE.finditer(line):
        marker, level, decl, s, sc, e, ec = m.groups()
        out.append(
            {
                "marker": marker,
                "level": int(level),
                "decl": decl,
                "start_line": int(s),
                "start_col": int(sc),
                "end_line": int(e),
                "end_col": int(ec),
            }
        )
    return out


def run_main(args: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = cli.main(args)
    return rc, buf.getvalue()


def repo_file(rel: str) -> str:
    return os.path.join(TEST_REPOS, rel)


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def code_section(out: str) -> list[str]:
    lines = out.split("\n")
    section = lines[1:]
    while section and section[-1] == "":
        section.pop()
    return section


# (absolute path, line) cases across languages, including real-world repos.
def all_cases() -> list[tuple[str, int]]:
    cases = [(SAMPLE, 47), (SAMPLE, 21), (SAMPLE, 60)]
    repo = [
        ("C/zlib/adler32.c", 70),
        ("C/zlib/adler32.c", 86),
        ("C++/leveldb/util/arena.cc", 15),
        ("C++/leveldb/util/arena.cc", 21),
        ("C++/leveldb/util/arena.cc", 50),
        ("Java/Mindustry/tools/src/mindustry/tools/MapFixer.java", 22),
        ("Java/Mindustry/tools/src/mindustry/tools/MapFixer.java", 65),
        (
            "Kotlin/Meshtastic-Android/screenshot-tests/src/screenshotTest/"
            "kotlin/org/meshtastic/screenshots/core/AlertScreenshotTests.kt",
            31,
        ),
        ("JavaScript/express/lib/express.js", 37),
    ]
    for rel, line in repo:
        cases.append((repo_file(rel), line))
    return cases


class TestCoreHelpers(unittest.TestCase):
    def setUp(self):
        self.src = read_file(SAMPLE)
        self.blocks = core.analyze_blocks(self.src, path=SAMPLE)

    def test_block_len(self):
        for b in self.blocks:
            self.assertEqual(core.block_len(b), b[4] - b[0] + 1)

    def test_block_path_python(self):
        chain = core.block_path(self.blocks, 47)
        self.assertEqual([b[3] for b in chain], ["def abcd", "if"])
        # only descending markers in a path
        self.assertEqual(core.block_path(self.blocks, 47)[0][2], 0)
        self.assertEqual(core.block_path(self.blocks, 47)[1][2], 1)

    def test_effective_block_merges_short(self):
        # default N=5: the 3-line `if` is shorter -> merged into def abcd
        _, target = core.effective_block(self.blocks, 47, min_length=5)
        self.assertEqual(target[3], "def abcd")
        # N=1: the if is kept (3 >= 1)
        _, target = core.effective_block(self.blocks, 47, min_length=1)
        self.assertEqual(target[3], "if")

    def test_effective_block_climbs_to_root(self):
        # N larger than every block -> climbs to the root block
        _, target = core.effective_block(self.blocks, 47, min_length=1000)
        self.assertEqual(target[3], "def abcd")
        self.assertEqual(target[2], 0)

    def test_effective_block_outside_any(self):
        path_blocks, target = core.effective_block(self.blocks, 3, min_length=5)
        self.assertEqual(path_blocks, [])
        self.assertIsNone(target)


class TestCliRegression(unittest.TestCase):
    """Plain (non-query) mode and argument handling."""

    def test_normal_sample(self):
        rc, out = run_main([SAMPLE])
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("\n"), 1)
        self.assertEqual(
            out,
            "[0]def abcd{21,1~61,20}>[1]if{46,5~48,16}|[1]for{52,5~59,18}<[0]if{63,1~69,13}\n",
        )

    def test_no_args(self):
        rc, out = run_main([])
        self.assertEqual(rc, 2)
        self.assertIn("no input file given", out)

    def test_stdin_rejected(self):
        rc, _ = run_main([])  # no file, no stdin fallback
        self.assertEqual(rc, 2)

    def test_mutually_exclusive_queries(self):
        rc, _ = run_main(["-p", "47", "-c", "47", SAMPLE])
        self.assertEqual(rc, 2)

    def test_invalid_line(self):
        rc, _ = run_main(["-c", "abc", SAMPLE])
        self.assertEqual(rc, 2)

    def test_invalid_min_length(self):
        rc, _ = run_main(["-c", "47", "-N", "abc", SAMPLE])
        self.assertEqual(rc, 2)

    def test_invalid_max_length(self):
        rc, _ = run_main(["-c", "47", "-M", "0", SAMPLE])
        self.assertEqual(rc, 2)

    def test_normal_matches_library(self):
        for path, line in all_cases():
            if not os.path.exists(path):
                continue
            with self.subTest(path=os.path.basename(path)):
                src = read_file(path)
                rc, out = run_main([path])
                self.assertEqual(rc, 0)
                self.assertEqual(out, core.analyze(src, path=path) + "\n")


class TestPathQuery(unittest.TestCase):
    def check(self, path, line):
        if not os.path.exists(path):
            self.skipTest("repo not cloned")
        src = read_file(path)
        blocks = core.analyze_blocks(src, path=path)
        rc, out = run_main(["-p", str(line), path])
        self.assertEqual(rc, 0)
        lines = out.split("\n")
        path_line = lines[0]
        # a path is strictly descending: no siblings, no ascents
        self.assertNotIn("|", path_line)
        self.assertNotIn("<", path_line)
        self.assertEqual(path_line, core.format_blocks(core.block_path(blocks, line)))
        # path query prints no block code
        self.assertEqual(code_section(out), [])

    def test_sample(self):
        self.check(SAMPLE, 47)

    def test_all_cases(self):
        for path, line in all_cases():
            with self.subTest(path=os.path.basename(path), line=line):
                self.check(path, line)


class TestCodeQuery(unittest.TestCase):
    def check(self, path, line, min_length=5, max_length=99999):
        if not os.path.exists(path):
            self.skipTest("repo not cloned")
        src = read_file(path)
        blocks = core.analyze_blocks(src, path=path)
        args = ["-c", str(line)]
        if min_length != 5:
            args += ["-N", str(min_length)]
        if max_length != 99999:
            args += ["-M", str(max_length)]
        args.append(path)
        rc, out = run_main(args)
        self.assertEqual(rc, 0)

        path_line = out.split("\n")[0]
        self.assertNotIn("|", path_line)
        self.assertNotIn("<", path_line)

        parsed = parse_path(path_line)
        self.assertTrue(parsed, f"could not parse path line: {path_line!r}")

        # path must match the library-computed effective path
        expected_blocks, target = core.effective_block(blocks, line, min_length)
        base_path = core.format_blocks(expected_blocks)
        block = parsed[-1]
        s, e = block["start_line"], block["end_line"]
        file_lines = src.splitlines()
        length = e - s + 1
        section = code_section(out)
        if length > max_length:
            # Collapsed by -M: squashed onto the path line as
            # "blockpath:line:code" with no separate code section.
            self.assertEqual(path_line, f"{base_path}:{line}:{file_lines[line - 1]}")
            self.assertEqual(section, [])
        else:
            self.assertEqual(path_line, base_path)
            self.assertEqual(section, file_lines[s - 1 : e])

    def test_sample_default_merges_short(self):
        # default N=5: the 3-line if is merged into def abcd
        self.check(SAMPLE, 47)
        _, target = core.effective_block(
            core.analyze_blocks(read_file(SAMPLE), path=SAMPLE), 47, 5
        )
        self.assertEqual(target[3], "def abcd")

    def test_sample_min1_keeps_if(self):
        self.check(SAMPLE, 47, min_length=1)

    def test_sample_fallback_with_max2(self):
        # the if is 3 lines > 2 -> fallback single line
        self.check(SAMPLE, 47, min_length=1, max_length=2)

    def test_sample_large_block_fallback(self):
        # def abcd is 41 lines > 2 -> fallback single line
        self.check(SAMPLE, 21, max_length=2)

    def test_arena_short_for_merged_then_deeper(self):
        # for (3 lines) merges into Arena::~Arena (5 lines, not < 5)
        self.check(repo_file("C++/leveldb/util/arena.cc"), 15)

    def test_arena_deep_merge_with_N10(self):
        # for -> Arena::~Arena -> namespace all merge up to namespace (>=10)
        path = repo_file("C++/leveldb/util/arena.cc")
        if not os.path.exists(path):
            self.skipTest("repo not cloned")
        _, target = core.effective_block(
            core.analyze_blocks(read_file(path), path=path), 15, 10
        )
        self.assertEqual(target[3], "namespace leveldb")
        self.check(path, 15, min_length=10)

    def test_arena_if_fallback_with_M3(self):
        self.check(repo_file("C++/leveldb/util/arena.cc"), 21, max_length=3)

    def test_all_cases_full(self):
        for path, line in all_cases():
            with self.subTest(path=os.path.basename(path), line=line):
                self.check(path, line)

    def test_all_cases_min1(self):
        # with N=1 nothing is merged; code should match the innermost block
        for path, line in all_cases():
            with self.subTest(path=os.path.basename(path), line=line):
                self.check(path, line, min_length=1)


if __name__ == "__main__":
    unittest.main()
