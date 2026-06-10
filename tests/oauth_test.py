import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import parse_qs, urlparse

from mint_blender_asset_browser.auth import RefreshTokenStore, StoredRefreshToken
from mint_blender_asset_browser.config import MintBlenderConfig
from mint_blender_asset_browser.oauth import LoopbackCallbackServer, OAuthController


class OAuthControllerTest(unittest.TestCase):
    def test_start_builds_authorization_session_and_opens_browser(self):
        opened = []
        with tempfile.TemporaryDirectory() as tmp:
            config = MintBlenderConfig(
                oauth_authorize_url="https://mcp.test/oauth/authorize",
                loopback_port=49152,
                token_store_path=Path(tmp) / "oauth.json",
            )
            controller = OAuthController(config, RefreshTokenStore(config.token_store_path))

            session = controller.start(open_browser=lambda url: opened.append(url) or True)

            self.assertEqual(opened, [session.authorization_url])
            self.assertEqual(controller.pending_session, session)
            params = parse_qs(urlparse(session.authorization_url).query)
            self.assertEqual(params["scope"], ["mint:assets:read"])
            self.assertEqual(params["code_challenge_method"], ["S256"])
            self.assertEqual(session.redirect_uri, "http://127.0.0.1:49152/oauth/callback")

    def test_disconnect_clears_pending_session_and_refresh_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = MintBlenderConfig(token_store_path=Path(tmp) / "oauth.json")
            store = RefreshTokenStore(config.token_store_path)
            store.save(
                StoredRefreshToken(
                    refresh_token="refresh_123",
                    client_id="mint_blender",
                    token_url=config.oauth_token_url,
                )
            )
            controller = OAuthController(config, store)
            controller.pending_session = controller.start(open_browser=lambda url: True)

            controller.disconnect()

            self.assertIsNone(controller.pending_session)
            self.assertIsNone(store.load())

    def test_loopback_callback_captures_code_after_state_check(self):
        callback = LoopbackCallbackServer()
        result = {}

        def wait():
            result["code"] = callback.wait_for_callback("state_123", timeout_seconds=2)

        thread = threading.Thread(target=wait)
        thread.start()
        urlopen("%s?code=code_123&state=state_123" % callback.redirect_uri).read()
        thread.join(timeout=2)
        callback.close()

        self.assertEqual(result["code"], "code_123")


if __name__ == "__main__":
    unittest.main()
