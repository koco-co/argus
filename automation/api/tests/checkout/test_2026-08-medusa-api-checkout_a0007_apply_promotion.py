"""A0007：应用 ARGUS10 并按运行时种子推导折后金额。"""

from __future__ import annotations

from typing import Any

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.models.checkout.store import ApiApplyPromotionsRequest
from automation.api.tests.checkout.support import create_cart_with_line

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0007"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_apply_argus10_calculates_discount_from_seed(
    store_client: FullStoreClient,
    seed_state: dict[str, str],
    seed_registry: dict[str, Any],
) -> None:
    setup = create_cart_with_line(store_client, seed_state)
    code = seed_registry["discount_argus10"]["value"]
    response = store_client.apply_promotions(
        setup.cart.id, ApiApplyPromotionsRequest(promo_codes=[code])
    )
    price = seed_registry["product_price_eur"]["value"]
    percentage = seed_registry["discount_argus10"]["percentage"]

    assert response.cart.discount_total == pytest.approx(price * percentage / 100)
    assert response.cart.total == pytest.approx(price * (100 - percentage) / 100)
