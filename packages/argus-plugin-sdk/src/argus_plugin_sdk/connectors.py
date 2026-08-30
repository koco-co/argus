"""v2 内置的只读 OpenAPI 参考连接器。"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

import httpx  # pyright: ignore[reportMissingImports]
import yaml  # pyright: ignore[reportMissingModuleSource]
from yaml.events import AliasEvent  # pyright: ignore[reportMissingModuleSource]
from yaml.nodes import MappingNode  # pyright: ignore[reportMissingModuleSource]

from .contracts import (  # pyright: ignore[reportMissingImports]
    PluginContext,
    PluginManifest,
    SourceEnvelope,
    SourceError,
)
from .security import (  # pyright: ignore[reportMissingImports]
    SourceSecurityError,
    contains_secret,
    load_json,
    next_public_url,
    read_limited_response,
    validate_public_url,
    validate_response_peer,
)

_MAX_REDIRECTS = 3
_MAX_DOCUMENT_DEPTH = 64


class _StrictSafeLoader(yaml.SafeLoader):
    """Reject YAML aliases and duplicate keys at the untrusted-source boundary."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(AliasEvent):
            self.get_event()
            raise SourceSecurityError("source YAML aliases are not supported")
        return super().compose_node(parent, index)

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as exc:
                raise SourceSecurityError("source document object keys must be scalar") from exc
            if duplicate:
                raise SourceSecurityError("source document contains duplicate keys")
            try:
                mapping[key] = self.construct_object(value_node, deep=deep)
            except TypeError as exc:
                raise SourceSecurityError("source document object keys must be scalar") from exc
        return mapping


def _validate_document_shape(value: Any, depth: int = 0) -> None:
    if depth > _MAX_DOCUMENT_DEPTH:
        raise SourceSecurityError("source document is nested too deeply")
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise SourceSecurityError("source document object keys must be strings")
        for item in value.values():
            _validate_document_shape(item, depth + 1)
        return
    if isinstance(value, list):
        for item in value:
            _validate_document_shape(item, depth + 1)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise SourceSecurityError("source document contains a non-finite number")
    if value is not None and not isinstance(value, (bool, int, float, str)):
        raise SourceSecurityError("source document contains an unsupported YAML value")


def _load_strict_yaml(content: bytes) -> Any:
    loader = _StrictSafeLoader(content)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def _parse_document(content: bytes) -> dict[str, Any]:
    try:
        parsed = load_json(content)
    except SourceSecurityError:
        raise
    except (ValueError, UnicodeDecodeError):
        parsed = _load_strict_yaml(content)
    if not isinstance(parsed, dict):
        raise ValueError("source document must be an object")
    _validate_document_shape(parsed)
    return parsed


class OpenAPIReferenceConnector:
    """抓取 OpenAPI/Swagger 文档；只返回 source envelope，不写项目目录。"""

    manifest = PluginManifest(
        name="openapi-reference",
        version="0.2.0",
        source_types=["openapi"],
        capabilities=["api", "openapi"],
    )

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, source_ref: str, *, context: PluginContext) -> SourceEnvelope:
        fetched_at = datetime.now(UTC)
        try:
            document = self._fetch_document(source_ref, context)
            if not isinstance(document, dict) or not (
                isinstance(document.get("openapi"), str) or isinstance(document.get("swagger"), str)
            ):
                raise ValueError("source is not an OpenAPI or Swagger document")
            if contains_secret(document, context):
                raise ValueError("source document contains credential-shaped data")
            return SourceEnvelope(
                source_type="openapi",
                source_ref=source_ref,
                fetched_at=fetched_at,
                content=document,
            )
        except Exception:  # noqa: BLE001 - connector failures become stable envelopes
            return SourceEnvelope(
                source_type="openapi",
                # Never persist an attacker-controlled URL on an error path.
                source_ref=None,
                fetched_at=fetched_at,
                error=SourceError(
                    code="source_unavailable",
                    message="OpenAPI 来源不可用或未通过安全校验",
                ),
            )

    def _fetch_document(self, source_ref: str, context: PluginContext) -> dict[str, Any]:
        validate_public_url(source_ref)
        headers: dict[str, str] = {}
        bearer = context.credentials.get("bearer_token")
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        timeout = httpx.Timeout(
            connect=context.connect_timeout_seconds,
            read=context.read_timeout_seconds,
            write=context.read_timeout_seconds,
            pool=context.connect_timeout_seconds,
        )
        candidate_transport = getattr(self._client, "_transport", None) if self._client else None
        # Only deterministic MockTransport injection is accepted.  Reusing a
        # preconfigured HTTP transport could carry verify=False, proxy, cookie,
        # or other settings that bypass this connector's policy.
        transport = (
            candidate_transport if isinstance(candidate_transport, httpx.MockTransport) else None
        )
        with httpx.Client(
            transport=transport,
            timeout=timeout,
            headers=headers,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            current = source_ref
            for _ in range(_MAX_REDIRECTS + 1):
                document, location = self._request_once(
                    client,
                    current,
                    context.max_bytes,
                    headers=headers,
                )
                if location is None:
                    return document
                current = next_public_url(current, location, same_origin_as=source_ref)
        raise SourceSecurityError("too many redirects")

    @staticmethod
    def _request_once(
        client: httpx.Client,
        source_ref: str,
        max_bytes: int,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        with client.stream(
            "GET",
            source_ref,
            headers=headers,
            follow_redirects=False,
        ) as response:
            validate_response_peer(response)
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise SourceSecurityError("redirect has no location")
                return {}, location
            response.raise_for_status()
            content = read_limited_response(response, max_bytes)
        return _parse_document(content), None
