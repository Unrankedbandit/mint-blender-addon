import ssl
import tempfile
import unittest

from pathlib import Path

from mint_blender_asset_browser.config import MintBlenderConfig
from mint_blender_asset_browser.http import (
    UnsafeUrlError,
    _relax_strict_x509_verification,
    _ssl_context,
    ensure_safe_url,
)


class HttpTest(unittest.TestCase):
    def test_ensure_safe_url_allows_https_and_local_http_only(self):
        self.assertEqual(ensure_safe_url("https://cdn.mint.gg/model.glb"), "https://cdn.mint.gg/model.glb")
        self.assertEqual(ensure_safe_url("http://127.0.0.1:3000/callback"), "http://127.0.0.1:3000/callback")
        self.assertEqual(ensure_safe_url("http://localhost:3000/api"), "http://localhost:3000/api")

        for url in [
            "http://example.com/model.glb",
            "file:///home/example/.ssh/id_rsa",
            "ftp://cdn.mint.gg/model.glb",
            "javascript:alert(1)",
        ]:
            with self.subTest(url=url):
                with self.assertRaises(UnsafeUrlError):
                    ensure_safe_url(url)

    def test_relax_strict_x509_verification_keeps_tls_verification_without_strict_flag(self):
        strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
        if not strict_flag:
            self.skipTest("Python ssl module does not expose VERIFY_X509_STRICT")

        context = ssl.create_default_context()
        context.verify_flags |= strict_flag

        _relax_strict_x509_verification(context)

        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertFalse(context.verify_flags & strict_flag)

    def test_ssl_context_loads_default_roots_before_local_ca(self):
        with tempfile.TemporaryDirectory() as tmp:
            ca_path = Path(tmp) / "local-ca.pem"
            ca_path.write_text("", encoding="utf-8")
            calls = []

            class FakeContext:
                verify_flags = 0

                def load_verify_locations(self, cafile):
                    calls.append(("load_verify_locations", cafile))

            original_create_default_context = ssl.create_default_context
            original_relax = _relax_strict_x509_verification

            try:
                ssl.create_default_context = lambda: calls.append(
                    ("create_default_context", None)
                ) or FakeContext()
                import mint_blender_asset_browser.http as http_module

                http_module._relax_strict_x509_verification = lambda context: calls.append(
                    ("relax", None)
                ) or context

                context = _ssl_context(MintBlenderConfig(ca_cert_file=ca_path))
            finally:
                ssl.create_default_context = original_create_default_context
                http_module._relax_strict_x509_verification = original_relax

            self.assertIsNotNone(context)
            self.assertEqual(
                calls,
                [
                    ("create_default_context", None),
                    ("load_verify_locations", str(ca_path)),
                    ("relax", None),
                ],
            )


if __name__ == "__main__":
    unittest.main()
