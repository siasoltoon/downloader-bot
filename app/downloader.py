import logging
import time
from pathlib import Path
from urllib.parse import urlsplit

import yt_dlp

from app.config import settings
from app.cookies import validate_netscape_cookie_file
from app.formats import collect_formats

log = logging.getLogger(__name__)


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "unknown").lower().removeprefix("www.")
    except ValueError:
        return "invalid"


def _is_finished_file(path: Path) -> bool:
    return path.is_file() and not path.name.endswith((".part", ".ytdl", ".tmp"))


def _cookie_file_for_host(host: str) -> Path | None:
    """Return the site-specific Netscape cookie file for a hostname, if present."""
    if not host or host in {"unknown", "invalid"}:
        return None

    parts = host.split(".")
    candidates = []
    for index in range(len(parts) - 1):
        candidates.append(".".join(parts[index:]))

    for domain in candidates:
        path = settings.cookies_dir / f"{domain}.txt"
        if path.is_file():
            return path
    return None


def _yt_dlp_opts(host: str) -> dict:
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
    cookie_file = _cookie_file_for_host(host)
    if cookie_file:
        valid, reason, count = validate_netscape_cookie_file(cookie_file)
        if valid:
            opts["cookiefile"] = str(cookie_file)
            log.info(
                "cookies:enabled host=%s file=%s cookies=%d format=netscape",
                host,
                cookie_file.name,
                count,
            )
        else:
            log.warning(
                "cookies:invalid host=%s file=%s reason=%s cookies=%d",
                host,
                cookie_file.name,
                reason,
                count,
            )
    else:
        log.info("cookies:not_found host=%s", host)
    return opts


class Downloader:
    def __init__(self, download_dir: Path, temp_dir: Path):
        self.download_dir = download_dir
        self.temp_dir = temp_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        settings.cookies_dir.mkdir(parents=True, exist_ok=True)

    def inspect(self, url: str) -> dict:
        started = time.monotonic()
        host = _host(url)
        log.info("extract:start host=%s", host)
        opts = _yt_dlp_opts(host)
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
        job_dir = self.download_dir / str(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        template = str(job_dir / "%(title).120s.%(ext)s")
        opts = _yt_dlp_opts(host)
        opts.update({
            "format": format_expression,
            "outtmpl": template,
            "noplaylist": True,
            "restrictfilenames": True,
            "merge_output_format": "mp4",
            "paths": {"home": str(job_dir), "temp": str(self.temp_dir)},
            "retries": 3,
            "fragment_retries": 3,
            "continuedl": True,
            "overwrites": False,
        })
        if progress_hook:
            opts["progress_hooks"] = [progress_hook]
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            matches = [p for p in job_dir.rglob("*") if _is_finished_file(p)]
            if not matches:
                matches = [p for p in self.download_dir.rglob(f"{job_id}-*") if _is_finished_file(p)]
            if not matches:
                log.error(
                    "download:output_missing job=%s job_dir=%s files=%s temp_files=%s",
                    job_id,
                    job_dir,
                    [p.name for p in job_dir.rglob("*")],
                    [p.name for p in self.temp_dir.glob("*") if p.is_file()][:20],
                )
                raise RuntimeError("Download completed but output file was not found")
            path = max(matches, key=lambda p: p.stat().st_mtime)
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
