#!/usr/bin/env python
"""Branch-aware staged coverage gate (Roadmap 1.7 / PRD §5.1).

Referential integrity runs at every tier: every referenced id exists, ids are
unique per scope, traceability rows resolve. Tier demands scale with the
iteration's own progress:

- ``r-t``  every requirement cited by >=1 test point (accepted ``not_testable``
  exemptions remove the demand; ``manual_only`` keeps it)
- ``t-c``  every test point cited by >=1 functional case
- ``c-auto`` every case not excluded by ``manual_only`` maps to >=1 collected
  automation nodeid (``automation_test_ids`` must be REAL ``pytest
  --collect-only`` results - invented-but-well-formed ids fail)
- ``r-a``  every requirement not covered by an accepted exemption appears in
  >=1 API case's ``requirement_ids``
- ``a-auto`` every API case maps to >=1 collected nodeid
- ``from-iteration`` (the CI mode) selects tiers from the iteration's branch
  and current state, cumulatively; ``accepted``/``merged`` demand the
  complete branch chain
- ``auto``  local audit aggregate - runs every tier of the declared branch;
  never a CI gate

Exemptions are honored only when ``exemptions.yaml`` is ``accepted`` and each
entry carries a non-empty reason (the schema enforces the reason).

Nodeid collection runs pytest's collection in-process (``pytest.main`` with
a recording plugin) - real collection, no shell, no string commands.
"""

from __future__ import annotations

import argparse
import importlib
import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from _registry_lib import REPO_ROOT, RegistryError, _assert_safe_path, validate_path
from argus_core.parsing import load_yaml  # pyright: ignore[reportMissingImports]

_TIERS = ("r-t", "t-c", "c-auto", "r-a", "a-auto")
_NODEID = re.compile(r"^automation/.+::[^:]+$")


class CoverageError(Exception):
    """User-facing coverage failure."""


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def fail(self, *messages: str) -> None:
        self.problems.extend(messages)


def _load(path: Path) -> Any:
    _assert_safe_path(path, label="artifact", require_file=True)
    return load_yaml(path.read_bytes())


def _load_required(iteration_dir: Path, name: str, report: Report) -> Any:
    path = iteration_dir / name
    if path.is_symlink():
        report.fail(f"{path}: 必须是安全的普通文件")
        return None
    if not path.exists():
        return None
    try:
        validate_path(path)
        return _load(path)
    except RegistryError as exc:
        report.fail(str(exc))
    except (OSError, UnicodeError, ValueError):
        report.fail(f"{path}: 不是安全可解析的 YAML 文档")
    return None


# ---------------------------------------------------------------- exemptions


def load_exemptions(iteration_dir: Path) -> dict[str, str]:
    """返回已接受且带理由的 ``requirement_id -> kind`` 映射。"""
    path = iteration_dir / "exemptions.yaml"
    if path.is_symlink():
        raise ValueError("exemptions.yaml 必须是安全的普通文件")
    if not path.exists():
        return {}
    if not path.is_file():
        raise ValueError("exemptions.yaml 必须是安全的普通文件")
    document = _load(path)
    if not isinstance(document, dict) or document.get("status") != "accepted":
        return {}  # draft/review exemptions are not yet honored
    honored: dict[str, str] = {}
    for entry in document.get("exemptions", []):
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("requirement_id"), str)
            and isinstance(entry.get("kind"), str)
            and isinstance(entry.get("reason"), str)
            and entry["reason"].strip()
        ):
            honored[entry["requirement_id"]] = entry["kind"]
    return honored


def load_exemption_document(iteration_dir: Path, report: Report) -> dict[str, Any] | None:
    """读取豁免，供完整性检查同时检查未接受的条目。"""
    path = iteration_dir / "exemptions.yaml"
    if path.is_symlink():
        report.fail("exemptions.yaml 必须是安全的普通文件")
        return None
    if not path.exists():
        return None
    if not path.is_file():
        report.fail("exemptions.yaml 必须是安全的普通文件")
        return None
    try:
        document = _load(path)
    except (OSError, UnicodeError, ValueError, RegistryError):
        report.fail("无法读取安全的 exemptions.yaml")
        return None
    if not isinstance(document, dict):
        report.fail("exemptions.yaml 顶层必须是映射")
        return None
    entries = document.get("exemptions", [])
    if not isinstance(entries, list):
        report.fail("exemptions.yaml 的 exemptions 必须是列表")
        document["exemptions"] = []
    return document


