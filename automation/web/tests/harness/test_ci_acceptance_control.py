"""仅供手工 CI 调度验证失败重跑与 flaky 分类；常规执行保持通过。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.module("harness"),
    pytest.mark.case_id("C0000"),
    pytest.mark.iteration("harness"),
    pytest.mark.read_only,
]

_SCENARIOS = {"normal", "force_failure", "force_flaky"}


def test_ci_acceptance_control() -> None:
    """按手工调度参数稳定地产生成功、持续失败或仅首轮失败。"""
    scenario = os.environ.get("ARGUS_CI_ACCEPTANCE_SCENARIO", "normal")
    assert scenario in _SCENARIOS, f"未知 CI 验收场景：{scenario}"
    if scenario == "force_failure":
        pytest.fail("强制失败验收探针：预期两轮均失败")
    if scenario != "force_flaky":
        return

    sentinel_root = Path(os.environ.get("RUNNER_TEMP", "reports"))
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    sentinel = sentinel_root / f"argus-ci-flaky-{run_id}.seen"
    if not sentinel.exists():
        sentinel_root.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("首轮失败已发生\n", encoding="utf-8")
        pytest.fail("强制 flaky 验收探针：首轮预期失败")
