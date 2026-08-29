"""通知构建、渠道注册、隔离重试与最新摘要解析。"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Mapping
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


def load_config(path: Path, *, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """读取本地配置，并用 CI 环境变量覆盖渠道秘密。

    GitHub Actions 只把 Secrets 注入环境，不生成携密文件；空环境变量视为未配置，
    以兼容 fork PR 和尚未启用通知的仓库。
    """
    if path.exists():
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        LOGGER.warning("通知配置不存在，尝试从环境变量装配：%s", path)
        document = {}
    if not isinstance(document, dict):
        raise ValueError("notify 配置顶层必须是映射")

    raw_channels = document.get("channels", {})
    if not isinstance(raw_channels, dict):
        raise ValueError("notify 配置 channels 必须是映射")
    channels = {
        str(name): dict(values) for name, values in raw_channels.items() if isinstance(values, dict)
    }
    env = os.environ if environ is None else environ

    for channel in ("dingtalk", "feishu", "wecom"):
        key = f"ARGUS_NOTIFY_{channel.upper()}_WEBHOOK"
        if value := env.get(key, "").strip():
            channels[channel] = {"webhook": value}

    email_env = {
        "smtp_host": env.get("ARGUS_NOTIFY_EMAIL_SMTP_HOST", "").strip(),
        "smtp_port": env.get("ARGUS_NOTIFY_EMAIL_SMTP_PORT", "").strip(),
        "username": env.get("ARGUS_NOTIFY_EMAIL_USERNAME", "").strip(),
        "password": env.get("ARGUS_NOTIFY_EMAIL_PASSWORD", "").strip(),
        "to": env.get("ARGUS_NOTIFY_EMAIL_TO", "").strip(),
    }
    if any(email_env.values()):
        email = dict(channels.get("email", {}))
        for key in ("smtp_host", "username", "password"):
            if email_env[key]:
                email[key] = email_env[key]
        if email_env["smtp_port"]:
            try:
                email["smtp_port"] = int(email_env["smtp_port"])
            except ValueError as exc:
                raise ValueError("邮件通知端口必须是整数") from exc
        if email_env["to"]:
            email["to"] = [item.strip() for item in email_env["to"].split(",") if item.strip()]
        required = ("smtp_host", "username", "password", "to")
        missing = [key for key in required if not email.get(key)]
        if missing:
            raise ValueError(f"邮件通知环境变量不完整，缺少：{', '.join(missing)}")
        channels["email"] = email

    return {**document, "channels": channels}
