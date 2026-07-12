"""Language dispatch for ``codehierarchy``.

``analyze`` detects the language from the file extension (or an explicit
``--language`` override) and forwards to the appropriate analyzer:

* ``.py`` / ``.pyw`` / ``.pyi`` -> Python (AST based)
* curly-brace languages (C, C++, Objective-C, Java, Kotlin, JavaScript,
  TypeScript, C#, Go, Rust, Swift, Scala, Dart, PHP, ...) -> token based

The output format is identical for every language.
"""

from __future__ import annotations

import os

from .curly_analyzer import analyze_curly
from .python_analyzer import analyze_python

# Map file extensions to a language key.
EXT_LANG = {
    ".py": "python", ".pyw": "python", ".pyi": "python",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".c++": "cpp",
    ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp", ".h++": "cpp",
    ".java": "java",
    ".kt": "kotlin", ".kts": "kotlin",
    ".m": "objc", ".mm": "objcpp",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".swift": "swift",
    ".scala": "scala", ".sc": "scala",
    ".dart": "dart",
    ".php": "php",
}


def detect_language(path: str | None, language: str | None) -> str:
    """Resolve the language key from an explicit override or the file path.

    Falls back to ``"python"`` when neither is available (e.g. stdin without
    ``--language``), since the tool originated as a Python analyzer.
    """
    if language:
        return language
    if path:
        ext = os.path.splitext(path)[1].lower()
        if ext in EXT_LANG:
            return EXT_LANG[ext]
    return "python"


def analyze(source: str, path: str | None = None, language: str | None = None) -> str:
    """Return the single-line block-structure description of ``source``."""
    lang = detect_language(path, language)
    if lang == "python":
        return analyze_python(source)
    return analyze_curly(source, lang)
