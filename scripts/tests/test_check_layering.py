"""Roadmap 1.14 acceptance tests for scripts/check_layering.py.

DoD: forbidden-edge fixtures (automation->iterations, plugins->skills
internals, shared->scripts) each fail; clean skeleton passes; skills
process-rule grep is advisory-only.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
from conftest import _load_script


@pytest.fixture(scope="module")
def checker() -> Any:
    return _load_script("check_layering")


def _write(tmp_path: Path, rel: str, body: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _problems(checker: Any, path: Path) -> list[str]:
    report = checker.Report()
    checker.scan_python(path, report)
    return report.problems


def test_automation_to_iterations_import_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/tests/checkout/test_bad.py",
        "import iterations\n\ndef test_x():\n    pass\n",
    )
    problems = _problems(checker, path)
    assert any("automation -> iterations" in p for p in problems)


def test_plugins_to_skills_internals_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(tmp_path, "plugins/requirement-sources/conn.py", "import agents\n\nx = 1\n")
    problems = _problems(checker, path)
    assert any("plugins -> agents" in p for p in problems)


def test_shared_to_scripts_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "shared/utils/helper.py",
        "from scripts import helper\n\ndef x():\n    return helper\n",
    )
    problems = _problems(checker, path)
    assert any("shared -> scripts" in p for p in problems)


def test_automation_path_open_of_iterations_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "automation/web/pages/checkout/reader.py",
        'from pathlib import Path\n\nDATA = Path("iterations/2026-08-x/requirements.yaml")\n',
    )
    problems = _problems(checker, path)
    assert any("references iterations/ paths" in p for p in problems)


def test_shared_path_literal_of_iterations_fails(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "shared/assertions/db_asserts.py",
        'def load():\n    return open("iterations/2026-08-x/cases.yaml")\n',
    )
    problems = _problems(checker, path)
    assert any("references iterations/ paths" in p for p in problems)


def test_clean_skeleton_passes(checker: Any, tmp_path: Path) -> None:
    files = {
        "plugins/requirement-sources/conn.py": (
            "import httpx\n\ndef fetch():\n    return httpx.get\n"
        ),
        "shared/utils/helper.py": ("import yaml\n\ndef dump(x):\n    return yaml.safe_dump(x)\n"),
        "automation/web/pages/checkout/checkout_page.py": (
            "from shared.config import settings\n\n\nclass CheckoutPage:\n    pass\n"
        ),
        "automation/conftest.py": "import pytest\n",
        "scripts/check_example.py": ("from _registry_lib import REPO_ROOT\n\nROOT = REPO_ROOT\n"),
    }
    for rel, body in files.items():
        _write(tmp_path, rel, body)
    report = checker.Report()
    for rel in files:
        checker.scan_python(tmp_path / rel, report)
    assert report.problems == []


def test_relative_import_within_layer_passes(checker: Any, tmp_path: Path) -> None:
    path = _write(
        tmp_path, "shared/notify/dispatcher.py", "from .base import Notifier\n\nx = Notifier\n"
    )
    assert _problems(checker, path) == []


def test_skills_advisory_is_warning_only(checker: Any, tmp_path: Path, capsys: Any) -> None:
    skills = tmp_path / ".agents" / "skills" / "demo"
    skills.mkdir(parents=True, exist_ok=True)
    (skills / "SKILL.md").write_text(
        "use: import playwright\nthen drive the browser directly\n", encoding="utf-8"
    )
    checker.check_skills_advisory(skills, report := checker.Report())
    assert len(report.warnings) == 1
    assert report.problems == []
