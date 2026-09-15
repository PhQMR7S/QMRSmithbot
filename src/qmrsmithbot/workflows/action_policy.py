from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit


class ActionPolicyError(ValueError):
    """Raised when a workflow action violates the platform egress policy."""


@dataclass(frozen=True, slots=True)
class ResolvedAddress:
    """A DNS result that has passed the workflow egress policy."""

    host: str
    address: str


def validate_http_url(url: str, *, max_length: int = 2048) -> str:
    """Validate URL syntax and reject schemes/hosts unsafe for server-side HTTP."""

    if not isinstance(url, str) or not url or len(url) > max_length:
        raise ActionPolicyError("HTTP URL is missing or exceeds the maximum length")

    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ActionPolicyError("HTTP URL is invalid") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ActionPolicyError("HTTP action only permits http and https")
    if parsed.username is not None or parsed.password is not None:
        raise ActionPolicyError("HTTP action does not permit embedded credentials")
    if not parsed.hostname:
        raise ActionPolicyError("HTTP URL must contain a hostname")
    if parsed.fragment:
        raise ActionPolicyError("HTTP action does not permit URL fragments")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ActionPolicyError("HTTP action does not permit localhost targets")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ActionPolicyError("HTTP URL contains an invalid port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ActionPolicyError("HTTP URL port is outside the valid range")

    _reject_unsafe_ip(hostname)
    return url


def resolve_and_validate_host(host: str) -> tuple[ResolvedAddress, ...]:
    """Resolve a hostname and reject every unsafe address returned by DNS.

    All returned addresses must pass validation. This prevents an attacker from
    bypassing the URL policy with a hostname that resolves to a private or
    link-local address. Callers must re-run this check after every redirect.
    """

    normalized = host.rstrip(".").lower()
    if not normalized or len(normalized) > 253:
        raise ActionPolicyError("HTTP hostname is invalid")
    if normalized == "localhost" or normalized.endswith(".localhost"):
        raise ActionPolicyError("HTTP action does not permit localhost targets")

    _reject_unsafe_ip(normalized)
    try:
        results = socket.getaddrinfo(normalized, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ActionPolicyError("HTTP hostname could not be resolved") from exc

    addresses = {result[4][0] for result in results if result[4]}
    if not addresses:
        raise ActionPolicyError("HTTP hostname resolved to no addresses")

    resolved: list[ResolvedAddress] = []
    for address in sorted(addresses):
        _reject_unsafe_ip(address)
        resolved.append(ResolvedAddress(host=normalized, address=address))
    return tuple(resolved)


def validate_redirect(url: str, *, max_length: int = 2048) -> str:
    """Validate a redirect target exactly like an initial HTTP target."""

    return validate_http_url(url, max_length=max_length)


def _reject_unsafe_ip(host: str) -> None:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return

    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise ActionPolicyError("HTTP action target resolves to a disallowed address")
