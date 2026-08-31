#!/usr/bin/env python
"""Registry-driven artifact schema validator (Roadmap 1.2).

The single validation implementation called by skills, pre-commit and CI
(ARCHITECTURE §1): every given path is matched against
``scripts/schema_registry.yaml`` — the only filename↔schema authority — and
validated with jsonschema Draft-07 plus an explicit ``FormatChecker`` so
``format: date-time`` rejects malformed strings (rfc3339-validator).

Exit codes: 0 all valid · 1 validation failure or unregistered path ·
2 usage error. Failures name the exact JSON path of each violating element.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from pathlib import Path

from _registry_lib import (
    DEFAULT_REGISTRY,
    REPO_ROOT,
    RegistryError,
    _assert_safe_path,
    binding_for_path,
    load_registry,
    schema_errors,
)
from argus_core.parsing import load_yaml  # pyright: ignore[reportMissingImports]

_PRUNE = {".venv", ".git", "__pycache__", ".mimosa", ".pytest_cache", ".ruff_cache"}


def display_path(path: Path) -> str:
    absolute = path.resolve()
    try:
        return absolute.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def validate_one(path: Path, registry_path: Path) -> list[str]:
    relative = display_path(path)
    try:
        _assert_safe_path(path, label="artifact", require_file=True)
    except RegistryError as exc:
        return [str(exc)]
    binding = binding_for_path(path, registry_path)
    if binding is None:
        return [f"unregistered artifact path: {relative}"]
    try:
        document = load_yaml(path.read_bytes())
    except (OSError, UnicodeError, ValueError):
        return [f"{relative}: not a safely parseable YAML document"]
    return [f"{relative}: {message}" for message in schema_errors(binding, document)]


def all_registered_files(registry_path: Path) -> list[Path]:
    bindings = load_registry(registry_path)
    matches: list[Path] = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in _PRUNE and not d.startswith(".")]
        for name in files:
            path = Path(root) / name
            relative = path.relative_to(REPO_ROOT).as_posix()
            if any(fnmatch.fnmatch(relative, binding["path_pattern"]) for binding in bindings):
                matches.append(path)
    return sorted(matches)


def expand_targets(paths: list[Path]) -> list[Path]:
    """将迭代目录递归展开为 YAML，保持单文件 CLI 兼容。"""
    targets: list[Path] = []
    for path in paths:
        if path.is_symlink():
            targets.append(path)
        elif path.is_dir():
            targets.extend(
                sorted(candidate for candidate in path.rglob("*.yaml") if candidate.is_file())
            )
        else:
            targets.append(path)
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="YAML files or iteration dirs")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument(
        "--all",
        action="store_true",
        help="validate every repo file matching a registered path pattern",
    )
    args = parser.parse_args(argv)

    targets = expand_targets(list(args.paths))
    if args.all:
        targets.extend(all_registered_files(args.registry))
    if not args.all and not targets:
        parser.error("no paths given (pass file paths or --all)")
        return 2
    if not targets:
        print("validate_schema: no registered artifact files found; nothing to validate")
        return 0

    failures: list[str] = []
    for path in targets:
        try:
            failures.extend(validate_one(path, args.registry))
        except RegistryError as exc:
            failures.append(str(exc))
    for failure in failures:
        print(f"error: {failure}", file=sys.stderr)
    if failures:
        print(f"validate_schema: {len(failures)} error(s)", file=sys.stderr)
        return 1
    print(f"validate_schema: {len(targets)} file(s) valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
