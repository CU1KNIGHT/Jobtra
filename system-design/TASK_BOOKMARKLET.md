# Task: One-Click Save from Any Job Page (Bookmarklet)

Follow-up feature for the Job Application Tracker. Extends the existing app described in `DESIGN.md`. Read that first.

## Goal

Let the user save a job to the tracker with one click from *any* webpage — including logged-in sites like LinkedIn that can't be scraped server-side.

Mechanism: a JavaScript bookmarklet living in the user's browser bookmarks bar. When clicked on a job page, it reads the page's visible text, sends it to the tracker's backend with the page URL, the backend parses it with the active LLM provider, saves a new row, and shows a small confirmation toast on the page.

## Why this approach

LinkedIn, Xing, and similar sites can't be fetched server-side because they require login and render content with JavaScript. The backend's `httpx.get(url)` only sees an empty shell. The bookmarklet sidesteps this entirely: it runs **inside the user's already-logged-in tab**, so it can read whatever the user sees, then hands the text to the backend. No credentials, no scraping, no anti-bot games.

Tradeoff vs. the existing paste-and-parse flow: the bookmarklet **saves immediately, no preview**. The user fixes mistakes after the fact via the edit button. This is intentional — a preview step would mean opening a new tab, which defeats the one-click value proposition.

## User workflow

**One-time setup** (Settings page):

1. User opens `http://localhost:8001/settings`.
2. Sees a "Browser bookmark" section with a draggable link labeled "➕ Add to Job Tracker".
3. Shows their bookmarks bar (Ctrl+Shift+B / Cmd+Shift+B).
4. Drags the link onto the bookmarks bar.

**Daily use** (any job page):

1. User is on a LinkedIn / Indeed / StepStone / company careers page job posting.
2. Clicks the bookmark.
3. Toast appears bottom-right of the page: "✓ Saved: \<position\> at \<company\>". Fades after 2 seconds.
4. New row exists in the tracker. User can verify/edit it whenever.

On failure (backend down, parse error, etc.) the toast shows the error with the same hint strings the existing parse endpoint returns.

## Backend changes

### New endpoint

```
POST /api/parse-from-bookmarklet
```

Body:

```json
{
  "text": "<full visible text of the page>",
  "url": "<page URL>"
}
```

Behavior:

1. Validate `text` is non-empty. Reject with 400 otherwise.
2. Truncate `text` to ~12,000 characters (same cap as the URL fetcher uses).
3. Call the active provider's `parse(text, model)` using whatever's in the `settings` table.
4. Stamp `source_url = body.url` and `source_text = truncated_text` on the result.
5. Set defaults: `date_applied = today`, `status = "open"`.
6. **Save directly** by calling `db.create_job(parsed)` — do not return a preview.
7. Return the full saved `Job` (including the assigned `id`) with status 201.

Errors map to the same shape as `/api/parse`:

| Failure                   | HTTP | Body                                                                       |
| ------------------------- | ---- | -------------------------------------------------------------------------- |
| Empty text                | 400  | `{ "error": "Empty page text" }`                                           |
| `ProviderUnavailable`     | 503  | `{ "error": "...", "hint": "Start Ollama with: ollama serve" }`            |
| `ProviderAuthError`       | 401  | `{ "error": "Invalid or missing API key", "hint": "Add X_API_KEY to .env" }` |
| `ProviderBadOutput`       | 502  | `{ "error": "Model returned invalid JSON" }`                               |
| `ProviderTimeout`         | 504  | `{ "error": "Provider timed out" }`                                        |

### CORS configuration

The bookmarklet runs on third-party origins (`https://www.linkedin.com`, `https://stepstone.de`, etc.) and POSTs to `http://localhost:8001`. The browser blocks this by default.

Add CORS middleware in `server.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)
```

`allow_origins=["*"]` is fine because the app is local-only and has no auth — there's nothing to steal. No need to enumerate every job site.

### No schema change

