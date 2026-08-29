"""workstream 状态机；所有迁移都是显式控制面操作。"""

from __future__ import annotations

from datetime import UTC, datetime

from .approvals import ApprovalError, require_latest  # pyright: ignore[reportMissingImports]
from .models import (  # pyright: ignore[reportMissingImports]
    Actor,
    ApprovalAction,
    ApprovalStage,
    IterationDocument,
    IterationStatus,
    LifecycleEvent,
    Surface,
    Workstream,
    WorkstreamStatus,
)


class StateError(ValueError):
    """状态迁移或状态聚合不合法。"""


_COMMON: dict[WorkstreamStatus, set[WorkstreamStatus]] = {
    WorkstreamStatus.BLOCKED: {WorkstreamStatus.CREATED},
    WorkstreamStatus.AUTOMATION_PENDING: {WorkstreamStatus.READY},
    WorkstreamStatus.READY: {WorkstreamStatus.EXECUTING},
    WorkstreamStatus.EXECUTING: {
        WorkstreamStatus.PASSED,
        WorkstreamStatus.BUDGET_EXCEEDED,
        WorkstreamStatus.ESCALATED,
        WorkstreamStatus.BLOCKED,
    },
}
_WEB: dict[WorkstreamStatus, set[WorkstreamStatus]] = {
    WorkstreamStatus.CREATED: {WorkstreamStatus.REQUIREMENTS_ACCEPTED},
    WorkstreamStatus.REQUIREMENTS_ACCEPTED: {WorkstreamStatus.DESIGN_PENDING},
    WorkstreamStatus.DESIGN_PENDING: {WorkstreamStatus.AUTOMATION_PENDING},
}
_API: dict[WorkstreamStatus, set[WorkstreamStatus]] = {
    WorkstreamStatus.CREATED: {WorkstreamStatus.REQUIREMENTS_ACCEPTED},
    WorkstreamStatus.REQUIREMENTS_ACCEPTED: {WorkstreamStatus.MAPPING_PENDING},
    WorkstreamStatus.MAPPING_PENDING: {WorkstreamStatus.SPEC_PENDING},
    WorkstreamStatus.SPEC_PENDING: {WorkstreamStatus.CASES_PENDING},
    WorkstreamStatus.CASES_PENDING: {WorkstreamStatus.AUTOMATION_PENDING},
}


def _transition_map(workstream: Workstream) -> dict[WorkstreamStatus, set[WorkstreamStatus]]:
    return {**(_WEB if workstream.surface == Surface.WEB else _API), **_COMMON}


def _refresh_iteration_status(document: IterationDocument) -> None:
    statuses = {item.status for item in document.workstreams}
    if WorkstreamStatus.BLOCKED in statuses:
        document.status = IterationStatus.BLOCKED
    elif statuses and statuses <= {WorkstreamStatus.PROMOTED}:
        document.status = IterationStatus.PROMOTED
    elif statuses and statuses <= {WorkstreamStatus.PASSED, WorkstreamStatus.PROMOTED}:
        document.status = IterationStatus.ACCEPTED
    elif statuses <= {WorkstreamStatus.CREATED}:
        document.status = IterationStatus.CREATED
    else:
        document.status = IterationStatus.ACTIVE


def transition(
    document: IterationDocument,
    workstream_id: str,
    target: WorkstreamStatus,
    actor: Actor,
    *,
    reason: str | None = None,
) -> LifecycleEvent:
    """在内存文档上执行一步迁移；Store 负责锁内持久化。"""
    try:
        workstream = document.workstream(workstream_id)
    except KeyError as exc:
        raise StateError(str(exc)) from exc
    allowed = _transition_map(workstream).get(workstream.status, set())
    if target == WorkstreamStatus.BLOCKED:
        allowed = {WorkstreamStatus.BLOCKED}
    if workstream.status == WorkstreamStatus.BLOCKED and actor != Actor.USER:
        raise StateError("leaving blocked requires an explicit user action")
    if target not in allowed:
        raise StateError(
            f"illegal transition {workstream.status.value} -> {target.value} "
            f"for {workstream.surface.value} workstream"
        )
    if target == WorkstreamStatus.REQUIREMENTS_ACCEPTED:
        try:
            require_latest(
                document,
                workstream_id,
                ApprovalStage.REQUIREMENTS,
                ApprovalAction.ACCEPTED,
            )
        except ApprovalError as exc:
            raise StateError(str(exc)) from exc
    elif target == WorkstreamStatus.DESIGN_PENDING:
        pass
    elif target == WorkstreamStatus.AUTOMATION_PENDING:
        stage = ApprovalStage.DESIGN if workstream.surface == Surface.WEB else ApprovalStage.CASES
        try:
            require_latest(document, workstream_id, stage, ApprovalAction.ACCEPTED)
        except ApprovalError as exc:
            raise StateError(str(exc)) from exc
    elif target == WorkstreamStatus.SPEC_PENDING or target == WorkstreamStatus.CASES_PENDING:
        try:
            require_latest(document, workstream_id, ApprovalStage.MAPPING, ApprovalAction.ACCEPTED)
        except ApprovalError as exc:
            raise StateError(str(exc)) from exc
    elif target == WorkstreamStatus.EXECUTING:
        try:
            require_latest(
                document,
                workstream_id,
                ApprovalStage.ENVIRONMENT,
                ApprovalAction.PROVIDED,
            )
        except ApprovalError as exc:
            raise StateError(str(exc)) from exc
    if target == WorkstreamStatus.BLOCKED and not (reason or "").strip():
        raise StateError("blocked transition requires a non-empty reason")

    event = LifecycleEvent(
        id=f"event-{len(document.events) + 1:04d}",
        workstream_id=workstream_id,
        from_status=workstream.status,
        to_status=target,
        actor=actor,
        recorded_at=datetime.now(UTC),
        reason=reason.strip() if reason else None,
    )
    workstream.status = target
    workstream.revision += 1
    document.events.append(event)
    _refresh_iteration_status(document)
    return event
