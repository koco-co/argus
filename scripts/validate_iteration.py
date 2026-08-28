#!/usr/bin/env python
"""Iteration state-machine + staleness validator (Roadmap 1.3).

Pure check by contract (PRD §6 / Roadmap 1.3): prints verdicts and proposed
`stale` status rewrites as a diff and exits non-zero; working-tree mutation
happens only via explicit ``--fix`` (committed separately by the user or a
bot). Pre-commit and CI always run in check mode.

Enforced semantics (DATA_MODEL §11 / PRD §5):
- transition legality against the branch-aware PRD §5 route graph, including
  any→blocked (with blocked_reason) and user-only unblocking, plus the
  user-triggered reopen edges;
- ``requirements_mapped`` only on the API branch, ``test_points_review`` only
  on the UI branch; the both-true Hybrid combination is rejected outright;
- events[] chain consistency — ``state`` must equal the last event's
  ``to_state`` (hand-editing either is a validation error; the writer is
  scripts/record_event.py, Roadmap 1.15b);
- approval integrity: gate states require the latest stage approval to carry
  the expected action, and requirements/test-point/exemption approvals must
  match the current artifact bytes;
- single-in-progress rule across the repo (ARCHITECTURE §5.1);
- staleness verdicts computed from the full ``generated_from`` chain: an
  upstream hash mismatch downgrades the artifact to ``stale`` (check mode
  shows the rewrite, ``--fix`` writes it); consuming stale inputs downstream
  is reported;
- run-summary invariants: attempt numbers consecutive from 1, unique;
  ``passed`` ⇒ last attempt passes; ``failed`` ⇒ last attempt documents the
  failure; ``escalated`` ⇒ escalation with a non-trivial reason class;
  recorded ``diff_ref`` paths must resolve.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from _registry_lib import REPO_ROOT, RegistryError, binding_for_path, validate_path

_REGISTRY = REPO_ROOT / "scripts" / "schema_registry.yaml"

# PRD §5 routes. Front: shared prefix. Mid: branch-specific. Tail: shared.
_FRONT = {
    "created": {"requirements_clarifying"},
    "requirements_clarifying": {"requirements_accepted"},
    "requirements_accepted": set(),
}
_UI_MID = {
    "requirements_accepted": {"requirements_clarifying", "test_points_review"},
    "test_points_review": {"test_points_accepted"},
    "test_points_accepted": {"test_points_review", "functional_cases_generating"},
    "functional_cases_generating": {"functional_cases_exported"},
    "functional_cases_exported": {"web_automation_generating"},
    "web_automation_generating": {"web_automation_generated", "blocked"},
    "web_automation_generated": {"env_pending"},
}
_API_MID = {
    "requirements_accepted": {"requirements_clarifying", "requirements_mapped"},
    "requirements_mapped": {"spec_normalizing"},
    "spec_normalizing": {"spec_valid"},
    "spec_valid": {"api_cases_generating"},
    "api_cases_generating": {"api_cases_exported"},
    "api_cases_exported": {"api_automation_generating"},
    "api_automation_generating": {"api_automation_generated"},
    "api_automation_generated": {"env_pending"},
}
_TAIL = {
    "env_pending": {"env_configured"},
    "env_configured": {"executing"},
    "executing": {"execution_passed", "execution_budget_exceeded", "escalated"},
    "execution_passed": {"acceptance_pending"},
    "execution_budget_exceeded": {"acceptance_pending"},
    "escalated": {"acceptance_pending"},
    "acceptance_pending": {"accepted"},
    "accepted": {"merged"},
    "merged": set(),
}
# 进入下列状态前必须具备的用户批准记录：
# to_state -> ((approvals[].stage, approvals[].action), ...)
_APPROVAL_GATES = {
    "requirements_accepted": (("requirements", "accepted"),),
    "requirements_mapped": (("exemptions", "accepted"),),
    "test_points_accepted": (
        ("test_points", "accepted"),
        ("exemptions", "accepted"),
    ),
    "env_configured": (("environment", "provided"),),
    "accepted": (("acceptance", "accepted"),),
}
_APPROVAL_ARTIFACTS = {
    "requirements": "requirements.yaml",
    "exemptions": "exemptions.yaml",
    "test_points": "test_points.yaml",
}


def successors(state: str, ui: bool) -> set[str]:
    graph: dict[str, set[str]] = {}
    for layer in (_FRONT, _UI_MID if ui else _API_MID, _TAIL):
        for source, targets in layer.items():
            graph.setdefault(source, set()).update(targets)
    graph.setdefault("blocked", set())
    # any state may become blocked; leaving blocked needs a user action but is
    # otherwise unconstrained (return path is chosen by the user/agent pair)
    for source in list(graph):
        if source != "blocked":
            graph[source].add("blocked")
        graph["blocked"].add(source)
    return graph.get(state, set())


def legal_transition(from_state: str, to_state: str, ui: bool, triggered_by: str) -> str | None:
    """Return None when legal, else a human-readable reason."""
    if to_state == "blocked":
        return None  # any state may block; blocked_reason completeness checked separately
    if from_state == "blocked":
        return (
            None
            if triggered_by == "user"
            else ("leaving blocked requires a user action (triggered_by=user)")
        )
    if (
        triggered_by == "user"
        and to_state == "requirements_clarifying"
        and from_state not in ("created", "requirements_clarifying")
    ):
        # reopen protocol (PRD §5): a user-triggered reopen may return the
        # iteration to requirement clarification from any downstream state;
        # scripts/reopen_iteration.py records it and propagates staleness.
        return None
    if to_state not in successors(from_state, ui):
        return f"illegal transition {from_state} -> {to_state}"
    if from_state == "requirements_accepted" and to_state == "requirements_clarifying":
        return (
            None
            if triggered_by == "user"
            else "reopen of accepted requirements requires triggered_by=user"
        )
    if from_state == "test_points_accepted" and to_state == "test_points_review":
        return (
            None
            if triggered_by == "user"
            else "reopen of accepted test points requires triggered_by=user"
        )
    return None


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_recorded(recorded: str, iterations_dir: Path) -> Path | None:
    """解析仓库相对、迭代相对或当前证据目录相对的记录路径。"""
    for base in (REPO_ROOT, iterations_dir.parent, iterations_dir):
        candidate = base / recorded
        if candidate.exists():
            return candidate
    suffix = Path(*Path(recorded).parts[1:]) if recorded.startswith("iterations/") else None
    if suffix is not None:
        candidate = iterations_dir.parent / suffix
        if candidate.exists():
            return candidate
    return None


class IterationReport:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.verdicts: list[str] = []
        self.pending_stale = False

    def error(self, message: str) -> None:
        self.errors.append(message)

    def verdict(self, message: str) -> None:
        self.verdicts.append(message)


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def check_iteration(
    iteration_dir: Path,
    report: IterationReport,
    in_progress_elsewhere: str | None = None,
) -> None:
    iteration_yaml = iteration_dir / "iteration.yaml"
    # 0. schema gate (also rejects the post-v1 Hybrid combination via the
    #    branches oneOf) and single-in-progress rule
    try:
        validate_path(iteration_yaml, _REGISTRY)
    except RegistryError as exc:
        report.error(str(exc))
        return
    document: dict[str, Any] = _load_yaml(iteration_yaml) or {}
    iteration_id: str = document["iteration_id"]
    ui: bool = document["branches"]["ui"]
    state: str = document["state"]

    if in_progress_elsewhere and in_progress_elsewhere != iteration_id:
        report.error(
            f"single-in-progress violation: iteration {in_progress_elsewhere!r} is "
            f"also non-terminal"
        )

    if document["state"] == "blocked" and not document.get("blocked_reason"):
        report.error("blocked state requires a non-empty blocked_reason")

    # 1. events chain consistency + transition legality
    events: list[dict[str, Any]] = document.get("events", [])
    previous = "created"
    for index, event in enumerate(events):
        reason = legal_transition(event["from_state"], event["to_state"], ui, event["triggered_by"])
        if reason:
            report.error(f"events[{index}]: {reason}")
        if event["from_state"] != previous:
            report.error(
                f"events[{index}]: chain broken (from_state {event['from_state']!r} "
                f"but previous to_state was {previous!r}) — hand-edited events[]?"
            )
        previous = event["to_state"]
    if state != previous:
        report.error(
            f"state {state!r} does not match the event chain (last to_state "
            f"{previous!r}) — hand-editing state is a validation error; "
            f"use scripts/record_event.py"
        )

    # 2. approval integrity for every gate state that was entered. 只查“是否
    # 曾经 accepted”会让后续 rejected 或被改写的产物继续穿过门禁。
    approvals: list[dict[str, Any]] = document.get("approvals", [])
    for event in events:
        gate = _APPROVAL_GATES.get(event["to_state"])
        if gate is None:
            continue
        for stage, action in gate:
            latest = next(
                (approval for approval in reversed(approvals) if approval.get("stage") == stage),
                None,
            )
            if latest is None:
                report.error(
                    f"transition to {event['to_state']} requires an approvals[] entry "
                    f"(stage={stage}, action={action}) recorded by record_approval.py"
                )
                continue
            if latest.get("action") != action:
                report.error(
                    f"transition to {event['to_state']} requires the latest approvals[] entry "
                    f"for stage={stage} to use action={action}, got {latest.get('action')!r}"
                )
                continue
            artifact_name = _APPROVAL_ARTIFACTS.get(stage)
            if artifact_name is None:
                continue
            artifact_path = iteration_dir / artifact_name
            if not artifact_path.is_file():
                report.error(
                    f"transition to {event['to_state']} requires {artifact_name} so the "
                    f"stage={stage} approval digest can be verified"
                )
                continue
            current_digest = sha256_of(artifact_path)
            if latest.get("artifact_sha256") != current_digest:
                report.error(
                    f"transition to {event['to_state']} has stale or invalid "
                    f"artifact_sha256 for stage={stage}: recorded "
                    f"{latest.get('artifact_sha256')!r}, current {current_digest}; "
                    f"record the explicit decision through record_approval.py"
                )

    # 3. staleness over the full generated_from chain
    proposed: dict[str, str] = {}
    for artifact_file in sorted(iteration_dir.rglob("*.yaml")):
        if artifact_file == iteration_yaml:
            continue
        artifact_binding = binding_for_path(artifact_file, _REGISTRY)
        if artifact_binding is None:
            continue
        doc = _load_yaml(artifact_file)
        if not isinstance(doc, dict):
            continue
        generated_from = doc.get("generated_from")
        if not isinstance(generated_from, dict):
            continue
        upstream = resolve_recorded(generated_from["artifact"], iteration_dir)
        current = sha256_of(upstream) if upstream else None
        if current != generated_from["sha256"]:
            map_key = artifact_binding["artifact"]
            proposed[map_key] = "stale"
            detail = "upstream missing" if upstream is None else "upstream hash mismatch"
            report.verdict(
                f"stale: {artifact_file.relative_to(iteration_dir.parent).as_posix()} "
                f"({detail}) — artifacts.{map_key}.status should become 'stale'"
            )
    artifacts_map: dict[str, Any] = document.get("artifacts", {})
    for map_key, new_status in proposed.items():
        entry = artifacts_map.get(map_key)
        if entry is None or entry.get("status") != new_status:
            report.pending_stale = True
            report.verdict(
                f"proposed rewrite (check mode, not written): "
                f"artifacts.{map_key}.status "
                f"{(entry or {}).get('status')!r} -> {new_status!r}"
            )
    consuming = sorted(k for k, v in proposed.items() if v == "stale")
    if consuming and state not in {
        "created",
        "requirements_clarifying",
        "requirements_accepted",
    }:
        report.error(
            f"stale input consumed downstream of {state}: {', '.join(consuming)} — "
            f"generation/execution must not consume stale inputs until regenerated "
            f"or re-confirmed through the reopen protocol"
        )

    # 4. run-summary invariants (DATA_MODEL §11)
    for run_summary in sorted(iteration_dir.glob("runs/*/run-summary.yaml")):
        check_run_summary(run_summary, report)


def check_run_summary(run_summary: Path, report: IterationReport) -> None:
    label = Path(os.path.relpath(run_summary, REPO_ROOT)).as_posix()
    try:
        validate_path(run_summary, _REGISTRY)
    except RegistryError as exc:
        report.error(str(exc))
        return
    doc: dict[str, Any] = _load_yaml(run_summary) or {}
    attempts: list[dict[str, Any]] = doc.get("attempts", [])
    numbers = [a["attempt_number"] for a in attempts]
    if numbers != list(range(1, len(numbers) + 1)):
        report.error(f"{label}: attempt_number must be consecutive from 1, got {numbers}")
    status: str = doc["status"]
    if status == "passed" and attempts and attempts[-1]["result"] != "pass":
        report.error(f"{label}: terminal passed requires the last attempt to pass")
    if status == "failed" and attempts and attempts[-1]["result"] != "fail":
        report.error(f"{label}: terminal failed requires the last attempt to document the failure")
    if status == "escalated":
        escalation = doc.get("escalation")
        if not isinstance(escalation, dict):
            report.error(f"{label}: escalated requires an escalation record")
        elif escalation.get("reason_class") == "none":
            report.error(f"{label}: escalated requires a concrete reason_class")
    for index, attempt in enumerate(attempts):
        diff_ref = attempt.get("diff_ref")
        if not diff_ref:
            continue
        if diff_ref.endswith(".patch") or "/" in diff_ref:
            # self_debug_helper 以单次 run 目录为相对路径基准写入 diff_ref，
            # 校验器必须使用同一契约，否则记录器生成的合法证据会被误判。
            candidate = resolve_recorded(diff_ref, run_summary.parent)
            if candidate is None and not diff_ref.startswith("stash"):
                report.error(f"{label}: attempts[{index}].diff_ref does not resolve: {diff_ref}")


def find_in_progress(iterations_dir: Path, exclude: str | None = None) -> str | None:
    if not iterations_dir.is_dir():
        return None
    for iteration_yaml in sorted(iterations_dir.glob("*/iteration.yaml")):
        if iteration_yaml.parent.name.startswith("test-fixture-"):
            continue  # permanent script-test fixtures are exempt (Roadmap 1.16)
        try:
            document = _load_yaml(iteration_yaml)
        except yaml.YAMLError:
            continue
        state = document.get("state") if isinstance(document, dict) else None
        if state not in {"accepted", "merged"} and iteration_yaml.parent.name != exclude:
            return iteration_yaml.parent.name
    return None


def apply_fixes(iteration_dir: Path, report: IterationReport) -> None:
    iteration_yaml = iteration_dir / "iteration.yaml"
    document: dict[str, Any] = _load_yaml(iteration_yaml) or {}
    changed = False
    for artifact_file in sorted(iteration_dir.rglob("*.yaml")):
        if artifact_file == iteration_yaml:
            continue
        binding = binding_for_path(artifact_file, _REGISTRY)
        if binding is None:
            continue
        doc = _load_yaml(artifact_file)
        if not isinstance(doc, dict) or not isinstance(doc.get("generated_from"), dict):
            continue
        generated_from = doc["generated_from"]
        upstream = resolve_recorded(generated_from["artifact"], iteration_dir)
        current = sha256_of(upstream) if upstream else None
        if current != generated_from["sha256"]:
            map_key = binding["artifact"]
            entry = document.setdefault("artifacts", {}).setdefault(
                map_key, {"status": "not_started", "input_sha256": None}
            )
            if entry.get("status") != "stale":
                entry["status"] = "stale"
                changed = True
    if changed:
        iteration_yaml.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        report.verdict(f"--fix wrote stale statuses to {iteration_yaml}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "iterations",
        nargs="+",
        type=Path,
        help="one or more iterations/<id> dirs or iteration.yaml files",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="write proposed stale-status rewrites (user/bot commits them)",
    )
    args = parser.parse_args(argv)

    failed = False
    for raw in args.iterations:
        iteration_dir = raw if raw.is_absolute() else REPO_ROOT / raw
        if iteration_dir.is_file() and iteration_dir.name == "iteration.yaml":
            iteration_dir = iteration_dir.parent  # pre-commit passes each file itself
        if not (iteration_dir / "iteration.yaml").exists():
            print(f"error: no iteration.yaml under {iteration_dir}", file=sys.stderr)
            failed = True
            continue

        report = IterationReport()
        sibling = find_in_progress(iteration_dir.parent, exclude=iteration_dir.name)
        check_iteration(iteration_dir, report, in_progress_elsewhere=sibling)

        if args.fix and not report.errors:
            apply_fixes(iteration_dir, report)

        for verdict in report.verdicts:
            print(verdict)
        for error in report.errors:
            print(f"error: {error}", file=sys.stderr)
        if report.errors:
            print(f"validate_iteration: {len(report.errors)} error(s)", file=sys.stderr)
            failed = True
            continue
        if report.pending_stale and not args.fix:
            print(
                "validate_iteration: stale rewrites pending (run --fix to write them)",
                file=sys.stderr,
            )
            failed = True
            continue
        if report.verdicts:
            print(f"validate_iteration: {len(report.verdicts)} verdict(s)")
        else:
            print(f"validate_iteration: {iteration_dir.name} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
