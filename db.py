"""SQLite access. Parameterised queries only; never string-format user input into SQL."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

from .seed import DEPARTMENTS

SCHEMA = Path(__file__).with_name("schema.sql")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DB_PATH"], timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 10000")
        g.db = conn
    return g.db


def close_db(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def q(sql: str, args: tuple | list = (), one: bool = False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def run(sql: str, args: tuple | list = ()) -> sqlite3.Cursor:
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur


def init_db() -> None:
    """Create tables and seed the six departments (insert-only; never overwrites edits)."""
    db = get_db()
    db.executescript(SCHEMA.read_text())
    existing = {r["slug"] for r in db.execute("SELECT slug FROM departments")}
    ts = now_iso()
    for d in DEPARTMENTS:
        if d["slug"] in existing:
            continue
        db.execute(
            """INSERT INTO departments
               (slug, number, name, tagline, description, services, categories, theme,
                is_visible, sort_order, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,1,?,?,?)""",
            (
                d["slug"], d["number"], d["name"], d["tagline"], d["description"],
                json.dumps(d["services"]), json.dumps(d["categories"]), d["theme"],
                d["number"], ts, ts,
            ),
        )
    db.commit()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()


def log_activity(action: str, subject_type: str = "", subject_id: int | None = None,
                 detail: str = "", admin: dict | None = None, actor: str = "") -> None:
    run(
        """INSERT INTO activity_log (admin_id, actor, action, subject_type, subject_id, detail, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (admin["id"] if admin else None, actor or (admin["email"] if admin else "system"),
         action, subject_type, subject_id, detail[:300], now_iso()),
    )
