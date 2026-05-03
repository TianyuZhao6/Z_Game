from __future__ import annotations

import math
import json
import sys
import time
from typing import Callable, Mapping, Optional
from urllib.parse import parse_qs

import pygame

IS_WEB = sys.platform == "emscripten"


def browser_now_s() -> float:
    if IS_WEB:
        try:
            import platform as web_platform

            window = getattr(web_platform, "window", None)
            perf = getattr(window, "performance", None) if window is not None else None
            now = getattr(perf, "now", None) if perf is not None else None
            if callable(now):
                return float(now()) / 1000.0
        except Exception:
            pass
    try:
        return time.perf_counter()
    except Exception:
        return 0.0


def _web_location_marker() -> str:
    if not IS_WEB:
        return ""
    try:
        import platform as web_platform

        window = getattr(web_platform, "window", None)
        location = getattr(window, "location", None) if window else None
        search = str(getattr(location, "search", "") or "").lower()
        hash_part = str(getattr(location, "hash", "") or "").lower()
        return f"{search}&{hash_part}"
    except Exception:
        return ""


def _web_query_params() -> dict[str, str]:
    if not IS_WEB:
        return {}
    marker = _web_location_marker()
    if not marker:
        return {}
    cleaned = marker.replace("#", "&").replace("?", "&").lstrip("&")
    if not cleaned:
        return {}
    try:
        parsed = parse_qs(cleaned, keep_blank_values=True)
    except Exception:
        return {}
    out: dict[str, str] = {}
    for key, values in parsed.items():
        if not key:
            continue
        try:
            out[str(key).strip().lower()] = str(values[-1] if values else "").strip()
        except Exception:
            continue
    return out


def _web_query_value(*names: str, default: str = "") -> str:
    params = _web_query_params()
    for name in names:
        key = str(name or "").strip().lower()
        if not key:
            continue
        value = str(params.get(key, "") or "").strip()
        if value:
            return value
    return str(default or "")


def _web_query_int(*names: str, default: int = 0) -> int:
    raw = _web_query_value(*names, default="")
    try:
        return int(float(raw))
    except Exception:
        return int(default)


def _web_query_float(*names: str, default: float = 0.0) -> float:
    raw = _web_query_value(*names, default="")
    try:
        return float(raw)
    except Exception:
        return float(default)


def _detect_web_autostart() -> bool:
    marker = _web_location_marker()
    return any(token in marker for token in ("autostart=1", "debug_start=1", "start=1"))


def _detect_web_diag() -> bool:
    marker = _web_location_marker()
    return any(token in marker for token in ("diag=1", "debug=1", "profile=1"))


def _detect_web_flag(*tokens: str) -> bool:
    marker = _web_location_marker()
    return any(str(token or "").lower() in marker for token in tokens)


def _normalize_diag_biome(value: str | None) -> str:
    raw = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    aliases = {
        "wind": "Domain of Wind",
        "domain of wind": "Domain of Wind",
        "mist": "Misty Forest",
        "misty": "Misty Forest",
        "misty forest": "Misty Forest",
        "hell": "Scorched Hell",
        "scorched hell": "Scorched Hell",
        "stone": "Bastion of Stone",
        "bastion": "Bastion of Stone",
        "bastion of stone": "Bastion of Stone",
    }
    return aliases.get(raw, "")


