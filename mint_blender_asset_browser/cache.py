"""Durable local asset cache helpers."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return safe or "asset"


class AssetCache:
    def __init__(self, root: Path):
        self.root = root

    def path_for(self, asset_id: str, url: str, extension: str = ".glb") -> Path:
        suffix = extension if extension.startswith(".") else ".%s" % extension
        fingerprint = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        filename = "%s-%s%s" % (_safe_name(asset_id), fingerprint, suffix)
        return self.root / filename

    def write_bytes(self, asset_id: str, url: str, data: bytes, extension: str = ".glb") -> Path:
        path = self.path_for(asset_id, url, extension)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def exists(self, asset_id: str, url: str, extension: str = ".glb") -> bool:
        return self.path_for(asset_id, url, extension).exists()
