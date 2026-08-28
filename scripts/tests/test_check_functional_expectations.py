"""Roadmap 1.15a acceptance tests for scripts/check_functional_expectations.py.

DoD: valid seed-derived fixture passes; literal-oracle fixture fails;
hallucinated seed name fails against a populated registry fixture;
module-tag-uniqueness violation fails; registry-absent advisory vs
--enforce-seeds hard gate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import _load_script

SHA = "a" * 64


@pytest.fixture(scope="module")
def checker() -> Any:
    return _load_script("check_functional_expectations")


def _case(case_id: str, module_tags: list[str], steps: list[dict]) -> dict:
    return {
        "case_id": case_id,
        "title": f"Case {case_id}",
        "priority": 1,
        "precondition": "none",
        "steps": steps,
        "tags": module_tags,
        "test_point_ids": ["T0001"],
    }


def _derived_step(expected: str, seed: str = "product_price_usd") -> dict:
    return {
        "action": "Read the order total.",
        "expected": expected,
        "expected_kind": "derived_value",
        "derived_from": {"seed": seed, "rule": "price * 0.9 rounded to cents"},
    }


def _cases_document(cases: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "iteration_id": "2026-08-exp",
        "status": "exported",
        "generated_from": {
            "artifact": "iterations/2026-08-exp/test_points.yaml",
            "sha256": SHA,
        },
        "cases": cases,
    }


def _seeded_registry() -> dict:
    return {
        "schema_version": "1.0",
        "target_app": "medusa",
        "seeds": {
            "product_price_usd": {"type": "money", "value": "150.00"},
            "discount_code": {"type": "code", "value": "QA-DISCOUNT"},
        },
    }


def _write_cases(tmp_path: Path, cases: list[dict]) -> Path:
    root = tmp_path / "iterations" / "2026-08-exp"
    root.mkdir(parents=True, exist_ok=True)
    (root / "functional-cases.yaml").write_text(
        yaml.safe_dump(_cases_document(cases), sort_keys=False), encoding="utf-8"
    )
    return root


def _registry(tmp_path: Path) -> Path:
    path = tmp_path / "shared" / "testdata" / "seed-registry.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(_seeded_registry(), sort_keys=False), encoding="utf-8")
    return path


def test_valid_seed_derived_fixture_passes(checker: Any, tmp_path: Path) -> None:
    root = _write_cases(
        tmp_path,
        [
            _case(
                "C0001",
                ["module:checkout"],
                [
                    {
                        "action": "Apply discount and read total.",
                        "expected": "Total equals the seeded price minus the seeded discount.",
                        "expected_kind": "derived_value",
                        "derived_from": {
                            "seed": "product_price_usd",
                            "rule": "price - seeded discount amount",
                        },
                    },
                ],
            ),
        ],
    )
    registry = _registry(tmp_path)
    assert checker.main([str(root), "--registry", str(registry)]) == 0


def test_registry_absent_is_advisory_only(checker: Any, tmp_path: Path, capsys: Any) -> None:
    root = _write_cases(
        tmp_path,
        [
            _case(
                "C0001",
                ["module:checkout"],
                [
                    _derived_step("Total equals seeded price minus ten percent."),
                ],
            ),
        ],
    )
    missing_registry = tmp_path / "missing-seed-registry.yaml"
    assert checker.main([str(root), "--registry", str(missing_registry)]) == 0
    captured = capsys.readouterr()
    assert "seed registry absent" in captured.err


def test_enforce_seeds_makes_missing_registry_hard(checker: Any, tmp_path: Path) -> None:
    root = _write_cases(
        tmp_path,
        [
            _case(
                "C0001",
                ["module:checkout"],
                [
                    _derived_step("Total equals seeded price minus ten percent."),
                ],
            ),
        ],
    )
    missing_registry = tmp_path / "missing-seed-registry.yaml"
    assert (
        checker.main(
            [
                str(root),
                "--enforce-seeds",
                "--registry",
                str(missing_registry),
            ]
        )
        == 1
    )


def test_literal_oracle_currency_fails(checker: Any, tmp_path: Path) -> None:
    root = _write_cases(
        tmp_path,
        [
            _case(
                "C0001",
                ["module:checkout"],
                [
                    _derived_step("Total equals $150.00"),
                ],
            ),
        ],
    )
    registry = _registry(tmp_path)
    assert checker.main([str(root), "--registry", str(registry)]) == 1


def test_money_shaped_literal_fails(checker: Any, tmp_path: Path) -> None:
    root = _write_cases(
        tmp_path,
        [
            _case(
                "C0001",
                ["module:checkout"],
                [
                    _derived_step("Total equals 150.00 USD"),
                ],
            ),
        ],
    )
    registry = _registry(tmp_path)
    assert checker.main([str(root), "--registry", str(registry)]) == 1


def test_relationship_wording_passes(checker: Any, tmp_path: Path) -> None:
    root = _write_cases(
        tmp_path,
        [
            _case(
                "C0001",
                ["module:checkout"],
                [
                    _derived_step("Total equals seeded price minus 10 percent, rounded to cents."),
                ],
            ),
        ],
    )
    registry = _registry(tmp_path)
    assert checker.main([str(root), "--registry", str(registry)]) == 0


def test_hallucinated_seed_fails_against_populated_registry(checker: Any, tmp_path: Path) -> None:
    root = _write_cases(
        tmp_path,
        [
            _case(
                "C0001",
                ["module:checkout"],
                [
                    _derived_step(
                        "Total equals seeded price minus ten percent.",
                        seed="hallucinated_price_seed",
                    ),
                ],
            ),
        ],
    )
    registry = _registry(tmp_path)
    assert checker.main([str(root), "--registry", str(registry)]) == 1


def test_module_tag_uniqueness_violation_fails(checker: Any, tmp_path: Path) -> None:
    root = _write_cases(
        tmp_path,
        [
            _case(
                "C0001",
                ["module:checkout", "module:orders"],
                [
                    {
                        "action": "Do it.",
                        "expected": "It works.",
                        "expected_kind": "ui_state",
                    },
                ],
            ),
        ],
    )
    assert checker.main([str(root)]) == 1
