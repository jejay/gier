"""Documented, reproducible ``gier`` usage examples over the pinned test repos.

These are *example* tests: each one pins a concrete, sensible ``gier`` command
against a specific file in ``test-repos/`` (which are cloned and pinned, so the
output is reproducible) and asserts the part of the output that makes the
example useful -- usually *which code block* the match landed in, that the
matched text is present, and (where relevant) that the common indentation was
reported in the fence (``N spaces unindented`` / ``N tab unindented``) or that a
``-M`` collapse squashed the block to a single ``blockpath:line:code`` line.

The intent is twofold:

* Showcase what a developer *working in a given repository* might reasonably
  search for -- the entry point of an extractor, the methods of an HTTP
  framework, every function of a C API, the coroutine methods of a ViewModel,
  etc.
* Double as regression tests that ``gier`` keeps pointing at the right block.

Several examples use Python regular expressions (anchors, character classes,
alternation) to show off the search power. Tests are skipped when the
underlying repo is not cloned.
"""

import contextlib
import io
import os
import unittest

from gier import __main__ as cli

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_REPOS = os.path.join(REPO_ROOT, "test-repos")


class GierExampleTest(unittest.TestCase):
    def _gier(self, pattern, rel_path, extra=None):
        path = os.path.join(TEST_REPOS, rel_path)
        if not os.path.exists(path):
            self.skipTest(f"test repo not cloned: {rel_path}")
        args = list(extra or [])
        args += [pattern, path]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = cli.gier_main(list(args))
        return rc, buf.getvalue()


class TestPythonExamples(GierExampleTest):
    def test_ytdlp_base_extractor_method(self):
        # yt-dlp: a developer extending the downloader hunts for the extractor
        # entry point. `def _real_extract` is defined on the base InfoExtractor
        # (a 4000-line class, so gier collapses it to `class:line:code`) and on
        # the small SearchInfoExtractor / UnsupportedURLIE helpers (shown in
        # full). gier points at the *right* enclosing class for each override.
        #   gier "def _real_extract" test-repos/Python/yt-dlp/yt_dlp/extractor/common.py
        rc, out = self._gier(
            "def _real_extract", "Python/yt-dlp/yt_dlp/extractor/common.py"
        )
        self.assertEqual(rc, 0)
        self.assertIn("[0]class InfoExtractor", out)
        self.assertIn("def _real_extract", out)
        # the small helpers are shown in full, the huge base class is squashed
        self.assertIn("[0]class SearchInfoExtractor", out)
        self.assertIn("[0]class UnsupportedURLIE", out)

    def test_homeassistant_integration_teardown(self):
        # Home Assistant: removing an integration goes through
        # `async def async_remove`. The method lives on both the per-entry
        # `ConfigEntry` (huge -> squashed) and the `ConfigEntries` manager
        # (small -> shown in full, with its 4-space indent reported).
        #   gier "async def async_remove" test-repos/Python/core/homeassistant/config_entries.py
        rc, out = self._gier(
            "async def async_remove", "Python/core/homeassistant/config_entries.py"
        )
        self.assertEqual(rc, 0)
        self.assertIn("[0]class ConfigEntry", out)
        self.assertIn("async def async_remove", out)
        self.assertIn("[0]class ConfigEntries", out)
        self.assertIn("4 spaces unindented", out)


