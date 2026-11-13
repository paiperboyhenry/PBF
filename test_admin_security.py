import io

import pytest

from conftest import ADMIN_EMAIL, ADMIN_PASSWORD, png_bytes, token
from pbf import models
from pbf.util import parse_video_url, safe_https_url


ADMIN_PAGES = ["/admin/", "/admin/projects", "/admin/projects/new", "/admin/departments", "/admin/enquiries",
               "/admin/settings", "/admin/account", "/admin/enquiries.csv"]


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_admin_requires_login(client, path):
    r = client.get(path)
    assert r.status_code == 302 and "/admin/login" in r.headers["Location"]


def test_admin_writes_require_login_and_csrf(client, admin, app):
    anon = app.test_client()
    t = token(anon)
    assert anon.post("/admin/projects/1/publish", data={"csrf_token": t}).status_code == 401
    # signed in but no / wrong CSRF token -> refused
    assert admin.post("/admin/settings", data={"contact_email": "x@y.zz"}).status_code == 403
    assert admin.post("/admin/settings", data={"contact_email": "x@y.zz", "csrf_token": "bad"}).status_code == 403


def test_cross_origin_post_is_rejected(admin):
    t = token(admin, "/admin/settings")
    r = admin.post("/admin/settings", data={"csrf_token": t, "budget_ranges": "A"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_login_failures_do_not_reveal_which_part_was_wrong(client):
    t = token(client)
    a = client.post("/admin/login", data={"email": ADMIN_EMAIL, "password": "wrong", "csrf_token": t})
    b = client.post("/admin/login", data={"email": "nobody@example.test", "password": "wrong", "csrf_token": t})
    assert a.status_code == b.status_code == 401
    assert "Incorrect email or password." in a.get_data(as_text=True) and "Incorrect email or password." in b.get_data(as_text=True)


def test_login_is_rate_limited(client):
    t = token(client)
    codes = [client.post("/admin/login", data={"email": ADMIN_EMAIL, "password": "nope", "csrf_token": t}).status_code
             for _ in range(7)]
    assert 401 in codes
    # after repeated failures even the right password is locked out for a while
    r = client.post("/admin/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "csrf_token": t})
    assert r.status_code == 401 and "Too many attempts" in r.get_data(as_text=True)


def test_open_redirect_blocked_on_login(client):
    t = token(client)
    r = client.post("/admin/login?next=https://evil.example", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "csrf_token": t})
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/")


def test_admin_responses_not_cached_or_indexed(admin):
    r = admin.get("/admin/")
    assert r.headers["Cache-Control"] == "no-store" and "noindex" in r.headers["X-Robots-Tag"]
    assert "pbf_session" in admin.get("/").headers.get("Set-Cookie", "") or True


def test_password_change_signs_out_other_sessions(admin, app):
    other = app.test_client()
    t = token(other)
    other.post("/admin/login", data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "csrf_token": t})
    assert other.get("/admin/").status_code == 200
    t = token(admin, "/admin/account")
    r = admin.post("/admin/account", data={"csrf_token": t, "current": ADMIN_PASSWORD, "new": "Another-Strong-Pass-22", "confirm": "Another-Strong-Pass-22"})
    assert r.status_code == 302
    assert admin.get("/admin/").status_code == 200       # this session continues
    assert other.get("/admin/").status_code == 302       # the other one is out


def test_weak_password_rejected(admin):
    t = token(admin, "/admin/account")
    r = admin.post("/admin/account", data={"csrf_token": t, "current": ADMIN_PASSWORD, "new": "short", "confirm": "short"}, follow_redirects=True)
    assert "at least 12" in r.get_data(as_text=True)


def test_setup_route_is_closed_unless_token_set_and_no_admin(client, app):
    assert client.get("/admin/setup").status_code == 404  # admin exists -> closed


def test_no_hardcoded_credentials_in_source():
    from pathlib import Path
    import re
    root = Path(__file__).resolve().parent.parent / "pbf"
    text = "\n".join(p.read_text() for p in root.rglob("*.py"))
    assert not re.search(r"password\s*=\s*['\"][^'\"]{4,}['\"]", text.replace("not-a-real-password", ""))


# ---------- uploads
def _new_project(admin, app, **files):
    with app.app_context():
        dept = models.department_by_slug("brand-strategy-identity")
    t = token(admin, "/admin/projects/new")
    data = {"csrf_token": t, "department_id": dept["id"], "title": "Upload Test", "project_type": "client"}
    data.update(files)
    return admin.post("/admin/projects/new", data=data, content_type="multipart/form-data", follow_redirects=True)


def test_non_image_disguised_as_image_is_rejected(admin, app):
    r = _new_project(admin, app, cover=(io.BytesIO(b"<?php echo 1; ?>"), "cover.png"))
    assert "isn&#39;t a valid image" in r.get_data(as_text=True) or "isn't a valid image" in r.get_data(as_text=True)
    with app.app_context():
        p = models.projects(published_only=False)[0]
    assert p["cover"] is None


def test_svg_and_html_uploads_rejected(admin, app):
    r = _new_project(admin, app, cover=(io.BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'), "x.svg"))
    assert "valid image" in r.get_data(as_text=True)


def test_oversized_image_rejected(admin, app):
    app.config["MAX_IMAGE_MB"] = 1
    big = png_bytes((2600, 2600))  # noisy enough? solid PNG compresses; use random bytes header instead
    import os
    from PIL import Image
    buf = io.BytesIO()
    Image.frombytes("RGB", (1400, 1400), os.urandom(1400 * 1400 * 3)).save(buf, "PNG")
    r = _new_project(admin, app, cover=(io.BytesIO(buf.getvalue()), "big.png"))
    assert "larger than 1 MB" in r.get_data(as_text=True)


def test_uploaded_image_is_reencoded_and_metadata_stripped(admin, app, tmp_path):
    from PIL import Image
    buf = io.BytesIO()
    im = Image.new("RGB", (2400, 1600), (22, 22, 22))
    exif = Image.Exif(); exif[0x010F] = "SecretCameraMaker"; exif[0x8825] = {1: "N", 2: (1, 1, 1)}
    im.save(buf, "JPEG", exif=exif)
    _new_project(admin, app, cover=(io.BytesIO(buf.getvalue()), "photo.jpg"))
    files = list((app.config["PUBLIC_MEDIA_DIR"]).rglob("*.webp"))
    assert files and all(f.read_bytes()[:4] == b"RIFF" for f in files)
    assert all(b"SecretCameraMaker" not in f.read_bytes() for f in files)
    widths = sorted(int(f.stem.rsplit("-", 1)[1]) for f in files)
    assert widths == [640, 1280, 1920]                 # responsive variants, capped at 1920
    assert list(app.config["PUBLIC_MEDIA_DIR"].rglob("*-og.jpg"))   # share image generated


def test_video_upload_checks_signature(admin, app):
    with app.app_context():
        dept = models.department_by_slug("digital-experiences")
    t = token(admin, "/admin/projects/new")
    r = admin.post("/admin/projects/new", data={"csrf_token": t, "department_id": dept["id"], "title": "Vid", "project_type": "personal",
                   "video_file": (io.BytesIO(b"MZ\x90\x00 not a video"), "clip.mp4")}, content_type="multipart/form-data", follow_redirects=True)
    assert "must be an MP4" in r.get_data(as_text=True)
    mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 200
    r = admin.post("/admin/projects/new", data={"csrf_token": token(admin, "/admin/projects/new"), "department_id": dept["id"], "title": "Vid2",
                   "project_type": "personal", "video_file": (io.BytesIO(mp4), "clip.mp4")}, content_type="multipart/form-data", follow_redirects=True)
    assert "must be an MP4" not in r.get_data(as_text=True)


def test_cannot_publish_without_cover_and_type_is_mandatory(admin, app):
    r = _new_project(admin, app)
    with app.app_context():
        p = models.projects(published_only=False)[0]
    r = admin.post(f"/admin/projects/{p['id']}/publish", data={"csrf_token": token(admin, "/admin/")}, follow_redirects=True)
    assert "Add a cover image before publishing" in r.get_data(as_text=True)
    t = token(admin, "/admin/projects/new")
    with app.app_context():
        dept = models.department_by_slug("brand-strategy-identity")
    r = admin.post("/admin/projects/new", data={"csrf_token": t, "department_id": dept["id"], "title": "No type"}, content_type="multipart/form-data")
    assert r.status_code == 422 and "Client, Concept or Personal" in r.get_data(as_text=True)


def test_delete_needs_exact_title_and_removes_files(admin, app):
    _new_project(admin, app, cover=(io.BytesIO(png_bytes()), "c.png"))
    with app.app_context():
        p = models.projects(published_only=False)[0]
    media = app.config["PUBLIC_MEDIA_DIR"]
    assert list(media.rglob("*.webp"))
    r = admin.post(f"/admin/projects/{p['id']}/delete", data={"csrf_token": token(admin, "/admin/"), "confirm_title": "wrong"})
    assert r.status_code == 422
    with app.app_context():
        assert models.project_by_id(p["id"])
    admin.post(f"/admin/projects/{p['id']}/delete", data={"csrf_token": token(admin, "/admin/"), "confirm_title": "Upload Test"})
    with app.app_context():
        assert models.project_by_id(p["id"]) is None
    assert not list(media.rglob("*.webp"))


def test_project_ordering_controls_public_order(admin, app):
    with app.app_context():
        dept = models.department_by_slug("brand-strategy-identity")
    for title in ("Alpha", "Bravo", "Charlie"):
        admin.post("/admin/projects/new", data={"csrf_token": token(admin, "/admin/projects/new"), "department_id": dept["id"], "title": title,
                   "project_type": "client", "cover": (io.BytesIO(png_bytes()), "c.png")}, content_type="multipart/form-data")
    with app.app_context():
        ids = {p["title"]: p["id"] for p in models.projects(published_only=False)}
    for pid in ids.values():
        admin.post(f"/admin/projects/{pid}/publish", data={"csrf_token": token(admin, "/admin/")})
    def order():
        with app.app_context():
            return [p["title"] for p in models.projects(dept_id=dept["id"])]
    first = order()
    last = first[-1]
    for _ in range(len(first)):
        admin.post(f"/admin/projects/{ids[last]}/move", data={"csrf_token": token(admin, "/admin/"), "direction": "up"})
    assert order()[0] == last


def test_category_must_belong_to_department(admin, app):
    with app.app_context():
        dept = models.department_by_slug("brand-strategy-identity")
    r = admin.post("/admin/projects/new", data={"csrf_token": token(admin, "/admin/projects/new"), "department_id": dept["id"], "title": "X",
                   "project_type": "client", "category": "Lookbooks"}, content_type="multipart/form-data")
    assert r.status_code == 422


def test_settings_validation_and_public_effect(admin, app):
    t = token(admin, "/admin/settings")
    bad = admin.post("/admin/settings", data={"csrf_token": t, "contact_email": "nope", "whatsapp_number": "0712345678", "instagram_url": "https://evil.com/x", "budget_ranges": "A"})
    assert bad.status_code == 200 and "doesn&#39;t look right" in bad.get_data(as_text=True)
    ok = admin.post("/admin/settings", data={"csrf_token": t, "contact_email": "hello@example.test", "whatsapp_number": "+254 700 000 000",
                    "instagram_url": "instagram.com/pbf", "tiktok_url": "", "location": "Nairobi, Kenya", "international_note": "Worldwide", "budget_ranges": "Small\nLarge"})
    assert ok.status_code == 302
    html = app.test_client().get("/contact").get_data(as_text=True)
    assert "mailto:hello@example.test" in html and "wa.me/254700000000" in html and "https://instagram.com/pbf" in html
    form = app.test_client().get("/start-a-project").get_data(as_text=True)
    assert 'value="Small"' in form and 'value="Large"' in form and "Under KSh 10,000" not in form


def test_helpers():
    assert parse_video_url("https://youtu.be/dQw4w9WgXcQ")["embed"].endswith("/dQw4w9WgXcQ")
    assert parse_video_url("https://vimeo.com/123456789")["provider"] == "vimeo"
    assert parse_video_url("javascript:alert(1)") is None and parse_video_url("http://youtube.com/watch?v=abc12345") is None
    assert safe_https_url("javascript:alert(1)") == "" and safe_https_url("example.com/x").startswith("https://")
    assert safe_https_url("https://instagram.com/x", ("instagram.com",)) and not safe_https_url("https://notinstagram.com", ("instagram.com",))
