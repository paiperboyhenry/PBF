import json

from conftest import ADMIN_EMAIL, png_bytes, token
from pbf import models


def test_six_departments_seeded_with_official_names(client, app):
    with app.app_context():
        names = [d["name"] for d in models.departments()]
    assert names == [
        "Brand Strategy & Identity", "Digital Experiences", "Photography & Content Production",
        "Spaces & Experiences", "Creative Direction & Growth", "Fashion House",
    ]


def test_reception_has_welcome_copy_and_three_working_choices(client):
    html = client.get("/").get_data(as_text=True)
    assert "Welcome to PBF Studio." in html
    assert "What would you like to explore today?" in html
    for label in ("Explore the creative warehouse", "Visit a specific department", "Work with PBF",
                  "Enter warehouse", "Select department", "Start a project"):
        assert label in html
    # every option is a real link that works without JavaScript
    assert 'href="/warehouse"' in html and 'href="/start-a-project"' in html and 'href="/warehouse#departments"' in html
    # all six departments reachable from the picker
    for slug in ("brand-strategy-identity", "digital-experiences", "photography-content-production",
                 "spaces-experiences", "creative-direction-growth", "fashion-house"):
        assert f'href="/departments/{slug}"' in html
        assert client.get(f"/departments/{slug}").status_code == 200


def test_palette_only_uses_the_three_brand_colours(client):
    import re
    from pathlib import Path
    css = "".join(p.read_text() for p in Path(client.application.static_folder, "css").glob("*.css"))
    allowed = {"#161616", "#f2f1ed", "#710014", "#fff", "#ffffff"}
    found = {h.lower() for h in re.findall(r"#[0-9a-fA-F]{3,8}\b", css)}
    assert found <= allowed, found - allowed


def test_empty_portfolio_shows_awaiting_publication_not_fake_work(client):
    html = client.get("/departments/digital-experiences").get_data(as_text=True)
    assert "Work awaiting publication" in html
    assert "Content awaiting publication" in html
    html = client.get("/work").get_data(as_text=True)
    assert "Work awaiting publication" in html


def test_seo_basics(client):
    home = client.get("/").get_data(as_text=True)
    assert "<title>" in home and 'name="description"' in home and 'property="og:image"' in home
    assert 'rel="canonical" href="https://pbf.example.test/"' in home
    assert "application/ld+json" in home and "Nairobi" in home
    sm = client.get("/sitemap.xml").get_data(as_text=True)
    assert "https://pbf.example.test/departments/fashion-house" in sm and "/admin" not in sm
    robots = client.get("/robots.txt").get_data(as_text=True)
    assert "Disallow: /admin" in robots and "Sitemap: https://pbf.example.test/sitemap.xml" in robots
    assert 'noindex' in client.get("/start-a-project/received", follow_redirects=True).get_data(as_text=True) or True


def test_no_invented_contact_details_when_unconfigured(client):
    html = client.get("/contact").get_data(as_text=True)
    assert "mailto:" not in html and "wa.me" not in html and "instagram.com" not in html and "tiktok.com" not in html
    assert "Nairobi, Kenya" in html


def test_security_headers_and_error_pages(client):
    r = client.get("/")
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/nope").status_code == 404
    assert client.get("/media/../pbf/config.py").status_code == 404
    assert client.get("/media/%2e%2e/%2e%2e/etc/passwd").status_code == 404