# ------------------------------------------------------- referential integrity


def _duplicates(ids: list[str], label: str) -> list[str]:
    seen: set[str] = set()
    duplicates = {i for i in ids if i in seen or seen.add(i)}
    return [f"duplicate {label} id: {i}" for i in sorted(duplicates)]


def check_referential_integrity(
    requirements: dict | None,
    test_points: dict | None,
    cases: dict | None,
    api_cases: dict | None,
    traceability: dict | None,
    report: Report,
    exemptions: dict | None = None,
) -> None:
    requirement_ids: set[str] = set()
    if requirements is not None:
        requirement_values = [r["requirement_id"] for r in requirements["requirements"]]
        requirement_ids = set(requirement_values)
        report.fail(*_duplicates(requirement_values, "requirement"))

    point_ids: set[str] = set()
    if test_points is not None:
        point_values = [p["test_point_id"] for p in test_points["test_points"]]
        point_ids = set(point_values)
        report.fail(*_duplicates(point_values, "test point"))
        for point in test_points["test_points"]:
            for dangling in set(point["requirement_ids"]) - requirement_ids:
                report.fail(
                    f"test point {point['test_point_id']} cites unknown requirement {dangling}"
                )

    case_ids: set[str] = set()
    if cases is not None:
        case_values = [c["case_id"] for c in cases["cases"]]
        case_ids = set(case_values)
        report.fail(*_duplicates(case_values, "functional case"))
        for case in cases["cases"]:
            for dangling in set(case["test_point_ids"]) - point_ids:
                report.fail(f"case {case['case_id']} cites unknown test point {dangling}")

    api_ids: set[str] = set()
    if api_cases is not None:
        api_values = [c["api_case_id"] for c in api_cases["cases"]]
        api_ids = set(api_values)
        report.fail(*_duplicates(api_values, "API case"))

    if exemptions is not None:
        exemption_ids = [
            entry["requirement_id"]
            for entry in exemptions.get("exemptions", [])
            if isinstance(entry, dict) and isinstance(entry.get("requirement_id"), str)
        ]
        report.fail(*_duplicates(exemption_ids, "exemption requirement"))
        for exemption_id in exemption_ids:
            if exemption_id not in requirement_ids:
                report.fail(f"exemption cites unknown requirement {exemption_id}")

    if traceability is not None:
        rows = traceability["links"]
        keys = [
            (
                r["requirement_id"],
                r.get("test_point_id"),
                r.get("functional_case_id"),
                r.get("api_case_id"),
            )
            for r in rows
        ]
        for key, count in {k: keys.count(k) for k in keys}.items():
            if count > 1:
                report.fail(f"duplicate traceability row {key}")
        for row in rows:
            if row["requirement_id"] not in requirement_ids:
                report.fail(f"traceability cites unknown requirement {row['requirement_id']}")
            if row.get("test_point_id") and row["test_point_id"] not in point_ids:
                report.fail(f"traceability cites unknown test point {row['test_point_id']}")
            if row.get("functional_case_id") and row["functional_case_id"] not in case_ids:
                report.fail(
                    f"traceability cites unknown functional case {row['functional_case_id']}"
                )
            if row.get("api_case_id") and row["api_case_id"] not in api_ids:
                report.fail(f"traceability cites unknown API case {row['api_case_id']}")


# ----------------------------------------------------------------- collection


