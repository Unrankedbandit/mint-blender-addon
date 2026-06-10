import json
import math
import tempfile
import unittest
from pathlib import Path

from mint_blender_asset_browser.cache import AssetCache
from mint_blender_asset_browser.config import MintBlenderConfig
from mint_blender_asset_browser.kiri_bridge import (
    KiriBridgeUnavailableError,
    KiriInsightLog,
    KIRI_SPLAT_MODE_CAMERA,
    KIRI_SPLAT_MODE_DISABLE_UPDATES,
    KIRI_SPLAT_MODE_POINT_CLOUD,
    KIRI_SPLAT_MODE_RENDER,
    active_kiri_splat_object,
    activate_kiri_splat_object,
    current_kiri_splat_display_mode,
    current_kiri_splat_point_radius,
    create_kiri_insight_log,
    import_world_splat_with_kiri,
    kiri_ready,
    list_kiri_splat_objects,
    refine_kiri_splat_points,
    set_kiri_splat_display_mode,
    update_active_kiri_splat_view,
)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body


class FakeProps:
    def __init__(self):
        self.import_face_vert = None
        self.import_uv = None
        self.import_proxy = None
        self.active_mode = None
        self.edit_mode_menu = None
        self.r2_main_mode = None
        self.r2_sh_degree = 3


class FakeModifier:
    def __init__(self, name):
        self.name = name
        self.show_viewport = True
        self.values = {"Socket_51": 1.0}

    def __getitem__(self, key):
        return self.values[key]

    def __setitem__(self, key, value):
        self.values[key] = value


class FakeObjectProps:
    def __init__(self):
        self.update_mode = "Disable Camera Updates"
        self.cam_update = False


class FakeObject:
    def __init__(self, name, kiri=True):
        self.name = name
        self.modifiers = [FakeModifier("KIRI_3DGS_Render_GN")] if kiri else []
        self.values = {"3DGS_Mesh_Type": "3DGS"} if kiri else {}
        self.data = type("FakeMeshData", (), {"attributes": []})()
        self.sna_dgs_object_properties = FakeObjectProps()
        self.selected = False
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]

    def get(self, key):
        return self.values.get(key)

    def __setitem__(self, key, value):
        self.values[key] = value

    def select_set(self, selected):
        self.selected = selected


class FakeViewLayerObjects:
    def __init__(self):
        self.active = None


class FakeViewLayer:
    def __init__(self):
        self.objects = FakeViewLayerObjects()


class FakeScene:
    def __init__(self, with_props=True):
        self.objects = []
        if with_props:
            self.sna_dgs_scene_properties = FakeProps()


class FakeContext:
    def __init__(self, with_props=True):
        self.scene = FakeScene(with_props=with_props)
        self.selected_objects = []
        self.view_layer = FakeViewLayer()


class FakeSnaOps:
    def __init__(self, bpy_ref):
        self.bpy_ref = bpy_ref
        self.imports = []
        self.selected_names = []
        self.align_calls = 0

    def dgs_render_import_ply_e0a3a(self, filepath):
        self.imports.append(filepath)
        imported = FakeObject("Kiri Import")
        self.bpy_ref.context.scene.objects.append(imported)
        self.bpy_ref.context.selected_objects = [imported]
        return {"FINISHED"}

    def dgs_render_select_object_b1f49(self, sna_object_name):
        self.selected_names.append(sna_object_name)
        for obj in self.bpy_ref.context.scene.objects:
            obj.select_set(False)
            if obj.name == sna_object_name:
                self.bpy_ref.context.view_layer.objects.active = obj
                obj.select_set(True)
                self.bpy_ref.context.selected_objects = [obj]
                return {"FINISHED"}
        return {"CANCELLED"}

    def dgs_render_align_active_to_view_30b13(self):
        self.align_calls += 1
        return {"FINISHED"}


class FakeOps:
    def __init__(self, bpy_ref, with_operator=True):
        if with_operator:
            self.sna = FakeSnaOps(bpy_ref)
        else:
            self.sna = object()


class FakeBpy:
    def __init__(self, with_props=True, with_operator=True):
        self.context = FakeContext(with_props=with_props)
        self.ops = FakeOps(self, with_operator=with_operator)


class FakeClient:
    def __init__(self, import_url="https://cdn.mint.gg/exports/blender/worlds/gallery-hash.ply"):
        self.exports = []
        self.import_url = import_url

    def export_world_ply(self, access_token, world_id):
        self.exports.append((access_token, world_id))
        return {
            "object": "world_splat_export",
            "worldId": world_id,
            "format": "ply",
            "importUrl": self.import_url,
        }


