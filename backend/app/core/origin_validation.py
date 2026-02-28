"""Origin validation utility for public endpoints."""

from urllib.parse import urlparse

from fastapi import Request


def validate_origin(request: Request, allowed_domains: list[str]) -> bool:
    """Validate the request origin against allowed domains."""
    origin = request.headers.get("origin") or request.headers.get("referer")

    if not origin:
        return False

    try:
        parsed = urlparse(origin)
        host = parsed.hostname or ""
    except Exception:
        return False

    if not allowed_domains:
        return False

    for domain in allowed_domains:
        domain = domain.lower().strip()
        host_lower = host.lower()

        # Exact match
        if host_lower == domain:
            return True

        # Wildcard subdomain match (*.example.com)
        if domain.startswith("*."):
            base_domain = domain[2:]
            if host_lower == base_domain or host_lower.endswith(f".{base_domain}"):
                return True

    return False
