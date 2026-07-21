# IntelliMOST

> **Transform your shop floor with AI-powered work study.** IntelliMOST brings MOST studies, live production performance, quality actions, and improvement signals into one Flask application.

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/release/python-3110/)
[![Flask](https://img.shields.io/badge/Flask-application-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Last commit](https://img.shields.io/github/last-commit/shahram8708/IntelliMost)](https://github.com/shahram8708/IntelliMost/commits/main)
[![Repository](https://img.shields.io/badge/GitHub-shahram8708%2FIntelliMost-181717?logo=github)](https://github.com/shahram8708/IntelliMost)

## Table of Contents

- [About the Project](#about-the-project)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Variables](#environment-variables)
  - [Running the Project](#running-the-project)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Configuration](#configuration)
- [Testing](#testing)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [Roadmap](#roadmap)
- [License](#license)
- [Acknowledgements](#acknowledgements)
- [Contact / Author](#contact--author)

## About the Project

IntelliMOST is a multi-plant manufacturing operations application for teams that need to turn work observations and production data into action. It couples Maynard Operation Sequence Technique (MOST) work studies with shift output, downtime, rejections, OEE, CAPA, root-cause analysis, alerts, and scheduled improvement opportunities. The app is aimed at industrial engineers, plant managers, QA teams, shift supervisors, operators, and platform administrators. Its practical edge is the closed loop: identify a standard-time or shop-floor problem, investigate it, track corrective action, and export the evidence from the same system.

## Key Features

- Creates guided MOST studies using General Move, Controlled Move, and Tool Use sequences, then calculates TMU, standard time, and allowance-adjusted time.
- Supports manual timer, direct-entry, and video-upload study observations; published studies can be revised, archived, compared with recent shifts, and exported as PDFs.
- Records production output, downtime, and rejection events against active shifts and recalculates Availability, Performance, Quality, and OEE.
- Provides role-aware dashboards for seven roles, from super administrators through operators, with plant-scoped data access.
- Manages CAPA records end to end, including evidence uploads, comments, status changes, 5 Whys RCA workspaces, and CAPA PDF exports.
- Evaluates configurable metric alert rules every five minutes, emails recipients/escalation recipients, and lets users acknowledge alerts or turn them into CAPAs.
- Generates daily improvement opportunities from changeover, rejection, downtime Pareto, and standard-time-gap analyses.
- Offers Gemini-backed suggestions for MOST indices, improvement wording, and root-cause context, with rule-based fallbacks when no API key is configured.
- Exports audit logs as CSV, and production-quality, downtime, and configurable reports as Excel or PDF.

## Tech Stack

| Area | Technologies |
| --- | --- |
| **Frontend** | Server-rendered Jinja2 templates; HTML; CSS; vanilla JavaScript; Bootstrap classes; Chart.js usage in analytics/dashboard scripts; inline SVG logo |
| **Backend** | Python **3.11** (Docker base), Flask, Flask-SQLAlchemy, Flask-Migrate/Alembic, Flask-Login, Flask-WTF/WTForms, Flask-Bcrypt, Flask-Mail, Flask-Limiter, Flask-APScheduler, Flask-Babel, python-dotenv, itsdangerous |
| **Database** | SQLAlchemy ORM; SQLite by default for development and production fallback; PostgreSQL supported through `DATABASE_URL` |
| **Reporting & AI** | WeasyPrint for PDFs, openpyxl for XLSX, Google Gen AI (`google-genai`) with Google Search grounding, Pillow, Requests, python-dateutil, pytz |
| **DevOps / runtime** | Gunicorn, Docker, Docker Compose, Python slim Linux image |
| **Security & operations** | CSRF protection, bcrypt password hashes, login lockout fields, role checks, rate limiting, secure production cookies, SMTP notifications, audit logs, APScheduler jobs |

Dependency versions are intentionally **not pinned** in `requirements.txt`; the only explicit runtime version in the repository is Python 3.11 in `Dockerfile`.

## Project Structure

```text
IntelliMost/
├── .env.example                 # Environment-variable template
├── .gitignore                   # Python, virtualenv, database/migration exclusions
├── Dockerfile                   # Python 3.11 / Gunicorn production image
├── docker-compose.yml           # Single web-service Compose configuration
├── requirements.txt             # Unpinned Python dependencies
├── config.py                    # Development and production Flask configuration
├── run.py                       # Local development entry point
├── wsgi.py                      # Production WSGI entry point
├── app/                         # Flask application package
│   ├── __init__.py              # App factory, blueprint registration, filters, seed and scheduler bootstrapping
│   ├── extensions.py            # Shared Flask extension instances
│   ├── forms/                   # WTForms for admin, auth, MOST, quality, reporting, and profile flows
│   ├── models/                  # SQLAlchemy entities: plants, lines, machines, shifts, studies, CAPAs, alerts, users, and more
│   ├── routes/                  # Blueprint controllers for every web area plus JSON API endpoints
│   ├── services/                # OEE/MOST calculations, AI, alerts, reports, email, improvements, and scheduled jobs
│   ├── utils/                   # Authorization decorators and audit/helper functions
│   ├── static/                  # main.css, application JavaScript, and logo.svg
│   └── templates/               # Jinja views
│       ├── admin/               # Tenant, users, plant/line/machine/SKU, audit, lead, and integration screens
│       ├── alerts/, analytics/, auth/, capa/, dashboard/  # Operational feature views
│       ├── downtime/, improvements/, production/, profile/, rca/, rejections/, reports/
│       ├── work_study/          # Study wizard, detail, edit, comparison, and export views
│       ├── reports_pdf/         # PDF layouts for MOST, CAPA, and generic reports
│       ├── components/          # Shared header, sidebar, cards, alerts, pagination, and footer
│       ├── errors/              # 403, 404, and 500 pages
│       ├── base.html            # Authenticated layout
│       └── base_public.html     # Public-site layout
└── seeds/                       # Deterministic demonstration dataset and seed runner
    ├── __init__.py
    └── seed.py                  # Plants, users, equipment, historical operations, alerts, CAPAs, and audit data
```

## Getting Started

### Prerequisites

Install the following before starting:

- [Git](https://git-scm.com/downloads) to clone the repository.
- [Python 3.11](https://www.python.org/downloads/release/python-3110/) to match the included Docker image. A modern Python 3 release may work, but the repository verifies no other version.
- [pip](https://pip.pypa.io/en/stable/installation/) and optionally [venv](https://docs.python.org/3/library/venv.html) for an isolated local environment.
- Optional: [Docker Desktop](https://www.docker.com/products/docker-desktop/) and Docker Compose for containerized execution.
- Optional: PostgreSQL and Redis when using `DATABASE_URL` and `REDIS_URL` in production. SQLite and in-memory rate-limit storage work out of the box for local development.
- Linux container deployments need the system libraries used by WeasyPrint; the supplied Dockerfile installs them for you.

### Installation

1. Clone the project and enter it.

   ```bash
   git clone https://github.com/shahram8708/IntelliMost.git
   cd IntelliMost
   ```

2. Create and activate a virtual environment.

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

   On Windows PowerShell:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the application dependencies.

   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Create your local environment file and set at least a secure development secret.

   ```bash
   cp .env.example .env
   ```

5. Start the app. On its first successful startup, IntelliMOST creates the SQLite schema and loads its demonstration dataset if there are no users yet.

   ```bash
   python run.py
   ```

6. Open [http://localhost:5000](http://localhost:5000), select **Sign In**, and use a seeded account. For example:

   ```text
   Email: rajesh.sharma@intellimost.io
   Password: SuperAdmin@2024
   ```

   The seed file contains role-specific demo passwords. These accounts are demonstration data only—do not retain them in a reachable deployment.

### Environment Variables

Copy `.env.example` to `.env`. The table includes every environment variable read by the application, including the scheduler switch that is not present in the example file.

| Variable | Description | Example |
| --- | --- | --- |
| `SECRET_KEY` | Flask session, CSRF, and token-signing secret; replace the insecure config fallback in every real deployment. | `a-long-random-64-character-secret` |
| `DATABASE_URL` | Production SQLAlchemy database URL; falls back to `sqlite:///intellimost_prod.db` in production. | `postgresql://user:password@localhost:5432/intellimost_prod` |
| `MAIL_SERVER` | SMTP server for invitations, password resets, alerts, and CAPA notifications. | `smtp.gmail.com` |
| `MAIL_PORT` | SMTP port; the app enables TLS. | `587` |
| `MAIL_USERNAME` | SMTP user name. | `your-email@gmail.com` |
| `MAIL_PASSWORD` | SMTP password or app password. | `your-app-password` |
| `MAIL_DEFAULT_SENDER` | Sender address for outbound mail. | `noreply@intellimost.io` |
| `UPLOAD_FOLDER` | Root folder for profile photos, CAPA evidence, and study videos. | `uploads` |
| `FLASK_ENV` | Selects `development` or `production` configuration; unknown values resolve to development. | `development` |
| `GEMINI_API_KEY` | Enables Gemini calls for MOST, improvement, and RCA assistance; fallbacks remain available without it. | `your-gemini-api-key` |
| `APP_TIMEZONE` | Default display timezone; a user's plant timezone overrides it when available. | `Asia/Kolkata` |
| `REDIS_URL` | Flask-Limiter storage URI; the default is in-memory storage. | `redis://localhost:6379/0` |
| `DISABLE_SCHEDULER` | Set to `1` to avoid starting APScheduler—particularly helpful in tests or multi-worker environments. | `1` |

### Running the Project

**Development**

```bash
source .venv/bin/activate
export FLASK_ENV=development
python run.py
```

The development server binds to `0.0.0.0:5000`, uses debug mode, and deliberately disables the reloader. Development uses `sqlite:///intellimost_dev.db`.

**Production with Gunicorn**

```bash
source .venv/bin/activate
export FLASK_ENV=production
export SECRET_KEY="replace-this-with-a-strong-random-secret"
gunicorn --workers 4 --bind 0.0.0.0:5000 wsgi:app
```

**Docker / Compose**

```bash
cp .env.example .env
# Edit .env: set a real SECRET_KEY and production values.
docker compose up --build
```

The Compose service maps port `5000`, mounts `./uploads` at `/app/uploads`, and mounts `./intellimost_dev.db` for the SQLite database file. There is no frontend build step: Flask serves the checked-in static assets and templates directly.

## Usage

### Start from the role dashboard

Sign in and IntelliMOST directs users to `/dashboard/`. Dashboard context changes by role: super admins see cross-plant data, while other users are scoped to their assigned plant. Operators and supervisors can record activity; industrial engineers can build studies; QA and managers can own and close CAPAs.

### Create a MOST standard-time study

1. Go to **Work Study → New Study** (`/work-study/new`).
2. Choose the study context and observation method (`manual_timer`, `video_upload`, or `direct_entry`).
3. Add elements using `general_move`, `controlled_move`, or `tool_use` and valid MOST indices (`0, 1, 3, 6, 10, 16, 24, 32`).
4. Choose an allowance, finalize, and publish the study.

For a General Move, IntelliMOST totals `A1 + B1 + G1 + A2 + B2 + P1 + A3`, multiplies the index sum by 10 TMU, then converts TMU at **0.036 seconds/TMU**. It stores both raw standard time and allowance-adjusted time. Use the study detail page to export a PDF or compare the allowed time with recent production-shift cycle times.

### Close the production-quality loop

- Log an active shift's output at **Production → Log Output**.
- Log an unplanned downtime event and close it when resolved.
- Log rejected quantity with its defect type, probable cause, quality checkpoint, and batch reference.
- The system calculates OEE as `Availability × Performance × Quality`; the OEE service labels `>=85%` as `world_class`, `>=65%` as `acceptable`, and lower values as `requires_attention`.
- Create a CAPA from an alert or directly from **CAPA → New**, complete its 5 Whys workspace, upload evidence during a status update, and export the CAPA report.

### Use AI assistance safely

Set `GEMINI_API_KEY` to enable model-backed MOST-index suggestions and RCA/improvement assistance. The app's service includes rule-based suggestions if the key is absent or a model call fails, so core workflow does not depend on Gemini. Review every recommendation before publishing a standard or closing a quality action.

## API Documentation

All API routes are mounted below `/api` and require an authenticated Flask-Login session. Browser JavaScript sends `X-CSRFToken` with JSON POST requests; API clients must also supply a valid CSRF token or disable CSRF only in a controlled test configuration. Non-super-admin responses are scoped to the current user's plant.

| Method | URL | Description | Request body / query | Response |
| --- | --- | --- | --- | --- |
| `GET` | `/api/dashboard/metrics` | Retrieves line status, averaged OEE, attainment, alerts, downtime count, and recent alerts. | None | Object with `oee`, `attainment_percent`, `active_alerts`, `active_downtime_events`, `production_lines`, and `recent_alerts`. |
| `GET` | `/api/line/<id>/status` | Retrieves one line's active-shift output, target, and unresolved downtime. | Path `id` | Object with `line`, `output`, `target`, `active_downtime`. Returns 403 outside the user's plant. |
| `POST` | `/api/most/suggest-indices` | Gets an AI or fallback MOST-index recommendation. | JSON: `element_name`, `element_description`, optional `timer_duration_sec` | Suggestion object returned by `suggest_most_indices`. |
| `POST` | `/api/rca/similar-events` | Searches up to five plant-scoped RCA/CAPA matches using terms from the deviation description. | JSON: `deviation_description` | `{ "results": [{ "capa_number", "title", "root_cause_statement", "root_cause_category", "closed_at" }] }` |
| `POST` | `/api/alert/<id>/acknowledge` | Acknowledges an alert and logs the action. | JSON: optional `action`, `notes` | `{ "ok": true, "status": "acknowledged" }` |
| `GET` | `/api/shift/active` | Gets one active shift visible to the current user. | Optional query `line_id` | Shift object (`shift_id`, `line_name`, times and counts) or `{ "shift_id": null }`. |
| `GET` | `/api/downtime/active` | Lists unresolved downtime events for visible machines. | None | Array of `{ "id", "machine", "event_type", "start_time" }`. |

Example request after signing in through the web UI and obtaining the page's CSRF meta token:

```bash
curl -X POST http://localhost:5000/api/most/suggest-indices \
  -H 'Content-Type: application/json' \
  -H 'X-CSRFToken: <csrf-token>' \
  -b 'session=<flask-session-cookie>' \
  -d '{
    "element_name": "Pick component and place in fixture",
    "element_description": "Reach to bin, grasp a component, move it to the fixture, and position it.",
    "timer_duration_sec": 4.2
  }'
```

## Configuration

- **`config.py`** defines `DevelopmentConfig` and `ProductionConfig`. Development enables debugging and uses `intellimost_dev.db`; production disables debug, reads `DATABASE_URL`, sets secure/HTTP-only/Lax session cookie settings, limits uploads to 500 MB, and applies default rate limits of `200 per day;50 per hour`.
- **Application factory (`app/__init__.py`)** creates `uploads/profiles`, `uploads/evidence`, and `uploads/videos`; creates missing tables with `db.create_all()`; seeds only an empty user database; and registers blueprints, filters, error pages, and context data.
- **Scheduler** starts unless `DISABLE_SCHEDULER=1`. It evaluates alerts every 5 minutes, generates improvement opportunities daily at 01:00, checks overdue CAPAs daily at 08:00, and closes completed shifts every 15 minutes. Avoid running multiple schedulers against the same production database; designate one scheduler process or disable it on web workers.
- **Plant settings** customize timezone, industry type, subscription tier, contacts, production-line targets, shift duration, planned breaks, machines, SKUs, and three-level reason-code hierarchy through the admin screens.
- **Database evolution:** Flask-Migrate/Alembic is installed and initialized as an extension, but this repository has no committed `migrations/` directory. For schema changes, create and commit migrations rather than relying on `db.create_all()` in a long-lived production database.

## Testing

No test files, test runner configuration, or CI workflow are present in the repository. As a result, there is no project-provided automated test command or documented coverage baseline.

Before production use, add tests around role and plant scoping, CSRF-protected API mutations, MOST/OEE formulas, CAPA status rules, alert threshold evaluation, report exports, and scheduled jobs. Start with `pytest` plus an isolated SQLite test database and set `DISABLE_SCHEDULER=1` in the test environment.

## Deployment

### Deploy with Docker

1. Provision PostgreSQL and optionally Redis, or deliberately choose the SQLite fallback for a small single-instance setup.
2. Create production secrets and settings in `.env`; never deploy the values from `.env.example` unchanged.
3. Build and start the included image.

   ```bash
   docker compose up --build -d
   docker compose logs -f web
   ```

4. Put a TLS-terminating reverse proxy/load balancer in front of port 5000 and expose HTTPS rather than Gunicorn directly.
5. Persist the uploads volume and database independently of the container lifecycle. Back up the database and uploaded evidence.
6. Run exactly one scheduler-enabled application instance. Set `DISABLE_SCHEDULER=1` on any additional web replicas.

The `Dockerfile` installs WeasyPrint system libraries, creates `uploads` and `migrations` directories, exposes port 5000, and launches `gunicorn --workers 4 --bind 0.0.0.0:5000 wsgi:app`.

### Cloud / CI notes

The repository contains no platform manifests for Vercel, Heroku, AWS, or other cloud providers, and no GitHub Actions or other CI/CD pipeline. Deploy it as a conventional Python WSGI service using the Docker image or the Gunicorn command above, supplying managed PostgreSQL/Redis/SMTP as appropriate.

## Contributing

Contributions are welcome. This codebase already separates controllers, forms, models, and services, so keep new work in the same shape and avoid embedding business calculations in templates or routes.

1. Fork the repository and create a focused branch.

   ```bash
   git checkout -b feature/short-description
   ```

2. Create a virtual environment, install dependencies, configure `.env`, and verify the relevant workflow manually.
3. Add or update tests when you introduce the test suite; never commit `.env`, local databases, uploaded evidence, generated PDFs, or credentials.
4. Use clear Python names, preserve existing Flask blueprint boundaries, enforce role/plant scope, validate all form input, and use the existing audit helper for auditable actions.
5. Commit with an imperative message and push your branch.

   ```bash
   git add .
   git commit -m "Add concise description of change"
   git push origin feature/short-description
   ```

6. Open a pull request describing the problem, user roles affected, implementation, validation performed, screenshots for UI changes, and any migration/environment changes.

**Bug reports:** include expected versus actual behavior, reproduction steps, account role/plant context, browser or runtime version, sanitized logs, and screenshots where helpful. Never include session cookies, secrets, customer data, or uploaded evidence.

**Feature requests:** explain the manufacturing workflow, the role that needs it, success criteria, and whether it affects work-study calculation, production metrics, CAPA, reporting, or multi-plant scoping.

## Roadmap

The following items are inferred from the repository's current capabilities and gaps, not an official published plan.

- [x] Guided MOST work studies with PDF export and historical-shift comparison.
- [x] Production, downtime, rejection, OEE, CAPA/RCA, alerts, reports, audit logs, and role-aware administration.
- [x] Docker/Gunicorn execution and scheduled operational jobs.
- [ ] Add a committed test suite, coverage reporting, and CI checks.
- [ ] Pin and regularly update dependency versions; add a lockfile or constraints file.
- [ ] Commit database migrations and document a safe production migration workflow.
- [ ] Add health checks, structured logging, monitoring, and explicit scheduler leadership for horizontally scaled deployments.
- [ ] Publish an OSS license, release/version policy, and hosted demonstration or product screenshots.
- [ ] Strengthen deployment documentation around PostgreSQL drivers, Redis, backups, TLS, and production secrets.

## Acknowledgements

IntelliMOST is built on the Flask ecosystem and uses SQLAlchemy, Alembic, WTForms, WeasyPrint, openpyxl, Gunicorn, and Google Gen AI. The optional AI integration uses the [Google Gen AI SDK](https://github.com/googleapis/python-genai) and its Google Search grounding tool. The work-study calculator implements concepts from the Maynard Operation Sequence Technique (MOST), while operational performance is presented through the standard OEE Availability × Performance × Quality model.
