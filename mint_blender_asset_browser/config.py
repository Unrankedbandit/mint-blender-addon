"""Configuration for the Mint Blender extension."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional


@dataclass(frozen=True)
class MintBlenderConfig:
    api_base_url: str = "https://mint.gg/api/blender/v1"
    oauth_authorize_url: str = "https://mcp.mint.gg/oauth/authorize"
    oauth_token_url: str = "https://mcp.mint.gg/oauth/token"
    client_id: str = "mint_blender"
    oauth_scope: str = "mint:assets:read"
    loopback_host: str = "127.0.0.1"
    loopback_port: int = 0
    loopback_callback_path: str = "/oauth/callback"
    cache_dir: Path = Path.home() / ".cache" / "mint-blender"
    token_store_path: Path = Path.home() / ".config" / "mint-blender" / "oauth.json"
    ca_cert_file: Optional[Path] = None

    @property
    def loopback_redirect_uri(self) -> str:
        port = self.loopback_port or 0
        return "http://%s:%s%s" % (
            self.loopback_host,
            port,
            self.loopback_callback_path,
        )

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "MintBlenderConfig":
        env = environ or os.environ
        ca_cert_file = env.get("MINT_BLENDER_CA_CERT_FILE")
        return cls(
            api_base_url=env.get("MINT_BLENDER_API_BASE_URL", cls.api_base_url),
            oauth_authorize_url=env.get(
                "MINT_BLENDER_OAUTH_AUTHORIZE_URL",
                cls.oauth_authorize_url,
            ),
            oauth_token_url=env.get(
                "MINT_BLENDER_OAUTH_TOKEN_URL",
                cls.oauth_token_url,
            ),
            client_id=env.get("MINT_BLENDER_CLIENT_ID", cls.client_id),
            ca_cert_file=Path(ca_cert_file).expanduser() if ca_cert_file else None,
        )
