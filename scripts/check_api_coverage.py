#!/usr/bin/env python
"""API endpoint coverage checker (Roadmap 1.8 / PRD §4.4).

Checks ``api/spec.normalized.yaml`` against ``api/cases.yaml``:

- every endpoint NOT marked ``out_of_scope`` has >=1 ``happy_path`` case and
  >=1 ``negative``/``edge`` case (gaps are reported with the operation_id);
- an endpoint marked ``out_of_scope: true`` must carry a non-empty
  ``out_of_scope_reason`` (omitting the flag entirely stays legal - the
  vacuous-conditional rule from DATA_MODEL §6);
- every API case cites ``requirement_ids[]``; every requirement not removed
  by an ACCEPTED ``not_testable`` exemption appears in >=1 API case's
  ``requirement_ids[]`` (``manual_only`` does NOT remove the R->A demand -
  DATA_MODEL §2.1: it only stops the automation tier).

Sources are schema-gated through the shared registry before checking.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml
from _registry_lib import REPO_ROOT, RegistryError, validate_path

HappyKinds = {"happy_path"}
NegativeKinds = {"negative", "edge"}


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def fail(self, *messages: str) -> None:
        self.problems.extend(messages)


def _load_validated(iteration_dir: Path, name: str) -> dict[str, Any]:
    path = iteration_dir / name
    validate_path(path)
    document: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return document


def load_exemptions(iteration_dir: Path) -> dict[str, str]:
    """requirement_id -> kind for ACCEPTED exemptions with non-empty reasons."""
    path = iteration_dir / "exemptions.yaml"
    if not path.exists():
        return {}
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if document.get("status") != "accepted":
        return {}
    honored: dict[str, str] = {}
    for entry in document.get("exemptions", []):
        if entry.get("reason", "").strip():
            honored[entry["requirement_id"]] = entry["kind"]
    return honored


def check(
    spec: dict[str, Any],
    cases: dict[str, Any],
    requirements: dict[str, Any],
    exemptions: dict[str, str],
    report: Report,
) -> None:
    per_operation: dict[str, list[dict[str, Any]]] = {}
    for case in cases["cases"]:
        rids = case.get("requirement_ids") or []
        if not rids:
            report.fail(f"API case {case['api_case_id']} has no requirement_ids")
        per_operation.setdefault(case["operation_id"], []).append(case)

    for endpoint in spec["endpoints"]:
        operation_id = endpoint["operation_id"]
        if endpoint.get("out_of_scope"):
            if not (endpoint.get("out_of_scope_reason") or "").strip():
                report.fail(f"endpoint {operation_id} is out_of_scope without a non-empty reason")
            continue  # out-of-scope endpoints carry no case demand
        kinds = {c["case_type"] for c in per_operation.get(operation_id, [])}
        if not (kinds & HappyKinds):
            report.fail(f"endpoint {operation_id} lacks a happy_path case")
        if not (kinds & NegativeKinds):
            report.fail(f"endpoint {operation_id} lacks a negative/edge case")

    cited: set[str] = set()
    for case in cases["cases"]:
        cited.update(case.get("requirement_ids") or [])
    for requirement in requirements["requirements"]:
        rid = requirement["requirement_id"]
        if exemptions.get(rid) == "not_testable":
            continue
        if rid not in cited:
            report.fail(f"requirement {rid} is not cited by any API case")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, help="iterations/<id> directory")
    args = parser.parse_args(argv)

    iteration_dir = args.iteration if args.iteration.is_absolute() else REPO_ROOT / args.iteration
    if not iteration_dir.is_dir():
        print(f"error: iteration directory {iteration_dir} not found", file=sys.stderr)
        return 1

    report = Report()
    try:
        spec = _load_validated(iteration_dir, "api/spec.normalized.yaml")
        cases = _load_validated(iteration_dir, "api/cases.yaml")
        requirements = _load_validated(iteration_dir, "requirements.yaml")
        exemptions = load_exemptions(iteration_dir)
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    check(spec, cases, requirements, exemptions, report)

    if report.problems:
        for problem in report.problems:
            print(f"api coverage gap: {problem}")
        print(f"check_api_coverage: {len(report.problems)} gap(s)", file=sys.stderr)
        return 1
    print("check_api_coverage: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
