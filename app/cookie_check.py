import sys
from pathlib import Path

from app.config import settings
from app.downloader import _cookie_file_for_host


def _validate_netscape_cookie_file(path: Path) -> tuple[bool, str, int]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return False, "not_utf8", 0
    except OSError as exc:
        return False, f"read_error:{type(exc).__name__}", 0

    lines = raw.splitlines()
    if not lines:
        return False, "empty", 0

    cookie_count = 0
    has_netscape_header = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# Netscape HTTP Cookie File"):
            has_netscape_header = True
            continue
        if stripped.startswith("#"):
            continue

        fields = line.split("\t")
        if len(fields) != 7:
            return False, "invalid_field_count", cookie_count

        domain, include_subdomains, path_value, secure, expires, name, value = fields
        if not domain or not path_value or not name:
            return False, "invalid_required_field", cookie_count
        if include_subdomains not in {"TRUE", "FALSE"}:
            return False, "invalid_include_subdomains", cookie_count
        if secure not in {"TRUE", "FALSE"}:
            return False, "invalid_secure_flag", cookie_count
        try:
            int(expires)
        except ValueError:
            return False, "invalid_expiry", cookie_count
        cookie_count += 1

    if not has_netscape_header:
        return False, "missing_netscape_header", cookie_count
    if cookie_count == 0:
        return False, "no_cookies", 0
    return True, "valid_netscape", cookie_count


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
    valid, reason, count = _validate_netscape_cookie_file(path)
    print(f"status={'VALID' if valid else 'INVALID'}")
    print(f"format=netscape")
    print(f"cookie_count={count}")
    print(f"reason={reason}")
    print("cookie_values=REDACTED")
    return 0 if valid else 3


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.cookie_check <hostname>")
        raise SystemExit(1)
    raise SystemExit(check(sys.argv[1]))