class TestJavaScriptExamples(GierExampleTest):
    def test_svelte_compiler_entry_point(self):
        # Svelte: the compiler entry point `export function compile`. The big
        # `compile` is collapsed to a single line; the tiny `compileModule` is
        # printed in full.
        #   gier "export function compile" test-repos/JavaScript/svelte/packages/svelte/src/compiler/index.js
        rc, out = self._gier(
            "export function compile",
            "JavaScript/svelte/packages/svelte/src/compiler/index.js",
        )
        self.assertEqual(rc, 0)
        self.assertIn("[0]function compile", out)
        self.assertIn("export function compile(source, options)", out)
        self.assertIn("[0]function compileModule", out)

    def test_express_middleware_registration(self):
        # Express: `app.use` registers middleware. gier lands inside the
        # `function use` definition (54 lines -> collapsed to the match line).
        #   gier "app\.use" test-repos/JavaScript/express/lib/application.js
        rc, out = self._gier(
            r"app\.use", "JavaScript/express/lib/application.js"
        )
        self.assertEqual(rc, 0)
        self.assertIn("[0]function use", out)
        self.assertIn("app.use = function use(fn)", out)

    def test_fastify_http_method_registration(self):
        # Fastify: every HTTP verb is wired up in one place via
        # `this.decorate(_method, ...)`. gier shows the enclosing
        # `addHttpMethod` block (4-space indent reported).
        #   gier "this\.decorate\(_method" test-repos/JavaScript/fastify/fastify.js
        rc, out = self._gier(
            r"this\.decorate\(_method", "JavaScript/fastify/fastify.js"
        )
        self.assertEqual(rc, 0)
        self.assertIn("[1]function addHttpMethod", out)
        self.assertIn("this.decorate(_method, function (url, options, handler)", out)
        self.assertIn("4 spaces unindented", out)


class TestRustExamples(GierExampleTest):
    def test_nushell_command_run_method(self):
        # nushell: a command's logic lives in `fn run`. `run.rs`'s `Run` impl is
        # 200+ lines, so we raise `-M` to keep it whole; gier reports the 4
        # spaces that were removed.
        #   gier -M 300 "fn run" test-repos/Rust/nushell/crates/nu-command/src/misc/run.rs
        rc, out = self._gier(
            "fn run",
            "Rust/nushell/crates/nu-command/src/misc/run.rs",
            extra=["-M", "300"],
        )
        self.assertEqual(rc, 0)
        self.assertIn("[0]impl Command for Run", out)
        self.assertIn("[1]fn run->Result", out)
        self.assertIn("fn run(", out)
        self.assertIn("4 spaces unindented", out)

    def test_rustpython_public_functions(self):
        # RustPython: list the public functions of a module with a regex. The
        # functions sit at column 0, so no indent is reported.
        #   gier "pub fn \w+" test-repos/Rust/RustPython/crates/compiler-core/src/bytecode.rs
        rc, out = self._gier(
            r"pub fn \w+", "Rust/RustPython/crates/compiler-core/src/bytecode.rs"
        )
        self.assertEqual(rc, 0)
        self.assertIn("[0]fn encode_exception_table->alloc::boxed::Box", out)
        self.assertIn("pub fn encode_exception_table", out)


class TestCExamples(GierExampleTest):
    def test_libgit2_remote_api(self):
        # libgit2: a developer browsing the remote API greps the whole prefix
        # `git_remote_*`. Anchored regex + character class lists every such
        # function; long ones collapse, short ones print in full.
        #   gier "^int git_remote_\w+" test-repos/C/libgit2/src/libgit2/remote.c
        rc, out = self._gier(
            r"^int git_remote_\w+", "C/libgit2/src/libgit2/remote.c"
        )
        self.assertEqual(rc, 0)
        self.assertIn("[0]int git_remote_create_options_init", out)
        self.assertIn("int git_remote_create_options_init(", out)
        # several more matched across the file
        self.assertIn("git_remote_create_with_opts", out)

    def test_zlib_gzip_read_functions(self):
        # zlib: "what gzip read primitives exist?" -> `gz<word>(`. The regex
        # catches both definitions (`gz_load(`, `gzread(`) and references.
        #   gier "gz\w+\(" test-repos/C/zlib/gzread.c
        rc, out = self._gier(r"gz\w+\(", "C/zlib/gzread.c")
        self.assertEqual(rc, 0)
        self.assertIn("[0]local int gz_load", out)
        self.assertIn("gz_load(", out)


