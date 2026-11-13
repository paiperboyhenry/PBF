"""Private admin: sign-in, dashboard, projects, departments, enquiries, settings."""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request,
                   send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from . import mailer, media, models, security, settings
from .db import get_db, log_activity, now_iso, q, run
from .security import admin_required, client_ip, current_admin, login_user, logout_user, safe_next
from .seed import ENQUIRY_STATUSES, PROJECT_TYPES
from .util import clean_lines, json_list, normalise_phone, safe_https_url, slugify, whatsapp_link

bp = Blueprint("admin", __name__)

_DUMMY_HASH = generate_password_hash("not-a-real-password")
STATUS_LABELS = dict(ENQUIRY_STATUSES)


@bp.before_request
def _gate():
    """Everything under /admin needs a signed-in admin, except sign-in and first-run setup."""
    if request.endpoint in {"admin.login", "admin.setup"}:
        return None
    if not current_admin():
        if request.method == "GET":
            return redirect(url_for("admin.login", next=request.full_path.rstrip("?")))
        abort(401)
    return None


@bp.context_processor
def _ctx():
    return {"status_labels": STATUS_LABELS, "project_types": PROJECT_TYPES,
            "enquiry_statuses": ENQUIRY_STATUSES,
            "new_enquiries": (q("SELECT COUNT(*) AS n FROM enquiries WHERE status='new'", one=True) or {"n": 0})["n"]
            if current_admin() else 0}


# ------------------------------------------------------------------ auth
@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_admin():
        return redirect(url_for("admin.dashboard"))
    has_admin = q("SELECT 1 FROM admin_users LIMIT 1", one=True) is not None
    setup_open = (not has_admin) and bool(current_app.config["SETUP_TOKEN"])
    error = ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()[:254]
        password = request.form.get("password") or ""
        ip_key, email_key = f"login-ip:{client_ip()}", f"login-email:{email}"
        if security.rate_blocked(ip_key, 15, 900) or security.rate_blocked(email_key, 5, 900):
            error = "Too many attempts. Wait 15 minutes and try again."
        else:
            row = q("SELECT * FROM admin_users WHERE email = ? AND is_active = 1", (email,), one=True)
            ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password) and row is not None
            if ok:
                security.rate_clear(email_key)
                login_user(row)
                run("UPDATE admin_users SET last_login_at = ? WHERE id = ?", (now_iso(), row["id"]))
                log_activity("admin.login", "admin", row["id"], admin=dict(row))
                return redirect(safe_next(request.args.get("next")))
            security.rate_hit(ip_key)
            security.rate_hit(email_key)
            error = "Incorrect email or password."
    return render_template("admin/login.html", error=error, setup_open=setup_open), (401 if error else 200)


@bp.post("/logout")
def logout():
    logout_user()
    return redirect(url_for("admin.login"))


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    """First-run only: creates the first admin when SETUP_TOKEN is set and no admin exists yet."""
    token = current_app.config["SETUP_TOKEN"]
    if not token or q("SELECT 1 FROM admin_users LIMIT 1", one=True):
        abort(404)
    error = ""
    if request.method == "POST":
        key = f"setup:{client_ip()}"
        if security.rate_blocked(key, 8, 900):
            error = "Too many attempts. Wait a few minutes."
        else:
            security.rate_hit(key)
            import hmac
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            if not hmac.compare_digest(request.form.get("token", ""), token):
                error = "That setup token isn't right."
            elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                error = "Enter a valid email address."
            elif password != request.form.get("password2", ""):
                error = "The two passwords don't match."
            elif security.password_problem(password):
                error = security.password_problem(password)
            else:
                run("INSERT INTO admin_users (email, name, password_hash, created_at) VALUES (?,?,?,?)",
                    (email, (request.form.get("name") or "").strip()[:80], generate_password_hash(password), now_iso()))
                flash("Admin account created. Sign in below. You can now remove SETUP_TOKEN from your settings.", "ok")
                return redirect(url_for("admin.login"))
    return render_template("admin/setup.html", error=error), (400 if error else 200)


