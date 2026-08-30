#!/usr/bin/env python
"""对仓库内每个 v1 iteration 执行语义覆盖门禁。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from _registry_lib import REPO_ROOT, RegistryError, _assert_safe_path


def _run_checker(checker: str, iteration: Path, *extra: str) -> int:
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / checker),
        str(iteration),
        *extra,
    ]
    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("root", type=Path, nargs="?", default=Path("iterations"))
    args = parser.parse_args(argv)

    root = args.root if args.root.is_absolute() else REPO_ROOT / args.root
    try:
        _assert_safe_path(root, label="iteration root")
    except RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if root.is_symlink() or not root.is_dir():
        print(f"error: iteration root {root} not found or is unsafe", file=sys.stderr)
        return 1

    failures = 0
    checked = 0
    try:
        iterations = sorted(path for path in root.iterdir() if path.is_dir())
    except OSError as exc:
        print(f"error: cannot read iteration root: {type(exc).__name__}", file=sys.stderr)
        return 1
    for iteration in iterations:
        try:
            _assert_safe_path(iteration, label="iteration")
        except RegistryError as exc:
            print(f"error: {exc}", file=sys.stderr)
            failures += 1
            continue
        functional_cases = iteration / "functional-cases.yaml"
        if functional_cases.is_file():
            checked += 1
            failures += (
                _run_checker("check_functional_expectations.py", iteration, "--enforce-seeds") != 0
            )

        api_cases = iteration / "api" / "cases.yaml"
        if api_cases.is_file():
            checked += 1
            failures += _run_checker("check_api_coverage.py", iteration) != 0

    if failures:
        print(f"check_iteration_gates: {failures} failure(s)", file=sys.stderr)
        return 1
    print(f"check_iteration_gates: OK [{checked} semantic gate(s)]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
