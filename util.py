"""Small helpers: slugs, text rendering, video URL parsing, template filters."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from markupsafe import Markup, escape

from .seed import PROJECT_TYPES

EAT = ZoneInfo("Africa/Nairobi")


def slugify(text: str, fallback: str = "item") -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:80].strip("-") or fallback


def json_list(raw) -> list:
    if isinstance(raw, list):
        return raw
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []


def clean_lines(raw: str, limit: int = 40, max_len: int = 120) -> list[str]:
    """Textarea (one per line) or comma separated -> clean list, de-duplicated, order kept."""
    out: list[str] = []
    for part in re.split(r"[\n\r]+", raw or ""):
        part = re.sub(r"\s+", " ", part).strip().strip("•·-–— ").strip()
        if part and part[:max_len] not in out:
            out.append(part[:max_len])
        if len(out) >= limit:
            break
    return out


def parse_video_url(url: str) -> dict | None:
    """Return embed details for YouTube/Vimeo, else None. Only https URLs are accepted."""
    try:
        u = urlparse((url or "").strip())
    except ValueError:
        return None
    if u.scheme != "https" or not u.hostname:
        return None
    host = u.hostname.lower().removeprefix("www.")
    vid = None
    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if u.path == "/watch":
            vid = parse_qs(u.query).get("v", [None])[0]
        else:
            m = re.match(r"^/(?:embed|shorts|live)/([\w-]{6,20})", u.path)
            vid = m.group(1) if m else None
        if vid and re.fullmatch(r"[\w-]{6,20}", vid):
            return {"provider": "youtube", "id": vid,
                    "embed": f"https://www.youtube-nocookie.com/embed/{vid}"}
    elif host == "youtu.be":
        vid = u.path.lstrip("/").split("/")[0]
        if re.fullmatch(r"[\w-]{6,20}", vid or ""):
            return {"provider": "youtube", "id": vid,
                    "embed": f"https://www.youtube-nocookie.com/embed/{vid}"}
    elif host in {"vimeo.com", "player.vimeo.com"}:
        m = re.search(r"/(?:video/)?(\d{5,12})(?:/|$)", u.path)
        if m:
            return {"provider": "vimeo", "id": m.group(1),
                    "embed": f"https://player.vimeo.com/video/{m.group(1)}"}
    return None


def safe_https_url(url: str, hosts: tuple[str, ...] | None = None) -> str:
    """Return the URL if it is http(s) (optionally limited to hosts), else ''."""
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        # Anything that starts with another scheme (javascript:, data:, mailto:, ftp:...) is refused,
        # not "fixed up". Bare hosts like example.com/page or example.com:8080 get https:// added.
        if re.match(r"^[a-z][a-z0-9+.\-]*:(?!\d+(/|$))", url, re.I) or url.startswith("//"):
            return ""
        url = "https://" + url
    try:
        u = urlparse(url)
    except ValueError:
        return ""
    if u.scheme not in {"http", "https"} or not u.hostname or " " in url or "." not in u.hostname:
        return ""
    try:
        u.port  # raises ValueError for a malformed port
    except ValueError:
        return ""
    if hosts:
        h = u.hostname.lower()
        if not any(h == x or h.endswith("." + x) for x in hosts):
            return ""
    return url[:500]


def normalise_phone(raw: str) -> str:
    """Digits only (international form without '+'). Returns '' if it doesn't look like a number."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    return digits if 7 <= len(digits) <= 15 else ""


def whatsapp_link(number: str, text: str = "") -> str:
    digits = normalise_phone(number)
    if not digits or digits.startswith("0"):
        return ""
    from urllib.parse import quote
    return f"https://wa.me/{digits}" + (f"?text={quote(text)}" if text else "")


def paragraphs(text: str) -> Markup:
    """Escape user text and turn blank lines into paragraphs, single newlines into <br>."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", (text or "").replace("\r", "")) if b.strip()]
    html = "".join(f"<p>{escape(b).replace(chr(10), Markup('<br>'))}</p>" for b in blocks)
    return Markup(html)


def month_year(value: str | None) -> str:
    if not value:
        return ""
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(value[:10] if fmt == "%Y-%m-%d" else value[:7], fmt).strftime("%B %Y")
        except ValueError:
            continue
    return ""


def local_dt(value: str | None, fmt: str = "%d %b %Y, %H:%M") -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    if dt.tzinfo is None:
        from datetime import timezone
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(EAT).strftime(fmt)


def excerpt(text: str, n: int = 150) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= n:
        return text
    return text[: n - 1].rsplit(" ", 1)[0].rstrip(",.;:—-") + "…"


def type_label(value: str) -> str:
    return PROJECT_TYPES.get(value, "")


def register_filters(app) -> None:
    app.jinja_env.filters.update(
        paragraphs=paragraphs,
        month_year=month_year,
        local_dt=local_dt,
        excerpt=excerpt,
        type_label=type_label,
        json_list=json_list,
        tojson_compact=lambda v: Markup(json.dumps(v, separators=(",", ":")).replace("<", "\\u003c")),
    )
