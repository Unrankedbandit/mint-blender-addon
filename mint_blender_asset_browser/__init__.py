"""Mint Asset Browser Blender extension entrypoint."""

from .ui import register, unregister

bl_info = {
    "name": "Mint Asset Browser",
    "author": "Mint",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Mint",
    "description": "Browse and import your Mint AI generated assets",
    "category": "Import-Export",
}
