"""Roadmap 1.7 acceptance tests for scripts/check_coverage.py.

DoD: UI/API gap fixtures fail with branch-aware messages; fully-covered
branch fixtures pass; not_testable/manual_only exemptions honored only with
accepted status + reasons; automation_test_ids cross-checked against REAL
pytest --collect-only results (an invented-but-well-formed nodeid fails);
from-iteration is state-driven; auto aggregates locally.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest  # pyright: ignore[reportMissingImports]
import yaml
from conftest import FIXTURES_DIR as FIXTURE_DIR
from conftest import _load_script

SCHEMA_FIXTURES = FIXTURE_DIR / "schemas"
SHA = "a" * 64


@pytest.fixture(scope="module")
def coverage() -> Any:
    return _load_script("check_coverage")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _requirements(root: Path, iteration_id: str, rids: tuple[str, ...]) -> None:
    lines = [
        'schema_version: "1.0"',
        f"iteration_id: {iteration_id}",
        "status: accepted",
        "generated_from:",
        f"  artifact: iterations/{iteration_id}/00-raw/dump.md",
        f"  sha256: {SHA}",
        "requirements:",
    ]
    for rid in rids:
        lines += [
            f"  - requirement_id: {rid}",
            f"    title: Requirement {rid}",
            f"    description: Description for {rid}.",
        ]
    _write(root / "requirements.yaml", "\n".join(lines) + "\n")


def _test_points(root: Path, iteration_id: str, mapping: dict[str, tuple[str, ...]]) -> None:
    lines = [
        'schema_version: "1.0"',
        f"iteration_id: {iteration_id}",
        "status: accepted",
        "generated_from:",
        f"  artifact: iterations/{iteration_id}/requirements.yaml",
        f"  sha256: {SHA}",
        "test_points:",
    ]
    for tid, rids in mapping.items():
        lines += [
            f"  - test_point_id: {tid}",
            f"    requirement_ids: [{', '.join(rids)}]",
            f"    description: Point {tid}.",
            "    type: happy",
        ]
    _write(root / "test_points.yaml", "\n".join(lines) + "\n")


def _cases(root: Path, iteration_id: str, spec: list[tuple[str, str, tuple[str, ...]]]) -> None:
    lines = [
        'schema_version: "1.0"',
        f"iteration_id: {iteration_id}",
        "status: exported",
        "generated_from:",
        f"  artifact: iterations/{iteration_id}/test_points.yaml",
        f"  sha256: {SHA}",
        "cases:",
    ]
    for cid, module, tids in spec:
        lines += [
            f"  - case_id: {cid}",
            f"    title: Case {cid}",
            "    priority: 1",
            "    side_effect: none",
            "    precondition: none",
            "    steps:",
            "      - action: Do it.",
            "        expected: It worked.",
            "        expected_kind: ui_state",
            f'    tags: ["module:{module}"]',
            f"    test_point_ids: [{', '.join(tids)}]",
        ]
    _write(root / "functional-cases.yaml", "\n".join(lines) + "\n")


def _api_cases(root: Path, iteration_id: str, mapping: dict[str, tuple[str, ...]]) -> None:
    lines = [
        'schema_version: "1.0"',
        f"iteration_id: {iteration_id}",
        "status: cases_valid",
        "generated_from:",
        f"  artifact: iterations/{iteration_id}/api/spec.normalized.yaml",
        f"  sha256: {SHA}",
        "cases:",
    ]
    for aid, rids in mapping.items():
        lines += [
            f"  - api_case_id: {aid}",
            f"    requirement_ids: [{', '.join(rids)}]",
            f"    operation_id: op{aid[-1]}",
            "    endpoint: /store/things",
            "    method: GET",
            f"    title: API case {aid}",
            "    case_type: happy_path",
            "    side_effect: none",
            "    module: things",
            "    request: {}",
            "    expected_response:",
            "      status_code: 200",
            "      body_assertions:",
            "        - path: $.value",
            "          operator: type",
            "          value_type: number",
            "          expected: number",
        ]
    _write(root / "api/cases.yaml", "\n".join(lines) + "\n")


def _traceability(root: Path, iteration_id: str, rows: str) -> None:
    _write(
        root / "traceability.yaml",
        f'schema_version: "1.0"\niteration_id: {iteration_id}\nlinks:\n' + rows,
    )


def _nodeid(test_file: str, test_name: str) -> str:
    return f"automation/{test_file}::{test_name}"


def _iteration_doc(iteration_id: str, state: str) -> dict:
    return {
        "schema_version": "1.0",
        "iteration_id": iteration_id,
        "state": state,
        "blocked_reason": None,
        "branches": {"ui": True, "api": False},
        "artifacts": {
            key: {"status": "not_started"}
            for key in (
                "requirements",
                "exemptions",
                "test_points",
                "functional_cases",
                "api_spec",
                "api_cases",
                "web_automation",
                "api_automation",
                "execution",
            )
        },
        "approvals": [],
        "events": [],
    }


def _automation_tree(tmp_path: Path, nodeids: list[tuple[str, str]]) -> Path:
    """A REAL pytest tree whose collected nodeids match the given pairs."""
    automation = tmp_path / "automation"
    for test_file, test_name in nodeids:
        path = automation / test_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"def {test_name}():\n    assert True\n", encoding="utf-8")
    return automation


def _run(coverage: Any, tmp_path: Path, capsys: Any, *args: str) -> tuple[int, str, str]:
    code = coverage.main([str(tmp_path / "iterations" / "2026-08-cov"), *args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture()
def ui_iteration(tmp_path: Path) -> Path:
    root = tmp_path / "iterations" / "2026-08-cov"
    _requirements(root, "2026-08-cov", ("R0001", "R0002"))
    _test_points(root, "2026-08-cov", {"T0001": ("R0001",), "T0002": ("R0002",)})
    _cases(
        root, "2026-08-cov", [("C0001", "checkout", ("T0001",)), ("C0002", "orders", ("T0002",))]
    )
    return root


def test_ui_fully_covered_passes(coverage: Any, ui_iteration: Path) -> None:
    assert coverage.main([str(ui_iteration), "--tier", "r-t"]) == 0
    assert coverage.main([str(ui_iteration), "--tier", "t-c"]) == 0


def test_duplicate_test_point_ids_are_reported(
    coverage: Any, ui_iteration: Path, capsys: Any
) -> None:
    path = ui_iteration / "test_points.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("test_point_id: T0002", "test_point_id: T0001"),
        encoding="utf-8",
    )
    assert coverage.main([str(ui_iteration), "--tier", "r-t"]) == 1
    assert "duplicate test point id: T0001" in capsys.readouterr().out


def test_duplicate_functional_case_ids_are_reported(
    coverage: Any, ui_iteration: Path, capsys: Any
) -> None:
    _cases(
        ui_iteration,
        "2026-08-cov",
        [("C0001", "checkout", ("T0001",)), ("C0001", "orders", ("T0002",))],
    )
    assert coverage.main([str(ui_iteration), "--tier", "t-c"]) == 1
    assert "duplicate functional case id: C0001" in capsys.readouterr().out


def test_duplicate_api_case_ids_are_reported(coverage: Any, tmp_path: Path, capsys: Any) -> None:
    root = tmp_path / "iterations" / "2026-08-cov"
    _requirements(root, "2026-08-cov", ("R0001", "R0002"))
    _api_cases(root, "2026-08-cov", {"A0001": ("R0001",), "A0002": ("R0002",)})
    path = root / "api/cases.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("api_case_id: A0002", "api_case_id: A0001"),
        encoding="utf-8",
    )
    assert coverage.main([str(root), "--tier", "r-a"]) == 1
    assert "duplicate API case id: A0001" in capsys.readouterr().out


def test_exemption_for_unknown_requirement_is_reported(
    coverage: Any, ui_iteration: Path, capsys: Any
) -> None:
    _write(
        ui_iteration / "exemptions.yaml",
        'schema_version: "1.0"\n'
        "iteration_id: 2026-08-cov\n"
        "status: accepted\n"
        "generated_from:\n"
        "  artifact: iterations/2026-08-cov/requirements.yaml\n"
        f"  sha256: {SHA}\n"
        "exemptions:\n"
        "  - requirement_id: R9999\n"
        "    kind: not_testable\n"
        "    reason: No such requirement.\n",
    )
    assert coverage.main([str(ui_iteration), "--tier", "r-t"]) == 1
    assert "exemption cites unknown requirement R9999" in capsys.readouterr().out


def test_ui_requirement_gap_fails_with_branch_message(
    coverage: Any, ui_iteration: Path, capsys: Any
) -> None:
    _test_points(ui_iteration, "2026-08-cov", {"T0001": ("R0001",)})
    code, out, _ = _run(coverage, ui_iteration.parent.parent, capsys, "--tier", "r-t")
    assert code == 1
    assert "[UI R->T] requirement R0002 has no test point" in out


def test_api_requirement_gap_names_api_tier(coverage: Any, tmp_path: Path, capsys: Any) -> None:
    root = tmp_path / "iterations" / "2026-08-cov"
    _requirements(root, "2026-08-cov", ("R0001", "R0002"))
    _api_cases(root, "2026-08-cov", {"A0001": ("R0001",)})
    code, out, _ = _run(coverage, tmp_path, capsys, "--tier", "r-a")
    assert code == 1
    assert "[API R->A] requirement R0002 is not cited by any API case" in out


def test_not_testable_exemption_requires_accepted_status(coverage: Any, ui_iteration: Path) -> None:
    _write(
        ui_iteration / "exemptions.yaml",
        'schema_version: "1.0"\n'
        "iteration_id: 2026-08-cov\n"
        "status: draft\n"
        "exemptions:\n"
        "  - requirement_id: R0002\n"
        "    kind: not_testable\n"
        "    reason: Not automatable in this environment.\n",
    )
    _test_points(ui_iteration, "2026-08-cov", {"T0001": ("R0001",)})
    # draft exemption is NOT honored -> R0002 still demands a test point
    assert coverage.main([str(ui_iteration), "--tier", "r-t"]) == 1


def test_accepted_not_testable_exemption_removes_demand(coverage: Any, ui_iteration: Path) -> None:
    _write(
        ui_iteration / "exemptions.yaml",
        'schema_version: "1.0"\n'
        "iteration_id: 2026-08-cov\n"
        "status: accepted\n"
        "exemptions:\n"
        "  - requirement_id: R0002\n"
        "    kind: not_testable\n"
        "    reason: Feature exists only behind an external flag we cannot set.\n",
    )
    _test_points(ui_iteration, "2026-08-cov", {"T0001": ("R0001",)})
    _cases(ui_iteration, "2026-08-cov", [("C0001", "checkout", ("T0001",))])
    assert coverage.main([str(ui_iteration), "--tier", "r-t"]) == 0


def test_tier_gap_test_point_without_case(coverage: Any, ui_iteration: Path, capsys: Any) -> None:
    _cases(ui_iteration, "2026-08-cov", [("C0001", "checkout", ("T0001",))])
    code, out, _ = _run(coverage, ui_iteration.parent.parent, capsys, "--tier", "t-c")
    assert code == 1
    assert "[UI T->C] test point T0002 has no functional case" in out


def test_manual_only_case_is_exempt_from_automation_tier(
    coverage: Any, ui_iteration: Path, tmp_path: Path, capsys: Any
) -> None:
    automation = _automation_tree(tmp_path, [("web/tests/checkout/test_x.py", "test_x")])
    _write(
        ui_iteration / "exemptions.yaml",
        'schema_version: "1.0"\n'
        "iteration_id: 2026-08-cov\n"
        "status: accepted\n"
        "exemptions:\n"
        "  - requirement_id: R0002\n"
        "    kind: manual_only\n"
        "    reason: Physical scanner hardware required.\n",
    )
    rows = (
        f"- requirement_id: R0001\n"
        f"  test_point_id: T0001\n"
        f"  functional_case_id: C0001\n"
        f"  automation_test_ids:\n"
        f"    - {_nodeid('web/tests/checkout/test_x.py', 'test_x')}\n"
    )
    _traceability(ui_iteration, "2026-08-cov", rows)
    code, out, err = _run(
        coverage,
        ui_iteration.parent.parent,
        capsys,
        "--tier",
        "c-auto",
        "--automation-dir",
        str(automation),
    )
    assert code == 0, (out, err)


def test_invented_wellformed_nodeid_fails(
    coverage: Any, ui_iteration: Path, tmp_path: Path, capsys: Any
) -> None:
    automation = _automation_tree(tmp_path, [("web/tests/checkout/test_real.py", "test_real")])
    rows = (
        f"- requirement_id: R0001\n"
        f"  test_point_id: T0001\n"
        f"  functional_case_id: C0001\n"
        f"  automation_test_ids:\n"
        f"    - {_nodeid('web/tests/checkout/test_invented.py', 'test_invented')}\n"
    )
    _traceability(ui_iteration, "2026-08-cov", rows)
    code, out, _ = _run(
        coverage,
        ui_iteration.parent.parent,
        capsys,
        "--tier",
        "c-auto",
        "--automation-dir",
        str(automation),
    )
    assert code == 1
    assert "not collectable" in out


def test_real_collected_nodeid_passes_c_auto(
    coverage: Any, ui_iteration: Path, tmp_path: Path, capsys: Any
) -> None:
    automation = _automation_tree(
        tmp_path,
        [
            ("web/tests/checkout/test_a.py", "test_a"),
            ("web/tests/orders/test_b.py", "test_b"),
        ],
    )
    rows = ""
    for cid, tid, rid, nid in [
        ("C0001", "T0001", "R0001", _nodeid("web/tests/checkout/test_a.py", "test_a")),
        ("C0002", "T0002", "R0002", _nodeid("web/tests/orders/test_b.py", "test_b")),
    ]:
        rows += (
            f"- requirement_id: {rid}\n  test_point_id: {tid}\n"
            f"  functional_case_id: {cid}\n  automation_test_ids:\n    - {nid}\n"
        )
    _traceability(ui_iteration, "2026-08-cov", rows)
    code, out, err = _run(
        coverage,
        ui_iteration.parent.parent,
        capsys,
        "--tier",
        "c-auto",
        "--automation-dir",
        str(automation),
    )
    assert code == 0, (out, err)


def test_from_iteration_selects_tiers_by_state(
    coverage: Any, ui_iteration: Path, tmp_path: Path, capsys: Any
) -> None:
    # state = test_points_accepted demands R->T only (which passes fully covered)
    document = _iteration_doc("2026-08-cov", state="test_points_accepted")
    (ui_iteration / "iteration.yaml").write_text(yaml.safe_dump(document, sort_keys=False))
    code, out, _ = _run(coverage, tmp_path, capsys, "--tier", "from-iteration")
    assert code == 0
    assert "tiers checked: r-t" in out


def test_from_iteration_merged_demands_complete_chain(
    coverage: Any, ui_iteration: Path, tmp_path: Path, capsys: Any
) -> None:
    document = _iteration_doc("2026-08-cov", state="merged")
    (ui_iteration / "iteration.yaml").write_text(yaml.safe_dump(document, sort_keys=False))
    code, _, _ = _run(coverage, tmp_path, capsys, "--tier", "from-iteration")
    assert code == 1  # c-auto unmet (no traceability) - complete chain demanded


def test_changed_scope_selects_only_touched_iterations(coverage: Any, tmp_path: Path) -> None:
    """只改 iteration 工件时，不应让历史 iteration 阻断当前草稿。"""
    iterations = tmp_path / "iterations"
    for iteration_id in ("order-ui", "order-api"):
        (iterations / iteration_id).mkdir(parents=True)
        (iterations / iteration_id / "iteration.yaml").write_text("state: created\n")

    selected = coverage.select_changed_iteration_dirs(
        iterations,
        ["iterations/order-api/api/cases.yaml", "docs/spec/product/PRD.md"],
    )
    assert selected == [iterations / "order-api"]


@pytest.mark.parametrize(
    "changed_path",
    [
        "automation/api/tests/orders/test_order.py",
        "shared/config/settings.py",
        "scripts/check_coverage.py",
    ],
)
def test_changed_scope_checks_all_iterations_for_shared_impact(
    coverage: Any, tmp_path: Path, changed_path: str
) -> None:
    """自动化或共享门禁变化可能破坏任一历史链，必须检查全部 iteration。"""
    iterations = tmp_path / "iterations"
    expected = []
    for iteration_id in ("order-ui", "order-api"):
        path = iterations / iteration_id
        path.mkdir(parents=True)
        (path / "iteration.yaml").write_text("state: created\n")
        expected.append(path)

    assert coverage.select_changed_iteration_dirs(iterations, [changed_path]) == sorted(expected)


def test_changed_scope_ignores_unrelated_paths(coverage: Any, tmp_path: Path) -> None:
    """纯文档变化不需要重复执行 iteration 覆盖门禁。"""
    iterations = tmp_path / "iterations"
    iterations.mkdir()
    assert coverage.select_changed_iteration_dirs(iterations, ["README.md"]) == []


def test_changed_scope_rejects_deleted_iteration(coverage: Any, tmp_path: Path) -> None:
    """删除 iteration 不能被范围筛选静默跳过。"""
    iterations = tmp_path / "iterations"
    iterations.mkdir()
    with pytest.raises(coverage.CoverageError, match="已不存在"):
        coverage.select_changed_iteration_dirs(
            iterations,
            ["iterations/deleted-one/iteration.yaml"],
        )


def test_static_ci_uses_pull_request_changed_scope() -> None:
    """PR 覆盖门禁必须取得完整基线，并把 base SHA 交给范围选择器。"""
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in workflow
    assert "ARGUS_BASE_SHA: ${{ github.event.pull_request.base.sha }}" in workflow
    assert '--changed-base "$ARGUS_BASE_SHA"' in workflow
