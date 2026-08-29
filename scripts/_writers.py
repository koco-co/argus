#!/usr/bin/env python
"""迭代生命周期命名空间的唯一写入器（Roadmap 1.15b）。

- ``record_event.py`` 唯一写入 ``state`` 与 ``events[]``；每次迁移持久化前都
  按 ARCHITECTURE/PRD §5 的合法性规则检查。
- ``record_approval.py`` 唯一写入 ``approvals[]``；显式决定记录
  ``actor: user``，持续授权下的代理审查记录为
  ``action: delegated, actor: agent``，两者都绑定产物摘要（environment 阶段
  对保留键、遮蔽值的脱敏副本计算摘要）。
- ``reopen_iteration.py`` 记录用户或受托代理重开事件，保留所有已分配 ID，
  并将下游产物标记为 ``stale``，阻止 stale 消费者在重新生成或确认前继续使用。

如果 iteration 文件未通过 Schema，或事件链不一致，三个写入器都会拒绝写入；
手工改写会被拒绝，不会被静默修补。
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from _registry_lib import binding_for_path, schema_errors

APPROVAL_STAGES = (
    "requirements",
    "exemptions",
    "test_points",
    "environment",
    "acceptance",
    "skill_change",
)
APPROVAL_ACTIONS = ("accepted", "rejected", "provided", "approved", "delegated")
ACTORS = ("agent", "script", "user")
DELEGATION_SCOPES = (
    "requirements",
    "exemptions",
    "test_points",
    "environment",
    "acceptance",
    "skill_change",
    "lifecycle_reopen",
)


class WriterError(Exception):
    """User-facing refusal to write."""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_timestamp(value: str) -> datetime:
    """解析 RFC3339 时间；所有比较统一转换到 UTC。"""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(UTC)


def delegation_violations(
    document: dict[str, Any],
    approval: dict[str, Any],
    *,
    required_scope: str | None = None,
    now: datetime | None = None,
    enforce_current_window: bool = False,
) -> list[str]:
    """校验 delegated 决定绑定的用户授权，不接受自由文本冒充授权。

    生命周期复核只验证历史决定在记录当时位于授权窗口内；唯一写入器
    额外传入 ``enforce_current_window=True``，阻止授权过期后产生新的决定。
    """

    violations: list[str] = []
    delegation = document.get("delegation")
    delegation_id = approval.get("delegation_id")
    if not isinstance(delegation, dict):
        return ["delegated approval requires a structured iteration.delegation record"]
    if delegation_id != delegation.get("id"):
        violations.append("delegated approval delegation_id does not match iteration.delegation.id")
    if delegation.get("granted_by") != "user":
        violations.append("iteration.delegation.granted_by must be user")
    basis = delegation.get("basis")
    if not isinstance(basis, str) or not basis.strip():
        violations.append("iteration.delegation.basis must be non-empty")
    elif delegation.get("basis_sha256") != _sha256(basis.encode("utf-8")):
        violations.append("iteration.delegation.basis_sha256 does not match basis")
    scope = delegation.get("scope")
    if not isinstance(scope, list) or required_scope not in scope:
        violations.append(
            f"delegation scope does not include {required_scope or 'the requested stage'}"
        )
    try:
        granted_at = _parse_timestamp(str(delegation["granted_at"]))
        expires_at = _parse_timestamp(str(delegation["expires_at"]))
        if expires_at <= granted_at:
            violations.append("iteration.delegation.expires_at must be after granted_at")
        approval_at = _parse_timestamp(str(approval["timestamp"]))
        if approval_at < granted_at or approval_at > expires_at:
            violations.append("delegated approval timestamp is outside the delegation window")
        current = now or datetime.now(UTC)
        if enforce_current_window and current > expires_at:
            violations.append("iteration.delegation has expired")
    except (KeyError, TypeError, ValueError):
        violations.append("iteration.delegation timestamps must be valid timezone-aware date-times")
    return violations


def load_iteration(iteration_dir: Path) -> tuple[Path, dict[str, Any]]:
    iteration_yaml = iteration_dir / "iteration.yaml"
    if not iteration_yaml.exists():
        raise WriterError(f"{iteration_yaml} not found")
    document = yaml.safe_load(iteration_yaml.read_text(encoding="utf-8")) or {}
    return iteration_yaml, document


def validate_document(
    iteration_yaml: Path,
    document: dict[str, Any],
    *,
    allow_terminal_acceptance_repair: bool = False,
) -> None:
    binding = binding_for_path(iteration_yaml)
    if binding is None:
        raise WriterError(f"unregistered artifact path: {iteration_yaml}")
    errors = schema_errors(binding, document)
    if errors:
        raise WriterError("iteration.yaml is invalid (hand-edited?): " + "; ".join(errors))
    from validate_iteration import lifecycle_violations

    semantic_errors = lifecycle_violations(document)
    if allow_terminal_acceptance_repair:
        semantic_errors = [
            error
            for error in semantic_errors
            if not error.startswith(
                "acceptance approval was appended after the terminal accepted event"
            )
        ]
    if semantic_errors:
        raise WriterError(
            "iteration.yaml lifecycle is invalid (hand-edited?): " + "; ".join(semantic_errors)
        )


def write_iteration(
    iteration_yaml: Path, document: dict[str, Any], *, check_lifecycle: bool = True
) -> None:
    if check_lifecycle:
        validate_document(iteration_yaml, document)
    else:
        binding = binding_for_path(iteration_yaml)
        if binding is None:
            raise WriterError(f"unregistered artifact path: {iteration_yaml}")
        errors = schema_errors(binding, document)
        if errors:
            raise WriterError("iteration.yaml is invalid: " + "; ".join(errors))
    document["updated_at"] = _now()
    iteration_yaml.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def record_event(
    iteration_dir: Path,
    from_state: str,
    to_state: str,
    triggered_by: str,
    reason: str | None = None,
    merge_sha: str | None = None,
    pr_number: int | None = None,
    mark_downstream_stale: bool = False,
    delegation_id: str | None = None,
) -> dict[str, Any]:
    from validate_iteration import approval_gate_violations, legal_transition

    iteration_yaml, document = load_iteration(iteration_dir)
    validate_document(
        iteration_yaml,
        document,
        allow_terminal_acceptance_repair=mark_downstream_stale
        and to_state == "requirements_clarifying",
    )
    if document["state"] != from_state:
        raise WriterError(
            f"stale transition request: iteration state is {document['state']!r}, "
            f"not {from_state!r} - a hand-edited file or outdated caller"
        )
    violation = legal_transition(from_state, to_state, document["branches"]["ui"], triggered_by)
    if violation:
        raise WriterError(f"illegal transition {from_state} -> {to_state}: {violation}")
    gate_violations = approval_gate_violations(
        to_state,
        iteration_dir,
        document.get("approvals", []),
        document,
    )
    if gate_violations:
        raise WriterError("; ".join(gate_violations))
    if to_state == "blocked" and not (reason or "").strip():
        raise WriterError("moving to blocked requires a non-empty --reason")
    if mark_downstream_stale and not (
        triggered_by in {"user", "agent"} and to_state == "requirements_clarifying"
    ):
        raise WriterError(
            "mark_downstream_stale is reserved for a user/delegated reopen to "
            "requirements_clarifying"
        )
    if mark_downstream_stale and triggered_by == "agent":
        if not delegation_id:
            raise WriterError("delegated reopen requires --delegation-id")
        event_probe = {
            "delegation_id": delegation_id,
            "timestamp": _now(),
        }
        violations = delegation_violations(
            document,
            event_probe,
            required_scope="lifecycle_reopen",
            enforce_current_window=True,
        )
        if violations:
            raise WriterError("delegated reopen rejected: " + "; ".join(violations))
    elif delegation_id is not None:
        raise WriterError("--delegation-id 仅可用于 delegated reopen")
    event: dict[str, Any] = {
        "from_state": from_state,
        "to_state": to_state,
        "timestamp": _now(),
        "triggered_by": triggered_by,
    }
    if to_state == "merged":
        if triggered_by != "script" or not merge_sha or pr_number is None:
            raise WriterError("merged 事件必须由 script 写入真实 merge_sha 与 pr_number")
        event["merge_sha"] = merge_sha
        event["pr_number"] = pr_number
    elif merge_sha is not None or pr_number is not None:
        raise WriterError("merge_sha/pr_number 只能写入 merged 事件")
    if mark_downstream_stale:
        propagate_stale(document)
        if delegation_id:
            event["delegation_id"] = delegation_id
    document["events"].append(event)
    document["state"] = to_state
    if to_state == "blocked":
        document["blocked_reason"] = reason
    if from_state == "blocked":
        document["blocked_reason"] = None
    write_iteration(iteration_yaml, document)
    return document


def record_approval(
    iteration_dir: Path,
    stage: str,
    action: str,
    artifact_sha256: str,
    note: str | None = None,
    delegation_id: str | None = None,
) -> dict[str, Any]:
    iteration_yaml, document = load_iteration(iteration_dir)
    if action == "delegated" and not (note or "").strip():
        raise WriterError("delegated approval requires a non-empty --note with authorization basis")
    if action == "delegated":
        if not delegation_id:
            raise WriterError("delegated approval requires --delegation-id")
        probe = {
            "delegation_id": delegation_id,
            "timestamp": _now(),
        }
        violations = delegation_violations(
            document, probe, required_scope=stage, enforce_current_window=True
        )
        if violations:
            raise WriterError("delegated approval rejected: " + "; ".join(violations))
    elif delegation_id is not None:
        raise WriterError("--delegation-id 仅可用于 delegated approval")
    approval: dict[str, Any] = {
        "stage": stage,
        "action": action,
        "actor": "agent" if action == "delegated" else "user",
        "timestamp": _now(),
        "artifact_sha256": artifact_sha256,
    }
    if note:
        approval["note"] = note
    if delegation_id:
        approval["delegation_id"] = delegation_id
    document["approvals"].append(approval)
    write_iteration(iteration_yaml, document)
    return document


def record_delegation(
    iteration_dir: Path,
    delegation_id: str,
    basis: str,
    scope: list[str],
    granted_at: str,
    expires_at: str,
) -> dict[str, Any]:
    """通过独立 writer 持久化当前任务的用户授权范围。"""

    iteration_yaml, document = load_iteration(iteration_dir)
    if not delegation_id.startswith("delegation-"):
        raise WriterError("delegation id must start with delegation-")
    if not basis.strip():
        raise WriterError("delegation basis must be non-empty")
    if not scope or any(item not in DELEGATION_SCOPES for item in scope):
        raise WriterError("delegation scope contains an unknown or empty scope")
    try:
        start = _parse_timestamp(granted_at)
        end = _parse_timestamp(expires_at)
    except ValueError as exc:
        raise WriterError(f"invalid delegation window: {exc}") from exc
    if end <= start:
        raise WriterError("delegation expires_at must be after granted_at")
    current = document.get("delegation")
    proposed = {
        "id": delegation_id,
        "granted_by": "user",
        "basis": basis,
        "basis_sha256": _sha256(basis.encode("utf-8")),
        "scope": list(dict.fromkeys(scope)),
        "granted_at": granted_at,
        "expires_at": expires_at,
    }
    if current is not None and current != proposed:
        raise WriterError("iteration.delegation already exists with different content")
    document["delegation"] = proposed
    # 迁移旧版已由本任务写入的 delegated 记录；由唯一生命周期 writer
    # 一次性补上结构化引用，避免把自由文本当作授权来源。
    for approval in document.get("approvals", []):
        if approval.get("action") == "delegated" and "delegation_id" not in approval:
            approval["delegation_id"] = delegation_id
    # 旧版 delegated 记录可能缺少 delegation_id，且历史终态后追加的批准
    # 会由下一步 reopen 规则拒绝；这里只做一次结构化迁移，最终生命周期
    # 仍必须由 validate_iteration.py 通过。
    write_iteration(iteration_yaml, document, check_lifecycle=False)
    return document


def bind_delegated_approvals(
    iteration_dir: Path,
    delegation_id: str,
) -> dict[str, Any]:
    """为历史 delegated 记录补充唯一授权引用，仍由批准 writer 落盘。"""

    iteration_yaml, document = load_iteration(iteration_dir)
    delegation = document.get("delegation")
    if not isinstance(delegation, dict) or delegation.get("id") != delegation_id:
        raise WriterError("delegation record does not exist or id does not match")
    changed = False
    for approval in document.get("approvals", []):
        if approval.get("action") != "delegated":
            continue
        existing = approval.get("delegation_id")
        if existing is not None and existing != delegation_id:
            raise WriterError("a delegated approval is bound to a different delegation")
        if existing is None:
            approval["delegation_id"] = delegation_id
            changed = True
    if changed:
        write_iteration(iteration_yaml, document)
    return document


def artifact_digest(path: Path) -> str:
    return _sha256(path.read_bytes())


def redacted_digest(path: Path) -> str:
    """SHA-256 over a redacted copy: keys and shape preserved, values masked."""
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def mask(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: mask(item) for key, item in value.items()}
        if isinstance(value, list):
            return [mask(item) for item in value]
        return "***"

    return _sha256(yaml.safe_dump(mask(document), sort_keys=False).encode("utf-8"))


def propagate_stale(document: dict[str, Any]) -> list[str]:
    """Mark every downstream artifact stale (reopen protocol, PRD §5)."""
    stale: list[str] = []
    for key, entry in document.get("artifacts", {}).items():
        if key == "requirements":
            continue
        if entry.get("status") not in (None, "not_started", "stale"):
            entry["status"] = "stale"
            stale.append(key)
    return stale


def main(argv: list[str] | None = None) -> int:
    """Minimal unified CLI kept for symmetry; each script's __main__ delegates
    here with its own subcommand. See scripts/record_event.py,
    scripts/record_approval.py and scripts/reopen_iteration.py."""
    raise SystemExit(
        "this module is a library of sole writers; invoke record_event.py, "
        "record_approval.py or reopen_iteration.py"
    )


if __name__ == "__main__":  # pragma: no cover
    main()
