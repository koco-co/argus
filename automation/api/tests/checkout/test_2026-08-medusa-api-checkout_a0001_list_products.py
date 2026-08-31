"""A0001：查询真实 T-Shirt 与黑色 S 码变体。"""

from __future__ import annotations

from typing import Any

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0001"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
    pytest.mark.read_only,
]


def test_list_products_contains_black_small_variant(
    store_client: FullStoreClient,
    seed_state: dict[str, str],
    seed_registry: dict[str, Any],
) -> None:
    response = store_client.list_tshirt(seed_state["region_europe"])
    product = next(item for item in response.products if item.handle == "t-shirt")
    variant = next(item for item in product.variants if item.sku == "SHIRT-S-BLACK")

    assert variant.title == "S / Black"
    assert (
        variant.calculated_price.currency_code
        == seed_registry["product_price_eur"]["currency_code"]
    )
    assert variant.calculated_price.calculated_amount == pytest.approx(
        seed_registry["product_price_eur"]["value"]
    )
