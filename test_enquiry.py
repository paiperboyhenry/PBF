import io
import json

from conftest import enquiry_form, png_bytes, token
from pbf import db as dbm
from pbf import mailer


def post(client, data, ajax=True):
    data = dict(data)
    data["csrf_token"] = token(client, "/start-a-project")
    headers = {"X-Requested-With": "fetch"} if ajax else {}
    return client.post("/start-a-project", data=data, headers=headers, content_type="multipart/form-data")


def stored(app):
    with app.app_context():
        return dbm.q("SELECT * FROM enquiries ORDER BY id")


def test_valid_enquiry_is_stored_and_confirmed_honestly(client, app):
    r = post(client, enquiry_form(app, whatsapp="+254 712 345 678", country="Kenya"))
    body = r.get_json()
    assert r.status_code == 200 and body["ok"] is True and body["ref"].startswith("PBF-")
    assert body["email_confirmation"] is False            # no SMTP configured -> never claim an email was sent
    rows = stored(app)
    assert len(rows) == 1 and rows[0]["whatsapp"] == "+254712345678" and rows[0]["ack_status"] == "not_configured"
    assert json.loads(rows[0]["services"]) == ["Digital Experiences"]


def test_whatsapp_follow_up_link_only_when_configured(client, app, admin):
    assert post(client, enquiry_form(app)).get_json()["whatsapp_url"] == ""
    admin.post("/admin/settings", data={"csrf_token": token(admin, "/admin/settings"), "whatsapp_number": "+254700111222", "budget_ranges": "KSh 75,000–150,000"})
    anon = app.test_client()
    url = post(anon, enquiry_form(app)).get_json()["whatsapp_url"]
    assert url.startswith("https://wa.me/254700111222?text=")


def test_enquiry_visible_in_admin_with_status_and_private_notes(client, admin, app):
    post(client, enquiry_form(app, full_name="Visible Person", business_name="Acme Ltd"))
    page = admin.get("/admin/enquiries").get_data(as_text=True)
    assert "Visible Person" in page and "PBF-" in page
    with app.app_context():
        eid = dbm.q("SELECT id FROM enquiries", one=True)["id"]
    detail = admin.get(f"/admin/enquiries/{eid}").get_data(as_text=True)
    assert "We need a new website" in detail and "amina@example.com" in detail and "KSh 75,000" in detail
    for status in ("contacted", "in_discussion", "won", "closed", "new"):
        r = admin.post(f"/admin/enquiries/{eid}/status", data={"csrf_token": token(admin, "/admin/"), "status": status})
        assert r.status_code == 302
        with app.app_context():
            assert dbm.q("SELECT status FROM enquiries WHERE id=?", (eid,), one=True)["status"] == status
    assert admin.post(f"/admin/enquiries/{eid}/status", data={"csrf_token": token(admin, "/admin/"), "status": "bogus"}).status_code == 400
    admin.post(f"/admin/enquiries/{eid}/notes", data={"csrf_token": token(admin, "/admin/"), "body": "Call on Monday <script>alert(1)</script>"})
    detail = admin.get(f"/admin/enquiries/{eid}").get_data(as_text=True)
    assert "Call on Monday" in detail and "<script>alert(1)</script>" not in detail
    # notes are never exposed to the public
    assert "Call on Monday" not in client.get("/").get_data(as_text=True)


def test_enquiry_markup_is_escaped_in_admin(client, admin, app):
    post(client, enquiry_form(app, full_name='<img src=x onerror=alert(1)>', description="<script>alert('x')</script> long enough text here"))
    html = admin.get("/admin/enquiries").get_data(as_text=True)
    assert "<img src=x" not in html
    with app.app_context():
        eid = dbm.q("SELECT id FROM enquiries", one=True)["id"]
    assert "<script>alert('x')</script>" not in admin.get(f"/admin/enquiries/{eid}").get_data(as_text=True)


