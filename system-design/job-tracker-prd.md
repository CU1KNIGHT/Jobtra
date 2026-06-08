# Job Application Tracker — PRD & Functional Specification

> **Status:** describes the software **as currently built**. This is a combined Product Requirements Document (what the product does, from the user's view) and Functional Specification (how each feature behaves in detail).

---

## 1. Overview

The Job Application Tracker is a single-user, self-hosted web app for managing a job search end-to-end. It keeps a structured list of applications, uses an LLM to turn raw job postings into structured records, stores related documents (CVs, cover letters, certificates), and connects to the user's email inbox to detect and classify application-related messages (rejections, interview invites, offers) and link them back to the relevant job.

- **Deployment model:** runs locally; FastAPI backend + SQLite, plain HTML/JS frontend, no build step.
- **AI providers:** pluggable — Ollama (local), Anthropic, or OpenAI.
- **Primary user:** an individual job seeker tracking their own applications.

### 1.1 Goals

- Replace ad-hoc spreadsheets with a structured, searchable application list.
- Minimize manual data entry via AI parsing of postings (paste, URL, or browser bookmarklet) and bulk import.
- Surface status changes automatically by reading the user's email.
- Keep all data local and under the user's control.

### 1.2 Non-goals

- Multi-user / multi-tenant accounts, authentication, or roles.
- Sending email or applying to jobs on the user's behalf.
- A hosted/cloud SaaS offering.
- Mobile-native apps (the web UI is responsive but browser-based).

---

## 2. Personas

| Persona | Needs |
|---|---|
| **Active job seeker** | Track many applications, see status at a glance, avoid retyping posting details, never lose track of which company an email refers to. |
| **Privacy-conscious user** | Keep data on their own machine; choose a local LLM (Ollama) so postings/emails aren't sent to a third party. |

---

## 3. Architecture Summary

- **Backend:** FastAPI (`App/src/server.py`), routers under `App/src/routers/`.
- **Storage:** SQLite (`jobs.db`), auto-created and auto-migrated on startup. Uploaded files live on disk under `DOCS_DIR` (default `~/.job-tracker/docs`).
- **Frontend:** static HTML pages in `ui/` (`index.html`, `email.html`, `documents.html`, `job_detail.html`) with vanilla JS in `ui/js/` and CSS in `ui/css/`. Served via `/static`; pages are returned by navigation routes with a `__BASE_URL__` placeholder substituted server-side.
- **AI abstraction:** `providers/` exposes a common interface (`parse`, `complete`, `list_models`) implemented by `OllamaProvider`, `AnthropicProvider`, `OpenAIProvider`.
- **Config:** `.env` via `python-dotenv` (`HOST`, `PORT`, `DOCS_DIR`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`).

---

## 4. Functional Areas

### 4.1 Job Tracking (Jobs page, `/`)

**Purpose:** the home view — a table of all applications with search, filter, and CRUD.

#### List & search

- All jobs ordered by `date_applied` descending. Each row shows position, company, city, status pill, skills, and a document-count badge when documents are attached.
- Free-text search filters client-side across position, company, city, and skills (case-insensitive substring).
- Status filter dropdown. Fixed statuses: `open`, `applied`, `interview_done`, `rejected`, `rejected_after_interview`, `accepted`.

#### Two-level row expansion

- Clicking a row expands an inline **summary panel** showing key fields (position, company, city, status, skills, date applied) without leaving the list.
- From the summary panel, clicking **"View details"** opens the full detail panel — a second, deeper level of expansion with all fields and tabs.

#### Add / Edit / Delete

- **Add job:** opens a dialog with all fields. Required: position, company, date_applied. Status defaults to `open`. Skills entered comma-separated.
- **Edit:** reopens the dialog pre-filled.
- **Delete:** removes the job, cascading to its document links.

#### Job detail panel — tabs

The full detail panel (or standalone page `/jobs/{id}`) has three tabs:

- **Details:** all structured fields, editable with optional AI assist (Ollama / local LLM).
- **Email history:** lists all emails linked to this job. Each email is clickable to read the full message text inline. Any email can be unlinked directly from this tab if it is not relevant.
- **Files:** lists attached documents. Files can be viewed inline (PDF/image preview), deleted, added via file picker, or added by **drag-and-drop** onto the tab area.

#### Validation

Position, company, and `date_applied` must be non-empty. Status must be one of the six valid values (enforced by Pydantic `JobInput` and a SQLite `CHECK` constraint).

---

### 4.2 AI Parsing — Paste & Parse / URL / Bookmarklet / Re-parse

**Purpose:** create or refresh a structured job record from an unstructured posting without manual typing.

#### Paste & Parse dialog

Two tabs:

- **URL:** server fetches the page (`fetcher.py`) and extracts text, then parses.
- **Text:** user pastes the posting body directly.

Parsing runs through the active provider/model and returns structured fields: position, company, description, address, city, hr_email, hr_phone, whatsapp, telegram, hours_per_week, languages, skills. The original `source_url`/`source_text` are stored on the job so it can be re-parsed later.

#### Browser bookmarklet

A draggable bookmarklet (configured from Settings) sends the visible text of any job page to `POST /api/parse-from-bookmarklet`, which parses and creates a job in one click. Page text is capped at 12,000 chars.

#### Re-parse

`POST /api/jobs/{id}/reparse` re-runs parsing from the stored source. If a `source_url` exists it re-fetches; on fetch failure it falls back to cached `source_text`. Only parser-produced fields are overwritten — `date_applied`, `status`, `id`, `created_at` are preserved. Fails with a clear message if the job has no stored source.

#### URL fetch safety (`fetcher.py`)

Only `http`/`https`; blocks private/loopback/link-local/reserved IPs and `.local`/`.internal` hosts (SSRF guard). Response capped at 2 MB and text at 12,000 chars.

#### Error handling

Provider errors map to actionable HTTP responses:

| Code | Meaning |
|---|---|
| 401 | Missing API key — hint to add it to `.env` |
| 503 | Provider unavailable — e.g. "Start Ollama with: ollama serve" |
| 502 | Model returned invalid JSON |
| 504 | Timeout |

---

### 4.3 Import & Export

#### CSV export

Downloads the currently filtered list as CSV with columns: `id`, `position`, `company`, `date_applied`, `status`, `city`, `address`, `hr_email`, `hr_phone`, `skills`, `description`, `created_at`, `updated_at`.

#### Import (`POST /api/jobs/import`)

Bulk-import from a `.csv` or `.json` file.

- **Format detection:** by file extension, falling back to sniffing the first non-whitespace character. JSON accepts a list, a single object, or `{"jobs": [...]}`. CSV uses the header row.
- **Tolerant field mapping:** unknown columns/keys are ignored. Alternative names aliased case- and separator-insensitively, including German headers:
  - `title` / `role` / `Titel` / `Stelle` → `position`
  - `employer` / `Firma` / `Unternehmen` → `company`
  - `Bewerbungsdatum` / `date` → `date_applied`
  - `Stadt` / `location` → `city`
  - `Tags` / `Fähigkeiten` → `skills`
  - `url` / `link` → `source_url`
- **Tolerant status:** normalized case-insensitively against English + German synonyms — e.g. `Applied`/`Beworben` → `applied`, `Interview`/`Vorstellungsgespräch` → `interview_done`, `Offer`/`Zusage` → `accepted`, `Abgelehnt`/`Declined` → `rejected`, `Wishlist`/`Offen` → `open`. Unrecognized status falls back to `open`.
- **Defaults:** missing `date_applied` → today; missing/blank status → `open`.
- **Required:** position and company. Rows lacking these are reported as per-row errors without aborting the import.
- **Blank rows** (trailing CSV newlines) are skipped silently.
- **Duplicate skipping:** rows matching an existing job by `(position, company, date_applied)` (case-insensitive) are skipped. Re-running the same file is safe.
- **Result:** `{ total, imported, skipped, errors: [{row, error}] }` surfaced as a summary plus per-row error list.

---

### 4.4 Documents Library (Documents page, `/documents`)

**Purpose:** a reusable library of files (CVs, cover letters, certificates, portfolios) that can be attached to multiple jobs.

#### Upload & storage

- File + `doc_type` (`cv`, `cover_letter`, `certificate`, `portfolio`, `other`) + optional notes.
- Accepted types: pdf, doc/docx, txt, png/jpg/jpeg.
- Content-addressed deduplication by SHA-256 hash; uploading an identical file returns the existing document.

#### Library vs job view

- Opening `/documents?job=<id>` shows only documents attached to that job, plus an "attach from library" picker.
- The plain page shows the whole library with a **"used by N jobs"** usage count per document.
- Clicking the "used by" count navigates to the jobs list pre-filtered to show only jobs that use that document.

#### Cross-filter (multi-doc)

Documents can be multi-selected. Selecting two or more documents and clicking **"Show jobs"** filters the jobs list to show only jobs that use all selected documents simultaneously.

#### Attach / detach / download / delete

- **Attach:** link an existing library document to a job, or upload a new file in the same step.
- **Download:** streams the stored file with its original filename.
- **Delete:** blocked (409) while the document is still attached to any job; the response lists the blocking jobs. Detaching from all jobs first is required.

#### Filtering & search

- Filter by document type.
- Free-text search by filename or notes.

---

### 4.5 Email Integration (Email page, `/email`)

**Purpose:** automatically detect application-related emails, classify them with the LLM, and link them to the matching job.

#### Accounts

- Add IMAP accounts: label, host, port (default 993), username, password.
- **Passwords are encrypted at rest** with Fernet (key stored in settings, auto-generated on first use). Account responses never include the encrypted password.
- Accounts can be edited, deleted (cascades to their messages), or have their sync history reset ("Full re-sync" → next sync re-fetches everything).

#### Sync (`POST /api/email/sync`)

- Connects via IMAP over SSL to each active account. Incremental: uses `SINCE last_sync` where possible, else `ALL`. First-ever sync is capped to the 500 most recent messages.
- Extracts subject, sender, received date, and plaintext body (body capped at 12,000 chars); stores new messages as `pending`. De-duplicated per account by IMAP UID.
- Single-flight: a second sync request while one is running returns `already_running`. The UI polls `/api/email/status` until completion.

#### Browsing & inline viewing

- Messages list shows: relevance dot, status badge, linked-job badge (links to the job), filter pills (All / Job related / Pending / Irrelevant / Error) with counts, account filter, and free-text search over subject/sender.
- Clicking any email in the list opens a **detail panel displaying the full message body inline** — without leaving the email page.
- **Pagination:** the number of emails shown per page is controlled by the "Emails per page" setting in Settings (see 4.6). The list provides next/previous page controls.

#### Classification / processing

- **Process all pending** (`POST /api/email/process`): streams NDJSON progress events as each pending message is classified.
- **Process / Re-process single** (`POST /api/email/messages/{id}/process`): runs or re-runs classification on one message. UI shows **▶ Process** for `pending`/`error` messages and **↻ Re-process** for already-processed ones.

The LLM returns: `relevant` (bool), `status` (`rejection` | `interview_invite` | `offer` | `application_received` | `other` | null), `company`, `position`, `date`, `confidence` (0–1), `notes`.

- The `notes` field is stored in the email record and is **displayed and manually editable** in the email detail panel.
- Irrelevant messages are marked `irrelevant`; relevant ones store the extracted `llm_status` and raw JSON.

#### Job linking & status updates

- When a relevant message's `company` matches a job, the email is **always linked** to that job (`linked_job_id`), independent of confidence.
- Company matching is **bidirectional and suffix-tolerant**: normalizes both names (lowercase, strip punctuation and legal suffixes like `GmbH`, `AG`, `Steuerberatungsgesellschaft`) and matches if either contains the other. Prefers active jobs, then most recent by date.
- **Status auto-update** is gated: only when `confidence ≥ 0.85` **and** the job is not already in a terminal state (`rejected`, `rejected_after_interview`, `accepted`). Mapping: `rejection` → `rejected`, `interview_invite` → `interview_done`, `application_received` → `applied`.
- **Manual linking:** any message can be linked to a chosen job, changed, or unlinked from the message detail panel.

---

### 4.6 AI Provider Settings

**Purpose:** choose which model parses postings and classifies emails.

#### Provider & model

- Choose **provider** (`ollama`, `anthropic`, `openai`) and **model**. Models can be listed live from the provider (`GET /api/models?provider=`) or typed manually.
- **API-key status** surfaced per provider (whether `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` is present); Ollama needs no key.
- **Test parse** runs a sample through the selected provider/model to confirm it works.

#### Bookmarklet

- Presented here for drag-to-bookmarks-bar; embeds the configured base URL.
- **Re-dragging is required whenever `PORT` changes**, as the bookmarklet URL contains the port number. This is noted in the Settings UI.

#### Email settings

- Separate `email_provider` and `email_ollama_model` for email classification.
- Sync interval and keywords configurable.
- **Emails per page:** integer setting controlling pagination in the email list (e.g. 20, 50, 100). Default: 50.

#### Read / write

`GET/PUT /api/settings` reads/writes the active provider+model (validated against the known provider list).

---

### 4.7 UI / Navigation

- **Collapsible left sidebar** shared across all pages: brand, Navigation (Jobs / Email / Docs / **Dashboard**), and a bottom group (Settings, theme toggle).
- Sidebar state (expanded vs icon-rail) and theme persist in `localStorage`; collapses to a horizontal bar on narrow screens.
- Page-specific actions live in each page's header (e.g. Jobs: Import / Export CSV / Paste & parse / Add job; Email: Sync / Accounts; Docs: Upload).
- **Dark/light theme** via a `data-theme` attribute set before paint to avoid flashes.

---

### 4.8 Dashboard (Dashboard page, `/dashboard`)

**Purpose:** a read-only analytics view giving the user a visual overview of their entire job search — progress, trends, geography, and focus areas — at a glance.

#### Summary metric cards

Four KPI cards displayed at the top of the page:

| Card | Value | Notes |
|---|---|---|
| Total applications | Count of all jobs | All time |
| Active / open | Count with status `open` or `applied` | Awaiting response |
| Interviews done | Count with status `interview_done` | Conversion rate shown as subtitle |
| Rejection rate | Rejected / total as % | `rejected` + `rejected_after_interview` combined |

#### Charts

All charts are rendered client-side from data returned by `GET /api/dashboard`. Each chart has a title, a short subtitle, and a custom HTML legend (no Chart.js default legend). All use Chart.js 4.x.

**Monthly applications — line chart**

- X axis: calendar months (e.g. Jan–Dec of the current year, or last 12 months rolling).
- Y axis: count of jobs with `date_applied` in that month.
- Single dataset, filled area below the line.
- Purpose: shows application velocity and effort over time.

**Status distribution — donut chart**

- Segments: `applied`, `interview_done`, `rejected` (groups `rejected` + `rejected_after_interview`), `accepted`, `open`.
- Each segment labelled with count and percentage in the legend.
- Purpose: instant read on where all applications stand.

**Applications by job type — bar chart**

- X axis: job type categories (full-time, contract, part-time, internship, freelance).
- Y axis: count per type.
- Each bar a distinct color from the purple ramp.
- Purpose: shows which employment types the user is targeting.

**Applications by city — Leaflet map**

- Interactive map rendered with **Leaflet.js** using **OpenStreetMap** tiles (no API key required).
- Each city with at least one application is plotted as a `CircleMarker`; radius scales with `sqrt(count)` so high-volume cities don't visually dominate low-count ones.
- Clicking a marker opens a Leaflet popup showing city name and application count.
- Map auto-fits bounds to the set of plotted cities on load (`map.fitBounds`); falls back to a default center (Germany: `[51.1, 10.4]`, zoom 6) if no city geodata is available.
- Purpose: geographic distribution of the search effort.
- Implementation notes:
  - Leaflet JS + CSS loaded from `unpkg.com` (`leaflet@1.9.x`).
  - City coordinates resolved via a backend-side static lookup table (`city → [lat, lng]`) covering major German cities; unrecognized city names are omitted from the map and listed as "unmapped" in a small note below the chart.
  - Tile URL: `https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png` with standard OSM attribution.
  - Map container requires an explicit pixel height (e.g. `320px`) — Leaflet cannot render into a zero-height div.
  - Map is initialized after the container is visible in the DOM; a `ResizeObserver` calls `map.invalidateSize()` if the sidebar collapses or expands.

**Position treemap**

- Rectangular treemap where each tile represents a unique `position` value (or normalized position title).
- Tile area proportional to application count for that position.
- Tiles labelled with position name + count; tiles too small to label are shown without text.
- Purpose: surfaces which roles the user is applying for most, revealing focus or scatter.
- Implementation note: squarify layout algorithm computed client-side from sorted position counts.

#### Data source — `GET /api/dashboard`

Single endpoint returning all aggregated data needed by the page. No raw job records are returned; only counts and groupings. Response shape:

```json
{
  "summary": {
    "total": 47,
    "active": 12,
    "interviews": 8,
    "rejection_rate": 0.57
  },
  "by_month": [
    { "month": "2025-01", "count": 2 },
    { "month": "2025-02", "count": 3 }
  ],
  "by_status": [
    { "status": "applied", "count": 12 },
    { "status": "interview_done", "count": 8 },
    { "status": "rejected", "count": 27 }
  ],
  "by_type": [
    { "type": "full-time", "count": 31 },
    { "type": "contract", "count": 10 }
  ],
  "by_city": [
    { "city": "Berlin", "count": 18 },
    { "city": "Dresden", "count": 12 }
  ],
  "by_position": [
    { "position": "Backend Engineer", "count": 14 },
    { "position": "Kotlin Developer", "count": 9 }
  ]
}
```

All fields are computed with SQLite `GROUP BY` queries; no external services required. The endpoint is read-only and always reflects the current state of the `jobs` table.

> **City geocoding:** the `by_city` array is enriched server-side — each entry gets a `lat` and `lng` from a static lookup table of major German cities before the response is returned. Cities not found in the lookup are included without coordinates (`lat: null, lng: null`) and skipped by the Leaflet map renderer.

#### Behavior & UX

- The page is **read-only** — no editing actions. Navigation back to the jobs list is via the sidebar.
- Charts update on every page load (no caching); a manual **Refresh** button is available in the page header.
- Empty state: if fewer than 3 jobs exist, a prompt is shown instead of charts ("Add more applications to see your dashboard").
- All charts respect the active **dark/light theme**.
- The page is added to the left sidebar navigation between Docs and Settings.

---

## 5. Data Model (SQLite)

| Table | Key columns |
|---|---|
| **jobs** | `id`, `position`, `company`, `description`, `date_applied`, `status`, `address`, `city`, `hr_email`, `hr_phone`, `skills`, `whatsapp`, `telegram`, `hours_per_week`, `languages`, `source_url`, `source_text`, `created_at`, `updated_at`. `CHECK` constraint on `status`. |
| **settings** | Single row (`id=1`): `provider`, `model`, `email_provider`, `email_ollama_model`, `email_sync_interval`, `email_keywords`, `email_page_size`, `fernet_key`. |
| **documents** | `id`, `filename`, `doc_type`, `file_path`, `file_hash` (UNIQUE), `file_size`, `uploaded_at`, `notes`. |
| **job_documents** | `id`, `job_id` (FK→jobs CASCADE), `document_id` (FK→documents RESTRICT), `attached_at`. `UNIQUE(job_id, document_id)`. |
| **email_accounts** | `id`, `label`, `imap_host`, `imap_port`, `username`, `password_enc`, `last_sync_at`, `active`. |
| **email_messages** | `id`, `account_id` (FK→email_accounts CASCADE), `uid`, `subject`, `sender`, `received_at`, `body_text`, `relevance`, `processed_at`, `linked_job_id` (FK→jobs), `llm_status`, `llm_raw` (full classifier JSON, incl. notes). `UNIQUE(account_id, uid)`. |

> **Schema notes:** auto-created and auto-migrated on startup. Two new columns added:
> - `settings.email_page_size` (integer, default 50) — controls email list pagination.
> - `email_messages.llm_notes` (text, nullable) — stores the `notes` field returned by the LLM.

---

## 6. API Surface (Selected)

| Method & path | Purpose |
|---|---|
| `GET /`, `/email`, `/documents`, `/jobs/{id}`, `/dashboard` | Serve pages (`/settings` redirects to `/`) |
| `GET /api/dashboard` | Aggregated dashboard data (summary, by_month, by_status, by_type, by_city, by_position) |
| `GET/POST /api/jobs` | List / create jobs |
| `GET/PUT/DELETE /api/jobs/{id}` | Read / update / delete job |
| `POST /api/jobs/import` | CSV/JSON bulk import |
| `POST /api/parse` | AI parse from text or URL |
| `POST /api/jobs/{id}/reparse` | Re-parse from stored source |
| `POST /api/parse-from-bookmarklet` | Parse + create from bookmarklet |
| `GET /api/documents` | List document library |
| `POST /api/documents` | Upload new document |
| `GET /api/documents/{id}/download` | Download file |
| `DELETE /api/documents/{id}` | Delete (blocked if attached to any job) |
| `GET/POST /api/jobs/{id}/documents` | List / attach docs to job |
| `DELETE /api/jobs/{id}/documents/{doc_id}` | Detach doc from job |
| `GET/POST/PUT/DELETE /api/email/accounts/...` | Email account CRUD |
| `POST /api/email/accounts/{id}/reset-sync` | Full re-sync reset |
| `POST /api/email/sync` | Trigger sync |
| `GET /api/email/status` | Sync status (poll) |
| `GET /api/email/messages` | List messages (paginated, filtered) |
| `POST /api/email/process` | Classify all pending |
| `POST /api/email/messages/{id}/process` | Classify / re-process one message |
| `POST /api/email/messages/{id}/link` | Link message to job |
| `DELETE /api/email/messages/{id}/link` | Unlink message from job |
| `GET/PUT /api/settings` | Read / write settings |
| `GET /api/email/settings` | Read email-specific settings |
| `GET /api/models` | List models for provider |
| `GET /api/config` | Read runtime config |

---

## 7. Configuration & Run

| Variable | Default | Notes |
|---|---|---|
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `8001` | Changing requires re-dragging the bookmarklet (the bookmarklet URL embeds the port) |
| `DOCS_DIR` | `~/.job-tracker/docs` | Directory for uploaded files |
| `ANTHROPIC_API_KEY` | _(none)_ | Required only for Anthropic provider |
| `OPENAI_API_KEY` | _(none)_ | Required only for OpenAI provider |

Run: `uvicorn server:app --reload` (from `App/src`), then open `http://localhost:8001`. `jobs.db` is created on first run; back up by copying the file.

---

## 8. Security & Privacy

- **Local-first:** all data in a local SQLite file and local disk; with Ollama, postings/emails never leave the machine.
- **Email passwords** encrypted at rest with Fernet; never returned by the API.
- **SSRF protection** on URL fetching (scheme allow-list, private-host blocking, size caps).
- **CORS** is currently fully open (`allow_origins=["*"]`, `allow_private_network=True`) to support the bookmarklet posting from arbitrary pages — acceptable for a localhost single-user tool, but a hardening point if ever exposed.

---

## 9. Known Constraints / Limitations

- Single user; no authentication.
- Company matching is name-based (substring, suffix-tolerant) and does not factor in position; with two open applications at the same company, an email links to the most recent active one.
- Unrecognized import statuses silently become `open` (favoring import success over strictness).
- No automatic background sync scheduler — sync is user-triggered (`email_sync_interval` setting exists but scheduling is out of scope of the current request flow).
- LLM output quality (relevance, extracted company/status, confidence) depends on the chosen model.
