import contextlib
import io
import os
import re
import tempfile
import unittest

from gier import __main__ as cli


class GierTest(unittest.TestCase):
    def _run(self, args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = cli.gier_main(list(args))
        return rc, buf.getvalue()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, content):
        p = os.path.join(self.dir, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content)
        return p

    def test_single_file_no_filename_by_default(self):
        p = self._write("a.py", "def foo():\n    return 1\n")
        rc, out = self._run(["foo", p])
        self.assertEqual(rc, 0)
        self.assertNotIn(f"{p}:", out)
        self.assertIn("[0]def foo", out)
        self.assertIn("return 1", out)
        # a single finding has no separator line (md format)
        self.assertNotIn("\n--\n", out)

    def test_multiple_files_auto_show_filename(self):
        p1 = self._write("a.py", "def foo():\n    return 1\n")
        p2 = self._write("b.py", "def bar():\n    return 2\n")
        # default (md) format: both files shown, but findings are NOT separated
        # by a '--' line -- each block's source is its own fenced code block.
        rc, out = self._run(["def", p1, p2])
        self.assertEqual(rc, 0)
        self.assertIn(f"{p1}:", out)
        self.assertIn(f"{p2}:", out)
        self.assertNotIn("\n--\n", out)
        # '--format=plain' restores the classic '--' separator between findings.
        rc, out_plain = self._run(["--format=plain", "def", p1, p2])
        self.assertEqual(rc, 0)
        self.assertIn("\n--\n", out_plain)
        self.assertNotIn("\n--\n\n", out_plain)

    def test_no_filename_flag_overrides_multiple(self):
        p1 = self._write("a.py", "def foo():\n    return 1\n")
        p2 = self._write("b.py", "def bar():\n    return 2\n")
        rc, out = self._run(["-h", "def", p1, p2])
        self.assertEqual(rc, 0)
        self.assertNotIn(f"{p1}:", out)
        self.assertNotIn(f"{p2}:", out)

    def test_with_filename_flag_on_single_file(self):
        p = self._write("a.py", "def foo():\n    return 1\n")
        rc, out = self._run(["-H", "foo", p])
        self.assertEqual(rc, 0)
        self.assertIn(f"{p}:", out)

    def test_ignore_case(self):
        p = self._write("a.py", "def foo():\n    return 1\n")
        rc, out = self._run(["FOO", p])
        self.assertEqual(rc, 1)  # no match without -i
        rc, out = self._run(["-i", "FOO", p])
        self.assertEqual(rc, 0)
        self.assertIn("[0]def foo", out)

    def test_min_block_length_merges_small_block(self):
        src = "def outer():\n    def inner():\n        return 1\n    return inner()\n"
        p = self._write("a.py", src)
        # default -N 5: inner (2 lines) merges into outer -> only outer in the path
        rc, out = self._run(["return 1", p])
        self.assertEqual(rc, 0)
        block_path = out.split("\n", 1)[0]
        self.assertIn("[0]def outer", block_path)
        self.assertNotIn("def inner", block_path)
        # -N 2: inner is kept -> inner appears in the path line
        rc, out = self._run(["-N", "2", "return 1", p])
        self.assertEqual(rc, 0)
        block_path = out.split("\n", 1)[0]
        self.assertIn("def inner", block_path)

    def test_max_block_length_collapses_to_line(self):
        src = "def big():\n    a = 1\n    b = 2\n    c = 3\n    d = 4\n    return a\n"
        p = self._write("a.py", src)
        # -M 1: block too long -> single 'line:code' fallback (line 3)
        rc, out = self._run(["-M", "1", "b = 2", p])
        self.assertEqual(rc, 0)
        self.assertIn("3:", out)
        self.assertNotIn("return a", out)
        # default -M: whole block source is shown
        rc, out = self._run(["b = 2", p])
        self.assertEqual(rc, 0)
        self.assertIn("return a", out)
        self.assertNotIn("3:", out)

    def test_default_max_block_length_is_20(self):
        # gier collapses blocks longer than 20 lines by default (token-friendly
        # for agents); an explicit large -M restores the full block.
        src = "def big():\n" + "\n".join(f"    x{i} = {i}" for i in range(25)) + "\n"
        p = self._write("a.py", src)
        rc, out = self._run(["x0 = 0", p])
        self.assertEqual(rc, 0)
        self.assertIn("2:", out)  # collapsed to a single 'LINE:CODE'
        self.assertNotIn("x24 = 24", out)
        rc, out = self._run(["-M", "99999", "x0 = 0", p])
        self.assertEqual(rc, 0)
        self.assertIn("x24 = 24", out)  # full block shown again

    def test_glob_pattern_expands(self):
        self._write("a.py", "def foo():\n    return 1\n")
        self._write("sub/b.py", "def bar():\n    return 2\n")
        pattern = os.path.join(self.dir, "**", "*.py")
        rc, out = self._run(["def", pattern])
        self.assertEqual(rc, 0)
        # glob returned more than one file -> filename auto-shown
        self.assertIn("a.py", out)
        self.assertIn("sub", out)

    def test_object_literal_counted_by_default(self):
        p = self._write("a.js", "const o = { a: 1, b: 2 };\n")
        rc, out = self._run(["const", p])
        self.assertEqual(rc, 0)
        self.assertIn("const o=", out)

    def test_no_match_returns_one(self):
        p = self._write("a.py", "def foo():\n    return 1\n")
        rc, out = self._run(["zzz_no_such_token", p])
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")

    def test_missing_literal_file_is_error(self):
        rc, out = self._run(["foo", os.path.join(self.dir, "does_not_exist.py")])
        self.assertEqual(rc, 2)

    def test_match_outside_any_block_falls_back_to_grep(self):
        # "level" appears in the module docstring (no enclosing block) and
        # inside a function (enclosed). The docstring match falls back to a
        # classic grep line; the in-block match uses the block path.
        src = '"""level mentioned at module level"""\n\n\ndef f():\n    level = 1\n    return level\n'
        p = self._write("a.py", src)
        rc, out = self._run(["level", p])
        self.assertEqual(rc, 0)
        self.assertIn("[0]def f", out)  # in-block match -> block path
        self.assertIn('1:"""level mentioned', out)  # docstring -> grep fallback
        # default (md) format has no '--' separator between findings; the block
        # path and the grep-fallback line are simply adjacent.
        self.assertNotIn("\n--\n", out)
        # '--format=plain' restores the classic '--' separator.
        rc, out_plain = self._run(["--format=plain", "level", p])
        self.assertEqual(rc, 0)
        self.assertIn("\n--\n", out_plain)

    def test_match_with_no_blocks_uses_grep_fallback(self):
        # A file with no blocks at all falls back to grep lines for every match.
        src = "# level only at top level\nx = 1\n"
        p = self._write("a.py", src)
        rc, out = self._run(["level", p])
        self.assertEqual(rc, 0)
        self.assertIn("1:# level only at top level", out)

    def test_multiline_flag_always_set(self):
        self.assertTrue(cli._compile_pattern("x", False).flags & re.MULTILINE)
        self.assertTrue(cli._compile_pattern("x", True).flags & re.MULTILINE)
        self.assertTrue(cli._compile_pattern("x", True).flags & re.IGNORECASE)
        self.assertFalse(cli._compile_pattern("x", False).flags & re.IGNORECASE)

    def test_invalid_pattern_is_error(self):
        p = self._write("a.py", "def foo():\n    return 1\n")
        rc, out = self._run(["(", p])
        self.assertEqual(rc, 2)

    def test_color_always_wraps_only_the_match_text(self):
        p = self._write("a.py", "def foo():\n    return 1\n")
        rc, out = self._run(["--color=always", "foo", p])
        self.assertEqual(rc, 0)
        # the matched 'foo' is wrapped, and nothing else on the line is
        self.assertIn("\x1b[1;31mfoo\x1b[0m", out)
        # the block-path metadata is never colored
        self.assertIn("[0]def ", out)
        self.assertNotIn("\x1b[1;31m[0]def", out)

    def test_color_never_emits_no_escape(self):
        p = self._write("a.py", "def foo():\n    return 1\n")
        rc, out = self._run(["--color=never", "foo", p])
        self.assertEqual(rc, 0)
        self.assertNotIn("\x1b", out)

    def test_color_auto_is_off_when_stdout_is_not_a_tty(self):
        # the harness captures stdout into a non-tty buffer, so 'auto' must
        # behave like 'never' (no escape codes).
        p = self._write("a.py", "def foo():\n    return 1\n")
        rc, out = self._run(["--color=auto", "foo", p])
        self.assertEqual(rc, 0)
        self.assertNotIn("\x1b", out)

    def test_color_default_is_auto(self):
        # with no --color flag, behavior must equal --color=auto (off here)
        p = self._write("a.py", "def foo():\n    return 1\n")
        rc, out = self._run(["foo", p])
        self.assertEqual(rc, 0)
        self.assertNotIn("\x1b", out)

    def test_color_invalid_value_is_error(self):
        p = self._write("a.py", "def foo():\n    return 1\n")
        rc, out = self._run(["--color=rainbow", "foo", p])
        self.assertEqual(rc, 2)
        self.assertIn("--color must be auto, always or never", out)

    def test_color_always_colors_collapsed_block_line(self):
        # with -M 1 the block collapses to a single 'LINE:CODE' record; the
        # matched text inside that record must still be colored.
        src = "def big():\n    a = 1\n    b = 2\n    return a\n"
        p = self._write("a.py", src)
        rc, out = self._run(["--color=always", "-M", "1", "b = 2", p])
        self.assertEqual(rc, 0)
        self.assertIn("\x1b[1;31mb = 2\x1b[0m", out)

    def test_format_md_wraps_source_in_code_fence(self):
        # default (md) format wraps the block's source in a fenced code block
        # and omits the '--' inter-finding separator.
        p = self._write("a.py", "def foo():\n    return 1\n")
        rc, out = self._run(["foo", p])
        self.assertEqual(rc, 0)
        self.assertIn("[0]def foo", out)
        self.assertIn("\n```\n", out)
        # the fenced block is closed again before the record ends
        self.assertIn("```\n", out)
        self.assertNotIn("\n--\n", out)

    def test_format_plain_uses_separator_and_no_fence(self):
        # '--format=plain' restores the classic '--' separator and prints the
        # source unfenced.
        p1 = self._write("a.py", "def foo():\n    return 1\n")
        p2 = self._write("b.py", "def bar():\n    return 2\n")
        rc, out = self._run(["--format=plain", "def", p1, p2])
        self.assertEqual(rc, 0)
        self.assertIn("\n--\n", out)
        self.assertNotIn("```", out)

    def test_format_invalid_value_is_error(self):
        p = self._write("a.py", "def foo():\n    return 1\n")
        rc, out = self._run(["--format=rainbow", "foo", p])
        self.assertEqual(rc, 2)
        self.assertIn("--format must be one of md, plain", out)

    def test_collapsed_block_squashed_in_all_formats(self):
        # When -M collapses a block, the record is squashed onto a single line
        # as blockpath:line:code -- no fence, no separator -- in every format.
        src = "def big():\n    a = 1\n    b = 2\n    return a\n"
        p = self._write("a.py", src)
        for fmt in ("md", "plain"):
            with self.subTest(fmt=fmt):
                rc, out = self._run([f"--format={fmt}", "-M", "1", "b = 2", p])
                self.assertEqual(rc, 0)
                self.assertIn("[0]def big", out)
                self.assertIn(":3:    b = 2", out)
                # squashed onto one line: no code fence, no newline between the
                # block path and the "line:code" tail.
                self.assertNotIn("```", out)
                self.assertNotIn("\n3:", out)
                # the full block is not shown
                self.assertNotIn("return a", out)

    # --- markdown common-indentation dedenting ---

    def test_md_dedents_common_indent_and_reports_in_fence(self):
        from gier.__main__ import _format_md_code_block
        code = ["    def f():", "        x = 1", "        return x"]
        block = _format_md_code_block(code, "source\n")
        self.assertTrue(block.startswith("```4 spaces unindented\n"))
        self.assertIn("def f():", block)
        self.assertIn("    x = 1", block)           # relative indent preserved
        self.assertNotIn("    def f():", block)     # 4-space common indent gone
        self.assertTrue(block.rstrip().endswith("```"))

    def test_md_no_common_indent_left_verbatim(self):
        from gier.__main__ import _format_md_code_block
        code = ["def f():", "    x = 1"]             # first line at column 0
        block = _format_md_code_block(code, "source\n")
        self.assertTrue(block.startswith("```\n"))   # no "unindented" note
        self.assertIn("def f():\n    x = 1", block)

    def test_md_single_line_block_not_dedented(self):
        from gier.__main__ import _format_md_code_block
        block = _format_md_code_block(["    x = 1"], "source\n")
        self.assertTrue(block.startswith("```\n"))
        self.assertIn("    x = 1", block)

    def test_md_tab_indent_reports_tabs(self):
        from gier.__main__ import _format_md_code_block
        code = ["\tdef f():", "\t\tx = 1"]
        block = _format_md_code_block(code, "source\n")
        self.assertTrue(block.startswith("```1 tab unindented\n"))
        self.assertIn("def f():", block)
        self.assertIn("\tx = 1", block)

    def test_md_mixed_indent_not_dedented(self):
        from gier.__main__ import _format_md_code_block
        code = ["\t  def f():", "\t  x = 1"]         # common prefix is mixed
        block = _format_md_code_block(code, "source\n")
        self.assertTrue(block.startswith("```\n"))   # not handled -> verbatim
        self.assertIn("\t  def f():", block)

    def test_md_preserves_crlf(self):
        from gier.__main__ import _format_md_code_block
        code = ["    def f():", "        x = 1"]
        block = _format_md_code_block(code, "line1\r\nline2\r\n")
        self.assertIn("\r\n", block)
        self.assertNotIn("\n", block.replace("\r\n", ""))

    def test_gier_md_dedents_indented_rust_block(self):
        example = os.path.join(os.path.dirname(__file__), "..",
                               "examples", "space_sim.rs")
        if not os.path.exists(example):
            self.skipTest("example not present")
        rc, out = self._run(["match", example])
        self.assertEqual(rc, 0)
        self.assertIn("20 spaces unindented", out)
        self.assertIn("4 spaces unindented", out)
        # the deeply-nested match body lost its 20-space common indent
        self.assertIn("match body.classify() {", out)
        self.assertNotIn("                    match body.classify() {", out)


if __name__ == "__main__":
    unittest.main()
