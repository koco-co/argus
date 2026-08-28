"""仅允许读取语句的数据库包装器（ARCHITECTURE §6 Layer 2）。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Protocol

_STATEMENT_VERBS = {"select", "with", "explain", "show", "describe", "table", "pragma"}
_WRITE_TOKEN = re.compile(r"\b(?:insert|update|delete|merge|copy)\b", re.IGNORECASE)
_ANALYZE_TOKEN = re.compile(r"\banalyze\b", re.IGNORECASE)
_MULTI_STATEMENT = re.compile(r";\s*\S", re.DOTALL)


class _Result(Protocol):
    def fetchall(self) -> list[Any]: ...


class _Connection(Protocol):
    def execute(self, sql: str, params: tuple[Any, ...]) -> _Result: ...


class ReadOnlyDBClient:
    """以语句头白名单和 DML 词扫描提供第二层只读防线。"""

    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    @staticmethod
    def validate(sql: str) -> None:
        normalized = sql.lstrip("( \n\t")
        parts = normalized.split(None, 1)
        head = parts[0].lower().rstrip(";") if parts else ""
        if head not in _STATEMENT_VERBS:
            raise PermissionError(f"ReadOnlyDBClient 已阻止语句：{sql[:80]!r}")
        if _MULTI_STATEMENT.search(sql):
            raise PermissionError(f"ReadOnlyDBClient 已阻止多语句：{sql[:80]!r}")
        if head in {"with", "explain"} and (_WRITE_TOKEN.search(sql) or _ANALYZE_TOKEN.search(sql)):
            raise PermissionError(f"ReadOnlyDBClient 已阻止潜在写语句：{sql[:80]!r}")

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
        self.validate(sql)
        return list(self._connection.execute(sql, params).fetchall())

    def query_mappings(self, sql: str, params: tuple[Any, ...] = ()) -> list[Mapping[str, Any]]:
        rows = self.query(sql, params)
        if not all(isinstance(row, Mapping) for row in rows):
            raise TypeError("数据库驱动必须返回 Mapping 行，才能执行字段断言")
        return rows
