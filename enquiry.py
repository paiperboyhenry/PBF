"""The project enquiry system: multi-step form, server-side validation, spam protection, storage."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from . import mailer, media, models, settings
from .db import get_db, log_activity, now_iso
from .public import seo
from .security import (check_form_token, client_ip, hash_ip, issue_form_token, rate_blocked, rate_hit,
                       turnstile_enabled, verify_turnstile)
from .seed import TIMELINES
from .util import clean_lines, normalise_phone, safe_https_url, whatsapp_link

bp = Blueprint("enquiry", __name__)

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
HOURLY_LIMIT = 6
DAILY_LIMIT = 20


def service_options() -> list[str]:
    names = [d["name"] for d in models.departments()]
    return names + ["Multiple services", "Other"]


def validate(form, files) -> tuple[dict, dict]:
    errors: dict[str, str] = {}
    s = settings.load()

    def text(name: str, limit: int) -> str:
        return re.sub(r"[ \t]+", " ", (form.get(name) or "").replace("\r", "")).strip()[:limit]

    clean = {
        "full_name": text("full_name", 120),
        "business_name": text("business_name", 160),
        "email": text("email", 254).lower(),
        "country": text("country", 80),
        "service_other": text("service_other", 200),
        "description": text("description", 5000),
        "extra_notes": text("extra_notes", 3000),
    }
    if not clean["full_name"]:
        errors["full_name"] = "Please tell us your name."
    if not clean["email"]:
        errors["email"] = "Please add an email address so we can reply."
    elif not EMAIL_RE.match(clean["email"]):
        errors["email"] = "That email address doesn't look right."

    raw_whatsapp = text("whatsapp", 40)
    clean["whatsapp"] = ""
    if raw_whatsapp:
        digits = normalise_phone(raw_whatsapp)
        if not digits:
            errors["whatsapp"] = "Enter your WhatsApp number with country code, e.g. +254…"
        else:
            clean["whatsapp"] = "+" + digits

    allowed = service_options()
    picked = [v for v in form.getlist("services") if v in allowed]
    clean["services"] = list(dict.fromkeys(picked))
    if not clean["services"]:
        errors["services"] = "Choose at least one service."
    if "Other" in clean["services"] and not clean["service_other"]:
        errors["service_other"] = "Tell us what else you need."
    if "Other" not in clean["services"]:
        clean["service_other"] = ""

    if len(clean["description"]) < 20:
        errors["description"] = "Tell us a little more about the project (a few sentences is plenty)."

    budget = text("budget", 80)
    clean["budget"] = budget if budget in s["budget_ranges"] else ""
    if budget and not clean["budget"]:
        errors["budget"] = "Please choose one of the listed budget options."
    timeline = text("timeline", 40)
    clean["timeline"] = timeline if timeline in TIMELINES else ""
    if timeline and not clean["timeline"]:
        errors["timeline"] = "Please choose one of the listed timelines."

    links = clean_lines(form.get("reference_links", ""), limit=6, max_len=300)
    good = []
    for line in links:
        url = safe_https_url(line)
        if url:
            good.append(url)
        else:
            errors["reference_links"] = f"“{line[:40]}” isn't a valid link."
    clean["reference_links"] = good[:5]

    uploads = [f for f in files.getlist("attachments") if f and f.filename]
    if len(uploads) > current_app.config["MAX_ATTACHMENTS"]:
        errors["attachments"] = f"Attach up to {current_app.config['MAX_ATTACHMENTS']} files."
    clean["_uploads"] = uploads
    return clean, errors


def _fail(message: str, status: int, errors: dict | None = None):
    return jsonify(ok=False, message=message, errors=errors or {}), status


@bp.get("/start-a-project")
def form():
    s = settings.load()
    preset = {}
    dept = models.department_by_slug(request.args.get("department", ""))
    if dept:  # arriving from a department page: pre-select that service
        preset["services"] = [dept["name"]]
    return render_template(
        "public/enquiry.html",
        services=service_options(), budgets=s["budget_ranges"], timelines=TIMELINES,
        form_token=issue_form_token(), turnstile_key=current_app.config["TURNSTILE_SITE_KEY"] if turnstile_enabled() else "",
        max_attachments=current_app.config["MAX_ATTACHMENTS"], max_attachment_mb=current_app.config["MAX_ATTACHMENT_MB"],
        values=preset, errors={},
        seo=seo("Start a project", "Tell PBF Studio about your project: brand identity, website, photography, "
                "interiors, creative direction or fashion. A short form, six steps, no obligation."),
    )


@bp.post("/start-a-project")
@bp.post("/api/enquiry")
def submit():
    wants_json = request.path.startswith("/api/") or request.headers.get("X-Requested-With") == "fetch"
    ip = client_ip()
    if rate_blocked(f"enq:{ip}", HOURLY_LIMIT, 3600) or rate_blocked(f"enqd:{ip}", DAILY_LIMIT, 86400):
        return _respond_error(wants_json, "You've sent several enquiries recently. Please try again later or reach us on WhatsApp.", 429)
    rate_hit(f"enq:{ip}")
    rate_hit(f"enqd:{ip}")

    if request.form.get("website"):  # honeypot field, hidden from people
        return _respond_error(wants_json, "We couldn't verify this submission. Please refresh the page and try again.", 400)
    problem = check_form_token(request.form.get("ft", ""))
    if problem == "too_fast":
        return _respond_error(wants_json, "That was very quick. Please take a moment, check your details and send again.", 400)
    if problem:
        return _respond_error(wants_json, "This form has expired. Please refresh the page — your answers are kept if you use the same browser tab.", 400)
    if turnstile_enabled() and not verify_turnstile(request.form.get("cf-turnstile-response", "")):
        return _respond_error(wants_json, "We couldn't confirm you're human. Please try the check again.", 400)

    clean, errors = validate(request.form, request.files)
    if errors:
        if wants_json:
            return _fail("Please check the highlighted fields.", 422, errors)
        return _rerender(clean, errors)

    db = get_db()
    ts = now_iso()
    enquiry_id = 0
    try:
        cur = db.execute(
            """INSERT INTO enquiries
               (full_name, business_name, email, whatsapp, country, services, service_other, description,
                budget, timeline, reference_links, extra_notes, ip_hash, user_agent, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (clean["full_name"], clean["business_name"], clean["email"], clean["whatsapp"], clean["country"],
             json.dumps(clean["services"]), clean["service_other"], clean["description"], clean["budget"],
             clean["timeline"], json.dumps(clean["reference_links"]), clean["extra_notes"],
             hash_ip(ip),
             (request.headers.get("User-Agent") or "")[:200], ts, ts),
        )
        enquiry_id = cur.lastrowid
        ref = f"PBF-{datetime.now(timezone.utc).year}-{enquiry_id:04d}"
        db.execute("UPDATE enquiries SET ref = ? WHERE id = ?", (ref, enquiry_id))
        for fs in clean["_uploads"]:
            info = media.save_attachment(fs, enquiry_id)
            db.execute(
                "INSERT INTO enquiry_files (enquiry_id, original_name, stored_name, mime, size, created_at) VALUES (?,?,?,?,?,?)",
                (enquiry_id, info["original_name"], info["stored_name"], info["mime"], info["size"], ts),
            )
        db.commit()
    except media.MediaError as exc:
        db.rollback()
        media.delete_enquiry_files(enquiry_id)
        if wants_json:
            return _fail(str(exc), 422, {"attachments": str(exc)})
        return _rerender(clean, {"attachments": str(exc)})
    except Exception:  # noqa: BLE001 - never tell the visitor it worked if it didn't
        db.rollback()
        current_app.logger.exception("Enquiry could not be stored")
        return _respond_error(wants_json, "We couldn't save your enquiry. Nothing was sent — please try again, or contact us on WhatsApp.", 500)

    log_activity("enquiry.received", "enquiry", enquiry_id, f"{ref} from {clean['full_name']}", actor="visitor")
    mailer.dispatch(enquiry_id)

    follow_up = whatsapp_link(settings.load().get("whatsapp_number", ""),
                              f"Hello PBF Studio, I just sent a project enquiry (ref {ref}).")
    payload = {"ok": True, "ref": ref, "whatsapp_url": follow_up, "email_confirmation": mailer.smtp_configured()}
    if wants_json:
        return jsonify(payload)
    session["last_enquiry"] = payload
    return redirect(url_for("enquiry.received"))


