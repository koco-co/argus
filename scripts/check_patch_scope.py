#!/usr/bin/env python
"""Self-debug patch-scope guard (Roadmap 1.15 / PRD §4.7).

Evaluates a unified diff produced by the self-debug repair actor:

- ALLOW-LIST: touched paths must be inside ``automation/web/{pages,components}/``
  or ``automation/api/{clients,models}/`` (locator/wait/type/import
  implementation). Everything else - tests, fixtures, iterations/**,
  config/**, .agents/**, AGENTS.md, collection config - is outside the
  allow-list and hard-fails.
- SHARED TESTDATA: ``shared/testdata/**`` is reachable only for data_issue
  reseed-hook wiring; any changed line carrying ``expected_*`` keys or seed
  formula definitions fails (seed formulas are frozen by design - a
  suspected wrong formula escalates to the user via the reopen protocol).
- BANNED PATTERNS on added lines: ``pytest.skip(...)``/``pytest.xfail(...)``,
  ``@pytest.mark.skip``/``@pytest.mark.xfail``, ``assert True`` and bare
  ``except Exception: pass``. Assertion changes cannot hide here: any diff
  touching ``automation/**/tests/**`` already fails as a frozen path.

Usage: ``check_patch_scope.py <patch.diff>`` or ``-`` for stdin.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ALLOWED = re.compile(r"^automation/web/(pages|components)/|^automation/api/(clients|models)/")
_TESTDATA = "shared/testdata/"
_FROZEN_TESTDATA_LINE = re.compile(r"expected_\w+|def seed_", re.IGNORECASE)
_BANNED = (
    ("pytest.skip/xfail", re.compile(r"pytest\.(?:skip|xfail)\(")),
    ("skip/xfail marker", re.compile(r"@pytest\.mark\.(?:skip|xfail)\b")),
    ("assert True", re.compile(r"^\s*assert True\b")),
    ("bare except-pass", re.compile(r"^\s*except Exception:\s*(?:pass\s*)?(?:#.*)?$")),
)


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self._seen_paths: set[str] = set()

    def fail_once_per_path(self, path: str, message: str) -> None:
        if path not in self._seen_paths:
            self._seen_paths.add(path)
            self.fail(message)

    def fail(self, message: str) -> None:
        self.problems.append(message)


def check_patch_text(patch: str, report: Report) -> None:
    current: str | None = None
    for line in patch.splitlines():
        if line.startswith("+++ "):
            target = line[4:].split("\t")[0].strip()
            current = None if target == "/dev/null" else re.sub(r"^b/", "", target)
            continue
        if line.startswith("--- "):
            continue
        if line.startswith(("+", "-")):
            content = line[1:]
            if current is None:
                continue
            in_allow_list = bool(_ALLOWED.match(current))
            in_testdata = current.startswith(_TESTDATA)
            if not in_allow_list and not in_testdata:
                report.fail_once_per_path(
                    current,
                    f"outside allow-list: {current} (only automation/web/pages, "
                    f"automation/web/components, automation/api/clients and "
                    f"automation/api/models may change)",
                )
                continue
            if in_testdata and _FROZEN_TESTDATA_LINE.search(content):
                report.fail(
                    f"{current}: frozen shared-testdata content changed "
                    f"({content.strip()[:60]!r}) - seed formulas and expected_* "
                    f"values escalate to the user, never auto-edit"
                )
            if line.startswith("+"):
                for label, pattern in _BANNED:
                    if pattern.search(content) or (
                        label == "assert True" and pattern.search(content)
                    ):
                        report.fail(
                            f"{current}: banned pattern '{label}' in added line: "
                            f"{content.strip()[:60]!r}"
                        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("patch", nargs="?", help="unified diff file, or '-' to read stdin")
    args = parser.parse_args(argv)

    if not args.patch:
        parser.error("pass a patch file or '-' for stdin")
        return 2
    patch = sys.stdin.read() if args.patch == "-" else Path(args.patch).read_text(encoding="utf-8")

    report = Report()
    check_patch_text(patch, report)

    for problem in report.problems:
        print(f"patch-scope violation: {problem}")
    if report.problems:
        print(f"check_patch_scope: {len(report.problems)} violation(s)", file=sys.stderr)
        return 1
    print("check_patch_scope: patch within allowed scope")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
