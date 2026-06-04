# Job Application Tracker — Product Requirements Document (PRD)

> What the product is and what it should do, from a user/product perspective.
> For detailed per-feature behavior, data model, and API surface see
> [`functional-spec.md`](./functional-spec.md).

---

## 1. Overview

The Job Application Tracker is a single-user, self-hosted web app for managing a
job search end-to-end. It keeps a structured list of applications, uses an LLM to
turn raw job postings into structured records, stores related documents (CVs,
cover letters, certificates), and connects to the user's email inbox to detect
and classify application-related messages (rejections, interview invites, offers)
and link them back to the relevant job.

- **Deployment model:** runs locally; FastAPI backend + SQLite, plain HTML/JS frontend, no build step.
- **AI providers:** pluggable — Ollama (local), Anthropic, or OpenAI.
- **Primary user:** an individual job seeker tracking their own applications.

---

## 2. Goals & Non-goals

### 2.1 Goals
- Replace ad-hoc spreadsheets with a structured, searchable application list.
- Minimize manual data entry via AI parsing of postings (paste, URL, or browser bookmarklet) and bulk import.
- Surface status changes automatically by reading the user's email.
- Keep all data local and under the user's control.

### 2.2 Non-goals
- Multi-user / multi-tenant accounts, authentication, or roles.
- Sending email or applying to jobs on the user's behalf.
- A hosted/cloud SaaS offering.
- Mobile-native apps (the web UI is responsive but browser-based).

---

## 3. Personas

| Persona | Needs |
|---|---|
| **Active job seeker** | Track many applications, see status at a glance, avoid retyping posting details, never lose track of which company an email refers to. |
| **Privacy-conscious user** | Keep data on their own machine; choose a local LLM (Ollama) so postings/emails aren't sent to a third party. |

---

## 4. Feature requirements

Each capability below is described at the product level — *what* it provides.
The exact mechanics (validation rules, thresholds, mappings, endpoints) are in
the Functional Specification.

### 4.1 Job tracking
The home view is a table of all applications with at-a-glance status, search, and
status filtering. Users can add, edit, delete, and expand jobs to see full detail,
and open a standalone page per job. Applications move through a fixed set of
statuses: open, applied, interview done, rejected, rejected after interview, accepted.

### 4.2 AI parsing of postings
Users can create a structured job record from an unstructured posting without
manual typing — by pasting text, supplying a URL (fetched server-side), or using a
one-click **browser bookmarklet** that captures the visible text of any job page
(including sites where the user is logged in). The original source is stored so a
job can later be **re-parsed** without losing its date or status.

### 4.3 Import & export
Users can export the current (filtered) job list to CSV, and **bulk-import** jobs
from a CSV or JSON file exported from another tool. Import is tolerant of foreign
schemas: alternative column names and status vocabularies (English and German) are
mapped automatically, duplicates are skipped, and bad rows are reported without
aborting the whole import.

### 4.4 Document library
A reusable library of files (CVs, cover letters, certificates, portfolios) that can
be attached to multiple jobs. Identical files are de-duplicated. Documents can be
attached/detached per job, downloaded, and deleted — with deletion blocked while a
document is still in use by any job.

### 4.5 Email integration
Users connect IMAP email accounts; the app syncs messages and uses the LLM to
detect application-related emails and classify them (rejection, interview invite,
offer, received). Relevant emails are **linked to the matching job automatically**,
and a job's status is **advanced automatically** when the classification is
confident enough and the job isn't already finalized. Users can also link, change,
unlink, and re-process messages manually, and browse/filter their inbox by relevance.

### 4.6 AI provider settings
Users choose which provider (Ollama / Anthropic / OpenAI) and model powers parsing
and email classification, see whether the required API key is present, list
available models, and run a test parse. The drag-to-install bookmarklet is provided
here.

### 4.7 Experience
A consistent, collapsible left sidebar provides navigation across Jobs, Email, and
Documents; page-specific actions live in each page's header. Light/dark theme and
sidebar state persist across sessions, and the layout adapts to narrow screens.

---

## 5. Constraints & assumptions

- **Single user, local-first.** No authentication; the app trusts whoever can reach it.
- **Privacy by choice of provider.** With Ollama, postings and emails stay on the machine; with Anthropic/OpenAI they are sent to that provider for parsing/classification.
- **AI quality varies by model.** Parsing accuracy and email classification/confidence depend on the selected model.
- **Email sync is user-triggered.** There is no always-on background scheduler in the current flow.
- **Data portability.** All data lives in a single SQLite file plus a documents directory; backup is a file copy.

---

## 6. Success criteria

- A user can capture a posting into a structured record in one action (paste / URL / bookmarklet) rather than manual entry.
- Imported data from another tracker lands with correct fields and statuses without manual cleanup of common variations.
- After syncing email, application-related messages are correctly linked to their jobs, and obvious status changes (e.g. a rejection) are reflected without manual editing.
- All of the above works against a local model with no data leaving the machine.
