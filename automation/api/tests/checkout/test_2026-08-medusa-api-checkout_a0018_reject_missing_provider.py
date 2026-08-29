"""A0018：缺少支付提供者时返回结构化 400 错误。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.models.checkout.store import ApiMissingProviderPaymentSessionRequest
from automation.api.tests.checkout.support import (
    add_standard_shipping,
    create_cart_with_line,
    update_guest_cart,
)

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0018"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_initialize_payment_session_rejects_missing_provider(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> None:
    setup = add_standard_shipping(
        store_client,
        update_guest_cart(store_client, create_cart_with_line(store_client, seed_state)),
    )
    collection = store_client.create_payment_collection(setup.cart.id).payment_collection
    error = store_client.initialize_payment_session_error(
        collection.id, ApiMissingProviderPaymentSessionRequest()
    )

    assert error.type == "invalid_data"
    assert error.message
