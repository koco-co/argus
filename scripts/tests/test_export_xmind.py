"""Roadmap 1.5 acceptance tests for scripts/export_xmind.py.

DoD: output opens/parses (zip→content.json) for a fixture with ≥2 modules;
structure asserts iteration→module→R→T→C→step; two runs produce identical
SHA-256; the `<Project>_v<N>_Cases.xmind` filename version increments and
never overwrites (GLOSSARY export-filename rule).
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

EXPORT_FIXTURES = FIXTURE_DIR / "export"


@pytest.fixture(scope="module")
def exporter() -> Any:
    return _load_script("export_xmind")


@pytest.fixture()
def iteration_dir(tmp_path: Path) -> Path:
    iteration_dir = tmp_path / "iterations" / "2026-08-export-demo"
    iteration_dir.mkdir(parents=True)
    for name in ("requirements.yaml", "test_points.yaml", "functional-cases.yaml"):
        shutil.copyfile(EXPORT_FIXTURES / name, iteration_dir / name)
    return iteration_dir


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_two_runs_identical_sha_and_version_increments(exporter: Any, iteration_dir: Path) -> None:
    first = exporter.export(iteration_dir)
    second = exporter.export(iteration_dir)
    third = exporter.export(iteration_dir)
    assert first.name == "argus_v1_Cases.xmind"
    assert second.name == "argus_v2_Cases.xmind"
    assert third.name == "argus_v3_Cases.xmind"
    assert _sha(first) == _sha(second) == _sha(third)


def test_zip_opens_and_content_json_parses(exporter: Any, iteration_dir: Path) -> None:
    destination = exporter.export(iteration_dir)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        sheets = json.loads(archive.read("content.json"))
    assert len(sheets) == 1
    assert sheets[0]["rootTopic"]["title"] == "2026-08-export-demo"


def test_structure_iteration_module_r_t_c_step(exporter: Any, iteration_dir: Path) -> None:
    destination = exporter.export(iteration_dir)
    sheet = exporter.verify_structure(destination)  # raises unless full chain holds
    root = sheet["rootTopic"]
    modules = root["children"]["attached"]
    assert {node["title"] for node in modules} == {"checkout", "orders"}

    checkout = next(node for node in modules if node["title"] == "checkout")
    requirements = checkout["children"]["attached"]
    assert [node["id"] for node in requirements] == ["req-R0001"]
    points = requirements[0]["children"]["attached"]
    assert {node["id"] for node in points} == {"point-T0001", "point-T0003"}
    # C0003 links T0001 and T0003 -> appears under each source path, same id
    under_t1 = next(node for node in points if node["id"] == "point-T0001")
    case_ids = {node["id"] for node in under_t1["children"]["attached"]}
    assert case_ids == {"case-C0001", "case-C0003"}
    under_t3 = next(node for node in points if node["id"] == "point-T0003")
    assert [node["id"] for node in under_t3["children"]["attached"]] == ["case-C0003"]
    steps = under_t3["children"]["attached"][0]["children"]["attached"]
    assert steps[0]["title"].startswith("Apply expired code")


def test_draft_cases_refuse_export(exporter: Any, iteration_dir: Path) -> None:
    cases = iteration_dir / "functional-cases.yaml"
    cases.write_text(
        cases.read_text(encoding="utf-8").replace("status: exported", "status: draft"),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="export requires"):
        exporter.export(iteration_dir)
    assert not (iteration_dir / "exports").exists()


def test_missing_test_points_source_refused(exporter: Any, iteration_dir: Path) -> None:
    (iteration_dir / "test_points.yaml").unlink()
    with pytest.raises(Exception, match="missing source"):
        exporter.export(iteration_dir)


def test_cli_entrypoint_writes_export(iteration_dir: Path) -> None:
    """Makefile 调用脚本时必须真正执行 main，而不是静默空跑。"""
    result = subprocess.run(
        [sys.executable, "scripts/export_xmind.py", str(iteration_dir)],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "export_xmind: wrote" in result.stdout
    assert list((iteration_dir / "exports").glob("*.xmind"))
