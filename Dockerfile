# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Port is sourced from .env (passed in as a build arg by docker compose); the
# 8001 here is only a bootstrap default for a bare `docker build` with no arg.
ARG PORT=8001

# Install dependencies first so this layer is cached across code changes.
COPY App/requirements.txt ./App/requirements.txt
RUN pip install --no-cache-dir -r App/requirements.txt

# Application code, static UI, and the version file (read at startup).
COPY App/src ./App/src
COPY ui ./ui
COPY VERSION ./VERSION

# Persist all mutable state on a mounted volume, outside the source tree.
# HOST is the address users type in the browser (used for the bookmarklet link);
# it is independent of the 0.0.0.0 bind below. Override HOST with your LAN IP /
# hostname if you access the app from another machine.
ENV DB_PATH=/data/jobs.db \
    SECRET_KEY_PATH=/data/secret.key \
    DOCS_DIR=/data/docs \
    HOST=localhost \
    PORT=${PORT}
VOLUME ["/data"]

# Run from App/src so the app's bare imports (import db, from config import ...)
# resolve, matching the local-dev layout.
WORKDIR /app/App/src
EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
