"""自动化根夹具：生产只读收集门禁与 xdist worker 隔离。"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

import httpx
import pytest

from shared.config.settings import EnvConfig, load_env


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """PROD 环境仅保留显式标注 ``read_only`` 的用例。"""

    if os.environ.get("TEST_ENV", "local").lower() != "prod":
        return
    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        (selected if item.get_closest_marker("read_only") else deselected).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected


def build_worker_namespace(run_id: str, worker_id: str) -> str:
    """构造只含安全字符且跨 worker 不相撞的运行命名空间。"""

    raw = f"{run_id}-{worker_id}".lower()
    return re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")


@pytest.fixture(scope="session")
def env_config() -> EnvConfig:
    """每个 xdist worker 独立加载一份不可共享的配置对象。"""

    return load_env()


@pytest.fixture(scope="session")
def worker_namespace(worker_id: str) -> str:
    """xdist 同一轮共享 run id、各 worker 拥有独立后缀。"""

    run_id = os.environ.get("ARGUS_RUN_ID") or os.environ.get(
        "PYTEST_XDIST_TESTRUNUID", "local-run"
    )
    return build_worker_namespace(run_id, worker_id)


@pytest.fixture(scope="session")
def isolated_http_session(env_config: EnvConfig) -> Iterator[httpx.Client]:
    """每个 worker 创建并销毁自己的 HTTP 会话，禁止跨进程共享状态。"""

    with httpx.Client(base_url=env_config.base_url, timeout=10, trust_env=False) as client:
        yield client