def test_server_side_validation(client, app):
    r = post(client, enquiry_form(app, full_name="", email="not-an-email", services=[], description="short", whatsapp="12", budget="Free!", timeline="Yesterday"))
    assert r.status_code == 422 and not r.get_json()["ok"]
    errs = r.get_json()["errors"]
    assert {"full_name", "email", "services", "description", "whatsapp", "budget", "timeline"} <= set(errs)
    assert stored(app) == []                                # nothing saved on failure


def test_budget_and_timeline_are_optional(client, app):
    r = post(client, enquiry_form(app, budget="", timeline=""))
    assert r.status_code == 200 and r.get_json()["ok"]


def test_other_requires_detail_and_unknown_services_ignored(client, app):
    r = post(client, enquiry_form(app, services=["Other"]))
    assert r.status_code == 422 and "service_other" in r.get_json()["errors"]
    r = post(client, enquiry_form(app, services=["Hacking"]))
    assert r.status_code == 422 and "services" in r.get_json()["errors"]
    r = post(client, enquiry_form(app, services=["Other", "Fashion House"], service_other="Packaging labels"))
    assert r.status_code == 200


def test_reference_links_validated(client, app):
    r = post(client, enquiry_form(app, reference_links="https://example.com/a\njavascript:alert(1)"))
    assert r.status_code == 422 and "reference_links" in r.get_json()["errors"]
    r = post(client, enquiry_form(app, reference_links="https://example.com/a\nexample.org/b"))
    assert r.status_code == 200
    assert json.loads(stored(app)[0]["reference_links"]) == ["https://example.com/a", "https://example.org/b"]


def test_honeypot_blocks_bots_and_stores_nothing(client, app):
    r = post(client, enquiry_form(app, website="http://spam.example"))
    assert r.status_code == 400 and stored(app) == []


def test_too_fast_and_missing_token_rejected(client, app):
    app.config["FORM_MIN_SECONDS"] = 30
    r = post(client, enquiry_form(app))
    assert r.status_code == 400 and "quick" in r.get_json()["message"]
    app.config["FORM_MIN_SECONDS"] = 0
    r = post(client, enquiry_form(app, ft=""))
    assert r.status_code == 400
    r = post(client, enquiry_form(app, ft="forged.token.value"))
    assert r.status_code == 400 and stored(app) == []


def test_csrf_required_on_public_form(client, app):
    data = enquiry_form(app)
    assert client.post("/start-a-project", data=data, headers={"X-Requested-With": "fetch"}).status_code == 403


def test_rate_limit(client, app):
    codes = [post(client, enquiry_form(app, full_name=f"P{i}")).status_code for i in range(9)]
    assert codes[:6] == [200] * 6 and set(codes[6:]) == {429}
    assert len(stored(app)) == 6


def test_attachments_validated_by_content_and_stored_privately(client, admin, app):
    good = enquiry_form(app)
    good["attachments"] = [(io.BytesIO(png_bytes((400, 300))), "brief.png"), (io.BytesIO(b"%PDF-1.4\n%fake but pdf-signed\n"), "deck.pdf")]
    r = post(client, good)
    assert r.status_code == 200
    with app.app_context():
        files = dbm.q("SELECT * FROM enquiry_files")
        eid = files[0]["enquiry_id"]
    assert {f["mime"] for f in files} == {"image/png", "application/pdf"}
    # stored outside the public media tree and not reachable by URL
    assert not list(app.config["PUBLIC_MEDIA_DIR"].rglob("*.pdf"))
    stored_name = files[0]["stored_name"]
    assert app.test_client().get(f"/media/enquiries/{eid}/{stored_name}").status_code == 404
    # only an admin can download, as an attachment
    fid = files[0]["id"]
    assert app.test_client().get(f"/admin/enquiries/{eid}/files/{fid}").status_code == 302
    dl = admin.get(f"/admin/enquiries/{eid}/files/{fid}")
    assert dl.status_code == 200 and "attachment" in dl.headers["Content-Disposition"] and dl.headers["X-Content-Type-Options"] == "nosniff"


