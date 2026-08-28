"""Roadmap 1.18 acceptance tests for scripts/check_orphan_tests.py.

DoD: orphan fixture (well-formed markers, unknown case) fails naming the
nodeid; properly referenced fixture passes; allowlisted harness smoke passes.
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
    return _load_script("check_orphan_tests")


def _test_body() -> str:
    return (
        "import pytest\n"
        "\n"
        '@pytest.mark.module("checkout")\n'
        '@pytest.mark.case_id("C0001")\n'
        '@pytest.mark.iteration("2026-08-orphan")\n'
        "def test_checkout_flow():\n    assert True\n"
    )


def _iteration_dir(tmp_path: Path, with_traceability: bool) -> Path:
    root = tmp_path / "iterations" / "2026-08-orphan"
    (root / "api").mkdir(parents=True, exist_ok=True)
    cases = {
        "schema_version": "1.0",
        "iteration_id": "2026-08-orphan",
        "status": "exported",
        "generated_from": {
            "artifact": "iterations/2026-08-orphan/test_points.yaml",
            "sha256": SHA,
        },
        "cases": [
            {
                "case_id": "C0001",
                "title": "Sample case",
                "priority": 1,
                "precondition": "none",
                "steps": [{"action": "Do it.", "expected": "Works.", "expected_kind": "ui_state"}],
                "tags": ["module:checkout"],
                "test_point_ids": ["T0001"],
            }
        ],
    }
    (root / "functional-cases.yaml").write_text(
        yaml.safe_dump(cases, sort_keys=False), encoding="utf-8"
    )
    if with_traceability:
        trace = {
            "schema_version": "1.0",
            "iteration_id": "2026-08-orphan",
            "links": [
                {
                    "requirement_id": "R0001",
                    "test_point_id": "T0001",
                    "functional_case_id": "C0001",
                    "automation_test_ids": [
                        "automation/web/tests/checkout/test_referenced.py::test_checkout_flow"
                    ],
                }
            ],
        }
        (root / "traceability.yaml").write_text(
            yaml.safe_dump(trace, sort_keys=False), encoding="utf-8"
        )
    return root


def _automation_tree(tmp_path: Path, nodeid: str) -> Path:
    file_part, _, _func = nodeid.rpartition("::")
    path = tmp_path / file_part
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_test_body(), encoding="utf-8")
    return tmp_path / "automation"


def test_properly_referenced_test_passes(checker: Any, tmp_path: Path) -> None:
    _iteration_dir(tmp_path, with_traceability=True)
    automation = _automation_tree(
        tmp_path, "automation/web/tests/checkout/test_referenced.py::test_checkout_flow"
    )
    assert (
        checker.main(
            [
                "--automation-dir",
                str(automation),
                "--iterations-dir",
                str(tmp_path / "iterations"),
            ]
        )
        == 0
    )


def test_orphan_test_without_traceability_fails_naming_nodeid(checker: Any, tmp_path: Path) -> None:
    _iteration_dir(tmp_path, with_traceability=False)
    automation = _automation_tree(
        tmp_path, "automation/web/tests/checkout/test_referenced.py::test_checkout_flow"
    )
    assert (
        checker.main(
            [
                "--automation-dir",
                str(automation),
                "--iterations-dir",
                str(tmp_path / "iterations"),
            ]
        )
        == 1
    )


def test_orphan_test_with_unknown_case_fails(checker: Any, tmp_path: Path) -> None:
    body = _test_body().replace("C0001", "C9999")
    file_part = "automation/web/tests/checkout/test_unknown.py"
    path = tmp_path / file_part
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    _iteration_dir(tmp_path, with_traceability=True)
    assert (
        checker.main(
            [
                "--automation-dir",
                str(tmp_path / "automation"),
                "--iterations-dir",
                str(tmp_path / "iterations"),
            ]
        )
        == 1
    )


def test_allowlisted_harness_smoke_passes(
    checker: Any, tmp_path: Path, allowlist_file: Path
) -> None:
    harness = tmp_path / "automation" / "web" / "tests" / "harness"
    harness.mkdir(parents=True, exist_ok=True)
    (harness / "test_harness_smoke.py").write_text(
        "def test_smoke():\n    assert True\n",
        encoding="utf-8",  # no markers at all
    )
    _iteration_dir(tmp_path, with_traceability=True)
    assert (
        checker.main(
            [
                "--automation-dir",
                str(tmp_path / "automation"),
                "--iterations-dir",
                str(tmp_path / "iterations"),
                "--allowlist",
                str(allowlist_file),
            ]
        )
        == 0
    )


@pytest.fixture()
def allowlist_file(tmp_path: Path) -> Path:
    path = tmp_path / "orphan-allowlist.yaml"
    path.write_text(
        yaml.safe_dump({"exempt": ["automation/**/tests/harness/**"]}, sort_keys=False),
        encoding="utf-8",
    )
    return path