@bp.route("/account", methods=["GET", "POST"])
def account():
    admin = current_admin()
    if request.method == "POST":
        current, new = request.form.get("current", ""), request.form.get("new", "")
        if not check_password_hash(admin["password_hash"], current):
            flash("Your current password isn't right.", "error")
        elif new != request.form.get("confirm", ""):
            flash("The new passwords don't match.", "error")
        elif security.password_problem(new):
            flash(security.password_problem(new), "error")
        else:
            run("UPDATE admin_users SET password_hash = ?, session_epoch = session_epoch + 1, name = ? WHERE id = ?",
                (generate_password_hash(new), (request.form.get("name") or admin["name"])[:80], admin["id"]))
            row = q("SELECT * FROM admin_users WHERE id = ?", (admin["id"],), one=True)
            login_user(row)  # keep this session, invalidate all others
            log_activity("admin.password_changed", "admin", admin["id"], admin=admin)
            flash("Password updated. Other devices have been signed out.", "ok")
            return redirect(url_for("admin.account"))
    return render_template("admin/account.html")


# ------------------------------------------------------------------ dashboard
@bp.get("/")
def dashboard():
    counts = models.project_counts()
    totals = q("SELECT SUM(status='published') AS pub, SUM(status='draft') AS dr FROM projects", one=True)
    recent = q("SELECT * FROM enquiries ORDER BY created_at DESC, id DESC LIMIT 6")
    activity = q("SELECT * FROM activity_log ORDER BY created_at DESC, id DESC LIMIT 12")
    status_counts = {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) AS n FROM enquiries GROUP BY status")}
    s = settings.load()
    checks = [
        ("Email delivery (SMTP)", mailer.smtp_configured(), "Set SMTP_HOST and MAIL_FROM to send enquiry notifications and client confirmations."),
        ("Studio notification channel", bool(mailer.webhook_configured() or (mailer.smtp_configured() and (s.get('notify_email') or s.get('contact_email')))), "Set a notification email in Settings (needs SMTP) or NOTIFY_WEBHOOK_URL."),
        ("WhatsApp number", bool(whatsapp_link(s.get("whatsapp_number", ""))), "Add your WhatsApp number in Settings to show WhatsApp buttons."),
        ("Contact email", bool(s.get("contact_email")), "Add a public contact email in Settings."),
        ("Social links", bool(s.get("instagram_url") or s.get("tiktok_url")), "Add Instagram / TikTok URLs in Settings."),
        ("Site URL", bool(current_app.config["SITE_URL"]), "Set SITE_URL (e.g. https://pbf.studio) so sitemap and sharing links are correct."),
    ]
    return render_template("admin/dashboard.html", counts=counts["by_department"],
                           published=totals["pub"] or 0, drafts=totals["dr"] or 0, recent=recent,
                           activity=activity, status_counts=status_counts, checks=checks,
                           enquiry_total=sum(status_counts.values()))


# ------------------------------------------------------------------ projects
def _project_form_data(existing: dict | None = None) -> tuple[dict, dict]:
    f = request.form
    errors: dict[str, str] = {}
    depts = {d["id"]: d for d in models.departments(visible_only=False)}
    try:
        dept_id = int(f.get("department_id", ""))
    except ValueError:
        dept_id = 0
    if dept_id not in depts:
        errors["department_id"] = "Choose a department."
    title = re.sub(r"\s+", " ", f.get("title", "")).strip()[:140]
    if not title:
        errors["title"] = "Give the project a title."
    ptype = f.get("project_type", "")
    if ptype not in PROJECT_TYPES:
        errors["project_type"] = "Choose Client, Concept or Personal — concept work must never be shown as client work."
    category = f.get("category", "").strip()
    if category and dept_id in depts and category not in depts[dept_id]["categories"]:
        errors["category"] = "That category doesn't belong to the chosen department."
    date = f.get("project_date", "").strip()
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            errors["project_date"] = "Use a valid date."
    ext = f.get("external_url", "").strip()
    ext_clean = safe_https_url(ext) if ext else ""
    if ext and not ext_clean:
        errors["external_url"] = "That link isn't valid."
    data = {
        "department_id": dept_id,
        "title": title,
        "client_name": re.sub(r"\s+", " ", f.get("client_name", "")).strip()[:140],
        "category": category,
        "description": f.get("description", "").replace("\r", "").strip()[:8000],
        "services": clean_lines(f.get("services", ""), limit=30),
        "project_type": ptype,
        "project_date": date or None,
        "external_url": ext_clean,
        "slug_input": slugify(f.get("slug", ""), "") if f.get("slug") else "",
    }
    return data, errors


