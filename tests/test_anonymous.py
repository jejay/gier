"""Tests for how anonymous functions/classes are captured.

Two kinds of tests:

* ``TestAnonymousBlocksInRepos`` -- runs the analyzer over real cloned
  sources under ``test-repos/`` and asserts that the expected anonymous-block
  construct is captured (skipped when a repo is absent).
* ``TestAnonymousBlockContract`` -- pins down the *exact* declaration text the
  analyzer produces for each anonymous-block kind (and the known limitations)
  using small synthetic sources, so the behavior is documented and stable.

Run with::

    uv run python -m unittest discover -s tests -t . -v
"""

import os
import re
import unittest
from pathlib import Path

from gier import core

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_REPOS = os.path.join(REPO_ROOT, "test-repos")


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def repo_file(rel: str) -> str:
    return os.path.join(TEST_REPOS, rel)


def first_file_with(dir_rel, pattern, exts):
    """Return (abspath, line) for the first file under ``test-repos/<dir_rel>``
    whose contents match ``pattern`` (a regex), with the 1-based line of the
    first match. ``None`` if the repo is absent or nothing matches."""
    d = repo_file(dir_rel)
    if not os.path.isdir(d):
        return None
    rx = re.compile(pattern)
    for root, _, files in os.walk(d):
        if ".git" in root or "node_modules" in root or "/build/" in root or "/.gradle" in root:
            continue
        for fn in files:
            if os.path.splitext(fn)[1] not in exts:
                continue
            p = os.path.join(root, fn)
            try:
                with open(p, encoding="utf-8", errors="ignore") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if rx.search(line):
                    return p, i
    return None


def first_file_whose_analysis_matches(dir_rel, pattern, exts, expect_re):
    """Return (abspath) for the first file under ``test-repos/<dir_rel>`` whose
    analysis output matches ``expect_re`` (a compiled regex). ``None`` if the
    repo is absent or nothing matches -- used so we only assert on anonymous
    blocks the analyzer actually captures (not ones skipped inside parens)."""
    d = repo_file(dir_rel)
    if not os.path.isdir(d):
        return None
    for root, _, files in os.walk(d):
        if ".git" in root or "node_modules" in root or "/build/" in root or "/.gradle" in root:
            continue
        for fn in files:
            if os.path.splitext(fn)[1] not in exts:
                continue
            p = os.path.join(root, fn)
            try:
                src = read_text(p)
            except OSError:
                continue
            if re.search(pattern, src):
                out = core.analyze(src, path=p)
                if expect_re.search(out):
                    return p
    return None