WEB_WINDOW_SIZE = (1280, 720)
WEB_MAX_FRAME_DT = 0.05
WEB_AUTOSAVE_INTERVAL = 0.0
WEB_SINGLE_BGM = False
# Default web BGM back to the native HTML-audio path. The mixer path is still
# available for debugging, but native playback isolates BGM from the pygame
# effect mixer and was the clean/noise-free browser path.
WEB_NATIVE_BGM = IS_WEB and (not _detect_web_flag("mixbgm=1", "mixerbgm=1", "nonativebgm=1"))
WEB_NATIVE_FX_AUDIO = IS_WEB and bool(WEB_NATIVE_BGM) and (not _detect_web_flag("mixfx=1", "mixerfx=1", "nonativefx=1"))
WEB_AUTOSTART = _detect_web_autostart()
WEB_DIAG_MODE = _detect_web_diag()
WEB_DIAG_SCENARIO = _web_query_value("scenario", "diagscenario", default="").strip().lower()
WEB_DIAG_FORCE_LEVEL = _web_query_int("level", "diaglevel", default=-1)
WEB_DIAG_FORCE_BIOME = _normalize_diag_biome(_web_query_value("biome", "diagbiome", default=""))
WEB_DIAG_FORCE_TRANSITION = IS_WEB and _detect_web_flag("transition=1", "menutrans=1", "hextrans=1")
WEB_DIAG_FORCE_ULTIMATE = IS_WEB and _detect_web_flag("god=1", "ultimate=1")
WEB_DIAG_DURATION_S = max(0.0, _web_query_float("duration", "diagdur", default=0.0))
WEB_DIAG_CAPTURE_MAX_FRAMES = max(300, _web_query_int("diagframes", default=4800)) if IS_WEB else 0
WEB_DIAG_EXPORT_INTERVAL = max(15, _web_query_int("diagexport", default=45)) if IS_WEB else 0
WEB_DIAG_TAG = _web_query_value("tag", "diagtag", default="")
WEB_PAINT_RENDER_REFRESH_MS = 50 if IS_WEB else 0
WEB_PAINT_DYNAMIC_REFRESH_MS = 66 if IS_WEB else 0
WEB_PAINT_STATIC_REFRESH_MS = 140 if IS_WEB else 0
WEB_PAINT_CAMERA_QUANT = 16 if IS_WEB else 1
WEB_WALL_NEAR_RADIUS_CELLS = 10 if IS_WEB else 0
WEB_USE_WALL_BAND_OPT = False
WEB_SIMPLE_ENEMY_FULL_MOVE_RADIUS_CELLS = 10 if IS_WEB else 0
WEB_FOCUS_PAN_DURATION = 0.18 if IS_WEB else 0.70
WEB_FOCUS_HOLD_TIME = 0.08 if IS_WEB else 0.35
WEB_LITE_RENDER_PICKUP_CAP = 12
WEB_LITE_RENDER_TURRET_CAP = 8
WEB_LITE_RENDER_ENEMY_CAP = 10
WEB_LITE_RENDER_BULLET_CAP = 28
WEB_LITE_RENDER_ENEMY_SHOT_CAP = 16
WEB_SIM_ENEMY_SHOT_CAP = 24
WEB_WAVE_SPAWN_BATCH = 8
WEB_ALLOW_LITE_RENDER = IS_WEB
WEB_QUALITY_ORDER = ("full", "balanced", "safe")
WEB_QUALITY_PRESETS = {
    "full": {
        "target_fps": 24,
        "flow_refresh_interval": 1.00,
        "spatial_refresh_interval": 0.32,
        "enemy_cap": 30,
        "max_render_width": 1600,
        "max_render_height": 900,
        "render_interval": 1.0 / 24.0,
        "render_scale": 1.0,
        "max_damage_texts": 4,
        "max_fx_particles": 16,
        "max_spoils_on_field": 8,
        "max_enemy_shots": 12,
        "contact_damage_mult": 0.25,
        "player_hit_cooldown_mult": 2.0,
        "enemy_speed_mult": 0.70,
        "threat_budget_mult": 1.0,
        "spawn_interval_mult": 1.0,
        "use_lite_render": True,
        "disable_fx_audio": False,
        "enable_astar_recovery": False,
    },
    "balanced": {
        "target_fps": 18,
        "flow_refresh_interval": 0.95,
        "spatial_refresh_interval": 0.28,
        "enemy_cap": 6,
        "max_render_width": 1152,
        "max_render_height": 648,
        "render_interval": 1.0 / 9.0,
        "render_scale": 0.82,
        "max_damage_texts": 20,
        "max_fx_particles": 96,
        "max_spoils_on_field": 24,
        "max_enemy_shots": 20,
        "contact_damage_mult": 0.65,
        "player_hit_cooldown_mult": 1.25,
        "enemy_speed_mult": 0.9,
        "threat_budget_mult": 0.9,
        "spawn_interval_mult": 1.15,
        "use_lite_render": True,
        "disable_fx_audio": False,
        "enable_astar_recovery": False,
    },
    "safe": {
        "target_fps": 16,
        "flow_refresh_interval": 1.05,
        "spatial_refresh_interval": 0.32,
        "enemy_cap": 8,
        "max_render_width": 960,
        "max_render_height": 540,
        "render_interval": 1.0 / 8.0,
        "render_scale": 0.9,
        "max_damage_texts": 16,
        "max_fx_particles": 72,
        "max_spoils_on_field": 20,
        "max_enemy_shots": 16,
        "contact_damage_mult": 0.55,
        "player_hit_cooldown_mult": 1.4,
        "enemy_speed_mult": 0.85,
        "threat_budget_mult": 0.8,
        "spawn_interval_mult": 1.25,
        "use_lite_render": True,
        "disable_fx_audio": True,
        "enable_astar_recovery": False,
    },
}
WEB_DEFAULT_QUALITY = "full"
WEB_TARGET_FPS = int(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["target_fps"])
WEB_FLOW_REFRESH_INTERVAL = float(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["flow_refresh_interval"])
WEB_SPATIAL_REFRESH_INTERVAL = float(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["spatial_refresh_interval"])
WEB_ENEMY_CAP = int(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["enemy_cap"])
WEB_MAX_RENDER_WIDTH = int(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["max_render_width"])
WEB_MAX_RENDER_HEIGHT = int(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["max_render_height"])
WEB_RENDER_INTERVAL = float(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["render_interval"])
WEB_RENDER_SCALE = float(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY].get("render_scale", 1.0) or 1.0)
WEB_CONTACT_DAMAGE_MULT = float(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY].get("contact_damage_mult", 1.0) or 1.0)
WEB_PLAYER_HIT_COOLDOWN_MULT = float(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY].get("player_hit_cooldown_mult", 1.0) or 1.0)
WEB_ENEMY_SPEED_MULT = float(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY].get("enemy_speed_mult", 1.0) or 1.0)
WEB_THREAT_BUDGET_MULT = float(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY].get("threat_budget_mult", 1.0) or 1.0)
WEB_SPAWN_INTERVAL_MULT = float(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY].get("spawn_interval_mult", 1.0) or 1.0)
WEB_MAX_DAMAGE_TEXTS = int(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["max_damage_texts"])
WEB_MAX_FX_PARTICLES = int(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["max_fx_particles"])
WEB_MAX_SPOILS_ON_FIELD = int(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["max_spoils_on_field"])
WEB_SIM_ENEMY_SHOT_CAP = int(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["max_enemy_shots"])
WEB_USE_LITE_RENDER = bool(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["use_lite_render"])
WEB_PROFILER_ENABLED = IS_WEB and WEB_DIAG_MODE
WEB_PROFILER_OVERLAY = IS_WEB and WEB_DIAG_MODE
WEB_DISABLE_FX_AUDIO = bool(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["disable_fx_audio"])
WEB_ENABLE_ENEMY_PAINT = True
WEB_ENABLE_VULNERABILITY_MARKS = True
WEB_ENABLE_HURRICANES = True
WEB_ENABLE_DAMAGE_TEXTS = True
WEB_ENABLE_AEGIS_PULSES = True
WEB_ENABLE_GROUND_SPIKES = True
WEB_ENABLE_CURING_PAINT = True
WEB_ENABLE_DOT_ROUNDS = True
WEB_ENABLE_ASTAR_RECOVERY = bool(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["enable_astar_recovery"])
WEB_LEVELUP_AUTO_PICK_SEC = 2.5 if IS_WEB else 0.0
WEB_ENABLE_FOG = True
WEB_FOG_SIMPLE_BANDS = True
WEB_FOG_RENDER_SCALE = 0.25 if IS_WEB else 1.0
WEB_FOG_REFRESH_MS = 320 if IS_WEB else 0
WEB_FOG_PLAYER_QUANT = 14 if IS_WEB else 1
WEB_FOG_LANTERN_QUANT = 18 if IS_WEB else 1
WEB_FOG_PULSE_QUANT = 5 if IS_WEB else 1
WEB_FOG_CAMERA_QUANT = 64 if IS_WEB else 1
WEB_FOG_MAX_LANTERNS = 10 if IS_WEB else 0
WEB_FOG_OVERLAY_ALPHA = 46 if IS_WEB else 0
WEB_FOG_PLAYER_CLEAR_SCALE = 1.0 if IS_WEB else 1.0
WEB_FOG_LANTERN_CLEAR_SCALE = 1.28 if IS_WEB else 1.0
WEB_HELL_TRAIL_INTERVAL_MULT = 1.45 if IS_WEB else 1.0
WEB_HELL_TRAIL_DIST_MULT = 1.35 if IS_WEB else 1.0
WEB_HURRICANE_ENEMY_SIM_INTERVAL = (1.0 / 30.0) if IS_WEB else 0.0
WEB_HURRICANE_SHOT_PULL_INTERVAL = (1.0 / 30.0) if IS_WEB else 0.0
WEB_HURRICANE_VISUAL_REFRESH_MS = 80 if IS_WEB else 0
WEB_HURRICANE_PHASE_BUCKETS = 6 if IS_WEB else 0
WEB_HURRICANE_MAX_AFFECTED_ENEMIES = 18 if IS_WEB else 0
WEB_HURRICANE_MAX_AFFECTED_SHOTS = 24 if IS_WEB else 0
WEB_HURRICANE_MAX_VISIBLE_RINGS = 2 if IS_WEB else 0
WEB_MAX_VISIBLE_ACIDS = 10 if IS_WEB else 0
WEB_SPOIL_BURST_CAP = 4 if IS_WEB else 0
WEB_MAX_ACIDS = 18 if IS_WEB else 0
WEB_SKIP_FLOW = IS_WEB and _detect_web_flag("skipflow=1")
# Browser stability mode keeps the desktop layout and combat density, but drops
# two late-run systems that repeatedly stalled Chrome in long sessions.
WEB_SKIP_FLOW_FIELD = IS_WEB and (not _detect_web_flag("flowfield=1", "ff=1"))
WEB_SKIP_ENEMY_SPOIL_COLLECT = IS_WEB and (not _detect_web_flag("enemycoins=1", "allowenemycoins=1"))
WEB_SKIP_UPDATE = IS_WEB and _detect_web_flag("skipupdate=1")
WEB_SKIP_BULLETS = IS_WEB and _detect_web_flag("skipbullets=1")
WEB_SKIP_ENEMY_MOVE = IS_WEB and _detect_web_flag("skipmove=1")
WEB_SKIP_ENEMY_SPECIAL = IS_WEB and _detect_web_flag("skipspecial=1")
WEB_DISABLE_TIMED_SPAWNS = IS_WEB and _detect_web_flag("notimedspawns=1", "nowaves=1")
# Optional web-only limiter for spawn types; default is desktop parity.
WEB_LIMIT_SPAWN_TYPES = IS_WEB and _detect_web_flag("safeenemies=1")
# Browser enemy projectiles are still unstable in long wasm sessions. Keep the
# normal web route on the safer path and allow explicit opt-in when needed.
WEB_SKIP_ENEMY_SHOTS = IS_WEB and (not _detect_web_flag("enemyshots=1", "allowenemyshots=1"))
WEB_SKIP_RENDER = IS_WEB and _detect_web_flag("skiprender=1")


