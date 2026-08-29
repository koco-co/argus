"""A0002：无效地区查询返回结构化错误。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0002"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
    pytest.mark.read_only,
]


def test_list_products_rejects_invalid_region(store_client: FullStoreClient) -> None:
    error = store_client.list_products_error("t-shirt", "reg_missing_for_argus")

    assert error.type == "invalid_data"
    assert error.message
