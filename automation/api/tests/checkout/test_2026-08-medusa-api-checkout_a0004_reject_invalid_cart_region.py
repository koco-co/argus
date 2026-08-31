"""A0004：无效地区创建购物车返回结构化错误。"""

from __future__ import annotations

import pytest

from automation.api.clients.checkout.store_client import FullStoreClient
from automation.api.models.checkout.store import ApiInvalidCreateCartRequest

pytestmark = [
    pytest.mark.module("checkout"),
    pytest.mark.case_id("A0004"),
    pytest.mark.iteration("2026-08-medusa-api-checkout"),
]


def test_create_cart_rejects_unknown_region(store_client: FullStoreClient) -> None:
    error = store_client.create_cart_error(
        ApiInvalidCreateCartRequest(region_id="reg_missing_for_argus")
    )

    assert error.type == "not_found"
    assert error.message
