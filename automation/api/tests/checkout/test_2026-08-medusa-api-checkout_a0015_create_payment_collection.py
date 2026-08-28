"""A0015：为已选配送的购物车创建支付集合。"""

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
    pytest.mark.case_id("A0015"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_create_payment_collection_matches_cart_total(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> None:
    setup = add_standard_shipping(
        store_client,
        update_guest_cart(store_client, create_cart_with_line(store_client, seed_state)),
    )
    collection = store_client.create_payment_collection(setup.cart.id).payment_collection

    assert collection.id
    assert collection.currency_code == setup.cart.currency_code
    assert collection.amount == pytest.approx(setup.cart.total)
