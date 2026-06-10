"""OAuth connect/disconnect controller for the Blender UI."""

from __future__ import annotations

import secrets
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

from .auth import RefreshTokenStore, build_authorization_url, generate_pkce_pair
from .config import MintBlenderConfig

OpenBrowser = Callable[[str], bool]


@dataclass(frozen=True)
class OAuthSession:
    state: str
    verifier: str
    authorization_url: str
    redirect_uri: str


@dataclass(frozen=True)
class OAuthCallbackResult:
    code: str
    state: str


class LoopbackCallbackServer:
    def __init__(self, host: str = "127.0.0.1", path: str = "/oauth/callback"):
        self.host = host
        self.path = path
        self.result: Optional[OAuthCallbackResult] = None
        self.error: Optional[str] = None

        parent = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # type: ignore
                parsed = urlparse(self.path)
                if parsed.path != parent.path:
                    self.send_response(404)
                    self.end_headers()
                    return
                params = parse_qs(parsed.query)
                code = params.get("code", [None])[0]
                state = params.get("state", [None])[0]
                error = params.get("error", [None])[0]
                if error:
                    parent.error = str(error)
                elif code and state:
                    parent.result = OAuthCallbackResult(str(code), str(state))
                else:
                    parent.error = "missing_code"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Mint authorization complete. You can return to Blender.")

            def log_message(self, format, *args):  # type: ignore
                return

        self.server = HTTPServer((host, 0), Handler)

    @property
    def redirect_uri(self) -> str:
        port = self.server.server_address[1]
        return "http://%s:%s%s" % (self.host, port, self.path)

    def wait_for_callback(self, expected_state: str, timeout_seconds: int = 300) -> str:
        self.server.timeout = timeout_seconds
        self.server.handle_request()
        if self.error:
            raise RuntimeError("OAuth callback failed: %s" % self.error)
        if not self.result:
            raise TimeoutError("Timed out waiting for Mint OAuth callback")
        if self.result.state != expected_state:
            raise RuntimeError("OAuth callback state did not match")
        return self.result.code

    def close(self) -> None:
        self.server.server_close()


class OAuthController:
    def __init__(self, config: MintBlenderConfig, token_store: RefreshTokenStore):
        self.config = config
        self.token_store = token_store
        self.pending_session: Optional[OAuthSession] = None

    def start(
        self,
        open_browser: Optional[OpenBrowser] = None,
        redirect_uri: Optional[str] = None,
    ) -> OAuthSession:
        pair = generate_pkce_pair()
        state = secrets.token_urlsafe(24)
        callback_uri = redirect_uri or self.config.loopback_redirect_uri
        authorization_url = build_authorization_url(
            self.config,
            state=state,
            code_challenge=pair["challenge"],
            redirect_uri=callback_uri,
        )
        session = OAuthSession(
            state=state,
            verifier=pair["verifier"],
            authorization_url=authorization_url,
            redirect_uri=callback_uri,
        )
        self.pending_session = session
        (open_browser or webbrowser.open)(authorization_url)
        return session

    def disconnect(self) -> None:
        self.pending_session = None
        self.token_store.clear()
