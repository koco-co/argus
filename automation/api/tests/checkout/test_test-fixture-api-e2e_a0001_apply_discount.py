"""由 test-fixture-api-e2e/A0001 生成的促销金额 API 用例。"""

from __future__ import annotations

from typing import Any

import pytest

from automation.api.clients.checkout.store_client import StoreClient
from automation.api.models.checkout.store import ApplyPromotionsRequest

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0001"),
    pytest.mark.iteration("test-fixture-api-e2e"),
]


def test_apply_valid_promotion(
    store_client: StoreClient,
    seed_state: dict[str, str],
    seed_registry: dict[str, Any],
) -> None:
    product = store_client.list_tshirt(seed_state["region_europe"]).products[0]
    variant = next(item for item in product.variants if item.title == "S / Black")
    cart = store_client.create_cart(seed_state["region_europe"]).cart
    store_client.add_line_item(cart.id, variant.id)
    code = seed_registry["discount_argus10"]["value"]
    response = store_client.apply_promotions(
        cart.id, ApplyPromotionsRequest(promo_codes=[code])
    )
    price = seed_registry["product_price_eur"]["value"]
    percentage = seed_registry["discount_argus10"]["percentage"]
    assert response.cart.total == price * (100 - percentage) / 100
    assert response.cart.discount_total == price * percentage / 100
