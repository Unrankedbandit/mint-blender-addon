"""HTTP helpers shared by the Blender extension."""

from __future__ import annotations

import ipaddress
import ssl
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

from .config import MintBlenderConfig

UrlOpen = Callable[..., Any]


class UnsafeUrlError(ValueError):
    pass


def _is_local_http_host(hostname: Optional[str]) -> bool:
    if not hostname:
        return False

    normalized = hostname.lower()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True

    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def ensure_safe_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "https" and parsed.netloc:
        return url

    if parsed.scheme == "http" and _is_local_http_host(parsed.hostname):
        return url

    raise UnsafeUrlError("Unsupported URL scheme for Mint Blender add-on: %s" % parsed.scheme)


def _relax_strict_x509_verification(context: ssl.SSLContext) -> ssl.SSLContext:
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if strict_flag:
        context.verify_flags &= ~strict_flag
    return context


def _ssl_context(config: MintBlenderConfig) -> Optional[ssl.SSLContext]:
    if not config.ca_cert_file:
        return None
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(config.ca_cert_file))
    return _relax_strict_x509_verification(context)


def urlopen_with_config(
    request: Any,
    config: MintBlenderConfig,
    urlopen: Optional[UrlOpen] = None,
    **kwargs: Any,
) -> Any:
    request_url = getattr(request, "full_url", request)
    if isinstance(request_url, str):
        ensure_safe_url(request_url)

    opener = urlopen or urllib.request.urlopen
    context = _ssl_context(config)
    if context is not None:
        kwargs["context"] = context
    return opener(request, **kwargs)
