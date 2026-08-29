#!/usr/bin/env python
"""通过 Medusa Admin API 幂等补齐并验证 Argus seed 基线。"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import yaml
from _target_app import (
    RUNTIME_ENV,
    TARGET_DIR,
    ensure_runtime_env,
    wait_http,
    write_runtime_env,
)

BACKEND_URL = "http://127.0.0.1:9000"
SEED_STATE = TARGET_DIR / "seed-state.yaml"


class SeedError(RuntimeError):
    """Seed 无法收敛或运行实例不符合锁定契约。"""


def discounted_total(price: int | float, percentage: int | float) -> Decimal:
    """从运行时 seed 值计算折后总额，测试不能复制结果常量。"""
    amount = Decimal(str(price))
    rate = Decimal(str(percentage))
    return (amount * (Decimal(100) - rate) / Decimal(100)).quantize(Decimal("0.01"))


def assert_stable_state(state: dict[str, str], path: Path = SEED_STATE) -> None:
    """重复 reset 必须返回同一组实体 ID，否则拒绝假称幂等。"""
    if path.exists():
        previous = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if previous != state:
            raise SeedError(f"seed 实体 ID 不稳定：previous={previous}, current={state}")
        return
    path.write_text(yaml.safe_dump(state, sort_keys=True), encoding="utf-8")


class AdminClient:
    """只封装本地 Medusa Admin API；响应形状不匹配时立即失败。"""

    def __init__(self, email: str, password: str) -> None:
        self.client = httpx.Client(base_url=BACKEND_URL, timeout=30.0, trust_env=False)
        response = self.client.post(
            "/auth/user/emailpass", json={"email": email, "password": password}
        )
        self._raise(response, "管理员登录")
        token = response.json().get("token")
        if not token:
            raise SeedError("管理员登录响应缺少 token")
        self.client.headers["Authorization"] = f"Bearer {token}"

    @staticmethod
    def _raise(response: httpx.Response, operation: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SeedError(
                f"{operation}失败：HTTP {response.status_code} {response.text[:500]}"
            ) from exc

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        response = self.client.get(path, params=params or None)
        self._raise(response, f"GET {path}")
        return response.json()

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(path, json=payload)
        self._raise(response, f"POST {path}")
        return response.json()

    def close(self) -> None:
        self.client.close()


def _items(document: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = document.get(key)
    if not isinstance(value, list):
        raise SeedError(f"Admin API 响应缺少 {key}[]")
    return value


def _find(items: list[dict[str, Any]], field: str, value: Any, label: str) -> dict[str, Any]:
    item = next((candidate for candidate in items if candidate.get(field) == value), None)
    if item is None:
        raise SeedError(f"缺少 seed {label}：{field}={value!r}")
    return item


def _publishable_key(admin: AdminClient, runtime: dict[str, str]) -> str:
    existing = runtime.get("ARGUS_PUBLISHABLE_KEY", "")
    if existing and existing != "pk_pending":
        with httpx.Client(timeout=20.0, trust_env=False) as client:
            response = client.get(
                f"{BACKEND_URL}/store/products",
                headers={"x-publishable-api-key": existing},
            )
        if response.status_code < 400:
            return existing

    channels = _items(admin.get("/admin/sales-channels", limit=100), "sales_channels")
    channel = _find(channels, "name", "Default Sales Channel", "默认销售渠道")
    created = admin.post(
        "/admin/api-keys", {"title": "Argus Local Storefront", "type": "publishable"}
    ).get("api_key", {})
    key_id, token = created.get("id"), created.get("token")
    if not key_id or not token:
        raise SeedError("创建 publishable API key 的响应缺少 id/token")
    admin.post(f"/admin/api-keys/{key_id}/sales-channels", {"add": [channel["id"]]})
    return str(token)


def _ensure_customer(admin: AdminClient) -> dict[str, Any]:
    email = "argus-customer@example.invalid"
    customers = _items(admin.get("/admin/customers", limit=100), "customers")
    existing = next((customer for customer in customers if customer.get("email") == email), None)
    if existing:
        return existing
    return admin.post(
        "/admin/customers",
        {"email": email, "first_name": "Argus", "last_name": "Customer"},
    )["customer"]


def _ensure_promotion(admin: AdminClient) -> dict[str, Any]:
    promotions = _items(admin.get("/admin/promotions", limit=100), "promotions")
    existing = next(
        (promotion for promotion in promotions if promotion.get("code") == "ARGUS10"),
        None,
    )
    if existing:
        return existing
    payload = {
        "code": "ARGUS10",
        "type": "standard",
        "status": "active",
        "application_method": {
            "description": "Argus 本地验收九折优惠",
            "value": 10,
            "currency_code": "eur",
            "type": "percentage",
            "target_type": "order",
            "allocation": "across",
        },
    }
    return admin.post("/admin/promotions", payload)["promotion"]


def seed() -> dict[str, str]:
    """验证官方 starter 基线，并经 Admin API 幂等创建用户侧实体。"""
    wait_http(f"{BACKEND_URL}/health", timeout=180)
    runtime = ensure_runtime_env()
    admin = AdminClient(runtime["ARGUS_ADMIN_EMAIL"], runtime["ARGUS_ADMIN_PASSWORD"])
    try:
        regions = _items(
            admin.get("/admin/regions", limit=100, fields="+payment_providers.*"),
            "regions",
        )
        region = _find(regions, "name", "Europe", "欧洲区域")
        products = _items(
            admin.get(
                "/admin/products",
                limit=100,
                fields="+variants.*,+variants.inventory_items.*",
            ),
            "products",
        )
        product = _find(products, "handle", "t-shirt", "T-Shirt 产品")
        shipping = _items(admin.get("/admin/shipping-options", limit=100), "shipping_options")
        shipping_option = _find(shipping, "name", "Standard Shipping", "标准配送")
        providers = region.get("payment_providers", [])
        if not isinstance(providers, list):
            raise SeedError("Europe 区域响应缺少 payment_providers[]")
        provider = _find(providers, "id", "pp_system_default", "手工支付提供者")
        customer = _ensure_customer(admin)
        promotion = _ensure_promotion(admin)
        publishable_key = _publishable_key(admin, runtime)
    finally:
        admin.close()

    variant = _find(product.get("variants", []), "sku", "SHIRT-S-BLACK", "黑色 S 码变体")
    state = {
        "customer_argus": str(customer["id"]),
        "discount_argus10": str(promotion["id"]),
        "inventory_tshirt_s_black": str(
            variant.get("inventory_items", [{}])[0].get("id", variant["id"])
        ),
        "payment_manual": str(provider["id"]),
        "product_tshirt": str(product["id"]),
        "region_europe": str(region["id"]),
        "shipping_standard": str(shipping_option["id"]),
    }
    assert_stable_state(state)
    runtime["ARGUS_PUBLISHABLE_KEY"] = publishable_key
    runtime["NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY"] = publishable_key
    write_runtime_env(runtime, RUNTIME_ENV)
    print("Medusa seed 已通过 Admin API 收敛，实体 ID 保持稳定")
    return state


def main() -> int:
    seed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
