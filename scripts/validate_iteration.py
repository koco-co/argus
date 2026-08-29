#!/usr/bin/env python
"""迭代状态机与 stale 校验器（Roadmap 1.3）。

按契约执行纯检查（PRD §6、Roadmap 1.3）：打印 verdict 和拟议的 ``stale`` 状态差异并在
发现问题时返回非零；只有显式 ``--fix``（由用户或机器人单独提交）才允许修改工作树。
Pre-commit 和 CI 始终以检查模式运行。

强制语义（DATA_MODEL §11、PRD §5）：
- 按分支检查 PRD §5 路由图的迁移合法性，包括任意状态→blocked（带 blocked_reason）、仅用户可
  解阻以及用户触发的重开边；
- ``requirements_mapped`` 仅允许 API 分支，``test_points_review`` 仅允许 UI 分支；两者同时为真
  的 Hybrid 组合直接拒绝；
- events[] 链一致性：``state`` 必须等于最后事件的 ``to_state``（手改任一字段都是校验错误，
  唯一写入器为 scripts/record_event.py，Roadmap 1.15b）；
- 批准完整性：门禁状态要求最新阶段批准带有预期显式 action 或真实 delegated 决定，且需求、
  测试点、豁免的摘要必须匹配当前产物字节；
- 仓库级单一进行中迭代规则（ARCHITECTURE §5.1）；
- 基于完整 ``generated_from`` 链计算 stale verdict：上游摘要不匹配会将产物降级为 ``stale``
  （检查模式只显示差异，``--fix`` 才写入），并报告下游消费 stale 输入；
- run-summary 不变量：attempt 编号从 1 连续且唯一；``passed`` ⇒ 最后 attempt 通过；``failed``
  ⇒ 最后 attempt 记录失败；``escalated`` ⇒ 带具体 reason class；记录的 ``diff_ref`` 必须可解析。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from _registry_lib import REPO_ROOT, RegistryError, binding_for_path, validate_path

_REGISTRY = REPO_ROOT / "scripts" / "schema_registry.yaml"

# PRD §5 路由：前段共享，中段按分支区分，尾段共享。
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
# 进入下列状态前必须具备显式用户决定，或用户持续授权下的 agent 审查记录：
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
    # 任意状态都可以进入 blocked；离开 blocked 需要用户动作，其余路径由用户与 agent 共同选择。
    for source in list(graph):
        if source != "blocked":
            graph[source].add("blocked")
        graph["blocked"].add(source)
    return graph.get(state, set())


def legal_transition(from_state: str, to_state: str, ui: bool, triggered_by: str) -> str | None:
    """合法时返回 None，否则返回可读的拒绝原因。"""
    if to_state == "blocked":
        return None  # any state may block; blocked_reason completeness checked separately
    if from_state == "blocked":
        return (
            None
            if triggered_by == "user"
            else ("leaving blocked requires a user action (triggered_by=user)")
        )
    if (
        triggered_by in {"user", "agent"}
        and to_state == "requirements_clarifying"
        and from_state not in ("created", "requirements_clarifying")
    ):
        # 重开协议（PRD §5）：用户可直接重开；agent 必须由 record_event.py 携带有效持续授权。
        return None
    if to_state not in successors(from_state, ui):
        return f"illegal transition {from_state} -> {to_state}"
    if from_state == "requirements_accepted" and to_state == "requirements_clarifying":
        return (
            None
            if triggered_by in {"user", "agent"}
            else "reopen of accepted requirements requires triggered_by=user or delegated agent"
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


def approval_gate_violations(
    to_state: str,
    iteration_dir: Path,
    approvals: list[dict[str, Any]],
    document: dict[str, Any] | None = None,
) -> list[str]:
    """返回进入状态前未满足的批准条件，供校验器与唯一事件写入器共用。"""
    violations: list[str] = []
    for stage, action in _APPROVAL_GATES.get(to_state, ()):
        latest = next(
            (approval for approval in reversed(approvals) if approval.get("stage") == stage),
            None,
        )
        if latest is None:
            violations.append(
                f"transition to {to_state} requires an approvals[] entry "
                f"(stage={stage}, action={action}) recorded by record_approval.py"
            )
            continue
        if latest.get("action") not in {action, "delegated"}:
            violations.append(
                f"transition to {to_state} requires the latest approvals[] entry "
                f"for stage={stage} to use action={action} or delegated, "
                f"got {latest.get('action')!r}"
            )
            continue
        if latest.get("action") == "delegated":
            from _writers import delegation_violations

            delegated_errors = delegation_violations(document or {}, latest, required_scope=stage)
            if delegated_errors:
                violations.extend(
                    f"transition to {to_state}: {error}" for error in delegated_errors
                )
                continue
        artifact_name = _APPROVAL_ARTIFACTS.get(stage)
        if artifact_name is None:
            if stage == "acceptance":
                execution_digest = (
                    (document or {}).get("artifacts", {}).get("execution", {}).get("input_sha256")
                )
                if execution_digest and latest.get("artifact_sha256") != execution_digest:
                    violations.append(
                        "acceptance approval must reference the current execution evidence digest"
                    )
            continue
        artifact_path = iteration_dir / artifact_name
        if not artifact_path.is_file():
            violations.append(
                f"transition to {to_state} requires {artifact_name} so the "
                f"stage={stage} approval digest can be verified"
            )
            continue
        current_digest = sha256_of(artifact_path)
        if latest.get("artifact_sha256") != current_digest:
            violations.append(
                f"transition to {to_state} has stale or invalid "
                f"artifact_sha256 for stage={stage}: recorded "
                f"{latest.get('artifact_sha256')!r}, current {current_digest}; "
                f"record the explicit decision through record_approval.py"
            )
    return violations


def lifecycle_violations(document: dict[str, Any]) -> list[str]:
    """校验当前生命周期链，不依赖磁盘产物或仓库级单迭代状态。"""
    violations: list[str] = []
    ui = document["branches"]["ui"]
    state = document["state"]
    for index, approval in enumerate(document.get("approvals", [])):
        action = approval.get("action")
        actor = approval.get("actor")
        note = approval.get("note")
        if action == "delegated" and (not isinstance(note, str) or not note.strip()):
            violations.append(f"approvals[{index}]: delegated approval requires a non-empty note")
        if action == "delegated" and actor != "agent":
            violations.append(f"approvals[{index}]: delegated approval must use actor=agent")
        if action != "delegated" and actor != "user":
            violations.append(f"approvals[{index}]: explicit approval actions must use actor=user")
        if action == "delegated":
            from _writers import delegation_violations

            violations.extend(
                f"approvals[{index}]: {error}"
                for error in delegation_violations(
                    document, approval, required_scope=approval.get("stage")
                )
            )
    if state == "blocked" and not document.get("blocked_reason"):
        violations.append("blocked state requires a non-empty blocked_reason")

    previous = "created"
    for index, event in enumerate(document.get("events", [])):
        reason = legal_transition(event["from_state"], event["to_state"], ui, event["triggered_by"])
        if reason:
            violations.append(f"events[{index}]: {reason}")
        is_delegated_reopen = (
            event["triggered_by"] == "agent"
            and event["to_state"] == "requirements_clarifying"
            and event["from_state"] not in ("created", "requirements_clarifying")
        )
        if is_delegated_reopen:
            from _writers import delegation_violations

            if not event.get("delegation_id"):
                violations.append(f"events[{index}]: delegated reopen requires delegation_id")
            violations.extend(
                f"events[{index}]: {error}"
                for error in delegation_violations(
                    document, event, required_scope="lifecycle_reopen"
                )
            )
        elif event.get("delegation_id") is not None:
            violations.append(
                f"events[{index}]: delegation_id is only valid on a delegated reopen event"
            )
        if event["from_state"] != previous:
            violations.append(
                f"events[{index}]: chain broken (from_state {event['from_state']!r} "
                f"but previous to_state was {previous!r}) — hand-edited events[]?"
            )
        previous = event["to_state"]
    accepted_events = [
        event for event in document.get("events", []) if event.get("to_state") == "accepted"
    ]
    if state == "accepted" and accepted_events:
        accepted_at = accepted_events[-1].get("timestamp")
        try:
            accepted_time = datetime.fromisoformat(str(accepted_at).replace("Z", "+00:00"))
            if accepted_time.tzinfo is None:
                raise ValueError("accepted event timestamp lacks timezone")
            accepted_time = accepted_time.astimezone(UTC)
            acceptance_approvals = [
                approval
                for approval in document.get("approvals", [])
                if approval.get("stage") == "acceptance"
            ]
            if not acceptance_approvals:
                violations.append(
                    "accepted state requires an acceptance approval before its accepted event"
                )
            for approval in acceptance_approvals:
                approval_time = datetime.fromisoformat(
                    str(approval.get("timestamp")).replace("Z", "+00:00")
                )
                if approval_time.tzinfo is None or approval_time.astimezone(UTC) > accepted_time:
                    violations.append(
                        "acceptance approval was appended after the terminal accepted event; "
                        "reopen and execute a fresh chain before accepting again"
                    )
        except (TypeError, ValueError):
            violations.append(
                "accepted event and acceptance approval timestamps must be valid date-times"
            )
    if state != previous:
        violations.append(
            f"state {state!r} does not match the event chain (last to_state "
            f"{previous!r}) — hand-editing state is a validation error; "
            f"use scripts/record_event.py"
        )
    return violations


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
    # 0. Schema 门禁（通过 branches oneOf 同时拒绝 post-v1 Hybrid 组合）及单一进行中规则。
    try:
        validate_path(iteration_yaml, _REGISTRY)
    except RegistryError as exc:
        report.error(str(exc))
        return
    document: dict[str, Any] = _load_yaml(iteration_yaml) or {}
    iteration_id: str = document["iteration_id"]
    state: str = document["state"]

    if in_progress_elsewhere and in_progress_elsewhere != iteration_id:
        report.error(
            f"single-in-progress violation: iteration {in_progress_elsewhere!r} is "
            f"also non-terminal"
        )

    # 1. events 链一致性与迁移合法性。
    events: list[dict[str, Any]] = document.get("events", [])
    for violation in lifecycle_violations(document):
        report.error(violation)

    # 2. 检查每个已进入门禁状态的批准完整性。只查“是否曾经 accepted”会让后续 rejected
    # 或被改写的产物继续穿过门禁。
    approvals: list[dict[str, Any]] = document.get("approvals", [])
    for event in events:
        for violation in approval_gate_violations(
            event["to_state"], iteration_dir, approvals, document
        ):
            report.error(violation)

    # 3. 基于完整 generated_from 链检查 stale。
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

    # 4. run-summary 不变量（DATA_MODEL §11）。
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
        help="一个或多个 iterations/<id> 目录或 iteration.yaml 文件",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="写入拟议的 stale 状态差异（由用户或机器人另行提交）",
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
        sibling = (
            None
            if iteration_dir.name.startswith("test-fixture-")
            else find_in_progress(iteration_dir.parent, exclude=iteration_dir.name)
        )
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
