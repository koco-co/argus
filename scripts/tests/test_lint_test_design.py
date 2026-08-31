"""统一测试设计 lint 的正反例回归。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest  # pyright: ignore[reportMissingImports]
import yaml
from conftest import _load_script

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_ITERATION = REPO_ROOT / "iterations/2026-08-medusa-ui-checkout"
API_ITERATION = REPO_ROOT / "iterations/2026-08-medusa-api-checkout"


@pytest.fixture(scope="module")
def linter() -> Any:
    return _load_script("lint_test_design")


def _copy_iteration(source: Path, tmp_path: Path) -> Path:
    destination = tmp_path / "iterations" / source.name
    shutil.copytree(source, destination)
    return destination


def test_canonical_designs_pass(linter: Any) -> None:
    assert linter.lint_iteration(UI_ITERATION) == []
    assert linter.lint_iteration(API_ITERATION) == []


def test_functional_lint_reports_stable_actionable_diagnostic(linter: Any, tmp_path: Path) -> None:
    iteration = _copy_iteration(UI_ITERATION, tmp_path)
    cases_path = iteration / "functional-cases.yaml"
    document = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    document["cases"][0]["tags"].append("module:orders")
    cases_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    diagnostics = linter.lint_iteration(iteration, "functional_cases")
    matching = [item for item in diagnostics if item.rule_id == "functional.module_tag_exactly_one"]
    assert matching
    item = matching[0]
    assert item.artifact.endswith("/functional-cases.yaml")
    assert item.location == "cases[0].tags"
    assert item.fix and "module" in item.fix


def test_api_lint_rejects_typed_assertion_drift(linter: Any, tmp_path: Path) -> None:
    iteration = _copy_iteration(API_ITERATION, tmp_path)
    cases_path = iteration / "api" / "cases.yaml"
    document = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    assertion = document["cases"][8]["expected_response"]["body_assertions"][0]
    assertion["expected"] = 123
    cases_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    diagnostics = linter.lint_iteration(iteration, "api_cases")
    assert any(item.rule_id == "api_cases.typed_assertion_mismatch" for item in diagnostics)


def test_api_lint_rejects_non_string_derived_reference_without_crashing(
    linter: Any, tmp_path: Path
) -> None:
    iteration = _copy_iteration(API_ITERATION, tmp_path)
    cases_path = iteration / "api" / "cases.yaml"
    document = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    expected = document["cases"][6]["expected_response"]
    expected["body_assertions"][0]["expected"] = {"oracle": "amount"}
    cases_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    diagnostics = linter.lint_iteration(iteration, "api_cases")
    rule_ids = {item.rule_id for item in diagnostics}
    assert "api_cases.derived_assertion_reference" in rule_ids
    assert "api_cases.unused_oracle" in rule_ids


def test_api_lint_rejects_derived_oracle_type_or_target_drift(linter: Any, tmp_path: Path) -> None:
    iteration = _copy_iteration(API_ITERATION, tmp_path)
    cases_path = iteration / "api" / "cases.yaml"
    document = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    expected = document["cases"][6]["expected_response"]
    expected["derived_oracles"] = [
        {
            "name": "amount",
            "target_path": "$.cart.other_total",
            "expression": "seeded_amount",
            "inputs": [{"name": "seeded_amount", "source": "seed", "path": "$.amount"}],
            "value_type": "integer",
        }
    ]
    expected["body_assertions"] = [
        {
            "path": "$.cart.total",
            "operator": "derived_equals",
            "value_type": "number",
            "expected": "amount",
        }
    ]
    cases_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    diagnostics = linter.lint_iteration(iteration, "api_cases")
    rule_ids = {item.rule_id for item in diagnostics}
    assert "api_cases.derived_type_mismatch" in rule_ids
    assert "api_cases.derived_target_mismatch" in rule_ids


@pytest.mark.parametrize(
    ("source", "stage", "relative"),
    [
        (UI_ITERATION, "requirements", "requirements.yaml"),
        (UI_ITERATION, "exemptions", "exemptions.yaml"),
        (UI_ITERATION, "test_points", "test_points.yaml"),
        (UI_ITERATION, "functional_cases", "functional-cases.yaml"),
        (API_ITERATION, "api_spec", "api/spec.normalized.yaml"),
        (API_ITERATION, "api_cases", "api/cases.yaml"),
    ],
)
def test_each_stage_requires_its_source_artifact(
    linter: Any, tmp_path: Path, source: Path, stage: str, relative: str
) -> None:
    iteration = _copy_iteration(source, tmp_path)
    (iteration / relative).unlink()

    diagnostics = linter.lint_iteration(iteration, stage)
    assert any(
        item.rule_id == "design.missing" and item.location == "<root>" for item in diagnostics
    )


def test_schema_failure_is_reported_before_semantic_guessing(linter: Any, tmp_path: Path) -> None:
    iteration = _copy_iteration(UI_ITERATION, tmp_path)
    cases_path = iteration / "functional-cases.yaml"
    document = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    document["cases"][0].pop("side_effect")
    cases_path.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    diagnostics = linter.lint_iteration(iteration, "functional_cases")
    assert any(item.rule_id == "schema.invalid" for item in diagnostics)
