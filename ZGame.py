from __future__ import annotations
import heapq
import sys
import asyncio
import pygame
import math
import threading
import random
import os
import copy
import hashlib
import colorsys
from effects import *
from collections import deque
from typing import Dict, List, Set, Tuple, Optional

from zgame.audio_analysis import NeuroMusicVisualizer
from zgame.browser import (
    IS_WEB,
    WEB_DEMO,
    WEB_AUTOSAVE_INTERVAL,
    WEB_DEMO_BOSS_TIME_LIMIT,
    WEB_ENABLE_AEGIS_PULSES,
    WEB_ENABLE_CURING_PAINT,
    WEB_ENABLE_DAMAGE_TEXTS,
    WEB_ENABLE_DOT_ROUNDS,
    WEB_ENABLE_ENEMY_PAINT,
    WEB_ENABLE_GROUND_SPIKES,
    WEB_ENABLE_HURRICANES,
    WEB_ENABLE_VULNERABILITY_MARKS,
    WEB_DEMO_DISABLE_CONTINUE,
    WEB_DEMO_LEVEL_LIMIT,
    WEB_DEMO_LEVEL_TIME_LIMIT,
    WEB_DEMO_RENDER_BULLET_CAP,
    WEB_DEMO_RENDER_ENEMY_CAP,
    WEB_DEMO_RENDER_ENEMY_SHOT_CAP,
    WEB_DEMO_RENDER_PICKUP_CAP,
    WEB_DEMO_RENDER_TURRET_CAP,
    WEB_DEMO_SCENE_BIOMES,
    WEB_DEMO_SHOP_PROP_IDS,
    WEB_DEMO_SKIP_INTRO,
    WEB_ENEMY_CAP,
    WEB_FLOW_REFRESH_INTERVAL,
    WEB_INPUT,
    WEB_TARGET_FPS,
    WEB_USE_LITE_RENDER,
    WEB_WINDOW_SIZE,
    get_initial_web_window_size,
)
from zgame.paths import (
    BASE_DIR,
    EXPORT_DIR,
    SAVE_DIR,
    SAVE_FILE,
    asset_candidates as _asset_candidates,
    audio_path_variants as _audio_path_variants,
    expand_audio_candidates as _expand_audio_candidates,
    first_existing_path as _first_existing_path,
)
from zgame import entity_core as entity_core_support
from zgame import enemy_core as enemy_core_support
from zgame import enemy_projectiles as enemy_projectiles_support
from zgame import enemy_subclasses as enemy_subclasses_support
from zgame import hazards as hazards_support
from zgame import player_projectiles as player_projectiles_support
from zgame import turrets as turrets_support
from zgame import pickups as pickups_support
from zgame import paint as paint_support
from zgame import world_runtime as world_runtime_support
from zgame import worldgen_pathing as worldgen_pathing_support
from zgame import effects_runtime as effects_runtime_support
from zgame import menu_visuals as menu_visuals_support
from zgame import menu_flow as menu_flow_support
from zgame import persistence as persistence_support
from zgame import shop_support
from zgame import game_state as game_state_support
from zgame import spawn_logic as spawn_logic_support
from zgame import screens as screens_support
from zgame import shop_ui as shop_ui_support
from zgame import pause_ui as pause_ui_support
from zgame import app_flow as app_flow_support
from zgame import audio_runtime as audio_runtime_support
from zgame import render_runtime as render_runtime_support
from zgame import runtime_state as runtime_state_support

_THIS_MODULE = sys.modules[__name__]


def _runtime_state():
    return runtime_state_support.runtime(_THIS_MODULE)


def _meta_state():
    return runtime_state_support.meta(_THIS_MODULE)


def _invalidate_view_caches() -> None:
    runtime = _runtime_state()
    runtime["_hex_bg_surface"] = None
    runtime["_hex_grid_cache"] = None
    runtime["_hex_transition"] = None
    runtime["_hex_grid_view_size"] = None
    runtime["_neuro_bg_surface"] = None
    runtime["_intro_star_far"] = []
    runtime["_intro_star_near"] = []
    runtime["_intro_columns"] = []
    runtime["_intro_view_size"] = None


def _refresh_viewport(surface: pygame.Surface | None = None) -> pygame.Surface | None:
    global VIEW_W, VIEW_H
    surface = surface or pygame.display.get_surface()
    if surface is not None:
        VIEW_W, VIEW_H = surface.get_size()
    return surface


def _handle_web_window_event(event) -> pygame.Surface | None:
    if not IS_WEB:
        return pygame.display.get_surface()
    resize_types = {pygame.VIDEORESIZE}
    for name in ("WINDOWRESIZED", "WINDOWSIZECHANGED"):
        etype = getattr(pygame, name, None)
        if etype is not None:
            resize_types.add(etype)
    if getattr(event, "type", None) not in resize_types:
        return pygame.display.get_surface()
    width = max(640, int(getattr(event, "w", 0) or VIEW_W or WEB_WINDOW_SIZE[0]))
    height = max(360, int(getattr(event, "h", 0) or VIEW_H or WEB_WINDOW_SIZE[1]))
    surface = pygame.display.set_mode((width, height), pygame.RESIZABLE)
    _refresh_viewport(surface)
    _invalidate_view_caches()
    return surface


def _sync_web_input_event(event) -> None:
    WEB_INPUT.sync_event(event, BINDINGS, action_key)

# --- Event queue helper to prevent ghost clicks ---
def flush_events():
    try:
        pygame.event.clear()
    except Exception:
        pass
    if IS_WEB:
        WEB_INPUT.clear()


# --- UI helper ---
def pause_settings_only(screen, background_surf):
    """
    Show the Pause menu but only let the player go into Settings and then come back.
    Returns only when the user chooses CONTINUE (or closes the menu).
    """
    while True:
        choice = show_pause_menu(screen, background_surf)
        if choice == 'settings':
            show_settings_popup(screen, background_surf)
            # when settings closes, show pause again
            continue
        # treat anything else as 'continue'
        break
    flush_events()


def pause_from_overlay(screen, bg_surface):
    # Show pause; loop when settings closes so we land back on pause.
    while True:
        choice = show_pause_menu(screen, bg_surface)
        if choice in (None, "continue"):
            return "continue"
        if choice == "settings":
            show_settings_popup(screen, bg_surface)
            flush_events()
            continue  # back to pause
        return choice  # "home" | "exit" | "restart"


# --- Font helper ---
def mono_font(size: int) -> "pygame.font.Font":
    # Try common monospaced fonts; fall back safely
    candidates = ["Consolas", "Menlo", "DejaVu Sans Mono", "Courier New", "monospace"]
    try:
        name = pygame.font.match_font(candidates)
        if name:
            return pygame.font.Font(name, size)
    except Exception:
        pass
    return pygame.font.SysFont("monospace", size)


def _draw_rect_perimeter_progress(surf: "pygame.Surface",
                                  rect: "pygame.Rect",
                                  progress: float,
                                  color: tuple[int, int, int],
                                  width: int = 4) -> None:
    """
    Draw a single stroke that wraps the rect's perimeter from top-left clockwise.
    The stroke length is progress * perimeter. No fill, just contour.
    """
    p = max(0.0, min(1.0, float(progress)))
    if p <= 0:
        return
    x, y, w, h = rect.x, rect.y, rect.w, rect.h
    perimeter = 2 * (w + h)
    remain = int(perimeter * p)
    edges = [  # ((sx,sy),(ex,ey), length)
        ((x, y), (x + w, y), w),  # top: left -> right
        ((x + w, y), (x + w, y + h), h),  # right: top -> bottom
        ((x + w, y + h), (x, y + h), w),  # bottom: right -> left
        ((x, y + h), (x, y), h),  # left: bottom -> top
    ]
    for (sx, sy), (ex, ey), L in edges:
        if remain <= 0:
            break
        seg = min(remain, L)
        if sx == ex:
            # vertical
            diry = 1 if ey > sy else -1
            pygame.draw.line(surf, color, (sx, sy), (sx, sy + diry * seg), width)
        else:
            # horizontal
            dirx = 1 if ex > sx else -1
            pygame.draw.line(surf, color, (sx, sy), (sx + dirx * seg, sy), width)
        remain -= seg


# === Shield HUD style (tweak as you like) ===
SHIELD_EDGE_COLOR = (30, 140, 190)  # dark cyan
SHIELD_FILL_COLOR = (60, 180, 255, 60)  # translucent inner tint (RGBA with alpha)
SHIELD_EDGE_WIDTH = 3  # shell stroke thickness
SHIELD_EXPAND_PX = 4  # how much wider than the HP bar