def clamp_web_dt(dt_s: float, *, max_dt: float = WEB_MAX_FRAME_DT) -> float:
    try:
        dt = float(dt_s)
    except Exception:
        return 0.0
    if (not math.isfinite(dt)) or dt <= 0.0:
        return 0.0
    return min(dt, float(max_dt))


def is_web_interaction_event(event) -> bool:
    event_type = getattr(event, "type", None)
    if event_type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
        return True
    finger_down = getattr(pygame, "FINGERDOWN", None)
    return finger_down is not None and event_type == finger_down


def is_escape_event(event) -> bool:
    if getattr(event, "type", None) != pygame.KEYDOWN:
        return False
    try:
        if int(getattr(event, "key", -1)) == int(pygame.K_ESCAPE):
            return True
    except Exception:
        pass
    try:
        aliases = WEB_INPUT._aliases_for_event(event)
    except Exception:
        aliases = set()
    return bool({"esc", "escape"} & set(aliases))


def cap_web_surface_size(width: int, height: int) -> tuple[int, int]:
    width = max(640, int(width or WEB_WINDOW_SIZE[0]))
    height = max(360, int(height or WEB_WINDOW_SIZE[1]))
    scale = min(
        1.0,
        float(WEB_MAX_RENDER_WIDTH) / float(max(1, width)),
        float(WEB_MAX_RENDER_HEIGHT) / float(max(1, height)),
    )
    if scale >= 0.999:
        return width, height
    return max(640, int(round(width * scale))), max(360, int(round(height * scale)))


def _normalize_quality_name(profile_name: str | None) -> str:
    name = str(profile_name or "").strip().lower()
    if name in WEB_QUALITY_PRESETS:
        return name
    return WEB_DEFAULT_QUALITY


def _window_call(fn_name: str, *args):
    if not IS_WEB:
        return None
    try:
        import platform as web_platform

        window = getattr(web_platform, "window", None)
        fn = getattr(window, fn_name, None) if window is not None else None
        if fn is None:
            return None
        return fn(*args)
    except Exception:
        return None


def _publish_browser_diag_export(payload: dict[str, object]) -> None:
    if not IS_WEB:
        return
    try:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return
    try:
        _window_call("__zgame_diag_push", text)
    except Exception:
        pass
    if WEB_DIAG_MODE:
        try:
            print(f"__ZGAME_PY_DIAG__{text}")
        except Exception:
            pass


def _quality_payload(profile_name: str) -> dict[str, object]:
    name = _normalize_quality_name(profile_name)
    preset = WEB_QUALITY_PRESETS.get(name, WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY])
    payload = dict(preset)
    payload["quality"] = name
    payload["single_bgm"] = bool(WEB_SINGLE_BGM)
    for feature_name in (
        "enable_enemy_paint",
        "enable_vulnerability_marks",
        "enable_hurricanes",
        "enable_damage_texts",
        "enable_aegis_pulses",
        "enable_ground_spikes",
        "enable_curing_paint",
        "enable_dot_rounds",
    ):
        payload[feature_name] = True
    return payload


