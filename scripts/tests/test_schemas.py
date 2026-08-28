"""Roadmap 1.1 acceptance tests: every schema validates a hand-written valid
fixture and rejects invalid ones (missing required, bad enum/pattern, failed
conditionals, vacuous-conditional regressions).

Fixture naming convention under scripts/tests/fixtures/schemas/:
  <artifact>--<scenario>.valid.yaml    must pass
  <artifact>--<scenario>.invalid.yaml  must be rejected
Placement follows DATA_MODEL ownership (skills' schemas/, scripts/schemas/,
plugins/_interface/schemas/).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft7Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "schemas"

_FTD = REPO_ROOT / ".agents/skills/functional-test-design/schemas"
_ATD = REPO_ROOT / ".agents/skills/api-test-design/schemas"
_PAYLOADS = REPO_ROOT / "plugins/_interface/schemas"
_SCRIPTS_SCHEMAS = REPO_ROOT / "scripts/schemas"

SCHEMAS: dict[str, Path] = {
    "requirements": _FTD / "requirements.schema.json",
    "exemptions": REPO_ROOT / "scripts/schemas/exemptions.schema.json",
    "iteration": REPO_ROOT / "scripts/schemas/iteration.schema.json",
    "test_points": _FTD / "test_points.schema.json",
    "functional_cases": _FTD / "functional_cases.schema.json",
    "api_spec": _ATD / "api_spec.schema.json",
    "api_cases": _ATD / "api_cases.schema.json",
    "traceability": REPO_ROOT / "scripts/schemas/traceability.schema.json",
    "run_summary": REPO_ROOT / "scripts/schemas/run_summary.schema.json",
    "requirement_source_payload": _PAYLOADS / "requirement_source_payload.schema.json",
    "api_source_payload": _PAYLOADS / "api_source_payload.schema.json",
    "medusa_source": _SCRIPTS_SCHEMAS / "medusa_source.schema.json",
}


def load_schema(name: str) -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(SCHEMAS[name].read_text(encoding="utf-8"))
    return schema


def validate(name: str, document: Any) -> list[str]:
    validator = Draft7Validator(load_schema(name), format_checker=FormatChecker())
    return [e.message for e in validator.iter_errors(document)]


def schema_cases(kind: str) -> list[tuple[str, Path]]:
    fixtures = sorted(FIXTURE_DIR.glob(f"*.{kind}.yaml"))
    assert fixtures, f"no {kind} fixtures found"
    return [(f.name.split("--", 1)[0], f) for f in fixtures]


def fixture_id(value: object) -> str:
    if isinstance(value, Path):
        return value.name
    return str(value)


@pytest.mark.parametrize(
    ("schema_name", "fixture_path"),
    schema_cases("valid"),
    ids=fixture_id,
)
def test_valid_fixtures_pass(schema_name: str, fixture_path: Path) -> None:
    document = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    errors = validate(schema_name, document)
    assert errors == [], f"{fixture_path.name} should pass: {errors}"


@pytest.mark.parametrize(
    ("schema_name", "fixture_path"),
    schema_cases("invalid"),
    ids=fixture_id,
)
def test_invalid_fixtures_rejected(schema_name: str, fixture_path: Path) -> None:
    document = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    errors = validate(schema_name, document)
    assert errors != [], f"{fixture_path.name} should be rejected"


def test_every_schema_has_at_least_one_fixture_pair() -> None:
    valid = {name for name, _ in schema_cases("valid")}
    invalid = {name for name, _ in schema_cases("invalid")}
    covered = valid & invalid
    missing = sorted(set(SCHEMAS) - covered - {"iteration"})
    assert missing == [], f"schemas without committed fixture pairs: {missing}"


def test_vacuous_conditional_out_of_scope_omitted_passes_without_reason() -> None:
    """An endpoint omitting `out_of_scope` entirely must NOT demand a reason
    (Draft-07 dialect rule: every `if` carries an explicit `required`)."""
    fixture = FIXTURE_DIR / "api_spec--in-scope-no-reason.valid.yaml"
    document = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    endpoint = document["endpoints"][0]
    assert "out_of_scope" not in endpoint and "out_of_scope_reason" not in endpoint
    assert validate("api_spec", document) == []


def test_api_spec_preserves_combinators_and_component_refs() -> None:
    """Combinators survive verbatim and `$ref`s keep their component pattern."""
    fixture = FIXTURE_DIR / "api_spec--spec-valid.valid.yaml"
    document = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    assert validate("api_spec", document) == []
    order = document["components"]["schemas"]["Order"]
    assert order["properties"]["total"]["type"] == "integer"
    assert "oneOf" in document["components"]["schemas"]["Money"]
    ref = document["endpoints"][0]["parameters"][0]["schema"]["$ref"]
    assert ref.startswith("#/components/schemas/")
    response = document["endpoints"][0]["responses"][0]["body_schema"]
    assert [branch["$ref"] for branch in response["allOf"][:1]] == ["#/components/schemas/Order"]


def test_iteration_schema_fixture_pair_from_scaffolder_document(
    new_iteration: Any,
) -> None:
    """The iteration aggregate (DATA_MODEL §3) is exercised by 0.7's scaffolder
    tests; here one canonical valid/invalid pair proves the schema directly."""
    valid = new_iteration.build_iteration_document("2026-08-direct", "ui")
    assert validate("iteration", valid) == []
    invalid = dict(valid)
    invalid["branches"] = {"ui": True, "api": True}
    assert validate("iteration", invalid) != []
