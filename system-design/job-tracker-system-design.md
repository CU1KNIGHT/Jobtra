# Job Application Tracker — System Design

Version 2.0 — includes bookmarklet, email sync, local LLM processing via Ollama, and document library

---

## 1. Overview

A local-first, privacy-respecting job application tracker that runs entirely on `localhost`. It aggregates applications from three input paths: manual paste-and-parse, a browser bookmarklet (for LinkedIn and gated job sites), and automatic email inbox scanning. A locally-running LLM (Ollama) processes all text — no cloud API keys required by default. A cloud provider (OpenAI, Anthropic) is optional and selectable at runtime.

The system keeps a single source of truth: a SQLite database on the user's machine. Nothing leaves the machine unless the user opts into a cloud LLM provider.

---

## 2. High-Level Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│  Browser (localhost:8001)                                             │
│                                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐ │
│  │ Tracker  │  │ Settings │  │  Email   │  │ Bookmarklet (runs on  │ │
│  │  (index) │  │  page    │  │   tab    │  │ third-party job site) │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────────┬───────────┘ │
└───────┼─────────────┼─────────────┼────────────────────┼─────────────┘
        │             │             │                    │
        ▼             ▼             ▼                    ▼
┌───────────────────────────────────────────────────────────────────────┐
│  FastAPI Server  (server.py)                                          │
│                                                                       │
│  GET  /                          → index.html                        │
│  GET  /settings                  → settings.html (BASE_URL injected) │
│  GET  /email                     → email.html                        │
│  GET  /documents                 → documents.html                    │
│                                                                       │
│  POST /api/parse                 ← paste/URL input                   │
│  POST /api/parse-from-bookmarklet← bookmarklet POST                  │
│  POST /api/jobs                  ← confirm/save parsed job           │
│  GET  /api/jobs                  ← list all jobs                     │
│  PUT  /api/jobs/{id}             ← edit / status update              │
│  DELETE /api/jobs/{id}           ← delete job                        │
│  POST /api/jobs/{id}/reparse     ← re-parse stored source text       │
│                                                                       │
│  POST /api/jobs/{id}/documents   ← attach document to job            │
│  DELETE /api/jobs/{id}/documents/{doc_id} ← detach document from job │
│  GET  /api/documents             ← list document library             │
│  POST /api/documents             ← upload new file to library        │
│  DELETE /api/documents/{doc_id}  ← delete from library (if unused)  │
│                                                                       │
│  GET  /api/email/accounts        ← list connected email accounts     │
│  POST /api/email/accounts        ← add IMAP account                  │
│  DELETE /api/email/accounts/{id} ← remove account                   │
│  POST /api/email/sync            ← trigger manual sync               │
│  GET  /api/email/status          ← sync status (last run, count)     │
│  GET  /api/email/messages        ← list fetched relevant emails      │
│  POST /api/email/process         ← LLM-process selected/all emails   │
│  GET  /api/config                ← { base_url, active_provider }     │
└──────────────────────────┬────────────────────────────────────────────┘
                           │
          ┌────────────────┴─────────────────┐
          │                                  │
          ▼                                  ▼
┌──────────────────┐               ┌──────────────────────┐
│  Provider Layer  │               │  Email Layer         │
│  (providers.py)  │               │  (email_sync.py)     │
│                  │               │                      │
│  OllamaProvider  │               │  IMAPClient          │
│  OpenAIProvider  │               │  EmailFilter         │
│  AnthropicProvider│              │  AttachmentParser    │
└────────┬─────────┘               └──────────┬───────────┘
         │                                    │
         ▼                                    ▼
┌──────────────────┐               ┌──────────────────────┐
│  Ollama          │               │  User's email inboxes│
│  (localhost:11434│               │  (IMAP: Gmail/Outlook│
│  — stays local)  │               │  /custom SMTP)       │
└──────────────────┘               └──────────────────────┘
         │
         ▼
