# Jobtra

A self-hosted web app for tracking your job hunt end to end — applications, documents, and recruiter emails — in one place. It runs locally on SQLite, ships with a clean HTML/JS frontend served by FastAPI, and uses an LLM (local or hosted) to parse job postings and classify incoming email.

No accounts, no cloud, no telemetry. Your data lives in a single SQLite file on your machine.

<!-- Add screenshots to a docs/ folder and link them here, e.g.:
![Dashboard](docs/dashboard.png)
-->
<img width="1799" height="933" alt="demo" src="https://github.com/user-attachments/assets/3cc015cd-8c53-49b6-8047-769d6f2c421e" />


## Features

- **Application tracking** — CRUD over your applications with a six-stage pipeline: `open → applied → interview_done → rejected / rejected_after_interview → accepted`. Rich fields for company, position, city/address, HR email/phone, WhatsApp/Telegram, hours per week, languages, skills, and job type.
- **AI job parsing** — Paste a posting or drop in a URL and an LLM fills in the fields for you. Re-parse any saved job to refresh details from its original source.
- **One-click bookmarklet** — Save the job you're viewing in your browser straight to the tracker, no copy-paste.
- **Dashboard analytics** — Totals, active pipeline, interview count, rejection rate, and breakdowns by month, status, job type, city, and position, plus an interactive map of where you've applied (cities geocoded via OpenStreetMap) and a treemap view.
- **Document manager** — Upload résumés/cover letters, attach them to applications, and see where each is used. Files are de-duplicated by content hash.
- **Email sync & classification** — Connect IMAP mailboxes, sync messages, and have the LLM flag which are job-related and what they mean (rejection, interview invite, offer, …). Relevant emails auto-link to the matching application and can advance its status. Account passwords are encrypted at rest (Fernet); sync runs on a configurable schedule.
- **Import / export** — Bulk-import jobs from CSV or JSON (tolerant of column aliases and other tools' status vocabularies, with duplicate detection), and export your list back to CSV.
- **Pagination** — Jobs and emails page automatically once they exceed a per-page limit you set in Settings.
- **Dark / light theme** and a responsive UI with no build step.

## Tech stack

- **Backend:** Python 3.9+, [FastAPI](https://fastapi.tiangolo.com/), Uvicorn
- **Storage:** SQLite (single file), [cryptography](https://cryptography.io/) (Fernet) for email-password encryption
- **Frontend:** Plain HTML/CSS/JavaScript, no build step or framework ([Chart.js](https://www.chartjs.org/) and [Leaflet](https://leafletjs.com/) are loaded from a CDN for charts and the map)
- **LLM providers:** [Ollama](https://ollama.com/) (local, default), [LM Studio](https://lmstudio.ai/) (local), Anthropic, or OpenAI

## Quick start

The easiest way to run Jobtra — no terminal knowledge needed. After cloning (or downloading) the project:

- **macOS / Linux:** double-click `install-and-run.sh`, or run `./install-and-run.sh`
- **Windows:** double-click `run-windows.bat`

The first run creates a local Python environment, installs dependencies, starts the server, and opens <http://localhost:8001> in your browser. Later runs just start the app. Close the window (or press Ctrl+C) to stop it.

`jobs.db` is created automatically on first run, and the API docs live at `http://localhost:8001/docs`.

> **AI features are optional.** Everything except job parsing and email classification works without an LLM. For those, run [Ollama](https://ollama.com/) or [LM Studio](https://lmstudio.ai/) locally (no API key) or add an Anthropic/OpenAI key — see [Configuration](#configuration).

## Other ways to run

### Docker

```bash
cp .env.example .env         # fill in any API keys, optionally change HOST/PORT
docker compose -f docker-compose.yml up -d --build
# open http://localhost:8001
```

All state (`jobs.db`, encryption key, uploaded docs) lives on the named volume `jobtra-data` and survives rebuilds. Set `HOST` in `.env` to your LAN IP/hostname so the bookmarklet link points at the right address. Back up the volume with:

```bash
docker run --rm -v jobtra-data:/data -v "$PWD":/backup busybox \
  tar czf /backup/jobtra-data.tgz /data
```

For development with live reload, run `docker compose up` instead (the `docker-compose.override.yml` overlay adds `--reload` and a source bind-mount).

### Manual (Python venv)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r App/requirements.txt
uvicorn server:app --reload --app-dir App/src
# open http://localhost:8001
```

## Configuration

Copy `.env.example` to `.env` (at the repo root for Docker, or `App/.env` for local runs) and set what you need. All variables are optional.

| Variable | Default | Description |
| --- | --- | --- |
| `HOST` | `localhost` | Address used in the browser and for the bookmarklet link. Set to your LAN IP/hostname for remote access. |
| `PORT` | `8001` | Port the app is served on. |
| `ANTHROPIC_API_KEY` | — | Required only if you use the Anthropic provider. |
| `OPENAI_API_KEY` | — | Required only if you use the OpenAI provider. |
| `DB_PATH` | `jobs.db` | Path to the SQLite file. Set to a volume path (e.g. `/data/jobs.db`) for containers. |
| `SECRET_KEY_PATH` | `secret.key` | Path to the Fernet key that encrypts email passwords. Kept outside the DB by design. |
| `DOCS_DIR` | `~/.jobtra/docs` | Where uploaded documents are stored. |

Provider, model, email settings, per-page limit, and email keywords are configured in-app on the **Settings** page.

### LLM providers

Choose a provider and model under **Settings**:

- **Ollama** (default) — fully local, no key required. Start it with `ollama serve` and pull a model (e.g. `ollama pull llama3.1:8b`).
- **LM Studio** — fully local, no key required. Start its local server (Developer tab → Start Server, default port `1234`) and load a model.
- **Anthropic** — set `ANTHROPIC_API_KEY`.
- **OpenAI** — set `OPENAI_API_KEY`.

Email classification can use a different provider/model than job parsing.

### Email sync

On the **Email** page, add one or more IMAP accounts (host, port, username, app password). Passwords are encrypted with a Fernet key stored separately from the database. Messages sync on demand or automatically on the interval set in Settings, and the LLM classifies each as relevant/irrelevant and infers a status; relevant mail auto-links to the matching application.

### Save jobs with one click

The **Settings** page has a bookmarklet you can drag to your bookmarks bar. Click it on any job page to send the visible text to the tracker and save the job automatically. If you change `PORT`/`HOST`, re-drag the bookmarklet to update it.

## Project structure

```
.
├── App/
│   ├── requirements.txt          # runtime deps
│   ├── requirements-dev.txt      # + test deps
│   ├── src/
│   │   ├── server.py             # FastAPI app & router wiring
│   │   ├── config.py             # env-driven config
│   │   ├── db.py                 # SQLite access + schema/migrations
│   │   ├── settings.py           # app settings helpers
│   │   ├── util.py               # Pydantic models, validators
│   │   ├── parse.py / parser.py  # LLM job-posting parsing
│   │   ├── fetcher.py            # URL → text
│   │   ├── geocode.py            # city → lat/lng via Nominatim (cached)
│   │   ├── email_sync.py         # IMAP sync + email classification
│   │   ├── providers/            # ollama / lmstudio / anthropic / openai adapters
│   │   └── routers/              # navigation + /api/* endpoints
│   └── tests/                    # pytest suite
├── ui/                           # HTML/CSS/JS frontend (served at /static)
├── Dockerfile
├── docker-compose.yml            # production-ish run
├── docker-compose.override.yml   # dev overlay (reload + bind-mount)
├── install-and-run.sh            # macOS/Linux install & run launcher
├── run-windows.bat               # Windows install & run launcher
├── install.sh / install.bat      # standalone one-time installers
└── VERSION
```

## API

Interactive OpenAPI docs are available at `/docs` while the app is running. Highlights:

| Method & path | Purpose |
| --- | --- |
| `GET/POST /api/jobs`, `GET/PUT/DELETE /api/jobs/{id}` | Manage applications |
| `POST /api/jobs/import` | Bulk import (CSV/JSON) |
| `POST /api/parse` · `POST /api/jobs/{id}/reparse` | Parse a posting / re-parse a job |
| `GET/PUT /api/settings` · `GET /api/models` | App settings & available models |
| `GET/POST/DELETE /api/documents...` | Document management |
| `GET /api/email/messages` · `POST /api/email/sync` · `POST /api/email/process` | Email sync & classification |
| `GET/POST/DELETE /api/email/accounts...` | Email accounts |
| `GET /api/dashboard` | Dashboard analytics |

## Development

```bash
cd App
pip install -r requirements-dev.txt
python -m pytest            # fast unit + API tests (App/tests)
```

### UI tests (end-to-end, browser)

Browser-driven tests live in `App/ui_tests` and are **excluded from the default
run** (they're tagged `ui`) so the everyday suite stays fast and needs no
browser. They start a real Uvicorn server against a throwaway database and drive
the pages with Playwright/Chromium:

```bash
pip install pytest-playwright
python -m playwright install chromium   # or use a system Chromium (see below)
python -m pytest App/ui_tests -m ui     # run the UI suite
```

If Playwright can't install its bundled browser for your OS, point it at a
system Chromium/Chrome instead:

```bash
export CHROMIUM_PATH=/usr/bin/chromium-browser
python -m pytest App/ui_tests -m ui
```

The frontend has no build step — edit files under `ui/` and reload. Static assets are cache-busted by the `VERSION` file at the repo root.

## Data & privacy

- All data is stored locally in SQLite (`jobs.db`) plus uploaded files under `DOCS_DIR`. **Back up by copying these; reset by deleting `jobs.db`.**
- Email-account passwords are encrypted at rest with a Fernet key kept in a separate file (`SECRET_KEY_PATH`) so the key never sits inside the database it protects. **Keep that key safe — losing it makes stored passwords unrecoverable; leaking it defeats the encryption.**
- The app makes outbound network calls only to: your configured LLM provider (for parsing/classification), your IMAP server (for email sync), URLs you explicitly paste for parsing, and OpenStreetMap's Nominatim service (to geocode application cities for the dashboard map, queried once per new city and cached). There is no telemetry.

## Contributing

Issues and pull requests are welcome. Please run the test suite (`python -m pytest`) before submitting, and keep changes consistent with the existing style (plain JS on the frontend, no new frontend build tooling).

## License

Released under the [MIT License](LICENSE).
