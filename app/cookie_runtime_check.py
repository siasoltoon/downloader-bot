"""Safe runtime check for site-specific cookie loading.

This module performs no network requests and never prints cookie values.
It verifies that the configured cookie file is valid and that downloader
configuration passes its path to yt-dlp as ``cookiefile``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

from app.cookies import validate_netscape_cookie_file
from app.downloader import _cookie_file_for_host, _yt_dlp_opts


def _host(value: str) -> str:
    value = value.strip().lower().removeprefix("www.")
    if not value or "." not in value:
        raise ValueError("host must be a hostname such as example.com")
    return value


def run(host: str) -> int:
    host = _host(host)
    cookie_file = _cookie_file_for_host(host)

    print(f"host={host}")
    print(f"cookie_directory={cookie_file.parent if cookie_file else 'not_found'}")
    print(f"file={cookie_file.name if cookie_file else 'not_found'}")

    if cookie_file is None:
        print("status=FAIL")
        print("reason=cookie_file_not_found")
        return 1

    valid, reason, count = validate_netscape_cookie_file(cookie_file)
    print(f"format_status={'VALID' if valid else 'INVALID'}")
    print(f"cookie_count={count}")
    print(f"format_reason={reason}")
    if not valid:
        print("status=FAIL")
        return 1

    # Capture the options generated for yt-dlp without constructing a real
    # downloader or making any request to the target site.
    with patch("app.downloader.validate_netscape_cookie_file", return_value=(True, reason, count)):
        opts = _yt_dlp_opts(host)

    configured_path = opts.get("cookiefile")
    expected_path = str(cookie_file)
    loaded = configured_path == expected_path

    print(f"yt_dlp_cookiefile_configured={'YES' if configured_path else 'NO'}")
    print(f"yt_dlp_cookiefile_matches={'YES' if loaded else 'NO'}")
    print("network_request=NOT_PERFORMED")
    print(f"status={'PASS' if loaded else 'FAIL'}")
    return 0 if loaded else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe local cookie runtime check")
    parser.add_argument("host", help="site hostname, e.g. example.com")
    args = parser.parse_args()
    try:
        return run(args.host)
    except Exception as exc:
        print("status=FAIL")
        print(f"reason={type(exc).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
