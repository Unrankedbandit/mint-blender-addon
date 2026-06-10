"""Kiri 3DGS bridge for Mint world splats."""

from __future__ import annotations

import json
import math
import os
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .cache import AssetCache
from .client import MintBlenderClient
from .config import MintBlenderConfig
from .http import urlopen_with_config

UrlOpen = Callable[..., Any]


class KiriBridgeError(RuntimeError):
    pass


class KiriBridgeUnavailableError(KiriBridgeError):
    pass


class KiriImportError(KiriBridgeError):
    pass


KIRI_SPLAT_MODE_RENDER = "RENDER"
KIRI_SPLAT_MODE_DISABLE_UPDATES = "DISABLE_UPDATES"
KIRI_SPLAT_MODE_POINT_CLOUD = "POINT_CLOUD"
KIRI_SPLAT_MODE_CAMERA = "CAMERA"
KIRI_SPLAT_MODES = {
    KIRI_SPLAT_MODE_RENDER,
    KIRI_SPLAT_MODE_DISABLE_UPDATES,
    KIRI_SPLAT_MODE_POINT_CLOUD,
    KIRI_SPLAT_MODE_CAMERA,
}
KIRI_RENDER_MODIFIER_NAME = "KIRI_3DGS_Render_GN"
KIRI_POINT_RADIUS_SOCKET = "Socket_51"
MINT_KIRI_X_ROTATION_CORRECTION_RADIANS = -math.pi / 2
MINT_KIRI_IMPORT_SCALE_FACTOR = 2.5
MINT_KIRI_WORLD_ID_PROP = "mint_world_id"
MINT_KIRI_WORLD_NAME_PROP = "mint_world_name"


