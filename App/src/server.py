from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import UI_DIR
from routers import navigation
from routers.api import bookmarklet, config, job, models, parse, settings as api_settings
from routers.api.document import document
from routers.api.email import messages, sync, settings as email_settings, accounts

app = FastAPI(title="Job Application Tracker")
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

app.mount("/static", StaticFiles(directory=UI_DIR), name="static")
