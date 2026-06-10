import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mint_blender_asset_browser.auth import (
    RefreshTokenStore,
    StoredRefreshToken,
    build_authorization_url,
    exchange_authorization_code,
    exchange_refresh_token,
    generate_pkce_pair,
)
from mint_blender_asset_browser.config import MintBlenderConfig


class AuthTest(unittest.TestCase):
    def test_config_reads_local_ca_cert_file_from_env(self):
        config = MintBlenderConfig.from_env(
            {
                "MINT_BLENDER_API_BASE_URL": "https://mint.test/api/blender/v1",
                "MINT_BLENDER_CA_CERT_FILE": "~/local-ca.pem",
            }
        )

        self.assertEqual(
            config.api_base_url,
            "https://mint.test/api/blender/v1",
        )
        self.assertEqual(config.ca_cert_file, Path.home() / "local-ca.pem")

    def test_config_ignores_global_ssl_cert_file_env(self):
        config = MintBlenderConfig.from_env(
            {
                "SSL_CERT_FILE": "~/global-ca.pem",
            }
        )

        self.assertIsNone(config.ca_cert_file)

    def test_pkce_pair_uses_s256_challenge(self):
        pair = generate_pkce_pair()

        self.assertIn("verifier", pair)
        self.assertIn("challenge", pair)
        self.assertNotEqual(pair["verifier"], pair["challenge"])
        self.assertGreaterEqual(len(pair["verifier"]), 43)

    def test_authorization_url_requests_asset_read_scope(self):
        config = MintBlenderConfig(
            oauth_authorize_url="https://mcp.test/oauth/authorize",
            client_id="mint_blender_test",
            loopback_port=49152,
        )

        url = build_authorization_url(
            config,
            state="state_123",
            code_challenge="challenge_123",
        )

        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "mcp.test")
        self.assertEqual(params["client_id"], ["mint_blender_test"])
        self.assertEqual(params["scope"], ["mint:assets:read"])
        self.assertEqual(
            params["redirect_uri"],
            ["http://127.0.0.1:49152/oauth/callback"],
        )
        self.assertEqual(params["code_challenge_method"], ["S256"])

    def test_refresh_token_store_persists_only_refresh_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oauth.json"
            store = RefreshTokenStore(path)
            token = StoredRefreshToken(
                refresh_token="refresh_123",
                client_id="mint_blender",
                token_url="https://mcp.test/oauth/token",
            )

            store.save(token)
            self.assertEqual(store.load(), token)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("access_token", data)
            if os.name != "nt":
                self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

            store.clear()
            self.assertIsNone(store.load())

    def test_exchange_authorization_code_posts_pkce_token_request(self):
        calls = []

        class Response:
            def read(self):
                return json.dumps(
                    {
                        "access_token": "access_123",
                        "refresh_token": "refresh_123",
                        "expires_in": 3600,
                        "token_type": "Bearer",
                    }
                ).encode("utf-8")

        def urlopen(request, **kwargs):
            calls.append((request, kwargs))
            return Response()

        config = MintBlenderConfig(
            oauth_token_url="https://mcp.test/oauth/token",
            client_id="mint_blender_test",
        )

        token = exchange_authorization_code(
            config,
            code="code_123",
            code_verifier="verifier_123",
            redirect_uri="http://127.0.0.1:49152/oauth/callback",
            urlopen=urlopen,
        )

        request, kwargs = calls[0]
        body = parse_qs(request.data.decode("utf-8"))
        self.assertEqual(kwargs["timeout"], 30)
        self.assertEqual(request.full_url, "https://mcp.test/oauth/token")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(body["grant_type"], ["authorization_code"])
        self.assertEqual(body["code_verifier"], ["verifier_123"])
        self.assertEqual(token.access_token, "access_123")
        self.assertEqual(token.refresh_token, "refresh_123")

    def test_exchange_refresh_token_posts_refresh_token_request(self):
        calls = []

        class Response:
            def read(self):
                return json.dumps(
                    {
                        "access_token": "access_next",
                        "refresh_token": "refresh_next",
                        "expires_in": 3600,
                        "token_type": "Bearer",
                    }
                ).encode("utf-8")

        def urlopen(request, **kwargs):
            calls.append((request, kwargs))
            return Response()

        config = MintBlenderConfig(
            oauth_token_url="https://mcp.test/oauth/token",
            client_id="mint_blender_test",
        )

        token = exchange_refresh_token(
            config,
            refresh_token="refresh_123",
            urlopen=urlopen,
        )

        request, kwargs = calls[0]
        body = parse_qs(request.data.decode("utf-8"))
        self.assertEqual(kwargs["timeout"], 30)
        self.assertEqual(request.full_url, "https://mcp.test/oauth/token")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(body["grant_type"], ["refresh_token"])
        self.assertEqual(body["refresh_token"], ["refresh_123"])
        self.assertEqual(token.access_token, "access_next")
        self.assertEqual(token.refresh_token, "refresh_next")


if __name__ == "__main__":
    unittest.main()
