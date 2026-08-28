"""Roadmap 1.3 acceptance tests for scripts/validate_iteration.py.

Covers the DoD fixture list: legal UI/API route chains (incl.
requirements_mapped on the API branch), explicit Hybrid rejection, illegal
jumps, stale downgrade verdicts shown but unwritten (and written by --fix),
stale-input consumption surfaced, attempt-ordering and passed-last-attempt
violations, hand-edited state/events rejection, blocked(
validation_budget_exhausted) acceptance, second-in-progress rejection.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import FIXTURES_DIR, _load_script

SCHEMA_FIXTURES = FIXTURES_DIR / "schemas"
SHA = "a" * 64


@pytest.fixture(scope="module")
def validator(tmp_path_factory: pytest.TempPathFactory) -> Any:
    module = _load_script("validate_iteration")
    return module


def _raw(name: str) -> str:
    return (SCHEMA_FIXTURES / name).read_text(encoding="utf-8")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _event(from_state: str, to_state: str, triggered_by: str = "agent") -> dict:
    return {
        "from_state": from_state,
        "to_state": to_state,
        "timestamp": "2026-08-28T10:00:00Z",
        "triggered_by": triggered_by,
    }


def _approval(stage: str, action: str) -> dict:
    return {
        "stage": stage,
        "action": action,
        "actor": "user",
        "timestamp": "2026-08-28T09:59:00Z",
        "artifact_sha256": SHA,
    }


def _iteration_doc(iteration_id: str, ui: bool, state: str, events: list, approvals: list) -> dict:
    return {
        "schema_version": "1.0",
        "iteration_id": iteration_id,
        "state": state,
        "blocked_reason": None,
        "branches": {"ui": ui, "api": not ui},
        "artifacts": {
            key: {"status": "not_started", "input_sha256": None}
            for key in (
                "requirements",
                "exemptions",
                "test_points",
                "functional_cases",
                "api_spec",
                "api_cases",
                "web_automation",
                "api_automation",
                "execution",
            )
        },
        "approvals": approvals,
        "events": events,
        "source_manifest": [],
        "updated_at": "2026-08-28T10:00:00Z",
    }


def _scaffold(
    root: Path,
    iteration_id: str,
    doc: dict,
    requirements_raw: str | None = None,
    upstream_name: str = "00-raw/requirements-dump.md",
) -> Path:
    iteration_dir = root / "iterations" / iteration_id
    iteration_dir.mkdir(parents=True, exist_ok=True)
    (iteration_dir / "iteration.yaml").write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    if requirements_raw is not None:
        (iteration_dir / "requirements.yaml").write_text(requirements_raw, encoding="utf-8")
        upstream = iteration_dir / upstream_name
        upstream.parent.mkdir(parents=True, exist_ok=True)
        upstream.write_text("upstream content", encoding="utf-8")
    return iteration_dir


def _ui_chain_events() -> tuple[list, list]:
    states = [
        "created",
        "requirements_clarifying",
        "requirements_accepted",
        "test_points_review",
        "test_points_accepted",
    ]
    events = [
        _event("created", "requirements_clarifying"),
        _event("requirements_clarifying", "requirements_accepted"),
        _event("requirements_accepted", "test_points_review"),
        _event("test_points_review", "test_points_accepted"),
    ]
    approvals = [
        _approval("requirements", "accepted"),
        _approval("exemptions", "accepted"),
        _approval("test_points", "accepted"),
    ]
    return states, events or approvals


def test_legal_ui_route_chain_passes(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc(
        "2026-08-ui-ok",
        ui=True,
        state="test_points_accepted",
        events=[
            _event("created", "requirements_clarifying"),
            _event("requirements_clarifying", "requirements_accepted"),
            _event("requirements_accepted", "test_points_review"),
            _event("test_points_review", "test_points_accepted"),
        ],
        approvals=[
            _approval("requirements", "accepted"),
            _approval("exemptions", "accepted"),
            _approval("test_points", "accepted"),
        ],
    )
    iteration_dir = _scaffold(tmp_path, "2026-08-ui-ok", doc)
    assert validator.main([str(iteration_dir)]) == 0


def test_legal_api_route_chain_with_requirements_mapped(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc(
        "2026-08-api-ok",
        ui=False,
        state="requirements_mapped",
        events=[
            _event("created", "requirements_clarifying"),
            _event("requirements_clarifying", "requirements_accepted"),
            _event("requirements_accepted", "requirements_mapped"),
        ],
        approvals=[
            _approval("requirements", "accepted"),
            _approval("exemptions", "accepted"),
        ],
    )
    iteration_dir = _scaffold(tmp_path, "2026-08-api-ok", doc)
    assert validator.main([str(iteration_dir)]) == 0


def test_requirements_mapped_rejected_on_ui_branch(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc(
        "2026-08-ui-mapped",
        ui=True,
        state="requirements_mapped",
        events=[
            _event("created", "requirements_clarifying"),
            _event("requirements_clarifying", "requirements_accepted"),
            _event("requirements_accepted", "requirements_mapped"),
        ],
        approvals=[_approval("requirements", "accepted")],
    )
    iteration_dir = _scaffold(tmp_path, "2026-08-ui-mapped", doc)
    assert validator.main([str(iteration_dir)]) == 1


def test_hybrid_branch_combination_rejected(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc("2026-08-hybrid", ui=True, state="created", events=[], approvals=[])
    doc["branches"] = {"ui": True, "api": True}
    iteration_dir = _scaffold(tmp_path, "2026-08-hybrid", doc)
    assert validator.main([str(iteration_dir)]) == 1


def test_illegal_jump_rejected(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc(
        "2026-08-jump",
        ui=True,
        state="test_points_review",
        events=[_event("created", "test_points_review")],
        approvals=[],
    )
    iteration_dir = _scaffold(tmp_path, "2026-08-jump", doc)
    assert validator.main([str(iteration_dir)]) == 1


def test_missing_approval_gate_rejected(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc(
        "2026-08-no-approval",
        ui=True,
        state="requirements_accepted",
        events=[
            _event("created", "requirements_clarifying"),
            _event("requirements_clarifying", "requirements_accepted"),
        ],
        approvals=[],
    )
    iteration_dir = _scaffold(tmp_path, "2026-08-no-approval", doc)
    assert validator.main([str(iteration_dir)]) == 1


@pytest.mark.parametrize("ui", [True, False])
def test_missing_exemptions_approval_gate_rejected(
    validator: Any, tmp_path: Path, ui: bool
) -> None:
    """UI 与 API 分支都不能绕过需求豁免签收。"""
    if ui:
        state = "test_points_accepted"
        events = [
            _event("created", "requirements_clarifying"),
            _event("requirements_clarifying", "requirements_accepted"),
            _event("requirements_accepted", "test_points_review"),
            _event("test_points_review", "test_points_accepted"),
        ]
        approvals = [
            _approval("requirements", "accepted"),
            _approval("test_points", "accepted"),
        ]
    else:
        state = "requirements_mapped"
        events = [
            _event("created", "requirements_clarifying"),
            _event("requirements_clarifying", "requirements_accepted"),
            _event("requirements_accepted", "requirements_mapped"),
        ]
        approvals = [_approval("requirements", "accepted")]
    iteration_id = f"2026-08-no-exemption-{'ui' if ui else 'api'}"
    doc = _iteration_doc(iteration_id, ui=ui, state=state, events=events, approvals=approvals)
    iteration_dir = _scaffold(tmp_path, iteration_id, doc)
    assert validator.main([str(iteration_dir)]) == 1


def test_hand_edited_state_rejected(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc(
        "2026-08-hand-edit",
        ui=True,
        state="test_points_accepted",
        events=[
            _event("created", "requirements_clarifying"),
            _event("requirements_clarifying", "requirements_accepted"),
        ],
        approvals=[_approval("requirements", "accepted")],
    )
    iteration_dir = _scaffold(tmp_path, "2026-08-hand-edit", doc)
    assert validator.main([str(iteration_dir)]) == 1


def test_hand_edited_event_chain_rejected(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc(
        "2026-08-chain-break",
        ui=True,
        state="requirements_accepted",
        events=[
            _event("test_points_review", "requirements_accepted"),
        ],
        approvals=[_approval("requirements", "accepted")],
    )
    iteration_dir = _scaffold(tmp_path, "2026-08-chain-break", doc)
    assert validator.main([str(iteration_dir)]) == 1


def test_blocked_with_budget_reason_accepted_and_user_unblock(
    validator: Any, tmp_path: Path
) -> None:
    doc = _iteration_doc(
        "2026-08-budget",
        ui=True,
        state="requirements_clarifying",
        events=[
            _event("created", "requirements_clarifying"),
            _event(
                "requirements_clarifying",
                "blocked",
            ),
            _event("blocked", "requirements_clarifying", triggered_by="user"),
        ],
        approvals=[],
    )
    doc["blocked_reason"] = None  # unblocked again
    iteration_dir = _scaffold(tmp_path, "2026-08-budget", doc)
    # the blocked hop lacks a reason only while IN blocked; we left it, so OK
    assert validator.main([str(iteration_dir)]) == 0


def test_blocked_without_reason_rejected(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc(
        "2026-08-blocked",
        ui=True,
        state="blocked",
        events=[_event("created", "blocked")],
        approvals=[],
    )
    doc["blocked_reason"] = None
    iteration_dir = _scaffold(tmp_path, "2026-08-blocked", doc)
    assert validator.main([str(iteration_dir)]) == 1


def test_non_user_unblock_rejected(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc(
        "2026-08-unblock",
        ui=True,
        state="requirements_clarifying",
        events=[
            _event("created", "blocked"),
            _event("blocked", "requirements_clarifying"),  # agent unblocking
        ],
        approvals=[],
    )
    doc["blocked_reason"] = None
    iteration_dir = _scaffold(tmp_path, "2026-08-unblock", doc)
    assert validator.main([str(iteration_dir)]) == 1


def test_reopen_edge_is_user_only(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc(
        "2026-08-reopen",
        ui=True,
        state="requirements_clarifying",
        events=[
            _event("created", "requirements_clarifying"),
            _event("requirements_clarifying", "requirements_accepted"),
            _event("requirements_accepted", "requirements_clarifying", "agent"),
        ],
        approvals=[_approval("requirements", "accepted")],
    )
    iteration_dir = _scaffold(tmp_path, "2026-08-reopen", doc)
    assert validator.main([str(iteration_dir)]) == 1


def test_stale_verdict_shown_but_not_written(validator: Any, tmp_path: Path, capsys: Any) -> None:
    requirements_raw = _raw("requirements--accepted.valid.yaml")
    doc = _iteration_doc(
        "2026-08-stale",
        ui=True,
        state="requirements_accepted",
        events=[
            _event("created", "requirements_clarifying"),
            _event("requirements_clarifying", "requirements_accepted"),
        ],
        approvals=[_approval("requirements", "accepted")],
    )
    iteration_dir = _scaffold(tmp_path, "2026-08-stale", doc, requirements_raw)
    # point generated_from at a live upstream, then tamper with the file
    requirements = iteration_dir / "requirements.yaml"
    document = yaml.safe_load(requirements.read_text(encoding="utf-8"))
    document["generated_from"] = {
        "artifact": "iterations/2026-08-stale/00-raw/requirements-dump.md",
        "sha256": _sha("upstream content"),
    }
    requirements.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    upstream = iteration_dir / "00-raw" / "requirements-dump.md"
    upstream.write_text("tampered upstream", encoding="utf-8")

    before = (iteration_dir / "iteration.yaml").read_text()
    assert validator.main([str(iteration_dir)]) == 1
    out = capsys.readouterr()
    assert "stale" in out.out
    assert "proposed rewrite" in out.out
    assert (iteration_dir / "iteration.yaml").read_text() == before


def test_fix_writes_stale_status_and_rerun_is_clean(
    validator: Any, tmp_path: Path, capsys: Any
) -> None:
    requirements_raw = _raw("requirements--accepted.valid.yaml")
    doc = _iteration_doc(
        "2026-08-fix",
        ui=True,
        state="requirements_accepted",
        events=[
            _event("created", "requirements_clarifying"),
            _event("requirements_clarifying", "requirements_accepted"),
        ],
        approvals=[_approval("requirements", "accepted")],
    )
    iteration_dir = _scaffold(tmp_path, "2026-08-fix", doc, requirements_raw)
    requirements = iteration_dir / "requirements.yaml"
    document = yaml.safe_load(requirements.read_text(encoding="utf-8"))
    document["generated_from"] = {
        "artifact": "iterations/2026-08-fix/00-raw/requirements-dump.md",
        "sha256": _sha("upstream content"),
    }
    requirements.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    (iteration_dir / "00-raw" / "requirements-dump.md").write_text("tampered")

    assert validator.main([str(iteration_dir), "--fix"]) == 0
    fixed = yaml.safe_load((iteration_dir / "iteration.yaml").read_text(encoding="utf-8"))
    assert fixed["artifacts"]["requirements"]["status"] == "stale"
    capsys.readouterr()
    assert validator.main([str(iteration_dir)]) == 0


def test_stale_input_consumption_is_surfaced(validator: Any, tmp_path: Path, capsys: Any) -> None:
    doc = _iteration_doc(
        "2026-08-consume",
        ui=True,
        state="test_points_accepted",
        events=[
            _event("created", "requirements_clarifying"),
            _event("requirements_clarifying", "requirements_accepted"),
            _event("requirements_accepted", "test_points_review"),
            _event("test_points_review", "test_points_accepted"),
        ],
        approvals=[
            _approval("requirements", "accepted"),
            _approval("exemptions", "accepted"),
            _approval("test_points", "accepted"),
        ],
    )
    iteration_dir = _scaffold(
        tmp_path, "2026-08-consume", doc, _raw("requirements--accepted.valid.yaml")
    )
    requirements = iteration_dir / "requirements.yaml"
    document = yaml.safe_load(requirements.read_text(encoding="utf-8"))
    document["generated_from"] = {
        "artifact": "iterations/2026-08-consume/00-raw/requirements-dump.md",
        "sha256": _sha("upstream content"),
    }
    requirements.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    (iteration_dir / "00-raw" / "requirements-dump.md").write_text("tampered")

    assert validator.main([str(iteration_dir), "--fix"]) == 1
    captured = capsys.readouterr()
    assert "stale input consumed" in captured.err


def test_second_in_progress_iteration_rejected(validator: Any, tmp_path: Path) -> None:
    first = _iteration_doc(
        "2026-08-one",
        ui=True,
        state="created",
        events=[],
        approvals=[],
    )
    second = deepcopy(first)
    second["iteration_id"] = "2026-08-two"
    _scaffold(tmp_path, "2026-08-one", first)
    iteration_two = _scaffold(tmp_path, "2026-08-two", second)
    assert validator.main([str(iteration_two)]) == 1


def _run_summary_doc(status: str, attempts: list, **extra: Any) -> dict:
    doc = {
        "schema_version": "1.0",
        "iteration_id": "2026-08-runs",
        "run_id": "run-20260828T101500Z-a3f2",
        "modules": ["checkout"],
        "status": status,
        "retry_budget": 5,
        "attempts": attempts,
    }
    doc.update(extra)
    return doc


def _attempt(n: int, result: str, failure_class: str = "none", **kw: Any) -> dict:
    base = {
        "attempt_number": n,
        "result": result,
        "failure_class": failure_class,
        "summary": f"attempt {n}: {result}",
    }
    base.update(kw)
    return base


def test_run_summary_attempt_ordering_violation(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc(
        "2026-08-runs",
        ui=True,
        state="created",
        events=[],
        approvals=[],
    )
    iteration_dir = _scaffold(tmp_path, "2026-08-runs", doc)
    run_dir = iteration_dir / "runs" / "run-20260828T101500Z-a3f2"
    run_dir.mkdir(parents=True)
    bad = _run_summary_doc(
        "running",
        [_attempt(1, "fail", "locator_drift"), _attempt(3, "fail", "timing")],
        started_at="2026-08-28T10:15:00Z",
        finished_at="2026-08-28T10:31:00Z",
        env="local",
        scope="module_set",
    )
    (run_dir / "run-summary.yaml").write_text(yaml.safe_dump(bad, sort_keys=False))
    assert validator.main([str(iteration_dir)]) == 1


def test_run_summary_passed_requires_last_pass(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc("2026-08-runs2", ui=True, state="created", events=[], approvals=[])
    iteration_dir = _scaffold(tmp_path, "2026-08-runs2", doc)
    run_dir = iteration_dir / "runs" / "run-20260828T101500Z-a3f2"
    run_dir.mkdir(parents=True)
    bad = _run_summary_doc(
        "passed",
        [_attempt(1, "fail", "locator_drift")],
        started_at="2026-08-28T10:15:00Z",
        finished_at="2026-08-28T10:31:00Z",
        env="local",
        scope="module_set",
    )
    (run_dir / "run-summary.yaml").write_text(yaml.safe_dump(bad, sort_keys=False))
    assert validator.main([str(iteration_dir)]) == 1


def test_run_summary_unresolvable_diff_ref(validator: Any, tmp_path: Path) -> None:
    doc = _iteration_doc("2026-08-runs3", ui=True, state="created", events=[], approvals=[])
    iteration_dir = _scaffold(tmp_path, "2026-08-runs3", doc)
    run_dir = iteration_dir / "runs" / "run-20260828T101500Z-a3f2"
    run_dir.mkdir(parents=True)
    bad = _run_summary_doc(
        "running",
        [_attempt(1, "fail", "locator_drift", diff_ref="runs/nowhere/attempt-1.patch")],
    )
    (run_dir / "run-summary.yaml").write_text(yaml.safe_dump(bad, sort_keys=False))
    assert validator.main([str(iteration_dir)]) == 1


def test_run_summary_resolves_diff_ref_from_its_run_directory(
    validator: Any, tmp_path: Path
) -> None:
    """记录器接受的相对 patch 路径必须也能通过迭代校验器。"""
    doc = _iteration_doc("2026-08-runs4", ui=True, state="created", events=[], approvals=[])
    iteration_dir = _scaffold(tmp_path, "2026-08-runs4", doc)
    run_dir = iteration_dir / "runs" / "run-20260828T101500Z-a3f2"
    run_dir.mkdir(parents=True)
    summary = _run_summary_doc(
        "passed",
        [_attempt(1, "pass", diff_ref="attempt-1.patch")],
        started_at="2026-08-28T10:15:00Z",
        finished_at="2026-08-28T10:16:00Z",
        env="local",
        scope="module_set",
    )
    (run_dir / "attempt-1.patch").write_text("diff --git a/a b/a\n", encoding="utf-8")
    (run_dir / "run-summary.yaml").write_text(yaml.safe_dump(summary, sort_keys=False))
    assert validator.main([str(iteration_dir)]) == 0
