"""手写靶场基础设施烟测；不代表任何迭代业务覆盖。"""

from __future__ import annotations

import httpx
import pytest

pytestmark = [
    pytest.mark.module("harness"),
    pytest.mark.case_id("C0000"),
    pytest.mark.iteration("harness"),
    pytest.mark.read_only,
]


@pytest.mark.parametrize("probe", range(4))
def test_harness_smoke(
    isolated_http_session: httpx.Client,
    worker_namespace: str,
    probe: int,
) -> None:
    response = isolated_http_session.get("/dk")
    assert response.status_code == 200
    assert "Medusa" in response.text
    assert worker_namespace
    assert probe >= 0
