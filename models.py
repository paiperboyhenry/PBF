"""Read-side data access for departments, projects and their media."""
from __future__ import annotations

import json

from .db import q
from .util import json_list

_DEPT_SQL = """
SELECT d.*, ci.path AS cover_path, ci.width AS cover_w, ci.height AS cover_h,
       ci.variants AS cover_variants, ci.alt AS cover_alt
FROM departments d
LEFT JOIN department_images ci ON ci.department_id = d.id AND ci.role = 'cover'
"""

_PROJECT_SQL = """
SELECT p.*, d.slug AS dept_slug, d.name AS dept_name, d.number AS dept_number,
       d.is_visible AS dept_visible, d.theme AS dept_theme,
       ci.id AS cover_id, ci.path AS cover_path, ci.width AS cover_w, ci.height AS cover_h,
       ci.variants AS cover_variants, ci.alt AS cover_alt
FROM projects p
JOIN departments d ON d.id = p.department_id
LEFT JOIN project_images ci ON ci.project_id = p.id AND ci.role = 'cover'
"""


def image_from(row, prefix: str = "cover_") -> dict | None:
    path = row[f"{prefix}path"]
    if not path:
        return None
    return {
        "path": path,
        "width": row[f"{prefix}w"],
        "height": row[f"{prefix}h"],
        "variants": json_list(row[f"{prefix}variants"]),
        "alt": row[f"{prefix}alt"] or "",
    }


def _dept(row) -> dict:
    d = dict(row)
    d["services"] = json_list(d["services"])
    d["categories"] = json_list(d["categories"])
    d["cover"] = image_from(row)
    return d


def _project(row) -> dict:
    p = dict(row)
    p["services"] = json_list(p["services"])
    p["cover"] = image_from(row)
    return p


def departments(visible_only: bool = True) -> list[dict]:
    where = " WHERE d.is_visible = 1" if visible_only else ""
    return [_dept(r) for r in q(_DEPT_SQL + where + " ORDER BY d.sort_order, d.number")]


def department_by_slug(slug: str, visible_only: bool = True) -> dict | None:
    sql = _DEPT_SQL + " WHERE d.slug = ?" + (" AND d.is_visible = 1" if visible_only else "")
    row = q(sql, (slug,), one=True)
    return _dept(row) if row else None


def department_by_id(dept_id: int) -> dict | None:
    row = q(_DEPT_SQL + " WHERE d.id = ?", (dept_id,), one=True)
    return _dept(row) if row else None


def department_gallery(dept_id: int) -> list[dict]:
    rows = q(
        "SELECT * FROM department_images WHERE department_id = ? AND role = 'gallery' ORDER BY sort_order, id",
        (dept_id,),
    )
    return [_img(r) for r in rows]


def _img(r) -> dict:
    return {
        "id": r["id"], "path": r["path"], "width": r["width"], "height": r["height"],
        "variants": json_list(r["variants"]), "alt": r["alt"] or "",
    }


def projects(dept_id: int | None = None, published_only: bool = True, limit: int | None = None,
             visible_depts_only: bool = True) -> list[dict]:
    where, args = [], []
    if dept_id is not None:
        where.append("p.department_id = ?")
        args.append(dept_id)
    if published_only:
        where.append("p.status = 'published'")
    if visible_depts_only:
        where.append("d.is_visible = 1")
    sql = _PROJECT_SQL + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY p.sort_order ASC, p.project_date DESC, p.id DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [_project(r) for r in q(sql, args)]


def project_by_slug(dept_id: int, slug: str) -> dict | None:
    row = q(_PROJECT_SQL + " WHERE p.department_id = ? AND p.slug = ?", (dept_id, slug), one=True)
    return _project(row) if row else None


def project_by_id(project_id: int) -> dict | None:
    row = q(_PROJECT_SQL + " WHERE p.id = ?", (project_id,), one=True)
    return _project(row) if row else None


def project_gallery(project_id: int) -> list[dict]:
    rows = q(
        "SELECT * FROM project_images WHERE project_id = ? AND role = 'gallery' ORDER BY sort_order, id",
        (project_id,),
    )
    return [_img(r) for r in rows]


def project_videos(project_id: int) -> list[dict]:
    from .util import parse_video_url
    out = []
    for r in q("SELECT * FROM project_videos WHERE project_id = ? ORDER BY sort_order, id", (project_id,)):
        v = dict(r)
        v["embed"] = parse_video_url(v["url"]) if v["kind"] == "link" else None
        out.append(v)
    return out


def neighbours(project: dict) -> tuple[dict | None, dict | None]:
    """Previous/next published project in the same department (display order)."""
    siblings = projects(dept_id=project["department_id"])
    ids = [s["id"] for s in siblings]
    if project["id"] not in ids:
        return None, None
    i = ids.index(project["id"])
    prev_p = siblings[i - 1] if i > 0 else None
    next_p = siblings[i + 1] if i < len(siblings) - 1 else None
    return prev_p, next_p


def project_counts() -> dict:
    rows = q(
        """SELECT d.id, d.name, d.number,
                  SUM(CASE WHEN p.status='published' THEN 1 ELSE 0 END) AS published,
                  SUM(CASE WHEN p.status='draft' THEN 1 ELSE 0 END) AS drafts
           FROM departments d LEFT JOIN projects p ON p.department_id = d.id
           GROUP BY d.id ORDER BY d.sort_order, d.number"""
    )
    return {
        "by_department": [
            {"id": r["id"], "name": r["name"], "number": r["number"],
             "published": r["published"] or 0, "drafts": r["drafts"] or 0}
            for r in rows
        ]
    }


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)
