"""Roadmap 5.1：PROD 收集门禁与 worker 隔离命名验收。"""

from __future__ import annotations

from typing import Any, cast

import pytest

from automation import conftest as automation_conftest


class _Item:
    def __init__(self, read_only: bool) -> None:
        self.read_only = read_only

    def get_closest_marker(self, name: str) -> object | None:
        return object() if name == "read_only" and self.read_only else None


class _Hook:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def pytest_deselected(self, *, items: list[_Item]) -> None:
        self.calls.append({"items": items})


class _Config:
    def __init__(self) -> None:
        self.hook = _Hook()


def test_prod_deselects_every_non_read_only_item(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ENV", "prod")
    kept = _Item(read_only=True)
    removed = _Item(read_only=False)
    items = [kept, removed]
    config = _Config()
    automation_conftest.pytest_collection_modifyitems(cast(Any, config), cast(Any, items))
    assert items == [kept]
    assert config.hook.calls == [{"items": [removed]}]


def test_non_prod_keeps_all_items(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ENV", "local")
    items = [_Item(read_only=False)]
    config = _Config()
    automation_conftest.pytest_collection_modifyitems(cast(Any, config), cast(Any, items))
    assert len(items) == 1
    assert config.hook.calls == []


def test_worker_namespace_is_stable_per_worker_and_distinct() -> None:
    first = automation_conftest.build_worker_namespace("run-42", "gw0")
    repeated = automation_conftest.build_worker_namespace("run-42", "gw0")
    second = automation_conftest.build_worker_namespace("run-42", "gw1")
    assert first == repeated
    assert first != second
    assert first.startswith("run-42-")
