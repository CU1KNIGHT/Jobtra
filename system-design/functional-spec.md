# Job Application Tracker — Functional Specification

> How each feature behaves in detail, plus the data model, API surface, and
> operational notes. For the product-level "what & why" see [`PRD.md`](./PRD.md).
> This document describes the software **as currently built**.

---

## 1. Architecture summary

- **Backend:** FastAPI (`App/src/server.py`), routers under `App/src/routers/`.
- **Storage:** SQLite (`jobs.db`), auto-created and auto-migrated on startup. Uploaded files live on disk under `DOCS_DIR` (default `~/.job-tracker/docs`).
- **Frontend:** static HTML pages in `ui/` (`index.html`, `email.html`, `documents.html`, `job_detail.html`) with vanilla JS in `ui/js/` and CSS in `ui/css/`. Served via `/static`; pages are returned by navigation routes with a `__BASE_URL__` placeholder substituted server-side.
- **AI abstraction:** `providers/` exposes a common interface (`parse`, `complete`, `list_models`) implemented by `OllamaProvider`, `AnthropicProvider`, `OpenAIProvider`.
- **Config:** `.env` via `python-dotenv` (`HOST`, `PORT`, `DOCS_DIR`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`).

---

## 2. Functional areas

### 2.1 Job tracking (Jobs page, `/`)

- **List:** all jobs, ordered by `date_applied` descending. Each row shows position, company, city, status pill, skills, and a document-count badge when documents are attached.
- **Search:** free-text box filters client-side across position, company, city, and skills (case-insensitive substring).
- **Status filter:** dropdown filters to one status. Statuses (fixed set): `open`, `applied`, `interview_done`, `rejected`, `rejected_after_interview`, `accepted`.
- **Row expand:** clicking a row expands an inline detail panel with the full field set.
- **Add job:** dialog with all fields. Required: position, company, date_applied. Status defaults to `open`. Skills entered comma-separated.
- **Edit / Delete:** edit reopens the dialog pre-filled; delete removes the job (cascades to its document links and is referenced by any linked emails).
- **Detail page (`/jobs/{id}`):** standalone page for a single job; 404 if the job doesn't exist.
- **Validation:** position, company, and date_applied must be non-empty; status must be one of the six valid values (enforced by Pydantic `JobInput` and a SQLite `CHECK` constraint).

### 2.2 AI parsing — Paste & Parse / URL / Bookmarklet / Re-parse

- **Paste & Parse dialog** (Jobs page) has two tabs:
  - **URL:** server fetches the page (`fetcher.py`) and extracts text, then parses.
  - **Text:** user pastes the posting body directly.
- Parsing runs through the **active provider/model** and returns structured fields (position, company, description, address, city, hr_email, hr_phone, whatsapp, telegram, hours_per_week, languages, skills). The original `source_url`/`source_text` are stored on the job for later re-parsing.
- **Browser bookmarklet:** sends the visible text of any job page to `POST /api/parse-from-bookmarklet`, which parses and creates a job in one click — works on sites where the user is logged in. Page text is capped at 12,000 chars.
- **Re-parse** (`POST /api/jobs/{id}/reparse`): re-runs parsing from the stored source. If a `source_url` exists it re-fetches; on fetch failure it falls back to cached `source_text`. Only parser-produced fields are overwritten — `date_applied`, `status`, `id`, `created_at` are preserved. Fails with a clear message if the job has no stored source.
- **URL fetch safety (`fetcher.py`):** only `http`/`https`; blocks private/loopback/link-local/reserved IPs and `.local`/`.internal` hosts (SSRF guard); response capped at 2 MB and text at 12,000 chars.
- **Error handling (shared across parse endpoints):** provider errors map to actionable HTTP responses — 401 (missing API key, with hint to add it to `.env`), 503 (provider unavailable, e.g. "Start Ollama with: ollama serve"), 502 (model returned invalid JSON), 504 (timeout).

### 2.3 Import & export

**CSV export** (Jobs page): downloads the currently filtered list as CSV with columns `id, position, company, date_applied, status, city, address, hr_email, hr_phone, skills, description, created_at, updated_at`.

**Import** (`POST /api/jobs/import`): bulk-import from a `.csv` or `.json` file.
- **Format detection:** by file extension, falling back to sniffing the first non-whitespace character. JSON accepts a list, a single object, or `{"jobs": [...]}`. CSV uses the header row.
- **Tolerant field mapping:** unknown columns/keys (e.g. `id`, `created_at`) are ignored. Alternative names are aliased onto canonical fields, case- and separator-insensitive, including German headers — e.g. `title`/`role`/`Titel`/`Stelle` → `position`; `employer`/`Firma`/`Unternehmen` → `company`; `Bewerbungsdatum`/`date` → `date_applied`; `Stadt`/`location` → `city`; `Tags`/`Fähigkeiten` → `skills`; `url`/`link` → `source_url`.
- **Tolerant status:** status values are normalized case-insensitively against a synonym map (English + German), e.g. `Applied`/`Beworben` → `applied`, `Interview`/`Vorstellungsgespräch` → `interview_done`, `Offer`/`Zusage` → `accepted`, `Abgelehnt`/`Declined` → `rejected`, `Wishlist`/`Offen` → `open`. An **unrecognized** status does not fail the row — it falls back to `open`.
- **Defaults:** missing `date_applied` → today; missing/blank status → `open`.
- **Required:** position and company. Rows lacking a recognizable position/company are reported as per-row errors (the import does not abort).
- **Blank rows** (trailing CSV newlines) are skipped silently.
- **Duplicate skipping:** a row matching an existing job by `(position, company, date_applied)` (case-insensitive) is skipped — and duplicates within the same file too. Re-running the same file is therefore safe.
- **Result:** `{ total, imported, skipped, errors: [{row, error}] }`, surfaced in the import dialog as a summary plus per-row error list.

### 2.4 Documents library (Documents page, `/documents`)

- **Upload:** file + `doc_type` (`cv`, `cover_letter`, `certificate`, `portfolio`, `other`) + optional notes. Accepted types: pdf, doc/docx, txt, png/jpg/jpeg.
- **Content-addressed dedupe:** files are stored by SHA-256 hash; uploading an identical file returns the existing document instead of duplicating it on disk.
- **Library vs job view:** opening `/documents?job=<id>` shows only documents attached to that job, plus an "attach from library" picker. The plain page shows the whole library with a "used by N jobs" usage count.
- **Attach / detach:** documents can be attached to a job (link row in `job_documents`, unique per job+document) or detached. Attaching can also upload a new file in the same step.
- **Download:** streams the stored file with its original filename.
- **Delete:** deleting from the library is **blocked** (409) while the document is still attached to any job; the response lists the blocking jobs. Detaching from all jobs first is required.
- **Filtering/search:** by type and by filename/notes text.

### 2.5 Email integration (Email page, `/email`)

**Accounts:**
- Add IMAP accounts (label, host, port [default 993], username, password). **Passwords are encrypted at rest** with Fernet (key stored in settings, auto-generated on first use). Account responses never include the encrypted password.
- Accounts can be edited, deleted (cascades to their messages), or have their sync history reset ("Full re-sync" → next sync re-fetches everything).

**Sync (`POST /api/email/sync`, background task):**
- Connects via IMAP over SSL to each active account. Incremental: uses `SINCE last_sync` where possible, else `ALL`. First-ever sync is capped to the 500 most recent messages.
- Extracts subject, sender, received date, and plaintext body (body capped at 12,000 chars); stores new messages as `pending`. De-duplicated per account by IMAP UID.
- Single-flight: a second sync request while one is running returns `already_running`. The UI polls `/api/email/status` until completion.

**Classification / processing:**
- **Process all pending** (`POST /api/email/process`): streams NDJSON progress events as each pending message is classified.
- **Process / Re-process single** (`POST /api/email/messages/{id}/process`): runs (or re-runs) classification on one message regardless of its current state. The UI shows **▶ Process** for `pending`/`error` messages and **↻ Re-process** for already-processed ones.
- The LLM returns: `relevant` (bool), `status` (`rejection`|`interview_invite`|`offer`|`application_received`|`other`|null), `company`, `position`, `date`, `confidence` (0–1), `notes`.
- **Relevance:** irrelevant messages are marked `irrelevant`; relevant ones store the extracted `llm_status` and raw JSON.

**Job linking & status updates (key behavior):**
- When a relevant message's `company` matches a job, the email is **always linked** to that job (`linked_job_id`), independent of confidence — so it appears against the job.
- Company matching (`find_matching_job`) is **bidirectional and suffix-tolerant**: it normalizes both names (lowercase, strip punctuation and legal/generic suffixes like `GmbH`, `Steuerberatungsgesellschaft`, `AG`) and matches if either contains the other — so a job stored as `kalkül` links to an email signed `kalkül Dresden GmbH`. Matching considers **all** jobs (including finalized ones) but prefers still-active jobs, then most recent by date.
- **Status auto-update** is the more consequential action and is gated: it only changes the job's status when `confidence ≥ 0.85` **and** the job is not already in a terminal state (`rejected`, `rejected_after_interview`, `accepted`). Mapping: `rejection`→`rejected`, `interview_invite`→`interview_done`, `application_received`→`applied`. This prevents an old "application received" email from un-rejecting a finalized job.
- **Manual linking:** any message can be linked to a chosen job, changed, or unlinked from the message detail panel.

**Browsing:** messages list with relevance dot, status badge, linked-job badge (links to the job), filter pills (All / Job related / Pending / Irrelevant / Error) with counts, account filter, and free-text search over subject/sender.

### 2.6 AI provider settings (Settings dialog on Jobs page)

- Choose **provider** (`ollama`, `anthropic`, `openai`) and **model**. Models can be listed live from the provider (`GET /api/models?provider=`), or typed manually.
- **API-key status** is surfaced per provider (whether `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` is present); Ollama needs no key.
- **Test parse** runs a sample through the selected provider/model to confirm it works.
- The browser **bookmarklet** is presented here for drag-to-bookmarks-bar; it embeds the configured base URL (re-drag needed if `PORT` changes).
- `GET/PUT /api/settings` reads/writes the active provider+model (validated against the known provider list). Email processing has its own optional settings (`email_provider`, `email_ollama_model`, sync interval, keywords).

### 2.7 UI / navigation

- **Collapsible left sidebar**, shared across Jobs, Email, and Documents pages: brand, **Navigation** (Jobs / Email / Docs), and a bottom group (Settings, theme toggle). State (expanded vs icon-rail) and theme persist in `localStorage`; the sidebar collapses to a horizontal bar on narrow screens.
- Page-specific actions live in each page's header (e.g. Jobs: Import / Export CSV / Paste & parse / Add job; Email: Sync / Accounts; Docs: Upload).
- **Dark/light theme** via a `data-theme` attribute set before paint to avoid flashes.

---

## 3. Data model (SQLite)

- **jobs** — `id, position, company, description, date_applied, status, address, city, hr_email, hr_phone, skills, whatsapp, telegram, hours_per_week, languages, source_url, source_text, created_at, updated_at`. `CHECK` constraint on `status`.
- **settings** — single row (`id=1`): `provider, model` + email settings columns (`email_provider, email_ollama_model, email_sync_interval, email_keywords, fernet_key`).
- **documents** — `id, filename, doc_type, file_path, file_hash (UNIQUE), file_size, uploaded_at, notes`.
- **job_documents** — `id, job_id (FK→jobs, ON DELETE CASCADE), document_id (FK→documents, ON DELETE RESTRICT), attached_at`, `UNIQUE(job_id, document_id)`.
- **email_accounts** — `id, label, imap_host, imap_port, username, password_enc, last_sync_at, active`.
- **email_messages** — `id, account_id (FK→email_accounts, CASCADE), uid, subject, sender, received_at, body_text, relevance, processed_at, linked_job_id (FK→jobs), llm_status, llm_raw`, `UNIQUE(account_id, uid)`.

Schema is created if missing and **auto-migrated** at startup (adds newer columns to `jobs`/`settings`).

---

## 4. API surface (selected)

| Method & path | Purpose |
|---|---|
| `GET /` , `/email`, `/documents`, `/jobs/{id}` | Serve pages (`/settings` redirects to `/`) |
| `GET/POST /api/jobs`, `GET/PUT/DELETE /api/jobs/{id}` | Job CRUD |
| `POST /api/jobs/import` | CSV/JSON bulk import |
| `POST /api/parse`, `POST /api/jobs/{id}/reparse`, `POST /api/parse-from-bookmarklet` | AI parsing |
| `GET /api/documents`, `POST /api/documents`, `GET /api/documents/{id}/download`, `DELETE /api/documents/{id}` | Document library |
| `GET/POST /api/jobs/{id}/documents`, `DELETE /api/jobs/{id}/documents/{doc_id}` | Attach/detach docs |
| `GET/POST/PUT/DELETE /api/email/accounts...`, `POST .../reset-sync` | Email accounts |
| `POST /api/email/sync`, `GET /api/email/status` | Sync + status |
| `GET /api/email/messages`, `POST .../process`, `POST .../{id}/process`, `POST/DELETE .../{id}/link` | Messages, classify, link |
| `GET/PUT /api/settings`, `GET /api/email/settings`, `GET /api/models`, `GET /api/config` | Settings & models |

---

## 5. Configuration & run

### 5.1 Prerequisites

- Python 3.10+
- pip

### 5.2 Installation

```bash
# 1. Clone the repository
git clone <repo-url>
cd job-tracker

# 2. Install Python dependencies
pip install -r App/requirements.txt

# 3. Create your environment file
cp App/.env.example App/src/.env
# Edit .env and fill in any API keys you need
```

### 5.3 Environment variables

```
HOST=127.0.0.1        # default
PORT=8001             # default; changing it requires re-dragging the bookmarklet
DOCS_DIR=~/.job-tracker/docs
ANTHROPIC_API_KEY=... # optional, for Anthropic provider
OPENAI_API_KEY=...    # optional, for OpenAI provider
```

### 5.4 Running

```bash
cd App/src
uvicorn server:app --reload
```

Open `http://localhost:8001`. `jobs.db` is created automatically on first run.

### 5.5 Backup

Two things need to be backed up together:
- `jobs.db` — the SQLite database (all job, email, and document metadata)
- `DOCS_DIR` (default `~/.job-tracker/docs`) — the actual uploaded files on disk

Backing up only `jobs.db` without `DOCS_DIR` leaves document records pointing to missing files. Copy both atomically (e.g. stop the server first) for a consistent snapshot.

### 5.6 First-run behaviour

On first run with no provider configured, AI features (parse, email classification) will fail with a 503 until a provider is set via the Settings dialog. The app is otherwise fully functional — jobs can be added and managed manually without a provider.

---

## 6. Security & privacy

- **Local-first:** all data in a local SQLite file and local disk; with Ollama, postings/emails never leave the machine.
- **Email passwords** encrypted at rest with Fernet; never returned by the API.
- **SSRF protection** on URL fetching (scheme allow-list, private-host blocking, size caps).
- **CORS** is currently fully open (`allow_origins=["*"]`, `allow_private_network=True`) to support the bookmarklet posting from arbitrary pages — acceptable for a localhost single-user tool, but a hardening point if ever exposed.

---

## 7. Known constraints / limitations

- Single user; no authentication.
- Company matching is name-based (substring, suffix-tolerant) and does not factor in position; with two open applications at the same company, an email links to the most recent active one.
- Unrecognized import statuses silently become `open` (favoring import success over strictness).
- No automatic background sync scheduler in the request path — sync is user-triggered (an `email_sync_interval` setting exists but scheduling is out of scope of the current request flow).
- LLM output quality (relevance, extracted company/status, confidence) depends on the chosen model.
- Auto-migration only adds columns; it does not rename or drop them. Destructive schema changes require a manual migration.
- No document versioning — uploading a revised file (e.g. updated CV) creates a new document record; the old one remains and must be manually detached and deleted.
- Manually adding a duplicate job through the UI is not blocked; duplicate detection only applies during import.

---

## 8. Glossary

| Term | Definition |
|---|---|
| **Bookmarklet** | A browser bookmark containing JavaScript. Dragged to the bookmarks bar; clicking it on a job posting page sends the page text to the tracker for parsing. |
| **Fernet** | A symmetric encryption scheme from the `cryptography` Python library. Used here to encrypt IMAP passwords at rest. |
| **IMAP** | Internet Message Access Protocol — the standard protocol for reading email from a mail server. |
| **NDJSON** | Newline-Delimited JSON. A streaming format where each line is a valid JSON object. Used by the email processing endpoint to stream progress events as each message is classified. |
| **Ollama** | A tool for running large language models locally. When selected as provider, no data leaves the machine. |
| **Provider** | An abstraction over an AI backend (`OllamaProvider`, `AnthropicProvider`, `OpenAIProvider`) that exposes a common `parse` / `complete` / `list_models` interface. |
| **Re-parse** | Re-running AI parsing on an existing job using its stored `source_url` or `source_text`, overwriting only parser-produced fields. |
| **SSRF** | Server-Side Request Forgery — an attack where a server is tricked into making requests to internal/private network addresses. Mitigated in `fetcher.py` by blocking private IP ranges and reserved hostnames. |
| **Terminal status** | A job status that represents a final outcome: `rejected`, `rejected_after_interview`, or `accepted`. Email-triggered status updates will not overwrite a job already in a terminal state. |
| **`updated_at`** | Timestamp on the `jobs` table updated whenever any field on the job is modified via `PUT /api/jobs/{id}`. |

---

## 9. Revision history

| Version | Date | Notes |
|---|---|---|
| 1.0 | — | Initial spec — documents software as currently built. |
