"""A0019：完成完整游客结算并验证真实订单投影。"""

from __future__ import annotations

import pytest  # pyright: ignore[reportMissingImports]

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.tests.checkout.support import prepare_payment_checkout

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0019"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_complete_cart_creates_authorized_order(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> None:
    setup = prepare_payment_checkout(store_client, seed_state)
    response = store_client.complete_cart(setup.cart.id)
    order = response.order

    assert response.type == "order"
    assert order.id
    assert order.email == "argus-api@example.invalid"
    item = next(item for item in order.items if item.variant_id == setup.variant.id)
    assert item.variant_sku == setup.variant.sku
    assert item.quantity == 1
    assert setup.shipping_option is not None
    shipping = next(
        method
        for method in order.shipping_methods
        if method.shipping_option_id == setup.shipping_option.id
    )
    assert shipping.name == "Standard Shipping"
    payment = order.payment_collections[0]
    assert payment.status == "authorized"
    assert order.total == pytest.approx(setup.cart.total)
