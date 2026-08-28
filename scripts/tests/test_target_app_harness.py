"""Roadmap 5.0.1 靶应用锁定、生命周期和健康门禁测试。"""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import _load_script


@pytest.fixture(scope="module")
def harness() -> Any:
    return _load_script("_target_app")


def test_lockfile_pins_every_moving_dependency(harness: Any) -> None:
    lock = harness.load_lock()
    assert lock["medusa"]["version"] == "2.19.0"
    assert len(lock["medusa"]["commit"]) == 40
    assert lock["storefront"]["commit"] == lock["medusa"]["commit"]
    for component in ("node", "postgres", "redis"):
        assert "@sha256:" in lock[component]["image"]


def test_compose_declares_single_full_stack(harness: Any) -> None:
    document = yaml.safe_load(harness.COMPOSE_FILE.read_text(encoding="utf-8"))
    assert set(document["services"]) == {"postgres", "redis", "backend", "storefront"}
    assert document["services"]["postgres"]["ports"] == ["127.0.0.1:15432:5432"]
    assert document["services"]["backend"]["ports"] == ["9000:9000"]
    assert document["services"]["storefront"]["ports"] == ["8000:8000"]


def test_backend_override_disables_internal_database_ssl() -> None:
    """Compose 服务名不是 localhost，必须显式关闭本地 PostgreSQL 的 SSL。"""
    root = Path(__file__).resolve().parents[2]
    config = (root / "target-app/overrides/medusa-config.ts").read_text(encoding="utf-8")
    dockerfile = (root / "target-app/Dockerfile").read_text(encoding="utf-8")
    assert "databaseDriverOptions" in config
    assert "ssl: false" in config
    assert "COPY overrides/medusa-config.ts" in dockerfile


