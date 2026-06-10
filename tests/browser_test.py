import unittest

from mint_blender_asset_browser.browser import AssetBrowserState


class FakeClient:
    def me(self, access_token):
        return {"walletAddress": "0xAlice"}

    def list_models(self, access_token, limit=50, cursor=None):
        return {
            "data": [
                {
                    "id": "model_1",
                    "name": "Oak Chair",
                    "status": "succeeded",
                    "importSupported": True,
                },
                {
                    "id": "model_2",
                    "name": "Stone Table",
                    "status": "succeeded",
                    "importSupported": True,
                },
            ],
            "pagination": {"nextCursor": None, "hasMore": False},
        }

    def list_worlds(self, access_token, limit=50, cursor=None):
        return {
            "data": [
                {
                    "id": "world_1",
                    "name": "Gallery World",
                    "status": "succeeded",
                    "importSupported": False,
                }
            ],
            "pagination": {"nextCursor": None, "hasMore": False},
        }

    def list_packs(self, access_token, limit=50, cursor=None):
        return {
            "data": [
                {
                    "id": "pack_1",
                    "name": "Prop Kit",
                    "status": "succeeded",
                    "modelCount": 1,
                    "items": [
                        {
                            "id": "item_1",
                            "label": "Barrel",
                            "model": {
                                "id": "model_pack_1",
                                "name": "Barrel",
                                "status": "succeeded",
                                "importSupported": True,
                            },
                        }
                    ],
                }
            ],
            "pagination": {"nextCursor": None, "hasMore": False},
        }


class BrowserStateTest(unittest.TestCase):
    def test_refresh_loads_models_and_worlds(self):
        state = AssetBrowserState()
        state.set_connected("access_123")

        state.refresh(FakeClient())

        self.assertEqual(state.owner, {"walletAddress": "0xAlice"})
        self.assertEqual(len(state.models), 2)
        self.assertEqual(len(state.worlds), 1)
        self.assertEqual(len(state.packs), 1)
        self.assertEqual(state.status, "Loaded 2 models, 1 worlds, and 1 packs")

    def test_search_filters_current_assets(self):
        state = AssetBrowserState()
        state.set_connected("access_123")
        state.refresh(FakeClient())
        state.search = "oak"

        self.assertEqual([asset["id"] for asset in state.filtered_models()], ["model_1"])
        self.assertEqual(state.filtered_worlds(), [])
        self.assertEqual(state.filtered_packs(), [])

    def test_pack_models_are_import_lookup_candidates(self):
        state = AssetBrowserState()
        state.set_connected("access_123")
        state.refresh(FakeClient())

        state.selected_pack_id = "pack_1"

        self.assertEqual(state.selected_pack()["name"], "Prop Kit")
        self.assertEqual([model["id"] for model in state.pack_models()], ["model_pack_1"])
        self.assertEqual(state.find_model("model_pack_1")["name"], "Barrel")

    def test_worlds_are_import_lookup_candidates(self):
        state = AssetBrowserState()
        state.set_connected("access_123")
        state.refresh(FakeClient())

        self.assertEqual(state.find_world("world_1")["name"], "Gallery World")
        self.assertIsNone(state.find_world("missing"))

    def test_disconnect_clears_runtime_state(self):
        state = AssetBrowserState(access_token="access_123")
        state.models = [{"id": "model_1"}]
        state.worlds = [{"id": "world_1"}]
        state.packs = [{"id": "pack_1"}]
        state.selected_pack_id = "pack_1"

        state.disconnect()

        self.assertFalse(state.connected)
        self.assertEqual(state.models, [])
        self.assertEqual(state.worlds, [])
        self.assertEqual(state.packs, [])
        self.assertIsNone(state.selected_pack_id)
        self.assertEqual(state.status, "Disconnected")


if __name__ == "__main__":
    unittest.main()
