import email as email_lib
import imaplib
import json
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
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


def is_relevant(subject: str, body: str) -> bool:
    text = ((subject or "") + " " + (body or "")[:500]).lower()
    return any(kw in text for kw in RELEVANCE_KEYWORDS)


# ── Sync ──────────────────────────────────────────────────────────────────────

def sync_account(account: dict) -> tuple[int, str]:
    """Sync one IMAP account synchronously. Returns (new_count, error_or_empty)."""
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
        conn_imap.select("INBOX")
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
        # download an entire inbox in one shot.
        if not last_sync and len(uid_list) > 500:
            uid_list = uid_list[-500:]

        new_count = 0

        for uid_bytes in uid_list:
            uid_str = uid_bytes.decode()
            if db.email_message_exists(account["id"], uid_str):
                continue

            _, msg_data = conn_imap.fetch(uid_bytes, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue

            raw_bytes = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw_bytes)

            subject = _decode_header_str(msg.get("Subject", "") or "")
            sender = msg.get("From", "") or ""
            body = _extract_plaintext(msg)

            date_str = msg.get("Date", "")
            try:
                received_at = parsedate_to_datetime(date_str).isoformat()
            except Exception:
                received_at = datetime.now(timezone.utc).isoformat()

            db.create_email_message({
                "account_id": account["id"],
                "uid": uid_str,
                "subject": subject[:500],
                "sender": sender[:200],
                "received_at": received_at,
                "body_text": body[:12000],
                "relevance": "pending",
            })
            new_count += 1

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
    "interview_invite": "interview_done",
    "application_received": "applied",
}


async def process_pending_emails(model: str, provider_name: str = "ollama"):
    """Async generator: process all pending emails, yield NDJSON event strings."""
    messages = db.list_email_messages(relevance="pending")
    for msg in messages:
        try:
            result = await process_email_with_llm(msg, model, provider_name)
            relevant = result.get("relevant", False)
            now = datetime.now(timezone.utc).isoformat()

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

            if company:
                matched = db.find_matching_job(company, position)
                if matched:
                    if confidence >= 0.85:
                        new_status = STATUS_MAP.get(llm_status)
                        if new_status:
                            db.update_job_status(matched["id"], new_status)
                        db.update_email_message(msg["id"], {"linked_job_id": matched["id"]})
                        linked_job_id = matched["id"]

            yield json.dumps({
                "id": msg["id"],
                "relevance": "relevant",
                "llm_status": llm_status,
                "confidence": confidence,
                "linked_job_id": linked_job_id,
                "company": company,
                "position": position,
                "notes": result.get("notes", ""),
                "auto_applied": linked_job_id is not None and confidence >= 0.85,
            }) + "\n"

        except (ProviderUnavailable, ProviderTimeout, ProviderBadOutput) as e:
            db.update_email_message(msg["id"], {"relevance": "error"})
            yield json.dumps({"id": msg["id"], "error": str(e)}) + "\n"
            if isinstance(e, ProviderUnavailable):
                return
