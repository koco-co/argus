"""来源连接器的网络和凭据边界。"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin, urlsplit

from .contracts import PluginContext  # pyright: ignore[reportMissingImports]


class SourceSecurityError(ValueError):
    """来源引用、重定向或载荷触碰安全边界。"""


_SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "access_token",
    "authorization",
    "cookie",
    "private_key",
}


def validate_public_url(source_ref: str) -> None:
    """拒绝凭据 URL 及解析到私有/回环/链路本地地址的来源。"""
    try:
        parts = urlsplit(source_ref)
    except ValueError as exc:
        raise SourceSecurityError("source URL is malformed") from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise SourceSecurityError("source URL must use http or https")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise SourceSecurityError("source URL must not contain credentials, query, or fragment")
    try:
        port = parts.port
    except ValueError as exc:
        raise SourceSecurityError("source URL is malformed") from exc
    try:
        addresses = socket.getaddrinfo(
            parts.hostname,
            port or (443 if parts.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except (OSError, ValueError) as exc:
        raise SourceSecurityError("source host cannot be resolved safely") from exc
    if not addresses:
        raise SourceSecurityError("source host has no address")
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address[4][0])
        except (IndexError, ValueError) as exc:
            raise SourceSecurityError("source host returned an invalid address") from exc
        if not parsed.is_global:
            raise SourceSecurityError("source URL must resolve to a public address")


def next_public_url(current: str, location: str) -> str:
    target = urljoin(current, location)
    validate_public_url(target)
    return target


def read_limited_response(response: Any, max_bytes: int) -> bytes:
    """流式读取响应，避免在检查大小前把不受限正文载入内存。"""
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except (TypeError, ValueError) as exc:
            raise SourceSecurityError("source response has an invalid content-length") from exc
        if declared_length < 0 or declared_length > max_bytes:
            raise SourceSecurityError("source response exceeds size limit")
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise SourceSecurityError("source response exceeds size limit")
        chunks.append(chunk)
    return b"".join(chunks)


def contains_secret(value: object, context: PluginContext | None = None, depth: int = 0) -> bool:
    """只返回布尔值；不会把敏感值放进诊断或日志。"""
    if depth > 64:
        return True
    credentials: Iterable[str] = context.credentials.values() if context else ()
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _SENSITIVE_KEYS and item not in (None, "", "CHANGE_ME"):
                return True
            if contains_secret(item, context, depth + 1):
                return True
        return False
    if isinstance(value, list):
        return any(contains_secret(item, context, depth + 1) for item in value)
    if isinstance(value, str):
        return any(secret and secret in value for secret in credentials)
    return False
