from __future__ import annotations

import re
from urllib.parse import urlsplit


_STATUS_URL = re.compile(
    r"https?://(?:www\.)?(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,15})/status/(\d+)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_TRAILING_PUNCTUATION = ".,;:!?)]}>'\""


def parse_x_status_url(value: str | None) -> tuple[str, str] | None:
    """Return (account, post ID) from an X/Twitter status URL without network access."""
    if not value:
        return None
    candidate = value.strip().rstrip(_TRAILING_PUNCTUATION)
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or parsed.hostname is None:
        return None
    if parsed.hostname.lower() not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        return None
    match = _STATUS_URL.fullmatch(candidate.split("?", 1)[0].split("#", 1)[0])
    if not match:
        return None
    return match.group(1), match.group(2)


def find_x_status_url(text: str | None) -> str | None:
    """Find the first X/Twitter status URL in pasted text; leave the original text intact."""
    if not text:
        return None
    for match in _STATUS_URL.finditer(text):
        url = match.group(0).rstrip(_TRAILING_PUNCTUATION)
        if parse_x_status_url(url):
            return url
    return None
