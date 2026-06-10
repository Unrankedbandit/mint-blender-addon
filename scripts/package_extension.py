#!/usr/bin/env python3
"""Build the Mint Blender extension zip package."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
APP_DIR = SCRIPT_DIR.parent
SOURCE_DIR = APP_DIR / "mint_blender_asset_browser"
DIST_DIR = APP_DIR / "dist"

sys.path.insert(0, str(SCRIPT_DIR))
from validate_extension import parse_manifest_file, validate_source_tree, validate_zip_file  # noqa: E402


def iter_package_files(source_dir: Path):
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        yield path


def main() -> int:
    errors = validate_source_tree(SOURCE_DIR)
    if errors:
        for error in errors:
            print("error: %s" % error, file=sys.stderr)
        return 1

    manifest = parse_manifest_file(SOURCE_DIR / "blender_manifest.toml")
    package_path = DIST_DIR / (
        "%s-%s.zip" % (manifest["id"], manifest["version"])
    )
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in iter_package_files(SOURCE_DIR):
            archive.write(path, path.relative_to(SOURCE_DIR).as_posix())

    errors = validate_zip_file(package_path)
    if errors:
        for error in errors:
            print("error: %s" % error, file=sys.stderr)
        return 1

    print(package_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
