"""由 Medusa Store API cases 生成的同步类型化客户端。"""

from __future__ import annotations

import httpx

from automation.api.models.checkout.store import (
    ApplyPromotionsRequest,
    CartResponse,
    ErrorResponse,
    ProductListResponse,
)


class StoreClient:
    def __init__(self, base_url: str, publishable_key: str) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"x-publishable-api-key": publishable_key},
            timeout=10,
            trust_env=False,
        )

    def list_tshirt(self, region_id: str) -> ProductListResponse:
        response = self._client.get(
            "/store/products", params={"handle": "t-shirt", "region_id": region_id}
        )
        response.raise_for_status()
        return ProductListResponse.model_validate(response.json())

    def create_cart(self, region_id: str) -> CartResponse:
        response = self._client.post("/store/carts", json={"region_id": region_id})
        response.raise_for_status()
        return CartResponse.model_validate(response.json())

    def add_line_item(self, cart_id: str, variant_id: str) -> CartResponse:
        response = self._client.post(
            f"/store/carts/{cart_id}/line-items",
            json={"variant_id": variant_id, "quantity": 1},
        )
        response.raise_for_status()
        return CartResponse.model_validate(response.json())

    def apply_promotions(self, cart_id: str, request: ApplyPromotionsRequest) -> CartResponse:
        response = self._client.post(
            f"/store/carts/{cart_id}/promotions", json=request.model_dump()
        )
        response.raise_for_status()
        return CartResponse.model_validate(response.json())

    def apply_promotions_error(self, cart_id: str) -> ErrorResponse:
        response = self._client.post(f"/store/carts/{cart_id}/promotions", json={"code": "ARGUS10"})
        if response.status_code != 400:
            response.raise_for_status()
        return ErrorResponse.model_validate(response.json())

    def close(self) -> None:
        self._client.close()
