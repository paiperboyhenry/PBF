"""PBF Studio website application factory."""
from __future__ import annotations

import logging
from datetime import datetime

import click
from flask import Flask, jsonify, render_template, request, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from . import db as dbm
from . import models, security, settings
from .config import configure
from .util import register_filters, whatsapp_link


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    configure(app, overrides)
    logging.basicConfig(level=logging.INFO)

    hops = app.config["PROXY_HOPS"]
    if hops:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)

    dbm.init_app(app)
    register_filters(app)
    security.init_app(app)
    app.jinja_env.globals["csrf_token"] = security.csrf_token

    from .admin import bp as admin_bp
    from .enquiry import bp as enquiry_bp
    from .public import bp as public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(enquiry_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.context_processor
    def inject():
        s = settings.load()
        return {
            "site": s,
            "nav_departments": models.departments(),
            "admin": security.current_admin(),
            "year": datetime.now().year,
            "static_v": static_v,
            "media_url": media_url,
            "abs_url": abs_url,
            "csrf_token": security.csrf_token,
            "whatsapp_url": whatsapp_link(s.get("whatsapp_number", "")),
        }

    def static_v(filename: str) -> str:
        import os
        path = os.path.join(app.static_folder, filename)
        try:
            version = int(os.path.getmtime(path))
        except OSError:
            version = 0
        return url_for("static", filename=filename, v=version)

    def media_url(path: str, width: int | None = None, kind: str = "") -> str:
        if not path:
            return ""
        if kind == "og":
            return url_for("public.media_file", key=f"{path}-og.jpg")
        if "." in path.rsplit("/", 1)[-1]:  # video or other file with an extension
            return url_for("public.media_file", key=path)
        return url_for("public.media_file", key=f"{path}-{width}.webp")

    def abs_url(path: str) -> str:
        base = app.config["SITE_URL"] or request.url_root.rstrip("/")
        return base + path

    # Macros imported without context (partials/macros.html) need these as true globals.
    app.jinja_env.globals.update(static_v=static_v, media_url=media_url, abs_url=abs_url)

    register_errors(app)
    register_cli(app)
    return app


def register_errors(app: Flask) -> None:
    messages = {
        400: ("Request not understood", "Something about that request didn't look right."),
        401: ("Sign in required", "You need to sign in to see this."),
        403: ("Not allowed", "That request couldn't be verified. Go back, refresh the page and try again."),
        404: ("Page not found", "This room doesn't exist. Head back to reception."),
        405: ("Not allowed", "That action isn't available here."),
        413: ("File too large", "That upload is bigger than this site accepts."),
        429: ("Slow down", "Too many requests. Please wait a moment and try again."),
        500: ("Something went wrong", "We hit a problem on our side. Please try again shortly."),
    }

    def wants_json() -> bool:
        return (request.path.startswith("/api/") or request.headers.get("X-Requested-With") == "fetch"
                or request.accept_mimetypes.best == "application/json")

    @app.errorhandler(Exception)
    def handle(exc):
        if isinstance(exc, HTTPException):
            code = exc.code or 500
        else:
            app.logger.exception("Unhandled error")
            code = 500
        title, message = messages.get(code, ("Something went wrong", "Please try again."))
        if wants_json():
            return jsonify(ok=False, message=message), code
        try:
            return render_template("public/error.html", code=code, title=title, message=message,
                                   seo={"title": f"{title} — PBF Studio", "noindex": True}), code
        except Exception:  # noqa: BLE001 - last resort if the template layer itself is failing
            return f"{code} {title}", code


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    @click.argument("email")
    @click.option("--name", default="", help="Display name")
    def create_admin(email: str, name: str):
        """Create an admin user (prompts for the password; nothing is stored in config)."""
        from werkzeug.security import generate_password_hash
        email = email.strip().lower()
        problem = None
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        problem = security.password_problem(password)
        if problem:
            raise click.ClickException(problem)
        if dbm.q("SELECT 1 FROM admin_users WHERE email = ?", (email,), one=True):
            raise click.ClickException("An admin with that email already exists. Use reset-password.")
        dbm.run(
            "INSERT INTO admin_users (email, name, password_hash, created_at) VALUES (?,?,?,?)",
            (email, name, generate_password_hash(password), dbm.now_iso()),
        )
        click.echo(f"Admin {email} created.")

    @app.cli.command("reset-password")
    @click.argument("email")
    def reset_password(email: str):
        """Set a new password for an existing admin and sign out all their sessions."""
        from werkzeug.security import generate_password_hash
        row = dbm.q("SELECT id FROM admin_users WHERE email = ?", (email.strip().lower(),), one=True)
        if not row:
            raise click.ClickException("No admin with that email.")
        password = click.prompt("New password", hide_input=True, confirmation_prompt=True)
        problem = security.password_problem(password)
        if problem:
            raise click.ClickException(problem)
        dbm.run(
            "UPDATE admin_users SET password_hash = ?, session_epoch = session_epoch + 1 WHERE id = ?",
            (generate_password_hash(password), row["id"]),
        )
        click.echo("Password updated.")

    @app.cli.command("doctor")
    def doctor():
        """Show which integrations are configured (does not send anything)."""
        from . import mailer
        cfg = app.config
        rows = [
            ("Environment", cfg["PBF_ENV"]),
            ("SECRET_KEY", "set" if cfg["SECRET_KEY"] else "MISSING"),
            ("SITE_URL", cfg["SITE_URL"] or "not set (canonical/sitemap URLs fall back to the request host)"),
            ("Admin users", str(dbm.q("SELECT COUNT(*) AS n FROM admin_users", one=True)["n"])),
            ("SETUP_TOKEN", "set" if cfg["SETUP_TOKEN"] else "not set"),
            ("Email (SMTP)", "configured" if mailer.smtp_configured() else "not configured"),
            ("Webhook", "configured" if mailer.webhook_configured() else "not configured"),
            ("Turnstile", "configured" if security.turnstile_enabled() else "not configured"),
            ("Data directory", str(cfg["DATA_DIR"])),
        ]
        for label, value in rows:
            click.echo(f"{label:<16}{value}")
