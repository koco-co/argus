#!/usr/bin/env python
"""M9 唯一证据记录器：run 摘要、预算、检查点和受影响模块。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml  # pyright: ignore[reportMissingModuleSource]
from _registry_lib import RegistryError, validate_path
from argus_core.parsing import load_json, load_yaml  # pyright: ignore[reportMissingImports]
from jsonschema import Draft7Validator, FormatChecker  # pyright: ignore[reportMissingModuleSource]

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = re.compile(r"^run-[0-9]{8}T[0-9]{6}Z(?:-[a-z0-9]{4})?$")
ITERATION_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
TERMINAL = {"passed", "failed", "budget_exceeded", "escalated"}
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
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


def _assert_no_symlink_components(path: Path, *, label: str) -> None:
    candidate = path if path.is_absolute() else Path.cwd() / path
    if "\x00" in str(candidate) or "\\" in str(candidate) or ".." in candidate.parts:
        raise EvidenceError(f"{label} 不得包含路径穿越：{path}")
    current = Path(candidate.anchor)
    for part in candidate.parts:
        current /= part
        if current.is_symlink():
            raise EvidenceError(f"{label} 路径不得经过符号链接：{path}")


def _assert_run_dir(run_dir: Path) -> None:
    if (
        run_dir.parent.name != "runs"
        or not ITERATION_ID.fullmatch(run_dir.parent.parent.name)
        or run_dir.parent.parent.parent.name != "iterations"
        or not RUN_ID.fullmatch(run_dir.name)
    ):
        raise EvidenceError(f"{run_dir} 不是 iterations/<id>/runs/<run-id> run 目录")
    _assert_no_symlink_components(run_dir, label="run")


def _atomic_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    """Atomically persist evidence and sync both file and containing directory."""
    _assert_no_symlink_components(path, label="证据文件")
    if path.is_symlink() or path.parent.is_symlink() or not path.parent.is_dir():
        raise EvidenceError(f"证据文件路径不是安全目录：{path}")
    existing_mode = path.stat().st_mode & 0o777 if path.exists() else mode
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.chmod(temporary, existing_mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise EvidenceError(f"无法原子写入证据文件：{path}") from exc


def _write_yaml(path: Path, document: dict[str, Any]) -> None:
    try:
        payload = yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode("utf-8")
    except (UnicodeError, yaml.YAMLError, ValueError) as exc:
        raise EvidenceError("证据无法安全序列化为 YAML") from exc
    _atomic_write(path, payload)


def load_summary(run_dir: Path) -> dict[str, Any]:
    _assert_run_dir(run_dir)
    path = run_dir / "run-summary.yaml"
    _assert_no_symlink_components(path, label="run 摘要")
    if path.is_symlink() or not path.is_file():
        raise EvidenceError(f"缺少安全的 {path}")
    try:
        document = load_yaml(path.read_bytes()) or {}
    except (OSError, UnicodeError, ValueError) as exc:
        raise EvidenceError(f"{path} 不是安全可解析的 YAML 文档") from exc
    if not isinstance(document, dict):
        raise EvidenceError(f"{path} 顶层必须是映射")
    errors = validate_summary(document)
    if errors:
        raise EvidenceError(f"{path} 不符合 run-summary schema：{'; '.join(errors)}")
    return document


def _validate_state(state: dict[str, Any]) -> None:
    if set(state) != {"attempt_number", "patched_files", "verification_pending"}:
        raise EvidenceError("state 文件字段不符合检查点契约")
    attempt_number = state["attempt_number"]
    if (
        isinstance(attempt_number, bool)
        or not isinstance(attempt_number, int)
        or attempt_number < 0
    ):
        raise EvidenceError("state.attempt_number 必须是非负整数")
    patched_files = state["patched_files"]
    if not isinstance(patched_files, list) or any(
        not isinstance(item, str)
        or not item
        or "\x00" in item
        or "\\" in item
        or Path(item).is_absolute()
        or ".." in Path(item).parts
        for item in patched_files
    ):
        raise EvidenceError("state.patched_files 必须是安全的相对路径列表")
    if not isinstance(state["verification_pending"], bool):
        raise EvidenceError("state.verification_pending 必须是布尔值")


def _load_state(run_dir: Path) -> dict[str, Any]:
    _assert_run_dir(run_dir)
    path = run_dir / "state.json"
    if not path.exists() and not path.is_symlink():
        return {"attempt_number": 0, "patched_files": [], "verification_pending": False}
    if path.is_symlink() or not path.is_file():
        raise EvidenceError(f"state 文件不是安全的普通文件：{path}")
    try:
        state = load_json(path.read_bytes())
    except (OSError, UnicodeError, ValueError) as exc:
        raise EvidenceError(f"state 文件不是安全可解析的 JSON：{path}") from exc
    if not isinstance(state, dict):
        raise EvidenceError(f"state 文件顶层必须是对象：{path}")
    _validate_state(state)
    return state


def _write_state(run_dir: Path, state: dict[str, Any]) -> None:
    _assert_run_dir(run_dir)
    _validate_state(state)
    path = run_dir / "state.json"
    _assert_no_symlink_components(path, label="state 文件")
    if path.is_symlink() or path.parent.is_symlink():
        raise EvidenceError(f"state 文件不得是符号链接：{path}")
    _atomic_write(
        path,
        (json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
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
    _assert_run_dir(run_dir)
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
    if run_dir.exists():
        raise EvidenceError(f"run 目录已存在，禁止覆盖：{run_dir}")
    try:
        run_dir.mkdir(parents=True)
    except OSError as exc:
        raise EvidenceError(f"无法创建 run 目录：{run_dir}") from exc
    _write_yaml(run_dir / "run-summary.yaml", summary)
    _write_state(run_dir, {"attempt_number": 0, "patched_files": [], "verification_pending": False})
    return run_dir


def checkpoint(run_dir: Path, attempt_number: int, patched_files: list[str]) -> None:
    summary = load_summary(run_dir)
    if summary["status"] != "running":
        raise EvidenceError("终态 run 不得追加 checkpoint")
    if (
        isinstance(attempt_number, bool)
        or not isinstance(attempt_number, int)
        or attempt_number < 1
    ):
        raise EvidenceError("checkpoint attempt_number 必须是正整数")
    if not isinstance(patched_files, list):
        raise EvidenceError("patched_files 必须是安全的相对路径列表")
    if any(
        not isinstance(item, str)
        or not item
        or "\x00" in item
        or "\\" in item
        or Path(item).is_absolute()
        or ".." in Path(item).parts
        for item in patched_files
    ):
        raise EvidenceError("patched_files 必须是安全的相对路径列表")
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
    if summary["status"] != "running":
        raise EvidenceError("终态 run 不得追加 attempt")
    attempt_number = len(summary["attempts"]) + 1
    if state["attempt_number"] not in {0, attempt_number - 1, attempt_number}:
        raise EvidenceError("检查点 attempt_number 与摘要不连续")
    if diff_ref is not None:
        if not isinstance(diff_ref, str) or not diff_ref or "\x00" in diff_ref or "\\" in diff_ref:
            raise EvidenceError(f"diff_ref 不存在或越出 run 目录：{diff_ref}")
        reference = Path(diff_ref)
        candidate = run_dir / reference
        try:
            _assert_no_symlink_components(candidate, label="diff_ref")
        except EvidenceError as exc:
            raise EvidenceError(f"diff_ref 不存在或越出 run 目录：{diff_ref}") from exc
        if (
            reference.is_absolute()
            or ".." in reference.parts
            or candidate.is_symlink()
            or not candidate.is_file()
        ):
            raise EvidenceError(f"diff_ref 不存在或越出 run 目录：{diff_ref}")
        try:
            candidate.resolve().relative_to(run_dir.resolve())
        except ValueError as exc:
            raise EvidenceError(f"diff_ref 不得越出 run 目录：{diff_ref}") from exc
    item: dict[str, Any] = {
        "attempt_number": attempt_number,
        "result": result,
        "failure_class": failure_class,
        "summary": summary_text,
    }
    if diff_ref is not None:
        item["diff_ref"] = diff_ref
    summary["attempts"].append(item)
    errors = validate_summary(summary)
    if errors:
        raise EvidenceError("attempt 违反 run-summary schema：" + "; ".join(errors))
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
    # 升级类只收集一次事实证据并立即停止，不能消耗自动修复预算；
    # 预算只约束允许自动改码的循环。
    consumed = sum(
        1 for attempt in summary["attempts"] if attempt.get("failure_class") not in ESCALATION_ONLY
    )
    try:
        budget = int(summary["retry_budget"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceError("run-summary 的 retry_budget 无效") from exc
    return max(0, budget - consumed)


def validate_summary(summary: dict[str, Any]) -> list[str]:
    schema = load_json((REPO_ROOT / "scripts/schemas/run_summary.schema.json").read_bytes())
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
    state = _load_state(run_dir)
    if state["verification_pending"]:
        raise EvidenceError("完成验证组合前不得写入终态")
    summary = load_summary(run_dir)
    attempts = summary["attempts"]
    if not attempts:
        raise EvidenceError("终态至少需要一个真实 attempt")
    if state["attempt_number"] not in {0, len(attempts)}:
        raise EvidenceError("state attempt_number 与摘要不连续")
    if status == "passed" and attempts[-1]["result"] != "pass":
        raise EvidenceError("passed 的最后一次 attempt 必须通过")
    if status in {"failed", "budget_exceeded", "escalated"} and attempts[-1]["result"] != "fail":
        raise EvidenceError(f"{status} 的最后一次 attempt 必须记录失败")
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
    root = root if root.is_absolute() else Path.cwd() / root
    _assert_no_symlink_components(root, label="project root")
    automation_root = root / "automation"
    _assert_no_symlink_components(automation_root, label="automation root")
    python_files = sorted(automation_root.rglob("*.py"))
    normalized_changed: list[Path] = []
    for path in changed_files:
        candidate = path if path.is_absolute() else root / path
        _assert_no_symlink_components(candidate, label="changed file")
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise EvidenceError(f"changed file must be under project root: {path}") from exc
        normalized_changed.append(candidate)
    for path in python_files:
        _assert_no_symlink_components(path, label="automation source")
    affected = {_module_name(root, path) for path in normalized_changed}
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

    _assert_no_symlink_components(patch, label="patch")
    if patch.is_symlink() or not patch.is_file():
        raise EvidenceError(f"patch 必须是安全的普通文件：{patch}")
    from check_patch_scope import Report, check_patch_text

    report = Report()
    check_patch_text(patch.read_text(encoding="utf-8"), report)
    return report.problems


_STRICT_NON_NEGATIVE_INTEGER = re.compile(r"^(?:0|[1-9][0-9]*)$")
_SHA256 = re.compile(r"^sha256:[a-f0-9]{64}$")
_CODE_SHA = re.compile(r"^[a-f0-9]{40,64}$")
_SAFE_NODEID = re.compile(r"^automation/[^\x00\\\r\n]+::[^\x00\\\r\n]+$")
_MANIFEST_SCHEMA = REPO_ROOT / "scripts" / "schemas" / "execution_manifest.schema.json"


def _valid_nodeid(value: object) -> bool:
    if not isinstance(value, str) or _SAFE_NODEID.fullmatch(value) is None:
        return False
    file_part = value.split("::", 1)[0]
    return ".." not in Path(file_part).parts


def _junit_count(root: ET.Element, attribute: str) -> int:
    total = 0
    for suite in root.iter("testsuite"):
        value = suite.get(attribute, "0")
        if not _STRICT_NON_NEGATIVE_INTEGER.fullmatch(value):
            raise EvidenceError(f"JUnit 的 {attribute} 不是严格的非负整数")
        try:
            total += int(value)
        except (TypeError, ValueError) as exc:
            raise EvidenceError(f"JUnit 的 {attribute} 不是整数") from exc
    return total


def _read_junit(path: Path) -> dict[str, Any]:
    _assert_no_symlink_components(path, label="JUnit 证据")
    if path.is_symlink() or not path.is_file():
        raise EvidenceError(f"JUnit 证据必须是安全的普通文件：{path}")
    try:
        if path.stat().st_size > MAX_EVIDENCE_BYTES:
            raise EvidenceError("JUnit 证据超过大小限制")
        payload = path.read_bytes()
        lowered = payload.lower()
        if b"<!doctype" in lowered or b"<!entity" in lowered:
            raise EvidenceError("JUnit 证据不得包含 XML 外部实体声明")
        root = ET.fromstring(payload)
        if (
            root.tag not in {"testsuite", "testsuites"}
            or next(root.iter("testsuite"), None) is None
        ):
            raise EvidenceError("JUnit 根节点必须包含 testsuite")
    except EvidenceError:
        raise
    except (OSError, ET.ParseError, RecursionError) as exc:
        raise EvidenceError("JUnit 证据不是安全可解析的 XML") from exc
    stats: dict[str, Any] = {
        "tests": _junit_count(root, "tests"),
        "failures": _junit_count(root, "failures"),
        "errors": _junit_count(root, "errors"),
        "skipped": _junit_count(root, "skipped"),
    }
    if stats["tests"] <= 0:
        raise EvidenceError("JUnit 证据不得记录零测试")
    if stats["skipped"] >= stats["tests"]:
        raise EvidenceError("JUnit 证据不得全部 skipped")
    if stats["failures"] + stats["errors"] + stats["skipped"] > stats["tests"]:
        raise EvidenceError("JUnit 证据的 failures/errors/skipped 总数超过 tests")
    stats["sha256"] = hashlib.sha256(payload).hexdigest()
    stats["path"] = _evidence_reference(path)
    return stats


def _evidence_reference(path: Path) -> str:
    """以仓库相对路径保存报告引用，仓库外输入只保留安全文件名。"""

    _assert_no_symlink_components(path, label="证据引用")
    resolved = path.resolve()
    repo_root = REPO_ROOT.resolve()
    if resolved != repo_root and repo_root not in resolved.parents:
        name = path.name
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise EvidenceError(f"证据引用文件名不安全：{path}")
        return f"external/{name}"
    return resolved.relative_to(repo_root).as_posix()


def _read_execution_nodeids(path: Path) -> tuple[list[str], list[str], dict[str, str]]:
    _assert_no_symlink_components(path, label="pytest 执行清单")
    if path.is_symlink() or not path.is_file():
        raise EvidenceError(f"pytest 执行清单必须是安全的普通文件：{path}")
    try:
        if path.stat().st_size > MAX_EVIDENCE_BYTES:
            raise EvidenceError("pytest 执行清单超过大小限制")
        document = load_json(path.read_bytes())
    except EvidenceError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise EvidenceError(f"pytest 执行清单不是安全 JSON：{path}") from exc
    if not isinstance(document, dict):
        raise EvidenceError("pytest 执行清单必须是对象")
    if document.get("schema_version") != "1.1":
        raise EvidenceError("pytest 执行清单 schema_version 必须是 1.1")
    raw_collected = document.get("collected_nodeids")
    if not isinstance(raw_collected, list):
        raise EvidenceError("pytest 执行清单必须包含 collected_nodeids 数组")
    if any(not _valid_nodeid(nodeid) for nodeid in raw_collected):
        raise EvidenceError("pytest collection 清单包含非法 nodeid")
    if len(set(raw_collected)) != len(raw_collected):
        raise EvidenceError("pytest collection 清单包含重复 nodeid")
    nodeids = document.get("nodeids")
    if not isinstance(nodeids, list):
        raise EvidenceError("pytest 执行清单必须包含 nodeids 数组")
    if any(not _valid_nodeid(nodeid) for nodeid in nodeids):
        raise EvidenceError("pytest 执行清单包含非法 nodeid")
    if len(set(nodeids)) != len(nodeids):
        raise EvidenceError("pytest 执行清单包含重复 nodeid")
    if not set(nodeids).issubset(set(raw_collected)):
        raise EvidenceError("pytest 执行 nodeid 不在 collection 清单中")
    raw_outcomes = document.get("outcomes")
    if not isinstance(raw_outcomes, dict):
        raise EvidenceError("pytest 执行清单 outcomes 必须是对象")
    outcomes: dict[str, str] = {}
    allowed = {"passed", "failed", "skipped", "xfailed", "xpassed", "unknown"}
    for nodeid, outcome in raw_outcomes.items():
        if not _valid_nodeid(nodeid) or not isinstance(outcome, str) or outcome not in allowed:
            raise EvidenceError("pytest 执行清单 outcomes 包含非法条目")
        outcomes[nodeid] = outcome
    if set(outcomes) != set(nodeids):
        raise EvidenceError("pytest 执行清单必须为每个 executed nodeid 提供 outcome")
    return sorted(nodeids), sorted(raw_collected), outcomes


def _expected_nodeids(iteration_dir: Path, *, required: bool = True) -> list[str]:
    path = iteration_dir / "traceability.yaml"
    _assert_no_symlink_components(path, label="traceability")
    if not path.exists() and not path.is_symlink():
        if required:
            raise EvidenceError(f"缺少 traceability.yaml，无法精确绑定 iteration：{iteration_dir}")
        return []
    if path.is_symlink() or not path.is_file():
        raise EvidenceError(f"traceability.yaml 必须是安全的普通文件：{path}")
    try:
        validate_path(path)
        document = load_yaml(path.read_bytes())
    except (OSError, UnicodeError, ValueError, RegistryError) as exc:
        raise EvidenceError(f"traceability.yaml 不可安全解析：{path}") from exc
    if not isinstance(document, dict) or document.get("iteration_id") != iteration_dir.name:
        raise EvidenceError("traceability iteration_id 与目录不一致")
    links = document.get("links")
    if not isinstance(links, list):
        raise EvidenceError("traceability.links 必须是列表")
    nodeids: list[str] = []
    for link in links:
        if not isinstance(link, dict):
            raise EvidenceError("traceability link 必须是对象")
        values = link.get("automation_test_ids", [])
        if not isinstance(values, list):
            raise EvidenceError("traceability.automation_test_ids 必须是列表")
        for nodeid in values:
            if not _valid_nodeid(nodeid):
                raise EvidenceError("traceability 包含非法 automation nodeid")
            nodeids.append(nodeid)
    unique = sorted(set(nodeids))
    if required and not unique:
        raise EvidenceError(f"traceability 没有 automation nodeid：{iteration_dir}")
    if len(unique) != len(nodeids):
        raise EvidenceError("traceability 包含重复 automation nodeid")
    return unique


def _digest_file(path: Path, *, label: str) -> str:
    _assert_no_symlink_components(path, label=label)
    if path.is_symlink() or not path.is_file():
        raise EvidenceError(f"{label} 必须是安全的普通文件：{path}")
    try:
        if path.stat().st_size > MAX_EVIDENCE_BYTES:
            raise EvidenceError(f"{label} 超过大小限制")
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise EvidenceError(f"{label} 无法读取") from exc


def _target_config_digest() -> str:
    digest = hashlib.sha256()
    for relative in (
        "target-app/compose.yaml",
        "target-app/Dockerfile",
        "target-app/medusa.lock.yaml",
    ):
        path = REPO_ROOT / relative
        _assert_no_symlink_components(path, label="靶场配置")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\\0")
        if path.is_file() and not path.is_symlink():
            digest.update(path.read_bytes())
        else:
            digest.update(b"unavailable")
    return digest.hexdigest()


def _docker_image_ids() -> list[str]:
    command = ["docker", "compose", "-f", "target-app/compose.yaml", "images", "-q"]
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ["unavailable"]
    if completed.returncode != 0:
        return ["unavailable"]
    values: list[str] = []
    for line in completed.stdout.splitlines():
        value = line.strip()
        if re.fullmatch(r"sha256:[a-f0-9]{64}", value):
            values.append(value)
        elif re.fullmatch(r"[a-f0-9]{64}", value):
            values.append(f"sha256:{value}")
    return sorted(set(values)) or ["unavailable"]


def _allure_evidence(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "path": "unavailable",
            "sha256": hashlib.sha256(b"unavailable").hexdigest(),
            "available": False,
        }
    _assert_no_symlink_components(path, label="Allure 证据")
    if path.is_symlink() or not path.is_dir():
        return {
            "path": _evidence_reference(path),
            "sha256": hashlib.sha256(b"unavailable").hexdigest(),
            "available": False,
        }
    digest = hashlib.sha256()
    total = 0
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise EvidenceError(f"Allure 证据不得包含符号链接：{path}")
        if not item.is_file():
            continue
        data = item.read_bytes()
        total += len(data)
        if total > MAX_EVIDENCE_BYTES:
            raise EvidenceError("Allure 证据超过大小限制")
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\\0")
        digest.update(data)
    return {"path": _evidence_reference(path), "sha256": digest.hexdigest(), "available": True}


def _current_commit_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvidenceError("无法读取当前代码 commit SHA") from exc
    value = completed.stdout.strip()
    if completed.returncode != 0 or not _CODE_SHA.fullmatch(value):
        raise EvidenceError("当前代码 commit SHA 无效")
    return value


def _validate_execution_manifest(manifest: dict[str, Any]) -> list[str]:
    try:
        schema = load_json(_MANIFEST_SCHEMA.read_bytes())
    except (OSError, UnicodeError, ValueError) as exc:
        raise EvidenceError("execution manifest schema 不可读取") from exc
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(manifest), key=lambda error: list(error.absolute_path))
    return [error.message for error in errors]


def load_execution_manifest(run_dir: Path) -> dict[str, Any]:
    _assert_run_dir(run_dir)
    path = run_dir / "execution-manifest.json"
    _assert_no_symlink_components(path, label="execution manifest")
    if path.is_symlink() or not path.is_file():
        raise EvidenceError(f"缺少安全的 execution manifest：{path}")
    try:
        manifest = load_json(path.read_bytes())
    except (OSError, UnicodeError, ValueError) as exc:
        raise EvidenceError("execution manifest 不是安全 JSON") from exc
    if not isinstance(manifest, dict):
        raise EvidenceError("execution manifest 顶层必须是对象")
    errors = _validate_execution_manifest(manifest)
    if errors:
        raise EvidenceError("execution manifest schema 错误：" + "; ".join(errors))
    return manifest


def _write_execution_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    errors = _validate_execution_manifest(manifest)
    if errors:
        raise EvidenceError("execution manifest schema 错误：" + "; ".join(errors))
    _atomic_write(
        run_dir / "execution-manifest.json",
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def _resolve_expected_nodeids(expected: list[str], collected: list[str]) -> list[str]:
    """Resolve traceability selectors to the nodeids emitted by pytest.

    Pytest appends parameter IDs to a parametrized test (for example,
    ``::test_checkout[chromium]``), while traceability generated from the
    test function records the stable unparameterized selector.  Only a
    parameter suffix on an otherwise exact selector is accepted; unrelated
    collected tests remain an iteration-scope error.
    """

    remaining = set(collected)
    resolved: list[str] = []
    missing: list[str] = []
    for selector in expected:
        if selector in remaining:
            matches = [selector]
        else:
            parameter_prefix = f"{selector}["
            matches = sorted(nodeid for nodeid in remaining if nodeid.startswith(parameter_prefix))
        if not matches:
            missing.append(selector)
            continue
        resolved.extend(matches)
        remaining.difference_update(matches)
    if missing:
        raise EvidenceError(f"pytest collection 未包含 traceability nodeid：{missing}")
    if remaining:
        raise EvidenceError(f"pytest collection 包含非本 iteration nodeid：{sorted(remaining)}")
    return sorted(resolved)


def _manifest_attempt(
    expected: list[str],
    execution: dict[str, Any],
    junit: dict[str, Any],
    allure: dict[str, Any],
) -> dict[str, Any]:
    executed = execution["nodeids"]
    collected = execution["collected_nodeids"]
    outcomes = execution["outcomes"]
    resolved_expected = _resolve_expected_nodeids(expected, collected)
    missing = sorted(set(resolved_expected) - set(executed))
    if missing:
        raise EvidenceError(f"pytest 未执行 traceability nodeid：{missing}")
    extra = sorted(set(executed) - set(resolved_expected))
    if extra:
        raise EvidenceError(f"pytest 执行了非本 iteration nodeid：{extra}")
    if set(outcomes) != set(executed):
        raise EvidenceError("pytest 执行清单必须为每个 executed nodeid 提供 outcome")
    skipped = sorted(
        nodeid
        for nodeid in resolved_expected
        if outcomes[nodeid] in {"skipped", "xfailed", "xpassed"}
    )
    if skipped:
        raise EvidenceError(f"traceability nodeid 被 skipped/xfailed/xpassed：{skipped}")
    unknown = sorted(nodeid for nodeid in resolved_expected if outcomes[nodeid] == "unknown")
    if unknown:
        raise EvidenceError(f"traceability nodeid outcome 不可确认：{unknown}")
    if junit["tests"] != len(resolved_expected):
        raise EvidenceError("JUnit tests 数必须精确等于该 iteration 的 traceability nodeid 数")
    junit_failed = bool(junit["failures"] + junit["errors"])
    outcome_failed = any(outcomes[nodeid] == "failed" for nodeid in resolved_expected)
    if junit_failed != outcome_failed:
        raise EvidenceError("JUnit failures/errors 与 pytest nodeid outcome 不一致")
    result = "fail" if junit_failed else "pass"
    return {
        "result": result,
        "expected_nodeids": resolved_expected,
        "collected_nodeids": collected,
        "executed_nodeids": executed,
        "outcomes": outcomes,
        "junit": {
            "path": junit["path"],
            "sha256": junit["sha256"],
            "tests": junit["tests"],
            "failures": junit["failures"],
            "errors": junit["errors"],
            "skipped": junit["skipped"],
        },
        "allure": allure,
    }


def _build_manifest(
    iteration_dir: Path,
    run_id: str,
    env: str,
    expected: list[str],
    attempts: list[dict[str, Any]],
    *,
    commit_sha: str | None,
    command: str | None,
    environment_file: Path | None,
    seed_registry: Path | None,
    target_image_ids: list[str] | None,
    collected_nodeids: list[str],
) -> dict[str, Any]:
    current_sha = _current_commit_sha()
    if commit_sha is not None and commit_sha != current_sha:
        raise EvidenceError("manifest code_sha 必须与当前 checkout 的 commit SHA 一致")
    code_sha = current_sha
    if not _CODE_SHA.fullmatch(code_sha):
        raise EvidenceError("manifest code_sha 必须是当前代码 commit SHA")
    if not attempts:
        raise EvidenceError("execution manifest 至少需要一个 attempt")
    collected = sorted(
        {nodeid for attempt in attempts for nodeid in attempt["collected_nodeids"]}
        | set(collected_nodeids)
    )
    environment_path = environment_file or REPO_ROOT / f"config/env.{env}.yaml"
    seed_path = seed_registry or REPO_ROOT / "shared/testdata/seed-registry.yaml"
    manifest = {
        "schema_version": "1.1",
        "iteration_id": iteration_dir.name,
        "run_id": run_id,
        "code_sha": code_sha,
        "env": env,
        "scope": "full",
        "command": command or "not-recorded",
        "expected_nodeids": expected,
        "collected_nodeids": collected,
        "environment_summary": {
            "name": env,
            "path": _evidence_reference(environment_path),
            "sha256": _digest_file(environment_path, label="环境配置"),
        },
        "seed_summary": {
            "path": _evidence_reference(seed_path),
            "sha256": _digest_file(seed_path, label="seed registry"),
        },
        "target_summary": {
            "config_sha256": _target_config_digest(),
            "image_ids": sorted(set(target_image_ids or _docker_image_ids())),
        },
        "attempts": [],
    }
    for number, attempt in enumerate(attempts, start=1):
        item = dict(attempt)
        item["attempt_number"] = number
        manifest["attempts"].append(item)
    errors = _validate_execution_manifest(manifest)
    if errors:
        raise EvidenceError("execution manifest schema 错误：" + "; ".join(errors))
    return manifest


def _record_ci_attempts(
    iteration_dir: Path,
    run_id: str,
    modules: list[str],
    env: str,
    expected: list[str],
    attempt_inputs: list[dict[str, Any]],
    *,
    commit_sha: str | None,
    command: str | None,
    environment_file: Path | None,
    seed_registry: Path | None,
    target_image_ids: list[str] | None,
) -> Path:
    attempt_evidence: list[dict[str, Any]] = []
    for item in attempt_inputs:
        junit = _read_junit(item["junit"])
        execution_path = item.get("execution")
        if not isinstance(execution_path, Path):
            raise EvidenceError("每个 CI attempt 必须提供 pytest 执行清单")
        nodeids, collected_nodeids, outcomes = _read_execution_nodeids(execution_path)
        execution = {
            "nodeids": nodeids,
            "collected_nodeids": collected_nodeids,
            "outcomes": outcomes,
        }
        allure = _allure_evidence(item.get("allure"))
        attempt_evidence.append(_manifest_attempt(expected, execution, junit, allure))
    manifest_expected = sorted(
        {nodeid for attempt in attempt_evidence for nodeid in attempt["expected_nodeids"]}
    )
    manifest = _build_manifest(
        iteration_dir,
        run_id,
        env,
        manifest_expected,
        attempt_evidence,
        commit_sha=commit_sha,
        command=command,
        environment_file=environment_file,
        seed_registry=seed_registry,
        target_image_ids=target_image_ids,
        collected_nodeids=sorted(
            {nodeid for attempt in attempt_evidence for nodeid in attempt["collected_nodeids"]}
        ),
    )
    run_dir = initialize_run(iteration_dir, run_id, modules, env, 0, scope="full")
    for attempt in attempt_evidence:
        if attempt["result"] == "fail":
            append_attempt(
                run_dir,
                "fail",
                "unknown",
                (
                    f"CI attempt 失败：failures={attempt['junit']['failures']}, "
                    f"errors={attempt['junit']['errors']}"
                ),
                None,
            )
        else:
            append_attempt(run_dir, "pass", "none", "CI attempt 完整通过", None)
    # 先落盘完整 manifest，再把 run-summary 收口为终态，避免出现无 manifest 的终态 run。
    _write_execution_manifest(run_dir, manifest)
    finalize(run_dir, "passed" if attempt_evidence[-1]["result"] == "pass" else "failed")
    return run_dir


def record_ci(
    iteration_dir: Path,
    run_id: str,
    modules: list[str],
    env: str,
    junit: Path,
    *,
    expected_nodeids: list[str] | None = None,
    executed_nodeids: list[str] | None = None,
    execution_file: Path | None = None,
    allure: Path | None = None,
    commit_sha: str | None = None,
    command: str | None = None,
    environment_file: Path | None = None,
    seed_registry: Path | None = None,
    target_image_ids: list[str] | None = None,
) -> Path:
    """将 CI 单次执行写为一条带精确 nodeid/JUnit/环境绑定的 attempt。"""

    expected = expected_nodeids
    if expected is None:
        expected = _expected_nodeids(iteration_dir, required=True)
    if len(expected) != len(set(expected)):
        raise EvidenceError("expected nodeids 不得重复")
    if any(not _valid_nodeid(nodeid) for nodeid in expected):
        raise EvidenceError("expected nodeids 包含非法 nodeid")
    if execution_file is not None and executed_nodeids is not None:
        raise EvidenceError("execution_file 与 executed_nodeids 不能同时提供")
    if execution_file is None and executed_nodeids is None:
        raise EvidenceError("存在 traceability nodeid 时必须提供 pytest 执行清单")
    if execution_file is None and executed_nodeids is not None:
        raise EvidenceError(
            "仅提供 executed_nodeids 无法形成完整 1.1 执行清单；请提供 execution_file"
        )
    return _record_ci_attempts(
        iteration_dir,
        run_id,
        modules,
        env,
        expected,
        [{"junit": junit, "execution": execution_file, "allure": allure}],
        commit_sha=commit_sha,
        command=command,
        environment_file=environment_file,
        seed_registry=seed_registry,
        target_image_ids=target_image_ids,
    )


def archive_reports(run_dir: Path, sources: list[Path]) -> list[Path]:
    """把显示层报告复制进本 run，不覆盖既有证据。"""

    _assert_run_dir(run_dir)
    archived: list[Path] = []
    for source in sources:
        _assert_no_symlink_components(source, label="证据来源")
        if source.is_symlink():
            raise EvidenceError(f"证据来源不得包含符号链接：{source}")
        if not source.exists():
            continue
        if source.is_dir():
            for item in source.rglob("*"):
                if item.is_symlink():
                    raise EvidenceError(f"证据来源不得包含符号链接：{source}")
                if not item.is_dir() and not item.is_file():
                    raise EvidenceError(f"证据来源必须只包含普通文件：{source}")
        elif not source.is_file():
            raise EvidenceError(f"证据来源必须是普通文件或目录：{source}")
        target = run_dir / source.name
        if target.exists() or target.is_symlink():
            raise EvidenceError(f"证据目标已存在，禁止覆盖：{target}")
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        archived.append(target)
    return archived


def _case_modules(iteration_dir: Path) -> list[str]:
    modules: set[str] = set()
    for relative in ("functional-cases.yaml", "api/cases.yaml"):
        path = iteration_dir / relative
        _assert_no_symlink_components(path, label="case 文件")
        if path.is_symlink() or not path.is_file():
            continue
        try:
            document = load_yaml(path.read_bytes()) or {}
        except (OSError, UnicodeError, ValueError) as exc:
            raise EvidenceError(f"case 文件不是安全可解析的 YAML：{path}") from exc
        if not isinstance(document, dict):
            raise EvidenceError(f"case 文件顶层必须是映射：{path}")
        cases = document.get("cases", [])
        if not isinstance(cases, list):
            raise EvidenceError(f"case 文件的 cases 必须是列表：{path}")
        for case in cases:
            if not isinstance(case, dict):
                raise EvidenceError(f"case 文件包含非对象 case：{path}")
            module = case.get("module")
            if isinstance(module, str):
                modules.add(module)
            tags = case.get("tags", [])
            if not isinstance(tags, list):
                raise EvidenceError(f"case 文件的 tags 必须是列表：{path}")
            for tag in tags:
                if isinstance(tag, str) and tag.startswith("module:"):
                    modules.add(tag.split(":", 1)[1])
    return sorted(modules)


def _new_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("run-%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{os.urandom(2).hex()}"


def _same_path(first: Path, second: Path) -> bool:
    return os.path.abspath(first) == os.path.abspath(second)


def record_ci_auto(
    iterations_dir: Path,
    junit: Path,
    env: str,
    *,
    iteration: Path | None = None,
    executed_nodeids: Path | None = None,
    first_junit: Path | None = None,
    first_executed_nodeids: Path | None = None,
    retry_junit: Path | None = None,
    retry_executed_nodeids: Path | None = None,
    allure: Path | None = None,
    first_allure: Path | None = None,
    retry_allure: Path | None = None,
    commit_sha: str | None = None,
    command: str | None = None,
    environment_file: Path | None = None,
    seed_registry: Path | None = None,
    target_image_ids: list[str] | None = None,
) -> list[Path]:
    """为一个明确选定的 eligible iteration 记录精确的 first/retry 证据链。"""

    _assert_no_symlink_components(iterations_dir, label="iterations directory")
    if iterations_dir.is_symlink() or not iterations_dir.is_dir():
        raise EvidenceError(f"iterations directory 不是安全的目录：{iterations_dir}")
    eligible = {
        "web_automation_generated",
        "api_automation_generated",
        "env_pending",
        "env_configured",
        "executing",
        "execution_passed",
        "acceptance_pending",
        "accepted",
        "merged",
    }
    if retry_junit is not None and first_junit is None:
        raise EvidenceError("retry JUnit 必须同时提供 first JUnit")
    if first_executed_nodeids is not None and first_junit is None:
        raise EvidenceError("first pytest 执行清单必须绑定 first JUnit")
    if retry_executed_nodeids is not None and retry_junit is None:
        raise EvidenceError("retry pytest 执行清单必须绑定 retry JUnit")
    if first_allure is not None and first_junit is None:
        raise EvidenceError("first Allure 必须绑定 first JUnit")
    if retry_allure is not None and retry_junit is None:
        raise EvidenceError("retry Allure 必须绑定 retry JUnit")
    if executed_nodeids is not None and (first_junit is not None or retry_junit is not None):
        raise EvidenceError("executed-nodeids 不能与 first/retry execution 组合使用")
    if first_junit is not None:
        if retry_junit is not None:
            if not _same_path(retry_junit, junit):
                raise EvidenceError("最终 JUnit 必须是 retry JUnit")
        elif not _same_path(first_junit, junit):
            raise EvidenceError("没有 retry 时最终 JUnit 必须是 first JUnit")
    attempt_inputs: list[dict[str, Any]] = []
    if first_junit is not None:
        if first_executed_nodeids is None:
            raise EvidenceError("first JUnit 必须绑定 first pytest 执行清单")
        attempt_inputs.append(
            {"junit": first_junit, "execution": first_executed_nodeids, "allure": first_allure}
        )
    if retry_junit is not None:
        if retry_executed_nodeids is None:
            raise EvidenceError("retry JUnit 必须绑定 retry pytest 执行清单")
        attempt_inputs.append(
            {"junit": retry_junit, "execution": retry_executed_nodeids, "allure": retry_allure}
        )
    elif not attempt_inputs or not _same_path(first_junit or junit, junit):
        execution = executed_nodeids or first_executed_nodeids
        if execution is None:
            raise EvidenceError("最终 JUnit 必须绑定 pytest 执行清单")
        attempt_inputs.append({"junit": junit, "execution": execution, "allure": allure})
    if not attempt_inputs:
        raise EvidenceError("至少需要一个 CI attempt")

    if iteration is not None:
        _assert_no_symlink_components(iteration, label="iteration")
        if iteration.is_symlink() or not iteration.is_dir():
            raise EvidenceError(f"iteration 不是安全的目录：{iteration}")
        if not _same_path(iteration.parent, iterations_dir):
            raise EvidenceError("--iteration 必须是 iterations directory 的直接子目录")
        candidates = [iteration]
    else:
        candidates = sorted(
            candidate
            for candidate in iterations_dir.iterdir()
            if candidate.is_dir() and not candidate.is_symlink()
        )

    eligible_candidates: list[Path] = []
    for candidate in candidates:
        aggregate = candidate / "iteration.yaml"
        _assert_no_symlink_components(candidate, label="iteration directory")
        _assert_no_symlink_components(aggregate, label="iteration 文件")
        if not aggregate.exists():
            continue
        if aggregate.is_symlink() or not aggregate.is_file():
            continue
        try:
            document = load_yaml(aggregate.read_bytes()) or {}
        except (OSError, UnicodeError, ValueError) as exc:
            raise EvidenceError(f"iteration 文件不是安全可解析的 YAML：{aggregate}") from exc
        if not isinstance(document, dict):
            raise EvidenceError(f"iteration 文件顶层必须是映射：{aggregate}")
        if document.get("state") not in eligible:
            continue
        eligible_candidates.append(candidate)

    if iteration is None and len(eligible_candidates) > 1:
        names = ", ".join(path.name for path in eligible_candidates)
        raise EvidenceError(
            "多个 iteration 同时 eligible，必须分别调用 --iteration 记录证据：" + names
        )
    if iteration is not None and not eligible_candidates:
        raise EvidenceError(f"指定 iteration 不在可执行状态：{iteration}")

    run_id = _new_run_id()
    written: list[Path] = []
    for candidate in eligible_candidates:
        modules = _case_modules(candidate)
        expected = _expected_nodeids(candidate, required=True)
        if not modules:
            raise EvidenceError(f"eligible iteration 没有可执行 module：{candidate}")
        written.append(
            _record_ci_attempts(
                candidate,
                run_id,
                modules,
                env,
                expected,
                attempt_inputs,
                commit_sha=commit_sha,
                command=command,
                environment_file=environment_file,
                seed_registry=seed_registry,
                target_image_ids=target_image_ids,
            )
        )
    return written


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
    ci.add_argument("--executed-nodeids", type=Path)
    ci.add_argument("--alluredir", type=Path)
    ci.add_argument("--commit-sha")
    ci.add_argument("--command", dest="execution_command")
    ci.add_argument("--environment-file", type=Path)
    ci.add_argument("--seed-registry", type=Path)
    ci.add_argument("--target-image-id", action="append", default=[])
    nodes = sub.add_parser("expected-nodeids")
    nodes.add_argument("iteration", type=Path)
    archive = sub.add_parser("archive")
    archive.add_argument("run_dir", type=Path)
    archive.add_argument("source", type=Path, nargs="+")
    ci_auto = sub.add_parser("record-ci-auto")
    ci_auto.add_argument("--iterations", type=Path, default=REPO_ROOT / "iterations")
    ci_auto.add_argument("--iteration", type=Path)
    ci_auto.add_argument("--env", choices=("local", "test", "ci", "prod"), default="ci")
    ci_auto.add_argument("--junit", type=Path, required=True)
    ci_auto.add_argument("--executed-nodeids", type=Path)
    ci_auto.add_argument("--first-junit", type=Path)
    ci_auto.add_argument("--first-executed-nodeids", type=Path)
    ci_auto.add_argument("--retry-junit", type=Path)
    ci_auto.add_argument("--retry-executed-nodeids", type=Path)
    ci_auto.add_argument("--alluredir", type=Path)
    ci_auto.add_argument("--first-alluredir", type=Path)
    ci_auto.add_argument("--retry-alluredir", type=Path)
    ci_auto.add_argument("--commit-sha")
    ci_auto.add_argument("--command", dest="execution_command")
    ci_auto.add_argument("--environment-file", type=Path)
    ci_auto.add_argument("--seed-registry", type=Path)
    ci_auto.add_argument("--target-image-id", action="append", default=[])
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
            print(
                record_ci(
                    args.iteration,
                    args.run_id,
                    args.module,
                    args.env,
                    args.junit,
                    execution_file=args.executed_nodeids,
                    allure=args.alluredir,
                    commit_sha=args.commit_sha,
                    command=args.execution_command,
                    environment_file=args.environment_file,
                    seed_registry=args.seed_registry,
                    target_image_ids=args.target_image_id,
                )
            )
        elif args.command == "expected-nodeids":
            for nodeid in _expected_nodeids(args.iteration, required=True):
                print(nodeid)
        elif args.command == "archive":
            for path in archive_reports(args.run_dir, args.source):
                print(path)
        elif args.command == "record-ci-auto":
            for path in record_ci_auto(
                args.iterations,
                args.junit,
                args.env,
                iteration=args.iteration,
                executed_nodeids=args.executed_nodeids,
                first_junit=args.first_junit,
                first_executed_nodeids=args.first_executed_nodeids,
                retry_junit=args.retry_junit,
                retry_executed_nodeids=args.retry_executed_nodeids,
                allure=args.alluredir,
                first_allure=args.first_alluredir,
                retry_allure=args.retry_alluredir,
                commit_sha=args.commit_sha,
                command=args.execution_command,
                environment_file=args.environment_file,
                seed_registry=args.seed_registry,
                target_image_ids=args.target_image_id,
            ):
                print(path)
    except EvidenceError as exc:
        print(f"self-debug evidence error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
