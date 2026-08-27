"""Roadmap 1.8 acceptance tests for scripts/check_api_coverage.py.

DoD: endpoint missing negative/edge fails with the operation_id listed;
out_of_scope+reason passes; missing reason fails; every API case has
requirement_ids[]; every non-exempt requirement is covered.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import _load_script

SHA = "a" * 64


@pytest.fixture(scope="module")
def checker() -> Any:
    return _load_script("check_api_coverage")


def _endpoint(
    operation_id: str, out_of_scope: bool | None = None, reason: str | None = None
) -> dict:
    endpoint: dict = {
        "operation_id": operation_id,
        "path": f"/store/{operation_id}",
        "method": "GET",
        "module": "things",
        "parameters": [],
        "responses": [{"status_code": 200}],
    }
    if out_of_scope is not None:
        endpoint["out_of_scope"] = out_of_scope
    if reason is not None:
        endpoint["out_of_scope_reason"] = reason
    return endpoint


def _case(api_case_id: str, operation_id: str, case_type: str, rids: tuple[str, ...]) -> dict:
    return {
        "api_case_id": api_case_id,
        "requirement_ids": list(rids),
        "operation_id": operation_id,
        "endpoint": f"/store/{operation_id}",
        "method": "GET",
        "title": f"Case {api_case_id}",
        "case_type": case_type,
        "module": "things",
        "request": {},
        "expected_response": {"status_code": 200},
    }


def _spec(endpoints: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "iteration_id": "2026-08-api-cov",
        "status": "spec_valid",
        "service_name": "store",
        "generated_from": {
            "artifact": "iterations/2026-08-api-cov/00-raw/openapi.yaml",
            "sha256": SHA,
        },
        "endpoints": endpoints,
    }


def _cases(cases: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "iteration_id": "2026-08-api-cov",
        "status": "cases_valid",
        "generated_from": {
            "artifact": "iterations/2026-08-api-cov/api/spec.normalized.yaml",
            "sha256": SHA,
        },
        "cases": cases,
    }


def _requirements(rids: tuple[str, ...]) -> dict:
    return {
        "schema_version": "1.0",
        "iteration_id": "2026-08-api-cov",
        "status": "accepted",
        "generated_from": {"artifact": "iterations/2026-08-api-cov/00-raw/dump.md", "sha256": SHA},
        "requirements": [
            {"requirement_id": rid, "title": f"R {rid}", "description": f"Desc {rid}."}
            for rid in rids
        ],
    }


def _covered_everything() -> tuple[dict, dict, dict]:
    spec = _spec([_endpoint("listThings"), _endpoint("getThing")])
    cases = _cases(
        [
            _case("A0001", "listThings", "happy_path", ("R0001",)),
            _case("A0002", "listThings", "negative", ("R0001",)),
            _case("A0003", "getThing", "happy_path", ("R0001",)),
            _case("A0004", "getThing", "edge", ("R0002",)),
        ]
    )
    requirements = _requirements(("R0001", "R0002"))
    return spec, cases, requirements


def test_fully_covered_spec_passes(checker: Any) -> None:
    report = checker.Report()
    spec, cases, requirements = _covered_everything()
    checker.check(spec, cases, requirements, {}, report)
    assert report.problems == []


def test_missing_negative_case_lists_operation_id(checker: Any) -> None:
    report = checker.Report()
    spec, cases, requirements = _covered_everything()
    cases["cases"] = [c for c in cases["cases"] if c["api_case_id"] != "A0002"]
    checker.check(spec, cases, requirements, {}, report)
    assert any("listThings lacks a negative/edge case" in p for p in report.problems), (
        report.problems
    )


def test_missing_happy_case_lists_operation_id(checker: Any) -> None:
    report = checker.Report()
    spec, cases, requirements = _covered_everything()
    cases["cases"] = [c for c in cases["cases"] if c["case_type"] != "happy_path"]
    checker.check(spec, cases, requirements, {}, report)
    assert any("listThings lacks a happy_path case" in p for p in report.problems)
    assert any("getThing lacks a happy_path case" in p for p in report.problems)


def test_out_of_scope_with_reason_needs_no_cases(checker: Any) -> None:
    report = checker.Report()
    spec = _spec(
        [
            _endpoint("adminSync", out_of_scope=True, reason="Admin-only upstream sync."),
        ]
    )
    cases = _cases([])
    requirements = _requirements(())
    checker.check(spec, cases, requirements, {}, report)
    assert report.problems == []


def test_out_of_scope_without_reason_fails(checker: Any) -> None:
    report = checker.Report()
    spec = _spec([_endpoint("adminSync", out_of_scope=True)])
    checker.check(spec, _cases([]), _requirements(()), {}, report)
    assert any("out_of_scope without a non-empty reason" in p for p in report.problems)


def test_out_of_scope_omitted_entirely_is_legal(checker: Any) -> None:
    """Vacuous-conditional rule: no flag at all never demands a reason."""
    report = checker.Report()
    spec = _spec([_endpoint("listThings")])
    cases = _cases(
        [
            _case("A0001", "listThings", "happy_path", ("R0001",)),
            _case("A0002", "listThings", "edge", ("R0001",)),
        ]
    )
    requirements = _requirements(("R0001",))
    checker.check(spec, cases, requirements, {}, report)
    assert report.problems == []


def test_case_without_requirement_ids_fails(checker: Any) -> None:
    report = checker.Report()
    spec, cases, requirements = _covered_everything()
    cases["cases"][0]["requirement_ids"] = []
    checker.check(spec, cases, requirements, {}, report)
    assert any("A0001 has no requirement_ids" in p for p in report.problems)


def test_uncovered_requirement_fails_unless_not_testable_exempt(checker: Any) -> None:
    spec, cases, requirements = _covered_everything()
    requirements["requirements"].append(
        {"requirement_id": "R0003", "title": "R3", "description": "D3."}
    )
    report = checker.Report()
    checker.check(spec, cases, requirements, {}, report)
    assert any("R0003 is not cited by any API case" in p for p in report.problems)

    # manual_only does NOT remove the R->A demand (DATA_MODEL §2.1)
    report = checker.Report()
    checker.check(spec, cases, requirements, {"R0003": "manual_only"}, report)
    assert any("R0003 is not cited" in p for p in report.problems)

    # accepted not_testable removes it
    report = checker.Report()
    checker.check(spec, cases, requirements, {"R0003": "not_testable"}, report)
    assert report.problems == []
