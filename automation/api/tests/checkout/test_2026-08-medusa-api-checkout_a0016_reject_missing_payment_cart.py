"""A0016：缺少购物车 ID 时拒绝创建支付集合。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.models.checkout.store import ApiMissingCartIdPaymentCollectionRequest

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0016"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_create_payment_collection_rejects_missing_cart(
    store_client: FullStoreClient,
) -> None:
    error = store_client.create_payment_collection_error(ApiMissingCartIdPaymentCollectionRequest())

    assert error.type == "invalid_data"
    assert "cart_id" in error.message