def _unique_slug(dept_id: int, base: str, exclude_id: int | None = None) -> str:
    base = slugify(base, "project")
    slug, n = base, 2
    while True:
        row = q("SELECT id FROM projects WHERE department_id = ? AND slug = ?", (dept_id, slug), one=True)
        if not row or row["id"] == exclude_id:
            return slug
        slug = f"{base}-{n}"
        n += 1


def _save_uploads(project_id: int) -> list[str]:
    """Process cover, gallery and video uploads for a project. Returns warnings to show the admin."""
    warnings: list[str] = []
    db = get_db()
    folder = f"projects/{project_id}"
    ts = now_iso()

    cover = request.files.get("cover")
    if cover and cover.filename:
        try:
            info = media.save_image(cover, folder, og=True)
            old = q("SELECT * FROM project_images WHERE project_id = ? AND role = 'cover'", (project_id,), one=True)
            if old:
                media.delete_image(old["path"], json_list(old["variants"]))
                db.execute("DELETE FROM project_images WHERE id = ?", (old["id"],))
            db.execute(
                "INSERT INTO project_images (project_id, role, path, width, height, variants, alt, sort_order, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (project_id, "cover", info["path"], info["width"], info["height"], json.dumps(info["variants"]),
                 request.form.get("cover_alt", "").strip()[:200], 0, ts),
            )
            db.commit()
        except media.MediaError as exc:
            warnings.append(f"Cover image: {exc}")

    next_order = (q("SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM project_images WHERE project_id = ?", (project_id,), one=True)["n"])
    for fs in request.files.getlist("gallery"):
        if not fs or not fs.filename:
            continue
        try:
            info = media.save_image(fs, folder)
            db.execute(
                "INSERT INTO project_images (project_id, role, path, width, height, variants, alt, sort_order, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (project_id, "gallery", info["path"], info["width"], info["height"], json.dumps(info["variants"]), "", next_order, ts),
            )
            db.commit()
            next_order += 1
        except media.MediaError as exc:
            warnings.append(str(exc))

    vorder = (q("SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM project_videos WHERE project_id = ?", (project_id,), one=True)["n"])
    link = request.form.get("video_url", "").strip()
    if link:
        url = safe_https_url(link)
        if url:
            db.execute("INSERT INTO project_videos (project_id, kind, url, title, sort_order, created_at) VALUES (?,?,?,?,?,?)",
                       (project_id, "link", url, request.form.get("video_title", "").strip()[:140], vorder, ts))
            db.commit()
            vorder += 1
        else:
            warnings.append("The video link isn't a valid https link.")
    vfile = request.files.get("video_file")
    if vfile and vfile.filename:
        try:
            key = media.save_video(vfile, folder)
            db.execute("INSERT INTO project_videos (project_id, kind, url, title, sort_order, created_at) VALUES (?,?,?,?,?,?)",
                       (project_id, "upload", key, request.form.get("video_title", "").strip()[:140], vorder, ts))
            db.commit()
        except media.MediaError as exc:
            warnings.append(str(exc))
    return warnings


def _project_context(project: dict | None, values: dict | None = None, errors: dict | None = None) -> dict:
    depts = models.departments(visible_only=False)
    return {
        "project": project, "values": values or {}, "errors": errors or {}, "departments": depts,
        "gallery": models.project_gallery(project["id"]) if project else [],
        "videos": models.project_videos(project["id"]) if project else [],
        "dept_categories": {d["id"]: d["categories"] for d in depts},
        "max_image_mb": current_app.config["MAX_IMAGE_MB"], "max_video_mb": current_app.config["MAX_VIDEO_MB"],
    }


@bp.get("/projects")
def projects():
    dept = request.args.get("department", type=int)
    status = request.args.get("status", "")
    items = models.projects(dept_id=dept, published_only=False, visible_depts_only=False)
    if status in ("draft", "published"):
        items = [p for p in items if p["status"] == status]
    if not dept:  # group by department, keeping each department's display order
        order = {d["id"]: i for i, d in enumerate(models.departments(visible_only=False))}
        items.sort(key=lambda p: (order.get(p["department_id"], 99), p["sort_order"]))
    return render_template("admin/projects.html", items=items, departments=models.departments(visible_only=False),
                           filter_dept=dept, filter_status=status)


