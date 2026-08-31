# Telegram Downloader Bot

A modular Telegram media downloader built around yt-dlp and an S3-compatible object-storage adapter.

## Flow

1. User sends an HTTP(S) media URL.
2. yt-dlp extracts metadata and available video formats without downloading.
3. The bot presents detected video heights as inline buttons.
4. The selected format is downloaded to temporary/local storage.
5. The resulting file is uploaded through the S3-compatible storage adapter.
6. The bot returns a presigned download URL.

## Setup

Requires Python 3.11+ and FFmpeg.

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install .
copy .env.example .env
```

Fill `TELEGRAM_BOT_TOKEN` and the storage credentials in `.env`, then:

```bash
python -m app.main
```

## Storage

The storage adapter uses the S3 API, so an S3-compatible provider can be configured with endpoint, bucket, access key and secret key. Keep credentials only in environment variables; never commit `.env`.

## Notes

Format availability is source-dependent. DRM-protected, login-only, geo-restricted, or otherwise inaccessible media may not be downloadable. The bot does not attempt to bypass DRM or access controls. Use it only for content you are authorized to download.
