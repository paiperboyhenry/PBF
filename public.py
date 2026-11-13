"""Public pages: reception, warehouse, departments, projects, static pages, SEO files, media."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Response, abort, current_app, render_template, request, send_file, url_for

from . import media, models, settings
from .security import current_admin
from .seed import PROJECT_TYPES
from .util import excerpt, month_year, whatsapp_link

bp = Blueprint("public", __name__)

SITE_NAME = "PBF Studio"
HOME_DESCRIPTION = (
    "PBF Studio is an independent creative studio in Nairobi, Kenya, working with businesses in Kenya and "
    "internationally across branding, digital experiences, photography, spaces, creative direction and fashion."
)


def seo(title: str | None = None, description: str = HOME_DESCRIPTION, image: str = "",
        noindex: bool = False, og_type: str = "website", jsonld: list | None = None) -> dict:
    full = f"{title} — {SITE_NAME}" if title else f"{SITE_NAME} — Independent creative studio in Nairobi"
    return {"title": full, "description": excerpt(description, 190), "image": image, "noindex": noindex,
            "og_type": og_type, "jsonld": jsonld or []}


def _breadcrumb(items: list[tuple[str, str]]) -> dict:
    base = current_app.config["SITE_URL"] or request.url_root.rstrip("/")
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": base + path}
            for i, (name, path) in enumerate(items)
        ],
    }


# ------------------------------------------------------------------ main experience
@bp.get("/")
def home():
    depts = models.departments()
    featured = models.projects(limit=6)
    return render_template("public/home.html", departments=depts, featured=featured, seo=seo())


@bp.get("/warehouse")
def warehouse():
    return render_template(
        "public/warehouse.html", departments=models.departments(),
        seo=seo("The Creative Warehouse",
                "Walk through the six PBF Studio creative departments: brand strategy, digital, photography, "
                "spaces, creative direction and the Fashion House."),
    )


@bp.get("/departments/<slug>")
def department(slug: str):
    admin = current_admin()
    d = models.department_by_slug(slug, visible_only=not admin)
    if not d:
        abort(404)
    items = models.projects(dept_id=d["id"], visible_depts_only=False)
    others = [x for x in models.departments() if x["id"] != d["id"]]
    idx = next((i for i, x in enumerate(models.departments()) if x["id"] == d["id"]), None)
    all_d = models.departments()
    prev_d = all_d[idx - 1] if idx not in (None, 0) else None
    next_d = all_d[idx + 1] if idx is not None and idx < len(all_d) - 1 else None
    first = items[0]["cover"] if items and items[0]["cover"] else d["cover"]
    return render_template(
        "public/department.html", dept=d, projects=items, gallery=models.department_gallery(d["id"]),
        prev_dept=prev_d, next_dept=next_d, other_departments=others,
        seo=seo(
            d["name"], f"{d['description']} Services include {', '.join(d['services'][:4]).lower()} and more.",
            image=media_og(first), noindex=not d["is_visible"],
            jsonld=[_breadcrumb([("Home", "/"), ("Warehouse", "/warehouse"), (d["name"], f"/departments/{d['slug']}")])],
        ),
    )


@bp.get("/departments/<slug>/<project_slug>")
def project(slug: str, project_slug: str):
    admin = current_admin()
    d = models.department_by_slug(slug, visible_only=not admin)
    if not d:
        abort(404)
    p = models.project_by_slug(d["id"], project_slug)
    if not p:
        abort(404)
    preview = p["status"] != "published"
    if preview and not admin:
        abort(404)
    prev_p, next_p = models.neighbours(p) if not preview else (None, None)
    desc = p["description"] or f"{p['title']} — {PROJECT_TYPES[p['project_type']]} by PBF Studio in {d['name']}."
    base = current_app.config["SITE_URL"] or request.url_root.rstrip("/")
    ld = {
        "@context": "https://schema.org",
        "@type": "CreativeWork",
        "name": p["title"],
        "description": excerpt(desc, 300),
        "url": f"{base}/departments/{d['slug']}/{p['slug']}",
        "creator": {"@type": "Organization", "name": SITE_NAME},
        "genre": d["name"],
    }
    if p["project_date"]:
        ld["dateCreated"] = p["project_date"]
    if p["cover"]:
        ld["image"] = base + media_og(p["cover"], absolute=False)
    return render_template(
        "public/project.html", dept=d, project=p, gallery=models.project_gallery(p["id"]),
        videos=models.project_videos(p["id"]), prev_project=prev_p, next_project=next_p, preview=preview,
        type_labels=PROJECT_TYPES,
        seo=seo(f"{p['title']} · {d['name']}", desc, image=media_og(p["cover"]), noindex=preview,
                og_type="article", jsonld=[ld, _breadcrumb([
                    ("Home", "/"), (d["name"], f"/departments/{d['slug']}"),
                    (p["title"], f"/departments/{d['slug']}/{p['slug']}")])]),
    )


@bp.get("/work")
def work():
    depts = models.departments()
    items = models.projects()
    return render_template(
        "public/work.html", departments=depts, projects=items,
        seo=seo("Selected Work", "Selected work from PBF Studio across brand identity, digital, photography, "
                "spaces, creative direction and fashion. Client projects and concept work are labelled clearly."),
    )


@bp.get("/services")
def services():
    return render_template(
        "public/services.html", departments=models.departments(),
        seo=seo("Services", "Brand strategy and identity, websites and e-commerce, photography and content "
                "production, interiors and retail spaces, creative direction and social media, and fashion "
                "concepts — from one independent studio in Nairobi."),
    )


@bp.get("/about")
def about():
    return render_template(
        "public/about.html", departments=models.departments(),
        seo=seo("About", "PBF Studio is an independent creative studio bringing strategy, design, digital "
                "experiences and visual production together for businesses in Nairobi and worldwide."),
    )


@bp.get("/contact")
def contact():
    return render_template(
        "public/contact.html",
        seo=seo("Contact", "Start a project with PBF Studio, an independent creative studio in Nairobi, Kenya, "
                "working with businesses in Kenya and internationally."),
    )


# ------------------------------------------------------------------ helpers for templates/seo
def media_og(cover: dict | None, absolute: bool = True) -> str:
    """Open Graph image: the project's own 1200x630 crop if present, else the default."""
    if cover:
        path = url_for("public.media_file", key=f"{cover['path']}-og.jpg")
    else:
        path = url_for("static", filename="img/og-default.jpg")
    if not absolute:
        return path
    base = current_app.config["SITE_URL"] or request.url_root.rstrip("/")
    return base + path


