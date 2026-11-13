import io
import re

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

from pbf import create_app
from pbf import db as dbm
from pbf.security import issue_form_token

ADMIN_EMAIL = "owner@example.test"
ADMIN_PASSWORD = "Correct-Horse-9-Battery"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("PBF_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("NOTIFY_WEBHOOK_URL", raising=False)
    app = create_app({"TESTING": True, "SYNC_NOTIFICATIONS": True, "FORM_MIN_SECONDS": 0, "GZIP": False,
                      "SITE_URL": "https://pbf.example.test"})
    with app.app_context():
        dbm.run("INSERT INTO admin_users (email, name, password_hash, created_at) VALUES (?,?,?,?)",
                (ADMIN_EMAIL, "Owner", generate_password_hash(ADMIN_PASSWORD), dbm.now_iso()))
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def token(client, path="/admin/login"):
    client.get(path)
    with client.session_transaction() as s:
        return s["_csrf"]


@pytest.fixture()
def admin(client):
    t = token(client)
    r = client.post("/admin/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "csrf_token": t})
    assert r.status_code == 302, r.data[:300]
    return client


def png_bytes(size=(1600, 1000), color=(113, 0, 20)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def enquiry_form(app, **over):
    with app.test_request_context():
        ft = issue_form_token()
    data = {"full_name": "Amina Otieno", "email": "amina@example.com", "services": ["Digital Experiences"],
            "description": "We need a new website for our Nairobi bakery with online ordering.",
            "budget": "KSh 75,000–150,000", "timeline": "Within 1 month", "ft": ft}
    data.update(over)
    return data
