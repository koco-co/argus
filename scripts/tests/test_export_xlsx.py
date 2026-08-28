"""Roadmap 1.6 acceptance tests for scripts/export_xlsx.py.

DoD: openpyxl round-trip asserts the API export columns
(api_case_id/module/operation_id/method/endpoint/case_type/title/request.* /
expected_response.*) and populated values; two runs produce identical bytes.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES_DIR as FIXTURE_DIR
from conftest import _load_script

SCHEMA_FIXTURES = FIXTURE_DIR / "schemas"


@pytest.fixture(scope="module")
def exporter() -> Any:
    return _load_script("export_xlsx")


@pytest.fixture()
def iteration_dir(tmp_path: Path) -> Path:
    iteration_dir = tmp_path / "iterations" / "2026-08-xlsx-demo"
    api_dir = iteration_dir / "api"
    api_dir.mkdir(parents=True)
    shutil.copyfile(SCHEMA_FIXTURES / "api_cases--cases-valid.valid.yaml", api_dir / "cases.yaml")
    return iteration_dir


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_two_runs_identical_bytes_and_version_increments(
    exporter: Any, iteration_dir: Path
) -> None:
    first = exporter.export(iteration_dir)
    second = exporter.export(iteration_dir)
    assert first.name == "argus_v1_API_Cases.xlsx"
    assert second.name == "argus_v2_API_Cases.xlsx"
    assert _sha(first) == _sha(second)


def test_core_properties_modified_timestamp_is_pinned(exporter: Any, iteration_dir: Path) -> None:
    """openpyxl 保存时会重写 modified，导出器必须在 ZIP 层再次固定。"""
    destination = exporter.export(iteration_dir)
    with zipfile.ZipFile(destination) as archive:
        core = archive.read("docProps/core.xml").decode("utf-8")
    assert "<dcterms:modified" in core
    assert ">1980-01-01T00:00:00Z</dcterms:modified>" in core


def test_round_trip_columns_and_populated_values(exporter: Any, iteration_dir: Path) -> None:
    destination = exporter.export(iteration_dir)
    header, rows = exporter.round_trip(destination)
    assert header == exporter.COLUMNS
    assert len(rows) == 2  # A0001 + A0002, sorted by api_case_id

    first = rows[0]
    by_column = dict(zip(exporter.COLUMNS, first, strict=True))
    assert by_column["api_case_id"] == "A0001"
    assert by_column["module"] == "orders"
    assert by_column["operation_id"] == "getOrder"
    assert by_column["method"] == "GET"
    assert by_column["endpoint"] == "/store/orders/{id}"
    assert by_column["case_type"] == "happy_path"
    assert by_column["title"] == "Fetch seeded order returns 200"
    assert json.loads(by_column["request.path_params"]) == {"id": "{{order_id}}"}
    assert json.loads(by_column["request.variables"]) == [
        {"name": "order_id", "source": "seed", "expression": "seeded_order_id"}
    ]
    assert by_column["expected_response.status_code"] == "200"

    negative = rows[1]
    by_column = dict(zip(exporter.COLUMNS, negative, strict=True))
    assert by_column["api_case_id"] == "A0002"
    assert by_column["case_type"] == "negative"
    assert by_column["request.path_params"] in ("", None)  # empty cell reads back falsy


def test_draft_cases_refuse_export(exporter: Any, iteration_dir: Path) -> None:
    cases = iteration_dir / "api" / "cases.yaml"
    cases.write_text(
        cases.read_text(encoding="utf-8").replace("status: cases_valid", "status: cases_draft"),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="export requires"):
        exporter.export(iteration_dir)
    assert not (iteration_dir / "exports").exists()


def test_missing_source_refused(exporter: Any, tmp_path: Path) -> None:
    iteration_dir = tmp_path / "iterations" / "2026-08-empty"
    iteration_dir.mkdir(parents=True)
    with pytest.raises(Exception, match="missing source"):
        exporter.export(iteration_dir)


def test_cli_entrypoint_writes_export(iteration_dir: Path) -> None:
    """Makefile 调用脚本时必须真正执行 main，而不是静默空跑。"""
    result = subprocess.run(
        [sys.executable, "scripts/export_xlsx.py", str(iteration_dir)],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "export_xlsx: wrote" in result.stdout
    assert list((iteration_dir / "exports").glob("*.xlsx"))
