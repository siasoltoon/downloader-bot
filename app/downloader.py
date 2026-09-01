import logging
import time
from pathlib import Path
from urllib.parse import urlsplit

import yt_dlp

from app.formats import collect_formats

log = logging.getLogger(__name__)


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "unknown").lower()
    except ValueError:
        return "invalid"


class Downloader:
    def __init__(self, download_dir: Path, temp_dir: Path):
        self.download_dir = download_dir
        self.temp_dir = temp_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def inspect(self, url: str) -> dict:
        started = time.monotonic()
        host = _host(url)
        log.info("extract:start host=%s", host)
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            formats = collect_formats(info)
            log.info(
                "extract:success host=%s extractor=%s title=%r formats=%d duration=%s elapsed=%.2fs",
                host,
                info.get("extractor_key") or info.get("extractor") or "unknown",
                (info.get("title") or "Untitled")[:160],
                len(formats),
                info.get("duration"),
                time.monotonic() - started,
            )
            return {
                "title": info.get("title") or "Untitled",
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "extractor": info.get("extractor_key") or info.get("extractor"),
                "webpage_url": info.get("webpage_url") or url,
                "formats": formats,
            }
        except Exception:
            log.exception("extract:failed host=%s elapsed=%.2fs", host, time.monotonic() - started)
            raise

    def download(self, url: str, format_expression: str, job_id: int, progress_hook=None) -> Path:
        started = time.monotonic()
        host = _host(url)
        log.info("download:start job=%s host=%s format=%s", job_id, host, format_expression)
        template = str(self.download_dir / f"{job_id}-%(title).120s.%(ext)s")
        opts = {
            "format": format_expression,
            "outtmpl": template,
            "noplaylist": True,
            "restrictfilenames": True,
            "merge_output_format": "mp4",
            "paths": {"home": str(self.download_dir), "temp": str(self.temp_dir)},
            "retries": 3,
            "fragment_retries": 3,
            "continuedl": True,
            "overwrites": False,
            "quiet": True,
            "no_warnings": True,
        }
        if progress_hook:
            opts["progress_hooks"] = [progress_hook]
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            matches = sorted(
                self.download_dir.glob(f"{job_id}-*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not matches:
                raise RuntimeError("Download completed but output file was not found")
            path = matches[0]
            log.info(
                "download:success job=%s file=%s size=%d elapsed=%.2fs",
                job_id,
                path.name,
                path.stat().st_size,
                time.monotonic() - started,
            )
            return path
        except Exception:
            log.exception("download:failed job=%s host=%s elapsed=%.2fs", job_id, host, time.monotonic() - started)
            raise
