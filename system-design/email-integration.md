# Email Integration (IONOS / 1&1 Webmail)

Personal Python project to integrate a 1&1 IONOS mailbox into a local app —
fetch messages over IMAP, parse them, and send mail over SMTP.

## Goals

- Fetch emails from a 1&1 IONOS mailbox into the local app
- Parse subject, sender, body (plain + HTML), and attachments
- Send emails from the same account via SMTP
- Keep credentials out of the source tree

## Tech stack

- **Language:** Python 3.11+
- **IMAP:** [`imap-tools`](https://pypi.org/project/imap-tools/) (wrapper around stdlib `imaplib`)
- **SMTP:** stdlib `smtplib` + `email.message.EmailMessage`
- **HTML cleanup:** `beautifulsoup4`
- **Env / secrets:** `python-dotenv`
- **Env manager:** `uv`
- **IDE:** PyCharm Professional (free via JetBrains open-source license)

## Server settings (IONOS)

| Direction | Host             | Port | Security  |
| --------- | ---------------- | ---- | --------- |
| IMAP      | `imap.ionos.com` | 993  | SSL/TLS   |
| SMTP      | `smtp.ionos.com` | 465  | SSL/TLS   |
| SMTP alt  | `smtp.ionos.com` | 587  | STARTTLS  |

- Username = full email address
- Password = mailbox password (use an **app-specific password** if 2FA is on the IONOS account)

## Project layout

```
email-app/
├── .env                  # MAIL_USER, MAIL_PASSWORD (gitignored)
├── .env.example
├── pyproject.toml
├── README.md
└── src/
    ├── __init__.py
    ├── config.py         # load env vars
    ├── fetcher.py        # IMAP fetch + parse
    ├── sender.py         # SMTP send
    └── main.py           # entry point
```

## Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    "imap-tools>=1.6",
    "beautifulsoup4>=4.12",
    "python-dotenv>=1.0",
]
```

Install:

```bash
uv venv
uv pip install -e .
```

## Fetching (IMAP)

```python
from imap_tools import MailBox, AND

with MailBox("imap.ionos.com").login(USER, PASSWORD, initial_folder="INBOX") as mb:
    for msg in mb.fetch(AND(seen=False), limit=20, mark_seen=False):
        print(msg.subject, msg.from_, msg.date)
        body = msg.text or msg.html
        for att in msg.attachments:
            print(att.filename, att.content_type, len(att.payload))
```

## Sending (SMTP)

```python
import smtplib
from email.message import EmailMessage

msg = EmailMessage()
msg["Subject"] = "Hello"
msg["From"] = USER
msg["To"] = "recipient@example.com"
msg.set_content("Plain text body")
msg.add_alternative("<p>HTML body</p>", subtype="html")

with smtplib.SMTP("smtp.ionos.com", 587) as s:
    s.starttls()
    s.login(USER, PASSWORD)
    s.send_message(msg)
```

## Things to watch out for

- **MIME edge cases** — multipart/alternative vs multipart/mixed, nested parts,
  charset detection. `imap-tools` handles most of this; don't roll your own
  parser.
- **Incremental sync** — track UIDs locally, or use `mb.idle.wait()` for
  push-style updates (IMAP IDLE).
- **HTML sanitization** — run incoming HTML through BeautifulSoup before
  rendering or storing.
- **Quoted-reply stripping** — separating new content from `"On X wrote:"`
  history is non-trivial; consider `mail-parser` or `EmailReplyParser` if
  needed.
- **Rate limits** — IONOS limits SMTP send rate (a few hundred/hour on
  standard mail plans). Fine for personal use, plan around it if scaling.
- **Secrets** — never hardcode passwords; load from `.env` and gitignore it.

## Open questions / next steps

- [ ] Storage backend for parsed mail (SQLite vs Postgres?)
- [ ] Sync strategy: poll every N minutes vs IMAP IDLE
- [ ] UI? CLI first, optional FastAPI + web frontend later
- [ ] Attachment storage: filesystem + DB reference, or BLOB in DB?
- [ ] LLM-powered classification / summarization (Anthropic API)?