┌──────────────────┐
│  SQLite DB       │
│  (tracker.db)    │
└──────────────────┘
```

---

## 3. Data Model

### 3.1 `jobs` table

| Column         | Type    | Notes                                                                   |
|----------------|---------|-------------------------------------------------------------------------|
| id             | INTEGER | PK, autoincrement                                                       |
| company        | TEXT    | Parsed company name                                                     |
| position       | TEXT    | Job title                                                               |
| location       | TEXT    | City / remote / hybrid                                                  |
| salary         | TEXT    | Nullable, raw string (e.g. "€60k–€80k")                                |
| status         | TEXT    | Enum: open, applied, interview, offer, rejected, accepted, withdrawn    |
| date_applied   | TEXT    | ISO date, defaults to today                                             |
| source_url     | TEXT    | Original page URL (bookmarklet / URL paste)                             |
| source_text    | TEXT    | Truncated raw text used for parsing                                     |
| source_email_id| INTEGER | FK → email_messages.id (nullable)                                       |
| notes          | TEXT    | User freetext                                                           |
| created_at     | TEXT    | ISO datetime                                                            |
| updated_at     | TEXT    | ISO datetime                                                            |

### 3.2 `documents` table

One row per unique file on disk. Files are identified by content hash, not filename.

| Column      | Type    | Notes                                                         |
|-------------|---------|---------------------------------------------------------------|
| id          | INTEGER | PK, autoincrement                                             |
| filename    | TEXT    | Original name on upload, e.g. "CV_2026.pdf"                  |
| doc_type    | TEXT    | `cv` \| `cover_letter` \| `certificate` \| `portfolio` \| `other` |
| file_path   | TEXT    | Absolute path on disk, e.g. `~/.job-tracker/docs/a3f9b2.pdf` |
| file_hash   | TEXT    | SHA-256 hex digest — uniqueness key                           |
| file_size   | INTEGER | Bytes                                                         |
| uploaded_at | TEXT    | ISO datetime of first upload                                  |
| notes       | TEXT    | User annotation, nullable                                     |

Files on disk are named by their hash (e.g. `a3f9b2.pdf`), not by their original filename. This prevents two different files with the same name from colliding. The original filename is preserved in `documents.filename` for display only.

### 3.3 `job_documents` join table

Many jobs can reference the same document; no file duplication.

| Column      | Type    | Notes                                             |
|-------------|---------|---------------------------------------------------|
| id          | INTEGER | PK                                                |
| job_id      | INTEGER | FK → jobs.id ON DELETE CASCADE                    |
| document_id | INTEGER | FK → documents.id ON DELETE RESTRICT              |
| attached_at | TEXT    | ISO datetime this link was created                |

`ON DELETE RESTRICT` on `document_id` means a document cannot be deleted from the library while it is still attached to any job. The UI must warn and offer to detach first.

### 3.4 `settings` table

| Column | Type | Notes |
|--------|------|-------|
| key    | TEXT | PK    |
| value  | TEXT |       |

Key/value pairs used:

- `provider` — `ollama` | `openai` | `anthropic`
- `ollama_model` — e.g. `llama3.2:3b`
- `openai_model` — e.g. `gpt-4o-mini`
- `anthropic_model` — e.g. `claude-haiku-4-5-20251001`
- `openai_api_key`
- `anthropic_api_key`
- `email_sync_interval_minutes` — default `60`
- `email_filter_keywords` — JSON array, default `["application", "interview", "offer", "reject", "position", "role", "hiring"]`

### 3.5 `email_accounts` table

| Column       | Type    | Notes                               |
|--------------|---------|-------------------------------------|
| id           | INTEGER | PK                                  |
| label        | TEXT    | User-facing name, e.g. "Work Gmail" |
| imap_host    | TEXT    | e.g. `imap.gmail.com`               |
| imap_port    | INTEGER | 993 for SSL                         |
| username     | TEXT    | Email address                       |
| password_enc | TEXT    | AES-256 encrypted, key from keyring |
| last_sync_at | TEXT    | ISO datetime                        |
| active       | INTEGER | 0/1, can disable without deleting   |

### 3.6 `email_messages` table

| Column         | Type    | Notes                                                                                            |
|----------------|---------|--------------------------------------------------------------------------------------------------|
| id             | INTEGER | PK                                                                                               |
| account_id     | INTEGER | FK → email_accounts.id                                                                           |
| uid            | TEXT    | IMAP UID (unique within account)                                                                 |
| subject        | TEXT    |                                                                                                  |
| sender         | TEXT    |                                                                                                  |
| received_at    | TEXT    | ISO datetime                                                                                     |
| body_text      | TEXT    | Plaintext body, truncated to 12,000 chars                                                        |
| relevance      | TEXT    | `pending` \| `relevant` \| `irrelevant`                                                          |
| processed_at   | TEXT    | Nullable — when LLM processing ran                                                               |
| linked_job_id  | INTEGER | FK → jobs.id (nullable, set after processing)                                                    |
| llm_status     | TEXT    | `rejection` \| `interview_invite` \| `offer` \| `application_received` \| `other` \| `null`     |
| llm_raw        | TEXT    | Raw JSON returned by LLM                                                                         |

---

## 4. Feature Modules

### 4.1 Core Tracker

Manual paste-and-parse: user pastes a job description or URL into the main page. The backend fetches the URL (if given) or uses the pasted text directly, truncates to 12,000 chars, calls the active LLM provider with a structured extraction prompt, and returns a preview card. The user confirms, edits inline, and saves.

Re-parse: any job row with a non-null `source_text` shows a ↻ button. Clicking it re-sends the stored text through the current active provider/model — useful when switching models or fixing a bad initial parse.

### 4.2 Browser Bookmarklet

**Problem it solves**: LinkedIn, Xing, StepStone, and most ATS portals require login and render via JS. The backend's `httpx.get(url)` only sees a login wall. The bookmarklet runs *inside the user's already-authenticated tab*, reads `document.body.innerText`, and POSTs it to the local backend. No credentials ever leave the browser.

**Setup (one-time)**: User visits `http://localhost:8001/settings`, finds the "Browser bookmark" section, and drags the "➕ Add to Job Tracker" link to their bookmarks bar.

