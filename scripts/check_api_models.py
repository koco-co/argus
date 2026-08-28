#!/usr/bin/env python
"""API 客户端与模型一致性检查器（Roadmap 1.12、PRD §4.6）。

检查 ``automation/api/clients/**`` 与 ``automation/api/models/**``：

- 每个公开客户端方法必须声明返回类型（``__init__`` 和 ``_private`` 辅助方法除外），且
  不能返回原始 ``dict``；依据 CODING_STANDARDS，``model_dump()`` 只能在传输边界执行一次；
- 返回类型必须对应 ``automation/api/models/**`` 中定义的 Pydantic ``BaseModel`` 子类；
- 使用 ``--spec`` 时，类名与规范 ``components.schemas`` 匹配的模型只能声明来源 Schema
  已声明的字段；客户端字段超出来源字段即失败。

没有匹配 Schema 的模型会跳过（规范可能在规范化阶段被降级，PRD §4.4 的升级路径负责此情况）。
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Any

import yaml
from _registry_lib import REPO_ROOT, RegistryError, validate_path


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)


def _annotation_name(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value  # forward reference
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_raw_dict(node: ast.expr | None) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "dict"
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and node.value.split("[")[0].strip() == "dict"
    if isinstance(node, ast.Subscript):
        return _is_raw_dict(node.value)
    return False


def collect_models(models_dir: Path) -> dict[str, Path]:
    """BaseModel（含间接继承）子类名 -> 定义文件。"""
    models: dict[str, Path] = {}
    inheritance: dict[str, tuple[Path, set[str]]] = {}
    for path in sorted(models_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                base_names = {
                    base.attr
                    if isinstance(base, ast.Attribute)
                    else (base.id if isinstance(base, ast.Name) else "")
                    for base in node.bases
                }
                inheritance[node.name] = (path, base_names)
    # 生成模型通常通过统一配置基类间接继承 Pydantic；固定点迭代可识别
    # 任意层级的继承，同时保持只扫描 models/ 目录的边界。
    known = {name for name, (_, bases) in inheritance.items() if "BaseModel" in bases}
    changed = True
    while changed:
        changed = False
        for name, (_, bases) in inheritance.items():
            if name not in known and bases & known:
                known.add(name)
                changed = True
    for name in known:
        models[name] = inheritance[name][0]
    return models


def model_fields(path: Path, class_name: str) -> dict[str, int]:
    """返回带注解类字段的字段名 -> 声明行号映射。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    fields: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for statement in node.body:
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                    fields[statement.target.id] = statement.lineno
    return fields


def check_clients(client_files: list[Path], models: dict[str, Path], report: Report) -> None:
    for path in client_files:
        # --all 会同时发现 conftest、models 与 tests；只有 clients/** 属于
        # “公开传输方法必须返回 Pydantic 模型”的契约边界。
        if "/clients/" not in f"/{path.as_posix()}":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            annotation = node.returns
            if annotation is None:
                report.fail(
                    f"{path}:{node.lineno}: public client method {node.name!r} has no "
                    f"return annotation (typed end-to-end required)"
                )
                continue
            if _is_raw_dict(annotation):
                report.fail(
                    f"{path}:{node.lineno}: client method {node.name!r} returns a raw "
                    f"dict - pair it with a pydantic model"
                )
                continue
            name = _annotation_name(annotation)
            if name is not None and name not in models and name != "None":
                report.fail(
                    f"{path}:{node.lineno}: client method {node.name!r} returns "
                    f"{name!r} which is not a model under automation/api/models/**"
                )


def check_models_against_spec(models_dir: Path, spec: dict[str, Any], report: Report) -> None:
    schemas = spec.get("components", {}).get("schemas", {})
    if not schemas:
        return
    for path in sorted(models_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            schema = schemas.get(node.name)
            if schema is None or "properties" not in schema:
                continue
            allowed = set(schema["properties"])
            for field_name, lineno in model_fields(path, node.name).items():
                if field_name not in allowed:
                    report.fail(
                        f"{path}:{lineno}: model {node.name!r} declares field "
                        f"{field_name!r} which is absent from the normalized source "
                        f"schema (hallucinated field)"
                    )


def models_dir_for(targets: list[Path]) -> Path:
    """返回待扫描客户端的同级 models 目录（兼容沙箱和测试路径）。"""
    for path in targets:
        parts = path.resolve().parts
        if "automation" in parts:
            index = parts.index("automation")
            return Path(*parts[: index + 1]) / "api" / "models"
    return REPO_ROOT / "automation" / "api" / "models"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="需要检查的客户端或模型文件")
    parser.add_argument(
        "--all", action="store_true", help="扫描 automation/api/**（可配合 --spec）"
    )
    parser.add_argument("--spec", type=Path, help="用于字段子集检查的 api/spec.normalized.yaml")
    args = parser.parse_args(argv)

    targets: list[Path] = list(args.paths)
    if args.all:
        api_dir = REPO_ROOT / "automation" / "api"
        targets.extend(sorted(api_dir.rglob("*.py")))
    if not targets:
        parser.error("no paths given (pass file paths or --all)")
        return 2

    report = Report()
    models_dir = models_dir_for(targets)
    models = collect_models(models_dir)
    check_clients(targets, models, report)

    if args.spec:
        try:
            validate_path(args.spec)
        except RegistryError as exc:
            report.fail(str(exc))
        else:
            spec = yaml.safe_load(args.spec.read_text(encoding="utf-8")) or {}
            check_models_against_spec(models_dir, spec, report)

    for problem in report.problems:
        print(f"api model violation: {problem}")
    if report.problems:
        print(f"check_api_models: {len(report.problems)} violation(s)", file=sys.stderr)
        return 1
    print(f"check_api_models: {len(targets)} file(s) conformant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
