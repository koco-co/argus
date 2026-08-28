#!/usr/bin/env python
"""API endpoint 覆盖检查器（Roadmap 1.8、PRD §4.4）。

将 ``api/spec.normalized.yaml`` 与 ``api/cases.yaml`` 逐项比对：

- 未标记 ``out_of_scope`` 的 endpoint 至少有一个 ``happy_path`` 和一个
  ``negative``/``edge`` 用例，缺口报告对应的 operation_id；
- 标记 ``out_of_scope: true`` 的 endpoint 必须带非空
  ``out_of_scope_reason``（完全省略该字段仍合法，遵循 DATA_MODEL §6 的条件规则）；
- 每个 API case 都引用 ``requirement_ids[]``；未被已接受 ``not_testable`` 豁免移除的需求，
  至少出现在一个 API case 的 ``requirement_ids[]`` 中（``manual_only`` 不会移除 R→A 要求，
  它只停止自动化层）。

检查前先通过共享注册表执行来源 Schema 门禁。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml
from _registry_lib import REPO_ROOT, RegistryError, validate_path

HappyKinds = {"happy_path"}
NegativeKinds = {"negative", "edge"}


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def fail(self, *messages: str) -> None:
        self.problems.extend(messages)


def _load_validated(iteration_dir: Path, name: str) -> dict[str, Any]:
    path = iteration_dir / name
    validate_path(path)
    document: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return document


def load_exemptions(iteration_dir: Path) -> dict[str, str]:
    """返回带非空理由且已接受豁免的 requirement_id -> kind 映射。"""
    path = iteration_dir / "exemptions.yaml"
    if not path.exists():
        return {}
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if document.get("status") != "accepted":
        return {}
    honored: dict[str, str] = {}
    for entry in document.get("exemptions", []):
        if entry.get("reason", "").strip():
            honored[entry["requirement_id"]] = entry["kind"]
    return honored


def check(
    spec: dict[str, Any],
    cases: dict[str, Any],
    requirements: dict[str, Any],
    exemptions: dict[str, str],
    report: Report,
) -> None:
    per_operation: dict[str, list[dict[str, Any]]] = {}
    for case in cases["cases"]:
        rids = case.get("requirement_ids") or []
        if not rids:
            report.fail(f"API case {case['api_case_id']} has no requirement_ids")
        # side_effect 描述整个可回放链（包括 setup），不是只描述目标请求。
        # 任何依赖 prev_response 的 case 都已经执行过前置请求；标成 none
        # 会让 M9 在失败重跑时跳过 fresh reset，产生重复资源或污染。
        if (
            any(
                isinstance(variable, dict) and variable.get("source") == "prev_response"
                for variable in (case.get("request", {}) or {}).get("variables", [])
            )
            and case.get("side_effect", "none") == "none"
        ):
            report.fail(
                f"API case {case['api_case_id']} uses prev_response but declares "
                "side_effect=none; declare the setup chain side effect"
            )
        per_operation.setdefault(case["operation_id"], []).append(case)

    for endpoint in spec["endpoints"]:
        operation_id = endpoint["operation_id"]
        if endpoint.get("out_of_scope"):
            if not (endpoint.get("out_of_scope_reason") or "").strip():
                report.fail(f"endpoint {operation_id} is out_of_scope without a non-empty reason")
            continue  # out-of-scope endpoints carry no case demand
        kinds = {c["case_type"] for c in per_operation.get(operation_id, [])}
        if not (kinds & HappyKinds):
            report.fail(f"endpoint {operation_id} lacks a happy_path case")
        if not (kinds & NegativeKinds):
            report.fail(f"endpoint {operation_id} lacks a negative/edge case")
        declared_statuses = {
            response.get("status_code")
            for response in endpoint.get("responses", [])
            if isinstance(response, dict)
        }
        for case in per_operation.get(operation_id, []):
            status_code = (case.get("expected_response") or {}).get("status_code")
            if isinstance(status_code, int) and status_code >= 500:
                report.fail(
                    f"API case {case['api_case_id']} expects HTTP {status_code}; "
                    "backend_5xx is escalation-only and cannot be a passing oracle"
                )
            if status_code not in declared_statuses:
                report.fail(
                    f"API case {case['api_case_id']} expects HTTP {status_code}, "
                    f"but endpoint {operation_id} does not declare that response"
                )

    cited: set[str] = set()
    for case in cases["cases"]:
        cited.update(case.get("requirement_ids") or [])
    for requirement in requirements["requirements"]:
        rid = requirement["requirement_id"]
        if exemptions.get(rid) == "not_testable":
            continue
        if rid not in cited:
            report.fail(f"requirement {rid} is not cited by any API case")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, help="iterations/<id> 目录")
    args = parser.parse_args(argv)

    iteration_dir = args.iteration if args.iteration.is_absolute() else REPO_ROOT / args.iteration
    if not iteration_dir.is_dir():
        print(f"error: iteration directory {iteration_dir} not found", file=sys.stderr)
        return 1

    report = Report()
    try:
        spec = _load_validated(iteration_dir, "api/spec.normalized.yaml")
        cases = _load_validated(iteration_dir, "api/cases.yaml")
        requirements = _load_validated(iteration_dir, "requirements.yaml")
        exemptions = load_exemptions(iteration_dir)
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    check(spec, cases, requirements, exemptions, report)

    if report.problems:
        for problem in report.problems:
            print(f"api coverage gap: {problem}")
        print(f"check_api_coverage: {len(report.problems)} gap(s)", file=sys.stderr)
        return 1
    print("check_api_coverage: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