def apply_web_quality_profile(game, profile_name: str | None, *, reason: str = "") -> str:
    if not getattr(game, "IS_WEB", False):
        return "desktop"
    payload = _quality_payload(profile_name)
    assignments = {
        "WEB_DEFAULT_QUALITY": str(payload["quality"]),
        "WEB_NATIVE_BGM": bool(WEB_NATIVE_BGM),
        "WEB_NATIVE_FX_AUDIO": bool(WEB_NATIVE_FX_AUDIO),
        "WEB_PAINT_RENDER_REFRESH_MS": int(WEB_PAINT_RENDER_REFRESH_MS),
        "WEB_PAINT_DYNAMIC_REFRESH_MS": int(WEB_PAINT_DYNAMIC_REFRESH_MS),
        "WEB_PAINT_STATIC_REFRESH_MS": int(WEB_PAINT_STATIC_REFRESH_MS),
        "WEB_PAINT_CAMERA_QUANT": int(WEB_PAINT_CAMERA_QUANT),
        "WEB_WINDOW_SIZE": (int(payload["max_render_width"]), int(payload["max_render_height"])),
        "WEB_TARGET_FPS": int(payload["target_fps"]),
        "WEB_FLOW_REFRESH_INTERVAL": float(payload["flow_refresh_interval"]),
        "WEB_SPATIAL_REFRESH_INTERVAL": float(payload["spatial_refresh_interval"]),
        "WEB_ENEMY_CAP": int(payload["enemy_cap"]),
        "WEB_MAX_RENDER_WIDTH": int(payload["max_render_width"]),
        "WEB_MAX_RENDER_HEIGHT": int(payload["max_render_height"]),
        "WEB_RENDER_INTERVAL": float(payload["render_interval"]),
        "WEB_RENDER_SCALE": float(payload.get("render_scale", 1.0) or 1.0),
        "WEB_CONTACT_DAMAGE_MULT": float(payload.get("contact_damage_mult", 1.0) or 1.0),
        "WEB_PLAYER_HIT_COOLDOWN_MULT": float(payload.get("player_hit_cooldown_mult", 1.0) or 1.0),
        "WEB_ENEMY_SPEED_MULT": float(payload.get("enemy_speed_mult", 1.0) or 1.0),
        "WEB_THREAT_BUDGET_MULT": float(payload.get("threat_budget_mult", 1.0) or 1.0),
        "WEB_SPAWN_INTERVAL_MULT": float(payload.get("spawn_interval_mult", 1.0) or 1.0),
        "WEB_MAX_DAMAGE_TEXTS": int(payload["max_damage_texts"]),
        "WEB_MAX_FX_PARTICLES": int(payload["max_fx_particles"]),
        "WEB_MAX_SPOILS_ON_FIELD": int(payload["max_spoils_on_field"]),
        "WEB_SIM_ENEMY_SHOT_CAP": int(payload["max_enemy_shots"]),
        "WEB_USE_LITE_RENDER": bool(payload["use_lite_render"]),
        "WEB_SINGLE_BGM": bool(payload["single_bgm"]),
        "WEB_DISABLE_FX_AUDIO": bool(payload["disable_fx_audio"]),
        "WEB_ENABLE_ENEMY_PAINT": bool(payload["enable_enemy_paint"]),
        "WEB_ENABLE_VULNERABILITY_MARKS": bool(payload["enable_vulnerability_marks"]),
        "WEB_ENABLE_HURRICANES": bool(payload["enable_hurricanes"]),
        "WEB_ENABLE_DAMAGE_TEXTS": bool(payload["enable_damage_texts"]),
        "WEB_ENABLE_AEGIS_PULSES": bool(payload["enable_aegis_pulses"]),
        "WEB_ENABLE_GROUND_SPIKES": bool(payload["enable_ground_spikes"]),
        "WEB_ENABLE_CURING_PAINT": bool(payload["enable_curing_paint"]),
        "WEB_ENABLE_DOT_ROUNDS": bool(payload["enable_dot_rounds"]),
        "WEB_ENABLE_ASTAR_RECOVERY": bool(payload["enable_astar_recovery"]),
    }
    for key, value in assignments.items():
        globals()[key] = value
        try:
            setattr(game, key, value)
        except Exception:
            pass
    runtime = getattr(game, "__dict__", {})
    runtime["_web_quality_profile"] = str(payload["quality"])
    runtime["_web_quality_reason"] = str(reason or "")
    runtime["_web_quality_last_adjust_s"] = browser_now_s()
    _window_call("__zgame_apply_render_limits", int(payload["max_render_width"]), int(payload["max_render_height"]))
    try:
        surface = pygame.display.get_surface()
        if surface is not None:
            next_size = get_initial_web_window_size()
            if surface.get_size() != next_size:
                new_surface = pygame.display.set_mode(next_size, pygame.RESIZABLE)
                refresh_view = getattr(game, "_refresh_viewport", None)
                if callable(refresh_view):
                    refresh_view(new_surface)
                invalidate = getattr(game, "_invalidate_view_caches", None)
                if callable(invalidate):
                    invalidate()
    except Exception:
        pass
    return str(payload["quality"])


def maybe_adjust_web_quality_profile(game, profiler) -> str | None:
    # Keep one fixed browser profile for the entire run. Live canvas/profile
    # changes were causing layout drift from desktop and destabilizing Chrome.
    return None


def _normalize_web_key_name(name: str | None) -> str:
    raw = str(name or "").strip().lower()
    if not raw or raw == "unknown key":
        return ""
    raw = raw.replace("keypad ", "kp ")
    raw = raw.replace("arrowup", "up")
    raw = raw.replace("arrowdown", "down")
    raw = raw.replace("arrowleft", "left")
    raw = raw.replace("arrowright", "right")
    alias_map = {
        "return": "enter",
        "kp enter": "enter",
        "left shift": "shift",
        "right shift": "shift",
        "left ctrl": "ctrl",
        "right ctrl": "ctrl",
        "left alt": "alt",
        "right alt": "alt",
        "escape": "esc",
    }
    return alias_map.get(raw, raw)


