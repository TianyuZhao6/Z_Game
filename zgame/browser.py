from __future__ import annotations

import sys
from typing import Callable, Mapping, Optional

import pygame

IS_WEB = sys.platform == "emscripten"
WEB_WINDOW_SIZE = (960, 540)
WEB_TARGET_FPS = 30
WEB_FLOW_REFRESH_INTERVAL = 0.60
WEB_ENEMY_CAP = 10
WEB_DEMO = IS_WEB
WEB_DEMO_SKIP_INTRO = True
WEB_DEMO_DISABLE_CONTINUE = True
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
                    getattr(pygame, "WINDOWLEAVE", None),
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
