"""Argus 0.2 的稳定控制面数据模型。

这里的模型只描述已持久化的事实，不描述任何 Agent、模型或执行器行为。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import (  # pyright: ignore[reportMissingImports]
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

SCHEMA_VERSION = "2.0"
_SHA256 = r"^[a-f0-9]{64}$"
_SHA1 = r"^[a-f0-9]{40}$"
_SIGNATURE = r"^[a-f0-9]{64}$"
_ID = r"^[a-z0-9][a-z0-9-]{1,63}$"
_GITHUB_REPOSITORY = r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})$"
_SENSITIVE_METADATA_KEYS = {
    "password",
    "secret",
    "token",
    "apikey",
    "accesstoken",
    "authorization",
    "cookie",
    "privatekey",
    "credential",
    "credentials",
    "clientsecret",
    "bearer",
    "auth",
}


def _sensitive_metadata_key(key: object) -> bool:
    normalized = "".join(character for character in str(key).lower() if character.isalnum())
    return normalized in _SENSITIVE_METADATA_KEYS or normalized.endswith(
        ("password", "secret", "token", "apikey", "credential", "authorization", "cookie")
    )


def _contains_sensitive_metadata(value: object, depth: int = 0) -> bool:
    if depth > 32:
        return True
    if isinstance(value, Mapping):
        return any(
            _sensitive_metadata_key(key) or _contains_sensitive_metadata(item, depth + 1)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_sensitive_metadata(item, depth + 1) for item in value)
    if isinstance(value, str):
        try:
            parts = urlsplit(value)
        except ValueError:
            return False
        return bool(
            parts.username
            or parts.password
            or any(
                _sensitive_metadata_key(key)
                for key, _ in parse_qsl(parts.query, keep_blank_values=True)
            )
        )
    return False


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    @field_validator("*", mode="after")
    @classmethod
    def timezone_aware_datetimes(cls, value: Any) -> Any:
        if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
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
        if self.granted_at > datetime.now(UTC):
            raise ValueError("granted_at cannot be in the future")
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

    @field_validator("artifact")
    @classmethod
    def safe_artifact_reference(cls, value: str) -> str:
        if (
            value.startswith(("/", "\\"))
            or (len(value) > 1 and value[1] == ":")
            or "\x00" in value
            or "\\" in value
            or any(part == ".." for part in value.split("/"))
        ):
            raise ValueError("artifact must be a safe relative path")
        return value

    @model_validator(mode="after")
    def validate_matrix(self) -> Approval:
        if self.recorded_at > datetime.now(UTC):
            raise ValueError("approval recorded_at cannot be in the future")
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
    revision: StrictInt = Field(default=0, ge=0)
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_sensitive_metadata(self) -> Workstream:
        if _contains_sensitive_metadata(self.metadata):
            raise ValueError("workstream metadata must not contain credential-shaped data")
        return self


class LifecycleEvent(_ContractModel):
    id: str = Field(pattern=_ID)
    workstream_id: str = Field(pattern=_ID)
    from_status: WorkstreamStatus
    to_status: WorkstreamStatus
    actor: Actor
    recorded_at: datetime
    reason: str | None = None

    @model_validator(mode="after")
    def reject_future_event(self) -> LifecycleEvent:
        if self.recorded_at > datetime.now(UTC):
            raise ValueError("event recorded_at cannot be in the future")
        return self


class MergeFact(_ContractModel):
    """由外部 GitHub 事实核验得到的单个 workstream promotion 载荷。"""

    workstream_id: str = Field(pattern=_ID)
    provider: Literal["github"] = "github"
    repository: str = Field(pattern=_GITHUB_REPOSITORY)
    pull_request: StrictInt = Field(gt=0)
    base_ref: Literal["release"] = "release"
    merged: Literal[True] = True
    merge_sha: str = Field(pattern=_SHA1)
    merged_at: datetime
    source_url: str = Field(min_length=1)
    verified_at: datetime
    # External verifier evidence is persisted with the promotion fact. The
    # pair is optional for parsing legacy/unverified data, but promotion's
    # verifier boundary requires both fields.
    verifier: str | None = Field(default=None, pattern=r"^github-api$")
    verification_signature: str | None = Field(default=None, pattern=_SIGNATURE)

    @model_validator(mode="after")
    def validate_external_binding(self) -> MergeFact:
        expected_url = f"https://github.com/{self.repository}/pull/{self.pull_request}"
        if self.source_url != expected_url:
            raise ValueError("source_url must be the canonical GitHub pull request URL")
        if (self.verifier is None) != (self.verification_signature is None):
            raise ValueError("verifier and verification_signature must be provided together")
        now = datetime.now(UTC)
        if self.merged_at > now or self.verified_at > now:
            raise ValueError("merge fact timestamps cannot be in the future")
        if self.verified_at < self.merged_at:
            raise ValueError("verified_at must not precede merged_at")
        return self


_WEB_TRANSITIONS: dict[WorkstreamStatus, frozenset[WorkstreamStatus]] = {
    WorkstreamStatus.CREATED: frozenset({WorkstreamStatus.REQUIREMENTS_ACCEPTED}),
    WorkstreamStatus.REQUIREMENTS_ACCEPTED: frozenset({WorkstreamStatus.DESIGN_PENDING}),
    WorkstreamStatus.DESIGN_PENDING: frozenset({WorkstreamStatus.AUTOMATION_PENDING}),
}
_API_TRANSITIONS: dict[WorkstreamStatus, frozenset[WorkstreamStatus]] = {
    WorkstreamStatus.CREATED: frozenset({WorkstreamStatus.REQUIREMENTS_ACCEPTED}),
    WorkstreamStatus.REQUIREMENTS_ACCEPTED: frozenset({WorkstreamStatus.MAPPING_PENDING}),
    WorkstreamStatus.MAPPING_PENDING: frozenset({WorkstreamStatus.SPEC_PENDING}),
    WorkstreamStatus.SPEC_PENDING: frozenset({WorkstreamStatus.CASES_PENDING}),
    WorkstreamStatus.CASES_PENDING: frozenset({WorkstreamStatus.AUTOMATION_PENDING}),
}
_COMMON_TRANSITIONS: dict[WorkstreamStatus, frozenset[WorkstreamStatus]] = {
    WorkstreamStatus.AUTOMATION_PENDING: frozenset({WorkstreamStatus.READY}),
    WorkstreamStatus.READY: frozenset({WorkstreamStatus.EXECUTING}),
    WorkstreamStatus.EXECUTING: frozenset(
        {
            WorkstreamStatus.PASSED,
            WorkstreamStatus.BUDGET_EXCEEDED,
            WorkstreamStatus.ESCALATED,
            WorkstreamStatus.BLOCKED,
        }
    ),
    WorkstreamStatus.BLOCKED: frozenset({WorkstreamStatus.CREATED}),
    WorkstreamStatus.PASSED: frozenset({WorkstreamStatus.PROMOTED}),
}

_APPROVAL_WINDOW_STATUSES: dict[ApprovalStage, tuple[WorkstreamStatus, ...]] = {
    ApprovalStage.REQUIREMENTS: (WorkstreamStatus.CREATED,),
    ApprovalStage.DESIGN: (WorkstreamStatus.DESIGN_PENDING,),
    ApprovalStage.MAPPING: (WorkstreamStatus.MAPPING_PENDING,),
    ApprovalStage.CASES: (WorkstreamStatus.CASES_PENDING,),
    ApprovalStage.ENVIRONMENT: (WorkstreamStatus.READY,),
    ApprovalStage.EXECUTION: (
        WorkstreamStatus.PASSED,
        WorkstreamStatus.BUDGET_EXCEEDED,
        WorkstreamStatus.ESCALATED,
    ),
    ApprovalStage.PROMOTION: (WorkstreamStatus.PASSED,),
}


class IterationDocument(_ContractModel):
    schema_version: Literal["2.0"] = SCHEMA_VERSION
    iteration_id: str = Field(pattern=_ID)
    status: IterationStatus = IterationStatus.CREATED
    revision: StrictInt = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime
    workstreams: list[Workstream] = Field(min_length=1)
    approvals: list[Approval] = Field(default_factory=list)
    events: list[LifecycleEvent] = Field(default_factory=list)
    delegation: DelegationGrant | None = None
    promotions: list[MergeFact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_sensitive_metadata(self) -> IterationDocument:
        if _contains_sensitive_metadata(self.metadata):
            raise ValueError("iteration metadata must not contain credential-shaped data")
        return self

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
        self._validate_lifecycle()
        return self

    def _approval_window_start(
        self,
        workstream_id: str,
        stage: ApprovalStage,
        *,
        before: datetime | None = None,
    ) -> datetime | None:
        starts: list[datetime] = []
        if stage == ApprovalStage.REQUIREMENTS:
            starts.append(self.created_at)
            # A user resume from blocked returns the workstream to CREATED;
            # that is a fresh requirements window and invalidates approvals
            # from the prior lifecycle attempt.
            starts.extend(
                event.recorded_at
                for event in self.events
                if event.workstream_id == workstream_id
                and event.to_status == WorkstreamStatus.CREATED
                and (before is None or event.recorded_at <= before)
            )
        for event in self.events:
            if event.workstream_id != workstream_id:
                continue
            if event.to_status not in _APPROVAL_WINDOW_STATUSES.get(stage, ()):
                continue
            if before is None or event.recorded_at <= before:
                starts.append(event.recorded_at)
        return max(starts) if starts else None

    def _statuses_at(self, moment: datetime) -> dict[str, WorkstreamStatus]:
        statuses = {item.id: WorkstreamStatus.CREATED for item in self.workstreams}
        for event in self.events:
            if event.recorded_at > moment:
                break
            statuses[event.workstream_id] = event.to_status
        return statuses

    def _validate_lifecycle(self) -> None:
        """Replay events so aggregate fields cannot be edited around the chain."""
        expected = {item.id: WorkstreamStatus.CREATED for item in self.workstreams}
        now = datetime.now(UTC)
        previous_event_at = self.created_at
        for index, event in enumerate(self.events):
            if event.recorded_at > now:
                raise ValueError(f"events[{index}].recorded_at cannot be in the future")
            if event.recorded_at < previous_event_at:
                raise ValueError("lifecycle events must be in append-time order")
            previous_event_at = event.recorded_at
            if event.recorded_at < self.created_at:
                raise ValueError(f"events[{index}].recorded_at precedes iteration creation")
            current = expected[event.workstream_id]
            if event.from_status != current:
                raise ValueError(
                    f"events[{index}] from_status does not match the workstream event chain"
                )
            workstream = self.workstream(event.workstream_id)
            transitions = {
                **(_WEB_TRANSITIONS if workstream.surface == Surface.WEB else _API_TRANSITIONS),
                **_COMMON_TRANSITIONS,
            }
            allowed_targets = transitions.get(current, frozenset())
            if event.to_status not in allowed_targets:
                raise ValueError(
                    f"events[{index}] contains an illegal {current.value} -> "
                    f"{event.to_status.value} transition"
                )
            if event.to_status == WorkstreamStatus.BLOCKED and not (event.reason or "").strip():
                raise ValueError("blocked lifecycle events require a non-empty reason")
            if event.from_status == WorkstreamStatus.BLOCKED and event.actor != Actor.USER:
                raise ValueError("leaving blocked requires an explicit user event")
            if event.to_status == WorkstreamStatus.PROMOTED and event.actor != Actor.SCRIPT:
                raise ValueError("promotion lifecycle events must be written by script")

            required_gates: list[tuple[ApprovalStage, ApprovalAction]] = []
            required_gate = {
                WorkstreamStatus.REQUIREMENTS_ACCEPTED: (
                    ApprovalStage.REQUIREMENTS,
                    ApprovalAction.ACCEPTED,
                ),
                WorkstreamStatus.SPEC_PENDING: (
                    ApprovalStage.MAPPING,
                    ApprovalAction.ACCEPTED,
                ),
                WorkstreamStatus.EXECUTING: (
                    ApprovalStage.ENVIRONMENT,
                    ApprovalAction.PROVIDED,
                ),
                WorkstreamStatus.PROMOTED: (
                    ApprovalStage.PROMOTION,
                    ApprovalAction.APPROVED,
                ),
            }.get(event.to_status)
            if required_gate is not None:
                required_gates.append(required_gate)
            if event.to_status == WorkstreamStatus.AUTOMATION_PENDING:
                required_gates.append(
                    (
                        ApprovalStage.DESIGN
                        if workstream.surface == Surface.WEB
                        else ApprovalStage.CASES,
                        ApprovalAction.ACCEPTED,
                    )
                )
            if event.to_status == WorkstreamStatus.PROMOTED:
                required_gates.insert(
                    0,
                    (ApprovalStage.EXECUTION, ApprovalAction.ACCEPTED),
                )
            for stage, action in required_gates:
                window_start = self._approval_window_start(
                    event.workstream_id,
                    stage,
                    before=event.recorded_at,
                )
                candidates = [
                    approval
                    for approval in self.approvals
                    if approval.workstream_id == event.workstream_id
                    and approval.stage == stage
                    and window_start is not None
                    and window_start <= approval.recorded_at <= event.recorded_at
                ]
                # The append order is the audit order.  A later rejection must
                # invalidate an earlier acceptance; looking for any matching
                # approval would allow a stale decision to reopen a gate.
                latest = candidates[-1] if candidates else None
                if (
                    latest is None
                    or (latest.action != action and latest.action != ApprovalAction.DELEGATED)
                    or (stage == ApprovalStage.REQUIREMENTS and latest.actor != Actor.USER)
                ):
                    raise ValueError(
                        f"event {event.to_status.value} requires the latest valid "
                        f"{stage.value} approval"
                    )
            if event.to_status == WorkstreamStatus.PROMOTED:
                matching_facts = [
                    fact for fact in self.promotions if fact.workstream_id == event.workstream_id
                ]
                if not matching_facts or any(
                    fact.verifier is None or fact.verification_signature is None
                    for fact in matching_facts
                ):
                    raise ValueError("promotion event requires persisted verifier evidence")
                if any(fact.verified_at > event.recorded_at for fact in matching_facts):
                    raise ValueError("promotion verifier evidence must precede promotion event")
                passed_events = [
                    prior
                    for prior in self.events[:index]
                    if prior.workstream_id == event.workstream_id
                    and prior.to_status == WorkstreamStatus.PASSED
                ]
                if not passed_events or any(
                    fact.merged_at < passed_events[-1].recorded_at
                    or fact.verified_at < passed_events[-1].recorded_at
                    for fact in matching_facts
                ):
                    raise ValueError("promotion verifier evidence must follow the passed event")
            expected[event.workstream_id] = event.to_status
        for workstream in self.workstreams:
            if expected[workstream.id] != workstream.status:
                raise ValueError(
                    f"workstream {workstream.id} status does not match its event chain"
                )
            event_count = sum(1 for item in self.events if item.workstream_id == workstream.id)
            if workstream.revision != event_count:
                raise ValueError(
                    f"workstream {workstream.id} revision does not match its event chain"
                )

        if not self.events and self.status != IterationStatus.CREATED:
            raise ValueError("non-created iteration must contain lifecycle events")
        if self.revision < len(self.events):
            raise ValueError("iteration revision cannot be lower than its event count")
        if self.updated_at < self.created_at or self.updated_at > now:
            raise ValueError("iteration timestamps must be ordered and not in the future")
        latest_recorded_at = max(
            [
                self.created_at,
                *(event.recorded_at for event in self.events),
                *(approval.recorded_at for approval in self.approvals),
                *(fact.verified_at for fact in self.promotions),
                *((self.delegation.granted_at,) if self.delegation is not None else ()),
            ]
        )
        if self.updated_at < latest_recorded_at:
            raise ValueError("updated_at must not precede the latest lifecycle fact")
        previous_approval_at = self.created_at
        for index, approval in enumerate(self.approvals):
            if approval.recorded_at > now:
                raise ValueError(f"approvals[{index}].recorded_at cannot be in the future")
            if approval.recorded_at < self.created_at:
                raise ValueError(f"approvals[{index}].recorded_at precedes iteration creation")
            if approval.recorded_at < previous_approval_at:
                raise ValueError("approvals must be in append-time order")
            previous_approval_at = approval.recorded_at
            if approval.action == ApprovalAction.DELEGATED:
                grant = self.delegation
                if (
                    grant is None
                    or approval.delegation_id != grant.id
                    or approval.stage not in grant.scope
                    or not grant.granted_at <= approval.recorded_at <= grant.expires_at
                ):
                    raise ValueError(
                        f"delegated {approval.stage.value} approval is not bound to a valid grant"
                    )
            if approval.stage == ApprovalStage.PROMOTION:
                statuses_at_approval = self._statuses_at(approval.recorded_at)
                if not (
                    statuses_at_approval[approval.workstream_id] == WorkstreamStatus.PASSED
                    and set(statuses_at_approval.values())
                    <= {WorkstreamStatus.PASSED, WorkstreamStatus.PROMOTED}
                ):
                    raise ValueError("promotion approval is outside the accepted lifecycle window")
            window_start = self._approval_window_start(
                approval.workstream_id,
                approval.stage,
                before=approval.recorded_at,
            )
            if approval.stage in _APPROVAL_WINDOW_STATUSES and window_start is None:
                raise ValueError(f"{approval.stage.value} approval is outside its lifecycle window")
            target = {
                ApprovalStage.REQUIREMENTS: WorkstreamStatus.REQUIREMENTS_ACCEPTED,
                ApprovalStage.MAPPING: WorkstreamStatus.SPEC_PENDING,
                ApprovalStage.CASES: WorkstreamStatus.AUTOMATION_PENDING,
                ApprovalStage.DESIGN: WorkstreamStatus.AUTOMATION_PENDING,
                ApprovalStage.ENVIRONMENT: WorkstreamStatus.EXECUTING,
                # Acceptance is an iteration aggregate decision and has no
                # workstream status transition in v2.
                ApprovalStage.PROMOTION: WorkstreamStatus.PROMOTED,
            }.get(approval.stage)
            if target is not None and window_start is not None:
                # Compare only with the target event in this lifecycle
                # window.  A resume from blocked creates a fresh CREATED
                # window, so an old target event must not invalidate a new
                # requirements approval.
                event_at = max(
                    (
                        event.recorded_at
                        for event in self.events
                        if event.workstream_id == approval.workstream_id
                        and event.to_status == target
                        and event.recorded_at >= window_start
                    ),
                    default=None,
                )
                if event_at is not None and approval.recorded_at > event_at:
                    raise ValueError(
                        f"approval {approval.id} was recorded after its lifecycle migration"
                    )
        for index, fact in enumerate(self.promotions):
            if fact.verified_at > now or fact.verified_at < fact.merged_at:
                raise ValueError(f"promotions[{index}] has invalid verification time")
            if fact.merged_at < self.created_at or fact.verified_at < self.created_at:
                raise ValueError(f"promotions[{index}] precedes iteration creation")

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
