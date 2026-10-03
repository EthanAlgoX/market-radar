from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit


LOCAL_ORIGINS = {
    f"http://{host}:{port}"
    for host in ["localhost", "127.0.0.1", "[::1]"]
    for port in [5173, 8787]
}
LOCAL_CALLBACKS = {
    f"http://{host}:8787/api/connections/reddit/callback"
    for host in ["localhost", "127.0.0.1", "[::1]"]
}
LOCAL_CALLBACK = "http://localhost:8787/api/connections/reddit/callback"


def _authority(hostname: str, port: int | None, scheme: str) -> str:
    host = f"[{hostname}]" if ":" in hostname else hostname
    return f"{host}:{port}" if port and port != (443 if scheme == "https" else 80) else host


def _raw_authority(hostname: str, port: int | None) -> str:
    host = f"[{hostname}]" if ":" in hostname else hostname
    return f"{host}:{port}" if port is not None else host


def _valid_hostname(hostname: str) -> bool:
    if ":" in hostname:
        try:
            return isinstance(ipaddress.ip_address(hostname), ipaddress.IPv6Address)
        except ValueError:
            return False
    return bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", hostname)) and all(
        label and len(label) <= 63 and not label.startswith("-") and not label.endswith("-")
        for label in hostname.split(".")
    ) and len(hostname) <= 253


@dataclass(frozen=True)
class DeploymentURL:
    """Explicit external URL; never infer trusted domains from proxy headers."""

    base_url: str
    origin: str
    authority: str
    base_path: str

    @classmethod
    def parse(cls, value: str) -> DeploymentURL:
        message = "RADAR_PUBLIC_URL must be an absolute HTTPS URL with a safe optional path and no credentials, query or fragment."
        try:
            if not value or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value) or any(char in value for char in "\\?#"):
                raise ValueError(message)
            parsed = urlsplit(value)
            host, port = parsed.hostname or "", parsed.port
            if parsed.scheme not in {"http", "https"} or not _valid_hostname(host) or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
                raise ValueError(message)
            # Plain HTTP is supported only for explicit loopback development.
            if parsed.scheme == "http" and host not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError(message)
            if port is not None and not 1 <= port <= 65535:
                raise ValueError(message)
            if parsed.netloc.lower() != _raw_authority(host, port):
                raise ValueError(message)
            path = parsed.path[:-1] if parsed.path.endswith("/") else parsed.path
            if path and (not path.startswith("/") or not re.fullmatch(r"(?:/[A-Za-z0-9._~-]+)+", path) or any(part in {".", ".."} for part in path.split("/"))):
                raise ValueError(message)
            authority = _authority(host, port, parsed.scheme)
            origin = f"{parsed.scheme}://{authority}"
            return cls(f"{origin}{path}/", origin, authority, path)
        except (ValueError, UnicodeError) as error:
            raise ValueError(message) from error

    @property
    def reddit_callback(self) -> str:
        return self.base_url + "api/connections/reddit/callback"


def trusted_request_host(value: str, public_url: DeploymentURL | None, *, allow_testserver: bool = False) -> bool:
    """Validate the Host authority itself, including a configured public port."""
    try:
        if not value or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value) or any(char in value for char in "@/\\?#,"):
            return False
        parsed = urlsplit("http://" + value)
        hostname, port = parsed.hostname or "", parsed.port
        if not _valid_hostname(hostname) or parsed.path or parsed.query or parsed.fragment or parsed.username is not None:
            return False
        if port is not None and not 1 <= port <= 65535:
            return False
        if parsed.netloc.lower() != _raw_authority(hostname, port):
            return False
        if hostname in {"localhost", "127.0.0.1", "::1"} or allow_testserver and hostname == "testserver":
            return True
        if public_url:
            scheme = urlsplit(public_url.origin).scheme
            return _authority(hostname, port, scheme) == public_url.authority
        return False
    except ValueError:
        return False


def route_path(path: str, root_path: str) -> str:
    """Handle a stripping reverse proxy with or without Uvicorn root-path."""
    if root_path and (path == root_path or path.startswith(root_path + "/")):
        return path[len(root_path):] or "/"
    return path
