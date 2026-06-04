from fastapi import APIRouter
from fastapi import BackgroundTasks

import db
import email_sync

# ── Email sync ────────────────────────────────────────────────────────────────

router = APIRouter(tags=["email", "sync"])

@router.post("/api/email/sync")
def trigger_email_sync(background_tasks: BackgroundTasks):
    if email_sync.is_sync_running():
        return {"status": "already_running"}
    background_tasks.add_task(email_sync.run_sync_guarded)
    return {"status": "started"}


@router.get("/api/email/status")
def email_status():
    status = db.get_email_sync_status()
    status["sync_running"] = email_sync.is_sync_running()
    return status