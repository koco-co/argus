"""A0012：缺少购物车 ID 时拒绝查询配送方式。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0012"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_list_shipping_options_rejects_missing_cart(store_client: FullStoreClient) -> None:
    error = store_client.list_shipping_options_error()

    assert error.type == "invalid_data"
    assert "cart_id" in error.message
