"""State container for the Mint asset browser UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


AssetRecord = Dict[str, Any]


def _page_data(response: Dict[str, Any]) -> List[AssetRecord]:
    data = response.get("data", [])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _matches_search(asset: AssetRecord, query: str) -> bool:
    if not query:
        return True
    haystack = " ".join(
        str(asset.get(key, ""))
        for key in ["id", "name", "prompt", "status"]
    ).lower()
    return query.lower() in haystack


@dataclass
class AssetBrowserState:
    access_token: Optional[str] = None
    active_tab: str = "models"
    search: str = ""
    show_account_section: bool = True
    show_assets_section: bool = True
    status: str = "Disconnected"
    models: List[AssetRecord] = field(default_factory=list)
    worlds: List[AssetRecord] = field(default_factory=list)
    packs: List[AssetRecord] = field(default_factory=list)
    selected_pack_id: Optional[str] = None
    owner: Optional[AssetRecord] = None

    @property
    def connected(self) -> bool:
        return bool(self.access_token)

    def set_connected(self, access_token: str) -> None:
        self.access_token = access_token
        self.status = "Connected"

    def disconnect(self) -> None:
        self.access_token = None
        self.models = []
        self.worlds = []
        self.packs = []
        self.selected_pack_id = None
        self.owner = None
        self.status = "Disconnected"

    def refresh(self, client: Any, limit: int = 50) -> None:
        if not self.access_token:
            self.status = "Connect to Mint first"
            return

        self.owner = client.me(self.access_token)
        self.models = _page_data(client.list_models(self.access_token, limit=limit))
        self.worlds = _page_data(client.list_worlds(self.access_token, limit=limit))
        self.packs = _page_data(client.list_packs(self.access_token, limit=limit))
        if self.selected_pack_id and not self.selected_pack():
            self.selected_pack_id = None
        self.status = "Loaded %d models, %d worlds, and %d packs" % (
            len(self.models),
            len(self.worlds),
            len(self.packs),
        )

    def filtered_models(self) -> List[AssetRecord]:
        return [asset for asset in self.models if _matches_search(asset, self.search)]

    def filtered_worlds(self) -> List[AssetRecord]:
        return [asset for asset in self.worlds if _matches_search(asset, self.search)]

    def filtered_packs(self) -> List[AssetRecord]:
        return [asset for asset in self.packs if _matches_search(asset, self.search)]

    def selected_pack(self) -> Optional[AssetRecord]:
        if not self.selected_pack_id:
            return None
        for pack in self.packs:
            if pack.get("id") == self.selected_pack_id:
                return pack
        return None

    def pack_models(self, pack: Optional[AssetRecord] = None) -> List[AssetRecord]:
        source = pack if pack is not None else self.selected_pack()
        items = source.get("items") if isinstance(source, dict) else None
        if not isinstance(items, list):
            return []

        models: List[AssetRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            model = item.get("model")
            if isinstance(model, dict):
                models.append(model)
        return models

    def find_model(self, asset_id: str) -> Optional[AssetRecord]:
        for model in self.models:
            if model.get("id") == asset_id:
                return model
        for pack in self.packs:
            for model in self.pack_models(pack):
                if model.get("id") == asset_id:
                    return model
        return None

    def find_world(self, asset_id: str) -> Optional[AssetRecord]:
        for world in self.worlds:
            if world.get("id") == asset_id:
                return world
        return None