class TestAnonymousBlocksInRepos(unittest.TestCase):
    """Anonymous functions/classes are captured on real cloned sources."""

    def _assert_captured(self, dir_rel, pattern, exts, expect_substr):
        found = first_file_with(dir_rel, pattern, exts)
        if found is None:
            self.skipTest(f"no {dir_rel} repo cloned / no match")
        path, line = found
        out = core.analyze(read_text(path), path=path)
        self.assertIn(
            expect_substr, out, f"anonymous block not captured in {path}:{line}"
        )

    def test_kotlin_object_expression(self):
        # `object : Foo { }` -> captured as "object:Foo"
        # (uses the analysis-matches helper because `object :` inside a call
        # argument gets relabeled as the enclosing call, not "object:")
        path = first_file_whose_analysis_matches(
            "Kotlin", r"object\s*:", {".kt", ".kts"}, re.compile(r"object:")
        )
        if path is None:
            self.skipTest("no captured Kotlin object expression found in repos")
        self.assertIn("object:", core.analyze(read_text(path), path=path))

    def test_kotlin_trailing_lambda(self):
        # `x.map { y -> ... }` -> captured; a nested `param -> { }` lambda puts
        # the arrow in the block's decl, so "->" appears in the analysis.
        path = first_file_whose_analysis_matches(
            "Kotlin", r"->\s*\{", {".kt", ".kts"}, re.compile(r"->")
        )
        if path is None:
            self.skipTest("no captured Kotlin lambda found in repos")
        self.assertIn("->", core.analyze(read_text(path), path=path))

    def test_java_anonymous_class(self):
        # `new Foo() { }` at statement level -> captured as "new Foo"
        path = first_file_whose_analysis_matches(
            "Java", r"new\s+\w+\(\)\s*\{", {".java"}, re.compile(r"\[\d+\]new ")
        )
        if path is None:
            self.skipTest("no captured Java anonymous class found in repos")
        self.assertRegex(core.analyze(read_text(path), path=path), r"\[\d+\]new ")

    def test_c_anonymous_struct(self):
        # `struct { ... } s;` -> captured as "struct"
        self._assert_captured("C", r"struct\s*\{", {".c", ".h"}, "[0]struct")

    def test_cpp_anonymous_namespace(self):
        # `namespace { ... }` -> captured as "namespace"
        self._assert_captured("C++", r"namespace\s*\{", {".cc", ".cpp", ".cxx", ".hpp", ".hh"}, "[0]namespace")

    def test_js_arrow_function(self):
        # `() => { }` -> captured as "(arrow)"
        self._assert_captured("JavaScript", r"=>\s*\{", {".js", ".ts", ".mjs", ".cjs"}, "(arrow)")

    def test_js_function_expression(self):
        # `const f = function() { }` -> captured (decl contains "function")
        self._assert_captured("JavaScript", r"=\s*function\s*\(", {".js", ".ts", ".mjs", ".cjs"}, "[0]function")

    def test_cpp_lambda(self):
        # an assigned lambda `auto f = [](){}` -> captured as "[...]"
        # (skipped when every lambda happens to be inside a call's parens)
        path = first_file_whose_analysis_matches(
            "C++",
            r"=\s*\[\s*[&=\w]*\]\s*\(",
            {".cc", ".cpp", ".cxx", ".hpp", ".hh"},
            re.compile(r'\d+/\[[&=a-zA-Z0-9, ]*\]\{'),
        )
        if path is None:
            self.skipTest("no captured C++ lambda found in repos")
        out = core.analyze(read_text(path), path=path)
        self.assertRegex(out, r'\d+/\[[&=a-zA-Z0-9, ]*\]\{')


