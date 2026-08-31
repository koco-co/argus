"""Web 自动化的靶场种子夹具。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest  # pyright: ignore[reportMissingImports]
from argus_core.parsing import load_yaml  # pyright: ignore[reportMissingImports]

REPO_ROOT = Path(__file__).resolve().parents[2]


def _safe_file(path: Path, label: str) -> Path:
    if "\x00" in str(path) or "\\" in str(path) or ".." in path.parts:
        raise RuntimeError(f"{label} 路径不安全")
    current = Path(path.anchor)
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise RuntimeError(f"{label} 不得经过符号链接")
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} 必须是安全的普通文件")
    return path


@pytest.fixture(scope="session")
def seed_registry() -> dict[str, Any]:
    document = load_yaml(
        _safe_file(REPO_ROOT / "shared/testdata/seed-registry.yaml", "seed registry").read_bytes()
    )
    if not isinstance(document, dict) or not isinstance(document.get("seeds"), dict):
        raise RuntimeError("seed registry 缺少 seeds 映射")
    return document["seeds"]


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
