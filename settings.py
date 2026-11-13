"""Admin-editable site settings. Database values win; environment variables are the defaults."""
from __future__ import annotations

import json

from flask import current_app, g

from .db import get_db, now_iso, q
from .seed import DEFAULT_BUDGET_RANGES

KEYS = (
    "contact_email", "whatsapp_number", "instagram_url", "tiktok_url",
    "location", "international_note", "notify_email", "budget_ranges",
)


def load() -> dict:
    if "settings" in g:
        return g.settings
    data = dict(current_app.config["DEFAULT_SETTINGS"])
    data["budget_ranges"] = list(DEFAULT_BUDGET_RANGES)
    for row in q("SELECT key, value FROM site_settings"):
        if row["key"] == "budget_ranges":
            try:
                ranges = json.loads(row["value"])
                if isinstance(ranges, list) and ranges:
                    data["budget_ranges"] = [str(x) for x in ranges]
            except ValueError:
                pass
        elif row["key"] in KEYS:
            data[row["key"]] = row["value"]
    g.settings = data
    return data


def save(key: str, value) -> None:
    if key not in KEYS:
        raise KeyError(key)
    if key == "budget_ranges":
        value = json.dumps(list(value))
    db = get_db()
    db.execute(
        """INSERT INTO site_settings (key, value, updated_at) VALUES (?,?,?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (key, value, now_iso()),
    )
    db.commit()
    g.pop("settings", None)
