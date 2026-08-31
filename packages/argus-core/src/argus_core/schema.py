"""控制面 Schema 的单一运行时入口。"""

from __future__ import annotations

from typing import Any

from .models import IterationDocument  # pyright: ignore[reportMissingImports]


def iteration_schema() -> dict[str, Any]:
    """返回可导出的 JSON Schema 副本，调用方可安全修改结果。"""
    return IterationDocument.model_json_schema()


def validate_iteration(value: Any) -> IterationDocument:
    """以同一 Pydantic 契约校验从 YAML/JSON 解码的对象。"""
    return IterationDocument.model_validate(value)
