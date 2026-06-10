import tempfile
import unittest
from pathlib import Path

from mint_blender_asset_browser.cache import AssetCache


class AssetCacheTest(unittest.TestCase):
    def test_paths_are_stable_and_sanitized_by_url_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = AssetCache(Path(tmp))
            first = cache.path_for("Model 1/Chair", "https://cdn.mint.gg/chair.glb")
            second = cache.path_for("Model 1/Chair", "https://cdn.mint.gg/chair.glb")
            other = cache.path_for("Model 1/Chair", "https://cdn.mint.gg/chair-v2.glb")

            self.assertEqual(first, second)
            self.assertNotEqual(first, other)
            self.assertTrue(first.name.startswith("Model-1-Chair-"))
            self.assertTrue(first.name.endswith(".glb"))

    def test_write_bytes_creates_cache_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = AssetCache(Path(tmp))
            path = cache.write_bytes("model_1", "https://cdn.mint.gg/model.glb", b"glb")

            self.assertTrue(path.exists())
            self.assertTrue(cache.exists("model_1", "https://cdn.mint.gg/model.glb"))
            self.assertEqual(path.read_bytes(), b"glb")


if __name__ == "__main__":
    unittest.main()
