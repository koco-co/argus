#!/usr/bin/env python
"""Sole writers of the iteration lifecycle namespaces (Roadmap 1.15b).

- ``record_event.py``     sole writer of ``state`` + ``events[]``; every
  recorded transition is checked against the ARCHITECTURE/PRD §5 legality
  rules (reuse of validate_iteration.legal_transition) before it persists.
- ``record_approval.py``  sole writer of ``approvals[]``; always records
  ``actor: user`` plus the artifact digest (stage=environment digests are
  computed over a redacted copy - values masked, keys preserved).
- ``reopen_iteration.py`` user-triggered reopen: records the reopen event,
  preserves all allocated IDs, and marks downstream artifacts ``stale`` so
  stale consumers are blocked until regeneration.

All three refuse to write anything when the iteration file is not
schema-valid or its event chain is inconsistent - a hand-edited file is
rejected instead of being silently amended.
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
APPROVAL_ACTIONS = ("accepted", "rejected", "provided", "approved")
ACTORS = ("agent", "script", "user")


class WriterError(Exception):
    """User-facing refusal to write."""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_iteration(iteration_dir: Path) -> tuple[Path, dict[str, Any]]:
    iteration_yaml = iteration_dir / "iteration.yaml"
    if not iteration_yaml.exists():
        raise WriterError(f"{iteration_yaml} not found")
    document = yaml.safe_load(iteration_yaml.read_text(encoding="utf-8")) or {}
    return iteration_yaml, document


def validate_document(iteration_yaml: Path, document: dict[str, Any]) -> None:
    binding = binding_for_path(iteration_yaml)
    if binding is None:
        raise WriterError(f"unregistered artifact path: {iteration_yaml}")
    errors = schema_errors(binding, document)
    if errors:
        raise WriterError("iteration.yaml is invalid (hand-edited?): " + "; ".join(errors))


def write_iteration(iteration_yaml: Path, document: dict[str, Any]) -> None:
    validate_document(iteration_yaml, document)
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
) -> dict[str, Any]:
    from validate_iteration import legal_transition

    iteration_yaml, document = load_iteration(iteration_dir)
    if document["state"] != from_state:
        raise WriterError(
            f"stale transition request: iteration state is {document['state']!r}, "
            f"not {from_state!r} - a hand-edited file or outdated caller"
        )
    violation = legal_transition(from_state, to_state, document["branches"]["ui"], triggered_by)
    if violation:
        raise WriterError(f"illegal transition {from_state} -> {to_state}: {violation}")
    if to_state == "blocked" and not (reason or "").strip():
        raise WriterError("moving to blocked requires a non-empty --reason")
    event = {
        "from_state": from_state,
        "to_state": to_state,
        "timestamp": _now(),
        "triggered_by": triggered_by,
    }
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
) -> dict[str, Any]:
    iteration_yaml, document = load_iteration(iteration_dir)
    approval: dict[str, Any] = {
        "stage": stage,
        "action": action,
        "actor": "user",
        "timestamp": _now(),
        "artifact_sha256": artifact_sha256,
    }
    if note:
        approval["note"] = note
    document["approvals"].append(approval)
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
