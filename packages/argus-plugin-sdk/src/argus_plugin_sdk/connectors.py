"""v2 内置的只读 OpenAPI 参考连接器。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx  # pyright: ignore[reportMissingImports]
import yaml

from .contracts import (  # pyright: ignore[reportMissingImports]
    PluginContext,
    PluginManifest,
    SourceEnvelope,
    SourceError,
)
from .security import (  # pyright: ignore[reportMissingImports]
    SourceSecurityError,
    contains_secret,
    next_public_url,
    read_limited_response,
    validate_public_url,
)

_MAX_REDIRECTS = 3


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
        except (SourceSecurityError, ValueError, TypeError, yaml.YAMLError, httpx.HTTPError):
            return SourceEnvelope(
                source_type="openapi",
                source_ref=source_ref,
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
        if self._client is not None:
            return self._request_document(self._client, source_ref, headers, context)
        with httpx.Client(
            timeout=timeout,
            headers=headers,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            current = source_ref
            for _ in range(_MAX_REDIRECTS + 1):
                document, location = self._request_once(client, current, context.max_bytes)
                if location is None:
                    return document
                current = next_public_url(current, location)
        raise SourceSecurityError("too many redirects")

    def _request_document(
        self,
        client: httpx.Client,
        source_ref: str,
        headers: dict[str, str],
        context: PluginContext,
    ) -> dict[str, Any]:
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
            current = next_public_url(current, location)
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
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise SourceSecurityError("redirect has no location")
                return {}, location
            response.raise_for_status()
            content = read_limited_response(response, max_bytes)
        try:
            parsed = json.loads(content)
        except (ValueError, UnicodeDecodeError):
            parsed = yaml.safe_load(content)
        if not isinstance(parsed, dict):
            raise ValueError("source document must be an object")
        return parsed, None
