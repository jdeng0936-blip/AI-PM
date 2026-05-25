"""
app/services/email_api.py — 邮件通知通道服务
实现 SMTP 发送邮件功能。
"""

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger("aipm.email_api")


def is_configured() -> bool:
    """检查邮件服务是否已配置 SMTP"""
    return bool(settings.smtp_server and settings.smtp_user and settings.smtp_password and settings.smtp_from_email)


def _send_email_sync(to_email: str, subject: str, content_markdown: str) -> None:
    """同步的内部发送邮件方法"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = to_email

    # 由于是 Markdown 格式，我们也可以简单做一下转义发送纯文本，或转 HTML
    # 这里我们直接当做纯文本发送，并在内容前加提示
    text_content = content_markdown

    part1 = MIMEText(text_content, "plain", "utf-8")
    msg.attach(part1)

    # 连接到 SMTP 服务器
    try:
        if settings.smtp_port in [465]:
            # SSL
            with smtplib.SMTP_SSL(settings.smtp_server, settings.smtp_port) as server:
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
        else:
            # STARTTLS
            with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        raise e


async def send_markdown_email(to_email: str, subject: str, content_markdown: str) -> None:
    """异步发送邮件"""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send_email_sync, to_email, subject, content_markdown)
