"""Shared schema-registry loading and validation (single implementation).

Consumed by ``scripts/new_iteration.py`` (scaffold-time validation) and
``scripts/validate_schema.py`` (pre-commit/CI CLI). The registry table is the
only filename↔schema authority (ARCHITECTURE §1, DATA_MODEL §11); nothing
infers a schema from filename similarity.

Path matching: a file's repo-relative path is matched against binding
``path_pattern`` globs (fnmatch). Paths outside the repo (tests, scratch
trees) additionally match by their canonical suffix starting at ``iterations/``
so validation behaves identically in sandbox roots; a repo file must never
rely on that fallback.
"""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = REPO_ROOT / "scripts" / "schema_registry.yaml"


class RegistryError(Exception):
    """User-facing registry or validation failure."""


def load_registry(registry_path: Path = DEFAULT_REGISTRY) -> list[dict[str, Any]]:
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    bindings = data.get("bindings") if isinstance(data, dict) else None
    if not isinstance(bindings, list) or not bindings:
        raise RegistryError(f"schema registry {registry_path} has no bindings")
    for binding in bindings:
        if not isinstance(binding.get("artifact"), str) or not binding["artifact"]:
            raise RegistryError(f"registry binding missing 'artifact': {binding}")
        if not isinstance(binding.get("path_pattern"), str) or not binding["path_pattern"]:
            raise RegistryError(f"registry binding missing 'path_pattern': {binding}")
        has_single = isinstance(binding.get("schema"), str) and bool(binding["schema"])
        variants = binding.get("any_of")
        has_variants = isinstance(variants, list) and len(variants) >= 1
        if has_single == has_variants:  # exactly one of the two forms
            raise RegistryError(
                f"registry binding {binding['artifact']!r} needs exactly one of "
                f"'schema' or a non-empty 'any_of' list"
            )
    return bindings


def binding_for(bindings: list[dict[str, Any]], relative_path: str) -> dict[str, Any] | None:
    for binding in bindings:
        if fnmatch.fnmatch(relative_path, binding["path_pattern"]):
            return binding
    return None


def _candidates(path: Path) -> list[str]:
    """Repo-relative path first; then the canonical iterations/ suffix so
    sandbox/test trees resolve to the same bindings."""
    relative = Path(os.path.relpath(path, REPO_ROOT)).as_posix()
    candidates = [relative]
    marker = "iterations/"
    index = relative.find(marker)
    if index > 0:
        candidates.append(relative[index:])
    return candidates


def binding_for_path(path: Path, registry_path: Path = DEFAULT_REGISTRY) -> dict[str, Any] | None:
    bindings = load_registry(registry_path)
    for candidate in _candidates(path):
        binding = binding_for(bindings, candidate)
        if binding is not None:
            return binding
    return None


def _json_path(error: Any) -> str:
    parts = [f"[{p}]" if isinstance(p, int) else str(p) for p in error.absolute_path]
    if not parts:
        return "<root>"
    return parts[0] + "".join((p if p.startswith("[") else f".{p}") for p in parts[1:])


def schema_errors(binding: dict[str, Any], document: Any) -> list[str]:
    """Validate a document against the binding's schema (or any_of variants).
    Returns an empty list when valid; otherwise messages naming the exact
    JSON path of each violation (for any_of, the errors of every variant)."""
    schema_refs: list[str] = [binding["schema"]] if "schema" in binding else list(binding["any_of"])
    messages: list[str] = []
    for schema_ref in schema_refs:
        schema_path = Path(__file__).resolve().parent.parent / schema_ref
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = Draft7Validator(schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
        for error in errors:
            messages.append(f"at '{_json_path(error)}': {error.message} [{schema_ref}]")
        if not errors:
            return []  # any_of: first variant that validates wins
    return messages


def validate_path(path: Path, registry_path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    """Validate one YAML file through the registry. Raises RegistryError for
    unregistered paths or schema violations."""
    binding = binding_for_path(path, registry_path)
    if binding is None:
        relative = Path(os.path.relpath(path, REPO_ROOT)).as_posix()
        raise RegistryError(f"unregistered artifact path: {relative}")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RegistryError(f"{path} is not parseable YAML: {exc}") from exc
    errors = schema_errors(binding, document)
    if errors:
        detail = "; ".join(errors)
        raise RegistryError(f"{path} failed {binding['artifact']}: {detail}")
    return binding