@lru_cache(maxsize=1)
def collected_nodeids(automation_dir: str) -> frozenset[str]:
    """Real pytest collection (``pytest.main --collect-only``) over the
    automation tree, recorded through ``pytest_collection_finish``."""
    root = Path(automation_dir)
    try:
        _assert_safe_path(root, label="automation directory")
    except RegistryError as exc:
        raise CoverageError(str(exc)) from exc
    if root.is_symlink():
        raise CoverageError(f"automation directory must not be a symlink: {root}")
    if not root.is_dir():
        return frozenset()

    pytest = importlib.import_module("pytest")

    class _Recorder:
        nodeids: list[str] = []

        def pytest_collection_finish(self, session: Any) -> None:
            _Recorder.nodeids = [str(item.nodeid) for item in session.items]

    recorder = _Recorder()
    root_absolute = str(root.resolve())
    # Isolate the nested run from this repository and from the surrounding
    # session (cwd, sys.path, conftest module, plugin autoload) so collection
    # cannot leak state into or out of the session.
    previous_cwd = Path.cwd()
    saved_path = list(sys.path)
    saved_conftest = sys.modules.get("conftest")
    saved_flag = os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD")
    modules_before = set(sys.modules)
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.chdir(root.parent)
    try:
        collection_status = pytest.main(
            [
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                root_absolute,
            ],
            plugins=[recorder],
        )
        if collection_status != 0:
            raise CoverageError(
                f"pytest collection failed for {root_absolute} (exit={collection_status})"
            )
    finally:
        os.chdir(previous_cwd)
        sys.path[:] = saved_path
        if saved_flag is None:
            os.environ.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
        else:
            os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = saved_flag
        if saved_conftest is not None:
            sys.modules["conftest"] = saved_conftest
        else:
            sys.modules.pop("conftest", None)
        # drop test modules the nested collection imported so later runs with
        # same-basename files in different roots never hit import mismatch
        for name in set(sys.modules) - modules_before:
            if name.startswith("test_") or name == "conftest":
                sys.modules.pop(name, None)
    # nodeid form varies with the rootdir pytest infers: normalize every
    # variant to the stable "automation/..." repo-relative shape.
    absolute_prefix = f"{root_absolute}/"
    relative_prefix = f"{root.name}/"
    nodeids: list[str] = []
    for nodeid in recorder.nodeids:
        if nodeid.startswith(absolute_prefix):
            nodeids.append(f"{relative_prefix}{nodeid[len(absolute_prefix) :]}")
        elif nodeid.startswith(relative_prefix):
            nodeids.append(nodeid)
        else:
            nodeids.append(f"{relative_prefix}{nodeid}")
    return frozenset(nodeids)


# -------------------------------------------------------------------- tiers


def case_requirements(case: dict, test_points: dict) -> set[str]:
    requirements: set[str] = set()
    for point in test_points["test_points"]:
        if point["test_point_id"] in case["test_point_ids"]:
            requirements.update(point["requirement_ids"])
    return requirements


def _recorded_nodeids(traceability: dict, key: str) -> dict[str, list[str]]:
    recorded: dict[str, list[str]] = {}
    for row in traceability["links"]:
        if row.get(key):
            recorded.setdefault(row[key], []).extend(row.get("automation_test_ids", []))
    return recorded