The existing `source_url` and `source_text` columns added for re-parse already cover what the bookmarklet needs. Bookmarklet-created jobs get re-parse for free.

## Frontend changes

### Settings page addition

New section in `settings.html`, below the provider/model section:

```
┌─────────────────────────────────────────────────────────┐
│ Browser bookmark                                        │
│                                                         │
│ Drag this link to your bookmarks bar:                   │
│                                                         │
│           [➕ Add to Job Tracker]   <-- draggable        │
│                                                         │
│ Then visit any job page (LinkedIn, Indeed, a company    │
│ careers page, etc.) and click the bookmark. The job is  │
│ saved automatically to your tracker.                    │
│                                                         │
│ Show bookmarks bar: Ctrl+Shift+B (Windows/Linux) /      │
│ Cmd+Shift+B (Mac).                                      │
│                                                         │
│ Requires the tracker to be running at localhost:8001.   │
│ Tested in Chrome and Firefox. Safari may block it.      │
└─────────────────────────────────────────────────────────┘
```

The link's `href` is the URL-encoded bookmarklet code. Its display text shows what becomes the bookmark name.

### The bookmarklet code

The bookmarklet must hit the same host:port the backend is running on. Don't hardcode `localhost:8001`. The Settings page injects the configured `BASE_URL` into the JS at render time.

Source (write this readable, then minify and URL-encode for the `href`):

```javascript
(async () => {
  const text = document.body.innerText;
  const url = location.href;

  // Small inline toast
  const toast = document.createElement('div');
  toast.style.cssText = `
    position: fixed; bottom: 20px; right: 20px; z-index: 999999;
    background: #222; color: #fff; padding: 12px 16px;
    border-radius: 6px; font: 14px system-ui, sans-serif;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3); max-width: 320px;
  `;
  toast.textContent = 'Saving to tracker...';
  document.body.appendChild(toast);

  try {
    // __BASE_URL__ is replaced at render time with e.g. "http://127.0.0.1:8001"
    const r = await fetch('__BASE_URL__/api/parse-from-bookmarklet', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, url })
    });
    const data = await r.json();
    if (!r.ok) {
      const hint = data.hint ? ` (${data.hint})` : '';
      toast.textContent = `✗ ${data.error || 'Save failed'}${hint}`;
      toast.style.background = '#a00';
    } else {
      toast.textContent = `✓ Saved: ${data.position} at ${data.company}`;
      toast.style.background = '#060';
    }
  } catch (e) {
    toast.textContent = `✗ Tracker not reachable. Is the server running?`;
    toast.style.background = '#a00';
  }

  setTimeout(() => toast.remove(), 3000);
})();
```

To turn this into the bookmarklet href:

1. Substitute `__BASE_URL__` with the actual base URL the backend is serving on (e.g. `http://127.0.0.1:8001`).
2. Strip comments and minify (or keep as-is — bookmarks have generous size limits).
3. URL-encode the whole thing.
4. Prefix with `javascript:`.
5. Use that as the `href` of an `<a>` tag with `draggable="true"`.

Two options for the substitution:

**Option A — server-side template** (recommended). `settings.html` is served by a route that templates `BASE_URL` into the page before returning it. Simplest is to read the HTML file, do a string replace, return as `HTMLResponse`. Or use Jinja2 if it's already in the project (it isn't, so don't add it just for this).

**Option B — client-side build**. Settings page hits a small new endpoint `GET /api/config` returning `{ base_url: "http://127.0.0.1:8001" }`, then JS builds the bookmarklet `href` from that. One extra request but keeps `settings.html` as a static file.

Pick Option A for fewer moving parts.

```python
# In server.py
import os
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8001"))
BASE_URL = f"http://{HOST}:{PORT}"

@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    html = Path("settings.html").read_text()
    return html.replace("__BASE_URL__", BASE_URL)
```

In `settings.html` the bookmarklet link references the template marker, and the inline script substitutes it before assigning to `href`:

```html
<a id="bookmarklet" draggable="true">➕ Add to Job Tracker</a>

<script>
  const BASE_URL = "__BASE_URL__";  // replaced server-side
  const code = `(async () => { /* ... bookmarklet code with __BASE_URL__ ... */ })();`
    .replaceAll("__BASE_URL__", BASE_URL);
  document.getElementById('bookmarklet').href =
    'javascript:' + encodeURIComponent(code);
</script>
```

### Port-change caveat (document on the Settings page)

The bookmarklet snapshots the URL at the moment it's dragged to the bookmarks bar. If the user later changes `PORT` in `.env`, **existing bookmarks will keep calling the old port** and fail silently with "Tracker not reachable."

Add an inline note in the Settings page under the bookmark section:

```
Note: this bookmark calls http://127.0.0.1:8001. If you change the
PORT in .env later, re-drag this bookmark to update it.
```

The base URL in the note should be templated too — show the user the actual URL it points to.

## Acceptance checks

1. **Setup**: Drag the link from `/settings` to bookmarks bar. Click it on `https://example.com` — toast says "Saving..." then "✗ Empty page text" (because example.com has minimal text). Confirms the wiring works end-to-end.
2. **Real job, public site**: Open any company careers page job posting. Click bookmark. Toast turns green with the job title and company. Refresh the tracker → new row at the top.
3. **Real job, LinkedIn**: While logged into LinkedIn, open a job posting. Click bookmark. Toast turns green. The previously-failing URL-paste flow on the same job should still fail with "Site may require login" — only the bookmarklet path works for LinkedIn.
4. **Backend down**: Stop the FastAPI server. Click bookmark on a job page. Toast says "✗ Tracker not reachable. Is the server running?". Restart server, click again, works.
5. **Provider down**: Server running, but Ollama killed (and Ollama is the active provider). Click bookmark. Toast says "✗ ... Start Ollama with: ollama serve".
6. **Re-parse compatibility**: A bookmarklet-saved job has non-empty `source_url` and `source_text`. The "↻ Re-parse" button is visible on that row.
7. **Custom port**: Set `PORT=9000` in `.env`, restart server, visit `http://127.0.0.1:9000/settings`. The bookmarklet's href contains `127.0.0.1:9000`, the note below it shows the right URL, and re-dragging + clicking from a job page works against port 9000.

## Out of scope (explicitly)

- **No preview before save.** That's the design. To edit, use the existing edit button on the row.
- **No site-specific extractors.** `document.body.innerText` works on everything; the LLM tolerates the noise. If quality becomes a problem on LinkedIn specifically, a future task can add `if (location.hostname === 'www.linkedin.com') text = document.querySelector('.job-view-layout')?.innerText || text;`.
- **No browser extension.** That's a different feature with install friction. The bookmarklet ships first; if it's heavily used, a packaged extension is the upgrade path.
- **No Safari support.** Safari blocks `fetch` from HTTPS pages to `http://localhost` more aggressively than Chrome/Firefox. Document this; don't try to work around it.
- **No HTTPS for the backend.** Chrome and Firefox carve out `http://localhost` from mixed-content blocking, so the plain HTTP backend works. Adding HTTPS would require a self-signed cert and trust setup — not worth it for a local app.

## README update

Add a short section: "Save jobs with one click — see the Settings page for the browser bookmark."

## Implementation order

1. Read `HOST` and `PORT` from env in `server.py`, define `BASE_URL`.
2. Add CORS middleware to `server.py`.
3. Add `POST /api/parse-from-bookmarklet` to `server.py` (reuses existing provider chain and `db.create_job`).
4. Change `GET /settings` to read `settings.html` and substitute `__BASE_URL__` before returning.
5. Add the bookmark section to `settings.html`, including the port-change note that shows the actual base URL.
6. Manually run through the seven acceptance checks above.
7. Update `README.md` to mention `HOST`/`PORT` env vars and the bookmark feature.