**Daily use**: On any job posting, click the bookmark. A toast appears bottom-right: "Saving…" → "✓ Saved: \<position\> at \<company\>". No preview — saves immediately. User edits via the row's edit button if needed.

**Important**: The bookmarklet `href` is generated server-side with `__BASE_URL__` substituted to the actual `HOST:PORT` the server is running on. If the user changes `PORT` in `.env`, they must re-drag the bookmark from `/settings`.

**CORS requirement**: Because the bookmarklet runs on `https://www.linkedin.com` and POSTs to `http://localhost:8001`, browsers would block the request by default. `CORSMiddleware` with `allow_origins=["*"]` is added to the FastAPI app. This is safe because the app is local-only with no authentication surface to protect.

**Endpoint**: `POST /api/parse-from-bookmarklet`

```json
// Request
{ "text": "...", "url": "https://www.linkedin.com/jobs/view/..." }

// Response 201
{
  "id": 42,
  "company": "Acme GmbH",
  "position": "Backend Engineer",
  "status": "open",
  "date_applied": "2026-05-29",
  ...
}
```

### 4.3 Document Library

Documents are stored once and referenced by many jobs. No duplication.

#### 4.3.1 Upload Flow

```
User uploads file
       │
       ▼
Compute SHA-256 of file bytes
       │
       ▼
SELECT * FROM documents WHERE file_hash = ?
       │
   ┌───┴────────────┐
  found           not found
   │                   │
   │            Save file to disk
   │            as {hash}.{ext}
   │            INSERT INTO documents
   │                   │
   └───────┬───────────┘
           │
    INSERT INTO job_documents
    (job_id, document_id)
           │
           ▼
    Return documents row + job_documents link
    to frontend
```

A CV uploaded once gets one row in `documents` and one file on disk. Attaching it to 5 jobs creates 5 rows in `job_documents`, all pointing to the same `document_id`. Even if the same file is uploaded from two different paths or with different filenames, the SHA-256 hash detects it as identical and no duplicate is written to disk.

#### 4.3.2 Attaching Documents to a Job

The job detail page upload button offers two options:

- **Upload new file** — hashes the file, creates a new `documents` row if hash is unseen, always creates a `job_documents` link.
- **Attach from library** — opens a searchable list of all files in `documents`, lets the user pick one or more, creates `job_documents` rows with no file I/O.

#### 4.3.3 Delete Flow

Two separate actions:

- **Detach** (`DELETE /api/jobs/{id}/documents/{doc_id}`) — removes only the `job_documents` row. The file and `documents` row remain. This is the default action from the job detail page.
- **Delete from library** (`DELETE /api/documents/{doc_id}`) — only allowed if `SELECT COUNT(*) FROM job_documents WHERE document_id = ?` returns 0. If still attached to any job, returns `409` with a list of affected jobs. The ✕ button in the library UI is disabled when count > 0.

#### 4.3.4 Migration from Old Schema

If documents were already stored under a previous `job_documents` design that conflated file storage with job attachment:

```sql
-- 1. Create new tables
CREATE TABLE documents ( ... );
CREATE TABLE job_documents_new ( ... );

-- 2. Migrate existing rows
-- For each old row: compute hash of the file, insert into documents if not exists,
-- then insert the link into job_documents_new.
-- Done in a Python migration script (not pure SQL) because hashing requires file I/O.

-- 3. Rename
ALTER TABLE job_documents RENAME TO job_documents_old;
ALTER TABLE job_documents_new RENAME TO job_documents;
```

The migration script reads each file from disk, hashes it, deduplicates, and rebuilds the two-table structure. Files missing from disk are flagged as broken links rather than crashing the migration.

