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

from _registry_lib import REPO_ROOT, RegistryError, _assert_safe_path
from argus_core.parsing import load_yaml  # pyright: ignore[reportMissingImports]
from check_coverage import CoverageError, collected_nodeids

_DEFAULT_ALLOWLIST = REPO_ROOT / "scripts" / "orphan-allowlist.yaml"


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)


def load_allowlist(path: Path) -> list[str]:
    try:
        _assert_safe_path(path, label="orphan allowlist")
    except RegistryError as exc:
        raise ValueError("orphan allowlist path is unsafe") from exc
    if path.is_symlink():
        raise ValueError("orphan allowlist must be a regular file")
    if not path.exists():
        return []
    if not path.is_file():
        raise ValueError("orphan allowlist must be a regular file")
    try:
        document = load_yaml(path.read_bytes()) or {}
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("orphan allowlist is not safely parseable") from exc
    if not isinstance(document, dict) or not isinstance(document.get("exempt", []), list):
        raise ValueError("orphan allowlist must contain an exempt list")
    patterns = document["exempt"]
    if any(not isinstance(pattern, str) or not pattern for pattern in patterns):
        raise ValueError("orphan allowlist patterns must be non-empty strings")
    return patterns


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
    try:
        _assert_safe_path(iteration_dir, label="orphan iteration")
    except RegistryError:
        report.fail(f"orphan nodeid {nodeid}: unsafe iteration path")
        return
    case_found = False
    trace_found = False
    for source, case_key, trace_key in (
        ("functional-cases.yaml", "case_id", "functional_case_id"),
        ("api/cases.yaml", "api_case_id", "api_case_id"),
    ):
        path = iteration_dir / source
        if not path.is_file() or path.is_symlink():
            continue
        try:
            document = load_yaml(path.read_bytes()) or {}
        except (OSError, UnicodeError, ValueError):
            report.fail(f"orphan source {path} is not safely parseable")
            continue
        if not isinstance(document, dict) or not isinstance(document.get("cases", []), list):
            report.fail(f"orphan source {path} must contain a cases list")
            continue
        cases = document["cases"]
        if any(not isinstance(case, dict) for case in cases):
            report.fail(f"orphan source {path} contains a non-object case")
            continue
        case_ids = {case[case_key] for case in cases if isinstance(case.get(case_key), str)}
        if case_id in case_ids:
            case_found = True
        trace_path = iteration_dir / "traceability.yaml"
        if trace_path.is_symlink():
            report.fail(f"orphan traceability {trace_path} must not be a symlink")
            continue
        if trace_path.is_file():
            try:
                _assert_safe_path(trace_path, label="orphan traceability")
                trace = load_yaml(trace_path.read_bytes()) or {}
            except (OSError, UnicodeError, ValueError, RegistryError):
                report.fail(f"orphan traceability {trace_path} is not safely parseable")
                continue
            if not isinstance(trace, dict) or not isinstance(trace.get("links", []), list):
                report.fail(f"orphan traceability {trace_path} must contain a links list")
                continue
            for row in trace["links"]:
                if isinstance(row, dict) and row.get(trace_key) == case_id:
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
        try:
            _assert_safe_path(source_path, label="orphan source")
            source_path.resolve().relative_to(automation_dir.resolve())
        except (OSError, ValueError, RegistryError):
            report.fail(f"orphan nodeid {nodeid}: unsafe source path")
            continue
        markers = extract_markers(source_path, function_name)
        iteration_id = markers.get("iteration")
        case_id = markers.get("case_id")
        if not iteration_id or not case_id:
            report.fail(
                f"orphan nodeid {nodeid}: missing iteration/case_id markers - "
                f"hand-written tests must be allowlisted explicitly"
            )
            continue
        iteration_reference = Path(iteration_id)
        try:
            iteration_root = iterations_dir.resolve()
            if (
                iteration_reference.is_absolute()
                or "\\" in iteration_id
                or len(iteration_reference.parts) != 1
                or iteration_reference.parts[0] != iteration_id
            ):
                raise ValueError("iteration marker is not a safe child name")
            raw_candidate = iterations_dir / iteration_reference
            _assert_safe_path(raw_candidate, label="orphan iteration")
            if raw_candidate.is_symlink() or not raw_candidate.is_dir():
                raise ValueError("iteration marker does not name a regular directory")
            candidate = raw_candidate.resolve()
            candidate.relative_to(iteration_root)
        except (OSError, ValueError, RegistryError):
            report.fail(f"orphan nodeid {nodeid}: unsafe iteration marker")
            continue
        resolves(case_id, candidate, report, nodeid)


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

    try:
        _assert_safe_path(args.automation_dir, label="automation directory")
        _assert_safe_path(args.iterations_dir, label="iterations directory")
        if (
            args.automation_dir.is_symlink()
            or not args.automation_dir.is_dir()
            or args.iterations_dir.is_symlink()
            or not args.iterations_dir.is_dir()
        ):
            raise ValueError("automation and iterations roots must be regular directories")
        patterns = load_allowlist(args.allowlist)
        nodeids = collected_nodeids(str(args.automation_dir))
    except (OSError, ValueError, RegistryError, CoverageError):
        print("error: orphan allowlist or automation tree is not safely readable", file=sys.stderr)
        return 1
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