@bp.route("/projects/new", methods=["GET", "POST"])
def project_new():
    if request.method == "POST":
        data, errors = _project_form_data()
        if errors:
            flash("Please fix the highlighted fields. Re-select any files you chose.", "error")
            return render_template("admin/project_form.html", **_project_context(None, request.form, errors)), 422
        ts = now_iso()
        slug = _unique_slug(data["department_id"], data["slug_input"] or data["title"])
        low = q("SELECT COALESCE(MIN(sort_order), 0) - 1 AS n FROM projects WHERE department_id = ?", (data["department_id"],), one=True)["n"]
        cur = run(
            """INSERT INTO projects (department_id, slug, title, client_name, category, description, services,
                                     project_type, project_date, external_url, status, sort_order, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,'draft',?,?,?)""",
            (data["department_id"], slug, data["title"], data["client_name"], data["category"], data["description"],
             json.dumps(data["services"]), data["project_type"], data["project_date"], data["external_url"], low, ts, ts),
        )
        pid = cur.lastrowid
        warnings = _save_uploads(pid)
        for w in warnings:
            flash(w, "error")
        log_activity("project.created", "project", pid, data["title"], admin=current_admin())
        flash("Project saved as a draft. Preview it, then publish when you're happy.", "ok")
        return redirect(url_for("admin.project_edit", pid=pid))
    preset = {"department_id": request.args.get("department", "")}
    return render_template("admin/project_form.html", **_project_context(None, preset))


@bp.route("/projects/<int:pid>", methods=["GET", "POST"])
def project_edit(pid: int):
    p = models.project_by_id(pid)
    if not p:
        abort(404)
    if request.method == "POST":
        data, errors = _project_form_data(p)
        if errors:
            flash("Please fix the highlighted fields.", "error")
            return render_template("admin/project_form.html", **_project_context(p, request.form, errors)), 422
        slug = p["slug"]
        wanted = data["slug_input"] or (p["slug"] if data["department_id"] == p["department_id"] else data["title"])
        if wanted != p["slug"] or data["department_id"] != p["department_id"]:
            slug = _unique_slug(data["department_id"], wanted, exclude_id=pid)
        order = p["sort_order"]
        if data["department_id"] != p["department_id"]:
            order = q("SELECT COALESCE(MIN(sort_order), 0) - 1 AS n FROM projects WHERE department_id = ?", (data["department_id"],), one=True)["n"]
        run(
            """UPDATE projects SET department_id=?, slug=?, title=?, client_name=?, category=?, description=?,
                      services=?, project_type=?, project_date=?, external_url=?, sort_order=?, updated_at=? WHERE id=?""",
            (data["department_id"], slug, data["title"], data["client_name"], data["category"], data["description"],
             json.dumps(data["services"]), data["project_type"], data["project_date"], data["external_url"], order, now_iso(), pid),
        )
        for w in _save_uploads(pid):
            flash(w, "error")
        log_activity("project.updated", "project", pid, data["title"], admin=current_admin())
        flash("Project updated.", "ok")
        return redirect(url_for("admin.project_edit", pid=pid))
    return render_template("admin/project_form.html", **_project_context(p))


@bp.post("/projects/<int:pid>/publish")
def project_publish(pid: int):
    p = models.project_by_id(pid)
    if not p:
        abort(404)
    if not p["cover"]:
        flash("Add a cover image before publishing.", "error")
    elif not p["title"] or not p["project_type"]:
        flash("A title and project type are required to publish.", "error")
    else:
        run("UPDATE projects SET status='published', published_at=COALESCE(published_at, ?), updated_at=? WHERE id=?",
            (now_iso(), now_iso(), pid))
        log_activity("project.published", "project", pid, p["title"], admin=current_admin())
        flash(f"“{p['title']}” is live in {p['dept_name']}.", "ok")
    return redirect(request.form.get("back") or url_for("admin.project_edit", pid=pid))


@bp.post("/projects/<int:pid>/unpublish")
def project_unpublish(pid: int):
    p = models.project_by_id(pid)
    if not p:
        abort(404)
    run("UPDATE projects SET status='draft', updated_at=? WHERE id=?", (now_iso(), pid))
    log_activity("project.unpublished", "project", pid, p["title"], admin=current_admin())
    flash(f"“{p['title']}” is back to draft and hidden from the public site.", "ok")
    return redirect(request.form.get("back") or url_for("admin.project_edit", pid=pid))


