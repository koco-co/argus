"""A0006：缺少变体 ID 时拒绝加购。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.models.checkout.store import ApiMissingVariantLineItemRequest

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0006"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_add_line_item_rejects_missing_variant(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> None:
    cart = store_client.create_cart(seed_state["region_europe"]).cart
    error = store_client.add_line_item_error(cart.id, ApiMissingVariantLineItemRequest())

    assert error.type == "invalid_data"
    assert error.message
