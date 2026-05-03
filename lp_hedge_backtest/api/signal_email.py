"""
Email notifications for Signal Lab events.
Reuses the same email_config.json as the LP hedge bots.
"""
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_CONFIG_PATH = os.getenv("EMAIL_CONFIG_PATH", "/var/www/dev/trading/email_config.json")
_RECIPIENTS  = [
    r.strip()
    for r in os.getenv("EMAIL_RECIPIENTS", "perdomo.gustavo@gmail.com").split(",")
    if r.strip()
]


def _load_cfg():
    try:
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def send_signal_email(subject: str, body: str) -> None:
    """Fire-and-forget email. Logs failure but never raises."""
    cfg = _load_cfg()
    if not cfg:
        print("[Signal Lab] Email skipped — config not found", flush=True)
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
