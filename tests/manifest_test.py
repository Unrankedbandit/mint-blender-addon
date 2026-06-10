import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.package_extension import iter_package_files
from scripts.validate_extension import (
    SOURCE_DIR,
    parse_manifest_file,
    validate_manifest,
    validate_source_tree,
    validate_zip_file,
)


class ManifestTest(unittest.TestCase):
    def test_manifest_declares_blender_extension_metadata(self):
        manifest = parse_manifest_file(SOURCE_DIR / "blender_manifest.toml")

        self.assertEqual(validate_manifest(manifest), [])
        self.assertEqual(manifest["schema_version"], "1.0.0")
        self.assertEqual(manifest["type"], "add-on")
        self.assertEqual(manifest["id"], "mint_blender_asset_browser")
        self.assertEqual(manifest["permissions"]["network"].endswith("."), False)

    def test_source_tree_has_required_extension_files(self):
        self.assertEqual(validate_source_tree(SOURCE_DIR), [])

    def test_public_repo_hygiene_files_exist(self):
        app_dir = SOURCE_DIR.parent

        self.assertTrue((app_dir / "README.md").exists())
        self.assertTrue((app_dir / "CHANGELOG.md").exists())
        self.assertTrue((app_dir / "LICENSE").exists())
        self.assertTrue((app_dir / ".gitignore").exists())

    def test_package_file_iterator_excludes_bytecode(self):
        names = {path.name for path in iter_package_files(SOURCE_DIR)}

        self.assertIn("__init__.py", names)
        self.assertIn("blender_manifest.toml", names)
        self.assertNotIn("__pycache__", names)

    def test_zip_validation_requires_manifest_and_entrypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extension.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.write(
                    SOURCE_DIR / "blender_manifest.toml",
                    "blender_manifest.toml",
                )
                archive.write(SOURCE_DIR / "__init__.py", "__init__.py")

            self.assertEqual(validate_zip_file(path), [])


if __name__ == "__main__":
    unittest.main()
