"""A0010：非法邮箱时拒绝更新购物车。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.models.checkout.store import ApiInvalidUpdateCartRequest
from automation.api.tests.checkout.support import create_cart_with_line

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0010"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_update_cart_rejects_invalid_email(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> None:
    setup = create_cart_with_line(store_client, seed_state)
    error = store_client.update_cart_error(
        setup.cart.id, ApiInvalidUpdateCartRequest(email="not-an-email")
    )

    assert error.type == "invalid_data"
    assert error.message
