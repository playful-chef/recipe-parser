from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse

_WHITESPACE_RE = re.compile(r"\s+")


def collapse_ws(value: str | None) -> str:
    """Normalize whitespace and NBSPs into single ASCII spaces."""
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value.replace("\xa0", " ")).strip()


def normalize_url(candidate: str, base_url: str, allowed_hosts: set[str] | None = None) -> str | None:
    """Resolve a URL relative to base_url and ensure it stays on an allowed host."""
    if not candidate:
        return None
    merged = urljoin(base_url, candidate)
    parsed = urlparse(merged)
    if parsed.scheme not in {"http", "https"}:
        return None
    if allowed_hosts and parsed.netloc not in allowed_hosts:
        return None
    sanitized = parsed._replace(fragment="")
    return urlunparse(sanitized)


