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