class KiriBridgeTest(unittest.TestCase):
    def test_kiri_ready_requires_scene_props_and_import_operator(self):
        self.assertTrue(kiri_ready(FakeBpy()))
        self.assertFalse(kiri_ready(FakeBpy(with_props=False)))
        self.assertFalse(kiri_ready(FakeBpy(with_operator=False)))

    def test_import_world_exports_downloads_caches_and_dispatches_to_kiri(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_bpy = FakeBpy()
            signed_url = "https://cdn.mint.gg/exports/blender/worlds/gallery-hash.ply?token=secret#fragment"
            client = FakeClient(signed_url)
            requests = []

            def urlopen(request, **kwargs):
                requests.append((request, kwargs))
                return FakeResponse(b"ply-bytes")

            path = import_world_splat_with_kiri(
                {"id": "world_1", "name": "  Gallery   World  "},
                "access_123",
                client,
                AssetCache(Path(tmp)),
                config=MintBlenderConfig(),
                urlopen=urlopen,
                bpy_module=fake_bpy,
                insight_log=KiriInsightLog(Path(tmp) / "kiri.log"),
            )

            log_entries = [
                json.loads(line)
                for line in (Path(tmp) / "kiri.log").read_text(encoding="utf-8").splitlines()
            ]
            log_events = [entry["event"] for entry in log_entries]
            export_log = next(entry for entry in log_entries if entry["event"] == "mint_export_request_done")
            download_log = next(entry for entry in log_entries if entry["event"] == "ply_download_start")
            props = fake_bpy.context.scene.sna_dgs_scene_properties
            self.assertEqual(client.exports, [("access_123", "world_1")])
            self.assertEqual(path.read_bytes(), b"ply-bytes")
            self.assertIn("world_splat_import_start", log_events)
            self.assertIn("mint_export_request_start", log_events)
            self.assertIn("ply_download_done", log_events)
            self.assertIn("kiri_operator_start", log_events)
            self.assertIn("kiri_render_preview_config", log_events)
            self.assertIn("kiri_orientation_correction_done", log_events)
            self.assertIn("kiri_camera_update_mode_start", log_events)
            self.assertIn("world_splat_import_done", log_events)
            self.assertEqual(
                [request.full_url for request, _kwargs in requests],
                [signed_url],
            )
            self.assertEqual(requests[0][1]["timeout"], 30)
            self.assertEqual(requests[0][0].get_header("Accept"), "application/octet-stream, */*")
            self.assertEqual(
                export_log["importUrl"],
                "https://cdn.mint.gg/exports/blender/worlds/gallery-hash.ply",
            )
            self.assertEqual(
                download_log["url"],
                "https://cdn.mint.gg/exports/blender/worlds/gallery-hash.ply",
            )
            self.assertNotIn("secret", json.dumps(log_entries))
            self.assertEqual(props.import_face_vert, "Verts")
            self.assertEqual(props.import_uv, False)
            self.assertEqual(props.import_proxy, True)
            self.assertEqual(props.r2_sh_degree, 0)
            self.assertIsNone(props.r2_main_mode)
            self.assertEqual(props.active_mode, "Edit")
            self.assertEqual(props.edit_mode_menu, "Import")
            self.assertEqual(
                fake_bpy.context.scene.objects[0].sna_dgs_object_properties.update_mode,
                "Enable Camera Updates",
            )
            self.assertAlmostEqual(
                fake_bpy.context.scene.objects[0].rotation_euler[0],
                -math.pi / 2,
            )
            self.assertEqual(fake_bpy.context.scene.objects[0].scale, [2.5, 2.5, 2.5])
            self.assertEqual(
                fake_bpy.context.scene.objects[0].values["mint_world_id"],
                "world_1",
            )
            self.assertEqual(
                fake_bpy.context.scene.objects[0].values["mint_world_name"],
                "Gallery World",
            )
            self.assertEqual(
                fake_bpy.ops.sna.imports,
                [str(path)],
            )
            self.assertEqual(fake_bpy.context.scene.objects[0].name, "Gallery World")
            self.assertEqual(fake_bpy.context.view_layer.objects.active.name, "Gallery World")

    def test_import_world_reuses_cached_ply(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_bpy = FakeBpy()
            client = FakeClient()
            cache = AssetCache(Path(tmp))
            import_url = "https://cdn.mint.gg/exports/blender/worlds/gallery-hash.ply"
            cached = cache.write_bytes("world_1", import_url, b"cached", ".ply")

            path = import_world_splat_with_kiri(
                {"id": "world_1", "name": "Gallery"},
                "access_123",
                client,
                cache,
                config=MintBlenderConfig(),
                urlopen=lambda request: self.fail("cache hit should not download"),
                bpy_module=fake_bpy,
                insight_log=KiriInsightLog(Path(tmp) / "kiri.log"),
            )

            self.assertEqual(path, cached)
            self.assertEqual(path.read_bytes(), b"cached")
            self.assertEqual(fake_bpy.ops.sna.imports, [str(cached)])

    def test_import_world_requires_kiri_before_exporting(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient()
            with self.assertRaises(KiriBridgeUnavailableError):
                import_world_splat_with_kiri(
                    {"id": "world_1", "name": "Gallery"},
                    "access_123",
                    client,
                    AssetCache(Path(tmp)),
                    bpy_module=FakeBpy(with_operator=False),
                    insight_log=KiriInsightLog(Path(tmp) / "kiri.log"),
                )

            self.assertEqual(client.exports, [])

    def test_lists_and_activates_kiri_splat_objects(self):
        fake_bpy = FakeBpy()
        banana = FakeObject("Banana")
        apple = FakeObject("Apple")
        plain = FakeObject("Plain Cube", kiri=False)
        fake_bpy.context.scene.objects = [banana, plain, apple]

        self.assertEqual(
            [obj.name for obj in list_kiri_splat_objects(fake_bpy)],
            ["Apple", "Banana"],
        )
        self.assertIsNone(active_kiri_splat_object(fake_bpy))

        activated = activate_kiri_splat_object("Banana", fake_bpy)

        self.assertIs(activated, banana)
        self.assertEqual(fake_bpy.ops.sna.selected_names, ["Banana"])
        self.assertIs(active_kiri_splat_object(fake_bpy), banana)
        self.assertTrue(banana.selected)
        self.assertFalse(apple.selected)

    def test_set_kiri_splat_display_mode_maps_to_kiri_props(self):
        fake_bpy = FakeBpy()
        splat = FakeObject("Gallery")
        fake_bpy.context.scene.objects = [splat]

        set_kiri_splat_display_mode("Gallery", KIRI_SPLAT_MODE_POINT_CLOUD, fake_bpy)

        props = fake_bpy.context.scene.sna_dgs_scene_properties
        self.assertEqual(props.active_mode, "Edit")
        self.assertEqual(props.edit_mode_menu, "Import")
        self.assertEqual(splat.sna_dgs_object_properties.update_mode, "Show As Point Cloud")
        self.assertEqual(current_kiri_splat_display_mode(splat, fake_bpy), KIRI_SPLAT_MODE_POINT_CLOUD)

        set_kiri_splat_display_mode("Gallery", KIRI_SPLAT_MODE_CAMERA, fake_bpy)

        self.assertEqual(props.active_mode, "Edit")
        self.assertEqual(splat.sna_dgs_object_properties.update_mode, "Enable Camera Updates")
        self.assertEqual(current_kiri_splat_display_mode(splat, fake_bpy), KIRI_SPLAT_MODE_CAMERA)

        set_kiri_splat_display_mode("Gallery", KIRI_SPLAT_MODE_DISABLE_UPDATES, fake_bpy)

        self.assertEqual(props.active_mode, "Edit")
        self.assertEqual(splat.sna_dgs_object_properties.update_mode, "Disable Camera Updates")
        self.assertEqual(current_kiri_splat_display_mode(splat, fake_bpy), KIRI_SPLAT_MODE_DISABLE_UPDATES)

        set_kiri_splat_display_mode("Gallery", KIRI_SPLAT_MODE_RENDER, fake_bpy)

        self.assertEqual(props.r2_main_mode, "Update")
        self.assertEqual(props.active_mode, "Render")
        self.assertEqual(current_kiri_splat_display_mode(splat, fake_bpy), KIRI_SPLAT_MODE_RENDER)

    def test_refine_kiri_splat_points_halves_point_radius(self):
        fake_bpy = FakeBpy()
        splat = FakeObject("Gallery")
        fake_bpy.context.scene.objects = [splat]

        refine_kiri_splat_points("Gallery", fake_bpy)

        self.assertEqual(current_kiri_splat_point_radius(splat), 0.5)

    def test_update_active_kiri_splat_view_uses_kiri_operator(self):
        fake_bpy = FakeBpy()

        update_active_kiri_splat_view(fake_bpy)

        self.assertEqual(fake_bpy.ops.sna.align_calls, 1)

    def test_update_active_kiri_splat_view_requires_operator(self):
        fake_bpy = FakeBpy()
        fake_bpy.ops.sna.dgs_render_align_active_to_view_30b13 = None

        with self.assertRaises(KiriBridgeUnavailableError):
            update_active_kiri_splat_view(fake_bpy)

    def test_kiri_log_echo_is_env_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            import os

            previous = os.environ.pop("MINT_BLENDER_KIRI_LOG_ECHO", None)
            try:
                config = MintBlenderConfig(cache_dir=Path(tmp))
                self.assertFalse(create_kiri_insight_log(config).echo)

                os.environ["MINT_BLENDER_KIRI_LOG_ECHO"] = "1"
                self.assertTrue(create_kiri_insight_log(config).echo)
            finally:
                if previous is None:
                    os.environ.pop("MINT_BLENDER_KIRI_LOG_ECHO", None)
                else:
                    os.environ["MINT_BLENDER_KIRI_LOG_ECHO"] = previous


if __name__ == "__main__":
    unittest.main()
