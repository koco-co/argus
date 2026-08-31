"""A0020：不存在的购物车不能完成订单。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0020"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_complete_cart_rejects_unknown_cart(store_client: FullStoreClient) -> None:
    error = store_client.complete_cart_error("cart_missing_for_argus")

    assert error.type == "not_found"
    assert error.message
