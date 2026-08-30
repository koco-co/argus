#!/usr/bin/env python
"""通过 Medusa Admin API 幂等补齐并验证 Argus seed 基线。"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx  # pyright: ignore[reportMissingImports]
import yaml  # pyright: ignore[reportMissingModuleSource]
from _target_app import (
    RUNTIME_ENV,
    TARGET_DIR,
    _assert_safe_path,
    ensure_runtime_env,
    wait_http,
    write_runtime_env,
)
from argus_core.parsing import load_json, load_yaml  # pyright: ignore[reportMissingImports]

BACKEND_URL = "http://127.0.0.1:9000"
SEED_STATE = TARGET_DIR / "seed-state.yaml"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class SeedError(RuntimeError):
    """Seed 无法收敛或运行实例不符合锁定契约。"""


def discounted_total(price: int | float, percentage: int | float) -> Decimal:
    """从运行时 seed 值计算折后总额，测试不能复制结果常量。"""
    amount = Decimal(str(price))
    rate = Decimal(str(percentage))
    return (amount * (Decimal(100) - rate) / Decimal(100)).quantize(Decimal("0.01"))


def assert_stable_state(state: dict[str, str], path: Path = SEED_STATE) -> None:
    """重复 reset 必须返回同一组实体 ID，否则拒绝假称幂等。"""
    _assert_safe_path(path, label="seed state")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise SeedError(f"seed 状态文件必须是安全的普通文件：{path}")
    if path.is_file():
        try:
            previous = load_yaml(path.read_bytes()) or {}
        except (OSError, UnicodeError, ValueError) as exc:
            raise SeedError("seed 状态文件不是安全可解析的 YAML 文档") from exc
        if previous != state:
            raise SeedError("seed 实体 ID 不稳定；请清理靶场状态后重新 seed")
        return
    path.write_text(yaml.safe_dump(state, sort_keys=True), encoding="utf-8")


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = load_json(response.content)
    except (UnicodeError, ValueError) as exc:
        raise SeedError("Medusa Admin API 返回了不安全的 JSON") from exc
    if not isinstance(payload, dict):
        raise SeedError("Medusa Admin API 响应顶层必须是对象")
    return payload


class AdminClient:
    """只封装本地 Medusa Admin API；响应形状不匹配时立即失败。"""

    def __init__(self, email: str, password: str) -> None:
        self.client = httpx.Client(base_url=BACKEND_URL, timeout=30.0, trust_env=False)
        try:
            response = self.client.post(
                "/auth/user/emailpass", json={"email": email, "password": password}
            )
            self._raise(response, "管理员登录")
            token = _response_json(response).get("token")
            if not isinstance(token, str) or not token:
                raise SeedError("管理员登录响应缺少有效 token")
            self.client.headers.update({"Authorization": f"Bearer {token}"})
        except Exception:
            self.client.close()
            raise

    @staticmethod
    def _raise(response: httpx.Response, operation: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SeedError(f"{operation}失败：HTTP {response.status_code}") from exc

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        response = self.client.get(path, params=params or None)
        self._raise(response, f"GET {path}")
        return _response_json(response)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(path, json=payload)
        self._raise(response, f"POST {path}")
        return _response_json(response)

    def close(self) -> None:
        self.client.close()


def _items(document: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = document.get(key)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise SeedError(f"Admin API 响应缺少有效的 {key}[]")
    return value


def _find(items: list[dict[str, Any]], field: str, value: Any, label: str) -> dict[str, Any]:
    item = next((candidate for candidate in items if candidate.get(field) == value), None)
    if item is None:
        raise SeedError(f"缺少 seed {label}：{field}={value!r}")
    return item


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise SeedError(f"{label} 响应缺少安全的实体 ID")
    return value


def _response_object(document: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise SeedError(f"{label} 响应缺少有效的 {key} 对象")
    return value


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
    channel_id = _safe_id(channel.get("id"), "默认销售渠道")
    created_document = admin.post(
        "/admin/api-keys", {"title": "Argus Local Storefront", "type": "publishable"}
    )
    created = _response_object(created_document, "api_key", "publishable API key")
    key_id = _safe_id(created.get("id"), "publishable API key")
    token = created.get("token")
    if not isinstance(token, str) or not token:
        raise SeedError("创建 publishable API key 的响应缺少有效 token")
    admin.post(f"/admin/api-keys/{key_id}/sales-channels", {"add": [channel_id]})
    return token


def _ensure_customer(admin: AdminClient) -> dict[str, Any]:
    email = "argus-customer@example.invalid"
    customers = _items(admin.get("/admin/customers", limit=100), "customers")
    existing = next((customer for customer in customers if customer.get("email") == email), None)
    if existing:
        return existing
    return _response_object(
        admin.post(
            "/admin/customers",
            {"email": email, "first_name": "Argus", "last_name": "Customer"},
        ),
        "customer",
        "customer",
    )


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
    return _response_object(admin.post("/admin/promotions", payload), "promotion", "promotion")


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
        providers = _items(region, "payment_providers")
        provider = _find(providers, "id", "pp_system_default", "手工支付提供者")
        customer = _ensure_customer(admin)
        promotion = _ensure_promotion(admin)
        publishable_key = _publishable_key(admin, runtime)
    except (KeyError, TypeError) as exc:
        raise SeedError("Medusa Admin API 响应形状不符合 seed 契约") from exc
    finally:
        admin.close()

    variants = _items(product, "variants")
    variant = _find(variants, "sku", "SHIRT-S-BLACK", "黑色 S 码变体")
    inventory_items = variant.get("inventory_items", [])
    if not isinstance(inventory_items, list) or any(
        not isinstance(item, dict) for item in inventory_items
    ):
        raise SeedError("黑色 S 码变体响应缺少有效 inventory_items[]")
    inventory_id = inventory_items[0].get("id") if inventory_items else variant.get("id")
    state = {
        "customer_argus": _safe_id(customer.get("id"), "Argus customer"),
        "discount_argus10": _safe_id(promotion.get("id"), "ARGUS10 promotion"),
        "inventory_tshirt_s_black": _safe_id(inventory_id, "黑色 S 码库存"),
        "payment_manual": _safe_id(provider.get("id"), "手工支付提供者"),
        "product_tshirt": _safe_id(product.get("id"), "T-Shirt 产品"),
        "region_europe": _safe_id(region.get("id"), "Europe 区域"),
        "shipping_standard": _safe_id(shipping_option.get("id"), "Standard Shipping"),
    }
    assert_stable_state(state)
    runtime["ARGUS_PUBLISHABLE_KEY"] = publishable_key
    runtime["NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY"] = publishable_key
    write_runtime_env(runtime, RUNTIME_ENV)
    print("Medusa seed 已通过 Admin API 收敛，实体 ID 保持稳定")
    return state


def main() -> int:
    try:
        seed()
    except Exception:  # noqa: BLE001 - CLI 边界只输出稳定的脱敏错误
        print("Medusa seed 失败：靶应用不可用或响应未通过安全校验")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
