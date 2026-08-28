"""Web 自动化的靶场种子夹具。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def seed_registry() -> dict[str, Any]:
    return yaml.safe_load(
        (REPO_ROOT / "shared/testdata/seed-registry.yaml").read_text(encoding="utf-8")
    )["seeds"]


@pytest.fixture
def guest_address(worker_namespace: str) -> dict[str, str]:
    """纯虚构且按 worker 隔离的游客地址，不产生真实个人信息。"""

    return {
        "first_name": "Argus",
        "last_name": "Guest",
        "address_1": "1 Test Street",
        "company": "Argus Test",
        "postal_code": "1000",
        "city": "Copenhagen",
        "province": "Hovedstaden",
        "country_code": "dk",
        "email": f"{worker_namespace}@example.invalid",
        "phone": "+4512345678",
    }
