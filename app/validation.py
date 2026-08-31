from urllib.parse import urlparse


def valid_url(value: str) -> bool:
    if not value or len(value) > 4096:
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False
