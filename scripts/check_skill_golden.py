#!/usr/bin/env python
"""校验 Skill 冻结输入及隔离再生成产物的 Schema/语义基线。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_COMPARISONS = {"yaml", "python_ast", "python_ast_compatible"}


@dataclass
class Report:
    """收集全部差异，避免首个失败掩盖同批其他回归。"""

    problems: list[str] = field(default_factory=list)
    compared: list[str] = field(default_factory=list)


def _safe_relative(value: object, *, field_name: str, report: Report) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        report.problems.append(f"{field_name} 必须是非空相对路径")
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        report.problems.append(f"{field_name} 不得越出基线目录：{value}")
        return None
    return path


def _load_yaml(path: Path, *, label: str, report: Report) -> Any | None:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        report.problems.append(f"{label} 无法读取为 YAML：{exc}")
        return None


def _verify_inputs(baseline_dir: Path, entries: object, report: Report) -> None:
    if not isinstance(entries, list) or not entries:
        report.problems.append("manifest.inputs 必须至少包含一份冻结输入")
        return
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            report.problems.append(f"manifest.inputs[{index}] 必须是对象")
            continue
        relative = _safe_relative(
            entry.get("path"), field_name=f"manifest.inputs[{index}].path", report=report
        )
        expected_hash = entry.get("sha256")
        if relative is None:
            continue
        path = baseline_dir / relative
        if not path.is_file():
            report.problems.append(f"冻结输入不存在：{relative.as_posix()}")
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if not isinstance(expected_hash, str) or actual_hash != expected_hash:
            report.problems.append(f"冻结输入摘要不匹配：{relative.as_posix()}，实际 {actual_hash}")


def _validate_schema(
    actual: Any,
    schema_value: object,
    *,
    artifact_path: Path,
    report: Report,
) -> None:
    schema_relative = _safe_relative(
        schema_value, field_name=f"{artifact_path.as_posix()}.schema", report=report
    )
    if schema_relative is None:
        return
    schema_path = REPO_ROOT / schema_relative
    schema = _load_yaml(schema_path, label=f"Schema {schema_relative.as_posix()}", report=report)
    if schema is None:
        return
    errors = sorted(
        Draft7Validator(schema, format_checker=FormatChecker()).iter_errors(actual),
        key=lambda error: list(error.absolute_path),
    )
    for error in errors:
        location = "/".join(str(item) for item in error.absolute_path) or "<root>"
        report.problems.append(
            f"{artifact_path.as_posix()} Schema 失败 {location}：{error.message}"
        )


def _compare_yaml(
    expected_path: Path,
    actual_path: Path,
    *,
    schema: object,
    report: Report,
) -> None:
    expected = _load_yaml(expected_path, label=f"黄金产物 {expected_path}", report=report)
    actual = _load_yaml(actual_path, label=f"再生成产物 {actual_path}", report=report)
    if expected is None or actual is None:
        return
    if schema is not None:
        _validate_schema(actual, schema, artifact_path=actual_path, report=report)
    if expected != actual:
        report.problems.append(
            f"{actual_path.name} 存在 YAML 语义差异："
            f"expected={json.dumps(expected, ensure_ascii=False, sort_keys=True)}；"
            f"actual={json.dumps(actual, ensure_ascii=False, sort_keys=True)}"
        )


def _ast_dump(path: Path, *, label: str, report: Report) -> str | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        report.problems.append(f"{label} 无法解析为 Python：{exc}")
        return None
    return ast.dump(tree, include_attributes=False)


def _compare_python(expected_path: Path, actual_path: Path, report: Report) -> None:
    expected = _ast_dump(expected_path, label=f"黄金产物 {expected_path}", report=report)
    actual = _ast_dump(actual_path, label=f"再生成产物 {actual_path}", report=report)
    if expected is not None and actual is not None and expected != actual:
        report.problems.append(f"{actual_path.name} 存在 Python AST 语义差异")


def _parse_python(path: Path, *, label: str, report: Report) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        report.problems.append(f"{label} 无法解析为 Python：{exc}")
        return None


def _compare_class_compatible(
    expected: ast.ClassDef,
    actual: ast.ClassDef,
    *,
    artifact_name: str,
    report: Report,
) -> None:
    """保持既有类/方法语义，允许共享 POM 增量增加方法。"""

    expected_header = ast.dump(
        ast.ClassDef(
            name=expected.name,
            bases=expected.bases,
            keywords=expected.keywords,
            body=[],
            decorator_list=expected.decorator_list,
            type_params=getattr(expected, "type_params", []),
        ),
        include_attributes=False,
    )
    actual_header = ast.dump(
        ast.ClassDef(
            name=actual.name,
            bases=actual.bases,
            keywords=actual.keywords,
            body=[],
            decorator_list=actual.decorator_list,
            type_params=getattr(actual, "type_params", []),
        ),
        include_attributes=False,
    )
    if expected_header != actual_header:
        report.problems.append(f"{artifact_name} 既有类 {expected.name} 定义发生语义差异")
        return

    function_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    actual_methods = {node.name: node for node in actual.body if isinstance(node, function_types)}
    for method in (node for node in expected.body if isinstance(node, function_types)):
        current = actual_methods.get(method.name)
        if current is None:
            report.problems.append(f"{artifact_name} 缺少既有方法 {expected.name}.{method.name}")
        elif ast.dump(method, include_attributes=False) != ast.dump(
            current, include_attributes=False
        ):
            report.problems.append(
                f"{artifact_name} 既有方法 {expected.name}.{method.name} 存在 AST 语义差异"
            )

    expected_other = {
        ast.dump(node, include_attributes=False)
        for node in expected.body
        if not isinstance(node, function_types)
    }
    actual_other = {
        ast.dump(node, include_attributes=False)
        for node in actual.body
        if not isinstance(node, function_types)
    }
    for missing in sorted(expected_other - actual_other):
        report.problems.append(f"{artifact_name} 既有类成员发生语义差异：{missing}")


def _compare_python_compatible(expected_path: Path, actual_path: Path, report: Report) -> None:
    """比较旧生成语义是否仍被当前增量共享资产完整保留。"""

    expected = _parse_python(expected_path, label=f"黄金产物 {expected_path}", report=report)
    actual = _parse_python(actual_path, label=f"再生成产物 {actual_path}", report=report)
    if expected is None or actual is None:
        return

    actual_classes = {node.name: node for node in actual.body if isinstance(node, ast.ClassDef)}
    function_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    actual_functions = {node.name: node for node in actual.body if isinstance(node, function_types)}
    actual_other = {
        ast.dump(node, include_attributes=False)
        for node in actual.body
        if not isinstance(node, (ast.ClassDef, *function_types))
    }

    for node in expected.body:
        if isinstance(node, ast.ClassDef):
            current_class = actual_classes.get(node.name)
            if current_class is None:
                report.problems.append(f"{actual_path.name} 缺少既有类 {node.name}")
            else:
                _compare_class_compatible(
                    node,
                    current_class,
                    artifact_name=actual_path.name,
                    report=report,
                )
        elif isinstance(node, function_types):
            current_function = actual_functions.get(node.name)
            if current_function is None:
                report.problems.append(f"{actual_path.name} 缺少既有函数 {node.name}")
            elif ast.dump(node, include_attributes=False) != ast.dump(
                current_function, include_attributes=False
            ):
                report.problems.append(f"{actual_path.name} 既有函数 {node.name} 存在 AST 语义差异")
        elif ast.dump(node, include_attributes=False) not in actual_other:
            report.problems.append(
                f"{actual_path.name} 既有模块成员存在 AST 语义差异："
                f"{ast.dump(node, include_attributes=False)}"
            )


def verify_baseline(baseline_dir: Path, actual_root: Path) -> Report:
    """用一份基线清单验证冻结输入和隔离目录内的再生成产物。"""

    report = Report()
    manifest_path = baseline_dir / "manifest.yaml"
    manifest = _load_yaml(manifest_path, label="基线清单", report=report)
    if not isinstance(manifest, dict):
        if manifest is not None:
            report.problems.append("基线清单根节点必须是对象")
        return report
    if manifest.get("schema_version") != "1.0":
        report.problems.append("manifest.schema_version 必须为 1.0")
    for key in ("skill_name", "skill_version", "sample_id"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            report.problems.append(f"manifest.{key} 必须是非空字符串")
    _verify_inputs(baseline_dir, manifest.get("inputs"), report)

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        report.problems.append("manifest.artifacts 必须至少包含一项")
        return report
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            report.problems.append(f"manifest.artifacts[{index}] 必须是对象")
            continue
        relative = _safe_relative(
            artifact.get("path"),
            field_name=f"manifest.artifacts[{index}].path",
            report=report,
        )
        comparison = artifact.get("comparison")
        if comparison not in ALLOWED_COMPARISONS:
            report.problems.append(f"manifest.artifacts[{index}].comparison 不支持：{comparison}")
            continue
        if relative is None:
            continue
        expected_path = baseline_dir / "expected" / relative
        actual_path = actual_root / relative
        if not expected_path.is_file():
            report.problems.append(f"黄金产物不存在：{relative.as_posix()}")
            continue
        if not actual_path.is_file():
            report.problems.append(f"再生成产物不存在：{relative.as_posix()}")
            continue
        if comparison == "yaml":
            _compare_yaml(
                expected_path,
                actual_path,
                schema=artifact.get("schema"),
                report=report,
            )
        elif comparison == "python_ast":
            _compare_python(expected_path, actual_path, report)
        else:
            _compare_python_compatible(expected_path, actual_path, report)
        report.compared.append(relative.as_posix())
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--actual-root", type=Path, required=True)
    args = parser.parse_args(argv)
    report = verify_baseline(args.baseline.resolve(), args.actual_root.resolve())
    if report.problems:
        for problem in report.problems:
            print(f"ERROR: {problem}")
        return 1
    print(f"Skill 黄金基线通过：{len(report.compared)} 项语义产物")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
