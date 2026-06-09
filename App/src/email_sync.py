import email as email_lib
import imaplib
import json
import re
import threading
from datetime import datetime, timezone
from typing import Optional
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from cryptography.fernet import Fernet

import db
from providers import get_provider
from providers.base import ProviderBadOutput, ProviderTimeout, ProviderUnavailable

EMAIL_SYSTEM_PROMPT = """\
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
}"""

RELEVANCE_KEYWORDS = [
    "application", "interview", "offer", "reject", "unfortunately",
    "congratulations", "position", "role", "hiring", "thank you for applying",
    "next steps", "assessment", "onboarding", "move forward",
]

# ── Encryption ────────────────────────────────────────────────────────────────

def encrypt_password(password: str) -> str:
    key = db.get_or_create_fernet_key()
    return Fernet(key).encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    key = db.get_or_create_fernet_key()
    return Fernet(key).decrypt(encrypted.encode()).decode()


# ── IMAP helpers ─────────────────────────────────────────────────────────────

def _decode_header_str(raw: str) -> str:
    parts = decode_header(raw or "")
    result = ""
    for part, charset in parts:
        if isinstance(part, bytes):
            result += part.decode(charset or "utf-8", errors="replace")
        else:
            result += str(part)
    return result


def _extract_plaintext(msg) -> str:
    if msg.is_multipart():
        parts = []
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    parts.append(
                        part.get_payload(decode=True).decode(
                            part.get_content_charset() or "utf-8", errors="replace"
                        )
                    )
                except Exception:
                    pass
        return "\n".join(parts)
    try:
        return msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", errors="replace"
        )
    except Exception:
        return ""


def is_relevant(subject: str, body: str, keywords=None) -> bool:
    kws = keywords if keywords else RELEVANCE_KEYWORDS
    text = ((subject or "") + " " + (body or "")[:500]).lower()
    return any((kw or "").lower() in text for kw in kws)


# ── Sync ──────────────────────────────────────────────────────────────────────

def _mailbox_name(list_line) -> str:
    """Pull the mailbox name out of an IMAP LIST response line."""
    line = list_line.decode(errors="replace") if isinstance(list_line, bytes) else str(list_line)
    quoted = re.findall(r'"([^"]*)"', line)
    if quoted:
        return quoted[-1]
    toks = line.split()
    return toks[-1] if toks else ""


def _quote_mailbox(name: str) -> str:
    """Quote a mailbox name for SELECT when it contains spaces/specials."""
    if name.startswith('"') and name.endswith('"'):
        return name
    return f'"{name}"' if (" " in name or "/" in name) else name


def find_sent_mailbox(conn_imap) -> Optional[str]:
    """Locate the account's Sent folder. Prefer the IMAP \\Sent special-use
    flag; fall back to common provider names (Gmail, Outlook, Dovecot, …)."""
    try:
        status, boxes = conn_imap.list()
        if status == "OK" and boxes:
            for raw in boxes:
                line = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
                if "\\Sent" in line:
                    name = _mailbox_name(raw)
                    if name:
                        return name
    except Exception:
        pass
    for cand in ("Sent", "Sent Items", "Sent Mail", "[Gmail]/Sent Mail", "INBOX.Sent"):
        try:
            status, _ = conn_imap.select(_quote_mailbox(cand), readonly=True)
            if status == "OK":
                return cand
        except Exception:
            continue
    return None


