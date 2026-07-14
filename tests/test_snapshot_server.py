"""Tests for the snapshot-test webserver (``tools/snapshot_server.py``).

These spin up the real :class:`http.server` instance on a free port and fetch
pages over HTTP, so they exercise the actual serving path (including parsing
the spec files and building GitHub deep links from the pinned test-repos).
"""

import os
import re
import sys
import threading
import unittest
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
import snapshot_server  # noqa: E402

TEST_REPOS = os.path.join(REPO_ROOT, "test-repos")
BITCOIN = os.path.join(TEST_REPOS, "C++", "bitcoin")
BITCOIN_FILE = "test-repos/C++/bitcoin/src/validation.cpp"


class SnapshotServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = snapshot_server.create_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            exc.close()
            return exc.code, body

    def test_index_lists_examples(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("gier snapshot tests", body)
        # every spec shows up as a link, and its (escaped) command is listed
        for spec in snapshot_server.load_specs():
            self.assertIn(f'/example/{spec["slug"]}', body)
            self.assertIn(snapshot_server.html.escape(spec["command"]), body)

    def test_example_page_renders(self):
        status, body = self._get("/example/ytdlp-base-extractor")
        self.assertEqual(status, 200)
        self.assertIn("yt-dlp", body)
        self.assertIn("def _real_extract", body)
        self.assertIn('class="output"', body)

    def test_no_extra_blank_line_between_block_path_and_fence(self):
        # A matched block-path header is rendered as a <a class="match"> which
        # is already display:block. Inside <pre> (white-space: pre) a literal
        # "\n" after it would therefore render as an *extra* blank line
        # between the path and its code fence. _render_output must suppress that
        # separator so the visual line stream equals the source verbatim.
        output = (
            "[0]class Foo{1,1~9,1}>[1]def bar{2,5~8,1}\n"
            "```4 spaces unindented\n"
            "def bar(self):\n"
            "    return 1\n"
            "```"
        )
        blob = "https://github.com/o/r/blob/abc/rel"
        rendered = snapshot_server._render_output(output, blob)
        # The bug signature: an anchor immediately followed by a newline.
        self.assertNotIn("</a>\n", rendered)
        # Simulate the browser's display:block line breaking and confirm the
        # visual lines exactly match the input (no blank lines added/merged).
        lines, cur = [], ""
        for part in re.split(r'(<a class="match"[^>]*>.*?</a>)', rendered, flags=re.S):
            if not part:
                continue
            if part.startswith('<a '):
                if cur:
                    lines.append(cur)
                    cur = ""
                content = re.sub(
                    r'<a class="match"[^>]*>(.*?)</a>', r'\1', part, flags=re.S
                )
                lines.append(content)
            else:
                for i, seg in enumerate(part.split('\n')):
                    cur += seg
                    if i < part.count('\n'):
                        lines.append(cur)
                        cur = ""
        if cur:
            lines.append(cur)
        self.assertEqual([snapshot_server.html.unescape(x) for x in lines],
                         output.split('\n'))

    def test_unknown_example_is_404(self):
        status, _ = self._get("/example/does-not-exist")
        self.assertEqual(status, 404)

    def test_github_info_absent_repo_is_none(self):
        # no crash, just no link, when the repo isn't cloned
        self.assertIsNone(
            snapshot_server.github_info("test-repos/nope/missing.py")
        )

    def test_github_deep_links_when_repo_present(self):
        if not os.path.isdir(BITCOIN):
            self.skipTest("bitcoin test repo not cloned")
        info = snapshot_server.github_info(BITCOIN_FILE)
        self.assertIsNotNone(info)
        self.assertTrue(info["base"].startswith("https://github.com/bitcoin/bitcoin/blob/"))
        self.assertIn("src/validation.cpp", info["base"])

        status, body = self._get("/example/bitcoin-subsidy")
        self.assertEqual(status, 200)
        # the "view on GitHub" link for the whole file
        self.assertIn(info["base"], body)
        self.assertIn(info["short"], body)
        # a match/block line became a deep link to a specific line
        self.assertIn(f'{info["base"]}#L', body)


if __name__ == "__main__":
    unittest.main()
