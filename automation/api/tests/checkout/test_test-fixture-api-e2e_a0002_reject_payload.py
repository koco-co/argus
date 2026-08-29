"""由 test-fixture-api-e2e/A0002 生成的非法促销请求 API 用例。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import StoreClient

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0002"),
    pytest.mark.iteration("test-fixture-api-e2e"),
]


def test_reject_invalid_promotion_payload(
    store_client: StoreClient, seed_state: dict[str, str]
) -> None:
    product = store_client.list_tshirt(seed_state["region_europe"]).products[0]
    variant = next(item for item in product.variants if item.title == "S / Black")
    cart = store_client.create_cart(seed_state["region_europe"]).cart
    store_client.add_line_item(cart.id, variant.id)
    error = store_client.apply_promotions_error(cart.id)
    assert error.type == "invalid_data"
    assert "promo_codes" in error.message
