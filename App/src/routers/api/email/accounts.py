from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
import email_sync

# ── Email accounts ────────────────────────────────────────────────────────────
router = APIRouter(tags=["email", "account"])

class EmailAccountInput(BaseModel):
    label: str
    imap_host: str
    imap_port: int = 993
    username: str
    password: Optional[str] = None
    active: int = 1


@router.get("/api/email/accounts")
def list_email_accounts():
    accounts = db.list_email_accounts()
    return [_safe_account(a) for a in accounts]


@router.post("/api/email/accounts", status_code=201)
def create_email_account(payload: EmailAccountInput):
    if not payload.password:
        raise HTTPException(400, "Password is required when creating an account")
    password_enc = email_sync.encrypt_password(payload.password)
    account = db.create_email_account({
        "label": payload.label,
        "imap_host": payload.imap_host,
        "imap_port": payload.imap_port,
        "username": payload.username,
        "password_enc": password_enc,
        "active": payload.active,
    })
    return _safe_account(account)


@router.put("/api/email/accounts/{account_id}")
def update_email_account(account_id: int, payload: EmailAccountInput):
    if db.get_email_account(account_id) is None:
        raise HTTPException(404, "Account not found")
    account = db.update_email_account(account_id, payload.model_dump(exclude={"password"}))
    if payload.password:
        db.update_email_account_password(account_id, email_sync.encrypt_password(payload.password))
    return _safe_account(account)


@router.delete("/api/email/accounts/{account_id}", status_code=204)
def delete_email_account(account_id: int):
    if not db.delete_email_account(account_id):
        raise HTTPException(404, "Account not found")


@router.post("/api/email/accounts/{account_id}/reset-sync", status_code=204)
def reset_account_sync(account_id: int):
    if db.get_email_account(account_id) is None:
        raise HTTPException(404, "Account not found")
    db.reset_email_account_sync_time(account_id)


def _safe_account(a: dict) -> dict:
    return {k: v for k, v in a.items() if k != "password_enc"}
