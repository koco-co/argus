"""来源连接器的网络和凭据边界。"""

from __future__ import annotations

import ipaddress
import json
import math
import socket
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit

from .contracts import PluginContext  # pyright: ignore[reportMissingImports]


class SourceSecurityError(ValueError):
    """来源引用、重定向或载荷触碰安全边界。"""


_MAX_JSON_BYTES = 8 * 1024 * 1024
_MAX_URL_UNQUOTE_PASSES = 8


def _decoded_path(value: str) -> str:
    """Decode bounded layers so double-encoded traversal cannot pass policy."""
    decoded = value
    for _ in range(_MAX_URL_UNQUOTE_PASSES):
        next_value = unquote(decoded)
        if next_value == decoded:
            return decoded
        decoded = next_value
    raise SourceSecurityError("source URL contains excessive encoding")


def _has_raw_control_or_space(value: str) -> bool:
    return any(
        character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F
        for character in value
    )


def load_json(content: bytes | str) -> Any:
    """Parse untrusted JSON without duplicate keys or non-finite numbers."""

    if isinstance(content, str):
        try:
            encoded = content.encode("utf-8")
        except UnicodeError as exc:
            raise SourceSecurityError("source JSON is not valid UTF-8") from exc
    elif isinstance(content, bytes):
        encoded = content
    else:
        raise TypeError("source JSON content must be bytes or str")
    if len(encoded) > _MAX_JSON_BYTES:
        raise SourceSecurityError("source JSON exceeds size limit")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SourceSecurityError("source JSON contains duplicate keys")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise SourceSecurityError(f"source JSON contains non-finite value {value}")

    def validate_value(value: Any, depth: int = 0) -> Any:
        if depth > 64:
            raise SourceSecurityError("source JSON is too deeply nested")
        if isinstance(value, float) and not math.isfinite(value):
            raise SourceSecurityError("source JSON contains a non-finite number")
        if isinstance(value, dict):
            for item in value.values():
                validate_value(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                validate_value(item, depth + 1)
        return value

    try:
        parsed = json.loads(
            encoded,
            object_pairs_hook=unique_pairs,
            parse_constant=reject_constant,
        )
        return validate_value(parsed)
    except SourceSecurityError:
        raise
    except (RecursionError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("source JSON is malformed") from exc


_SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "apikey",
    "accesstoken",
    "authorization",
    "cookie",
    "privatekey",
    "credential",
    "credentials",
    "clientsecret",
    "bearer",
    "auth",
}


def _sensitive_key(key: object) -> bool:
    normalized = "".join(character for character in str(key).lower() if character.isalnum())
    return normalized in _SENSITIVE_KEYS or normalized.endswith(
        ("password", "secret", "token", "apikey", "credential", "authorization", "cookie")
    )


def validate_public_url(source_ref: str) -> None:
    """拒绝凭据 URL 及解析到私有/回环/链路本地地址的来源。"""
    if not isinstance(source_ref, str):
        raise SourceSecurityError("source URL must be a string")
    if _has_raw_control_or_space(source_ref):
        raise SourceSecurityError("source URL is malformed")
    try:
        parts = urlsplit(source_ref)
        port = parts.port
    except ValueError as exc:
        raise SourceSecurityError("source URL is malformed") from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise SourceSecurityError("source URL must use http or https")
    if port is not None and not 1 <= port <= 65535:
        raise SourceSecurityError("source URL port is invalid")
    try:
        decoded_path = _decoded_path(parts.path)
    except (TypeError, ValueError, SourceSecurityError) as exc:
        raise SourceSecurityError("source URL is malformed") from exc
    if (
        "\x00" in source_ref
        or "\\" in source_ref
        or _has_raw_control_or_space(decoded_path)
        or "\x00" in decoded_path
        or "\\" in decoded_path
        or any(part == ".." for part in decoded_path.split("/"))
    ):
        raise SourceSecurityError("source URL must not contain NUL, backslash, or traversal")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise SourceSecurityError("source URL must not contain credentials, query, or fragment")
    try:
        addresses = socket.getaddrinfo(
            parts.hostname,
            port if port is not None else (443 if parts.scheme == "https" else 80),
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


def next_public_url(current: str, location: str, *, same_origin_as: str | None = None) -> str:
    """Resolve a redirect and optionally keep it on the original origin."""
    if not isinstance(current, str) or not isinstance(location, str):
        raise SourceSecurityError("redirect URL must be a string")
    if same_origin_as is not None and not isinstance(same_origin_as, str):
        raise SourceSecurityError("redirect origin must be a string")
    try:
        target = urljoin(current, location)
    except (TypeError, ValueError) as exc:
        raise SourceSecurityError("redirect URL is malformed") from exc
    validate_public_url(target)
    if same_origin_as is not None:
        try:
            source = urlsplit(same_origin_as)
            destination = urlsplit(target)
            source_port = (
                source.port
                if source.port is not None
                else (443 if source.scheme == "https" else 80)
            )
            destination_port = (
                destination.port
                if destination.port is not None
                else (443 if destination.scheme == "https" else 80)
            )
        except ValueError as exc:
            raise SourceSecurityError("redirect URL is malformed") from exc
        if (
            destination.scheme != source.scheme
            or destination.hostname != source.hostname
            or destination_port != source_port
        ):
            raise SourceSecurityError("redirect must remain on the original origin")
    return target


def validate_response_peer(response: Any) -> None:
    """Reject a network response whose final peer is not globally routable.

    URL DNS validation is only a preflight check. HTTPX exposes the connected
    network stream after the request; checking its peer closes the DNS
    rebinding window. Mock transports have no network stream and are allowed
    for deterministic unit tests.
    """
    stream = getattr(response, "extensions", {}).get("network_stream")
    if stream is None:
        return
    try:
        peer = stream.get_extra_info("server_addr")
        if peer is None:
            peer = stream.get_extra_info("peername")
    except AttributeError as exc:
        raise SourceSecurityError("source response peer cannot be inspected") from exc
    if not peer:
        raise SourceSecurityError("source response peer cannot be inspected")
    try:
        address = peer[0] if isinstance(peer, tuple) else peer
        parsed = ipaddress.ip_address(address)
    except (IndexError, TypeError, ValueError) as exc:
        raise SourceSecurityError("source response peer is not an IP address") from exc
    if not parsed.is_global:
        raise SourceSecurityError("source response peer must be a public address")


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
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _sensitive_key(key) and item not in (None, "", "CHANGE_ME"):
                return True
            if contains_secret(item, context, depth + 1):
                return True
        return False
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(contains_secret(item, context, depth + 1) for item in value)
    if isinstance(value, str):
        if any(secret and secret in value for secret in credentials):
            return True
        try:
            parts = urlsplit(value)
        except ValueError:
            return False
        if parts.scheme in {"http", "https"} and (
            parts.username
            or parts.password
            or any(_sensitive_key(key) for key, _ in parse_qsl(parts.query, keep_blank_values=True))
        ):
            return True
    return False