class WebInputState:
    def __init__(self) -> None:
        self._keys_down: set[int] = set()
        self._actions_down: set[str] = set()
        self._binding_aliases: dict[str, set[str]] = {}

    def clear(self) -> None:
        self._keys_down.clear()
        self._actions_down.clear()

    def _aliases_for_keycode(self, keycode: int | None) -> set[str]:
        aliases: set[str] = set()
        if keycode is None:
            return aliases
        try:
            key_name = _normalize_web_key_name(pygame.key.name(int(keycode)))
        except Exception:
            key_name = ""
        if key_name:
            aliases.add(key_name)
            if key_name.startswith("kp "):
                aliases.add(key_name[3:])
        return aliases

    def _aliases_for_event(self, event) -> set[str]:
        aliases: set[str] = set()
        try:
            aliases.update(self._aliases_for_keycode(int(getattr(event, "key", None))))
        except Exception:
            pass
        try:
            text = str(getattr(event, "unicode", "") or "").strip().lower()
        except Exception:
            text = ""
        if text:
            aliases.add(_normalize_web_key_name(text))
        aliases.discard("")
        return aliases

    def refresh_binding_aliases(self, bindings: Mapping[str, int]) -> None:
        self._binding_aliases.clear()
        for action, keycode in bindings.items():
            self._binding_aliases[action] = self._aliases_for_keycode(int(keycode))

    def event_matches_action(
        self,
        event,
        action: str,
        action_key: Callable[[str], Optional[int]],
    ) -> bool:
        if getattr(event, "type", None) not in (pygame.KEYDOWN, pygame.KEYUP):
            return False
        key = action_key(action)
        if key is None:
            return False
        try:
            if int(getattr(event, "key", -1)) == int(key):
                return True
        except Exception:
            pass
        expected = self._binding_aliases.get(action) or self._aliases_for_keycode(int(key))
        if not expected:
            return False
        return bool(expected & self._aliases_for_event(event))

    def sync_event(
        self,
        event,
        bindings: Mapping[str, int],
        action_key: Callable[[str], Optional[int]],
    ) -> None:
        if not IS_WEB:
            return
        try:
            if event.type == pygame.KEYDOWN:
                self._keys_down.add(int(event.key))
                for action in bindings:
                    if self.event_matches_action(event, action, action_key):
                        self._actions_down.add(action)
            elif event.type == pygame.KEYUP:
                self._keys_down.discard(int(event.key))
                for action in tuple(self._actions_down):
                    if self.event_matches_action(event, action, action_key):
                        self._actions_down.discard(action)
            else:
                focus_lost_types = {
                    getattr(pygame, "WINDOWFOCUSLOST", None),
                }
                if event.type in focus_lost_types:
                    self.clear()
        except Exception:
            pass

    def binding_pressed(self, action: str, keycode: int | None) -> bool:
        if keycode is None:
            return False
        try:
            return action in self._actions_down or int(keycode) in self._keys_down
        except Exception:
            return False


WEB_INPUT = WebInputState()


def _set_browser_profiler_phase(phase: str, detail: str = "") -> None:
    if not IS_WEB:
        return
    try:
        import platform as web_platform

        window = getattr(web_platform, "window", None)
        if window is None:
            return
        setattr(window, "__zgame_prof_phase", str(phase or ""))
        if detail:
            setattr(window, "__zgame_prof_detail", str(detail))
    except Exception:
        pass


def _set_browser_profiler_metrics(
    *,
    frame: int | None = None,
    dt_ms: float | None = None,
    raw_dt_ms: float | None = None,
    total_ms: float | None = None,
    update_ms: float | None = None,
    render_ms: float | None = None,
    browser_gap_ms: float | None = None,
    rendered: bool | None = None,
    idle_loops: int | None = None,
    accum_ms: float | None = None,
    phase_json: str | None = None,
    counts_json: str | None = None,
) -> None:
    if not IS_WEB:
        return
    try:
        import platform as web_platform

        window = getattr(web_platform, "window", None)
        if window is None:
            return
        if frame is not None:
            setattr(window, "__zgame_py_frame", int(frame))
        if dt_ms is not None:
            setattr(window, "__zgame_py_dt_ms", round(float(dt_ms), 2))
        if raw_dt_ms is not None:
            setattr(window, "__zgame_py_raw_dt_ms", round(float(raw_dt_ms), 2))
        if total_ms is not None:
            setattr(window, "__zgame_py_total_ms", round(float(total_ms), 2))
        if update_ms is not None:
            setattr(window, "__zgame_py_update_ms", round(float(update_ms), 2))
        if render_ms is not None:
            setattr(window, "__zgame_py_render_ms", round(float(render_ms), 2))
        if browser_gap_ms is not None:
            setattr(window, "__zgame_py_browser_gap_ms", round(float(browser_gap_ms), 2))
        if rendered is not None:
            setattr(window, "__zgame_py_rendered", int(bool(rendered)))
        if idle_loops is not None:
            setattr(window, "__zgame_py_idle_loops", int(idle_loops))
        if accum_ms is not None:
            setattr(window, "__zgame_py_accum_ms", round(float(accum_ms), 2))
        if phase_json is not None:
            setattr(window, "__zgame_py_phase_json", str(phase_json or ""))
        if counts_json is not None:
            setattr(window, "__zgame_py_counts_json", str(counts_json or ""))
        setattr(window, "__zgame_py_heartbeat_ms", round(float(time.perf_counter()) * 1000.0, 1))
    except Exception:
        pass


def report_web_runtime_error(context: str, err) -> None:
    if not IS_WEB:
        return
    try:
        import platform as web_platform

        window = getattr(web_platform, "window", None)
        if window is None:
            return
        msg = str(err or "").strip().replace("\r", " ").replace("\n", " | ")
        full = f"{context}: {msg}".strip(": ").strip()
        setattr(window, "__zgame_last_error", full[:240])
        setattr(window, "__zgame_py_error", full[:4096])
        setattr(window, "__zgame_py_dead", True)
    except Exception:
        pass


