# Telegram Downloader Bot

A modular Telegram media downloader for URLs supported by yt-dlp, with selectable source formats and S3-compatible object storage.

## Architecture

`Telegram → URL validation → yt-dlp inspection → format selection → persistent SQLite job queue → worker → local/temporary file → S3-compatible storage → download URL`

The bot does not bypass DRM, authentication, geo restrictions, or other access controls. Use it only with media you are authorized to download.

## Features

- Automatic yt-dlp extractor selection.
- Metadata and available video formats inspected before download.
- Quality buttons generated from formats actually exposed by the source.
- Video-only formats can be paired with the best available audio stream.
- Persistent SQLite job records with recovery after process restart.
- Configurable worker concurrency and per-user active-job limits.
- Retry and continued-download options delegated to yt-dlp.
- FFmpeg support for merging and post-processing.
- S3-compatible upload adapter with optional public URL or presigned URL.
- Local-file cleanup after successful upload.
- Docker image with FFmpeg included.
- Ruff + pytest + Docker build validation in GitHub Actions.

## Setup

Python 3.11+ and FFmpeg are required for local execution.

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# Linux/macOS
# source .venv/bin/activate
pip install '.[dev]'
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/macOS
```

Set `TELEGRAM_BOT_TOKEN` and all required storage variables in `.env`.

```bash
python -m app.main
```

## Docker

```bash
docker build -t downloader-bot .
docker run --env-file .env -v downloader-data:/app/data -v downloader-downloads:/app/downloads -v downloader-tmp:/app/tmp downloader-bot
```

## Storage

`app/storage.py` uses the S3 API. Configure endpoint, bucket, credentials and expiration through environment variables. If `STORAGE_PUBLIC_BASE_URL` is set, the bot returns that object's public URL; otherwise it creates a presigned `GetObject` URL.

## Job lifecycle

`inspecting → pending → queued → downloading → uploading → completed`

Failures are recorded as `failed`. Jobs interrupted while downloading/uploading are returned to `queued` on restart so the worker can retry them.

## Testing

```bash
pytest -q
ruff check app tests
```

CI runs both commands and builds the Docker image.