def test_storefront_splits_internal_and_browser_backend_addresses(harness: Any) -> None:
    document = yaml.safe_load(harness.COMPOSE_FILE.read_text(encoding="utf-8"))
    environment = document["services"]["storefront"]["environment"]
    assert environment["MEDUSA_INTERNAL_BACKEND_URL"] == "http://backend:9000"
    assert environment["NEXT_PUBLIC_MEDUSA_BACKEND_URL"] == "http://localhost:9000"
    dockerfile = (harness.TARGET_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "process.env.MEDUSA_INTERNAL_BACKEND_URL" in dockerfile


def test_api_fixture_uses_environment_api_base_url() -> None:
    """生成 API 夹具不得硬编码靶场后端地址。"""
    root = Path(__file__).resolve().parents[2]
    source = (root / "automation/api/conftest.py").read_text(encoding="utf-8")
    assert "env_config.api_base_url" in source
    assert "http://localhost:9000" not in source


def test_up_rebuilds_backend_before_migration() -> None:
    up_script = (Path(__file__).resolve().parents[1] / "target_app_up.py").read_text(
        encoding="utf-8"
    )
    assert 'compose(["build", "backend"])' in up_script
    assert up_script.index('compose(["build", "backend"])') < up_script.index('"db:migrate"')
    assert '"./src/migration-scripts/initial-data-seed.ts"' not in up_script


def test_up_provisions_readonly_role_after_migration() -> None:
    """只读角色必须在业务表迁移完成后、测试 seed 前创建并授权。"""
    source = (Path(__file__).resolve().parents[1] / "target_app_up.py").read_text(encoding="utf-8")
    assert "ensure_readonly_role" in source
    assert source.index('"db:migrate"') < source.index("ensure_readonly_role()")
    assert source.index("ensure_readonly_role()") < source.index("seed()")


def test_readonly_role_contract_is_fail_closed(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """本地数据库角色同时具备 SELECT 授权和事务级只读兜底。"""
    captured: list[list[str]] = []

    def fake_compose(arguments: list[str], **_: Any) -> Any:
        captured.append(arguments)

        class Result:
            returncode = 1 if "CREATE TABLE public.argus_readonly_probe" in arguments[-1] else 0
            stdout = "" if returncode else "t|t|t\n"
            stderr = (
                "ERROR: cannot execute CREATE TABLE in a read-only transaction"
                if returncode
                else ""
            )

        return Result()

    monkeypatch.setattr(harness, "compose", fake_compose)
    harness.ensure_readonly_role()
    harness.verify_readonly_role()

    provision_sql = captured[0][-1]
    assert "GRANT SELECT ON ALL TABLES" in provision_sql
    assert "ALTER DEFAULT PRIVILEGES" in provision_sql
    assert "default_transaction_read_only = on" in provision_sql
    assert "NOSUPERUSER" in provision_sql
    verification_sql = captured[1][-1]
    assert "default_transaction_read_only" in verification_sql
    for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        assert f"'{privilege}'" in verification_sql
    assert "CREATE TABLE public.argus_readonly_probe" in captured[2][-1]


def test_runtime_env_is_private_and_stable(harness: Any, tmp_path: Path) -> None:
    path = tmp_path / "runtime.env"
    first = harness.ensure_runtime_env(path)
    second = harness.ensure_runtime_env(path)
    assert first == second
    assert first["ARGUS_ADMIN_EMAIL"].endswith("@example.invalid")
    assert first["JWT_SECRET"] != "CHANGE_ME"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_local_http_clients_do_not_inherit_host_proxy() -> None:
    root = Path(__file__).resolve().parents[2]
    helper = (root / "scripts/_target_app.py").read_text(encoding="utf-8")
    seed = (root / "scripts/target_app_seed.py").read_text(encoding="utf-8")
    assert "trust_env=False" in helper
    assert seed.count("trust_env=False") == 2


def test_compose_environment_comes_from_lockfile(harness: Any, tmp_path: Path) -> None:
    runtime = harness.ensure_runtime_env(tmp_path / "runtime.env")
    environment = harness.compose_environment(harness.load_lock(), runtime)
    assert environment["NODE_IMAGE"].startswith("node:22.12.0-bookworm-slim@sha256:")
    assert environment["POSTGRES_IMAGE"].startswith("postgres:17.6-alpine3.22@sha256:")
    assert environment["REDIS_IMAGE"].startswith("redis:7.4.6-alpine3.21@sha256:")
    assert environment["DTC_COMMIT"] == "cb603dfda0a82e8bb5e81622f295e0ff90ac6913"


def test_down_defaults_to_removing_harness_volumes(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[list[str]] = []

    def fake_run(args: list[str], **_: Any) -> Any:
        captured.append(args)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(harness.subprocess, "run", fake_run)
    harness.compose(["down", "--volumes", "--remove-orphans"])
    assert captured[0][-3:] == ["down", "--volumes", "--remove-orphans"]


def test_seed_registry_covers_declared_entities() -> None:
    registry_path = Path(__file__).resolve().parents[2] / "shared/testdata/seed-registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    required = {
        "region_europe",
        "currency_eur",
        "currency_usd",
        "product_tshirt",
        "inventory_tshirt_s_black",
        "shipping_standard",
        "payment_manual",
        "customer_argus",
        "discount_argus10",
        "product_price_eur",
        "product_price_usd",
        "discounted_total",
    }
    assert required <= set(registry["seeds"])
    assert all(seed.get("type") for seed in registry["seeds"].values())


def test_discount_total_is_derived_from_seed_values() -> None:
    seed = _load_script("target_app_seed")
    assert seed.discounted_total(price=10, percentage=10) == 9


def test_seed_canary_turns_red_when_registry_price_is_corrupted() -> None:
    canary = _load_script("target_app_canary")
    registry = canary.load_registry()
    assert canary.verify_oracle(registry, live_price=10, live_percentage=10) == 9
    corrupted = yaml.safe_load(yaml.safe_dump(registry))
    corrupted["seeds"]["product_price_eur"]["value"] = 11
    with pytest.raises(canary.CanaryError, match="价格不一致"):
        canary.verify_oracle(corrupted, live_price=10, live_percentage=10)


def test_seed_queries_relations_from_supported_admin_resources() -> None:
    source = (Path(__file__).resolve().parents[1] / "target_app_seed.py").read_text(
        encoding="utf-8"
    )
    assert 'fields="+payment_providers.*"' in source
    assert 'fields="+variants.*,+variants.inventory_items.*"' in source
    assert 'admin.get("/admin/payment-providers"' not in source


def test_seed_state_rejects_entity_id_drift(tmp_path: Path) -> None:
    seed = _load_script("target_app_seed")
    state_path = tmp_path / "seed-state.yaml"
    seed.assert_stable_state({"product_tshirt": "prod_1"}, state_path)
    seed.assert_stable_state({"product_tshirt": "prod_1"}, state_path)
    with pytest.raises(seed.SeedError, match="不稳定"):
        seed.assert_stable_state({"product_tshirt": "prod_2"}, state_path)
