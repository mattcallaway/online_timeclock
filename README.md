# TimeClock — Employee Time & Scheduling App

A lightweight, self-hostable Python/Flask employee timeclock and scheduling
application designed for deployment on a Linode (or any Linux) server.

## Quick Start (Development)

### Prerequisites
- Python 3.11+
- pip

### Setup

```bash
# 1. Create and activate virtual environment
python -m venv venv
source venv/bin/activate       # Linux/macOS
venv\Scripts\activate          # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your .env file
cp .env.example .env
# Edit .env — set SECRET_KEY, ADMIN_PASSWORD, etc.

# 4. Initialise database and create admin user
python init_db.py

# 5. Run development server
python run.py
# App runs at http://127.0.0.1:5000
```

## Project Structure

```
app/
  auth/       — Login / logout / password change
  admin/      — Admin dashboard, user management, audit log, edit requests
  employee/   — Employee dashboard, profile, own audit history
  timeclock/  — Clock-in/out, time entries, edit requests, CSV export
  schedule/   — Shift calendar (week view), admin CRUD
  messages/   — Internal messaging (admin ↔ employee only)
  models.py   — All SQLAlchemy models + log_audit() helper
  config.py   — Environment-based Flask config
  templates/  — Jinja2 HTML templates
deploy/
  nginx.conf.example          — Nginx reverse proxy config
  gunicorn.service.example    — systemd service for Gunicorn
init_db.py    — One-time DB init + admin seed
run.py        — Development server entrypoint
wsgi.py       — Gunicorn / production entrypoint
```

## Environment Variables (.env)

| Variable        | Required | Description                          |
|-----------------|----------|--------------------------------------|
| SECRET_KEY      | Yes      | Flask session secret (random string) |
| DATABASE_URL    | Yes      | SQLite or PostgreSQL URL             |
| FLASK_ENV       | No       | `development` or `production`        |
| ADMIN_USERNAME  | Yes*     | Used by init_db.py only              |
| ADMIN_PASSWORD  | Yes*     | Used by init_db.py only              |
| ADMIN_FULL_NAME | No       | Used by init_db.py only              |
| ADMIN_EMAIL     | No       | Used by init_db.py only              |

*Required only when running init_db.py

## Production Deployment (Linode)

1. Upload project to `/home/timeclock/timeclock/`
2. Create virtualenv and install requirements
3. Set up `.env` with production values (PostgreSQL URL, long random SECRET_KEY)
4. Run `python init_db.py` once
5. Copy `deploy/gunicorn.service.example` → `/etc/systemd/system/timeclock.service`, adjust paths
6. `sudo systemctl enable timeclock && sudo systemctl start timeclock`
7. Copy `deploy/nginx.conf.example` → `/etc/nginx/sites-available/timeclock`, adjust domain
8. `sudo ln -s /etc/nginx/sites-available/timeclock /etc/nginx/sites-enabled/`
9. `sudo nginx -t && sudo systemctl reload nginx`
10. (Recommended) Obtain SSL: `sudo certbot --nginx -d your-domain.com`

## Switching to PostgreSQL

Change `DATABASE_URL` in `.env`:
```
DATABASE_URL=postgresql://user:password@localhost/timeclock_db
```
Then run `python init_db.py` (or `flask db upgrade` if using migrations).

## Key Features

- **Clock In / Clock Out** with live shift timer
- **6-hour overdue reminder** on employee and admin dashboards
- **Full audit trail** — every change logged with old/new values, actor, IP, timestamp
- **Time entry edit requests** — employee submits, admin approves/denies
- **Admin direct edit** with required reason (always logged)
- **Internal messaging** — admin ↔ employee only, read/unread tracking
- **Scheduling calendar** — weekly view, admin CRUD, employee view-only
- **CSV exports** — admin exports all, employees export own
- **Role-based access control** — strict server-side enforcement
- **Soft deactivation** — users deactivated, not deleted; all records preserved
- **Remember Me** — 30-day persistent sessions
- **Confirm modals** — all destructive actions require confirmation
