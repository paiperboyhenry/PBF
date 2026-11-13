"""Configuration. Everything sensitive comes from environment variables."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> int:
    """Read KEY=VALUE lines from a .env file next to the app (stdlib only).

    Real environment variables always win; the file never overrides them. Returns how many keys were set.
    """
    path = path or (BASE_DIR / ".env")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    count = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if value[:1] in {'"', "'"} and value.count(value[0]) >= 2:
            value = value[1:value.index(value[0], 1)]
        else:
            value = value.split(" #", 1)[0].strip()
        if key and key.replace("_", "").isalnum() and key not in os.environ and value != "":
            os.environ[key] = value
            count += 1
    return count


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _dev_secret(data_dir: Path) -> str:
    """Development-only secret, persisted so sessions survive restarts."""
    path = data_dir / ".dev_secret"
    if path.exists():
        return path.read_text().strip()
    value = secrets.token_urlsafe(48)
    path.write_text(value)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value


def configure(app, overrides: dict | None = None) -> None:
    if overrides is None:          # tests pass overrides and must never pick up a developer's local .env
        load_dotenv()
    env = os.environ.get("PBF_ENV", "development").lower()
    production = env == "production"
    data_dir = Path(os.environ.get("PBF_DATA_DIR", BASE_DIR / "data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    secret = os.environ.get("SECRET_KEY", "")
    if not secret:
        if production:
            raise RuntimeError(
                "SECRET_KEY is required when PBF_ENV=production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        secret = _dev_secret(data_dir)

    app.config.update(
        PBF_ENV=env,
        PRODUCTION=production,
        SECRET_KEY=secret,
        DATA_DIR=data_dir,
        DB_PATH=str(data_dir / "pbf.sqlite3"),
        PUBLIC_MEDIA_DIR=data_dir / "media",
        PRIVATE_DIR=data_dir / "private",
        SITE_URL=os.environ.get("SITE_URL", "").rstrip("/"),
        SETUP_TOKEN=os.environ.get("SETUP_TOKEN", ""),
        PROXY_HOPS=_int("PROXY_HOPS", 0),
        GZIP=_bool("PBF_GZIP", True),
        # Sessions
        SESSION_COOKIE_NAME="pbf_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
        PERMANENT_SESSION_LIFETIME=_int("SESSION_HOURS", 8) * 3600,
        # Uploads
        MAX_IMAGE_MB=_int("MAX_IMAGE_MB", 15),
        MAX_VIDEO_MB=_int("MAX_VIDEO_MB", 200),
        MAX_ATTACHMENT_MB=_int("MAX_ATTACHMENT_MB", 8),
        MAX_ATTACHMENTS=3,
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,  # default; upload routes raise it per request
        SEND_FILE_MAX_AGE_DEFAULT=31536000,
        # Email (all optional)
        SMTP_HOST=os.environ.get("SMTP_HOST", ""),
        SMTP_PORT=_int("SMTP_PORT", 587),
        SMTP_USER=os.environ.get("SMTP_USER", ""),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD", ""),
        SMTP_SSL=_bool("SMTP_SSL", False),
        SMTP_STARTTLS=_bool("SMTP_STARTTLS", True),
        MAIL_FROM=os.environ.get("MAIL_FROM", ""),
        NOTIFY_WEBHOOK_URL=os.environ.get("NOTIFY_WEBHOOK_URL", ""),
        SYNC_NOTIFICATIONS=False,
        # Cloudflare Turnstile (optional spam protection)
        TURNSTILE_SITE_KEY=os.environ.get("TURNSTILE_SITE_KEY", ""),
        TURNSTILE_SECRET_KEY=os.environ.get("TURNSTILE_SECRET_KEY", ""),
        # Defaults for admin-editable settings (admin values win once saved)
        DEFAULT_SETTINGS={
            "contact_email": os.environ.get("CONTACT_EMAIL", ""),
            "whatsapp_number": os.environ.get("WHATSAPP_NUMBER", ""),
            "instagram_url": os.environ.get("INSTAGRAM_URL", ""),
            "tiktok_url": os.environ.get("TIKTOK_URL", ""),
            "notify_email": os.environ.get("NOTIFY_EMAIL", ""),
            "location": "Nairobi, Kenya",
            "international_note": "Working with businesses in Kenya and internationally.",
        },
    )
    if overrides:
        app.config.update(overrides)

    for sub in (app.config["PUBLIC_MEDIA_DIR"], app.config["PRIVATE_DIR"]):
        Path(sub).mkdir(parents=True, exist_ok=True)