def _percentiles(values: list[float], *ps: int) -> dict[str, float]:
    cleaned = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not cleaned:
        return {f"p{int(p)}": 0.0 for p in ps}
    out: dict[str, float] = {}
    last = len(cleaned) - 1
    for p in ps:
        if last <= 0:
            out[f"p{int(p)}"] = round(cleaned[0], 3)
            continue
        q = max(0.0, min(100.0, float(p))) / 100.0
        idx = q * last
        lo = int(math.floor(idx))
        hi = min(last, lo + 1)
        frac = idx - lo
        val = cleaned[lo] * (1.0 - frac) + cleaned[hi] * frac
        out[f"p{int(p)}"] = round(val, 3)
    return out


class WebRuntimeProfiler:
    """Web-only frame profiler with exportable hitch and transition diagnostics."""

    def __init__(self) -> None:
        self.enabled = bool(WEB_PROFILER_ENABLED)
        self.overlay_enabled = bool(WEB_PROFILER_OVERLAY)
        self.frame_index = 0
        self.current_phase = ""
        self._phase_started_at = 0.0
        self._phase_order: list[str] = []
        self._phase_last: dict[str, float] = {}
        self._phase_avg: dict[str, float] = {}
        self._phase_max: dict[str, float] = {}
        self._counters: dict[str, int | float | str] = {}
        self.last_total_ms = 0.0
        self.avg_total_ms = 0.0
        self.max_total_ms = 0.0
        self.last_dt_ms = 0.0
        self.last_raw_dt_ms = 0.0
        self.max_raw_dt_ms = 0.0
        self.last_update_ms = 0.0
        self.last_render_ms = 0.0
        self.last_browser_gap_ms = 0.0
        self.last_rendered = False
        self.last_heap_mb = None
        self.peak_heap_mb = 0.0
        self.last_hot_label = ""
        self.last_hot_ms = 0.0
        self.last_hot_total_ms = 0.0
        self._last_console_log_s = -999.0
        self._hot_phase_threshold_ms = 16.0
        self._hot_total_threshold_ms = 33.0
        self.rendered_frames = 0
        self.skipped_frames = 0
        self.hitch_counts = {25: 0, 33: 0, 50: 0, 100: 0}
        self.worst_hitch_ms = 0.0
        self.current_hitch_streak_33 = 0
        self.longest_hitch_streak_33 = 0
        self.samples: list[dict[str, object]] = []
        self.events: list[dict[str, object]] = []
        self.session_started_s = browser_now_s()
        self.session_meta: dict[str, object] = {
            "scenario": WEB_DIAG_SCENARIO,
            "tag": WEB_DIAG_TAG,
            "forced_level": WEB_DIAG_FORCE_LEVEL,
            "forced_biome": WEB_DIAG_FORCE_BIOME,
            "quality": WEB_DEFAULT_QUALITY,
        }
        self._export_interval = max(0, int(WEB_DIAG_EXPORT_INTERVAL or 0))
        self._capture_limit = max(0, int(WEB_DIAG_CAPTURE_MAX_FRAMES or 0))

    def set_context(self, **values) -> None:
        if not self.enabled:
            return
        for key, value in values.items():
            if value is None:
                continue
            self.session_meta[str(key)] = value

    def begin_frame(self, dt_s: float, *, raw_dt_s: float | None = None) -> None:
        if not self.enabled:
            return
        self.frame_index += 1
        self.current_phase = ""
        self._phase_started_at = time.perf_counter()
        self._phase_order = []
        self._phase_last = {}
        self._counters = {}
        self.last_hot_label = ""
        self.last_hot_ms = 0.0
        self.last_dt_ms = max(0.0, float(dt_s) * 1000.0)
        raw_s = float(raw_dt_s if raw_dt_s is not None else dt_s)
        self.last_raw_dt_ms = max(0.0, raw_s * 1000.0)
        self.max_raw_dt_ms = max(self.max_raw_dt_ms, self.last_raw_dt_ms)
        _set_browser_profiler_phase("frame")
        _set_browser_profiler_metrics(
            frame=self.frame_index,
            dt_ms=self.last_dt_ms,
            raw_dt_ms=self.last_raw_dt_ms,
        )

    def mark(self, phase: str) -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        if self.current_phase:
            self._record(self.current_phase, (now - self._phase_started_at) * 1000.0)
        self.current_phase = str(phase or "")
        self._phase_started_at = now
        _set_browser_profiler_phase(self.current_phase)

    def counter(self, name: str, value) -> None:
        if not self.enabled:
            return
        self._counters[str(name)] = value

    def event(self, kind: str, **data) -> None:
        if not self.enabled:
            return
        item = {
            "kind": str(kind or ""),
            "frame": int(self.frame_index),
            "t_s": round(browser_now_s() - self.session_started_s, 4),
        }
        for key, value in data.items():
            if value is None:
                continue
            item[str(key)] = value
        self.events.append(item)
        if len(self.events) > 256:
            del self.events[:-256]
        self._publish_export(force=True)

    def transition_event(self, kind: str, **data) -> None:
        payload = dict(data)
        payload["transition"] = True
        self.event(f"transition:{kind}", **payload)

    def finish(self, *, rendered: bool) -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        if self.current_phase:
            self._record(self.current_phase, (now - self._phase_started_at) * 1000.0)
        total_ms = sum(self._phase_last.values())
        render_ms = float(self._phase_last.get("render", 0.0) or 0.0)
        update_ms = max(0.0, total_ms - render_ms)
        browser_gap_ms = max(0.0, self.last_raw_dt_ms - total_ms)
        self.last_total_ms = total_ms
        self.last_update_ms = update_ms
        self.last_render_ms = render_ms
        self.last_browser_gap_ms = browser_gap_ms
        self.avg_total_ms = total_ms if self.frame_index <= 1 else (self.avg_total_ms * 0.92 + total_ms * 0.08)
        self.max_total_ms = max(self.max_total_ms, total_ms)
        self.last_rendered = bool(rendered)
        if rendered:
            self.rendered_frames += 1
        else:
            self.skipped_frames += 1
        self._update_hitch_stats(total_ms)
        self._refresh_heap()
        self._capture_sample(rendered=rendered)
        self._maybe_log_hot_frame(now)
        _set_browser_profiler_phase(
            "render" if rendered else "update",
            f"frame={self.frame_index} total={total_ms:.1f}ms",
        )
        _set_browser_profiler_metrics(
            frame=self.frame_index,
            dt_ms=self.last_dt_ms,
            raw_dt_ms=self.last_raw_dt_ms,
            total_ms=self.last_total_ms,
            update_ms=self.last_update_ms,
            render_ms=self.last_render_ms,
            browser_gap_ms=self.last_browser_gap_ms,
            rendered=rendered,
            phase_json=json.dumps({name: round(float(ms), 3) for name, ms in self._phase_last.items()}, ensure_ascii=False, separators=(",", ":")),
            counts_json=json.dumps(dict(self._counters), ensure_ascii=False, separators=(",", ":")),
        )
        self._publish_export(force=False)
        self.current_phase = ""
        self._phase_started_at = now

    def _record(self, phase: str, elapsed_ms: float) -> None:
        phase = str(phase or "")
        if not phase:
            return
        elapsed_ms = max(0.0, float(elapsed_ms))
        self._phase_last[phase] = elapsed_ms
        if phase not in self._phase_order:
            self._phase_order.append(phase)
        avg_ms = self._phase_avg.get(phase)
        self._phase_avg[phase] = elapsed_ms if avg_ms is None else (avg_ms * 0.92 + elapsed_ms * 0.08)
        self._phase_max[phase] = max(self._phase_max.get(phase, 0.0), elapsed_ms)
        if elapsed_ms >= self.last_hot_ms:
            self.last_hot_ms = elapsed_ms
            self.last_hot_label = phase

    def _update_hitch_stats(self, frame_ms: float) -> None:
        frame_ms = max(0.0, float(frame_ms))
        self.worst_hitch_ms = max(self.worst_hitch_ms, frame_ms)
        for threshold in tuple(self.hitch_counts.keys()):
            if frame_ms > float(threshold):
                self.hitch_counts[threshold] += 1
        if frame_ms > 33.0:
            self.current_hitch_streak_33 += 1
            self.longest_hitch_streak_33 = max(self.longest_hitch_streak_33, self.current_hitch_streak_33)
        else:
            self.current_hitch_streak_33 = 0

    def _capture_sample(self, *, rendered: bool) -> None:
        if self._capture_limit <= 0:
            return
        sample = {
            "frame": int(self.frame_index),
            "t_s": round(browser_now_s() - self.session_started_s, 4),
            "raw_dt_ms": round(self.last_raw_dt_ms, 3),
            "dt_ms": round(self.last_dt_ms, 3),
            "frame_ms": round(self.last_total_ms, 3),
            "update_ms": round(self.last_update_ms, 3),
            "render_ms": round(self.last_render_ms, 3),
            "browser_gap_ms": round(self.last_browser_gap_ms, 3),
            "rendered": int(bool(rendered)),
            "phase_ms": {name: round(float(ms), 3) for name, ms in self._phase_last.items()},
            "counts": dict(self._counters),
        }
        self.samples.append(sample)
        if len(self.samples) > self._capture_limit:
            del self.samples[:-self._capture_limit]

    def _maybe_log_hot_frame(self, now_s: float) -> None:
        hot_name = ""
        hot_ms = 0.0
        for phase_name, elapsed_ms in self._phase_last.items():
            if elapsed_ms >= hot_ms:
                hot_name = phase_name
                hot_ms = elapsed_ms
        self.last_hot_label = hot_name
        self.last_hot_ms = hot_ms
        self.last_hot_total_ms = self.last_total_ms
        if hot_ms < self._hot_phase_threshold_ms and self.last_total_ms < self._hot_total_threshold_ms:
            return
        if (now_s - self._last_console_log_s) < 0.75:
            return
        self._last_console_log_s = now_s
        counts = " ".join(
            f"{key}={self._counters[key]}"
            for key in ("obs", "en", "b", "es", "sp", "txt", "fx", "rendered")
            if key in self._counters
        )
        print(
            f"[WebProfiler] frame={self.frame_index} dt={self.last_dt_ms:.1f}ms "
            f"total={self.last_total_ms:.1f}ms update={self.last_update_ms:.1f}ms "
            f"render={self.last_render_ms:.1f}ms gap={self.last_browser_gap_ms:.1f}ms "
            f"hot={hot_name}:{hot_ms:.1f}ms heap={self.last_heap_mb if self.last_heap_mb is not None else 'n/a'}MB {counts}".rstrip()
        )

    def _refresh_heap(self) -> None:
        heap_mb = None
        browser_error = ""
        try:
            import platform as web_platform

            window = getattr(web_platform, "window", None)
            perf = getattr(window, "performance", None) if window is not None else None
            mem = getattr(perf, "memory", None) if perf is not None else None
            used = getattr(mem, "usedJSHeapSize", None) if mem is not None else None
            if used is not None:
                heap_mb = round(float(used) / (1024.0 * 1024.0), 1)
            browser_error = str(getattr(window, "__zgame_last_error", "") or "") if window is not None else ""
        except Exception:
            heap_mb = None
            browser_error = ""
        self.last_heap_mb = heap_mb
        if heap_mb is not None:
            self.peak_heap_mb = max(self.peak_heap_mb, heap_mb)
        self._counters["jserr"] = browser_error[:128] if browser_error else ""

    def summary(self) -> dict[str, object]:
        frame_values = [float(sample.get("frame_ms", 0.0) or 0.0) for sample in self.samples]
        raw_values = [float(sample.get("raw_dt_ms", 0.0) or 0.0) for sample in self.samples]
        render_values = [float(sample.get("render_ms", 0.0) or 0.0) for sample in self.samples]
        update_values = [float(sample.get("update_ms", 0.0) or 0.0) for sample in self.samples]
        browser_gap_values = [float(sample.get("browser_gap_ms", 0.0) or 0.0) for sample in self.samples]
        return {
            "frames": int(self.frame_index),
            "rendered_frames": int(self.rendered_frames),
            "skipped_frames": int(self.skipped_frames),
            "avg_frame_ms": round(float(sum(frame_values) / max(1, len(frame_values))), 3) if frame_values else 0.0,
            "avg_render_ms": round(float(sum(render_values) / max(1, len(render_values))), 3) if render_values else 0.0,
            "avg_update_ms": round(float(sum(update_values) / max(1, len(update_values))), 3) if update_values else 0.0,
            "avg_browser_gap_ms": round(float(sum(browser_gap_values) / max(1, len(browser_gap_values))), 3) if browser_gap_values else 0.0,
            "worst_hitch_ms": round(self.worst_hitch_ms, 3),
            "longest_hitch_streak_33": int(self.longest_hitch_streak_33),
            "hitch_counts": {str(key): int(value) for key, value in self.hitch_counts.items()},
            "frame_percentiles_ms": _percentiles(frame_values, 50, 90, 95, 99),
            "raw_dt_percentiles_ms": _percentiles(raw_values, 50, 90, 95, 99),
            "render_percentiles_ms": _percentiles(render_values, 50, 90, 95, 99),
            "update_percentiles_ms": _percentiles(update_values, 50, 90, 95, 99),
            "browser_gap_percentiles_ms": _percentiles(browser_gap_values, 50, 90, 95, 99),
            "phase_avg_ms": {key: round(val, 3) for key, val in self._phase_avg.items()},
            "phase_max_ms": {key: round(val, 3) for key, val in self._phase_max.items()},
        }

    def export_payload(self) -> dict[str, object]:
        return {
            "source": "python-web-profiler",
            "session": dict(self.session_meta),
            "summary": self.summary(),
            "last_frame": {
                "frame": int(self.frame_index),
                "dt_ms": round(self.last_dt_ms, 3),
                "raw_dt_ms": round(self.last_raw_dt_ms, 3),
                "frame_ms": round(self.last_total_ms, 3),
                "update_ms": round(self.last_update_ms, 3),
                "render_ms": round(self.last_render_ms, 3),
                "browser_gap_ms": round(self.last_browser_gap_ms, 3),
                "rendered": int(self.last_rendered),
                "hot_phase": self.last_hot_label,
                "hot_phase_ms": round(self.last_hot_ms, 3),
                "heap_mb": self.last_heap_mb,
                "peak_heap_mb": self.peak_heap_mb,
            },
            "events": list(self.events),
            "samples": list(self.samples),
        }

    def _publish_export(self, *, force: bool) -> None:
        if not self.enabled:
            return
        if (not force) and self._export_interval > 0 and (self.frame_index % self._export_interval) != 0:
            return
        _publish_browser_diag_export(self.export_payload())

    def overlay_lines(self) -> list[str]:
        if (not self.enabled) or (not self.overlay_enabled):
            return []
        summary = self.summary()
        frame_p95 = float(summary.get("frame_percentiles_ms", {}).get("p95", 0.0) or 0.0)
        raw_p95 = float(summary.get("raw_dt_percentiles_ms", {}).get("p95", 0.0) or 0.0)
        lines = [
            f"WEB PROFILER  f:{self.frame_index}  dt:{self.last_dt_ms:.1f} raw:{self.last_raw_dt_ms:.1f}  frame:{self.last_total_ms:.1f}/{summary.get('avg_frame_ms', 0.0):.1f}/{self.max_total_ms:.1f}",
            f"upd:{self.last_update_ms:.1f}  rnd:{self.last_render_ms:.1f}  gap:{self.last_browser_gap_ms:.1f}  p95:{frame_p95:.1f}/{raw_p95:.1f}",
            f"hitch >25:{self.hitch_counts[25]}  >33:{self.hitch_counts[33]}  >50:{self.hitch_counts[50]}  worst:{self.worst_hitch_ms:.1f}  streak33:{self.longest_hitch_streak_33}",
            f"hot {self.last_hot_label or '-'}  {self.last_hot_ms:.1f} ms  rendered:{int(self.last_rendered)}",
        ]
        preferred = ("pre", "events", "focus", "update", "bullets", "spawn", "flow", "enemy_move", "enemy_special", "enemy_shots", "render")
        ordered = [name for name in preferred if name in self._phase_last]
        ordered.extend(name for name in self._phase_order if name not in ordered)
        for phase_name in ordered[:8]:
            last_ms = self._phase_last.get(phase_name, 0.0)
            avg_ms = self._phase_avg.get(phase_name, 0.0)
            max_ms = self._phase_max.get(phase_name, 0.0)
            lines.append(f"{phase_name:<13} {last_ms:>5.1f} / {avg_ms:>5.1f} / {max_ms:>5.1f}")
        counter_parts = []
        for key in ("obs", "en", "b", "es", "sp", "hp", "txt", "fx", "wind", "hell", "fog", "wave", "trans", "trans_stall"):
            if key in self._counters:
                counter_parts.append(f"{key}:{self._counters[key]}")
        if counter_parts:
            lines.append("  ".join(counter_parts))
        if "audio" in self._counters:
            audio_line = f"audio:{self._counters['audio']}"
            if self.last_heap_mb is not None:
                audio_line += f"  heap:{self.last_heap_mb:.1f}/{self.peak_heap_mb:.1f}MB"
            lines.append(audio_line)
        elif self.last_heap_mb is not None:
            lines.append(f"heap:{self.last_heap_mb:.1f}/{self.peak_heap_mb:.1f}MB")
        js_err = str(self._counters.get("jserr", "") or "").strip()
        if js_err:
            lines.append(f"jserr:{js_err[:72]}")
        return lines


def get_initial_web_window_size() -> tuple[int, int]:
    if IS_WEB:
        try:
            import platform as web_platform  # pygbag bridge on web

            win = getattr(web_platform, "window", None)
            w = int(getattr(win, "innerWidth", 0) or 0)
            h = int(getattr(win, "innerHeight", 0) or 0)
            if w > 0 and h > 0:
                return max(640, w), max(360, h)
        except Exception:
            pass
    try:
        info = pygame.display.Info()
        w = int(getattr(info, "current_w", 0) or 0)
        h = int(getattr(info, "current_h", 0) or 0)
    except Exception:
        w = h = 0
    if w <= 0 or h <= 0:
        return WEB_WINDOW_SIZE
    return max(800, w), max(450, h)
