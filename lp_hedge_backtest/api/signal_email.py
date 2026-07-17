"""Email notifications for Signal Lab events.
Falls back to Telegram push (admin chat IDs) when SMTP fails.
"""
import os
import smtplib
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from api.email_config import load_email_config

_RECIPIENTS  = [
    r.strip()
    for r in os.getenv("EMAIL_RECIPIENTS", "perdomo.gustavo@gmail.com").split(",")
    if r.strip()
]
_TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TG_CHATS = [
    c.strip()
    for c in os.getenv("ADMIN_TELEGRAM_CHAT_IDS", "").split(",")
    if c.strip()
]


def check_smtp() -> bool:
    """Returns True if SMTP credentials are currently valid."""
    cfg = load_email_config()
    if not cfg:
        return False
    try:
        s = smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"])
        s.starttls()
        s.login(cfg["smtp_username"], cfg["smtp_password"])
        s.quit()
        return True
    except Exception:
        return False


def _tg_fallback(subject: str, body: str) -> None:
    """Push a Telegram message to admin chats when email is unavailable."""
    if not _TG_TOKEN or not _TG_CHATS:
        return
    text = f"🔴 [Signal Lab — email DOWN]\n{subject}\n\n{body}"
    for chat_id in _TG_CHATS:
        try:
            data = urllib.parse.urlencode({
                "chat_id": chat_id,
                "text":    text,
            }).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
                data=data,
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            print(f"📨 [Signal Lab] Telegram fallback sent to chat {chat_id}", flush=True)
        except Exception as te:
            print(f"❌ [Signal Lab] Telegram fallback failed for {chat_id}: {te}", flush=True)


def send_signal_email(subject: str, body: str) -> None:
    """Fire-and-forget email. Falls back to Telegram push on SMTP failure."""
    cfg = load_email_config()
    if not cfg:
        print("[Signal Lab] Email skipped — config not found", flush=True)
        _tg_fallback(subject, body)
        return
    try:
        msg = MIMEMultipart()
        msg["From"]    = cfg["sender_email"]
        msg["To"]      = ", ".join(_RECIPIENTS)
        msg["Subject"] = f"🧪 [Signal Lab] {subject}"
        msg.attach(MIMEText(body, "plain"))
        s = smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"])
        s.starttls()
        s.login(cfg["smtp_username"], cfg["smtp_password"])
        s.send_message(msg)
        s.quit()
        print(f"📧 [Signal Lab] Email sent: {subject}", flush=True)
    except Exception as e:
        print(f"❌ [Signal Lab] Email failed: {e}", flush=True)
        _tg_fallback(subject, body)
