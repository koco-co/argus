"""控制面读取不可信 YAML/JSON 时使用的保守解析器。"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

import yaml  # pyright: ignore[reportMissingModuleSource]
from yaml.events import AliasEvent  # pyright: ignore[reportMissingModuleSource]
from yaml.nodes import MappingNode  # pyright: ignore[reportMissingModuleSource]

_MAX_BYTES = 8 * 1024 * 1024
_MAX_DEPTH = 64


class ParseError(ValueError):
    """输入不是可安全解码的单文档。"""


def _validate_shape(value: Any, depth: int = 0) -> None:
    if depth > _MAX_DEPTH:
        raise ParseError("document is nested too deeply")
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ParseError("document object keys must be strings")
        for item in value.values():
            _validate_shape(item, depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_shape(item, depth + 1)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ParseError("document contains a non-finite number")
    if value is not None and not isinstance(value, (bool, int, float, str, date, datetime)):
        raise ParseError("document contains an unsupported value")


class _StrictSafeLoader(yaml.SafeLoader):
    """拒绝 YAML alias 和重复键，避免歧义与别名展开攻击。"""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(AliasEvent):
            self.get_event()
            raise ParseError("YAML aliases are not supported")
        return super().compose_node(parent, index)

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=True)
            try:
                duplicate = key in mapping
            except TypeError as exc:
                raise ParseError("document mapping keys must be hashable") from exc
            if duplicate:
                raise ParseError("document contains duplicate keys")
            mapping[key] = self.construct_object(value_node, deep=True)
        return mapping


def _bounded_bytes(content: bytes | str, max_bytes: int) -> bytes:
    if (
        not isinstance(max_bytes, int)
        or isinstance(max_bytes, bool)
        or max_bytes < 1
        or max_bytes > _MAX_BYTES
    ):
        raise ValueError("max_bytes must be an integer between 1 and 8 MiB")
    if isinstance(content, str):
        try:
            encoded = content.encode("utf-8")
        except UnicodeError as exc:
            raise ParseError("document is not valid UTF-8") from exc
    elif isinstance(content, bytes):
        encoded = content
    else:
        raise TypeError("document content must be bytes or str")
    if len(encoded) > max_bytes:
        raise ParseError("document exceeds size limit")
    return encoded


def load_yaml(content: bytes | str, *, max_bytes: int = _MAX_BYTES) -> Any:
    """在大小、深度、重复键和 alias 边界内解析单个 YAML/JSON 文档。"""
    encoded = _bounded_bytes(content, max_bytes)
    loader: _StrictSafeLoader | None = None
    try:
        loader = _StrictSafeLoader(encoded)
        value = loader.get_single_data()
    except ParseError:
        raise
    except (RecursionError, TypeError, UnicodeError, yaml.YAMLError) as exc:
        raise ParseError("document is malformed") from exc
    finally:
        if loader is not None:
            loader.dispose()
    _validate_shape(value)
    return value


def load_json(content: bytes | str, *, max_bytes: int = _MAX_BYTES) -> Any:
    """在大小、深度、重复键和非有限数字边界内解析 JSON。"""
    encoded = _bounded_bytes(content, max_bytes)

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ParseError("JSON contains duplicate keys")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ParseError(f"JSON contains non-finite value {value}")

    try:
        value = json.loads(
            encoded,
            object_pairs_hook=unique_pairs,
            parse_constant=reject_constant,
        )
    except ParseError:
        raise
    except (RecursionError, TypeError, UnicodeError, ValueError) as exc:
        raise ParseError("JSON is malformed") from exc
    _validate_shape(value)
    return value