### 4.4 Email Integration

#### 4.4.1 Goals

- Scan the user's inbox(es) for job-related emails (rejections, interview invites, offers, confirmations).
- Use a local Ollama model to classify each email and extract the status update.
- Automatically update the corresponding `jobs` row status if a match is found, or surface the email for manual linking.
- Never send email credentials or email content to any cloud service (all LLM processing uses the locally-running Ollama instance).

#### 4.4.2 Email Sync Flow

```
┌─────────────────────────────────────────────────────────────┐
│  email_sync.py  — sync cycle (manual or scheduled)          │
│                                                             │
│  For each active email_account:                             │
│    1. Connect via IMAP SSL                                  │
│    2. SEARCH UNSEEN SINCE <last_sync_at>                    │
│    3. For each message UID:                                 │
│       a. Fetch BODY[TEXT] + ENVELOPE (subject, from, date)  │
│       b. Keyword pre-filter: skip if no hit in subject      │
│          or first 500 chars of body                         │
│       c. Insert into email_messages (relevance = "pending") │
│    4. Update account.last_sync_at                           │
│                                                             │
│  Keyword pre-filter (fast, no LLM):                         │
│  subject/body contains any of:                              │
│    application, interview, offer, reject, congratulations,  │
│    unfortunately, position, role, hiring, thank you for     │
│    applying, next steps, assessment, onboarding             │
└─────────────────────────────────────────────────────────────┘
```

The keyword pre-filter is intentionally broad and false-positive-friendly. The LLM step does the precise classification; the pre-filter just avoids sending every promotional email through the LLM.

#### 4.4.3 LLM Email Processing

Triggered by the "Process All" button in the UI, or individually per email.

```
For each email_message WHERE relevance = "pending":

  1. Build prompt:
     SYSTEM: You extract job application status updates from emails.
     USER:
       Subject: {subject}
       From: {sender}
       Body (truncated to 3000 chars):
       {body_text}

       Return JSON only:
       {
         "relevant": true/false,
         "status": "rejection"|"interview_invite"|"offer"|"application_received"|"other"|null,
         "company": "...",
         "position": "...",
         "date": "ISO date or null",
         "confidence": 0.0–1.0,
         "notes": "one-sentence summary"
       }

  2. Call active provider's parse() — ALWAYS uses Ollama for email processing
     (never cloud provider, regardless of settings — email privacy guarantee)

  3. Parse JSON response.
     If relevant=false → set email.relevance = "irrelevant", stop.
     If relevant=true  → set email.relevance = "relevant", store llm_status + llm_raw.

  4. Auto-link attempt:
     Search jobs WHERE company ILIKE email.llm.company
       AND (position ILIKE email.llm.position OR date_applied within 60 days)
     If one confident match → update jobs.status, set email.linked_job_id.
     If ambiguous → surface for manual linking in the UI.

  5. If no matching job exists and status = "application_received" → create new job row.
```

**Privacy guarantee**: Email processing always uses the local Ollama provider, regardless of which provider is selected globally. This is enforced in `email_sync.py` by constructing the `OllamaProvider` directly, not reading from settings. A notice in the UI informs the user: "Email content is processed locally by Ollama and never sent to cloud services."

#### 4.4.4 IMAP Credential Storage

Credentials are not stored in plaintext. On first save:

1. Generate a random AES-256 key, store it in the OS keyring (`keyring` Python library — works on Windows Credential Manager, macOS Keychain, Linux Secret Service).
2. Encrypt the IMAP password with that key.
3. Store the encrypted bytes (base64) in `email_accounts.password_enc`.

If the OS keyring is unavailable (headless server), fall back to a `.env`-derived master key with a warning in the UI.

---

## 5. Frontend Pages

### 5.1 `index.html` — Main Tracker

- Table of all jobs, sorted by `created_at` DESC.
- Status badge per row, color-coded: open (gray), applied (blue), interview (amber), offer (green), rejected (red), accepted (teal), withdrawn (muted).
- Inline edit on click. Inline status dropdown.
- ↻ Re-parse button (shown if `source_text` is non-null).
- Email-linked indicator: envelope icon if `source_email_id` is set; click reveals the email in a side panel.
- Document count badge per row; click opens the job's attached documents panel.
- Paste/URL input at the top of the page.

### 5.2 `settings.html` — Settings

Sections:

