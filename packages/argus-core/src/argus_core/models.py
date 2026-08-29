"""Argus 0.2 的稳定控制面数据模型。

这里的模型只描述已持久化的事实，不描述任何 Agent、模型或执行器行为。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal

from pydantic import (  # pyright: ignore[reportMissingImports]
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)

SCHEMA_VERSION = "2.0"
_SHA256 = r"^[a-f0-9]{64}$"
_SHA1 = r"^[a-f0-9]{40}$"
_ID = r"^[a-z0-9][a-z0-9-]{1,63}$"


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    @field_validator("*", mode="after")
    @classmethod
    def timezone_aware_datetimes(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            raise ValueError("datetime fields must include a timezone")
        return value


class Surface(StrEnum):
    """项目测试面；v2 明确把 web 与 api 作为独立 workstream。"""

    WEB = "web"
    API = "api"


class WorkstreamStatus(StrEnum):
    CREATED = "created"
    REQUIREMENTS_ACCEPTED = "requirements_accepted"
    DESIGN_PENDING = "design_pending"
    MAPPING_PENDING = "mapping_pending"
    SPEC_PENDING = "spec_pending"
    CASES_PENDING = "cases_pending"
    AUTOMATION_PENDING = "automation_pending"
    READY = "ready"
    EXECUTING = "executing"
    PASSED = "passed"
    BUDGET_EXCEEDED = "budget_exceeded"
    ESCALATED = "escalated"
    BLOCKED = "blocked"
    PROMOTED = "promoted"


class IterationStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    ACCEPTED = "accepted"
    PROMOTED = "promoted"
    BLOCKED = "blocked"


class ApprovalStage(StrEnum):
    REQUIREMENTS = "requirements"
    DESIGN = "design"
    MAPPING = "mapping"
    CASES = "cases"
    ENVIRONMENT = "environment"
    EXECUTION = "execution"
    PROMOTION = "promotion"
    SKILL_CHANGE = "skill_change"


class ApprovalAction(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PROVIDED = "provided"
    APPROVED = "approved"
    DELEGATED = "delegated"


class Actor(StrEnum):
    USER = "user"
    AGENT = "agent"
    SCRIPT = "script"


class DelegationGrant(_ContractModel):
    """结构化的用户授权；M1 和 promotion 永远不在 scope 中。"""

    id: str = Field(pattern=r"^delegation-[a-z0-9][a-z0-9-]{1,63}$")
    granted_by: Literal["user"] = "user"
    basis: str = Field(min_length=1)
    basis_sha256: str = Field(pattern=_SHA256)
    scope: list[ApprovalStage] = Field(min_length=1)
    granted_at: datetime
    expires_at: datetime

    @field_validator("scope")
    @classmethod
    def unique_delegation_scope(cls, value: list[ApprovalStage]) -> list[ApprovalStage]:
        if len(set(value)) != len(value):
            raise ValueError("delegation scope must not contain duplicates")
        forbidden = {ApprovalStage.REQUIREMENTS, ApprovalStage.PROMOTION}
        if forbidden.intersection(value):
            raise ValueError("requirements and promotion cannot be delegated")
        return value

    @model_validator(mode="after")
    def validate_grant(self) -> DelegationGrant:
        import hashlib

        if hashlib.sha256(self.basis.encode("utf-8")).hexdigest() != self.basis_sha256:
            raise ValueError("basis_sha256 does not match basis")
        if self.expires_at <= self.granted_at:
            raise ValueError("expires_at must be after granted_at")
        return self


class Approval(_ContractModel):
    """一条确认事实；固定矩阵在 ``validate_matrix`` 中执行。"""

    id: str = Field(pattern=_ID)
    workstream_id: str = Field(pattern=_ID)
    stage: ApprovalStage
    action: ApprovalAction
    actor: Actor
    artifact: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=_SHA256)
    recorded_at: datetime
    note: str | None = None
    delegation_id: str | None = Field(default=None, pattern=_ID)

    _NONEMPTY_NOTE: ClassVar[str] = "delegated approval requires a non-empty note"

    @model_validator(mode="after")
    def validate_matrix(self) -> Approval:
        allowed: dict[ApprovalStage, set[tuple[ApprovalAction, Actor]]] = {
            ApprovalStage.REQUIREMENTS: {
                (ApprovalAction.ACCEPTED, Actor.USER),
                (ApprovalAction.REJECTED, Actor.USER),
            },
            ApprovalStage.DESIGN: {
                (ApprovalAction.ACCEPTED, Actor.USER),
                (ApprovalAction.REJECTED, Actor.USER),
                (ApprovalAction.DELEGATED, Actor.AGENT),
            },
            ApprovalStage.MAPPING: {
                (ApprovalAction.ACCEPTED, Actor.USER),
                (ApprovalAction.REJECTED, Actor.USER),
                (ApprovalAction.DELEGATED, Actor.AGENT),
            },
            ApprovalStage.CASES: {
                (ApprovalAction.ACCEPTED, Actor.USER),
                (ApprovalAction.REJECTED, Actor.USER),
                (ApprovalAction.DELEGATED, Actor.AGENT),
            },
            ApprovalStage.ENVIRONMENT: {
                (ApprovalAction.PROVIDED, Actor.USER),
                (ApprovalAction.REJECTED, Actor.USER),
                (ApprovalAction.DELEGATED, Actor.AGENT),
            },
            ApprovalStage.EXECUTION: {
                (ApprovalAction.ACCEPTED, Actor.USER),
                (ApprovalAction.REJECTED, Actor.USER),
                (ApprovalAction.DELEGATED, Actor.AGENT),
            },
            ApprovalStage.PROMOTION: {
                (ApprovalAction.APPROVED, Actor.USER),
                (ApprovalAction.REJECTED, Actor.USER),
            },
            ApprovalStage.SKILL_CHANGE: {
                (ApprovalAction.APPROVED, Actor.USER),
                (ApprovalAction.REJECTED, Actor.USER),
                (ApprovalAction.DELEGATED, Actor.AGENT),
            },
        }
        if self.stage == ApprovalStage.REQUIREMENTS and self.action == ApprovalAction.DELEGATED:
            raise ValueError("requirements acceptance cannot be delegated")
        if (self.action, self.actor) not in allowed[self.stage]:
            raise ValueError(
                f"{self.stage.value} does not allow {self.action.value}/{self.actor.value}"
            )
        if self.action == ApprovalAction.DELEGATED:
            if not self.delegation_id:
                raise ValueError("delegated approval requires delegation_id")
            if not isinstance(self.note, str) or not self.note.strip():
                raise ValueError(self._NONEMPTY_NOTE)
        elif self.delegation_id is not None:
            raise ValueError("delegation_id is only valid for delegated approvals")
        return self


class Workstream(_ContractModel):
    id: str = Field(pattern=_ID)
    surface: Surface
    status: WorkstreamStatus = WorkstreamStatus.CREATED
    revision: int = Field(default=0, ge=0)
    metadata: dict[str, str] = Field(default_factory=dict)


class LifecycleEvent(_ContractModel):
    id: str = Field(pattern=_ID)
    workstream_id: str = Field(pattern=_ID)
    from_status: WorkstreamStatus
    to_status: WorkstreamStatus
    actor: Actor
    recorded_at: datetime
    reason: str | None = None


class MergeFact(_ContractModel):
    """由外部 GitHub 事实核验得到的单个 workstream promotion 载荷。"""

    workstream_id: str = Field(pattern=_ID)
    provider: Literal["github"] = "github"
    repository: str = Field(pattern=r"^[^/\s]+/[^/\s]+$")
    pull_request: PositiveInt
    base_ref: Literal["release"] = "release"
    merged: Literal[True] = True
    merge_sha: str = Field(pattern=_SHA1)
    merged_at: datetime
    source_url: str = Field(min_length=1)
    verified_at: datetime


class IterationDocument(_ContractModel):
    schema_version: Literal["2.0"] = SCHEMA_VERSION
    iteration_id: str = Field(pattern=_ID)
    status: IterationStatus = IterationStatus.CREATED
    revision: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime
    workstreams: list[Workstream] = Field(min_length=1)
    approvals: list[Approval] = Field(default_factory=list)
    events: list[LifecycleEvent] = Field(default_factory=list)
    delegation: DelegationGrant | None = None
    promotions: list[MergeFact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_ids(self) -> IterationDocument:
        workstream_ids = [item.id for item in self.workstreams]
        if len(set(workstream_ids)) != len(workstream_ids):
            raise ValueError("workstream ids must be unique")
        approval_ids = [item.id for item in self.approvals]
        if len(set(approval_ids)) != len(approval_ids):
            raise ValueError("approval ids must be unique")
        event_ids = [item.id for item in self.events]
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("event ids must be unique")
        known_workstream_ids = set(workstream_ids)
        for approval in self.approvals:
            if approval.workstream_id not in known_workstream_ids:
                raise ValueError("approval references an unknown workstream")
        for event in self.events:
            if event.workstream_id not in known_workstream_ids:
                raise ValueError("event references an unknown workstream")
        promotion_ids = [item.workstream_id for item in self.promotions]
        if any(item not in known_workstream_ids for item in promotion_ids):
            raise ValueError("promotion fact references an unknown workstream")
        if len(set(promotion_ids)) != len(promotion_ids):
            raise ValueError("a workstream can have only one promotion fact")
        promoted_ids = {
            item.id for item in self.workstreams if item.status == WorkstreamStatus.PROMOTED
        }
        if set(promotion_ids) != promoted_ids:
            raise ValueError("promotion facts must match promoted workstreams")
        expected_status = self._expected_status()
        if self.status != expected_status:
            raise ValueError(
                f"iteration status {self.status.value} does not match aggregate "
                f"{expected_status.value}"
            )
        return self

    def _expected_status(self) -> IterationStatus:
        statuses = {item.status for item in self.workstreams}
        if WorkstreamStatus.BLOCKED in statuses:
            return IterationStatus.BLOCKED
        if statuses <= {WorkstreamStatus.PROMOTED}:
            return IterationStatus.PROMOTED
        if statuses <= {WorkstreamStatus.PASSED, WorkstreamStatus.PROMOTED}:
            return IterationStatus.ACCEPTED
        if statuses <= {WorkstreamStatus.CREATED}:
            return IterationStatus.CREATED
        return IterationStatus.ACTIVE

    def workstream(self, workstream_id: str) -> Workstream:
        for workstream in self.workstreams:
            if workstream.id == workstream_id:
                return workstream
        raise KeyError(f"unknown workstream: {workstream_id}")
