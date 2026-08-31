#!/usr/bin/env python
"""Argus 测试设计 lint 门禁。

该脚本是 requirements、test_points、functional-cases 和 API cases 的内容
与格式第二层校验。JSON Schema 负责字段形状；本脚本负责跨产物引用、覆盖、
endpoint/case 一致性和可执行语义。每条诊断使用稳定 rule_id，并给出
artifact、YAML 路径、实际问题和可执行修复建议。

这是一个单次、无副作用的 lint pass。Skill 在收到错误后必须修复源产物并
重新运行本脚本；不存在固定的自动修复轮次上限。产品事实无法由来源确认时，
应回到澄清流程，而不是猜测或绕过 lint。
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from _registry_lib import (
    REPO_ROOT,
    RegistryError,
    _assert_safe_path,
    binding_for_path,
    schema_errors,
    validate_path,
)
from argus_core.parsing import load_yaml  # pyright: ignore[reportMissingImports]

_ITERATION_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_DESIGN_FILES = {
    "requirements": "requirements.yaml",
    "exemptions": "exemptions.yaml",
    "test_points": "test_points.yaml",
    "functional_cases": "functional-cases.yaml",
    "api_spec": "api/spec.normalized.yaml",
    "api_cases": "api/cases.yaml",
}
_UI_STAGES = {
    "test_points_review",
    "test_points_accepted",
    "functional_cases_generating",
    "functional_cases_exported",
    "web_automation_generating",
    "web_automation_generated",
    "env_pending",
    "env_configured",
    "executing",
    "execution_passed",
    "execution_budget_exceeded",
    "escalated",
    "acceptance_pending",
    "accepted",
    "merged",
}
_API_STAGES = {
    "requirements_mapped",
    "spec_normalizing",
    "spec_valid",
    "api_cases_generating",
    "api_cases_exported",
    "api_automation_generating",
    "api_automation_generated",
    "env_pending",
    "env_configured",
    "executing",
    "execution_passed",
    "execution_budget_exceeded",
    "escalated",
    "acceptance_pending",
    "accepted",
    "merged",
}


@dataclass(frozen=True)
class Diagnostic:
    """One stable, actionable lint result."""

    rule_id: str
    artifact: str
    location: str
    message: str
    actual: str | None = None
    expected: str | None = None
    fix: str | None = None
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LintError(Exception):
    """Lint input cannot be safely inspected."""


def _short(value: object, limit: int = 240) -> str:
    text = str(value).replace("\x00", "<NUL>").replace("\r", "\\r").replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _artifact_name(iteration_dir: Path, relative: str) -> str:
    return f"iterations/{iteration_dir.name}/{relative}"


def _diag(
    diagnostics: list[Diagnostic],
    rule_id: str,
    iteration_dir: Path,
    relative: str,
    location: str,
    message: str,
    *,
    actual: object | None = None,
    expected: object | None = None,
    fix: str | None = None,
    severity: str = "error",
) -> None:
    diagnostics.append(
        Diagnostic(
            rule_id=rule_id,
            artifact=_artifact_name(iteration_dir, relative),
            location=location,
            message=message,
            actual=None if actual is None else _short(actual),
            expected=None if expected is None else _short(expected),
            fix=fix,
            severity=severity,
        )
    )


def _safe_iteration_dir(iteration_dir: Path) -> Path:
    candidate = iteration_dir if iteration_dir.is_absolute() else REPO_ROOT / iteration_dir
    _assert_safe_path(candidate, label="iteration directory")
    if candidate.is_symlink() or not candidate.is_dir():
        raise LintError("iteration directory must be a regular directory")
    if not _ITERATION_ID.fullmatch(candidate.name):
        raise LintError("iteration directory name is unsafe")
    return candidate


def _load_yaml_file(path: Path) -> Any:
    _assert_safe_path(path, label="design artifact", require_file=True)
    if path.is_symlink() or not path.is_file():
        raise LintError("design artifact must be a regular file")
    return load_yaml(path.read_bytes())


def _load_design(
    iteration_dir: Path,
    key: str,
    diagnostics: list[Diagnostic],
    *,
    required: bool,
) -> dict[str, Any] | None:
    relative = _DESIGN_FILES[key]
    path = iteration_dir / relative
    if not path.exists() and not path.is_symlink():
        if required:
            _diag(
                diagnostics,
                "design.missing",
                iteration_dir,
                relative,
                "<root>",
                f"{key} 产物缺失",
                actual="missing",
                expected="存在且可校验的 YAML 产物",
                fix=f"生成并保存 {relative}，再重新运行 test-design lint",
            )
        return None
    if path.is_symlink() or not path.is_file():
        _diag(
            diagnostics,
            "design.unsafe_file",
            iteration_dir,
            relative,
            "<root>",
            f"{key} 产物不是安全的普通文件",
            expected="regular file",
            fix="移除符号链接或特殊文件，写入安全的普通 YAML 文件",
        )
        return None
    try:
        validate_path(path)
        document = _load_yaml_file(path)
    except (OSError, UnicodeError, ValueError, RegistryError, LintError) as exc:
        _diag(
            diagnostics,
            "schema.invalid",
            iteration_dir,
            relative,
            "<root>",
            f"{key} 产物未通过 Schema/安全解析：{_short(exc)}",
            actual=exc,
            expected="通过 schema_registry.yaml 对应 Schema",
            fix="按 Schema 错误路径修复源 YAML，不要修改派生文件代替源文件",
        )
        return None
    if not isinstance(document, dict):
        _diag(
            diagnostics,
            "schema.root_type",
            iteration_dir,
            relative,
            "<root>",
            f"{key} 顶层必须是对象",
            actual=type(document).__name__,
            expected="mapping/object",
            fix="将 YAML 顶层改为对象，并保留对应的 schema_version",
        )
        return None
    binding = binding_for_path(path)
    if binding is None:
        _diag(
            diagnostics,
            "schema.unregistered",
            iteration_dir,
            relative,
            "<root>",
            f"{key} 产物没有注册的 Schema 绑定",
            fix="在 schema_registry.yaml 注册准确的 artifact/path/schema 绑定",
        )
        return None
    errors = schema_errors(binding, document)
    if errors:
        for error in errors:
            _diag(
                diagnostics,
                "schema.invalid",
                iteration_dir,
                relative,
                "<schema>",
                f"{key} Schema 校验失败：{error}",
                actual=error,
                expected="对应 Schema 的字段、类型和条件均满足",
                fix="按错误中给出的 YAML 路径修复源产物，然后重新 lint",
            )
        return None
    return document


def _load_iteration(iteration_dir: Path, diagnostics: list[Diagnostic]) -> dict[str, Any] | None:
    path = iteration_dir / "iteration.yaml"
    try:
        _assert_safe_path(path, label="iteration", require_file=True)
        validate_path(path)
        document = _load_yaml_file(path)
    except (OSError, UnicodeError, ValueError, RegistryError, LintError) as exc:
        _diag(
            diagnostics,
            "iteration.invalid",
            iteration_dir,
            "iteration.yaml",
            "<root>",
            f"iteration.yaml 未通过安全解析或 Schema：{_short(exc)}",
            actual=exc,
            expected="通过 iteration.yaml 的安全解析和 Schema",
            fix="先修复 iteration.yaml 的 Schema 和生命周期状态，再运行 lint",
        )
        return None
    if not isinstance(document, dict):
        _diag(
            diagnostics,
            "iteration.root_type",
            iteration_dir,
            "iteration.yaml",
            "<root>",
            "iteration.yaml 顶层必须是对象",
            expected="mapping/object",
            fix="将 iteration.yaml 顶层改为对象",
        )
        return None
    return document


def _duplicates(values: Iterable[object]) -> list[object]:
    seen: set[object] = set()
    duplicate: set[object] = set()
    for value in values:
        if value in seen:
            duplicate.add(value)
        seen.add(value)
    return sorted(duplicate, key=str)


def _ids(
    document: dict[str, Any],
    key: str,
    id_key: str,
    diagnostics: list[Diagnostic],
    iteration_dir: Path,
) -> set[str]:
    values = document.get(key, [])
    if not isinstance(values, list):
        return set()
    identifiers = [item.get(id_key) for item in values if isinstance(item, dict)]
    for duplicate in _duplicates(identifiers):
        _diag(
            diagnostics,
            "design.duplicate_id",
            iteration_dir,
            _DESIGN_FILES.get(key, key),
            f"{key}[{id_key}={duplicate}]",
            f"{key} 中存在重复 ID",
            actual=duplicate,
            expected="同一产物内 ID 唯一",
            fix=f"保留一个 {duplicate}，其余条目分配稳定且未占用的 ID",
        )
    return {value for value in identifiers if isinstance(value, str)}


def _accepted_exemptions(exemptions: dict[str, Any] | None) -> dict[str, str]:
    if not exemptions or exemptions.get("status") != "accepted":
        return {}
    values = exemptions.get("exemptions", [])
    if not isinstance(values, list):
        return {}
    result: dict[str, str] = {}
    for item in values:
        if isinstance(item, dict):
            rid = item.get("requirement_id")
            kind = item.get("kind")
            if isinstance(rid, str) and isinstance(kind, str):
                result[rid] = kind
    return result


def _check_requirements(
    iteration_dir: Path,
    requirements: dict[str, Any],
    diagnostics: list[Diagnostic],
) -> set[str]:
    requirement_ids = _ids(
        requirements, "requirements", "requirement_id", diagnostics, iteration_dir
    )
    for index, requirement in enumerate(requirements.get("requirements", [])):
        if not isinstance(requirement, dict):
            continue
        source = requirement.get("source")
        if source is not None and not isinstance(source, str):
            _diag(
                diagnostics,
                "requirements.source_type",
                iteration_dir,
                "requirements.yaml",
                f"requirements[{index}].source",
                "需求来源引用必须是字符串",
                actual=type(source).__name__,
                expected="string path or URL",
                fix="保留可追溯的字符串来源；没有来源时删除该可选字段",
            )
    return requirement_ids


def _check_exemptions(
    iteration_dir: Path,
    exemptions: dict[str, Any],
    requirement_ids: set[str],
    diagnostics: list[Diagnostic],
) -> dict[str, str]:
    values = exemptions.get("exemptions", [])
    if not isinstance(values, list):
        return {}
    exemption_ids = [item.get("requirement_id") for item in values if isinstance(item, dict)]
    for duplicate in _duplicates(exemption_ids):
        _diag(
            diagnostics,
            "exemptions.duplicate_requirement",
            iteration_dir,
            "exemptions.yaml",
            f"exemptions[requirement_id={duplicate}]",
            "同一个 requirement 只能有一条 exemption",
            actual=duplicate,
            expected="每个 requirement 最多一条 exemption",
            fix="合并重复 exemption，保留一个有明确 kind/reason 的条目",
        )
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            continue
        rid = item.get("requirement_id")
        if isinstance(rid, str) and rid not in requirement_ids:
            _diag(
                diagnostics,
                "exemptions.unknown_requirement",
                iteration_dir,
                "exemptions.yaml",
                f"exemptions[{index}].requirement_id",
                "豁免引用了不存在的 requirement",
                actual=rid,
                expected="requirements.yaml 中存在的 R####",
                fix="改为真实 requirement_id，或删除无依据的豁免",
            )
        if exemptions.get("status") == "accepted" and not str(item.get("reason", "")).strip():
            _diag(
                diagnostics,
                "exemptions.reason_required",
                iteration_dir,
                "exemptions.yaml",
                f"exemptions[{index}].reason",
                "accepted exemption 必须有非空理由",
                expected="可审计且非空的 reason",
                fix="补充基于需求/源码/环境事实的具体豁免理由",
            )
    return _accepted_exemptions(exemptions)


def _check_test_points(
    iteration_dir: Path,
    test_points: dict[str, Any],
    requirement_ids: set[str],
    exemptions: dict[str, str],
    requirements: dict[str, Any] | None,
    diagnostics: list[Diagnostic],
) -> set[str]:
    point_ids = _ids(test_points, "test_points", "test_point_id", diagnostics, iteration_dir)
    values = test_points.get("test_points", [])
    if not isinstance(values, list):
        return point_ids
    cited: set[str] = set()
    for index, point in enumerate(values):
        if not isinstance(point, dict):
            continue
        rids = point.get("requirement_ids", [])
        if not isinstance(rids, list):
            continue
        for rid in rids:
            if isinstance(rid, str):
                cited.add(rid)
                if rid not in requirement_ids:
                    _diag(
                        diagnostics,
                        "test_points.unknown_requirement",
                        iteration_dir,
                        "test_points.yaml",
                        f"test_points[{index}].requirement_ids",
                        "测试点引用了不存在的 requirement",
                        actual=rid,
                        expected="requirements.yaml 中存在的 R####",
                        fix="改为真实 requirement_id，不要创建占位需求",
                    )
    if requirements and requirements.get("status") == "accepted":
        for rid in sorted(requirement_ids - cited):
            if exemptions.get(rid) == "not_testable":
                continue
            _diag(
                diagnostics,
                "coverage.requirement_to_test_point",
                iteration_dir,
                "test_points.yaml",
                "test_points",
                "accepted requirement 没有被任何测试点覆盖",
                actual=rid,
                expected="至少一个 test_point，或 accepted not_testable exemption",
                fix="新增引用该 requirement 的测试点，或先取得有依据的 not_testable 豁免",
            )
    return point_ids


def _module_tags(case: dict[str, Any]) -> list[str]:
    tags = case.get("tags", [])
    return [tag for tag in tags if isinstance(tag, str) and tag.startswith("module:")]


def _check_functional_cases(
    iteration_dir: Path,
    cases: dict[str, Any],
    point_ids: set[str],
    diagnostics: list[Diagnostic],
) -> set[str]:
    case_ids = _ids(cases, "cases", "case_id", diagnostics, iteration_dir)
    values = cases.get("cases", [])
    if not isinstance(values, list):
        return case_ids
    cited_points: set[str] = set()
    for index, case in enumerate(values):
        if not isinstance(case, dict):
            continue
        tags = _module_tags(case)
        if len(tags) != 1:
            _diag(
                diagnostics,
                "functional.module_tag_exactly_one",
                iteration_dir,
                "functional-cases.yaml",
                f"cases[{index}].tags",
                "每个功能用例必须有且仅有一个 module:<name> tag",
                actual=tags,
                expected="exactly one module tag",
                fix="保留一个真实核心模块 tag，删除多余或补上缺失的 module tag",
            )
        point_values = case.get("test_point_ids", [])
        if isinstance(point_values, list):
            for point_id in point_values:
                if isinstance(point_id, str):
                    cited_points.add(point_id)
                    if point_id not in point_ids:
                        _diag(
                            diagnostics,
                            "functional.unknown_test_point",
                            iteration_dir,
                            "functional-cases.yaml",
                            f"cases[{index}].test_point_ids",
                            "功能用例引用了不存在的测试点",
                            actual=point_id,
                            expected="test_points.yaml 中存在的 T####",
                            fix="改为真实 test_point_id，不要伪造来源关系",
                        )
        steps = case.get("steps", [])
        if isinstance(steps, list):
            for step_index, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue
                expected = step.get("expected")
                if not isinstance(expected, str) or not expected.strip():
                    _diag(
                        diagnostics,
                        "functional.expected_observable",
                        iteration_dir,
                        "functional-cases.yaml",
                        f"cases[{index}].steps[{step_index}].expected",
                        "步骤预期不能为空",
                        actual=expected,
                        expected="可观察的 UI 状态、文案或派生值关系",
                        fix="填写可由执行者直接观察或计算的预期，不使用‘正常/完成’等空泛词",
                    )
    if cases.get("status") in {"valid", "exported"}:
        for point_id in sorted(point_ids - cited_points):
            _diag(
                diagnostics,
                "coverage.test_point_to_functional_case",
                iteration_dir,
                "functional-cases.yaml",
                "cases",
                "有效测试点没有被功能用例覆盖",
                actual=point_id,
                expected="至少一个 functional case 引用该 T####",
                fix="新增功能用例并在 test_point_ids 中引用该测试点",
            )
    return case_ids


def _check_api_spec(
    iteration_dir: Path, spec: dict[str, Any], diagnostics: list[Diagnostic]
) -> set[str]:
    values = spec.get("endpoints", [])
    if not isinstance(values, list):
        return set()
    operation_ids: list[object] = []
    for index, endpoint in enumerate(values):
        if not isinstance(endpoint, dict):
            continue
        operation_ids.append(endpoint.get("operation_id"))
        if (
            endpoint.get("out_of_scope")
            and not str(endpoint.get("out_of_scope_reason", "")).strip()
        ):
            _diag(
                diagnostics,
                "api_spec.out_of_scope_reason",
                iteration_dir,
                "api/spec.normalized.yaml",
                f"endpoints[{index}].out_of_scope_reason",
                "out_of_scope endpoint 必须有非空理由",
                expected="具体、可审计的 out_of_scope_reason",
                fix="补充范围排除依据，或移除 out_of_scope 标记并生成用例",
            )
    for duplicate in _duplicates(operation_ids):
        _diag(
            diagnostics,
            "api_spec.duplicate_operation_id",
            iteration_dir,
            "api/spec.normalized.yaml",
            "endpoints.operation_id",
            "normalized spec 中 operation_id 必须唯一",
            actual=duplicate,
            expected="每个 endpoint 一个稳定 operation_id",
            fix="为不同 endpoint 分配稳定且唯一的 operation_id",
        )
    return {value for value in operation_ids if isinstance(value, str)}


def _expected_value_matches_type(value: object, value_type: object) -> bool:
    if value_type == "string":
        return isinstance(value, str)
    if value_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "object":
        return isinstance(value, dict)
    if value_type == "array":
        return isinstance(value, list)
    if value_type == "null":
        return value is None
    return False


def _check_api_response_contract(
    iteration_dir: Path,
    case_index: int,
    expected_response: dict[str, Any],
    diagnostics: list[Diagnostic],
) -> None:
    assertions = expected_response.get("body_assertions", [])
    if not isinstance(assertions, list):
        return
    paths: set[str] = set()
    for assertion_index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict):
            continue
        path = assertion.get("path")
        operator = assertion.get("operator")
        value_type = assertion.get("value_type")
        expected = assertion.get("expected")
        location = f"cases[{case_index}].expected_response.body_assertions[{assertion_index}]"
        if isinstance(path, str) and path in paths:
            _diag(
                diagnostics,
                "api_cases.duplicate_assertion_path",
                iteration_dir,
                "api/cases.yaml",
                location,
                "同一 API case 不应重复声明同一 response path",
                actual=path,
                expected="每个业务断言使用唯一 path",
                fix="合并重复断言，或为不同断言指定不同 JSONPath",
            )
        if isinstance(path, str):
            paths.add(path)
        if operator == "type" and expected != value_type:
            _diag(
                diagnostics,
                "api_cases.type_assertion_mismatch",
                iteration_dir,
                "api/cases.yaml",
                location,
                "type 断言的 expected 必须与 value_type 一致",
                actual=expected,
                expected=value_type,
                fix="让 expected 表示声明的 JSON 值类型，或改用 equals/contains 断言",
            )
        elif operator in {
            "equals",
            "not_equals",
            "contains",
            "matches",
        } and not _expected_value_matches_type(expected, value_type):
            _diag(
                diagnostics,
                "api_cases.typed_assertion_mismatch",
                iteration_dir,
                "api/cases.yaml",
                location,
                "业务断言 expected 的实际类型与 value_type 不一致",
                actual=type(expected).__name__,
                expected=value_type,
                fix="按 response Schema 填写同类型 expected，不能用字符串替代数组/数字",
            )
        if operator == "derived_equals" and not isinstance(expected, str):
            _diag(
                diagnostics,
                "api_cases.derived_assertion_reference",
                iteration_dir,
                "api/cases.yaml",
                location,
                "derived_equals 必须引用一个 derived_oracles.name",
                actual=expected,
                expected="oracle name string",
                fix="先定义 derived_oracles 条目，再在断言中引用其 name",
            )

    oracles = expected_response.get("derived_oracles", [])
    if not isinstance(oracles, list):
        return
    names: set[str] = set()
    oracle_by_name: dict[str, dict[str, Any]] = {}
    for oracle_index, oracle in enumerate(oracles):
        if not isinstance(oracle, dict):
            continue
        name = oracle.get("name")
        location = f"cases[{case_index}].expected_response.derived_oracles[{oracle_index}]"
        if isinstance(name, str) and name in names:
            _diag(
                diagnostics,
                "api_cases.duplicate_oracle_name",
                iteration_dir,
                "api/cases.yaml",
                location,
                "derived oracle name 必须在 case 内唯一",
                actual=name,
                expected="唯一的 snake_case oracle name",
                fix="为重复 oracle 分配稳定唯一名称",
            )
        if isinstance(name, str):
            names.add(name)
            oracle_by_name.setdefault(name, oracle)
        inputs = oracle.get("inputs", [])
        if isinstance(inputs, list) and not inputs:
            _diag(
                diagnostics,
                "api_cases.oracle_without_inputs",
                iteration_dir,
                "api/cases.yaml",
                location,
                "derived oracle 必须声明至少一个输入来源",
                expected="seed、response、prev_response 或 request input",
                fix="补充每个计算变量的真实来源 JSONPath",
            )
    references = {
        assertion.get("expected")
        for assertion in assertions
        if (
            isinstance(assertion, dict)
            and assertion.get("operator") == "derived_equals"
            and isinstance(assertion.get("expected"), str)
        )
    }
    missing = sorted(
        reference
        for reference in references
        if isinstance(reference, str) and reference not in names
    )
    if missing:
        _diag(
            diagnostics,
            "api_cases.unknown_oracle_reference",
            iteration_dir,
            "api/cases.yaml",
            f"cases[{case_index}].expected_response",
            "业务断言引用了未定义的 derived oracle",
            actual=missing,
            expected="derived_oracles.name",
            fix="补齐对应 oracle，或改用不依赖 oracle 的 typed assertion",
        )
    for assertion_index, assertion in enumerate(assertions):
        if not isinstance(assertion, dict) or assertion.get("operator") != "derived_equals":
            continue
        name = assertion.get("expected")
        if not isinstance(name, str):
            continue
        oracle = oracle_by_name.get(name)
        if oracle is None:
            continue
        location = f"cases[{case_index}].expected_response.body_assertions[{assertion_index}]"
        if assertion.get("value_type") != oracle.get("value_type"):
            _diag(
                diagnostics,
                "api_cases.derived_type_mismatch",
                iteration_dir,
                "api/cases.yaml",
                location,
                "derived_equals 的 value_type 必须与 oracle 一致",
                actual=assertion.get("value_type"),
                expected=oracle.get("value_type"),
                fix="统一 body_assertions 与 derived_oracles 的结果类型",
            )
        if assertion.get("path") != oracle.get("target_path"):
            _diag(
                diagnostics,
                "api_cases.derived_target_mismatch",
                iteration_dir,
                "api/cases.yaml",
                location,
                "derived_equals 的 path 必须与 oracle.target_path 一致",
                actual=assertion.get("path"),
                expected=oracle.get("target_path"),
                fix="让断言 path 与派生 oracle 的目标响应字段逐字一致",
            )
    unused = sorted(
        name for name in names if name not in {ref for ref in references if isinstance(ref, str)}
    )
    if unused:
        _diag(
            diagnostics,
            "api_cases.unused_oracle",
            iteration_dir,
            "api/cases.yaml",
            f"cases[{case_index}].expected_response.derived_oracles",
            "derived oracle 必须被一个 derived_equals 业务断言引用",
            actual=unused,
            expected="每个 oracle name 都有对应 body_assertions.expected",
            fix="补充引用该 oracle 的 typed derived_equals 断言，或删除无效 oracle",
        )


def _check_api_cases(
    iteration_dir: Path,
    api_cases: dict[str, Any],
    spec: dict[str, Any] | None,
    requirement_ids: set[str],
    exemptions: dict[str, str],
    diagnostics: list[Diagnostic],
) -> set[str]:
    api_ids = _ids(api_cases, "cases", "api_case_id", diagnostics, iteration_dir)
    values = api_cases.get("cases", [])
    if not isinstance(values, list):
        return api_ids
    endpoints: dict[str, dict[str, Any]] = {}
    for endpoint in (spec or {}).get("endpoints", []):
        if isinstance(endpoint, dict) and isinstance(endpoint.get("operation_id"), str):
            endpoints[endpoint["operation_id"]] = endpoint
    by_operation: dict[str, list[dict[str, Any]]] = {}
    cited_requirements: set[str] = set()
    for index, case in enumerate(values):
        if not isinstance(case, dict):
            continue
        rids = case.get("requirement_ids", [])
        if isinstance(rids, list):
            for rid in rids:
                if isinstance(rid, str):
                    cited_requirements.add(rid)
                    if rid not in requirement_ids:
                        _diag(
                            diagnostics,
                            "api_cases.unknown_requirement",
                            iteration_dir,
                            "api/cases.yaml",
                            f"cases[{index}].requirement_ids",
                            "API case 引用了不存在的 requirement",
                            actual=rid,
                            expected="requirements.yaml 中存在的 R####",
                            fix="改为真实 requirement_id，不要伪造 R→A 链路",
                        )
        expected_response = case.get("expected_response")
        if isinstance(expected_response, dict):
            _check_api_response_contract(iteration_dir, index, expected_response, diagnostics)
        operation_id = case.get("operation_id")
        if isinstance(operation_id, str):
            by_operation.setdefault(operation_id, []).append(case)
            endpoint = endpoints.get(operation_id)
            if endpoint is None and spec is not None:
                _diag(
                    diagnostics,
                    "api_cases.unknown_operation",
                    iteration_dir,
                    "api/cases.yaml",
                    f"cases[{index}].operation_id",
                    "API case 的 operation_id 不存在于 normalized spec",
                    actual=operation_id,
                    expected="api/spec.normalized.yaml 中的 operation_id",
                    fix="改为真实 operation_id，或先补充并规范化真实 endpoint",
                )
            elif endpoint is not None:
                if case.get("endpoint") != endpoint.get("path"):
                    _diag(
                        diagnostics,
                        "api_cases.endpoint_mismatch",
                        iteration_dir,
                        "api/cases.yaml",
                        f"cases[{index}].endpoint",
                        "API case endpoint 与 normalized spec 不一致",
                        actual=case.get("endpoint"),
                        expected=endpoint.get("path"),
                        fix="以 normalized spec 的 path 为准更新 API case",
                    )
                if case.get("method") != endpoint.get("method"):
                    _diag(
                        diagnostics,
                        "api_cases.method_mismatch",
                        iteration_dir,
                        "api/cases.yaml",
                        f"cases[{index}].method",
                        "API case method 与 normalized spec 不一致",
                        actual=case.get("method"),
                        expected=endpoint.get("method"),
                        fix="以 normalized spec 的 method 为准更新 API case",
                    )
        variables = (case.get("request") or {}).get("variables", [])
        has_previous_response = isinstance(variables, list) and any(
            isinstance(variable, dict) and variable.get("source") == "prev_response"
            for variable in variables
        )
        if has_previous_response and case.get("side_effect", "none") == "none":
            _diag(
                diagnostics,
                "api_cases.replay_side_effect",
                iteration_dir,
                "api/cases.yaml",
                f"cases[{index}].side_effect",
                "依赖 prev_response 的可回放链不能声明 side_effect=none",
                actual="none",
                expected="整个 setup/replay 链的真实副作用",
                fix="按 setup 链声明 creates/updates/deletes，或移除前置响应依赖",
            )
    if spec is not None and api_cases.get("status") in {"cases_valid", "exported"}:
        for operation_id, endpoint in endpoints.items():
            if endpoint.get("out_of_scope"):
                continue
            operation_cases = by_operation.get(operation_id, [])
            kinds = {case.get("case_type") for case in operation_cases}
            if "happy_path" not in kinds:
                _diag(
                    diagnostics,
                    "coverage.api_happy_path",
                    iteration_dir,
                    "api/cases.yaml",
                    f"operation_id={operation_id}",
                    "in-scope endpoint 缺少 happy_path case",
                    expected="至少一个 happy_path case",
                    fix="为该 endpoint 增加基于真实响应 Schema 的正向 case",
                )
            if not kinds.intersection({"negative", "edge"}):
                _diag(
                    diagnostics,
                    "coverage.api_negative_or_edge",
                    iteration_dir,
                    "api/cases.yaml",
                    f"operation_id={operation_id}",
                    "in-scope endpoint 缺少 negative/edge case",
                    expected="至少一个 negative 或 edge case",
                    fix="为该 endpoint 增加可观察错误或边界行为 case",
                )
    if api_cases.get("status") in {"cases_valid", "exported"}:
        for rid in sorted(requirement_ids - cited_requirements):
            if exemptions.get(rid) == "not_testable":
                continue
            _diag(
                diagnostics,
                "coverage.requirement_to_api_case",
                iteration_dir,
                "api/cases.yaml",
                "cases",
                "accepted requirement 没有被 API case 覆盖",
                actual=rid,
                expected="至少一个 API case 引用该 R####，或 accepted not_testable exemption",
                fix="新增真实 API case 并引用该 requirement，或补充有依据的豁免",
            )
    return api_ids


def _run_existing_semantic_checks(
    iteration_dir: Path,
    functional_cases: dict[str, Any] | None,
    api_spec: dict[str, Any] | None,
    api_cases: dict[str, Any] | None,
    diagnostics: list[Diagnostic],
) -> None:
    """将已有专门语义检查器纳入同一 lint 输出合同。"""

    if functional_cases is not None:
        try:
            from check_functional_expectations import (  # type: ignore[import-not-found]
                Report as ExpectationReport,
            )
            from check_functional_expectations import (
                check_cases,
                load_seed_registry,
            )

            report = ExpectationReport()
            seeds = load_seed_registry(REPO_ROOT / "shared/testdata/seed-registry.yaml")
            check_cases(functional_cases, seeds, True, report)
            for problem in [*report.problems, *report.warnings]:
                _diag(
                    diagnostics,
                    "functional.expectation",
                    iteration_dir,
                    "functional-cases.yaml",
                    "cases",
                    problem,
                    fix="按 seed registry 和 expected_kind 修复派生值预期；不要复制固定金额",
                    severity="error" if problem in report.problems else "warning",
                )
        except (OSError, UnicodeError, ValueError, RegistryError) as exc:
            _diag(
                diagnostics,
                "functional.expectation_checker",
                iteration_dir,
                "functional-cases.yaml",
                "<checker>",
                f"功能预期检查器无法安全运行：{_short(exc)}",
                fix="修复 seed registry 或功能用例后重新运行 lint",
            )
    if api_spec is not None and api_cases is not None:
        try:
            from check_api_coverage import (  # type: ignore[import-not-found]
                Report as ApiReport,
            )
            from check_api_coverage import (
                check,
                load_exemptions,
            )

            requirements_path = iteration_dir / "requirements.yaml"
            requirements = (
                _load_yaml_file(requirements_path) if requirements_path.is_file() else None
            )
            if isinstance(requirements, dict):
                report = ApiReport()
                exemptions = load_exemptions(iteration_dir)
                check(api_spec, api_cases, requirements, exemptions, report)
                for problem in report.problems:
                    _diag(
                        diagnostics,
                        "api.semantic",
                        iteration_dir,
                        "api/cases.yaml",
                        "cases",
                        problem,
                        fix="按 normalized spec、requirements 和 API case 的真实关系修复",
                    )
        except (OSError, UnicodeError, ValueError, RegistryError) as exc:
            _diag(
                diagnostics,
                "api.semantic_checker",
                iteration_dir,
                "api/cases.yaml",
                "<checker>",
                f"API 语义检查器无法安全运行：{_short(exc)}",
                fix="修复 API 输入产物后重新运行 lint",
            )


_STAGE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "requirements": ("requirements",),
    "exemptions": ("requirements", "exemptions"),
    "test_points": ("requirements", "exemptions", "test_points"),
    "functional_cases": (
        "requirements",
        "exemptions",
        "test_points",
        "functional_cases",
    ),
    "api_spec": ("requirements", "exemptions", "api_spec"),
    "api_cases": ("requirements", "exemptions", "api_spec", "api_cases"),
}


def _requested_keys(
    stage: str,
    iteration: dict[str, Any] | None,
    iteration_dir: Path,
) -> tuple[list[str], set[str]]:
    if stage != "all":
        if stage == "acceptance":
            stage = "all"
        elif stage not in _STAGE_DEPENDENCIES:
            raise LintError(f"unknown lint stage: {stage}")
        else:
            keys = list(_STAGE_DEPENDENCIES[stage])
            return keys, set(keys)
    existing = [
        key for key, relative in _DESIGN_FILES.items() if (iteration_dir / relative).exists()
    ]
    required: set[str] = set()
    if iteration is not None:
        state = iteration.get("state")
        branches = iteration.get("branches") or {}
        ui = bool(branches.get("ui"))
        api = bool(branches.get("api"))
        if state != "created":
            required.add("requirements")
        if ui and state in _UI_STAGES:
            required.update({"exemptions", "test_points"})
        if ui and state in {
            "functional_cases_generating",
            "functional_cases_exported",
            "web_automation_generating",
            "web_automation_generated",
            "env_pending",
            "env_configured",
            "executing",
            "execution_passed",
            "execution_budget_exceeded",
            "escalated",
            "acceptance_pending",
            "accepted",
            "merged",
        }:
            required.add("functional_cases")
        if api and state in _API_STAGES:
            required.add("exemptions")
        if api and state in {
            "spec_normalizing",
            "spec_valid",
            "api_cases_generating",
            "api_cases_exported",
            "api_automation_generating",
            "api_automation_generated",
            "env_pending",
            "env_configured",
            "executing",
            "execution_passed",
            "execution_budget_exceeded",
            "escalated",
            "acceptance_pending",
            "accepted",
            "merged",
        }:
            required.update({"api_spec", "api_cases"})
    return sorted(set(existing) | required), required


def lint_iteration(iteration_dir: Path, stage: str = "all") -> list[Diagnostic]:
    """Return deterministic diagnostics for one iteration without writing files."""

    candidate = _safe_iteration_dir(iteration_dir)
    diagnostics: list[Diagnostic] = []
    iteration_path = candidate / "iteration.yaml"
    iteration = (
        _load_iteration(candidate, diagnostics)
        if iteration_path.exists() or iteration_path.is_symlink() or stage == "all"
        else None
    )
    keys, required = _requested_keys(stage, iteration, candidate)
    documents: dict[str, dict[str, Any]] = {}
    for key in keys:
        document = _load_design(
            candidate, key, diagnostics, required=key in required or stage == key
        )
        if document is not None:
            documents[key] = document
            if document.get("iteration_id") != candidate.name:
                _diag(
                    diagnostics,
                    "design.iteration_id_mismatch",
                    candidate,
                    _DESIGN_FILES[key],
                    "iteration_id",
                    "产物 iteration_id 与所在目录不一致",
                    actual=document.get("iteration_id"),
                    expected=candidate.name,
                    fix="使用当前 iteration 目录的稳定 ID，不要跨 iteration 复用产物",
                )

    requirements = documents.get("requirements")
    requirement_ids: set[str] = set()
    if requirements is not None:
        requirement_ids = _check_requirements(candidate, requirements, diagnostics)
    exemptions = documents.get("exemptions")
    exemption_map: dict[str, str] = {}
    if exemptions is not None:
        exemption_map = _check_exemptions(candidate, exemptions, requirement_ids, diagnostics)

    test_points = documents.get("test_points")
    point_ids: set[str] = set()
    if test_points is not None:
        point_ids = _check_test_points(
            candidate,
            test_points,
            requirement_ids,
            exemption_map,
            requirements,
            diagnostics,
        )

    functional_cases = documents.get("functional_cases")
    if functional_cases is not None:
        _check_functional_cases(candidate, functional_cases, point_ids, diagnostics)

    api_spec = documents.get("api_spec")
    if api_spec is not None:
        _check_api_spec(candidate, api_spec, diagnostics)
    api_cases = documents.get("api_cases")
    if api_cases is not None:
        _check_api_cases(
            candidate,
            api_cases,
            api_spec,
            requirement_ids,
            exemption_map,
            diagnostics,
        )

    _run_existing_semantic_checks(candidate, functional_cases, api_spec, api_cases, diagnostics)
    return sorted(
        diagnostics,
        key=lambda item: (item.severity != "error", item.artifact, item.location, item.rule_id),
    )


def format_diagnostic(diagnostic: Diagnostic, *, json_output: bool = False) -> str:
    if json_output:
        import json

        return json.dumps(diagnostic.to_dict(), ensure_ascii=False, sort_keys=True)
    line = (
        f"[{diagnostic.severity.upper()}] [{diagnostic.rule_id}] "
        f"{diagnostic.artifact}#{diagnostic.location}: {diagnostic.message}"
    )
    if diagnostic.actual is not None:
        line += f"；实际：{diagnostic.actual}"
    if diagnostic.expected is not None:
        line += f"；期望：{diagnostic.expected}"
    if diagnostic.fix is not None:
        line += f"；修复：{diagnostic.fix}"
    return line


def _iter_root(root: Path) -> list[Path]:
    _assert_safe_path(root, label="iterations root")
    if root.is_symlink() or not root.is_dir():
        raise LintError("iterations root must be a regular directory")
    try:
        entries = sorted(root.iterdir())
    except OSError as exc:
        raise LintError("iterations root cannot be read") from exc
    return [entry for entry in entries if entry.is_dir() and not entry.is_symlink()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, nargs="?", help="iterations/<id> 目录")
    parser.add_argument("--all", action="store_true", help="lint iterations/ 下全部 iteration")
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT / "iterations", help="--all 使用的 iteration 根目录"
    )
    parser.add_argument(
        "--stage",
        choices=[*sorted(_DESIGN_FILES), "acceptance", "all"],
        default="all",
        help="只 lint 一个设计阶段；acceptance 等价于当前分支的全部设计产物",
    )
    parser.add_argument("--json", action="store_true", help="每条诊断输出为 JSON")
    args = parser.parse_args(argv)
    if args.all == (args.iteration is not None):
        parser.error("必须且只能指定 iteration 位置参数或 --all")

    try:
        if args.all:
            root = args.root if args.root.is_absolute() else REPO_ROOT / args.root
            iterations = _iter_root(root)
        else:
            iterations = [args.iteration]
        diagnostics: list[Diagnostic] = []
        for iteration in iterations:
            diagnostics.extend(lint_iteration(iteration, args.stage))
    except (LintError, OSError, ValueError, RegistryError) as exc:
        print(f"test-design lint error: {_short(exc)}", file=sys.stderr)
        return 1

    for diagnostic in diagnostics:
        print(format_diagnostic(diagnostic, json_output=args.json))
    errors = [item for item in diagnostics if item.severity == "error"]
    warnings = [item for item in diagnostics if item.severity == "warning"]
    print(
        f"test-design lint: {len(errors)} error(s), {len(warnings)} warning(s)",
        file=sys.stderr if errors else sys.stdout,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
