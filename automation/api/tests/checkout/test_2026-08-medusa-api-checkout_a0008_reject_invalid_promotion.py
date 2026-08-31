"""A0008：非法促销码返回结构化 400 错误。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.tests.checkout.support import create_cart_with_line

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0008"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_apply_invalid_promotion_returns_error(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> None:
    setup = create_cart_with_line(store_client, seed_state)
    error = store_client.apply_promotions_error(setup.cart.id, "NOT-A-REAL-CODE")

    assert error.type == "invalid_data"
    assert "invalid" in error.message.lower()
