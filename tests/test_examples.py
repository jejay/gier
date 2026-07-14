"""Golden-file tests that run the *real* ``gier`` CLI as a subprocess.

Each example lives in its own, human-readable spec file under
``tests/examples/<slug>.txt``. A spec records the exact command to run and the
full, verbatim output it should produce::

    name: <short title>
    repo: <which pinned test-repo>
    about: <one-line description of why a developer would run this>
    command: uv run gier "pattern" test-repos/.../file

    === output ===
    <EXACT gier stdout, verbatim, until end of file>

These are *real* commands: the test shells out to ``uv run gier ...`` (exactly
the string stored in ``command:``) and compares the captured stdout against the
stored ``=== output ===`` section. Nothing is faked -- the same binary a user
would run is invoked, so the spec files double as the complete, explorable
output logs the maintainer can read and judge.

To add an example: drop a new ``<slug>.txt`` in ``tests/examples/`` (the
``command:`` must be a runnable ``uv run gier ...`` invocation). To refresh the
golden output after an intentional change, just re-run that command and paste
the new stdout under ``=== output ===``.

The specs are skipped when ``uv`` is unavailable or when the referenced
``test-repos/`` file is not cloned.
"""

import glob
import os
import shutil
import subprocess
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")
OUT_MARKER = "=== output ==="


def parse_spec(text: str) -> tuple[str, str]:
    """Return ``(command, expected_output)`` from a spec file's text."""
    command = None
    for line in text.split("\n"):
        if line.startswith("command:"):
            command = line[len("command:"):].strip()
            break
    idx = text.index(OUT_MARKER)
    raw = text[idx + len(OUT_MARKER):]
    if raw.startswith("\n"):
        raw = raw[1:]
    return command, raw


def _referenced_repo_files(command: str) -> list[str]:
    return [tok for tok in command.split() if tok.startswith("test-repos/")]


class GierGoldenExampleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("uv") is None:
            raise unittest.SkipTest("uv is not available; cannot run gier CLI")

    def _check_spec(self, spec_path: str):
        with open(spec_path, encoding="utf-8") as fh:
            text = fh.read()
        command, expected = parse_spec(text)

        # Skip gracefully if the target repo is not cloned in this environment.
        for rel in _referenced_repo_files(command):
            if not os.path.exists(os.path.join(REPO_ROOT, rel)):
                self.skipTest(f"test repo not cloned: {rel}")

        proc = subprocess.run(
            command, shell=True, cwd=REPO_ROOT,
            capture_output=True, text=True,
        )
        self.assertEqual(
            proc.returncode, 0,
            msg=f"command failed (rc={proc.returncode}): {command}\n"
                f"stderr: {proc.stderr.strip()}",
        )
        self.assertEqual(
            proc.stdout, expected,
            msg=f"output for {os.path.basename(spec_path)} differs from golden",
        )

    def test_specs_exist(self):
        specs = glob.glob(os.path.join(EXAMPLES_DIR, "*.txt"))
        self.assertGreater(len(specs), 0, "no example spec files found")


# Generate one test method per spec file so the suite shows them individually.
for _SPEC in sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.txt"))):
    _SLUG = os.path.splitext(os.path.basename(_SPEC))[0].replace("-", "_")
    _NAME = f"test_{_SLUG}"

    def _make(spec=_SPEC):
        def _test(self):
            self._check_spec(spec)
        return _test

    setattr(GierGoldenExampleTest, _NAME, _make(_SPEC))


if __name__ == "__main__":
    unittest.main()