1. **LLM Provider** — radio: Ollama / OpenAI / Anthropic. Show model input per provider. Test connection button.
2. **Ollama** — model name, pull shortcut, health check badge.
3. **Browser bookmark** — drag-to-install link. Port-change caveat note.
4. **Email accounts** — list of connected IMAP accounts, add/remove. Sync interval setting.
5. **Email keywords** — editable list used for the pre-filter.
6. **Danger zone** — wipe database, reset settings.

### 5.3 `email.html` — Email Tab

```
┌─────────────────────────────────────────────────────────────┐
│ Email                          [↻ Sync Now]  [⚙ Accounts]  │
│                                                             │
│ Last sync: 2 minutes ago · 3 new messages                   │
│                                                             │
│ [Process All Unprocessed ▶]   [Filter: All ▼]              │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ ● [rejection]  "Unfortunately, your application…"      │ │
│ │   Acme GmbH · Backend Engineer · 28 May 2026           │ │
│ │   → Linked to job row #42  [View]                      │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │ ● [interview]  "We'd love to invite you to…"           │ │
│ │   TechCorp · Senior Developer · 27 May 2026            │ │
│ │   → No match found  [Link manually]  [Create new job]  │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │ ○ [pending]    "Thank you for applying to…"            │ │
│ │   Unknown Company · 25 May 2026                        │ │
│ │   [Process this email ▶]                               │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ℹ Email content is processed locally by Ollama.            │
│   It is never sent to cloud services.                       │
└─────────────────────────────────────────────────────────────┘
```

Status badges: `rejection` → red, `interview_invite` → amber, `offer` → green, `application_received` → blue, `other` → gray, `pending` → outlined/muted.

Clicking an email row expands it to show the full subject, sender, body excerpt, and LLM-extracted notes. The "Link manually" flow opens a searchable dropdown of existing job rows.

**Sync status** polling: the frontend polls `GET /api/email/status` every 5 seconds while a sync is in progress, showing a spinner and "Syncing… (12/47 emails scanned)".

**Process All** button: POSTs to `/api/email/process` with `{ "batch": "all_pending" }`. Response is streamed as newline-delimited JSON events, one per processed email, so the UI can update row states in real time without a full page reload.

### 5.4 `documents.html` — Document Library

```
Documents library                          [+ Upload new]

CV_2026.pdf          cv           2.1 MB   Used by 7 jobs   [↓] [✕]
CoverLetter_Acme.pdf cover_letter 340 KB   Used by 1 job    [↓] [✕]
Python_Cert.pdf      certificate  180 KB   Used by 3 jobs   [↓] [✕]
```

The "Used by N jobs" count comes from `SELECT COUNT(*) FROM job_documents WHERE document_id = ?`. Clicking it navigates to a filtered jobs view. The ✕ button is disabled if count > 0, or shows a confirmation warning listing the affected jobs.

---

## 6. Backend Implementation

### 6.1 `server.py` additions

```python
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8001"))
BASE_URL = f"http://{HOST}:{PORT}"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    html = Path("../ui/settings.html").read_text()
    return html.replace("__BASE_URL__", BASE_URL)


@app.get("/email", response_class=HTMLResponse)
async def email_page():
    return Path("../ui/email.html").read_text()


@app.get("/documents", response_class=HTMLResponse)
async def documents_page():
    return Path("../ui/documents.html").read_text()


@app.post("/api/parse-from-bookmarklet", status_code=201)
async def parse_from_bookmarklet(body: BookmarkletRequest):
    if not body.text.strip():
        raise HTTPException(400, detail={"error": "Empty page text"})
    text = body.text[:12000]
    provider = get_active_provider()
    parsed = await provider.parse(text, get_active_model())
    parsed.source_url = body.url
    parsed.source_text = text
    parsed.date_applied = date.today().isoformat()
    parsed.status = "open"
    job = db.create_job(parsed)
    return job


@app.post("/api/jobs/{job_id}/documents", status_code=201)
async def attach_document(job_id: int, file: UploadFile = File(...), doc_type: str = "other"):
    file_bytes = await file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    ext = Path(file.filename).suffix
    existing = db.get_document_by_hash(file_hash)
    if existing:
        doc = existing
    else:
        file_path = DOCS_DIR / f"{file_hash}{ext}"
        file_path.write_bytes(file_bytes)
        doc = db.create_document(filename=file.filename, doc_type=doc_type,
                                 file_path=str(file_path), file_hash=file_hash,
                                 file_size=len(file_bytes))
    link = db.attach_document(job_id=job_id, document_id=doc.id)
    return {"document": doc, "link": link}


@app.delete("/api/jobs/{job_id}/documents/{doc_id}", status_code=204)
async def detach_document(job_id: int, doc_id: int):
    db.detach_document(job_id=job_id, document_id=doc_id)


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: int):
    count = db.count_job_documents(doc_id)
    if count > 0:
        jobs = db.get_jobs_for_document(doc_id)
        raise HTTPException(409, detail={"error": "Document still attached", "jobs": jobs})
    db.delete_document(doc_id)


@app.post("/api/email/sync")
async def trigger_email_sync(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_email_sync)
    return {"status": "started"}


@app.post("/api/email/process")
async def process_emails(body: ProcessEmailsRequest):
    return StreamingResponse(
        process_pending_emails(body.batch),
        media_type="application/x-ndjson"
    )
```

