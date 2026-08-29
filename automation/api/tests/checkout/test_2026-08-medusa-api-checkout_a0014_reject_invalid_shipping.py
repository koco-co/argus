"""A0014：无效配送选项时拒绝更新购物车。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.tests.checkout.support import create_cart_with_line

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0014"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_add_shipping_method_rejects_unknown_option(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> None:
    setup = create_cart_with_line(store_client, seed_state)
    error = store_client.add_shipping_method_error(setup.cart.id, "so_missing_for_argus")

    assert error.type == "invalid_data"
    assert error.message
