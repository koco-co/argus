#!/usr/bin/env python
"""Scaffold iterations/<id>/ — sole creator of iteration directories (Roadmap 0.7).

Creates the full iteration tree (ARCHITECTURE §2) with ``iteration.yaml`` at
``state: created`` and declared branches, then validates every scaffolded YAML
that has a registry binding through the shared registry path
(``scripts/schema_registry.yaml`` — the same table Phase 1's
``validate_schema.py`` will expose as a CLI). Artifact YAMLs beyond the
iteration aggregate are produced by their owning skills (DATA_MODEL §1
"Produced by"), not by this scaffolder.

Rules enforced here (v1):
- ``iteration_id`` must match GLOSSARY format ``^[a-z0-9][a-z0-9-]{2,63}$``.
- Same-ID rerun errors unless ``--force``; force requires re-typing the ID.
- At most one non-terminal iteration may exist (ARCHITECTURE §5.1).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from _registry_lib import (
    DEFAULT_REGISTRY,
    RegistryError,
    schema_errors,
)
from _registry_lib import (
    load_registry as _load_registry,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = DEFAULT_REGISTRY

ITERATION_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
# Terminal states per ARCHITECTURE §5.1: everything else counts as in-progress
# and v1 permits only one such iteration at a time.
TERMINAL_STATES = {"accepted", "merged"}

# Directory skeleton of one iteration (ARCHITECTURE §2). Artifact YAML/MD files
# are NOT scaffolded: most DATA_MODEL schemas have no schema-valid empty form
# (minItems 1), and an invalid placeholder would fail pre-commit/CI once its
# schema registers in Phase 1 — owning skills create them at their phase.
ITERATION_DIRS = (
    "00-raw",
    "api",
    "exports",
    "runs",
)


class NewIterationError(Exception):
    """User-facing scaffolding failure."""


def load_registry(registry_path: Path = REGISTRY_PATH) -> list[dict[str, Any]]:
    try:
        return _load_registry(registry_path)  # type: ignore[arg-type]
    except RegistryError as exc:
        raise NewIterationError(str(exc)) from exc


def binding_for(bindings: list[dict[str, Any]], relative_path: str) -> dict[str, Any] | None:
    """Kept for callers that already hold a bindings list."""
    from _registry_lib import binding_for as _binding_for

    return _binding_for(bindings, relative_path)


def validate_artifact(
    canonical_path: str,
    document: Any,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    """Validate a document against the schema its canonical artifact path is
    bound to in the registry. Raises NewIterationError for unregistered paths
    or validation failures, naming the exact JSON path of each violation."""
    try:
        bindings = _load_registry(registry_path)
        from _registry_lib import binding_for as _binding_for

        binding = _binding_for(bindings, canonical_path)
        if binding is None:
            raise NewIterationError(f"unregistered artifact path: {canonical_path}")
        errors = schema_errors(binding, document)
    except RegistryError as exc:
        raise NewIterationError(str(exc)) from exc
    if errors:
        raise NewIterationError(
            f"{canonical_path} failed {binding['artifact']}: {'; '.join(errors)}"
        )
    return binding


def validate_via_registry(yaml_path: Path, registry_path: Path = REGISTRY_PATH) -> dict[str, str]:
    """Validate one YAML file through the shared registry path (repo-relative
    location decides the binding — the Phase 1 validator behavior)."""
    relative = Path(os.path.relpath(yaml_path, REPO_ROOT)).as_posix()
    document = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return validate_artifact(relative, document, registry_path)


def find_in_progress_iteration(iterations_dir: Path) -> str | None:
    if not iterations_dir.is_dir():
        return None
    for iteration_yaml in sorted(iterations_dir.glob("*/iteration.yaml")):
        try:
            document = yaml.safe_load(iteration_yaml.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise NewIterationError(
                f"cannot parse {iteration_yaml} while checking the single-in-progress rule: {exc}"
            ) from exc
        state = document.get("state") if isinstance(document, dict) else None
        if state not in TERMINAL_STATES:
            return iteration_yaml.parent.name
    return None


def build_iteration_document(iteration_id: str, branch: str) -> dict:
    branches = {"ui": branch == "ui", "api": branch == "api"}
    not_started = {"status": "not_started", "input_sha256": None}
    return {
        "schema_version": "1.0",
        "iteration_id": iteration_id,
        "state": "created",
        "blocked_reason": None,
        "branches": branches,
        "artifacts": {
            "requirements": dict(not_started),
            "exemptions": dict(not_started),
            "test_points": dict(not_started),
            "functional_cases": dict(not_started),
            "api_spec": dict(not_started),
            "api_cases": dict(not_started),
            "web_automation": dict(not_started),
            "api_automation": dict(not_started),
            "execution": dict(not_started),
        },
        "approvals": [],
        "events": [],
        "source_manifest": [],
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def scaffold_iteration(
    iteration_id: str,
    branch: str,
    iterations_dir: Path,
    registry_path: Path = REGISTRY_PATH,
    force: bool = False,
) -> Path:
    if not ITERATION_ID_PATTERN.fullmatch(iteration_id):
        raise NewIterationError(
            f"invalid iteration_id {iteration_id!r}: must match "
            f"^[a-z0-9][a-z0-9-]{{2,63}}$ (GLOSSARY: 3-64 chars, lowercase, "
            f"leading YYYY-MM- recommended)"
        )
    in_progress = find_in_progress_iteration(iterations_dir)
    if in_progress is not None and in_progress != iteration_id:
        raise NewIterationError(
            f"iteration {in_progress!r} is still non-terminal; v1 allows at most "
            f"one in-progress iteration (ARCHITECTURE §5.1). Finish or close it first."
        )
    iteration_dir = iterations_dir / iteration_id
    exists_nonempty = iteration_dir.exists() and any(iteration_dir.iterdir())
    if exists_nonempty and not force:
        raise NewIterationError(
            f"iterations/{iteration_id} already exists; rerunning the scaffolder "
            f"requires --force plus re-typed confirmation"
        )
    if exists_nonempty and force:
        # Reset only scaffolder-owned state (template dirs + iteration.yaml);
        # anything else found in the directory belongs to its owners and stays.
        for member in ITERATION_DIRS:
            shutil.rmtree(iteration_dir / member, ignore_errors=True)
        (iteration_dir / "iteration.yaml").unlink(missing_ok=True)
    for member in ITERATION_DIRS:
        (iteration_dir / member).mkdir(parents=True, exist_ok=True)
        keeper = iteration_dir / member / ".gitkeep"
        if not keeper.exists():
            keeper.touch()
    iteration_yaml = iteration_dir / "iteration.yaml"
    document = build_iteration_document(iteration_id, branch)
    iteration_yaml.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    validate_artifact(f"iterations/{iteration_id}/iteration.yaml", document, registry_path)
    return iteration_dir


def print_tree(iteration_dir: Path) -> None:
    for path in sorted(iteration_dir.rglob("*")):
        kind = "dir " if path.is_dir() else "file"
        print(f"  {kind}  {path.relative_to(iteration_dir.parent).as_posix()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("iteration_id", help="GLOSSARY-format iteration id")
    parser.add_argument(
        "--branch",
        choices=("ui", "api"),
        default="ui",
        help="declared branch for this iteration (v1: exactly one; default: ui)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-scaffold an existing same-ID directory (requires re-typed confirmation)",
    )
    parser.add_argument(
        "--iterations-dir",
        type=Path,
        default=REPO_ROOT / "iterations",
        help="iterations root (tests override this)",
    )
    args = parser.parse_args(argv)

    iterations_dir = (
        args.iterations_dir
        if args.iterations_dir.is_absolute()
        else REPO_ROOT / args.iterations_dir
    )
    iteration_dir = iterations_dir / args.iteration_id
    needs_confirmation = args.force and iteration_dir.exists() and any(iteration_dir.iterdir())
    if needs_confirmation:
        try:
            answer = input(
                f"Type the iteration id to confirm re-scaffold of iterations/{args.iteration_id}: "
            )
        except EOFError:
            answer = ""
        if answer != args.iteration_id:
            print("confirmation did not match the iteration id; aborting", file=sys.stderr)
            return 2
    try:
        scaffold_iteration(args.iteration_id, args.branch, iterations_dir, force=args.force)
    except NewIterationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"scaffolded iterations/{args.iteration_id} (branches: {args.branch})")
    print_tree(iteration_dir)
    route = (
        "functional-test-design (M1 -> M2 -> M3, then web automation)"
        if args.branch == "ui"
        else "M1 accepted only, then api-test-design (M4 -> M5; no test_points.yaml)"
    )
    print(f"route: {route}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
