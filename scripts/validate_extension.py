#!/usr/bin/env python3
"""Validate the Mint Blender extension scaffold."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List

APP_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = APP_DIR / "mint_blender_asset_browser"

REQUIRED_MANIFEST_KEYS = [
    "schema_version",
    "id",
    "version",
    "name",
    "tagline",
    "maintainer",
    "type",
    "blender_version_min",
    "license",
]


def parse_value(value: str) -> Any:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        items = []
        inner = value[1:-1].strip()
        if not inner:
            return items
        for item in inner.split(","):
            item = item.strip()
            if item.startswith('"') and item.endswith('"'):
                item = item[1:-1]
            items.append(item)
        return items
    return value


def parse_manifest_text(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    section = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            result.setdefault(section, {})
            continue
        if "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        parsed = parse_value(value)
        if section:
            section_data = result.setdefault(section, {})
            if isinstance(section_data, dict):
                section_data[key] = parsed
        else:
            result[key] = parsed
    return result


def parse_manifest_file(path: Path) -> Dict[str, Any]:
    return parse_manifest_text(path.read_text(encoding="utf-8"))


def validate_manifest(manifest: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for key in REQUIRED_MANIFEST_KEYS:
        if key not in manifest:
            errors.append("manifest is missing %s" % key)

    if manifest.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    if manifest.get("type") != "add-on":
        errors.append("type must be add-on")
    if not re.match(r"^[a-z0-9_]+$", str(manifest.get("id", ""))):
        errors.append("id must contain only lowercase letters, numbers, and underscores")
    tagline = manifest.get("tagline")
    if isinstance(tagline, str) and tagline.endswith("."):
        errors.append("tagline should not end with punctuation")
    license_values = manifest.get("license")
    if not isinstance(license_values, list) or not license_values:
        errors.append("license must be a non-empty list")
    elif not all(str(value).startswith("SPDX:") for value in license_values):
        errors.append("license values must use the SPDX: prefix")

    permissions = manifest.get("permissions")
    if not isinstance(permissions, dict):
        errors.append("manifest must include permission reasons")
    else:
        for permission in ["network", "files"]:
            reason = permissions.get(permission)
            if not isinstance(reason, str) or not reason:
                errors.append("permission %s must include a reason" % permission)
            elif reason.endswith("."):
                errors.append("permission %s reason should not end with punctuation" % permission)

    return errors


def validate_source_tree(source_dir: Path = SOURCE_DIR) -> List[str]:
    errors: List[str] = []
    manifest_path = source_dir / "blender_manifest.toml"
    init_path = source_dir / "__init__.py"

    if not manifest_path.exists():
        errors.append("source tree is missing blender_manifest.toml")
    else:
        errors.extend(validate_manifest(parse_manifest_file(manifest_path)))
    if not init_path.exists():
        errors.append("source tree is missing __init__.py")
    return errors


def validate_zip_file(path: Path) -> List[str]:
    errors: List[str] = []
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "blender_manifest.toml" not in names:
            errors.append("package is missing blender_manifest.toml")
        if "__init__.py" not in names:
            errors.append("package is missing __init__.py")
        if "blender_manifest.toml" in names:
            text = archive.read("blender_manifest.toml").decode("utf-8")
            errors.extend(validate_manifest(parse_manifest_text(text)))
    return errors


def run_blender_validation(target: Path) -> int:
    blender = shutil.which("blender")
    if not blender:
        print("Blender executable not found; skipped official extension validation")
        return 0
    return subprocess.run(
        [blender, "--command", "extension", "validate", str(target)],
        check=False,
    ).returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path)
    parser.add_argument("--blender", action="store_true")
    args = parser.parse_args()

    target = args.package or SOURCE_DIR
    errors = (
        validate_zip_file(target)
        if target.suffix == ".zip"
        else validate_source_tree(target)
    )
    if errors:
        for error in errors:
            print("error: %s" % error, file=sys.stderr)
        return 1

    if args.blender:
        return run_blender_validation(target)

    print("Mint Blender extension scaffold is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
