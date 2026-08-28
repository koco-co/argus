"""A0011：查询购物车可用配送方式并定位 Standard Shipping。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.tests.checkout.support import create_cart_with_line, update_guest_cart

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0011"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_list_shipping_options_contains_seeded_standard_option(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> None:
    setup = update_guest_cart(store_client, create_cart_with_line(store_client, seed_state))
    options = store_client.list_shipping_options(setup.cart.id).shipping_options
    standard = next(option for option in options if option.name == "Standard Shipping")

    assert standard.id == seed_state["shipping_standard"]
    assert standard.amount >= 0