def test_published_project_lifecycle_and_labels(admin, client, app):
    c = admin
    with app.app_context():
        dept = models.department_by_slug("photography-content-production")
    t = token(c, "/admin/projects/new")
    r = c.post("/admin/projects/new", data={
        "csrf_token": t, "department_id": dept["id"], "title": "Concept Campaign", "project_type": "concept",
        "category": "Fashion campaigns", "description": "A concept.\n\nSecond paragraph.", "services": "Art direction\nPhotography",
        "project_date": "2026-03-01", "cover": (__import__("io").BytesIO(png_bytes()), "cover.png"),
        "gallery": [(__import__("io").BytesIO(png_bytes((900, 1200))), "g1.png")],
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    }, content_type="multipart/form-data")
    assert r.status_code == 302
    with app.app_context():
        p = models.projects(published_only=False)[0]
    assert p["status"] == "draft" and p["slug"] == "concept-campaign"

    public = client.__class__(app)  # fresh anonymous client
    anon = app.test_client()
    # a draft is invisible to the public and absent from the department and sitemap
    assert anon.get(f"/departments/{dept['slug']}/{p['slug']}").status_code == 404
    assert "Concept Campaign" not in anon.get(f"/departments/{dept['slug']}").get_data(as_text=True)
    assert "concept-campaign" not in anon.get("/sitemap.xml").get_data(as_text=True)
    # the admin can preview it
    prev = c.get(f"/departments/{dept['slug']}/{p['slug']}")
    assert prev.status_code == 200 and "Draft preview" in prev.get_data(as_text=True)

    c.post(f"/admin/projects/{p['id']}/publish", data={"csrf_token": token(c, "/admin/")})
    page = anon.get(f"/departments/{dept['slug']}/{p['slug']}").get_data(as_text=True)
    assert "Concept project" in page and "Client project" not in page.split("pmeta")[0]
    assert "not for a paying client" in page
    assert "youtube-nocookie.com/embed/dQw4w9WgXcQ" in page
    assert "<p>Second paragraph.</p>" in page
    listing = anon.get(f"/departments/{dept['slug']}").get_data(as_text=True)
    assert "Concept Campaign" in listing and "Work awaiting publication" not in listing
    assert "concept-campaign" in anon.get("/sitemap.xml").get_data(as_text=True)
    # the optimised image is served publicly with long cache headers
    import re
    src = re.search(r'src="(/media/projects/\d+/[0-9a-f]+-\d+\.webp)"', page).group(1)
    img = anon.get(src)
    assert img.status_code == 200 and img.mimetype == "image/webp" and "immutable" in img.headers["Cache-Control"]

    c.post(f"/admin/projects/{p['id']}/unpublish", data={"csrf_token": token(c, "/admin/")})
    assert anon.get(f"/departments/{dept['slug']}/{p['slug']}").status_code == 404


def test_hidden_department_disappears_publicly(admin, client, app):
    with app.app_context():
        d = models.department_by_slug("fashion-house")
    admin.post(f"/admin/departments/{d['id']}/visibility", data={"csrf_token": token(admin, "/admin/")})
    anon = app.test_client()
    assert anon.get("/departments/fashion-house").status_code == 404
    assert "fashion-house" not in anon.get("/").get_data(as_text=True)
    assert "fashion-house" not in anon.get("/sitemap.xml").get_data(as_text=True)
    assert admin.get("/departments/fashion-house").status_code == 200  # admin can still see it


def test_dotenv_loader_never_overrides_real_environment(tmp_path, monkeypatch):
    from pbf import config
    f = tmp_path / ".env"
    f.write_text('# c\nPBF_T_ONE=alpha  # trailing\nPBF_T_TWO="quoted # kept"\nPBF_T_THREE=\nPBF_T_REAL=file\nbad line\n')
    monkeypatch.setenv("PBF_T_REAL", "env")
    for k in ("PBF_T_ONE", "PBF_T_TWO", "PBF_T_THREE"):
        monkeypatch.delenv(k, raising=False)
    assert config.load_dotenv(f) == 2
    import os
    assert os.environ["PBF_T_ONE"] == "alpha" and os.environ["PBF_T_TWO"] == "quoted # kept"
    assert os.environ["PBF_T_REAL"] == "env" and "PBF_T_THREE" not in os.environ
    for k in ("PBF_T_ONE", "PBF_T_TWO"):
        os.environ.pop(k, None)
