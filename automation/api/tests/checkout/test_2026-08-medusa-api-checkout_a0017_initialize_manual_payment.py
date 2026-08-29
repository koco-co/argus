"""A0017：初始化隔离测试用 Manual Payment 会话。"""

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
    pytest.mark.case_id("A0017"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_initialize_manual_payment_session(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> None:
    setup = add_standard_shipping(
        store_client,
        update_guest_cart(store_client, create_cart_with_line(store_client, seed_state)),
    )
    collection = store_client.create_payment_collection(setup.cart.id).payment_collection
    initialized = store_client.initialize_payment_session(
        collection.id, seed_state["payment_manual"]
    ).payment_collection

    assert initialized.payment_sessions
    session = initialized.payment_sessions[0]
    assert session.provider_id == seed_state["payment_manual"]
    assert session.status == "pending"
    assert session.amount == pytest.approx(initialized.amount)
