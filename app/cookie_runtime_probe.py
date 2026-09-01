"""Safe cookie runtime probe for yt-dlp.

This diagnostic performs a metadata-only yt-dlp request (download=False), using
only the configured site-specific cookie file. It never prints cookie names or
values and never downloads media or writes output files.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

from app.config import settings
from app.downloader import _cookie_file_for_host, _yt_dlp_opts
from app.cookies import validate_netscape_cookie_file


class _QuietLogger:
    """Suppress yt-dlp messages so cookie contents/URLs cannot leak to stdout."""

    def debug(self, msg: str) -> None:
        return

    def info(self, msg: str) -> None:
        return

    def warning(self, msg: str) -> None:
        return

    def error(self, msg: str) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe yt-dlp cookie usability without downloading media")
    parser.add_argument("url", help="URL belonging to the cookie file's site")
    args = parser.parse_args()

    parsed = urlparse(args.url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host:
        print("status=FAIL")
        print("reason=invalid_host")
        return 2

    cookie_file = _cookie_file_for_host(host)
    print(f"host={host}")
    print(f"cookie_directory={settings.cookies_dir}")

    if not cookie_file:
        print("cookie_file=NOT_FOUND")
        print("status=FAIL")
        print("reason=cookie_file_not_found")
        return 2

    valid, reason, count = validate_netscape_cookie_file(cookie_file)
    print(f"file={cookie_file.name}")
    print(f"format_status={'VALID' if valid else 'INVALID'}")
    print(f"cookie_count={count}")
    print(f"format_reason={reason}")

    if not valid:
        print("status=FAIL")
        print("reason=invalid_cookie_file")
        return 2

    opts = _yt_dlp_opts(host)
    cookiefile = opts.get("cookiefile")
    print(f"yt_dlp_cookiefile_configured={'YES' if cookiefile else 'NO'}")
    print(f"yt_dlp_cookiefile_matches={'YES' if cookiefile and Path(cookiefile).resolve() == cookie_file.resolve() else 'NO'}")

    if not cookiefile:
        print("status=FAIL")
        print("reason=yt_dlp_cookiefile_missing")
        return 2

    probe_opts = dict(opts)
    probe_opts.update(
        {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "logger": _QuietLogger(),
        }
    )

    print("probe=yt_dlp_metadata_only")
    print("download=NOT_PERFORMED")

    try:
        with yt_dlp.YoutubeDL(probe_opts) as ydl:
            info = ydl.extract_info(args.url, download=False)
        title_present = bool(info.get("title")) if isinstance(info, dict) else False
        print("request_result=SUCCESS")
        print(f"metadata_title_present={'YES' if title_present else 'NO'}")
        print("status=PASS")
        return 0
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        if "403" in lowered or "forbidden" in lowered:
            reason_code = "http_403_forbidden"
        elif "401" in lowered or "unauthorized" in lowered:
            reason_code = "http_401_unauthorized"
        elif "429" in lowered or "too many requests" in lowered:
            reason_code = "http_429_rate_limited"
        elif "cookie" in lowered:
            reason_code = "cookie_related_error"
        else:
            reason_code = "request_failed"
        print("request_result=FAILED")
        print(f"reason={reason_code}")
        print("status=FAIL")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
