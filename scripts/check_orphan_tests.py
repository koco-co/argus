#!/usr/bin/env python
"""Reverse orphan-test closure (Roadmap 1.18 / PRD §7.1).

Every test nodeid that pytest ACTUALLY collects over the automation tree
must resolve back to the iteration data that justifies its existence:

- the test carries ``iteration`` and ``case_id`` markers;
- the owning iteration (``iterations/<id>/``) contains a case with that id
  in ``functional-cases.yaml`` (UI) or ``api/cases.yaml`` (API);
- a ``traceability.yaml`` row links that case (and requirement) - so no
  hand-written test can slip in through the side door.

Only an explicitly registered allowlist (``--allowlist``, e.g. harness smoke
tests) exempts a nodeid; ``scripts/tests`` never reaches this checker
because it lives outside the automation collection root.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import sys
from pathlib import Path

import yaml
from _registry_lib import REPO_ROOT
from check_coverage import collected_nodeids

_DEFAULT_ALLOWLIST = REPO_ROOT / "scripts" / "orphan-allowlist.yaml"


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)


def load_allowlist(path: Path) -> list[str]:
    if not path.exists():
        return []
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [str(pattern) for pattern in document.get("exempt", [])]


def is_exempt(nodeid: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(nodeid, pattern) for pattern in patterns)


def _marker_value(node: ast.expr) -> tuple[str, str] | None:
    """从 ``pytest.mark.<name>("value")`` 表达式读取受治理标记。"""
    if not isinstance(node, ast.Call) or not node.args:
        return None
    attr: ast.expr = node.func
    parts: list[str] = []
    while isinstance(attr, ast.Attribute):
        parts.insert(0, attr.attr)
        attr = attr.value
    if isinstance(attr, ast.Name):
        parts.insert(0, attr.id)
    if len(parts) < 2 or parts[-2] != "mark":
        return None
    name = parts[-1]
    arg = node.args[0]
    if name not in ("module", "case_id", "iteration"):
        return None
    if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
        return None
    return name, arg.value


def extract_markers(path: Path, function_name: str) -> dict[str, str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return {}
    markers: dict[str, str] = {}
    # 生成代码采用模块级 pytestmark 列表，函数装饰器仍可覆盖同名标记。
    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        if not any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in targets
        ):
            continue
        value = statement.value
        if value is None:
            continue
        values = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
        for item in values:
            parsed = _marker_value(item)
            if parsed is not None:
                markers[parsed[0]] = parsed[1]
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function_name:
            continue
        for decorator in node.decorator_list:
            parsed = _marker_value(decorator)
            if parsed is not None:
                markers[parsed[0]] = parsed[1]
    return markers


def resolves(case_id: str, iteration_dir: Path, report: Report, nodeid: str) -> None:
    case_found = False
    trace_found = False
    for source, case_key, trace_key in (
        ("functional-cases.yaml", "case_id", "functional_case_id"),
        ("api/cases.yaml", "api_case_id", "api_case_id"),
    ):
        path = iteration_dir / source
        if not path.exists():
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        case_ids = {c[case_key] for c in document.get("cases", []) if case_key in c}
        if case_id in case_ids:
            case_found = True
        trace_path = iteration_dir / "traceability.yaml"
        if trace_path.exists():
            trace = yaml.safe_load(trace_path.read_text(encoding="utf-8")) or {}
            for row in trace.get("links", []):
                if row.get(trace_key) == case_id:
                    trace_found = True
    if not case_found:
        report.fail(
            f"orphan nodeid {nodeid}: case {case_id} does not exist in the owning "
            f"iteration ({iteration_dir.name})"
        )
    elif not trace_found:
        report.fail(f"orphan nodeid {nodeid}: case {case_id} has no traceability row")


def check_nodeids(
    nodeids: frozenset[str],
    automation_dir: Path,
    iterations_dir: Path,
    patterns: list[str],
    report: Report,
) -> None:
    for nodeid in sorted(nodeids):
        if is_exempt(nodeid, patterns):
            continue
        file_part, _, function_name = nodeid.rpartition("::")
        if not file_part or not function_name:
            report.fail(f"orphan nodeid {nodeid}: cannot parse collected item")
            continue
        source_path = automation_dir.parent / file_part
        markers = extract_markers(source_path, function_name)
        iteration_id = markers.get("iteration")
        case_id = markers.get("case_id")
        if not iteration_id or not case_id:
            report.fail(
                f"orphan nodeid {nodeid}: missing iteration/case_id markers - "
                f"hand-written tests must be allowlisted explicitly"
            )
            continue
        resolves(case_id, iterations_dir / iteration_id, report, nodeid)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--automation-dir",
        type=Path,
        default=REPO_ROOT / "automation",
        help="automation tree to collect (tests override)",
    )
    parser.add_argument(
        "--iterations-dir",
        type=Path,
        default=REPO_ROOT / "iterations",
        help="iterations root (tests override)",
    )
    parser.add_argument("--allowlist", type=Path, default=_DEFAULT_ALLOWLIST)
    args = parser.parse_args(argv)

    patterns = load_allowlist(args.allowlist)
    nodeids = collected_nodeids(str(args.automation_dir))
    report = Report()
    check_nodeids(nodeids, args.automation_dir, args.iterations_dir, patterns, report)

    for problem in report.problems:
        print(f"orphan test: {problem}")
    if report.problems:
        print(f"check_orphan_tests: {len(report.problems)} orphan(s)", file=sys.stderr)
        return 1
    print(f"check_orphan_tests: {len(nodeids)} collected nodeid(s) all resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
