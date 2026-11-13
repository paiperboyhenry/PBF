"""Authentication, CSRF, rate limiting, spam checks, security headers and response compression."""
from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app, g, redirect, request, session, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .db import get_db, q

MB = 1024 * 1024
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


# ---------------------------------------------------------------- identity helpers
def client_ip() -> str:
    return request.remote_addr or "0.0.0.0"


def hash_ip(ip: str) -> str:
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, ip.encode(), hashlib.sha256).hexdigest()[:32]


# ---------------------------------------------------------------- CSRF
def csrf_token() -> str:
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def _same_origin() -> bool:
    for header in ("Origin", "Referer"):
        value = request.headers.get(header)
        if value:
            return urlparse(value).netloc == request.host
    return True  # no browser headers: the CSRF token still has to match


def _guard_request() -> None:
    path = request.path
    if request.method in _UNSAFE:
        cfg = current_app.config
        if path.startswith(("/admin/projects", "/admin/departments")):
            request.max_content_length = (cfg["MAX_VIDEO_MB"] + 25) * MB
        elif path in ("/start-a-project", "/api/enquiry"):
            request.max_content_length = (cfg["MAX_ATTACHMENTS"] * cfg["MAX_ATTACHMENT_MB"] + 2) * MB
        if not _same_origin():
            abort(403)
        sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        expected = session.get("_csrf", "")
        if not expected or not sent or not hmac.compare_digest(expected, sent):
            abort(403)


# ---------------------------------------------------------------- admin auth
def current_admin() -> dict | None:
    if "admin" in g:
        return g.admin
    g.admin = None
    admin_id = session.get("admin_id")
    if admin_id:
        row = q("SELECT * FROM admin_users WHERE id = ? AND is_active = 1", (admin_id,), one=True)
        if row and row["session_epoch"] == session.get("epoch"):
            g.admin = dict(row)
    return g.admin


def login_user(row) -> None:
    session.clear()  # new session on login prevents fixation
    session["admin_id"] = row["id"]
    session["epoch"] = row["session_epoch"]
    session.permanent = True
    csrf_token()


def logout_user() -> None:
    session.clear()


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_admin():
            if request.method == "GET":
                return redirect(url_for("admin.login", next=request.full_path.rstrip("?")))
            abort(401)
        return view(*args, **kwargs)
    return wrapper


def safe_next(target: str | None) -> str:
    """Only allow redirects to admin pages on this site."""
    if target and target.startswith("/admin") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("admin.dashboard")


def password_problem(password: str) -> str:
    if len(password) < 12:
        return "Use at least 12 characters."
    if password.lower() == password or password.upper() == password or not any(c.isdigit() for c in password):
        return "Mix upper and lower case letters and include a number."
    return ""


# ---------------------------------------------------------------- rate limiting (SQLite backed)
def rate_blocked(key: str, limit: int, window: int) -> bool:
    now = time.time()
    n = q("SELECT COUNT(*) AS n FROM rate_events WHERE key = ? AND ts > ?", (key, now - window), one=True)["n"]
    return n >= limit


def rate_hit(key: str) -> None:
    db = get_db()
    now = time.time()
    db.execute("INSERT INTO rate_events (key, ts) VALUES (?, ?)", (key, now))
    if secrets.randbelow(50) == 0:
        db.execute("DELETE FROM rate_events WHERE ts < ?", (now - 2 * 86400,))
    db.commit()


def rate_clear(key: str) -> None:
    db = get_db()
    db.execute("DELETE FROM rate_events WHERE key = ?", (key,))
    db.commit()


# ---------------------------------------------------------------- enquiry spam protection
def _form_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="pbf-enquiry-form")


def issue_form_token() -> str:
    return _form_serializer().dumps({"t": int(time.time())})


def check_form_token(token: str, min_age: int | None = None, max_age: int = 86400) -> str:
    """Return '' if fine, otherwise a short reason. Forms submitted faster than a human can type are rejected."""
    if min_age is None:
        min_age = current_app.config.get("FORM_MIN_SECONDS", 4)
    if not token:
        return "missing"
    try:
        data = _form_serializer().loads(token, max_age=max_age)
    except BadSignature:
        return "expired"
    if time.time() - data.get("t", 0) < min_age:
        return "too_fast"
    return ""


def turnstile_enabled() -> bool:
    cfg = current_app.config
    return bool(cfg["TURNSTILE_SITE_KEY"] and cfg["TURNSTILE_SECRET_KEY"])


def verify_turnstile(response_token: str) -> bool:
    """Fail closed: if Turnstile is configured and cannot be verified, the submission is rejected."""
    if not response_token:
        return False
    body = urllib.parse.urlencode({
        "secret": current_app.config["TURNSTILE_SECRET_KEY"],
        "response": response_token,
        "remoteip": client_ip(),
    }).encode()
    req = urllib.request.Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", data=body)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310 (fixed https URL)
            return bool(json.loads(resp.read().decode()).get("success"))
    except (urllib.error.URLError, ValueError, TimeoutError):
        return False


# ---------------------------------------------------------------- headers + compression
def _csp() -> str:
    cdn = " https://challenges.cloudflare.com" if turnstile_enabled() else ""
    parts = [
        "default-src 'self'",
        f"script-src 'self'{cdn}",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "media-src 'self'",
        "font-src 'self'",
        "connect-src 'self'",
        f"frame-src https://www.youtube-nocookie.com https://player.vimeo.com{cdn}",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
    if current_app.config["PRODUCTION"]:
        parts.append("upgrade-insecure-requests")
    return "; ".join(parts)


_COMPRESSIBLE = ("text/html", "text/css", "application/javascript", "text/javascript",
                 "application/json", "image/svg+xml", "application/xml", "text/xml", "text/plain")


def _after_request(resp):
    h = resp.headers
    h.setdefault("Content-Security-Policy", _csp())
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    if current_app.config["PRODUCTION"]:
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.path.startswith("/admin"):
        h["Cache-Control"] = "no-store"
        h["X-Robots-Tag"] = "noindex, nofollow"
    if (current_app.config["GZIP"] and resp.status_code == 200 and not resp.direct_passthrough
            and "Content-Encoding" not in h and "gzip" in request.headers.get("Accept-Encoding", "")
            and (resp.mimetype in _COMPRESSIBLE)):
        data = resp.get_data()
        if len(data) > 600:
            resp.set_data(gzip.compress(data, compresslevel=6))
            h["Content-Encoding"] = "gzip"
            h.add("Vary", "Accept-Encoding")
    return resp


def init_app(app) -> None:
    app.before_request(_guard_request)
    app.after_request(_after_request)
