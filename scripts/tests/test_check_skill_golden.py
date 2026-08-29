"""Roadmap 8.2：Skill 冻结输入与语义黄金基线门禁。"""

from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import _load_script


@pytest.fixture(scope="module")
def checker() -> Any:
    return _load_script("check_skill_golden")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _baseline(tmp_path: Path, *, comparison: str = "yaml") -> tuple[Path, Path]:
    baseline = tmp_path / "baseline"
    actual = tmp_path / "actual"
    input_path = baseline / "input" / "source.yaml"
    _write(input_path, "value: source\n")
    source_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
    suffix = "yaml" if comparison == "yaml" else "py"
    _write(
        baseline / f"expected/artifact.{suffix}",
        """
        alpha: 1
        beta: [two, three]
        """
        if comparison == "yaml"
        else """
        def total(value: int) -> int:
            return value + 1
        """,
    )
    manifest = {
        "schema_version": "1.0",
        "skill_name": "sample-skill",
        "skill_version": "1.0.0",
        "sample_id": "sample-001",
        "inputs": [{"path": "input/source.yaml", "sha256": source_hash}],
        "artifacts": [
            {
                "path": f"artifact.{suffix}",
                "comparison": comparison,
            }
        ],
    }
    _write(baseline / "manifest.yaml", yaml.safe_dump(manifest, sort_keys=False))
    return baseline, actual


def test_yaml_comparison_ignores_formatting_and_key_order(checker: Any, tmp_path: Path) -> None:
    baseline, actual = _baseline(tmp_path)
    _write(actual / "artifact.yaml", "beta:\n  - two\n  - three\nalpha: 1\n")

    report = checker.verify_baseline(baseline, actual)

    assert report.problems == []
    assert report.compared == ["artifact.yaml"]


def test_yaml_semantic_drift_is_reported(checker: Any, tmp_path: Path) -> None:
    baseline, actual = _baseline(tmp_path)
    _write(actual / "artifact.yaml", "alpha: 2\nbeta: [two, three]\n")

    report = checker.verify_baseline(baseline, actual)

    assert any("语义差异" in problem for problem in report.problems)


def test_python_comparison_ignores_comments_and_formatting(checker: Any, tmp_path: Path) -> None:
    baseline, actual = _baseline(tmp_path, comparison="python_ast")
    _write(
        actual / "artifact.py",
        """
        # 重新生成器允许改变注释与排版，但不能改变 AST 行为。
        def total(value: int) -> int:
            return (value + 1)
        """,
    )

    report = checker.verify_baseline(baseline, actual)

    assert report.problems == []


def test_python_ast_drift_is_reported(checker: Any, tmp_path: Path) -> None:
    baseline, actual = _baseline(tmp_path, comparison="python_ast")
    _write(actual / "artifact.py", "def total(value: int) -> int:\n    return value - 1\n")

    report = checker.verify_baseline(baseline, actual)

    assert any("AST 语义差异" in problem for problem in report.problems)


def test_python_compatible_comparison_allows_additive_methods(checker: Any, tmp_path: Path) -> None:
    """共享 POM 可增量新增方法，但旧方法的 AST 必须保持不变。"""
    baseline, actual = _baseline(tmp_path, comparison="python_ast")
    manifest_path = baseline / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["comparison"] = "python_ast_compatible"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    _write(
        baseline / "expected/artifact.py",
        """
        class CartPage:
            def total(self, value: int) -> int:
                return value + 1
        """,
    )
    _write(
        actual / "artifact.py",
        """
        from pathlib import Path

        class CartPage:
            def total(self, value: int) -> int:
                return value + 1

            def capture(self, path: Path) -> None:
                path.touch()
        """,
    )

    report = checker.verify_baseline(baseline, actual)

    assert report.problems == []


def test_python_compatible_comparison_rejects_changed_existing_method(
    checker: Any, tmp_path: Path
) -> None:
    baseline, actual = _baseline(tmp_path, comparison="python_ast")
    manifest_path = baseline / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["comparison"] = "python_ast_compatible"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    _write(
        baseline / "expected/artifact.py",
        """
        class CartPage:
            def total(self, value: int) -> int:
                return value + 1
        """,
    )
    _write(
        actual / "artifact.py",
        """
        class CartPage:
            def total(self, value: int) -> int:
                return value - 1
        """,
    )

    report = checker.verify_baseline(baseline, actual)

    assert any("既有方法" in problem for problem in report.problems)


def test_modified_frozen_input_is_rejected(checker: Any, tmp_path: Path) -> None:
    baseline, actual = _baseline(tmp_path)
    _write(baseline / "input/source.yaml", "value: changed\n")
    _write(actual / "artifact.yaml", "alpha: 1\nbeta: [two, three]\n")

    report = checker.verify_baseline(baseline, actual)

    assert any("冻结输入摘要不匹配" in problem for problem in report.problems)


def test_registered_repository_baselines_verify_their_snapshots(checker: Any) -> None:
    root = Path(__file__).resolve().parents[2]
    manifests = sorted((root / ".agents" / "skills").glob("*/versions/baselines/*/manifest.yaml"))
    assert len(manifests) == 4
    for manifest in manifests:
        baseline = manifest.parent
        document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        assert document["skill_name"] == manifest.parents[3].name
        assert all(
            artifact.get("schema")
            for artifact in document["artifacts"]
            if artifact["comparison"] == "yaml"
        )
        report = checker.verify_baseline(baseline, root)
        assert report.problems == [], f"{baseline}: {report.problems}"
