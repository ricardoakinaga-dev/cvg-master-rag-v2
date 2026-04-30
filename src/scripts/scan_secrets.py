#!/usr/bin/env python3
"""Lightweight repository secret scanner for CI.

This scanner is intentionally dependency-free so it can run before project
install steps. It focuses on high-signal credential formats and skips generated
artifacts, local env files, virtualenvs, runtime data and dependency folders.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

EXCLUDED_DIRS = {
    ".git",
    ".claude",
    ".codex",
    ".pytest_cache",
    ".mypy_cache",
    ".next",
    ".next-playwright",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "venv-py312-incomplete-20260419",
    "data",
    "logs",
    "test-results",
}

EXCLUDED_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".sqlite",
    ".db",
}

EXCLUDED_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    "tsconfig.tsbuildinfo",
}

SECRET_PATTERNS = {
    "openai_api_key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b"),
    "github_token": re.compile(r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9_]{30,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    kind: str


def should_skip(path: Path) -> bool:
    relative_parts = path.relative_to(ROOT).parts
    if any(part in EXCLUDED_DIRS for part in relative_parts):
        return True
    if path.name in EXCLUDED_FILE_NAMES:
        return True
    if path.name.startswith(".env.") and path.name != ".env.example":
        return True
    return path.suffix.lower() in EXCLUDED_FILE_SUFFIXES


def iter_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not should_skip(path)
    ]


def scan_file(path: Path) -> list[Finding]:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    findings: list[Finding] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        for kind, pattern in SECRET_PATTERNS.items():
            if pattern.search(line):
                findings.append(Finding(path=path, line=line_number, kind=kind))
    return findings


def main() -> int:
    findings = []
    for path in iter_files():
        findings.extend(scan_file(path))

    if not findings:
        print("Secret scan passed: no high-signal secrets found.")
        return 0

    print("Secret scan failed: possible secrets found.", file=sys.stderr)
    for finding in findings:
        relative_path = finding.path.relative_to(ROOT)
        print(f"- {relative_path}:{finding.line} [{finding.kind}]", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
