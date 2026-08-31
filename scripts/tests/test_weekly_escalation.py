"""Roadmap 7.1：连续两次周回归失败的 issue 升级。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest  # pyright: ignore[reportMissingImports]
from conftest import _load_script


@pytest.fixture(scope="module")
def escalation() -> Any:
    return _load_script("weekly_escalation")


def test_previous_completed_schedule_failure_triggers(escalation: Any) -> None:
    runs = [
        {"id": 20, "event": "schedule", "status": "in_progress", "conclusion": None},
        {"id": 19, "event": "schedule", "status": "completed", "conclusion": "failure"},
    ]
    assert escalation.has_previous_failure(runs, current_run_id=20)


def test_previous_success_or_non_schedule_does_not_trigger(escalation: Any) -> None:
    runs = [
        {"id": 18, "event": "workflow_dispatch", "status": "completed", "conclusion": "failure"},
        {"id": 17, "event": "schedule", "status": "completed", "conclusion": "success"},
    ]
    assert not escalation.has_previous_failure(runs, current_run_id=20)


def test_open_tracking_issue_is_reused(escalation: Any) -> None:
    issues = [
        {"number": 7, "title": escalation.ISSUE_TITLE, "html_url": "https://example/7"},
    ]
    assert escalation.existing_issue(issues) == issues[0]


def test_schedule_workflow_wires_issue_escalation() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/trusted-notifications.yml").read_text(encoding="utf-8")
    regression = (root / ".github/workflows/regression.yml").read_text(encoding="utf-8")
    assert "issues: write" in workflow
    assert "github.event.workflow_run.event == 'schedule'" in workflow
    assert "scripts/weekly_escalation.py" in workflow
    assert "--classification failed" in workflow
    assert "ref: ${{ github.event_name == 'schedule' && 'release' || github.sha }}" in regression
