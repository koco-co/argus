"""A0013：选择 Standard Shipping 并回读购物车配送方法。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.tests.checkout.support import (
    add_standard_shipping,
    create_cart_with_line,
    update_guest_cart,
)

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0013"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_add_standard_shipping_updates_cart(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> None:
    setup = add_standard_shipping(
        store_client,
        update_guest_cart(store_client, create_cart_with_line(store_client, seed_state)),
    )

    assert setup.shipping_option is not None
    assert any(
        method.shipping_option_id == setup.shipping_option.id
        for method in setup.cart.shipping_methods
    )
