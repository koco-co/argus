"""API 自动化的 Medusa Store 客户端与种子夹具。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest  # pyright: ignore[reportMissingImports]
from argus_core.parsing import load_yaml  # pyright: ignore[reportMissingImports]

from automation.api.clients.checkout.store_client import FullStoreClient
from shared.config.settings import EnvConfig

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


def _runtime() -> dict[str, str]:
    values: dict[str, str] = {}
    path = _safe_file(REPO_ROOT / "target-app/runtime.env", "runtime.env")
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if key and "\x00" not in key and "\x00" not in value:
                values[key] = value
    return values


@pytest.fixture(scope="session")
def store_client(env_config: EnvConfig) -> Iterator[FullStoreClient]:
    runtime = _runtime()
    client = FullStoreClient(
        env_config.api_base_url or env_config.base_url,
        runtime["ARGUS_PUBLISHABLE_KEY"],
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def seed_state() -> dict[str, str]:
    document = load_yaml(
        _safe_file(REPO_ROOT / "target-app/seed-state.yaml", "seed-state").read_bytes()
    )
    if not isinstance(document, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in document.items()
    ):
        raise RuntimeError("seed-state 必须是字符串键值对象")
    return document


@pytest.fixture(scope="session")
def seed_registry() -> dict[str, Any]:
    document = load_yaml(
        _safe_file(REPO_ROOT / "shared/testdata/seed-registry.yaml", "seed registry").read_bytes()
    )
    if not isinstance(document, dict) or not isinstance(document.get("seeds"), dict):
        raise RuntimeError("seed registry 缺少 seeds 映射")
    return document["seeds"]
