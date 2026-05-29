# Job Application Tracker — System Design

A minimal web app to track job applications. CRUD on a list of jobs, displayed in a table, persisted to a local SQLite database. Includes AI-assisted parsing: paste a raw job posting **or a job URL**, get a pre-filled form back, review, save. Parser provider is configurable in a Settings page — choose between Ollama (local), Anthropic Claude, or OpenAI, with the model dropdown populated live from each provider's API.

## Goals & non-goals

**Goals**

- Add, view, edit, delete job application records.
- Parse pasted job descriptions **or job URLs** via a configurable LLM provider (Ollama / Anthropic / OpenAI) into structured form data; user reviews before saving.
- Settings page to pick provider + model. Model list fetched live from the active provider.
- Persist to local SQLite file (survives restarts; can be backed up by copying one file).
- Single-page UI, no build step, no frameworks.
- Runnable with two commands (plus Ollama running separately if used).

**Non-goals**

- Authentication / multi-user. Single-user, single-machine (or self-hosted on the user's LAN).
- Scraping protected job boards (LinkedIn, Indeed) that require login or render via JavaScript — only static HTML is supported.
- Email integration, notifications.
- Mobile-specific design. Should work on mobile browsers, but desktop is primary.
- Storing API keys in the database. Keys live in `.env` only.

## Tech stack

| Layer    | Choice                          | Why                                                       |
| -------- | ------------------------------- | --------------------------------------------------------- |
| Backend  | Python 3.10+ with FastAPI       | Minimal boilerplate, auto API docs at `/docs`             |
| DB       | SQLite via stdlib `sqlite3`     | Zero install, one file, no ORM needed                     |
| LLM      | Ollama / Anthropic / OpenAI     | Provider picked at runtime; all called via HTTP           |
| Config   | `.env` for keys, SQLite for choices | Keys out of the DB; user prefs persist across restarts |
| Frontend | One `index.html` with vanilla JS | No build, no framework, no node_modules                   |
| Serving  | FastAPI serves the HTML + API   | One process, one port (default 8000)                      |

Dependencies: `fastapi`, `uvicorn`, `httpx`, `python-dotenv`. That's it.

Ollama is **not** a Python dependency — it's installed separately from `ollama.com` and runs as its own background service. Anthropic and OpenAI are accessed via plain HTTP through `httpx`; no SDK packages are added.

## Project structure

```
job-tracker/
├── server.py             # FastAPI app: API routes + serves index.html
├── db.py                 # SQLite connection + schema init + CRUD helpers
├── settings.py           # Read/write the singleton settings row
├── fetcher.py            # Fetch URL → cleaned plain text (for LLM input)
├── providers/
│   ├── __init__.py       # get_provider(name) factory
│   ├── base.py           # Provider protocol: parse() and list_models()
│   ├── ollama.py         # Ollama implementation
│   ├── anthropic.py      # Claude implementation
│   └── openai.py         # OpenAI implementation
├── index.html            # Main page (HTML + CSS + JS in one file)
├── settings.html         # Settings page (same style, separate file)
├── jobs.db               # SQLite file (created on first run, gitignored)
├── .env                  # API keys (gitignored)
├── .env.example          # Template, committed
├── requirements.txt      # fastapi, uvicorn, httpx, python-dotenv
└── README.md             # How to run (incl. Ollama setup + key setup)
```

## Data model

Two tables: `jobs` and `settings`.

### `jobs`

```sql
CREATE TABLE IF NOT EXISTS jobs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  position      TEXT    NOT NULL,
  company       TEXT    NOT NULL,
  description   TEXT    DEFAULT '',
  date_applied  TEXT    NOT NULL,                  -- ISO date 'YYYY-MM-DD'
  status        TEXT    NOT NULL DEFAULT 'open',
  address       TEXT    DEFAULT '',
  city          TEXT    DEFAULT '',
  hr_email      TEXT    DEFAULT '',
  hr_phone      TEXT    DEFAULT '',
  skills        TEXT    DEFAULT '',                -- comma-separated, e.g. "Kotlin,Spring,PostgreSQL"
  source_url    TEXT    DEFAULT '',                -- URL the job was parsed from (if any)
  source_text   TEXT    DEFAULT '',                -- Raw posting text used at parse time (for re-parse)
  created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  CHECK (status IN ('open','applied','interview_done','rejected','rejected_after_interview','accepted'))
);
```

`source_url` and `source_text` are populated automatically when a job is created via the parse flow. They're hidden from the main table view but visible in the expanded row and the edit form. They exist for one purpose: re-parsing.

### `settings`

A singleton table: always exactly one row with `id = 1`. Used to persist the user's provider/model choice across restarts.

```sql
CREATE TABLE IF NOT EXISTS settings (
  id        INTEGER PRIMARY KEY CHECK (id = 1),
  provider  TEXT NOT NULL DEFAULT 'ollama',     -- 'ollama' | 'anthropic' | 'openai'
  model     TEXT NOT NULL DEFAULT 'llama3.1:8b'
);

-- Seed the row on init:
INSERT OR IGNORE INTO settings (id, provider, model) VALUES (1, 'ollama', 'llama3.1:8b');
```

`settings.py` exposes `get_settings()` and `update_settings(provider, model)`. API keys are **never** stored here — they come from `.env`.

### Schema migration

Since `source_url` and `source_text` were added after the initial release, `db.py` runs an idempotent migration at startup:

```python
def migrate():
    cols = {row['name'] for row in conn.execute("PRAGMA table_info(jobs)")}
    if 'source_url' not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN source_url TEXT DEFAULT ''")
    if 'source_text' not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN source_text TEXT DEFAULT ''")
    conn.commit()
```

Existing rows get empty strings for both fields — the re-parse button is simply hidden on jobs without a source.

### Status values

| Value                      | UI label                |
| -------------------------- | ----------------------- |
| `open`                     | Open                    |
| `applied`                  | Applied                 |
| `interview_done`           | Interview done          |
| `rejected`                 | Rejected                |
| `rejected_after_interview` | Rejected after interview |
| `accepted`                 | Accepted                |

Skills are stored as a single comma-separated string. Trim whitespace around each on save; split on `,` on display. Simpler than a join table and fine for manual entry.

## API

All under `/api`. JSON in, JSON out. No auth.

| Method | Path                | Body                              | Response                  | Notes                                          |
| ------ | ------------------- | --------------------------------- | ------------------------- | ---------------------------------------------- |
| GET    | `/api/jobs`         | —                                 | `Job[]`                   | Ordered by `date_applied DESC`                 |
| GET    | `/api/jobs/{id}`    | —                                 | `Job`                     | 404 if missing                                 |
| POST   | `/api/jobs`         | `JobInput`                        | `Job` (with new `id`)     | 201 on create                                  |
| PUT    | `/api/jobs/{id}`    | `JobInput`                        | `Job` (updated)           | 404 if missing; updates `updated_at`           |
| DELETE | `/api/jobs/{id}`    | —                                 | `{ deleted: true }`       | 404 if missing                                 |
| POST   | `/api/parse`        | `{ "text"?: "...", "url"?: "..." }` | `{ ...JobInput, source_url, source_text }` | Either field is required (not both). URL → server fetches HTML, strips to text, then parses. Response includes the source fields so the client can save them. |
| POST   | `/api/jobs/{id}/reparse` | —                            | `Job` (updated)           | Re-runs parsing on the stored `source_url` (preferred) or `source_text`. 400 if neither exists. Updates parsed fields in place; preserves `date_applied`, `status`, and `id`. |
| GET    | `/api/settings`     | —                                 | `{provider, model, providers, key_status}` | Includes static provider list + which keys are set |
| PUT    | `/api/settings`     | `{ "provider": "...", "model": "..." }` | `{provider, model}` | Validates provider is one of the three         |
| GET    | `/api/models?provider=X` | —                            | `{ models: string[] }`    | Live fetch from provider's API. 503 on failure. |

### `JobInput` (request body)

```json
{
  "position": "Backend Developer",
  "company": "ACME GmbH",
  "description": "Spring Boot microservices role",
  "date_applied": "2026-05-20",
  "status": "applied",
  "address": "Hauptstr. 1",
  "city": "Dresden",
  "hr_email": "hr@acme.de",
  "hr_phone": "+49 351 1234567",
  "skills": "Kotlin, Spring Boot, PostgreSQL, Docker"
}
```

Validation:

- `position`, `company`, `date_applied` are required and non-empty.
- `status` must be one of the six values above; defaults to `open` if omitted.
- `hr_email` is not strictly validated server-side beyond being a string — keep validation lax to avoid blocking weird real-world inputs.
- All other fields default to empty string.

### `Job` (response)

`JobInput` plus `id`, `created_at`, `updated_at`.

### Static route

`GET /` serves `index.html`.

## Frontend (`index.html`)

Everything inline: one `<style>` block, one `<script>` block, no external dependencies.

### Layout

```
┌─────────────────────────────────────────────────────────┐
│ Job Applications     [📋 Paste / URL] [+ Add] [⚙ Settings] │
├─────────────────────────────────────────────────────────┤
│ Search: [_____________]  Status: [All ▾]                │
├─────────────────────────────────────────────────────────┤
│ Date       Position        Company    Status    Actions │
│ 2026-05-20 Backend Dev     ACME GmbH  Applied   ✎  🗑   │
│ 2026-05-18 Android Dev     PIKO       Open      ✎  🗑   │
│ ...                                                     │
└─────────────────────────────────────────────────────────┘
```

### Components (just functions, no framework)

1. **Table view** — main display. Columns: Date applied, Position, Company, City, Status (as colored pill), Actions. Click a row to expand inline and show full record (description, address, hr email/phone, skills as pill tags). Hidden columns OK on narrow screens.

2. **Add/Edit form** — a `<dialog>` modal with all fields. Same form serves three modes: create blank, create pre-filled (from parser), edit existing. Buttons: Save, Cancel. On Save: POST or PUT then refresh the table.

3. **Paste & parse dialog** — a `<dialog>` that accepts **either** a URL or pasted text. Layout:
   - Mode tabs at top: `[ URL ] [ Text ]`. Default tab is URL.
   - URL tab: single `<input type="url">` plus "Fetch & parse" button.
   - Text tab: large `<textarea>` plus "Parse" button.
   - Active provider/model shown above the action button (e.g. "Using: Anthropic / claude-sonnet-4-5") with a "Change…" link to Settings.
   Flow:
   1. User submits URL or text. Empty input is rejected client-side.
   2. Button shows spinner. For URLs, label changes to "Fetching…" then "Parsing…" once the request advances. Frontend can't actually tell which phase the backend is in, so just say "Working…".
   3. Backend either fetches+cleans the URL or uses the pasted text, then runs the active provider's `parse()`.
   4. On success the dialog closes and the **Add/Edit form opens pre-filled**. User reviews/edits, hits Save.
   5. On error, show the error inline with the hint from the backend ("Site may require login. Try copy-pasting the text instead." / "Add ANTHROPIC_API_KEY to .env" / "Start Ollama with: `ollama serve`"). If a URL fetch fails with a hint about copy-pasting, the dialog stays open and pre-switches to the Text tab so the user can paste immediately.

4. **Settings page** (`settings.html`, served at `GET /settings`) — separate page, same styling:
   - Provider radio group: `Ollama` / `Anthropic Claude` / `OpenAI`. Each row shows a small key-status indicator on its right ("✅ Key configured" / "⚠ Set `OPENAI_API_KEY` in .env" / "— Not needed for Ollama").
   - Model `<select>` — populated by calling `GET /api/models?provider=X` whenever the provider changes. While the request is in flight, the select is disabled and shows "Loading…". On error, falls back to a text input so the user can type a model id manually, with the error message displayed below.
   - Save button → PUT `/api/settings`, then a small toast "Saved" and a link back to the main page.
   - A "Test parse" button that runs a hardcoded sample posting against the current selection and shows the parsed result — quick sanity check that everything works end-to-end.

5. **Delete** — confirm via `window.confirm("Delete this application?")`, then DELETE and refresh.

6. **Filter bar** — text search (client-side substring match across position/company/skills/city) and status dropdown.

7. **CSV export button** (top right) — generates a CSV from the current filtered list and triggers download.

### State

A single module-level array `jobs = []`. After every mutation, re-fetch from `/api/jobs` and re-render. Simpler than maintaining diffs.

### Status pill colors

Use CSS class per status. Suggested palette (neutral, accessible):

- `open` — gray
- `applied` — blue
- `interview_done` — purple
- `rejected` — red
- `rejected_after_interview` — dark red
- `accepted` — green

### Styling

Keep it minimal: system font stack, ~720–960px max-width container, borderless table with row hover, dialog uses native `<dialog>` element. No CSS framework. Total CSS should be under ~100 lines.

## LLM providers

All provider logic lives under `providers/`. Each module exports a class that implements a common protocol; `server.py` never imports a specific provider directly — it goes through `get_provider(name)`.

### `providers/base.py` — the protocol

```python
class Provider(Protocol):
    name: str

    async def parse(self, text: str, model: str) -> dict:
        """Return a dict of JobInput fields. Raise ProviderError on failure."""

    async def list_models(self) -> list[str]:
        """Return available model IDs. Raise ProviderError on failure."""
```

Custom exception hierarchy:

```python
class ProviderError(Exception): ...
class ProviderUnavailable(ProviderError): ...   # network / not running / wrong URL
class ProviderAuthError(ProviderError): ...     # missing or invalid API key
class ProviderBadOutput(ProviderError): ...     # model returned unparseable response
class ProviderTimeout(ProviderError): ...
```

### The three implementations

| Provider     | Endpoint (parse)                                  | Endpoint (models)                          | Auth                                |
| ------------ | ------------------------------------------------- | ------------------------------------------ | ----------------------------------- |
| `ollama`     | `POST http://localhost:11434/api/generate`        | `GET  http://localhost:11434/api/tags`     | none                                |
| `anthropic`  | `POST https://api.anthropic.com/v1/messages`      | `GET  https://api.anthropic.com/v1/models` | `x-api-key: $ANTHROPIC_API_KEY` + `anthropic-version: 2023-06-01` |
| `openai`     | `POST https://api.openai.com/v1/chat/completions` | `GET  https://api.openai.com/v1/models`    | `Authorization: Bearer $OPENAI_API_KEY` |

Per-provider notes:

- **Ollama** — request uses `"format": "json"` to force JSON output. `list_models()` reads the `models[].name` array from `/api/tags`.
- **Anthropic** — system prompt as `system` field, user text as a single `user` message. Force JSON by including "Respond with JSON only" in the system prompt and parsing the first `content[0].text` block. `list_models()` filters response to current Claude models only.
- **OpenAI** — use `response_format: { "type": "json_object" }`. `list_models()` should filter to chat models (those whose id starts with `gpt-`) to keep the dropdown short.

### Shared prompt

All three providers use the same extraction prompt (defined once in `providers/base.py` as `EXTRACTION_PROMPT`):

```
You are a job-posting parser. Extract structured data from the job
posting below and return ONLY a JSON object with these fields:

  position      string  - job title
  company       string  - company name
  description   string  - 1-2 sentence summary of the role
  city          string  - city where the job is located, "" if remote/unknown
  address       string  - full street address if present, else ""
  hr_email      string  - contact email if present, else ""
  hr_phone      string  - contact phone if present, else ""
  skills        string  - comma-separated list of required technical skills

If a field is not present in the text, use an empty string. Do not
invent information. Output JSON only, no commentary.
```

Output handling is identical across providers:

1. Parse the response body as JSON.
2. Keep only the expected keys; missing → `""`; unknown → discard.
3. Set defaults: `date_applied = today`, `status = "open"`.
4. Return the dict. Saving is the user's job after review.

### API keys (`.env`)

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

Both are optional. Loaded once at startup via `python-dotenv`. Missing key for the active provider → `/api/parse` returns 401 with the hint `"Add ANTHROPIC_API_KEY to .env"`. `GET /api/settings` includes a `key_status` object so the Settings page can show "✅ Key configured" / "⚠ No key set" next to each provider.

### Error contract (`/api/parse` and `/api/models`)

| Failure                  | HTTP | Body                                                                         |
| ------------------------ | ---- | ---------------------------------------------------------------------------- |
| `ProviderUnavailable`    | 503  | `{ "error": "...", "hint": "Start Ollama with: ollama serve" }` (or similar) |
| `ProviderAuthError`      | 401  | `{ "error": "Invalid or missing API key", "hint": "Add X_API_KEY to .env" }` |
| `ProviderBadOutput`      | 502  | `{ "error": "Model returned invalid JSON" }`                                 |
| `ProviderTimeout`        | 504  | `{ "error": "Provider timed out" }`                                          |
| `FetchError` (URL mode)  | 400 / 408 / 502 | `{ "error": "...", "hint": "Try copy-pasting the page text instead." }` |

Frontend surfaces these inline.

## Re-parsing existing jobs

A job created via the parse flow keeps two breadcrumbs: `source_url` and `source_text`. Re-parse lets the user re-run extraction on either one — useful when:

- The initial parse missed fields (the LLM had a bad day, or you've since upgraded to a stronger model).
- You switched provider in Settings and want to try the new one on old postings.
- The original URL has been updated by the company and you want the fresh content.

### `POST /api/jobs/{id}/reparse` behavior

1. Load the job. If both `source_url` and `source_text` are empty → 400 `{ "error": "This job has no source to re-parse from", "hint": "Re-parse only works on jobs created via Paste/URL." }`.
2. **Source selection**: prefer `source_url` if present (fetches fresh content); fall back to `source_text` otherwise.
3. Fetch (if URL) and run the active provider exactly like `/api/parse`. Use whatever provider+model is currently selected in Settings — re-parse always uses *now's* settings, not whatever was used originally.
4. **Merge into the existing row**: overwrite only the fields the parser produces (`position`, `company`, `description`, `city`, `address`, `hr_email`, `hr_phone`, `skills`). Preserve everything the user owns: `date_applied`, `status`, `id`, `created_at`. Update `updated_at` to `now`.
5. If the source was `source_url` and fetching succeeded, refresh `source_text` with the new cleaned text. Keeps the breadcrumb current.
6. Return the updated `Job`.

### Error handling

Re-parse can fail in the same ways as `/api/parse`, plus the 400 above. The frontend treats this as recoverable — the original record is untouched until the parse succeeds. Only on success is the row updated. Implementation: parse first, then `UPDATE` in a single transaction.

### Frontend

A small "↻ Re-parse" button on the row's expanded view, **conditionally rendered** — only shown when `source_url` or `source_text` is non-empty. On click:

1. `window.confirm("Re-parse this job? Description and contact fields may change. Status and date will be kept.")` — short, lists what's at risk.
2. POST `/api/jobs/{id}/reparse`. Button shows spinner.
3. On success, refresh the table; the expanded row re-renders with the new values. A small "Updated" toast confirms.
4. On error, show the error inline in the expanded row with the same hints used by `/api/parse`.

## URL fetching (`fetcher.py`)

When `/api/parse` is called with a `url` instead of `text`, the backend fetches the page and converts it to plain text before handing off to the LLM. Self-contained module, no FastAPI imports.

```python
async def fetch_as_text(url: str) -> str:
    """Fetch URL, return cleaned plain text. Raises FetchError on failure."""
```

### Fetch behavior

1. **Validate URL** — must start with `http://` or `https://`. Reject anything else (including `file://`, `ftp://`) with `FetchError("Only http/https URLs are supported")`.
2. **Block local addresses** — reject `localhost`, `127.0.0.1`, `0.0.0.0`, `169.254.*` (link-local), `10.*`, `192.168.*`, `172.16-31.*` (RFC1918), and IPv6 loopback `::1`. This is a basic SSRF guard since the server might later be hosted on a LAN. Implement by parsing the host with `urllib.parse.urlparse` and checking against a deny-list of prefixes; reject anything that resolves to a private range. Return 400 with `"error": "Local/private URLs are not allowed"`.
3. **HTTP GET** with `httpx.AsyncClient`:
   - 10-second total timeout.
   - Single redirect follow (max 3 hops).
   - `User-Agent: JobTracker/1.0` — some sites 403 without one.
   - Response size cap: 2 MB. If `Content-Length` exceeds that, abort early; if it's missing, read in chunks and abort once exceeded.
   - Reject responses where `Content-Type` doesn't start with `text/html` or `application/xhtml`.
4. Convert HTML → text (see below).
5. Truncate to ~12,000 characters before returning. Larger pages waste tokens and most job postings fit easily.

### HTML cleanup (naive, no library)

Pure regex, in this order:

```python
import re

def html_to_text(html: str) -> str:
    # 1. Drop script/style/noscript blocks including content
    html = re.sub(r'<(script|style|noscript)\b[^>]*>.*?</\1>',
                  '', html, flags=re.DOTALL | re.IGNORECASE)
    # 2. Convert block tags to newlines (so paragraphs survive)
    html = re.sub(r'</(p|div|li|h[1-6]|br|tr)>', '\n',
                  html, flags=re.IGNORECASE)
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    # 3. Strip all remaining tags
    html = re.sub(r'<[^>]+>', '', html)
    # 4. Decode the common HTML entities
    html = (html.replace('&nbsp;', ' ').replace('&amp;', '&')
                .replace('&lt;', '<').replace('&gt;', '>')
                .replace('&quot;', '"').replace('&#39;', "'"))
    # 5. Collapse whitespace
    html = re.sub(r'[ \t]+', ' ', html)
    html = re.sub(r'\n\s*\n+', '\n\n', html)
    return html.strip()
```

This is crude on purpose. It will keep navigation menus, cookie banners, and footers — but the LLM tolerates noise well enough that this works for most job-board pages. The non-goal "scraping protected job boards" covers the cases this breaks on (LinkedIn, Indeed): they require JS rendering or login, so even a better extractor wouldn't help without a real browser. Document this in the README: "If a URL doesn't parse well, copy-paste the visible page text instead."

### `FetchError` cases

| Failure                       | HTTP | Body                                                                       |
| ----------------------------- | ---- | -------------------------------------------------------------------------- |
| Invalid scheme / local URL    | 400  | `{ "error": "...", "hint": "Use a public http/https URL" }`                |
| Timeout (10s)                 | 408  | `{ "error": "Page took too long to load" }`                                |
| HTTP 4xx/5xx from target site | 502  | `{ "error": "Page returned HTTP 403", "hint": "Site may require login. Try copy-pasting the text instead." }` |
| Non-HTML content type         | 502  | `{ "error": "URL is not an HTML page" }`                                   |
| Response too large (>2 MB)    | 502  | `{ "error": "Page is too large" }`                                         |

### Wiring in `server.py`

The `/api/parse` handler:

```python
@app.post("/api/parse")
async def parse(body: ParseRequest):
    if body.url and body.text:
        raise HTTPException(400, "Provide either text or url, not both")
    if not body.url and not body.text:
        raise HTTPException(400, "Provide text or url")
    
    text = body.text or await fetch_as_text(body.url)
    provider = get_provider(current_settings.provider)
    parsed = await provider.parse(text, current_settings.model)
    
    # Stamp source for future re-parse
    parsed["source_url"] = body.url or ""
    parsed["source_text"] = text
    return parsed
```

Map `FetchError` to the appropriate status via an exception handler, same pattern as `ProviderError`.

- Date input uses `<input type="date">`. Default value when adding = today.
- On first load, if the table is empty, show an empty-state message inline: "No applications yet. Click + Add job to start."
- Errors from the API (e.g. validation failure) are surfaced via a small banner at the top of the dialog. Don't use `alert()` for form errors.
- The dialog should be closable with Escape key (native `<dialog>` behavior).
- Sort: default order is `date_applied DESC` from the API. Client doesn't re-sort.

## Run instructions

`requirements.txt`:

```
fastapi
uvicorn[standard]
httpx
python-dotenv
```

Prerequisites depend on which providers you'll use:

- **Ollama** — install from `ollama.com` and run `ollama serve`.
- **Anthropic** — set `ANTHROPIC_API_KEY` in `.env`.
- **OpenAI** — set `OPENAI_API_KEY` in `.env`.

You only need to set up the providers you'll actually use. The app starts fine with none configured; you just can't parse until one is.

`.env.example` (commit this):

```
# Server
HOST=127.0.0.1
PORT=8000

# Fill in only the providers you'll use.
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
```

`server.py` reads `HOST` and `PORT` from env (defaulting to `127.0.0.1` and `8000`) and exposes them as a constant `BASE_URL` for templating into HTML (used by the Settings page for the bookmarklet).

`README.md` should document:

```
# 1. (Optional) Install Ollama for local parsing
ollama pull llama3.1:8b
ollama serve              # leave running in its own terminal

# 2. (Optional) Add API keys to .env
cp .env.example .env
# then edit .env — set PORT here too if 8000 is taken

# 3. Run the app
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn server:app --reload --host $HOST --port $PORT
# or just: uvicorn server:app --reload   (uses env vars if set)
# open http://localhost:8000   (or whatever PORT you set)
# settings page: http://localhost:8000/settings
```

The SQLite file `jobs.db` is created on first run if absent. Back up by copying it. Reset by deleting it.

## Implementation order (for Claude Code)

1. **`db.py`** — open connection, run `CREATE TABLE IF NOT EXISTS` for both `jobs` and `settings`, seed the singleton settings row, run the `source_url`/`source_text` migration. Expose `list_jobs`, `get_job`, `create_job`, `update_job`, `delete_job`, plus `update_parsed_fields(id, parsed_dict)` for re-parse (preserves `date_applied`, `status`). Single connection with `check_same_thread=False` and `row_factory = sqlite3.Row`.
2. **`settings.py`** — `get_settings()` and `update_settings(provider, model)` against the singleton row. Validate `provider` is one of `ollama|anthropic|openai`.
3. **`providers/base.py`** — `Provider` protocol, `ProviderError` hierarchy, `EXTRACTION_PROMPT` constant, helper to whitelist+default keys in the parsed dict.
4. **`providers/ollama.py`, `anthropic.py`, `openai.py`** — each implements `parse()` and `list_models()`. Map HTTP errors to the right exception subclass. 60s timeout on parse, 10s on list_models.
5. **`providers/__init__.py`** — `get_provider(name)` factory; reads keys from env via `os.getenv`; raises `ProviderAuthError` if a cloud provider's key is missing.
6. **`fetcher.py`** — `fetch_as_text(url)`, `FetchError` exception. URL validation + SSRF guard + `httpx` GET + the regex-based `html_to_text()`. No FastAPI imports.
7. **`server.py`** — FastAPI app, `load_dotenv()` at startup, Pydantic models (including `ParseRequest` with optional `text` and `url`), all CRUD + parse + reparse + settings + models routes. Map `ProviderError` *and* `FetchError` subclasses to the right HTTP status. `GET /` → `index.html`, `GET /settings` → `settings.html`.
8. **`index.html`** — table + add/edit dialog + paste & parse dialog (with URL/Text tabs, showing active provider/model) + expanded-row re-parse button. Vanilla JS, fetch helpers, render, form handlers.
9. **`settings.html`** — provider radios + model select + test-parse button. Re-fetches `/api/models` when provider changes; falls back to free-text input on error.
10. **`requirements.txt`, `.env.example`, `README.md`, `.gitignore`** (`jobs.db`, `.venv`, `__pycache__`, `.env`).

Acceptance check:

- All previous CRUD + CSV + manual flows still work.
- Settings page lists three providers with key-status indicators.
- Switching to Anthropic with a valid key → model dropdown populates from the API → save → paste & parse uses Claude.
- Switching to OpenAI → same flow with GPT models.
- Switching to Ollama → models list comes from `/api/tags` (only locally-pulled models appear).
- Switching to a provider with no key → parse fails with the "Add X_API_KEY to .env" hint.
- Killing Ollama while selected → parse fails with "Start Ollama with: ollama serve".
- **URL mode:** paste a public job posting URL (e.g. a company careers page, not LinkedIn) → form opens pre-filled.
- **URL mode failure:** paste a LinkedIn URL → 502 with the "Site may require login" hint → dialog auto-switches to Text tab.
- **SSRF guard:** paste `http://localhost:8080` → 400 with "Local/private URLs are not allowed".
- **Re-parse:** create a job via URL, then expand the row → "↻ Re-parse" button appears → click → confirm → fields refresh; `date_applied` and `status` are unchanged. On manually-created jobs (no source), the button is hidden.
- **Re-parse with new provider:** parse a job with Ollama → switch Settings to Claude → re-parse the same job → Claude's output overwrites the fields.
