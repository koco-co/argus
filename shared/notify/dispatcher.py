"""通知构建、渠道注册、隔离重试与最新摘要解析。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from shared.notify.base import Notifier
from shared.notify.email import EmailNotifier
from shared.notify.webhook import WebhookNotifier

LOGGER = logging.getLogger("argus.notify")


def newest_summary(iterations_dir: Path) -> Path:
    candidates = list(iterations_dir.glob("*/runs/*/run-summary.yaml"))
    if not candidates:
        raise FileNotFoundError(f"{iterations_dir} 下没有 run-summary.yaml")
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def render_summary(document: dict[str, Any], classification: str | None = None) -> str:
    status = classification or str(document.get("status", "unknown"))
    attempts = document.get("attempts", [])
    return "\n".join(
        [
            "Argus 自动化执行结果",
            f"迭代: {document.get('iteration_id', 'unknown')}",
            f"运行: {document.get('run_id', 'unknown')}",
            f"状态: {status}",
            f"模块: {', '.join(document.get('modules', []))}",
            f"尝试次数: {len(attempts)}",
        ]
    )


def build_notifiers(config: dict[str, Any]) -> dict[str, Notifier]:
    channels = config.get("channels", {})
    result: dict[str, Notifier] = {}
    for name, values in channels.items():
        if name in {"dingtalk", "feishu", "wecom"}:
            result[name] = WebhookNotifier(name, values["webhook"])
        elif name == "email":
            result[name] = EmailNotifier(values)
        else:
            LOGGER.warning("忽略未知通知渠道：%s", name)
    return result


def dispatch(
    message: str,
    notifiers: dict[str, Notifier],
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for name, notifier in notifiers.items():
        for index, delay in enumerate((1.0, 2.0, 4.0), start=1):
            try:
                notifier.send(message)
                results[name] = True
                break
            except Exception as exc:  # noqa: BLE001 - 渠道隔离边界必须吞并并记录所有异常
                LOGGER.error("通知渠道 %s 第 %d 次失败：%s", name, index, exc)
                if index < 3:
                    sleeper(delay)
        else:
            results[name] = False
    return results


def load_config(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise ValueError("notify 配置顶层必须是映射")
    return document
