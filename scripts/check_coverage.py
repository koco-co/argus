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
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from _registry_lib import REPO_ROOT, RegistryError, validate_path

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
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_required(iteration_dir: Path, name: str, report: Report) -> Any:
    path = iteration_dir / name
    if not path.exists():
        return None
    try:
        validate_path(path)
    except RegistryError as exc:
        report.fail(str(exc))
        return None
    return _load(path)


# ---------------------------------------------------------------- exemptions


def load_exemptions(iteration_dir: Path) -> dict[str, str]:
    """requirement_id -> kind, for ACCEPTED exemptions with non-empty reasons."""
    path = iteration_dir / "exemptions.yaml"
    if not path.exists():
        return {}
    document = _load(path)
    if document.get("status") != "accepted":
        return {}  # draft/review exemptions are not yet honored
    honored: dict[str, str] = {}
    for entry in document.get("exemptions", []):
        if entry.get("reason", "").strip():
            honored[entry["requirement_id"]] = entry["kind"]
    return honored


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
) -> None:
    requirement_ids: set[str] = set()
    if requirements is not None:
        requirement_ids = {r["requirement_id"] for r in requirements["requirements"]}
        report.fail(
            *_duplicates([r["requirement_id"] for r in requirements["requirements"]], "requirement")
        )

    point_ids: set[str] = set()
    if test_points is not None:
        point_ids = {p["test_point_id"] for p in test_points["test_points"]}
        report.fail(*_duplicates(sorted(point_ids), "test point"))
        for point in test_points["test_points"]:
            for dangling in set(point["requirement_ids"]) - requirement_ids:
                report.fail(
                    f"test point {point['test_point_id']} cites unknown requirement {dangling}"
                )

    case_ids: set[str] = set()
    if cases is not None:
        case_ids = {c["case_id"] for c in cases["cases"]}
        report.fail(*_duplicates(sorted(case_ids), "functional case"))
        for case in cases["cases"]:
            for dangling in set(case["test_point_ids"]) - point_ids:
                report.fail(f"case {case['case_id']} cites unknown test point {dangling}")

    api_ids: set[str] = set()
    if api_cases is not None:
        api_ids = {c["api_case_id"] for c in api_cases["cases"]}
        report.fail(*_duplicates(sorted(api_ids), "API case"))

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
    if not root.is_dir():
        return frozenset()

    import pytest

    class _Recorder:
        nodeids: list[str] = []

        def pytest_collection_finish(self, session: Any) -> None:
            _Recorder.nodeids = [str(item.nodeid) for item in session.items]

    recorder = _Recorder()
    root_absolute = str(root.resolve())
    # Isolate the nested run from this repository (cwd, sys.path, conftest
    # module) so collection cannot leak state into or out of the session.
    previous_cwd = Path.cwd()
    saved_path = list(sys.path)
    saved_conftest = sys.modules.get("conftest")
    os.chdir(root.parent)
    try:
        pytest.main(
            [
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                root_absolute,
            ],
            plugins=[recorder],
        )
    finally:
        os.chdir(previous_cwd)
        sys.path[:] = saved_path
        if saved_conftest is not None:
            sys.modules["conftest"] = saved_conftest
        else:
            sys.modules.pop("conftest", None)
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


# ------------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, help="iterations/<id> directory")
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
    args = parser.parse_args(argv)

    iteration_dir = args.iteration if args.iteration.is_absolute() else REPO_ROOT / args.iteration
    if not iteration_dir.is_dir():
        print(f"error: iteration directory {iteration_dir} not found", file=sys.stderr)
        return 1

    report = Report()
    iteration_yaml = iteration_dir / "iteration.yaml"
    branches: dict = {"ui": True, "api": False}
    state = "created"
    if iteration_yaml.exists():
        try:
            validate_path(iteration_yaml)
        except RegistryError as exc:
            report.fail(str(exc))
        document = _load(iteration_yaml) or {}
        branches = document.get("branches", branches)
        state = document.get("state", state)

    requirements = _load_required(iteration_dir, "requirements.yaml", report)
    test_points = _load_required(iteration_dir, "test_points.yaml", report)
    cases = _load_required(iteration_dir, "functional-cases.yaml", report)
    api_cases = _load_required(iteration_dir, "api/cases.yaml", report)
    traceability = _load_required(iteration_dir, "traceability.yaml", report)
    exemptions = load_exemptions(iteration_dir)

    check_referential_integrity(requirements, test_points, cases, api_cases, traceability, report)

    if args.tier == "from-iteration":
        tiers = tiers_for_state(branches, state)
    elif args.tier == "auto":
        tiers = ["r-t", "t-c", "c-auto"] if branches["ui"] else ["r-a", "a-auto"]
    else:
        tiers = [args.tier]

    collected = collected_nodeids(str(args.automation_dir))
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
            f"[tier={args.tier}, ui={branches['ui']}, state={state}]",
            file=sys.stderr,
        )
        return 1
    print(
        f"check_coverage: OK [tier={args.tier}, ui={branches['ui']}, state={state}, "
        f"tiers checked: {', '.join(tiers) or 'none'}]"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