def check_tier(
    tier: str,
    requirements: dict | None,
    test_points: dict | None,
    cases: dict | None,
    api_cases: dict | None,
    traceability: dict | None,
    exemptions: dict[str, str],
    collected: frozenset[str],
    report: Report,
) -> None:
    if tier == "r-t":
        if requirements is None or test_points is None:
            report.fail("[UI R->T] requires requirements.yaml and test_points.yaml")
            return
        covered: set[str] = set()
        for point in test_points["test_points"]:
            covered.update(point["requirement_ids"])
        for requirement in requirements["requirements"]:
            rid = requirement["requirement_id"]
            if exemptions.get(rid) == "not_testable":
                continue
            if rid not in covered:
                report.fail(f"[UI R->T] requirement {rid} has no test point")

    elif tier == "t-c":
        if test_points is None or cases is None:
            report.fail("[UI T->C] requires test_points.yaml and functional-cases.yaml")
            return
        cited: set[str] = set()
        for case in cases["cases"]:
            cited.update(case["test_point_ids"])
        for point in test_points["test_points"]:
            if point["test_point_id"] not in cited:
                report.fail(f"[UI T->C] test point {point['test_point_id']} has no functional case")

    elif tier == "c-auto":
        if cases is None or traceability is None or test_points is None:
            report.fail(
                "[UI C->automation] requires test_points, functional-cases and traceability.yaml"
            )
            return
        recorded = _recorded_nodeids(traceability, "functional_case_id")
        for case in cases["cases"]:
            linked = case_requirements(case, test_points)
            if linked and all(exemptions.get(rid) == "manual_only" for rid in linked):
                continue  # manual_only removes the automation demand
            nodeids = recorded.get(case["case_id"], [])
            if not nodeids:
                report.fail(f"[UI C->automation] case {case['case_id']} maps to no nodeid")
                continue
            for nodeid in nodeids:
                if not _NODEID.match(nodeid):
                    raise CoverageError(
                        f"traceability automation_test_id is not well-formed: {nodeid}"
                    )
                if nodeid not in collected:
                    cid = case["case_id"]
                    report.fail(
                        f"[UI C->automation] case {cid} nodeid is not collectable: {nodeid}"
                    )

    elif tier == "r-a":
        if requirements is None or api_cases is None:
            report.fail("[API R->A] requires requirements.yaml and api/cases.yaml")
            return
        cited: set[str] = set()
        for case in api_cases["cases"]:
            cited.update(case["requirement_ids"])
        for requirement in requirements["requirements"]:
            rid = requirement["requirement_id"]
            if exemptions.get(rid) == "not_testable":
                continue
            if rid not in cited:
                report.fail(f"[API R->A] requirement {rid} is not cited by any API case")

    elif tier == "a-auto":
        if api_cases is None or traceability is None:
            report.fail("[API A->automation] requires api/cases.yaml and traceability.yaml")
            return
        recorded = _recorded_nodeids(traceability, "api_case_id")
        for case in api_cases["cases"]:
            nodeids = recorded.get(case["api_case_id"], [])
            if not nodeids:
                report.fail(f"[API A->automation] case {case['api_case_id']} maps to no nodeid")
                continue
            for nodeid in nodeids:
                if not _NODEID.match(nodeid):
                    raise CoverageError(
                        f"traceability automation_test_id is not well-formed: {nodeid}"
                    )
                if nodeid not in collected:
                    aid = case["api_case_id"]
                    report.fail(
                        f"[API A->automation] case {aid} nodeid is not collectable: {nodeid}"
                    )


# ------------------------------------------------------- state-based selection

UI_UNLOCK = {
    "r-t": "test_points_accepted",
    "t-c": "functional_cases_exported",
    "c-auto": "web_automation_generated",
}
API_UNLOCK = {
    "r-a": "api_cases_exported",
    "a-auto": "api_automation_generated",
}
UI_ORDER = [
    "created",
    "requirements_clarifying",
    "requirements_accepted",
    "test_points_review",
    "test_points_accepted",
    "functional_cases_generating",
    "functional_cases_exported",
    "web_automation_generating",
    "web_automation_generated",
    "env_pending",
    "env_configured",
    "executing",
    "execution_passed",
    "execution_budget_exceeded",
    "escalated",
    "acceptance_pending",
    "accepted",
    "merged",
]
API_ORDER = [
    "created",
    "requirements_clarifying",
    "requirements_accepted",
    "requirements_mapped",
    "spec_normalizing",
    "spec_valid",
    "api_cases_generating",
    "api_cases_exported",
    "api_automation_generating",
    "api_automation_generated",
    "env_pending",
    "env_configured",
    "executing",
    "execution_passed",
    "execution_budget_exceeded",
    "escalated",
    "acceptance_pending",
    "accepted",
    "merged",
]