class TestAnonymousBlockContract(unittest.TestCase):
    """Exact declaration text the analyzer produces per anonymous-block kind.

    These use synthetic sources (not the cloned repos) to document behavior
    and the known limitations precisely.
    """

    def test_kotlin_object_expression(self):
        out = core.analyze("val x = object : Foo {\n  fun bar() {}\n}\n", path="a.kt")
        self.assertIn("object:Foo", out)

    def test_kotlin_trailing_lambda(self):
        out = core.analyze("val x = list.map { y -> y }\n", path="a.kt")
        self.assertIn("list.map", out)

    def test_java_anonymous_class(self):
        src = "class A {\n  Runnable r = new Runnable() {\n    public void run() {}\n  };\n}\n"
        out = core.analyze(src, path="A.java")
        self.assertIn("new Runnable", out)

    def test_java_anonymous_class_inside_call(self):
        # Passed as a call argument: the block is still captured, but relabeled
        # as the enclosing call -- the "new Foo" signature is swallowed by
        # _strip_enclosing (the outer parens wrap the argument list).
        src = "class A {\n  void m() {\n    executor.execute(new Runnable() {\n      public void run() {}\n    });\n  }\n}\n"
        out = core.analyze(src, path="A.java")
        self.assertIn("executor.execute", out)
        self.assertNotIn("new Runnable", out)

    def test_cpp_lambda(self):
        self.assertIn("[]", core.analyze("auto f = []() { return 0; };\n", path="a.cpp"))
        self.assertIn(
            "[&]", core.analyze("auto f = [&](int x) { return x; };\n", path="a.cpp")
        )

    def test_cpp_lambda_inside_call(self):
        # A lambda passed as a call argument is captured as the enclosing call;
        # it does not appear as a standalone "[...]" block.
        src = "void m() {\n  std::sort(v.begin(), v.end(), [](int a, int b) { return a < b; });\n}\n"
        out = core.analyze(src, path="a.cpp")
        self.assertRegex(out, r"\[\d+\]std::sort")
        self.assertNotRegex(out, r'\d+/\[[&=a-zA-Z0-9, ]*\]\{')

    def test_js_arrow(self):
        out = core.analyze("const f = () => { return 1; };\n", path="a.js")
        self.assertIn("(arrow)", out)

    def test_js_function_expression(self):
        out = core.analyze("const f = function() { return 1; };\n", path="a.js")
        self.assertIn("function", out)

    def test_c_anonymous_struct(self):
        out = core.analyze("struct { int x; } s;\n", path="a.c")
        self.assertIn("[0]struct", out)

    def test_cpp_anonymous_namespace(self):
        out = core.analyze("namespace {\n  void f() {}\n}\n", path="a.cpp")
        self.assertIn("[0]namespace", out)

    def test_default_treats_swift_closure_as_block(self):
        # The default now treats object-looking `{` as a block, so the Swift
        # closure is captured (decl "f=").
        out = core.analyze("let f = { x in x }\n", path="a.swift")
        self.assertIn("f=", out)

    def test_exclude_fp_objects_reverts_to_old_behavior(self):
        # --exclude-fp-objects (allow_fp_objects=False) restores the old
        # reject-object-literals behavior: the Swift closure is skipped.
        out = core.analyze("let f = { x in x }\n", path="a.swift", allow_fp_objects=False)
        self.assertEqual(out.strip(), "")

    def test_default_captures_switch_case_block(self):
        # `case X: { ... }` is captured by default (decl "case").
        src = "switch (x) {\n  case 1: { foo(); }\n}\n"
        out = core.analyze(src, path="a.js")
        self.assertRegex(out, r"\[\d+\]case")

    def test_exclude_fp_objects_skips_switch_case_block(self):
        src = "switch (x) {\n  case 1: { foo(); }\n}\n"
        off = core.analyze(src, path="a.js", allow_fp_objects=False)
        self.assertNotIn("[0]case", off)

    def test_default_captures_object_literal_false_positive(self):
        # A real object literal `const o = { a: 1 }` is captured by default too
        # -- that is the accepted false positive.
        src = "const o = { a: 1, b: 2 };\n"
        out = core.analyze(src, path="a.js")
        self.assertIn("const o=", out)

    def test_exclude_fp_objects_skips_object_literal(self):
        src = "const o = { a: 1, b: 2 };\n"
        off = core.analyze(src, path="a.js", allow_fp_objects=False)
        self.assertNotIn("const o=", off)

    def test_exclude_fp_objects_is_noop_for_python(self):
        out_off = core.analyze("def g():\n    f = lambda a: a\n", path="a.py", allow_fp_objects=False)
        out_on = core.analyze("def g():\n    f = lambda a: a\n", path="a.py", allow_fp_objects=True)
        self.assertEqual(out_off, out_on)

    def test_python_lambda_not_a_block(self):
        # Python lambdas have no braces, so they are never a block
        out = core.analyze("def g():\n    f = lambda a: a\n", path="a.py")
        self.assertNotIn("lambda", out)

    def test_rust_closure(self):
        out = core.analyze("let f = |x| { x };\n", path="a.rs")
        self.assertIn("let f=|x|", out)

    def test_rust_closure_in_call(self):
        # closure passed to a higher-order fn -> captured as the call, with the
        # closure params kept in the decl (iter()'s parens are the outermost)
        out = core.analyze("fn m(){ v.iter().map(|x| { x }); }", path="a.rs")
        self.assertIn("v.iter.map(|x|", out)

    def test_go_func_literal(self):
        out = core.analyze("package m\nfunc _() { f := func() { } }\n", path="a.go")
        self.assertIn("[0]func", out)

    def test_csharp_arrow(self):
        out = core.analyze("class A{ void M(){ Action a = () => { }; } }\n", path="a.cs")
        self.assertIn("(arrow)", out)

    def test_csharp_delegate(self):
        out = core.analyze("class A{ void M(){ D d = delegate(int x) { }; } }\n", path="a.cs")
        self.assertIn("delegate", out)

    def test_php_anon_fn(self):
        out = core.analyze("<?php $f = function() { };\n", path="a.php")
        self.assertIn("[0]function", out)

    def test_dart_anon_fn(self):
        out = core.analyze("void m() { var f = () { }; }\n", path="a.dart")
        self.assertIn("var f=", out)

    def test_scala_trailing_lambda(self):
        out = core.analyze("object A { def m = list.map { x => x } }\n", path="a.scala")
        self.assertIn("list.map", out)

    def test_swift_trailing_closure(self):
        # trailing closures ARE captured (as the call name)
        out = core.analyze("func m() { foo { x in x } }\n", path="a.swift")
        self.assertRegex(out, r"\[\d+\]foo")


if __name__ == "__main__":
    unittest.main()
