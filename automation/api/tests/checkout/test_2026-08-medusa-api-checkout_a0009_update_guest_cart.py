"""A0009：写入虚构游客邮箱和德国配送地址。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.tests.checkout.support import create_cart_with_line, update_guest_cart

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0009"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_update_cart_persists_guest_contact_and_addresses(
    store_client: FullStoreClient, seed_state: dict[str, str]
) -> None:
    setup = update_guest_cart(store_client, create_cart_with_line(store_client, seed_state))

    assert setup.cart.email == "argus-api@example.invalid"
    assert setup.cart.shipping_address is not None
    assert setup.cart.shipping_address.country_code == "de"
    assert setup.cart.billing_address is not None
    assert setup.cart.billing_address.postal_code == "10115"
