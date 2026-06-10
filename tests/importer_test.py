import tempfile
import unittest
from pathlib import Path

from mint_blender_asset_browser.cache import AssetCache
from mint_blender_asset_browser.importer import (
    ImportUnsupportedError,
    import_model_asset,
)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body


class FakeNamed:
    def __init__(self, name, materials=None):
        self.name = name
        self.materials = materials or []


class FakeMaterialSlot:
    def __init__(self, material):
        self.material = material


class FakeObject:
    def __init__(self, name, data=None, materials=None):
        self.name = name
        self.data = data
        self.material_slots = [FakeMaterialSlot(material) for material in materials or []]


class FakeScene:
    def __init__(self, objects=None):
        self.objects = list(objects or [])


class FakeContext:
    def __init__(self, objects=None):
        self.scene = FakeScene(objects)
        self.selected_objects = []


class FakeBpy:
    def __init__(self, imported_objects=None, existing_objects=None):
        self.imports = []
        self.imported_objects = list(imported_objects or [])
        self.context = FakeContext(existing_objects)
        self.ops = self
        self.import_scene = self

    def gltf(self, filepath):
        self.imports.append(filepath)
        self.context.scene.objects.extend(self.imported_objects)
        self.context.selected_objects = list(self.imported_objects)


class ImporterTest(unittest.TestCase):
    def test_import_model_downloads_cached_glb_and_dispatches_blender_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = AssetCache(Path(tmp))
            fake_bpy = FakeBpy()
            requested = []

            def urlopen(request, **kwargs):
                requested.append((request, kwargs))
                return FakeResponse(b"glb-bytes")

            path = import_model_asset(
                {
                    "id": "model_1",
                    "importSupported": True,
                    "importUrl": "https://cdn.mint.gg/model.glb",
                },
                cache,
                urlopen=urlopen,
                bpy_module=fake_bpy,
            )

            self.assertTrue(path.exists())
            self.assertEqual(path.read_bytes(), b"glb-bytes")
            self.assertEqual([request.full_url for request, _kwargs in requested], ["https://cdn.mint.gg/model.glb"])
            self.assertEqual(requested[0][1]["timeout"], 30)
            self.assertEqual(requested[0][0].get_header("User-agent"), "MintBlenderAssetBrowser/0.1.0")
            self.assertEqual(
                requested[0][0].get_header("Accept"),
                "model/gltf-binary, application/octet-stream, */*",
            )
            self.assertEqual(fake_bpy.imports, [str(path)])

    def test_import_model_reuses_cached_glb(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = AssetCache(Path(tmp))
            fake_bpy = FakeBpy()
            cache.write_bytes("model_1", "https://cdn.mint.gg/model.glb", b"cached")

            path = import_model_asset(
                {
                    "id": "model_1",
                    "importSupported": True,
                    "importUrl": "https://cdn.mint.gg/model.glb",
                },
                cache,
                urlopen=lambda url: self.fail("cache hit should not download"),
                bpy_module=fake_bpy,
            )

            self.assertEqual(path.read_bytes(), b"cached")
            self.assertEqual(fake_bpy.imports, [str(path)])

    def test_import_model_renames_imported_objects_with_mint_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = AssetCache(Path(tmp))
            material = FakeNamed("tripo_material_5bbc56f3")
            mesh = FakeNamed("tripo_mesh_5bbc56f3", materials=[material])
            imported = FakeObject("tripo_node_5bbc56f3", data=mesh, materials=[material])
            fake_bpy = FakeBpy(imported_objects=[imported])

            import_model_asset(
                {
                    "id": "model_1",
                    "name": "  Heavy   Gunner  ",
                    "importSupported": True,
                    "importUrl": "https://cdn.mint.gg/model.glb",
                },
                cache,
                urlopen=lambda request, **kwargs: FakeResponse(b"glb-bytes"),
                bpy_module=fake_bpy,
            )

            self.assertEqual(imported.name, "Heavy Gunner")
            self.assertEqual(mesh.name, "Heavy Gunner Mesh")
            self.assertEqual(material.name, "Heavy Gunner Material")

    def test_import_model_suffixes_multiple_imported_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = AssetCache(Path(tmp))
            first_mesh = FakeNamed("tripo_mesh_first")
            second_mesh = FakeNamed("tripo_mesh_second")
            first = FakeObject("tripo_node_first", data=first_mesh)
            second = FakeObject("tripo_node_second", data=second_mesh)
            fake_bpy = FakeBpy(imported_objects=[first, second])

            import_model_asset(
                {
                    "id": "model_1",
                    "name": "Scout Pilot",
                    "importSupported": True,
                    "importUrl": "https://cdn.mint.gg/model.glb",
                },
                cache,
                urlopen=lambda request, **kwargs: FakeResponse(b"glb-bytes"),
                bpy_module=fake_bpy,
            )

            self.assertEqual(first.name, "Scout Pilot 01")
            self.assertEqual(second.name, "Scout Pilot 02")
            self.assertEqual(first_mesh.name, "Scout Pilot Mesh 01")
            self.assertEqual(second_mesh.name, "Scout Pilot Mesh 02")

    def test_import_model_rejects_non_importable_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ImportUnsupportedError):
                import_model_asset(
                    {
                        "id": "model_raw",
                        "importSupported": False,
                        "importUrl": None,
                    },
                    AssetCache(Path(tmp)),
                    bpy_module=FakeBpy(),
                )


if __name__ == "__main__":
    unittest.main()
