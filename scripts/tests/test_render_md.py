"""Roadmap 1.4 acceptance tests for scripts/render_md.py.

DoD: two runs are byte-identical (SHA-256 compared); golden output fixture
committed; sources are schema-gated through the registry before rendering.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES_DIR as FIXTURE_DIR
from conftest import _load_script

SCHEMA_FIXTURES = FIXTURE_DIR / "schemas"
GOLDEN_DIR = FIXTURE_DIR / "render"


@pytest.fixture(scope="module")
def render_md() -> Any:
    return _load_script("render_md")


def _setup_iteration(tmp_path: Path, name: str) -> Path:
    iteration_dir = tmp_path / "iterations" / "2026-08-render"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    source = iteration_dir / name
    fixture = {
        "requirements.yaml": "requirements--accepted.valid.yaml",
        "test_points.yaml": "test_points--accepted.valid.yaml",
    }[name]
    source.write_text((SCHEMA_FIXTURES / fixture).read_text(encoding="utf-8"))
    return iteration_dir


def test_two_runs_byte_identical(render_md: Any, tmp_path: Path) -> None:
    iteration_dir = _setup_iteration(tmp_path, "requirements.yaml")
    first = render_md.render_iteration(iteration_dir)
    output = first[0]
    sha_one = hashlib.sha256(output.read_bytes()).hexdigest()
    second = render_md.render_iteration(iteration_dir)
    sha_two = hashlib.sha256(second[0].read_bytes()).hexdigest()
    assert first == second == [iteration_dir / "requirement.md"]
    assert sha_one == sha_two


def test_golden_requirement_md_fixture(render_md: Any, tmp_path: Path) -> None:
    iteration_dir = _setup_iteration(tmp_path, "requirements.yaml")
    render_md.render_iteration(iteration_dir)
    rendered = (iteration_dir / "requirement.md").read_text(encoding="utf-8")
    golden = GOLDEN_DIR / "requirement.golden.md"
    if not golden.exists():  # first generation records the golden
        shutil.copyfile(iteration_dir / "requirement.md", golden)
    assert rendered == golden.read_text(encoding="utf-8"), (
        "rendered requirement.md drifted from the golden fixture — update "
        "the fixture only together with an intentional renderer change"
    )


def test_invalid_source_is_not_rendered(render_md: Any, tmp_path: Path) -> None:
    iteration_dir = _setup_iteration(tmp_path, "requirements.yaml")
    source = iteration_dir / "requirements.yaml"
    source.write_text("schema_version: '1.0'\nstatus: nonsense\n")
    with pytest.raises(Exception, match="failed"):
        render_md.render_iteration(iteration_dir)
    assert not (iteration_dir / "requirement.md").exists()


def test_missing_source_is_skipped(render_md: Any, tmp_path: Path) -> None:
    iteration_dir = tmp_path / "iterations" / "2026-08-render"
    iteration_dir.mkdir(parents=True)
    assert render_md.render_iteration(iteration_dir) == []
