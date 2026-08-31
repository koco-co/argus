"""Roadmap 1.15b 三个唯一写入器的验收测试。

DoD：拒绝手工编辑批准路径与 state/events[]；显式批准记录 actor 和产物摘要；事件只引用
合法迁移；重开保留 ID、标记下游 stale，并阻止 stale 消费者。
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest  # pyright: ignore[reportMissingImports]
import yaml  # pyright: ignore[reportMissingModuleSource]
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
def record_delegation() -> Any:
    return _load_script("record_delegation")


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


def _write_valid_requirements(iteration_dir: Path) -> Path:
    artifact = iteration_dir / "requirements.yaml"
    artifact.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "iteration_id": iteration_dir.name,
                "status": "accepted",
                "generated_from": {
                    "artifact": "fixture/source.md",
                    "sha256": "a" * 64,
                },
                "requirements": [
                    {
                        "requirement_id": "R0001",
                        "title": "Fixture requirement",
                        "description": "A valid fixture requirement for writer tests.",
                    }
                ],
                "ambiguities": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return artifact


def _write_valid_exemptions(iteration_dir: Path) -> Path:
    artifact = iteration_dir / "exemptions.yaml"
    artifact.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "iteration_id": iteration_dir.name,
                "status": "accepted",
                "generated_from": {
                    "artifact": "fixture/requirements.yaml",
                    "sha256": "a" * 64,
                },
                "exemptions": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return artifact


def _add_requirements_approval(iteration_dir: Path) -> None:
    """为写入器测试构造由当前 requirements 字节支持的批准记录。"""
    artifact = _write_valid_requirements(iteration_dir)
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


def test_writer_rejects_symlinked_iteration_lock(record_event: Any, tmp_path: Path) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-w1-symlink-lock", "requirements_clarifying")
    lock = iteration_dir / ".iteration.yaml.lock"
    foreign = tmp_path / "foreign.lock"
    foreign.write_text("unchanged", encoding="utf-8")
    lock.symlink_to(foreign)
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
    assert foreign.read_text(encoding="utf-8") == "unchanged"


def test_merged_writer_requires_verified_result(writers: Any, tmp_path: Path) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-w1-merged-capability", "accepted")
    with pytest.raises(writers.WriterError, match="external verifier"):
        writers.record_merged_event(iteration_dir, "not-a-sha", -7)


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


def test_record_event_design_lint_is_a_pre_write_gate(
    record_event: Any, tmp_path: Path, capsys: Any
) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-w1-lint-gate", "requirements_clarifying")
    _add_requirements_approval(iteration_dir)
    artifact = iteration_dir / "requirements.yaml"
    document = yaml.safe_load(artifact.read_text(encoding="utf-8"))
    document["requirements"][0]["source"] = {"not": "a string"}
    artifact.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    iteration_yaml = iteration_dir / "iteration.yaml"
    aggregate = yaml.safe_load(iteration_yaml.read_text(encoding="utf-8"))
    aggregate["approvals"][0]["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    iteration_yaml.write_text(yaml.safe_dump(aggregate, sort_keys=False), encoding="utf-8")
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
    assert "test-design lint gate rejected transition" in capsys.readouterr().err
    assert iteration_yaml.read_text(encoding="utf-8") == before


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
    reopen_iteration: Any,
    tmp_path: Path,
    capsys: Any,
) -> None:
    """生命周期数组虽过 Schema、但链断裂时，三个写入入口都不得追加。"""
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
    document["artifacts"]["test_points"]["status"] = "accepted"
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

    assert reopen_iteration.main([str(iteration_dir), "--reason", "fixture reopen"]) == 1
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


def test_record_approval_design_lint_is_a_pre_write_gate(
    record_approval: Any, tmp_path: Path, capsys: Any
) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-approval-lint", "requirements_clarifying")
    artifact = _write_valid_requirements(iteration_dir)
    requirements = yaml.safe_load(artifact.read_text(encoding="utf-8"))
    requirements["requirements"][0]["source"] = {"unexpected": "object"}
    artifact.write_text(yaml.safe_dump(requirements, sort_keys=False), encoding="utf-8")

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
            ]
        )
        == 1
    )
    assert "test-design lint gate rejected approval" in capsys.readouterr().err
    assert yaml.safe_load((iteration_dir / "iteration.yaml").read_text())["approvals"] == []


def test_record_approval_records_user_actor_and_artifact_hash(
    record_approval: Any, tmp_path: Path
) -> None:
    iteration_dir = _scaffold(tmp_path, "2026-08-w7", "requirements_clarifying")
    artifact = _write_valid_requirements(iteration_dir)
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


def test_requirements_approval_cannot_be_delegated(
    record_approval: Any, tmp_path: Path, capsys: Any
) -> None:
    """M1 的产品取舍不能被持续授权或 agent 记录替代。"""
    iteration_dir = _scaffold(tmp_path, "2026-08-requirements-delegated", "requirements_clarifying")
    artifact = _write_valid_requirements(iteration_dir)

    assert (
        record_approval.main(
            [
                str(iteration_dir),
                "--stage",
                "requirements",
                "--action",
                "delegated",
                "--artifact",
                str(artifact),
                "--note",
                "即使有持续授权，M1 仍需用户接受。",
                "--delegation-id",
                "delegation-not-allowed",
            ]
        )
        == 1
    )
    assert "cannot be delegated" in capsys.readouterr().err
    assert yaml.safe_load((iteration_dir / "iteration.yaml").read_text())["approvals"] == []


def test_delegated_approval_requires_note_and_records_agent(
    record_approval: Any, record_delegation: Any, tmp_path: Path, capsys: Any
) -> None:
    """持续授权必须如实记录代理决策者，并保留可审计的授权说明。"""
    iteration_dir = _scaffold(tmp_path, "2026-08-delegated", "requirements_accepted")
    _write_valid_requirements(iteration_dir)
    artifact = _write_valid_exemptions(iteration_dir)

    assert (
        record_approval.main(
            [
                str(iteration_dir),
                "--stage",
                "exemptions",
                "--action",
                "delegated",
                "--artifact",
                str(artifact),
            ]
        )
        == 1
    )
    assert "requires a non-empty --note" in capsys.readouterr().err
    assert yaml.safe_load((iteration_dir / "iteration.yaml").read_text())["approvals"] == []

    assert (
        record_delegation.main(
            [
                str(iteration_dir),
                "--id",
                "delegation-test-writer",
                "--basis",
                "依据用户持续授权的写入器夹具",
                "--scope",
                "exemptions",
                "--granted-at",
                "2026-08-28T09:00:00Z",
                "--expires-at",
                "2026-12-31T23:59:59Z",
            ]
        )
        == 0
    )

    assert (
        record_approval.main(
            [
                str(iteration_dir),
                "--stage",
                "exemptions",
                "--action",
                "delegated",
                "--artifact",
                str(artifact),
                "--note",
                "依据用户在当前任务中的持续授权，由 agent 审查空豁免清单后推进。",
                "--delegation-id",
                "delegation-test-writer",
            ]
        )
        == 0
    )
    approval = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())["approvals"][-1]
    assert approval["action"] == "delegated"
    assert approval["actor"] == "agent"
    assert approval["note"].startswith("依据用户")
    assert approval["delegation_id"] == "delegation-test-writer"


def test_expired_delegation_rejects_new_approval(
    record_approval: Any, record_delegation: Any, tmp_path: Path, capsys: Any
) -> None:
    """授权窗口过期后，唯一批准写入器不得产生新的代理决定。"""
    iteration_dir = _scaffold(tmp_path, "2026-08-delegated-expired", "requirements_accepted")
    _write_valid_requirements(iteration_dir)
    artifact = _write_valid_exemptions(iteration_dir)

    assert (
        record_delegation.main(
            [
                str(iteration_dir),
                "--id",
                "delegation-expired-writer",
                "--basis",
                "依据用户持续授权的过期窗口夹具",
                "--scope",
                "exemptions",
                "--granted-at",
                "2020-01-01T00:00:00Z",
                "--expires-at",
                "2020-01-02T00:00:00Z",
            ]
        )
        == 0
    )
    before = (iteration_dir / "iteration.yaml").read_text(encoding="utf-8")

    assert (
        record_approval.main(
            [
                str(iteration_dir),
                "--stage",
                "exemptions",
                "--action",
                "delegated",
                "--artifact",
                str(artifact),
                "--note",
                "过期授权不得继续写入代理决定。",
                "--delegation-id",
                "delegation-expired-writer",
            ]
        )
        == 1
    )
    assert "iteration.delegation has expired" in capsys.readouterr().err
    assert (iteration_dir / "iteration.yaml").read_text(encoding="utf-8") == before


def test_approval_stage_cannot_be_recorded_before_its_lifecycle_state(
    record_approval: Any, tmp_path: Path, capsys: Any
) -> None:
    """未来阶段的批准不能在 iteration 创建阶段预先污染审计链。"""
    iteration_dir = _scaffold(tmp_path, "2026-08-early-approval", "created")
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
        == 1
    )
    assert "只能在当前阶段写入" in capsys.readouterr().err
    assert yaml.safe_load((iteration_dir / "iteration.yaml").read_text())["approvals"] == []


def test_record_approval_supports_exemptions_stage(record_approval: Any, tmp_path: Path) -> None:
    """需求豁免必须能经唯一写入器形成独立的用户批准记录。"""
    iteration_dir = _scaffold(tmp_path, "2026-08-exemptions", "requirements_accepted")
    _write_valid_requirements(iteration_dir)
    artifact = _write_valid_exemptions(iteration_dir)

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
    assert "hand-edited?" in capsys.readouterr().err


def test_reopen_preserves_ids_and_marks_downstream_stale(
    reopen_iteration: Any, record_event: Any, record_approval: Any, tmp_path: Path
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

    # An ordinary accepted-artifact reopen keeps the original M1 approval;
    # only blocked recovery creates a fresh requirements window.
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
                "user",
            ]
        )
        == 0
    )

    blocked_dir = _scaffold(tmp_path, "2026-08-blocked-reopen", "blocked")
    _add_requirements_approval(blocked_dir)
    assert (
        record_event.main(
            [
                str(blocked_dir),
                "--from",
                "blocked",
                "--to",
                "created",
                "--by",
                "user",
            ]
        )
        == 0
    )
    assert reopen_iteration.main([str(blocked_dir), "--reason", "retry after recovery"]) == 0
    assert (
        record_event.main(
            [
                str(blocked_dir),
                "--from",
                "requirements_clarifying",
                "--to",
                "requirements_accepted",
                "--by",
                "user",
            ]
        )
        == 1
    )
    blocked_requirements = blocked_dir / "requirements.yaml"
    assert (
        record_approval.main(
            [
                str(blocked_dir),
                "--stage",
                "requirements",
                "--action",
                "accepted",
                "--artifact",
                str(blocked_requirements),
            ]
        )
        == 0
    )
    assert (
        record_event.main(
            [
                str(blocked_dir),
                "--from",
                "requirements_clarifying",
                "--to",
                "requirements_accepted",
                "--by",
                "user",
            ]
        )
        == 0
    )


def test_reopen_blocks_stale_consumers_via_validator(
    reopen_iteration: Any, validators: Any, tmp_path: Path
) -> None:
    """validate_iteration 拒绝携带 stale 产物却已推进的状态。"""
    validate_iteration = validators[0]
    iteration_dir = _scaffold(tmp_path, "2026-08-block", "test_points_accepted")
    document = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())
    document["artifacts"]["test_points"]["status"] = "accepted"
    (iteration_dir / "iteration.yaml").write_text(yaml.safe_dump(document, sort_keys=False))
    assert reopen_iteration.main([str(iteration_dir)]) == 0
    # 模拟下游仍携带 stale 状态却继续推进。
    document = yaml.safe_load((iteration_dir / "iteration.yaml").read_text())
    document["state"] = "functional_cases_exported"
    (iteration_dir / "iteration.yaml").write_text(yaml.safe_dump(document, sort_keys=False))
    assert validate_iteration.main([str(iteration_dir)]) != 0
