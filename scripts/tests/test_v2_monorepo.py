"""Argus 0.2 core、SDK 与 Medusa adapter 的契约回归。"""

from __future__ import annotations

import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx  # pyright: ignore[reportMissingImports]
import pytest  # pyright: ignore[reportMissingImports]
import yaml  # pyright: ignore[reportMissingModuleSource]
from argus_core import (  # pyright: ignore[reportMissingImports]
    Actor,
    Approval,
    ApprovalAction,
    ApprovalError,
    ApprovalStage,
    DelegationGrant,
    IterationDocument,
    IterationStore,
    MergeFact,
    ParseError,
    PromotionError,
    StateError,
    StoreError,
    Surface,
    VerifiedMergeFact,
    Workstream,
    WorkstreamStatus,
    iteration_schema,
    load_json,
    load_verified_merge_fact,
    load_yaml,
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
    SourceError,
)
from argus_plugin_sdk.security import (  # pyright: ignore[reportMissingImports]
    contains_secret,
    validate_response_peer,
)
from argus_plugin_sdk.security import (  # pyright: ignore[reportMissingImports]
    load_json as load_source_json,
)
from jsonschema import (  # pyright: ignore[reportMissingModuleSource]
    Draft202012Validator,
    FormatChecker,
)
from pydantic import ValidationError  # pyright: ignore[reportMissingImports]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _verified_fact(tmp_path: Path, fact: MergeFact, monkeypatch) -> VerifiedMergeFact:
    key = "fixture-verifier-key"
    monkeypatch.setenv("ARGUS_MERGE_VERIFIER_KEY", key)
    payload = fact.model_dump(mode="json", exclude_none=True)
    payload["verifier"] = "github-api"
    payload["verification_signature"] = hmac.new(
        key.encode(),
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    path = tmp_path / "verified-merge.json"
    path.write_text(json.dumps({"verifier": "github-api", "fact": payload}), encoding="utf-8")
    return load_verified_merge_fact(path)


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


def test_source_envelope_runtime_dump_matches_static_one_of_schema() -> None:
    schema_path = (
        Path(__file__).parents[2]
        / "packages/argus-plugin-sdk/src/argus_plugin_sdk/schemas/source_envelope.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    timestamp = datetime(2026, 8, 29, tzinfo=UTC)
    for envelope in (
        SourceEnvelope(source_type="fixture", fetched_at=timestamp, content={"ok": True}),
        SourceEnvelope(
            source_type="fixture",
            fetched_at=timestamp,
            error=SourceError(code="failed", message="no"),
        ),
    ):
        assert not list(validator.iter_errors(envelope.model_dump(mode="json")))
        assert ("content" in envelope.model_dump()) != ("error" in envelope.model_dump())


def test_control_plane_parser_rejects_ambiguous_untrusted_documents() -> None:
    with pytest.raises(ParseError, match="duplicate"):
        load_json(b'{"status":"created","status":"active"}')
    with pytest.raises(ParseError, match="non-finite"):
        load_json(b'{"value":NaN}')
    with pytest.raises(ParseError, match="aliases"):
        load_yaml(b"fact: &fact {}\ncopy: *fact\n")
    with pytest.raises(ValueError, match="non-finite"):
        load_source_json(b'{"value":1e999}')
    with pytest.raises(ParseError, match="duplicate"):
        load_yaml("name: one\nname: two\n")
    with pytest.raises(ParseError, match="non-finite"):
        load_yaml("value: .nan\n")
    with pytest.raises(ParseError, match="too deeply"):
        load_yaml("[" * 65 + "0" + "]" * 65)
    with pytest.raises(ParseError, match="size limit"):
        load_json(b"{}", max_bytes=1)
    with pytest.raises(ParseError, match="unsupported"):
        load_yaml("value: !!binary YQ==\n")


def test_source_errors_do_not_echo_credential_bearing_refs(monkeypatch) -> None:
    monkeypatch.setattr(
        "argus_plugin_sdk.security.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    envelope = OpenAPIReferenceConnector().fetch(
        "https://user:password@example.com/openapi.json",
        context=PluginContext(),
    )
    assert envelope.source_ref is None
    assert "password" not in repr(envelope.model_dump())


def test_secret_detection_covers_nested_payloads_and_sensitive_urls() -> None:
    assert contains_secret({"nested": [{"apiKey": "secret"}]})
    assert contains_secret({"api_key": "secret"})
    assert contains_secret({"url": "https://example.test/?access_token=secret"})
    assert not contains_secret({"description": "authentication is required"})


def test_dns_rebinding_to_a_private_peer_is_rejected() -> None:
    class Stream:
        def get_extra_info(self, name: str):
            return ("10.0.0.7", 443) if name == "server_addr" else None

    class Response:
        extensions = {"network_stream": Stream()}

    with pytest.raises(ValueError, match="public"):
        validate_response_peer(Response())


def test_github_repository_and_api_url_are_canonicalized() -> None:
    for value in ("owner/repo?token=x", "owner/repo#frag", "owner/repo\\evil"):
        with pytest.raises(ValueError):
            GitHubIssuesConnector._repository(value)
    for api_url in (
        "https://api.github.com/v3",
        "https://api.github.com:444",
        "https://evil.example.com",
    ):
        with pytest.raises(ValueError):
            GitHubIssuesConnector(api_url=api_url)
    with pytest.raises(ValueError):
        GitHubIssuesConnector(
            httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
            api_url="https://user:password@example.com",
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


def test_core_metadata_rejects_credential_shaped_values() -> None:
    with pytest.raises(ValidationError, match="credential-shaped"):
        Workstream(
            id="web-stream",
            surface=Surface.WEB,
            metadata={"apiKey": "secret"},
        )
    with pytest.raises(ValidationError, match="credential-shaped"):
        Workstream(
            id="web-stream",
            surface=Surface.WEB,
            metadata={"private_key": "secret"},
        )
    with pytest.raises(ValidationError, match="credential-shaped"):
        IterationDocument(
            iteration_id="iteration-v2",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            workstreams=[Workstream(id="web-stream", surface=Surface.WEB)],
            metadata={"source": {"url": "https://user:pass@example.test"}},
        )


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


def test_iteration_document_replays_events_and_rejects_revision_drift(tmp_path) -> None:
    store = _make_store(tmp_path, Surface.WEB)
    payload = store.load("iteration-v2").model_dump(mode="json")
    payload["status"] = "accepted"
    payload["workstreams"][0]["status"] = "passed"
    with pytest.raises(ValidationError, match="event chain"):
        IterationDocument.model_validate(payload)

    payload = store.load("iteration-v2").model_dump(mode="json")
    payload["approvals"] = [
        _approval(
            "web-stream",
            ApprovalStage.PROMOTION,
            ApprovalAction.APPROVED,
        ).model_dump(mode="json")
    ]
    payload["updated_at"] = datetime.now(UTC).isoformat()
    with pytest.raises(ValidationError, match="promotion approval"):
        IterationDocument.model_validate(payload)

    payload = store.load("iteration-v2").model_dump(mode="json")
    payload["status"] = "active"
    payload["workstreams"][0]["status"] = "requirements_accepted"
    payload["workstreams"][0]["revision"] = 1
    payload["events"] = [
        {
            "id": "event-0001",
            "workstream_id": "web-stream",
            "from_status": "created",
            "to_status": "requirements_accepted",
            "actor": "agent",
            "recorded_at": datetime.now(UTC).isoformat(),
        }
    ]
    with pytest.raises(ValidationError, match="latest valid requirements approval"):
        IterationDocument.model_validate(payload)

    payload = store.load("iteration-v2").model_dump(mode="json")
    payload["status"] = "blocked"
    payload["workstreams"][0]["status"] = "blocked"
    payload["workstreams"][0]["revision"] = 1
    payload["events"] = [
        {
            "id": "event-0001",
            "workstream_id": "web-stream",
            "from_status": "created",
            "to_status": "blocked",
            "actor": "agent",
            "recorded_at": datetime.now(UTC).isoformat(),
            "reason": "fixture",
        }
    ]
    with pytest.raises(ValidationError, match="illegal created -> blocked"):
        IterationDocument.model_validate(payload)

    store = _make_store(tmp_path / "second", Surface.WEB)
    # A valid event chain is then made inconsistent by changing its event edge.
    store.approve("iteration-v2", _approval("web-stream", ApprovalStage.REQUIREMENTS))
    store.transition("iteration-v2", "web-stream", "requirements_accepted", "user")
    payload = store.load("iteration-v2").model_dump(mode="json")
    payload["events"][0]["from_status"] = "design_pending"
    with pytest.raises(ValidationError, match="event chain"):
        IterationDocument.model_validate(payload)
    payload = store.load("iteration-v2").model_dump(mode="json")
    payload["workstreams"][0]["revision"] = 0
    with pytest.raises(ValidationError, match="revision"):
        IterationDocument.model_validate(payload)


def test_approvals_are_limited_to_current_phase_and_reject_future_time(tmp_path) -> None:
    store = _make_store(tmp_path, Surface.WEB)
    with pytest.raises(ApprovalError, match="accepted iteration"):
        store.approve(
            "iteration-v2",
            _approval(
                "web-stream",
                ApprovalStage.PROMOTION,
                action=ApprovalAction.APPROVED,
            ),
        )
    with pytest.raises(ValidationError, match="future"):
        _approval(
            "web-stream",
            ApprovalStage.REQUIREMENTS,
            recorded_at=datetime(2099, 1, 1, tzinfo=UTC),
        )


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


def test_latest_rejection_invalidates_an_earlier_acceptance(tmp_path) -> None:
    store = _make_store(tmp_path, Surface.WEB)
    store.approve("iteration-v2", _approval("web-stream", ApprovalStage.REQUIREMENTS))
    store.approve(
        "iteration-v2",
        _approval(
            "web-stream",
            ApprovalStage.REQUIREMENTS,
            ApprovalAction.REJECTED,
            number=2,
        ),
    )
    with pytest.raises(StateError, match="explicit user decision"):
        store.transition("iteration-v2", "web-stream", "requirements_accepted", "user")


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
    with pytest.raises(StateError, match="illegal transition"):
        store.transition("iteration-v2", "web-stream", "blocked", "agent", "源不可用")

    # Reach execution before entering the terminal blocked state.
    store.approve("iteration-v2", _approval("web-stream", ApprovalStage.REQUIREMENTS))
    store.transition("iteration-v2", "web-stream", "requirements_accepted", "user")
    store.transition("iteration-v2", "web-stream", "design_pending", "agent")
    store.approve("iteration-v2", _approval("web-stream", ApprovalStage.DESIGN, number=2))
    store.transition("iteration-v2", "web-stream", "automation_pending", "agent")
    store.transition("iteration-v2", "web-stream", "ready", "agent")
    store.approve(
        "iteration-v2",
        _approval(
            "web-stream",
            ApprovalStage.ENVIRONMENT,
            ApprovalAction.PROVIDED,
            number=3,
        ),
    )
    store.transition("iteration-v2", "web-stream", "executing", "agent")
    store.transition("iteration-v2", "web-stream", "blocked", "agent", "源不可用")
    with pytest.raises(StateError, match="explicit user"):
        store.transition("iteration-v2", "web-stream", "created", "agent")
    store.transition("iteration-v2", "web-stream", "created", "user", "用户重新开始")
    document = store.load("iteration-v2")
    assert document.status.value == "created"
    assert document.workstreams[0].status == WorkstreamStatus.CREATED
    with pytest.raises(StateError, match="current lifecycle window"):
        store.transition("iteration-v2", "web-stream", "requirements_accepted", "user")
    store.approve(
        "iteration-v2",
        _approval("web-stream", ApprovalStage.REQUIREMENTS, number=4),
    )
    store.transition("iteration-v2", "web-stream", "requirements_accepted", "user")
    assert (
        store.load("iteration-v2").workstreams[0].status == WorkstreamStatus.REQUIREMENTS_ACCEPTED
    )


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
            recorded_at=datetime.now(UTC),
            delegation_id="delegation-local-review",
            note="已审查页面对象契约",
        ),
    )
    store.transition("iteration-v2", "web-stream", "automation_pending", "agent")
    assert store.load("iteration-v2").workstreams[0].status == WorkstreamStatus.AUTOMATION_PENDING


def test_api_lifecycle_and_promotion_require_external_fact(tmp_path, monkeypatch) -> None:
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
            recorded_at=datetime.now(UTC),
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
            recorded_at=datetime.now(UTC),
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
    fact_time = datetime.now(UTC)
    fact = MergeFact(
        workstream_id="api-stream",
        repository="example/project",
        pull_request=42,
        merge_sha="a" * 40,
        merged_at=fact_time,
        source_url="https://github.com/example/project/pull/42",
        verified_at=fact_time,
    )
    with pytest.raises(PromotionError, match="independent verifier"):
        promote(store, "iteration-v2", "api-stream", cast(Any, fact))
    verified = _verified_fact(tmp_path, fact, monkeypatch)
    snapshot = verified.fact
    snapshot.merge_sha = "b" * 40
    assert verified.fact.merge_sha == "a" * 40
    with pytest.raises(PromotionError, match="immutable"):
        verified.verifier = "forged"  # type: ignore[misc]
    with pytest.raises(PromotionError, match="execution"):
        promote(store, "iteration-v2", "api-stream", verified)
    store.approve(
        "iteration-v2",
        _approval("api-stream", ApprovalStage.EXECUTION, number=5),
    )
    store.approve(
        "iteration-v2",
        _approval(
            "api-stream",
            ApprovalStage.PROMOTION,
            ApprovalAction.APPROVED,
            number=6,
        ),
    )
    promote(
        store,
        "iteration-v2",
        "api-stream",
        verified,
    )
    document = store.load("iteration-v2")
    assert document.status.value == "promoted"
    assert document.promotions[0].merge_sha == "a" * 40

    persisted = store.path_for("iteration-v2")
    raw = yaml.safe_load(persisted.read_text(encoding="utf-8"))
    raw["promotions"][0]["merge_sha"] = "b" * 40
    persisted.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(StoreError, match="invalid v2 iteration"):
        store.load("iteration-v2")


def test_promotion_requires_an_explicit_external_verifier_envelope(tmp_path) -> None:
    missing = tmp_path / "missing.yaml"
    missing.write_text("fact: {}\n", encoding="utf-8")
    with pytest.raises(PromotionError, match="independent verifier"):
        load_verified_merge_fact(missing)

    forged = tmp_path / "forged.json"
    forged.write_text(
        json.dumps(
            {
                "verifier": "just-a-string",
                "fact": {
                    "workstream_id": "api-stream",
                    "repository": "example/project",
                    "pull_request": 42,
                    "merge_sha": "a" * 40,
                    "merged_at": "2026-08-29T00:00:00Z",
                    "source_url": "https://github.com/example/project/pull/42",
                    "verified_at": "2026-08-29T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PromotionError, match="bind verifier identity"):
        load_verified_merge_fact(forged)


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
        assert request.headers["authorization"] == "Bearer bearer-secret"
        return httpx.Response(200, json={"openapi": "3.0.3", "paths": {}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = OpenAPIReferenceConnector(client).fetch(
        "https://example.com/openapi.json",
        context=PluginContext(
            max_bytes=2048,
            credentials={"bearer_token": "bearer-secret"},
        ),
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


@pytest.mark.parametrize(
    "payload",
    [
        b'{"openapi":"3.0.3","openapi":"3.0.2","paths":{}}',
        b"openapi: &version 3.0.3\npaths: *version\n",
    ],
)
def test_openapi_connector_rejects_ambiguous_documents(monkeypatch, payload: bytes) -> None:
    monkeypatch.setattr(
        "argus_plugin_sdk.security.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload))
    )
    result = OpenAPIReferenceConnector(client).fetch(
        "https://example.com/openapi.json",
        context=PluginContext(),
    )
    client.close()
    assert result.content is None
    assert result.error is not None


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
