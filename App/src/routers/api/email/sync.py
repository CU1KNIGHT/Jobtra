from fastapi import APIRouter
from fastapi import BackgroundTasks

import db
import email_sync

# ── Email sync ────────────────────────────────────────────────────────────────

_sync_running = False

router = APIRouter(tags=["email", "sync"])

@router.post("/api/email/sync")
def trigger_email_sync(background_tasks: BackgroundTasks):
    global _sync_running
    if _sync_running:
        return {"status": "already_running"}
    _sync_running = True

    def _run():
        global _sync_running
        try:
            email_sync.run_email_sync()
        finally:
            _sync_running = False

    background_tasks.add_task(_run)
    return {"status": "started"}


@router.get("/api/email/status")
def email_status():
    status = db.get_email_sync_status()
    status["sync_running"] = _sync_running
    return status