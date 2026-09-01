import sys

from app.config import settings
from app.cookies import validate_netscape_cookie_file
from app.downloader import _cookie_file_for_host


def check(host: str) -> int:
    normalized = host.strip().lower().removeprefix("www.")
    path = _cookie_file_for_host(normalized)

    print(f"cookie_directory={settings.cookies_dir}")
    print(f"host={normalized}")

    if path is None:
        print("status=NOT_FOUND")
        print("message=No site-specific cookie file was found.")
        return 2

    print(f"file={path.name}")
    print(f"size_bytes={path.stat().st_size}")
    valid, reason, count = validate_netscape_cookie_file(path)
    print(f"status={'VALID' if valid else 'INVALID'}")
    print("format=netscape")
    print(f"cookie_count={count}")
    print(f"reason={reason}")
    print("cookie_values=REDACTED")
    return 0 if valid else 3


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.cookie_check <hostname>")
        raise SystemExit(1)
    raise SystemExit(check(sys.argv[1]))
