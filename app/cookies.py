from pathlib import Path


def validate_netscape_cookie_file(path: Path) -> tuple[bool, str, int]:
    """Validate cookie-file structure without logging cookie names or values."""
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

        domain, include_subdomains, path_value, secure, expires, name, _value = fields
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
