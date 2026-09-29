from __future__ import annotations

from pathlib import Path

CODE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
    ".yaml",
    ".yml",
    ".toml",
}
CODE_NAMES = {"Dockerfile", "Makefile", "Justfile", "AGENTS.md", "CLAUDE.md"}


def is_code_path(path: str) -> bool:
    item = Path(path)
    return item.suffix.lower() in CODE_EXTENSIONS or item.name in CODE_NAMES
