"""由 Medusa Store API cases 生成的同步类型化客户端。"""

# ruff: noqa: I001 — 保留冻结 fixture 的旧 import 节点，同时加载正式 API 增量模型。

from __future__ import annotations

import httpx
from pydantic import BaseModel

from automation.api.models.checkout.store import (
    ApplyPromotionsRequest,
    CartResponse,
    ErrorResponse,
    ProductListResponse,
)

from automation.api.models.checkout.store import (
    ApiAddLineItemRequest,
    ApiAddShippingMethodRequest,
    ApiApplyPromotionsRequest,
    ApiCartResponse,
    ApiCreateCartRequest,
    ApiCreatePaymentCollectionRequest,
    ApiErrorResponse,
    ApiInitializePaymentSessionRequest,
    ApiInvalidCreateCartRequest,
    ApiInvalidUpdateCartRequest,
    ApiMalformedPromotionRequest,
    ApiMissingCartIdPaymentCollectionRequest,
    ApiMissingProviderPaymentSessionRequest,
    ApiMissingVariantLineItemRequest,
    ApiOrderResponse,
    ApiPaymentCollectionResponse,
    ApiProductListResponse,
    ApiShippingOptionListResponse,
    ApiUpdateCartRequest,
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


class FullStoreClient(StoreClient):
    """M7 为正式 API iteration 增量生成的完整 Store 客户端。"""

    @staticmethod
    def _dump(payload: BaseModel) -> dict[str, object]:
        """在传输边界执行唯一一次模型序列化。"""

        return payload.model_dump(exclude_none=True)

    @staticmethod
    def _error(response: httpx.Response) -> ApiErrorResponse:
        """把结构化错误解析为完整 API 模型。"""

        try:
            return ApiErrorResponse.model_validate(response.json())
        except ValueError as exc:
            raise httpx.HTTPStatusError(
                "Medusa error response is not a typed error envelope",
                request=response.request,
                response=response,
            ) from exc

    def list_tshirt(self, region_id: str) -> ApiProductListResponse:
        response = self._client.get(
            "/store/products",
            params={
                "handle": "t-shirt",
                "region_id": region_id,
                "fields": "+id,+handle,+variants,+variants.prices",
            },
        )
        response.raise_for_status()
        return ApiProductListResponse.model_validate(response.json())

    def list_products(self, handle: str, region_id: str) -> ApiProductListResponse:
        response = self._client.get(
            "/store/products", params={"handle": handle, "region_id": region_id}
        )
        response.raise_for_status()
        return ApiProductListResponse.model_validate(response.json())

    def list_products_error(self, handle: str, region_id: str) -> ApiErrorResponse:
        response = self._client.get(
            "/store/products", params={"handle": handle, "region_id": region_id}
        )
        if response.status_code != 400:
            response.raise_for_status()
        return self._error(response)

    def create_cart(self, region_id: str) -> ApiCartResponse:
        payload = ApiCreateCartRequest(region_id=region_id)
        response = self._client.post("/store/carts", json=self._dump(payload))
        response.raise_for_status()
        return ApiCartResponse.model_validate(response.json())

    def create_cart_error(self, payload: ApiInvalidCreateCartRequest) -> ApiErrorResponse:
        response = self._client.post("/store/carts", json=self._dump(payload))
        if response.status_code != 404:
            response.raise_for_status()
        return self._error(response)

    def add_line_item(self, cart_id: str, variant_id: str) -> ApiCartResponse:
        payload = ApiAddLineItemRequest(variant_id=variant_id, quantity=1)
        response = self._client.post(f"/store/carts/{cart_id}/line-items", json=self._dump(payload))
        response.raise_for_status()
        return ApiCartResponse.model_validate(response.json())

    def add_line_item_error(
        self, cart_id: str, payload: ApiMissingVariantLineItemRequest
    ) -> ApiErrorResponse:
        response = self._client.post(f"/store/carts/{cart_id}/line-items", json=self._dump(payload))
        if response.status_code != 400:
            response.raise_for_status()
        return self._error(response)

    def apply_promotions(self, cart_id: str, request: ApiApplyPromotionsRequest) -> ApiCartResponse:
        response = self._client.post(f"/store/carts/{cart_id}/promotions", json=self._dump(request))
        response.raise_for_status()
        return ApiCartResponse.model_validate(response.json())

    def apply_promotions_error(self, cart_id: str, code: str | None = None) -> ApiErrorResponse:
        request: BaseModel
        if code is None:
            request = ApiMalformedPromotionRequest(code="ARGUS10")
        else:
            request = ApiApplyPromotionsRequest(promo_codes=[code])
        response = self._client.post(f"/store/carts/{cart_id}/promotions", json=self._dump(request))
        if response.status_code != 400:
            response.raise_for_status()
        return self._error(response)

    def update_cart(self, cart_id: str, request: ApiUpdateCartRequest) -> ApiCartResponse:
        response = self._client.post(f"/store/carts/{cart_id}", json=self._dump(request))
        response.raise_for_status()
        return ApiCartResponse.model_validate(response.json())

    def update_cart_error(
        self, cart_id: str, payload: ApiInvalidUpdateCartRequest
    ) -> ApiErrorResponse:
        response = self._client.post(f"/store/carts/{cart_id}", json=self._dump(payload))
        if response.status_code != 400:
            response.raise_for_status()
        return self._error(response)

    def list_shipping_options(self, cart_id: str) -> ApiShippingOptionListResponse:
        response = self._client.get("/store/shipping-options", params={"cart_id": cart_id})
        response.raise_for_status()
        return ApiShippingOptionListResponse.model_validate(response.json())

    def list_shipping_options_error(self) -> ApiErrorResponse:
        response = self._client.get("/store/shipping-options")
        if response.status_code != 400:
            response.raise_for_status()
        return self._error(response)

    def add_shipping_method(self, cart_id: str, option_id: str) -> ApiCartResponse:
        payload = ApiAddShippingMethodRequest(option_id=option_id)
        response = self._client.post(
            f"/store/carts/{cart_id}/shipping-methods", json=self._dump(payload)
        )
        response.raise_for_status()
        return ApiCartResponse.model_validate(response.json())

    def add_shipping_method_error(self, cart_id: str, option_id: str) -> ApiErrorResponse:
        payload = ApiAddShippingMethodRequest(option_id=option_id)
        response = self._client.post(
            f"/store/carts/{cart_id}/shipping-methods", json=self._dump(payload)
        )
        if response.status_code != 400:
            response.raise_for_status()
        return self._error(response)

    def create_payment_collection(self, cart_id: str) -> ApiPaymentCollectionResponse:
        payload = ApiCreatePaymentCollectionRequest(cart_id=cart_id)
        response = self._client.post("/store/payment-collections", json=self._dump(payload))
        response.raise_for_status()
        return ApiPaymentCollectionResponse.model_validate(response.json())

    def create_payment_collection_error(
        self, payload: ApiMissingCartIdPaymentCollectionRequest
    ) -> ApiErrorResponse:
        response = self._client.post("/store/payment-collections", json=self._dump(payload))
        if response.status_code != 400:
            response.raise_for_status()
        return self._error(response)

    def initialize_payment_session(
        self, collection_id: str, provider_id: str
    ) -> ApiPaymentCollectionResponse:
        payload = ApiInitializePaymentSessionRequest(provider_id=provider_id)
        response = self._client.post(
            f"/store/payment-collections/{collection_id}/payment-sessions",
            json=self._dump(payload),
        )
        response.raise_for_status()
        return ApiPaymentCollectionResponse.model_validate(response.json())

    def initialize_payment_session_error(
        self, collection_id: str, payload: ApiMissingProviderPaymentSessionRequest
    ) -> ApiErrorResponse:
        response = self._client.post(
            f"/store/payment-collections/{collection_id}/payment-sessions",
            json=self._dump(payload),
        )
        if response.status_code != 400:
            response.raise_for_status()
        return self._error(response)

    def complete_cart(self, cart_id: str) -> ApiOrderResponse:
        response = self._client.post(f"/store/carts/{cart_id}/complete")
        response.raise_for_status()
        return ApiOrderResponse.model_validate(response.json())

    def complete_cart_error(self, cart_id: str) -> ApiErrorResponse:
        response = self._client.post(f"/store/carts/{cart_id}/complete")
        if response.status_code != 404:
            response.raise_for_status()
        return self._error(response)
