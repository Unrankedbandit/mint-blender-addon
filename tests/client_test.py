import json
import unittest
from urllib.error import HTTPError

from mint_blender_asset_browser.client import MintApiError, MintBlenderClient
from mint_blender_asset_browser.config import MintBlenderConfig


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return json.dumps(self._body).encode("utf-8")

    def close(self):
        pass


class ClientTest(unittest.TestCase):
    def test_list_models_sends_bearer_token_and_pagination(self):
        calls = []

        def urlopen(request, timeout):
            calls.append((request, timeout))
            return FakeResponse(
                200,
                {
                    "data": [],
                    "pagination": {"nextCursor": None, "hasMore": False},
                },
            )

        client = MintBlenderClient(
            MintBlenderConfig(api_base_url="https://mint.test/api/blender/v1"),
            urlopen=urlopen,
        )

        result = client.list_models("access_123", limit=25, cursor="cursor_1")

        self.assertEqual(result["data"], [])
        request, timeout = calls[0]
        self.assertEqual(timeout, 30)
        self.assertEqual(
            request.full_url,
            "https://mint.test/api/blender/v1/models?limit=25&cursor=cursor_1",
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer access_123")
        self.assertEqual(request.get_method(), "GET")

    def test_list_packs_sends_bearer_token_and_pagination(self):
        calls = []

        def urlopen(request, timeout):
            calls.append((request, timeout))
            return FakeResponse(
                200,
                {
                    "data": [],
                    "pagination": {"nextCursor": None, "hasMore": False},
                },
            )

        client = MintBlenderClient(
            MintBlenderConfig(api_base_url="https://mint.test/api/blender/v1"),
            urlopen=urlopen,
        )

        result = client.list_packs("access_123", limit=25, cursor="cursor_1")

        self.assertEqual(result["data"], [])
        request, timeout = calls[0]
        self.assertEqual(timeout, 30)
        self.assertEqual(
            request.full_url,
            "https://mint.test/api/blender/v1/packs?limit=25&cursor=cursor_1",
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer access_123")
        self.assertEqual(request.get_method(), "GET")

    def test_get_model_url_encodes_path_segment(self):
        calls = []

        def urlopen(request, timeout):
            calls.append(request)
            return FakeResponse(200, {"id": "model/one"})

        client = MintBlenderClient(
            MintBlenderConfig(api_base_url="https://mint.test/api/blender/v1"),
            urlopen=urlopen,
        )

        client.get_model("access_123", "model/one")

        self.assertEqual(
            calls[0].full_url,
            "https://mint.test/api/blender/v1/models/model%2Fone",
        )

    def test_export_world_ply_posts_to_export_endpoint_with_long_timeout(self):
        calls = []

        def urlopen(request, timeout):
            calls.append((request, timeout))
            return FakeResponse(
                200,
                {
                    "object": "world_splat_export",
                    "worldId": "world/one",
                    "format": "ply",
                    "importUrl": "https://cdn.mint.gg/exports/blender/worlds/world-hash.ply",
                },
            )

        client = MintBlenderClient(
            MintBlenderConfig(api_base_url="https://mint.test/api/blender/v1"),
            urlopen=urlopen,
        )

        result = client.export_world_ply("access_123", "world/one")

        self.assertEqual(result["format"], "ply")
        request, timeout = calls[0]
        self.assertEqual(timeout, 600)
        self.assertEqual(
            request.full_url,
            "https://mint.test/api/blender/v1/worlds/world%2Fone/exports/ply",
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer access_123")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(request.get_method(), "POST")

    def test_problem_responses_raise_api_error(self):
        def urlopen(request, timeout):
            return FakeResponse(404, {"detail": "Model not found"})

        client = MintBlenderClient(
            MintBlenderConfig(api_base_url="https://mint.test/api/blender/v1"),
            urlopen=urlopen,
        )

        with self.assertRaises(MintApiError) as raised:
            client.get_model("access_123", "missing")

        self.assertEqual(raised.exception.status, 404)
        self.assertEqual(str(raised.exception), "Model not found")

    def test_http_error_problem_body_raises_api_error_with_detail(self):
        def urlopen(request, timeout):
            response = FakeResponse(
                401,
                {
                    "title": "Invalid OAuth token",
                    "detail": "The Mint OAuth bearer token is invalid or expired.",
                },
            )
            raise HTTPError(request.full_url, 401, "Unauthorized", {}, response)

        client = MintBlenderClient(
            MintBlenderConfig(api_base_url="https://mint.test/api/blender/v1"),
            urlopen=urlopen,
        )

        with self.assertRaises(MintApiError) as raised:
            client.me("expired")

        self.assertEqual(raised.exception.status, 401)
        self.assertEqual(
            str(raised.exception),
            "The Mint OAuth bearer token is invalid or expired.",
        )


if __name__ == "__main__":
    unittest.main()
