-- PBF Studio database schema (SQLite). Safe to run repeatedly.

CREATE TABLE IF NOT EXISTS admin_users (
  id            INTEGER PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE,
  name          TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  is_active     INTEGER NOT NULL DEFAULT 1,
  session_epoch INTEGER NOT NULL DEFAULT 0,
  last_login_at TEXT,
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS departments (
  id          INTEGER PRIMARY KEY,
  slug        TEXT NOT NULL UNIQUE,
  number      INTEGER NOT NULL,
  name        TEXT NOT NULL,
  tagline     TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL,
  services    TEXT NOT NULL DEFAULT '[]',
  categories  TEXT NOT NULL DEFAULT '[]',
  theme       TEXT NOT NULL DEFAULT 'gallery' CHECK (theme IN ('gallery','atelier')),
  is_visible  INTEGER NOT NULL DEFAULT 1,
  sort_order  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS department_images (
  id            INTEGER PRIMARY KEY,
  department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
  role          TEXT NOT NULL DEFAULT 'gallery' CHECK (role IN ('cover','gallery')),
  path          TEXT NOT NULL,
  width         INTEGER NOT NULL,
  height        INTEGER NOT NULL,
  variants      TEXT NOT NULL DEFAULT '[]',
  alt           TEXT NOT NULL DEFAULT '',
  sort_order    INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_department_cover ON department_images(department_id) WHERE role = 'cover';

CREATE TABLE IF NOT EXISTS projects (
  id            INTEGER PRIMARY KEY,
  department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
  slug          TEXT NOT NULL,
  title         TEXT NOT NULL,
  client_name   TEXT NOT NULL DEFAULT '',
  category      TEXT NOT NULL DEFAULT '',
  description   TEXT NOT NULL DEFAULT '',
  services      TEXT NOT NULL DEFAULT '[]',
  project_type  TEXT NOT NULL CHECK (project_type IN ('client','concept','personal')),
  project_date  TEXT,
  external_url  TEXT NOT NULL DEFAULT '',
  status        TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published')),
  sort_order    INTEGER NOT NULL DEFAULT 0,
  published_at  TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  UNIQUE (department_id, slug)
);
CREATE INDEX IF NOT EXISTS ix_projects_dept ON projects(department_id, status, sort_order);

CREATE TABLE IF NOT EXISTS project_images (
  id         INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  role       TEXT NOT NULL DEFAULT 'gallery' CHECK (role IN ('cover','gallery')),
  path       TEXT NOT NULL,
  width      INTEGER NOT NULL,
  height     INTEGER NOT NULL,
  variants   TEXT NOT NULL DEFAULT '[]',
  alt        TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_project_cover ON project_images(project_id) WHERE role = 'cover';

CREATE TABLE IF NOT EXISTS project_videos (
  id         INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL CHECK (kind IN ('link','upload')),
  url        TEXT NOT NULL,
  title      TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enquiries (
  id             INTEGER PRIMARY KEY,
  ref            TEXT NOT NULL DEFAULT '',
  full_name      TEXT NOT NULL,
  business_name  TEXT NOT NULL DEFAULT '',
  email          TEXT NOT NULL,
  whatsapp       TEXT NOT NULL DEFAULT '',
  country        TEXT NOT NULL DEFAULT '',
  services       TEXT NOT NULL DEFAULT '[]',
  service_other  TEXT NOT NULL DEFAULT '',
  description    TEXT NOT NULL,
  budget         TEXT NOT NULL DEFAULT '',
  timeline       TEXT NOT NULL DEFAULT '',
  reference_links TEXT NOT NULL DEFAULT '[]',
  extra_notes    TEXT NOT NULL DEFAULT '',
  status         TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','contacted','in_discussion','won','closed')),
  ip_hash        TEXT NOT NULL DEFAULT '',
  user_agent     TEXT NOT NULL DEFAULT '',
  ack_status     TEXT NOT NULL DEFAULT 'not_configured',
  notify_status  TEXT NOT NULL DEFAULT 'not_configured',
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_enquiries_status ON enquiries(status, created_at);

CREATE TABLE IF NOT EXISTS enquiry_notes (
  id         INTEGER PRIMARY KEY,
  enquiry_id INTEGER NOT NULL REFERENCES enquiries(id) ON DELETE CASCADE,
  admin_id   INTEGER REFERENCES admin_users(id) ON DELETE SET NULL,
  body       TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enquiry_files (
  id            INTEGER PRIMARY KEY,
  enquiry_id    INTEGER NOT NULL REFERENCES enquiries(id) ON DELETE CASCADE,
  original_name TEXT NOT NULL,
  stored_name   TEXT NOT NULL,
  mime          TEXT NOT NULL,
  size          INTEGER NOT NULL,
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS site_settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_log (
  id           INTEGER PRIMARY KEY,
  admin_id     INTEGER REFERENCES admin_users(id) ON DELETE SET NULL,
  actor        TEXT NOT NULL DEFAULT '',
  action       TEXT NOT NULL,
  subject_type TEXT NOT NULL DEFAULT '',
  subject_id   INTEGER,
  detail       TEXT NOT NULL DEFAULT '',
  created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_activity_created ON activity_log(created_at);

CREATE TABLE IF NOT EXISTS rate_events (
  id  INTEGER PRIMARY KEY,
  key TEXT NOT NULL,
  ts  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_rate_key_ts ON rate_events(key, ts);
