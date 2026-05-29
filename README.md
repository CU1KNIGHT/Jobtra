# Job Application Tracker

A minimal web app to track job applications. CRUD on a SQLite-backed list, served by FastAPI with a plain HTML/JS frontend.

## Setup & run

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn server:app --reload
# open http://localhost:8000
```

Optional: copy `.env.example` to `.env` and set `HOST`, `PORT`, or API keys:

```
HOST=127.0.0.1
PORT=8000
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

## Save jobs with one click

See the Settings page (`http://localhost:8000/settings`) for a browser bookmark you can drag to your bookmarks bar. Clicking it on any job page (including LinkedIn while logged in) sends the visible text to the tracker and saves the job automatically — no copy-pasting needed.

## Notes

- `jobs.db` is created automatically on first run. Back up by copying the file. Reset by deleting it.
- API docs available at `http://localhost:8000/docs`.
- If you change `PORT` in `.env`, re-drag the bookmark from the Settings page to update it.
