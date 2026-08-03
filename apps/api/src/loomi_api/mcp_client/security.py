from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loomi_api.config import Settings
from loomi_api.mcp_client.protocol import SAFE_TEMPLATE_RE, MCPClientError

MINIMAL_STDIO_ENV = ("HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER")
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata",
}


@dataclass(frozen=True)
class ResolvedRemoteEndpoint:
    url: str
    scheme: str
    hostname: str
    host_header: str
    port: int
    target: str
    address: str


def validate_template_name(name: str) -> str:
    if not SAFE_TEMPLATE_RE.fullmatch(name):
        raise MCPClientError("invalid_template", "Unknown or malformed stdio template.")
    return name


def build_minimal_env(allowlist: list[str], secret_ref: str | None = None) -> dict[str, str]:
    allowed = {key for key in MINIMAL_STDIO_ENV if key in os.environ}
    for key in allowlist:
        safe_name = _safe_env_name(key)
        if safe_name is not None:
            allowed.add(safe_name)
    if secret_ref and secret_ref.startswith("env:"):
        name = _safe_env_name(secret_ref[4:])
        if name:
            allowed.add(name)
    return {key: os.environ[key] for key in sorted(allowed) if key in os.environ}


def resolve_bearer_token(secret_ref: str | None) -> str | None:
    if not secret_ref or not secret_ref.startswith("env:"):
        return None
    name = _safe_env_name(secret_ref[4:])
    if not name:
        return None
    value = os.environ.get(name)
    return value or None


def validate_secret_ref(secret_ref: str | None) -> str | None:
    if secret_ref in {None, ""}:
        return None
    if not secret_ref.startswith("env:"):
        raise MCPClientError(
            "invalid_secret_ref",
            "MCP secrets must be stored as secret references such as env:NAME.",
        )
    name = _safe_env_name(secret_ref[4:])
    if name is None:
        raise MCPClientError("invalid_secret_ref", "MCP secret reference is malformed.")
    return f"env:{name}"


def validate_working_directory(settings: Settings, value: str | None) -> str | None:
    if not value:
        return None
    root = (settings.storage_root / "mcp-workdirs").resolve()
    candidate = Path(value).expanduser().resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise MCPClientError(
            "invalid_working_directory",
            "MCP stdio working directories must live under the configured MCP workdir root.",
        ) from exc
    return str(candidate)


def validate_remote_endpoint(
    settings: Settings,
    url: str,
    *,
    allow_private_networks: bool = False,
) -> str:
    return resolve_remote_endpoint(
        settings,
        url,
        allow_private_networks=allow_private_networks,
    ).url


def resolve_remote_endpoint(
    settings: Settings,
    url: str,
    *,
    allow_private_networks: bool = False,
) -> ResolvedRemoteEndpoint:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise MCPClientError("invalid_remote_endpoint", "Remote MCP endpoints must be HTTP(S).")
    if parsed.scheme != "https" and settings.environment not in {"local", "test"}:
        raise MCPClientError(
            "remote_tls_required",
            "Remote MCP endpoints must use HTTPS outside local development.",
        )
    if not parsed.hostname:
        raise MCPClientError("invalid_remote_endpoint", "Remote MCP endpoint host is required.")
    if parsed.username or parsed.password:
        raise MCPClientError(
            "remote_credentials_in_url",
            "Remote MCP credentials must use secret references, not URL userinfo.",
        )
    hostname = parsed.hostname
    assert hostname is not None
    if not allow_private_networks:
        addresses = _resolve_allowed_addresses(hostname)
    elif settings.environment == "production" and not settings.mcp_allow_private_networks:
        raise MCPClientError(
            "private_networks_disabled",
            "Private-network MCP endpoints are disabled in production.",
        )
    else:
        addresses = _resolve_addresses(hostname)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    default_port = 443 if parsed.scheme == "https" else 80
    host_header = hostname if port == default_port else f"{hostname}:{port}"
    return ResolvedRemoteEndpoint(
        url=url,
        scheme=parsed.scheme,
        hostname=hostname,
        host_header=host_header,
        port=port,
        target=target,
        address=str(addresses[0]),
    )


def sanitized_server_config(payload: dict[str, Any]) -> dict[str, Any]:
    safe = dict(payload)
    safe.pop("secret_ref", None)
    safe.pop("command", None)
    safe.pop("resolved_command", None)
    return safe


def _reject_private_destination(hostname: str) -> None:
    _resolve_allowed_addresses(hostname)


def _resolve_allowed_addresses(
    hostname: str,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    lowered = hostname.strip(".").casefold()
    if lowered in BLOCKED_HOSTNAMES or lowered.endswith(".local"):
        raise MCPClientError("ssrf_blocked", "Remote MCP endpoint resolves to a blocked host.")
    try:
        addresses = [ipaddress.ip_address(lowered)]
    except ValueError:
        addresses = _resolve_addresses(hostname)
    for address in addresses:
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise MCPClientError(
                "ssrf_blocked",
                "Remote MCP endpoint resolves to a private or reserved address.",
            )
    return addresses


def _resolve_addresses(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise MCPClientError("remote_dns_failed", "Remote MCP endpoint DNS lookup failed.") from exc
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for family, _, _, _, sockaddr in infos:
        raw = str(sockaddr[0])
        if family in {socket.AF_INET, socket.AF_INET6}:
            addresses.append(ipaddress.ip_address(raw))
    if not addresses:
        raise MCPClientError("remote_dns_failed", "Remote MCP endpoint did not resolve.")
    return addresses


def _safe_env_name(value: str) -> str | None:
    if not value or len(value) > 120:
        return None
    if not value.replace("_", "A").isalnum() or value[0].isdigit():
        return None
    return value
