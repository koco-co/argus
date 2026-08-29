"""只读 GitHub Issues 参考连接器。"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx  # pyright: ignore[reportMissingImports]

from .contracts import (  # pyright: ignore[reportMissingImports]
    PluginContext,
    PluginManifest,
    SourceEnvelope,
    SourceError,
)
from .security import (  # pyright: ignore[reportMissingImports]
    SourceSecurityError,
    contains_secret,
    read_limited_response,
    validate_public_url,
)

_REPOSITORY = re.compile(r"^[^/\s]+/[^/\s]+$")
_MAX_PAGES = 10


class GitHubIssuesConnector:
    """读取 issues 作为不可信需求来源，不创建/修改 issue。"""

    manifest = PluginManifest(
        name="github-issues",
        version="0.2.0",
        source_types=["github-issues"],
        capabilities=["requirements", "issues"],
    )

    def __init__(
        self,
        client: httpx.Client | None = None,
        api_url: str = "https://api.github.com",
    ) -> None:
        self._client = client
        self._api_url = api_url.rstrip("/")
        if client is None:
            self._validate_api_url()

    def _validate_api_url(self) -> None:
        from urllib.parse import urlsplit

        try:
            parts = urlsplit(self._api_url)
        except ValueError as exc:
            raise ValueError("GitHub API URL is malformed") from exc
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise ValueError("GitHub API URL must be an HTTPS host without credentials")
        if parts.query or parts.fragment:
            raise ValueError("GitHub API URL must not contain query or fragment")

    def fetch(self, source_ref: str, *, context: PluginContext) -> SourceEnvelope:
        fetched_at = datetime.now(UTC)
        try:
            repository = self._repository(source_ref)
            token = context.credentials.get("token")
            if not token:
                raise ValueError("GitHub token is required")
            issues = self._fetch_issues(repository, token, context)
            content = {"repository": repository, "issues": issues}
            if contains_secret(content, context):
                raise ValueError("source document contains credential-shaped data")
            return SourceEnvelope(
                source_type="github-issues",
                source_ref=source_ref,
                fetched_at=fetched_at,
                content=content,
            )
        except (SourceSecurityError, ValueError, TypeError, httpx.HTTPError):
            return SourceEnvelope(
                source_type="github-issues",
                source_ref=source_ref,
                fetched_at=fetched_at,
                error=SourceError(
                    code="source_unavailable",
                    message="GitHub Issues 来源不可用或未通过安全校验",
                ),
            )

    @staticmethod
    def _repository(source_ref: str) -> str:
        repository = source_ref.removeprefix("https://github.com/").strip("/")
        if not _REPOSITORY.fullmatch(repository):
            raise ValueError("source_ref must be an owner/repository")
        return repository

    def _fetch_issues(
        self,
        repository: str,
        token: str,
        context: PluginContext,
    ) -> list[dict[str, Any]]:
        if self._client is None:
            validate_public_url(self._api_url)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._client is not None:
            client = self._client
            close = False
        else:
            client = httpx.Client(
                base_url=self._api_url,
                headers=headers,
                timeout=httpx.Timeout(
                    connect=context.connect_timeout_seconds,
                    read=context.read_timeout_seconds,
                    write=context.read_timeout_seconds,
                    pool=context.connect_timeout_seconds,
                ),
                trust_env=False,
            )
            close = True
        try:
            result: list[dict[str, Any]] = []
            consumed_bytes = 0
            for page in range(1, _MAX_PAGES + 1):
                with client.stream(
                    "GET",
                    f"/repos/{repository}/issues",
                    headers=headers,
                    params={"state": "all", "per_page": 100, "page": page},
                ) as response:
                    response.raise_for_status()
                    remaining = context.max_bytes - consumed_bytes
                    if remaining <= 0:
                        raise SourceSecurityError("source response exceeds size limit")
                    payload_bytes = read_limited_response(response, remaining)
                consumed_bytes += len(payload_bytes)
                try:
                    payload = json.loads(payload_bytes)
                except (TypeError, ValueError, UnicodeDecodeError) as exc:
                    raise ValueError("GitHub Issues response is not JSON") from exc
                if not isinstance(payload, list):
                    raise ValueError("GitHub Issues response must be a list")
                for issue in payload:
                    if isinstance(issue, dict) and "pull_request" not in issue:
                        result.append(issue)
                if len(payload) < 100 or len(result) >= 1000:
                    break
            return result[:1000]
        finally:
            if close:
                client.close()