### 6.2 `email_sync.py`

```python
import imaplib, email, keyring
from cryptography.fernet import Fernet

RELEVANCE_KEYWORDS = [
    "application", "interview", "offer", "reject", "unfortunately",
    "congratulations", "position", "role", "hiring", "thank you for applying",
    "next steps", "assessment", "onboarding", "move forward",
]

class IMAPClient:
    def __init__(self, account: EmailAccount):
        key = keyring.get_password("job-tracker", account.username)
        password = Fernet(key).decrypt(account.password_enc).decode()
        self.conn = imaplib.IMAP4_SSL(account.imap_host, account.imap_port)
        self.conn.login(account.username, password)

    def fetch_since(self, since: datetime) -> list[RawEmail]:
        self.conn.select("INBOX")
        _, uids = self.conn.search(None, f'SINCE {since.strftime("%d-%b-%Y")}')
        results = []
        for uid in uids[0].split():
            _, data = self.conn.fetch(uid, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            body = extract_plaintext(msg)
            if is_relevant(msg["Subject"], body):
                results.append(RawEmail(uid=uid, subject=msg["Subject"],
                    sender=msg["From"], body=body[:12000],
                    received_at=parsedate(msg["Date"])))
        return results

def is_relevant(subject: str, body: str) -> bool:
    text = (subject + " " + body[:500]).lower()
    return any(kw in text for kw in RELEVANCE_KEYWORDS)
```

### 6.3 `providers.py` — Email Processing

Email processing always constructs `OllamaProvider` directly:

```python
EMAIL_SYSTEM_PROMPT = """
You extract job application status updates from emails.
Return only valid JSON. No markdown, no preamble.
Schema:
{
  "relevant": bool,
  "status": "rejection"|"interview_invite"|"offer"|"application_received"|"other"|null,
  "company": string|null,
  "position": string|null,
  "date": "YYYY-MM-DD"|null,
  "confidence": float 0.0-1.0,
  "notes": string
}
"""

async def process_email_with_llm(email: EmailMessage, db_settings: Settings) -> EmailLLMResult:
    # Always Ollama — never cloud — regardless of global provider setting
    provider = OllamaProvider(model=db_settings.ollama_model or "llama3.2:3b")
    prompt = f"Subject: {email.subject}\nFrom: {email.sender}\n\n{email.body_text[:3000]}"
    raw = await provider.complete(EMAIL_SYSTEM_PROMPT, prompt)
    return parse_email_llm_response(raw)
```

---

## 7. LLM Provider Interface

All providers implement the same interface:

```python
class BaseProvider:
    async def parse(self, text: str, model: str) -> ParsedJob:
        """Extract job fields from a job description text."""

    async def complete(self, system: str, user: str) -> str:
        """Raw completion, used for email processing."""
```

### Recommended Ollama models by use case

| Use case       | Recommended model | Notes                                              |
|----------------|-------------------|----------------------------------------------------|
| Job parsing    | `llama3.2:3b`     | Fast, good JSON extraction                         |
| Job parsing    | `qwen2.5:7b`      | Better structured output, more RAM                 |
| Email classify | `llama3.2:3b`     | Short inputs, very fast                            |
| Email classify | `phi3.5:3.8b`     | Good instruction-following, low RAM                |

For email classification specifically, a 3B model is recommended even if the user has a larger model configured globally — processing an inbox of 50+ emails with a 70B model would be impractically slow. This can be configured separately via the `email_ollama_model` setting (defaults to `llama3.2:3b`).

---

## 8. Status Lifecycle

