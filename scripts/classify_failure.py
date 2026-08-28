#!/usr/bin/env python
"""根据结构化测试证据机械预分类 M9 故障。"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_ESCALATION_ONLY = {
    "environment_unavailable",
    "auth_failure",
    "backend_5xx",
    "product_behavior_mismatch",
    "requirement_conflict",
}
_REPAIRABLE = {
    "locator_drift",
    "timing",
    "fixture_error",
    "serialization_error",
    "import_type_error",
    "data_issue",
}


@dataclass(frozen=True)
class Verdict:
    failure_class: str
    escalation_only: bool
    explanation: str


def classify(evidence: dict[str, Any]) -> Verdict:
    """按不可降级优先级返回唯一分类。"""

    status = evidence.get("status_code")
    error_type = str(evidence.get("error_type", "")).lower()
    if evidence.get("requirement_conflict"):
        result = ("requirement_conflict", "需求与可观察行为冲突")
    elif evidence.get("redirected_to_login") or status in {401, 403}:
        result = ("auth_failure", "鉴权拒绝或跳转到登录页")
    elif isinstance(status, int) and 500 <= status <= 599:
        result = ("backend_5xx", f"后端返回 {status}")
    elif evidence.get("connection_error") or "connection" in error_type:
        result = ("environment_unavailable", "连接失败或环境不可用")
    elif evidence.get("element_present") and evidence.get("actual_differs"):
        result = ("product_behavior_mismatch", "元素存在但状态或值与预期不符")
    elif "assertion" in error_type:
        result = ("product_behavior_mismatch", "断言失败必须升级，禁止自动改预期")
    elif "timeout" in error_type and not evidence.get("element_present", False):
        result = ("locator_drift", "超时且 DOM 证据中元素不存在")
    elif "timeout" in error_type:
        result = ("timing", "元素存在但等待条件未满足")
    elif "fixture" in error_type:
        result = ("fixture_error", "fixture 装载失败")
    elif "validation" in error_type or "serial" in error_type:
        result = ("serialization_error", "模型校验或序列化失败")
    elif "import" in error_type or "typeerror" in error_type:
        result = ("import_type_error", "导入或类型错误")
    elif evidence.get("data_issue"):
        result = ("data_issue", "种子连接或命名空间异常")
    else:
        result = ("unknown", "证据不足，禁止自动修复")
    name, explanation = result
    return Verdict(name, name in _ESCALATION_ONLY or name == "unknown", explanation)


def refine(verdict: Verdict, proposed: str) -> Verdict:
    """仅允许在可修复边界内细分，升级类永远不可降级。"""

    if verdict.escalation_only and proposed != verdict.failure_class:
        raise ValueError(f"{verdict.failure_class} 是升级类，不得降级为 {proposed}")
    if proposed not in _REPAIRABLE | _ESCALATION_ONLY | {"unknown"}:
        raise ValueError(f"未知分类：{proposed}")
    return Verdict(
        proposed,
        proposed in _ESCALATION_ONLY or proposed == "unknown",
        verdict.explanation,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("evidence", type=Path, help="结构化 JSON 证据")
    args = parser.parse_args(argv)
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    print(json.dumps(asdict(classify(evidence)), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