def tiers_for_state(branches: dict, state: str) -> list[str]:
    if branches["ui"]:
        unlocks, order = UI_UNLOCK, UI_ORDER
        complete = ["r-t", "t-c", "c-auto"]
    else:
        unlocks, order = API_UNLOCK, API_ORDER
        complete = ["r-a", "a-auto"]
    if state in ("accepted", "merged"):
        return complete  # complete branch chain demanded
    position = order.index(state) if state in order else -1
    return [tier for tier in complete if position >= order.index(unlocks[tier])]


# ---------------------------------------------------------- PR 变更范围选择


def _all_iteration_dirs(iterations_dir: Path) -> list[Path]:
    selected: list[Path] = []
    for child in sorted(iterations_dir.iterdir()):
        if child.is_symlink():
            raise CoverageError(f"iteration directory must not be a symlink: {child}")
        if not child.is_dir():
            continue
        iteration_yaml = child / "iteration.yaml"
        if iteration_yaml.is_symlink():
            raise CoverageError(f"iteration.yaml must not be a symlink: {iteration_yaml}")
        if iteration_yaml.is_file():
            selected.append(child)
    return selected


def select_changed_iteration_dirs(iterations_dir: Path, changed_paths: list[str]) -> list[Path]:
    """把 PR 变更映射到必须执行覆盖门禁的 iteration。

    iteration 自身变化只检查对应目录；自动化、共享代码或覆盖门禁变化可能
    破坏任何既有 nodeid/链路，因此保守检查全部 iteration。
    """
    shared_impacts = (
        "automation/",
        "shared/",
        "scripts/check_coverage.py",
        "scripts/check_api_coverage.py",
        "scripts/check_orphan_tests.py",
    )
    if any(path.startswith(shared_impacts) for path in changed_paths):
        return _all_iteration_dirs(iterations_dir)

    iteration_ids = {
        parts[1]
        for path in changed_paths
        if (parts := Path(path).parts) and len(parts) >= 3 and parts[0] == "iterations"
    }
    selected: list[Path] = []
    for iteration_id in sorted(iteration_ids):
        candidate = iterations_dir / iteration_id
        iteration_yaml = candidate / "iteration.yaml"
        if (
            candidate.is_symlink()
            or not candidate.is_dir()
            or iteration_yaml.is_symlink()
            or not iteration_yaml.is_file()
        ):
            raise CoverageError(f"变更的 iteration 已不存在或不是安全目录：{iteration_id}")
        selected.append(candidate)
    return selected


