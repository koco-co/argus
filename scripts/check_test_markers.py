#!/usr/bin/env python
"""Test marker consistency checker (Roadmap 1.11 / GLOSSARY marker set).

Every generated automation test must carry exactly the marker set
``@pytest.mark.module("<name>")``, ``@pytest.mark.case_id("<id>")`` and
``@pytest.mark.iteration("<id>")`` (a module-level ``pytestmark = [...]``
assignment satisfies the same contract). Markers are metadata; run selection
is by directory. Consistency rules enforced here:

- the ``module`` marker value must equal the module directory the file lives
  in (``automation/{web,api}/tests/<module>/...``);
- ``iteration``/``case_id`` marker values must agree with the generated
  filename convention ``test_<iteration_id>_<case_id>_<behavior>.py``
  (compared case-insensitively - filenames carry lowercase c0012/a0007,
  markers carry C0012/A0007).

Files outside ``automation/**/tests/**`` are ignored.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

from _registry_lib import REPO_ROOT

_TESTS_MARKER = "/tests/"
_CASE_SEGMENT = re.compile(r"^[ca]\d{4}$", re.IGNORECASE)
_REQUIRED = ("module", "case_id", "iteration")


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)


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


def _string_arg(decorator: ast.expr) -> str | None:
    if isinstance(decorator, ast.Call) and decorator.args:
        arg = decorator.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return None


def collect_markers(tree: ast.AST) -> dict[str, list[str]]:
    """All markers declared via decorators or a module-level pytestmark list."""
    markers: dict[str, list[str]] = {name: [] for name in _REQUIRED}

    def add(name: str | None, value: str | None) -> None:
        if name in markers:
            if value is None:
                value = ""  # marker present but its string argument is missing
            markers[name].append(value)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                add(_marker_name(decorator), _string_arg(decorator))
        if isinstance(node, ast.Assign):
            target = node.targets[0] if node.targets else None
            if isinstance(target, ast.Name) and target.id == "pytestmark":
                elements: list[ast.expr] = []
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    elements = list(node.value.elts)
                else:
                    elements = [node.value]
                for element in elements:
                    if isinstance(element, ast.Call):
                        add(_marker_name(element), _string_arg(element))
                    else:
                        add(_marker_name(element), None)
    return markers


def parse_filename(stem: str) -> tuple[str, str, str] | None:
    """test_<iteration_id>_<case_id>_<behavior> -> (iteration, case, behavior)."""
    if not stem.startswith("test_"):
        return None
    tokens = stem[len("test_") :].split("_")
    case_index = next(
        (index for index, token in enumerate(tokens) if _CASE_SEGMENT.match(token)),
        None,
    )
    if case_index is None or case_index == 0 or case_index == len(tokens) - 1:
        return None
    iteration = "_".join(tokens[:case_index])
    case = tokens[case_index]
    behavior = "_".join(tokens[case_index + 1 :])
    return iteration, case, behavior


def check_file(path: Path, report: Report) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    markers = collect_markers(tree)

    for name in _REQUIRED:
        if not markers[name]:
            report.fail(f"{path}: missing required marker '@pytest.mark.{name}(...)'")
        elif len(markers[name]) > 1:
            report.fail(f"{path}: marker '{name}' declared {len(markers[name])} times")
        if any(value == "" for value in markers[name]):
            report.fail(f"{path}: marker '{name}' requires a single string argument")

    parts = list(path.parts)
    if _TESTS_MARKER in "/".join(parts) + "/":
        tests_index = len(parts) - parts[::-1].index("tests") - 1
        module_dir = parts[tests_index + 1] if tests_index + 1 < len(parts) - 1 else None
        if module_dir and markers["module"]:
            module_value = markers["module"][0]
            if module_value != module_dir:
                report.fail(
                    f"{path}: module marker {module_value!r} does not match the file's "
                    f"module directory {module_dir!r}"
                )

    parsed = parse_filename(path.stem)
    if parsed and all(markers[name] for name in ("iteration", "case_id")):
        iteration, case, _ = parsed
        if markers["iteration"][0] != iteration:
            report.fail(
                f"{path}: iteration marker {markers['iteration'][0]!r} does not match "
                f"filename segment {iteration!r}"
            )
        if markers["case_id"][0].lower() != case.lower():
            report.fail(
                f"{path}: case_id marker {markers['case_id'][0]!r} does not match "
                f"filename segment {case!r}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="test files to check")
    parser.add_argument("--all", action="store_true", help="scan automation/**/tests/**")
    args = parser.parse_args(argv)

    targets: list[Path] = list(args.paths)
    if args.all:
        tests_root = REPO_ROOT / "automation"
        targets.extend(sorted(tests_root.rglob("tests/**/test_*.py")))
    if not targets:
        parser.error("no paths given (pass file paths or --all)")
        return 2

    report = Report()
    for path in targets:
        if path.is_file() and "/tests/" in f"/{path.as_posix()}":
            check_file(path, report)

    for problem in report.problems:
        print(f"marker violation: {problem}")
    if report.problems:
        print(f"check_test_markers: {len(report.problems)} violation(s)", file=sys.stderr)
        return 1
    print(f"check_test_markers: {len(targets)} file(s) consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
