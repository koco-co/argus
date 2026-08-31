"""PROD 收集门禁反例：本地可收集，生产必须机械剔除。"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.module("harness"),
    pytest.mark.case_id("C0000"),
    pytest.mark.iteration("harness"),
]


def test_non_read_only_probe() -> None:
    assert True