```
                ┌──────────────────────────────────────────┐
                │              Job Status FSM              │
                └──────────────────────────────────────────┘

  [bookmarklet / paste]
         │
         ▼
      ┌──────┐   manual / email "application_received"
      │ open │ ──────────────────────────────────────────► ┌─────────┐
      └──────┘                                             │ applied │
                                                           └────┬────┘
                                                                │
                                          email "interview_invite" / manual
                                                                │
                                                                ▼
                                                         ┌───────────┐
                                                         │ interview │
                                                         └─────┬─────┘
                                                               │
                        ┌──────────────────────────────────────┤
                        │                                      │
               email "offer" / manual              email "rejection" / manual
                        │                                      │
                        ▼                                      ▼
                   ┌────────┐                           ┌───────────┐
                   │ offer  │                           │ rejected  │
                   └───┬────┘                           └───────────┘
                       │
              manual accept / decline
                       │
          ┌────────────┴──────────────┐
          ▼                           ▼
    ┌──────────┐               ┌───────────┐
    │ accepted │               │ withdrawn │
    └──────────┘               └───────────┘
```

Email processing triggers automatic status transitions only when `confidence >= 0.85`. Below that threshold, the email is surfaced as a "suggested update" in the UI — the user reviews and confirms. This prevents a miscategorised marketing email from erroneously setting a job to `rejected`.

---

## 9. Error Handling

### Provider errors (unified across all endpoints)

| Exception             | HTTP | Body                                                                 |
|-----------------------|------|----------------------------------------------------------------------|
| `ProviderUnavailable` | 503  | `{ "error": "...", "hint": "Start Ollama with: ollama serve" }`      |
| `ProviderAuthError`   | 401  | `{ "error": "Invalid API key", "hint": "Add X_API_KEY to .env" }`    |
| `ProviderBadOutput`   | 502  | `{ "error": "Model returned invalid JSON" }`                         |
| `ProviderTimeout`     | 504  | `{ "error": "Provider timed out" }`                                  |
| Empty text            | 400  | `{ "error": "Empty page text" }`                                     |

### Document errors

| Situation                           | Behaviour                                                                  |
|-------------------------------------|----------------------------------------------------------------------------|
| Delete document still attached      | 409 with list of attached jobs. UI disables ✕ button when count > 0.      |
| File missing from disk on migration | Flagged as broken link; migration continues without crashing.              |
| Duplicate upload (same hash)        | Silently reuses existing `documents` row; creates new `job_documents` link.|

### Email-specific errors

| Situation                | Behaviour                                                                    |
|--------------------------|------------------------------------------------------------------------------|
| IMAP connection failed   | Account shows "⚠ Connection failed" in settings. Sync skipped, not crashed. |
| IMAP auth failed         | Prompt user to re-enter credentials.                                         |
| LLM returns invalid JSON | Mark email as `relevance = "error"`, show in UI with manual process option.  |
| No matching job row      | Surface email as "unlinked" for manual review.                               |
| Keyring unavailable      | Warn in UI. Fall back to `.env` master key.                                  |

---

## 10. Security Considerations

| Concern                        | Mitigation                                                          |
|--------------------------------|---------------------------------------------------------------------|
| IMAP credentials at rest       | AES-256 encrypted, key in OS keyring                               |
| Email content to cloud         | Blocked by design — email LLM processing hardcoded to Ollama       |
| CORS `allow_origins=["*"]`     | Safe because app is local-only, no session auth, nothing to steal  |
| Bookmarklet on HTTPS pages     | Chrome/Firefox carve out localhost from mixed-content blocking     |
| Safari                         | Not supported — Safari blocks HTTP fetch from HTTPS aggressively   |
| SQLite path traversal          | DB path is hardcoded, not user-supplied                            |
| Prompt injection in job text   | LLM output validated against strict JSON schema; unexpected fields dropped |
| Document path traversal        | Files stored under a fixed `DOCS_DIR`; paths are never user-supplied |

---

## 11. Environment Variables

```bash
# .env

# Server
HOST=127.0.0.1          # Change to 0.0.0.0 to expose on LAN (not recommended)
PORT=8001

# Default LLM provider (can be overridden in settings UI)
LLM_PROVIDER=ollama     # ollama | openai | anthropic
OLLAMA_MODEL=llama3.2:3b
EMAIL_OLLAMA_MODEL=llama3.2:3b   # Model used specifically for email processing

# Optional cloud keys
OPENAI_API_KEY=
ANTHROPIC_API_KEY=

# Email sync
EMAIL_SYNC_INTERVAL=60  # minutes; set to 0 to disable background sync

# Document storage
DOCS_DIR=~/.job-tracker/docs    # Directory for stored document files

# Security
# MASTER_KEY is only used as fallback if OS keyring is unavailable
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
MASTER_KEY=
```

---

## 12. Dependencies

