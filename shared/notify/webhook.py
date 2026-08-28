"""钉钉、飞书和企业微信机器人通知。"""

from __future__ import annotations

from typing import Any

import httpx

from shared.notify.base import Notifier


class WebhookNotifier(Notifier):
    def __init__(self, channel: str, webhook: str, client: httpx.Client | None = None) -> None:
        self.channel = channel
        self.webhook = webhook
        self.client = client or httpx.Client(timeout=10, trust_env=False)

    def _payload(self, message: str) -> dict[str, Any]:
        if self.channel == "feishu":
            return {"msg_type": "text", "content": {"text": message}}
        return {"msgtype": "text", "text": {"content": message}}

    def send(self, message: str) -> None:
        response = self.client.post(self.webhook, json=self._payload(message))
        response.raise_for_status()
        body = response.json() if response.content else {}
        code = body.get("errcode", body.get("code", 0)) if isinstance(body, dict) else 0
        if code not in {0, "0", None}:
            raise RuntimeError(f"{self.channel} webhook 返回错误码 {code}")
