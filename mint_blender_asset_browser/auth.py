"""OAuth helpers for the Mint Blender extension."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.request
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from .config import MintBlenderConfig
from .http import urlopen_with_config

UrlOpen = Callable[..., Any]


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce_pair(byte_length: int = 32) -> Mapping[str, str]:
    verifier = _base64url(os.urandom(byte_length))
    challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return {"verifier": verifier, "challenge": challenge}


def build_authorization_url(
    config: MintBlenderConfig,
    state: str,
    code_challenge: str,
    redirect_uri: Optional[str] = None,
) -> str:
    params = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": redirect_uri or config.loopback_redirect_uri,
        "scope": config.oauth_scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return "%s?%s" % (
        config.oauth_authorize_url,
        urllib.parse.urlencode(params),
    )


@dataclass(frozen=True)
class StoredRefreshToken:
    refresh_token: str
    client_id: str
    token_url: str


@dataclass(frozen=True)
class TokenResponse:
    access_token: str
    refresh_token: Optional[str]
    expires_in: Optional[int]
    token_type: str


def exchange_authorization_code(
    config: MintBlenderConfig,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    urlopen: Optional[UrlOpen] = None,
) -> TokenResponse:
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": config.client_id,
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        config.oauth_token_url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    response = urlopen_with_config(request, config, urlopen, timeout=30)
    return parse_token_response(response)


def exchange_refresh_token(
    config: MintBlenderConfig,
    refresh_token: str,
    urlopen: Optional[UrlOpen] = None,
) -> TokenResponse:
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": config.client_id,
            "refresh_token": refresh_token,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        config.oauth_token_url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    response = urlopen_with_config(request, config, urlopen, timeout=30)
    return parse_token_response(response)


def parse_token_response(response: Any) -> TokenResponse:
    data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("access_token"), str):
        raise RuntimeError("Mint OAuth token response was invalid")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")
    return TokenResponse(
        access_token=data["access_token"],
        refresh_token=refresh_token if isinstance(refresh_token, str) else None,
        expires_in=expires_in if isinstance(expires_in, int) else None,
        token_type=str(data.get("token_type") or "Bearer"),
    )


class RefreshTokenStore:
    """Small JSON refresh-token store.

    Access tokens are intentionally not persisted; they should stay memory-only
    in the Blender process.
    """

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Optional[StoredRefreshToken]:
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        refresh_token = data.get("refresh_token")
        client_id = data.get("client_id")
        token_url = data.get("token_url")
        if not all(isinstance(value, str) for value in [refresh_token, client_id, token_url]):
            return None
        return StoredRefreshToken(
            refresh_token=refresh_token,
            client_id=client_id,
            token_url=token_url,
        )

    def save(self, token: StoredRefreshToken) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            os.chmod(self.path.parent, 0o700)

        tmp_path = self.path.with_name(".%s.tmp" % self.path.name)
        tmp_path.write_text(
            json.dumps(
                {
                    "refresh_token": token.refresh_token,
                    "client_id": token.client_id,
                    "token_url": token.token_url,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        if os.name != "nt":
            os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, self.path)
        if os.name != "nt":
            os.chmod(self.path, 0o600)

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return