def _respond_error(wants_json: bool, message: str, status: int):
    if wants_json:
        return _fail(message, status)
    return _rerender({}, {"_form": message}, status)


def _rerender(values: dict, errors: dict, status: int = 422):
    s = settings.load()
    values = dict(values)
    for key in ("full_name", "business_name", "email", "whatsapp", "country", "service_other", "description",
                "budget", "timeline", "extra_notes"):
        values.setdefault(key, request.form.get(key, ""))
    values.setdefault("services", [v for v in request.form.getlist("services") if v in service_options()])
    if "reference_links" not in values:
        values["reference_links"] = clean_lines(request.form.get("reference_links", ""), limit=6, max_len=300)
    return render_template(
        "public/enquiry.html",
        services=service_options(), budgets=s["budget_ranges"], timelines=TIMELINES,
        form_token=issue_form_token(), turnstile_key=current_app.config["TURNSTILE_SITE_KEY"] if turnstile_enabled() else "",
        max_attachments=current_app.config["MAX_ATTACHMENTS"], max_attachment_mb=current_app.config["MAX_ATTACHMENT_MB"],
        values={k: v for k, v in values.items() if not k.startswith("_")}, errors=errors,
        seo=seo("Start a project", noindex=True),
    ), status


@bp.get("/start-a-project/received")
def received():
    info = session.pop("last_enquiry", None)
    if not info:
        return redirect(url_for("enquiry.form"))
    return render_template("public/enquiry_done.html", info=info,
                           seo=seo("Enquiry received", noindex=True))
