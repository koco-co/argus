"""Roadmap 5.3：M9 证据记录、恢复和预算门禁。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import _load_script


@pytest.fixture(scope="module")
def helper() -> Any:
    return _load_script("self_debug_helper")


def _init(helper: Any, tmp_path: Path, budget: int = 2) -> Path:
    iteration = tmp_path / "iterations" / "ui-run"
    iteration.mkdir(parents=True)
    run_dir = helper.initialize_run(
        iteration,
        "run-20260828T120000Z-abcd",
        ["checkout"],
        "local",
        budget,
    )
    return run_dir


def test_checkpoint_forces_verification_before_attempt(helper: Any, tmp_path: Path) -> None:
    run_dir = _init(helper, tmp_path)
    helper.checkpoint(run_dir, 1, ["automation/web/pages/checkout/cart_page.py"])
    state = json.loads((run_dir / "state.json").read_text())
    assert state == {
        "attempt_number": 1,
        "patched_files": ["automation/web/pages/checkout/cart_page.py"],
        "verification_pending": True,
    }
    with pytest.raises(helper.EvidenceError, match="验证组合"):
        helper.append_attempt(run_dir, "fail", "locator_drift", "仍未找到元素", None)


def test_recovery_resumes_budget_and_terminal_summary_is_schema_valid(
    helper: Any, tmp_path: Path
) -> None:
    run_dir = _init(helper, tmp_path)
    patch = run_dir / "attempt-1.patch"
    patch.write_text("--- a/x\n+++ b/x\n", encoding="utf-8")
    helper.checkpoint(run_dir, 1, ["automation/web/pages/checkout/cart_page.py"])
    assert helper.recovery_action(run_dir) == "verification_required"
    helper.complete_verification(run_dir)
    helper.append_attempt(run_dir, "fail", "locator_drift", "选择器漂移", patch.name)
    assert helper.remaining_budget(run_dir) == 1
    helper.checkpoint(run_dir, 2, [])
    helper.complete_verification(run_dir)
    helper.append_attempt(run_dir, "pass", "none", "受影响模块回归通过", None)
    helper.finalize(run_dir, "passed")

    summary = yaml.safe_load((run_dir / "run-summary.yaml").read_text())
    assert [item["attempt_number"] for item in summary["attempts"]] == [1, 2]
    assert summary["status"] == "passed"
    assert helper.validate_summary(summary) == []


def test_budget_exceeded_requires_consumed_budget(helper: Any, tmp_path: Path) -> None:
    run_dir = _init(helper, tmp_path, budget=2)
    helper.append_attempt(run_dir, "fail", "locator_drift", "第一次失败", None)
    with pytest.raises(helper.EvidenceError, match="预算尚未耗尽"):
        helper.finalize(run_dir, "budget_exceeded")


def test_escalation_only_attempt_does_not_consume_repair_budget(
    helper: Any, tmp_path: Path
) -> None:
    """产品行为不符等升级类只记录证据，不占用自动修复预算。"""
    run_dir = _init(helper, tmp_path, budget=2)
    helper.append_attempt(
        run_dir,
        "fail",
        "product_behavior_mismatch",
        "真实商品总额与需求预期不符",
        None,
    )
    assert helper.remaining_budget(run_dir) == 2
    helper.finalize(
        run_dir,
        "escalated",
        "product_behavior_mismatch",
        "断言证据完整，禁止自动修改预期",
    )


def test_evidence_writer_refuses_outside_run_directory(helper: Any, tmp_path: Path) -> None:
    with pytest.raises(helper.EvidenceError, match="run 目录"):
        helper.load_summary(tmp_path)


def test_affected_modules_follow_import_closure(helper: Any, tmp_path: Path) -> None:
    root = tmp_path
    page = root / "automation/web/pages/checkout/cart_page.py"
    component = root / "automation/web/components/shared/price.py"
    test = root / "automation/web/tests/checkout/test_case.py"
    for path in (page, component, test):
        path.parent.mkdir(parents=True, exist_ok=True)
    component.write_text("class Price: pass\n", encoding="utf-8")
    page.write_text(
        "from automation.web.components.shared.price import Price\nclass CartPage: pass\n",
        encoding="utf-8",
    )
    test.write_text(
        "from automation.web.pages.checkout.cart_page import CartPage\n",
        encoding="utf-8",
    )
    assert helper.affected_modules(root, [component]) == ["checkout"]


def test_helper_invokes_patch_scope_gate(helper: Any, tmp_path: Path) -> None:
    patch = tmp_path / "bad.patch"
    patch.write_text(
        "--- a/automation/web/tests/checkout/test_bad.py\n"
        "+++ b/automation/web/tests/checkout/test_bad.py\n"
        "@@ -1 +1 @@\n"
        "+assert True\n",
        encoding="utf-8",
    )
    problems = helper.verify_patch(patch)
    assert any("outside allow-list" in problem for problem in problems)


@pytest.mark.parametrize(("failures", "status"), [(0, "passed"), (1, "failed")])
def test_record_ci_writes_one_full_scope_attempt(
    helper: Any, tmp_path: Path, failures: int, status: str
) -> None:
    iteration = tmp_path / "iterations" / f"ci-{status}"
    iteration.mkdir(parents=True)
    junit = tmp_path / f"{status}.xml"
    junit.write_text(
        f'<testsuites><testsuite tests="1" failures="{failures}" errors="0"/></testsuites>',
        encoding="utf-8",
    )
    run_id = "run-20260828T130000Z-abcd" if status == "passed" else "run-20260828T130001Z-abcd"
    run_dir = helper.record_ci(iteration, run_id, ["checkout"], "ci", junit)
    summary = yaml.safe_load((run_dir / "run-summary.yaml").read_text())
    assert summary["scope"] == "full"
    assert summary["status"] == status
    assert len(summary["attempts"]) == 1


def test_archive_reports_never_overwrites(helper: Any, tmp_path: Path) -> None:
    run_dir = _init(helper, tmp_path)
    report = tmp_path / "allure-results"
    report.mkdir()
    (report / "result.json").write_text("{}\n", encoding="utf-8")
    assert helper.archive_reports(run_dir, [report]) == [run_dir / "allure-results"]
    with pytest.raises(helper.EvidenceError, match="禁止覆盖"):
        helper.archive_reports(run_dir, [report])
