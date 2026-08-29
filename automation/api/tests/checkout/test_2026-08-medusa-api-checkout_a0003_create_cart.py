"""A0003：按运行时地区创建游客购物车。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0003"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_create_cart_uses_seeded_region(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> None:
    cart = store_client.create_cart(seed_state["region_europe"]).cart

    assert cart.id
    assert cart.region_id == seed_state["region_europe"]
    assert cart.items == []