@bp.route("/projects/<int:pid>/delete", methods=["GET", "POST"])
def project_delete(pid: int):
    p = models.project_by_id(pid)
    if not p:
        abort(404)
    if request.method == "POST":
        if request.form.get("confirm_title", "").strip() != p["title"]:
            flash("Type the project title exactly to confirm deletion.", "error")
            return render_template("admin/project_delete.html", project=p), 422
        for img in q("SELECT * FROM project_images WHERE project_id = ?", (pid,)):
            media.delete_image(img["path"], json_list(img["variants"]))
        for v in q("SELECT * FROM project_videos WHERE project_id = ? AND kind='upload'", (pid,)):
            media.delete_public_file(v["url"])
        run("DELETE FROM projects WHERE id = ?", (pid,))
        log_activity("project.deleted", "project", pid, p["title"], admin=current_admin())
        flash(f"“{p['title']}” was deleted.", "ok")
        return redirect(url_for("admin.projects"))
    return render_template("admin/project_delete.html", project=p)


def _swap_order(table: str, row_id: int, group_col: str, group_val: int, direction: str, order_col: str = "sort_order",
                extra: str = "") -> None:
    """Move a row up or down among its siblings by renumbering the group sequentially."""
    assert table in {"projects", "departments", "project_images", "department_images"}
    rows = q(f"SELECT id FROM {table} WHERE {group_col} = ? {extra} ORDER BY {order_col}, id", (group_val,))
    ids = [r["id"] for r in rows]
    if row_id not in ids:
        return
    i = ids.index(row_id)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
    db = get_db()
    for pos, rid in enumerate(ids):
        db.execute(f"UPDATE {table} SET {order_col} = ? WHERE id = ?", (pos + 1, rid))
    db.commit()


@bp.post("/projects/<int:pid>/move")
def project_move(pid: int):
    p = models.project_by_id(pid)
    if not p:
        abort(404)
    direction = "up" if request.form.get("direction") == "up" else "down"
    _swap_order("projects", pid, "department_id", p["department_id"], direction)
    log_activity("project.reordered", "project", pid, p["title"], admin=current_admin())
    return redirect(request.form.get("back") or url_for("admin.projects", department=p["department_id"]))


@bp.post("/projects/<int:pid>/images/<int:iid>/<action>")
def project_image_action(pid: int, iid: int, action: str):
    img = q("SELECT * FROM project_images WHERE id = ? AND project_id = ?", (iid, pid), one=True)
    if not img:
        abort(404)
    db = get_db()
    if action == "delete":
        media.delete_image(img["path"], json_list(img["variants"]))
        db.execute("DELETE FROM project_images WHERE id = ?", (iid,))
        if img["role"] == "cover":
            db.execute("UPDATE projects SET status='draft' WHERE id = ?", (pid,))
            flash("Cover removed. The project was set back to draft because published projects need a cover.", "ok")
        else:
            flash("Image removed.", "ok")
    elif action == "alt":
        db.execute("UPDATE project_images SET alt = ? WHERE id = ?", (request.form.get("alt", "").strip()[:200], iid))
        flash("Description saved.", "ok")
    elif action in ("up", "down") and img["role"] == "gallery":
        db.commit()
        _swap_order("project_images", iid, "project_id", pid, action, extra="AND role = 'gallery'")
    elif action == "cover" and img["role"] == "gallery":
        old = q("SELECT id FROM project_images WHERE project_id = ? AND role = 'cover'", (pid,), one=True)
        if old:
            db.execute("UPDATE project_images SET role = 'gallery', sort_order = 0 WHERE id = ?", (old["id"],))
        db.execute("UPDATE project_images SET role = 'cover', sort_order = 0 WHERE id = ?", (iid,))
        flash("Cover image changed. (Social-share crops are only generated for uploaded covers — re-upload the cover for the best share preview.)", "ok")
    else:
        abort(400)
    db.commit()
    return redirect(url_for("admin.project_edit", pid=pid) + "#media")


@bp.post("/projects/<int:pid>/videos/<int:vid>/delete")
def project_video_delete(pid: int, vid: int):
    v = q("SELECT * FROM project_videos WHERE id = ? AND project_id = ?", (vid, pid), one=True)
    if not v:
        abort(404)
    if v["kind"] == "upload":
        media.delete_public_file(v["url"])
    run("DELETE FROM project_videos WHERE id = ?", (vid,))
    flash("Video removed.", "ok")
    return redirect(url_for("admin.project_edit", pid=pid) + "#media")


# ------------------------------------------------------------------ departments
@bp.get("/departments")
def departments():
    return render_template("admin/departments.html", departments=models.departments(visible_only=False),
                           counts={c["id"]: c for c in models.project_counts()["by_department"]})


