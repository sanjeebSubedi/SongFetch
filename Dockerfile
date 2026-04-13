FROM python:3.12-slim-bookworm

ARG UID=1000
ARG GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/appuser

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    chromium \
    chromium-driver \
    curl \
    ffmpeg \
    nodejs \
    npm \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

RUN python -m pip install --upgrade pip \
 && python -m pip install -e . \
 && groupadd --gid "${GID}" appuser \
 && useradd --uid "${UID}" --gid "${GID}" --create-home --shell /bin/bash appuser \
 && mkdir -p /app/downloads \
 && chown -R appuser:appuser /app /home/appuser

USER appuser

ENTRYPOINT ["python", "main.py"]