def changed_paths_since(base_ref: str, repo_root: Path = REPO_ROOT) -> list[str]:
    """读取 base 到当前 HEAD 的文件变化；Git 错误必须显式阻断。"""
    verify = subprocess.run(
        ["git", "rev-parse", "--verify", f"{base_ref}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if verify.returncode != 0:
        raise CoverageError(f"无法解析覆盖比较基线 {base_ref}：{verify.stderr.strip()}")
    diff = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD", "--"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if diff.returncode != 0:
        raise CoverageError(f"无法读取 PR 变更范围：{diff.stderr.strip()}")
    return [line for line in diff.stdout.splitlines() if line]


# ------------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "iteration",
        type=Path,
        nargs="?",
        help="iterations/<id> directory (omit to evaluate every iteration)",
    )
    parser.add_argument(
        "--tier",
        choices=(*_TIERS, "from-iteration", "auto"),
        default="from-iteration",
        help="coverage tier (from-iteration is the CI mode; auto is local-only)",
    )
    parser.add_argument(
        "--automation-dir",
        type=Path,
        default=REPO_ROOT / "automation",
        help="automation tree for nodeid collection (tests override)",
    )
    parser.add_argument(
        "--changed-base",
        help="只检查相对该 Git 基线受影响的 iteration；自动化/共享门禁变化检查全部",
    )
    args = parser.parse_args(argv)

    if args.changed_base and args.iteration is not None:
        parser.error("--changed-base 不能与显式 iteration 路径同时使用")
    if args.iteration is None:
        args.iteration = REPO_ROOT / "iterations"
    iteration_dir = args.iteration if args.iteration.is_absolute() else REPO_ROOT / args.iteration
    try:
        _assert_safe_path(iteration_dir, label="iteration directory")
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if iteration_dir.is_symlink() or not iteration_dir.is_dir():
        print(f"error: iteration directory {iteration_dir} not found", file=sys.stderr)
        return 1

    if args.changed_base:
        try:
            iteration_dirs = select_changed_iteration_dirs(
                iteration_dir,
                changed_paths_since(args.changed_base),
            )
        except CoverageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if not iteration_dirs:
            print("check_coverage: 当前变更不影响 iteration 覆盖链")
            return 0
    else:
        # 无显式 iteration 时评估全部；release push/定时任务使用此路径。
        try:
            iteration_dirs = _all_iteration_dirs(iteration_dir) or [iteration_dir]
        except (OSError, CoverageError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    overall = 0
    for single_dir in iteration_dirs:
        code = evaluate_one(single_dir, args.tier, args.automation_dir)
        overall = overall or code
    return overall


def evaluate_one(iteration_dir: Path, tier_arg: str, automation_dir: Path) -> int:
    report = Report()
    iteration_yaml = iteration_dir / "iteration.yaml"
    branches: dict = {"ui": True, "api": False}
    state = "created"
    if iteration_yaml.is_symlink() or iteration_yaml.exists():
        validated = True
        try:
            validate_path(iteration_yaml)
        except RegistryError as exc:
            report.fail(str(exc))
            validated = False
        document: Any = {}
        if validated:
            try:
                document = _load(iteration_yaml) or {}
            except (OSError, UnicodeError, ValueError, RegistryError):
                report.fail(f"{iteration_yaml}: 不是安全可解析的 YAML 文档")
        if isinstance(document, dict):
            branches = document.get("branches", branches)
            state = document.get("state", state)

    requirements = _load_required(iteration_dir, "requirements.yaml", report)
    test_points = _load_required(iteration_dir, "test_points.yaml", report)
    cases = _load_required(iteration_dir, "functional-cases.yaml", report)
    api_cases = _load_required(iteration_dir, "api/cases.yaml", report)
    traceability = _load_required(iteration_dir, "traceability.yaml", report)
    exemption_document = load_exemption_document(iteration_dir, report)
    exemptions: dict[str, str] = {}
    if exemption_document is not None and exemption_document.get("status") == "accepted":
        for entry in exemption_document.get("exemptions", []):
            if (
                isinstance(entry, dict)
                and isinstance(entry.get("requirement_id"), str)
                and isinstance(entry.get("kind"), str)
                and isinstance(entry.get("reason"), str)
                and entry["reason"].strip()
            ):
                exemptions[entry["requirement_id"]] = entry["kind"]

    check_referential_integrity(
        requirements,
        test_points,
        cases,
        api_cases,
        traceability,
        report,
        exemption_document,
    )

    if tier_arg == "from-iteration":
        tiers = tiers_for_state(branches, state)
    elif tier_arg == "auto":
        tiers = ["r-t", "t-c", "c-auto"] if branches["ui"] else ["r-a", "a-auto"]
    else:
        tiers = [tier_arg]

    try:
        collected = collected_nodeids(str(automation_dir))
    except CoverageError as exc:
        report.fail(f"automation collection unavailable: {exc}")
        collected = frozenset()
    for tier in tiers:
        try:
            check_tier(
                tier,
                requirements,
                test_points,
                cases,
                api_cases,
                traceability,
                exemptions,
                collected,
                report,
            )
        except CoverageError as exc:
            report.fail(f"[{tier}] {exc}")

    if report.problems:
        for problem in report.problems:
            print(f"coverage gap: {problem}")
        print(
            f"check_coverage: {len(report.problems)} gap(s) "
            f"[tier={tier_arg}, ui={branches['ui']}, state={state}]",
            file=sys.stderr,
        )
        return 1
    print(
        f"check_coverage: OK [tier={tier_arg}, ui={branches['ui']}, state={state}, "
        f"tiers checked: {', '.join(tiers) or 'none'}]"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
