#!/usr/bin/env python
"""Functional expectation checker (Roadmap 1.15a / DATA_MODEL §5, §11).

Semantic checks over ``functional-cases.yaml`` that JSON Schema cannot
express:

- exactly ONE ``module:<name>`` tag per case (Draft-07 ``contains`` only
  proves >=1; this check enforces uniqueness);
- a ``derived_value`` step must carry ``derived_from`` AND describe the
  expected value as a relationship - an unexplained currency amount or
  money-shaped literal inside the expectation text fails (the oracle must be
  re-derived from seeded context, never copied: PRD §4.5);
- ``derived_from.seed`` must resolve against the target app's seed registry
  (``shared/testdata/seed-registry.yaml``, produced by Roadmap 5.0.2):
  * registry absent            -> ADVISORY WARNING (early M3 dry-runs) and
                                  a hard failure under ``--enforce-seeds``
                                  (the M6 generation gate);
  * registry present, seed not -> hard failure always (hallucinated seed).

Sources are schema-gated through the shared registry before checking.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from _registry_lib import REPO_ROOT, RegistryError, _assert_safe_path, validate_path
from argus_core.parsing import load_yaml  # pyright: ignore[reportMissingImports]

DEFAULT_REGISTRY = REPO_ROOT / "shared" / "testdata" / "seed-registry.yaml"
_CURRENCY = re.compile(
    r"[$¥€£]\s?\d[\d,]*(?:\.\d{1,2})?"
    r"|\b\d[\d,]*\.\d{2}\s?(?:USD|EUR|CNY|GBP|JPY)\b"
    r"|\b\d[\d,]*\s?(?:美元|元)\b"
)


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.warnings: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def load_seed_registry(registry_path: Path) -> dict[str, Any] | None:
    """The seed mapping when the registry exists, else None."""
    _assert_safe_path(registry_path, label="seed registry", require_file=False)
    if registry_path.is_symlink():
        raise ValueError("seed registry must be a regular file")
    if not registry_path.exists():
        return None
    if not registry_path.is_file():
        raise ValueError("seed registry must be a regular file")
    document = load_yaml(registry_path.read_bytes()) or {}
    if not isinstance(document, dict) or not isinstance(document.get("seeds"), dict):
        raise ValueError("seed registry must contain an object-valued seeds mapping")
    return document["seeds"]


def check_case(
    case: dict[str, Any], seeds: dict[str, Any] | None, enforce_seeds: bool, report: Report
) -> None:
    case_id = case["case_id"]
    module_tags = [t for t in case["tags"] if t.startswith("module:")]
    if len(module_tags) != 1:
        report.fail(
            f"case {case_id} carries {len(module_tags)} module: tags "
            f"({', '.join(module_tags) or 'none'}) - exactly one is required"
        )

    for number, step in enumerate(case["steps"], start=1):
        if step["expected_kind"] != "derived_value":
            continue
        derived_from = step.get("derived_from")
        if derived_from is None:
            report.fail(f"case {case_id} step {number}: derived_value without derived_from")
            continue
        if _CURRENCY.search(step["expected"]):
            report.fail(
                f"case {case_id} step {number}: unexplained currency/numeric literal "
                "in expectation - describe the relationship and derive the concrete "
                "value from the seed context"
            )
        seed = derived_from["seed"]
        if seeds is None:
            message = (
                f"case {case_id} step {number}: seed registry absent - cannot verify "
                f"derived_from.seed {seed!r}"
            )
            if enforce_seeds:
                report.fail(message)
            else:
                report.warn(message)
        elif seed not in seeds:
            report.fail(
                f"case {case_id} step {number}: hallucinated seed {seed!r} - "
                f"not present in the seed registry"
            )


def check_cases(
    cases: dict[str, Any], seeds: dict[str, Any] | None, enforce_seeds: bool, report: Report
) -> None:
    for case in cases["cases"]:
        check_case(case, seeds, enforce_seeds, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration", type=Path, help="iterations/<id> directory")
    parser.add_argument(
        "--enforce-seeds",
        action="store_true",
        help="M6 gate: a missing seed registry is a hard failure instead of a warning",
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args(argv)

    iteration_dir = args.iteration if args.iteration.is_absolute() else REPO_ROOT / args.iteration
    cases_path = iteration_dir / "functional-cases.yaml"
    if cases_path.is_symlink() or not cases_path.is_file():
        print(f"error: {cases_path} not found or not a regular file", file=sys.stderr)
        return 1
    try:
        validate_path(cases_path)
        cases: dict[str, Any] = load_yaml(cases_path.read_bytes()) or {}
        if not isinstance(cases, dict) or not isinstance(cases.get("cases"), list):
            raise ValueError("functional cases must contain a cases list")
        seeds = load_seed_registry(args.registry)
    except (OSError, UnicodeError, ValueError, RegistryError):
        print("error: functional cases or seed registry is not safely parseable", file=sys.stderr)
        return 1
    report = Report()
    check_cases(cases, seeds, args.enforce_seeds, report)

    for warning in report.warnings:
        print(f"expectation warning: {warning}", file=sys.stderr)
    for problem in report.problems:
        print(f"expectation violation: {problem}")
    if report.problems:
        print(
            f"check_functional_expectations: {len(report.problems)} violation(s)",
            file=sys.stderr,
        )
        return 1
    print(
        f"check_functional_expectations: OK "
        f"[{len(cases['cases'])} case(s), seed registry "
        f"{'present' if seeds is not None else 'absent'}]"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
