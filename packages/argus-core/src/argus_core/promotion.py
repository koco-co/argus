"""从已验收 workstream 到 merged/promoted 的事实收口。"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .approvals import ApprovalError, require_latest  # pyright: ignore[reportMissingImports]
from .models import (  # pyright: ignore[reportMissingImports]
    Actor,
    ApprovalAction,
    ApprovalStage,
    IterationDocument,
    IterationStatus,
    LifecycleEvent,
    MergeFact,
    WorkstreamStatus,
)
from .parsing import load_yaml  # pyright: ignore[reportMissingImports]
from .store import IterationStore, StoreError  # pyright: ignore[reportMissingImports]


class PromotionError(ValueError):
    """promotion 缺少人工批准、外部事实或覆盖链。"""


_VERIFIER_KEY_ENV = "ARGUS_MERGE_VERIFIER_KEY"
_VERIFIER_CAPABILITY = object()
_MAX_VERIFIER_BYTES = 64 * 1024


def _signed_payload(fact: MergeFact) -> bytes:
    payload = fact.model_dump(mode="json", exclude={"verification_signature"}, exclude_none=True)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _verify_signature(fact: MergeFact, verifier: str) -> None:
    if fact.verifier != verifier or not fact.verification_signature:
        raise PromotionError("verifier output must bind verifier identity to the fact")
    key = os.environ.get(_VERIFIER_KEY_ENV)
    if not key:
        raise PromotionError(f"{_VERIFIER_KEY_ENV} is required to verify promotion evidence")
    expected = hmac.new(key.encode("utf-8"), _signed_payload(fact), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, fact.verification_signature):
        raise PromotionError("verifier evidence signature does not match the merge fact")


def verify_persisted_promotions(document: IterationDocument) -> None:
    """Re-check every persisted fact before a Store read or write succeeds."""
    for fact in document.promotions:
        _verify_signature(fact, "github-api")


def _safe_verifier_file(path: Path) -> Path:
    candidate = path if path.is_absolute() else Path.cwd() / path
    if "\x00" in str(candidate) or "\\" in str(candidate) or ".." in candidate.parts:
        raise PromotionError("verifier output path must not contain NUL or traversal")
    current = Path(candidate.anchor)
    for part in candidate.parts:
        current /= part
        if current.is_symlink():
            raise PromotionError("verifier output path must not pass through a symlink")
    if not candidate.is_file() or candidate.is_symlink():
        raise PromotionError("verifier output must be a regular local file")
    return candidate


class VerifiedMergeFact:
    """An immutable verifier result created only at the verifier boundary."""

    __slots__ = ("_fact_json", "_verifier")

    def __init__(self, fact: MergeFact, verifier: str, *, capability: object | None = None) -> None:
        if capability is not _VERIFIER_CAPABILITY:
            raise PromotionError("merge facts must be created by the verifier loader")
        _verify_signature(fact, verifier)
        object.__setattr__(
            self,
            "_fact_json",
            json.dumps(fact.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
        )
        object.__setattr__(self, "_verifier", verifier)

    @property
    def fact(self) -> MergeFact:
        # Return a fresh validated value so callers cannot mutate the signed
        # snapshot held by this wrapper.
        return MergeFact.model_validate_json(self._fact_json)

    @property
    def verifier(self) -> str:
        return self._verifier

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise PromotionError("merge verification is immutable")


def load_verified_merge_fact(path: Path) -> VerifiedMergeFact:
    """Load only the explicit output envelope of an external verifier."""
    path = _safe_verifier_file(path)
    try:
        payload: Any = load_yaml(path.read_bytes(), max_bytes=_MAX_VERIFIER_BYTES)
    except (OSError, UnicodeError, ValueError) as exc:
        raise PromotionError("verifier output is not readable YAML/JSON") from exc
    if not isinstance(payload, dict):
        raise PromotionError("verifier output must be an object")
    verifier = payload.get("verifier")
    if not isinstance(verifier, str) or not verifier.strip():
        raise PromotionError("verifier output must identify an independent verifier")
    if set(payload) != {"verifier", "fact"}:
        raise PromotionError("verifier output must contain exactly verifier and fact")
    raw_fact = payload.get("fact")
    if not isinstance(raw_fact, dict):
        raise PromotionError("verifier output must contain a fact object")
    try:
        fact = MergeFact.model_validate(raw_fact)
    except ValueError as exc:
        raise PromotionError("verifier output contains an invalid merge fact") from exc
    _verify_signature(fact, verifier)
    return VerifiedMergeFact(fact, verifier, capability=_VERIFIER_CAPABILITY)


def promote(
    store: IterationStore,
    iteration_id: str,
    workstream_id: str,
    fact: VerifiedMergeFact,
) -> None:
    """Accept only a fact wrapped by an independent verifier boundary."""
    if type(fact) is not VerifiedMergeFact:
        raise PromotionError("promotion requires an independent verifier result")
    if not isinstance(fact.fact, MergeFact):
        raise PromotionError("promotion verifier result contains an invalid fact")
    _verify_signature(fact.fact, fact.verifier)
    # Detach the transaction from the caller's mutable wrapper.  The signature
    # is checked before copying, and the copy is the only value captured by the
    # locked mutation below.
    verified_fact = fact.fact.model_copy(deep=True)

    def mutate(document: IterationDocument) -> None:
        if document.status == IterationStatus.PROMOTED:
            raise PromotionError("iteration is already promoted")
        if verified_fact.workstream_id != workstream_id:
            raise PromotionError("merge fact workstream_id does not match the target")
        if verified_fact.repository.strip() == "":
            raise PromotionError("merge fact repository must be non-empty")
        try:
            workstream = document.workstream(workstream_id)
        except KeyError as exc:
            raise PromotionError(str(exc)) from exc
        if workstream.status != WorkstreamStatus.PASSED:
            raise PromotionError("only a passed workstream can be promoted")
        passed_events = [
            event
            for event in document.events
            if event.workstream_id == workstream_id and event.to_status == WorkstreamStatus.PASSED
        ]
        if not passed_events or (
            verified_fact.merged_at < passed_events[-1].recorded_at
            or verified_fact.verified_at < passed_events[-1].recorded_at
        ):
            raise PromotionError("merge fact timestamps must follow the passed event")
        try:
            require_latest(
                document,
                workstream_id,
                ApprovalStage.EXECUTION,
                ApprovalAction.ACCEPTED,
            )
            require_latest(
                document,
                workstream_id,
                ApprovalStage.PROMOTION,
                ApprovalAction.APPROVED,
            )
        except ApprovalError as exc:
            raise PromotionError(str(exc)) from exc
        promoted_at = datetime.now(UTC)
        workstream.status = WorkstreamStatus.PROMOTED
        workstream.revision += 1
        document.events.append(
            LifecycleEvent(
                id=f"event-{len(document.events) + 1:04d}",
                workstream_id=workstream_id,
                from_status=WorkstreamStatus.PASSED,
                to_status=WorkstreamStatus.PROMOTED,
                actor=Actor.SCRIPT,
                recorded_at=promoted_at,
                reason="external GitHub merge fact verified",
            )
        )
        document.promotions.append(verified_fact)
        if all(item.status == WorkstreamStatus.PROMOTED for item in document.workstreams):
            object.__setattr__(document, "status", IterationStatus.PROMOTED)
        else:
            # Mixed passed/promoted workstreams remain accepted until the last
            # external fact arrives (the aggregate model's terminal pre-state).
            object.__setattr__(document, "status", IterationStatus.ACCEPTED)

    try:
        store.transact(iteration_id, mutate)
    except (StoreError, ValueError) as exc:
        raise PromotionError(str(exc)) from exc
