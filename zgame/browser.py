from __future__ import annotations

import math
import sys
from typing import Callable, Mapping, Optional

import pygame

IS_WEB = sys.platform == "emscripten"


def _detect_web_demo() -> bool:
    if not IS_WEB:
        return False
    try:
        import platform as web_platform

        window = getattr(web_platform, "window", None)
        location = getattr(window, "location", None) if window else None
        search = str(getattr(location, "search", "") or "").lower()
        hash_part = str(getattr(location, "hash", "") or "").lower()
        marker = f"{search}&{hash_part}"
        return any(token in marker for token in ("demo=1", "web_demo=1", "mode=demo", "#demo"))
    except Exception:
        return False
WEB_WINDOW_SIZE = (960, 540)
WEB_TARGET_FPS = 20
WEB_MAX_FRAME_DT = 0.05
WEB_AUTOSAVE_INTERVAL = 0.0
WEB_FLOW_REFRESH_INTERVAL = 0.90
WEB_SPATIAL_REFRESH_INTERVAL = 0.12
WEB_ENEMY_CAP = 8
WEB_MAX_RENDER_WIDTH = 720
WEB_MAX_RENDER_HEIGHT = 405
WEB_RENDER_INTERVAL = 1.0 / 12.0
WEB_DEMO = _detect_web_demo()
WEB_DEMO_SKIP_INTRO = WEB_DEMO
WEB_DEMO_DISABLE_CONTINUE = WEB_DEMO
WEB_DEMO_LEVEL_LIMIT = 2
WEB_DEMO_LEVEL_TIME_LIMIT = 40.0
WEB_DEMO_BOSS_TIME_LIMIT = 45.0
WEB_DEMO_SCENE_BIOMES = ("Domain of Wind", "Misty Forest")
WEB_DEMO_SHOP_PROP_IDS = frozenset({
    "coin_magnet",
    "carapace",
    "aegis_pulse",
    "auto_turret",
    "piercing_rounds",
    "ricochet_scope",
    "explosive_rounds",
    "dot_rounds",
    "curing_paint",
    "ground_spikes",
    "mark_vulnerability",
    "stationary_turret",
})
WEB_DEMO_RENDER_PICKUP_CAP = 8
WEB_DEMO_RENDER_TURRET_CAP = 4
WEB_DEMO_RENDER_ENEMY_CAP = 8
WEB_DEMO_RENDER_BULLET_CAP = 28
WEB_DEMO_RENDER_ENEMY_SHOT_CAP = 18
WEB_USE_LITE_RENDER = True
WEB_ENABLE_ENEMY_PAINT = not WEB_DEMO
WEB_ENABLE_VULNERABILITY_MARKS = not WEB_DEMO
WEB_ENABLE_HURRICANES = not WEB_DEMO
WEB_ENABLE_DAMAGE_TEXTS = not WEB_DEMO
WEB_ENABLE_AEGIS_PULSES = not WEB_DEMO
WEB_ENABLE_GROUND_SPIKES = not WEB_DEMO
WEB_ENABLE_CURING_PAINT = not WEB_DEMO
WEB_ENABLE_DOT_ROUNDS = not WEB_DEMO
WEB_ENABLE_ASTAR_RECOVERY = False


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
