# send_newsletter.py — TLCA auto-email via Gmail SMTP
from __future__ import annotations

import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# --- Config ---
GMAIL_USER = os.getenv("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").strip()
RECIPIENTS = [address.strip() for address in os.getenv("INTEL_RECIPIENTS", "").split(",") if address.strip()]

OUT_DIR = Path(os.getenv("INTEL_OUT_DIR", "output"))
EDITION = os.getenv("INTEL_EDITION", "1")
SUBJECT_PREFIX = os.getenv("INTEL_SUBJECT_PREFIX", "Global Competitor Intelligence Brief - GBS | GCC | Agentic AI")


def now_date() -> str:
    return datetime.now(timezone.utc).strftime("%d %B %Y")


def get_newsletter_html() -> str | None:
    path = OUT_DIR / "newsletter_full.html"
    if not path.exists():
        print(f"[WARN] Newsletter not found at {path}")
        return None
    return path.read_text(encoding="utf-8")


def send_newsletter() -> bool:
    if not GMAIL_USER or "@" not in GMAIL_USER:
        print("[ERROR] GMAIL_USER must be a valid email address.")
        return False

    if not GMAIL_APP_PASSWORD:
        print("[ERROR] GMAIL_APP_PASSWORD not set. Export it and retry.")
        return False

    if not RECIPIENTS:
        print("[ERROR] INTEL_RECIPIENTS must contain at least one email address.")
        return False

    html = get_newsletter_html()
    if not html:
        return False

    subject = f"{SUBJECT_PREFIX} | {now_date()} | Edition {EDITION}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(RECIPIENTS)

    # Plain text fallback
    plain = f"Weekly Competitor Intelligence Brief\n{now_date()} | Edition {EDITION}\n\nPlease view this email in an HTML-capable client."
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, RECIPIENTS, msg.as_string())

        print(f"[OK] Newsletter sent to: {', '.join(RECIPIENTS)}")
        print(f"     Subject: {subject}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("[ERROR] Gmail authentication failed. Check GMAIL_APP_PASSWORD.")
        return False
    except Exception as e:
        print(f"[ERROR] Failed to send: {e}")
        return False


if __name__ == "__main__":
    success = send_newsletter()
    raise SystemExit(0 if success else 1)
