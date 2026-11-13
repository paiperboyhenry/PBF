"""Outbound notifications. Nothing here is assumed to work: each send records its real outcome."""
from __future__ import annotations

import json
import logging
import smtplib
import threading
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app

from . import settings
from .db import get_db, now_iso, q
from .util import json_list

log = logging.getLogger("pbf.mail")


def smtp_configured() -> bool:
    cfg = current_app.config
    return bool(cfg["SMTP_HOST"] and cfg["MAIL_FROM"])


def webhook_configured() -> bool:
    return bool(current_app.config["NOTIFY_WEBHOOK_URL"])


def send_mail(to: str, subject: str, body: str, reply_to: str = "") -> None:
    cfg = current_app.config
    msg = EmailMessage()
    msg["From"] = cfg["MAIL_FROM"]
    msg["To"] = to
    msg["Subject"] = subject.replace("\n", " ")[:200]
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    if cfg["SMTP_SSL"]:
        client = smtplib.SMTP_SSL(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15)
    else:
        client = smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15)
    with client:
        if cfg["SMTP_STARTTLS"] and not cfg["SMTP_SSL"]:
            client.starttls()
        if cfg["SMTP_USER"]:
            client.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
        client.send_message(msg)


def _summary(e) -> str:
    services = ", ".join(json_list(e["services"])) or "—"
    if e["service_other"]:
        services += f" (other: {e['service_other']})"
    links = "\n  ".join(json_list(e["reference_links"])) or "—"
    return (
        f"Reference: {e['ref']}\n"
        f"Name: {e['full_name']}\n"
        f"Business: {e['business_name'] or '—'}\n"
        f"Email: {e['email']}\n"
        f"WhatsApp: {e['whatsapp'] or '—'}\n"
        f"Country: {e['country'] or '—'}\n"
        f"Services: {services}\n"
        f"Budget: {e['budget'] or 'Not given'}\n"
        f"Timeline: {e['timeline'] or 'Not given'}\n"
        f"Reference links:\n  {links}\n\n"
        f"Project description:\n{e['description']}\n\n"
        f"Additional notes:\n{e['extra_notes'] or '—'}\n"
    )


def _set_status(enquiry_id: int, column: str, value: str) -> None:
    assert column in {"ack_status", "notify_status"}
    db = get_db()
    db.execute(f"UPDATE enquiries SET {column} = ?, updated_at = ? WHERE id = ?", (value, now_iso(), enquiry_id))
    db.commit()


def _deliver(enquiry_id: int) -> None:
    """Runs inside an app context. Records 'sent' or 'failed' honestly for each channel."""
    e = q("SELECT * FROM enquiries WHERE id = ?", (enquiry_id,), one=True)
    if not e:
        return
    s = settings.load()
    notify_to = s.get("notify_email") or s.get("contact_email")

    # Studio notification: email and/or webhook
    outcomes = []
    if smtp_configured() and notify_to:
        try:
            send_mail(notify_to, f"New enquiry {e['ref']} — {e['full_name']}", _summary(e), reply_to=e["email"])
            outcomes.append(True)
        except Exception:  # noqa: BLE001 - any delivery failure is recorded, never raised to the visitor
            log.exception("Studio notification email failed for %s", e["ref"])
            outcomes.append(False)
    if webhook_configured():
        text = f"New PBF Studio enquiry {e['ref']} from {e['full_name']} ({e['email']})"
        payload = json.dumps({"text": text, "content": text}).encode()
        req = urllib.request.Request(
            current_app.config["NOTIFY_WEBHOOK_URL"], data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=8):  # noqa: S310 (URL comes from server config only)
                outcomes.append(True)
        except (urllib.error.URLError, TimeoutError, ValueError):
            log.exception("Webhook notification failed for %s", e["ref"])
            outcomes.append(False)
    if outcomes:
        _set_status(enquiry_id, "notify_status", "sent" if all(outcomes) else "failed")

    # Client acknowledgement
    if smtp_configured():
        body = (
            f"Hello {e['full_name']},\n\n"
            "Thank you for getting in touch with PBF Studio. We have received your project enquiry "
            f"(reference {e['ref']}) and will come back to you personally.\n\n"
            "Here is a copy of what you sent us:\n\n"
            f"{_summary(e)}\n— PBF Studio\nIndependent Creative Studio, Nairobi, Kenya\n"
        )
        try:
            send_mail(e["email"], f"We received your enquiry — {e['ref']}", body, reply_to=notify_to or "")
            _set_status(enquiry_id, "ack_status", "sent")
        except Exception:  # noqa: BLE001
            log.exception("Acknowledgement email failed for %s", e["ref"])
            _set_status(enquiry_id, "ack_status", "failed")


def dispatch(enquiry_id: int) -> None:
    """Send notifications without delaying the visitor's response."""
    app = current_app._get_current_object()
    s = settings.load()
    studio_channel = (smtp_configured() and bool(s.get("notify_email") or s.get("contact_email"))) or webhook_configured()
    if not (smtp_configured() or studio_channel):
        return
    if smtp_configured():
        _set_status(enquiry_id, "ack_status", "queued")
    if studio_channel:
        _set_status(enquiry_id, "notify_status", "queued")

    def work():
        with app.app_context():
            try:
                _deliver(enquiry_id)
            except Exception:  # noqa: BLE001
                log.exception("Notification worker crashed for enquiry %s", enquiry_id)

    if app.config["SYNC_NOTIFICATIONS"]:
        work()
    else:
        threading.Thread(target=work, daemon=True).start()
