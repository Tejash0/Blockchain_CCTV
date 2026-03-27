"""
Email alert sender for incident notifications.
Uses Python built-in smtplib — no extra dependency required.
Configure via ai-service/.env (ALERT_EMAIL_* variables).
"""
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_incident_email(
    smtp_host: str,
    smtp_port: int,
    sender: str,
    password: str,
    recipients: list[str],
    camera_id: str,
    event_type: str,
    confidence: float,
    video_hash: str,
    transaction_hash: str = "",
    timestamp: float = 0.0,
):
    """
    Send an incident alert email after blockchain confirmation.
    Returns True on success, False on any failure (never raises).
    """
    if not smtp_host or not sender or not password or not recipients:
        print("Email alert skipped — SMTP not configured in .env")
        return False

    try:
        dt = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "N/A"
        confidence_pct = f"{confidence * 100:.1f}%"
        tx_line = f"Transaction Hash : {transaction_hash}" if transaction_hash else "Transaction      : Pending / unavailable"

        subject = f"[CCTV Alert] {event_type.upper()} detected — {camera_id}"

        body = f"""\
INCIDENT ALERT — Blockchain CCTV Verification System
=====================================================

Camera ID        : {camera_id}
Event Type       : {event_type}
Confidence       : {confidence_pct}
Detected At      : {dt}

Video Hash       : {video_hash}
{tx_line}

This clip has been cryptographically hashed and recorded on the blockchain.
Use the Verifier page to confirm authenticity at any time.

-- Blockchain CCTV System (automated alert)
"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(body, "plain"))

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())

        print(f"Incident email sent to {recipients}")
        return True

    except Exception as e:
        print(f"Failed to send incident email: {e}")
        return False
