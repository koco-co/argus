#!/usr/bin/env python
"""API client/model conformance checker (Roadmap 1.12 / PRD §4.6).

Over ``automation/api/clients/**`` and ``automation/api/models/**``:

- every public client method must declare a return annotation (``__init__``
  and ``_private`` helpers are exempt) and that annotation must not be a raw
  ``dict`` shape (CODING_STANDARDS: ``model_dump()`` happens exactly once at
  the transport edge);
- the return annotation must pair with a pydantic ``BaseModel`` subclass
  defined under ``automation/api/models/**`` (client-method <-> model
  pairing);
- with ``--spec``: every model whose class name matches a schema in the
  normalized spec's ``components.schemas`` must declare only fields that the
  source schema also declares (client fields <= normalized source-schema
  fields) - hallucinated fields fail.

Models whose class name has no matching schema are skipped (the schema may
not have survived normalization - PRD §4.4 escalation path covers that).
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
    """BaseModel subclass name -> defining file."""
    models: dict[str, Path] = {}
    for path in sorted(models_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = (
                        base.attr
                        if isinstance(base, ast.Attribute)
                        else (base.id if isinstance(base, ast.Name) else None)
                    )
                    if base_name == "BaseModel":
                        models[node.name] = path
    return models


def model_fields(path: Path, class_name: str) -> dict[str, int]:
    """field name -> declaration line, for annotated class attributes."""
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
    """The models dir sibling of the scanned clients (sandbox/test friendly):
    derived from the first target containing an `automation` segment."""
    for path in targets:
        parts = path.resolve().parts
        if "automation" in parts:
            index = parts.index("automation")
            return Path(*parts[: index + 1]) / "api" / "models"
    return REPO_ROOT / "automation" / "api" / "models"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="client/model files to check")
    parser.add_argument(
        "--all", action="store_true", help="scan automation/api/** (requires --spec)"
    )
    parser.add_argument(
        "--spec", type=Path, help="api/spec.normalized.yaml for the field-subset check"
    )
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
