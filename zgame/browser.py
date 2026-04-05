from __future__ import annotations

import math
import sys
import time
from typing import Callable, Mapping, Optional

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


def _detect_web_autostart() -> bool:
    marker = _web_location_marker()
    return any(token in marker for token in ("autostart=1", "debug_start=1", "start=1"))


def _detect_web_diag() -> bool:
    marker = _web_location_marker()
    return any(token in marker for token in ("diag=1", "debug=1", "profile=1", "autostart=1"))


WEB_WINDOW_SIZE = (1280, 720)
WEB_MAX_FRAME_DT = 0.05
WEB_AUTOSAVE_INTERVAL = 0.0
WEB_SINGLE_BGM = IS_WEB
WEB_AUTOSTART = _detect_web_autostart()
WEB_DIAG_MODE = _detect_web_diag()
WEB_LITE_RENDER_PICKUP_CAP = 18
WEB_LITE_RENDER_TURRET_CAP = 10
WEB_LITE_RENDER_ENEMY_CAP = 16
WEB_LITE_RENDER_BULLET_CAP = 48
WEB_LITE_RENDER_ENEMY_SHOT_CAP = 32
WEB_ALLOW_LITE_RENDER = False
WEB_QUALITY_ORDER = ("full", "balanced", "safe")
WEB_QUALITY_PRESETS = {
    "full": {
        "target_fps": 16,
        "flow_refresh_interval": 1.00,
        "spatial_refresh_interval": 0.32,
        "enemy_cap": 12,
        "max_render_width": 720,
        "max_render_height": 405,
        "render_interval": 1.0 / 5.0,
        "use_lite_render": False,
        "disable_fx_audio": False,
        "enable_astar_recovery": False,
    },
    "balanced": {
        "target_fps": 18,
        "flow_refresh_interval": 0.95,
        "spatial_refresh_interval": 0.28,
        "enemy_cap": 14,
        "max_render_width": 960,
        "max_render_height": 540,
        "render_interval": 1.0 / 6.0,
        "use_lite_render": False,
        "disable_fx_audio": False,
        "enable_astar_recovery": False,
    },
    "safe": {
        "target_fps": 16,
        "flow_refresh_interval": 1.05,
        "spatial_refresh_interval": 0.32,
        "enemy_cap": 10,
        "max_render_width": 720,
        "max_render_height": 405,
        "render_interval": 1.0 / 5.0,
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
WEB_USE_LITE_RENDER = bool(WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY]["use_lite_render"])
WEB_PROFILER_ENABLED = IS_WEB
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


def _quality_payload(profile_name: str) -> dict[str, object]:
    name = _normalize_quality_name(profile_name)
    preset = WEB_QUALITY_PRESETS.get(name, WEB_QUALITY_PRESETS[WEB_DEFAULT_QUALITY])
    payload = dict(preset)
    payload["quality"] = name
    payload["single_bgm"] = True
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
        "WEB_WINDOW_SIZE": (int(payload["max_render_width"]), int(payload["max_render_height"])),
        "WEB_TARGET_FPS": int(payload["target_fps"]),
        "WEB_FLOW_REFRESH_INTERVAL": float(payload["flow_refresh_interval"]),
        "WEB_SPATIAL_REFRESH_INTERVAL": float(payload["spatial_refresh_interval"]),
        "WEB_ENEMY_CAP": int(payload["enemy_cap"]),
        "WEB_MAX_RENDER_WIDTH": int(payload["max_render_width"]),
        "WEB_MAX_RENDER_HEIGHT": int(payload["max_render_height"]),
        "WEB_RENDER_INTERVAL": float(payload["render_interval"]),
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
    rendered: bool | None = None,
    idle_loops: int | None = None,
    accum_ms: float | None = None,
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
        if rendered is not None:
            setattr(window, "__zgame_py_rendered", int(bool(rendered)))
        if idle_loops is not None:
            setattr(window, "__zgame_py_idle_loops", int(idle_loops))
        if accum_ms is not None:
            setattr(window, "__zgame_py_accum_ms", round(float(accum_ms), 2))
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
        setattr(window, "__zgame_py_error", full[:512])
        setattr(window, "__zgame_py_dead", True)
    except Exception:
        pass


class WebRuntimeProfiler:
    """Small web-only frame profiler for spotting the last hot gameplay phase."""

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
        self.last_rendered = False
        self.last_heap_mb = None
        self.peak_heap_mb = 0.0
        self.last_hot_label = ""
        self.last_hot_ms = 0.0
        self.last_hot_total_ms = 0.0
        self._last_console_log_s = -999.0
        self._hot_phase_threshold_ms = 16.0
        self._hot_total_threshold_ms = 33.0

    def begin_frame(self, dt_s: float, *, raw_dt_s: float | None = None) -> None:
        if not self.enabled:
            return
        self.frame_index += 1
        self.current_phase = ""
        self._phase_started_at = time.perf_counter()
        self._phase_order = []
        self._phase_last = {}
        self._counters = {}
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

    def finish(self, *, rendered: bool) -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        if self.current_phase:
            self._record(self.current_phase, (now - self._phase_started_at) * 1000.0)
        total_ms = sum(self._phase_last.values())
        self.last_total_ms = total_ms
        self.avg_total_ms = total_ms if self.frame_index <= 1 else (self.avg_total_ms * 0.92 + total_ms * 0.08)
        self.max_total_ms = max(self.max_total_ms, total_ms)
        self.last_rendered = bool(rendered)
        self._refresh_heap()
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
            rendered=rendered,
        )
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
            for key in ("obs", "en", "b", "es", "spawn", "rendered")
            if key in self._counters
        )
        print(
            f"[WebProfiler] frame={self.frame_index} dt={self.last_dt_ms:.1f}ms "
            f"total={self.last_total_ms:.1f}ms hot={hot_name}:{hot_ms:.1f}ms "
            f"heap={self.last_heap_mb if self.last_heap_mb is not None else 'n/a'}MB {counts}".rstrip()
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
        self._counters["jserr"] = browser_error[:96] if browser_error else ""

    def overlay_lines(self) -> list[str]:
        if (not self.enabled) or (not self.overlay_enabled):
            return []
        lines = [
            f"WEB PROFILER  f:{self.frame_index}  dt:{self.last_dt_ms:.1f} raw:{self.last_raw_dt_ms:.1f}  total:{self.last_total_ms:.1f}/{self.avg_total_ms:.1f}/{self.max_total_ms:.1f}",
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
        for key in ("obs", "en", "b", "es", "spawn", "wave", "trans"):
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
        if self.last_raw_dt_ms > self.last_total_ms + 8.0:
            lines.append(f"browser_gap {max(0.0, self.last_raw_dt_ms - self.last_total_ms):.1f} ms")
        return lines


def get_initial_web_window_size() -> tuple[int, int]:
    if IS_WEB:
        try:
            import platform as web_platform  # pygbag bridge on web

            win = getattr(web_platform, "window", None)
            w = int(getattr(win, "innerWidth", 0) or 0)
            h = int(getattr(win, "innerHeight", 0) or 0)
            if w > 0 and h > 0:
                return cap_web_surface_size(max(640, w), max(360, h))
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
    return cap_web_surface_size(max(800, w), max(450, h))
