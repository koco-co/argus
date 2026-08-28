"""Roadmap 1.15b acceptance tests: the three sole writers.

DoD: hand-edited approval path is rejected; hand-edited state/events[] is
rejected; explicit approval records actor/artifact hash; event records
reference legal transitions only; reopen preserves IDs, marks downstream
stale, and blocks stale consumers.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import _load_script

SHA = "a" * 64


def test_record_approval_script_entrypoint_imports_shared_package() -> None:
    """唯一批准写入器必须支持 AGENTS.md 规定的脚本路径调用。"""
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/record_approval.py"), "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture()
def validators(new_iteration: Any) -> tuple[Any, Any]:
    return _load_script("validate_iteration"), None


@pytest.fixture(scope="module")
def writers() -> Any:
    return _load_script("_writers")


@pytest.fixture(scope="module")
def record_event() -> Any:
    return _load_script("record_event")


@pytest.fixture(scope="module")
def record_approval() -> Any:
    return _load_script("record_approval")


@pytest.fixture(scope="module")
def reopen_iteration() -> Any:
    return _load_script("reopen_iteration")


def _events_to(state: str, ui: bool) -> list[dict[str, str]]:
    """为写入器单测构造分支合法的既有生命周期。"""
    route = (
        [
            "created",
            "requirements_clarifying",
            "requirements_accepted",
            "test_points_review",
            "test_points_accepted",
            "functional_cases_generating",
            "functional_cases_exported",
            "web_automation_generating",
            "web_automation_generated",
            "env_pending",
            "env_configured",
            "executing",
            "execution_passed",
            "acceptance_pending",
            "accepted",
        ]
        if ui
        else [
            "created",
            "requirements_clarifying",
            "requirements_accepted",
            "requirements_mapped",
            "spec_normalizing",
            "spec_valid",
            "api_cases_generating",
            "api_cases_exported",
            "api_automation_generating",
            "api_automation_generated",
            "env_pending",
            "env_configured",
            "executing",
            "execution_passed",
            "acceptance_pending",
            "accepted",
        ]
    )
    if state == "blocked":
        route = ["created", "blocked"]
    elif state not in route:
        return []
    else:
        route = route[: route.index(state) + 1]
    return [
        {
            "from_state": source,
            "to_state": target,
            "timestamp": "2026-08-28T09:00:00Z",
            "triggered_by": "agent",
        }
        for source, target in zip(route, route[1:], strict=False)
    ]


def _doc(iteration_id: str, state: str, *, ui: bool = True) -> dict:
    return {
        "schema_version": "1.0",
        "iteration_id": iteration_id,
        "state": state,
        "blocked_reason": "fixture_block" if state == "blocked" else None,
        "branches": {"ui": ui, "api": not ui},
        "artifacts": {
            key: {"status": "not_started"}
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
        "approvals": [],
        "events": _events_to(state, ui),
    }


def _scaffold(tmp_path: Path, iteration_id: str, state: str, *, ui: bool = True) -> Path:
    iteration_dir = tmp_path / "iterations" / iteration_id
    iteration_dir.mkdir(parents=True, exist_ok=True)
    (iteration_dir / "iteration.yaml").write_text(
        yaml.safe_dump(_doc(iteration_id, state, ui=ui), sort_keys=False), encoding="utf-8"
    )
    return iteration_dir


def _add_requirements_approval(iteration_dir: Path) -> None:
    """为写入器测试构造由当前 requirements 字节支持的批准记录。"""
    artifact = iteration_dir / "requirements.yaml"
    artifact.write_text("schema_version: '1.0'\n", encoding="utf-8")
    iteration_yaml = iteration_dir / "iteration.yaml"
    document = yaml.safe_load(iteration_yaml.read_text(encoding="utf-8"))
    document["approvals"].append(
        {
            "stage": "requirements",
            "action": "accepted",
            "actor": "user",
            "timestamp": "2026-08-28T10:00:00Z",
            "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        }
    )
    iteration_yaml.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def test_record_event_legal_transition_persists(record_event: Any, tmp_path: Path) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-w1", "requirements_clarifying")
    _add_requirements_approval(iteration_dir)
    assert (
        record_event.main(
            [
                str(iteration_dir),
                "--from",
                "requirements_clarifying",
                "--to",
                "requirements_accepted",
                "--by",
                "agent",
            ]
        )
        == 0
    )
    document = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())
    assert document["state"] == "requirements_accepted"
    assert document["events"][-1]["to_state"] == "requirements_accepted"
    assert document["events"][-1]["triggered_by"] == "agent"


def test_record_event_rejects_gate_without_approval(
    record_event: Any, tmp_path: Path, capsys: Any
) -> None:
    """门禁前置条件必须在事件写入磁盘前生效。"""
    iteration_dir = _scaffold(tmp_path, "2026-08-w1-no-approval", "requirements_clarifying")
    before = (iteration_dir / "iteration.yaml").read_text(encoding="utf-8")

    assert (
        record_event.main(
            [
                str(iteration_dir),
                "--from",
                "requirements_clarifying",
                "--to",
                "requirements_accepted",
                "--by",
                "agent",
            ]
        )
        == 1
    )
    assert "requires an approvals[] entry" in capsys.readouterr().err
    assert (iteration_dir / "iteration.yaml").read_text(encoding="utf-8") == before


def test_writers_reject_schema_valid_but_broken_event_chain(
    record_event: Any,
    record_approval: Any,
    tmp_path: Path,
    capsys: Any,
) -> None:
    """生命周期数组虽过 Schema、但链断裂时，两个写入入口都不得追加。"""
    iteration_dir = _scaffold(tmp_path, "2026-08-w1-broken-chain", "requirements_clarifying")
    _add_requirements_approval(iteration_dir)
    iteration_yaml = iteration_dir / "iteration.yaml"
    document = yaml.safe_load(iteration_yaml.read_text(encoding="utf-8"))
    document["events"] = [
        {
            "from_state": "test_points_review",
            "to_state": "requirements_clarifying",
            "timestamp": "2026-08-28T10:00:00Z",
            "triggered_by": "user",
        }
    ]
    iteration_yaml.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    before = iteration_yaml.read_text(encoding="utf-8")

    assert (
        record_event.main(
            [
                str(iteration_dir),
                "--from",
                "requirements_clarifying",
                "--to",
                "requirements_accepted",
                "--by",
                "agent",
            ]
        )
        == 1
    )
    assert "chain broken" in capsys.readouterr().err
    assert iteration_yaml.read_text(encoding="utf-8") == before

    assert (
        record_approval.main(
            [
                str(iteration_dir),
                "--stage",
                "requirements",
                "--action",
                "accepted",
                "--artifact",
                str(iteration_dir / "requirements.yaml"),
            ]
        )
        == 1
    )
    assert "chain broken" in capsys.readouterr().err
    assert iteration_yaml.read_text(encoding="utf-8") == before


def test_record_event_stale_transition_rejected(
    record_event: Any, tmp_path: Path, capsys: Any
) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-w2", "requirements_accepted")
    before = (iteration_dir / "iteration.yaml").read_text()
    assert (
        record_event.main(
            [
                str(iteration_dir),
                "--from",
                "requirements_clarifying",
                "--to",
                "test_points_review",
                "--by",
                "agent",
            ]
        )
        == 1
    )
    assert "state is 'requirements_accepted'" in capsys.readouterr().err
    assert (iteration_dir / "iteration.yaml").read_text() == before


def test_record_event_illegal_jump_rejected(record_event: Any, tmp_path: Path) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-w3", "created")
    assert (
        record_event.main(
            [
                str(iteration_dir),
                "--from",
                "created",
                "--to",
                "test_points_review",
                "--by",
                "agent",
            ]
        )
        == 1
    )


def test_record_event_agent_cannot_leave_blocked(record_event: Any, tmp_path: Path) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-w4", "blocked")
    assert (
        record_event.main(
            [
                str(iteration_dir),
                "--from",
                "blocked",
                "--to",
                "requirements_clarifying",
                "--by",
                "agent",
            ]
        )
        == 1
    )


def test_record_event_blocked_requires_reason(record_event: Any, tmp_path: Path) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-w5", "requirements_clarifying")
    assert (
        record_event.main(
            [
                str(iteration_dir),
                "--from",
                "requirements_clarifying",
                "--to",
                "blocked",
                "--by",
                "agent",
            ]
        )
        == 1
    )
    assert (
        record_event.main(
            [
                str(iteration_dir),
                "--from",
                "requirements_clarifying",
                "--to",
                "blocked",
                "--by",
                "agent",
                "--reason",
                "validation_budget_exhausted",
            ]
        )
        == 0
    )
    document = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())
    assert document["blocked_reason"] == "validation_budget_exhausted"


def test_hand_edited_approval_rejected_by_writer(record_approval: Any, tmp_path: Path) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-w6", "created")
    document = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())
    document["approvals"].append(
        {
            "stage": "requirements",
            "action": "accepted",
            "actor": "agent",
            "timestamp": "not-a-time",
            "artifact_sha256": "nope",
        }
    )
    (iteration_dir / "iteration.yaml").write_text(yaml.safe_dump(document, sort_keys=False))
    assert (
        record_approval.main(
            [
                str(iteration_dir),
                "--stage",
                "requirements",
                "--action",
                "accepted",
                "--sha256",
                SHA,
            ]
        )
        == 1
    )


def test_record_approval_records_user_actor_and_artifact_hash(
    record_approval: Any, tmp_path: Path
) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-w7", "created")
    artifact = tmp_path / "requirements.yaml"
    artifact.write_text("requirements file content\n", encoding="utf-8")
    assert (
        record_approval.main(
            [
                str(iteration_dir),
                "--stage",
                "requirements",
                "--action",
                "accepted",
                "--artifact",
                str(artifact),
                "--note",
                "accepted in session",
            ]
        )
        == 0
    )
    document = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())
    approval = document["approvals"][-1]
    assert approval["actor"] == "user"
    assert approval["artifact_sha256"] != ""
    assert len(approval["artifact_sha256"]) == 64


def test_record_approval_supports_exemptions_stage(record_approval: Any, tmp_path: Path) -> None:
    """需求豁免必须能经唯一写入器形成独立的用户批准记录。"""
    iteration_dir = _scaffold(tmp_path, "2026-08-exemptions", "requirements_accepted")
    artifact = tmp_path / "exemptions.yaml"
    artifact.write_text("schema_version: '1.0'\nexemptions: []\n", encoding="utf-8")

    assert (
        record_approval.main(
            [
                str(iteration_dir),
                "--stage",
                "exemptions",
                "--action",
                "accepted",
                "--artifact",
                str(artifact),
            ]
        )
        == 0
    )
    document = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())
    assert document["approvals"][-1]["stage"] == "exemptions"


def test_environment_approval_requires_green_settings_check(
    record_approval: Any, tmp_path: Path, capsys: Any
) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-env-red", "env_pending", ui=False)
    env_file = tmp_path / "env.local.yaml"
    env_file.write_text("base_url: http://localhost:9000\n", encoding="utf-8")

    assert (
        record_approval.main(
            [
                str(iteration_dir),
                "--stage",
                "environment",
                "--action",
                "provided",
                "--artifact",
                str(env_file),
            ]
        )
        == 1
    )
    error = capsys.readouterr().err
    assert "auth.username: 缺失" in error
    assert "db.dsn: 必须是 PostgreSQL DSN" in error
    assert yaml.safe_load((iteration_dir / "iteration.yaml").read_text())["approvals"] == []


def test_environment_approval_records_only_after_green_settings_check(
    record_approval: Any, tmp_path: Path
) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-env-green", "env_pending")
    env_file = tmp_path / "env.local.yaml"
    env_file.write_text("base_url: http://localhost:8000\n", encoding="utf-8")

    assert (
        record_approval.main(
            [
                str(iteration_dir),
                "--stage",
                "environment",
                "--action",
                "provided",
                "--artifact",
                str(env_file),
            ]
        )
        == 0
    )
    document = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())
    assert document["approvals"][-1]["stage"] == "environment"


def test_hand_edited_state_blocks_event_writer(
    record_event: Any, tmp_path: Path, capsys: Any
) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-w8", "accepted")  # no events to match
    document = yaml.safe_load((iteration_dir / "iteration.yaml").read_text(encoding="utf-8"))
    document["events"] = []
    (iteration_dir / "iteration.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    assert (
        record_event.main(
            [
                str(iteration_dir),
                "--from",
                "created",
                "--to",
                "requirements_clarifying",
                "--by",
                "agent",
            ]
        )
        == 1
    )
    assert "hand-edited file" in capsys.readouterr().err


def test_reopen_preserves_ids_and_marks_downstream_stale(
    reopen_iteration: Any, tmp_path: Path
) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-reopen", "test_points_accepted")
    document = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())
    document["artifacts"]["test_points"]["status"] = "accepted"
    (iteration_dir / "iteration.yaml").write_text(yaml.safe_dump(document, sort_keys=False))
    requirements = iteration_dir / "requirements.yaml"
    requirements.write_text(
        "schema_version: '1.0'\n", encoding="utf-8"
    )  # allocated ID file must survive untouched

    assert reopen_iteration.main([str(iteration_dir), "--reason", "requirements changed"]) == 0
    reopened = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())
    assert reopened["state"] == "requirements_clarifying"
    assert reopened["artifacts"]["test_points"]["status"] == "stale"
    assert requirements.read_text() == "schema_version: '1.0'\n"
    assert reopened["events"][-1]["triggered_by"] == "user"
    assert reopened["events"][-1]["to_state"] == "requirements_clarifying"


def test_reopen_blocks_stale_consumers_via_validator(
    reopen_iteration: Any, validators: Any, tmp_path: Path
) -> None:
    """A stale artifact + advanced state is refused by validate_iteration."""
    validate_iteration = validators[0]
    iteration_dir = _scaffold(tmp_path, "2026-08-block", "test_points_accepted")
    document = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())
    document["artifacts"]["test_points"]["status"] = "accepted"
    (iteration_dir / "iteration.yaml").write_text(yaml.safe_dump(document, sort_keys=False))
    assert reopen_iteration.main([str(iteration_dir)]) == 0
    # simulate downstream progress while still carrying stale statuses
    document = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())
    document["state"] = "functional_cases_exported"
    (iteration_dir / "iteration.yaml").write_text(yaml.safe_dump(document, sort_keys=False))
    assert validate_iteration.main([str(iteration_dir)]) != 0
