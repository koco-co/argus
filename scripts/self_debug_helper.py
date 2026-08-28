#!/usr/bin/env python
"""M9 唯一证据记录器：run 摘要、预算、检查点和受影响模块。"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = re.compile(r"^run-[0-9]{8}T[0-9]{6}Z(?:-[a-z0-9]{4})?$")
TERMINAL = {"passed", "failed", "budget_exceeded", "escalated"}
ESCALATION_ONLY = {
    "environment_unavailable",
    "auth_failure",
    "backend_5xx",
    "product_behavior_mismatch",
    "requirement_conflict",
    "unknown",
}


class EvidenceError(Exception):
    """证据记录器拒绝不合法写入。"""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _assert_run_dir(run_dir: Path) -> None:
    if run_dir.parent.name != "runs" or not RUN_ID.fullmatch(run_dir.name):
        raise EvidenceError(f"{run_dir} 不是 iterations/<id>/runs/<run-id> run 目录")


def _write_yaml(path: Path, document: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")


def load_summary(run_dir: Path) -> dict[str, Any]:
    _assert_run_dir(run_dir)
    path = run_dir / "run-summary.yaml"
    if not path.exists():
        raise EvidenceError(f"缺少 {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_state(run_dir: Path) -> dict[str, Any]:
    _assert_run_dir(run_dir)
    path = run_dir / "state.json"
    if not path.exists():
        return {"attempt_number": 0, "patched_files": [], "verification_pending": False}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_state(run_dir: Path, state: dict[str, Any]) -> None:
    (run_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def initialize_run(
    iteration_dir: Path,
    run_id: str,
    modules: list[str],
    env: str,
    retry_budget: int = 5,
    scope: str = "module_set",
) -> Path:
    if not RUN_ID.fullmatch(run_id):
        raise EvidenceError(f"非法 run_id：{run_id}")
    if not modules:
        raise EvidenceError("modules 不得为空")
    run_dir = iteration_dir / "runs" / run_id
    if run_dir.exists():
        raise EvidenceError(f"run 目录已存在，禁止覆盖：{run_dir}")
    run_dir.mkdir(parents=True)
    summary = {
        "schema_version": "1.0",
        "iteration_id": iteration_dir.name,
        "run_id": run_id,
        "started_at": _now(),
        "env": env,
        "scope": scope,
        "modules": modules,
        "status": "running",
        "retry_budget": retry_budget,
        "attempts": [],
    }
    errors = validate_summary(summary)
    if errors:
        raise EvidenceError("run-summary 初始化失败：" + "; ".join(errors))
    _write_yaml(run_dir / "run-summary.yaml", summary)
    _write_state(run_dir, {"attempt_number": 0, "patched_files": [], "verification_pending": False})
    return run_dir


def checkpoint(run_dir: Path, attempt_number: int, patched_files: list[str]) -> None:
    summary = load_summary(run_dir)
    expected = len(summary["attempts"]) + 1
    if attempt_number != expected:
        raise EvidenceError(f"attempt_number 应为 {expected}，收到 {attempt_number}")
    _write_state(
        run_dir,
        {
            "attempt_number": attempt_number,
            "patched_files": sorted(set(patched_files)),
            "verification_pending": True,
        },
    )


def recovery_action(run_dir: Path) -> str:
    state = _load_state(run_dir)
    return "verification_required" if state["verification_pending"] else "ready"


def complete_verification(run_dir: Path) -> None:
    state = _load_state(run_dir)
    if not state["verification_pending"]:
        raise EvidenceError("没有待完成的验证组合")
    state["verification_pending"] = False
    _write_state(run_dir, state)


def append_attempt(
    run_dir: Path,
    result: str,
    failure_class: str,
    summary_text: str,
    diff_ref: str | None,
) -> None:
    state = _load_state(run_dir)
    if state["verification_pending"]:
        raise EvidenceError("恢复或 patch 后必须先完成验证组合，才能记录 attempt")
    summary = load_summary(run_dir)
    attempt_number = len(summary["attempts"]) + 1
    if state["attempt_number"] not in {0, attempt_number}:
        raise EvidenceError("检查点 attempt_number 与摘要不连续")
    if diff_ref is not None and not (run_dir / diff_ref).is_file():
        raise EvidenceError(f"diff_ref 不存在：{diff_ref}")
    item: dict[str, Any] = {
        "attempt_number": attempt_number,
        "result": result,
        "failure_class": failure_class,
        "summary": summary_text,
    }
    if diff_ref is not None:
        item["diff_ref"] = diff_ref
    summary["attempts"].append(item)
    _write_yaml(run_dir / "run-summary.yaml", summary)
    _write_state(
        run_dir,
        {
            "attempt_number": attempt_number,
            "patched_files": state["patched_files"],
            "verification_pending": False,
        },
    )


def remaining_budget(run_dir: Path) -> int:
    summary = load_summary(run_dir)
    return max(0, int(summary["retry_budget"]) - len(summary["attempts"]))


def validate_summary(summary: dict[str, Any]) -> list[str]:
    schema = json.loads((REPO_ROOT / "scripts/schemas/run_summary.schema.json").read_text())
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(summary), key=lambda error: list(error.path))
    return [error.message for error in errors]


def finalize(
    run_dir: Path,
    status: str,
    reason_class: str | None = None,
    explanation: str | None = None,
) -> None:
    if status not in TERMINAL:
        raise EvidenceError(f"非法终态：{status}")
    summary = load_summary(run_dir)
    attempts = summary["attempts"]
    if not attempts:
        raise EvidenceError("终态至少需要一个真实 attempt")
    if status == "passed" and attempts[-1]["result"] != "pass":
        raise EvidenceError("passed 的最后一次 attempt 必须通过")
    if status == "budget_exceeded" and remaining_budget(run_dir) > 0:
        raise EvidenceError("预算尚未耗尽，不得写 budget_exceeded")
    if status == "escalated":
        if reason_class not in ESCALATION_ONLY or not explanation:
            raise EvidenceError("escalated 必须带升级类 reason_class 和证据说明")
        summary["escalation"] = {"reason_class": reason_class, "explanation": explanation}
    summary["status"] = status
    summary["finished_at"] = _now()
    errors = validate_summary(summary)
    if errors:
        raise EvidenceError("run-summary 终态非法：" + "; ".join(errors))
    _write_yaml(run_dir / "run-summary.yaml", summary)


def _module_name(root: Path, path: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.add(node.module)
    return values


def affected_modules(root: Path, changed_files: list[Path]) -> list[str]:
    python_files = sorted((root / "automation").rglob("*.py"))
    affected = {_module_name(root, path) for path in changed_files}
    changed = True
    while changed:
        changed = False
        for path in python_files:
            module = _module_name(root, path)
            if module in affected:
                continue
            imports = _imports(path)
            depends_on_affected = any(
                any(name == item or name.startswith(item + ".") for item in affected)
                for name in imports
            )
            if depends_on_affected:
                affected.add(module)
                changed = True
    modules: set[str] = set()
    for module in affected:
        parts = module.split(".")
        test_roots = (["automation", "web", "tests"], ["automation", "api", "tests"])
        if len(parts) >= 5 and parts[:3] in test_roots:
            modules.add(parts[3])
    return sorted(modules)


def verify_patch(patch: Path) -> list[str]:
    """调用统一 patch-scope 机械门禁，供每个修复周期复用。"""

    from check_patch_scope import Report, check_patch_text

    report = Report()
    check_patch_text(patch.read_text(encoding="utf-8"), report)
    return report.problems


def record_ci(
    iteration_dir: Path,
    run_id: str,
    modules: list[str],
    env: str,
    junit: Path,
) -> Path:
    """将 CI 单次只读执行转换成 scope=full 的一条 attempt。"""

    root = ET.parse(junit).getroot()
    failures = sum(int(suite.get("failures", "0")) for suite in root.iter("testsuite"))
    errors = sum(int(suite.get("errors", "0")) for suite in root.iter("testsuite"))
    run_dir = initialize_run(iteration_dir, run_id, modules, env, 0, scope="full")
    if failures + errors:
        append_attempt(
            run_dir,
            "fail",
            "unknown",
            f"CI 单次执行失败：failures={failures}, errors={errors}",
            None,
        )
        finalize(run_dir, "failed")
    else:
        append_attempt(run_dir, "pass", "none", "CI 单次完整执行通过", None)
        finalize(run_dir, "passed")
    return run_dir


def archive_reports(run_dir: Path, sources: list[Path]) -> list[Path]:
    """把显示层报告复制进本 run，不覆盖既有证据。"""

    _assert_run_dir(run_dir)
    archived: list[Path] = []
    for source in sources:
        if not source.exists():
            continue
        target = run_dir / source.name
        if target.exists():
            raise EvidenceError(f"证据目标已存在，禁止覆盖：{target}")
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        archived.append(target)
    return archived


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("iteration", type=Path)
    init.add_argument("--run-id", required=True)
    init.add_argument("--module", action="append", required=True)
    init.add_argument("--env", choices=("local", "test", "ci", "prod"), required=True)
    init.add_argument("--budget", type=int, default=5)
    recover = sub.add_parser("recovery")
    recover.add_argument("run_dir", type=Path)
    save = sub.add_parser("checkpoint")
    save.add_argument("run_dir", type=Path)
    save.add_argument("--attempt", type=int, required=True)
    save.add_argument("--patched-file", action="append", default=[])
    verified = sub.add_parser("verification-complete")
    verified.add_argument("run_dir", type=Path)
    attempt = sub.add_parser("attempt")
    attempt.add_argument("run_dir", type=Path)
    attempt.add_argument("--result", choices=("pass", "fail"), required=True)
    attempt.add_argument("--failure-class", required=True)
    attempt.add_argument("--summary", required=True)
    attempt.add_argument("--diff-ref")
    finish = sub.add_parser("finalize")
    finish.add_argument("run_dir", type=Path)
    finish.add_argument("--status", choices=sorted(TERMINAL), required=True)
    finish.add_argument("--reason-class")
    finish.add_argument("--explanation")
    impact = sub.add_parser("affected-modules")
    impact.add_argument("--root", type=Path, default=REPO_ROOT)
    impact.add_argument("changed_file", type=Path, nargs="+")
    scope = sub.add_parser("verify-patch")
    scope.add_argument("patch", type=Path)
    ci = sub.add_parser("record-ci")
    ci.add_argument("iteration", type=Path)
    ci.add_argument("--run-id", required=True)
    ci.add_argument("--module", action="append", required=True)
    ci.add_argument("--env", choices=("local", "test", "ci", "prod"), default="ci")
    ci.add_argument("--junit", type=Path, required=True)
    archive = sub.add_parser("archive")
    archive.add_argument("run_dir", type=Path)
    archive.add_argument("source", type=Path, nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            print(initialize_run(args.iteration, args.run_id, args.module, args.env, args.budget))
        elif args.command == "recovery":
            action = recovery_action(args.run_dir)
            print(action)
            return 3 if action == "verification_required" else 0
        elif args.command == "checkpoint":
            checkpoint(args.run_dir, args.attempt, args.patched_file)
        elif args.command == "verification-complete":
            complete_verification(args.run_dir)
        elif args.command == "attempt":
            append_attempt(
                args.run_dir,
                args.result,
                args.failure_class,
                args.summary,
                args.diff_ref,
            )
        elif args.command == "finalize":
            finalize(
                args.run_dir,
                args.status,
                args.reason_class,
                args.explanation,
            )
        elif args.command == "affected-modules":
            for module in affected_modules(args.root, args.changed_file):
                print(module)
        elif args.command == "verify-patch":
            problems = verify_patch(args.patch)
            for problem in problems:
                print(f"patch-scope violation: {problem}")
            return 1 if problems else 0
        elif args.command == "record-ci":
            print(record_ci(args.iteration, args.run_id, args.module, args.env, args.junit))
        elif args.command == "archive":
            for path in archive_reports(args.run_dir, args.source):
                print(path)
    except EvidenceError as exc:
        print(f"self-debug evidence error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
