#!/usr/bin/env python
"""POM boundary checker (Roadmap 1.10 / ARCHITECTURE §5, CODING_STANDARDS).

Both directions, dispatched by path:

1. Test files (any path containing ``/tests/``): locator/playwright API is
   forbidden - ``get_by_*``, ``locator(...)``, ``frame_locator`` and the
   action-with-selector-literal form (``page.click(".sel")``,
   ``fill("#id", ...)``, ``check``/``hover``/``select_option``/...) as well as
   XPath literals (``//...`` or ``xpath=``). Tests call page objects and
   assert; they never touch the DOM themselves.

2. Page-object files (paths containing ``/pages/``, ``/components/`` or
   ``/screens/``): ``assert`` statements and ``expect(...)`` calls are
   forbidden - objects return values, tests assert. Additionally the
   literal-return heuristic flags a method that returns only string/number
   constants (or f-strings) with no locator interaction in its body - the
   stub-style fake green of Roadmap 5.5(d). The only escape hatch is a
   reviewed line comment ``# static-copy-ok: <reason>`` on the def line.

Files matching neither pattern are ignored.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

from _registry_lib import REPO_ROOT

_LOCATOR_PREFIX = "get_by_"
_LOCATOR_METHODS = {"locator", "frame_locator"}
_ACTION_METHODS = {
    "click",
    "dblclick",
    "fill",
    "check",
    "uncheck",
    "hover",
    "tap",
    "select_option",
    "select_text",
    "set_input_files",
    "type",
}
_OBJECT_MARKERS = ("/pages/", "/components/", "/screens/")
_TESTS_MARKER = "/tests/"
_ESCAPE = re.compile(r"#\s*static-copy-ok:\s*(?P<reason>.+)")


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)


def classify(path: Path) -> str | None:
    posix = path.as_posix()
    if _TESTS_MARKER in f"/{posix}":
        return "tests"
    if any(marker in f"/{posix}" for marker in _OBJECT_MARKERS):
        return "objects"
    return None


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _is_selector_literal(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and (node.value.startswith("//") or "xpath=" in node.value)
    )


def scan_tests(tree: ast.AST, path: Path, report: Report) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        lineno = node.lineno
        if name.startswith(_LOCATOR_PREFIX) or name in _LOCATOR_METHODS:
            report.fail(
                f"{path}:{lineno}: locator API '{name}(...)' inside tests/ - "
                f"encapsulate it in a page object"
            )
            continue
        if name in _ACTION_METHODS and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                report.fail(
                    f"{path}:{lineno}: action '{name}(\"{first.value}\")' with a selector "
                    f"literal inside tests/ - move the interaction into a page object"
                )
            elif _is_selector_literal(first):
                report.fail(f"{path}:{lineno}: xpath selector literal inside tests/")
        for arg in node.args:
            if _is_selector_literal(arg):
                report.fail(f"{path}:{lineno}: xpath selector literal inside tests/")


def scan_objects(tree: ast.AST, path: Path, source_lines: list[str], report: Report) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            report.fail(
                f"{path}:{node.lineno}: assert inside page-object code - return values, "
                f"tests assert"
            )
            continue
        if isinstance(node, ast.Call) and _call_name(node) == "expect":
            report.fail(f"{path}:{node.lineno}: expect(...) inside page-object code - tests assert")

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _line_has_escape(source_lines, node.lineno):
            continue
        returns = [
            item.value
            for item in ast.walk(node)
            if isinstance(item, ast.Return) and item.value is not None
        ]
        if not returns:
            continue
        literal_only = all(
            isinstance(value, ast.Constant)
            and isinstance(value.value, (str, int, float))
            or isinstance(value, ast.JoinedStr)
            for value in returns
        )
        has_locator_interaction = any(
            isinstance(item, ast.Call)
            and (
                _call_name(item).startswith(_LOCATOR_PREFIX) or _call_name(item) in _LOCATOR_METHODS
            )
            for item in ast.walk(node)
        )
        if literal_only and not has_locator_interaction:
            report.fail(
                f"{path}:{node.lineno}: function {node.name!r} returns only literals with "
                f"no locator interaction (stub-return heuristic) - derive values from "
                f"locators or justify with # static-copy-ok: <reason>"
            )


def _line_has_escape(source_lines: list[str], lineno: int) -> bool:
    line = source_lines[lineno - 1] if 0 < lineno <= len(source_lines) else ""
    match = _ESCAPE.search(line)
    return bool(match and match.group("reason").strip())


def scan_file(path: Path, report: Report) -> None:
    kind = classify(path)
    if kind is None:
        return
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    if kind == "tests":
        scan_tests(tree, path, report)
    else:
        scan_objects(tree, path, source.splitlines(), report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="Python files to scan")
    parser.add_argument("--all", action="store_true", help="scan the whole automation tree")
    args = parser.parse_args(argv)

    targets: list[Path] = list(args.paths)
    if args.all:
        targets.extend(sorted((REPO_ROOT / "automation").rglob("*.py")))
    if not targets:
        parser.error("no paths given (pass file paths or --all)")
        return 2

    report = Report()
    for path in targets:
        if path.is_file():
            scan_file(path, report)

    for problem in report.problems:
        print(f"pom boundary violation: {problem}")
    if report.problems:
        print(f"check_pom_boundary: {len(report.problems)} violation(s)", file=sys.stderr)
        return 1
    print(f"check_pom_boundary: {len(targets)} file(s) clean")
    return 0
