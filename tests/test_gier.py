import contextlib
import io
import os
import tempfile
import unittest

from codehierarchy import __main__ as cli


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
        self.assertIn("0/def foo", out)
        self.assertIn("return 1", out)
        self.assertTrue(out.rstrip().endswith("--"))

    def test_multiple_files_auto_show_filename(self):
        p1 = self._write("a.py", "def foo():\n    return 1\n")
        p2 = self._write("b.py", "def bar():\n    return 2\n")
        rc, out = self._run(["def", p1, p2])
        self.assertEqual(rc, 0)
        self.assertIn(f"{p1}:", out)
        self.assertIn(f"{p2}:", out)
        # findings are separated by a blank line
        self.assertIn("\n--\n\n", out)

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
        self.assertIn("0/def foo", out)

    def test_min_block_length_merges_small_block(self):
        src = "def outer():\n    def inner():\n        return 1\n    return inner()\n"
        p = self._write("a.py", src)
        # default -N 5: inner (2 lines) merges into outer -> only outer in the path
        rc, out = self._run(["return 1", p])
        self.assertEqual(rc, 0)
        block_path = out.split("\n", 1)[0]
        self.assertIn("0/def outer", block_path)
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

    def test_invalid_pattern_is_error(self):
        p = self._write("a.py", "def foo():\n    return 1\n")
        rc, out = self._run(["(", p])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