def _sync_mailbox(conn_imap, account: dict, mailbox: str, direction: str, uid_prefix: str) -> int:
    """Sync one IMAP mailbox into email_messages. `direction` is 'incoming' or
    'outgoing'; for outgoing mail the stored `sender` holds the recipient (the
    person we wrote to, e.g. a job's HR contact). Returns the new-message count."""
    try:
        status, _ = conn_imap.select(_quote_mailbox(mailbox), readonly=True)
        if status != "OK":
            return 0
    except Exception:
        return 0

    last_sync = account.get("last_sync_at")
    if last_sync:
        try:
            dt = datetime.fromisoformat(last_sync)
            since_str = dt.strftime("%d-%b-%Y")
            _, data = conn_imap.search(None, f"SINCE {since_str}")
        except Exception:
            _, data = conn_imap.search(None, "ALL")
    else:
        _, data = conn_imap.search(None, "ALL")

    uid_list = data[0].split() if data[0] else []

    # On the first ever sync cap to the 500 most-recent so we don't
    # download an entire mailbox in one shot.
    if not last_sync and len(uid_list) > 500:
        uid_list = uid_list[-500:]

    outgoing = direction == "outgoing"
    new_count = 0

    for uid_bytes in uid_list:
        uid_str = uid_prefix + uid_bytes.decode()
        if db.email_message_exists(account["id"], uid_str):
            continue

        _, msg_data = conn_imap.fetch(uid_bytes, "(BODY.PEEK[])")
        if not msg_data or not msg_data[0]:
            continue

        raw_bytes = msg_data[0][1]
        msg = email_lib.message_from_bytes(raw_bytes)

        subject = _decode_header_str(msg.get("Subject", "") or "")
        # For sent mail the meaningful party is the recipient, not ourselves.
        counterparty = _decode_header_str(msg.get("To" if outgoing else "From", "") or "")
        body = _extract_plaintext(msg)

        date_str = msg.get("Date", "")
        try:
            received_at = parsedate_to_datetime(date_str).isoformat()
        except Exception:
            received_at = datetime.now(timezone.utc).isoformat()

        created = db.create_email_message({
            "account_id": account["id"],
            "uid": uid_str,
            "subject": subject[:500],
            "sender": counterparty[:200],
            "received_at": received_at,
            "body_text": body[:12000],
            "direction": direction,
            # Sent mail isn't classified by the LLM; mark it relevant so it stays
            # out of the pending queue while still showing up and being linkable.
            "relevance": "relevant" if outgoing else "pending",
        })

        # Auto-link a sent email to the job whose HR address we wrote to.
        if outgoing and created:
            addr = parseaddr(counterparty)[1].lower()
            job = db.find_job_by_hr_email(addr) if addr else None
            if job:
                db.update_email_message(created["id"], {"linked_job_id": job["id"]})

        new_count += 1

    return new_count


def sync_account(account: dict) -> tuple[int, str]:
    """Sync one IMAP account (INBOX + Sent). Returns (new_count, error_or_empty)."""
    try:
        password = decrypt_password(account["password_enc"])
    except Exception as e:
        return 0, f"Failed to decrypt password: {e}"

    try:
        conn_imap = imaplib.IMAP4_SSL(account["imap_host"], int(account["imap_port"]))
        conn_imap.login(account["username"], password)
    except Exception as e:
        return 0, f"Connection failed: {e}"

    try:
        new_count = _sync_mailbox(conn_imap, account, "INBOX", "incoming", "")
        sent_mailbox = find_sent_mailbox(conn_imap)
        if sent_mailbox:
            new_count += _sync_mailbox(conn_imap, account, sent_mailbox, "outgoing", "sent-")

        conn_imap.logout()
        db.update_email_account_sync_time(account["id"])
        return new_count, ""
    except Exception as e:
        try:
            conn_imap.logout()
        except Exception:
            pass
        return 0, str(e)


def run_email_sync() -> dict:
    """Sync all active accounts. Called as a BackgroundTasks task."""
    accounts = db.list_email_accounts(active_only=True)
    total_new = 0
    errors = []
    for account in accounts:
        count, err = sync_account(account)
        total_new += count
        if err:
            errors.append({"account": account["label"], "error": err})
    return {"new_messages": total_new, "errors": errors}


# ── Single-flight sync guard (shared by manual trigger + auto scheduler) ───────
_sync_lock = threading.Lock()
_sync_running = False


def is_sync_running() -> bool:
    return _sync_running


