#!/usr/bin/env python
"""Credential-pattern scan over trackable text (Roadmap 1.13 / PRD §6).

Seed patterns cover the documented minimum: Bearer tokens, JWTs, AKIA-style
cloud keys, DSNs with embedded passwords, PEM private-key blocks and generic
credential-shaped key/value pairs. Line-level escape hatch:
``# secret-ok: <reason>`` (reviewed exemptions only).

Noise control: obvious placeholder values (``CHANGE_ME``) are ignored, and
the generic key/value rule requires a 12+ char value so prose like
"password rules" never trips. Binary files are skipped. The in-house scan
stays alongside the optional gitleaks pairing because it understands 00-raw
business context and these exemption markers (Roadmap 1.13).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _registry_lib import REPO_ROOT

_SEED_PATTERNS: dict[str, re.Pattern[str]] = {
    "bearer-token": re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/=]{16,}"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "dsn-password": re.compile(
        r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://"
        r"[^\s:/@]+:[^\s@]{3,}@[^\s]+"
    ),
    "generic-key-value": re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|access[_-]?key)\b"
        r"\s*[=:]\s*['\"]?[A-Za-z0-9+/_-]{12,}['\"]?"
    ),
    "private-key-block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
_PLACEHOLDER = re.compile(r"CHANGE_ME", re.IGNORECASE)
_ESCAPE = re.compile(r"#\s*secret-ok:\s*(?P<reason>.+)")
_SKIP_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
    ".zip",
    ".gz",
    ".har",
    ".mp4",
    ".mov",
    ".bin",
    ".xlsx",
    ".docx",
    ".pptx",
}


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)


def _is_match_with_placeholder(match: re.Match[str]) -> bool:
    return bool(_PLACEHOLDER.search(match.group(0)))


def scan_text(path: Path, text: str, report: Report) -> None:
    lines = text.splitlines()
    for number, line in enumerate(lines, start=1):
        if _ESCAPE.search(line):
            continue  # reviewed line-level exemption
        for label, pattern in _SEED_PATTERNS.items():
            match = pattern.search(line)
            if match and not _is_match_with_placeholder(match):
                report.fail(
                    f"{path}:{number}: seeded credential pattern '{label}' "
                    f"(escape only via # secret-ok: <reason>)"
                )


def scan_file(path: Path, report: Report) -> None:
    if path.suffix.lower() in _SKIP_EXTENSIONS:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return  # binary content - manifest provenance covers it (PRD §6)
    scan_text(path, text, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="text files to scan")
    parser.add_argument(
        "--all",
        action="store_true",
        help="scan every tracked text file under iterations/** (00-raw included)",
    )
    args = parser.parse_args(argv)

    targets: list[Path] = list(args.paths)
    if args.all:
        iterations = REPO_ROOT / "iterations"
        if iterations.is_dir():
            targets.extend(sorted(iterations.rglob("*")))
    if not targets:
        parser.error("no paths given (pass file paths or --all)")
        return 2

    report = Report()
    for path in targets:
        if path.is_file():
            scan_file(path, report)

    for problem in report.problems:
        print(f"secret pattern: {problem}")
    if report.problems:
        print(f"check_secrets: {len(report.problems)} finding(s)", file=sys.stderr)
        return 1
    print(f"check_secrets: {len(targets)} file(s) clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
