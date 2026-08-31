"""钉钉、飞书和企业微信机器人通知。"""

from __future__ import annotations

from typing import Any

import httpx  # pyright: ignore[reportMissingImports]
from argus_core.parsing import load_json  # pyright: ignore[reportMissingImports]

from shared.notify.base import Notifier


class WebhookNotifier(Notifier):
    def __init__(
        self,
        channel: str,
        webhook: str | httpx.URL,
        client: httpx.Client | None = None,
    ) -> None:
        self.channel = channel
        self.webhook = webhook
        self.client = client or httpx.Client(timeout=10, trust_env=False)

    def _payload(self, message: str) -> dict[str, Any]:
        if self.channel == "feishu":
            return {"msg_type": "text", "content": {"text": message}}
        return {"msgtype": "text", "text": {"content": message}}

    def send(self, message: str) -> None:
        response = self.client.post(self.webhook, json=self._payload(message))
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # HTTPX 的默认异常会包含完整请求 URL；webhook URL 本身可能含密钥，
            # 因此只把状态码暴露给 dispatcher，不把异常原文带入日志。
            raise RuntimeError(
                f"{self.channel} webhook HTTP 状态 {exc.response.status_code}"
            ) from None
        try:
            body = load_json(response.content) if response.content else {}
        except (UnicodeError, ValueError) as exc:
            raise RuntimeError(f"{self.channel} webhook 返回了不安全的 JSON") from exc
        if not isinstance(body, dict):
            raise RuntimeError(f"{self.channel} webhook 返回了非对象 JSON")
        code = body.get("errcode", body.get("code", 0))
        success = (
            code is None or (type(code) is int and code == 0) or (type(code) is str and code == "0")
        )
        if not success:
            detail = str(code) if type(code) is int and abs(code) <= 10**9 else "non-zero"
            raise RuntimeError(f"{self.channel} webhook 返回错误码 {detail}")
