"""Roadmap 5.3：M9 证据记录、恢复和预算门禁。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest  # pyright: ignore[reportMissingImports]
import yaml
from conftest import _load_script


@pytest.fixture(scope="module")
def helper() -> Any:
    return _load_script("self_debug_helper")


@pytest.fixture(scope="module")
def execution_plugin() -> Any:
    return _load_script("pytest_execution_evidence")


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
    nodeid = "automation/api/tests/checkout/test_2026-08-case.py::test_case"
    (iteration / "traceability.yaml").write_text(
        "schema_version: '1.0'\n"
        f"iteration_id: ci-{status}\n"
        "links:\n"
        "  - requirement_id: R0001\n"
        "    api_case_id: A0001\n"
        f"    automation_test_ids: [{nodeid}]\n",
        encoding="utf-8",
    )
    execution = tmp_path / f"{status}-executed.json"
    _write_execution(
        execution,
        [nodeid],
        outcomes={nodeid: "failed" if failures else "passed"},
    )
    junit = tmp_path / f"{status}.xml"
    junit.write_text(
        f'<testsuites><testsuite tests="1" failures="{failures}" errors="0" skipped="0">'
        '<testcase classname="checkout" name="test_case"/></testsuite></testsuites>',
        encoding="utf-8",
    )
    environment = tmp_path / f"{status}-env.yaml"
    environment.write_text("base_url: http://localhost:8000\n", encoding="utf-8")
    seed = tmp_path / f"{status}-seed.yaml"
    seed.write_text("seeds: []\n", encoding="utf-8")
    run_id = "run-20260828T130000Z-abcd" if status == "passed" else "run-20260828T130001Z-abcd"
    run_dir = helper.record_ci(
        iteration,
        run_id,
        ["checkout"],
        "ci",
        junit,
        execution_file=execution,
        environment_file=environment,
        seed_registry=seed,
        target_image_ids=["unavailable"],
    )
    summary = yaml.safe_load((run_dir / "run-summary.yaml").read_text())
    assert summary["scope"] == "full"
    assert summary["status"] == status
    assert len(summary["attempts"]) == 1
    assert helper.load_execution_manifest(run_dir)["expected_nodeids"] == [nodeid]


def test_archive_reports_never_overwrites(helper: Any, tmp_path: Path) -> None:
    run_dir = _init(helper, tmp_path)
    report = tmp_path / "allure-results"
    report.mkdir()
    (report / "result.json").write_text("{}\n", encoding="utf-8")
    assert helper.archive_reports(run_dir, [report]) == [run_dir / "allure-results"]
    with pytest.raises(helper.EvidenceError, match="禁止覆盖"):
        helper.archive_reports(run_dir, [report])


def _write_execution(
    path: Path,
    nodeids: list[str],
    *,
    collected_nodeids: list[str] | None = None,
    outcomes: dict[str, str] | None = None,
) -> None:
    collected = collected_nodeids if collected_nodeids is not None else nodeids
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "collected_nodeids": collected,
                "nodeids": nodeids,
                "outcomes": outcomes if outcomes is not None else {n: "passed" for n in nodeids},
            }
        ),
        encoding="utf-8",
    )


def _write_junit(path: Path, *, failures: int = 0) -> None:
    path.write_text(
        f'<testsuites><testsuite tests="1" failures="{failures}" errors="0" skipped="0">'
        '<testcase classname="checkout" name="test_case"/></testsuite></testsuites>',
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        ('<testsuite tests="0" failures="0" errors="0" skipped="0"/>', "零测试"),
        ('<testsuite tests="2" failures="0" errors="0" skipped="2"/>', "全部 skipped"),
        ('<testsuite tests="1" failures="1" errors="1" skipped="0"/>', "总数超过 tests"),
    ],
)
def test_read_junit_rejects_empty_or_inconsistent_evidence(
    helper: Any, tmp_path: Path, xml: str, message: str
) -> None:
    path = tmp_path / "invalid.xml"
    path.write_text(xml, encoding="utf-8")
    with pytest.raises(helper.EvidenceError, match=message):
        helper._read_junit(path)


def _manifest_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    nodeid = "automation/api/tests/checkout/test_2026-08-case.py::test_case"
    execution = tmp_path / "executed.json"
    _write_execution(execution, [nodeid])
    junit = tmp_path / "junit.xml"
    _write_junit(junit)
    environment = tmp_path / "env.ci.yaml"
    environment.write_text("base_url: http://localhost:8000\n", encoding="utf-8")
    seed = tmp_path / "seed-registry.yaml"
    seed.write_text("seeds: []\n", encoding="utf-8")
    return execution, junit, environment, seed


def test_record_ci_writes_exact_execution_manifest(helper: Any, tmp_path: Path) -> None:
    iteration = tmp_path / "iterations" / "ci-manifest"
    iteration.mkdir(parents=True)
    execution, junit, environment, seed = _manifest_inputs(tmp_path)
    nodeid = "automation/api/tests/checkout/test_2026-08-case.py::test_case"
    run_dir = helper.record_ci(
        iteration,
        "run-20260829T120000Z-abcd",
        ["checkout"],
        "ci",
        junit,
        expected_nodeids=[nodeid],
        execution_file=execution,
        environment_file=environment,
        seed_registry=seed,
        target_image_ids=["unavailable"],
    )
    manifest = helper.load_execution_manifest(run_dir)
    assert manifest["expected_nodeids"] == [nodeid]
    assert manifest["collected_nodeids"] == [nodeid]
    assert manifest["attempts"][0]["collected_nodeids"] == [nodeid]
    assert manifest["attempts"][0]["outcomes"] == {nodeid: "passed"}


def test_record_ci_resolves_parameterized_pytest_nodeids(helper: Any, tmp_path: Path) -> None:
    iteration = tmp_path / "iterations" / "ci-parameterized"
    iteration.mkdir(parents=True)
    selector = "automation/web/tests/checkout/test_case.py::test_case"
    nodeid = f"{selector}[chromium]"
    execution = tmp_path / "parameterized-executed.json"
    _write_execution(execution, [nodeid], collected_nodeids=[nodeid])
    junit = tmp_path / "parameterized.xml"
    _write_junit(junit)
    environment = tmp_path / "parameterized-env.yaml"
    environment.write_text("base_url: http://localhost:8000\n", encoding="utf-8")
    seed = tmp_path / "parameterized-seed.yaml"
    seed.write_text("seeds: []\n", encoding="utf-8")

    run_dir = helper.record_ci(
        iteration,
        "run-20260829T120005Z-abcd",
        ["checkout"],
        "ci",
        junit,
        expected_nodeids=[selector],
        execution_file=execution,
        environment_file=environment,
        seed_registry=seed,
        target_image_ids=["unavailable"],
    )
    manifest = helper.load_execution_manifest(run_dir)
    assert manifest["expected_nodeids"] == [nodeid]
    assert manifest["attempts"][0]["expected_nodeids"] == [nodeid]
    assert manifest["attempts"][0]["outcomes"] == {nodeid: "passed"}


def test_manifest_rejects_junit_outcome_mismatch(helper: Any, tmp_path: Path) -> None:
    iteration = tmp_path / "iterations" / "ci-outcome-mismatch"
    iteration.mkdir(parents=True)
    nodeid = "automation/api/tests/checkout/test_2026-08-case.py::test_case"
    execution = tmp_path / "mismatch.json"
    _write_execution(execution, [nodeid], outcomes={nodeid: "failed"})
    junit = tmp_path / "mismatch.xml"
    _write_junit(junit)
    environment = tmp_path / "mismatch-env.yaml"
    environment.write_text("base_url: http://localhost:8000\n", encoding="utf-8")
    seed = tmp_path / "mismatch-seed.yaml"
    seed.write_text("seeds: []\n", encoding="utf-8")
    with pytest.raises(helper.EvidenceError, match="JUnit failures/errors 与 pytest"):
        helper.record_ci(
            iteration,
            "run-20260829T120004Z-abcd",
            ["checkout"],
            "ci",
            junit,
            expected_nodeids=[nodeid],
            execution_file=execution,
            environment_file=environment,
            seed_registry=seed,
            target_image_ids=["unavailable"],
        )
    assert not (iteration / "runs").exists()


def test_manifest_rejects_extra_executed_nodeid(helper: Any, tmp_path: Path) -> None:
    iteration = tmp_path / "iterations" / "ci-extra"
    iteration.mkdir(parents=True)
    nodeid = "automation/api/tests/checkout/test_2026-08-case.py::test_case"
    extra = "automation/web/tests/checkout/test_other.py::test_other"
    execution = tmp_path / "extra.json"
    _write_execution(execution, [nodeid, extra])
    junit = tmp_path / "extra.xml"
    _write_junit(junit)
    environment = tmp_path / "extra-env.yaml"
    environment.write_text("base_url: http://localhost:8000\n", encoding="utf-8")
    seed = tmp_path / "extra-seed.yaml"
    seed.write_text("seeds: []\n", encoding="utf-8")
    with pytest.raises(helper.EvidenceError, match="非本 iteration"):
        helper.record_ci(
            iteration,
            "run-20260829T120001Z-abcd",
            ["checkout"],
            "ci",
            junit,
            expected_nodeids=[nodeid],
            execution_file=execution,
            environment_file=environment,
            seed_registry=seed,
            target_image_ids=["unavailable"],
        )
    assert not (iteration / "runs").exists()


def test_record_ci_rejects_missing_traceability_manifest_scope(helper: Any, tmp_path: Path) -> None:
    iteration = tmp_path / "iterations" / "ci-no-traceability"
    iteration.mkdir(parents=True)
    junit = tmp_path / "no-traceability.xml"
    _write_junit(junit)
    with pytest.raises(helper.EvidenceError, match="缺少 traceability.yaml"):
        helper.record_ci(
            iteration,
            "run-20260829T120003Z-abcd",
            ["checkout"],
            "ci",
            junit,
            execution_file=tmp_path / "unused.json",
        )
    assert not (iteration / "runs").exists()


def test_record_ci_rejects_legacy_executed_nodeids_without_outcomes(
    helper: Any, tmp_path: Path
) -> None:
    iteration = tmp_path / "iterations" / "ci-legacy-execution"
    iteration.mkdir(parents=True)
    junit = tmp_path / "legacy.xml"
    _write_junit(junit)
    nodeid = "automation/api/tests/checkout/test_2026-08-case.py::test_case"
    with pytest.raises(helper.EvidenceError, match="无法形成完整 1.1 执行清单"):
        helper.record_ci(
            iteration,
            "run-20260829T120002Z-abcd",
            ["checkout"],
            "ci",
            junit,
            expected_nodeids=[nodeid],
            executed_nodeids=[nodeid],
        )
    assert not (iteration / "runs").exists()


def test_record_ci_auto_requires_iteration_scope_for_multiple_candidates(
    helper: Any, tmp_path: Path
) -> None:
    iterations = tmp_path / "iterations"
    for name in ("ci-one", "ci-two"):
        candidate = iterations / name
        candidate.mkdir(parents=True)
        (candidate / "iteration.yaml").write_text("state: accepted\n", encoding="utf-8")
    with pytest.raises(helper.EvidenceError, match="必须分别调用"):
        helper.record_ci_auto(
            iterations,
            tmp_path / "unused.xml",
            "ci",
            executed_nodeids=tmp_path / "unused.json",
        )


def test_record_ci_auto_keeps_first_and_retry_attempts(helper: Any, tmp_path: Path) -> None:
    iterations = tmp_path / "iterations"
    iteration = iterations / "ci-retry"
    iteration.mkdir(parents=True)
    nodeid = "automation/api/tests/checkout/test_2026-08-case.py::test_case"
    (iteration / "iteration.yaml").write_text("state: accepted\n", encoding="utf-8")
    (iteration / "api").mkdir()
    (iteration / "api/cases.yaml").write_text("cases:\n  - module: checkout\n", encoding="utf-8")
    (iteration / "traceability.yaml").write_text(
        "schema_version: '1.0'\n"
        "iteration_id: ci-retry\n"
        "links:\n"
        "  - requirement_id: R0001\n"
        "    api_case_id: A0001\n"
        f"    automation_test_ids: [{nodeid}]\n",
        encoding="utf-8",
    )
    first_execution = tmp_path / "first.json"
    _write_execution(first_execution, [nodeid], outcomes={nodeid: "failed"})
    retry_execution = tmp_path / "retry.json"
    _write_execution(retry_execution, [nodeid])
    first_junit = tmp_path / "first.xml"
    _write_junit(first_junit, failures=1)
    retry_junit = tmp_path / "retry.xml"
    _write_junit(retry_junit)
    environment = tmp_path / "retry-env.yaml"
    environment.write_text("base_url: http://localhost:8000\n", encoding="utf-8")
    seed = tmp_path / "retry-seed.yaml"
    seed.write_text("seeds: []\n", encoding="utf-8")

    [run_dir] = helper.record_ci_auto(
        iterations,
        retry_junit,
        "ci",
        iteration=iteration,
        first_junit=first_junit,
        first_executed_nodeids=first_execution,
        retry_junit=retry_junit,
        retry_executed_nodeids=retry_execution,
        environment_file=environment,
        seed_registry=seed,
        target_image_ids=["unavailable"],
    )
    manifest = helper.load_execution_manifest(run_dir)
    assert [attempt["attempt_number"] for attempt in manifest["attempts"]] == [1, 2]
    assert [attempt["result"] for attempt in manifest["attempts"]] == ["fail", "pass"]
    assert all(attempt["executed_nodeids"] == [nodeid] for attempt in manifest["attempts"])


def test_execution_plugin_records_collection_and_complete_outcomes(
    execution_plugin: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.chdir(tmp_path)
    output = Path("reports/executed.json")
    monkeypatch.setenv("ARGUS_EXECUTED_NODEIDS", str(output))
    execution_plugin.pytest_configure(SimpleNamespace())
    execution_plugin.pytest_collection_finish(
        SimpleNamespace(
            items=[
                SimpleNamespace(nodeid="automation/api/test_one.py::test_one"),
                SimpleNamespace(nodeid="automation/web/test_two.py::test_two"),
                SimpleNamespace(nodeid="scripts/test_not_recorded.py::test_three"),
            ]
        )
    )
    execution_plugin.pytest_runtest_logreport(
        SimpleNamespace(nodeid="automation/api/test_one.py::test_one", outcome="passed")
    )
    execution_plugin.pytest_runtest_logreport(
        SimpleNamespace(nodeid="automation/web/test_two.py::test_two", outcome="failed")
    )
    execution_plugin.pytest_runtest_logreport(
        SimpleNamespace(
            nodeid="automation/web/test_two.py::test_two",
            outcome="passed",
            when="teardown",
            wasxfail=False,
        )
    )
    execution_plugin.pytest_sessionfinish(SimpleNamespace(), 1)
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["collected_nodeids"] == [
        "automation/api/test_one.py::test_one",
        "automation/web/test_two.py::test_two",
    ]
    assert document["outcomes"] == {
        "automation/api/test_one.py::test_one": "passed",
        "automation/web/test_two.py::test_two": "failed",
    }


def test_execution_plugin_preserves_xfail_outcome(
    execution_plugin: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.chdir(tmp_path)
    output = Path("reports/xfail.json")
    monkeypatch.setenv("ARGUS_EXECUTED_NODEIDS", str(output))
    execution_plugin.pytest_configure(SimpleNamespace())
    nodeid = "automation/api/test_xfail.py::test_xfail"
    execution_plugin.pytest_collection_finish(
        SimpleNamespace(items=[SimpleNamespace(nodeid=nodeid)])
    )
    execution_plugin.pytest_runtest_logreport(
        SimpleNamespace(nodeid=nodeid, outcome="passed", when="call", wasxfail=True)
    )
    execution_plugin.pytest_sessionfinish(SimpleNamespace(), 0)

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["outcomes"] == {nodeid: "xpassed"}


def test_execution_plugin_retains_setup_failure_over_call_skip(
    execution_plugin: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.chdir(tmp_path)
    output = Path("reports/setup-failure.json")
    monkeypatch.setenv("ARGUS_EXECUTED_NODEIDS", str(output))
    execution_plugin.pytest_configure(SimpleNamespace())
    nodeid = "automation/api/test_fixture.py::test_setup_failure"
    execution_plugin.pytest_collection_finish(
        SimpleNamespace(items=[SimpleNamespace(nodeid=nodeid)])
    )
    execution_plugin.pytest_runtest_logreport(
        SimpleNamespace(nodeid=nodeid, outcome="failed", when="setup", wasxfail=False)
    )
    execution_plugin.pytest_runtest_logreport(
        SimpleNamespace(nodeid=nodeid, outcome="skipped", when="call", wasxfail=False)
    )
    execution_plugin.pytest_sessionfinish(SimpleNamespace(), 1)

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["outcomes"] == {nodeid: "failed"}
