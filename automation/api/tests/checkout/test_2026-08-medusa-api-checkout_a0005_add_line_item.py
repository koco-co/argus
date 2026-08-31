"""A0005：加入由真实响应解析出的黑色 S 码变体。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.tests.checkout.support import create_cart_with_line

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0005"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_add_line_item_uses_runtime_variant(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> None:
    setup = create_cart_with_line(store_client, seed_state)
    item = next(item for item in setup.cart.items if item.variant_id == setup.variant.id)

    assert item.quantity == 1
    assert item.unit_price == pytest.approx(setup.variant.calculated_price.calculated_amount)
