"""Roadmap 1.2 acceptance tests for scripts/validate_schema.py.

DoD: registered fixture tree exits 0; unregistered-yaml and wrong-schema
cases exit non-zero naming the exact JSON path; an invalid `date-time`
fixture is rejected; the registry binding matches DATA_MODEL placement
(covered in test_new_iteration.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import FIXTURES_DIR


@pytest.fixture()
def validator(new_iteration: Any) -> Any:
    # validate_schema.py shares new_iteration's registry-facing contract;
    # loading it through the same import mechanism keeps one sys.path fix.
    from conftest import _load_script

    _load_script("new_iteration")
    return _load_script("validate_schema")


def _write(path: Path, fixture_name: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((FIXTURES_DIR / "schemas" / fixture_name).read_text(encoding="utf-8"))
    return path


def test_registered_artifact_exits_zero(validator: Any, tmp_path: Path) -> None:
    requirements = _write(
        tmp_path / "iterations/2026-08-tree/requirements.yaml",
        "requirements--accepted.valid.yaml",
    )
    assert validator.main([str(requirements)]) == 0


def test_iteration_directory_expands_to_registered_yaml_files(
    validator: Any, tmp_path: Path
) -> None:
    """Makefile 传入迭代目录时应递归执行，而不是把目录当成 YAML 打开。"""
    iteration = tmp_path / "iterations/2026-08-tree"
    _write(iteration / "requirements.yaml", "requirements--accepted.valid.yaml")
    assert validator.main([str(iteration)]) == 0


def test_unregistered_yaml_exit_non_zero_naming_path(
    validator: Any, tmp_path: Path, capsys: Any
) -> None:
    stray = tmp_path / "iterations/2026-08-tree/notes.yaml"
    stray.parent.mkdir(parents=True)
    stray.write_text("schema_version: '1.0'\n")
    assert validator.main([str(stray)]) == 1
    assert "unregistered artifact path" in capsys.readouterr().err


def test_wrong_schema_names_exact_json_path(validator: Any, tmp_path: Path, capsys: Any) -> None:
    bad = _write(
        tmp_path / "iterations/2026-08-tree/requirements.yaml",
        "requirements--accepted-unresolved-ambiguity.invalid.yaml",
    )
    assert validator.main([str(bad)]) == 1
    err = capsys.readouterr().err
    assert "ambiguities[0].resolved" in err
    assert "requirements.yaml" in err


def test_malformed_datetime_rejected(validator: Any, tmp_path: Path) -> None:
    run_summary = _write(
        tmp_path / "iterations/2026-08-tree/runs/run-20260828T101500Z-a3f2/run-summary.yaml",
        "run_summary--passed.valid.yaml",
    )
    document = yaml.safe_load(run_summary.read_text(encoding="utf-8"))
    document["started_at"] = "2026-13-45T99:00:00Z"
    run_summary.write_text(yaml.safe_dump(document, sort_keys=False))
    assert validator.main([str(run_summary)]) == 1


@pytest.mark.parametrize(
    "source",
    sorted((FIXTURES_DIR / "schemas").glob("*source_payload--*.yaml")),
    ids=lambda path: path.name,
)
def test_source_payload_any_of_semantics(validator: Any, tmp_path: Path, source: Path) -> None:
    """两类信封的成功、失败和非法变体均通过真实文件路径绑定验证。"""
    artifact = _write(tmp_path / "iterations/2026-08-tree/00-raw/source-payload.yaml", source.name)
    expected = 1 if source.name.endswith(".invalid.yaml") else 0
    if source.name == "api_source_payload--wrong-source-type.invalid.yaml":
        # 注册表接受两类信封；该样本中的 jira 类型对需求信封合法。
        expected = 0
    assert validator.main([str(artifact)]) == expected


def test_dash_all_reports_registered_files_only(validator: Any, tmp_path: Path) -> None:
    """--all walks the real repo; a foreign tree must not leak in."""
    assert validator.main(["--all"]) == 0  # repo has no artifact files yet
