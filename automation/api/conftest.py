"""API 自动化的 Medusa Store 客户端与种子夹具。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from automation.api.clients.checkout.store_client import StoreClient

REPO_ROOT = Path(__file__).resolve().parents[2]


def _runtime() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (REPO_ROOT / "target-app/runtime.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


@pytest.fixture(scope="session")
def store_client() -> Iterator[StoreClient]:
    runtime = _runtime()
    client = StoreClient("http://localhost:9000", runtime["ARGUS_PUBLISHABLE_KEY"])
    yield client
    client.close()


@pytest.fixture(scope="session")
def seed_state() -> dict[str, str]:
    return yaml.safe_load((REPO_ROOT / "target-app/seed-state.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def seed_registry() -> dict[str, Any]:
    return yaml.safe_load(
        (REPO_ROOT / "shared/testdata/seed-registry.yaml").read_text(encoding="utf-8")
    )["seeds"]