class TestCppExamples(GierExampleTest):
    def test_bitcoin_subsidy_halving(self):
        # bitcoin: tracing the block-reward halving logic.
        #   gier "CAmount GetBlockSubsidy" test-repos/C++/bitcoin/src/validation.cpp
        rc, out = self._gier(
            "CAmount GetBlockSubsidy", "C++/bitcoin/src/validation.cpp"
        )
        self.assertEqual(rc, 0)
        self.assertIn("[0]CAmount GetBlockSubsidy", out)
        self.assertIn("CAmount GetBlockSubsidy(int nHeight", out)

    def test_bitcoin_member_function_defs(self):
        # bitcoin: "list every method definition returning bool/CAmount/void".
        # Alternation + anchored regex; `-M 1` squashes each to one
        # `blockpath:line:code` line, giving a compact function index.
        #   gier -M 1 "^(bool|CAmount|void) \w+::\w+" test-repos/C++/bitcoin/src/validation.cpp
        rc, out = self._gier(
            r"^(bool|CAmount|void) \w+::\w+",
            "C++/bitcoin/src/validation.cpp",
            extra=["-M", "1"],
        )
        self.assertEqual(rc, 0)
        self.assertIn(
            "[0]void Chainstate::MaybeUpdateMempoolForReorg{303,1~397,1}:303:void Chainstate::MaybeUpdateMempoolForReorg(",
            out,
        )
        self.assertIn("MemPoolAccept::PreChecks", out)

    def test_imgui_void_functions(self):
        # imgui: "enumerate every ImGui void function". Anchored regex over an
        # 18k-line file, squashed with `-M 1` into a tidy index of
        # `blockpath:line:code` lines.
        #   gier -M 1 "^void ImGui::" test-repos/C++/imgui/imgui.cpp
        rc, out = self._gier(
            r"^void ImGui::", "C++/imgui/imgui.cpp", extra=["-M", "1"]
        )
        self.assertEqual(rc, 0)
        self.assertIn(
            "[0]void ImGui::ColorConvertRGBtoHSV{2881,1~2899,1}:2881:void ImGui::ColorConvertRGBtoHSV(",
            out,
        )
        self.assertIn("ImGui::RenderText", out)


class TestJvmExamples(GierExampleTest):
    def test_kestra_plugin_annotation(self):
        # kestra: "which types are registered as plugins?" -> `@Plugin`. gier
        # surfaces the annotated `LogExporter` class (and its annotations).
        #   gier "@Plugin" test-repos/Java/kestra/core/src/main/java/io/kestra/core/models/tasks/logs/LogExporter.java
        rc, out = self._gier(
            "@Plugin",
            "Java/kestra/core/src/main/java/io/kestra/core/models/tasks/logs/LogExporter.java",
        )
        self.assertEqual(rc, 0)
        self.assertIn("[0]class LogExporter", out)
        self.assertIn("@Plugin", out)

    def test_signal_android_suspend_functions(self):
        # Signal-Android: a ViewModel's coroutine methods. `suspend fun`
        # lives on `CallLinkDetailsViewModel`; one method collapses (the class
        # is large), another prints in full with its 2-space indent reported.
        #   gier "suspend fun" test-repos/Kotlin/Signal-Android/app/src/main/java/org/thoughtcrime/securesms/calls/links/details/CallLinkDetailsViewModel.kt
        rc, out = self._gier(
            "suspend fun",
            "Kotlin/Signal-Android/app/src/main/java/org/thoughtcrime/securesms/calls/links/details/CallLinkDetailsViewModel.kt",
        )
        self.assertEqual(rc, 0)
        self.assertIn("[0]class CallLinkDetailsViewModel", out)
        self.assertIn("suspend fun setName", out)
        self.assertIn("2 spaces unindented", out)


class TestCSharpExamples(GierExampleTest):
    def test_aspnetcore_startup_configuration(self):
        # ASP.NET Core: the request pipeline is assembled in the `Startup`
        # class's `Configure*` methods. gier reports the 4 spaces removed.
        #   gier "public void Configure" test-repos/CSharp/aspnetcore/src/Middleware/Rewrite/sample/Startup.cs
        rc, out = self._gier(
            "public void Configure",
            "CSharp/aspnetcore/src/Middleware/Rewrite/sample/Startup.cs",
        )
        self.assertEqual(rc, 0)
        self.assertIn("[1]public void ConfigureServices", out)
        self.assertIn("public void ConfigureServices", out)
        self.assertIn("4 spaces unindented", out)


if __name__ == "__main__":
    unittest.main()