def run_sync_guarded() -> Optional[dict]:
    """Run a sync unless one is already in progress. Returns None if skipped."""
    global _sync_running
    with _sync_lock:
        if _sync_running:
            return None
        _sync_running = True
    try:
        return run_email_sync()
    finally:
        with _sync_lock:
            _sync_running = False


# ── LLM processing ────────────────────────────────────────────────────────────

async def process_email_with_llm(msg: dict, model: str, provider_name: str = "ollama") -> dict:
    user_prompt = (
        f"Subject: {msg['subject']}\nFrom: {msg['sender']}\n\n"
        f"{(msg.get('body_text') or '')[:3000]}"
    )
    provider = get_provider(provider_name)
    raw = await provider.complete(EMAIL_SYSTEM_PROMPT, user_prompt, model)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ProviderBadOutput("Model returned invalid JSON for email")


STATUS_MAP = {
    "rejection": "rejected",
    "interview_invite": "interview_invite",
    "application_received": "applied",
}

# Final states we won't auto-change (e.g. an old "received" email must not
# un-reject a job). Emails still get linked to these jobs.
TERMINAL_STATUSES = {"rejected", "rejected_after_interview", "accepted"}


async def process_pending_emails(model: str, provider_name: str = "ollama"):
    """Async generator: process all pending emails, yield NDJSON event strings."""
    messages = db.list_email_messages(relevance="pending")
    keywords = db.get_email_settings().get("email_keywords") or RELEVANCE_KEYWORDS
    for msg in messages:
        try:
            now = datetime.now(timezone.utc).isoformat()

            # Cheap keyword pre-filter: skip the LLM for emails that match no
            # keyword and mark them irrelevant straight away (saves tokens/time).
            if not is_relevant(msg.get("subject", ""), msg.get("body_text", ""), keywords):
                db.update_email_message(msg["id"], {
                    "relevance": "irrelevant",
                    "processed_at": now,
                    "llm_raw": json.dumps({"skipped": "keyword_prefilter"}),
                })
                yield json.dumps({"id": msg["id"], "relevance": "irrelevant", "skipped": True}) + "\n"
                continue

            result = await process_email_with_llm(msg, model, provider_name)
            relevant = result.get("relevant", False)

            if not relevant:
                db.update_email_message(msg["id"], {
                    "relevance": "irrelevant",
                    "processed_at": now,
                    "llm_raw": json.dumps(result),
                })
                yield json.dumps({"id": msg["id"], "relevance": "irrelevant"}) + "\n"
                continue

            llm_status = result.get("status")
            confidence = float(result.get("confidence", 0.0))

            db.update_email_message(msg["id"], {
                "relevance": "relevant",
                "processed_at": now,
                "llm_status": llm_status,
                "llm_raw": json.dumps(result),
            })

            linked_job_id = None
            company = result.get("company") or ""
            position = result.get("position") or ""

            status_updated = False
            if company:
                matched = db.find_matching_job(company, position)
                if matched:
                    # Always link the email to its job so it shows up in jobs.
                    db.update_email_message(msg["id"], {"linked_job_id": matched["id"]})
                    linked_job_id = matched["id"]
                    # Only auto-change status when confident and the job isn't final.
                    if confidence >= 0.85 and matched.get("status") not in TERMINAL_STATUSES:
                        new_status = STATUS_MAP.get(llm_status)
                        if new_status:
                            db.update_job_status(matched["id"], new_status)
                            status_updated = True

            yield json.dumps({
                "id": msg["id"],
                "relevance": "relevant",
                "llm_status": llm_status,
                "confidence": confidence,
                "linked_job_id": linked_job_id,
                "company": company,
                "position": position,
                "notes": result.get("notes", ""),
                "auto_applied": status_updated,
            }) + "\n"

        except (ProviderUnavailable, ProviderTimeout, ProviderBadOutput) as e:
            db.update_email_message(msg["id"], {"relevance": "error"})
            yield json.dumps({"id": msg["id"], "error": str(e)}) + "\n"
            if isinstance(e, ProviderUnavailable):
                return
