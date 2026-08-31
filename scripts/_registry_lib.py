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
import os
from pathlib import Path
from typing import Any

from argus_core.parsing import load_json, load_yaml  # pyright: ignore[reportMissingImports]
from jsonschema import Draft7Validator, FormatChecker  # pyright: ignore[reportMissingModuleSource]

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = REPO_ROOT / "scripts" / "schema_registry.yaml"


class RegistryError(Exception):
    """User-facing registry or validation failure."""


def _assert_safe_path(path: Path, *, label: str, require_file: bool = False) -> None:
    candidate = path if path.is_absolute() else Path.cwd() / path
    if "\x00" in str(candidate) or "\\" in str(candidate) or ".." in candidate.parts:
        raise RegistryError(f"{label} must not contain path traversal: {path}")
    current = Path(candidate.anchor)
    for part in candidate.parts:
        current /= part
        if current.is_symlink():
            raise RegistryError(f"{label} must not pass through a symlink: {path}")
    if require_file and (candidate.is_symlink() or not candidate.is_file()):
        raise RegistryError(f"{label} must be a regular file: {path}")


def _validate_relative_reference(value: object, *, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or "\\" in value
        or Path(value).is_absolute()
        or ".." in Path(value).parts
    ):
        raise RegistryError(f"{label} must be a safe repository-relative path")


def load_registry(registry_path: Path = DEFAULT_REGISTRY) -> list[dict[str, Any]]:
    _assert_safe_path(registry_path, label="schema registry", require_file=True)
    try:
        data = load_yaml(registry_path.read_bytes())
    except (OSError, ValueError) as exc:
        raise RegistryError(f"schema registry {registry_path} is not safely readable") from exc
    bindings = data.get("bindings") if isinstance(data, dict) else None
    if not isinstance(bindings, list) or not bindings:
        raise RegistryError(f"schema registry {registry_path} has no bindings")
    for binding in bindings:
        if not isinstance(binding, dict):
            raise RegistryError(f"registry binding must be an object: {binding!r}")
        if not isinstance(binding.get("artifact"), str) or not binding["artifact"]:
            raise RegistryError(f"registry binding missing 'artifact': {binding}")
        if not isinstance(binding.get("path_pattern"), str) or not binding["path_pattern"]:
            raise RegistryError(f"registry binding missing 'path_pattern': {binding}")
        path_pattern = binding["path_pattern"]
        if (
            "\x00" in path_pattern
            or "\\" in path_pattern
            or Path(path_pattern).is_absolute()
            or ".." in Path(path_pattern).parts
        ):
            raise RegistryError(
                f"registry binding {binding['artifact']!r} has an unsafe path_pattern"
            )
        has_single = isinstance(binding.get("schema"), str) and bool(binding["schema"])
        variants = binding.get("any_of")
        has_variants = isinstance(variants, list) and len(variants) >= 1
        if has_single:
            _validate_relative_reference(binding["schema"], label="schema reference")
        if isinstance(variants, list) and any(
            not isinstance(item, str) or not item for item in variants
        ):
            raise RegistryError(f"registry binding {binding['artifact']!r} has invalid any_of")
        if isinstance(variants, list):
            for item in variants:
                _validate_relative_reference(item, label="schema reference")
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
        _assert_safe_path(schema_path, label="schema", require_file=True)
        try:
            schema = load_json(schema_path.read_bytes())
        except (OSError, UnicodeError, ValueError) as exc:
            raise RegistryError(f"schema {schema_path} is not safely readable") from exc
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
    _assert_safe_path(path, label="artifact", require_file=True)
    binding = binding_for_path(path, registry_path)
    if binding is None:
        relative = Path(os.path.relpath(path, REPO_ROOT)).as_posix()
        raise RegistryError(f"unregistered artifact path: {relative}")
    try:
        document = load_yaml(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise RegistryError(f"{path} is not a safely parseable YAML document") from exc
    errors = schema_errors(binding, document)
    if errors:
        detail = "; ".join(errors)
        raise RegistryError(f"{path} failed {binding['artifact']}: {detail}")
    return binding