def _draw_shield_shell(surf: "pygame.Surface",
                       bar_rect: "pygame.Rect",
                       start_ratio: float,
                       length_ratio: float,
                       *,
                       expand: int = SHIELD_EXPAND_PX,
                       edge_width: int = SHIELD_EDGE_WIDTH,
                       edge_color: tuple[int, int, int] = SHIELD_EDGE_COLOR,
                       fill_color: tuple[int, int, int, int] = SHIELD_FILL_COLOR) -> None:
    """
    Draw a slightly larger, hollow rounded-rect over a portion of the HP bar.
    start_ratio: where the shield starts (0..1), usually at current HP ratio
    length_ratio: how much of the bar is covered by shield (0..1), clamped to not overflow
    """
    # clamp
    s = max(0.0, min(1.0, float(start_ratio)))
    L = max(0.0, min(1.0 - s, float(length_ratio)))
    if L <= 0.0:
        return
    # expanded rect that "wraps" the HP bar
    x = bar_rect.x + int(bar_rect.w * s) - expand
    w = max(1, int(bar_rect.w * L)) + expand * 2
    h = bar_rect.h + expand * 2
    y = bar_rect.y - expand
    rr = max(4, min(10, (bar_rect.h + expand) // 2 + 2))  # nice corners
    # translucent inner tint (optional, very light)
    if fill_color and len(fill_color) == 4 and fill_color[3] > 0:
        srf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(srf, fill_color, pygame.Rect(0, 0, w, h), border_radius=rr)
        surf.blit(srf, (x, y))
    # dark-cyan edge (hollow look)
    pygame.draw.rect(surf, edge_color, pygame.Rect(x, y, w, h), width=edge_width, border_radius=rr)


def feet_center(ent):
    # 世界坐标（含 INFO_BAR_HEIGHT 的平移）
    return (ent.x + ent.size * 0.5, ent.y + ent.size * 0.5 + INFO_BAR_HEIGHT)


def circle_touch(a, b, extra=0.0) -> bool:
    ax, ay = feet_center(a)
    bx, by = feet_center(b)
    ra = getattr(a, "radius", a.size * 0.5)
    rb = getattr(b, "radius", b.size * 0.5)
    r = ra + rb + float(extra)
    dx = ax - bx
    dy = ay - by
    return (dx * dx + dy * dy) <= (r * r)


def update_hit_flash_timer(entity, dt: float) -> None:
    """
    If HP dropped since last tick, start a short white flash.
    Always decays by dt so the flash fades back to the base color.
    """
    prev_hp = int(getattr(entity, "_flash_prev_hp", getattr(entity, "hp", 0)))
    cur_hp = int(getattr(entity, "hp", 0))
    if cur_hp < prev_hp:
        entity._hit_flash = float(HIT_FLASH_DURATION)
    else:
        entity._hit_flash = max(0.0, float(getattr(entity, "_hit_flash", 0.0)) - float(dt))
    entity._flash_prev_hp = cur_hp
    glow_t = max(0.0, float(getattr(entity, "_curing_paint_glow_t", 0.0)) - float(dt))
    entity._curing_paint_glow_t = glow_t
    if glow_t <= 0.0:
        entity._curing_paint_glow_intensity = 0.0


def draw_ui_topbar(screen, game_state, player, time_left: float | None = None,
                   enemies: list | None = None) -> None:
    """
    顶栏 HUD（绝对屏幕坐标，不受相机/等距相机影响）
    - 必须在世界/实体都画完之后再调用（最上层）
    - 不做 flip()；由外层渲染函数统一 flip
    """
    # 背板
    pygame.draw.rect(screen, (0, 0, 0), (0, 0, VIEW_W, INFO_BAR_HEIGHT))
    # 字体
    font_timer = pygame.font.SysFont(None, 28)
    mono_small = mono_font(22)
    font_hp = mono_font(22)
    # ===== 计时器（居中） =====
    runtime = _runtime_state()
    meta = _meta_state()
    tleft = float(time_left if time_left is not None else runtime.get("_time_left_runtime", LEVEL_TIME_LIMIT))
    tleft = max(0.0, tleft)
    mins = int(tleft // 60)
    secs = int(tleft % 60)
    timer_txt = font_timer.render(f"{mins:02d}:{secs:02d}", True, (255, 255, 255))
    center_x = VIEW_W // 2
    screen.blit(timer_txt, (center_x - timer_txt.get_width() // 2, 10))
    # ===== 关卡 LV（在计时器左侧 12px）=====
    level_idx = int(getattr(game_state, "current_level", 0))  # 0-based
    level_img = mono_small.render(f"LV {level_idx + 1:02d}", True, (255, 255, 255))
    level_x = center_x - timer_txt.get_width() // 2 - level_img.get_width() - 12
    screen.blit(level_img, (level_x, 10))
    # ===== 威胁预算 BDG（在计时器右侧 12px）=====
    bdg_val = budget_for_level(level_idx)
    bdg_img = mono_small.render(f"BDG {bdg_val}", True, (200, 200, 220))
    bdg_x = center_x + timer_txt.get_width() // 2 + 12
    screen.blit(bdg_img, (bdg_x, 10))
    # ===== HP 条（左上角）=====
    bar_w, bar_h = 220, 12
    bx, by = 16, 14
    ratio = 0.0 if max(1, getattr(player, "max_hp", 1)) == 0 else max(
        0.0, min(1.0, float(getattr(player, "hp", 0)) / float(max(1, getattr(player, "max_hp", 1)))))
    # frame + bg + fill
    pygame.draw.rect(screen, (60, 60, 60), (bx - 2, by - 2, bar_w + 4, bar_h + 4), border_radius=4)
    pygame.draw.rect(screen, (40, 40, 40), (bx, by, bar_w, bar_h), border_radius=3)
    pygame.draw.rect(screen, (0, 200, 80), (bx, by, int(bar_w * ratio), bar_h), border_radius=3)
    # --- Shield shell overlay (smoothed, slightly wider & hollow) ---
    base_shield = int(max(0, getattr(player, "shield_hp", 0)))
    carapace_shield = int(max(0, getattr(player, "carapace_hp", 0)))
    sleft = base_shield + carapace_shield
    mhp = int(max(1, getattr(player, "max_hp", 1)))
    # Smooth the visible fraction so it drains bit-by-bit
    target = 0.0 if mhp <= 0 else max(0.0, min(1.0, sleft / float(mhp)))
    vis = float(getattr(player, "_hud_shield_vis", target))
    vis += (target - vis) * 0.18
    player._hud_shield_vis = vis
    if vis > 0.002:
        bar_rect = pygame.Rect(bx, by, bar_w, bar_h)
        # Anchor at the LEFT of the HP bar so it’s visible even at full HP
        _draw_shield_shell(
            screen, bar_rect,
            start_ratio=0.0,  # <— was ratio
            length_ratio=vis,  # <— was add_vis
            expand=SHIELD_EXPAND_PX,
            edge_width=SHIELD_EDGE_WIDTH,
            edge_color=SHIELD_EDGE_COLOR,
            fill_color=SHIELD_FILL_COLOR
        )
    # ===== XP 条（紧贴 HP 条下方）=====
    xp_bar_w, xp_bar_h = bar_w, 6
    xp_bx, xp_by = bx, by + bar_h + 6
    xp_to_next = int(getattr(player, "xp_to_next", 0))
    xp_have = int(getattr(player, "xp", 0))
    xp_ratio = max(0.0, min(1.0, float(xp_have) / float(xp_to_next))) if xp_to_next > 0 else 0.0
    pygame.draw.rect(screen, (60, 60, 60), (xp_bx - 2, xp_by - 2, xp_bar_w + 4, xp_bar_h + 4), border_radius=4)
    pygame.draw.rect(screen, (40, 40, 40), (xp_bx, xp_by, xp_bar_w, xp_bar_h), border_radius=3)
    pygame.draw.rect(screen, (120, 110, 255), (xp_bx, xp_by, int(xp_bar_w * xp_ratio), xp_bar_h), border_radius=3)
    # 小标签（在条右侧显示等级）
    xp_label = mono_small.render(f"Lv {int(getattr(player, 'level', 1))}", True, (210, 210, 230))
    screen.blit(xp_label, (xp_bx + xp_bar_w + 8, xp_by - 6))
    # Bone Plating tracker
    plating_lvl = int(getattr(player, "bone_plating_level", 0))
    if plating_lvl > 0:
        plating_hp = int(max(0, getattr(player, "bone_plating_hp", 0)))
        plate_bar_w, plate_bar_h = bar_w, 6
        plate_bx, plate_by = bx, xp_by + xp_bar_h + 8
        pygame.draw.rect(screen, (60, 60, 60), (plate_bx - 2, plate_by - 2, plate_bar_w + 4, plate_bar_h + 4),
                         border_radius=4)
        pygame.draw.rect(screen, (30, 30, 34), (plate_bx, plate_by, plate_bar_w, plate_bar_h), border_radius=3)
        m_hp = max(1, int(getattr(player, "max_hp", 1)))
        plate_ratio = max(0.0, min(1.0, plating_hp / float(m_hp)))
        pygame.draw.rect(screen, BONE_PLATING_COLOR,
                         (plate_bx, plate_by, int(plate_bar_w * plate_ratio), plate_bar_h), border_radius=3)
        # regen marker
        cd = float(getattr(player, "_bone_plating_cd", BONE_PLATING_GAIN_INTERVAL))
        regen_ratio = 1.0 - max(0.0, min(1.0, cd / float(BONE_PLATING_GAIN_INTERVAL)))
        marker_x = plate_bx + int(plate_bar_w * regen_ratio)
        pygame.draw.line(screen, (255, 255, 255), (marker_x, plate_by - 1), (marker_x, plate_by + plate_bar_h + 1), 1)
        plate_txt = f"Bone {plating_hp}"
        if plating_lvl >= BONE_PLATING_MAX_LEVEL:
            plate_txt += " (MAX)"
        else:
            plate_txt += f" (Lv {plating_lvl})"
        plate_img = mono_small.render(plate_txt, True, BONE_PLATING_COLOR)
        screen.blit(plate_img, (plate_bx, plate_by + plate_bar_h + 2))
    # Active skill icons (bottom-right)
    def _draw_skill_icon(x, y, w, h, label, key_txt, cd, cd_total, active, flash_t, palette):
        base = pygame.Surface((w, h), pygame.SRCALPHA)
        bg = palette["bg"]
        border = palette["border_active"] if active else palette["border"]
        pygame.draw.rect(base, bg, base.get_rect(), border_radius=10)
        pygame.draw.rect(base, border, base.get_rect(), width=2, border_radius=10)
        # icon glyph
        glyph = pygame.Surface((w, h), pygame.SRCALPHA)
        if label == "BLAST":
            # crosshair icon
            pygame.draw.circle(glyph, palette["accent"], (w // 2, h // 2), 12, 2)
            pygame.draw.line(glyph, palette["accent"], (w // 2, 6), (w // 2, h - 6), 2)
            pygame.draw.line(glyph, palette["accent"], (6, h // 2), (w - 6, h // 2), 2)
            pygame.draw.circle(glyph, palette["accent"], (w // 2, h // 2), 3)
        else:
            # teleport plus icon
            pygame.draw.rect(glyph, palette["accent"], (w // 2 - 2, 8, 4, h - 16))
            pygame.draw.rect(glyph, palette["accent"], (8, h // 2 - 2, w - 16, 4))
            pygame.draw.circle(glyph, palette["accent_dim"], (w // 2, h // 2), 10, 2)
        base.blit(glyph, (0, 0))
        # labels
        lfont = pygame.font.SysFont("Consolas", 14, bold=True)
        keyfont = pygame.font.SysFont("Consolas", 14, bold=True)
        base.blit(lfont.render(label, True, palette["text"]), (8, h - 30))
        base.blit(keyfont.render(key_txt, True, palette["key"]), (8, h - 16))
        # cooldown overlay
        if cd > 0 and cd_total > 0:
            ratio = max(0.0, min(1.0, cd / cd_total))
            overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(overlay, (0, 0, 0, 190), (0, 0, w, int(h * ratio)))
            base.blit(overlay, (0, 0))
            num = keyfont.render(f"{int(math.ceil(cd))}", True, palette["text"])
            base.blit(num, num.get_rect(center=(w - 14, h // 2)))
        if flash_t > 0:
            pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.025)
            fx = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(fx, (*palette["accent"], int(70 + 80 * pulse)), fx.get_rect(), border_radius=12)
            base.blit(fx, (0, 0))
        screen.blit(base, (x, y))
    icon_w, icon_h = 92, 64
    margin = 12
    right_x = VIEW_W - icon_w - margin
    bottom_y = VIEW_H - icon_h - margin
    blast_palette = {
        "bg": (30, 16, 16),
        "border": (180, 80, 40),
        "border_active": (255, 140, 60),
        "accent": (255, 120, 60),
        "accent_dim": (190, 90, 50),
        "text": (240, 200, 180),
        "key": (255, 170, 120),
    }
    tele_palette = {
        "bg": (16, 26, 38),
        "border": (60, 140, 200),
        "border_active": (100, 200, 255),
        "accent": (90, 200, 255),
        "accent_dim": (70, 150, 210),
        "text": (210, 230, 250),
        "key": (140, 210, 255),
    }
    _draw_skill_icon(
        right_x, bottom_y - icon_h - 8, icon_w, icon_h, "BLAST", "Q",
        float(getattr(player, "blast_cd", 0.0)), BLAST_COOLDOWN,
        getattr(player, "targeting_skill", None) == "blast",
        float(player.skill_flash.get("blast", 0.0)),
        blast_palette,
    )
    _draw_skill_icon(
        right_x, bottom_y, icon_w, icon_h, "TELEPORT", "E",
        float(getattr(player, "teleport_cd", 0.0)), TELEPORT_COOLDOWN,
        getattr(player, "targeting_skill", None) == "teleport",
        float(player.skill_flash.get("teleport", 0.0)),
        tele_palette,
    )
    # 数字覆盖在进度条中间
    hp_text = f"{int(getattr(player, 'hp', 0))}/{int(getattr(player, 'max_hp', 0))}"
    hp_img = font_hp.render(hp_text, True, (20, 20, 20))
    screen.blit(hp_img, hp_img.get_rect(center=(bx + bar_w // 2, by + bar_h // 2 + 1)))
    # ===== 右上角：物品 & 金币 =====
    hud_font = font_timer  # 统一字号
    # 物品（最右）
    total_items = int(meta.get("run_items_spawned", 0))
    collected = int(meta.get("run_items_collected", 0))
    icon_x, icon_y = VIEW_W - 120, 10
    pygame.draw.circle(screen, (255, 255, 0), (icon_x, icon_y + 8), 8)
    items_text = hud_font.render(f"{collected}", True, (255, 255, 255))
    screen.blit(items_text, (icon_x + 18, icon_y))
    # 金币（物品左侧）
    spoils_total = int(meta.get("spoils", 0)) + int(getattr(game_state, "spoils_gained", 0))
    coin_x, coin_y = VIEW_W - 220, 10
    pygame.draw.circle(screen, (255, 215, 80), (coin_x, coin_y + 8), 8)
    pygame.draw.circle(screen, (255, 245, 200), (coin_x, coin_y + 8), 8, 1)
    spoils_text = hud_font.render(f"{spoils_total}", True, (255, 255, 255))
    screen.blit(spoils_text, (coin_x + 14, coin_y))
    # ===== 屏幕中央：一过性横幅 =====
    banner_drawn = False
    bt = float(getattr(game_state, "banner_t", 0.0))
    if bt > 0.0 and getattr(game_state, "banner_text", None):
        # 计算经过时间，做 1s 倒计时
        now = pygame.time.get_ticks()
        last = getattr(game_state, "_banner_tick_ms", None)
        if last is None:
            game_state._banner_tick_ms = now
        else:
            dt = (now - last) / 1000.0
            game_state._banner_tick_ms = now
            game_state.banner_t = max(0.0, bt - dt)
            bt = game_state.banner_t
        # 简单淡入淡出（前后各 0.15s）：算一个 0~1 的可见度
        life = 1.5  # 你也可以把它做成变量
        t_used = life - bt
        vis = 1.0
        fade = 0.15
        if t_used < fade:
            vis = t_used / fade
        elif bt < fade:
            vis = bt / fade
        vis = max(0.0, min(1.0, vis))
        # 横幅底板尺寸与位置（屏幕中央）
        pad_x = 36
        bar_h = 64
        top_y = INFO_BAR_HEIGHT + 220
        banner_rect = pygame.Rect(pad_x, top_y, VIEW_W - pad_x * 2, bar_h)
        # 半透明底
        s = pygame.Surface(banner_rect.size, pygame.SRCALPHA)
        base_alpha = int(170 * vis)
        pygame.draw.rect(s, (20, 20, 20, base_alpha), s.get_rect(), border_radius=12)
        # 文字
        msg = str(getattr(game_state, "banner_text", ""))
        font_big = mono_font(34)
        txt = font_big.render(msg, True, (255, 230, 140))
        # 轻微描边让它更显眼
        shadow = font_big.render(msg, True, (0, 0, 0))
        s.blit(shadow, shadow.get_rect(center=(s.get_width() // 2 + 1, s.get_height() // 2 + 1)))
        s.blit(txt, txt.get_rect(center=(s.get_width() // 2, s.get_height() // 2)))
        screen.blit(s, banner_rect.topleft)
        banner_drawn = True
        # 倒计时结束后清理
        if game_state.banner_t <= 0.0:
            game_state.banner_text = None
    # ===== Bandit escape countdown (center briefly, then top-right flash) =====
    bandit_escape = None
    if enemies:
        for z in enemies:
            if getattr(z, "type", "") == "bandit":
                esc = float(getattr(z, "escape_t", BANDIT_ESCAPE_TIME_BASE))
                if bandit_escape is None or esc < bandit_escape:
                    bandit_escape = esc
    if bandit_escape is None:
        if hasattr(game_state, "bandit_countdown_center_t"):
            game_state.bandit_countdown_center_t = 0.0
        game_state._bandit_countdown_tick_ms = None
    else:
        center_t = float(getattr(game_state, "bandit_countdown_center_t", 0.0))
        if banner_drawn:
            game_state._bandit_countdown_tick_ms = None
        else:
            if center_t > 0.0:
                now = pygame.time.get_ticks()
                last = getattr(game_state, "_bandit_countdown_tick_ms", None)
                if last is None:
                    game_state._bandit_countdown_tick_ms = now
                else:
                    dt = (now - last) / 1000.0
                    game_state._bandit_countdown_tick_ms = now
                    center_t = max(0.0, center_t - dt)
                    game_state.bandit_countdown_center_t = center_t
            else:
                game_state._bandit_countdown_tick_ms = None
        esc = max(0.0, float(bandit_escape))
        secs = int(esc)
        centi = int((esc - secs) * 100)
        if centi > 99:
            centi = 99
        msg = f"{secs:02d}:{centi:02d}"
        if (not banner_drawn) and center_t > 0.0:
            font_big = mono_font(34)
            txt = font_big.render(msg, True, (255, 230, 140))
            pad_x = 36
            bar_h = 64
            top_y = INFO_BAR_HEIGHT + 220
            banner_rect = pygame.Rect(pad_x, top_y, VIEW_W - pad_x * 2, bar_h)
            s = pygame.Surface(banner_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(s, (20, 20, 20, 170), s.get_rect(), border_radius=12)
            shadow = font_big.render(msg, True, (0, 0, 0))
            s.blit(shadow, shadow.get_rect(center=(s.get_width() // 2 + 1, s.get_height() // 2 + 1)))
            s.blit(txt, txt.get_rect(center=(s.get_width() // 2, s.get_height() // 2)))
            screen.blit(s, banner_rect.topleft)
        elif not banner_drawn:
            font_small = mono_font(26)
            txt = font_small.render(msg, True, (255, 230, 140))
            pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.03)
            txt.set_alpha(int(170 + 85 * pulse))
            pad_x = 10
            pad_y = 5
            w = txt.get_width() + pad_x * 2
            h = txt.get_height() + pad_y * 2
            x = VIEW_W - w - 10
            y = INFO_BAR_HEIGHT + 6
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            bg_alpha = int(70 + 60 * pulse)
            border_alpha = int(140 + 80 * pulse)
            pygame.draw.rect(s, (10, 10, 10, bg_alpha), s.get_rect(), border_radius=10)
            pygame.draw.rect(s, (255, 220, 140, border_alpha), s.get_rect(), width=2, border_radius=10)
            shadow = font_small.render(msg, True, (0, 0, 0))
            shadow.set_alpha(int(120 + 60 * pulse))
            s.blit(shadow, (pad_x + 1, pad_y + 1))
            s.blit(txt, (pad_x, pad_y))
            screen.blit(s, (x, y))


def _find_current_boss(enemies):
    # 约定：任意 is_boss=True 的单位都当作 BOSS
    for z in enemies:
        if getattr(z, "is_boss", False):
            return z
    return None


def draw_boss_hp_bar(screen, boss):
    # ---- 尺寸与位置（顶栏下方一条大血条）----
    bar_w = min(720, max(420, int(VIEW_W * 0.55)))
    bar_h = 18
    bx = (VIEW_W - bar_w) // 2
    by = INFO_BAR_HEIGHT + 44
    # ---- 比例与文字 ----
    mhp = int(getattr(boss, "max_hp", max(1, boss.hp)))
    cur = max(0, int(boss.hp))
    ratio = 0.0 if mhp <= 0 else max(0.0, min(1.0, cur / float(mhp)))
    # 名称回退：优先 boss_name/_display_name → Memory Devourer → BOSS
    name = (getattr(boss, "boss_name", None)
            or getattr(boss, "_display_name", None)
            or ("Memory Devourer" if getattr(boss, "is_boss", False) else "BOSS"))
    # 背板/边框
    pygame.draw.rect(screen, (28, 28, 32), (bx - 2, by - 2, bar_w + 4, bar_h + 4), border_radius=8)
    pygame.draw.rect(screen, (52, 52, 60), (bx, by, bar_w, bar_h), border_radius=6)
    # 血量（红色填充）
    fill_w = int(bar_w * ratio)
    if fill_w > 0:
        pygame.draw.rect(screen, (210, 64, 64), (bx, by, fill_w, bar_h), border_radius=6)
    fill_w = int(bar_w * ratio)
    if fill_w > 0:
        pygame.draw.rect(screen, (210, 64, 64), (bx, by, fill_w, bar_h), border_radius=6)
    # --- Boss shield wrap (smoothed cyan) ---
    sh = int(max(0, getattr(boss, "shield_hp", 0)))
    target = 0.0 if mhp <= 0 else max(0.0, min(1.0, sh / float(mhp)))
    bvis = float(getattr(boss, "_hud_shield_vis", target))
    bvis += (target - bvis) * 0.20
    boss._hud_shield_vis = bvis
    if bvis > 0.001:
        bar_rect = pygame.Rect(bx, by, bar_w, bar_h)
        _draw_shield_shell(
            screen, bar_rect,
            start_ratio=0.0,
            length_ratio=bvis,  # fraction of max HP the shield represents
            expand=SHIELD_EXPAND_PX,
            edge_width=SHIELD_EDGE_WIDTH,
            edge_color=SHIELD_EDGE_COLOR,
            fill_color=SHIELD_FILL_COLOR
        )
    # 分段刻度（70%/40% 阶段线，方便读阶段）
    for t in (0.7, 0.4):
        tx = bx + int(bar_w * t)
        pygame.draw.line(screen, (90, 90, 96), (tx, by), (tx, by + bar_h), 1)
    # 标题与数值
    title_font = pygame.font.SysFont(None, 26, bold=True)
    small_font = pygame.font.SysFont(None, 22)
    title = title_font.render(str(name), True, (240, 240, 240))
    vals = small_font.render(f"{cur}/{mhp}", True, (235, 235, 235))
    title_shadow = pygame.font.SysFont(None, 26, bold=True).render(str(name), True, (0, 0, 0))
    screen.blit(title_shadow, title_shadow.get_rect(midbottom=(VIEW_W // 2 + 1, by - 3)))
    screen.blit(title, title.get_rect(midbottom=(VIEW_W // 2, by - 4)))
    screen.blit(vals, vals.get_rect(midleft=(bx + 8, by + bar_h + 4)))


def _find_all_bosses(enemies):
    return [z for z in enemies if getattr(z, "is_boss", False)]


def draw_boss_hp_bars_twin(screen, bosses):
    a, b = bosses[0], bosses[1]
    bar_w = min(720, max(420, int(VIEW_W * 0.55)))
    bar_h = 16
    bx = (VIEW_W - bar_w) // 2
    by = INFO_BAR_HEIGHT + 26  # 往下挪，避免和顶部信息重叠
    # —— 只显示一次标题（两只同名时不重复）——
    title_name = (getattr(a, "boss_name", None) or getattr(a, "_display_name", None)
                  or getattr(b, "boss_name", None) or getattr(b, "_display_name", None)
                  or "BOSS")
    title_font = pygame.font.SysFont(None, 26, bold=True)
    title = title_font.render(str(title_name), True, (240, 240, 240))
    screen.blit(title, title.get_rect(midbottom=(VIEW_W // 2, by - 6)))

    def draw_one(boss, y, color):
        mhp = max(1, int(getattr(boss, "max_hp", getattr(boss, "hp", 1))))
        cur = max(0, int(getattr(boss, "hp", 0)))
        ratio = max(0.0, min(1.0, cur / float(mhp)))
        # make shield obvious even at full HP
        sh = max(0, int(getattr(boss, "shield_hp", 0)))
        if sh > 0:
            frac = min(1.0, sh / float(mhp))
            _draw_shield_shell(
                screen,
                pygame.Rect(bx, y, bar_w, bar_h),
                start_ratio=0.0,  # always wrap from the left
                length_ratio=frac,  # shield as fraction of max HP
                expand=SHIELD_EXPAND_PX,
                edge_width=SHIELD_EDGE_WIDTH,
                edge_color=SHIELD_EDGE_COLOR,
                fill_color=SHIELD_FILL_COLOR
            )
        # 背板/描边
        pygame.draw.rect(screen, (28, 28, 32), (bx - 2, y - 2, bar_w + 4, bar_h + 4), border_radius=8)
        pygame.draw.rect(screen, (52, 52, 60), (bx, y, bar_w, bar_h), border_radius=6)
        # 填充
        if ratio > 0:
            pygame.draw.rect(screen, color, (bx, y, int(bar_w * ratio), bar_h), border_radius=6)
        # 阶段刻度
        for t in (0.7, 0.4):
            tx = bx + int(bar_w * t)
            pygame.draw.line(screen, (90, 90, 96), (tx, y), (tx, y + bar_h), 1)
        # 右侧数值
        small = pygame.font.SysFont(None, 20)
        vals = small.render(f"{cur}/{mhp}", True, (235, 235, 235))
        screen.blit(vals, vals.get_rect(bottomright=(bx + bar_w - 6, y + bar_h + 16)))

    y1 = by
    y2 = by + bar_h + 12  # 两条之间 12px 间距
    draw_one(a, y1, (210, 64, 64))
    draw_one(b, y2, (230, 120, 70))


def pause_game_modal(screen, bg_surface, clock, time_left, player):
    return pause_ui_support.pause_game_modal(_THIS_MODULE, screen, bg_surface, clock, time_left, player)

# --- Domain/Biome helpers (one-level-only effects) ---
def apply_domain_buffs_for_level(game_state, player):
    """
    Read the queued runtime biome and arm per-level flags/multipliers.
    All effects are temporary for THIS level only.
    """
    runtime = _runtime_state()
    b = runtime.get("_next_biome", None)
    game_state.biome_active = b
    runtime["_last_biome"] = b
    # Clear prior biome-only player speed buff (preserve other speed changes)
    prev_biome_mult = float(getattr(player, "_biome_speed_mult", 1.0))
    if abs(prev_biome_mult - 1.0) > 1e-4:
        player.speed = min(PLAYER_SPEED_CAP, max(1.0, player.speed / max(0.0001, prev_biome_mult)))
    player._biome_speed_mult = 1.0
    # Reset per-level knobs
    game_state.biome_enemy_contact_mult = 1.0
    game_state.biome_boss_contact_mult = 1.0
    game_state.biome_enemy_hp_mult = 1.0
    game_state.biome_boss_hp_mult = 1.0
    game_state.biome_bandit_hp_mult = 1.0
    game_state.biome_curing_paint_bonus = 0
    game_state._fog_biome_forced = False
    player.xp_gain_mult = 1.0
    game_state.hurricanes = []
    if b == "Misty Forest":
        # Same fog feel as Lv10
        game_state.request_fog_field(player)
        game_state._fog_biome_forced = True
        # Tradeoff: foggy vision but +30% XP gains
        player.xp_gain_mult = 1.3
    elif b == "Scorched Hell":
        # Player ×2; enemies ×2; bosses ×1.5
        player.bullet_damage = int(player.bullet_damage * 2)
        game_state.biome_enemy_contact_mult = 2.0
        game_state.biome_boss_contact_mult = 1.5
        game_state.biome_curing_paint_bonus = 1
    elif b == "Bastion of Stone":
        player.shield_hp = int(round(player.max_hp * 0.50))
        player.shield_max = player.shield_hp
        total_shield = player.shield_hp + max(0, getattr(player, "carapace_hp", 0))
        player._hud_shield_vis = total_shield / float(max(1, player.max_hp))
        # New spawns this level: mark Stone so we add shields on spawn
        game_state.biome_active = b
    elif b == "Domain of Wind":
        game_state.biome_active = b
        if not hasattr(game_state, "hurricanes"):
            game_state.hurricanes = []
        game_state.hurricanes.clear()
        map_w = GRID_SIZE * CELL_SIZE
        map_h = GRID_SIZE * CELL_SIZE
        px, py = player.rect.center
        min_dist = CELL_SIZE * 6  # keep away from player birth area
        margin = HURRICANE_MAX_RADIUS * 1.2
        hx, hy = map_w * 0.5, map_h * 0.5 + INFO_BAR_HEIGHT
        for _ in range(40):
            tx = random.uniform(margin, map_w - margin)
            ty = INFO_BAR_HEIGHT + random.uniform(margin, map_h - margin)
            if math.hypot(tx - px, ty - py) >= min_dist:
                hx, hy = tx, ty
                break
        game_state.spawn_hurricane(hx, hy)
        # Temp speed buff for this level
        player._biome_speed_mult = 1.12
        player.speed = min(PLAYER_SPEED_CAP, max(1.0, player.speed * player._biome_speed_mult))


def apply_biome_on_enemy_spawn(z, game_state):
    """
    Called right after a enemy (or bandit/boss) is created & appended.
    Only affects Bastion of Stone HP bump for now.
    """
    b = getattr(game_state, "biome_active", None)
    if b == "Bastion of Stone":
        if getattr(z, "type", "") in ("bandit",) or getattr(z, "is_boss", False):
            z.shield_hp = int(round(z.max_hp * 0.25))
            z.shield_max = z.shield_hp
        else:
            z.shield_hp = int(round(z.max_hp * 0.50))
            z.shield_max = z.shield_hp


def draw_shield_outline(screen, rect):
    # pulsing alpha for visibility
    t = pygame.time.get_ticks() * 0.006
    a = 120 + int(80 * (0.5 + 0.5 * math.sin(t)))
    # draw a rounded rectangle outline on a small alpha surface
    pad = 6
    s = pygame.Surface((rect.width + pad * 2, rect.height + pad * 2), pygame.SRCALPHA)
    pygame.draw.rect(s, (90, 180, 255, a), s.get_rect(), width=4, border_radius=6)
    screen.blit(s, s.get_rect(center=rect.center))


_SPRITE_ALPHA_MASK_CACHE: dict[int, pygame.Surface] = {}
_SPRITE_OUTLINE_CACHE: dict[int, dict] = {}
_RECT_SPRITE_CACHE: dict[tuple[int, int], pygame.Surface] = {}
_STATIONARY_TURRET_ASSET_CACHE: dict[str, object] = {}
_AUTO_TURRET_ASSET_CACHE: dict[str, pygame.Surface | None] = {}
_ENEMY_SPRITE_CACHE: dict[tuple[str, int], pygame.Surface | None] = {}


def _sprite_alpha_mask(sprite: "pygame.Surface") -> "pygame.Surface":
    key = id(sprite)
    mask = _SPRITE_ALPHA_MASK_CACHE.get(key)
    if mask is None or mask.get_size() != sprite.get_size():
        mask = sprite.copy()
        mask.fill((255, 255, 255, 255), special_flags=pygame.BLEND_RGB_MAX)
        _SPRITE_ALPHA_MASK_CACHE[key] = mask
    return mask


def blit_sprite_tint(screen: "pygame.Surface", sprite: "pygame.Surface",
                     dest_pos: tuple[int, int], color: tuple[int, int, int, int]) -> None:
    if sprite is None:
        return
    if len(color) == 3:
        color = (color[0], color[1], color[2], 255)
    tint = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
    tint.fill(color)
    tint.blit(_sprite_alpha_mask(sprite), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    screen.blit(tint, dest_pos)


def _sprite_outline_points(sprite: "pygame.Surface") -> list[tuple[int, int]]:
    key = id(sprite)
    cached = _SPRITE_OUTLINE_CACHE.get(key)
    if cached and cached.get("size") == sprite.get_size():
        return cached.get("pts", [])
    mask = pygame.mask.from_surface(sprite, 1)
    pts = mask.outline()
    _SPRITE_OUTLINE_CACHE[key] = {"size": sprite.get_size(), "pts": pts}
    return pts


def draw_sprite_outline(screen: "pygame.Surface", sprite: "pygame.Surface",
                        dest_pos: tuple[int, int], color: tuple[int, int, int, int],
                        width: int = 3) -> None:
    pts = _sprite_outline_points(sprite)
    if not pts:
        return
    ox, oy = dest_pos
    outline_pts = [(ox + x, oy + y) for x, y in pts]
    pygame.draw.lines(screen, color, True, outline_pts, max(1, int(width)))


def _rect_sprite(w: int, h: int) -> "pygame.Surface":
    key = (max(1, int(w)), max(1, int(h)))
    cached = _RECT_SPRITE_CACHE.get(key)
    if cached is not None:
        return cached
    surf = pygame.Surface(key, pygame.SRCALPHA)
    surf.fill((255, 255, 255, 255))
    _RECT_SPRITE_CACHE[key] = surf
    return surf


def get_stationary_turret_assets() -> tuple[pygame.Surface | None, int, int]:
    target = (int(STATIONARY_TURRET_MAX_W), int(STATIONARY_TURRET_MAX_H))
    sprite = _STATIONARY_TURRET_ASSET_CACHE.get("sprite")
    cached_size = _STATIONARY_TURRET_ASSET_CACHE.get("size")
    if sprite is None or cached_size != target:
        sprite = _load_shop_sprite(
            "props/Stationary Turret/Stationary Turret.png",
            target,
            allow_upscale=False,
        )
        _STATIONARY_TURRET_ASSET_CACHE.clear()
        _STATIONARY_TURRET_ASSET_CACHE["sprite"] = sprite
        _STATIONARY_TURRET_ASSET_CACHE["size"] = target
        if sprite:
            mask = pygame.mask.from_surface(sprite, 1)
            rects = mask.get_bounding_rects()
            bbox = rects[0] if rects else mask.get_rect()
            foot_w = max(12, int(bbox.width * STATIONARY_TURRET_FOOTPRINT_W_FRAC))
            foot_h = max(8, int(bbox.height * STATIONARY_TURRET_FOOTPRINT_H_FRAC))
        else:
            foot_w = foot_h = int(CELL_SIZE * 0.7)
        _STATIONARY_TURRET_ASSET_CACHE["foot_w"] = foot_w
        _STATIONARY_TURRET_ASSET_CACHE["foot_h"] = foot_h
    return (
        _STATIONARY_TURRET_ASSET_CACHE.get("sprite"),
        int(_STATIONARY_TURRET_ASSET_CACHE.get("foot_w", int(CELL_SIZE * 0.7)) or 0),
        int(_STATIONARY_TURRET_ASSET_CACHE.get("foot_h", int(CELL_SIZE * 0.7)) or 0),
    )


def _auto_turret_sprite(dir_key: str) -> pygame.Surface | None:
    dir_key = dir_key.lower()
    cached = _AUTO_TURRET_ASSET_CACHE.get(dir_key)
    if dir_key in _AUTO_TURRET_ASSET_CACHE:
        return cached
    path_map = {
        "right": "props/auto-turret/right.png",
        "left": "props/auto-turret/left.png",
        "up": "props/auto-turret/back.png",
        "down": "props/auto-turret/down(front).png",
    }
    path = path_map.get(dir_key)
    surf = None
    if path:
        surf = _load_shop_sprite(path, (AUTO_TURRET_MAX_W, AUTO_TURRET_MAX_H), allow_upscale=False)
    _AUTO_TURRET_ASSET_CACHE[dir_key] = surf
    return surf


def _enemy_sprite(ztype: str, size_px: int) -> pygame.Surface | None:
    key = (ztype, int(size_px))
    if key in _ENEMY_SPRITE_CACHE:
        return _ENEMY_SPRITE_CACHE[key]
    path_map = {
        "basic": "characters/enemies/basic/basic.png",
        "fast": "characters/enemies/fast/fast.png",
        "tank": "characters/enemies/tank/tank.png",
        "strong": "characters/enemies/strong/strong.png",
        "ranged": "characters/enemies/ranged/ranged.png",
        "buffer": "characters/enemies/buffer/buffer.png",
        "shielder": "characters/enemies/shielder/shielder.png",
        "ravager": "characters/enemies/ravager/ravager.png",
    }
    path = path_map.get(ztype, None)
    sprite = None
    if path:
        # match player visual scale (~2x footprint)
        target = (int(size_px * 2.0), int(size_px * 2.0))
        sprite = _load_shop_sprite(path, target, allow_upscale=False)
    _ENEMY_SPRITE_CACHE[key] = sprite
    return sprite


# ==================== 游戏常量配置 ====================
# NOTE: Keep design notes & TODOs below; do not delete when refactoring.
# - Card system UI polish (later pass)
# - Sprite/animation pipeline to be added
# - Balance obstacle density via OBSTACLE_DENSITY/DECOR_DENSITY
GAME_TITLE = "NEURONVIVOR"
INFO_BAR_HEIGHT = 40
GRID_SIZE = 36
WORLD_SCALE = 1.3
BASE_CELL_SIZE = 40
CELL_SIZE = int(BASE_CELL_SIZE * WORLD_SCALE)
WINDOW_SIZE = GRID_SIZE * CELL_SIZE
TOTAL_HEIGHT = WINDOW_SIZE + INFO_BAR_HEIGHT
# Viewport (overridden at runtime when display is created)
VIEW_W = WINDOW_SIZE
VIEW_H = TOTAL_HEIGHT
OBSTACLE_HEALTH = 20
MAIN_BLOCK_HEALTH = 40
# --- view style ---
USE_ISO = True  # True: 伪3D等距渲染；False: 保持现在的纯2D
ISO_CELL_W = int(64 * WORLD_SCALE)  # 等距砖块在画面上的“菱形”宽
ISO_CELL_H = int(32 * WORLD_SCALE)  # 等距砖块在画面上的“菱形”半高（顶点到中心）
ISO_WALL_Z = int(22 * WORLD_SCALE)  # 障碍“墙体”抬起的高度（屏幕像素）
ISO_SHADOW_ALPHA = 90  # 椭圆阴影透明度
SPATIAL_CELL = int(CELL_SIZE * 1.25)  # 统一网格大小
WALL_STYLE = "hybrid"  # "billboard" | "prism" | "hybrid"
ISO_EQ_GAIN = math.sqrt(2) * (ISO_CELL_W * 0.5)
# --- unified UI palette (matches homepage style) ---
UI_BG = (16, 19, 26)
UI_PANEL = (24, 28, 38)
UI_PANEL_DARK = (18, 21, 30)
UI_BORDER = (88, 140, 200)
UI_BORDER_HOVER = (140, 200, 255)
UI_ACCENT = (120, 220, 255)
UI_ACCENT_WARM = (255, 140, 120)
UI_TEXT = (235, 240, 245)
MAP_BG = UI_BG
MAP_GRID = (44, 50, 60)
_SEKUYA_FONT_CACHE: dict[int, pygame.font.Font] = {}


def _get_sekuya_font(size: int) -> pygame.font.Font:
    """Load Sekuya font from assets/fonts; fallback to default if missing."""
    if size in _SEKUYA_FONT_CACHE:
        return _SEKUYA_FONT_CACHE[size]
    try:
        path = _first_existing_path([
            *_asset_candidates("fonts", "Sekuya-Regular.ttf"),
            *_asset_candidates("fonts", "Sekuya.ttf"),
        ])
        if not path:
            raise FileNotFoundError("Sekuya font not found")
        font = pygame.font.Font(path, size)
    except Exception:
        font = pygame.font.SysFont(None, size)
    _SEKUYA_FONT_CACHE[size] = font
    return font
# 角色圆形碰撞半径
PLAYER_RADIUS = int(CELL_SIZE * 0.30)  # matches 0.6×CELL_SIZE footprint
PLAYER_SPRITE_SCALE = 1.2  # visual-only scale vs collision footprint
ENEMY_RADIUS = int(CELL_SIZE * 0.30)
TANK_SIZE_MULT = 0.80  # tank footprint vs CELL_SIZE; slightly larger than basic
SHIELDER_SIZE_MULT = 0.80  # shielder footprint vs CELL_SIZE; bulkier for presence
STRONG_SIZE_MULT = 0.70  # strong footprint vs CELL_SIZE; hits harder visually too
HIT_FLASH_DURATION = 0.18  # seconds a white hit flash stays on screen
# 成长模式：'linear'（当前默认）或 'exp'（推荐）
MON_SCALE_MODE = "exp"  # "linear" / "exp"
MON_HP_GROWTH_PER_LEVEL = 0.08  # HP 每关 +8% 复利到软帽
MON_ATK_GROWTH_PER_LEVEL = 0.09  # ATK 每关 +9% 复利到软帽
MON_HP_GROWTH_PER_WAVE = 0.03  # HP 每波 +3% 复利
MON_ATK_GROWTH_PER_WAVE = 0.03  # ATK 每波 +3% 复利
MON_SOFTCAP_LEVEL = 10  # 关卡软帽起点
MON_SOFTCAP_FACTOR = 0.40  # 软帽后有效增长强度只有 40%
# --- map fill tuning ---
OBSTACLE_DENSITY = 0.14  # proportion of tiles to become obstacles (including clusters)
DECOR_DENSITY = 0.06  # proportion of tiles to place non-blocking decorations
MIN_ITEMS = 8  # ensure enough items on larger maps
DESTRUCTIBLE_RATIO = 0.3
PLAYER_SPEED = 4.5
PLAYER_SPEED_CAP = 6.5
ENEMY_SPEED = 2
ENEMY_SPEED_MAX = 4.0
ENEMY_ATTACK = 10
# --- next-level scene buff cards ---
SCENE_BIOMES = ["Domain of Wind", "Misty Forest", "Scorched Hell", "Bastion of Stone"]
_next_biome = None  # 记录玩家本关在商店后选择的“下关场景”
# === Wind Biome Tuning ===
# TORNADO_FUNNEL_HEIGHT = 160        # Visual height in pixels
# TORNADO_LAYER_COUNT = 12           # How many "slices" to draw for the 3D effect
# TORNADO_COLOR_CORE = (180, 200, 220)
# TORNADO_COLOR_EDGE = (100, 110, 130)

# Physics
HURRICANE_ROTATION_SPEED = 6.0     # Radians/sec (Spin speed)
HURRICANE_PULL_STRENGTH = 180.0    # Suction speed (pixels/sec) — gentler pull
HURRICANE_VORTEX_POWER = 450.0     # Orbital force (how hard it spins enemies)
# Visuals
TORNADO_FUNNEL_HEIGHT = 160        # Taller funnel
TORNADO_LAYER_COUNT = 16           # More slices for smoother 3D look
# "Neuro" Colors
TORNADO_CORE_COLOR = (140, 220, 255) # Light Cyan/Blue
TORNADO_EDGE_COLOR = (60, 100, 130)  # Darker Blue/Grey edges
# Wind Particle Colors (Grey & Light Green as requested)
WIND_PARTICLE_COLORS = [
    (180, 190, 200), # Light Grey
    (160, 210, 160), # Light Green
    (200, 235, 200), # Pale Green
]
# --- Splinter family tuning ---
SPLINTER_CHILD_COUNT = 3
SPLINTER_CHILD_HP_RATIO = 0.20  # each child = 20% of parent's MAX HP
SPLINTERLING_ATK_RATIO = 0.60  # child attack ~60% of parent's attack
SPLINTERLING_SPD_ADD = 1  # child runs a bit faster
SPLINTER_UNLOCK_LEVEL = 2  # 0-based: unlock at Lv3 (after level 2)
# ----- meta progression -----
SPOILS_PER_KILL = 3
SPOILS_PER_BLOCK = 1
# ----- spoils UI & drop tuning -----
SPOILS_DROP_CHANCE = 0.35  # 35% drop chance on enemy deaths
SPOILS_BLOCK_DROP_CHANCE = 0.50  # 50% 概率掉 1 枚（必要时再调）
# ----- enemy coin absorption scaling -----
COIN_ABSORB_TIER1_MAX_COINS = 10
COIN_ABSORB_TIER2_MAX_COINS = 20
COIN_ABSORB_SCALE_TIER1 = 1.10  # ~+10% by 10 coins
COIN_ABSORB_SCALE_TIER2 = 1.25  # ~+25% by 20 coins
COIN_ABSORB_SCALE_TIER3 = 1.40  # cap scale for 20+ coins
NAV_CLEAR_RADIUS = max(
    PLAYER_RADIUS,
    int(CELL_SIZE * 0.6 * COIN_ABSORB_SCALE_TIER3 * 0.5),
)  # ensure enlarged basics can navigate passages
SPOILS_PER_TYPE = {  # average coins per enemy type (rounded when spawning)
    "basic": (1, 1),  # min, max
    "fast": (1, 2),
    "strong": (2, 3),
    "tank": (2, 4),
    "ranged": (1, 3),
    "suicide": (1, 2),
    "buffer": (2, 3),
    "shielder": (2, 3),
    "bomber": (1, 2),  # alias for suicide, if used
    "splinter": (1, 2),
    "splinterling": (0, 1),
    "ravager": (2, 5),
}
# --- Twin Boss (Level 5 only) ---
ENABLE_TWIN_BOSS = True
TWIN_BOSS_LEVELS = {4}  # 关卡索引从0开始，4==第5关
TWIN_ENRAGE_ATK_MULT = 1.35
TWIN_ENRAGE_SPD_ADD = 1
# --- boss footprint (2x2 tiles) ---
BOSS_FOOTPRINT_TILES = 2  # 占格：2x2
BOSS_VISUAL_MARGIN = 6  # 视觉矩形边缘略收一点，避免贴边穿帮
BOSS_RADIUS_SHRINK = 0.98  # 圆半径微缩，减少“卡像素”感
# === Boss Skill Tunables ===
BOSS_SKILLS_ENABLED_LEVELS = {4}  # Lv-5 twin (0-indexed)
BOSS_TOXIC_DASH_CD = 6.0
BOSS_TOXIC_DASH_WINDUP = 0.65
BOSS_TOXIC_DASH_TIME = 0.55
BOSS_TOXIC_DASH_SPEED_MULT = 3.25
BOSS_VOMIT_CD = 5.0
BOSS_VOMIT_COUNT = 7
BOSS_VOMIT_CONE_DEG = 55
BOSS_VOMIT_SPEED = 380
BOSS_VOMIT_ARC_SEC = 0.45
BOSS_SUMMON_CD = 10.0
BOSS_SUMMON_COUNT = (3, 5)  # min, max
ACID_POOL_DPS = 10  # damage / second
ACID_POOL_SLOW = 0.35  # extra slow
ACID_POOL_TIME = 6.0
ACID_POOL_RADIUS_PX = int(CELL_SIZE * 0.65)
SMALL_PUDDLE_TIME = 4.0
SMALL_PUDDLE_RADIUS = int(CELL_SIZE * 0.45)
# Optional enrage ring
BOSS_RING_ENABLED = True
BOSS_RING_BURSTS = 2
BOSS_RING_PROJECTILES = 20
BOSS_RING_SPEED = 420
BOSS_RING_CD = 4.0
# === Dash & Afterimage tunables ===
BOSS_DASH_WINDUP = 0.40  # 蓄力前摇（保留张力）
BOSS_DASH_GO_TIME = 0.60  # 冲刺持续时间（原来 0.28 太短）
BOSS_DASH_SPEED_MULT = 4.2  # 冲刺速度倍数（原来 3.5 偏保守）
BOSS_DASH_SPEED_MULT_ENRAGED = 4.8  # 激怒版可更高一点
AFTERIMAGE_INTERVAL = 0.02  # 约每 1/50 秒一个（轨迹更连续）
AFTERIMAGE_TTL = 0.40  # ~6 帧消失（60fps）
AFTERIMAGE_LIGHTEN = 1.20  # 轻微提亮，保持“浅色块”而不是荧光
# coin bounce feel
COIN_POP_VY = -120.0  # initial vertical (screen-space) pop
COIN_GRAVITY = 400.0  # gravity pulling coin back to ground
COIN_RESTITUTION = 0.45  # energy kept on bounce
COIN_MIN_BOUNCE = 30.0  # stop bouncing when below this upward speed
COIN_PICKUP_RADIUS_BASE = 60  # small default coin pickup buffer (px)
RAVAGER_HP_MULT = 10.0  # Ravager: 10x base HP
RAVAGER_ATK_MULT = 2.0  # 2.0x contact damage
RAVAGER_SIZE_MULT = 1.25  # bigger than normal, smaller than boss
RAVAGER_CONTACT_MULT = 2.0  # scales contact damage
RAVAGER_DASH_CD_RANGE = (3.0, 4.5)
RAVAGER_DASH_WINDUP = 0.30
RAVAGER_DASH_TIME = 0.65
RAVAGER_DASH_SPEED_MULT = 2.0
XP_PLAYER_KILL = 6
XP_PLAYER_BLOCK = 2
XP_ENEMY_BLOCK = 3
XP_TRANSFER_RATIO = 0.7  # special → survivors
# --- shop pricing (level-scaled) ---
SHOP_PRICE_EXP = 1.12  # 每关指数涨幅（与 roguelite 节奏接近，10 关≈3.1x）
SHOP_PRICE_LINEAR = 0.02  # 每关线性微调（让早期也能感受到一点涨价）
SHOP_PRICE_STACK = 1.15  # 同一条目多次购买的叠加涨幅
SHOP_PRICE_REROLL_EXP = 1.06  # Reroll 的涨价更温和
SHOP_PRICE_REROLL_STACK = 1.25  # 多次 Reroll 叠加更贵（防刷）
COUPON_DISCOUNT_PER = 0.05  # each Coupon gives 5% off all shop prices this run
COUPON_MAX_LEVEL = 4
GOLDEN_INTEREST_RATE_PER_LEVEL = 0.05  # 5%/lvl interest on unspent coins
GOLDEN_INTEREST_CAPS = (30, 50, 70, 90)  # per-wave caps by level (1-4)
GOLDEN_INTEREST_MAX_LEVEL = 4
SHADY_LOAN_MAX_LEVEL = 3
SHADY_LOAN_INSTANT_GOLD = (80, 120, 160)
SHADY_LOAN_BASE_DEBT = (96, 144, 192)  # total debt added per purchase (higher than upfront)
SHADY_LOAN_DEBT_RATES = (0.25, 0.30, 0.35)
SHADY_LOAN_DEBT_CAPS = (50, 80, 110)
SHADY_LOAN_HP_PENALTIES = (0.30, 0.35, 0.40)
WANTED_POSTER_WAVES = 2
WANTED_POSTER_BOUNTY_BASE = 30
INTRO_ANALYZE_MS = 30  # window step for intro waveform (ms)
LOCKBOX_PROTECT_RATES = (0.25, 0.40, 0.55, 0.70)
LOCKBOX_MAX_LEVEL = len(LOCKBOX_PROTECT_RATES)
BANDIT_RADAR_SLOW_MULT = (0.92, 0.88, 0.84, 0.80)
BANDIT_RADAR_SLOW_DUR = (2.0, 3.0, 4.0, 5.0)
# ----- healing drop tuning -----
HEAL_DROP_CHANCE_ENEMY = 0.08  # 8% when a enemy dies
HEAL_DROP_CHANCE_BLOCK = 0.03  # 3% when a destructible block is broken
HEAL_POTION_AMOUNT = 6  # HP restored on pickup (capped to player.max_hp)
HEAL_MAX_ON_FIELD = 18  # cap active heals to avoid clutter spikes (e.g., long boss waves)
# ----- player XP rewards by enemy type -----
XP_PER_ENEMY_TYPE = {
    "basic": 6,
    "fast": 7,
    "ranged": 7,
    "strong": 10,
    "tank": 12,
    "suicide": 9,  # if killed before it explodes
    "buffer": 6,
    "shielder": 8,
    "splinter": 8,
    "splinterling": 4,
}
XP_ZLEVEL_BONUS = 2  # bonus XP per enemy level above 1
ENEMY_XP_TO_LEVEL = 15  # per level step for monsters
PLAYER_XP_TO_LEVEL = 30  # base; scales by +20%
# --- enemy spoils empowerment ---
Z_SPOIL_HP_PER = 1  # 每 1 金币：+1 MaxHP & +1 当期HP
Z_SPOIL_ATK_STEP = 5  # 每 5 金币：+1 攻击
Z_SPOIL_SPD_STEP = 10  # 每 10 金币：+0.5 速度
Z_SPOIL_SPD_ADD = 0.5
Z_SPOIL_SPD_CAP = float(ENEMY_SPEED_MAX)  # 速度上限（保持与你总上限一致）
Z_SPOIL_XP_BONUS_PER = 1  # 击杀时额外经验=每枚金币+1 XP
Z_GLOW_TIME = 0.35  # 捡到金币时金色光晕持续时间（秒）
# ----- player XP curve tuning -----
# Requirement to go from level L -> L+1:
#   base * (exp_growth ** (L-1)) + linear_growth * L + softcap_bump(L)
XP_CURVE_EXP_GROWTH = 1.12  # 10–13% feels good for roguelites; we use 12%
XP_CURVE_LINEAR = 3  # small linear term to smooth gaps
XP_CURVE_SOFTCAP_START = 7  # start softly increasing after level 7
XP_CURVE_SOFTCAP_POWER = 1.6  # how sharp the softcap rises (1.4–1.8 typical)
# ----- monster global scaling (by game level & wave) -----
MON_HP_GROWTH_PER_LEVEL = 0.10  # +10% HP per game level
MON_ATK_GROWTH_PER_LEVEL = 0.08  # +8% ATK per game level
MON_SPD_ADD_EVERY_LEVELS = 4  # +1 speed every N levels (soft cap below)
MON_SOFTCAP_LEVEL = 10  # reduce growth beyond this (diminishing)
MON_SOFTCAP_FACTOR = 0.6  # scale growth beyond softcap by this factor
MON_HP_GROWTH_PER_WAVE = 0.06  # +6% HP per wave
MON_ATK_GROWTH_PER_WAVE = 0.05  # +5% ATK per wave
MON_SPD_ADD_EVERY_WAVES = 6  # +1 speed every N waves
# ----- elites & bosses -----
ELITE_BASE_CHANCE = 0.08  # 8% at level 1
ELITE_CHANCE_PER_LEVEL = 0.02  # +2% per game level (clamped)
ELITE_MAX_CHANCE = 0.35
ELITE_HP_MULT_EXTRA = 1.6  # multiplicative on top of normal scaling
ELITE_ATK_MULT_EXTRA = 1.4
ELITE_SPD_ADD_EXTRA = 1
BOSS_EVERY_N_LEVELS = 5
BOSS_HP_MULT_EXTRA = 3.0
BOSS_ATK_MULT_EXTRA = 2.0
BOSS_SPD_ADD_EXTRA = 1
# ===== Boss1: Memory Devourer (腐蚀集群之心) =====
# 数值：显著增厚血量与接触伤害
MEMDEV_BASE_HP = 2000  # 基于第5关
MEMDEV_CONTACT_DAMAGE = 60  # 接触伤害提高
MEMDEV_SPEED = 1.5  # 很慢（后续阶段再涨）
# Boss 外形/占格（仅碰撞与显示，不改变地图阻挡规则）
BOSS_SIZE_FACTOR = 3.65  # 可视尺寸 = 1.65 × 单格
BOSS_RADIUS_FACTOR = 1.80  # 脚底圆半径 = 0.90 × 单格（≈直径1.8格，能“卡住”单格通道）
# Boss 掉落（保证性掉落，额外返还它吞的金币）
BOSS_LOOT_MIN = 24
BOSS_LOOT_MAX = 36
BOSS_HEAL_POTIONS = 2  # 击杀掉落的治疗瓶数量
# P1 / P2 酸液喷吐（地面腐蚀池）
ACID_DPS = 15  # 站上去每秒伤害
ACID_SLOW_FRAC = 0.45  # 减速 45%
ACID_LIFETIME = 6.0
ACID_TELEGRAPH_T = 0.6  # 提示圈时长
ACID_DOT_DURATION = 2.0  # 离开酸池后继续掉血的持续时间(秒)
ACID_DOT_MULT = 0.6  # DoT 的每秒伤害 = ACID_DPS * 这个系数
SPIT_WAVES_P1 = 3
SPIT_WAVES_P2 = 2  # 连续两次喷吐（每次多波）
SPIT_CONE_DEG = 60
SPIT_PUDDLES_PER_WAVE = 6
SPIT_RANGE = 6.0 * CELL_SIZE  # 每波最远生成点
# 召唤小怪（腐蚀幼体）
SPLIT_CD_P1 = 12.0
SPLIT_CD_P2 = 7.0
CHILD_HP = 50
CHILD_ATK = 10
CHILD_SPEED = 2.2
# 吸附融合（小怪>15s被拉回，BOSS 恢复100）
FUSION_LIFETIME = 15.0
FUSION_HEAL = 100
FUSION_PULL_RADIUS = 8.0 * CELL_SIZE
# P3 全屏酸爆（每掉 10% 触发一次）
RAIN_STEP = 0.10
RAIN_PUDDLES = 18
RAIN_TELEGRAPH_T = 0.5
# 濒死冲锋（<10%）
CHARGE_THRESH = 0.10
CHARGE_SPEED = 3.0
# ===== Coin Bandit（金币大盗）常量 =====
BANDIT_MIN_LEVEL_IDX = 2  # 前两关不出现（0基索引：2=第三关）
BANDIT_SPAWN_CHANCE_PER_WAVE = 0.28  # 每个非Boss波次独立检定（每关最多1只）
BANDIT_BASE_HP = 150  
BANDIT_BASE_SPEED = 2.35  # 相对普通僵尸更快（再叠加z_level等成长）
BANDIT_ESCAPE_TIME_BASE = 18.0  # 逃跑倒计时（秒）
BANDIT_ESCAPE_TIME_MIN = 10.0  # 下限
BANDIT_COUNTDOWN_CENTER_TIME = 1.0  # center countdown duration before moving to top-right
BANDIT_HP_DPS_MULT_MIN = 2.6  # Lv3-5: lower DPS scaling
BANDIT_HP_DPS_MULT_MID = 3.1  # Lv6-10: medium DPS scaling
BANDIT_HP_DPS_MULT_MAX = 4.0  # Lv11+: cap (matches previous tuning)
BANDIT_STEAL_RATE_MIN = 2  # 每秒最少偷取金币
BANDIT_STEAL_RATE_MAX = 10  # 每秒最多偷取金币
BANDIT_BONUS_RATE = 0.25  # 击杀后额外奖励比例（在偷取总额基础上再+25%）
BANDIT_BONUS_FLAT = 2  # 击杀后额外固定奖励
BANDIT_FLEE_RADIUS = 4 * CELL_SIZE  # run away when player gets this close
BANDIT_FLEE_SPEED_MULT = 1.4
BANDIT_BREAK_SLOW_TIME = 0.6
BANDIT_BREAK_SLOW_MULT = 0.55
# --- Mistweaver (Boss II) — appears at Lv10 (index 9) ---
MISTWEAVER_LEVELS = {9}  # 0-based：第10关
MIST_BASE_HP = 8000
MIST_CONTACT_DAMAGE = 28
MIST_SPEED = 2.2  # 略慢于玩家
MISTLING_LIFETIME = 10.0
MISTLING_BLAST_RADIUS = 70
MISTLING_BLAST_DAMAGE = 18
MISTLING_PULL_RADIUS = int(7.5 * CELL_SIZE)
MISTLING_HEAL = 120
XP_PER_ENEMY_TYPE["mistling"] = 5
MIST_RING_BURSTS = 3
MIST_RING_PROJECTILES = 28
MIST_RING_SPEED = 420.0
MIST_RING_CD = 5.5
MIST_RING_DAMAGE = 18
# 统一的地面危害样式
HAZARD_STYLES = {
    "acid": {  # 绿色腐蚀
        "fill": (70, 200, 100),  # 主色
        "ring": (150, 255, 170),  # 外圈高光
        "particle": (120, 230, 140),
    },
    "mist": {  # 冷色雾池
        "fill": (160, 170, 220),
        "ring": (210, 220, 255),
        "particle": (200, 210, 240),
    },
    "mist_door": {  # 雾门：更偏白、带脉冲圈
        "fill": (190, 200, 255),
        "ring": (240, 245, 255),
        "particle": (220, 230, 255),
        "pulse": True
    },
    "dash_mist": {
        "fill": (190, 195, 255),
        "ring": (245, 246, 255),
        "particle": (220, 225, 255),
    }
}
# Fog field (被动视野压缩)
FOG_VIEW_TILES = 6  # 约 6 格视距
FOG_OVERLAY_ALPHA = 190  # 覆雾不透明度
FOG_LANTERN_COUNT = 3  # 地图生成 3 个“驱雾灯笼”
FOG_LANTERN_HP = 60
FOG_LANTERN_CLEAR_RADIUS = int(CELL_SIZE * 3.2)  # 灯笼清雾半径（~3~4格）
# 雾门闪现
MIST_BLINK_CD = 10.0
MIST_DOOR_STAY = 2.0
MIST_DOOR_DPS = 5
MIST_DOOR_SLOW = 0.20
# P1
MIST_P1_BLADE_CD = 3.5
MIST_P1_BLADE_COUNT = 3  # 扇形 3 枚
MIST_P1_STRIP_TIME = 1.2
MIST_P1_STRIP_DPS = 10
MIST_P1_STRIP_SLOW = 0.35
MIST_SUMMON_IMPS = 3  # 每轮召唤 3 个 Wormling
# P2
MIST_P2_STORM_CD = 8.0
MIST_P2_STORM_WIND = 0.8
MIST_P2_STORM_POINTS = 8
MIST_P2_POOL_DPS = 14
MIST_P2_POOL_SLOW = 0.40
MIST_SILENCE_TIME = 3.0
MIST_SILENCE_RADIUS = int(CELL_SIZE * 3.0)
# P3
MIST_SONAR_STEP = 0.10  # 每掉 10% 触发一次
MIST_MARK_TIME = 3.0  # 被声纳命中后“被标记”时长
MIST_CHASE_BOOST = 1.0  # 标记时 Boss 额外 +1.0 速度
MIST_PHASE_CHANCE = 0.15  # 受击 15% 雾化
MIST_PHASE_TIME = 0.7
MIST_PHASE_TELE_TILES = 2.0  # 雾化时瞬位 2 格
# 远程伤害抗性（>=5格距离 → 0.8x）
MIST_RANGED_REDUCE_TILES = 5
MIST_RANGED_MULT = 0.8
# ----- affixes (small random spice) -----
AFFIX_CHANCE_BASE = 0.10
AFFIX_CHANCE_PER_LEVEL = 0.02
AFFIX_CHANCE_MAX = 0.45
# ----- spoils & XP inheritance tuning -----
XP_INHERIT_RADIUS = 240  # px: who is "nearby" to inherit XP
ENEMY_SIZE_MAX = int(CELL_SIZE * 1.8)  # cap size when buffed by XP
SPOIL_POP_VY = -30  # initial pop-up velocity for coin
SPOIL_GRAVITY = 80  # settle speed for coin pop
BOSS_EVERY_N_LEVELS = 5
BOSS_HP_MULT = 4.0
BOSS_ATK_MULT = 2.0
BOSS_SPD_ADD = 1
# --- combat tuning  ---
FIRE_RATE = None  # shots per second; if None, derive from BULLET_SPACING_PX
# --- survival mode & player health ---
LEVEL_TIME_LIMIT = 45.0  # seconds per run
BOSS_TIME_LIMIT = 60.0  # seconds for boss levels
PLAYER_MAX_HP = 40  # player total health
ENEMY_CONTACT_DAMAGE = 18  # damage per contact tick
PLAYER_HIT_COOLDOWN = 0.6  # seconds of i-frames after taking contact damage
# Fire-rate balance caps
MAX_FIRERATE_MULT = 2.0  # hard cap on multiplier (≈2x base)
MIN_FIRE_COOLDOWN = 0.12  # never shoot faster than once every 0.12s (~8.3/s)
BULLET_SPEED = 1000.0  # pixels per second (controls travel speed)
BULLET_SPACING_PX = 260.0  # desired spacing between bullets along their path
BULLET_RADIUS = 4
BULLET_RADIUS_MAX = 16
BULLET_DAMAGE_ENEMY = 12
BULLET_DAMAGE_BLOCK = 10
ENEMY_SHOT_DAMAGE_BLOCK = BULLET_DAMAGE_BLOCK
PLAYER_RANGE_DEFAULT = 400.0  # pixels; baseline player shooting range
PLAYER_RANGE_MAX = 800.0  # pixels; hard cap on player targeting/shooting range
MAX_FIRE_RANGE = PLAYER_RANGE_DEFAULT  # legacy alias for the baseline range
# --- Auto-turret tuning ---
AUTO_TURRET_BASE_DAMAGE = max(1, BULLET_DAMAGE_ENEMY // 3)  # weak-ish bullets
AUTO_TURRET_FIRE_INTERVAL = 0.9  # seconds between shots
AUTO_TURRET_RANGE_MULT = 0.8  # fraction of player range
AUTO_TURRET_OFFSET_RADIUS = 40.0  # distance from player center
AUTO_TURRET_ORBIT_SPEED = 2.0  # radians per second
AUTO_TURRET_MAX_W = int(CELL_SIZE * 0.55)  # ~half player footprint width
AUTO_TURRET_MAX_H = int(CELL_SIZE * 0.50)
STATIONARY_TURRET_MAX_W = int(CELL_SIZE * 1.35)
STATIONARY_TURRET_MAX_H = int(CELL_SIZE * 1.18)
STATIONARY_TURRET_FOOTPRINT_W_FRAC = 0.78  # portion of sprite bbox used for collision width
STATIONARY_TURRET_FOOTPRINT_H_FRAC = 0.45  # focus collision on the lower silhouette
# --- targeting / auto-aim (new) ---
PLAYER_TARGET_RANGE = PLAYER_RANGE_DEFAULT  # 射程内才会当候选（默认=子弹射程）
PLAYER_BLOCK_FORCE_RANGE_TILES = 2  # 玩家两格内遇到可破坏物 → 强制优先

# Range helpers keep player targeting/shooting within the intended cap.
def clamp_player_range(range_val: float) -> float:
    try:
        val = float(range_val)
    except Exception:
        return PLAYER_RANGE_DEFAULT
    return max(0.0, min(PLAYER_RANGE_MAX, val))


def compute_player_range(base_range: float, mult: float = 1.0) -> float:
    base = clamp_player_range(base_range)
    return clamp_player_range(base * float(mult))


def sanitize_meta_range(meta: dict) -> None:
    """Normalize META/base range to the intended defaults/caps."""
    if not isinstance(meta, dict):
        return
    base = clamp_player_range(meta.get("base_range", PLAYER_RANGE_DEFAULT))
    if base <= 0.0:
        base = PLAYER_RANGE_DEFAULT
    meta["base_range"] = base
    max_mult = PLAYER_RANGE_MAX / max(1.0, base)
    try:
        mult = float(meta.get("range_mult", 1.0))
    except Exception:
        mult = 1.0
    meta["range_mult"] = max(0.0, min(mult, max_mult))

# --- CRIT & damage text ---
CRIT_CHANCE_BASE = 0.05  # 基础暴击率=5%
CRIT_MULT_BASE = 1.8  # 暴击伤害倍数，后续可以做商店项
DMG_TEXT_TTL = 0.8  # 飘字存活时长（秒）
DMG_TEXT_RISE = 42.0  # 垂直上升速度（像素/秒）
DMG_TEXT_FADE = 0.25  # 尾段淡出比例（最后 25% 时间开始透明）
DMG_TEXT_SIZE_NORMAL = 28
DMG_TEXT_SIZE_CRIT = 38
# --- Active skills (player) ---
BLAST_RADIUS = 140  # px radius for fixed-point blast
BLAST_HITS_MIN = 8
BLAST_HITS_MAX = 14
BLAST_DMG_MULT = 0.70
BLAST_COOLDOWN = 10.0
BLAST_CAST_RANGE = 400.0  # baseline blast placement range (at least basic attack range)
TELEPORT_RANGE = 320.0  # max distance from player center
TELEPORT_COOLDOWN = 6.0
# --- Bone Plating ---
BONE_PLATING_STACK_HP = 2
BONE_PLATING_GAIN_INTERVAL = 6.0
BONE_PLATING_MAX_LEVEL = 5
BONE_PLATING_COLOR = (210, 235, 255)
BONE_PLATING_GLOW = (200, 245, 255, 140)
# --- Aegis Pulse (shield-synergy pulse) ---
AEGIS_PULSE_BASE_RADIUS = 100
AEGIS_PULSE_RADIUS_PER_LEVEL = 20
AEGIS_PULSE_BASE_DAMAGE = 15
AEGIS_PULSE_DAMAGE_PER_LEVEL = 7
AEGIS_PULSE_BASE_COOLDOWN = 4.0
AEGIS_PULSE_COOLDOWN_DELTA = 0.625
AEGIS_PULSE_TTL = 0.40  # legacy linger time (kept for backward compat of saves)
AEGIS_PULSE_DAMAGE_RATIOS = (0.30, 0.45, 0.60, 0.80, 1.00)  # % of max HP per level (1-5+)
AEGIS_PULSE_WAVE_GAP = 0.35  # seconds between multi-wave pulses
AEGIS_PULSE_COLOR = (120, 215, 255)
AEGIS_PULSE_FILL_ALPHA = 18  # lighter fill to avoid distracting cover
AEGIS_PULSE_RING_ALPHA = 200
# Visual layering for the expanding ripple
AEGIS_PULSE_BASE_LAYERS = 2  # minimum concentric rings
AEGIS_PULSE_LAYERS_PER_LEVEL = 0.5  # +1 layer every 2 levels (ceil)
AEGIS_PULSE_MAX_LAYERS = 6
AEGIS_PULSE_BASE_EXPAND_TIME = 1.0  # seconds for a ripple to reach full radius at lvl 1
AEGIS_PULSE_EXPAND_DELTA = 0.06  # faster expansion per level
AEGIS_PULSE_MIN_EXPAND_TIME = 0.45
AEGIS_PULSE_RING_FADE = 0.20
AEGIS_PULSE_MIN_START_R = 12
# --- Explosive Rounds (on-kill splash) ---
EXPLOSIVE_ROUNDS_RADIUS_MULTS = (0.65, 0.80, 0.95)
EXPLOSIVE_ROUNDS_DAMAGE_MULTS = (0.25, 0.35, 0.45)
EXPLOSIVE_ROUNDS_BOSS_MULT = 0.50
EXPLOSIVE_ROUNDS_FLASH_COLOR = (255, 200, 120)
EXPLOSIVE_ROUNDS_FLASH_TTL = (0.15, 0.22)
EXPLOSIVE_ROUNDS_FLASH_PARTICLES = (3, 6)
EXPLOSIVE_ROUNDS_FLASH_SPEED = (80.0, 200.0)
# --- D.O.T. Rounds (on-hit DoT) ---
DOT_ROUNDS_TICK_INTERVAL = 0.5
DOT_ROUNDS_DAMAGE_PER_TICK = (0.10, 0.16, 0.22)
DOT_ROUNDS_DURATIONS = (2.5, 3.0, 3.5)
DOT_ROUNDS_MAX_STACKS = (1, 1, 2)
DOT_ROUNDS_BOSS_MULT = 0.70
DOT_ROUNDS_HIT_SPARK_CYAN = ((0, 208, 255), (0, 255, 255))
DOT_ROUNDS_HIT_SPARK_WHITE = (255, 255, 255)
DOT_ROUNDS_HIT_SPARK_PARTICLES = (6, 10)
DOT_ROUNDS_HIT_SPARK_SPEED = (60.0, 180.0)
DOT_ROUNDS_HIT_SPARK_LIFE = (0.20, 0.30)
DOT_ROUNDS_HIT_SPARK_SIZE = (2, 3)
DOT_ROUNDS_GLOW_COLOR = (0, 230, 255)
# --- Ground Spikes (trail hazard) ---
GROUND_SPIKES_SPAWN_INTERVAL = 0.35
GROUND_SPIKES_SPAWN_DIST = 0.75 * CELL_SIZE
GROUND_SPIKES_DAMAGE_MULTS = (0.30, 0.40, 0.50)
GROUND_SPIKES_LIFETIMES = (3.0, 4.0, 5.0)
GROUND_SPIKES_MAX_ACTIVE = (6, 10, 14)
GROUND_SPIKES_RADIUS = CELL_SIZE * 0.28
GROUND_SPIKES_SLOW_MULT = 0.95
GROUND_SPIKES_SLOW_DURATION = 1.0
GROUND_SPIKES_RISE_TIME = 0.15
GROUND_SPIKES_GLOW_TIME = 0.20
GROUND_SPIKES_VIS_SCALE = (1.0, 1.25, 1.50)
GROUND_SPIKES_COLOR = (120, 230, 255)
GROUND_SPIKES_RING = (220, 255, 255)
GROUND_SPIKES_BASE_DARK = (40, 70, 85)
GROUND_SPIKES_SIDE_DARK = (70, 120, 140)
GROUND_SPIKES_SIDE_LIGHT = (150, 230, 245)
GROUND_SPIKES_TOP_COLOR = (210, 250, 255)
GROUND_SPIKES_HIT_PARTICLES = (4, 7)
GROUND_SPIKES_HIT_SPEED = (60.0, 160.0)
GROUND_SPIKES_HIT_LIFE = (0.10, 0.20)
GROUND_SPIKES_HIT_SIZE = (2, 4)
# --- Curing Paint (ground ink DoT) ---
CURING_PAINT_SPAWN_INTERVAL = 0.25
CURING_PAINT_SPAWN_DIST = 0.50 * CELL_SIZE
CURING_PAINT_RADIUS = CELL_SIZE * 0.60
CURING_PAINT_RADIUS_MULTS = (1.15, 1.30, 1.50)
CURING_PAINT_LIFETIMES = (2.0, 3.0, 4.0)
CURING_PAINT_DAMAGE_PER_TICK = (0.04, 0.06, 0.08)
CURING_PAINT_TICK_INTERVAL = 0.5
CURING_PAINT_BOSS_MULT = 0.70
CURING_PAINT_SPLASH_TIME = 0.12
CURING_PAINT_SPLASH_SCALE_START = 0.70
CURING_PAINT_SPLASH_SCALE_PEAK = 1.05
CURING_PAINT_SPLASH_SETTLE = 0.10
CURING_PAINT_BRIGHTNESS_MIN = 0.35
CURING_PAINT_BLOB_POINTS = 14
CURING_PAINT_WIGGLE_STRENGTH = 0.08
CURING_PAINT_WIGGLE_SPEED = 5.0
CURING_PAINT_FILL_COLOR = (120, 12, 22)
CURING_PAINT_EDGE_COLOR = (230, 70, 60)
CURING_PAINT_EDGE_HIGHLIGHT = (255, 120, 110)
CURING_PAINT_SPARK_COLORS = ((80, 220, 255), (255, 255, 255))
CURING_PAINT_SPARK_RATE = 0.85  # sparks per second per footprint at full intensity
CURING_PAINT_SPARK_SPEED = (40.0, 90.0)
CURING_PAINT_SPARK_LIFE = (0.16, 0.28)
CURING_PAINT_SPARK_SIZE = (2, 3)
# --- Enemy Paint (Corrupt Trailrunner trail) ---
ENEMY_PAINT_SPAWN_INTERVAL = 0.30
ENEMY_PAINT_SPAWN_DIST = 0.60 * CELL_SIZE
ENEMY_PAINT_RADIUS = CELL_SIZE * 0.60
ENEMY_PAINT_LIFETIME = 3.0
ENEMY_PAINT_SPEED_BONUS = 0.20
ENEMY_PAINT_DAMAGE_BONUS = 0.15
ENEMY_PAINT_PLAYER_SLOW = 0.25
ENEMY_PAINT_DOT_INTERVAL = 0.5
ENEMY_PAINT_DOT_HP_FRAC = 0.01
ENEMY_PAINT_BLOB_POINTS = 12
ENEMY_PAINT_WIGGLE_STRENGTH = 0.10
ENEMY_PAINT_WIGGLE_SPEED = 4.5
ENEMY_PAINT_FILL_COLOR = (20, 50, 30)
ENEMY_PAINT_EDGE_COLOR = (80, 200, 130)
ENEMY_PAINT_EDGE_HIGHLIGHT = (130, 255, 190)
ENEMY_PAINT_GLOW_COLOR = (50, 140, 90)
ENEMY_PAINT_PARTICLE_COLOR = (8, 18, 10)
ENEMY_PAINT_BLEND_IN = 0.12
# --- Enemy paint size tiers ---
PAINT_SIZE_NORMAL = CELL_SIZE * 0.60  # baseline (previous default)
PAINT_SIZE_ELITE = CELL_SIZE * 0.80   # bulkier elites
PAINT_SIZE_BOSS = CELL_SIZE * 1.10    # large boss splats
ENEMY_SIZE_NORMAL = "NORMAL"
ENEMY_SIZE_ELITE = "ELITE"
ENEMY_SIZE_BOSS = "BOSS"
ENEMY_PAINT_ELITE_SIZE_THRESHOLD = CELL_SIZE * 0.95  # floor: must meet/exceed threshold to bump tier
ENEMY_PAINT_BOSS_SIZE_THRESHOLD = CELL_SIZE * 1.30   # floor: bosses/very large units
# --- Hell biome enemy paint (all enemies) ---
HELL_ENEMY_PAINT_SPAWN_INTERVAL = 0.45
HELL_ENEMY_PAINT_SPAWN_DIST = 0.70 * CELL_SIZE
HELL_ENEMY_PAINT_RADIUS = CELL_SIZE * 0.45
HELL_ENEMY_PAINT_STATIC = True
# === DEBUG: Ultimate test mode (easy to delete) ===
ULTIMATE_HP_VALUE = 10_000_000


def determine_enemy_size_category(z) -> str:
    """Classify an enemy into paint size tiers. Rounds down between thresholds."""
    if z is None:
        return ENEMY_SIZE_NORMAL
    if getattr(z, "is_boss", False):
        return ENEMY_SIZE_BOSS
    size_px = max(0, int(getattr(z, "size", CELL_SIZE)))
    # Boss-size override uses floor thresholds so in-between sizes stay smaller
    if size_px >= int(ENEMY_PAINT_BOSS_SIZE_THRESHOLD):
        return ENEMY_SIZE_BOSS
    if getattr(z, "type", "") == "ravager" or getattr(z, "is_elite", False):
        return ENEMY_SIZE_ELITE
    if size_px >= int(ENEMY_PAINT_ELITE_SIZE_THRESHOLD):
        return ENEMY_SIZE_ELITE
    return ENEMY_SIZE_NORMAL


def set_enemy_size_category(z) -> str:
    cat = determine_enemy_size_category(z)
    if z is not None:
        z.size_category = cat
    return cat


def enemy_paint_radius_for(z) -> float:
    cat = determine_enemy_size_category(z)
    if cat == ENEMY_SIZE_BOSS:
        return float(PAINT_SIZE_BOSS)
    if cat == ENEMY_SIZE_ELITE:
        return float(PAINT_SIZE_ELITE)
    return float(PAINT_SIZE_NORMAL)


def activate_ultimate_mode(player, game_state=None):
    """Grant the player effectively infinite HP for testing; keep together for easy removal."""
    if player is None:
        return
    player._ultimate_debug = True
    player.max_hp = max(int(getattr(player, "max_hp", PLAYER_MAX_HP)), ULTIMATE_HP_VALUE)
    player.hp = player.max_hp
    player.shield_hp = max(getattr(player, "shield_hp", 0), int(ULTIMATE_HP_VALUE * 0.1))
    if game_state and hasattr(game_state, "flash_banner"):
        game_state.flash_banner("ULTIMATE MODE (DEBUG)", sec=1.5)


def coin_absorb_scale(z) -> float:
    """Linear tiered scale based on coins absorbed; clamps to tier3 cap."""
    coins = int(getattr(z, "coins_absorbed", getattr(z, "spoils", 0)))
    c1 = int(COIN_ABSORB_TIER1_MAX_COINS)
    c2 = int(COIN_ABSORB_TIER2_MAX_COINS)
    s1 = float(COIN_ABSORB_SCALE_TIER1)
    s2 = float(COIN_ABSORB_SCALE_TIER2)
    s3 = float(COIN_ABSORB_SCALE_TIER3)
    if coins <= 0 or c1 <= 0:
        return 1.0
    if coins < c1:
        t = coins / float(c1)
        return 1.0 + (s1 - 1.0) * t
    if coins < c2:
        span = max(1, c2 - c1)
        t = (coins - c1) / float(span)
        return s1 + (s2 - s1) * t
    # Tier3: grow toward cap, but never exceed it
    over = coins - c2
    # Use a soft span of 10 coins to reach the cap; floor behavior by clamping
    t = min(1.0, over / 10.0)
    return min(s3, s2 + (s3 - s2) * t)


def apply_coin_absorb_scale(z) -> None:
    """Apply coin-based scale to enemy size/rect/radius."""
    if z is None:
        return
    if not getattr(z, "_base_size", None):
        z._base_size = int(getattr(z, "size", CELL_SIZE * 0.6))
    scale = coin_absorb_scale(z)
    new_size = max(2, int(z._base_size * scale))
    if new_size == getattr(z, "size", new_size):
        return
    cx, cy = z.rect.center
    z.size = new_size
    z.rect = pygame.Rect(0, 0, z.size, z.size)
    z.rect.center = (cx, cy)
    z.x = float(z.rect.x)
    z.y = float(z.rect.y - INFO_BAR_HEIGHT)
    z.radius = int(z.size * 0.5)
    # reset foot points to avoid afterimage drift
    z._foot_prev = (z.rect.centerx, z.rect.bottom)
    z._foot_curr = (z.rect.centerx, z.rect.bottom)
# --- Mark of Vulnerability (offensive mark) ---
VULN_MARK_INTERVALS = (5.0, 4.0, 3.0)  # seconds between new marks (lv1→lv3)
VULN_MARK_BONUS = (0.15, 0.22, 0.30)  # damage taken multiplier bonus per level
VULN_MARK_DURATIONS = (5.0, 6.0, 7.0)  # mark lifetime per level
MARK_PULSE_PERIOD = 1.0  # seconds per beat
MARK_PULSE_MIN_SCALE = 0.85
MARK_PULSE_MAX_SCALE = 1.15
MARK_PULSE_MIN_ALPHA = 160
MARK_PULSE_MAX_ALPHA = 255
MARK_PULSE_DARK = (60, 0, 0)
MARK_PULSE_BRIGHT = (255, 40, 40)
mark_pulse_time = 0.0  # global pulse accumulator
HURRICANE_START_RADIUS = CELL_SIZE * 1.2
HURRICANE_MAX_RADIUS = CELL_SIZE * 6.0
HURRICANE_GROWTH_RATE = 8.0  # px/s (slower buildup)
HURRICANE_RANGE_MULT = 2.6
HURRICANE_PULL_STRENGTH = 180.0  # px/s pull toward center (reduced suction)
HURRICANE_PULL_GROWTH_MULT = 2.0  # extra pull scaling as the vortex grows
HURRICANE_BULLET_PULL = 140.0
HURRICANE_SPIN_BASE = 2.4  # rad/s target angular speed for swirling bullets
HURRICANE_SPIN_VARIANCE = 0.35  # ±35% variance when spawning a vortex
HURRICANE_BULLET_SPIN_STEER = 4.0  # how quickly bullet velocity is steered toward the spin
HURRICANE_ESCAPE_SPEED = 3.8  # speed to shrug most pull
HURRICANE_ESCAPE_SIZE = CELL_SIZE * 1.0  # entities larger than this resist more
HURRICANE_COLOR = (120, 200, 255)
SHOP_CATALOG_VERSION = 6  # bump to invalidate cached offers when catalog changes
# persistent (per run) upgrades bought in shop
META = {
    # —— 本轮累积资源 ——
    "spoils": 0,
    # —— 初始（基准）数值 ——（来自常量）
    "base_dmg": BULLET_DAMAGE_ENEMY,
    "base_fire_cd": MIN_FIRE_COOLDOWN,  # 以冷却秒数作为基准
    "base_range": float(PLAYER_RANGE_DEFAULT),
    "base_speed": float(PLAYER_SPEED),
    "base_maxhp": int(PLAYER_MAX_HP),
    "base_crit": float(CRIT_CHANCE_BASE),
    # —— 附加/加成 ——（购买/掉落/升级得到）
    "dmg": 0,  # 伤害 +X
    "firerate_mult": 1.0,  # 攻速 ×mult
    "range_mult": 1.0,  # 射程 ×mult
    "speed_mult": 1.0,  # 速度 ×mult
    "speed": 0,  # 速度 +X
    "maxhp": 0,  # 最大生命 +X
    "crit": 0.0,  # 暴击率 +X（0~1）
    "coin_magnet_radius": 0,  # 磁吸金币的额外拾取半径（像素）
    "auto_turret_level": 0,  # 自动炮台等级（每级多一个炮台）
    "stationary_turret_count": 0,
    "pierce_level": 0,  # 每发子弹可额外穿透的“击杀次数”
    "ricochet_level": 0,  # 每发子弹可弹射的次数
    "vuln_mark_level": 0,  # Mark of Vulnerability level
    "carapace_level": 0,
    "bone_plating_level": 0,
    "shrapnel_level": 0,
    "explosive_rounds_level": 0,
    "dot_rounds_level": 0,
    "ground_spikes_level": 0,
    "curing_paint_level": 0,
    "carapace_shield_hp": 0,
    "golden_interest_level": 0,
    "shady_loan_level": 0,
    "shady_loan_waves_remaining": 0,
    "shady_loan_remaining_debt": 0,
    "shady_loan_defaulted": False,
    "shady_loan_status": None,  # None/active/repaid/defaulted
    "shady_loan_last_level": 0,
    "shady_loan_grace_level": -1,
    "wanted_poster_waves": 0,
    "wanted_active": False,
    "lockbox_level": 0,
    "bandit_radar_level": 0,
    "coupon_level": 0,
    "aegis_pulse_level": 0,
    "run_items_spawned": 0,
    "run_items_collected": 0,
    "kill_count": 0,
}


def reset_run_state():
    runtime = _runtime_state()
    meta = _meta_state()
    meta.update({
        "spoils": 0,
        "base_dmg": BULLET_DAMAGE_ENEMY,
        "base_fire_cd": FIRE_COOLDOWN,
        "base_range": float(PLAYER_RANGE_DEFAULT),
        "base_speed": float(PLAYER_SPEED),
        "base_maxhp": int(PLAYER_MAX_HP),
        "base_crit": float(CRIT_CHANCE_BASE),
        "dmg": 0,
        "firerate_mult": 1.0,
        "range_mult": 1.0,
        "speed_mult": 1.0,
        "speed": 0,
        "maxhp": 0,
        "crit": 0.0,
        "coin_magnet_radius": 0,
        "auto_turret_level": 0,
        "stationary_turret_count": 0,
        "pierce_level": 0,
        "ricochet_level": 0,
        "vuln_mark_level": 0,
        "carapace_level": 0,
        "bone_plating_level": 0,
        "shrapnel_level": 0,
        "explosive_rounds_level": 0,
        "dot_rounds_level": 0,
        "ground_spikes_level": 0,
        "curing_paint_level": 0,
        "carapace_shield_hp": 0,
        "golden_interest_level": 0,
        "shady_loan_level": 0,
        "shady_loan_waves_remaining": 0,
        "shady_loan_remaining_debt": 0,
        "shady_loan_defaulted": False,
        "shady_loan_status": None,
        "shady_loan_last_level": 0,
        "shady_loan_grace_level": -1,
        "wanted_poster_waves": 0,
        "wanted_active": False,
        "lockbox_level": 0,
        "bandit_radar_level": 0,
        "coupon_level": 0,
        "aegis_pulse_level": 0,
        "run_items_spawned": 0,
        "run_items_collected": 0,
        "kill_count": 0,
        "bindings": dict(meta.get("bindings", DEFAULT_BINDINGS)),
    })
    runtime["_carry_player_state"] = None
    runtime["_pending_shop"] = False
    runtime.clear(
        "_last_spoils",
        "_coins_at_level_start",
        "_coins_at_shop_entry",
        "_shop_slot_ids_cache",
        "_shop_slots_cache",
        "_shop_reroll_id_cache",
        "_shop_reroll_cache",
        "_resume_shop_cache",
        "_intro_envelope",
    )
    _clear_level_start_baseline()


def _ensure_meta_defaults(meta=None):
    """Fill in newly added META keys when loading older saves."""
    m = _meta_state() if meta is None else meta
    if m is None or not hasattr(m, "get"):
        return
    defaults = {
        "vuln_mark_level": 0,
        "explosive_rounds_level": 0,
        "dot_rounds_level": 0,
        "ground_spikes_level": 0,
        "curing_paint_level": 0,
        "kill_count": 0,
        "bindings": {},
    }
    for k, v in defaults.items():
        if k not in m:
            m[k] = dict(v) if isinstance(v, dict) else v


def _load_meta_from_save(save_data: dict | None) -> None:
    """Apply saved META with range sanitization and fill missing defaults."""
    if not save_data:
        return
    meta_in = dict(save_data.get("meta", {}))
    sanitize_meta_range(meta_in)
    _ensure_meta_defaults(meta_in)
    save_data["meta"] = meta_in
    _meta_state().update(meta_in)
    _ensure_meta_defaults()
    _apply_meta_bindings(meta_in)


def _finite_float(value, default: float = 0.0, *, min_value: float | None = None,
                  max_value: float | None = None) -> float:
    try:
        out = float(value)
    except Exception:
        out = float(default)
    if not math.isfinite(out):
        out = float(default)
    if min_value is not None:
        out = max(float(min_value), out)
    if max_value is not None:
        out = min(float(max_value), out)
    return float(out)


def _finite_int(value, default: int = 0, *, min_value: int | None = None,
                max_value: int | None = None) -> int:
    out = _finite_float(
        value,
        float(default),
        min_value=None if min_value is None else float(min_value),
        max_value=None if max_value is None else float(max_value),
    )
    try:
        out_i = int(round(out))
    except Exception:
        out_i = int(default)
    if min_value is not None:
        out_i = max(int(min_value), out_i)
    if max_value is not None:
        out_i = min(int(max_value), out_i)
    return int(out_i)


def _clean_string(value, default: str | None = None) -> str | None:
    if value is None:
        return default
    try:
        text = str(value).strip()
    except Exception:
        return default
    return text or default


def _clean_rgb(value, default: tuple[int, int, int]) -> tuple[int, int, int]:
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        try:
            return (
                max(0, min(255, int(value[0]))),
                max(0, min(255, int(value[1]))),
                max(0, min(255, int(value[2]))),
            )
        except Exception:
            pass
    return default


def _world_bounds_with_pad(pad: float = 0.0) -> tuple[float, float, float, float]:
    world_w = float(max(WINDOW_SIZE, GRID_SIZE * CELL_SIZE))
    world_h = float(INFO_BAR_HEIGHT + max(WINDOW_SIZE, GRID_SIZE * CELL_SIZE))
    return (-pad, world_w + pad, INFO_BAR_HEIGHT - pad, world_h + pad)


def _sanitize_carry_player_state(carry: dict | None) -> dict | None:
    if not isinstance(carry, dict):
        return None
    return {
        "level": _finite_int(carry.get("level", 1), 1, min_value=1, max_value=250),
        "xp": _finite_int(carry.get("xp", 0), 0, min_value=0, max_value=50_000_000),
        "hp": _finite_int(carry.get("hp", PLAYER_MAX_HP), PLAYER_MAX_HP, min_value=0, max_value=50_000),
    }


def _sanitize_snapshot_payload(snapshot: dict | None) -> dict:
    snap = dict(snapshot) if isinstance(snapshot, dict) else {}
    min_x, max_x, min_y, max_y = _world_bounds_with_pad(float(CELL_SIZE) * 2.0)
    max_cells = max(1, int(GRID_SIZE) * int(GRID_SIZE))
    max_enemies = max(8, int(ENEMY_CAP) * 3)
    max_bullets = 512
    player_in = snap.get("player", {})
    player_in = dict(player_in) if isinstance(player_in, dict) else {}
    snap["player"] = {
        "x": _finite_float(player_in.get("x", 0.0), 0.0, min_value=min_x, max_value=max_x),
        "y": _finite_float(player_in.get("y", 0.0), 0.0, min_value=min_y - INFO_BAR_HEIGHT, max_value=max_y),
        "speed": _finite_int(player_in.get("speed", PLAYER_SPEED), PLAYER_SPEED, min_value=1, max_value=int(PLAYER_SPEED_CAP)),
        "size": _finite_int(player_in.get("size", int(CELL_SIZE * 0.6)), int(CELL_SIZE * 0.6), min_value=8, max_value=int(CELL_SIZE * 2.5)),
        "fire_cd": _finite_float(player_in.get("fire_cd", 0.0), 0.0, min_value=0.0, max_value=30.0),
        "hp": _finite_int(player_in.get("hp", PLAYER_MAX_HP), PLAYER_MAX_HP, min_value=0, max_value=50_000),
        "max_hp": _finite_int(player_in.get("max_hp", PLAYER_MAX_HP), PLAYER_MAX_HP, min_value=1, max_value=50_000),
        "hit_cd": _finite_float(player_in.get("hit_cd", 0.0), 0.0, min_value=0.0, max_value=10.0),
        "level": _finite_int(player_in.get("level", 1), 1, min_value=1, max_value=250),
        "xp": _finite_int(player_in.get("xp", 0), 0, min_value=0, max_value=50_000_000),
        "bone_plating_hp": _finite_int(player_in.get("bone_plating_hp", 0), 0, min_value=0, max_value=500),
        "bone_plating_cd": _finite_float(player_in.get("bone_plating_cd", BONE_PLATING_GAIN_INTERVAL), BONE_PLATING_GAIN_INTERVAL, min_value=0.0, max_value=60.0),
        "aegis_pulse_cd": _finite_float(player_in.get("aegis_pulse_cd", 0.0), 0.0, min_value=0.0, max_value=60.0),
    }
    clean_enemies = []
    for enemy in list(snap.get("enemies", []))[:max_enemies]:
        if not isinstance(enemy, dict):
            continue
        clean_enemies.append({
            "x": _finite_float(enemy.get("x", 0.0), 0.0, min_value=min_x, max_value=max_x),
            "y": _finite_float(enemy.get("y", 0.0), 0.0, min_value=min_y - INFO_BAR_HEIGHT, max_value=max_y),
            "attack": _finite_int(enemy.get("attack", ENEMY_ATTACK), ENEMY_ATTACK, min_value=1, max_value=50_000),
            "speed": _finite_int(enemy.get("speed", ENEMY_SPEED), ENEMY_SPEED, min_value=1, max_value=int(ENEMY_SPEED_MAX)),
            "type": _clean_string(enemy.get("type"), "basic") or "basic",
            "hp": _finite_int(enemy.get("hp", 30), 30, min_value=0, max_value=500_000),
            "max_hp": _finite_int(enemy.get("max_hp", enemy.get("hp", 30)), int(enemy.get("hp", 30) if isinstance(enemy.get("hp", 30), (int, float)) else 30), min_value=1, max_value=500_000),
            "spawn_elapsed": _finite_float(enemy.get("spawn_elapsed", 0.0), 0.0, min_value=0.0, max_value=60.0),
            "attack_timer": _finite_float(enemy.get("attack_timer", 0.0), 0.0, min_value=0.0, max_value=60.0),
        })
    snap["enemies"] = clean_enemies
    clean_obstacles = []
    for obstacle in list(snap.get("obstacles", []))[:max_cells]:
        if not isinstance(obstacle, dict):
            continue
        health_value = obstacle.get("health", None)
        clean_obstacles.append({
            "x": _finite_int(obstacle.get("x", 0), 0, min_value=0, max_value=max(0, GRID_SIZE - 1)),
            "y": _finite_int(obstacle.get("y", 0), 0, min_value=0, max_value=max(0, GRID_SIZE - 1)),
            "type": _clean_string(obstacle.get("type"), "Indestructible") or "Indestructible",
            "health": None if health_value is None else _finite_int(health_value, MAIN_BLOCK_HEALTH, min_value=-500_000, max_value=500_000),
            "main": bool(obstacle.get("main", False)),
        })
    snap["obstacles"] = clean_obstacles
    clean_items = []
    for item in list(snap.get("items", []))[:max_cells]:
        if not isinstance(item, dict):
            continue
        clean_items.append({
            "x": _finite_int(item.get("x", 0), 0, min_value=0, max_value=max(0, GRID_SIZE - 1)),
            "y": _finite_int(item.get("y", 0), 0, min_value=0, max_value=max(0, GRID_SIZE - 1)),
            "is_main": bool(item.get("is_main", False)),
        })
    snap["items"] = clean_items
    clean_decorations = []
    for deco in list(snap.get("decorations", []))[:max_cells]:
        if not isinstance(deco, (tuple, list)) or len(deco) < 2:
            continue
        clean_decorations.append([
            _finite_int(deco[0], 0, min_value=0, max_value=max(0, GRID_SIZE - 1)),
            _finite_int(deco[1], 0, min_value=0, max_value=max(0, GRID_SIZE - 1)),
        ])
    snap["decorations"] = clean_decorations
    clean_bullets = []
    for bullet in list(snap.get("bullets", []))[:max_bullets]:
        if not isinstance(bullet, dict):
            continue
        clean_bullets.append({
            "x": _finite_float(bullet.get("x", 0.0), 0.0, min_value=min_x, max_value=max_x),
            "y": _finite_float(bullet.get("y", 0.0), 0.0, min_value=min_y, max_value=max_y),
            "vx": _finite_float(bullet.get("vx", 0.0), 0.0, min_value=-BULLET_SPEED * 4.0, max_value=BULLET_SPEED * 4.0),
            "vy": _finite_float(bullet.get("vy", 0.0), 0.0, min_value=-BULLET_SPEED * 4.0, max_value=BULLET_SPEED * 4.0),
            "traveled": _finite_float(bullet.get("traveled", 0.0), 0.0, min_value=0.0, max_value=PLAYER_RANGE_MAX * 2.0),
        })
    snap["bullets"] = clean_bullets
    snap["time_left"] = _finite_float(
        snap.get("time_left", LEVEL_TIME_LIMIT),
        LEVEL_TIME_LIMIT,
        min_value=0.0,
        max_value=max(float(LEVEL_TIME_LIMIT), float(BOSS_TIME_LIMIT)) * 2.0,
    )
    return snap


def _sanitize_resume_save_data(save_data: dict | None) -> dict | None:
    if not isinstance(save_data, dict):
        return None
    data = copy.deepcopy(save_data)
    mode = _clean_string(data.get("mode"), "meta") or "meta"
    if mode not in ("meta", "snapshot"):
        mode = "meta"
    data["mode"] = mode
    meta_in = data.get("meta", {})
    meta_in = dict(meta_in) if isinstance(meta_in, dict) else {}
    if mode == "snapshot":
        meta_in["current_level"] = _finite_int(meta_in.get("current_level", 0), 0, min_value=0, max_value=9999)
        meta_in["chosen_enemy_type"] = _clean_string(meta_in.get("chosen_enemy_type"), "basic") or "basic"
    sanitize_meta_range(meta_in)
    _ensure_meta_defaults(meta_in)
    data["meta"] = meta_in
    if mode == "meta":
        data["current_level"] = _finite_int(data.get("current_level", 0), 0, min_value=0, max_value=9999)
    data["pending_shop"] = bool(data.get("pending_shop", False))
    data["carry_player"] = _sanitize_carry_player_state(data.get("carry_player"))
    biome = _clean_string(data.get("biome"), None)
    if biome is None and mode == "snapshot":
        biome = _clean_string(meta_in.get("biome"), None)
    if biome is None:
        data.pop("biome", None)
    else:
        data["biome"] = biome
        if mode == "snapshot":
            meta_in["biome"] = biome
    if mode == "snapshot":
        data["snapshot"] = _sanitize_snapshot_payload(data.get("snapshot", {}))
    else:
        data.pop("snapshot", None)
    shop_cache = data.get("shop_cache")
    if isinstance(shop_cache, dict):
        clean_cache = {}
        slots = shop_cache.get("slots")
        if isinstance(slots, list):
            clean_cache["slots"] = [_clean_string(slot, None) for slot in slots[:8]]
        reroll = _clean_string(shop_cache.get("reroll"), None)
        if reroll is not None:
            clean_cache["reroll"] = reroll
        if clean_cache:
            data["shop_cache"] = clean_cache
        else:
            data.pop("shop_cache", None)
    else:
        data.pop("shop_cache", None)
    if not isinstance(data.get("baseline"), dict):
        data.pop("baseline", None)
    return data


def _resume_level_from_save(save_data: dict | None) -> int:
    data = _sanitize_resume_save_data(save_data)
    if not data:
        return 0
    if data.get("mode") == "snapshot":
        meta_in = data.get("meta", {})
        return _finite_int(meta_in.get("current_level", 0), 0, min_value=0, max_value=9999)
    return _finite_int(data.get("current_level", 0), 0, min_value=0, max_value=9999)


def _apply_resume_save_data(save_data: dict | None) -> dict | None:
    runtime = _runtime_state()
    clean = _sanitize_resume_save_data(save_data)
    if not clean:
        runtime["_carry_player_state"] = None
        runtime["_pending_shop"] = False
        runtime.clear("_next_biome", "_resume_snapshot_data")
        _THIS_MODULE.current_level = 0
        return None
    _load_meta_from_save(clean)
    runtime["_carry_player_state"] = clean.get("carry_player", None)
    runtime["_pending_shop"] = bool(clean.get("pending_shop", False))
    runtime["_next_biome"] = clean.get("biome", None)
    if clean.get("mode") == "snapshot":
        runtime["_resume_snapshot_data"] = copy.deepcopy(clean)
    else:
        runtime.clear("_resume_snapshot_data")
    _THIS_MODULE.current_level = _resume_level_from_save(clean)
    return clean


def _reset_active_run_state(*, clear_save_file: bool = False) -> None:
    runtime = _runtime_state()
    if clear_save_file:
        clear_save()
    reset_run_state()
    _THIS_MODULE.current_level = 0
    runtime["_carry_player_state"] = None
    runtime["_pending_shop"] = False
    runtime.clear("_last_spoils", "_next_biome", "_last_biome", "_resume_snapshot_data")


def _verify_projectile_runtime_common(projectile, *, default_damage: int, default_range: float,
                                      max_speed: float, radius_default: int,
                                      radius_cap: int, color_default: tuple[int, int, int] | None = None,
                                      radius_fn=None) -> bool:
    if projectile is None:
        return False
    projectile.alive = bool(getattr(projectile, "alive", True))
    if not projectile.alive:
        return False
    pad = float(max(CELL_SIZE * 4, 256))
    min_x, max_x, min_y, max_y = _world_bounds_with_pad(pad)
    x = _finite_float(getattr(projectile, "x", 0.0), 0.0)
    y = _finite_float(getattr(projectile, "y", INFO_BAR_HEIGHT), INFO_BAR_HEIGHT)
    if x < min_x or x > max_x or y < min_y or y > max_y:
        projectile.alive = False
        return False
    vx = _finite_float(getattr(projectile, "vx", 0.0), 0.0)
    vy = _finite_float(getattr(projectile, "vy", 0.0), 0.0)
    if abs(vx) > max_speed or abs(vy) > max_speed:
        projectile.alive = False
        return False
    if (vx * vx + vy * vy) <= 1e-6:
        projectile.alive = False
        return False
    projectile.x = x
    projectile.y = y
    projectile.vx = vx
    projectile.vy = vy
    projectile.max_dist = _finite_float(getattr(projectile, "max_dist", default_range), default_range, min_value=1.0, max_value=max(default_range * 4.0, 1.0))
    projectile.traveled = _finite_float(getattr(projectile, "traveled", 0.0), 0.0, min_value=0.0, max_value=projectile.max_dist * 2.0)
    projectile.damage = _finite_int(
        getattr(projectile, "damage", getattr(projectile, "dmg", default_damage)),
        default_damage,
        min_value=1,
        max_value=500_000,
    )
    if hasattr(projectile, "dmg"):
        projectile.dmg = int(projectile.damage)
    if radius_fn is not None:
        projectile.r = int(radius_fn(projectile.damage))
    else:
        projectile.r = _finite_int(getattr(projectile, "r", radius_default), radius_default, min_value=2, max_value=radius_cap)
    if color_default is not None:
        projectile.color = _clean_rgb(getattr(projectile, "color", color_default), color_default)
    if projectile.traveled >= projectile.max_dist:
        projectile.alive = False
        return False
    return True


def verify_bullet_runtime(bullet, player=None) -> bool:
    default_range = clamp_player_range(getattr(player, "range", getattr(bullet, "max_dist", PLAYER_RANGE_DEFAULT)))
    ok = _verify_projectile_runtime_common(
        bullet,
        default_damage=BULLET_DAMAGE_ENEMY,
        default_range=default_range,
        max_speed=max(float(BULLET_SPEED) * 4.0, 1.0),
        radius_default=BULLET_RADIUS,
        radius_cap=BULLET_RADIUS_MAX,
        radius_fn=bullet_radius_for_damage,
    )
    if not ok:
        return False
    bullet.source = _clean_string(getattr(bullet, "source", "player"), "player") or "player"
    if hasattr(bullet, "pierce_left"):
        bullet.pierce_left = _finite_int(getattr(bullet, "pierce_left", 0), 0, min_value=0, max_value=32)
    if hasattr(bullet, "ricochet_left"):
        bullet.ricochet_left = _finite_int(getattr(bullet, "ricochet_left", 0), 0, min_value=0, max_value=32)
    return True


def verify_enemy_shot_runtime(enemy_shot) -> bool:
    base_speed = max(float(RANGED_PROJ_SPEED), float(MIST_RING_SPEED), 1.0)
    return _verify_projectile_runtime_common(
        enemy_shot,
        default_damage=RANGED_PROJ_DAMAGE,
        default_range=MAX_FIRE_RANGE,
        max_speed=base_speed * 4.0,
        radius_default=4,
        radius_cap=max(8, int(CELL_SIZE * 0.4)),
        color_default=(255, 120, 50),
        radius_fn=None,
    )


def _sanitize_dash_runtime(enemy, *, dash_cd_default: float, dash_time_cap: float) -> None:
    dash_state = _clean_string(getattr(enemy, "_dash_state", "idle"), "idle") or "idle"
    if dash_state not in ("idle", "wind", "go"):
        dash_state = "idle"
    enemy._dash_state = dash_state
    enemy._dash_cd = _finite_float(getattr(enemy, "_dash_cd", dash_cd_default), dash_cd_default, min_value=0.0, max_value=max(5.0, dash_cd_default * 6.0))
    enemy._dash_t = _finite_float(getattr(enemy, "_dash_t", 0.0), 0.0, min_value=0.0, max_value=max(1.0, dash_time_cap))
    enemy._dash_speed_hold = _finite_float(getattr(enemy, "_dash_speed_hold", getattr(enemy, "speed", ENEMY_SPEED)), getattr(enemy, "speed", ENEMY_SPEED), min_value=0.2, max_value=float(ENEMY_SPEED_MAX) * 4.0)
    enemy._ghost_accum = _finite_float(getattr(enemy, "_ghost_accum", 0.0), 0.0, min_value=0.0, max_value=max(float(AFTERIMAGE_INTERVAL) * 4.0, 1.0))


def verify_enemy_special_runtime(enemy) -> bool:
    if enemy is None:
        return False
    enemy.no_clip_t = _finite_float(getattr(enemy, "no_clip_t", 0.0), 0.0, min_value=0.0, max_value=20.0)
    ztype = _clean_string(getattr(enemy, "type", ""), "") or ""
    if ztype in ("ranged", "spitter"):
        enemy.ranged_cd = _finite_float(getattr(enemy, "ranged_cd", 0.0), 0.0, min_value=0.0, max_value=max(1.0, float(RANGED_COOLDOWN) * 4.0))
    if ztype in ("suicide", "bomber"):
        enemy.suicide_armed = bool(getattr(enemy, "suicide_armed", False))
        fuse_value = getattr(enemy, "fuse", None)
        if fuse_value is None and enemy.suicide_armed:
            enemy.fuse = float(SUICIDE_FUSE)
        elif fuse_value is None:
            enemy.fuse = None
        else:
            enemy.fuse = _finite_float(fuse_value, float(SUICIDE_FUSE), min_value=0.0, max_value=max(2.0, float(SUICIDE_FUSE) * 4.0))
    if ztype == "ravager":
        _sanitize_dash_runtime(
            enemy,
            dash_cd_default=sum(RAVAGER_DASH_CD_RANGE) / 2.0,
            dash_time_cap=max(float(RAVAGER_DASH_TIME), float(RAVAGER_DASH_WINDUP)) * 4.0,
        )
    if ztype == "boss_mem":
        skill_last = getattr(enemy, "skill_last", {})
        skill_last = dict(skill_last) if isinstance(skill_last, dict) else {}
        enemy.skill_last = {
            "dash": _finite_float(skill_last.get("dash", -99.0), -99.0, min_value=-999.0, max_value=999.0),
            "vomit": _finite_float(skill_last.get("vomit", -99.0), -99.0, min_value=-999.0, max_value=999.0),
            "summon": _finite_float(skill_last.get("summon", -99.0), -99.0, min_value=-999.0, max_value=999.0),
            "ring": _finite_float(skill_last.get("ring", -99.0), -99.0, min_value=-999.0, max_value=999.0),
        }
        skill_phase = getattr(enemy, "skill_phase", None)
        enemy.skill_phase = None if skill_phase is None else _clean_string(skill_phase, None)
        enemy.skill_t = _finite_float(getattr(enemy, "skill_t", 0.0), 0.0, min_value=0.0, max_value=20.0)
        enemy.spawn_delay = _finite_float(getattr(enemy, "spawn_delay", 0.6), 0.6, min_value=0.0, max_value=10.0)
        enemy._enrage_cd_mult = _finite_float(getattr(enemy, "_enrage_cd_mult", 1.0), 1.0, min_value=0.2, max_value=2.0)
        enemy.phase = _finite_int(getattr(enemy, "phase", 1), 1, min_value=1, max_value=3)
        enemy._spit_cd = _finite_float(getattr(enemy, "_spit_cd", 0.0), 0.0, min_value=0.0, max_value=30.0)
        enemy._split_cd = _finite_float(getattr(enemy, "_split_cd", 0.0), 0.0, min_value=0.0, max_value=30.0)
        enemy._rain_next_pct = _finite_float(getattr(enemy, "_rain_next_pct", 0.4), 0.4, min_value=0.0, max_value=1.0)
        enemy._charging = bool(getattr(enemy, "_charging", False))
        _sanitize_dash_runtime(
            enemy,
            dash_cd_default=5.25,
            dash_time_cap=max(float(BOSS_DASH_GO_TIME), float(BOSS_DASH_WINDUP)) * 4.0,
        )
    elif ztype == "boss_mist":
        enemy.phase = _finite_int(getattr(enemy, "phase", 1), 1, min_value=1, max_value=3)
        enemy.spawn_delay = _finite_float(getattr(enemy, "spawn_delay", 0.6), 0.6, min_value=0.0, max_value=10.0)
        enemy._storm_cd = _finite_float(getattr(enemy, "_storm_cd", 2.0), 2.0, min_value=0.0, max_value=max(12.0, float(MIST_P2_STORM_CD) * 3.0))
        enemy._blade_cd = _finite_float(getattr(enemy, "_blade_cd", 1.5), 1.5, min_value=0.0, max_value=max(8.0, float(MIST_P1_BLADE_CD) * 3.0))
        enemy._blink_cd = _finite_float(getattr(enemy, "_blink_cd", float(MIST_BLINK_CD)), float(MIST_BLINK_CD), min_value=0.0, max_value=max(8.0, float(MIST_BLINK_CD) * 3.0))
        enemy._sonar_next = _finite_float(getattr(enemy, "_sonar_next", 1.0), 1.0, min_value=-1.0, max_value=1.0)
        clone_ids = getattr(enemy, "_clone_ids", set())
        if isinstance(clone_ids, (set, list, tuple)):
            clean_ids = set()
            for clone_id in list(clone_ids)[:16]:
                try:
                    clean_ids.add(int(clone_id))
                except Exception:
                    continue
            enemy._clone_ids = clean_ids
        else:
            enemy._clone_ids = set()
        enemy._ring_cd = _finite_float(getattr(enemy, "_ring_cd", float(MIST_RING_CD)), float(MIST_RING_CD), min_value=0.0, max_value=max(8.0, float(MIST_RING_CD) * 3.0))
        enemy._ring_bursts_left = _finite_int(getattr(enemy, "_ring_bursts_left", 0), 0, min_value=0, max_value=max(1, int(MIST_RING_BURSTS)))
        enemy._ring_burst_t = _finite_float(getattr(enemy, "_ring_burst_t", 0.0), 0.0, min_value=0.0, max_value=4.0)
    return True


def mark_of_vulnerability_stats(level: int) -> tuple[float, float, float]:
    """Return (interval_s, bonus_mult, duration_s) for Mark of Vulnerability."""
    lvl = max(1, min(int(level), len(VULN_MARK_INTERVALS)))
    return (
        VULN_MARK_INTERVALS[lvl - 1],
        VULN_MARK_BONUS[lvl - 1],
        VULN_MARK_DURATIONS[lvl - 1],
    )


def mark_bonus_for(z: "Enemy") -> float:
    if getattr(z, "hp", 0) <= 0:
        return 0.0
    if float(getattr(z, "_vuln_mark_t", 0.0)) <= 0.0:
        return 0.0
    return max(0.0, float(getattr(z, "_vuln_mark_bonus", 0.0)))


def apply_vuln_bonus(z: "Enemy", dmg: int) -> int:
    """Scale incoming damage if the target is marked."""
    base = int(max(0, dmg))
    bonus = mark_bonus_for(z)
    if base <= 0 or bonus <= 0.0:
        return base
    scaled = int(round(base * (1.0 + bonus)))
    if scaled == base:
        scaled = base + 1
    try:
        z._vuln_hit_flash = max(0.0, float(getattr(z, "_vuln_hit_flash", 0.0)) + 0.12)
    except Exception:
        pass
    return max(0, scaled)


def explosive_rounds_stats(level: int, bullet_base: int | float) -> tuple[float, int, int]:
    """Return (radius_px, damage, boss_damage) for Explosive Rounds."""
    lvl = max(1, min(int(level), len(EXPLOSIVE_ROUNDS_DAMAGE_MULTS)))
    radius = float(CELL_SIZE) * float(EXPLOSIVE_ROUNDS_RADIUS_MULTS[lvl - 1])
    base = max(1, int(round(float(bullet_base) * EXPLOSIVE_ROUNDS_DAMAGE_MULTS[lvl - 1])))
    boss = max(
        1,
        int(round(float(bullet_base) * EXPLOSIVE_ROUNDS_DAMAGE_MULTS[lvl - 1] * EXPLOSIVE_ROUNDS_BOSS_MULT)),
    )
    return radius, base, boss


def dot_rounds_stats(level: int, bullet_base: int | float) -> tuple[float, float, int]:
    """Return (damage_per_tick, duration_s, max_stacks) for D.O.T. Rounds."""
    lvl = max(1, min(int(level), len(DOT_ROUNDS_DAMAGE_PER_TICK)))
    dmg_per_tick = float(bullet_base) * float(DOT_ROUNDS_DAMAGE_PER_TICK[lvl - 1])
    duration = float(DOT_ROUNDS_DURATIONS[lvl - 1])
    max_stacks = int(DOT_ROUNDS_MAX_STACKS[lvl - 1])
    return dmg_per_tick, duration, max_stacks


def ground_spikes_stats(level: int, bullet_base: int | float) -> tuple[float, float, int]:
    """Return (spike_damage, lifetime_s, max_active) for Ground Spikes."""
    lvl = max(1, min(int(level), len(GROUND_SPIKES_DAMAGE_MULTS)))
    damage = float(bullet_base) * float(GROUND_SPIKES_DAMAGE_MULTS[lvl - 1])
    lifetime = float(GROUND_SPIKES_LIFETIMES[lvl - 1])
    max_active = int(GROUND_SPIKES_MAX_ACTIVE[lvl - 1])
    return damage, lifetime, max_active


def curing_paint_radius(level: int) -> float:
    """Return radius_px for Curing Paint based on upgrade level."""
    lvl = max(1, min(int(level), len(CURING_PAINT_RADIUS_MULTS)))
    mult = float(CURING_PAINT_RADIUS_MULTS[lvl - 1]) if CURING_PAINT_RADIUS_MULTS else 1.0
    return float(CURING_PAINT_RADIUS) * mult


def curing_paint_stats(level: int, bullet_base: int | float) -> tuple[float, float, float]:
    """Return (damage_per_tick, lifetime_s, radius_px) for Curing Paint."""
    lvl = max(1, min(int(level), len(CURING_PAINT_DAMAGE_PER_TICK)))
    dmg_per_tick = float(bullet_base) * float(CURING_PAINT_DAMAGE_PER_TICK[lvl - 1])
    lifetime = float(CURING_PAINT_LIFETIMES[lvl - 1])
    radius = curing_paint_radius(lvl)
    return dmg_per_tick, lifetime, radius


def curing_paint_kill_bonus(kill_count: int) -> float:
    """Scale curing paint DoT by a small bonus per 10 kills."""
    return 1.0 + 0.002 * max(0, int(kill_count) // 10)


def curing_paint_base_color(player) -> tuple[int, int, int]:
    col = getattr(player, "paint_color", None) or getattr(player, "color", None)
    if isinstance(col, (tuple, list)) and len(col) >= 3:
        return (int(col[0]), int(col[1]), int(col[2]))
    return (0, 255, 0)


PATH_DISPLAY_ORDER = ("ballistic", "turret", "shield", "status", "economy", "summoner", "lucky")
PATH_DISPLAY_NAME = {
    "ballistic": "Ballistic",
    "turret": "Turret",
    "shield": "Shield",
    "status": "Status",
    "economy": "Economy",
    "summoner": "Summoner",
    "lucky": "Lucky",
}
PATH_ONLINE_THRESHOLD = 2
PATH_FULL_THRESHOLD = 4
PATH_BORDER_COLORS = {
    "ballistic": (255, 145, 95),   # orange
    "turret": (95, 220, 255),      # cyan
    "shield": (110, 170, 255),     # blue
    "status": (120, 225, 145),     # green
    "economy": (255, 215, 110),    # gold
    "summoner": (205, 150, 255),   # violet
    "lucky": (255, 120, 185),      # pink
    "general": (150, 175, 210),    # fallback
}

# Path tags for build summaries/tooltips. Multi-tag items intentionally bridge paths.
PROP_PATH_TAGS = {
    "piercing_rounds": ("ballistic",),
    "ricochet_scope": ("ballistic",),
    "shrapnel_shells": ("ballistic",),
    "explosive_rounds": ("ballistic",),
    "auto_turret": ("turret",),
    "stationary_turret": ("turret",),
    "carapace": ("shield",),
    "bone_plating": ("shield",),
    "aegis_pulse": ("shield",),
    "dot_rounds": ("status",),
    "curing_paint": ("status",),
    "ground_spikes": ("status",),
    "mark_vulnerability": ("status", "ballistic"),
    "coin_magnet": ("economy",),
    "golden_interest": ("economy",),
    "coupon": ("economy",),
    "lockbox": ("economy",),
    "bandit_radar": ("economy", "status"),
    "wanted_poster": ("economy", "lucky"),
    "shady_loan": ("economy", "lucky"),
    # Reserved ids for future summoner props
    "summon_core": ("summoner",),
    "summon_link": ("summoner",),
}


def prop_level_from_meta(prop_id: str, meta=None) -> int | None:
    """Canonical per-prop level read from meta state; keeps shop/pause/tooltips aligned."""
    m = _meta_state() if meta is None else meta
    if m is None or not hasattr(m, "get"):
        return None
    iid = str(prop_id or "")
    if iid == "coin_magnet":
        return int(m.get("coin_magnet_radius", 0) // 60)
    if iid == "auto_turret":
        return int(m.get("auto_turret_level", 0))
    if iid == "stationary_turret":
        return int(m.get("stationary_turret_count", 0))
    if iid == "ricochet_scope":
        return int(m.get("ricochet_level", 0))
    if iid == "piercing_rounds":
        return int(m.get("pierce_level", 0))
    if iid == "shrapnel_shells":
        return int(m.get("shrapnel_level", 0))
    if iid == "explosive_rounds":
        return int(m.get("explosive_rounds_level", 0))
    if iid == "dot_rounds":
        return int(m.get("dot_rounds_level", 0))
    if iid == "curing_paint":
        return int(m.get("curing_paint_level", 0))
    if iid == "ground_spikes":
        return int(m.get("ground_spikes_level", 0))
    if iid == "mark_vulnerability":
        return int(m.get("vuln_mark_level", 0))
    if iid == "bandit_radar":
        return int(m.get("bandit_radar_level", 0))
    if iid == "lockbox":
        return int(m.get("lockbox_level", 0))
    if iid == "golden_interest":
        return int(m.get("golden_interest_level", 0))
    if iid == "wanted_poster":
        return int(m.get("wanted_poster_waves", 0))
    if iid == "shady_loan":
        return int(m.get("shady_loan_level", 0))
    if iid == "coupon":
        return int(m.get("coupon_level", 0))
    if iid == "bone_plating":
        return int(m.get("bone_plating_level", 0))
    if iid == "carapace":
        hp = int(m.get("carapace_shield_hp", 0))
        return (hp + 19) // 20
    if iid == "aegis_pulse":
        return int(m.get("aegis_pulse_level", 0))
    return None


def _mix_rgb(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    tt = max(0.0, min(1.0, float(t)))
    return (
        int(a[0] + (b[0] - a[0]) * tt),
        int(a[1] + (b[1] - a[1]) * tt),
        int(a[2] + (b[2] - a[2]) * tt),
    )


def _scale_rgb(color: tuple[int, int, int], scale: float) -> tuple[int, int, int]:
    s = max(0.0, float(scale))
    return (
        max(0, min(255, int(color[0] * s))),
        max(0, min(255, int(color[1] * s))),
        max(0, min(255, int(color[2] * s))),
    )


def prop_path_border_color(prop_id: str) -> tuple[int, int, int]:
    tags = PROP_PATH_TAGS.get(str(prop_id or ""), ())
    if not tags:
        return PATH_BORDER_COLORS["general"]
    c0 = PATH_BORDER_COLORS.get(tags[0], PATH_BORDER_COLORS["general"])
    if len(tags) == 1:
        return c0
    c1 = PATH_BORDER_COLORS.get(tags[1], c0)
    return _mix_rgb(c0, c1, 0.5)


def _truncate_inline(text: str, max_chars: int = 170) -> str:
    s = str(text or "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max(0, max_chars - 3)].rstrip() + "..."


def prop_path_label(prop_id: str) -> str:
    tags = PROP_PATH_TAGS.get(str(prop_id or ""), ())
    if not tags:
        return "General"
    names = [PATH_DISPLAY_NAME.get(t, t.title()) for t in tags]
    return "/".join(names)


def path_scores_from_meta(meta=None) -> dict[str, int]:
    """Weighted path score by current prop levels; used for build clarity in pause/shop."""
    scores = {tag: 0 for tag in PATH_DISPLAY_ORDER}
    m = _meta_state() if meta is None else meta
    if m is None or not hasattr(m, "get"):
        return scores
    for prop_id, tags in PROP_PATH_TAGS.items():
        lvl = prop_level_from_meta(prop_id, m)
        if lvl is None or lvl <= 0:
            continue
        for tag in tags:
            scores[tag] = int(scores.get(tag, 0)) + int(lvl)
    return scores


def path_focus_summary_lines(meta=None, max_lines: int = 3) -> list[str]:
    scores = path_scores_from_meta(meta)
    order_index = {tag: idx for idx, tag in enumerate(PATH_DISPLAY_ORDER)}
    ranked = [(tag, sc) for tag, sc in scores.items() if sc > 0]
    ranked.sort(key=lambda x: (-x[1], order_index.get(x[0], 999)))
    out = []
    for tag, score in ranked[: max(1, int(max_lines))]:
        if score >= PATH_FULL_THRESHOLD:
            state = "full"
        elif score >= PATH_ONLINE_THRESHOLD:
            state = "online"
        else:
            state = "seed"
        out.append(f"{PATH_DISPLAY_NAME.get(tag, tag.title())}: {score} ({state})")
    if not out:
        out.append("No path online yet (2+ tagged levels to activate).")
    return out


def detailed_prop_tooltip_text(it, lvl: int | None, meta=None):
    """More specific tooltip with path context and current->next preview."""
    if not isinstance(it, dict):
        return None
    m = _meta_state() if meta is None else meta
    if m is None or not hasattr(m, "get"):
        return None
    iid = it.get("id")
    path_txt = prop_path_label(iid)
    cur_lvl = 0 if lvl is None else int(lvl)
    max_lvl = it.get("max_level")
    if iid == "shady_loan":
        cur_lvl = max(cur_lvl, int(m.get("shady_loan_last_level", cur_lvl)))
    if cur_lvl <= 0:
        lv1 = owned_prop_tooltip_text(it, 1, m)
        if lv1:
            return _truncate_inline(f"[{path_txt}] Lv1: {lv1}")
        return f"[{path_txt}]"
    now_txt = owned_prop_tooltip_text(it, cur_lvl, m)
    if not now_txt:
        return f"[{path_txt}]"
    next_txt = None
    can_level = max_lvl is None or cur_lvl < int(max_lvl)
    if can_level:
        next_txt = owned_prop_tooltip_text(it, cur_lvl + 1, m)
    if next_txt and next_txt != now_txt:
        return _truncate_inline(f"[{path_txt}] Now: {now_txt} | Next: {next_txt}")
    return _truncate_inline(f"[{path_txt}] {now_txt}")


def owned_prop_tooltip_text(it, lvl: int | None, meta=None):
    iid = it.get("id") if isinstance(it, dict) else None
    m = _meta_state() if meta is None else meta
    if m is None or not hasattr(m, "get"):
        return None
    lvl = 0 if lvl is None else int(lvl)
    if iid == "shady_loan":
        lvl = max(lvl, int(m.get("shady_loan_last_level", lvl)))
    if lvl <= 0:
        return None
    if iid == "lockbox":
        coins = max(0, int(m.get("spoils", 0)))
        pct = int(LOCKBOX_PROTECT_RATES[min(lvl - 1, len(LOCKBOX_PROTECT_RATES) - 1)] * 100)
        protected = lockbox_protected_min(coins, lvl)
        return f"{protected} coins restored (at {pct}%)"
    if iid == "bone_plating":
        gain = max(0, lvl * BONE_PLATING_STACK_HP)
        effective_speed = max(0.30, 0.98 ** lvl)
        spd_pen = max(0.0, (1.0 - effective_speed) * 100.0)
        spd_txt = f", -{spd_pen:.0f}% speed" if spd_pen >= 0.5 else ""
        return f"Every {int(BONE_PLATING_GAIN_INTERVAL)}s gain {gain} hp shield{spd_txt}"
    if iid == "coupon":
        disc = int(COUPON_DISCOUNT_PER * 100 * lvl)
        return f"-{disc}% shop prices"
    if iid == "piercing_rounds":
        return f"Pierce {lvl} extra enemy" + ("ies" if lvl > 1 else "")
    if iid == "ricochet_scope":
        return f"Bounce {lvl} times"
    if iid == "shrapnel_shells":
        base = 25
        per = 10
        chance = min(80, base + per * (lvl - 1))
        return f"{chance}% shrapnel on kill"
    if iid == "explosive_rounds":
        bullet_base = int(m.get("base_dmg", BULLET_DAMAGE_ENEMY)) + int(m.get("dmg", 0))
        radius, dmg, boss_dmg = explosive_rounds_stats(lvl, bullet_base)
        r_tiles = radius / float(CELL_SIZE)
        return f"Explode {dmg}/{boss_dmg} dmg, r {r_tiles:.2f} tiles"
    if iid == "dot_rounds":
        idx = min(max(lvl, 1), len(DOT_ROUNDS_DAMAGE_PER_TICK)) - 1
        pct = int(DOT_ROUNDS_DAMAGE_PER_TICK[idx] * 100)
        duration = float(DOT_ROUNDS_DURATIONS[idx])
        ticks = int(round(duration / float(DOT_ROUNDS_TICK_INTERVAL)))
        max_stacks = int(DOT_ROUNDS_MAX_STACKS[idx])
        return f"{pct}% base dmg per tick ({ticks} ticks), stacks {max_stacks}"
    if iid == "ground_spikes":
        idx = min(max(lvl, 1), len(GROUND_SPIKES_DAMAGE_MULTS)) - 1
        pct = int(GROUND_SPIKES_DAMAGE_MULTS[idx] * 100)
        life = float(GROUND_SPIKES_LIFETIMES[idx])
        max_active = int(GROUND_SPIKES_MAX_ACTIVE[idx])
        return f"{pct}% base dmg, {life:.1f}s life, max {max_active}, slow 5%"
    if iid == "curing_paint":
        idx = min(max(lvl, 1), len(CURING_PAINT_DAMAGE_PER_TICK)) - 1
        pct = int(CURING_PAINT_DAMAGE_PER_TICK[idx] * 100)
        life = float(CURING_PAINT_LIFETIMES[idx])
        return f"{pct}% base dmg/tick (0.5s), {life:.1f}s life"
    if iid == "mark_vulnerability":
        interval, bonus, duration = mark_of_vulnerability_stats(lvl)
        pct = int(bonus * 100)
        return f"Mark {interval:.1f}s, +{pct}% dmg for {duration:.1f}s"
    if iid == "bandit_radar":
        lvl_idx = min(max(lvl, 1), len(BANDIT_RADAR_SLOW_MULT))
        slow_pct = int((1.0 - BANDIT_RADAR_SLOW_MULT[lvl_idx - 1]) * 100)
        dur = BANDIT_RADAR_SLOW_DUR[lvl_idx - 1]
        return f"Bandits -{slow_pct}% speed for {dur:.0f}s"
    if iid == "aegis_pulse":
        idx = min(max(lvl, 1) - 1, len(AEGIS_PULSE_DAMAGE_RATIOS) - 1)
        pct = int(AEGIS_PULSE_DAMAGE_RATIOS[idx] * 100)
        return f"Pulse hits for {pct}% max HP"
    if iid == "golden_interest":
        rate_pct = int(GOLDEN_INTEREST_RATE_PER_LEVEL * 100 * lvl)
        cap = GOLDEN_INTEREST_CAPS[min(lvl - 1, len(GOLDEN_INTEREST_CAPS) - 1)]
        return f"Interest {rate_pct}% (cap {cap})"
    if iid == "wanted_poster":
        waves = int(m.get("wanted_poster_waves", 0))
        status = "ready" if waves > 0 else ("armed" if m.get("wanted_active") else "spent")
        return f"Bounty charges: {waves} ({status})"
    if iid == "shady_loan":
        debt = max(0, int(m.get("shady_loan_remaining_debt", 0)))
        waves = int(m.get("shady_loan_waves_remaining", 0))
        status = m.get("shady_loan_status")
        if status == "defaulted":
            idx = min(max(lvl, 1), SHADY_LOAN_MAX_LEVEL) - 1
            pct = int(SHADY_LOAN_HP_PENALTIES[idx] * 100)
            return f"Defaulted: -{pct}% max HP"
        if status == "repaid" and debt <= 0:
            return "Loan repaid"
        if status == "active" and debt > 0 and waves == 1:
            return "The loan settlement happens after this shop!"
        return f"Debt {debt}, {max(0, waves)} waves left (final clears remainder)"
    if iid == "coin_magnet":
        radius = int(m.get("coin_magnet_radius", 0))
        return f"Pickup radius +{radius}px"
    if iid == "auto_turret":
        return f"Auto-turret count {lvl}"
    if iid == "stationary_turret":
        return f"Stationary turrets {lvl}"
    if iid == "carapace":
        hp = int(m.get("carapace_shield_hp", 0))
        return f"Shield HP {hp}"
    return None


def apply_dot_rounds_stack(target: "Enemy", damage_per_tick: float, duration: float, max_stacks: int) -> None:
    if target is None or max_stacks <= 0 or duration <= 0.0:
        return
    stacks = getattr(target, "dot_rounds_stacks", None)
    if stacks is None:
        stacks = []
        target.dot_rounds_stacks = stacks
    entry = {
        "t": float(duration),
        "dur": float(duration),
        "dmg": float(max(0.0, damage_per_tick)),
    }
    if len(stacks) < max_stacks:
        stacks.append(entry)
    else:
        oldest = stacks.pop(0)
        oldest.update(entry)
        stacks.append(oldest)
    if not hasattr(target, "_dot_rounds_tick_t"):
        target._dot_rounds_tick_t = float(DOT_ROUNDS_TICK_INTERVAL)


def dot_rounds_visual_state(target: "Enemy") -> tuple[float, int]:
    stacks = getattr(target, "dot_rounds_stacks", None)
    if not stacks:
        return 0.0, 0
    ratio = 0.0
    for s in stacks:
        dur = float(s.get("dur", 0.0))
        if dur > 0.0:
            ratio = max(ratio, float(s.get("t", 0.0)) / dur)
    return max(0.0, min(1.0, ratio)), len(stacks)


def spawn_explosive_rounds_vfx(game_state: "GameState", x: float, y: float, radius: float) -> None:
    if game_state is None or not hasattr(game_state, "fx"):
        return
    ttl_min, ttl_max = EXPLOSIVE_ROUNDS_FLASH_TTL
    life = random.uniform(ttl_min, ttl_max)
    base_size = max(3, int(radius * 0.4))
    game_state.fx.particles.append(
        Particle(x, y, 0.0, 0.0, EXPLOSIVE_ROUNDS_FLASH_COLOR, life, base_size)
    )
    count = random.randint(EXPLOSIVE_ROUNDS_FLASH_PARTICLES[0], EXPLOSIVE_ROUNDS_FLASH_PARTICLES[1])
    sp_min, sp_max = EXPLOSIVE_ROUNDS_FLASH_SPEED
    for _ in range(count):
        ang = random.uniform(0.0, math.tau)
        speed = random.uniform(sp_min, sp_max)
        vx = math.cos(ang) * speed
        vy = math.sin(ang) * speed
        p_life = random.uniform(ttl_min, ttl_max)
        size = random.randint(2, max(3, int(radius * 0.2)))
        game_state.fx.particles.append(
            Particle(x, y, vx, vy, EXPLOSIVE_ROUNDS_FLASH_COLOR, p_life, size)
        )


def spawn_dot_rounds_hit_vfx(game_state: "GameState", x: float, y: float) -> None:
    if game_state is None or not hasattr(game_state, "fx"):
        return
    cmin, cmax = DOT_ROUNDS_HIT_SPARK_PARTICLES
    sp_min, sp_max = DOT_ROUNDS_HIT_SPARK_SPEED
    life_min, life_max = DOT_ROUNDS_HIT_SPARK_LIFE
    size_min, size_max = DOT_ROUNDS_HIT_SPARK_SIZE
    c1, c2 = DOT_ROUNDS_HIT_SPARK_CYAN
    g_min = min(c1[1], c2[1])
    g_max = max(c1[1], c2[1])
    count = random.randint(cmin, cmax)
    for _ in range(count):
        ang = random.uniform(0.0, math.tau)
        speed = random.uniform(sp_min, sp_max)
        vx = math.cos(ang) * speed
        vy = math.sin(ang) * speed
        life = random.uniform(life_min, life_max)
        size = random.randint(size_min, size_max)
        if random.random() < 0.28:
            col = DOT_ROUNDS_HIT_SPARK_WHITE
        else:
            col = (0, random.randint(g_min, g_max), 255)
        game_state.fx.particles.append(Particle(x, y, vx, vy, col, life, size))


def spawn_ground_spike_spawn_vfx(game_state: "GameState", x: float, y: float) -> None:
    if game_state is None or not hasattr(game_state, "fx"):
        return
    game_state.fx.particles.append(
        Particle(x, y, 0.0, 0.0, GROUND_SPIKES_RING, 0.16, 7)
    )
    for _ in range(random.randint(2, 4)):
        ang = random.uniform(0.0, math.tau)
        speed = random.uniform(20.0, 90.0)
        vx = math.cos(ang) * speed
        vy = math.sin(ang) * speed
        life = random.uniform(0.10, 0.18)
        size = random.randint(2, 3)
        game_state.fx.particles.append(Particle(x, y, vx, vy, GROUND_SPIKES_COLOR, life, size))


def spawn_ground_spike_hit_vfx(game_state: "GameState", x: float, y: float) -> None:
    if game_state is None or not hasattr(game_state, "fx"):
        return
    count = random.randint(GROUND_SPIKES_HIT_PARTICLES[0], GROUND_SPIKES_HIT_PARTICLES[1])
    sp_min, sp_max = GROUND_SPIKES_HIT_SPEED
    life_min, life_max = GROUND_SPIKES_HIT_LIFE
    size_min, size_max = GROUND_SPIKES_HIT_SIZE
    for _ in range(count):
        ang = random.uniform(0.0, math.tau)
        speed = random.uniform(sp_min, sp_max)
        vx = math.cos(ang) * speed
        vy = math.sin(ang) * speed
        life = random.uniform(life_min, life_max)
        size = random.randint(size_min, size_max)
        col = GROUND_SPIKES_COLOR if random.random() < 0.75 else (255, 255, 255)
        game_state.fx.particles.append(Particle(x, y, vx, vy, col, life, size))


def spawn_curing_paint_spark_vfx(game_state: "GameState", x: float, y: float, intensity: float) -> None:
    if game_state is None or not hasattr(game_state, "fx"):
        return
    if intensity <= 0.0:
        return
    color = random.choice(CURING_PAINT_SPARK_COLORS)
    speed = random.uniform(CURING_PAINT_SPARK_SPEED[0], CURING_PAINT_SPARK_SPEED[1])
    vx = random.uniform(-0.5, 0.5) * speed
    vy = -random.uniform(0.6, 1.0) * speed
    life = random.uniform(CURING_PAINT_SPARK_LIFE[0], CURING_PAINT_SPARK_LIFE[1])
    size = random.randint(CURING_PAINT_SPARK_SIZE[0], CURING_PAINT_SPARK_SIZE[1])
    jx = random.uniform(-6.0, 6.0)
    jy = random.uniform(-6.0, 6.0)
    game_state.fx.particles.append(Particle(x + jx, y + jy, vx, vy, color, life, size))

def trigger_explosive_rounds(player, game_state: "GameState", enemies,
                             origin_pos: tuple[float, float], bullet_base: int | None = None, meta=None) -> None:
    m = _meta_state() if meta is None else meta
    lvl = int(m.get("explosive_rounds_level", 0)) if hasattr(m, "get") else 0
    if lvl <= 0 or player is None or game_state is None or enemies is None or origin_pos is None:
        return
    if bullet_base is None:
        bullet_base = int(getattr(player, "bullet_damage", BULLET_DAMAGE_ENEMY))
    radius, base_dmg, boss_dmg = explosive_rounds_stats(lvl, bullet_base)
    if base_dmg <= 0 or radius <= 0:
        return
    queue = deque([(float(origin_pos[0]), float(origin_pos[1]))])
    while queue:
        cx, cy = queue.popleft()
        spawn_explosive_rounds_vfx(game_state, cx, cy, radius)
        for z in list(enemies):
            if getattr(z, "hp", 0) <= 0:
                continue
            zx, zy = z.rect.center
            dx = zx - cx
            dy = zy - cy
            zr = float(getattr(z, "radius", getattr(z, "size", CELL_SIZE) * 0.5))
            if dx * dx + dy * dy > (radius + zr) ** 2:
                continue
            dealt = boss_dmg if getattr(z, "is_boss", False) else base_dmg
            if dealt <= 0:
                continue
            if getattr(z, "type", "") == "boss_mist":
                if random.random() < MIST_PHASE_CHANCE:
                    game_state.add_damage_text(zx, zy, "TELEPORT", crit=False, kind="shield")
                    pdx = zx - player.rect.centerx
                    pdy = zy - player.rect.centery
                    L = (pdx * pdx + pdy * pdy) ** 0.5 or 1.0
                    ox = pdx / L * (MIST_PHASE_TELE_TILES * CELL_SIZE)
                    oy = pdy / L * (MIST_PHASE_TELE_TILES * CELL_SIZE)
                    z.x += ox
                    z.y += oy - INFO_BAR_HEIGHT
                    z.rect.x = int(z.x)
                    z.rect.y = int(z.y + INFO_BAR_HEIGHT)
                    continue
                dist_tiles = math.hypot((zx - cx) / CELL_SIZE, (zy - cy) / CELL_SIZE)
                if dist_tiles >= MIST_RANGED_REDUCE_TILES:
                    dealt = int(dealt * MIST_RANGED_MULT)
            dealt = apply_vuln_bonus(z, dealt)
            if dealt <= 0:
                continue
            hp_before = int(getattr(z, "hp", 0))
            if getattr(z, "shield_hp", 0) > 0:
                blocked = min(dealt, z.shield_hp)
                z.shield_hp -= dealt
                if blocked > 0:
                    game_state.add_damage_text(zx, zy, blocked, crit=False, kind="shield")
                overflow = dealt - blocked
                if overflow > 0:
                    z.hp -= overflow
                    game_state.add_damage_text(zx, zy - 10, overflow, crit=False, kind="hp_player")
            else:
                z.hp -= dealt
                game_state.add_damage_text(zx, zy, dealt, crit=False, kind="hp_player")
            if z.hp < hp_before:
                z._hit_flash = float(HIT_FLASH_DURATION)
                z._flash_prev_hp = int(max(0, z.hp))
            if z.hp <= 0 and not getattr(z, "_explosive_rounds_done", False):
                z._explosive_rounds_done = True
                queue.append((zx, zy))


def _aegis_pulse_damage_for(level: int, player_max_hp: int | float | None, meta=None) -> int:
    """Damage scales off max HP using per-level ratios."""
    lvl = max(1, int(level))
    ratios = AEGIS_PULSE_DAMAGE_RATIOS
    ratio = ratios[min(lvl - 1, len(ratios) - 1)]
    base_hp = player_max_hp
    m = _meta_state() if meta is None else meta
    if base_hp is None:
        if hasattr(m, "get"):
            base_hp = int(m.get("base_maxhp", PLAYER_MAX_HP)) + int(m.get("maxhp", 0))
        else:
            base_hp = int(PLAYER_MAX_HP)
    base_hp = max(1, int(base_hp))
    return max(1, int(round(base_hp * ratio)))


def aegis_pulse_stats(level: int, player_max_hp: int | float | None = None, meta=None) -> tuple[int, int, float]:
    """Return (radius_px, damage, cooldown_s) for the given Aegis Pulse level."""
    lvl = max(1, int(level))
    radius = AEGIS_PULSE_BASE_RADIUS + AEGIS_PULSE_RADIUS_PER_LEVEL * (lvl - 1)
    damage = _aegis_pulse_damage_for(lvl, player_max_hp, meta=meta)
    cooldown = max(0.3, AEGIS_PULSE_BASE_COOLDOWN - AEGIS_PULSE_COOLDOWN_DELTA * (lvl - 1))
    return radius, damage, cooldown


def aegis_pulse_wave_count(level: int) -> int:
    """Number of waves per activation; scales up to 3."""
    lvl = max(1, int(level))
    return max(1, min(3, lvl))

def aegis_pulse_visual_profile(level: int) -> tuple[int, float, float]:
    """Return (layers, expand_time, layer_gap) for the ripple animation."""
    lvl = max(1, int(level))
    layers = int(min(AEGIS_PULSE_MAX_LAYERS,
                     AEGIS_PULSE_BASE_LAYERS + math.ceil(lvl * AEGIS_PULSE_LAYERS_PER_LEVEL)))
    expand_time = max(
        AEGIS_PULSE_MIN_EXPAND_TIME,
        AEGIS_PULSE_BASE_EXPAND_TIME - AEGIS_PULSE_EXPAND_DELTA * (lvl - 1)
    )
    layer_gap = expand_time / max(1, layers)
    return layers, expand_time, layer_gap

def shop_price(base_cost: int, level_idx: int, kind: str = "normal", prop_level: int | None = None) -> int:
    """
    价格逻辑：
    - 基于关卡指数/线性上调（reroll 恒定）
    - 同一关内，同一条目随拥有等级叠加涨价（SHOP_PRICE_STACK）
    """
    discount_lvl = min(COUPON_MAX_LEVEL, int(_meta_state().get("coupon_level", 0)))
    discount_mult = max(0.0, 1.0 - COUPON_DISCOUNT_PER * discount_lvl)
    lvl_owned = max(0, int(prop_level or 0))
    if kind == "reroll":
        price = int(base_cost)
    else:
        exp = (SHOP_PRICE_EXP ** level_idx)
        lin = (1.0 + SHOP_PRICE_LINEAR * level_idx)
        stack = (SHOP_PRICE_STACK ** lvl_owned)
        price = int(round(base_cost * exp * lin * stack))
    price = int(round(price * discount_mult))
    return max(1, price)


# resume flags
_pending_shop = False  # if True, CONTINUE should open the shop first
# --- enemy type colors (for rendering) ---
ENEMY_COLORS = {
    "basic": (200, 70, 70),
    "fast": (255, 160, 60),
    "tank": (120, 180, 255),
    "strong": (220, 60, 140),
    "ranged": (255, 120, 50),
    "suicide": (255, 90, 90),
    "bomber": (255, 90, 90),
    "buffer": (80, 200, 140),
    "shielder": (60, 160, 255),
    "splinter": (180, 120, 250),
    "splinterling": (210, 160, 255),
    "mistling": (228, 218, 255),
    "bandit": (255, 215, 0),  # 金币大盗：金色
}
# --- colors (add) ---
BOSS_MEM_ENRAGED_COLOR = (102, 0, 102)
ENEMY_COLORS.update({
    "boss_mem": (170, 40, 200),  # 明亮紫色
    "boss_mem_enraged": (102, 0, 102),  # 暗紫色
    "corruptling": (120, 220, 120),  # 浅绿
    "boss_mist": (150, 140, 220),  # 冷紫
    "mist_clone": (180, 170, 240),  # 更浅，便于区分
})
ENEMY_COLORS["ravager"] = (120, 200, 230)  # dash-heavy brute
# --- XP rewards (add) ---
XP_PER_ENEMY_TYPE.update({
    "boss_mem": 40,  # base 给足奖励；击杀时还有 is_boss 3x 乘区
    "corruptling": 5,
})
XP_PER_ENEMY_TYPE["ravager"] = 12
# --- wave spawning ---
SPAWN_INTERVAL = 8.0
SPAWN_BASE = 3
SPAWN_GROWTH = 1
ENEMY_CAP = 30
# --- new enemy types tuning ---
RANGED_COOLDOWN = 1.2  # 远程怪开火间隔
RANGED_PROJ_SPEED = 520.0
RANGED_PROJ_DAMAGE = 12
SUICIDE_FUSE = 4.0  # 自爆怪引信时长（生成后计时）
SUICIDE_FLICKER = 0.8  # 引信末端闪烁时长
SUICIDE_RADIUS = 90  # 自爆半径（像素）
SUICIDE_DAMAGE = 35  # 对玩家伤害
SUICIDE_ARM_DIST = int(2.2 * CELL_SIZE)
BUFF_RADIUS = 220  # 增益怪范围
BUFF_DURATION = 4.0
BUFF_COOLDOWN = 7.0
BUFF_ATK_MULT = 1.3  # 攻击乘区
BUFF_SPD_ADD = 1  # 额外速度（像素/帧）
SHIELD_RADIUS = 220  # 护盾怪范围
SHIELD_AMOUNT = 25  # 护盾值
SHIELD_DURATION = 5.0
SHIELD_COOLDOWN = 9.0
# ----- threat budget spawning -----
THREAT_BUDGET_BASE = 6  # base points for level 0 (Lv1 in UI)
THREAT_BUDGET_EXP = 1.18  # exponential growth per level (≈+18%/lvl feels roguelite)
THREAT_BUDGET_MIN = 5  # never below this
THREAT_BOSS_BONUS = 1.5  # first spawn on boss level gets +50% budget
# cost per enemy type (integer points)
THREAT_COSTS = {
    "basic": 1,
    "fast": 2,
    "ranged": 3,
    "suicide": 2,
    "buffer": 3,
    "shielder": 3,
    "strong": 4,
    "tank": 4,
    "ravager": 5,
    "splinter": 4,
}
# (Optional) relative preference if multiple types fit the remaining budget
THREAT_WEIGHTS = {
    "basic": 50,
    "fast": 20,
    "ranged": 16,
    "suicide": 14,
    "buffer": 10,
    "shielder": 10,
    "strong": 8,
    "tank": 6,
    "ravager": 8,
    "splinter": 10,
}
# derive cooldown from either explicit FIRE_RATE or SPACING
if FIRE_RATE:
    FIRE_COOLDOWN = 1.0 / float(FIRE_RATE)
else:
    FIRE_COOLDOWN = float(BULLET_SPACING_PX) / float(BULLET_SPEED)
# Audio volumes (placeholders; no audio wired yet)
FX_VOLUME = 70  # 0-100
BGM_VOLUME = 60  # 0-100

LEVELS = [
    {"obstacle_count": 15, "item_count": 3, "enemy_count": 1, "block_hp": 10, "enemy_types": ["basic"],
     "reward": "enemy_fast"},
    {"obstacle_count": 18, "item_count": 4, "enemy_count": 2, "block_hp": 15, "enemy_types": ["basic", "strong"],
     "reward": "enemy_strong"},
]
# 方向向量
DIRECTIONS = {
    pygame.K_a: (-1, 0),
    pygame.K_d: (1, 0),
    pygame.K_w: (0, -1),
    pygame.K_s: (0, 1),
}

# === Input bindings (customizable) ===
DEFAULT_BINDINGS = {
    "move_up": pygame.K_w,
    "move_down": pygame.K_s,
    "move_left": pygame.K_a,
    "move_right": pygame.K_d,
    "blast": pygame.K_q,
    "teleport": pygame.K_e,
}
# Live bindings the game uses
BINDINGS = dict(DEFAULT_BINDINGS)
BINDING_SCANCODES = {}
_MANUAL_SCANCODES = {
    pygame.K_UP: 82,
    pygame.K_DOWN: 81,
    pygame.K_LEFT: 80,
    pygame.K_RIGHT: 79,
}


def _compute_scancode(keycode: int) -> int | None:
    """Return a scancode for a pygame keycode, or None if unknown."""
    sc = _MANUAL_SCANCODES.get(keycode)
    try:
        sc = sc if sc is not None else pygame.key.get_scancode_from_key(keycode)
    except Exception:
        sc = sc if sc is not None else None
    if sc is None or sc < 0:
        try:
            sc = pygame.key.get_scancode_from_name(pygame.key.name(keycode))
        except Exception:
            sc = sc if sc is not None else None
    if sc is not None and sc >= 0:
        return sc
    return None


def _refresh_scancodes():
    meta = _meta_state()
    BINDING_SCANCODES.clear()
    for action, keycode in BINDINGS.items():
        sc = _compute_scancode(int(keycode))
        if sc is not None:
            BINDING_SCANCODES[action] = sc
    WEB_INPUT.refresh_binding_aliases(BINDINGS)
    # mirror into META for persistence
    meta["bindings"] = {k: int(v) for k, v in BINDINGS.items()}


_refresh_scancodes()


def _apply_meta_bindings(meta: dict):
    """Load saved bindings from META into live bindings."""
    saved = meta.get("bindings") if meta else None
    if not isinstance(saved, dict):
        return
    for action, keycode in saved.items():
        try:
            set_binding(action, int(keycode))
        except Exception:
            continue
    _refresh_scancodes()


def action_key(action: str) -> int | None:
    """Return the pygame keycode for a named action."""
    return BINDINGS.get(action)


def set_binding(action: str, keycode: int) -> None:
    """Update the live binding for an action."""
    if action in DEFAULT_BINDINGS and isinstance(keycode, int):
        meta = _meta_state()
        BINDINGS[action] = keycode
        sc = _compute_scancode(keycode)
        if sc is not None:
            BINDING_SCANCODES[action] = sc
        elif action in BINDING_SCANCODES:
            BINDING_SCANCODES.pop(action, None)
        meta.setdefault("bindings", {})[action] = int(keycode)
        WEB_INPUT.refresh_binding_aliases(BINDINGS)


def binding_name(action: str) -> str:
    """Human-friendly key name."""
    key = action_key(action)
    try:
        return pygame.key.name(key).upper() if key is not None else "UNBOUND"
    except Exception:
        return "UNBOUND"


def binding_pressed(keys, action: str) -> bool:
    """Check if a binding is pressed given pygame.key.get_pressed().
    Uses scancode mapping so large keycodes (e.g., arrow keys) still work."""
    key = action_key(action)
    if key is None:
        return False
    if IS_WEB:
        return WEB_INPUT.binding_pressed(action, key)
    pressed = pygame.key.get_pressed()  # ensures we use pygame's full key mapping
    sc = BINDING_SCANCODES.get(action)
    if sc is not None and 0 <= sc < len(pressed) and pressed[sc]:
        return True
    # Fallback to pygame's keycode indexing (handles arrow key keycodes internally)
    try:
        return bool(pressed[key])
    except Exception:
        return False


def _bandit_death_notice(z, game_state):
    """Fire a one-time banner/text when a bandit dies, regardless of damage source."""
    if getattr(z, "type", "") != "bandit":
        return
    if getattr(z, "hp", 1) > 0:
        return
    if getattr(z, "_bandit_notice_done", False):
        return
    z._bandit_notice_done = True
    # If a wanted poster is active, let the bounty banner take over.
    meta = _meta_state()
    wanted_active = bool(meta.get("wanted_active", False) or getattr(game_state, "wanted_wave_active", False))
    if wanted_active:
        return
    stolen = int(getattr(z, "_stolen_total", 0))
    bonus = (int(stolen * BANDIT_BONUS_RATE) + int(BANDIT_BONUS_FLAT)) if stolen > 0 else 0
    refund = stolen + bonus
    if hasattr(game_state, "flash_banner"):
        if refund > 0:
            game_state.flash_banner(f"BANDIT DOWN — COINS +{refund}", sec=1.2)
        else:
            game_state.flash_banner("BANDIT DOWN", sec=1.2)
    game_state.add_damage_text(
        z.rect.centerx, z.rect.centery,
        f"+{refund}" if refund > 0 else "BANDIT DOWN",
        crit=True, kind="shield"
    )


def increment_kill_count(amount: int = 1) -> None:
    """Track total enemy kills this run for scaling effects."""
    meta = _meta_state()
    try:
        meta["kill_count"] = int(meta.get("kill_count", 0)) + int(amount)
    except Exception:
        meta["kill_count"] = int(amount)


def is_action_event(event, action: str) -> bool:
    """Shortcut for KEYDOWN on a given action binding."""
    if event.type != pygame.KEYDOWN:
        return False
    if IS_WEB:
        return WEB_INPUT.event_matches_action(event, action, action_key)
    return event.key == action_key(action)
# ==================== Save/Load Helpers ====================
_shop_sprite_cache: dict[str, pygame.Surface | bool] = {}
_web_save_cache: Optional[dict] = None
WEB_SAVE_STORAGE_KEY = "z_game_save_v1"


def _web_storage():
    return persistence_support.web_storage(_THIS_MODULE)


def _store_web_save(data: Optional[dict]) -> None:
    persistence_support.store_web_save(_THIS_MODULE, data)


def _load_web_save() -> Optional[dict]:
    return persistence_support.load_web_save(_THIS_MODULE)
def _load_shop_sprite(filename: str, max_size: tuple[int, int],
                      *, allow_upscale: bool = False) -> Optional["pygame.Surface"]:
    """Load and cache a sprite from assets/sprites, scaled to max_size."""
    if not filename:
        return None
    rel_path = os.path.normpath(filename)
    key = f"{rel_path}|{int(max_size[0])}x{int(max_size[1])}|up{int(allow_upscale)}"
    if key in _shop_sprite_cache:
        cached = _shop_sprite_cache[key]
        return cached if cached is not False else None
    candidates = _asset_candidates("sprites", rel_path)
    _shop_sprite_cache[key] = False
    for p in candidates:
        if p and os.path.exists(p):
            try:
                img = pygame.image.load(p).convert_alpha()
                if max_size:
                    max_w, max_h = int(max_size[0]), int(max_size[1])
                    if max_w > 0 and max_h > 0:
                        w, h = img.get_size()
                        if w > 0 and h > 0:
                            scale = min(max_w / w, max_h / h)
                            if not allow_upscale:
                                scale = min(scale, 1.0)
                            if scale != 1.0:
                                img = pygame.transform.smoothscale(
                                    img,
                                    (max(1, int(w * scale)), max(1, int(h * scale))),
                                )
                _shop_sprite_cache[key] = img
                break
            except Exception:
                _shop_sprite_cache[key] = False
    cached = _shop_sprite_cache[key]
    return cached if cached is not False else None


def _clear_shop_cache():
    runtime = _runtime_state()
    runtime.clear(
        "_shop_slot_ids_cache",
        "_shop_slots_cache",
        "_shop_reroll_id_cache",
        "_shop_reroll_cache",
        "_resume_shop_cache",
        "_intro_envelope",
    )


def _exportable_save_data() -> Optional[dict]:
    return persistence_support.exportable_save_data(_THIS_MODULE)


def _web_download_text(filename: str, text: str) -> tuple[bool, str]:
    return persistence_support.web_download_text(_THIS_MODULE, filename, text)


def export_current_save() -> tuple[bool, str]:
    return persistence_support.export_current_save(_THIS_MODULE)


def _golden_interest_gain(coins: int, level: int) -> int:
    """Return the per-wave interest payout based on current coins and Golden Interest level."""
    lvl = max(0, min(GOLDEN_INTEREST_MAX_LEVEL, int(level)))
    if lvl <= 0 or coins <= 0:
        return 0
    rate = GOLDEN_INTEREST_RATE_PER_LEVEL * lvl
    cap = GOLDEN_INTEREST_CAPS[min(lvl - 1, len(GOLDEN_INTEREST_CAPS) - 1)]
    raw_gain = math.floor(max(0, coins) * rate)
    return max(0, min(int(raw_gain), int(cap)))


def apply_golden_interest_payout() -> int:
    """
    Apply Golden Interest on shop exit (start of next wave).
    Returns the coins gained so callers can surface feedback if desired.
    """
    meta = _meta_state()
    coins = int(meta.get("spoils", 0))
    level = int(meta.get("golden_interest_level", 0))
    gain = _golden_interest_gain(coins, level)
    if gain > 0:
        meta["spoils"] = coins + gain
    return gain


def show_golden_interest_popup(screen, gain: int, new_total: int) -> None:
    """Simple modal over the shop that confirms Golden Interest payout with a coin-fountain flair."""
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont(None, 54, bold=True)
    body_font = pygame.font.SysFont(None, 30)
    btn_font = pygame.font.SysFont(None, 32)
    gold = (255, 215, 120)
    spawn_fountain = gain > 0
    # dim overlay
    dim = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    dim.fill((4, 6, 10, 170))
    # panel
    panel_w, panel_h = 520, 260
    panel = pygame.Rect(0, 0, panel_w, panel_h)
    panel.center = (VIEW_W // 2, VIEW_H // 2)
    btn_rect = pygame.Rect(0, 0, 180, 54)
    btn_rect.center = (panel.centerx, panel.bottom - 70)
    # coin fountain particles
    coins: list[dict] = []
    spawn_accum = 0.0
    # fountain intensity scales with how much interest was gained
    if gain <= 0:
        spawn_rate = 0.0
    elif gain < 10:
        spawn_rate = 4.0
    elif gain < 30:
        spawn_rate = 14.0
    elif gain < 50:
        spawn_rate = 20.0
    else:
        spawn_rate = 28.0
    panel_block = panel.inflate(60, 60)

    def spawn_coin():
        # try a few times to avoid spawning over the modal
        for _ in range(4):
            x = random.uniform(40, VIEW_W - 40)
            y = random.uniform(40, VIEW_H - 40)
            if panel_block.collidepoint(x, y):
                continue
            vx = random.uniform(-220, 220)
            vy = random.uniform(-280, -120)
            coins.append({
                "x": x,
                "y": y,
                "vx": vx,
                "vy": vy,
                "ttl": 3.0,
                "r": random.randint(5, 8),
            })
            break

    while True:
        dt = clock.tick(60) / 1000.0
        # spawn coins continuously until the modal closes (only if we earned interest)
        if spawn_fountain:
            spawn_accum += dt * spawn_rate  # coins per second based on gain
            while spawn_accum >= 1.0:
                spawn_coin()
                spawn_accum -= 1.0
        # update coins
        alive = []
        if spawn_fountain:
            for c in coins:
                c["ttl"] -= dt
                if c["ttl"] <= 0:
                    continue
                c["vy"] += 420 * dt
                c["x"] += c["vx"] * dt
                c["y"] += c["vy"] * dt
                alive.append(c)
        coins = alive

        screen.blit(dim, (0, 0))
        # draw fountain behind panel so it never blocks the modal
        if spawn_fountain:
            for c in coins:
                pygame.draw.circle(screen, gold, (int(c["x"]), int(c["y"])), int(c["r"]))

        pygame.draw.rect(screen, (30, 24, 10), panel, border_radius=14)
        pygame.draw.rect(screen, gold, panel, width=3, border_radius=14)
        title = title_font.render("Golden Interest", True, gold)
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 48)))
        desc_text = (
            "Your saved coins generated interest!"
            if gain > 0
            else "Saving more coins in the shop to earn interest!"
        )
        desc = body_font.render(desc_text, True, (235, 225, 205))
        screen.blit(desc, desc.get_rect(center=(panel.centerx, panel.top + 96)))
        if gain > 0:
            gain_text = body_font.render(f"+{gain} coins (now: {new_total})", True, gold)
            screen.blit(gain_text, gain_text.get_rect(center=(panel.centerx, panel.top + 140)))
        pygame.draw.rect(screen, (60, 50, 20), btn_rect, border_radius=10)
        pygame.draw.rect(screen, gold, btn_rect, width=2, border_radius=10)
        btn_label = btn_font.render("Next", True, gold)
        screen.blit(btn_label, btn_label.get_rect(center=btn_rect.center))
        pygame.display.flip()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                flush_events()
                return
            if ev.type == pygame.MOUSEBUTTONDOWN and btn_rect.collidepoint(ev.pos):
                flush_events()
                return


def _shady_loan_level_idx(level: int) -> int:
    lvl = max(0, min(SHADY_LOAN_MAX_LEVEL, int(level)))
    return max(0, lvl - 1)


def purchase_shady_loan() -> dict:
    """Increment Shady Loan, grant upfront coins, and refresh repayment with stacking debt."""
    meta = _meta_state()
    runtime = _runtime_state()
    prev_lvl = int(meta.get("shady_loan_level", 0))
    prev_debt = max(0, int(meta.get("shady_loan_remaining_debt", 0)))
    meta["shady_loan_status"] = "active"
    # Grace current level so repayment starts next level, not immediately.
    meta["shady_loan_grace_level"] = int(runtime.get("current_level", -1))
    # If the previous loan was fully repaid and we were at cap, restart at Lv1.
    if prev_lvl >= SHADY_LOAN_MAX_LEVEL and prev_debt <= 0:
        purchase_level = 1
    else:
        purchase_level = min(SHADY_LOAN_MAX_LEVEL, prev_lvl + 1 if prev_lvl > 0 else 1)
        if prev_lvl >= SHADY_LOAN_MAX_LEVEL and prev_debt > 0:
            purchase_level = SHADY_LOAN_MAX_LEVEL
    idx = _shady_loan_level_idx(purchase_level)
    instant = int(SHADY_LOAN_INSTANT_GOLD[idx])
    debt_add = int(SHADY_LOAN_BASE_DEBT[idx])
    new_debt = prev_debt + debt_add
    new_waves = int(meta.get("shady_loan_waves_remaining", 0)) + 1  # each purchase adds one wave
    meta["spoils"] = int(meta.get("spoils", 0)) + instant
    meta["shady_loan_last_level"] = purchase_level
    if prev_debt <= 0:
        meta["shady_loan_level"] = purchase_level
    else:
        meta["shady_loan_level"] = max(prev_lvl, purchase_level)
    meta["shady_loan_waves_remaining"] = new_waves
    meta["shady_loan_remaining_debt"] = new_debt
    meta["shady_loan_defaulted"] = False
    return {
        "level": int(meta["shady_loan_level"]),
        "instant": instant,
        "waves": new_waves,
        "debt": new_debt,
    }


def use_wanted_poster() -> dict:
    """Activate a 2-wave bounty window for bandit kills (consumable in shop)."""
    meta = _meta_state()
    waves = int(meta.get("wanted_poster_waves", 0)) + WANTED_POSTER_WAVES
    meta["wanted_poster_waves"] = waves
    meta["wanted_active"] = False  # will arm on next level start
    return {"waves": waves}


def apply_shady_loan_hp_penalty(penalty_ratio: float) -> int:
    """Apply the max HP cut when defaulting; returns the new max HP."""
    meta = _meta_state()
    runtime = _runtime_state()
    base_hp = max(1, int(meta.get("base_maxhp", PLAYER_MAX_HP)))
    bonus_hp = max(0, int(meta.get("maxhp", 0)))
    total_hp = base_hp + bonus_hp
    target = max(1, int(math.floor(total_hp * (1.0 - penalty_ratio))))
    new_bonus = min(bonus_hp, max(0, target - 1))
    new_base = max(1, target - new_bonus)
    meta["base_maxhp"] = new_base
    meta["maxhp"] = new_bonus
    carry = runtime.get("_carry_player_state")
    if isinstance(carry, dict):
        carry["hp"] = min(target, max(1, int(carry.get("hp", target))))
    baseline = runtime.get("_player_level_baseline")
    if isinstance(baseline, dict):
        baseline["hp"] = min(target, max(1, int(baseline.get("hp", target))))
        baseline["max_hp"] = min(target, max(1, int(baseline.get("max_hp", target))))
    return target


def apply_shady_loan_repayment() -> Optional[dict]:
    """
    Resolve one wave of Shady Loan repayment. Returns a summary dict when work was done,
    or None if no active loan exists.
    """
    meta = _meta_state()
    runtime = _runtime_state()
    level = int(meta.get("shady_loan_level", 0))
    debt_left = int(meta.get("shady_loan_remaining_debt", 0))
    waves_left = int(meta.get("shady_loan_waves_remaining", 0))
    coins_before = max(0, int(meta.get("spoils", 0)))
    current_level = int(runtime.get("current_level", -1))
    grace_level = int(meta.get("shady_loan_grace_level", -1))
    if meta.get("shady_loan_status") == "active" and debt_left > 0 and current_level == grace_level:
        return {
            "level": level,
            "raw_payment": 0,
            "capped_payment": 0,
            "actual_payment": 0,
            "coins_before": coins_before,
            "coins_after": coins_before,
            "debt_left": debt_left,
            "waves_left": waves_left,
            "defaulted": False,
            "hp_penalty_pct": 0.0,
            "new_max_hp": None,
            "cleared": False,
            "deferred": True,
        }  # skip repayment on the purchase level, but show a notice
    if level <= 0:
        return None
    if debt_left <= 0:
        meta["shady_loan_waves_remaining"] = 0
        return None
    idx = _shady_loan_level_idx(level)
    penalty_ratio = SHADY_LOAN_HP_PENALTIES[idx]
    lockbox_lvl = int(meta.get("lockbox_level", 0))
    # Already overdue -> apply default immediately
    if waves_left <= 0:
        new_max = apply_shady_loan_hp_penalty(penalty_ratio)
        meta["shady_loan_remaining_debt"] = 0
        meta["shady_loan_waves_remaining"] = 0
        meta["shady_loan_defaulted"] = True
        meta["shady_loan_status"] = "defaulted"
        meta["shady_loan_last_level"] = level
        meta["shady_loan_level"] = 0
        return {
            "level": level,
            "raw_payment": 0,
            "capped_payment": 0,
            "actual_payment": 0,
            "coins_before": coins_before,
            "coins_after": coins_before,
            "debt_left": 0,
            "waves_left": 0,
            "defaulted": True,
            "hp_penalty_pct": penalty_ratio,
            "new_max_hp": new_max,
            "cleared": False,
        }
    # Final wave: attempt to clear the entire remaining debt in one shot
    if waves_left <= 1:
        pay_all = clamp_coin_loss_with_lockbox(coins_before, min(debt_left, coins_before), lockbox_lvl)
        meta["spoils"] = coins_before - pay_all
        coins_after = int(meta.get("spoils", coins_before))
        debt_left = max(0, debt_left - pay_all)
        waves_left = 0
        defaulted = False
        new_max_hp = None
        if debt_left > 0:
            defaulted = True
            meta["shady_loan_defaulted"] = True
            meta["shady_loan_status"] = "defaulted"
            meta["shady_loan_last_level"] = level
            new_max_hp = apply_shady_loan_hp_penalty(penalty_ratio)
            debt_left = 0
            coins_after = int(meta.get("spoils", coins_after))
        else:
            meta["shady_loan_defaulted"] = False
            meta["shady_loan_status"] = "repaid"
            meta["shady_loan_last_level"] = level
        meta["shady_loan_level"] = 0
        meta["shady_loan_remaining_debt"] = debt_left
        meta["shady_loan_waves_remaining"] = waves_left
        return {
            "level": level,
            "raw_payment": pay_all,
            "capped_payment": pay_all,
            "actual_payment": pay_all,
            "coins_before": coins_before,
            "coins_after": coins_after,
            "debt_left": debt_left,
            "waves_left": waves_left,
            "defaulted": defaulted,
            "hp_penalty_pct": penalty_ratio if defaulted else 0.0,
            "new_max_hp": new_max_hp,
            "cleared": (debt_left <= 0 and not defaulted),
        }
    # Regular wave: pay capped percentage
    rate = float(SHADY_LOAN_DEBT_RATES[idx])
    cap = int(SHADY_LOAN_DEBT_CAPS[idx])
    raw_payment = int(math.floor(coins_before * rate))
    capped_payment = min(raw_payment, cap)
    actual_payment = min(capped_payment, coins_before, debt_left)
    actual_payment = clamp_coin_loss_with_lockbox(coins_before, actual_payment, lockbox_lvl)
    if actual_payment > 0:
        meta["spoils"] = coins_before - actual_payment
    coins_after = int(meta.get("spoils", coins_before))
    debt_left = max(0, debt_left - actual_payment)
    waves_left = max(0, waves_left - 1)
    defaulted = False
    new_max_hp = None
    if debt_left <= 0:
        debt_left = 0
        waves_left = 0
        meta["shady_loan_defaulted"] = False
        meta["shady_loan_status"] = "repaid"
        meta["shady_loan_last_level"] = level
        meta["shady_loan_level"] = 0
    meta["shady_loan_remaining_debt"] = debt_left
    meta["shady_loan_waves_remaining"] = waves_left
    return {
        "level": level,
        "raw_payment": raw_payment,
        "capped_payment": capped_payment,
        "actual_payment": actual_payment,
        "coins_before": coins_before,
        "coins_after": coins_after,
        "debt_left": debt_left,
        "waves_left": waves_left,
        "defaulted": defaulted,
        "hp_penalty_pct": penalty_ratio if defaulted else 0.0,
        "new_max_hp": new_max_hp,
        "cleared": (debt_left <= 0 and not defaulted),
    }


def show_shady_loan_popup(screen, outcome: dict) -> None:
    """Small modal summarizing Shady Loan repayment/default."""
    meta = _meta_state()
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont(None, 50, bold=True)
    body_font = pygame.font.SysFont(None, 28)
    btn_font = pygame.font.SysFont(None, 32)
    dim = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 170))
    panel_w, panel_h = 620, 260
    panel = pygame.Rect(0, 0, panel_w, panel_h)
    panel.center = (VIEW_W // 2, VIEW_H // 2)
    btn_rect = pygame.Rect(0, 0, 180, 52)
    btn_rect.center = (panel.centerx, panel.bottom - 60)
    red = (210, 80, 70)
    gold = (255, 215, 140)
    title_txt = "Shady Loan"
    lines: list[str] = []
    if outcome.get("defaulted"):
        pct = int(outcome.get("hp_penalty_pct", 0.0) * 100)
        new_hp = outcome.get("new_max_hp", "?")
        title_txt = "Shady Loan Defaulted"
        lines.append(f"Missed the deadline: -{pct}% max HP (now {new_hp}).")
        lines.append("Debt wiped, but the scar remains.")
    elif outcome.get("cleared"):
        title_txt = "Shady Loan Repaid"
        lines.append(f"Loan fully repaid at Lv{outcome.get('level', 1)}.")
        lines.append(f"Coins now: {outcome.get('coins_after', meta.get('spoils', 0))}.")
    elif outcome.get("deferred"):
        title_txt = "Shady Loan"
        lines.append("Repayment starts next level. No coins taken this wave.")
        lines.append(f"Debt left: {outcome.get('debt_left', 0)} | Waves left: {outcome.get('waves_left', 0)}")
        lines.append(f"Coins now: {outcome.get('coins_after', meta.get('spoils', 0))}.")
    else:
        payment = outcome.get("actual_payment", 0)
        debt_left = outcome.get("debt_left", 0)
        waves_left = outcome.get("waves_left", 0)
        lines.append(f"Paid {payment} coins toward the loan.")
        lines.append(f"Debt left: {debt_left} | Waves left: {waves_left}")
        lines.append(f"Coins now: {outcome.get('coins_after', meta.get('spoils', 0))}.")
    while True:
        screen.blit(dim, (0, 0))
        pygame.draw.rect(screen, (24, 22, 28), panel, border_radius=14)
        pygame.draw.rect(screen, red if outcome.get("defaulted") else gold, panel, 3, border_radius=14)
        title = title_font.render(title_txt, True, gold if not outcome.get("defaulted") else red)
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 46)))
        y = panel.top + 96
        for line in lines:
            surf = body_font.render(line, True, (230, 230, 230))
            screen.blit(surf, surf.get_rect(center=(panel.centerx, y)))
            y += 34
        pygame.draw.rect(screen, (50, 50, 60), btn_rect, border_radius=10)
        pygame.draw.rect(screen, gold, btn_rect, 2, border_radius=10)
        btn_lbl = btn_font.render("Next", True, gold)
        screen.blit(btn_lbl, btn_lbl.get_rect(center=btn_rect.center))
        pygame.display.flip()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                flush_events()
                return
            if ev.type == pygame.MOUSEBUTTONDOWN and btn_rect.collidepoint(ev.pos):
                flush_events()
                return


def lockbox_protected_min(coins_before: int, level: int | None = None) -> int:
    """Return the minimum coins kept by Lockbox for a single loss event."""
    lvl = LOCKBOX_MAX_LEVEL if level is None else int(level)
    lvl = max(0, min(lvl, LOCKBOX_MAX_LEVEL))
    if lvl <= 0:
        return 0
    rate = LOCKBOX_PROTECT_RATES[min(lvl - 1, len(LOCKBOX_PROTECT_RATES) - 1)]
    return int(math.floor(max(0, coins_before) * rate))


def clamp_coin_loss_with_lockbox(coins_before: int, raw_loss: int, level: int | None = None) -> int:
    """Cap a requested coin loss so Lockbox protection cannot be bypassed."""
    loss = max(0, int(raw_loss))
    floor = lockbox_protected_min(coins_before, level)
    if floor <= 0:
        return loss
    max_loss = max(0, coins_before - floor)
    return min(loss, max_loss)


def _atomic_write_json(path: str, data: dict) -> None:
    persistence_support.atomic_write_json(path, data)


def save_progress(current_level: int,
                  max_wave_reached: int | None = None,
                  pending_shop: bool = False):
    persistence_support.save_progress(_THIS_MODULE, current_level, max_wave_reached, pending_shop)


def capture_snapshot(game_state, player, enemies, current_level: int,
                     chosen_enemy_type: str = "basic", bullets: Optional[List['Bullet']] = None) -> dict:
    return persistence_support.capture_snapshot(
        _THIS_MODULE,
        game_state,
        player,
        enemies,
        current_level,
        chosen_enemy_type,
        bullets,
    )


def save_snapshot(snapshot: dict) -> None:
    persistence_support.save_snapshot(_THIS_MODULE, snapshot)


def load_save() -> Optional[dict]:
    return persistence_support.load_save(_THIS_MODULE)


def _clear_level_start_baseline():
    persistence_support.clear_level_start_baseline(_THIS_MODULE)


def _capture_level_start_baseline(level_idx: int, player: "Player", game_state: "GameState" | None = None):
    persistence_support.capture_level_start_baseline(_THIS_MODULE, level_idx, player, game_state)


def _restore_level_start_baseline(level_idx: int, player: "Player", game_state: "GameState"):
    persistence_support.restore_level_start_baseline(_THIS_MODULE, level_idx, player, game_state)


def has_save() -> bool:
    return persistence_support.has_save(_THIS_MODULE)


def clear_save() -> None:
    persistence_support.clear_save(_THIS_MODULE)


# ==================== UI Helpers ====================
def iso_equalized_step(dx: float, dy: float, speed: float) -> tuple[float, float]:
    """
    在等距投影下，将单位方向(dx,dy)缩放到“屏幕上恒定速度= speed 像素/帧（或/步）”。
    非等距则直接返回 dx*speed, dy*speed。
    """
    if not USE_ISO:
        return dx * speed, dy * speed
    half_w = ISO_CELL_W * 0.5
    half_h = ISO_CELL_H * 0.5
    # 这个方向对应的屏幕位移长度
    sx = (dx - dy) * half_w
    sy = (dx + dy) * half_h
    screen_mag = math.hypot(sx, sy) or 1.0
    scale = float(speed) * float(ISO_EQ_GAIN) / screen_mag
    return dx * scale, dy * scale


def bullet_radius_for_damage(dmg: int, meta=None) -> int:
    """
    Sub-linear growth by damage percentage, with a smooth cap.
    Base damage -> BULLET_RADIUS. As damage rises, the bonus eases in and
    asymptotically approaches BULLET_RADIUS_MAX.
    """
    m = _meta_state() if meta is None else meta
    base = float(m.get("base_dmg", BULLET_DAMAGE_ENEMY)) if hasattr(m, "get") else float(BULLET_DAMAGE_ENEMY)
    base = base or 1.0
    ratio = max(0.0, float(dmg) / base)
    if ratio <= 1.0:
        r = BULLET_RADIUS
    else:
        gain = ratio - 1.0  # % over base
        slow = gain / (1.0 + 0.75 * gain)  # slows early growth, < 1.0
        r = BULLET_RADIUS + (BULLET_RADIUS_MAX - BULLET_RADIUS) * slow
    return max(2, min(BULLET_RADIUS_MAX, int(round(r))))


def enemy_shot_radius_for_damage(dmg: int,
                                 base_radius: int = 4,
                                 cap: int = int(CELL_SIZE * 0.26),
                                 k: float = 0.035) -> int:
    """
    Smoothly map enemy shot damage → on-screen radius.
    - base_radius: default tiny shot
    - cap: max size (kept below player bullet cap to preserve readability)
    - k: growth rate (lower = slower growth)
    """
    dmg = max(0, int(dmg))
    r = base_radius + int((cap - base_radius) * (1.0 - math.exp(-k * dmg)))
    return max(base_radius, min(cap, r))

# === NEW: 等距相机偏移（基于玩家像素中心 → 网格中心 → 屏幕等距投影） ===
def calculate_iso_camera(player_x_px: float, player_y_px: float) -> tuple[int, int]:
    px_grid = player_x_px / CELL_SIZE
    py_grid = player_y_px / CELL_SIZE
    # 投到屏幕（不带 cam 偏移）
    pxs, pys = iso_world_to_screen(px_grid, py_grid, 0.0, 0.0, 0.0)
    camx = pxs - VIEW_W // 2
    camy = pys - (VIEW_H - INFO_BAR_HEIGHT) // 2
    return int(camx), int(camy)

HexCell, HexTransition, NeuroParticle, CometCorpse, CometBlast, AegisPulseRing = effects_runtime_support.install(
    _THIS_MODULE
)
(
    draw_button,
    hex_points_flat,
    build_hex_grid,
    ensure_hex_transition,
    ensure_hex_background,
    queue_menu_transition,
    run_pending_menu_transition,
    play_hex_transition,
    neuro_instruction_layout,
    draw_neuro_instruction,
    render_instruction_surface,
    ensure_neuro_background,
    _draw_intro_starfield,
    _draw_intro_datastreams,
    _draw_intro_holo_core,
    _draw_intro_scanlines,
    draw_intro_waves,
    draw_neuro_waves,
    draw_neuro_button,
    neuro_menu_layout,
    draw_neuro_info_column,
    draw_neuro_title_intro,
    draw_neuro_home_header,
    _draw_loading_screen,
) = menu_visuals_support.install(_THIS_MODULE)

# ==================== NEURO MUSIC VISUALIZATION ====================
_runtime_state()["_neuro_viz"] = NeuroMusicVisualizer()
_runtime_state()["_neuro_viz_loader"] = None
_runtime_state()["_neuro_viz_loader_path"] = None


def _get_neuro_viz() -> NeuroMusicVisualizer:
    runtime = _runtime_state()
    viz = runtime.get("_neuro_viz")
    if not isinstance(viz, NeuroMusicVisualizer):
        viz = NeuroMusicVisualizer()
        runtime["_neuro_viz"] = viz
    return viz


def _get_neuro_viz_loader() -> threading.Thread | None:
    return _runtime_state().get("_neuro_viz_loader")


def _set_neuro_viz_loader(loader: threading.Thread | None) -> None:
    _runtime_state()["_neuro_viz_loader"] = loader


def _get_neuro_viz_loader_path() -> str | None:
    return _runtime_state().get("_neuro_viz_loader_path")


def _set_neuro_viz_loader_path(path: str | None) -> None:
    _runtime_state()["_neuro_viz_loader_path"] = path
def compute_player_dps(p: "Player" | None, meta=None) -> float:
    # TODO
    # Add visual effect for bandit (growing circle around bandit)
    # Add same hint display for bosses (optional)
    # Add a exeution CG like scenefor bosses(slow time, whole scene become red in backgrounf and black in figures)
    m = _meta_state() if meta is None else meta
    if p is None:
        # 兜底：用 META 粗估
        base_dmg = BULLET_DAMAGE_ENEMY + (float(m.get("dmg", 0)) if hasattr(m, "get") else 0.0)
        # 使用玩家默认冷却推导攻速
        dummy = 1.0 / max(1e-6, FIRE_COOLDOWN / max(0.1, float(m.get("firerate_mult", 1.0)) if hasattr(m, "get") else 1.0))
        cc = float(m.get("crit", 0.0)) if hasattr(m, "get") else 0.0
        cm = float(CRIT_MULT_BASE)
        return base_dmg * dummy * (1.0 + max(0.0, min(1.0, cc)) * (cm - 1.0))
    dmg = float(getattr(p, "bullet_damage", BULLET_DAMAGE_ENEMY + (m.get("dmg", 0) if hasattr(m, "get") else 0)))
    sps = 1.0 / max(1e-6, p.fire_cooldown())  # 用 Player 的实际冷却（含攻速加成）
    cc = max(0.0, min(1.0, float(getattr(p, "crit_chance", 0.0))))
    cm = float(getattr(p, "crit_mult", CRIT_MULT_BASE))
    return dmg * sps * (1.0 + cc * (cm - 1.0))


def _skill_cast_range(skill_id: str, player) -> float:
    if skill_id == "blast":
        base_range = clamp_player_range(getattr(player, "range", PLAYER_RANGE_DEFAULT))
        return max(float(BLAST_CAST_RANGE), base_range)
    return float(TELEPORT_RANGE)


def _clamp_point_within_radius(px: float, py: float, tx: float, ty: float, limit: float) -> tuple[float, float]:
    dx, dy = tx - px, ty - py
    dist = math.hypot(dx, dy)
    if dist <= 1e-6 or dist <= limit:
        return float(tx), float(ty)
    scale = limit / dist
    return float(px + dx * scale), float(py + dy * scale)


def iso_screen_to_world_px(sx: float, sy: float, camx: float, camy: float) -> tuple[float, float]:
    """
    Inverse of iso_world_to_screen for wz=0.
    Returns world pixel coordinates (with INFO_BAR_HEIGHT baked in).
    """
    half_w = ISO_CELL_W * 0.5
    half_h = ISO_CELL_H * 0.5
    sxp = sx + camx
    syp = sy + camy - INFO_BAR_HEIGHT
    wx = (sxp / half_w + syp / half_h) * 0.5
    wy = (syp / half_h - sxp / half_w) * 0.5
    return float(wx * CELL_SIZE), float(wy * CELL_SIZE + INFO_BAR_HEIGHT)


def _apply_comet_blast_damage(player, game_state, enemies, target_pos) -> dict:
    """Apply AoE damage at the locked blast point; returns stats for VFX intensity."""
    tx, ty = target_pos
    r2 = float(BLAST_RADIUS) * float(BLAST_RADIUS)
    def _blast_falloff(dx: float, dy: float) -> float:
        """
        Damage scales from 200% at center → 80% at edge (linear with radius).
        """
        dist = math.hypot(dx, dy)
        t = max(0.0, min(1.0, dist / float(BLAST_RADIUS)))
        return 2.0 + (0.80 - 2.0) * t  # lerp(center=2.0, edge=0.80)
    hits = 0
    kills = 0
    for z in list(enemies):
        zx, zy = z.rect.center
        dx, dy = zx - tx, zy - ty
        if dx * dx + dy * dy <= r2:
            hits += 1
            hit_n = random.randint(BLAST_HITS_MIN, BLAST_HITS_MAX)
            falloff = _blast_falloff(dx, dy)
            dmg_per = max(1, int(getattr(player, "bullet_damage", BULLET_DAMAGE_ENEMY) * BLAST_DMG_MULT * falloff))
            total = hit_n * dmg_per
            before = int(getattr(z, "hp", 0))
            z.hp = max(0, before - total)
            z._comet_flash = max(0.2, float(getattr(z, "_comet_flash", 0.0)))
            z._comet_shake = max(0.25, float(getattr(z, "_comet_shake", 0.0)))
            game_state.add_damage_text(zx, zy - 10, total, crit=False, kind="skill")
            if z.hp <= 0:
                kills += 1
                z._comet_death = True
    # Damage destructible obstacles in the blast
    for gp, ob in list(getattr(game_state, "obstacles", {}).items()):
        if getattr(ob, "type", "") != "Destructible":
            continue
        if getattr(ob, "health", None) is None or ob.health <= 0:
            continue
        rect = ob.rect
        cx = min(max(tx, rect.left), rect.right)
        cy = min(max(ty, rect.top), rect.bottom)
        dx = cx - tx
        dy = cy - ty
        if dx * dx + dy * dy > r2:
            continue
        hit_n = random.randint(BLAST_HITS_MIN, BLAST_HITS_MAX)
        falloff = _blast_falloff(dx, dy)
        dmg_per = max(1, int(getattr(player, "bullet_damage", BULLET_DAMAGE_ENEMY) * BLAST_DMG_MULT * falloff))
        total = hit_n * dmg_per
        ob.health = (ob.health or 0) - total
        if ob.health <= 0:
            bx, by = rect.centerx, rect.centery
            del game_state.obstacles[gp]
            if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                game_state.spawn_spoils(bx, by, 1)
            if player:
                player.add_xp(XP_PLAYER_BLOCK)
    game_state.add_damage_text(int(tx), int(ty), "BLAST", crit=True, kind="skill")
    # Camera shake intensity falls with distance to player
    if player is not None and hasattr(game_state, "add_cam_shake"):
        px, py = player.rect.center
        dist = math.hypot(px - tx, py - ty)
        near = max(0.0, 1.0 - dist / max(1.0, BLAST_CAST_RANGE * 1.25))
        game_state.add_cam_shake(8.0 + 18.0 * near, duration=0.30 + 0.10 * near)
    return {"hits": hits, "kills": kills}


def _cast_fixed_point_blast(player, game_state, enemies, target_pos) -> bool:
    """Q-skill: lock a target and drop a comet; damage is applied on impact."""
    if player is None or game_state is None or target_pos is None:
        return False
    tx, ty = target_pos
    # Spawn comet off-screen (left/right) and arc into the target
    side = random.choice([-1, 1])
    start_x = tx + side * (VIEW_W * 0.7 + BLAST_RADIUS * 0.5)
    start_y = ty - VIEW_H * 0.8
    travel = random.uniform(0.55, 0.80)
    game_state.spawn_comet_blast(
        (tx, ty),
        (start_x, start_y),
        travel,
        impact_cb=lambda: _apply_comet_blast_damage(player, game_state, enemies, (tx, ty))
    )
    return True


def _teleport_player_to(player, game_state, target_pos) -> bool:
    """E-skill: blink within TELEPORT_RANGE, ignoring walls but not landing on obstacles."""
    if player is None or game_state is None or target_pos is None:
        return False
    tx, ty = target_pos
    # keep within screen bounds
    half = max(1, player.size // 2)
    tx = min(max(half, int(tx)), VIEW_W - half)
    ty = min(max(INFO_BAR_HEIGHT + half, int(ty)), VIEW_H - half)
    new_rect = player.rect.copy()
    new_rect.center = (tx, ty)
    for ob in game_state.obstacles.values():
        if new_rect.colliderect(ob.rect):
            return False  # cannot land on an obstacle
    player.rect = new_rect
    player.x = float(player.rect.x)
    player.y = float(player.rect.y - INFO_BAR_HEIGHT)
    _play_teleport_sfx()
    return True


def _compute_skill_target(player, game_state, mouse_pos, skill_id: str):
    """Return (tx, ty, valid, camx, camy) where tx/ty are clamped world pixels."""
    px, py = player.rect.center
    # camera tracks current player position so the mouse mapping stays accurate
    camx, camy = calculate_iso_camera(player.rect.centerx, player.rect.centery)
    tx, ty = iso_screen_to_world_px(mouse_pos[0], mouse_pos[1], camx, camy)
    cast_range = _skill_cast_range(skill_id, player)
    tx, ty = _clamp_point_within_radius(px, py, tx, ty, cast_range)
    valid = True
    if skill_id == "teleport":
        new_rect = player.rect.copy()
        new_rect.center = (int(tx), int(ty))
        for ob in game_state.obstacles.values():
            if new_rect.colliderect(ob.rect):
                valid = False
                break
    return (float(tx), float(ty), bool(valid), camx, camy)


def _update_skill_target(player, game_state):
    """Refresh targeting point/validity based on current mouse position."""
    if getattr(player, "targeting_skill", None) is None:
        return
    skill_id = player.targeting_skill
    mx, my = pygame.mouse.get_pos()
    tx, ty, valid, camx, camy = _compute_skill_target(player, game_state, (mx, my), skill_id)
    player.skill_target_pos = (tx, ty)
    player.skill_target_valid = bool(valid)
    player._last_cam_for_skill = (camx, camy)


def _draw_skill_overlay(surface, player, camx, camy):
    """Draw targeting rings; should be called after world draw so obstacles don't cover it."""
    if getattr(player, "targeting_skill", None):
        skill = player.targeting_skill
        px, py = player.rect.center
        cast_range = _skill_cast_range(skill, player)
        ring_col = (255, 140, 70) if skill == "blast" else (90, 190, 255)
        draw_iso_ground_ellipse(surface, px, py, cast_range, ring_col, 60, camx, camy, fill=False, width=3)
        tx, ty = getattr(player, "skill_target_pos", (px, py))
        valid = bool(getattr(player, "skill_target_valid", False))
        col_valid = (255, 140, 70) if skill == "blast" else (80, 210, 255)
        col_invalid = (230, 60, 60)
        col = col_valid if valid else col_invalid
        if skill == "blast":
            # Seed-of-life style: 1 center + 6 orbiting circles (60 deg apart), rotated over time
            t = pygame.time.get_ticks() * 0.001
            rot = t * 0.6  # radians
            orbit_r = BLAST_RADIUS * 0.5
            # outer ring
            draw_iso_ground_ellipse(surface, tx, ty, BLAST_RADIUS, col, 90 if valid else 50, camx, camy, fill=False,
                                    width=4)
            # center circle
            draw_iso_ground_ellipse(surface, tx, ty, orbit_r, col, 80 if valid else 40, camx, camy, fill=False,
                                    width=3)
            # six orbiting circles at 60° intervals
            for i in range(6):
                ang = rot + math.tau * i / 6.0
                ox = tx + math.cos(ang) * orbit_r
                oy = ty + math.sin(ang) * orbit_r
                draw_iso_ground_ellipse(surface, ox, oy, orbit_r, col, 80 if valid else 40, camx, camy, fill=False,
                                        width=3)
        else:
            draw_iso_ground_ellipse(surface, tx, ty, max(20, player.size), col, 80 if valid else 50, camx, camy,
                                    fill=False, width=4)



def animate_menu_exit(screen: pygame.Surface, snapshot: pygame.Surface, duration: int = 450):
    """Slide/fade the menu upward before entering the run."""
    clock = pygame.time.Clock()
    start = pygame.time.get_ticks()
    while True:
        elapsed = pygame.time.get_ticks() - start
        progress = min(1.0, elapsed / max(1, duration))
        dy = int(-VIEW_H * 0.35 * progress)
        alpha = int(255 * (1.0 - progress))
        frame = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
        temp = snapshot.copy()
        temp.set_alpha(alpha)
        frame.blit(temp, (0, dy))
        screen.fill((0, 0, 0))
        screen.blit(frame, (0, 0))
        pygame.display.flip()
        if progress >= 1.0:
            break
        clock.tick(60)


async def run_neuro_intro(screen: pygame.Surface):
    return await menu_flow_support.run_neuro_intro(_THIS_MODULE, screen)


def render_start_menu_surface(saved_exists: bool):
    return menu_flow_support.render_start_menu_surface(_THIS_MODULE, saved_exists)


async def show_start_menu(screen, *, skip_intro: bool = False):
    return await menu_flow_support.show_start_menu(_THIS_MODULE, screen, skip_intro=skip_intro)


def show_instruction(screen):
    return menu_flow_support.show_instruction(_THIS_MODULE, screen)


async def show_instruction_web(screen):
    return await menu_flow_support.show_instruction_web(_THIS_MODULE, screen)


async def show_settings_popup_web(screen, background_surf):
    return await screens_support.show_settings_popup_web(_THIS_MODULE, screen, background_surf)


async def show_fail_screen(screen, background_surf):
    return await screens_support.show_fail_screen(_THIS_MODULE, screen, background_surf)


async def show_success_screen(screen, background_surf, reward_choices):
    return await screens_support.show_success_screen(_THIS_MODULE, screen, background_surf, reward_choices)


def show_pause_menu(screen, background_surf):
    return menu_flow_support.show_pause_menu(_THIS_MODULE, screen, background_surf)


def _apply_levelup_choice(player, key: str):
    """Apply the chosen buff immediately AND persist in META so it carries over."""
    meta = _meta_state()
    if key == "dmg":
        meta["dmg"] = meta.get("dmg", 0) + 1
        player.bullet_damage += 1
    elif key == "firerate":
        meta["firerate_mult"] = float(meta.get("firerate_mult", 1.0)) * 1.05
        player.fire_rate_mult *= 1.05
    elif key == "range":
        base_range = clamp_player_range(meta.get("base_range", PLAYER_RANGE_DEFAULT))
        meta["base_range"] = base_range  # sanitize any persisted value
        new_mult = float(meta.get("range_mult", 1.0)) * 1.10
        max_mult = PLAYER_RANGE_MAX / max(1.0, base_range)
        meta["range_mult"] = min(new_mult, max_mult)
        # player.range is base * mult (clamped to the hard cap)
        if player is not None:
            player.range_base = clamp_player_range(getattr(player, "range_base", base_range))
            player.range = compute_player_range(player.range_base, meta["range_mult"])
    elif key == "speed":
        meta["speed_mult"] = float(meta.get("speed_mult", 1.0)) * 1.05
        base_spd = float(meta.get("base_speed", 2.6))
        # live-apply to player
        if player is not None:
            player.speed = min(PLAYER_SPEED_CAP, max(1.0, base_spd * meta["speed_mult"]))
    elif key == "maxhp":
        meta["maxhp"] = int(meta.get("maxhp", 0)) + 5
        player.max_hp += 5
        player.hp = min(player.max_hp, player.hp + 10)  # small heal like the mock
    elif key == "crit":
        meta["crit"] = min(0.75, float(meta.get("crit", 0.0)) + 0.02)
        if player is not None:
            player.crit_chance = min(0.75, float(getattr(player, "crit_chance", 0.0)) + 0.02)


def show_levelup_overlay(screen, background_surf, player):
    """
    Paused overlay: dim the current frame and show 4 random perk cards (2x2 grid) in the center.
    Returns the chosen perk key (e.g., "dmg", "firerate", "range", "speed", "maxhp").
    """
    import random
    import pygame
    W, H = screen.get_size()
    clock = pygame.time.Clock()
    # --- Perk pool (keys must match _apply_levelup_choice) ---
    pool = [
        {"key": "dmg", "title": "+1 Damage", "desc": "Increase your bullet damage by 1."},
        {"key": "firerate", "title": "+5% Fire Rate", "desc": "Shoot slightly faster (multiplicative)."},
        {"key": "range", "title": "+10% Range", "desc": "Longer effective range for shots."},
        {"key": "speed", "title": "+5% Speed", "desc": "Move faster."},
        {"key": "maxhp", "title": "+5 Max HP", "desc": "Increase max HP and heal 10."},
        {"key": "crit", "title": "+2% Crit", "desc": "Increase critical hit chance slightly"},
    ]
    cards = random.sample(pool, k=min(4, len(pool)))
    # Apply stat caps: once at or above caps, stop offering those perks
    speed_cap = PLAYER_SPEED_CAP
    if speed_cap is not None and player is not None:
        try:
            cur_spd = float(getattr(player, "speed", 0.0))
            if cur_spd >= float(speed_cap) - 1e-6:
                pool = [p for p in pool if p.get("key") != "speed"]
        except Exception:
            pass
    # Crit cap: use the same hard cap as level-up logic (75%)
    crit_cap = 0.75
    if player is not None:
        try:
            cur_crit = float(getattr(player, "crit_chance", 0.0))
            if cur_crit >= crit_cap - 1e-6:
                pool = [p for p in pool if p.get("key") != "crit"]
        except Exception:
            pass
    if not pool:
        # Fallback safety: always keep at least damage & max HP
        pool = [
            {"key": "dmg", "title": "+1 Damage", "desc": "Increase your bullet damage by 1."},
            {"key": "maxhp", "title": "+5 Max HP", "desc": "Increase max HP and heal 10."},
            {"key": "firerate", "title": "+5% Fire Rate", "desc": "Shoot slightly faster (multiplicative)."},
            {"key": "range", "title": "+10% Range", "desc": "Longer effective range for shots."},
        ]
    cards = random.sample(pool, k=min(4, len(pool)))
    # --- Fonts ---
    title_font = pygame.font.SysFont(None, 64)
    head_font = pygame.font.SysFont(None, 30)
    body_font = pygame.font.SysFont(None, 24)
    # --- Layout (2×2 grid) ---
    card_w, card_h = 420, 140
    gap_x, gap_y = 32, 28
    total_w = 2 * card_w + gap_x
    total_h = 2 * card_h + gap_y
    base_x = (W - total_w) // 2
    base_y = (H - total_h) // 2 + 10
    rects = []
    for i in range(len(cards)):
        cx = base_x + (i % 2) * (card_w + gap_x)
        cy = base_y + (i // 2) * (card_h + gap_y)
        rects.append(pygame.Rect(cx, cy, card_w, card_h))
    # --- Prebuild dim mask ---
    dim = pygame.Surface((W, H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 140))  # similar to pause overlay darkness
    title = title_font.render("LEVEL UP — CHOOSE ONE", True, (235, 235, 235))
    title_rect = title.get_rect(center=(W // 2, base_y - 48))
    hover = -1
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return None
            if e.type == pygame.KEYDOWN:
                # allow quick pick via 1..4
                if e.key in (pygame.K_1, pygame.K_KP_1) and len(cards) >= 1: return cards[0]["key"]
                if e.key in (pygame.K_2, pygame.K_KP_2) and len(cards) >= 2: return cards[1]["key"]
                if e.key in (pygame.K_3, pygame.K_KP_3) and len(cards) >= 3: return cards[2]["key"]
                if e.key in (pygame.K_4, pygame.K_KP_4) and len(cards) >= 4: return cards[3]["key"]
                # Esc
                if e.key == pygame.K_ESCAPE:
                    # Ignore Esc while level-up menu is open
                    continue
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and hover != -1:
                return cards[hover]["key"]
        mx, my = pygame.mouse.get_pos()
        hover = -1
        for i, r in enumerate(rects):
            if r.collidepoint(mx, my):
                hover = i
                break
        # --- draw ---
        screen.blit(background_surf, (0, 0))
        screen.blit(dim, (0, 0))
        screen.blit(title, title_rect)
        for i, (r, c) in enumerate(zip(rects, cards)):
            # soft shadow
            shadow = r.inflate(18, 18)
            pygame.draw.rect(screen, (0, 0, 0, 90), shadow, border_radius=18)
            # panel
            pygame.draw.rect(screen, (35, 36, 38), r, border_radius=14)
            # border: brighter on hover
            border_col = (200, 200, 200) if i == hover else (120, 120, 120)
            pygame.draw.rect(screen, border_col, r, width=2, border_radius=14)
            # little index tag (1–4)
            idx_lbl = head_font.render(str(i + 1), True, (210, 210, 210))
            screen.blit(idx_lbl, idx_lbl.get_rect(midleft=(r.left + 14, r.top + 18)))
            # title
            title_surf = head_font.render(c["title"], True, (230, 230, 230))
            screen.blit(title_surf, title_surf.get_rect(topleft=(r.left + 44, r.top + 12)))
            # description (wrap lightly)
            desc = c["desc"]
            d_surf = body_font.render(desc, True, (195, 195, 195))
            screen.blit(d_surf, d_surf.get_rect(topleft=(r.left + 20, r.top + 56)))
        pygame.display.flip()
        clock.tick(60)


def levelup_modal(screen, bg_surface, clock, time_left, player):
    """
    Wrapper that shows the picker, keeps the timer frozen, and
    resets the main clock baseline so dt won't include the pause time.
    """
    key = show_levelup_overlay(screen, bg_surface, player)
    if key:
        _apply_levelup_choice(player, key)  # <-- APPLY the chosen buff to LIVE player + META
    _runtime_state()["_time_left_runtime"] = time_left
    clock.tick(60)  # reset dt baseline so gameplay doesn't jump after modal
    flush_events()
    return time_left


def show_settings_popup(screen, background_surf):
    return screens_support.show_settings_popup(_THIS_MODULE, screen, background_surf)


def show_shop_screen(screen) -> Optional[str]:
    return shop_ui_support.show_shop_screen(_THIS_MODULE, screen)


def show_biome_picker_in_shop(screen) -> str:
    return shop_ui_support.show_biome_picker_in_shop(_THIS_MODULE, screen)


def is_boss_level(level_idx_zero_based: int) -> bool:
    return spawn_logic_support.is_boss_level(_THIS_MODULE, level_idx_zero_based)


def budget_for_level(level_idx_zero_based: int) -> int:
    return spawn_logic_support.budget_for_level(_THIS_MODULE, level_idx_zero_based)


def _pick_type_by_budget(rem: int, level_idx_zero_based: int) -> Optional[str]:
    return spawn_logic_support.pick_type_by_budget(_THIS_MODULE, rem, level_idx_zero_based)


def _spawn_positions(game_state: "GameState", player: "Player", enemies: List["Enemy"], want: int) -> List[
    Tuple[int, int]]:
    return spawn_logic_support.spawn_positions(_THIS_MODULE, game_state, player, enemies, want)


def promote_to_boss(z: "Enemy"):
    return spawn_logic_support.promote_to_boss(_THIS_MODULE, z)


def spawn_wave_with_budget(game_state: "GameState",
                           player: "Player",
                           current_level: int,
                           wave_index: int,
                           enemies: List["Enemy"],
                           cap: int) -> int:
    return spawn_logic_support.spawn_wave_with_budget(
        _THIS_MODULE,
        game_state,
        player,
        current_level,
        wave_index,
        enemies,
        cap,
    )


def trigger_twin_enrage(dead_boss, enemies, game_state):
    """If a bonded twin dies, power up the partner exactly once."""
    if not getattr(dead_boss, "is_boss", False):
        return
    partner = _find_twin_partner(dead_boss, enemies)
    if not partner or getattr(partner, "hp", 0) <= 0:
        return
    if getattr(partner, "_twin_powered", False):
        return
    enraged_now = False
    if hasattr(partner, "on_twin_partner_death"):
        partner.on_twin_partner_death()
        enraged_now = True
    else:
        partner.hp = int(getattr(partner, "max_hp", partner.hp))
        partner.attack = int(partner.attack * TWIN_ENRAGE_ATK_MULT)
        partner.speed = int(partner.speed + TWIN_ENRAGE_SPD_ADD)
        partner._twin_powered = True
        partner.is_enraged = True
        enraged_now = True
        try:
            partner.boss_name = (getattr(partner, "boss_name", "BOSS") + " [ENRAGED]")
        except Exception:
            pass
    if enraged_now and getattr(partner, "type", "") == "boss_mem":
        enraged_color = ENEMY_COLORS.get("boss_mem_enraged", BOSS_MEM_ENRAGED_COLOR)
        partner._current_color = enraged_color
        partner.color = enraged_color
    game_state.add_damage_text(
        partner.rect.centerx,
        partner.rect.top - 10,
        "ENRAGE!",
        crit=True,
        kind="hp",
    )


# ==================== 数据结构 ====================
Graph, Obstacle, FogLantern, MainBlock, Item, Player = entity_core_support.install(_THIS_MODULE)


# --- module-level helper: split parent into 3 splinterlings ---
def spawn_splinter_children(parent: "Enemy",
                            enemies: list,
                            game_state: "GameState",
                            level_idx: int,
                            wave_index: int):
    gx = int((parent.x + parent.size * 0.5) // CELL_SIZE)
    gy = int((parent.y + parent.size) // CELL_SIZE)
    neighbors = [(gx + dx, gy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if not (dx == 0 and dy == 0)]
    random.shuffle(neighbors)
    child_hp = max(1, int(parent.max_hp * SPLINTER_CHILD_HP_RATIO))
    child_atk = max(1, int(parent.attack * SPLINTERLING_ATK_RATIO))
    child_speed = min(ENEMY_SPEED_MAX, int(parent.speed) + int(SPLINTERLING_SPD_ADD))
    spawned = 0
    for nx, ny in neighbors:
        if spawned >= SPLINTER_CHILD_COUNT:
            break
        if not (0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE):
            continue
        if (nx, ny) in game_state.obstacles:
            continue
        occupied = False
        for z in enemies:
            zx = int((z.x + z.size * 0.5) // CELL_SIZE)
            zy = int((z.y + z.size * 0.5) // CELL_SIZE)
            if zx == nx and zy == ny:
                occupied = True
                break
        if occupied:
            continue
        child = Enemy((nx, ny), attack=child_atk, speed=child_speed, ztype="splinterling", hp=child_hp)
        child._can_split = False
        child._split_done = True
        enemies.append(child)
        spawned += 1
    return spawned


AfterImageGhost, Enemy = enemy_core_support.install(_THIS_MODULE)


MemoryDevourerBoss, MistClone, MistweaverBoss = enemy_subclasses_support.install(_THIS_MODULE)



Bullet = player_projectiles_support.install(_THIS_MODULE)
AutoTurret, StationaryTurret, StationaryTurretObstacle = turrets_support.install(_THIS_MODULE)
Spoil, HealPickup = pickups_support.install(_THIS_MODULE)
SpatialHash, TornadoEntity = world_runtime_support.install(_THIS_MODULE)


AcidPool, TelegraphCircle = hazards_support.install(_THIS_MODULE)
GroundSpike, CuringPaintFootprint, PaintTile = paint_support.install(_THIS_MODULE)


# ==================== NEW HIGH-FIDELITY COMET SYSTEM ====================

_effect_sfx_cache: dict[str, pygame.mixer.Sound | bool] = {}


def _init_effect_mixer():
    """Ensure mixer is ready before attempting to play SFX."""
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
    except Exception:
        pass


def _load_effect_sound(filename: str):
    """Look up an effect sound under assets/Effect (fallback to legacy paths)."""
    _init_effect_mixer()
    if filename in _effect_sfx_cache:
        return _effect_sfx_cache[filename]
    name_variants = _audio_path_variants(filename)
    candidates: list[str] = []
    for n in name_variants:
        candidates.extend(_asset_candidates("Effect", n))
        candidates.extend(_asset_candidates(n))  # legacy fallback
    _effect_sfx_cache[filename] = False
    for p in candidates:
        if p and os.path.exists(p):
            try:
                _effect_sfx_cache[filename] = pygame.mixer.Sound(p)
                break
            except Exception:
                _effect_sfx_cache[filename] = False
    return _effect_sfx_cache[filename]


def _play_effect_sfx(filename: str):
    """Play an effect sound respecting the global FX volume slider."""
    snd = _load_effect_sound(filename)
    if not snd:
        return
    try:
        snd.set_volume(max(0.0, min(1.0, float(FX_VOLUME) / 100.0)))
        snd.play()
    except Exception:
        pass


def _play_comet_sfx():
    """Play the comet impact SFX if present."""
    _play_effect_sfx("comet.wav")


def _play_teleport_sfx():
    """Play the teleport confirm SFX if present."""
    _play_effect_sfx("teleport.wav")


EnemyShot, MistShot, DamageText = enemy_projectiles_support.install(_THIS_MODULE)
GameSound = audio_runtime_support.install(_THIS_MODULE)


# ==================== 算法函数 ====================
def sign(v): return 1 if v > 0 else (-1 if v < 0 else 0)


# simple movement helper: use iso equalization only when using ISO view
def chase_step(ux: float, uy: float, speed: float):
    return iso_equalized_step(ux, uy, speed) if USE_ISO else (ux * speed, uy * speed)

(
    _expanded_block_mask,
    _reachable_to_edge,
    ensure_passage_budget,
    collide_and_slide_circle,
    heuristic,
    a_star_search,
    is_not_edge,
    get_level_config,
    reconstruct_path,
    generate_game_entities,
    build_graph,
    build_flow_field,
    crush_blocks_in_rect,
) = worldgen_pathing_support.install(_THIS_MODULE)


def resize_world_to_view():
    """Expand GRID_SIZE so the simulated world covers the whole visible area."""
    global GRID_SIZE, WINDOW_SIZE, TOTAL_HEIGHT
    # how many cells are visible horizontally/vertically
    cols_needed = math.ceil(VIEW_W / CELL_SIZE)
    rows_needed = math.ceil((VIEW_H - INFO_BAR_HEIGHT) / CELL_SIZE)
    # keep using a square grid; pick the max so both axes are covered
    new_size = max(GRID_SIZE, cols_needed, rows_needed)
    if new_size != GRID_SIZE:
        GRID_SIZE = new_size
        WINDOW_SIZE = GRID_SIZE * CELL_SIZE
        TOTAL_HEIGHT = WINDOW_SIZE + INFO_BAR_HEIGHT


def _web_level_config(config: dict) -> dict:
    if not IS_WEB:
        return config
    web_cfg = dict(config)
    obstacle_cap = 8 if WEB_DEMO else 10
    item_cap = 2 if WEB_DEMO else 2
    enemy_seed_cap = 1 if WEB_DEMO else 1
    web_cfg["obstacle_count"] = min(int(web_cfg.get("obstacle_count", 0)), obstacle_cap)
    web_cfg["item_count"] = min(int(web_cfg.get("item_count", 0)), item_cap)
    web_cfg["enemy_count"] = min(int(web_cfg.get("enemy_count", 0)), enemy_seed_cap)
    return web_cfg


def play_bounds_for_circle(radius: float) -> tuple[float, float, float, float]:
    """返回【圆心】在当前关卡内允许的最小/最大坐标 (x_min, y_min, x_max, y_max)。"""
    w = GRID_SIZE * CELL_SIZE  # 地图像素宽
    h = GRID_SIZE * CELL_SIZE  # 地图像素高（不包含顶部信息栏）
    x_min = radius
    x_max = w - radius
    y_min = INFO_BAR_HEIGHT + radius
    y_max = INFO_BAR_HEIGHT + h - radius
    return x_min, y_min, x_max, y_max


def iso_world_to_screen(wx: float, wy: float, wz: float = 0.0,
                        camx: float = 0.0, camy: float = 0.0) -> tuple[int, int]:
    """
    把【世界格坐标】(wx, wy, wz) 投到屏幕像素坐标。
    - wx, wy 以“格”为单位（像素请先 / CELL_SIZE 再传）
    - wz 额外竖向抬高（像素，向上为正），例如墙体高度/跳跃
    - camx, camy 是等距相机的屏幕偏移（像素）
    注意：UI 绝对不传 cam 偏移；UI 始终使用屏幕绝对坐标。
    """
    half_w = ISO_CELL_W * 0.5
    half_h = ISO_CELL_H * 0.5
    sx = (wx - wy) * half_w - camx
    sy = (wx + wy) * half_h - wz - camy + INFO_BAR_HEIGHT
    return int(sx), int(sy)


def iso_tile_points(gx: int, gy: int, camx: float, camy: float) -> list[tuple[int, int]]:
    """返回等距地砖菱形四个顶点（上、右、下、左）。"""
    cx, cy = iso_world_to_screen(gx, gy, 0, camx, camy)
    return [
        (cx, cy),
        (cx + ISO_CELL_W // 2, cy + ISO_CELL_H // 2),
        (cx, cy + ISO_CELL_H),
        (cx - ISO_CELL_W // 2, cy + ISO_CELL_H // 2),
    ]


def draw_iso_tile(surface, gx, gy, color, camx, camy, border=0):
    pts = iso_tile_points(gx, gy, camx, camy)
    pygame.draw.polygon(surface, color, pts, border)


def draw_iso_prism(surface, gx, gy, top_color, camx, camy, wall_h=ISO_WALL_Z):
    """
    画“墙砖”：带顶面和两个侧面（简单着色），用来替代 Destructible/Indestructible 方块。
    """
    top = iso_tile_points(gx, gy, camx, camy)
    # 侧面（右侧、左侧）
    r = [top[1], (top[1][0], top[1][1] + wall_h),
         (top[2][0], top[2][1] + wall_h), top[2]]
    l = [top[3], top[2], (top[2][0], top[2][1] + wall_h), (top[3][0], top[3][1] + wall_h)]
    # 颜色：顶面亮，右侧中，左侧暗
    c_top = top_color
    c_r = tuple(max(0, int(c * 0.78)) for c in top_color)
    c_l = tuple(max(0, int(c * 0.58)) for c in top_color)
    pygame.draw.polygon(surface, c_l, l)
    pygame.draw.polygon(surface, c_r, r)
    pygame.draw.polygon(surface, c_top, top)


# === ISO ground ellipse helpers ===
def iso_circle_radii_screen(r_px: float) -> tuple[int, int]:
    """
    把“世界平面半径 r_px（像素）”转换成屏幕上的椭圆半径 (rx, ry)（像素）。
    推导：沿屏幕水平轴的世界方向为 (dx,dy)=(t,-t)，垂直轴为 (t,t)，
    由 iso_world_to_screen 的线性部分可得：
      rx = r * ISO_CELL_W / (sqrt(2) * CELL_SIZE)
      ry = r * ISO_CELL_H / (sqrt(2) * CELL_SIZE)
    """
    rx = int(r_px * (ISO_CELL_W / (math.sqrt(2) * CELL_SIZE)))
    ry = int(r_px * (ISO_CELL_H / (math.sqrt(2) * CELL_SIZE)))
    return max(1, rx), max(1, ry)


def draw_iso_ground_ellipse(surface: pygame.Surface, x_px: float, y_px: float,
                            r_px: float, color: tuple, alpha: int,
                            camx: float, camy: float,
                            *, fill: bool = True, width: int = 2) -> None:
    """
    在地面(等距)绘制一个椭圆：中心传入世界像素坐标 (x_px, y_px)，半径 r_px（世界像素）。
    color=(R,G,B)，alpha=0..255。
    """
    # 世界“格”单位（iso_world_to_screen 需要传格坐标）
    wx = x_px / CELL_SIZE
    wy = (y_px - INFO_BAR_HEIGHT) / CELL_SIZE
    cx, cy = iso_world_to_screen(wx, wy, 0, camx, camy)
    rx, ry = iso_circle_radii_screen(float(r_px))
    # 用一张带透明通道的小画布来画椭圆，再贴到主画面
    surf = pygame.Surface((rx * 2 + 2, ry * 2 + 2), pygame.SRCALPHA)
    rgba = (int(color[0]), int(color[1]), int(color[2]), int(alpha))
    rect = pygame.Rect(1, 1, rx * 2, ry * 2)
    if fill:
        pygame.draw.ellipse(surf, rgba, rect)
    else:
        pygame.draw.ellipse(surf, rgba, rect, max(1, int(width)))
    surface.blit(surf, (cx - rx - 1, cy - ry - 1))


def _draw_poly_alpha(surface: pygame.Surface, color_rgba: tuple[int, int, int, int],
                     points: list[tuple[float, float]]) -> None:
    if not points:
        return
    min_x = min(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_x = max(p[0] for p in points)
    max_y = max(p[1] for p in points)
    w = int(max_x - min_x) + 4
    h = int(max_y - min_y) + 4
    if w <= 2 or h <= 2:
        return
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    shifted = [(p[0] - min_x + 2, p[1] - min_y + 2) for p in points]
    pygame.draw.polygon(surf, color_rgba, shifted)
    surface.blit(surf, (int(min_x - 2), int(min_y - 2)))


def _draw_polyline_alpha(surface: pygame.Surface, color_rgba: tuple[int, int, int, int],
                         points: list[tuple[float, float]], width: int = 2) -> None:
    if not points:
        return
    min_x = min(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_x = max(p[0] for p in points)
    max_y = max(p[1] for p in points)
    w = int(max_x - min_x) + 4
    h = int(max_y - min_y) + 4
    if w <= 2 or h <= 2:
        return
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    shifted = [(p[0] - min_x + 2, p[1] - min_y + 2) for p in points]
    pygame.draw.lines(surf, color_rgba, True, shifted, max(1, int(width)))
    surface.blit(surf, (int(min_x - 2), int(min_y - 2)))


def iso_world_px_to_screen(x_px: float, y_px: float, camx: float, camy: float, z_px: float = 0.0) -> tuple[int, int]:
    wx = x_px / CELL_SIZE
    wy = (y_px - INFO_BAR_HEIGHT) / CELL_SIZE
    return iso_world_to_screen(wx, wy, z_px, camx, camy)


def _lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, float(t)))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _scale_color(color: tuple[int, int, int], scale: float) -> tuple[int, int, int]:
    s = max(0.0, float(scale))
    return (
        max(0, min(255, int(color[0] * s))),
        max(0, min(255, int(color[1] * s))),
        max(0, min(255, int(color[2] * s))),
    )


def _curing_paint_blob_points(paint: "CuringPaintFootprint", radius: float,
                              camx: float, camy: float, t: float,
                              wiggle: float) -> list[tuple[int, int]]:
    points = []
    noise_list = getattr(paint, "_blob_noise", None)
    phase_list = getattr(paint, "_blob_phase", None)
    count = len(noise_list) if noise_list else CURING_PAINT_BLOB_POINTS
    if not noise_list:
        noise_list = [1.0] * int(count)
    if not phase_list:
        phase_list = [0.0] * int(count)
    rot = float(getattr(paint, "_blob_rot", 0.0))
    for i in range(int(count)):
        ang = rot + math.tau * i / float(count)
        noise = float(noise_list[i % len(noise_list)])
        phase = float(phase_list[i % len(phase_list)])
        jiggle = 1.0 + wiggle * math.sin(t * CURING_PAINT_WIGGLE_SPEED + phase)
        r = radius * noise * jiggle
        wx = paint.x + math.cos(ang) * r
        wy = paint.y + math.sin(ang) * r
        points.append(iso_world_px_to_screen(wx, wy, camx, camy, 0.0))
    return points


def _curing_paint_static_color_key(paint: "CuringPaintFootprint") -> tuple[int, int, int]:
    base_col = getattr(paint, "base_color", CURING_PAINT_FILL_COLOR)
    return (int(base_col[0]), int(base_col[1]), int(base_col[2]))


def _build_curing_paint_static_cache(paint: "CuringPaintFootprint") -> dict | None:
    life0 = max(0.001, float(getattr(paint, "life0", paint.t)))
    t_left = max(0.0, float(getattr(paint, "t", 0.0)))
    if t_left <= 0.0:
        return None
    intensity = max(0.0, min(1.0, t_left / life0))
    if intensity <= 0.0:
        return None
    age = max(0.0, life0 - t_left)
    t = getattr(paint, "_static_t", None)
    if t is None:
        t = pygame.time.get_ticks() * 0.001
        paint._static_t = t
    if CURING_PAINT_SPLASH_TIME > 0.0 and age < CURING_PAINT_SPLASH_TIME:
        prog = age / CURING_PAINT_SPLASH_TIME
        scale = CURING_PAINT_SPLASH_SCALE_START + prog * (
            CURING_PAINT_SPLASH_SCALE_PEAK - CURING_PAINT_SPLASH_SCALE_START
        )
    elif CURING_PAINT_SPLASH_SETTLE > 0.0 and age < CURING_PAINT_SPLASH_TIME + CURING_PAINT_SPLASH_SETTLE:
        settle = (age - CURING_PAINT_SPLASH_TIME) / CURING_PAINT_SPLASH_SETTLE
        scale = CURING_PAINT_SPLASH_SCALE_PEAK - (CURING_PAINT_SPLASH_SCALE_PEAK - 1.0) * settle
    else:
        scale = 1.0
    pulse = 0.84 + 0.16 * math.sin(t * 3.2 + (paint.x + paint.y) * 0.012)
    shimmer = 0.74 + 0.26 * math.sin(t * 6.0 + (paint.x - paint.y) * 0.02)
    base_r = float(paint.r) * scale
    wiggle = CURING_PAINT_WIGGLE_STRENGTH * intensity * (0.6 + 0.4 * shimmer)
    base_col = _curing_paint_static_color_key(paint)
    brightness = CURING_PAINT_BRIGHTNESS_MIN + (1.0 - CURING_PAINT_BRIGHTNESS_MIN) * intensity
    fill_col = _scale_color(base_col, brightness)
    red_edge = _lerp_color(base_col, CURING_PAINT_EDGE_COLOR, 0.55 + 0.25 * intensity)
    cyan_edge = _lerp_color(base_col, CURING_PAINT_SPARK_COLORS[0], 0.35 + 0.25 * shimmer)
    fill_alpha = int(150 * intensity * (0.7 + 0.3 * pulse))
    ring_alpha = int(210 * intensity * shimmer)
    cyan_alpha = int(120 * intensity * shimmer)
    core_alpha = int(90 * intensity * pulse)
    fill_points = None
    if fill_alpha > 0:
        fill_points = _curing_paint_blob_points(paint, base_r, 0.0, 0.0, t, wiggle)
    ring_points = None
    if ring_alpha > 0 or cyan_alpha > 0:
        ring_points = _curing_paint_blob_points(
            paint, base_r * (1.05 + 0.05 * pulse), 0.0, 0.0, t, wiggle + 0.02
        )
    core_points = None
    if core_alpha > 0:
        core_points = _curing_paint_blob_points(paint, base_r * 0.45, 0.0, 0.0, t, wiggle * 0.6)
    return {
        "key": (intensity, base_col),
        "fill_points": fill_points,
        "fill_rgba": (*fill_col, fill_alpha),
        "ring_points": ring_points,
        "ring_rgba": (*red_edge, ring_alpha),
        "cyan_rgba": (*cyan_edge, cyan_alpha),
        "core_points": core_points,
        "core_rgba": (*_lerp_color(base_col, CURING_PAINT_EDGE_HIGHLIGHT, 0.45), core_alpha),
    }


def draw_curing_paint_iso(surface: pygame.Surface, paint: "CuringPaintFootprint",
                          camx: float, camy: float, *, static: bool = False) -> None:
    life0 = max(0.001, float(getattr(paint, "life0", paint.t)))
    t_left = max(0.0, float(getattr(paint, "t", 0.0)))
    if t_left <= 0.0:
        return
    intensity = max(0.0, min(1.0, t_left / life0))
    if intensity <= 0.0:
        return
    if static:
        cache_key = (intensity, _curing_paint_static_color_key(paint))
        cache = getattr(paint, "_static_cache", None)
        if not cache or cache.get("key") != cache_key:
            cache = _build_curing_paint_static_cache(paint)
            paint._static_cache = cache
        if not cache:
            return
        if cache.get("fill_points") and cache["fill_rgba"][3] > 0:
            points = [(px - camx, py - camy) for px, py in cache["fill_points"]]
            _draw_poly_alpha(surface, cache["fill_rgba"], points)
        if cache.get("ring_points") and cache["ring_rgba"][3] > 0:
            ring_points = [(px - camx, py - camy) for px, py in cache["ring_points"]]
            _draw_polyline_alpha(surface, cache["ring_rgba"], ring_points, width=2)
            if cache["cyan_rgba"][3] > 0:
                _draw_polyline_alpha(surface, cache["cyan_rgba"], ring_points, width=1)
        if cache.get("core_points") and cache["core_rgba"][3] > 0:
            core_points = [(px - camx, py - camy) for px, py in cache["core_points"]]
            _draw_poly_alpha(surface, cache["core_rgba"], core_points)
        return
    age = max(0.0, life0 - t_left)
    t = pygame.time.get_ticks() * 0.001
    if CURING_PAINT_SPLASH_TIME > 0.0 and age < CURING_PAINT_SPLASH_TIME:
        prog = age / CURING_PAINT_SPLASH_TIME
        scale = CURING_PAINT_SPLASH_SCALE_START + prog * (
            CURING_PAINT_SPLASH_SCALE_PEAK - CURING_PAINT_SPLASH_SCALE_START
        )
    elif CURING_PAINT_SPLASH_SETTLE > 0.0 and age < CURING_PAINT_SPLASH_TIME + CURING_PAINT_SPLASH_SETTLE:
        settle = (age - CURING_PAINT_SPLASH_TIME) / CURING_PAINT_SPLASH_SETTLE
        scale = CURING_PAINT_SPLASH_SCALE_PEAK - (CURING_PAINT_SPLASH_SCALE_PEAK - 1.0) * settle
    else:
        scale = 1.0
    pulse = 0.84 + 0.16 * math.sin(t * 3.2 + (paint.x + paint.y) * 0.012)
    shimmer = 0.74 + 0.26 * math.sin(t * 6.0 + (paint.x - paint.y) * 0.02)
    base_r = float(paint.r) * scale
    wiggle = CURING_PAINT_WIGGLE_STRENGTH * intensity * (0.6 + 0.4 * shimmer)
    base_col = _curing_paint_static_color_key(paint)
    brightness = CURING_PAINT_BRIGHTNESS_MIN + (1.0 - CURING_PAINT_BRIGHTNESS_MIN) * intensity
    fill_col = _scale_color(base_col, brightness)
    red_edge = _lerp_color(base_col, CURING_PAINT_EDGE_COLOR, 0.55 + 0.25 * intensity)
    cyan_edge = _lerp_color(base_col, CURING_PAINT_SPARK_COLORS[0], 0.35 + 0.25 * shimmer)
    fill_alpha = int(150 * intensity * (0.7 + 0.3 * pulse))
    if fill_alpha > 0:
        points = _curing_paint_blob_points(paint, base_r, camx, camy, t, wiggle)
        _draw_poly_alpha(surface, (*fill_col, fill_alpha), points)
    ring_alpha = int(210 * intensity * shimmer)
    if ring_alpha > 0:
        ring_points = _curing_paint_blob_points(
            paint, base_r * (1.05 + 0.05 * pulse), camx, camy, t, wiggle + 0.02
        )
        _draw_polyline_alpha(surface, (*red_edge, ring_alpha), ring_points, width=2)
        cyan_alpha = int(120 * intensity * shimmer)
        if cyan_alpha > 0:
            _draw_polyline_alpha(surface, (*cyan_edge, cyan_alpha), ring_points, width=1)
    core_alpha = int(90 * intensity * pulse)
    if core_alpha > 0:
        inner_col = _lerp_color(base_col, CURING_PAINT_EDGE_HIGHLIGHT, 0.45)
        inner_points = _curing_paint_blob_points(paint, base_r * 0.45, camx, camy, t, wiggle * 0.6)
        _draw_poly_alpha(surface, (*inner_col, core_alpha), inner_points)


def _enemy_paint_blob_points(tile: "PaintTile", cx: float, cy: float, radius: float,
                             camx: float, camy: float, t: float, wiggle: float) -> list[tuple[int, int]]:
    points = []
    noise_list = getattr(tile, "_blob_noise", None)
    phase_list = getattr(tile, "_blob_phase", None)
    count = len(noise_list) if noise_list else ENEMY_PAINT_BLOB_POINTS
    if not noise_list:
        noise_list = [1.0] * int(count)
    if not phase_list:
        phase_list = [0.0] * int(count)
    rot = float(getattr(tile, "_blob_rot", 0.0))
    for i in range(int(count)):
        ang = rot + math.tau * i / float(count)
        noise = float(noise_list[i % len(noise_list)])
        phase = float(phase_list[i % len(phase_list)])
        jiggle = 1.0 + wiggle * math.sin(t * ENEMY_PAINT_WIGGLE_SPEED + phase)
        r = radius * noise * jiggle
        wx = cx + math.cos(ang) * r
        wy = cy + math.sin(ang) * r
        points.append(iso_world_px_to_screen(wx, wy, camx, camy, 0.0))
    return points


def _enemy_paint_static_color_key(tile: "PaintTile") -> tuple[int, int, int] | None:
    paint_color = getattr(tile, "paint_color", None)
    if isinstance(paint_color, (tuple, list)) and len(paint_color) >= 3:
        return (int(paint_color[0]), int(paint_color[1]), int(paint_color[2]))
    return None


def _build_enemy_paint_static_cache(gx: int, gy: int, tile: "PaintTile",
                                    intensity: float) -> dict | None:
    vis_intensity = max(0.0, min(1.0, float(intensity)))
    if vis_intensity <= 0.0:
        return None
    base_t = float(getattr(tile, "_spark_phase", 0.0))
    t = base_t * (0.35 + 0.65 * vis_intensity)
    shimmer = 0.7 + 0.3 * math.sin(t * (4.0 + 2.0 * vis_intensity) + base_t)
    pulse = 0.82 + 0.18 * math.sin(t * (2.4 + 1.6 * vis_intensity) + (gx + gy) * 0.38)
    base_r = float(getattr(tile, "paint_radius", ENEMY_PAINT_RADIUS)) * (0.85 + 0.15 * vis_intensity)
    base_r *= (0.95 + 0.05 * math.sin(t * 2.0 + base_t))
    wiggle = ENEMY_PAINT_WIGGLE_STRENGTH * (0.4 + 0.6 * vis_intensity) * (0.6 + 0.4 * shimmer)
    color_key = _enemy_paint_static_color_key(tile)
    custom_col = None
    if color_key is not None:
        custom_col = _lerp_color(color_key, (255, 255, 255), 0.35)
    if custom_col is None:
        fill_col = _scale_color(ENEMY_PAINT_FILL_COLOR, 0.65 + 0.35 * vis_intensity)
        edge_col = _lerp_color(ENEMY_PAINT_FILL_COLOR, ENEMY_PAINT_EDGE_COLOR, 0.55 + 0.35 * vis_intensity)
        highlight_col = _lerp_color(ENEMY_PAINT_EDGE_COLOR, ENEMY_PAINT_EDGE_HIGHLIGHT, 0.45 + 0.45 * shimmer)
        particle_col = ENEMY_PAINT_PARTICLE_COLOR
    else:
        fill_col = _scale_color(custom_col, 0.55 + 0.45 * vis_intensity)
        edge_col = _lerp_color(custom_col, (255, 255, 255), 0.35 + 0.35 * vis_intensity)
        highlight_col = _lerp_color(edge_col, (255, 255, 255), 0.4 + 0.4 * shimmer)
        particle_col = _scale_color(custom_col, 0.35)
    intensity_pow = vis_intensity ** 0.65
    fill_alpha = int(210 * intensity_pow * (0.7 + 0.3 * pulse))
    ring_alpha = int(230 * intensity_pow * shimmer)
    edge2_alpha = int(140 * intensity_pow * shimmer)
    cx = gx * CELL_SIZE + CELL_SIZE * 0.5
    cy = gy * CELL_SIZE + CELL_SIZE * 0.5 + INFO_BAR_HEIGHT
    fill_points = None
    if fill_alpha > 0:
        fill_points = _enemy_paint_blob_points(tile, cx, cy, base_r, 0.0, 0.0, t, wiggle)
    ring_points = None
    if ring_alpha > 0 or edge2_alpha > 0:
        ring_points = _enemy_paint_blob_points(tile, cx, cy, base_r * (1.05 + 0.05 * pulse), 0.0, 0.0, t, wiggle)
    particles = []
    if vis_intensity > 0.2:
        pcount = 2 if vis_intensity < 0.5 else 3
        particle_speed = 10.0 * (0.4 + 0.6 * vis_intensity)
        for i in range(pcount):
            phase = base_t + i * 2.1
            ang = t * (0.7 + 0.15 * i) + phase
            drift = (base_t * particle_speed + i * 5.3) % (base_r * 0.55)
            rad = base_r * (0.18 + 0.12 * math.sin(base_t * 1.3 + i)) + drift * 0.5
            px = cx + math.cos(ang) * rad
            py = cy + math.sin(ang) * rad * 0.6 - drift * 0.25
            sx, sy = iso_world_px_to_screen(px, py, 0.0, 0.0, 0.0)
            size = max(1, int(2 * vis_intensity))
            particles.append((sx, sy, size))
    return {
        "key": (vis_intensity, color_key),
        "fill_points": fill_points,
        "ring_points": ring_points,
        "fill_rgba": (*fill_col, fill_alpha),
        "ring_rgba": (*edge_col, ring_alpha),
        "edge2_rgba": (*highlight_col, edge2_alpha),
        "particles": particles,
        "particle_color": particle_col,
    }


def draw_enemy_paint_tile_iso(surface: pygame.Surface, gx: int, gy: int, tile: "PaintTile",
                              camx: float, camy: float, *, static: bool = False) -> None:
    if getattr(tile, "paint_owner", 0) != 2:
        return
    intensity = max(0.0, min(1.0, float(getattr(tile, "paint_intensity", 0.0))))
    if intensity <= 0.0:
        return
    age = max(0.0, float(getattr(tile, "paint_age", 0.0)))
    blend = 1.0
    blend_in = float(ENEMY_PAINT_BLEND_IN)
    if blend_in > 0.0:
        blend = max(0.0, min(1.0, age / blend_in))
        blend = blend * blend * (3.0 - 2.0 * blend)
    vis_intensity = max(0.0, min(1.0, intensity * blend))
    if vis_intensity <= 0.0:
        return
    if static and blend >= 0.999:
        cache_key = (vis_intensity, _enemy_paint_static_color_key(tile))
        cache = getattr(tile, "_static_cache", None)
        if not cache or cache.get("key") != cache_key:
            cache = _build_enemy_paint_static_cache(gx, gy, tile, vis_intensity)
            tile._static_cache = cache
        if not cache:
            return
        if cache.get("fill_points") and cache["fill_rgba"][3] > 0:
            points = [(px - camx, py - camy) for px, py in cache["fill_points"]]
            _draw_poly_alpha(surface, cache["fill_rgba"], points)
        if cache.get("ring_points") and cache["ring_rgba"][3] > 0:
            ring_points = [(px - camx, py - camy) for px, py in cache["ring_points"]]
            _draw_polyline_alpha(surface, cache["ring_rgba"], ring_points, width=2)
            if cache["edge2_rgba"][3] > 0:
                _draw_polyline_alpha(surface, cache["edge2_rgba"], ring_points, width=1)
        for sx, sy, size in cache.get("particles", []):
            pygame.draw.circle(surface, cache["particle_color"], (int(sx - camx), int(sy - camy)), size)
        return
    base_t = pygame.time.get_ticks() * 0.001
    anim_rate = 0.35 + 0.65 * intensity
    t = base_t * anim_rate
    cx = gx * CELL_SIZE + CELL_SIZE * 0.5
    cy = gy * CELL_SIZE + CELL_SIZE * 0.5 + INFO_BAR_HEIGHT
    shimmer = 0.7 + 0.3 * math.sin(t * (4.0 + 2.0 * intensity) + float(getattr(tile, "_spark_phase", 0.0)))
    pulse = 0.82 + 0.18 * math.sin(t * (2.4 + 1.6 * intensity) + (gx + gy) * 0.38)
    base_r = float(getattr(tile, "paint_radius", ENEMY_PAINT_RADIUS)) * (0.85 + 0.15 * vis_intensity)
    base_r *= (0.9 + 0.1 * blend)
    base_r *= (0.95 + 0.05 * math.sin(t * 2.0 + float(getattr(tile, "_spark_phase", 0.0))))
    wiggle = ENEMY_PAINT_WIGGLE_STRENGTH * (0.4 + 0.6 * intensity) * (0.6 + 0.4 * shimmer)
    paint_color = getattr(tile, "paint_color", None)
    custom_col = None
    if isinstance(paint_color, (tuple, list)) and len(paint_color) >= 3:
        raw_col = (int(paint_color[0]), int(paint_color[1]), int(paint_color[2]))
        custom_col = _lerp_color(raw_col, (255, 255, 255), 0.35)
    if custom_col is None:
        fill_col = _scale_color(ENEMY_PAINT_FILL_COLOR, 0.65 + 0.35 * vis_intensity)
        edge_col = _lerp_color(ENEMY_PAINT_FILL_COLOR, ENEMY_PAINT_EDGE_COLOR, 0.55 + 0.35 * vis_intensity)
        highlight_col = _lerp_color(ENEMY_PAINT_EDGE_COLOR, ENEMY_PAINT_EDGE_HIGHLIGHT, 0.45 + 0.45 * shimmer)
        particle_col = ENEMY_PAINT_PARTICLE_COLOR
    else:
        fill_col = _scale_color(custom_col, 0.55 + 0.45 * vis_intensity)
        edge_col = _lerp_color(custom_col, (255, 255, 255), 0.35 + 0.35 * vis_intensity)
        highlight_col = _lerp_color(edge_col, (255, 255, 255), 0.4 + 0.4 * shimmer)
        particle_col = _scale_color(custom_col, 0.35)
    intensity_pow = vis_intensity ** 0.65
    fill_alpha = int(210 * intensity_pow * (0.7 + 0.3 * pulse))
    if fill_alpha > 0:
        points = _enemy_paint_blob_points(tile, cx, cy, base_r, camx, camy, t, wiggle)
        _draw_poly_alpha(surface, (*fill_col, fill_alpha), points)
    ring_alpha = int(230 * intensity_pow * shimmer)
    if ring_alpha > 0:
        ring_points = _enemy_paint_blob_points(tile, cx, cy, base_r * (1.05 + 0.05 * pulse), camx, camy, t, wiggle)
        _draw_polyline_alpha(surface, (*edge_col, ring_alpha), ring_points, width=2)
        edge2_alpha = int(140 * intensity_pow * shimmer)
        if edge2_alpha > 0:
            _draw_polyline_alpha(surface, (*highlight_col, edge2_alpha), ring_points, width=1)
    if vis_intensity > 0.2:
        pcount = 2 if vis_intensity < 0.5 else 3
        particle_speed = 10.0 * (0.4 + 0.6 * vis_intensity)
        for i in range(pcount):
            phase = float(getattr(tile, "_spark_phase", 0.0)) + i * 2.1
            ang = t * (0.7 + 0.15 * i) + phase
            drift = (base_t * particle_speed + i * 5.3) % (base_r * 0.55)
            rad = base_r * (0.18 + 0.12 * math.sin(base_t * 1.3 + i)) + drift * 0.5
            px = cx + math.cos(ang) * rad
            py = cy + math.sin(ang) * rad * 0.6 - drift * 0.25
            sx, sy = iso_world_px_to_screen(px, py, camx, camy, 0.0)
            size = max(1, int(2 * vis_intensity))
            pygame.draw.circle(surface, particle_col, (int(sx), int(sy)), size)


def draw_ground_spike_iso(surface: pygame.Surface, spike: "GroundSpike", camx: float, camy: float) -> None:
    life0 = max(0.001, float(getattr(spike, "life0", spike.t)))
    age = max(0.0, life0 - float(spike.t))
    rise = 1.0 if GROUND_SPIKES_RISE_TIME <= 0 else min(1.0, age / GROUND_SPIKES_RISE_TIME)
    fade = max(0.0, min(1.0, float(spike.t) / life0))
    if fade <= 0.0 or rise <= 0.0:
        return
    pulse = 0.65 + 0.35 * math.sin(pygame.time.get_ticks() * 0.008 + (spike.x + spike.y) * 0.01)
    lvl = int(getattr(spike, "level", 1))
    idx = max(0, min(lvl - 1, len(GROUND_SPIKES_VIS_SCALE) - 1))
    vis_scale = float(GROUND_SPIKES_VIS_SCALE[idx])
    base_r = float(spike.r) * vis_scale * (0.4 + 0.6 * rise) * max(0.35, fade)
    height = float(spike.r) * 2.6 * vis_scale * rise * (0.35 + 0.65 * fade)
    top_r = max(1.0, base_r * 0.35)
    if age <= GROUND_SPIKES_GLOW_TIME:
        glow_p = max(0.0, 1.0 - age / max(0.001, GROUND_SPIKES_GLOW_TIME))
        glow_alpha = int(180 * glow_p)
        glow_scale = 1.0 + 0.18 * idx
        draw_iso_ground_ellipse(
            surface, spike.x, spike.y, base_r * 1.6 * glow_scale,
            GROUND_SPIKES_COLOR, glow_alpha, camx, camy, fill=True
        )
    ring_alpha = int(140 * fade * pulse)
    if ring_alpha > 0:
        ring_scale = 1.0 + 0.12 * idx
        draw_iso_ground_ellipse(
            surface, spike.x, spike.y, base_r * 1.1 * ring_scale,
            GROUND_SPIKES_RING, ring_alpha, camx, camy, fill=False, width=2
        )
    base_pts = [
        iso_world_px_to_screen(spike.x + base_r, spike.y, camx, camy, 0.0),
        iso_world_px_to_screen(spike.x, spike.y + base_r, camx, camy, 0.0),
        iso_world_px_to_screen(spike.x - base_r, spike.y, camx, camy, 0.0),
        iso_world_px_to_screen(spike.x, spike.y - base_r, camx, camy, 0.0),
    ]
    top_pts = [
        iso_world_px_to_screen(spike.x + top_r, spike.y, camx, camy, height),
        iso_world_px_to_screen(spike.x, spike.y + top_r, camx, camy, height),
        iso_world_px_to_screen(spike.x - top_r, spike.y, camx, camy, height),
        iso_world_px_to_screen(spike.x, spike.y - top_r, camx, camy, height),
    ]
    _draw_poly_alpha(surface, (*GROUND_SPIKES_BASE_DARK, int(160 * fade)), base_pts)
    side_alpha = int(200 * fade)
    for i in range(4):
        j = (i + 1) % 4
        col = GROUND_SPIKES_SIDE_LIGHT if i in (0, 1) else GROUND_SPIKES_SIDE_DARK
        _draw_poly_alpha(surface, (*col, side_alpha), [base_pts[i], base_pts[j], top_pts[j], top_pts[i]])
    _draw_poly_alpha(surface, (*GROUND_SPIKES_TOP_COLOR, int(220 * fade)), top_pts)


def draw_iso_hex_ring(surface: pygame.Surface, x_px: float, y_px: float, r_px: float,
                      color: tuple[int, int, int], alpha: float,
                      camx: float, camy: float,
                      *, sides: int = 6, fill_alpha: float = 0.0, width: int = 3) -> None:
    """Hex/oct ring helper projected onto the iso ground plane."""
    wx = x_px / CELL_SIZE
    wy = (y_px - INFO_BAR_HEIGHT) / CELL_SIZE
    cx, cy = iso_world_to_screen(wx, wy, 0, camx, camy)
    rx, ry = iso_circle_radii_screen(float(r_px))
    surf = pygame.Surface((rx * 2 + 6, ry * 2 + 6), pygame.SRCALPHA)
    scx, scy = surf.get_width() // 2, surf.get_height() // 2
    pts = []
    n = max(3, int(sides))
    for i in range(n):
        ang = math.tau * i / float(n)
        px = scx + math.cos(ang) * rx
        py = scy + math.sin(ang) * ry
        pts.append((px, py))
    if fill_alpha > 0:
        rgba_fill = (*color, int(max(0, min(255, fill_alpha))))
        pygame.draw.polygon(surf, rgba_fill, pts)
    rgba_ring = (*color, int(max(0, min(255, alpha))))
    pygame.draw.polygon(surf, rgba_ring, pts, max(1, int(width)))
    surface.blit(surf, (cx - surf.get_width() // 2, cy - surf.get_height() // 2))


def _player_has_any_shield(player) -> bool:
    return (
            int(getattr(player, "shield_hp", 0)) > 0
            or int(getattr(player, "carapace_hp", 0)) > 0
            or int(getattr(player, "bone_plating_hp", 0)) > 0  # treat plating as shield for Aegis Pulse
    )


def _apply_aegis_pulse_damage(player, game_state: "GameState", enemies, cx: float, cy: float,
                              radius: float, damage: int) -> None:
    rr = float(radius)
    dmg = int(max(0, damage))
    if getattr(game_state, "biome_active", None) == "Scorched Hell":
        dmg = int(round(dmg * 2.0))
    text_kind = "aegis"
    # Hit destructible obstacles (red blocks) the same way bullets do
    for gp, ob in list(getattr(game_state, "obstacles", {}).items()):
        if getattr(ob, "type", "") != "Destructible":
            continue
        # circle-rect intersection using closest point clamp
        rect = ob.rect
        closest_x = min(max(cx, rect.left), rect.right)
        closest_y = min(max(cy, rect.top), rect.bottom)
        dx = closest_x - cx
        dy = closest_y - cy
        if dx * dx + dy * dy > rr * rr:
            continue
        ob.health = (ob.health or 0) - BULLET_DAMAGE_BLOCK
        if ob.health <= 0:
            bx, by = rect.centerx, rect.centery
            del game_state.obstacles[gp]
            if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                game_state.spawn_spoils(bx, by, 1)
            if player:
                player.add_xp(XP_PLAYER_BLOCK)
    for z in list(enemies):
        if getattr(z, "hp", 0) <= 0:
            continue
        zr = float(getattr(z, "radius", getattr(z, "size", CELL_SIZE) * 0.5))
        dx = z.rect.centerx - cx
        dy = z.rect.centery - cy
        if dx * dx + dy * dy > (rr + zr) ** 2:
            continue
        dealt = int(max(0, dmg))
        if dealt <= 0:
            continue
        if getattr(z, "type", "") == "boss_mist":
            if random.random() < MIST_PHASE_CHANCE:
                game_state.add_damage_text(z.rect.centerx, z.rect.centery, "TELEPORT", crit=False, kind="shield")
                pdx = z.rect.centerx - player.rect.centerx
                pdy = z.rect.centery - player.rect.centery
                L = (pdx * pdx + pdy * pdy) ** 0.5 or 1.0
                ox = pdx / L * (MIST_PHASE_TELE_TILES * CELL_SIZE)
                oy = pdy / L * (MIST_PHASE_TELE_TILES * CELL_SIZE)
                z.x += ox
                z.y += oy - INFO_BAR_HEIGHT
                z.rect.x = int(z.x)
                z.rect.y = int(z.y + INFO_BAR_HEIGHT)
                continue
            dist_tiles = math.hypot((z.rect.centerx - cx) / CELL_SIZE,
                                    (z.rect.centery - cy) / CELL_SIZE)
            if dist_tiles >= MIST_RANGED_REDUCE_TILES:
                dealt = int(dealt * MIST_RANGED_MULT)
        dealt = apply_vuln_bonus(z, dealt)
        if getattr(z, "shield_hp", 0) > 0:
            blocked = min(dealt, z.shield_hp)
            z.shield_hp -= dealt
            if blocked > 0:
                game_state.add_damage_text(z.rect.centerx, z.rect.centery, blocked, crit=False, kind=text_kind)
            overflow = dealt - blocked
            if overflow > 0:
                z.hp -= overflow
                game_state.add_damage_text(z.rect.centerx, z.rect.centery - 10, overflow, crit=False, kind=text_kind)
        else:
            z.hp -= dealt
            game_state.add_damage_text(z.rect.centerx, z.rect.centery, dealt, crit=False, kind=text_kind)


def trigger_aegis_pulse(player, game_state: "GameState", enemies, radius: float, damage: int,
                        base_delay: float = 0.0) -> None:
    cx, cy = player.rect.centerx, player.rect.centery
    if not hasattr(game_state, "aegis_pulses") or game_state.aegis_pulses is None:
        game_state.aegis_pulses = []
    layers, expand_time, layer_gap = aegis_pulse_visual_profile(getattr(player, "aegis_pulse_level", 1))
    for idx in range(layers):
        delay = base_delay + idx * layer_gap
        game_state.aegis_pulses.append(
            AegisPulseRing(cx, cy, radius, delay, expand_time, AEGIS_PULSE_RING_FADE, damage)
        )


def tick_aegis_pulse(player, game_state: "GameState", enemies, dt: float) -> None:
    lvl = int(getattr(player, "aegis_pulse_level", 0))
    if lvl <= 0:
        return
    radius, damage, cooldown = aegis_pulse_stats(lvl, getattr(player, "max_hp", None))
    wave_count = aegis_pulse_wave_count(lvl)
    cd_timer = float(getattr(player, "_aegis_pulse_cd", cooldown))
    has_shield = _player_has_any_shield(player)
    if has_shield:
        cd_timer -= dt
        # if dt was large, fire multiple pulses to catch up without runaway loops
        while cd_timer <= 0.0:
            for w in range(wave_count):
                trigger_aegis_pulse(
                    player, game_state, enemies, radius, damage,
                    base_delay=float(w) * AEGIS_PULSE_WAVE_GAP
                )
            cd_timer += cooldown
            if cd_timer <= -cooldown * 1.5:
                cd_timer = cooldown
                break
    else:
        cd_timer = min(cd_timer, cooldown)
    player._aegis_pulse_cd = cd_timer


def roll_spoils_for_enemy(z: "Enemy") -> int:
    """Return number of coins to drop for a killed enemy, applying drop chance."""
    t = getattr(z, "type", "basic")
    # Ravagers should always drop spoils (no RNG miss)
    if t == "ravager":
        lo, hi = SPOILS_PER_TYPE.get("ravager", (2, 5))
        return random.randint(int(lo), int(hi))
    if random.random() > SPOILS_DROP_CHANCE:
        return 0
    lo, hi = SPOILS_PER_TYPE.get(t, (1, 1))
    return random.randint(int(lo), int(hi))


def player_xp_required(level: int) -> int:
    """
    XP required to go from `level` -> `level+1`.
    Early levels are quick; later levels ramp reasonably (like mature ARPG/roguelites).
    """
    L = max(1, int(level))
    base = PLAYER_XP_TO_LEVEL
    exp_part = base * (XP_CURVE_EXP_GROWTH ** (L - 1))
    linear_part = XP_CURVE_LINEAR * L
    softcap_part = 0.0
    if L >= XP_CURVE_SOFTCAP_START:
        softcap_part = (L - XP_CURVE_SOFTCAP_START) ** XP_CURVE_SOFTCAP_POWER
    return int(exp_part + linear_part + softcap_part + 0.5)


def _diminish_growth(level: int, per_level: float) -> float:
    """Apply softcap to per-level growth after MON_SOFTCAP_LEVEL."""
    if level <= MON_SOFTCAP_LEVEL:
        return per_level * level
    base = per_level * MON_SOFTCAP_LEVEL
    extra = (level - MON_SOFTCAP_LEVEL) * per_level * MON_SOFTCAP_FACTOR
    return base + extra


# ---- Per-run carry-over of player's growth between levels ----
# ---- Per-run carry-over of player's growth between levels ----
def capture_player_carry(player) -> dict:
    """Carry only progression: level and leftover XP. HP is NOT carried across levels."""
    return {
        "level": int(getattr(player, "level", 1)),
        "xp": int(getattr(player, "xp", 0)),  # leftover XP toward next level
        "hp": int(max(0, min(getattr(player, "hp", 0),
                             getattr(player, "max_hp", 0))))
    }


def apply_player_carry(player, carry: dict | None):
    """Rebuild level-based growth, then start the level at FULL HP."""
    if not carry:
        # Still start full HP each level, even with no carry
        player.hp = player.max_hp
        return
    target_level = max(1, int(carry.get("level", 1)))
    leftover_xp = max(0, int(carry.get("xp", 0)))
    carry_hp = carry.get("hp", None)
    # reset to level 1 baseline, then feed XP for target_level + leftover
    player.level = 1
    player.xp = 0
    player.xp_to_next = player_xp_required(1)
    total_xp = 0
    for L in range(1, target_level):
        total_xp += player_xp_required(L)
    total_xp += leftover_xp
    if total_xp > 0:
        player.add_xp(total_xp)
        player.levelup_pending = 0
    if carry_hp is not None:
        player.hp = max(1, min(player.max_hp, int(carry_hp)))
    else:
        player.hp = min(player.hp, player.max_hp)


def monster_scalars_for(game_level: int, wave_index: int) -> Dict[str, int | float]:
    """
    Return additive/multipliers for enemy stats based on the current game level & wave.
    We return {'hp_mult', 'atk_mult', 'spd_add', 'elite?', 'boss?'}.
    """
    L = max(0, int(game_level))
    W = max(0, int(wave_index))
    # 原处在 monster_scalars_for 内
    if MON_SCALE_MODE == "exp":
        # 关卡指数成长 + 软帽后降低“有效年化”
        pre = min(L, MON_SOFTCAP_LEVEL)
        post = max(0, L - MON_SOFTCAP_LEVEL)
        # 例：每关 8%（HP）/ 9%（ATK），软帽后仅按 40% 的强度继续复利
        hp_mult_lvl = ((1.0 + MON_HP_GROWTH_PER_LEVEL) ** pre *
                       (1.0 + MON_HP_GROWTH_PER_LEVEL * MON_SOFTCAP_FACTOR) ** post)
        atk_mult_lvl = ((1.0 + MON_ATK_GROWTH_PER_LEVEL) ** pre *
                        (1.0 + MON_ATK_GROWTH_PER_LEVEL * MON_SOFTCAP_FACTOR) ** post)
        # 波次也改为复利（更平滑），不想动可保留原来的线性乘子
        hp_mult_wave = (1.0 + MON_HP_GROWTH_PER_WAVE) ** W
        atk_mult_wave = (1.0 + MON_ATK_GROWTH_PER_WAVE) ** W
        hp_mult = hp_mult_lvl * hp_mult_wave
        atk_mult = atk_mult_lvl * atk_mult_wave
    else:
        # ← 保留你现在的线性+软帽逻辑
        hp_mult = (1.0 + _diminish_growth(L, MON_HP_GROWTH_PER_LEVEL)) * (1.0 + W * MON_HP_GROWTH_PER_WAVE)
        atk_mult = (1.0 + _diminish_growth(L, MON_ATK_GROWTH_PER_LEVEL)) * (1.0 + W * MON_ATK_GROWTH_PER_WAVE)
    # additive speed bumps
    spd_add = (L // MON_SPD_ADD_EVERY_LEVELS) + (W // MON_SPD_ADD_EVERY_WAVES)
    # elites (chance increases with game level)
    elite_p = min(ELITE_MAX_CHANCE, ELITE_BASE_CHANCE + L * ELITE_CHANCE_PER_LEVEL)
    is_elite = (random.random() < elite_p)
    # boss only on boss levels (your global const already exists)
    is_boss = is_boss_level(game_level) and (wave_index == 0)  # first wave of boss level
    # apply elite/boss extras to the multipliers
    if is_elite:
        hp_mult *= ELITE_HP_MULT_EXTRA
        atk_mult *= ELITE_ATK_MULT_EXTRA
        spd_add += ELITE_SPD_ADD_EXTRA
    if is_boss:
        hp_mult *= BOSS_HP_MULT_EXTRA
        atk_mult *= BOSS_ATK_MULT_EXTRA
        spd_add += BOSS_SPD_ADD_EXTRA
    return {"hp_mult": hp_mult, "atk_mult": atk_mult, "spd_add": spd_add, "elite": is_elite, "boss": is_boss}


def roll_affix(game_level: int) -> Optional[str]:
    """Roll a lightweight affix occasionally; return name or None."""
    p = min(AFFIX_CHANCE_MAX, AFFIX_CHANCE_BASE + game_level * AFFIX_CHANCE_PER_LEVEL)
    if random.random() >= p:
        return None
    # three simple mature affixes
    return random.choice(["frenzied", "armored", "veteran"])


def apply_affix(z: "Enemy", affix: Optional[str]):
    """Mutate a enemy with the chosen affix. Small, readable bonuses."""
    if not affix:
        return
    if affix == "frenzied":
        z.attack = int(z.attack * 1.15)
        z.speed = int(z.speed + 1)
        z._affix_tag = "F"  # tag for draw
    elif affix == "armored":
        z.max_hp = int(z.max_hp * 1.35)
        z.hp = int(z.hp * 1.35)
        z.speed = max(1, z.speed - 1)
        z._affix_tag = "A"
    elif affix == "veteran":
        z.z_level += 1
        z.attack = int(z.attack * 1.08 + 1)
        z.max_hp = int(z.max_hp * 1.10 + 1)
        z.hp = min(z.max_hp, z.hp + 2)
        z._affix_tag = "V"


def create_memory_devourer(grid_xy: Tuple[int, int], level_idx: int) -> "MemoryDevourerBoss":
    return MemoryDevourerBoss(grid_xy, level_idx)


def spawn_corruptling_at(x_px: float, y_px: float) -> "Enemy":
    """
    从屏幕像素坐标生成腐蚀幼体（近战小怪）。
    注意 y_px 包含了 INFO_BAR_HEIGHT，需要在换算格子时减掉。
    """
    # 像素 -> 格子；y 要扣掉信息栏偏移
    gx = int(max(0, min(GRID_SIZE - 1, x_px // CELL_SIZE)))
    gy = int(max(0, min(GRID_SIZE - 1, (y_px - INFO_BAR_HEIGHT) // CELL_SIZE)))
    z = Enemy((gx, gy),
               attack=int(CHILD_ATK),
               speed=int(max(1, CHILD_SPEED)),
               ztype="corruptling",
               hp=int(CHILD_HP))
    # 幼体更快进入战斗
    z.spawn_delay = 0.25
    return z


def spawn_mistling_at(cx, cy, level_idx=0):
    gx = max(0, min(GRID_SIZE - 1, int(cx // CELL_SIZE)))
    gy = max(0, min(GRID_SIZE - 1, int((cy - INFO_BAR_HEIGHT) // CELL_SIZE)))
    z = Enemy((gx, gy), attack=10, speed=3, ztype="mistling", hp=24)
    return z


def make_scaled_enemy(pos: Tuple[int, int], ztype: str, game_level: int, wave_index: int) -> "Enemy":
    """Factory: spawn a enemy already scaled, with elite/boss & affixes applied."""
    z = Enemy(pos, speed=ENEMY_SPEED, ztype=ztype)
    s = monster_scalars_for(game_level, wave_index)
    # bake stats
    z.attack = max(1, int(z.attack * s["atk_mult"]))
    z.max_hp = max(1, int(z.max_hp * s["hp_mult"]))
    z.hp = z.max_hp
    z.speed = int(z.speed + s["spd_add"])
    z.is_elite = bool(s["elite"])
    z.is_boss = bool(s["boss"])
    # small affix roll
    aff = roll_affix(game_level)
    apply_affix(z, aff)
    z._affix_name = aff
    # type-specific overrides
    if ztype == "ravager":
        z.attack = max(1, int(z.attack * RAVAGER_ATK_MULT))
        z.max_hp = max(1, int(z.max_hp * RAVAGER_HP_MULT))
        z.hp = z.max_hp
        cx, cy = z.rect.center
        z.size = int(CELL_SIZE * RAVAGER_SIZE_MULT)
        z.rect = pygame.Rect(0, 0, z.size, z.size)
        z.rect.center = (cx, cy)
        z.x = float(z.rect.x)
        z.y = float(z.rect.y - INFO_BAR_HEIGHT)
        z.radius = int(z.size * 0.50)
        z.contact_damage_mult = RAVAGER_CONTACT_MULT
        z._size_override = z.size  # keep enlarged footprint even after XP growth
        z._display_name = "Ravager"
        z._foot_prev = (z.rect.centerx, z.rect.bottom)
        z._foot_curr = (z.rect.centerx, z.rect.bottom)
        z._current_color = ENEMY_COLORS.get("ravager", z.color)
        z._base_size = int(z.size)
    # ← cap final move speed
    z.speed = min(ENEMY_SPEED_MAX, max(1, z.speed))
    set_enemy_size_category(z)
    return z


def make_coin_bandit(world_xy, level_idx: int, wave_idx: int, budget: int, player_dps: float | None = None):
    # world_xy 是“脚底世界坐标”（包含 INFO_BAR_HEIGHT 偏移的像素）
    wx, wy = world_xy
    gx = max(0, min(int(wx // CELL_SIZE), GRID_SIZE - 1))
    gy = max(0, min(int((wy - INFO_BAR_HEIGHT) // CELL_SIZE), GRID_SIZE - 1))  # ← 关键：扣掉顶栏
    # 用网格坐标创建 Enemy（引擎的 Enemy 构造本来就需要网格）
    z = Enemy((gx, gy), ztype="bandit", speed=BANDIT_BASE_SPEED)
    z.bandit_triggered = False
    z.bandit_break_t = 0.0
    # ===== 非线性随关卡/预算缩放 =====
    z.z_level = max(1, int(1 + level_idx * 0.25))
    scale_spd = (max(1.0, budget) ** 0.33) * 0.12 + 0.05 * level_idx
    z.speed = min(ENEMY_SPEED_MAX, BANDIT_BASE_SPEED + scale_spd)
    # 专用圆形碰撞体（用于与玩家的接触判定 & 光环半径）
    z.radius = int(z.size * 0.50)
    # Anti-jitter & corner-escape bookkeeping
    z.mode = "FLEE"
    z.last_collision_tile = None
    z.frames_on_same_tile = 0
    z.stuck_origin_pos = (z.x, z.y)
    z.escape_dir = (0.0, 0.0)
    z.escape_timer = 0.0
    # --- 生命值 = 基础血 + 玩家DPS × 等级分段倍率 ---
    dps = float(player_dps) if player_dps is not None else float(compute_player_dps(None))
    lvl = max(1, int(level_idx) + 1)  # display level (1-based)
    if lvl <= 5:
        t = 0.0 if lvl <= 3 else (lvl - 3) / 2.0
        dps_mult = BANDIT_HP_DPS_MULT_MIN + (BANDIT_HP_DPS_MULT_MID - BANDIT_HP_DPS_MULT_MIN) * t
    elif lvl <= 10:
        t = (lvl - 6) / 4.0
        dps_mult = BANDIT_HP_DPS_MULT_MID + (BANDIT_HP_DPS_MULT_MAX - BANDIT_HP_DPS_MULT_MID) * t
    else:
        dps_mult = BANDIT_HP_DPS_MULT_MAX
    target_hp = int(math.ceil(BANDIT_BASE_HP + dps * dps_mult))
    z.max_hp = target_hp
    z.hp = target_hp
    z.attack = 1  # 不是用来打人的
    z.is_elite = True  # 精英描边
    # z.ai_mode = "flee"         # 逃离玩家
    # 偷币逻辑：只动用“meta coin”，不碰本局普通金币
    steal_raw = BANDIT_STEAL_RATE_MIN + (BANDIT_STEAL_RATE_MAX - BANDIT_STEAL_RATE_MIN) * (
            1.0 - math.exp(-0.5 - 0.08 * level_idx - 0.004 * max(0, budget))
    )
    z.steal_per_sec = int(max(BANDIT_STEAL_RATE_MIN, min(BANDIT_STEAL_RATE_MAX, round(steal_raw))))
    esc_raw = BANDIT_ESCAPE_TIME_BASE - 0.004 * max(0, budget) - 0.4 * level_idx
    z.escape_t = max(BANDIT_ESCAPE_TIME_MIN, esc_raw)
    # 用于光环动画的相位
    z._aura_t = random.random()
    # 跟踪偷取与掉落奖励
    z._stolen_total = 0
    z._steal_accum = 0.0
    z._bonus_rate = BANDIT_BONUS_RATE
    return z


def transfer_xp_to_neighbors(dead_z: "Enemy", enemies: List["Enemy"],
                             ratio: float = XP_TRANSFER_RATIO,
                             radius: int = XP_INHERIT_RADIUS):
    """On death, share a portion of dead_z's XP to nearby survivors."""
    if not enemies or ratio <= 0:
        return
    cx, cy = dead_z.rect.centerx, dead_z.rect.centery
    r2 = radius * radius
    near = [zz for zz in enemies
            if zz is not dead_z and (zz.rect.centerx - cx) ** 2 + (zz.rect.centery - cy) ** 2 <= r2]
    if not near:
        return
    portion = int(max(0, dead_z.xp) * ratio)
    if portion <= 0:
        return
    share = max(1, portion // len(near))
    for t in near:
        t.gain_xp(share)


def _find_twin_partner(z, enemies):
    partner = None
    ref = getattr(z, "_twin_partner_ref", None)
    if callable(ref):
        partner = ref()
    elif ref is not None:
        partner = ref
    if partner is None and getattr(z, "twin_id", None) is not None:
        for cand in enemies:
            if getattr(cand, "is_boss", False) and getattr(cand, "twin_id", None) == z.twin_id and cand is not z:
                partner = cand
                break
    return partner

GameState = game_state_support.install(_THIS_MODULE)



# ==================== 相机 ====================
def compute_cam_for_center_iso(cx_px: int, cy_px: int) -> tuple[int, int]:
    """给定世界像素（含 INFO_BAR_HEIGHT 的 y），返回 iso 渲染用的 (cam_x, cam_y)。"""
    gx = cx_px / float(CELL_SIZE)
    gy = (cy_px - INFO_BAR_HEIGHT) / float(CELL_SIZE)
    sx, sy = iso_world_to_screen(gx, gy, 0, 0, 0)
    cam_x = int(sx - VIEW_W // 2)
    cam_y = int(sy - (VIEW_H - INFO_BAR_HEIGHT) // 2)
    return cam_x, cam_y


(
    draw_settings_gear,
    _current_music_pos_ms,
    _music_is_busy,
    _resume_bgm_if_needed,
    play_focus_chain_iso,
    play_focus_cinematic_iso,
    render_game_iso_web_lite,
    render_game_iso,
    render_game,
) = render_runtime_support.install(_THIS_MODULE)

def _play_bgm_candidates(candidates: list[str], volume: float = 0.6, fadeout_ms: int = 400):
    """Stop current BGM and play the first existing file in candidates."""
    runtime = _runtime_state()
    viz = _get_neuro_viz()
    try:
        bgm = runtime.get("_bgm")
        if getattr(bgm, "stop", None):
            try:
                bgm.stop(fade_ms=fadeout_ms)
            except Exception:
                pass
        expanded = _expand_audio_candidates(candidates)
        path = next((p for p in expanded if p and os.path.exists(p)), None)
        if not path:
            return False
        bgm = GameSound(music_path=path, volume=volume)
        runtime["_bgm"] = bgm
        bgm.playBackGroundMusic()
        
        # --- MODIFIED: Load into NeuroVisualizer instead of intro_envelope ---
        # Heavy librosa analysis can hitch the first frame; load it asynchronously.
        def _kickoff_load(p: str):
            if not viz:
                return
            if IS_WEB:
                try:
                    viz.load_music(p)
                except Exception as e:
                    print(f"[AudioAnalyzer] web fallback load failed for {p}: {e}")
                return
            # Avoid duplicate loaders on the same path
            loader = _get_neuro_viz_loader()
            loader_path = _get_neuro_viz_loader_path()
            if loader and loader.is_alive() and loader_path == p:
                return
            def _worker():
                try:
                    viz.load_music(p)
                except Exception as e:
                    print(f"[AudioAnalyzer] async load failed for {p}: {e}")
            _set_neuro_viz_loader_path(p)
            loader = threading.Thread(target=_worker, daemon=True)
            _set_neuro_viz_loader(loader)
            loader.start()
        
        _kickoff_load(path)
            
        return True
    except Exception as e:
        print(f"[Audio] bgm swap failed: {e}")
        return False



def play_intro_bgm():
    """Play Intro_V0 if present (home/start), fallback to ZGAME.wav."""
    intro_candidates = [
        *_asset_candidates("music", "Intro_V0.wav"),
        *_asset_candidates("music", "ZGAME.wav"),
    ]
    _play_bgm_candidates(intro_candidates, volume=BGM_VOLUME / 100.0)


def play_combat_bgm():
    """Play the main combat/shop track (ZGAME.wav)."""
    combat_candidates = [
        *_asset_candidates("music", "ZGAME.wav"),
    ]
    _play_bgm_candidates(combat_candidates, volume=BGM_VOLUME / 100.0)


# ==================== 游戏主循环 ====================
async def main_run_level(config, chosen_enemy_type: str) -> Tuple[str, Optional[str], pygame.Surface]:
    return await app_flow_support.main_run_level(_THIS_MODULE, config, chosen_enemy_type)


async def run_from_snapshot(save_data: dict) -> Tuple[str, Optional[str], pygame.Surface]:
    return await app_flow_support.run_from_snapshot(_THIS_MODULE, save_data)


# ==================== 入口 ====================
async def app_main() -> None:
    return await app_flow_support.app_main(_THIS_MODULE)


if __name__ == "__main__":
    asyncio.run(app_main())
# TODO
# Attack MODE need to figure out
# The item collection system can be hugely impact this game to next level
# Player and Enemy both can collect item to upgrade, after kill enemy, player can get the experience to upgrade, and
# I set a timer each game for winning condition, as long as player still alive, after the time is running out
# player won, vice versa. And after each combat, shop(roguelike feature) will appear for player to trade with item
# using the item they collect in the combat
# enemy's health, attack accumulate via level increases
# Special weapon can be trade in shop using big items collected in game(GOLDCOLLECTOR, etc.) OR
# Just make it only unlock by defeating boss/elite
# set limit for player fire rate
# monster type increased:
# influencer: when player approach, decrease player's speed, damage
# Special weapon: GoldCollector, Razor, rage blade jingqiandao
# 模型穿模，调大障碍物脚底的圆形hitbox判定，玩家左右移动的速度会比上下移动速度快不是视错觉需要调整方向向量，heal的颜色可以修改一下容易和敌蛋弄混
# 引入场景buff肉鸽机制，每关开始前会有类似骰子的动画随机出本关的场景buff：暂时想到的风林火山， 敌我双方都会受到增益或debuff
# need more roguelike features
# 命名与分区注释
#
# 在大文件中加入清晰的“分区头”：
#
# Config & Balance
#
# Math & Utils
#
# Entity Classes（Player/Enemy/Bullet/Obstacle/Item/Boss）
#
# AI & Pathfinding（A* / Flow Field）
#
# Level Gen & Spawn
#
# Rendering（iso/ortho，内含 draw_hud）
#
# Screens（Shop/Domain/Success/Fail/Pause）
#
# Main loop / Main entry
# Add new type of boss: BOSS Ⅱ：「雾织母巫 · Mistweaver」
# 主题：大雾支配者，靠分身与迷雾错位压迫。
# 基本数值（以第10关为基准）
# HP：6500（成长系数≈ +12%/关）
#
# 接触伤害：28
# 移速：中等（玩家略快）
# 抗性：距离≥5格时，远程伤害×0.8（逼近打法）
# 机制概览
# 浓雾场（被动）：开场降雾，玩家与怪物显示距离被压到 ~6格；地图上会生成3个驱雾灯笼（可被打掉），点亮/保护时所在半径内清雾。
# 幻影分身：同时存在“本体+2个幻影”。幻影只有1HP，命中即散成雾弹；命中幻影会短暂暴露本体方向（白色箭头飘字提示）。
# 雾门闪现：每10秒在两处雾门间瞬移一次，残留雾门2秒，对穿越者造成小额减速与5点DOT/秒。
# 阶段流程
# P1（100%→70%）
# 技能：雾刃投掷（扇形3枚，地上留1.2s雾带；雾带内ACID风格的减速+每秒10点伤）。
# 召唤：雾妖×3（小型近战，死亡即放小雾爆）。
# 对策：先清幻影与雾妖→保护/占一个灯笼的明区。
# P2（70%→35%）
# 白化风暴：每8秒一次全屏白雾，0.8秒后收束为随机8个“雾标点”，点位落雾池（每秒14伤+减速）。
# 静默领域：随机圆区3秒，屏蔽冲刺/技能；投掷与走位配合压边。
# 召唤→幻影刷新为3个。
# 对策：靠灯笼明区与移动读点，优先踩离雾池。
# P3（35%→0%）
# 猎杀回响：每损失10% HP发一次声纳圈（环形预警），命中的玩家在3秒内留下脚印（被本体追击加速）。
# 雾身：受击后有15%概率瞬时“雾化”0.7s免疫并位移2格。
# 对策：持续移动+在明区内输出；抓住雾化结束的硬直窗口。
# 掉落与奖励
# 灯笼全保留可得视野型饰品（+感知半径/更亮地面指示）。
# 额外灵魂币与少量治疗。
# 金币大盗 (Coin Bandit) - 随机刷新小BOSS
# 设计概念
# 一个狡猾的盗贼型小BOSS，专门偷取玩家金币并在被击败后返还。
# 外形： 金色怪物并带周边淡金色光晕
#
# 核心机制
# 随机出现：在非BOSS关卡中随机刷新，出现时有特殊音效和视觉提示
# 金币窃取：每秒存在就会偷取玩家会一定量的金币（2-10）
# 敏捷逃避：高移动速度，会优先躲避玩家而不是直接对抗
# 财富返还：被击败后掉落一个钱袋，包含所有偷取的金币加上额外奖励
# 逃脱机制：如果在特定时间内未被击败，会带着金币逃离关卡
# ============PROPS==========================
# 1.1. Piercing Rounds
# 1.2. Ricochet Scope
# 1.3. Bleeding Edge
# 1.4. Shrapnel Shells
# 1.5. Mark of Vulnerability
# 2.1. Bone Plating
# 2.2. Guardian Charm
# 2.3. Blood Pact
# 2.4. Retaliation Thorns
# 3.1. Lockbox
# 3.2. Wanted Poster
# 3.3. Coin Magnet
# 3.4. Golden Interest
# 3.5. Bandit Radar
# 4.1. Time Dilation Boots
# ============World View==========================
# MNEURONVIVOR short for memory neuron survivor
# Unfolds the memory of AD patient
# With different ending for this game