# ------------------------------------------------------------------ files, sitemap, robots
@bp.get("/media/<path:key>")
def media_file(key: str):
    root = media.public_root().resolve()
    path = (root / key).resolve()
    if root not in path.parents or not path.is_file():
        abort(404)
    ext = path.suffix.lower().lstrip(".")
    if ext not in media.MIME or ext == "pdf":
        abort(404)
    resp = send_file(path, mimetype=media.MIME[ext], conditional=True, max_age=31536000)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@bp.get("/robots.txt")
def robots():
    base = current_app.config["SITE_URL"] or request.url_root.rstrip("/")
    body = f"User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /api/\nDisallow: /start-a-project/received\n\nSitemap: {base}/sitemap.xml\n"
    return Response(body, mimetype="text/plain")


@bp.get("/sitemap.xml")
def sitemap():
    base = current_app.config["SITE_URL"] or request.url_root.rstrip("/")
    urls: list[tuple[str, str | None]] = [
        (p, None) for p in ("/", "/warehouse", "/work", "/services", "/about", "/contact", "/start-a-project")
    ]
    for d in models.departments():
        urls.append((f"/departments/{d['slug']}", None))
    for p in models.projects():
        urls.append((f"/departments/{p['dept_slug']}/{p['slug']}", (p["updated_at"] or "")[:10] or None))
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, lastmod in urls:
        parts.append(f"<url><loc>{base}{path}</loc>" + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "") + "</url>")
    parts.append("</urlset>")
    return Response("\n".join(parts), mimetype="application/xml")


@bp.get("/healthz")
def healthz():
    return Response("ok", mimetype="text/plain")