def test_bad_attachment_rejects_whole_enquiry(client, app):
    bad = enquiry_form(app)
    bad["attachments"] = [(io.BytesIO(b"MZ\x90 exe"), "invoice.pdf")]
    r = post(client, bad)
    assert r.status_code == 422 and "attachments" in r.get_json()["errors"]
    assert stored(app) == []
    assert not list((app.config["PRIVATE_DIR"] / "enquiries").glob("*/*")) if (app.config["PRIVATE_DIR"] / "enquiries").exists() else True


def test_too_many_attachments(client, app):
    d = enquiry_form(app)
    d["attachments"] = [(io.BytesIO(png_bytes((50, 50))), f"{i}.png") for i in range(5)]
    r = post(client, d)
    assert r.status_code == 422 and "attachments" in r.get_json()["errors"]


def test_no_js_post_redirects_to_confirmation_and_shows_errors(client, app):
    r = post(client, enquiry_form(app), ajax=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("/start-a-project/received")
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "Thank you" in page and "PBF-" in page
    assert client.get("/start-a-project/received").status_code == 302      # not replayable
    bad = post(client, enquiry_form(app, email="x"), ajax=False)
    assert bad.status_code == 422 and "That email address" in bad.get_data(as_text=True)
    assert "Amina Otieno" in bad.get_data(as_text=True)                    # answers are kept


def test_failed_storage_never_shows_success(client, app, monkeypatch):
    import pbf.enquiry as enq
    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(enq, "log_activity", lambda *a, **k: None)
    orig = enq.get_db
    class Broken:
        def __init__(self, real): self.real = real
        def execute(self, sql, *a):
            if sql.lstrip().startswith("INSERT INTO enquiries"):
                raise RuntimeError("disk full")
            return self.real.execute(sql, *a)
        def __getattr__(self, n): return getattr(self.real, n)
    monkeypatch.setattr(enq, "get_db", lambda: Broken(orig()))
    r = post(client, enquiry_form(app))
    assert r.status_code == 500 and r.get_json()["ok"] is False and "Nothing was sent" in r.get_json()["message"]


def test_notifications_record_real_outcome(client, app, monkeypatch):
    app.config.update(SMTP_HOST="smtp.invalid", MAIL_FROM="PBF <no-reply@example.test>")
    sent = []
    monkeypatch.setattr(mailer, "send_mail", lambda to, subject, body, reply_to="": sent.append((to, subject)))
    app.config["DEFAULT_SETTINGS"]["notify_email"] = "studio@example.test"
    r = post(client, enquiry_form(app))
    assert r.get_json()["email_confirmation"] is True
    rows = stored(app)
    assert rows[0]["ack_status"] == "sent" and rows[0]["notify_status"] == "sent"
    assert {t for t, _ in sent} == {"studio@example.test", "amina@example.com"}

    def fail(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(mailer, "send_mail", fail)
    post(client, enquiry_form(app, full_name="Second"))
    second = stored(app)[1]
    assert second["ack_status"] == "failed" and second["notify_status"] == "failed"      # recorded, enquiry still saved


def test_csv_export_neutralises_formulas(client, admin, app):
    post(client, enquiry_form(app, full_name="=HYPERLINK(\"http://evil\")"))
    csv_text = admin.get("/admin/enquiries.csv").get_data(as_text=True)
    assert "'=HYPERLINK" in csv_text and ",=HYPERLINK" not in csv_text


def test_delete_enquiry_removes_files(client, admin, app):
    d = enquiry_form(app)
    d["attachments"] = [(io.BytesIO(png_bytes((60, 60))), "a.png")]
    post(client, d)
    with app.app_context():
        eid = dbm.q("SELECT id FROM enquiries", one=True)["id"]
    folder = app.config["PRIVATE_DIR"] / "enquiries" / str(eid)
    assert folder.exists()
    admin.post(f"/admin/enquiries/{eid}/delete", data={"csrf_token": token(admin, "/admin/")})
    assert not folder.exists() and stored(app) == []
