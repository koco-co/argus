"""固定审批矩阵及最新决定规则。"""

from __future__ import annotations

from datetime import UTC, datetime

from .models import (  # pyright: ignore[reportMissingImports]
    Actor,
    Approval,
    ApprovalAction,
    ApprovalStage,
    DelegationGrant,
    IterationDocument,
)


class ApprovalError(ValueError):
    """审批不满足固定矩阵或授权窗口。"""


def latest_approval(
    document: IterationDocument,
    workstream_id: str,
    stage: ApprovalStage,
) -> Approval | None:
    """返回指定 workstream/stage 的最后一条决定；旧决定不能覆盖新拒绝。"""
    matches = [
        item
        for item in document.approvals
        if item.workstream_id == workstream_id and item.stage == stage
    ]
    return matches[-1] if matches else None


def verify_delegation(
    document: IterationDocument,
    approval: Approval,
    *,
    now: datetime | None = None,
) -> None:
    if approval.action != ApprovalAction.DELEGATED:
        return
    grant = document.delegation
    if not isinstance(grant, DelegationGrant):
        raise ApprovalError("delegated approval requires a structured delegation grant")
    if approval.delegation_id != grant.id:
        raise ApprovalError("delegation_id does not match the iteration grant")
    if approval.stage not in grant.scope:
        raise ApprovalError(f"delegation scope does not include {approval.stage.value}")
    moment = now or datetime.now(UTC)
    if not grant.granted_at <= approval.recorded_at <= grant.expires_at:
        raise ApprovalError("approval timestamp is outside the delegation window")
    if moment > grant.expires_at:
        raise ApprovalError("delegation grant has expired")


def require_latest(
    document: IterationDocument,
    workstream_id: str,
    stage: ApprovalStage,
    action: ApprovalAction,
) -> Approval:
    """要求当前阶段最后决定满足动作和固定 actor 规则。"""
    approval = latest_approval(document, workstream_id, stage)
    if approval is None:
        raise ApprovalError(f"{stage.value} requires an approval for workstream {workstream_id}")
    if stage == ApprovalStage.REQUIREMENTS:
        if approval.action != action or approval.actor != Actor.USER:
            raise ApprovalError("requirements acceptance must be an explicit user decision")
    elif approval.action != action and approval.action != ApprovalAction.DELEGATED:
        raise ApprovalError(f"latest {stage.value} approval must be {action.value} or delegated")
    verify_delegation(document, approval)
    return approval


def append_approval(document: IterationDocument, approval: Approval) -> None:
    """在模型已通过固定矩阵后追加审批；调用方负责持久化。"""
    if approval.workstream_id not in {item.id for item in document.workstreams}:
        raise ApprovalError(f"unknown workstream: {approval.workstream_id}")
    if approval.action == ApprovalAction.DELEGATED:
        verify_delegation(document, approval)
    document.approvals.append(approval)
