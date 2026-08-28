#!/usr/bin/env python
"""Static write-call audit of read-only-marked tests (Roadmap 1.17 / PRD §6).

``@pytest.mark.read_only`` is routing metadata, not a capability control -
this checker adds the static layer on top: any call expression inside a
read-only-marked test that resolves to a WRITE-SHAPED method name hard-fails,
naming the offending nodeid and method, unless the line carries a reviewed
``# prod-ok: <reason>`` comment.

Write-shaped = a method whose name tokenizes to a configured denylist verb
(defaults: create update delete remove insert post put patch save destroy
upsert purge) plus any extra names from ``--denylist-file`` (one name or
token per line, YAML list or plain text).
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

from _registry_lib import REPO_ROOT

_DEFAULT_VERBS = {
    "create",
    "update",
    "delete",
    "remove",
    "insert",
    "post",
    "put",
    "patch",
    "save",
    "destroy",
    "upsert",
    "purge",
}
_ESCAPE = re.compile(r"#\s*prod-ok:\s*(?P<reason>.+)")


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)


def _tokens(name: str) -> set[str]:
    return {token.lower() for token in re.split(r"[^a-zA-Z0-9]+", name) if token}


def load_denylist(path: Path | None) -> set[str]:
    verbs = set(_DEFAULT_VERBS)
    if path is None or not path.exists():
        return verbs
    text = path.read_text(encoding="utf-8")
    try:
        import yaml

        document = yaml.safe_load(text)
        if isinstance(document, list):
            verbs.update(str(item).lower() for item in document)
            return verbs
        if isinstance(document, dict):
            for value in document.values():
                if isinstance(value, list):
                    verbs.update(str(item).lower() for item in value)
            return verbs
    except yaml.YAMLError:
        pass
    verbs.update(token.lower() for token in re.split(r"[\s,]+", text) if token)
    return verbs


def scan_file(path: Path, denylist: set[str], report: Report) -> None:
    source = path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        read_only = any(_marker_name(decorator) == "read_only" for decorator in node.decorator_list)
        if not read_only:
            continue
        for item in ast.walk(node):
            if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Attribute):
                continue
            method = item.func.attr
            if _tokens(method) & denylist:
                line = source_lines[item.lineno - 1] if 0 < item.lineno <= len(source_lines) else ""
                if _ESCAPE.search(line):
                    continue
                nodeid = f"{path.as_posix()}::{node.name}"
                report.fail(
                    f"{nodeid}: read_only-marked test calls write-shaped method "
                    f"{method!r} - remove the call or justify with # prod-ok: <reason>"
                )


def _marker_name(decorator: ast.expr) -> str | None:
    node = decorator.func if isinstance(decorator, ast.Call) else decorator
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.insert(0, node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.insert(0, node.id)
    if len(parts) >= 2 and parts[-2] == "mark":
        return parts[-1]
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="test files to audit")
    parser.add_argument("--all", action="store_true", help="audit automation/**/tests/**")
    parser.add_argument(
        "--denylist-file", type=Path, help="extra write-shaped method names (per project)"
    )
    args = parser.parse_args(argv)

    targets: list[Path] = list(args.paths)
    if args.all:
        tests_root = REPO_ROOT / "automation"
        targets.extend(sorted(tests_root.rglob("tests/**/test_*.py")))
    if not targets:
        parser.error("no paths given (pass file paths or --all)")
        return 2

    denylist = load_denylist(args.denylist_file)
    report = Report()
    for path in targets:
        if path.is_file() and "/tests/" in f"/{path.as_posix()}":
            scan_file(path, denylist, report)

    for problem in report.problems:
        print(f"prod-scope violation: {problem}")
    if report.problems:
        print(f"check_prod_scope: {len(report.problems)} violation(s)", file=sys.stderr)
        return 1
    print(f"check_prod_scope: {len(targets)} file(s) clean")
    return 0
