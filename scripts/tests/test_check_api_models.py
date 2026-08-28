"""Roadmap 1.12 acceptance tests for scripts/check_api_models.py.

DoD: dict-returning-client and unknown-field fixtures fail; a typed
spec-conformant client passes.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import _load_script


@pytest.fixture(scope="module")
def checker() -> Any:
    return _load_script("check_api_models")


def _models_dir(tmp_path: Path, body: str, name: str = "things_models.py") -> Path:
    path = tmp_path / "automation" / "api" / "models" / "things" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _client_file(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "automation" / "api" / "clients" / "things" / "things_client.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


TYPED_MODELS = """\
    from pydantic import BaseModel

    class ThingResponse(BaseModel):
        id: str
        label: str
    """

TYPED_CLIENT = """\
    from automation.api.models.things.things_models import ThingResponse

    class ThingsClient:
        def get_thing(self, thing_id: str) -> ThingResponse:
            resp = self._http.get(f"/store/things/{thing_id}")
            return ThingResponse.model_validate(resp.json())
    """


def _spec(**schemas: Any) -> dict:
    return {
        "schema_version": "1.0",
        "iteration_id": "2026-08-api-cov",
        "status": "spec_valid",
        "service_name": "store",
        "generated_from": {
            "artifact": "iterations/2026-08-api-cov/00-raw/openapi.yaml",
            "sha256": "a" * 64,
        },
        "endpoints": [
            {
                "operation_id": "getThing",
                "path": "/store/things",
                "method": "GET",
                "module": "things",
                "parameters": [],
                "responses": [{"status_code": 200}],
            }
        ],
        "components": {"schemas": schemas},
    }


def test_typed_conformant_client_passes(checker: Any, tmp_path: Path) -> None:
    _models_dir(tmp_path, TYPED_MODELS)
    client = _client_file(tmp_path, TYPED_CLIENT)
    report = checker.Report()
    models = checker.collect_models(tmp_path / "automation" / "api" / "models")
    checker.check_clients([client], models, report)
    assert report.problems == []


def test_dict_returning_client_fails(checker: Any, tmp_path: Path) -> None:
    _models_dir(tmp_path, TYPED_MODELS)
    client = _client_file(
        tmp_path,
        """\
        class ThingsClient:
            def get_thing(self, thing_id: str) -> dict:
                return {}
        """,
    )
    report = checker.Report()
    models = checker.collect_models(tmp_path / "automation" / "api" / "models")
    checker.check_clients([client], models, report)
    assert any("raw dict" in p for p in report.problems)


def test_dict_generic_return_fails(checker: Any, tmp_path: Path) -> None:
    _models_dir(tmp_path, TYPED_MODELS)
    client = _client_file(
        tmp_path,
        """\
        from typing import Any

        class ThingsClient:
            def get_thing(self, thing_id: str) -> dict[str, Any]:
                return {}
        """,
    )
    report = checker.Report()
    models = checker.collect_models(tmp_path / "automation" / "api" / "models")
    checker.check_clients([client], models, report)
    assert any("raw dict" in p for p in report.problems)


def test_unannotated_public_method_fails(checker: Any, tmp_path: Path) -> None:
    _models_dir(tmp_path, TYPED_MODELS)
    client = _client_file(
        tmp_path,
        """\
        class ThingsClient:
            def get_thing(self, thing_id: str):
                return None
        """,
    )
    report = checker.Report()
    models = checker.collect_models(tmp_path / "automation" / "api" / "models")
    checker.check_clients([client], models, report)
    assert any("no return annotation" in p for p in report.problems)


def test_unknown_return_model_fails(checker: Any, tmp_path: Path) -> None:
    _models_dir(tmp_path, TYPED_MODELS)
    client = _client_file(
        tmp_path,
        """\
        class ThingsClient:
            def get_thing(self, thing_id: str) -> ThingReply:
                return None
        """,
    )
    report = checker.Report()
    models = checker.collect_models(tmp_path / "automation" / "api" / "models")
    checker.check_clients([client], models, report)
    assert any("'ThingReply' which is not a model" in p for p in report.problems)


def test_non_client_fixture_helpers_are_outside_client_contract(
    checker: Any, tmp_path: Path
) -> None:
    """conftest/tests 中的 dict 夹具不是传输客户端，不应被误报。"""
    helper = tmp_path / "automation" / "api" / "conftest.py"
    helper.parent.mkdir(parents=True)
    helper.write_text(
        "def seed_state() -> dict[str, str]:\n    return {}\n",
        encoding="utf-8",
    )
    report = checker.Report()
    checker.check_clients([helper], {}, report)
    assert report.problems == []


def test_unknown_field_against_spec_fails(checker: Any, tmp_path: Path) -> None:
    _models_dir(
        tmp_path,
        """\
        from pydantic import BaseModel

        class ThingResponse(BaseModel):
            id: str
            label: str
            price_with_vat: float
        """,
    )
    spec = _spec(
        **{
            "ThingResponse": {
                "type": "object",
                "required": ["id", "label"],
                "properties": {"id": {"type": "string"}, "label": {"type": "string"}},
            }
        }
    )
    report = checker.Report()
    checker.check_models_against_spec(tmp_path / "automation" / "api" / "models", spec, report)
    assert any(
        "'price_with_vat'" in p and "absent from the normalized source schema" in p
        for p in report.problems
    )


def test_spec_conformant_fields_pass(checker: Any, tmp_path: Path) -> None:
    _models_dir(tmp_path, TYPED_MODELS)
    spec = _spec(
        **{
            "ThingResponse": {
                "type": "object",
                "required": ["id", "label"],
                "properties": {"id": {"type": "string"}, "label": {"type": "string"}},
            }
        }
    )
    report = checker.Report()
    checker.check_models_against_spec(tmp_path / "automation" / "api" / "models", spec, report)
    assert report.problems == []


def test_model_without_matching_schema_is_skipped(checker: Any, tmp_path: Path) -> None:
    _models_dir(tmp_path, TYPED_MODELS)
    report = checker.Report()
    checker.check_models_against_spec(tmp_path / "automation" / "api" / "models", _spec(), report)
    assert report.problems == []


def test_cli_end_to_end_with_spec(checker: Any, tmp_path: Path) -> None:
    _models_dir(tmp_path, TYPED_MODELS)
    client = _client_file(tmp_path, TYPED_CLIENT)
    spec_path = tmp_path / "iterations" / "2026-08-api-cov" / "api" / "spec.normalized.yaml"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(
        yaml.safe_dump(
            _spec(
                **{
                    "ThingResponse": {
                        "type": "object",
                        "properties": {"id": {"type": "string"}, "label": {"type": "string"}},
                    }
                }
            ),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    assert checker.main([str(client), "--spec", str(spec_path)]) == 0
