import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import db
import email_sync
from config import UI_DIR
from routers import navigation
from routers.api import bookmarklet, config, dashboard, job, models, parse, settings as api_settings
from routers.api.document import document
from routers.api.email import messages, sync, settings as email_settings, accounts


async def _auto_sync_loop():
    """Periodically sync active email accounts every email_sync_interval minutes."""
    while True:
        try:
            interval = int(db.get_email_settings().get("email_sync_interval") or 60)
        except Exception:
            interval = 60
        await asyncio.sleep(max(5, interval) * 60)  # floor at 5 minutes
        try:
            if db.list_email_accounts(active_only=True) and not email_sync.is_sync_running():
                await asyncio.to_thread(email_sync.run_sync_guarded)
        except Exception:
            pass  # never let a sync error kill the scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_auto_sync_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="Jobtra", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
    allow_private_network=True,
)
app.include_router(messages.router)
app.include_router(email_settings.router)
app.include_router(sync.router)
app.include_router(document.router)
app.include_router(navigation.router)
app.include_router(config.router)
app.include_router(parse.router)
app.include_router(bookmarklet.router)
app.include_router(job.router)
app.include_router(api_settings.router)
app.include_router(models.router)
app.include_router(accounts.router)
app.include_router(dashboard.router)

app.mount("/static", StaticFiles(directory=UI_DIR), name="static")