@bp.route("/departments/<int:did>", methods=["GET", "POST"])
def department_edit(did: int):
    d = models.department_by_id(did)
    if not d:
        abort(404)
    if request.method == "POST":
        f = request.form
        description = f.get("description", "").strip()[:800]
        tagline = re.sub(r"\s+", " ", f.get("tagline", "")).strip()[:120]
        if not description:
            flash("The description can't be empty.", "error")
        else:
            services = clean_lines(f.get("services", ""), limit=30)
            categories = clean_lines(f.get("categories", ""), limit=20)
            run("UPDATE departments SET description=?, tagline=?, services=?, categories=?, is_visible=?, updated_at=? WHERE id=?",
                (description, tagline, json.dumps(services), json.dumps(categories), 1 if f.get("is_visible") else 0, now_iso(), did))
            db = get_db()
            ts = now_iso()
            cover = request.files.get("cover")
            if cover and cover.filename:
                try:
                    info = media.save_image(cover, f"departments/{did}", og=True)
                    old = q("SELECT * FROM department_images WHERE department_id = ? AND role='cover'", (did,), one=True)
                    if old:
                        media.delete_image(old["path"], json_list(old["variants"]))
                        db.execute("DELETE FROM department_images WHERE id = ?", (old["id"],))
                    db.execute("INSERT INTO department_images (department_id, role, path, width, height, variants, alt, sort_order, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                               (did, "cover", info["path"], info["width"], info["height"], json.dumps(info["variants"]),
                                f.get("cover_alt", "").strip()[:200], 0, ts))
                    db.commit()
                except media.MediaError as exc:
                    flash(f"Cover image: {exc}", "error")
            order = q("SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM department_images WHERE department_id = ?", (did,), one=True)["n"]
            for fs in request.files.getlist("gallery"):
                if not fs or not fs.filename:
                    continue
                try:
                    info = media.save_image(fs, f"departments/{did}")
                    db.execute("INSERT INTO department_images (department_id, role, path, width, height, variants, alt, sort_order, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                               (did, "gallery", info["path"], info["width"], info["height"], json.dumps(info["variants"]), "", order, ts))
                    db.commit()
                    order += 1
                except media.MediaError as exc:
                    flash(str(exc), "error")
            log_activity("department.updated", "department", did, d["name"], admin=current_admin())
            flash("Department updated.", "ok")
            return redirect(url_for("admin.department_edit", did=did))
    d = models.department_by_id(did)
    return render_template("admin/department_form.html", dept=d, gallery=models.department_gallery(did),
                           projects=models.projects(dept_id=did, published_only=False, visible_depts_only=False))


@bp.post("/departments/<int:did>/move")
def department_move(did: int):
    if not models.department_by_id(did):
        abort(404)
    direction = "up" if request.form.get("direction") == "up" else "down"
    db = get_db()
    rows = q("SELECT id FROM departments ORDER BY sort_order, number")
    ids = [r["id"] for r in rows]
    i = ids.index(did)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
    for pos, rid in enumerate(ids):
        db.execute("UPDATE departments SET sort_order = ? WHERE id = ?", (pos + 1, rid))
    db.commit()
    log_activity("department.reordered", "department", did, admin=current_admin())
    return redirect(url_for("admin.departments"))


@bp.post("/departments/<int:did>/visibility")
def department_visibility(did: int):
    d = models.department_by_id(did)
    if not d:
        abort(404)
    new = 0 if d["is_visible"] else 1
    run("UPDATE departments SET is_visible = ?, updated_at = ? WHERE id = ?", (new, now_iso(), did))
    log_activity("department.shown" if new else "department.hidden", "department", did, d["name"], admin=current_admin())
    flash(f"{d['name']} is now {'visible' if new else 'hidden'} on the public site.", "ok")
    return redirect(request.form.get("back") or url_for("admin.departments"))


@bp.post("/departments/<int:did>/images/<int:iid>/<action>")
def department_image_action(did: int, iid: int, action: str):
    img = q("SELECT * FROM department_images WHERE id = ? AND department_id = ?", (iid, did), one=True)
    if not img:
        abort(404)
    db = get_db()
    if action == "delete":
        media.delete_image(img["path"], json_list(img["variants"]))
        db.execute("DELETE FROM department_images WHERE id = ?", (iid,))
        flash("Image removed.", "ok")
    elif action == "alt":
        db.execute("UPDATE department_images SET alt = ? WHERE id = ?", (request.form.get("alt", "").strip()[:200], iid))
        flash("Description saved.", "ok")
    elif action in ("up", "down") and img["role"] == "gallery":
        db.commit()
        _swap_order("department_images", iid, "department_id", did, action, extra="AND role = 'gallery'")
    elif action == "cover" and img["role"] == "gallery":
        old = q("SELECT id FROM department_images WHERE department_id = ? AND role = 'cover'", (did,), one=True)
        if old:
            db.execute("UPDATE department_images SET role = 'gallery', sort_order = 0 WHERE id = ?", (old["id"],))
        db.execute("UPDATE department_images SET role = 'cover', sort_order = 0 WHERE id = ?", (iid,))
        flash("Department cover changed.", "ok")
    else:
        abort(400)
    db.commit()
    return redirect(url_for("admin.department_edit", did=did) + "#media")


# ------------------------------------------------------------------ enquiries
@bp.get("/enquiries")
def enquiries():
    status = request.args.get("status", "")
    term = request.args.get("q", "").strip()[:80]
    sql, args = "SELECT * FROM enquiries", []
    where = []
    if status in STATUS_LABELS:
        where.append("status = ?")
        args.append(status)
    if term:
        where.append("(full_name LIKE ? OR business_name LIKE ? OR email LIKE ? OR ref LIKE ?)")
        args += [f"%{term}%"] * 4
    if where:
        sql += " WHERE " + " AND ".join(where)
    rows = q(sql + " ORDER BY created_at DESC, id DESC LIMIT 300", args)
    counts = {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) AS n FROM enquiries GROUP BY status")}
    return render_template("admin/enquiries.html", rows=rows, counts=counts, filter_status=status, term=term)


@bp.get("/enquiries/<int:eid>")
def enquiry_detail(eid: int):
    e = q("SELECT * FROM enquiries WHERE id = ?", (eid,), one=True)
    if not e:
        abort(404)
    notes = q("""SELECT n.*, a.name AS admin_name, a.email AS admin_email FROM enquiry_notes n
                 LEFT JOIN admin_users a ON a.id = n.admin_id WHERE enquiry_id = ? ORDER BY n.created_at DESC, n.id DESC""", (eid,))
    files = q("SELECT * FROM enquiry_files WHERE enquiry_id = ? ORDER BY id", (eid,))
    wa = whatsapp_link(e["whatsapp"], f"Hello {e['full_name'].split(' ')[0]}, this is PBF Studio about your enquiry {e['ref']}.") if e["whatsapp"] else ""
    return render_template("admin/enquiry.html", e=e, notes=notes, files=files, wa=wa,
                           services=json_list(e["services"]), links=json_list(e["reference_links"]))


@bp.post("/enquiries/<int:eid>/status")
def enquiry_status(eid: int):
    status = request.form.get("status", "")
    if status not in STATUS_LABELS:
        abort(400)
    if not q("SELECT 1 FROM enquiries WHERE id = ?", (eid,), one=True):
        abort(404)
    run("UPDATE enquiries SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), eid))
    log_activity("enquiry.status", "enquiry", eid, STATUS_LABELS[status], admin=current_admin())
    flash(f"Status set to {STATUS_LABELS[status]}.", "ok")
    return redirect(url_for("admin.enquiry_detail", eid=eid))


@bp.post("/enquiries/<int:eid>/notes")
def enquiry_note_add(eid: int):
    body = request.form.get("body", "").strip()[:4000]
    if not q("SELECT 1 FROM enquiries WHERE id = ?", (eid,), one=True):
        abort(404)
    if not body:
        flash("Write a note first.", "error")
    else:
        run("INSERT INTO enquiry_notes (enquiry_id, admin_id, body, created_at) VALUES (?,?,?,?)",
            (eid, current_admin()["id"], body, now_iso()))
        log_activity("enquiry.note", "enquiry", eid, admin=current_admin())
        flash("Note added.", "ok")
    return redirect(url_for("admin.enquiry_detail", eid=eid) + "#notes")


@bp.post("/enquiries/<int:eid>/notes/<int:nid>/delete")
def enquiry_note_delete(eid: int, nid: int):
    run("DELETE FROM enquiry_notes WHERE id = ? AND enquiry_id = ?", (nid, eid))
    flash("Note deleted.", "ok")
    return redirect(url_for("admin.enquiry_detail", eid=eid) + "#notes")


@bp.get("/enquiries/<int:eid>/files/<int:fid>")
def enquiry_file(eid: int, fid: int):
    f = q("SELECT * FROM enquiry_files WHERE id = ? AND enquiry_id = ?", (fid, eid), one=True)
    path = media.attachment_path(eid, f["stored_name"]) if f else None
    if not path:
        abort(404)
    resp = send_file(path, mimetype=f["mime"], as_attachment=True, download_name=f["original_name"], max_age=0)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@bp.route("/enquiries/<int:eid>/delete", methods=["GET", "POST"])
def enquiry_delete(eid: int):
    e = q("SELECT * FROM enquiries WHERE id = ?", (eid,), one=True)
    if not e:
        abort(404)
    if request.method == "POST":
        media.delete_enquiry_files(eid)
        run("DELETE FROM enquiries WHERE id = ?", (eid,))
        log_activity("enquiry.deleted", "enquiry", eid, e["ref"], admin=current_admin())
        flash(f"Enquiry {e['ref']} deleted.", "ok")
        return redirect(url_for("admin.enquiries"))
    return render_template("admin/enquiry_delete.html", e=e)


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@bp.get("/enquiries.csv")
def enquiries_csv():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Reference", "Received (UTC)", "Status", "Name", "Business", "Email", "WhatsApp", "Country",
                "Services", "Budget", "Timeline", "Description", "Reference links", "Notes"])
    for e in q("SELECT * FROM enquiries ORDER BY created_at DESC"):
        w.writerow([_csv_safe(x) for x in (
            e["ref"], e["created_at"], STATUS_LABELS.get(e["status"], e["status"]), e["full_name"], e["business_name"],
            e["email"], e["whatsapp"], e["country"], "; ".join(json_list(e["services"])), e["budget"], e["timeline"],
            e["description"], "; ".join(json_list(e["reference_links"])), e["extra_notes"])])
    resp = Response(out.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=pbf-enquiries.csv"
    return resp


# ------------------------------------------------------------------ settings
@bp.route("/settings", methods=["GET", "POST"])
def site_settings():
    s = settings.load()
    errors: dict[str, str] = {}
    if request.method == "POST":
        f = request.form
        email = f.get("contact_email", "").strip()
        notify = f.get("notify_email", "").strip()
        for key, val in (("contact_email", email), ("notify_email", notify)):
            if val and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", val):
                errors[key] = "That email address doesn't look right."
        wa_raw = f.get("whatsapp_number", "").strip()
        wa = normalise_phone(wa_raw) if wa_raw else ""
        if wa_raw and (not wa or wa.startswith("0")):
            errors["whatsapp_number"] = "Use international format with country code, e.g. +254…"
        ig = safe_https_url(f.get("instagram_url", ""), ("instagram.com",)) if f.get("instagram_url", "").strip() else ""
        tt = safe_https_url(f.get("tiktok_url", ""), ("tiktok.com",)) if f.get("tiktok_url", "").strip() else ""
        if f.get("instagram_url", "").strip() and not ig:
            errors["instagram_url"] = "Enter a full Instagram link (instagram.com/…)."
        if f.get("tiktok_url", "").strip() and not tt:
            errors["tiktok_url"] = "Enter a full TikTok link (tiktok.com/@…)."
        budgets = clean_lines(f.get("budget_ranges", ""), limit=12, max_len=60)
        if not budgets:
            errors["budget_ranges"] = "Keep at least one budget option."
        if not errors:
            settings.save("contact_email", email)
            settings.save("notify_email", notify)
            settings.save("whatsapp_number", ("+" + wa) if wa else "")
            settings.save("instagram_url", ig)
            settings.save("tiktok_url", tt)
            settings.save("location", f.get("location", "").strip()[:120] or "Nairobi, Kenya")
            settings.save("international_note", f.get("international_note", "").strip()[:240])
            settings.save("budget_ranges", budgets)
            log_activity("settings.updated", "settings", admin=current_admin())
            flash("Settings saved.", "ok")
            return redirect(url_for("admin.site_settings"))
        flash("Please fix the highlighted fields.", "error")
        s = {**s, **{k: f.get(k, "") for k in f if k in s}}
        s["budget_ranges"] = clean_lines(f.get("budget_ranges", ""), limit=12, max_len=60) or s["budget_ranges"]
    return render_template("admin/settings.html", s=s, errors=errors,
                           smtp=mailer.smtp_configured(), webhook=mailer.webhook_configured())
