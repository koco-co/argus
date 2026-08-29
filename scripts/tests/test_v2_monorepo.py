"""Argus 0.2 core、SDK 与 Medusa adapter 的契约回归。"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx  # pyright: ignore[reportMissingImports]
import pytest  # pyright: ignore[reportMissingImports]
from argus_core import (  # pyright: ignore[reportMissingImports]
    Actor,
    Approval,
    ApprovalAction,
    ApprovalStage,
    DelegationGrant,
    IterationDocument,
    IterationStore,
    MergeFact,
    PromotionError,
    StateError,
    Surface,
    Workstream,
    WorkstreamStatus,
    iteration_schema,
    promote,
)
from argus_medusa import MedusaAdapter, MedusaConfig  # pyright: ignore[reportMissingImports]
from argus_plugin_sdk import (  # pyright: ignore[reportMissingImports]
    GitHubIssuesConnector,
    OpenAPIReferenceConnector,
    PluginContext,
    PluginManifest,
    PluginRegistry,
    SourceEnvelope,
)
from jsonschema import Draft202012Validator, FormatChecker  # pyright: ignore[reportMissingImports]
from pydantic import ValidationError  # pyright: ignore[reportMissingImports]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _approval(
    workstream_id: str,
    stage: ApprovalStage,
    action: ApprovalAction = ApprovalAction.ACCEPTED,
    actor: Actor = Actor.USER,
    number: int = 1,
    *,
    artifact: str = "artifact.yaml",
    recorded_at: datetime | None = None,
    delegation_id: str | None = None,
    note: str | None = None,
) -> Approval:
    return Approval(
        id=f"approval-{number:04d}",
        workstream_id=workstream_id,
        stage=stage,
        action=action,
        actor=actor,
        artifact=artifact,
        artifact_sha256=_sha(artifact),
        recorded_at=recorded_at or datetime.now(UTC),
        delegation_id=delegation_id,
        note=note,
    )


def _grant(now: datetime | None = None) -> DelegationGrant:
    start = now or datetime.now(UTC)
    basis = "用户明确授权本 iteration 的后续本地审查"
    return DelegationGrant(
        id="delegation-local-review",
        basis=basis,
        basis_sha256=_sha(basis),
        scope=[ApprovalStage.DESIGN, ApprovalStage.MAPPING, ApprovalStage.CASES],
        granted_at=start - timedelta(minutes=1),
        expires_at=start + timedelta(hours=1),
    )


def _make_store(tmp_path, *surfaces: Surface) -> IterationStore:
    store = IterationStore(tmp_path)
    store.create(
        "iteration-v2",
        [Workstream(id=f"{surface.value}-stream", surface=surface) for surface in surfaces],
    )
    return store


def test_static_sdk_schema_matches_exactly_one_envelope_result() -> None:
    schema_path = (
        Path(__file__).parents[2]
        / "packages/argus-plugin-sdk/src/argus_plugin_sdk/schemas/source_envelope.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    base = {
        "schema_version": "2.0",
        "source_type": "fixture",
        "fetched_at": "2026-08-29T00:00:00Z",
    }
    assert not list(validator.iter_errors({**base, "content": {"ok": True}}))
    assert not list(validator.iter_errors({**base, "error": {"code": "x", "message": "failed"}}))
    both = {**base, "content": {}, "error": {"code": "x", "message": "x"}}
    assert list(validator.iter_errors(both))
    assert list(validator.iter_errors(base))


def test_source_envelope_rejects_naive_timestamps() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        SourceEnvelope(
            source_type="fixture",
            fetched_at=datetime(2026, 8, 29),
            content={"ok": True},
        )


def test_static_core_schema_is_generated_from_runtime_contract() -> None:
    schema_path = (
        Path(__file__).parents[2]
        / "packages/argus-core/src/argus_core/schemas/iteration.schema.json"
    )
    assert json.loads(schema_path.read_text(encoding="utf-8")) == iteration_schema()


def test_runtime_schema_is_strict_and_exportable() -> None:
    schema = iteration_schema()
    assert schema["properties"]["schema_version"]["const"] == "2.0"
    assert "Workstream" in schema["$defs"]
    with pytest.raises(ValidationError):
        Workstream.model_validate({"id": "web-stream", "surface": "web", "unexpected": "nope"})


def test_core_document_rejects_unknown_references_and_bad_aggregate(tmp_path) -> None:
    store = _make_store(tmp_path, Surface.WEB)
    payload = store.load("iteration-v2").model_dump(mode="json")
    payload["approvals"] = [
        _approval("unknown-stream", ApprovalStage.DESIGN).model_dump(mode="json")
    ]
    with pytest.raises(ValidationError, match="unknown workstream"):
        IterationDocument.model_validate(payload)

    payload = store.load("iteration-v2").model_dump(mode="json")
    payload["status"] = "active"
    with pytest.raises(ValidationError, match="does not match aggregate"):
        IterationDocument.model_validate(payload)


def test_store_serializes_atomic_transactions_and_preserves_concurrent_updates(tmp_path) -> None:
    store = _make_store(tmp_path, Surface.WEB)

    def write_value(index: int) -> None:
        store.transact(
            "iteration-v2",
            lambda document: document.metadata.__setitem__(f"worker-{index}", "done"),
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write_value, range(8)))
    document = store.load("iteration-v2")
    assert len(document.metadata) == 8
    assert document.revision == 8
    assert document.workstreams[0].status == WorkstreamStatus.CREATED


def test_requirements_acceptance_is_user_only_and_rejection_is_not_persisted(tmp_path) -> None:
    store = _make_store(tmp_path, Surface.WEB)
    path = store.path_for("iteration-v2")
    before = path.read_bytes()
    with pytest.raises(ValidationError):
        _approval(
            "web-stream",
            ApprovalStage.REQUIREMENTS,
            ApprovalAction.DELEGATED,
            Actor.AGENT,
            delegation_id="delegation-local-review",
            note="not permitted",
        )
    with pytest.raises(StateError, match="requires an approval"):
        store.transition("iteration-v2", "web-stream", "requirements_accepted", "user")
    assert path.read_bytes() == before


def test_blocked_workstream_can_only_be_reopened_by_user(tmp_path) -> None:
    store = _make_store(tmp_path, Surface.WEB)
    store.transition("iteration-v2", "web-stream", "blocked", "agent", "源不可用")
    with pytest.raises(StateError, match="explicit user"):
        store.transition("iteration-v2", "web-stream", "created", "agent")
    store.transition("iteration-v2", "web-stream", "created", "user", "用户重新开始")
    document = store.load("iteration-v2")
    assert document.status.value == "created"
    assert document.workstreams[0].status == WorkstreamStatus.CREATED


def test_web_workstream_requires_later_review_and_supports_delegated_review(tmp_path) -> None:
    store = _make_store(tmp_path, Surface.WEB)
    now = datetime.now(UTC)
    store.grant("iteration-v2", _grant(now))
    store.approve("iteration-v2", _approval("web-stream", ApprovalStage.REQUIREMENTS))
    store.transition("iteration-v2", "web-stream", "requirements_accepted", "user")
    store.transition("iteration-v2", "web-stream", "design_pending", "agent")
    with pytest.raises(StateError, match="design"):
        store.transition("iteration-v2", "web-stream", "automation_pending", "agent")
    store.approve(
        "iteration-v2",
        _approval(
            "web-stream",
            ApprovalStage.DESIGN,
            ApprovalAction.DELEGATED,
            Actor.AGENT,
            2,
            recorded_at=now,
            delegation_id="delegation-local-review",
            note="已审查页面对象契约",
        ),
    )
    store.transition("iteration-v2", "web-stream", "automation_pending", "agent")
    assert store.load("iteration-v2").workstreams[0].status == WorkstreamStatus.AUTOMATION_PENDING


def test_api_lifecycle_and_promotion_require_external_fact(tmp_path) -> None:
    store = _make_store(tmp_path, Surface.API)
    now = datetime.now(UTC)
    store.grant("iteration-v2", _grant(now))
    store.approve("iteration-v2", _approval("api-stream", ApprovalStage.REQUIREMENTS))
    store.transition("iteration-v2", "api-stream", "requirements_accepted", "user")
    store.transition("iteration-v2", "api-stream", "mapping_pending", "agent")
    store.approve(
        "iteration-v2",
        _approval(
            "api-stream",
            ApprovalStage.MAPPING,
            ApprovalAction.DELEGATED,
            Actor.AGENT,
            2,
            recorded_at=now,
            delegation_id="delegation-local-review",
            note="已审查 endpoint mapping",
        ),
    )
    store.transition("iteration-v2", "api-stream", "spec_pending", "agent")
    store.transition("iteration-v2", "api-stream", "cases_pending", "agent")
    store.approve(
        "iteration-v2",
        _approval(
            "api-stream",
            ApprovalStage.CASES,
            ApprovalAction.DELEGATED,
            Actor.AGENT,
            3,
            recorded_at=now,
            delegation_id="delegation-local-review",
            note="已审查 happy 与 negative cases",
        ),
    )
    store.transition("iteration-v2", "api-stream", "automation_pending", "agent")
    store.transition("iteration-v2", "api-stream", "ready", "agent")
    with pytest.raises(StateError, match="environment"):
        store.transition("iteration-v2", "api-stream", "executing", "agent")
    store.approve(
        "iteration-v2",
        _approval(
            "api-stream",
            ApprovalStage.ENVIRONMENT,
            ApprovalAction.PROVIDED,
            number=4,
        ),
    )
    store.transition("iteration-v2", "api-stream", "executing", "agent")
    store.transition("iteration-v2", "api-stream", "passed", "agent")
    fact = MergeFact(
        workstream_id="api-stream",
        repository="example/project",
        pull_request=42,
        merge_sha="a" * 40,
        merged_at=now,
        source_url="https://github.com/example/project/pull/42",
        verified_at=now,
    )
    with pytest.raises(PromotionError, match="promotion"):
        promote(store, "iteration-v2", "api-stream", fact)
    store.approve(
        "iteration-v2",
        _approval(
            "api-stream",
            ApprovalStage.PROMOTION,
            ApprovalAction.APPROVED,
            number=5,
        ),
    )
    promote(store, "iteration-v2", "api-stream", fact)
    document = store.load("iteration-v2")
    assert document.status.value == "promoted"
    assert document.promotions[0].merge_sha == "a" * 40


def test_plugin_registry_rejects_unknown_plugins_and_credential_payloads() -> None:
    class Plugin:
        manifest = PluginManifest(
            name="fixture-plugin",
            version="0.2.0",
            source_types=["fixture"],
            capabilities=["requirements"],
        )

        def fetch(self, source_ref: str, *, context: PluginContext) -> SourceEnvelope:
            del context
            return SourceEnvelope(
                source_type="fixture",
                source_ref=source_ref,
                fetched_at=datetime.now(UTC),
                content={"token": "leaked"},
            )

    registry = PluginRegistry()
    registry.register(Plugin())
    context = PluginContext(credentials={"token": "leaked"})
    result = registry.fetch("fixture-plugin", "fixture", context=context)
    assert result.error is not None
    assert "leaked" not in result.error.message
    with pytest.raises(ValueError, match="unknown plugin"):
        registry.get("missing")
    assert "leaked" not in repr(context)
    assert "credentials" not in context.model_dump()


def test_openapi_connector_is_stream_limited_and_returns_envelope(monkeypatch) -> None:
    monkeypatch.setattr(
        "argus_plugin_sdk.security.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, json={"openapi": "3.0.3", "paths": {}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = OpenAPIReferenceConnector(client).fetch(
        "https://example.com/openapi.json",
        context=PluginContext(max_bytes=2048),
    )
    client.close()
    assert result.content == {"openapi": "3.0.3", "paths": {}}
    assert result.error is None


def test_openapi_connector_converts_malformed_document_to_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "argus_plugin_sdk.security.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"openapi: [")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = OpenAPIReferenceConnector(client).fetch(
        "https://example.com/openapi.yaml",
        context=PluginContext(),
    )
    client.close()
    assert result.content is None
    assert result.error is not None
    assert result.error.code == "source_unavailable"


def test_openapi_connector_rejects_private_redirect_and_oversize_response(monkeypatch) -> None:
    monkeypatch.setattr(
        "argus_plugin_sdk.security.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )

    def redirect_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    client = httpx.Client(transport=httpx.MockTransport(redirect_handler))
    result = OpenAPIReferenceConnector(client).fetch(
        "https://example.com/openapi.json",
        context=PluginContext(),
    )
    client.close()
    assert result.error is not None

    def large_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{" + b"x" * 100 + b"}")

    client = httpx.Client(transport=httpx.MockTransport(large_handler))
    result = OpenAPIReferenceConnector(client).fetch(
        "https://example.com/openapi.json",
        context=PluginContext(max_bytes=10),
    )
    client.close()
    assert result.error is not None


def test_github_connector_filters_pull_requests_and_requires_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer gh-test"
        return httpx.Response(
            200,
            json=[
                {"number": 1, "title": "requirement", "body": "checkout"},
                {"number": 2, "title": "pr", "pull_request": {"url": "x"}},
            ],
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.github.com")
    connector = GitHubIssuesConnector(client)
    result = connector.fetch(
        "example/project",
        context=PluginContext(credentials={"token": "gh-test"}),
    )
    assert result.error is None
    assert result.content == {
        "repository": "example/project",
        "issues": [{"number": 1, "title": "requirement", "body": "checkout"}],
    }
    missing = connector.fetch("example/project", context=PluginContext())
    assert missing.error is not None
    client.close()


def test_medusa_adapter_keeps_web_and_api_url_boundaries() -> None:
    adapter = MedusaAdapter(
        MedusaConfig(
            storefront_url="http://localhost:8000/",
            store_api_url="http://localhost:9000",
            environment="local",
        )
    )
    assert adapter.web.url("/checkout") == "http://localhost:8000/checkout"
    assert adapter.api.url("/store/carts") == "http://localhost:9000/store/carts"
    assert {item.surface for item in adapter.workstreams()} == {Surface.WEB, Surface.API}
    with pytest.raises(ValueError):
        adapter.api.url("https://evil.test")
    with pytest.raises(ValidationError):
        MedusaConfig(
            storefront_url="http://user:password@example.test",
            store_api_url="http://localhost:9000",
            environment="local",
        )