class KiriInsightLog:
    def __init__(self, path: Path, echo: bool = False):
        self.path = path
        self.echo = echo

    def log(self, event: str, **fields: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": event,
            **{key: _jsonable(_redact_log_field(key, value)) for key, value in fields.items()},
        }
        line = json.dumps(entry, sort_keys=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write("%s\n" % line)
            handle.flush()
            os.fsync(handle.fileno())
        if self.echo:
            print("[mint-blender:kiri] %s" % line)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return str(value)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _redact_url_query(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _redact_log_field(key: str, value: Any) -> Any:
    if isinstance(value, str) and key.lower().endswith("url"):
        return _redact_url_query(value)
    return value


def kiri_insight_log_path(config: MintBlenderConfig) -> Path:
    return config.cache_dir / "logs" / "kiri-bridge.log"


def create_kiri_insight_log(config: MintBlenderConfig, echo: bool = False) -> KiriInsightLog:
    return KiriInsightLog(
        kiri_insight_log_path(config),
        echo=echo or _env_flag("MINT_BLENDER_KIRI_LOG_ECHO"),
    )


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _load_bpy() -> Any:
    try:
        import bpy  # type: ignore
    except ImportError as error:
        raise RuntimeError("Blender bpy module is not available") from error
    return bpy


def _clean_asset_name(name: Any) -> Optional[str]:
    if not isinstance(name, str):
        return None

    cleaned = " ".join(name.split()).strip()
    return cleaned[:80] if cleaned else None


def _read_ply_url(url: str, config: MintBlenderConfig, urlopen: Optional[UrlOpen]) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream, */*",
            "User-Agent": "MintBlenderAssetBrowser/0.1.0",
        },
        method="GET",
    )
    response = urlopen_with_config(request, config, urlopen, timeout=30)
    return response.read()


def _scene_objects(bpy_ref: Any) -> list[Any]:
    context = getattr(bpy_ref, "context", None)
    scene = getattr(context, "scene", None)
    objects = getattr(scene, "objects", None)
    return list(objects) if objects is not None else []


def _selected_objects(bpy_ref: Any) -> list[Any]:
    context = getattr(bpy_ref, "context", None)
    selected = getattr(context, "selected_objects", None)
    return list(selected) if selected is not None else []


def _imported_objects_after(bpy_ref: Any, before_ids: set[int]) -> list[Any]:
    after = _scene_objects(bpy_ref)
    imported = [obj for obj in after if id(obj) not in before_ids]
    return imported or _selected_objects(bpy_ref)


def _operator_namespace(bpy_ref: Any) -> Any:
    return getattr(getattr(bpy_ref, "ops", None), "sna", None)


def kiri_ready(bpy_module: Optional[Any] = None) -> bool:
    bpy_ref = bpy_module or _load_bpy()
    scene = getattr(getattr(bpy_ref, "context", None), "scene", None)
    ops = _operator_namespace(bpy_ref)
    return bool(
        hasattr(scene, "sna_dgs_scene_properties")
        and hasattr(ops, "dgs_render_import_ply_e0a3a")
    )


def _set_prop(props: Any, name: str, value: Any) -> None:
    if hasattr(props, name):
        setattr(props, name, value)


def _configure_kiri_import(bpy_ref: Any) -> None:
    scene = getattr(getattr(bpy_ref, "context", None), "scene", None)
    props = getattr(scene, "sna_dgs_scene_properties", None)
    if props is None:
        raise KiriBridgeUnavailableError(
            "Install and enable KIRI Engine 3DGS Render to import worlds"
        )

    _set_prop(props, "import_face_vert", "Verts")
    _set_prop(props, "import_uv", False)
    _set_prop(props, "import_proxy", True)
    _set_prop(props, "active_mode", "Edit")
    _set_prop(props, "edit_mode_menu", "Import")


def _object_custom_value(obj: Any, key: str) -> Any:
    getter = getattr(obj, "get", None)
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            return None
    return None


def _set_object_custom_value(obj: Any, key: str, value: Any) -> None:
    try:
        obj[key] = value
        return
    except Exception:
        pass

    values = getattr(obj, "values", None)
    if isinstance(values, dict):
        values[key] = value


def _has_kiri_modifier(obj: Any) -> bool:
    for modifier in list(getattr(obj, "modifiers", None) or []):
        name = getattr(modifier, "name", "")
        if name == KIRI_RENDER_MODIFIER_NAME:
            return True
    return False


def _is_kiri_object(obj: Any) -> bool:
    return (
        _object_custom_value(obj, "3DGS_Mesh_Type") is not None
        or _has_kiri_modifier(obj)
    )


def list_kiri_splat_objects(bpy_module: Optional[Any] = None) -> list[Any]:
    bpy_ref = bpy_module or _load_bpy()
    objects = [obj for obj in _scene_objects(bpy_ref) if _is_kiri_object(obj)]
    return sorted(objects, key=lambda obj: str(getattr(obj, "name", "")).lower())


def active_kiri_splat_object(bpy_module: Optional[Any] = None) -> Optional[Any]:
    bpy_ref = bpy_module or _load_bpy()
    active = getattr(getattr(getattr(bpy_ref, "context", None), "view_layer", None), "objects", None)
    active_object = getattr(active, "active", None)
    return active_object if active_object is not None and _is_kiri_object(active_object) else None


def _find_kiri_splat_object(name: str, bpy_ref: Any) -> Any:
    for obj in list_kiri_splat_objects(bpy_ref):
        if str(getattr(obj, "name", "")) == name:
            return obj
    raise KiriImportError("Kiri splat not found: %s" % name)


def activate_kiri_splat_object(name: str, bpy_module: Optional[Any] = None) -> Any:
    bpy_ref = bpy_module or _load_bpy()
    obj = _find_kiri_splat_object(name, bpy_ref)
    ops = _operator_namespace(bpy_ref)
    select_op = getattr(ops, "dgs_render_select_object_b1f49", None)
    if callable(select_op):
        try:
            result = select_op(sna_object_name=str(getattr(obj, "name", name)))
            if result and "CANCELLED" in result:
                _set_active_object(bpy_ref, obj)
        except Exception:
            _set_active_object(bpy_ref, obj)
    else:
        _set_active_object(bpy_ref, obj)
    return obj


def _object_kiri_props(obj: Any) -> Any:
    return getattr(obj, "sna_dgs_object_properties", None)


def _set_kiri_object_update_mode(obj: Any, update_mode: str) -> None:
    props = _object_kiri_props(obj)
    if props is not None and hasattr(props, "update_mode"):
        setattr(props, "update_mode", update_mode)


def _set_kiri_object_camera_update(obj: Any, enabled: bool) -> None:
    props = _object_kiri_props(obj)
    if props is not None and hasattr(props, "cam_update"):
        setattr(props, "cam_update", enabled)


def kiri_splat_render_modifier(obj: Any) -> Optional[Any]:
    modifiers = getattr(obj, "modifiers", None)
    getter = getattr(modifiers, "get", None)
    if callable(getter):
        try:
            modifier = getter(KIRI_RENDER_MODIFIER_NAME)
            if modifier is not None:
                return modifier
        except Exception:
            pass

    for modifier in list(modifiers or []):
        if getattr(modifier, "name", None) == KIRI_RENDER_MODIFIER_NAME:
            return modifier
    return None


def _modifier_custom_value(modifier: Any, key: str) -> Any:
    try:
        return modifier[key]
    except Exception:
        return None


def _set_modifier_custom_value(modifier: Any, key: str, value: Any) -> None:
    try:
        modifier[key] = value
        return
    except Exception:
        pass

    values = getattr(modifier, "values", None)
    if isinstance(values, dict):
        values[key] = value


def current_kiri_splat_point_radius(obj: Any) -> Optional[float]:
    modifier = kiri_splat_render_modifier(obj)
    if modifier is None:
        return None
    value = _modifier_custom_value(modifier, KIRI_POINT_RADIUS_SOCKET)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def set_kiri_splat_point_radius(
    name: str,
    radius: float,
    bpy_module: Optional[Any] = None,
) -> Any:
    bpy_ref = bpy_module or _load_bpy()
    obj = activate_kiri_splat_object(name, bpy_ref)
    modifier = kiri_splat_render_modifier(obj)
    if modifier is None:
        raise KiriImportError("Kiri point radius control is unavailable")

    _set_modifier_custom_value(modifier, KIRI_POINT_RADIUS_SOCKET, max(0.001, float(radius)))
    update_tag = getattr(obj, "update_tag", None)
    if callable(update_tag):
        update_tag(refresh={"OBJECT"})
    return obj


def refine_kiri_splat_points(
    name: str,
    bpy_module: Optional[Any] = None,
) -> Any:
    bpy_ref = bpy_module or _load_bpy()
    obj = activate_kiri_splat_object(name, bpy_ref)
    current = current_kiri_splat_point_radius(obj)
    radius = current * 0.5 if current and current > 0 else 0.5
    return set_kiri_splat_point_radius(name, radius, bpy_ref)


def _kiri_scene_props(bpy_ref: Any) -> Any:
    scene = getattr(getattr(bpy_ref, "context", None), "scene", None)
    return getattr(scene, "sna_dgs_scene_properties", None)


def _set_kiri_scene_active_mode(bpy_ref: Any, active_mode: str) -> None:
    props = _kiri_scene_props(bpy_ref)
    if props is not None:
        _set_prop(props, "active_mode", active_mode)


def _set_kiri_scene_edit_menu(bpy_ref: Any) -> None:
    props = _kiri_scene_props(bpy_ref)
    if props is not None:
        _set_prop(props, "edit_mode_menu", "Import")


def set_kiri_splat_display_mode(
    name: str,
    mode: str,
    bpy_module: Optional[Any] = None,
) -> Any:
    if mode not in KIRI_SPLAT_MODES:
        raise KiriImportError("Unsupported Kiri splat mode: %s" % mode)

    bpy_ref = bpy_module or _load_bpy()
    obj = activate_kiri_splat_object(name, bpy_ref)

    if mode == KIRI_SPLAT_MODE_RENDER:
        props = _kiri_scene_props(bpy_ref)
        if props is not None:
            _set_prop(props, "r2_main_mode", "Update")
            _set_prop(props, "active_mode", "Render")
        return obj

    _set_kiri_scene_active_mode(bpy_ref, "Edit")
    _set_kiri_scene_edit_menu(bpy_ref)
    if mode == KIRI_SPLAT_MODE_DISABLE_UPDATES:
        _set_kiri_object_camera_update(obj, False)
        _set_kiri_object_update_mode(obj, "Disable Camera Updates")
    elif mode == KIRI_SPLAT_MODE_POINT_CLOUD:
        _set_kiri_object_camera_update(obj, False)
        _set_kiri_object_update_mode(obj, "Show As Point Cloud")
    elif mode == KIRI_SPLAT_MODE_CAMERA:
        _set_kiri_object_update_mode(obj, "Enable Camera Updates")
    return obj


def current_kiri_splat_display_mode(obj: Any, bpy_module: Optional[Any] = None) -> str:
    bpy_ref = bpy_module or _load_bpy()
    scene_props = _kiri_scene_props(bpy_ref)
    if getattr(scene_props, "active_mode", None) == "Render":
        return KIRI_SPLAT_MODE_RENDER

    object_props = _object_kiri_props(obj)
    update_mode = getattr(object_props, "update_mode", None)
    if update_mode == "Disable Camera Updates":
        return KIRI_SPLAT_MODE_DISABLE_UPDATES
    if update_mode == "Show As Point Cloud":
        return KIRI_SPLAT_MODE_POINT_CLOUD
    if update_mode == "Enable Camera Updates":
        return KIRI_SPLAT_MODE_CAMERA
    return KIRI_SPLAT_MODE_RENDER


def update_active_kiri_splat_view(
    bpy_module: Optional[Any] = None,
    context_override: Optional[dict[str, Any]] = None,
) -> None:
    bpy_ref = bpy_module or _load_bpy()
    ops = _operator_namespace(bpy_ref)
    align_op = getattr(ops, "dgs_render_align_active_to_view_30b13", None)
    if not callable(align_op):
        raise KiriBridgeUnavailableError("Kiri view update is unavailable")
    context = getattr(bpy_ref, "context", None)
    temp_override = getattr(context, "temp_override", None)
    if context_override and callable(temp_override):
        with temp_override(**context_override):
            result = align_op()
    else:
        result = align_op()
    if result and "CANCELLED" in result:
        raise KiriImportError("Kiri view update cancelled")


def _attribute_names(obj: Any) -> list[str]:
    attributes = getattr(getattr(obj, "data", None), "attributes", None)
    if attributes is None:
        return []
    if isinstance(attributes, dict):
        return [str(name) for name in attributes.keys()]

    names = []
    for attribute in list(attributes):
        name = getattr(attribute, "name", None)
        if isinstance(name, str):
            names.append(name)
    return names


def _has_sh_rest_attributes(obj: Any) -> bool:
    return any(name.startswith("f_rest_") for name in _attribute_names(obj))


def _set_active_object(bpy_ref: Any, obj: Any) -> None:
    view_layer = getattr(getattr(bpy_ref, "context", None), "view_layer", None)
    objects = getattr(view_layer, "objects", None)
    if objects is not None and hasattr(objects, "active"):
        objects.active = obj

    select_set = getattr(obj, "select_set", None)
    if callable(select_set):
        select_set(True)


def _configure_kiri_render_preview(
    bpy_ref: Any,
    imported_objects: list[Any],
    insight_log: Optional[KiriInsightLog] = None,
) -> None:
    scene = getattr(getattr(bpy_ref, "context", None), "scene", None)
    props = getattr(scene, "sna_dgs_scene_properties", None)
    if props is None:
        return

    kiri_objects = [obj for obj in imported_objects if _is_kiri_object(obj)]
    active_object = kiri_objects[0] if kiri_objects else (imported_objects[0] if imported_objects else None)
    if active_object is not None:
        _set_active_object(bpy_ref, active_object)

    has_sh_rest = _has_sh_rest_attributes(active_object) if active_object is not None else False
    if not has_sh_rest:
        _set_prop(props, "r2_sh_degree", 0)

    if insight_log:
        insight_log.log(
            "kiri_render_preview_config",
            activeObjectName=getattr(active_object, "name", None),
            hasShRestAttributes=has_sh_rest,
            shDegree=getattr(props, "r2_sh_degree", None),
            proxyImportEnabled=getattr(props, "import_proxy", None),
        )

    camera_mode_start = time.monotonic()
    if insight_log:
        insight_log.log(
            "kiri_camera_update_mode_start",
            freezeHint="If Blender freezes after this line, Kiri is enabling camera-updated splat display.",
        )
    if active_object is not None:
        _set_kiri_object_update_mode(active_object, "Enable Camera Updates")
    _set_prop(props, "active_mode", "Edit")
    _set_prop(props, "edit_mode_menu", "Import")
    if insight_log:
        insight_log.log(
            "kiri_camera_update_mode_done",
            durationMs=_elapsed_ms(camera_mode_start),
            activeMode=getattr(props, "active_mode", None),
            updateMode=getattr(_object_kiri_props(active_object), "update_mode", None)
            if active_object is not None
            else None,
        )


def _rename_kiri_objects(objects: list[Any], world_name: Any) -> None:
    base_name = _clean_asset_name(world_name)
    if not base_name:
        return

    kiri_objects = [obj for obj in objects if _is_kiri_object(obj)]
    total = len(kiri_objects)
    for index, obj in enumerate(kiri_objects):
        if not hasattr(obj, "name"):
            continue
        obj.name = base_name if total <= 1 else "%s %02d" % (base_name, index + 1)


def _tag_mint_kiri_objects(objects: list[Any], world: dict) -> None:
    world_id = world.get("id")
    world_name = _clean_asset_name(world.get("name"))
    for obj in objects:
        if not _is_kiri_object(obj):
            continue
        if world_id:
            _set_object_custom_value(obj, MINT_KIRI_WORLD_ID_PROP, str(world_id))
        if world_name:
            _set_object_custom_value(obj, MINT_KIRI_WORLD_NAME_PROP, world_name)


def _rotate_mint_kiri_objects(objects: list[Any]) -> int:
    rotated = 0
    for obj in objects:
        if not _is_kiri_object(obj):
            continue
        rotation = getattr(obj, "rotation_euler", None)
        if rotation is None:
            continue
        try:
            rotation[0] = float(rotation[0]) + MINT_KIRI_X_ROTATION_CORRECTION_RADIANS
            rotated += 1
        except Exception:
            continue
    return rotated


def _scale_mint_kiri_objects(objects: list[Any]) -> int:
    scaled = 0
    for obj in objects:
        if not _is_kiri_object(obj):
            continue
        scale = getattr(obj, "scale", None)
        if scale is None:
            continue
        try:
            for index in range(len(scale)):
                scale[index] = float(scale[index]) * MINT_KIRI_IMPORT_SCALE_FACTOR
            scaled += 1
        except Exception:
            continue
    return scaled


def _import_with_kiri(
    path: Path,
    world: dict,
    bpy_ref: Any,
    insight_log: Optional[KiriInsightLog] = None,
) -> None:
    if not kiri_ready(bpy_ref):
        raise KiriBridgeUnavailableError(
            "Install and enable KIRI Engine 3DGS Render to import worlds"
        )

    configure_start = time.monotonic()
    if insight_log:
        insight_log.log("kiri_configure_start")
    _configure_kiri_import(bpy_ref)
    if insight_log:
        insight_log.log("kiri_configure_done", durationMs=_elapsed_ms(configure_start))

    before_ids = {id(obj) for obj in _scene_objects(bpy_ref)}
    operator_start = time.monotonic()
    if insight_log:
        insight_log.log(
            "kiri_operator_start",
            path=path,
            fileSize=path.stat().st_size if path.exists() else None,
            sceneObjectsBefore=len(before_ids),
            freezeHint="If Blender freezes after this line, the Kiri import operator is blocking.",
        )
    result = _operator_namespace(bpy_ref).dgs_render_import_ply_e0a3a(filepath=str(path))
    if insight_log:
        insight_log.log(
            "kiri_operator_done",
            durationMs=_elapsed_ms(operator_start),
            result=result,
        )
    if result and "CANCELLED" in result:
        raise KiriImportError("Kiri import cancelled")

    imported = _imported_objects_after(bpy_ref, before_ids)
    if insight_log:
        insight_log.log(
            "kiri_verify_imported_objects",
            importedObjectCount=len(imported),
            kiriObjectCount=sum(1 for obj in imported if _is_kiri_object(obj)),
        )
    if not any(_is_kiri_object(obj) for obj in imported):
        raise KiriImportError(
            "Kiri did not import a 3DGS object. Check that the PLY is a 3DGS scan"
        )

    _rename_kiri_objects(imported, world.get("name"))
    _tag_mint_kiri_objects(imported, world)
    rotated_count = _rotate_mint_kiri_objects(imported)
    scaled_count = _scale_mint_kiri_objects(imported)
    if insight_log:
        insight_log.log(
            "kiri_rename_done",
            worldId=world.get("id"),
            worldName=_clean_asset_name(world.get("name")),
        )
        insight_log.log(
            "kiri_orientation_correction_done",
            objectCount=rotated_count,
            rotationXDegrees=-90,
            scaledObjectCount=scaled_count,
            scaleFactor=MINT_KIRI_IMPORT_SCALE_FACTOR,
        )
    _configure_kiri_render_preview(bpy_ref, imported, insight_log)


def _export_import_url(export: dict) -> str:
    import_url = export.get("importUrl") or export.get("plyUrl")
    if not isinstance(import_url, str) or not import_url:
        raise KiriImportError("This Mint world does not have a Kiri-compatible PLY export yet")
    return import_url


def _log_world_splat_start(
    log: KiriInsightLog,
    world: dict,
    world_id: str,
    cache: AssetCache,
    client: MintBlenderClient,
) -> None:
    log.log(
        "world_splat_import_start",
        worldId=world_id or None,
        worldName=world.get("name"),
        cacheDir=cache.root,
        apiBaseUrl=getattr(getattr(client, "config", None), "api_base_url", None),
        logPath=log.path,
    )


def _log_world_splat_error(
    log: KiriInsightLog,
    total_start: float,
    error: Exception,
) -> None:
    log.log(
        "world_splat_import_error",
        durationMs=_elapsed_ms(total_start),
        errorType=type(error).__name__,
        message=str(error),
        traceback=traceback.format_exc(),
    )


def prepare_world_splat_ply(
    world: dict,
    access_token: str,
    client: MintBlenderClient,
    cache: AssetCache,
    config: Optional[MintBlenderConfig] = None,
    urlopen: Optional[UrlOpen] = None,
    bpy_module: Optional[Any] = None,
    insight_log: Optional[KiriInsightLog] = None,
    check_kiri: bool = False,
    status_callback: Optional[Callable[[str], None]] = None,
) -> Path:
    total_start = time.monotonic()
    resolved_config = config or MintBlenderConfig.from_env()
    log = insight_log or create_kiri_insight_log(resolved_config)
    world_id = str(world.get("id") or "")
    _log_world_splat_start(log, world, world_id, cache, client)
    if not world_id:
        log.log("world_splat_import_error", errorType="KiriImportError", message="World not found")
        raise KiriImportError("World not found")

    try:
        if check_kiri:
            log.log("load_bpy_start", providedBpyModule=bpy_module is not None)
            bpy_ref = bpy_module or _load_bpy()
            ready = kiri_ready(bpy_ref)
            log.log("kiri_ready_check", ready=ready)
            if not ready:
                raise KiriBridgeUnavailableError(
                    "Install and enable KIRI Engine 3DGS Render to import worlds"
                )

        export_start = time.monotonic()
        if status_callback:
            status_callback("Converting...")
        log.log("mint_export_request_start", worldId=world_id)
        export = client.export_world_ply(access_token, world_id)
        if status_callback:
            status_callback(
                "Cached..."
                if export.get("cached") is True
                else "Preparing..."
            )
        log.log(
            "mint_export_request_done",
            durationMs=_elapsed_ms(export_start),
            exportObject=export.get("object"),
            format=export.get("format"),
            fileSize=export.get("fileSize"),
            importUrl=export.get("importUrl") or export.get("plyUrl"),
            cached=export.get("cached"),
        )

        import_url = _export_import_url(export)
        path = cache.path_for(world_id, import_url, ".ply")
        log.log("ply_cache_check", path=path, exists=path.exists())
        if not path.exists():
            download_start = time.monotonic()
            if status_callback:
                status_callback("Downloading...")
            log.log("ply_download_start", url=import_url)
            data = _read_ply_url(import_url, resolved_config, urlopen)
            log.log(
                "ply_download_done",
                durationMs=_elapsed_ms(download_start),
                byteCount=len(data),
            )
            write_start = time.monotonic()
            path = cache.write_bytes(world_id, import_url, data, ".ply")
            if status_callback:
                status_callback("Cached...")
            log.log(
                "ply_cache_write_done",
                durationMs=_elapsed_ms(write_start),
                path=path,
                byteCount=path.stat().st_size if path.exists() else None,
            )
        else:
            log.log(
                "ply_cache_hit",
                path=path,
                byteCount=path.stat().st_size if path.exists() else None,
            )
            if status_callback:
                status_callback("Cached...")

        return path
    except Exception as error:
        _log_world_splat_error(log, total_start, error)
        raise


def import_prepared_world_splat_with_kiri(
    path: Path,
    world: dict,
    config: Optional[MintBlenderConfig] = None,
    bpy_module: Optional[Any] = None,
    insight_log: Optional[KiriInsightLog] = None,
    total_start: Optional[float] = None,
) -> None:
    start = total_start if total_start is not None else time.monotonic()
    resolved_config = config or MintBlenderConfig.from_env()
    log = insight_log or create_kiri_insight_log(resolved_config)
    try:
        log.log("load_bpy_start", providedBpyModule=bpy_module is not None)
        bpy_ref = bpy_module or _load_bpy()
        ready = kiri_ready(bpy_ref)
        log.log("kiri_ready_check", ready=ready)
        if not ready:
            raise KiriBridgeUnavailableError(
                "Install and enable KIRI Engine 3DGS Render to import worlds"
            )
        _import_with_kiri(path, world, bpy_ref, log)
        log.log(
            "world_splat_import_done",
            durationMs=_elapsed_ms(start),
            path=path,
        )
    except Exception as error:
        _log_world_splat_error(log, start, error)
        raise


def import_world_splat_with_kiri(
    world: dict,
    access_token: str,
    client: MintBlenderClient,
    cache: AssetCache,
    config: Optional[MintBlenderConfig] = None,
    urlopen: Optional[UrlOpen] = None,
    bpy_module: Optional[Any] = None,
    insight_log: Optional[KiriInsightLog] = None,
) -> Path:
    total_start = time.monotonic()
    resolved_config = config or MintBlenderConfig.from_env()
    log = insight_log or create_kiri_insight_log(resolved_config)
    path = prepare_world_splat_ply(
        world,
        access_token,
        client,
        cache,
        config=resolved_config,
        urlopen=urlopen,
        bpy_module=bpy_module,
        insight_log=log,
        check_kiri=True,
    )
    import_prepared_world_splat_with_kiri(
        path,
        world,
        config=resolved_config,
        bpy_module=bpy_module,
        insight_log=log,
        total_start=total_start,
    )
    return path