```toml
# pyproject.toml

[tool.poetry.dependencies]
python = "^3.10"
fastapi = "^0.115"
uvicorn = "^0.29"
httpx = "^0.27"
cryptography = "^42"        # Fernet for IMAP password encryption
keyring = "^25"             # OS keyring integration
imaplib2 = "^3.6"          # Async-friendly IMAP (optional; stdlib imaplib works too)
python-multipart = "^0.0.9" # File upload support
```

No new LLM dependencies: email processing reuses the existing Ollama provider.

---

## 13. Implementation Order

1. **Backend — document library** (`documents` table, `GET/POST /api/documents`, hash-dedup upload logic).
2. **Backend — job document endpoints** (`POST/DELETE /api/jobs/{id}/documents`, attach-from-library flow).
3. **Frontend — document library page** (`documents.html`): file list, usage counts, upload, detach/delete.
4. **Frontend — job detail document panel**: attach/detach UI, upload vs. library picker.
5. **Backend — email_accounts CRUD** (`POST/GET/DELETE /api/email/accounts`). UI: account list in settings.
6. **Backend — IMAP client** (`email_sync.py`): connect, fetch, keyword filter, insert `email_messages`.
7. **Backend — sync endpoint** (`POST /api/email/sync`): background task, status polling endpoint.
8. **Backend — LLM email processing** (`POST /api/email/process`): Ollama-only, streaming NDJSON response.
9. **Backend — auto-link logic**: match processed email to existing job row, update status on high confidence.
10. **Frontend — `email.html`**: message list, process button, sync status, manual link flow.
11. **Backend — bookmarklet endpoint** (`POST /api/parse-from-bookmarklet`) + CORS middleware.
12. **Frontend — settings bookmarklet section**: drag link, `__BASE_URL__` injection, port-change caveat.
13. **End-to-end tests**: work through acceptance checks for bookmarklet, email, and document features.
14. **README update**: email setup guide (Gmail App Password / IMAP enable steps), HOST/PORT vars, bookmark feature, document library usage.

---

## 14. Acceptance Checks

### Bookmarklet

1. Drag link from `/settings`. Click on `https://example.com` → toast: "✗ Empty page text".
2. Open any public careers page job posting → toast turns green → row appears in tracker.
3. Open a LinkedIn job posting (logged in) → toast turns green → bookmarklet-only path works.
4. Stop FastAPI server → toast: "✗ Tracker not reachable. Is the server running?".
5. Kill Ollama with Ollama as active provider → toast: "✗ ... Start Ollama with: ollama serve".
6. Bookmarklet-saved job has non-null `source_text` → ↻ Re-parse button is visible.
7. Set `PORT=9000`, restart, visit `http://127.0.0.1:9000/settings` → bookmarklet href contains port 9000.

### Document Library

1. Upload a CV PDF to job #1 → file appears in library with correct hash, size, and type.
2. Upload the same CV PDF to job #2 → no new file written to disk; `documents` row count unchanged; new `job_documents` link created.
3. Upload a different CV PDF → new file written to disk; `documents` row count increments.
4. "Attach from library" on job #3 → searchable picker shows existing documents → selecting one creates a link without file I/O.
5. Detach document from job #1 → `job_documents` row removed; file still on disk; still visible in library.
6. Attempt to delete a document still attached to job #2 → 409 response; ✕ button disabled in UI.
7. Detach from all jobs → ✕ button enables → delete succeeds → file removed from disk.
8. Migration script on old schema → documents deduplicated by hash → broken-link files flagged.

### Email

1. Add a Gmail account with App Password → account shows "✓ Connected" in settings.
2. Click "↻ Sync Now" → spinner shows → inbox scanned → "N new messages" count updates.
3. A rejection email from a known job appears in the Email tab tagged `[rejection]`.
4. Click "Process All" → spinner per row → matched job row status updates to `rejected`.
5. A rejection email with confidence < 0.85 → surfaced as "suggested update", not auto-applied.
6. Stop Ollama → "Process All" → error banner: "Ollama not reachable — email processing requires a local LLM".
7. No cloud request is made during email processing (verify with network monitor).
8. Remove email account → credentials purged from keyring.

---

## 15. Out of Scope

- OAuth2 / Gmail API (App Password + IMAP is sufficient and simpler for local use)
- Push notifications / webhooks from email providers
- Browser extension (bookmarklet ships first)
- Mobile app
- Multi-user / shared database
- HTTPS on the backend (Chrome/Firefox exempt localhost; adding HTTPS requires self-signed cert + trust setup)
- Safari support for the bookmarklet (fetch from HTTPS to HTTP blocked)
- Attachment parsing (PDFs of offer letters) — future task; document library is the prerequisite
