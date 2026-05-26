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

## Notes

- `jobs.db` is created automatically on first run. Back up by copying the file. Reset by deleting it.
- API docs available at `http://localhost:8000/docs`.
