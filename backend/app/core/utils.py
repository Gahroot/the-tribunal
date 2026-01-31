"""Core utility functions."""

import ipaddress

from fastapi import Request


def get_client_ip(request: Request, trusted_proxies: list[str]) -> str:
    """Extract client IP from request with secure proxy validation.

    Only trusts X-Forwarded-For header if the request comes from a trusted proxy.
    This prevents IP spoofing attacks where malicious clients set fake headers.

    Args:
        request: FastAPI request object
        trusted_proxies: List of trusted proxy IP addresses (e.g., ["127.0.0.1", "::1"])

    Returns:
        Client IP address as a string

    Security:
        - Only accepts X-Forwarded-For from trusted proxies
        - Validates IP addresses to prevent injection attacks
        - Returns direct client IP if proxy is not trusted
        - Handles missing or malformed headers gracefully
    """
    # Get the direct client IP (the immediate connection)
    direct_ip = request.client.host if request.client else "unknown"

    # If direct IP is unknown, return it immediately
    if direct_ip == "unknown":
        return direct_ip

    # Validate that the direct IP is from a trusted proxy
    is_trusted_proxy = _is_trusted_proxy(direct_ip, trusted_proxies)
    if not is_trusted_proxy:
        return direct_ip

    # Only trust X-Forwarded-For if request is from a trusted proxy
    return _extract_forwarded_ip(request, direct_ip)


def _is_trusted_proxy(direct_ip: str, trusted_proxies: list[str]) -> bool:
    """Check if the direct IP is from a trusted proxy."""
    try:
        direct_ip_obj = ipaddress.ip_address(direct_ip)
        for trusted_proxy in trusted_proxies:
            try:
                trusted_proxy_obj = ipaddress.ip_address(trusted_proxy)
                if direct_ip_obj == trusted_proxy_obj:
                    return True
            except ValueError:
                # Invalid trusted proxy configuration - skip it
                continue
    except ValueError:
        # Invalid direct IP
        pass
    return False


def _extract_forwarded_ip(request: Request, fallback_ip: str) -> str:
    """Extract IP from X-Forwarded-For header with validation."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if not forwarded_for:
        return fallback_ip

    # X-Forwarded-For can contain multiple IPs: "client, proxy1, proxy2"
    # The leftmost IP is the original client
    ips = [ip.strip() for ip in forwarded_for.split(",")]
    if not ips:
        return fallback_ip

    # Validate the first IP before returning it
    first_ip = ips[0]
    try:
        # This validates the IP format and prevents injection
        ipaddress.ip_address(first_ip)
        return first_ip
    except ValueError:
        # Invalid IP in X-Forwarded-For - fall back to direct IP
        return fallback_ip
