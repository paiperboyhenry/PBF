# PBF Studio — website

A cinematic reception, a six-department creative warehouse, department portfolios with project pages, a six-step enquiry form and a private admin dashboard. Palette: Obsidian `#161616`, Soft Pearl `#F2F1ED`, Crimson `#710014` — nothing else.

**Stack:** Python 3.11+ · Flask · SQLite · Pillow · hand-written CSS/JS (no front-end framework, no build step).

> **Why not Next.js + Supabase?** The build environment had no package-registry access, so neither could be installed. Rather than ship something unrunnable, this is a deliberately small, dependency-light stack that runs anywhere Python does. Everything visitor-facing (the HTML, CSS, JS, the data model) ports cleanly if you later want Next.js/Supabase; the admin and enquiry logic would need rewriting.

---

## Run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # optional for local development
flask --app wsgi create-admin you@yourdomain.com --name "Your Name"   # prompts for a password
flask --app wsgi run --port 5000
```

Open <http://127.0.0.1:5000> and sign in at `/admin`. `flask --app wsgi doctor` shows which integrations are configured (it never sends anything).

There is **no default password anywhere**. The admin is created by you, with a password of at least 12 characters, mixing upper and lower case and including a number (checked on creation).

## Put it live

1. Host anywhere that runs Python (a small VPS, Render, Railway, Fly, etc.) behind HTTPS.
2. Set the environment variables below. At minimum: `PBF_ENV=production`, `SECRET_KEY`, `SITE_URL`, and `PBF_DATA_DIR` pointing at **persistent storage**.
3. Start with `gunicorn wsgi:app --workers 2 --bind 0.0.0.0:$PORT`.
4. If you are behind one reverse proxy (nginx, Cloudflare, most PaaS), set `PROXY_HOPS=1` so client IPs and HTTPS are detected correctly.
5. Create the first admin: either `flask --app wsgi create-admin …` on the server, or set a long random `SETUP_TOKEN`, visit `/admin/setup` once, then **remove the token**. The setup page is closed (404) whenever the token is unset or an admin already exists.
6. **Back up `PBF_DATA_DIR`.** It holds the SQLite database, uploaded images/videos (`media/`) and private enquiry attachments (`private/`).

Production refuses to start without `SECRET_KEY`.

## Environment variables

Real environment variables win over a `.env` file placed next to `wsgi.py`.

| Variable | Needed for | Notes |
|---|---|---|
| `PBF_ENV` | production | `production` turns on secure cookies and HSTS |
| `SECRET_KEY` | **production (required)** | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `SITE_URL` | SEO | Canonical URLs, sitemap, share links, e.g. `https://pbf.studio` |
| `PBF_DATA_DIR` | production | Persistent folder for DB and uploads |
| `PROXY_HOPS` | behind a proxy | Usually `1` |
| `SETUP_TOKEN` | optional | First-admin web setup; remove afterwards |
| `CONTACT_EMAIL`, `WHATSAPP_NUMBER`, `INSTAGRAM_URL`, `TIKTOK_URL` | Contact page, footer, WhatsApp follow-up | Also editable in **Admin → Settings** (those win). Anything left empty is simply not shown — nothing is invented |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`, `SMTP_STARTTLS` | Acknowledgement email to the enquirer | Without SMTP, enquiries are still saved and the visitor is told no email was sent |
| `NOTIFY_EMAIL` | Studio alert on new enquiry | Needs SMTP. Also in Admin → Settings |
| `NOTIFY_WEBHOOK_URL` | Studio alert without SMTP | Slack/Discord-style incoming webhook |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | Optional extra bot protection | Cloudflare Turnstile. Fails closed if enabled but unreachable |
| `MAX_IMAGE_MB` (15), `MAX_VIDEO_MB` (200), `MAX_ATTACHMENT_MB` (8), `SESSION_HOURS` (8) | Limits | |

## What you manage in the admin

- **Overview** — counts of projects, departments and enquiries by status (real numbers only).
- **Projects** — create, edit, preview drafts, publish, unpublish, delete (with confirmation). Cover image, gallery, video link or upload, services, date, and an honest label: **Client project**, **Concept project** or **Personal experiment**. Concept work is never shown as client work.
- **Departments** — descriptions, imagery, visibility and ordering of the six departments.
- **Enquiries** — every submission, with status *New / Contacted / In discussion / Won / Closed*, private notes (never public), attachment download, CSV export, delivery status of the emails.
- **Settings** — contact details, enquiry budget ranges, notification address.

A newly installed site has **no portfolio content** and shows tasteful "awaiting publication" states until you publish real work. No clients, testimonials, awards or results are invented anywhere.

## What has been verified — and what has not

**Verified (automated, 59 tests passing, plus real-browser runs in Chromium):**
- Reception, the three choices, department picker, warehouse doors → department pages, back-navigation.
- Intro: full / short / none, skip button, remembered preference, no replay within a session, reduced-motion, simplified mobile version.
- Enquiry: six steps, per-step validation, server-side validation, honeypot, timing check, rate limiting, CSRF, attachment content checks, enquiry saved and visible in admin, status changes, private notes, honest success/failure screens (a failed save never shows success).
- Admin: sign-in, session invalidation, create → preview → publish → appears in the right department → unpublish hides it, image optimisation (EXIF stripped, WebP), upload validation.
- Security headers/CSP, escaped output, CSV formula neutralising, safe redirects, path-traversal attempts.
- Mobile (iPhone 13 profile) and tablet: no horizontal overflow on the main pages; persistent *Start a project* / *Contact* bar.

**Not verified — needs your credentials, so test it after connecting:**
- **Email**: the SMTP path is covered by tests with a stubbed mail function only. It has **not** been sent through a real mail server. After setting `SMTP_*`, submit a test enquiry and confirm both emails arrive; the admin enquiry page shows `sent`/`failed` for each.
- **Webhook** and **Cloudflare Turnstile**: implemented, never called against the real services.
- **WhatsApp**: the follow-up button appears only when a number is set; it opens `wa.me` with a pre-filled message. Untested against a real number.
- Real-device testing (iOS Safari, Android Chrome), Lighthouse scores, and a load test.

## Known limitations (be aware, not hidden)

- **Logo** is a typographic placeholder ("PBF STUDIO" with a crimson bar). Replace it with the real mark when ready.
- **Imagery** in the reception and warehouse is built in CSS/SVG, not photography. The reception is a stylised room, not a render of your actual space — swap in real renders/photos by editing `pbf/static/css/scenes.css` and `templates/public/home.html`.
- **No sound design**, by choice.
- SQLite is right for a studio site with modest traffic on a single server; it does not scale across several app servers.
- Fonts (Inter, GFS Baskerville) are subset and self-hosted; Fashion House uses the serif for its atelier look.

## Layout

```
pbf/            app: config, db (schema.sql, seed.py), models, security, media, mailer,
                public.py, enquiry.py, admin.py, templates/, static/
tools/          make_assets.py — regenerates textures, favicon and subset fonts
tests/          pytest suite (python -m pytest -q)
wsgi.py         entry point
```

Useful commands: `flask --app wsgi doctor` · `flask --app wsgi create-admin EMAIL` · `flask --app wsgi reset-password EMAIL`.
