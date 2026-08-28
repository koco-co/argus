"""SMTP 邮件通知。"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from shared.notify.base import Notifier


class EmailNotifier(Notifier):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def send(self, message: str) -> None:
        mail = EmailMessage()
        mail["Subject"] = "Argus 自动化执行结果"
        mail["From"] = self.config["username"]
        mail["To"] = ", ".join(self.config["to"])
        mail.set_content(message)
        with smtplib.SMTP_SSL(
            self.config["smtp_host"], int(self.config.get("smtp_port", 465)), timeout=10
        ) as smtp:
            smtp.login(self.config["username"], self.config["password"])
            smtp.send_message(mail)
