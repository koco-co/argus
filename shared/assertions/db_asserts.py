"""通过只读包装器执行的示例数据库断言。"""

from __future__ import annotations

from typing import Any

from shared.db.readonly_client import ReadOnlyDBClient


def assert_row_exists(
    client: ReadOnlyDBClient,
    sql: str,
    params: tuple[Any, ...] = (),
) -> None:
    """断言只读查询至少返回一行。"""

    # pi-lens-ignore: python-sql-injection
    rows = client.query(sql, params)
    if not rows:
        raise AssertionError(f"只读查询未返回任何记录：{sql[:80]}")
