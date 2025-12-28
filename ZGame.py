from __future__ import annotations
import heapq
import sys
import pygame
import math
import threading
import random
import json
import os
import shutil
import copy
import wave
import hashlib
import numpy as np
import librosa
import colorsys
from effects import *
from queue import PriorityQueue
from collections import deque
from typing import Dict, List, Set, Tuple, Optional

# --- Event queue helper to prevent ghost clicks ---
def flush_events():
    try:
        pygame.event.clear()
    except Exception:
        pass


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
    dx = ax - bx;
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


def draw_ui_topbar(screen, game_state, player, time_left: float | None = None) -> None:
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
    tleft = float(time_left if time_left is not None else globals().get("_time_left_runtime", LEVEL_TIME_LIMIT))
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
    total_items = int(META.get("run_items_spawned", 0))
    collected = int(META.get("run_items_collected", 0))
    icon_x, icon_y = VIEW_W - 120, 10
    pygame.draw.circle(screen, (255, 255, 0), (icon_x, icon_y + 8), 8)
    items_text = hud_font.render(f"{collected}", True, (255, 255, 255))
    screen.blit(items_text, (icon_x + 18, icon_y))
    # 金币（物品左侧）
    spoils_total = int(META.get("spoils", 0)) + int(getattr(game_state, "spoils_gained", 0))
    coin_x, coin_y = VIEW_W - 220, 10
    pygame.draw.circle(screen, (255, 215, 80), (coin_x, coin_y + 8), 8)
    pygame.draw.circle(screen, (255, 245, 200), (coin_x, coin_y + 8), 8, 1)
    spoils_text = hud_font.render(f"{spoils_total}", True, (255, 255, 255))
    screen.blit(spoils_text, (coin_x + 14, coin_y))
    # ===== 屏幕中央：一过性横幅 =====
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
        # 倒计时结束后清理
        if game_state.banner_t <= 0.0:
            game_state.banner_text = None


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
    """
    Show Pause (and Settings) while freezing the survival timer.
    Returns (choice, updated_time_left) where choice is:
    'continue' | 'restart' | 'home' | 'exit'
    """
    globals()["_pause_player_ref"] = player
    # 1) start wall-clock for how long we stay paused
    pause_start_ms = pygame.time.get_ticks()
    # 2) loop Pause → (optional Settings) → back to Pause
    while True:
        choice = show_pause_menu(screen, bg_surface)
        if choice == 'settings':
            show_settings_popup(screen, bg_surface)
            flush_events()
            continue
        break
    globals()["_time_left_runtime"] = time_left  # keep HUD in sync
    # 4) reset the clock baseline so the next tick doesn't produce a huge dt
    clock.tick(60)
    flush_events()
    return choice, time_left


def _expanded_block_mask(obstacles: dict, grid_size: int, radius_px: int) -> list:
    """返回经过半径外扩后的阻挡掩码（True=不可走）"""
    # 把像素半径近似成网格曼哈顿半径：半格≈CELL_SIZE*0.5
    radius_cells = max(1, int(math.ceil(radius_px / (CELL_SIZE * 0.5))))
    mask = [[False] * grid_size for _ in range(grid_size)]
    # 原始脚印
    for (gx, gy) in obstacles.keys():
        mask[gy][gx] = True
    # 曼哈顿外扩
    if radius_cells > 0:
        base = [row[:] for row in mask]
        for y in range(grid_size):
            for x in range(grid_size):
                if not base[y][x]:
                    continue
                for dy in range(-radius_cells, radius_cells + 1):
                    for dx in range(-radius_cells, radius_cells + 1):
                        if abs(dx) + abs(dy) <= radius_cells:
                            nx, ny = x + dx, y + dy
                            if 0 <= nx < grid_size and 0 <= ny < grid_size:
                                mask[ny][nx] = True
    return mask


def _reachable_to_edge(start: tuple, mask: list) -> bool:
    """只在 mask 为 False 的格子上走，看能否走到外环"""
    n = len(mask)
    sx, sy = start
    if not (0 <= sx < n and 0 <= sy < n) or mask[sy][sx]:
        return False
    q = deque([(sx, sy)])
    seen = {(sx, sy)}
    while q:
        x, y = q.popleft()
        if x == 0 or y == 0 or x == n - 1 or y == n - 1:
            return True
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < n and 0 <= ny < n and not mask[ny][nx] and (nx, ny) not in seen:
                seen.add((nx, ny));
                q.append((nx, ny))
    return False


def ensure_passage_budget(obstacles: dict, grid_size: int, player_spawn: tuple, tries: int = 8):
    """
    若玩家出生点到外环不可达：随机移除 1-2 个可破坏障碍（最多 tries 次），保证可走。
    注意：只改 obstacles 这个 dict，不改其它东西。
    """
    # 预先收集可破坏障碍坐标
    destructibles = [pos for pos, ob in obstacles.items() if getattr(ob, "type", "") == "Destructible"]
    for _ in range(tries):
        mask = _expanded_block_mask(obstacles, grid_size, PLAYER_RADIUS)
        if _reachable_to_edge(player_spawn, mask):
            return  # OK
        if not destructibles:
            break
        # 随机挖一个试试（你也可以在这里用更聪明的挑选策略）
        pos = random.choice(destructibles)
        destructibles.remove(pos)
        obstacles.pop(pos, None)


# --- Domain/Biome helpers (one-level-only effects) ---
def apply_domain_buffs_for_level(game_state, player):
    """
    Read globals()['_next_biome'] and arm per-level flags/multipliers.
    All effects are temporary for THIS level only.
    """
    b = globals().get("_next_biome", None)
    game_state.biome_active = b
    globals()["_last_biome"] = b
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


# ==================== 游戏常量配置 ====================
# NOTE: Keep design notes & TODOs below; do not delete when refactoring.
# - Card system UI polish (later pass)
# - Sprite/animation pipeline to be added
# - Balance obstacle density via OBSTACLE_DENSITY/DECOR_DENSITY
GAME_TITLE = "NEURONVIVOR"
INFO_BAR_HEIGHT = 40
GRID_SIZE = 36
CELL_SIZE = 40
WINDOW_SIZE = GRID_SIZE * CELL_SIZE
TOTAL_HEIGHT = WINDOW_SIZE + INFO_BAR_HEIGHT
# Viewport (overridden at runtime when display is created)
VIEW_W = WINDOW_SIZE
VIEW_H = TOTAL_HEIGHT
OBSTACLE_HEALTH = 20
MAIN_BLOCK_HEALTH = 40
# --- view style ---
USE_ISO = True  # True: 伪3D等距渲染；False: 保持现在的纯2D
ISO_CELL_W = 64  # 等距砖块在画面上的“菱形”宽
ISO_CELL_H = 32  # 等距砖块在画面上的“菱形”半高（顶点到中心）
ISO_WALL_Z = 22  # 障碍“墙体”抬起的高度（屏幕像素）
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
        base_dir = os.path.dirname(__file__)
        candidates = [
            os.path.join(base_dir, "assets", "fonts", "Sekuya-Regular.ttf"),
            os.path.join(base_dir, "assets", "fonts", "Sekuya.ttf"),
        ]
        path = next((p for p in candidates if os.path.exists(p)), None)
        if not path:
            raise FileNotFoundError("Sekuya font not found")
        font = pygame.font.Font(path, size)
    except Exception:
        font = pygame.font.SysFont(None, size)
    _SEKUYA_FONT_CACHE[size] = font
    return font
# 角色圆形碰撞半径
PLAYER_RADIUS = int(CELL_SIZE * 0.30)  # matches 0.6×CELL_SIZE footprint
ENEMY_RADIUS = int(CELL_SIZE * 0.30)
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
ENEMY_SPEED_MAX = 4.5
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
DOT_ROUNDS_HIT_SPARK_COLORS = ((140, 240, 255), (255, 255, 255))
DOT_ROUNDS_HIT_SPARK_PARTICLES = (4, 7)
DOT_ROUNDS_HIT_SPARK_SPEED = (80.0, 220.0)
DOT_ROUNDS_HIT_SPARK_LIFE = (0.12, 0.22)
DOT_ROUNDS_HIT_SPARK_SIZE = (2, 5)
DOT_ROUNDS_GLOW_COLOR = (120, 235, 255)
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
SHOP_CATALOG_VERSION = 4  # bump to invalidate cached offers when catalog changes
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
}


def reset_run_state():
    META.update({
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
        "bindings": dict(META.get("bindings", DEFAULT_BINDINGS)),
    })
    globals()["_carry_player_state"] = None
    globals()["_pending_shop"] = False
    globals().pop("_last_spoils", None)
    globals().pop("_coins_at_level_start", None)
    globals().pop("_coins_at_shop_entry", None)
    globals().pop("_shop_slot_ids_cache", None)
    globals().pop("_shop_slots_cache", None)
    globals().pop("_shop_reroll_id_cache", None)
    globals().pop("_shop_reroll_cache", None)
    globals().pop("_resume_shop_cache", None)
    globals().pop("_intro_envelope", None)
    _clear_level_start_baseline()


def _ensure_meta_defaults():
    """Fill in newly added META keys when loading older saves."""
    defaults = {
        "vuln_mark_level": 0,
        "explosive_rounds_level": 0,
        "dot_rounds_level": 0,
        "bindings": {},
    }
    for k, v in defaults.items():
        if k not in META:
            META[k] = v


def _load_meta_from_save(save_data: dict | None) -> None:
    """Apply saved META with range sanitization and fill missing defaults."""
    if not save_data:
        return
    meta_in = dict(save_data.get("meta", {}))
    sanitize_meta_range(meta_in)
    save_data["meta"] = meta_in
    META.update(meta_in)
    _ensure_meta_defaults()
    _apply_meta_bindings(meta_in)


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
    for idx, col in enumerate(DOT_ROUNDS_HIT_SPARK_COLORS):
        count = random.randint(cmin, cmax)
        if idx > 0:
            count = max(2, count // 2)
        for _ in range(count):
            ang = random.uniform(0.0, math.tau)
            speed = random.uniform(sp_min, sp_max)
            vx = math.cos(ang) * speed
            vy = math.sin(ang) * speed
            life = random.uniform(life_min, life_max)
            size = random.randint(size_min, size_max)
            game_state.fx.particles.append(Particle(x, y, vx, vy, col, life, size))


def trigger_explosive_rounds(player, game_state: "GameState", enemies,
                             origin_pos: tuple[float, float], bullet_base: int | None = None) -> None:
    lvl = int(META.get("explosive_rounds_level", 0))
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


def _aegis_pulse_damage_for(level: int, player_max_hp: int | float | None) -> int:
    """Damage scales off max HP using per-level ratios."""
    lvl = max(1, int(level))
    ratios = AEGIS_PULSE_DAMAGE_RATIOS
    ratio = ratios[min(lvl - 1, len(ratios) - 1)]
    base_hp = player_max_hp
    if base_hp is None:
        base_hp = int(META.get("base_maxhp", PLAYER_MAX_HP)) + int(META.get("maxhp", 0))
    base_hp = max(1, int(base_hp))
    return max(1, int(round(base_hp * ratio)))


def aegis_pulse_stats(level: int, player_max_hp: int | float | None = None) -> tuple[int, int, float]:
    """Return (radius_px, damage, cooldown_s) for the given Aegis Pulse level."""
    lvl = max(1, int(level))
    radius = AEGIS_PULSE_BASE_RADIUS + AEGIS_PULSE_RADIUS_PER_LEVEL * (lvl - 1)
    damage = _aegis_pulse_damage_for(lvl, player_max_hp)
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
    discount_lvl = min(COUPON_MAX_LEVEL, int(META.get("coupon_level", 0)))
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
    BINDING_SCANCODES.clear()
    for action, keycode in BINDINGS.items():
        sc = _compute_scancode(int(keycode))
        if sc is not None:
            BINDING_SCANCODES[action] = sc
    # mirror into META for persistence
    META["bindings"] = {k: int(v) for k, v in BINDINGS.items()}


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
        BINDINGS[action] = keycode
        sc = _compute_scancode(keycode)
        if sc is not None:
            BINDING_SCANCODES[action] = sc
        elif action in BINDING_SCANCODES:
            BINDING_SCANCODES.pop(action, None)
        META.setdefault("bindings", {})[action] = int(keycode)


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
    wanted_active = bool(META.get("wanted_active", False) or getattr(game_state, "wanted_wave_active", False))
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


def is_action_event(event, action: str) -> bool:
    """Shortcut for KEYDOWN on a given action binding."""
    return event.type == pygame.KEYDOWN and event.key == action_key(action)
# ==================== Save/Load Helpers ====================
BASE_DIR = os.path.dirname(__file__) if "__file__" in globals() else os.getcwd()
SAVE_DIR = os.path.join(BASE_DIR, "TEMP")
os.makedirs(SAVE_DIR, exist_ok=True)
SAVE_FILE = os.path.join(SAVE_DIR, "savegame.json")


def _clear_shop_cache():
    globals().pop("_shop_slot_ids_cache", None)
    globals().pop("_shop_slots_cache", None)
    globals().pop("_shop_reroll_id_cache", None)
    globals().pop("_shop_reroll_cache", None)
    globals().pop("_resume_shop_cache", None)
    globals().pop("_intro_envelope", None)


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
    coins = int(META.get("spoils", 0))
    level = int(META.get("golden_interest_level", 0))
    gain = _golden_interest_gain(coins, level)
    if gain > 0:
        META["spoils"] = coins + gain
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
    prev_lvl = int(META.get("shady_loan_level", 0))
    prev_debt = max(0, int(META.get("shady_loan_remaining_debt", 0)))
    META["shady_loan_status"] = "active"
    # Grace current level so repayment starts next level, not immediately.
    META["shady_loan_grace_level"] = int(globals().get("current_level", -1))
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
    new_waves = int(META.get("shady_loan_waves_remaining", 0)) + 1  # each purchase adds one wave
    META["spoils"] = int(META.get("spoils", 0)) + instant
    META["shady_loan_last_level"] = purchase_level
    if prev_debt <= 0:
        META["shady_loan_level"] = purchase_level
    else:
        META["shady_loan_level"] = max(prev_lvl, purchase_level)
    META["shady_loan_waves_remaining"] = new_waves
    META["shady_loan_remaining_debt"] = new_debt
    META["shady_loan_defaulted"] = False
    return {
        "level": int(META["shady_loan_level"]),
        "instant": instant,
        "waves": new_waves,
        "debt": new_debt,
    }


def use_wanted_poster() -> dict:
    """Activate a 2-wave bounty window for bandit kills (consumable in shop)."""
    waves = int(META.get("wanted_poster_waves", 0)) + WANTED_POSTER_WAVES
    META["wanted_poster_waves"] = waves
    META["wanted_active"] = False  # will arm on next level start
    return {"waves": waves}


def apply_shady_loan_hp_penalty(penalty_ratio: float) -> int:
    """Apply the max HP cut when defaulting; returns the new max HP."""
    base_hp = max(1, int(META.get("base_maxhp", PLAYER_MAX_HP)))
    bonus_hp = max(0, int(META.get("maxhp", 0)))
    total_hp = base_hp + bonus_hp
    target = max(1, int(math.floor(total_hp * (1.0 - penalty_ratio))))
    new_bonus = min(bonus_hp, max(0, target - 1))
    new_base = max(1, target - new_bonus)
    META["base_maxhp"] = new_base
    META["maxhp"] = new_bonus
    carry = globals().get("_carry_player_state")
    if isinstance(carry, dict):
        carry["hp"] = min(target, max(1, int(carry.get("hp", target))))
    baseline = globals().get("_player_level_baseline")
    if isinstance(baseline, dict):
        baseline["hp"] = min(target, max(1, int(baseline.get("hp", target))))
        baseline["max_hp"] = min(target, max(1, int(baseline.get("max_hp", target))))
    return target


def apply_shady_loan_repayment() -> Optional[dict]:
    """
    Resolve one wave of Shady Loan repayment. Returns a summary dict when work was done,
    or None if no active loan exists.
    """
    level = int(META.get("shady_loan_level", 0))
    debt_left = int(META.get("shady_loan_remaining_debt", 0))
    waves_left = int(META.get("shady_loan_waves_remaining", 0))
    coins_before = max(0, int(META.get("spoils", 0)))
    current_level = int(globals().get("current_level", -1))
    grace_level = int(META.get("shady_loan_grace_level", -1))
    if META.get("shady_loan_status") == "active" and debt_left > 0 and current_level == grace_level:
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
        META["shady_loan_waves_remaining"] = 0
        return None
    idx = _shady_loan_level_idx(level)
    penalty_ratio = SHADY_LOAN_HP_PENALTIES[idx]
    lockbox_lvl = int(META.get("lockbox_level", 0))
    # Already overdue -> apply default immediately
    if waves_left <= 0:
        new_max = apply_shady_loan_hp_penalty(penalty_ratio)
        META["shady_loan_remaining_debt"] = 0
        META["shady_loan_waves_remaining"] = 0
        META["shady_loan_defaulted"] = True
        META["shady_loan_status"] = "defaulted"
        META["shady_loan_last_level"] = level
        META["shady_loan_level"] = 0
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
        META["spoils"] = coins_before - pay_all
        coins_after = int(META.get("spoils", coins_before))
        debt_left = max(0, debt_left - pay_all)
        waves_left = 0
        defaulted = False
        new_max_hp = None
        if debt_left > 0:
            defaulted = True
            META["shady_loan_defaulted"] = True
            META["shady_loan_status"] = "defaulted"
            META["shady_loan_last_level"] = level
            new_max_hp = apply_shady_loan_hp_penalty(penalty_ratio)
            debt_left = 0
            coins_after = int(META.get("spoils", coins_after))
        else:
            META["shady_loan_defaulted"] = False
            META["shady_loan_status"] = "repaid"
            META["shady_loan_last_level"] = level
        META["shady_loan_level"] = 0
        META["shady_loan_remaining_debt"] = debt_left
        META["shady_loan_waves_remaining"] = waves_left
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
        META["spoils"] = coins_before - actual_payment
    coins_after = int(META.get("spoils", coins_before))
    debt_left = max(0, debt_left - actual_payment)
    waves_left = max(0, waves_left - 1)
    defaulted = False
    new_max_hp = None
    if debt_left <= 0:
        debt_left = 0
        waves_left = 0
        META["shady_loan_defaulted"] = False
        META["shady_loan_status"] = "repaid"
        META["shady_loan_last_level"] = level
        META["shady_loan_level"] = 0
    META["shady_loan_remaining_debt"] = debt_left
    META["shady_loan_waves_remaining"] = waves_left
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
        lines.append(f"Coins now: {outcome.get('coins_after', META.get('spoils', 0))}.")
    elif outcome.get("deferred"):
        title_txt = "Shady Loan"
        lines.append("Repayment starts next level. No coins taken this wave.")
        lines.append(f"Debt left: {outcome.get('debt_left', 0)} | Waves left: {outcome.get('waves_left', 0)}")
        lines.append(f"Coins now: {outcome.get('coins_after', META.get('spoils', 0))}.")
    else:
        payment = outcome.get("actual_payment", 0)
        debt_left = outcome.get("debt_left", 0)
        waves_left = outcome.get("waves_left", 0)
        lines.append(f"Paid {payment} coins toward the loan.")
        lines.append(f"Debt left: {debt_left} | Waves left: {waves_left}")
        lines.append(f"Coins now: {outcome.get('coins_after', META.get('spoils', 0))}.")
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


def save_progress(current_level: int,
                  max_wave_reached: int | None = None,
                  pending_shop: bool = False):
    """Persist minimal progress plus META upgrades and player carry.
       If we're mid-level and a baseline exists for this same level,
       save META['spoils'] as the baseline coins (pre-bandit), and
       persist the baseline so CONTINUE can restore it."""
    # 1) Build a META copy; if baseline for this level exists, save baseline coins
    meta_for_save = dict(META)
    try:
        if bool(pending_shop) or bool(globals().get("_in_shop_ui", False)):
            # In/at the shop → keep current bank as-is
            meta_for_save["spoils"] = int(META.get("spoils", 0))
        else:
            # Mid-level → save the level-start baseline as before
            if int(globals().get("_baseline_for_level", -999)) == int(current_level):
                if "_coins_at_level_start" in globals():
                    meta_for_save["spoils"] = int(globals()["_coins_at_level_start"])
                items_base = globals().get("_items_run_baseline", {})
                try:
                    base_spawn = int(items_base.get("spawned", globals().get("_run_items_spawned_start",
                                                                             META.get("run_items_spawned", 0))))
                except Exception:
                    base_spawn = int(META.get("run_items_spawned", 0))
                try:
                    base_collect = int(items_base.get("collected", globals().get("_run_items_collected_start",
                                                                                 META.get("run_items_collected", 0))))
                except Exception:
                    base_collect = int(META.get("run_items_collected", 0))
                meta_for_save["run_items_spawned"] = max(0, int(base_spawn))
                meta_for_save["run_items_collected"] = max(0, int(base_collect))
    except Exception:
        pass
    # 2) Persist the baseline bundle if present
    baseline_bundle = {}
    if "_baseline_for_level" in globals():
        try:
            baseline_bundle["level"] = int(globals()["_baseline_for_level"])
        except Exception:
            pass
    if "_coins_at_level_start" in globals():
        try:
            baseline_bundle["coins"] = int(globals()["_coins_at_level_start"])
        except Exception:
            pass
    if "_player_level_baseline" in globals() and isinstance(globals()["_player_level_baseline"], dict):
        baseline_bundle["player"] = dict(globals()["_player_level_baseline"])
    if "_items_run_baseline" in globals() and isinstance(globals()["_items_run_baseline"], dict):
        try:
            ib = dict(globals()["_items_run_baseline"])
            if "count_this_level" in ib and ib["count_this_level"] is not None:
                ib["count_this_level"] = int(ib["count_this_level"])
            baseline_bundle["items"] = ib
        except Exception:
            pass
    if "_consumable_baseline" in globals() and isinstance(globals()["_consumable_baseline"], dict):
        try:
            baseline_bundle["consumables"] = dict(globals()["_consumable_baseline"])
        except Exception:
            pass
    data = {
        "mode": "progress",
        "current_level": int(current_level),
        "meta": meta_for_save,  # uses baseline spoils when appropriate
        "carry_player": globals().get("_carry_player_state", None),
        "pending_shop": bool(pending_shop),
        "biome": globals().get("_next_biome") or globals().get("_last_biome")
    }
    # Persist shop offer cache so exiting to desktop can't reroll for free
    slots_cache = globals().get("_shop_slot_ids_cache") or globals().get("_shop_slots_cache")
    if slots_cache and isinstance(slots_cache, list):
        ids_only = []
        for s in slots_cache:
            if isinstance(s, dict):
                ids_only.append(s.get("id") or s.get("name"))
            else:
                ids_only.append(s)
        slots_cache = ids_only
    reroll_cache = globals().get("_shop_reroll_id_cache") or globals().get("_shop_reroll_cache")
    if reroll_cache and isinstance(reroll_cache, dict):
        reroll_cache = reroll_cache.get("id") or reroll_cache.get("name")
    if slots_cache is not None or reroll_cache is not None:
        data["shop_cache"] = {
            "slots": slots_cache,
            "reroll": reroll_cache,
        }
    if max_wave_reached is not None:
        data["max_wave_reached"] = int(max_wave_reached)
    if baseline_bundle:
        data["baseline"] = baseline_bundle  # ← survive across Save & Quit
    try:
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save_progress error:", e)


def capture_snapshot(game_state, player, enemies, current_level: int,
                     chosen_enemy_type: str = "basic", bullets: Optional[List['Bullet']] = None) -> dict:
    """Create a full mid-run snapshot of the current game state."""
    snap = {
        "mode": "snapshot",
        "version": 3,
        "meta": {
            "current_level": int(current_level),
            "chosen_enemy_type": str(chosen_enemy_type or "basic"),
            "biome": getattr(game_state, "biome_active", globals().get("_next_biome"))
        },
        "snapshot": {
            "player": {"x": float(player.x), "y": float(player.y),
                       "speed": player.speed, "size": player.size,
                       "fire_cd": float(getattr(player, "fire_cd", 0.0)),
                       "hp": int(getattr(player, "hp", PLAYER_MAX_HP)),
                       "max_hp": int(getattr(player, "max_hp", PLAYER_MAX_HP)),
                       "hit_cd": float(getattr(player, "hit_cd", 0.0)),
                       "level": int(getattr(player, "level", 1)),
                       "xp": int(getattr(player, "xp", 0)),
                       "bone_plating_hp": int(getattr(player, "bone_plating_hp", 0)),
                       "bone_plating_cd": float(getattr(player, "_bone_plating_cd", BONE_PLATING_GAIN_INTERVAL)),
                       "aegis_pulse_cd": float(getattr(player, "_aegis_pulse_cd", 0.0))},
            "enemies": [{
                "x": float(z.x), "y": float(z.y),
                "attack": int(getattr(z, "attack", 10)),
                "speed": int(getattr(z, "speed", 2)),
                "type": str(getattr(z, "type", "basic")),
                "hp": int(getattr(z, "hp", 30)),
                "max_hp": int(getattr(z, "max_hp", getattr(z, "hp", 30))),
                "spawn_elapsed": float(getattr(z, "_spawn_elapsed", 0.0)),
                "attack_timer": float(getattr(z, "attack_timer", 0.0)),
            } for z in enemies],
            "obstacles": [{
                "x": int(ob.rect.x // CELL_SIZE),
                "y": int((ob.rect.y - INFO_BAR_HEIGHT) // CELL_SIZE),
                "type": ob.type,
                "health": None if ob.health is None else int(ob.health),
                "main": bool(getattr(ob, "is_main_block", False)),
            } for ob in game_state.obstacles.values()],
            "items": [{
                "x": int(it.x),
                "y": int(it.y),
                "is_main": bool(it.is_main),
            } for it in game_state.items],
            "decorations": [[int(dx), int(dy)] for (dx, dy) in getattr(game_state, "decorations", [])],
            "bullets": [{
                "x": float(b.x), "y": float(b.y),
                "vx": float(b.vx), "vy": float(b.vy),
                "traveled": float(b.traveled)
            } for b in (bullets or []) if getattr(b, "alive", True)],
            "time_left": float(globals().get("_time_left_runtime", LEVEL_TIME_LIMIT))
        }
    }
    return snap


def save_snapshot(snapshot: dict) -> None:
    """Write a snapshot dict to disk."""
    try:
        with open(SAVE_FILE, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f)
    except Exception as e:
        print(f"[Save] Failed to write snapshot: {e}", file=sys.stderr)


def load_save() -> Optional[dict]:
    """Load either meta or snapshot save; returns dict with 'mode' field or None."""
    try:
        if not os.path.exists(SAVE_FILE):
            return None
        try:
            with open(SAVE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[Save] Failed to read save file: {e}", file=sys.stderr)
            # move the bad save aside so we don't keep failing
            try:
                bad_path = SAVE_FILE + ".bak"
                shutil.move(SAVE_FILE, bad_path)
            except Exception:
                try:
                    os.remove(SAVE_FILE)
                except Exception:
                    pass
            return None
        if not isinstance(data, dict):
            return None
        # v1 compatibility (no mode)
        if "mode" not in data:
            data["mode"] = "meta"
        # normalize fields
        if data["mode"] == "meta":
            data.setdefault("current_level", 0)
        elif data["mode"] == "snapshot":
            data.setdefault("meta", {})
            data["meta"].setdefault("current_level", 0)
            data["meta"].setdefault("chosen_enemy_type", "basic")
            data.setdefault("snapshot", {})
        # --- Hydrate baseline globals so CONTINUE can restore on level entry ---
        try:
            b = data.get("baseline")
            if isinstance(b, dict):
                if "level" in b:
                    globals()["_baseline_for_level"] = int(b["level"])
                if "coins" in b:
                    globals()["_coins_at_level_start"] = int(b["coins"])
                if isinstance(b.get("items"), dict):
                    try:
                        ib = b.get("items", {})
                        spawn = int(ib.get("spawned", 0))
                        collect = int(ib.get("collected", 0))
                        cnt = ib.get("count_this_level", None)
                        if cnt is not None:
                            try:
                                cnt = int(cnt)
                            except Exception:
                                cnt = None
                        globals()["_items_run_baseline"] = {
                            "spawned": spawn,
                            "collected": collect,
                            "count_this_level": cnt,
                        }
                    except Exception:
                        pass
                if isinstance(b.get("consumables"), dict):
                    try:
                        cb = b.get("consumables", {})
                        globals()["_consumable_baseline"] = {
                            "carapace_shield_hp": int(cb.get("carapace_shield_hp", 0)),
                            "wanted_poster_waves": int(cb.get("wanted_poster_waves", 0)),
                            "wanted_active": bool(cb.get("wanted_active", False)),
                        }
                    except Exception:
                        pass
                if isinstance(b.get("player"), dict):
                    _pbase = dict(b["player"])
                    # Back-compat: if meta_stats missing, seed from save meta
                    if "meta_stats" not in _pbase and isinstance(data.get("meta"), dict):
                        meta = data["meta"]
                        try:
                            rng_base = clamp_player_range(_pbase.get("range_base", meta.get("base_range", PLAYER_RANGE_DEFAULT)))
                            rng_val = clamp_player_range(_pbase.get("range", rng_base))
                            rng_mult_est = rng_val / rng_base if rng_base else meta.get("range_mult", 1.0)
                        except Exception:
                            rng_mult_est = meta.get("range_mult", 1.0)
                        _pbase["meta_stats"] = {
                            "dmg": int(meta.get("dmg", 0)),
                            "firerate_mult": float(meta.get("firerate_mult", 1.0)),
                            "range_mult": float(meta.get("range_mult", rng_mult_est)),
                            "speed_mult": float(meta.get("speed_mult", 1.0)),
                            "crit": float(meta.get("crit", 0.0)),
                            "maxhp": int(meta.get("maxhp", 0)),
                        }
                    globals()["_player_level_baseline"] = _pbase
        except Exception as e:
            print(f"[Save] Baseline hydrate failed: {e}", file=sys.stderr)
        # hydrate shop cache so exiting doesn't reroll offers for free
        try:
            cache = data.get("shop_cache")
            if isinstance(cache, dict):
                slots = cache.get("slots")
                reroll = cache.get("reroll")
                if slots is not None:
                    globals()["_shop_slot_ids_cache"] = slots
                if reroll is not None:
                    globals()["_shop_reroll_id_cache"] = reroll
                globals()["_resume_shop_cache"] = True
        except Exception:
            pass
        return data
    except Exception as e:
        print(f"[Save] Failed to read save file: {e}", file=sys.stderr)
        return None


def _clear_level_start_baseline():
    globals().pop("_baseline_for_level", None)
    globals().pop("_coins_at_level_start", None)
    globals().pop("_coins_at_shop_entry", None)
    globals().pop("_player_level_baseline", None)
    globals().pop("_items_run_baseline", None)
    globals().pop("_consumable_baseline", None)
    globals().pop("_items_counted_level", None)
    globals().pop("_restart_from_shop", None)


def _capture_level_start_baseline(level_idx: int, player: "Player", game_state: "GameState" | None = None):
    """Record the exact state the first time we enter this level in this run."""
    globals()["_baseline_for_level"] = int(level_idx)
    # Snapshot level-start coins once per level so bandit thefts don't persist across restarts
    if (globals().get("_baseline_for_level", None) != level_idx
            or "_coins_at_level_start" not in globals()):
        globals()["_coins_at_level_start"] = int(META.get("spoils", 0))
    globals()["_player_level_baseline"] = {
        "level": int(getattr(player, "level", 1)),
        "xp": int(getattr(player, "xp", 0)),
        "xp_to_next": int(getattr(player, "xp_to_next", player_xp_required(1))),
        # keep these so level-ups during a failed attempt don't carry into restart
        "bullet_damage": int(getattr(player, "bullet_damage", META.get("base_dmg", 0) + META.get("dmg", 0))),
        "max_hp": int(getattr(player, "max_hp", META.get("base_maxhp", 0) + META.get("maxhp", 0))),
        "hp": int(getattr(player, "hp", META.get("base_maxhp", 0) + META.get("maxhp", 0))),
        "biome": getattr(game_state, "biome_active", globals().get("_next_biome")),
        # combat stats that may have been modified by level-up choices
        "fire_rate_mult": float(getattr(player, "fire_rate_mult", 1.0)),
        "range": clamp_player_range(getattr(player, "range", PLAYER_RANGE_DEFAULT)),
        "range_base": clamp_player_range(getattr(player, "range_base", PLAYER_RANGE_DEFAULT)),
        "crit_chance": float(getattr(player, "crit_chance", CRIT_CHANCE_BASE)),
        "crit_mult": float(getattr(player, "crit_mult", CRIT_MULT_BASE)),
        "speed": float(getattr(player, "speed", PLAYER_SPEED)),
        # snapshot the META stat multipliers so restarts don't re-stack level-up perks
        "meta_stats": {
            "dmg": int(META.get("dmg", 0)),
            "firerate_mult": float(META.get("firerate_mult", 1.0)),
            "range_mult": float(META.get("range_mult", 1.0)),
            "speed_mult": float(META.get("speed_mult", 1.0)),
            "crit": float(META.get("crit", 0.0)),
            "maxhp": int(META.get("maxhp", 0)),
        },
    }
    try:
        base_spawn = int(globals().get("_run_items_spawned_start", META.get("run_items_spawned", 0)))
    except Exception:
        base_spawn = int(META.get("run_items_spawned", 0))
    try:
        base_collect = int(globals().get("_run_items_collected_start", META.get("run_items_collected", 0)))
    except Exception:
        base_collect = int(META.get("run_items_collected", 0))
    lvl_items = None
    if game_state is not None:
        try:
            lvl_items = int(getattr(game_state, "items_total", len(getattr(game_state, "items", []))))
        except Exception:
            try:
                lvl_items = len(getattr(game_state, "items", []))
            except Exception:
                lvl_items = None
    globals()["_items_run_baseline"] = {
        "spawned": base_spawn,
        "collected": base_collect,
        "count_this_level": lvl_items,
    }
    # Snapshot consumable props that can be depleted mid-level (e.g., Carapace shield, Wanted Poster charge)
    globals()["_consumable_baseline"] = {
        "carapace_shield_hp": int(META.get("carapace_shield_hp", 0)),
        "wanted_poster_waves": int(META.get("wanted_poster_waves", 0)),
        "wanted_active": bool(META.get("wanted_active", False)),
    }


def _restore_level_start_baseline(level_idx: int, player: "Player", game_state: "GameState"):
    """Re-entering the same level: restore bank & player progression.
       If the restart originated from the shop, restore coins to the shop-entry snapshot;
       otherwise restore to the level-start snapshot as before.
    """
    if int(globals().get("_baseline_for_level", -999999)) != int(level_idx):
        return  # entering a different level → nothing to restore
    # 1) Coins: prefer shop-entry baseline if we just continue from  the shop
    # Always restore coins to the LEVEL-START snapshot on any restart.
    # If it's missing (shouldn't happen), fall back to shop-entry or 0.
    _ = bool(globals().pop("_restart_from_shop", False))  # still clear the flag
    if "_coins_at_level_start" in globals():
        META["spoils"] = int(globals()["_coins_at_level_start"])
    elif "_coins_at_shop_entry" in globals():
        META["spoils"] = int(globals()["_coins_at_shop_entry"])
    else:
        META["spoils"] = 0
    # 1.5) Items: restore run-level item counters to the level-start baseline
    items_base = globals().get("_items_run_baseline", None)
    if isinstance(items_base, dict):
        base_spawn = int(items_base.get("spawned", META.get("run_items_spawned", 0)))
        base_collect = int(items_base.get("collected", META.get("run_items_collected", 0)))
        lvl_items = items_base.get("count_this_level", None)
    else:
        base_spawn = int(globals().get("_run_items_spawned_start", META.get("run_items_spawned", 0)))
        base_collect = int(globals().get("_run_items_collected_start", META.get("run_items_collected", 0)))
        lvl_items = None
    if lvl_items is None:
        try:
            lvl_items = int(getattr(game_state, "items_total", len(getattr(game_state, "items", []))))
        except Exception:
            try:
                lvl_items = len(getattr(game_state, "items", []))
            except Exception:
                lvl_items = 0
    try:
        lvl_items = int(lvl_items)
    except Exception:
        lvl_items = 0
    META["run_items_spawned"] = max(0, int(base_spawn) + max(0, int(lvl_items)))
    META["run_items_collected"] = max(0, int(base_collect))
    globals()["_run_items_spawned_start"] = int(base_spawn)
    globals()["_run_items_collected_start"] = int(base_collect)
    globals()["_items_counted_level"] = int(level_idx)
    # 2) Clear per-level counters/state (same as before)
    if hasattr(game_state, "spoils_gained"):
        game_state.spoils_gained = 0
    if hasattr(game_state, "_bandit_stolen"):
        game_state._bandit_stolen = 0
    if hasattr(game_state, "level_coin_delta"):
        game_state.level_coin_delta = 0
    if hasattr(game_state, "bandit_spawned_this_level"):
        game_state.bandit_spawned_this_level = False
    # 3) Restore the player's baseline snapshot (unchanged logic)
    b = globals().get("_player_level_baseline", None)
    if isinstance(b, dict):
        # restore META stat multipliers first, so downstream calculations align with the baseline
        meta_stats = b.get("meta_stats", {})
        if not isinstance(meta_stats, dict):
            # Back-compat: derive a best-effort snapshot from baseline + current META
            try:
                rng_base = clamp_player_range(b.get("range_base", getattr(player, "range_base", PLAYER_RANGE_DEFAULT)))
                rng_val = clamp_player_range(b.get("range", rng_base))
                rng_mult_est = rng_val / rng_base if rng_base else META.get("range_mult", 1.0)
            except Exception:
                rng_mult_est = META.get("range_mult", 1.0)
            meta_stats = {
                "dmg": int(META.get("dmg", 0)),
                "firerate_mult": float(b.get("fire_rate_mult", META.get("firerate_mult", 1.0))),
                "range_mult": float(META.get("range_mult", rng_mult_est)),
                "speed_mult": float(META.get("speed_mult", 1.0)),
                "crit": float(META.get("crit", 0.0)),
                "maxhp": int(META.get("maxhp", 0)),
            }
        for k in ("dmg", "firerate_mult", "range_mult", "speed_mult", "crit", "maxhp"):
            if k in meta_stats:
                META[k] = meta_stats[k]
        player.level = int(b.get("level", 1))
        player.xp = int(b.get("xp", 0))
        player.xp_to_next = int(b.get("xp_to_next", player_xp_required(player.level)))
        player.bullet_damage = int(b.get("bullet_damage", player.bullet_damage))
        player.max_hp = int(b.get("max_hp", player.max_hp))
        player.hp = min(player.max_hp, int(b.get("hp", player.max_hp)))
        player.fire_rate_mult = float(b.get("fire_rate_mult", META.get("firerate_mult", getattr(player, "fire_rate_mult", 1.0))))
        player.range_base = clamp_player_range(b.get("range_base", getattr(player, "range_base", PLAYER_RANGE_DEFAULT)))
        # re-derive range from baseline base + current (restored) META multiplier to avoid cumulative drift
        player.range = compute_player_range(player.range_base, float(META.get("range_mult", 1.0)))
        player.crit_chance = float(b.get("crit_chance", getattr(player, "crit_chance", CRIT_CHANCE_BASE)))
        player.crit_mult = float(b.get("crit_mult", getattr(player, "crit_mult", CRIT_MULT_BASE)))
        player.speed = float(b.get("speed", getattr(player, "speed", PLAYER_SPEED)))
        # ensure biome is consistent on restore (helps downstream logic that reads game_state.biome_active)
        if b.get("biome") is not None:
            game_state.biome_active = b.get("biome")
        # clean any queued level-up picks on a restart to prevent double-application
        player.levelup_pending = 0
    # Restore consumable props to their level-start snapshot so retries don't stay depleted
    consumables = globals().get("_consumable_baseline")
    if isinstance(consumables, dict):
        if "carapace_shield_hp" in consumables:
            cap_hp = max(0, int(consumables.get("carapace_shield_hp", 0)))
            META["carapace_shield_hp"] = cap_hp
            player.carapace_hp = cap_hp
            player._hud_shield_vis = cap_hp / float(max(1, player.max_hp)) if cap_hp > 0 else 0.0
        if "wanted_poster_waves" in consumables:
            META["wanted_poster_waves"] = max(0, int(consumables.get("wanted_poster_waves", 0)))
        if "wanted_active" in consumables:
            META["wanted_active"] = bool(consumables.get("wanted_active", False))
            game_state.wanted_wave_active = bool(META.get("wanted_active", False))


def has_save() -> bool:
    return os.path.exists(SAVE_FILE)


def clear_save() -> None:
    try:
        if os.path.exists(SAVE_FILE):
            os.remove(SAVE_FILE)
    except Exception as e:
        print(f"[Save] Failed to delete save file: {e}", file=sys.stderr)


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


def bullet_radius_for_damage(dmg: int) -> int:
    """
    Sub-linear growth by damage percentage, with a smooth cap.
    Base damage -> BULLET_RADIUS. As damage rises, the bonus eases in and
    asymptotically approaches BULLET_RADIUS_MAX.
    """
    base = float(META.get("base_dmg", BULLET_DAMAGE_ENEMY)) or 1.0
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


def collide_and_slide_circle(entity, obstacles_iter, dx, dy):
    """
    以“圆心 + Minkowski 外扩”的方式，做【扫掠式】轴分离碰撞：
    - X 轴先扫：用线段(cx0 → cx1)与每个扩张矩形的左右边做一次1D相交测试，命中则把终点夹到边界；
    - Y 轴再扫：同理对上下边；
    这样即便步长较大/从角上斜切也不会穿过去。
    """
    entity._hit_ob = None
    if getattr(entity, "can_crush_all_blocks", False) and not hasattr(entity, "_crush_queue"):
        entity._crush_queue = []
    r = getattr(entity, "radius", max(8, CELL_SIZE // 3))
    size = entity.size
    # 起点（圆心，世界像素）
    cx0 = entity.x + size * 0.5
    cy0 = entity.y + size * 0.5 + INFO_BAR_HEIGHT
    # ---------- X 轴扫掠 ----------
    cx1 = cx0 + dx
    hit_x = None
    # 向右：找所有满足 cy0 ∈ [top, bottom] 且 线段跨过 left 的矩形，取最靠近的边
    if dx > 0:
        min_left = None
        for ob in obstacles_iter:
            if getattr(ob, "nonblocking", False):
                continue
            exp = ob.rect.inflate(r * 2, r * 2)
            if exp.top <= cy0 <= exp.bottom and cx0 <= exp.left <= cx1:
                if (min_left is None) or (exp.left < min_left[0]):
                    min_left = (exp.left, ob)
        if min_left:
            cx1 = min_left[0]
            hit_x = min_left[1]
            if getattr(entity, "can_crush_all_blocks", False):
                entity._crush_queue.append(hit_x)
    # 向左：对 right 边做相同处理
    elif dx < 0:
        max_right = None
        for ob in obstacles_iter:
            if getattr(ob, "nonblocking", False):
                continue
            exp = ob.rect.inflate(r * 2, r * 2)
            if exp.top <= cy0 <= exp.bottom and cx1 <= exp.right <= cx0:
                if (max_right is None) or (exp.right > max_right[0]):
                    max_right = (exp.right, ob)
        if max_right:
            cx1 = max_right[0]
            hit_x = max_right[1]
            if getattr(entity, "can_crush_all_blocks", False):
                entity._crush_queue.append(hit_x)
    if hit_x is not None:
        entity._hit_ob = hit_x
    x_min, y_min, x_max, y_max = play_bounds_for_circle(r)
    cx1 = max(x_min, min(cx1, x_max))
    entity.x = cx1 - size * 0.5  # 应用X位移（已夹到边界）
    # 更新圆心（X 已经改变）
    cx0 = entity.x + size * 0.5
    cy0 = entity.y + size * 0.5 + INFO_BAR_HEIGHT
    # ---------- Y 轴扫掠 ----------
    cy1 = cy0 + dy
    hit_y = None
    if dy > 0:
        min_top = None
        for ob in obstacles_iter:
            if getattr(ob, "nonblocking", False):
                continue
            exp = ob.rect.inflate(r * 2, r * 2)
            if exp.left <= cx0 <= exp.right and cy0 <= exp.top <= cy1:
                if (min_top is None) or (exp.top < min_top[0]):
                    min_top = (exp.top, ob)
        if min_top:
            cy1 = min_top[0]
            hit_y = min_top[1]
            if getattr(entity, "can_crush_all_blocks", False):
                try:
                    entity._crush_queue.append(hit_y)
                except Exception:
                    pass
    elif dy < 0:
        max_bottom = None
        for ob in obstacles_iter:
            if getattr(ob, "nonblocking", False):
                continue
            exp = ob.rect.inflate(r * 2, r * 2)
            if exp.left <= cx0 <= exp.right and cy1 <= exp.bottom <= cy0:
                if (max_bottom is None) or (exp.bottom > max_bottom[0]):
                    max_bottom = (exp.bottom, ob)
        if max_bottom:
            cy1 = max_bottom[0]
            hit_y = max_bottom[1]
            if getattr(entity, "can_crush_all_blocks", False):
                try:
                    entity._crush_queue.append(hit_y)
                except Exception:
                    pass
    if hit_y is not None:
        entity._hit_ob = hit_y
    x_min, y_min, x_max, y_max = play_bounds_for_circle(r)
    cy1 = max(y_min, min(cy1, y_max))
    # 应用Y位移（注意把 INFO_BAR_HEIGHT 减回去）
    entity.y = cy1 - size * 0.5 - INFO_BAR_HEIGHT
    # 同步 AABB（仅用于渲染/命中盒）
    entity.rect.x = int(entity.x)
    entity.rect.y = int(entity.y) + INFO_BAR_HEIGHT


# === NEW: 等距相机偏移（基于玩家像素中心 → 网格中心 → 屏幕等距投影） ===
def calculate_iso_camera(player_x_px: float, player_y_px: float) -> tuple[int, int]:
    px_grid = player_x_px / CELL_SIZE
    py_grid = player_y_px / CELL_SIZE
    # 投到屏幕（不带 cam 偏移）
    pxs, pys = iso_world_to_screen(px_grid, py_grid, 0.0, 0.0, 0.0)
    camx = pxs - VIEW_W // 2
    camy = pys - (VIEW_H - INFO_BAR_HEIGHT) // 2
    return int(camx), int(camy)


def draw_button(screen, label, pos, size=(180, 56), bg=(40, 40, 40), fg=(240, 240, 240), border=(15, 15, 15)):
    rect = pygame.Rect(pos, size)
    pygame.draw.rect(screen, border, rect.inflate(6, 6))
    pygame.draw.rect(screen, bg, rect)
    font = pygame.font.SysFont(None, 32)
    txt = font.render(label, True, fg)
    screen.blit(txt, txt.get_rect(center=rect.center))
    return rect


def hex_points_flat(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    """Canonical flat-top hex vertices (6 points, clockwise, sharing edges)."""
    pts = []
    for i in range(6):
        ang = math.radians(-60 * i)  # 0deg at +X for a flat-top layout
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts

# ==================== NEURO MUSIC VISUALIZATION ====================

class AudioAnalyzer:
    """
    Embedded analyzer using librosa to generate spectrogram data for visualization.
    Refactored from AudioAnalyzer.py for Game integration.
    Now includes caching to avoid re-analyzing the same BGM file every time.
    """
    def __init__(self):
        self.spectrogram = None
        self.frequencies_index_ratio = 0
        self.time_index_ratio = 0
        self.duration = 0.0
        self.loaded = False

    def _get_cache_path(self, filename):
        """Generate cache file path. Only cache the homepage Intro track to avoid multiple files."""
        try:
            name = os.path.basename(filename).lower()
            if "intro_v0" not in name:
                return None  # skip caching for non-homepage tracks to avoid extra npz files
            cache_dir = os.path.join(os.path.dirname(__file__) if "__file__" in globals() else os.getcwd(), "TEMP")
            os.makedirs(cache_dir, exist_ok=True)
            return os.path.join(cache_dir, "audio_analysis_intro_v0.npz")
        except Exception:
            return None

    def _load_from_cache(self, cache_path):
        """Load analysis results from cache file."""
        try:
            if not cache_path or not os.path.exists(cache_path):
                return False
            data = np.load(cache_path)
            self.spectrogram = data['spectrogram']
            self.time_index_ratio = float(data['time_index_ratio'])
            self.frequencies_index_ratio = float(data['frequencies_index_ratio'])
            self.duration = float(data['duration'])
            self.loaded = True
            print(f"[AudioAnalyzer] Loaded from cache: {cache_path}")
            return True
        except Exception as e:
            print(f"[AudioAnalyzer] Cache load failed: {e}")
            return False

    def _save_to_cache(self, cache_path):
        """Save analysis results to cache file."""
        try:
            if not cache_path or self.spectrogram is None:
                return False
            np.savez_compressed(
                cache_path,
                spectrogram=self.spectrogram,
                time_index_ratio=self.time_index_ratio,
                frequencies_index_ratio=self.frequencies_index_ratio,
                duration=self.duration
            )
            print(f"[AudioAnalyzer] Saved to cache: {cache_path}")
            return True
        except Exception as e:
            print(f"[AudioAnalyzer] Cache save failed: {e}")
            return False

    def load(self, filename):
        """Load and analyze audio file, using cache if available."""
        if not filename or not os.path.exists(filename):
            self.loaded = False
            return
        
        # Try to load from cache first (only for Intro_V0)
        cache_path = self._get_cache_path(filename)
        if cache_path and self._load_from_cache(cache_path):
            return  # Successfully loaded from cache
        
        # Cache miss or invalid - perform analysis
        try:
            print(f"[AudioAnalyzer] Analyzing {filename} (this may take a moment)...")
            # Load with librosa
            time_series, sample_rate = librosa.load(filename)
            
            # STFT -> Spectrogram (Decibels)
            # Using parameters tuned for visualizer responsiveness
            stft = np.abs(librosa.stft(time_series, hop_length=512, n_fft=2048*2))
            self.spectrogram = librosa.amplitude_to_db(stft, ref=np.max)
            
            frequencies = librosa.core.fft_frequencies(n_fft=2048*2)
            times = librosa.core.frames_to_time(np.arange(self.spectrogram.shape[1]), sr=sample_rate, hop_length=512, n_fft=2048*2)

            self.time_index_ratio = len(times) / times[-1] if len(times) > 0 else 0
            self.frequencies_index_ratio = len(frequencies) / frequencies[-1] if len(frequencies) > 0 else 0
            self.duration = float(times[-1]) if len(times) > 0 else 0.0
            self.loaded = True
            print(f"[AudioAnalyzer] Analysis complete for {filename}")
            
            # Save to cache for next time
            if cache_path:
                self._save_to_cache(cache_path)
        except Exception as e:
            print(f"[AudioAnalyzer] Failed to analyze {filename}: {e}")
            self.loaded = False
            self.duration = 0.0

    def get_decibel(self, target_time, freq):
        if not self.loaded or self.spectrogram is None:
            return -80 # silence
        
        # Wrap/guard time so looping BGM stays in-range
        if self.duration > 0:
            target_time = target_time % self.duration
        if target_time < 0:
            target_time = 0
        
        t_idx = int(target_time * self.time_index_ratio)
        f_idx = int(freq * self.frequencies_index_ratio)
        
        # Clamp indices
        if t_idx < 0: t_idx = 0
        if t_idx >= self.spectrogram.shape[1]: t_idx = self.spectrogram.shape[1] - 1
        if f_idx >= self.spectrogram.shape[0]: f_idx = self.spectrogram.shape[0] - 1
        
        return self.spectrogram[f_idx][t_idx]

class NeuroMusicVisualizer:
    """
    Real-time frequency visualizer in Neuroscape style.
    Replaces the old 'fake' waveform visualizer.
    """
    def __init__(self):
        self.analyzer = AudioAnalyzer()
        self.bars = []
        self.radius = 120
        self.min_radius = 120
        self.max_radius = 140
        self.radius_vel = 0
        
        # Visualization Config
        self.circle_color = (6, 10, 16) # Navy Dark
        self.poly_color = [70, 230, 255] # Neuro Cyan
        self.poly_color_default = [70, 230, 255]
        self.poly_color_bass = [180, 100, 255] # Purple tinge on bass kick
        
        # Frequency Bands definition (Hz)
        self.freq_groups = [
            {"start": 50, "stop": 100, "count": 10},    # Sub Bass
            {"start": 120, "stop": 250, "count": 25},   # Bass
            {"start": 251, "stop": 2000, "count": 40},  # Mids
            {"start": 2001, "stop": 6000, "count": 15}  # Highs
        ]
        
        self._init_bars()
        
    def _init_bars(self):
        self.bars = []
        # Create bar definitions
        total_bars = sum(g["count"] for g in self.freq_groups)
        angle_step = 360 / total_bars
        current_angle = 0
        
        for group in self.freq_groups:
            step = (group["stop"] - group["start"]) / group["count"]
            rng = group["start"]
            
            for _ in range(group["count"]):
                # Store freq range and current angle for this bar
                # Use a small range around the center freq for averaging
                freq_rng = np.arange(rng, rng + step + 1)
                self.bars.append({
                    "freq_rng": freq_rng,
                    "angle": current_angle,
                    "val": 0.0, # current height/value
                    "x": 0, "y": 0 # screen pos
                })
                rng += step
                current_angle += angle_step

    def load_music(self, path):
        if path:
            self.analyzer.load(path)

    def update(self, dt, music_pos_seconds):
        if not self.analyzer.loaded:
            return
        
        # Keep playback position in track range so looping songs stay synced
        if self.analyzer.duration > 0:
            music_pos_seconds = music_pos_seconds % self.analyzer.duration
        elif music_pos_seconds < 0:
            music_pos_seconds = 0.0

        # 1. Update bars based on spectrogram
        avg_bass = 0
        bass_count = 0
        
        for i, bar in enumerate(self.bars):
            # Sample Db
            db_sum = 0
            for f in bar["freq_rng"]:
                db_sum += self.analyzer.get_decibel(music_pos_seconds, f)
            avg_db = db_sum / len(bar["freq_rng"])
            
            # Normalize Db (-80 to 0) to (0 to 1) roughly
            # Noise floor usually -80db
            val = (avg_db + 80) / 80.0
            val = max(0.0, val) # Clamp
            
            # Smooth interpolation
            # Determine target height (scale factor)
            target = val * 80 # Max extra height 80px
            
            # Apply to bar value with smoothing
            bar["val"] += (target - bar["val"]) * 15 * dt
            
            # Track bass for the circle pump effect
            # First group is sub bass
            if i < self.freq_groups[0]["count"]:
                avg_bass += val
                bass_count += 1

        # 2. Update Central Circle Pump (Bass kick)
        if bass_count > 0:
            avg_bass /= bass_count
        
        # Threshold for "Beat"
        bass_trigger = 0.65 
        
        if avg_bass > bass_trigger:
            target_r = self.max_radius + (avg_bass - bass_trigger) * 60
            self.radius_vel = (target_r - self.radius) * 10
            # Shift color towards bass color
            for c in range(3):
                self.poly_color[c] += (self.poly_color_bass[c] - self.poly_color[c]) * 5 * dt
        else:
            self.radius_vel += (self.min_radius - self.radius) * 8 * dt # spring back
            # Shift color back to default
            for c in range(3):
                self.poly_color[c] += (self.poly_color_default[c] - self.poly_color[c]) * 5 * dt
                
        self.radius += self.radius_vel * dt
        
        # Dampening
        self.radius_vel *= 0.9

    def draw(self, screen, center_x, center_y):
        if not self.analyzer.loaded:
            # Fallback idle animation if no music loaded
            pygame.draw.circle(screen, self.circle_color, (center_x, center_y), int(self.min_radius), 2)
            return

        poly_points = []
        
        # Calculate vertices
        for bar in self.bars:
            # r = base radius + bar height
            r = self.radius + bar["val"]
            rad = math.radians(bar["angle"] - 90)
            
            x = center_x + math.cos(rad) * r
            y = center_y + math.sin(rad) * r
            # Cast to int to avoid pygame rejecting numpy/float coordinate pairs
            poly_points.append((int(round(x)), int(round(y))))
            
        if len(poly_points) > 2:
            # Clamp colors to valid pygame ints
            poly_col = tuple(max(0, min(255, int(round(c)))) for c in self.poly_color)
            circle_col = tuple(max(0, min(255, int(round(c)))) for c in self.circle_color)
            # Draw the filled shape (Navy background)
            pygame.draw.polygon(screen, circle_col, poly_points)
            # Draw the neon outline
            pygame.draw.polygon(screen, poly_col, poly_points, 3)
            
        # Draw inner decorative ring
        pygame.draw.circle(screen, (30, 40, 50), (center_x, center_y), int(self.radius * 0.8), 1)

# Global Instance
_neuro_viz = NeuroMusicVisualizer()
_neuro_viz_loader: threading.Thread | None = None
_neuro_viz_loader_path: str | None = None

# ==================== HEX TRANSITION SYSTEM (GEOMETRY SCALE) ====================

class HexCell:
    __slots__ = ("cx", "cy", "max_r", "trigger_delay", "current_scale", "points")

    def __init__(self, cx, cy, r):
        self.cx = float(cx)
        self.cy = float(cy)
        self.max_r = float(r)
        self.trigger_delay = 0.0
        self.current_scale = 0.0  # 0.0 = Invisible, 1.2 = Fully covering
        self.points = hex_points_flat(self.cx, self.cy, self.max_r)

def build_hex_grid(view_w: int, view_h: int, r: int = 50) -> list[HexCell]:
    # Slightly larger radius (50) for better performance on geometry calc
    size = float(r)
    step_x = size * 1.5
    step_y = math.sqrt(3) * size
    
    margin = size * 2.0
    cols = int(math.ceil((view_w + margin * 2) / step_x)) + 2
    rows = int(math.ceil((view_h + margin * 2) / step_y)) + 2
    
    cells = []
    start_x = -margin
    start_y = -margin
    
    for col in range(cols):
        for row in range(rows):
            x = start_x + col * step_x
            y = start_y + row * step_y
            if col % 2 != 0:
                y += step_y / 2.0
            
            # Bound check
            if x < -margin * 2 or x > view_w + margin * 2: continue
            if y < -margin * 2 or y > view_h + margin * 2: continue
            
            cells.append(HexCell(x, y, size))
    return cells

class HexTransition:
    def __init__(self, grid: list[HexCell]):
        self.grid = grid
        
        # --- Visual Config ---
        self.COLOR_FILL = (6, 10, 16)       # Deep Navy/Black background (darker)
        self.COLOR_OUTLINE = (70, 230, 255)  # Cyan Neon aligned to homepage
        self.OUTLINE_WIDTH = 2
        
        # --- Timing ---
        self.duration_in = 0.25    # Grow time
        self.duration_hold = 0.10  # Time to stay fully black
        self.duration_out = 0.25   # Shrink time 
       
        # State
        self.timer = 0.0
        self.state = "IDLE"
        self.midpoint_triggered = False

    def _get_delay(self, cell):
        # Randomize between vertical band and radial circle wipes for variety
        if random.random() < 0.5:
            # vertical banding: center row triggers first
            cx, cy = VIEW_W // 2, VIEW_H // 2
            dist = abs(cell.cy - cy)
            max_dist = (VIEW_H / 2.0) or 1.0
            norm_band = min(1.0, dist / max_dist)
            return norm_band * 0.55 + random.random() * 0.06
        else:
            # radial wipe: center triggers first
            cx, cy = VIEW_W // 2, VIEW_H // 2
            dist = math.hypot(cell.cx - cx, cell.cy - cy)
            max_dist = math.hypot(VIEW_W, VIEW_H) / 2.0
            norm_dist = min(1.0, dist / max_dist)
            return norm_dist * 0.55 + random.uniform(0, 0.08)

    def start(self):
        self.timer = 0.0
        self.state = "CLOSING" # Growing hexes to cover screen
        self.midpoint_triggered = False
        
        # Calculate delays
        for cell in self.grid:
            cell.trigger_delay = self._get_delay(cell)
            cell.current_scale = 0.0

    def is_active(self):
        return self.state != "IDLE"

    def should_swap_screens(self):
        if self.state == "HOLDING" and not self.midpoint_triggered:
            self.midpoint_triggered = True
            return True
        return False

    def update(self, dt: float):
        if self.state == "IDLE": return

        self.timer += dt

        # PHASE 1: GROW (Cover Screen)
        if self.state == "CLOSING":
            done_count = 0
            for cell in self.grid:
                start_t = cell.trigger_delay * 0.65
                actual_t = (self.timer - start_t) / max(0.001, self.duration_in * 0.7)
                t_clamped = max(0.0, min(1.0, actual_t))
                ease = t_clamped * t_clamped * (3.0 - 2.0 * t_clamped)
                cell.current_scale = min(1.0, ease)  # cap to avoid overlap
                if cell.current_scale >= 0.995:
                    done_count += 1
            if done_count >= len(self.grid) or self.timer > self.duration_in + 0.4:
                self.state = "HOLDING"
                self.timer = 0.0

        # PHASE 2: HOLD (Swap content behind)
        elif self.state == "HOLDING":
            # Force all to max scale to ensure black screen
            for cell in self.grid: cell.current_scale = 1.2 
            
            if self.timer >= self.duration_hold:
                self.state = "OPENING"
                self.timer = 0.0

        # PHASE 3: SHRINK (Reveal new screen)
        elif self.state == "OPENING":
            done_count = 0
            for cell in self.grid:
                start_t = cell.trigger_delay * 0.65
                actual_t = (self.timer - start_t) / max(0.001, self.duration_out * 0.7)
                t_clamped = max(0.0, min(1.0, actual_t))
                ease = t_clamped * t_clamped * (3.0 - 2.0 * t_clamped)
                cell.current_scale = max(0.0, 1.0 - ease)
                if cell.current_scale <= 0.01:
                    done_count += 1
            if done_count >= len(self.grid) or self.timer > self.duration_out + 0.4:
                self.state = "IDLE"

    def draw(self, screen: pygame.Surface):
        if self.state == "IDLE": return

        # Standard flat-top hex angles
        angles = [math.radians(a) for a in (0, 60, 120, 180, 240, 300)]
        center_y = VIEW_H * 0.5
        max_band = max(1.0, VIEW_H * 0.5)
        overlay = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
        veil = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
        if self.state == "CLOSING":
            cover_alpha = 230
        elif self.state == "HOLDING":
            cover_alpha = 255
        else:  # OPENING
            cover_alpha = int(200 * max(0.0, 1.0 - self.timer / max(0.001, self.duration_out)))
        veil.fill((0, 0, 0, cover_alpha))
        screen.blit(veil, (0, 0))

        for cell in self.grid:
            # OPTIMIZATION: Don't draw if invisible
            if cell.current_scale <= 0.01: continue
            cx, cy = cell.cx, cell.cy
            # Fixed outline geometry (shared edges)
            outline_points = cell.points
            # Scaled fill geometry
            draw_scale = max(0.0, min(1.0, cell.current_scale)) * 0.92
            fill_points = []
            for ang in angles:
                px = cx + cell.max_r * math.cos(ang)
                py = cy + cell.max_r * math.sin(ang)
                fill_points.append((cx + (px - cx) * draw_scale, cy + (py - cy) * draw_scale))

            # 修改点：高亮因子改为径向计算，中心亮四周暗
            dist_center = math.hypot(cell.cx - VIEW_W // 2, cell.cy - VIEW_H // 2)
            band_factor = 1.0 - min(1.0, dist_center / (VIEW_H * 0.6))

            # 3. Draw Fill
            # 稍微降低填充不透明度，让背景在动画早期稍微透一点点气
            fill_alpha = int(max(0, min(255, 255 * max(0.6, draw_scale))))
            pygame.draw.polygon(overlay, (*self.COLOR_FILL, fill_alpha), fill_points)
            
            # 4. Draw Outline
            # 修改点：大幅降低描边透明度(220 -> 160)，防止小格子密集时过于刺眼
            outline_base = 160 * (0.4 + 0.6 * band_factor)
            outline_alpha = int(max(0, min(255, 220 * (0.5 + 0.5 * band_factor) * max(0.3, draw_scale))))
            pygame.draw.polygon(overlay, (*self.COLOR_OUTLINE, outline_alpha), outline_points, self.OUTLINE_WIDTH)
        screen.blit(overlay, (0, 0))

# Global transition resources (lazy init)
_hex_grid_cache: list[HexCell] | None = None
_hex_transition: HexTransition | None = None
_hex_bg_surface: pygame.Surface | None = None
_menu_transition_frame: pygame.Surface | None = None
_skip_intro_once = False

def ensure_hex_transition():
    global _hex_grid_cache, _hex_transition
    if _hex_grid_cache is None:
        _hex_grid_cache = build_hex_grid(VIEW_W, VIEW_H, r=int(max(90, VIEW_W * 0.075)))
    # upgrade any existing cells to have points for static outlines
    for cell in _hex_grid_cache:
        if not hasattr(cell, "points"):
            try:
                cell.points = hex_points_flat(cell.cx, cell.cy, cell.max_r)
            except Exception:
                pass
    if _hex_transition is None:
        _hex_transition = HexTransition(_hex_grid_cache)
    return _hex_transition


def ensure_hex_background():
    global _hex_bg_surface, _hex_grid_cache
    if _hex_bg_surface is not None:
        return _hex_bg_surface
    if _hex_grid_cache is None:
        _hex_grid_cache = build_hex_grid(VIEW_W, VIEW_H, r=int(max(90, VIEW_W * 0.08)))
    for cell in _hex_grid_cache:
        if not hasattr(cell, "points"):
            cell.points = hex_points_flat(cell.cx, cell.cy, cell.max_r)
    surf = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    # gradient fill
    top_col = (12, 26, 32)
    bot_col = (6, 88, 110)
    for y in range(VIEW_H):
        t = y / max(1, VIEW_H - 1)
        col = (
            int(top_col[0] * (1 - t) + bot_col[0] * t),
            int(top_col[1] * (1 - t) + bot_col[1] * t),
            int(top_col[2] * (1 - t) + bot_col[2] * t),
        )
        pygame.draw.line(surf, col, (0, y), (VIEW_W, y))
    # outlines (true edge-aligned hexes)
    outline_col = (70, 230, 255, 170)
    for cell in _hex_grid_cache:
        pygame.draw.polygon(surf, outline_col, cell.points, width=2)
    _hex_bg_surface = surf
    return _hex_bg_surface


def queue_menu_transition(frame: pygame.Surface):
    """Cache the menu frame so the next scene can run the hex shutter using a live target frame."""
    global _menu_transition_frame
    _menu_transition_frame = frame


def run_pending_menu_transition(screen: pygame.Surface):
    """If a menu frame is queued, run the hex transition onto the already-rendered scene on screen."""
    global _menu_transition_frame
    if _menu_transition_frame is None:
        return
    from_surf = _menu_transition_frame
    to_surf = screen.copy()
    play_hex_transition(screen, from_surf, to_surf, direction="down")
    _menu_transition_frame = None


def play_hex_transition(screen: pygame.Surface, from_surface: pygame.Surface, to_surface: pygame.Surface,
                        direction: str = "down"):
    """
    Blocking helper that plays the full hex animation.
    1. Plays Close animation over from_surface.
    2. Swaps to to_surface when fully dark.
    3. Plays Open animation over to_surface.
    """
    trans = ensure_hex_transition()
    trans.start()
    
    clock = pygame.time.Clock()
    current_bg = from_surface
    
    while trans.is_active():
        dt = clock.tick(60) / 1000.0
        
        # Handle events to prevent OS thinking the app froze
        pygame.event.pump() 
        
        trans.update(dt)
        
        # The Midpoint Swap:
        # Check if the transition has reached the point where we switch backgrounds
        if trans.should_swap_screens(): 
            current_bg = to_surface
            
        # Draw Sequence
        # 1. Draw the underlying game/menu state (current_bg)
        if current_bg:
            screen.blit(current_bg, (0, 0))
            
        # 2. Draw the Hex Overlay on top
        trans.draw(screen)
        
        pygame.display.flip()
        
    flush_events()


def compute_player_dps(p: "Player" | None) -> float:
    # TODO
    # Add visual effect for bandit (growing circle around bandit)
    # Add same hint display for bosses (optional)
    # Add a exeution CG like scenefor bosses(slow time, whole scene become red in backgrounf and black in figures)
    if p is None:
        # 兜底：用 META 粗估
        base_dmg = BULLET_DAMAGE_ENEMY + float(META.get("dmg", 0))
        # 使用玩家默认冷却推导攻速
        dummy = 1.0 / max(1e-6, FIRE_COOLDOWN / max(0.1, float(META.get("firerate_mult", 1.0))))
        cc = float(META.get("crit", 0.0))
        cm = float(CRIT_MULT_BASE)
        return base_dmg * dummy * (1.0 + max(0.0, min(1.0, cc)) * (cm - 1.0))
    dmg = float(getattr(p, "bullet_damage", BULLET_DAMAGE_ENEMY + META.get("dmg", 0)))
    sps = 1.0 / max(1e-6, p.fire_cooldown())  # 用 Player 的实际冷却（含攻速加成）
    cc = max(0.0, min(1.0, float(getattr(p, "crit_chance", 0.0))))
    cm = float(getattr(p, "crit_mult", CRIT_MULT_BASE))
    return dmg * sps * (1.0 + cc * (cm - 1.0))


def draw_settings_gear(screen, x, y):
    """Draw a simple gear icon at (x,y) top-left; returns its rect."""
    rect = pygame.Rect(x, y, 32, 24)
    # outer
    pygame.draw.rect(screen, (50, 50, 50), rect, 2)
    # gear: circle + spokes
    cx, cy = x + 16, y + 12
    pygame.draw.circle(screen, (200, 200, 200), (cx, cy), 8, 2)
    pygame.draw.circle(screen, (200, 200, 200), (cx, cy), 3)
    for ang in (0, 60, 120, 180, 240, 300):
        rad = math.radians(ang)
        x1 = int(cx + 10 * math.cos(rad))
        y1 = int(cy + 10 * math.sin(rad))
        x2 = int(cx + 14 * math.cos(rad))
        y2 = int(cy + 14 * math.sin(rad))
        pygame.draw.line(screen, (200, 200, 200), (x1, y1), (x2, y2), 2)
    return rect


INSTRUCTION_LINES = [
    "WASD to move. Survive until the timer hits 00:00 to win.",
    "Break yellow blocks to reach hidden fragments.",
    "Enemies deal contact damage. Avoid or kite them.",
    "Auto-fire targets the closest enemy/block in range.",
    "Bandits: Radar tags them in red; intercept before they flee.",
    "Shop between levels to upgrade (turrets, bullets, economy).",
    "Lockbox protects a portion of coins; Golden Interest pays interest.",
    "Pause: ESC to open menu; Restart/Home keep your meta upgrades.",
]
INSTRUCTION_Y_START = 110
INSTRUCTION_LINE_SPACING = 38


def neuro_instruction_layout():
    panel_rect = pygame.Rect(int(VIEW_W * 0.14), int(VIEW_H * 0.26),
                             int(VIEW_W * 0.72), int(VIEW_H * 0.48))
    back_rect = pygame.Rect(0, 0, 220, 60)
    back_rect.center = (VIEW_W // 2, panel_rect.bottom + 70)
    return panel_rect, back_rect


def draw_neuro_instruction(surface: pygame.Surface, t: float, *, hover_back: bool,
                           title_font, body_font, btn_font):
    panel_rect, back_rect = neuro_instruction_layout()
    draw_neuro_waves(surface, t)
    title = title_font.render("INSTRUCTION", True, (220, 240, 255))
    surface.blit(title, title.get_rect(center=(VIEW_W // 2, int(VIEW_H * 0.16))))
    panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
    pygame.draw.rect(panel, (14, 32, 50, 140), panel.get_rect(), border_radius=18)
    pygame.draw.rect(panel, (80, 200, 255, 180), panel.get_rect(), width=2, border_radius=18)
    y = 26
    for line in INSTRUCTION_LINES:
        txt = body_font.render(line, True, (200, 225, 245))
        panel.blit(txt, (24, y))
        y += txt.get_height() + 12
    surface.blit(panel, panel_rect.topleft)
    drawn_back = draw_neuro_button(surface, back_rect, "BACK", btn_font,
                                   hovered=hover_back, disabled=False, t=t)
    return drawn_back


def render_instruction_surface():
    surf = ensure_neuro_background().copy()
    body_font = pygame.font.SysFont("Consolas", 20)
    title_font = pygame.font.SysFont("Consolas", 34, bold=True)
    btn_font = pygame.font.SysFont(None, 30)
    draw_neuro_instruction(surf, 0.0, hover_back=False,
                           title_font=title_font, body_font=body_font, btn_font=btn_font)
    return surf


# --- Neuro console start menu visuals ---
_neuro_bg_surface: pygame.Surface | None = None
_neuro_log_seed = random.getrandbits(24)
_NEURO_SYSTEM_MESSAGES = [
    "link stable. awaiting neural sync...",
    "bioscan: green. cortex latency 12ms.",
    "encryption tunnel alive. tracing ghosts...",
    "memory shards indexed. ready for run.",
    "diagnostics clean. no corruption detected.",
    "entropy pool topped. firing neurons.",
]
_intro_star_far: list[tuple[float, float, float, int]] = []
_intro_star_near: list[tuple[float, float, float, int]] = []
_intro_columns: list[tuple[float, float, float]] = []


def _seed_intro_layers():
    """Lazily build procedural starfield/column seeds so the intro stays image-free."""
    global _intro_star_far, _intro_star_near, _intro_columns
    rng = random.Random(_neuro_log_seed ^ 0xA51D)
    if not _intro_star_far:
        _intro_star_far = [
            (rng.uniform(0, VIEW_W), rng.uniform(0, VIEW_H), rng.random() * math.tau, rng.choice([1, 1, 2]))
            for _ in range(180)
        ]
    if not _intro_star_near:
        _intro_star_near = [
            (rng.uniform(0, VIEW_W), rng.uniform(0, VIEW_H), rng.random() * math.tau, rng.choice([2, 3]))
            for _ in range(110)
        ]
    if not _intro_columns:
        _intro_columns = [
            (rng.uniform(0.05, 0.95) * VIEW_W, rng.uniform(0.45, 0.75), rng.random() * math.tau)
            for _ in range(11)
        ]


def ensure_neuro_background():
    """Procedural neon backdrop; no external art required."""
    global _neuro_bg_surface
    if _neuro_bg_surface is not None:
        return _neuro_bg_surface
    _seed_intro_layers()
    surf = pygame.Surface((VIEW_W, VIEW_H))
    # vertical gradient with a glowing horizon
    for y in range(VIEW_H):
        t = y / max(1, VIEW_H - 1)
        col = (
            int(6 + 14 * (1 - t) + 6 * t),
            int(12 + 44 * t),
            int(24 + 82 * t),
        )
        pygame.draw.line(surf, col, (0, y), (VIEW_W, y))
    horizon = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    glow_center = (VIEW_W // 2, int(VIEW_H * 0.70))
    max_r = int(math.hypot(VIEW_W, VIEW_H) * 0.60)
    for r in range(max_r, 0, -12):
        fade = max(0.0, 1.0 - r / max_r)
        alpha = int(110 * (fade ** 1.25))
        if alpha <= 0:
            continue
        color = (20, 90 + int(60 * fade), 190 + int(26 * fade), alpha)
        pygame.draw.circle(horizon, color, glow_center, r)
    surf.blit(horizon, (0, 0), special_flags=pygame.BLEND_ADD)
    # aurora-style ribbons
    ribbon = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    rng = random.Random(_neuro_log_seed ^ 0x8A11)
    for i in range(7):
        x0 = int(-VIEW_W * 0.25 + i * VIEW_W * 0.22 + rng.randint(-30, 30))
        x1 = x0 + int(VIEW_W * 0.65)
        y0 = int(VIEW_H * (0.15 + 0.02 * i))
        y1 = int(VIEW_H * 0.9)
        col = (38 + i * 6, 140 + i * 8, 220, 16 + i * 5)
        pygame.draw.polygon(ribbon, col, [(x0, y0), (x1, y0 + 40), (x1 - 120, y1), (x0 - 80, y1 - 60)])
    surf.blit(ribbon, (0, 0), special_flags=pygame.BLEND_ADD)
    # soft techno grid
    grid = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    spacing = 32
    for y in range(0, VIEW_H, spacing):
        alpha = max(10, int(36 * (1 - abs((y - VIEW_H * 0.55) / (VIEW_H * 0.7)))))
        pygame.draw.line(grid, (18, 60, 86, alpha), (0, y), (VIEW_W, y))
    for x in range(0, VIEW_W, spacing):
        alpha = max(8, int(32 * (1 - abs((x - VIEW_W * 0.5) / (VIEW_W * 0.7)))))
        pygame.draw.line(grid, (18, 60, 86, alpha), (x, 0), (x, VIEW_H))
    surf.blit(grid, (0, 0))
    # star specks for depth
    dust = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    for _ in range(180):
        px, py = rng.randrange(VIEW_W), rng.randrange(VIEW_H)
        alpha = rng.randrange(12, 44)
        pygame.draw.circle(dust, (60, 150, 210, alpha), (px, py), 1)
    surf.blit(dust, (0, 0), special_flags=pygame.BLEND_ADD)
    # subtle depth darkening to avoid flat layering
    depth_mask = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    for y in range(VIEW_H):
        fade = abs((y - VIEW_H * 0.55) / (VIEW_H * 0.55))
        alpha = int(95 * (fade ** 1.25))
        if alpha <= 0:
            continue
        pygame.draw.line(depth_mask, (0, 0, 0, alpha), (0, y), (VIEW_W, y))
    surf.blit(depth_mask, (0, 0))
    vignette = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    edge_r = int(math.hypot(VIEW_W * 0.5, VIEW_H * 0.5))
    for r in range(edge_r, 0, -28):
        fade = 1.0 - r / edge_r
        alpha = int(120 * (fade ** 1.35))
        if alpha <= 0:
            continue
        pygame.draw.circle(vignette, (0, 0, 0, alpha), (VIEW_W // 2, VIEW_H // 2), r)
    surf.blit(vignette, (0, 0))
    _neuro_bg_surface = surf
    return _neuro_bg_surface


def _draw_intro_starfield(surface: pygame.Surface, t: float) -> None:
    """Animated parallax starfield for the intro."""
    _seed_intro_layers()
    overlay = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    for x, y, phase, size in _intro_star_far:
        px = (x + t * 12.0) % VIEW_W
        twinkle = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(phase + t * 0.55))
        alpha = int(48 * twinkle)
        pygame.draw.circle(overlay, (70, 130, 180, alpha), (int(px), int(y)), size)
    for x, y, phase, size in _intro_star_near:
        px = (x - t * 26.0) % VIEW_W
        twinkle = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(phase + t * 1.1))
        alpha = int(118 * twinkle)
        col = (120, 210, 240, alpha)
        pygame.draw.circle(overlay, col, (int(px), int(y)), size)
        tail_len = 10 + size * 2
        pygame.draw.line(
            overlay,
            (col[0], col[1], col[2], int(alpha * 0.6)),
            (int(px - tail_len * 0.6), int(y - 2)),
            (int(px + tail_len * 0.4), int(y + 2)),
            1,
        )
    surface.blit(overlay, (0, 0), special_flags=pygame.BLEND_ADD)


def _draw_intro_datastreams(surface: pygame.Surface, t: float) -> None:
    """Tall, translucent pillars that feel like stacked neural towers."""
    _seed_intro_layers()
    overlay = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    base_col = (60, 170, 220)
    for idx, (x0, h_factor, phase) in enumerate(_intro_columns):
        sway = math.sin(t * (0.7 + idx * 0.05) + phase) * (24 + idx * 1.5)
        x = int(x0 + sway)
        h = int(VIEW_H * h_factor)
        top = VIEW_H - h
        width = 14 + (idx % 3) * 6
        alpha = max(40, min(140, int(100 + 60 * math.sin(t * 1.4 + phase * 1.7))))
        col = (base_col[0] - idx * 2, base_col[1], 235, alpha)
        pts = [
            (x - width, VIEW_H),
            (x + width, VIEW_H),
            (x + int(width * 1.4), top + 32),
            (x - int(width * 1.4), top),
        ]
        pygame.draw.polygon(overlay, col, pts)
        pygame.draw.polygon(overlay, (col[0], col[1], col[2], min(200, alpha + 20)), pts, 2)
        pygame.draw.rect(
            overlay,
            (190, 230, 240, max(30, alpha // 2)),
            pygame.Rect(x - width + 2, top + 8, width * 2 - 4, 6),
            border_radius=4,
        )
    surface.blit(overlay, (0, 0))


def _draw_intro_holo_core(surface: pygame.Surface, t: float) -> None:
    """Central holographic orb with orbiting shards."""
    cx, cy = VIEW_W // 2, int(VIEW_H * 0.46)
    orb_size = 520
    orb = pygame.Surface((orb_size, orb_size), pygame.SRCALPHA)
    oc = orb_size // 2
    base_r = 150 + 12 * math.sin(t * 0.8)
    for i in range(12):
        r = int(base_r - i * 7)
        if r <= 0:
            break
        alpha = max(0, 150 - i * 12)
        color = (30 + i * 5, 150 + i * 4, 230, alpha)
        pygame.draw.circle(orb, color, (oc, oc), r, 1)
    # meridians
    for i in range(6):
        ang = (i / 6.0) * math.pi + 0.4 * math.sin(t * 0.45 + i)
        pts = []
        for j in range(-50, 51):
            lat = j / 50.0
            rr = base_r * math.cos(lat * 0.9)
            x = oc + math.cos(ang) * rr
            y = oc + math.sin(lat) * base_r * 0.65
            pts.append((x, y))
        pygame.draw.aalines(orb, (100, 210, 235, 72), False, pts, 1)
    # latitudes
    for i in range(-2, 3):
        ry = base_r * (0.35 + 0.22 * (2 - abs(i)))
        rx = base_r * 1.02
        col_a = 90 + i * 10
        pygame.draw.ellipse(orb, (80, 180, 230, col_a), pygame.Rect(oc - rx, oc - ry, rx * 2, ry * 2), 1)
    ring_radii = [int(base_r + 28), int(base_r + 58), int(base_r + 96)]
    for idx, r in enumerate(ring_radii):
        start = (t * (0.6 + idx * 0.18) + idx * 0.9) % (2 * math.pi)
        span = math.pi * (1.1 + 0.08 * math.sin(t * 0.7 + idx))
        col = (120, 230 - idx * 14, 240, 130 - idx * 16)
        pygame.draw.arc(orb, col, (oc - r, oc - r, 2 * r, 2 * r), start, start + span, 3)
        pygame.draw.arc(orb, col, (oc - r, oc - r, 2 * r, 2 * r), start + math.pi * 1.05, start + math.pi * 1.05 + span * 0.7, 2)
    # orbiting shards
    shards = 12
    for i in range(shards):
        ang = t * 0.65 + i * (math.tau / shards)
        rad = base_r + 80 + 26 * math.sin(t * 1.3 + i)
        px = oc + math.cos(ang) * rad
        py = oc + math.sin(ang) * rad * 0.55
        sz = 14 + (i % 4) * 3
        tri = [
            (px + math.cos(ang) * sz, py + math.sin(ang) * sz),
            (px + math.cos(ang + 2.1) * sz * 0.6, py + math.sin(ang + 2.1) * sz * 0.6),
            (px + math.cos(ang - 2.1) * sz * 0.6, py + math.sin(ang - 2.1) * sz * 0.6),
        ]
        pygame.draw.polygon(orb, (70 + (i * 12) % 90, 190, 235, 130), tri, 1)
    surface.blit(orb, (cx - oc, cy - oc), special_flags=pygame.BLEND_PREMULTIPLIED)


def _draw_intro_scanlines(surface: pygame.Surface, t: float) -> None:
    """Sweeping scan strip to make the scene feel like a live console feed."""
    overlay = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    stripe_h = 90
    sweep_y = (t * 120.0) % (VIEW_H + stripe_h) - stripe_h
    rect = pygame.Rect(0, int(sweep_y), VIEW_W, stripe_h)
    pygame.draw.rect(overlay, (20, 80, 120, 38), rect)
    pygame.draw.rect(overlay, (80, 200, 255, 48), rect, 2)
    surface.blit(overlay, (0, 0), special_flags=pygame.BLEND_ADD)


def _neuro_outline_points(cx: int, cy: int) -> list[tuple[float, float]]:
    """Return the current NeuroViz polygon points, falling back to a circle if unavailable."""
    try:
        if "_neuro_viz" in globals() and getattr(_neuro_viz, "bars", None):
            pts = []
            for bar in _neuro_viz.bars:
                r = _neuro_viz.radius + bar.get("val", 0.0)
                rad = math.radians(bar.get("angle", 0.0) - 90)
                pts.append((cx + math.cos(rad) * r, cy + math.sin(rad) * r))
            if len(pts) >= 3:
                return pts
    except Exception:
        pass
    # Fallback: soft circle approximation
    pts = []
    base_r = 140
    for i in range(36):
        ang = math.radians(i * 10.0)
        pts.append((cx + math.cos(ang) * base_r, cy + math.sin(ang) * base_r))
    return pts


def draw_intro_waves(target: pygame.Surface, t: float):
    """Start-screen waves: radial ripples running forever until any key is pressed."""
    overlay = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    cx, cy = VIEW_W // 2, int(VIEW_H * 0.52)
    max_r = math.hypot(VIEW_W, VIEW_H) * 0.55
    
    ripple_freq_hz = 0.9   # fixed spawn rate (waves per second)
    ripple_speed = 320.0    # px per second expansion
    max_age = max_r / ripple_speed
    active_ripples = int(max_age * ripple_freq_hz) + 4
    wave_period = 1.0 / ripple_freq_hz
    loop_window = max_age + wave_period  # wrap time so waves never end
    
    # Pull energy from the Neuro viz so the ripples breathe with the music
    energy = 0.0
    try:
        if "_neuro_viz" in globals() and getattr(_neuro_viz, "bars", None):
            energy = sum(b.get("val", 0.0) for b in _neuro_viz.bars) / max(1, len(_neuro_viz.bars))
    except Exception:
        pass
    energy_norm = max(0.0, min(1.0, energy / 70.0))
    
    base_alpha = 130 + int(90 * energy_norm)
    base_thickness = 2 + int(3 * energy_norm)
    hue_shift = int(40 * energy_norm)
    
    for i in range(active_ripples):
        age = (t + i * wave_period) % loop_window  # phase-offset so waves exist at t=0
        if age > max_age:
            continue
        
        radius = age * ripple_speed
        if radius <= 0 or radius > max_r:
            continue
        
        fade = max(0.0, 1.0 - radius / max_r)
        alpha = int(base_alpha * fade)
        if alpha <= 0:
            continue
        
        thickness = max(1, int(base_thickness + 2 * fade))
        col = (70, 200 + hue_shift, 255, alpha)
        pygame.draw.circle(overlay, col, (cx, cy), int(radius), thickness)
        
        # Subtle shimmer on each ring for a liquid feel
        shimmer_radius = radius + (6 + energy_norm * 6) * math.sin(age * math.tau * 0.33)
        if 0 < shimmer_radius < max_r:
            pygame.draw.circle(overlay, (col[0], col[1], col[2], int(alpha * 0.6)), (cx, cy), int(shimmer_radius), 1)
    
    target.blit(overlay, (0, 0))


def draw_neuro_waves(target: pygame.Surface, t: float):
    """Home/menus: infinite outline ripples based on the current NeuroViz shape & color."""
    overlay = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    cx, cy = VIEW_W // 2, int(VIEW_H * 0.52)
    base_pts = _neuro_outline_points(cx, cy)
    if len(base_pts) < 3:
        return
    
    # Average radius from center to shape vertices
    avg_r = sum(math.hypot(x - cx, y - cy) for x, y in base_pts) / len(base_pts)
    avg_r = max(1.0, avg_r)
    
    ripple_freq_hz = 0.95    # waves per second
    scale_speed = 0.85       # how fast each outline grows per second
    max_scale = 4.5          # where we fade out the ring
    max_age = (max_scale - 1.0) / scale_speed
    active_ripples = int(max_age * ripple_freq_hz) + 4
    wave_period = 1.0 / ripple_freq_hz
    loop_window = max_age + wave_period  # wrap time so waves never end
    
    energy = 0.0
    try:
        if "_neuro_viz" in globals() and getattr(_neuro_viz, "bars", None):
            energy = sum(b.get("val", 0.0) for b in _neuro_viz.bars) / max(1, len(_neuro_viz.bars))
    except Exception:
        pass
    energy_norm = max(0.0, min(1.0, energy / 70.0))
    
    base_alpha = 140 + int(80 * energy_norm)
    base_thickness = 2 + int(2 * energy_norm)
    col_base = tuple(int(c) for c in getattr(_neuro_viz, "poly_color", (70, 230, 255)))
    
    for i in range(active_ripples):
        age = (t + i * wave_period) % loop_window  # phase-offset so waves exist at t=0
        if age > max_age:
            continue
        scale = 1.0 + age * scale_speed
        if scale <= 0 or scale > max_scale:
            continue
        
        fade = max(0.0, 1.0 - (scale - 1.0) / (max_scale - 1.0))
        alpha = int(base_alpha * fade)
        if alpha <= 0:
            continue
        
        thickness = max(1, int(base_thickness + 3 * fade))
        pts = []
        
        for x, y in base_pts:
            dx = x - cx
            dy = y - cy
            pts.append((int(round(cx + dx * scale)), int(round(cy + dy * scale))))
        
        if len(pts) >= 3:
            r, g, b = [max(0, min(255, int(v))) for v in col_base[:3]]
            a = max(0, min(255, int(alpha)))
            pygame.draw.polygon(overlay, (r, g, b, a), pts, thickness)
        
        # Light shimmer echo for a more liquid feel
        shimmer_scale = scale + 0.05 + 0.02 * math.sin(age * math.tau * 0.5)
        if shimmer_scale < max_scale and len(base_pts) >= 3:
            pts_shimmer = [
                (int(round(cx + (x - cx) * shimmer_scale)), int(round(cy + (y - cy) * shimmer_scale)))
                for x, y in base_pts
            ]
            r, g, b = [max(0, min(255, int(v))) for v in col_base[:3]]
            a = max(0, min(255, int(alpha * 0.5)))
            pygame.draw.polygon(overlay, (r, g, b, a), pts_shimmer, 1)
    
    # Sliding EEG lines over the ripples
    line_cols = [
        (max(0, min(255, col_base[0])), max(0, min(255, col_base[1])), max(0, min(255, col_base[2])), 130),
        (max(0, min(255, col_base[0] + 20)), max(0, min(255, col_base[1] - 20)), max(0, min(255, col_base[2])), 110),
    ]
    for i, col in enumerate(line_cols):
        mid_y = int(VIEW_H * (0.34 + i * 0.18))
        amp = 14 + i * 5
        freq = 0.018 + i * 0.007
        speed = 80 + i * 40
        pts = []
        for x in range(0, VIEW_W + 12, 8):
            phase = t * speed * 0.05 + x * freq
            w = math.sin(phase) * amp + math.sin(phase * 0.35 + i) * amp * 0.24
            pts.append((x, int(round(mid_y + w))))
        if len(pts) >= 2:
            pygame.draw.lines(overlay, col, False, pts, 2)
    
    target.blit(overlay, (0, 0))


def draw_neuro_hover_spike(target: pygame.Surface, rect: pygame.Rect, t: float):
    """Tiny waveform spike that flickers on hover."""
    spike = pygame.Surface(rect.size, pygame.SRCALPHA)
    x = rect.width * (0.5 + 0.35 * math.sin(t * 9.0))
    pygame.draw.line(spike, (140, 255, 255, 170), (x, rect.height * 0.18), (x, rect.height * 0.82), 2)
    pygame.draw.circle(spike, (140, 255, 255, 190), (int(x), int(rect.height * 0.5)), 3)
    target.blit(spike, rect.topleft)


def draw_neuro_button(surface: pygame.Surface, rect: pygame.Rect, label: str, font,
                      *, hovered: bool, disabled: bool, t: float,
                      fill_col=None, border_col=None, text_col=None, show_spike: bool = True) -> pygame.Rect:
    scale = 1.04 if hovered and not disabled else 1.0
    scaled = pygame.Rect(0, 0, int(rect.width * scale), int(rect.height * scale))
    scaled.center = rect.center
    panel = pygame.Surface(scaled.size, pygame.SRCALPHA)
    fill_alpha = 150 if hovered and not disabled else 110
    if disabled:
        fill_alpha = 65
    base_fill = fill_col if fill_col is not None else (14, 32, 50)
    base_border = border_col if border_col is not None else (80, 200, 255)
    txt_col = text_col if text_col is not None else (220, 240, 255)
    pygame.draw.rect(panel, (*base_fill, fill_alpha), panel.get_rect(), border_radius=16)
    border_rgba = (*base_border, 220 if hovered and not disabled else 150)
    if disabled:
        border_rgba = (90, 110, 130, 120)
    pygame.draw.rect(panel, border_rgba, panel.get_rect(), width=2, border_radius=16)
    glow_alpha = 90 if hovered and not disabled else 40
    glow = pygame.Surface((scaled.width + 12, scaled.height + 12), pygame.SRCALPHA)
    pygame.draw.rect(glow, (40, 180, 255, glow_alpha), glow.get_rect(), border_radius=18)
    surface.blit(glow, scaled.inflate(12, 12).topleft)
    surface.blit(panel, scaled.topleft)
    draw_text_col = txt_col if not disabled else (130, 140, 150)
    text = font.render(label, True, draw_text_col)
    surface.blit(text, text.get_rect(center=scaled.center))
    if hovered and not disabled and show_spike:
        draw_neuro_hover_spike(surface, scaled, t)
    return scaled


def neuro_menu_layout(include_continue: bool = True):
    """Centers and sizes for the vertical stack of panels.
    Spacing adapts to 4 vs 5 buttons and sits near the circle center.
    """
    center_x = int(VIEW_W * 0.52)
    # Place column centered on the visualizer circle
    base_y = int(VIEW_H * 0.52)
    width, height = 320, 68
    ids = ["start", "instruction", "settings", "exit"]
    if include_continue:
        ids.insert(1, "continue")
    count = len(ids)
    # Tighter spacing for 5, looser for 4
    spacing = 78 if count >= 5 else 88
    # Offset upward so column is centered around base_y
    total_h = (count - 1) * spacing
    top_y = base_y - total_h // 2
    rects = {}
    y = top_y
    for ident in ids:
        rects[ident] = pygame.Rect(0, 0, width, height)
        rects[ident].center = (center_x, y)
        y += spacing
    return rects


def draw_neuro_info_column(surface: pygame.Surface, font, t: float, saved_exists: bool):
    col_rect = pygame.Rect(int(VIEW_W * 0.78), 80, int(VIEW_W * 0.17), VIEW_H - 160)
    panel = pygame.Surface(col_rect.size, pygame.SRCALPHA)
    pygame.draw.rect(panel, (12, 30, 50, 120), panel.get_rect(), border_radius=14)
    pygame.draw.rect(panel, (70, 180, 230, 170), panel.get_rect(), width=2, border_radius=14)
    surface.blit(panel, col_rect.topleft)
    # simple word wrap so system messages stay within the column
    def _wrap_text(txt: str, max_px: int) -> list[str]:
        words = txt.split()
        lines = []
        cur = ""
        for w in words:
            trial = w if not cur else f"{cur} {w}"
            if font.size(trial)[0] <= max_px:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [""]
    lines = [
        f"run time: {t:6.2f}s",
        f"seed: 0x{_neuro_log_seed:06X}",
        f"save slot: {'ready' if saved_exists else 'empty'}",
        f"build: neuro-console",
        _NEURO_SYSTEM_MESSAGES[int(t * 0.75) % len(_NEURO_SYSTEM_MESSAGES)],
    ]
    y = col_rect.top + 14
    text_max_w = col_rect.width - 28  # padding inside the panel
    for line in lines:
        for seg in _wrap_text(line, text_max_w):
            surf_line = font.render(seg, True, (150, 200, 230))
            surface.blit(surf_line, (col_rect.left + 14, y))
            y += surf_line.get_height() + 6


def draw_neuro_title_intro(surface: pygame.Surface, title_font, prompt_font, t: float):
    """Intro screen: center title aligned to holo core, with a neon pulse line prompt."""
    cx_core = VIEW_W // 2
    cy_core = int(VIEW_H * 0.46)
    title_text = GAME_TITLE.upper()
    title = title_font.render(title_text, True, (220, 236, 250))
    ghost = title_font.render(title_text, True, (60, 160, 210))
    title_rect = title.get_rect(center=(cx_core, cy_core - 12))
    surface.blit(ghost, title_rect.move(3, 3))
    surface.blit(title, title_rect)
    # neon underline pulses beneath the title
    underline = pygame.Surface((title_rect.width, 8), pygame.SRCALPHA)
    for x in range(0, underline.get_width(), 6):
        alpha = 90 + int(60 * math.sin(t * 3.5 + x * 0.08))
        pygame.draw.rect(underline, (90, 220, 255, alpha), pygame.Rect(x, 0, 4, 3))
    surface.blit(underline, (title_rect.left, title_rect.bottom + 8))
    
    # Gradient prompt on a pulsing neon line
    pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(t * 2.6))
    col_a = (120 + int(100 * pulse), 230, 255)
    col_b = (60, 160 + int(80 * pulse), 230)
    prompt_text = "PRESS ANY KEY TO LINK"
    prompt_base = prompt_font.render(prompt_text, True, (255, 255, 255))
    grad = pygame.Surface(prompt_base.get_size(), pygame.SRCALPHA)
    w, h = grad.get_size()
    for y in range(h):
        mix = y / max(1, h - 1)
        col = (
            int(col_a[0] * (1 - mix) + col_b[0] * mix),
            int(col_a[1] * (1 - mix) + col_b[1] * mix),
            int(col_a[2] * (1 - mix) + col_b[2] * mix),
            255,
        )
        pygame.draw.line(grad, col, (0, y), (w, y))
    grad.blit(prompt_base, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    line_y = title_rect.bottom + 172
    prompt_rect = grad.get_rect(center=(cx_core, line_y))
    side_len = max(80, grad.get_width() // 2)
    gap = prompt_rect.width // 2 + 20
    line_col = (col_a[0], col_a[1], col_a[2])
    seg_h = 8
    seg_w = 4
    seg_gap = 6
    # left pulsing segments
    left_line = pygame.Surface((side_len, seg_h), pygame.SRCALPHA)
    for x in range(0, side_len, seg_gap):
        alpha = 80 + int(70 * math.sin(t * 3.5 + x * 0.09))
        pygame.draw.rect(left_line, (*line_col, alpha), pygame.Rect(x, 2, seg_w, 3))
    surface.blit(left_line, (cx_core - gap - side_len, line_y - seg_h // 2))
    # right pulsing segments
    right_line = pygame.Surface((side_len, seg_h), pygame.SRCALPHA)
    for x in range(0, side_len, seg_gap):
        alpha = 80 + int(70 * math.sin(t * 3.5 + (side_len - x) * 0.09))
        pygame.draw.rect(right_line, (*line_col, alpha), pygame.Rect(x, 2, seg_w, 3))
    surface.blit(right_line, (cx_core + gap, line_y - seg_h // 2))
    surface.blit(grad, prompt_rect.topleft)


def draw_neuro_home_header(surface: pygame.Surface, font):
    """Homepage header: small console-style label."""
    # Use Sekuya font for the main title; fall back to provided font if load fails
    try:
        sekuya = _get_sekuya_font(font.get_height())
    except Exception:
        sekuya = font
    surface.blit(sekuya.render("> NEURONVIVOR", True, (170, 230, 255)), (50, 70))


def _current_music_pos_ms() -> int | None:
    """Safe wrapper for pygame.mixer.music.get_pos(), returning None if not playing."""
    try:
        pos = pygame.mixer.music.get_pos()
        if pos is None or pos < 0:
            return None
        return int(pos)
    except Exception:
        return None


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
    hits = 0
    kills = 0
    for z in list(enemies):
        zx, zy = z.rect.center
        dx, dy = zx - tx, zy - ty
        if dx * dx + dy * dy <= r2:
            hits += 1
            hit_n = random.randint(BLAST_HITS_MIN, BLAST_HITS_MAX)
            dmg_per = max(1, int(getattr(player, "bullet_damage", BULLET_DAMAGE_ENEMY) * BLAST_DMG_MULT))
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
        dmg_per = max(1, int(getattr(player, "bullet_damage", BULLET_DAMAGE_ENEMY) * BLAST_DMG_MULT))
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


def run_neuro_intro(screen: pygame.Surface):
    """Show one-time minimal intro (background + link prompt)."""
    clock = pygame.time.Clock()
    title_font = _get_sekuya_font(64)
    prompt_font = pygame.font.SysFont("Consolas", 24)
    t = 0.0
    while True:
        dt = clock.tick(60) / 1000.0
        t += dt
        screen.blit(ensure_neuro_background(), (0, 0))
        _draw_intro_starfield(screen, t)
        _draw_intro_datastreams(screen, t)
        draw_intro_waves(screen, t)
        _draw_intro_holo_core(screen, t)
        _draw_intro_scanlines(screen, t)
        draw_neuro_title_intro(screen, title_font, prompt_font, t)
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                return
            if event.type == pygame.MOUSEBUTTONDOWN:
                return


def render_start_menu_surface(saved_exists: bool):
    """Static snapshot of the Neuro Console menu (used for transitions)."""
    surf = ensure_neuro_background().copy()
    wave_t = 0.0
    draw_neuro_waves(surf, wave_t)
    header_font = _get_sekuya_font(26)
    btn_font = pygame.font.SysFont(None, 30)
    info_font = pygame.font.SysFont("Consolas", 18)
    draw_neuro_home_header(surf, header_font)
    rects = neuro_menu_layout(include_continue=saved_exists)
    draw_neuro_button(surf, rects["start"], "START NEW", btn_font, hovered=False, disabled=False, t=wave_t)
    if saved_exists:
        draw_neuro_button(surf, rects["continue"], "CONTINUE", btn_font,
                          hovered=False, disabled=False, t=wave_t)
    draw_neuro_button(surf, rects["instruction"], "INSTRUCTION", btn_font, hovered=False, disabled=False, t=wave_t)
    draw_neuro_button(surf, rects["settings"], "SETTINGS", btn_font, hovered=False, disabled=False, t=wave_t)
    draw_neuro_button(surf, rects["exit"], "EXIT", btn_font, hovered=False, disabled=False, t=wave_t)
    
    # --- MODIFIED: Draw static frame of NeuroViz ---
    # Note: We pass dt=0 to draw current state without updating physics
    _neuro_viz.draw(surf, surf.get_width() // 2, int(surf.get_height() * 0.52))
    
    draw_neuro_info_column(surf, info_font, wave_t, saved_exists)
    return surf


def show_start_menu(screen, *, skip_intro: bool = False):
    """Return a tuple ('new', None) or ('continue', save_data) based on player's choice."""
    flush_events()
    intro_flag = globals().pop("_skip_intro_once", False)
    if not skip_intro and not intro_flag:
        run_neuro_intro(screen)
    # Ensure home screen always uses Intro BGM
    try:
        cur = getattr(_bgm, "music_path", "") if "_bgm" in globals() else ""
        if "intro_v0.wav" not in cur.lower():
            play_intro_bgm()
    except Exception:
        try:
            play_intro_bgm()
        except Exception:
            pass
    clock = pygame.time.Clock()
    header_font = _get_sekuya_font(22)
    btn_font = pygame.font.SysFont(None, 30)
    info_font = pygame.font.SysFont("Consolas", 18)
    t = 0.0
    while True:
        dt = clock.tick(60) / 1000.0
        t += dt
        
        if pygame.mixer.music.get_busy():
            pos = pygame.mixer.music.get_pos() / 1000.0
            _neuro_viz.update(dt, pos)
            
        saved_exists = has_save()
        base_rects = neuro_menu_layout(include_continue=saved_exists)
        mouse_pos = pygame.mouse.get_pos()
        hover_id = None
        for ident, r in base_rects.items():
            if ident == "continue" and not saved_exists:
                continue  # hide continue when no save exists
            if r.inflate(int(r.width * 0.08), int(r.height * 0.08)).collidepoint(mouse_pos):
                hover_id = ident
                break
        screen.blit(ensure_neuro_background(), (0, 0))
        draw_neuro_waves(screen, t)
        
        _neuro_viz.draw(screen, VIEW_W // 2, int(VIEW_H * 0.52))
        

        draw_neuro_home_header(screen, header_font)
        drawn_rects = {}
        drawn_rects["start"] = draw_neuro_button(screen, base_rects["start"], "START NEW", btn_font,
                                                 hovered=hover_id == "start", disabled=False, t=t)
        if saved_exists:
            drawn_rects["continue"] = draw_neuro_button(
                screen, base_rects["continue"], "CONTINUE", btn_font,
                hovered=hover_id == "continue", disabled=False, t=t
            )
        drawn_rects["instruction"] = draw_neuro_button(
            screen, base_rects["instruction"], "INSTRUCTION", btn_font,
            hovered=hover_id == "instruction", disabled=False, t=t
        )
        drawn_rects["settings"] = draw_neuro_button(
            screen, base_rects["settings"], "SETTINGS", btn_font,
            hovered=hover_id == "settings", disabled=False, t=t
        )
        drawn_rects["exit"] = draw_neuro_button(
            screen, base_rects["exit"], "EXIT", btn_font,
            hovered=hover_id == "exit", disabled=False, t=t
        )
        draw_neuro_info_column(screen, info_font, t, saved_exists)
        run_pending_menu_transition(screen)
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if drawn_rects["start"].collidepoint(event.pos):
                    # hard reset the run state the instant START NEW is clicked
                    clear_save()  # delete savegame.json if it exists
                    reset_run_state()  # zero META, clear carry, cancel pending shop, drop _last_spoils
                    queue_menu_transition(screen.copy())
                    flush_events()
                    return ("new", None)
                cont_rect = drawn_rects.get("continue")
                if cont_rect and saved_exists and cont_rect.collidepoint(event.pos):
                    data = load_save()
                    if data:
                        queue_menu_transition(screen.copy())
                        flush_events()
                        return ("continue", data)
                if drawn_rects["instruction"].collidepoint(event.pos):
                    # Instruction transition: menu -> instruction
                    from_surf = screen.copy()
                    instr_surf = render_instruction_surface()
                    play_hex_transition(screen, from_surf, instr_surf, direction="down")
                    flush_events()
                    show_instruction(screen)
                    flush_events()
                if drawn_rects["settings"].collidepoint(event.pos):
                    show_settings_popup(screen, screen.copy())
                    flush_events()
                if drawn_rects["exit"].collidepoint(event.pos):
                    pygame.quit()
                    sys.exit()


def show_instruction(screen):
    clock = pygame.time.Clock()
    body_font = pygame.font.SysFont("Consolas", 20)
    title_font = pygame.font.SysFont("Consolas", 34, bold=True)
    btn_font = pygame.font.SysFont(None, 30)
    t = 0.0
    while True:
        dt = clock.tick(60) / 1000.0
        t += dt
        _, back_rect = neuro_instruction_layout()
        hover_back = back_rect.inflate(int(back_rect.width * 0.08), int(back_rect.height * 0.08)).collidepoint(
            pygame.mouse.get_pos()
        )
        screen.blit(ensure_neuro_background(), (0, 0))
        back = draw_neuro_instruction(screen, t, hover_back=hover_back,
                                      title_font=title_font, body_font=body_font, btn_font=btn_font)
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                from_surf = screen.copy()
                to_surf = render_start_menu_surface(has_save())
                play_hex_transition(screen, from_surf, to_surf, direction="up")
                return
            if event.type == pygame.MOUSEBUTTONDOWN and back.collidepoint(event.pos):
                from_surf = screen.copy()
                to_surf = render_start_menu_surface(has_save())
                play_hex_transition(screen, from_surf, to_surf, direction="up")
                return


def show_fail_screen(screen, background_surf):
    dim = pygame.Surface((VIEW_W, VIEW_H))
    dim.set_alpha(180)
    dim.fill((0, 0, 0))
    screen.blit(pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H)), (0, 0))
    screen.blit(dim, (0, 0))
    title = pygame.font.SysFont(None, 80).render("YOU WERE CORRUPTED!", True, (255, 60, 60))
    screen.blit(title, title.get_rect(center=(VIEW_W // 2, 140)))
    retry = draw_button(screen, "RETRY", (VIEW_W // 2 - 200, 300))
    home = draw_button(screen, "HOME", (VIEW_W // 2 + 20, 300))
    pygame.display.flip()
    start_menu_surf = None
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                bg = pygame.display.get_surface().copy()
                pick = pause_from_overlay(screen, bg)
                if pick == "continue":
                    # Repaint this Fail screen and keep waiting for input
                    return_to_fail = True
                    # Re-draw the same Fail UI:
                    dim = pygame.Surface((VIEW_W, VIEW_H))
                    dim.set_alpha(180)
                    dim.fill((0, 0, 0))
                    screen.blit(pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H)), (0, 0))
                    screen.blit(dim, (0, 0))
                    title = pygame.font.SysFont(None, 80).render("YOU WERE CORRUPTED!", True, (255, 60, 60))
                    screen.blit(title, title.get_rect(center=(VIEW_W // 2, 140)))
                    retry = draw_button(screen, "RETRY", (VIEW_W // 2 - 200, 300))
                    home = draw_button(screen, "HOME", (VIEW_W // 2 + 20, 300))
                    pygame.display.flip()
                    continue
                if pick == "home":
                    queue_menu_transition(pygame.display.get_surface().copy())
                    start_menu_surf = start_menu_surf or render_start_menu_surface(has_save())
                    flush_events()
                    return "home"
                if pick == "restart":
                    queue_menu_transition(pygame.display.get_surface().copy())
                    flush_events()
                    return "retry"
                if pick == "exit": pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if retry.collidepoint(event.pos):
                    queue_menu_transition(pygame.display.get_surface().copy())
                    flush_events()
                    return "retry"
                if home.collidepoint(event.pos):
                    queue_menu_transition(pygame.display.get_surface().copy())
                    start_menu_surf = start_menu_surf or render_start_menu_surface(has_save())
                    flush_events()
                    return "home"


def show_success_screen(screen, background_surf, reward_choices):
    dim = pygame.Surface((VIEW_W, VIEW_H))
    dim.set_alpha(150)
    dim.fill((0, 0, 0))
    screen.blit(pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H)), (0, 0))
    screen.blit(dim, (0, 0))
    title = pygame.font.SysFont(None, 80).render("MEMORY RESTORED!", True, (0, 255, 120))
    screen.blit(title, title.get_rect(center=(VIEW_W // 2, 100)))
    card_rects = []
    for i, card in enumerate(reward_choices):
        x = VIEW_W // 2 - (len(reward_choices) * 140) // 2 + i * 140
        rect = pygame.Rect(x, 180, 120, 160)
        pygame.draw.rect(screen, (220, 220, 220), rect)
        name = pygame.font.SysFont(None, 24).render(card.replace("_", " ").upper(), True, (20, 20, 20))
        screen.blit(name, name.get_rect(center=(rect.centerx, rect.bottom - 18)))
        pygame.draw.rect(screen, (40, 40, 40), rect, 3)
        pygame.draw.rect(screen, (70, 90, 90), rect.inflate(-30, -50))
        card_rects.append((rect, card))
    next_btn = draw_button(screen, "CONFIRM", (VIEW_W // 2 - 90, 370))
    chosen = None
    pygame.display.flip()
    start_menu_surf = None
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                bg = pygame.display.get_surface().copy()
                pick = pause_from_overlay(screen, bg)  # 只在暂停菜单里设置→返回暂停→继续
                if pick == "continue":
                    # —— 重新绘制“成功界面”，而不是失败界面 ——
                    dim = pygame.Surface((VIEW_W, VIEW_H))
                    dim.set_alpha(150)
                    dim.fill((0, 0, 0))
                    screen.blit(pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H)), (0, 0))
                    screen.blit(dim, (0, 0))
                    title = pygame.font.SysFont(None, 80).render("MEMORY RESTORED!", True, (0, 255, 120))
                    screen.blit(title, title.get_rect(center=(VIEW_W // 2, 100)))
                    card_rects = []
                    for i, card in enumerate(reward_choices):
                        x = VIEW_W // 2 - (len(reward_choices) * 140) // 2 + i * 140
                        rect = pygame.Rect(x, 180, 120, 160)
                        pygame.draw.rect(screen, (220, 220, 220), rect)
                        name = pygame.font.SysFont(None, 24).render(card.replace("_", " ").upper(), True, (20, 20, 20))
                        screen.blit(name, name.get_rect(center=(rect.centerx, rect.bottom - 18)))
                        pygame.draw.rect(screen, (40, 40, 40), rect, 3)
                        pygame.draw.rect(screen, (70, 90, 90), rect.inflate(-30, -50))
                        card_rects.append((rect, card))
                    next_btn = draw_button(screen, "CONFIRM", (VIEW_W // 2 - 90, 370))
                    pygame.display.flip()
                    continue  # 回到本界面等待点击
                if pick == "home":
                    queue_menu_transition(pygame.display.get_surface().copy())
                    flush_events()
                    return "home"  # 让上层逻辑去处理“回主页”
                if pick == "restart":
                    queue_menu_transition(pygame.display.get_surface().copy())
                    flush_events()
                    return "restart"  # 让上层逻辑去处理“重开本关”
                if pick == "exit":
                    pygame.quit()
                    sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                for rect, card in card_rects:
                    if rect.collidepoint(event.pos): chosen = card
                if next_btn.collidepoint(event.pos) and (chosen or len(reward_choices) == 0):
                    # animation add if needed
                    flush_events()
                    return chosen


def show_pause_menu(screen, background_surf):
    """Draw pause overlay with build info in the dimmed background, keeping buttons centered."""
    # 创建半透明背景
    dim = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    dim.fill((4, 6, 10, 180))
    bg_scaled = pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H))
    screen.blit(bg_scaled, (0, 0))
    screen.blit(dim, (0, 0))
    # 在变暗的背景中显示玩家build信息
    font_small = pygame.font.SysFont(None, 28)
    font_tiny = pygame.font.SysFont(None, 22)
    # 左上角显示基本属性
    left_margin = 30
    top_margin = 30
    y_offset = top_margin
    # 标题
    title = font_small.render("Player Stats", True, UI_TEXT)
    screen.blit(title, (left_margin, y_offset))
    y_offset += 40
    # ======= CURRENT + BASED-ON-LV1 READOUT =======
    p = globals().get("_pause_player_ref", None)
    base_dmg = int(META.get("base_dmg", BULLET_DAMAGE_ENEMY))
    base_cd = float(META.get("base_fire_cd", FIRE_COOLDOWN))
    base_range = clamp_player_range(META.get("base_range", PLAYER_RANGE_DEFAULT))
    base_speed = float(META.get("base_speed", PLAYER_SPEED))
    base_hp = int(META.get("base_maxhp", PLAYER_MAX_HP))
    base_crit = float(META.get("base_crit", CRIT_CHANCE_BASE))
    # --- damage ---
    cur_dmg = int(getattr(p, "bullet_damage", base_dmg + META.get("dmg", 0)))
    shop_dmg = int(META.get("dmg", 0))
    lvl_dmg = max(0, cur_dmg - base_dmg - shop_dmg)
    dmg_text = font_tiny.render(
        f"Damage: {cur_dmg}  (Lv1 {base_dmg}, +{shop_dmg} shop, +{lvl_dmg} lvl)",
        True, (230, 100, 100)
    )
    screen.blit(dmg_text, (left_margin, y_offset));
    y_offset += 30
    # --- fire rate ---
    # effective shots/sec shown plus Lv1 baseline
    if p:
        cur_cd = p.fire_cooldown()
    else:
        cur_cd = max(MIN_FIRE_COOLDOWN, base_cd / max(1.0, float(META.get('firerate_mult', 1.0))))
    cur_sps = 1.0 / cur_cd
    base_sps = 1.0 / max(MIN_FIRE_COOLDOWN, base_cd)
    fr_mult = float(META.get("firerate_mult", 1.0))
    fr_text = font_tiny.render(
        f"Fire Rate: {fr_mult:.2f}x  ({cur_sps:.2f}/s, Lv1 {base_sps:.2f}/s)",
        True, (100, 200, 100)
    )
    screen.blit(fr_text, (left_margin, y_offset));
    y_offset += 30
    # --- range ---
    rng_mult = float(META.get("range_mult", 1.0))
    cur_range = clamp_player_range(getattr(p, "range", compute_player_range(base_range, rng_mult)))
    eff_rng_mult = cur_range / base_range if base_range else rng_mult
    rng_text = font_tiny.render(
        f"Range: {eff_rng_mult:.2f}x  ({int(cur_range)} px, Lv1 {int(base_range)} px)",
        True, (200, 200, 100)
    )
    screen.blit(rng_text, (left_margin, y_offset));
    y_offset += 30
    # --- speed ---
    cur_speed = float(getattr(p, "speed", base_speed + META.get("speed", 0)))
    spd_text = font_tiny.render(
        f"Speed: {cur_speed:.1f}  (Lv1 {base_speed:.1f}, +{int(META.get('speed', 0))} shop)",
        True, (100, 100, 230)
    )
    screen.blit(spd_text, (left_margin, y_offset));
    y_offset += 30
    # --- max hp ---
    cur_mhp = int(getattr(p, "max_hp", base_hp + META.get("maxhp", 0)))
    shop_hp = int(META.get("maxhp", 0))
    lvl_hp = max(0, cur_mhp - base_hp - shop_hp)
    hp_text = font_tiny.render(
        f"Max HP: {cur_mhp}  (Lv1 {base_hp}, +{shop_hp} shop, +{lvl_hp} lvl)",
        True, (230, 150, 100)
    )
    screen.blit(hp_text, (left_margin, y_offset));
    y_offset += 30
    # --- crit ---
    cur_crit = float(getattr(p, "crit_chance", base_crit + META.get("crit", 0.0)))
    crit_text = font_tiny.render(
        f"Crit Chance: {int(cur_crit * 100)}%  (Lv1 {int(base_crit * 100)}%)",
        True, (255, 220, 120)
    )
    screen.blit(crit_text, (left_margin, y_offset));
    y_offset += 30
    # --- DPS (average, includes current damage/AS/crit) ---
    dps_val = compute_player_dps(p)
    dps_text = font_tiny.render(f"DPS: {dps_val:.2f}", True, (230, 230, 230))
    screen.blit(dps_text, (left_margin, y_offset));
    y_offset += 30
    # --- right column: possessions / inventory summary ---
    right_margin = VIEW_W - 30
    y_offset = top_margin
    title = font_small.render("Possessions", True, UI_TEXT)
    title_rect = title.get_rect(right=right_margin, top=y_offset)
    screen.blit(title, title_rect)
    y_offset += 40
    pos_font = pygame.font.SysFont(None, 24)
    catalog = globals().get("_pause_shop_catalog")
    if catalog is None:
        catalog = [
            {
                "id": "coin_magnet",
                "name": "Coin Magnet",
                "max_level": 5,
            },
            {
                "id": "auto_turret",
                "name": "Auto-Turret",
                "max_level": 5,
            },
            {
                "id": "stationary_turret",
                "name": "Stationary Turret",
                "max_level": 99,
            },
            {
                "id": "ricochet_scope",
                "name": "Ricochet Scope",
                "max_level": 3,
            },
            {
                "id": "piercing_rounds",
                "name": "Piercing Rounds",
                "max_level": 5,
            },
            {
                "id": "shrapnel_shells",
                "name": "Shrapnel Shells",
                "max_level": 3,
            },
            {
                "id": "explosive_rounds",
                "name": "Explosive Rounds",
                "max_level": 3,
            },
            {
                "id": "dot_rounds",
                "name": "D.O.T. Rounds",
                "max_level": 3,
            },
            {
                "id": "bone_plating",
                "name": "Bone Plating",
                "max_level": 5,
            },
            {
                "id": "carapace",
                "name": "Carapace",
                "max_level": None,
            },
            {
                "id": "aegis_pulse",
                "name": "Aegis Pulse",
                "max_level": 5,
            },
            {
                "id": "bandit_radar",
                "name": "Bandit Radar",
                "max_level": 4,
            },
            {
                "id": "lockbox",
                "name": "Lockbox",
                "max_level": LOCKBOX_MAX_LEVEL,
            },
            {
                "id": "mark_vulnerability",
                "name": "Mark of Vulnerability",
                "desc": "Every 5/4/3s mark a priority enemy for 5/6/7s; marked take +15/22/30% damage.",
                "cost": 25,
                "rarity": 3,
                "max_level": 3,
                "apply": lambda: META.update(
                    vuln_mark_level=min(3, int(META.get("vuln_mark_level", 0)) + 1)
                ),
            },
            {
                "id": "golden_interest",
                "name": "Golden Interest",
                "max_level": GOLDEN_INTEREST_MAX_LEVEL,
            },
            {
                "id": "wanted_poster",
                "name": "Wanted Poster",
                "max_level": None,
            },
            {
                "id": "shady_loan",
                "name": "Shady Loan",
                "max_level": SHADY_LOAN_MAX_LEVEL,
            },
            {
                "id": "coupon",
                "name": "Coupon",
                "max_level": COUPON_MAX_LEVEL,
            },
        ]
        globals()["_pause_shop_catalog"] = catalog
    # Invalidate cached shop offers when catalog changes
    if globals().get("_shop_catalog_version") != SHOP_CATALOG_VERSION:
        for key in (
                "_shop_slot_ids_cache", "_shop_slots_cache",
                "_shop_reroll_id_cache", "_shop_reroll_cache",
                "_resume_shop_cache",
        ):
            globals().pop(key, None)
        globals()["_shop_catalog_version"] = SHOP_CATALOG_VERSION

    def _pause_prop_level(item):
        iid = item.get("id")
        if iid == "coin_magnet":
            return int(META.get("coin_magnet_radius", 0) // 60)
        if iid == "auto_turret":
            return int(META.get("auto_turret_level", 0))
        if iid == "stationary_turret":
            return int(META.get("stationary_turret_count", 0))
        if iid == "ricochet_scope":
            return int(META.get("ricochet_level", 0))
        if iid == "piercing_rounds":
            return int(META.get("pierce_level", 0))
        if iid == "shrapnel_shells":
            return int(META.get("shrapnel_level", 0))
        if iid == "explosive_rounds":
            return int(META.get("explosive_rounds_level", 0))
        if iid == "dot_rounds":
            return int(META.get("dot_rounds_level", 0))
        if iid == "mark_vulnerability":
            return int(META.get("vuln_mark_level", 0))
        if iid == "bandit_radar":
            return int(META.get("bandit_radar_level", 0))
        if iid == "lockbox":
            return int(META.get("lockbox_level", 0))
        if iid == "golden_interest":
            return int(META.get("golden_interest_level", 0))
        if iid == "wanted_poster":
            return int(META.get("wanted_poster_waves", 0))
        if iid == "shady_loan":
            return int(META.get("shady_loan_level", 0))
        if iid == "coupon":
            return int(META.get("coupon_level", 0))
        if iid == "bone_plating":
            return int(META.get("bone_plating_level", 0))
        if iid == "carapace":
            carapace_hp = int(META.get("carapace_shield_hp", 0))
            return (carapace_hp + 19) // 20
        if iid == "aegis_pulse":
            return int(META.get("aegis_pulse_level", 0))
        return None

    owned = []
    for item in catalog:
        lvl = _pause_prop_level(item)
        max_lvl = item.get("max_level")
        if lvl and lvl > 0:
            owned.append((item["name"], lvl, max_lvl))
    if owned:
        for name, lvl, max_lvl in owned:
            lvl_str = f"{lvl}/{max_lvl}" if max_lvl else f"x{lvl}"
            text = f"{name}: {lvl_str}"
            surf = pos_font.render(text, True, UI_TEXT)
            rect = surf.get_rect(right=right_margin, top=y_offset)
            screen.blit(surf, rect)
            y_offset += 24
    panel_w, panel_h = min(520, VIEW_W - 80), min(500, VIEW_H - 160)
    panel = pygame.Rect(0, 0, panel_w, panel_h)
    panel.center = (VIEW_W // 2, VIEW_H // 2)
    title_surf = pygame.font.SysFont(None, 72).render("Paused", True, UI_TEXT)
    # 按钮
    btn_w, btn_h = 300, 56
    spacing = 14
    start_y = panel.top + 110
    labels = [("CONTINUE", "continue"),
              ("RESTART", "restart"),
              ("SETTINGS", "settings"),
              ("BACK TO HOMEPAGE", "home"),
              ("EXIT GAME (Save & Quit)", "exit")]
    btns = [(pygame.Rect(panel.centerx - btn_w // 2, start_y + i * (btn_h + spacing), btn_w, btn_h), tag, label)
            for i, (label, tag) in enumerate(labels)]
    def redraw(hover_tag: str | None):
        # redraw panel & buttons (hover animation)
        pygame.draw.rect(screen, UI_PANEL, panel, border_radius=16)
        pygame.draw.rect(screen, UI_BORDER, panel, width=3, border_radius=16)
        screen.blit(title_surf, title_surf.get_rect(center=(panel.centerx, panel.top + 58)))
        for rect, tag, label in btns:
            hover = (tag == hover_tag)
            fill = None
            border = None
            if tag == "exit":
                fill = (200, 50, 50)
                border = (255, 120, 120)
            draw_neuro_button(
                screen, rect, label, pygame.font.SysFont(None, 32),
                hovered=hover, disabled=False, t=pygame.time.get_ticks() * 0.001,
                fill_col=fill, border_col=border, show_spike=False
            )
    pygame.display.flip()
    while True:
        mx, my = pygame.mouse.get_pos()
        hover_tag = None
        for rect, tag, _ in btns:
            if rect.collidepoint((mx, my)):
                hover_tag = tag
                break
        redraw(hover_tag)
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                flush_events()
                return "continue"
            if event.type == pygame.MOUSEBUTTONDOWN:
                for rect, tag, _ in btns:
                    if rect.collidepoint(event.pos):
                        flush_events()
                        return tag


def _apply_levelup_choice(player, key: str):
    """Apply the chosen buff immediately AND persist in META so it carries over."""
    if key == "dmg":
        META["dmg"] = META.get("dmg", 0) + 1
        player.bullet_damage += 1
    elif key == "firerate":
        META["firerate_mult"] = float(META.get("firerate_mult", 1.0)) * 1.05
        player.fire_rate_mult *= 1.05
    elif key == "range":
        base_range = clamp_player_range(META.get("base_range", PLAYER_RANGE_DEFAULT))
        META["base_range"] = base_range  # sanitize any persisted value
        new_mult = float(META.get("range_mult", 1.0)) * 1.10
        max_mult = PLAYER_RANGE_MAX / max(1.0, base_range)
        META["range_mult"] = min(new_mult, max_mult)
        # player.range is base * mult (clamped to the hard cap)
        if player is not None:
            player.range_base = clamp_player_range(getattr(player, "range_base", base_range))
            player.range = compute_player_range(player.range_base, META["range_mult"])
    elif key == "speed":
        META["speed_mult"] = float(META.get("speed_mult", 1.0)) * 1.05
        base_spd = float(META.get("base_speed", 2.6))
        # live-apply to player
        if player is not None:
            player.speed = min(PLAYER_SPEED_CAP, max(1.0, base_spd * META["speed_mult"]))
    elif key == "maxhp":
        META["maxhp"] = int(META.get("maxhp", 0)) + 5
        player.max_hp += 5
        player.hp = min(player.max_hp, player.hp + 10)  # small heal like the mock
    elif key == "crit":
        META["crit"] = min(0.75, float(META.get("crit", 0.0)) + 0.02)
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
    speed_cap = globals().get("PLAYER_SPEED_CAP", None)
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
    globals()["_time_left_runtime"] = time_left
    clock.tick(60)  # reset dt baseline so gameplay doesn't jump after modal
    flush_events()
    return time_left


def show_settings_popup(screen, background_surf):
    """Settings hub with category buttons and rebinding for core controls."""
    global FX_VOLUME, BGM_VOLUME
    clock = pygame.time.Clock()
    dim = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 170))
    bg_scaled = pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H))
    panel_w, panel_h = min(520, VIEW_W - 80), min(520, VIEW_H - 160)
    panel = pygame.Rect(0, 0, panel_w, panel_h)
    panel.center = (VIEW_W // 2, VIEW_H // 2)
    title_font = pygame.font.SysFont(None, 56)
    font = pygame.font.SysFont(None, 26)
    section_font = pygame.font.SysFont(None, 28, bold=True)
    btn_font = pygame.font.SysFont(None, 32)
    # working values
    fx_val = int(FX_VOLUME)
    bgm_val = int(BGM_VOLUME)
    dragging = None  # None | "fx" | "bgm"
    page = "root"  # "root" | "audio" | "controls"
    waiting_action = None
    ctrl_buttons: list[tuple[pygame.Rect, str]] = []

    control_actions = [
        ("Move Up", "move_up"),
        ("Move Left", "move_left"),
        ("Move Down", "move_down"),
        ("Move Right", "move_right"),
        ("Blast", "blast"),
        ("Teleport", "teleport"),
    ]

    def draw_slider(label, value, top_y):
        screen.blit(font.render(f"{label}: {value}", True, UI_TEXT), (panel.left + 40, top_y))
        bar = pygame.Rect(panel.left + 40, top_y + 24, panel_w - 80, 10)
        knob_x = bar.x + int((value / 100) * bar.width)
        pygame.draw.rect(screen, (60, 70, 90), bar, border_radius=6)
        pygame.draw.circle(screen, UI_ACCENT, (knob_x, bar.y + 5), 8)
        return bar

    def val_from_bar(bar, mx):
        return max(0, min(100, int(((mx - bar.x) / max(1, bar.width)) * 100)))

    def draw_root():
        screen.blit(bg_scaled, (0, 0))
        screen.blit(dim, (0, 0))
        pygame.draw.rect(screen, UI_PANEL, panel, border_radius=16)
        pygame.draw.rect(screen, UI_BORDER, panel, width=3, border_radius=16)
        title = title_font.render("Settings", True, UI_TEXT)
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 60)))
        btn_w, btn_h = 220, 56
        audio_btn = pygame.Rect(0, 0, btn_w, btn_h)
        ctrl_btn = pygame.Rect(0, 0, btn_w, btn_h)
        close_btn = pygame.Rect(0, 0, btn_w, btn_h)
        audio_btn.center = (panel.centerx, panel.top + 160)
        ctrl_btn.center = (panel.centerx, panel.top + 230)
        close_btn.center = (panel.centerx, panel.bottom - 60)
        draw_neuro_button(screen, audio_btn, "Audio", btn_font,
                          hovered=audio_btn.collidepoint(pygame.mouse.get_pos()),
                          disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        draw_neuro_button(screen, ctrl_btn, "Controls", btn_font,
                          hovered=ctrl_btn.collidepoint(pygame.mouse.get_pos()),
                          disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        draw_neuro_button(screen, close_btn, "Close", btn_font,
                          hovered=close_btn.collidepoint(pygame.mouse.get_pos()),
                          disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        pygame.display.flip()
        return audio_btn, ctrl_btn, close_btn

    def draw_audio():
        screen.blit(bg_scaled, (0, 0))
        screen.blit(dim, (0, 0))
        pygame.draw.rect(screen, UI_PANEL, panel, border_radius=16)
        pygame.draw.rect(screen, UI_BORDER, panel, width=3, border_radius=16)
        title = title_font.render("Audio", True, UI_TEXT)
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 60)))
        nonlocal fx_bar, bgm_bar
        fx_bar = draw_slider("Effects Volume", fx_val, panel.top + 120)
        bgm_bar = draw_slider("BGM Volume", bgm_val, panel.top + 180)
        btn_w, btn_h = 180, 52
        back_btn = pygame.Rect(0, 0, btn_w, btn_h)
        close_btn = pygame.Rect(0, 0, btn_w, btn_h)
        back_btn.center = (panel.centerx - 100, panel.bottom - 60)
        close_btn.center = (panel.centerx + 100, panel.bottom - 60)
        draw_neuro_button(screen, back_btn, "Back", btn_font,
                          hovered=back_btn.collidepoint(pygame.mouse.get_pos()),
                          disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        draw_neuro_button(screen, close_btn, "Save", btn_font,
                          hovered=close_btn.collidepoint(pygame.mouse.get_pos()),
                          disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        pygame.display.flip()
        return back_btn, close_btn

    def draw_controls():
        screen.blit(bg_scaled, (0, 0))
        screen.blit(dim, (0, 0))
        pygame.draw.rect(screen, UI_PANEL, panel, border_radius=16)
        pygame.draw.rect(screen, UI_BORDER, panel, width=3, border_radius=16)
        title = title_font.render("Controls", True, UI_TEXT)
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 52)))
        hint = font.render("Click an action, then press a key to rebind.", True, UI_TEXT)
        screen.blit(hint, hint.get_rect(center=(panel.centerx, panel.top + 92)))
        ctrl_buttons.clear()
        start_y = panel.top + 130
        row_h = 46
        btn_w, btn_h = 180, 34
        for idx, (label, action) in enumerate(control_actions):
            y = start_y + idx * row_h
            screen.blit(font.render(label, True, UI_TEXT), (panel.left + 36, y))
            btn = pygame.Rect(0, 0, btn_w, btn_h)
            btn.center = (panel.centerx + 80, y + btn_h // 2)
            ctrl_buttons.append((btn, action))
            text = "Press a key..." if waiting_action == action else binding_name(action)
            draw_neuro_button(screen, btn, text, font,
                              hovered=btn.collidepoint(pygame.mouse.get_pos()),
                              disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        back_btn = pygame.Rect(0, 0, 160, 48)
        close_btn = pygame.Rect(0, 0, 160, 48)
        back_btn.center = (panel.centerx - 90, panel.bottom - 60)
        close_btn.center = (panel.centerx + 90, panel.bottom - 60)
        draw_neuro_button(screen, back_btn, "Back", btn_font,
                          hovered=back_btn.collidepoint(pygame.mouse.get_pos()),
                          disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        draw_neuro_button(screen, close_btn, "Save", btn_font,
                          hovered=close_btn.collidepoint(pygame.mouse.get_pos()),
                          disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        pygame.display.flip()
        return back_btn, close_btn

    # initial draw placeholders
    fx_bar = bgm_bar = None
    audio_btn = ctrl_btn = close_btn = None
    while True:
        if page == "root":
            audio_btn, ctrl_btn, close_btn = draw_root()
        elif page == "audio":
            back_btn, close_btn = draw_audio()
        elif page == "controls":
            back_btn, close_btn = draw_controls()
        else:
            page = "root"
            continue

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and waiting_action:
                waiting_action = None
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                FX_VOLUME = fx_val
                BGM_VOLUME = bgm_val
                if "_bgm" in globals() and getattr(_bgm, "set_volume", None):
                    _bgm.set_volume(BGM_VOLUME / 100.0)
                flush_events()
                return "close"

            if page == "root":
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    if audio_btn and audio_btn.collidepoint((mx, my)):
                        page = "audio"; dragging = None
                    elif ctrl_btn and ctrl_btn.collidepoint((mx, my)):
                        page = "controls"; waiting_action = None
                    elif close_btn and close_btn.collidepoint((mx, my)):
                        FX_VOLUME = fx_val; BGM_VOLUME = bgm_val
                        if "_bgm" in globals() and getattr(_bgm, "set_volume", None):
                            _bgm.set_volume(BGM_VOLUME / 100.0)
                        flush_events()
                        return "close"

            elif page == "audio":
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    if fx_bar and fx_bar.collidepoint((mx, my)):
                        fx_val = val_from_bar(fx_bar, mx)
                        FX_VOLUME = fx_val
                        dragging = "fx"
                    elif bgm_bar and bgm_bar.collidepoint((mx, my)):
                        bgm_val = val_from_bar(bgm_bar, mx)
                        BGM_VOLUME = bgm_val
                        if "_bgm" in globals() and getattr(_bgm, "set_volume", None):
                            _bgm.set_volume(BGM_VOLUME / 100.0)
                        dragging = "bgm"
                    elif back_btn and back_btn.collidepoint((mx, my)):
                        page = "root"; dragging = None
                    elif close_btn and close_btn.collidepoint((mx, my)):
                        FX_VOLUME = fx_val; BGM_VOLUME = bgm_val
                        if "_bgm" in globals() and getattr(_bgm, "set_volume", None):
                            _bgm.set_volume(BGM_VOLUME / 100.0)
                        flush_events()
                        return "close"
                if event.type == pygame.MOUSEBUTTONUP:
                    dragging = None
                if event.type == pygame.MOUSEMOTION and dragging:
                    mx, my = event.pos
                    if dragging == "fx" and fx_bar:
                        fx_val = val_from_bar(fx_bar, mx)
                        FX_VOLUME = fx_val
                    elif dragging == "bgm" and bgm_bar:
                        bgm_val = val_from_bar(bgm_bar, mx)
                        BGM_VOLUME = bgm_val
                        if "_bgm" in globals() and getattr(_bgm, "set_volume", None):
                            _bgm.set_volume(BGM_VOLUME / 100.0)

            elif page == "controls":
                if waiting_action and event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        waiting_action = None
                    else:
                        set_binding(waiting_action, event.key)
                        waiting_action = None
                    continue
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    clicked_any = False
                    for rect, action in ctrl_buttons:
                        if rect.collidepoint((mx, my)):
                            waiting_action = action
                            clicked_any = True
                            break
                    if clicked_any:
                        continue
                    if back_btn and back_btn.collidepoint((mx, my)):
                        waiting_action = None
                        page = "root"
                    elif close_btn and close_btn.collidepoint((mx, my)):
                        FX_VOLUME = fx_val; BGM_VOLUME = bgm_val
                        if "_bgm" in globals() and getattr(_bgm, "set_volume", None):
                            _bgm.set_volume(BGM_VOLUME / 100.0)
                        flush_events()
                        return "close"

        clock.tick(60)


def show_shop_screen(screen) -> Optional[str]:
    """Spend META['spoils'] on small upgrades. ESC opens Pause; return action or None when closed."""
    # If we're opening a fresh shop (not resuming from a saved-in-shop state), clear any cached offers
    if not globals().get("_resume_shop_cache", False):
        _clear_shop_cache()
    globals()["_resume_shop_cache"] = False
    play_combat_bgm()  # ensure shop uses the combat/main track
    # snapshot coins at shop entry (post-bank, pre-purchase)
    globals()["_coins_at_shop_entry"] = int(META.get("spoils", 0))
    globals()["_in_shop_ui"] = True
    try:
        clock = pygame.time.Clock()
        font = pygame.font.SysFont(None, 30)  # titles, cost, etc.
        desc_font = pygame.font.SysFont(None, 24)  # smaller font just for descriptions
        title_font = pygame.font.SysFont(None, 56)  
        btn_font = pygame.font.SysFont(None, 32)
        did_menu_hex = False
        # --- shared shop box style  ---
        SHOP_BOX_BG = UI_PANEL  # base background (Reroll style)
        SHOP_BOX_BORDER = UI_BORDER  # base border
        SHOP_BOX_BG_HOVER = (32, 40, 56)  # when hovered
        SHOP_BOX_BORDER_HOVER = UI_BORDER_HOVER
        SHOP_BOX_BG_DISABLED = UI_PANEL_DARK  # capped / disabled
        SHOP_BOX_BORDER_DISABLED = (70, 90, 120)
      
        # --- catalog of shop props ---
        catalog = [
            {
                "id": "coin_magnet",
                "name": "Coin Magnet",
                "key": "magnet",
                "cost": 10,
                "rarity": 1,
                "max_level": 5,  # 5 steps of radius, purely UI-level cap
                "desc": "Increase your coin pickup radius.",
                "apply": lambda: META.update(
                    coin_magnet_radius=META.get("coin_magnet_radius", 0) + 60
                ),
            },
            {
                "id": "carapace",
                "name": "Carapace",
                "desc": "Gain a small protective shield.",
                "cost": 6,  # cheap
                "rarity": 1,  # common
                "apply": lambda: META.update(
                    carapace_shield_hp=int(META.get("carapace_shield_hp", 0)) + 20
                ),
            },
            {
                "id": "aegis_pulse",
                "name": "Aegis Pulse",
                "desc": "Periodically release a hexagonal force field that damages nearby enemies when shield exists.",
                "cost": 28,
                "rarity": 3,
                "max_level": 5,
                "apply": lambda: META.update(
                    aegis_pulse_level=min(5, int(META.get("aegis_pulse_level", 0)) + 1)
                ),
            },
            {
                "id": "bone_plating",
                "name": "Bone Plating",
                "desc": "Every 6s gain 2 HP plating; max out at 5 buys to unlock full-hit negation, -2% speed.",
                "cost": 12,
                "rarity": 2,
                "max_level": 5,
                "apply": lambda: META.update(
                    bone_plating_level=min(5, int(META.get("bone_plating_level", 0)) + 1),
                    speed_mult=max(0.30, float(META.get("speed_mult", 1.0)) * 0.98),
                ),
            },
            {
                "id": "auto_turret",
                "name": "Auto-Turret",
                "key": "auto_turret",
                "cost": 14,
                "rarity": 2,
                "max_level": 5,
                "desc": "Summons an orbiting auto-turret that fires at nearby enemies.",
                "apply": lambda: META.update(
                    auto_turret_level=min(5, META.get("auto_turret_level", 0) + 1)
                ),
            },
            {
                "id": "piercing_rounds",
                "name": "Piercing Rounds",
                "desc": "Bullets can pierce +1 enemy.",
                "cost": 12,
                "rarity": 1,
                "max_level": 5,
                "apply": lambda: META.update(
                    pierce_level=min(5, int(META.get("pierce_level", 0)) + 1)
                ),
            },
            {
                "id": "ricochet_scope",
                "name": "Ricochet Scope",
                "desc": "Bullets that hit walls or enemies can bounce toward the nearest enemy.",
                "cost": 14,
                "rarity": 2,
                "max_level": 3,
                "apply": lambda: META.update(
                    ricochet_level=min(3, int(META.get("ricochet_level", 0)) + 1)
                ),
            },
            {
                "id": "shrapnel_shells",
                "name": "Shrapnel Shells",
                "desc": "On enemy death, 25/35/45% spawn 3–4 shrapnel splashes dealing 40% of lethal damage.",
                "cost": 16,
                "rarity": 3,
                "max_level": 3,
                "apply": lambda: META.update(
                    shrapnel_level=min(3, int(META.get("shrapnel_level", 0)) + 1)
                ),
            },
            {
                "id": "explosive_rounds",
                "name": "Explosive Rounds",
                "desc": "On bullet kill, explode for 25/35/45% bullet dmg in a small radius (bosses half).",
                "cost": 18,
                "rarity": 2,
                "max_level": 3,
                "apply": lambda: META.update(
                    explosive_rounds_level=min(3, int(META.get("explosive_rounds_level", 0)) + 1)
                ),
            },
            {
                "id": "dot_rounds",
                "name": "D.O.T. Rounds",
                "desc": "On hit, apply a stacking DoT based on base bullet dmg (0.5s ticks, bosses -30%).",
                "cost": 20,
                "rarity": 2,
                "max_level": 3,
                "apply": lambda: META.update(
                    dot_rounds_level=min(3, int(META.get("dot_rounds_level", 0)) + 1)
                ),
            },
            {
                "id": "mark_vulnerability",
                "name": "Mark of Vulnerability",
                "desc": "Every 5/4/3s mark a priority enemy for 5/6/7s; marked take +15/22/30% damage.",
                "cost": 22,
                "rarity": 3,
                "max_level": 3,
                "apply": lambda: META.update(
                    vuln_mark_level=min(3, int(META.get("vuln_mark_level", 0)) + 1)
                ),
            },
            {
                "id": "golden_interest",
                "name": "Golden Interest",
                "desc": "Earn interest on unspent coins after shopping (5/10/15/20%, cap 30/50/70/90).",
                "cost": 12,
                "rarity": 2,
                "max_level": GOLDEN_INTEREST_MAX_LEVEL,
                "apply": lambda: META.update(
                    golden_interest_level=min(
                        GOLDEN_INTEREST_MAX_LEVEL, int(META.get("golden_interest_level", 0)) + 1
                    )
                ),
            },
            {
                "id": "wanted_poster",
                "name": "Wanted Poster",
                "desc": "Consumable: next 2 levels, the first Bandit kill pays a bounty.",
                "cost": 15,
                "rarity": 2,
                "apply": use_wanted_poster,
            },
            {
                "id": "shady_loan",
                "name": "Shady Loan",
                "desc": "Risky loan: upfront gold now, pay it back over a few waves or lose max HP.",
                "cost": 0,
                "rarity": 3,
                "max_level": SHADY_LOAN_MAX_LEVEL,
                "apply": purchase_shady_loan,
            },
            {
                "id": "bandit_radar",
                "name": "Bandit Radar",
                "desc": "Bandits spawn slowed & highlighted (8/12/16/20% for 2/3/4/5s).",
                "cost": 18,
                "rarity": 2,
                "max_level": 4,
                "apply": lambda: META.update(
                    bandit_radar_level=min(4, int(META.get("bandit_radar_level", 0)) + 1)
                ),
            },
            {
                "id": "lockbox",
                "name": "Lockbox",
                "desc": "Protect a slice of your coins from bandits and other losses (25/40/55/70%).",
                "cost": 14,
                "rarity": 2,
                "max_level": LOCKBOX_MAX_LEVEL,
                "apply": lambda: META.update(
                    lockbox_level=min(LOCKBOX_MAX_LEVEL, int(META.get("lockbox_level", 0)) + 1)
                ),
            },
            {
                "id": "coupon",
                "name": "Coupon",
                "desc": "Permanently reduce 5% all shop prices this run.",
                "cost": 10,
                "rarity": 1,
                "max_level": COUPON_MAX_LEVEL,
                "apply": lambda: META.update(
                    coupon_level=min(COUPON_MAX_LEVEL, int(META.get("coupon_level", 0)) + 1)
                ),
            },
            {
                "id": "stationary_turret",
                "name": "Stationary Turret",
                "desc": "Adds a stationary turret that spawns at a random clear spot on the map each level.",
                "cost": 14,  # tweak as you like
                "rarity": 1,  # slightly rarer than basic stuff
                "max_level": 99,  # effectively unlimited copies
                "apply": lambda: META.update(
                    stationary_turret_count=int(META.get("stationary_turret_count", 0)) + 1
                ),
            },
            # reroll is treated specially: no level cap, always appears
            {
                "id": "reroll",
                "name": "Reroll",  # shorter title
                "key": "reroll",
                "cost": 3,
                "apply": "reroll",
            },
        ]
        # Mirror the live shop catalog into the pause menu so possessions stay in sync.
        globals()["_pause_shop_catalog"] = catalog
    finally:
        # just a guard; we clear this flag once we leave the function
        globals().pop("_in_shop_ui", None)
    # Persistent locked cards between shop screens; mirror to META so saves carry them
    saved_locked = META.get("locked_shop_ids")
    if isinstance(saved_locked, list):
        seen = set()
        initial_locked = []
        for lid in saved_locked:
            if isinstance(lid, str) and lid not in seen:
                seen.add(lid)
                initial_locked.append(lid)
    else:
        initial_locked = []
    locked_ids = globals().get("_locked_shop_ids")
    if locked_ids is None:
        locked_ids = list(initial_locked)
        globals()["_locked_shop_ids"] = locked_ids
    else:
        locked_ids[:] = list(initial_locked)

    def _persist_locked_ids():
        seen = set()
        ordered = []
        for lid in locked_ids:
            if isinstance(lid, str) and lid not in seen:
                seen.add(lid)
                ordered.append(lid)
        META["locked_shop_ids"] = ordered

    _persist_locked_ids()

    def _prop_level(it):
        """Read current level for capped props from META."""
        iid = it.get("id")
        if iid == "piercing_rounds":
            return int(META.get("pierce_level", 0))
        if iid == "ricochet_scope":
            return int(META.get("ricochet_level", 0))
        if iid == "shrapnel_shells":
            return int(META.get("shrapnel_level", 0))
        if iid == "explosive_rounds":
            return int(META.get("explosive_rounds_level", 0))
        if iid == "mark_vulnerability":
            return int(META.get("vuln_mark_level", 0))
        if iid == "stationary_turret":
            return int(META.get("stationary_turret_count", 0))
        if iid == "bandit_radar":
            return int(META.get("bandit_radar_level", 0))
        if iid == "lockbox":
            return int(META.get("lockbox_level", 0))
        if iid == "coin_magnet":
            # radius 0,60,120,... => treat as 0,1,2,...
            return int(META.get("coin_magnet_radius", 0) // 60)
        if iid == "auto_turret":
            return int(META.get("auto_turret_level", 0))
        if iid == "carapace":
            hp = int(META.get("carapace_shield_hp", 0))
            return (hp + 19) // 20
        if iid == "golden_interest":
            return int(META.get("golden_interest_level", 0))
        if iid == "shady_loan":
            return int(META.get("shady_loan_level", 0))
        if iid == "wanted_poster":
            return int(META.get("wanted_poster_waves", 0))
        if iid == "coupon":
            return int(META.get("coupon_level", 0))
        if iid == "bone_plating":
            return int(META.get("bone_plating_level", 0))
        if iid == "aegis_pulse":
            return int(META.get("aegis_pulse_level", 0))
        # reroll or anything else: no level display
        return None

    def _owned_live_text(it, lvl: int | None):
        iid = it.get("id")
        lvl = 0 if lvl is None else int(lvl)
        if iid == "shady_loan":lvl = max(lvl, int(META.get("shady_loan_last_level", lvl)))
        if lvl <= 0:
            return None
        if iid == "lockbox":
            coins = max(0, int(META.get("spoils", 0)))
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
            bullet_base = int(META.get("base_dmg", BULLET_DAMAGE_ENEMY)) + int(META.get("dmg", 0))
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
            waves = int(META.get("wanted_poster_waves", 0))
            status = "ready" if waves > 0 else ("armed" if META.get("wanted_active") else "spent")
            return f"Bounty charges: {waves} ({status})"
        if iid == "shady_loan":
            debt = max(0, int(META.get("shady_loan_remaining_debt", 0)))
            waves = int(META.get("shady_loan_waves_remaining", 0))
            status = META.get("shady_loan_status")
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
            radius = int(META.get("coin_magnet_radius", 0))
            return f"Pickup radius +{radius}px"
        if iid == "auto_turret":
            return f"Auto-turret count {lvl}"
        if iid == "stationary_turret":
            return f"Stationary turrets {lvl}"
        if iid == "carapace":
            hp = int(META.get("carapace_shield_hp", 0))
            return f"Shield HP {hp}"
        return None

    def _prop_max_level(it):
        return it.get("max_level", None)

    def _prop_at_cap(it):
        """Return True if this item has a max_level and the player already meets or exceeds it."""
        if it.get("id") == "shady_loan":
            lvl = int(META.get("shady_loan_level", 0))
            debt = int(META.get("shady_loan_remaining_debt", 0))
            active = META.get("shady_loan_status") == "active"
            # Only block re-offer when we're already at max level AND still owe money
            return active and debt > 0 and lvl >= SHADY_LOAN_MAX_LEVEL
        if it.get("id") == "wanted_poster":
            return False  # consumable; always offer
        max_lvl = _prop_max_level(it)
        if max_lvl is None:
            return False
        lvl = _prop_level(it)
        return lvl is not None and lvl >= max_lvl

    def _interp_weight(level_num: int, points: list[tuple[int, float]]) -> float:
        """Piecewise-linear helper for rarity curves."""
        if not points:
            return 0.0
        if level_num <= points[0][0]:
            return float(points[0][1])
        for (l0, v0), (l1, v1) in zip(points, points[1:]):
            if level_num <= l1:
                t = (level_num - l0) / float(max(1, l1 - l0))
                return v0 + (v1 - v0) * t
        return float(points[-1][1])

    def _rarity_weights_for_level(level_idx_zero_based: int) -> dict[int, float]:
        """Level-scaled weighting for shop rolls (rarity 1→4 focus; rarity 5 is ultra-rare past L8)."""
        level_num = max(1, int(level_idx_zero_based) + 1)
        curves = {
            1: [(1, 100.0), (3, 70.0), (5, 45.0), (7, 25.0), (9, 15.0), (10, 10.0)],
            2: [(1, 15.0), (2, 20.0), (3, 25.0), (5, 35.0), (7, 33.0), (9, 20.0), (10, 15.0)],
            3: [(1, 3.0), (3, 6.0), (4, 12.0), (6, 25.0), (8, 32.0), (10, 35.0)],
            4: [(1, 0.0), (2, 0.0), (3, 5.0), (5, 12.0), (7, 22.0), (9, 35.0), (10, 40.0)],
            5: [(1, 0.0), (7, 0.0), (8, 1.0), (10, 5.0)],
        }
        weights = {r: _interp_weight(level_num, pts) for r, pts in curves.items()}
        if level_num < 8:
            weights[5] = 0.0  # rarity 5 stays boss-only until late-game shops
        return weights

    def roll_offers():
        level_idx = int(globals().get("current_level", 0))
        rarity_weights = _rarity_weights_for_level(level_idx)
        # base pool (no reroll)
        pool = [c for c in catalog if c.get("id") != "reroll" and not _prop_at_cap(c)]
        # start with any locked cards from previous shops
        locked_cards = []
        for lid in locked_ids:
            for c in pool:
                if c.get("id") == lid:
                    locked_cards.append(c)
                    break
        # avoid duplicates in the random pool
        pool = [c for c in pool if c.get("id") not in locked_ids]
        offers = locked_cards[:4]
        if len(offers) < 4 and pool:
            # filter by level-appropriate rarities; fall back to full pool if curve excludes everything
            weighted_pool = [c for c in pool if rarity_weights.get(int(c.get("rarity", 1)), 0.0) > 0]
            source_pool = weighted_pool or pool
            available_by_rarity: dict[int, list] = {}
            for card in source_pool:
                r = int(card.get("rarity", 1))
                available_by_rarity.setdefault(r, []).append(card)
            remaining_cards = list(source_pool)
            while len(offers) < 4 and remaining_cards:
                rarities = [r for r, cards in available_by_rarity.items() if cards]
                weights = [rarity_weights.get(r, 0.0) for r in rarities]
                if not rarities:
                    break
                if all(w <= 0 for w in weights):
                    choice = random.choice(remaining_cards)
                else:
                    filtered = [(r, w) for r, w in zip(rarities, weights) if w > 0]
                    if filtered:
                        rarities, weights = zip(*filtered)
                    choice_rarity = random.choices(list(rarities), weights=list(weights), k=1)[0]
                    cards_for_rarity = available_by_rarity.get(choice_rarity) or []
                    if not cards_for_rarity:
                        available_by_rarity.pop(choice_rarity, None)
                        continue
                    choice = random.choice(cards_for_rarity)
                offers.append(choice)
                if choice in remaining_cards:
                    remaining_cards.remove(choice)
                cr = int(choice.get("rarity", 1))
                cards_for_rarity = available_by_rarity.get(cr)
                if cards_for_rarity and choice in cards_for_rarity:
                    cards_for_rarity.remove(choice)
                if cards_for_rarity == []:
                    available_by_rarity.pop(cr, None)
        offers = offers[:4]
        if len(offers) < 4:
            # Fallback: broaden pool (ignoring rarity weights) so the shop always shows 4 prop cards
            fallback_pool = [c for c in catalog if c.get("id") != "reroll"]
            random.shuffle(fallback_pool)
            for card in fallback_pool:
                if len(offers) >= 4:
                    break
                if card in offers or _prop_at_cap(card):
                    continue
                offers.append(card)
            # If still short, allow repeats from whatever remains (better to show something than leave a blank)
            fallback_pool = [c for c in fallback_pool if not _prop_at_cap(c)] or fallback_pool
            while len(offers) < 4 and fallback_pool:
                offers.append(random.choice(fallback_pool))
        # append dedicated reroll card at the end
        offers.append(next(c for c in catalog if c.get("id") == "reroll"))
        return offers

    offers = roll_offers()

    def _is_reroll_item(it):
        return (
                it.get("id") == "reroll"
                or it.get("key") == "reroll"
                or it.get("name") in ("Reroll Offers", "Reroll")
        )

    def _split_offers(current):
        slots = [c for c in current if not _is_reroll_item(c)]
        reroll = next((c for c in current if _is_reroll_item(c)), None)
        return slots, reroll

    def _save_slots():
        globals()["_shop_slots_cache"] = copy.deepcopy(normal_slots)
        globals()["_shop_reroll_cache"] = copy.deepcopy(reroll_offer)

    # Persist shop offers to prevent free "reroll" by re-entering
    slots_cache = globals().get("_shop_slots_cache")
    reroll_cache = globals().get("_shop_reroll_cache")
    if slots_cache is not None or reroll_cache is not None:
        normal_slots = copy.deepcopy(slots_cache) if slots_cache is not None else []
        reroll_offer = copy.deepcopy(reroll_cache)
        # purge any cached cards that reached cap since last shop
        normal_slots = [c for c in normal_slots if c and not _prop_at_cap(c)]
        if not normal_slots:
            offers = roll_offers()
            normal_slots, reroll_offer = _split_offers(offers)
    else:
        normal_slots, reroll_offer = _split_offers(offers)
        _save_slots()
    hovered_uid: Optional[str] = None  # used to stabilise hover so cards don't blink
    lockbox_msg: Optional[str] = None
    lockbox_msg_until = 0
    lockbox_msg_life = 2200  # ms
    owned_rows: list = []
    while True:
        # --- draw ---
        screen.fill((16, 16, 18))
        mx, my = pygame.mouse.get_pos()
        # Title (center)
        title_surf = title_font.render("TRADER", True, (235, 235, 235))
        screen.blit(title_surf, title_surf.get_rect(center=(VIEW_W // 2, 80)))
        # Spoils (center under title)
        money_surf = font.render(f"Coins: {META['spoils']}", True, (255, 230, 120))
        screen.blit(money_surf, money_surf.get_rect(center=(VIEW_W // 2, 130)))
        now_ms = pygame.time.get_ticks()
        overlay_surf = None
        overlay_alpha = 255
        if lockbox_msg and now_ms < lockbox_msg_until:
            lb_lvl = int(META.get("lockbox_level", 0))
            if lb_lvl > 0:
                protected = lockbox_protected_min(max(0, int(META.get("spoils", 0))), lb_lvl)
                msg_txt = f"{protected} coins restored"
                overlay_surf = pygame.font.SysFont("Franklin Gothic Medium", 96).render(msg_txt, True, (255, 230, 160))
                t = max(0.0, min(1.0, (lockbox_msg_until - now_ms) / float(lockbox_msg_life)))
                overlay_alpha = int(255 * t)
        # Offers row ? keep slot spacing even if some cards are gone
        card_w, card_h = 220, 180
        gap = 22
        y = 200
        total_w = len(normal_slots) * card_w + max(0, (len(normal_slots) - 1)) * gap
        start_x = (VIEW_W - total_w) // 2 if len(normal_slots) > 0 else VIEW_W // 2
        rects = []  # (rect, item, dyn_cost, is_capped, uid, lock_rect, slot_idx)
        x = start_x
        for slot_idx, it in enumerate(normal_slots):
            r = pygame.Rect(x, y, card_w, card_h)
            x += card_w + gap
            if it is None:
                continue
            level_idx = int(globals().get("current_level", 0))
            cur_lvl = _prop_level(it)
            dyn_cost = shop_price(int(it["cost"]), level_idx, kind="normal", prop_level=cur_lvl)
            max_lvl = _prop_max_level(it)
            is_capped = (max_lvl is not None and cur_lvl is not None and cur_lvl >= max_lvl)
            uid = it.get("id") or it.get("name")
            is_hover = (uid == hovered_uid)
            lock_rect = pygame.Rect(0, 0, 22, 22)
            lock_rect.topright = (r.right - 8, r.top + 8)
            if is_capped:
                bg_col = SHOP_BOX_BG_DISABLED
                border_col = SHOP_BOX_BORDER_DISABLED
            elif is_hover:
                bg_col = SHOP_BOX_BG_HOVER
                border_col = SHOP_BOX_BORDER_HOVER
            else:
                bg_col = SHOP_BOX_BG
                border_col = SHOP_BOX_BORDER
            pygame.draw.rect(screen, bg_col, r, border_radius=14)
            pygame.draw.rect(screen, border_col, r, 2, border_radius=14)
            if is_hover:
                title_s = font.render(it["name"], True, (235, 235, 235))
                words = it.get("desc", "").split()
                lines_wrap = []
                if words:
                    max_w = r.width - 28
                    line = ""
                    for w2 in words:
                        test = (line + " " + w2).strip()
                        test_surf = desc_font.render(test, True, (210, 210, 210))
                        if test_surf.get_width() > max_w and line:
                            lines_wrap.append(line)
                            line = w2
                        else:
                            line = test
                    if line:
                        lines_wrap.append(line)
                line_h = desc_font.get_linesize()
                block_h = title_s.get_height() + 4 + len(lines_wrap) * line_h
                top_y = r.centery - block_h // 2
                title_rect = title_s.get_rect(midtop=(r.centerx, top_y))
                screen.blit(title_s, title_rect)
                yy = title_rect.bottom + 4
                for ln in lines_wrap:
                    ln_surf = desc_font.render(ln, True, (210, 210, 210))
                    screen.blit(ln_surf, ln_surf.get_rect(midtop=(r.centerx, yy)))
                    yy += line_h
            else:
                name_surf = font.render(it["name"], True, (235, 235, 235))
                screen.blit(name_surf, name_surf.get_rect(midtop=(r.centerx, r.y + 10)))
                col = ((255, 230, 120) if META["spoils"] >= dyn_cost else (160, 140, 120))
                price_txt = f"$ {dyn_cost}"
                price_surf = font.render(price_txt, True, col)
                screen.blit(price_surf, price_surf.get_rect(midbottom=(r.centerx, r.bottom - 10)))
                rarity = int(it.get("rarity", 1))
                dot_r = 4
                for j in range(rarity):
                    cx = r.left + 14 + j * (dot_r * 2 + 6)
                    cy = r.bottom - 18
                    pygame.draw.circle(screen, (180, 160, 220), (cx, cy), dot_r)
            if max_lvl is not None and cur_lvl is not None:
                lvl_text = f"{cur_lvl}/{max_lvl}"
                lvl_color = ((180, 230, 255) if not is_capped else (140, 150, 160))
                lvl_surf = font.render(lvl_text, True, lvl_color)
                screen.blit(lvl_surf, lvl_surf.get_rect(bottomright=(r.right - 8, r.bottom - 6)))
            locked = it.get("id") in locked_ids
            if locked:
                bg_col = SHOP_BOX_BORDER_HOVER
                border_col = SHOP_BOX_BG
                icon_col = (20, 20, 22)
            else:
                bg_col = SHOP_BOX_BG
                border_col = SHOP_BOX_BORDER
                icon_col = (235, 235, 235)
            pygame.draw.rect(screen, bg_col, lock_rect, border_radius=6)
            pygame.draw.rect(screen, border_col, lock_rect, 2, border_radius=6)
            icon = desc_font.render("L", True, icon_col)
            screen.blit(icon, icon.get_rect(center=lock_rect.center))
            rects.append((r, it, dyn_cost, is_capped, uid, lock_rect, slot_idx))
        owned = []
        for itm in catalog:
            lvl = _prop_level(itm)
            if itm.get("id") == "shady_loan":
                status = META.get("shady_loan_status")
                if status in ("repaid", "defaulted") and (lvl is None or lvl <= 0):
                    lvl = max(1, int(META.get("shady_loan_last_level", 1)))  # keep visible in possessions after resolution
            max_lvl = _prop_max_level(itm)
            if lvl is not None and lvl > 0 and itm.get("id") != "reroll":
                owned.append({"itm": itm, "lvl": lvl, "max": max_lvl})
        if owned:
            margin_side = 40
            margin_bottom = 70
            line_h = font.get_linesize()
            name_w_max = max(font.render(ent["itm"]["name"], True, (0, 0, 0)).get_width() for ent in owned)
            col_w = max(170, name_w_max + 60)
            col_gap = 14
            cols = 1
            if len(owned) > 8:
                cols = 2
            if len(owned) > 16:
                cols = 3
            rows = max(1, math.ceil(len(owned) / cols))
            panel_w = col_w * cols + col_gap * (cols - 1) + 28
            header_h = line_h
            panel_h = 16 + header_h + rows * line_h + 12
            # Dock under the NEXT button and hug the left margin.
            # nudge right for balance but keep some margin
            panel_x = max(margin_side, int(VIEW_W * 0.075))
            # place below the buttons but keep on-screen
            base_y = y + card_h + 220
            panel_y = min(VIEW_H - panel_h - margin_bottom, base_y)
            panel = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
            pygame.draw.rect(screen, SHOP_BOX_BG, panel, border_radius=14)
            pygame.draw.rect(screen, SHOP_BOX_BORDER, panel, 2, border_radius=14)
            header = font.render("Possession", True, (220, 220, 230))  # 或你喜欢的标题
            screen.blit(header, header.get_rect(left=panel.x + 14, top=panel.y + 8))
            base_y = panel.y + 8 + header_h + 4
            owned_rows.clear()
            for idx, ent in enumerate(owned):
                name = ent["itm"]["name"]
                lvl = ent["lvl"]
                max_lvl = ent["max"]
                col = idx % cols
                row = idx // cols
                x0 = panel.x + 14 + col * (col_w + col_gap)
                y0 = base_y + row * line_h
                name_color = (210, 210, 210)
                lvl_color = (180, 230, 255)
                if ent["itm"].get("id") == "shady_loan" and META.get("shady_loan_status") == "defaulted":
                    name_color = (200, 80, 80)
                    lvl_color = (220, 120, 120)
                name_surf = font.render(name, True, name_color)
                lvl_str = f"{lvl}/{max_lvl}" if max_lvl is not None else f"x{lvl}"
                lvl_surf = font.render(lvl_str, True, lvl_color)
                screen.blit(name_surf, (x0, y0))
                screen.blit(lvl_surf, lvl_surf.get_rect(right=x0 + col_w, top=y0))
                owned_rows.append((pygame.Rect(x0, y0, col_w, line_h), ent))
        # --- Reroll 按钮：在卡片下方单独一行 ---
        reroll_rect = None
        if reroll_offer is not None:
            level_idx = int(globals().get("current_level", 0))
            reroll_dyn_cost = shop_price(
                int(reroll_offer["cost"]), level_idx, kind="reroll"
            )
            reroll_rect = pygame.Rect(0, 0, 220, 52)
            reroll_rect.center = (VIEW_W // 2, y + card_h + 70)
            can_afford = META.get("spoils", 0) >= reroll_dyn_cost
            if not can_afford:
                bg = SHOP_BOX_BG_DISABLED
                border = SHOP_BOX_BORDER_DISABLED
            elif reroll_rect.collidepoint((mx, my)):
                bg = SHOP_BOX_BG_HOVER
                border = SHOP_BOX_BORDER_HOVER
            else:
                bg = SHOP_BOX_BG
                border = SHOP_BOX_BORDER
            pygame.draw.rect(screen, bg, reroll_rect, border_radius=14)
            pygame.draw.rect(screen, border, reroll_rect, 2, border_radius=14)
            label = btn_font.render("Reroll", True, (235, 235, 235))
            label_rect = label.get_rect(center=(reroll_rect.centerx, reroll_rect.centery - 8))
            screen.blit(label, label_rect)
            cost_col = (255, 230, 120) if can_afford else (160, 140, 120)
            cost_surf = font.render(f"$ {reroll_dyn_cost}", True, cost_col)
            cost_rect = cost_surf.get_rect(center=(reroll_rect.centerx, reroll_rect.centery + 12))
            screen.blit(cost_surf, cost_rect)
            # 也把 reroll 按钮加入 rects，这样原来的点击逻辑可以直接使用
            uid = reroll_offer.get("id") or reroll_offer.get("name")
            rects.append((reroll_rect, reroll_offer, reroll_dyn_cost, False, uid, None, None))
        # possession hover tooltip
        tooltip_txt = None
        tooltip_pos = None
        if owned_rows:
            for row_rect, ent in owned_rows:
                if row_rect.collidepoint((mx, my)):
                    tooltip_txt = _owned_live_text(ent["itm"], ent["lvl"])
                    tooltip_pos = (row_rect.right + 10, row_rect.centery)
                    break
        if tooltip_txt:
            tip_surf = desc_font.render(tooltip_txt, True, (235, 235, 235))
            pad = 8
            bg = pygame.Surface((tip_surf.get_width() + pad * 2, tip_surf.get_height() + pad * 2), pygame.SRCALPHA)
            pygame.draw.rect(bg, (30, 30, 36, 230), bg.get_rect(), border_radius=10)
            pygame.draw.rect(bg, (120, 150, 210, 240), bg.get_rect(), 2, border_radius=10)
            bg.blit(tip_surf, (pad, pad))
            bx = min(VIEW_W - bg.get_width() - 10, tooltip_pos[0])
            by = max(60, min(VIEW_H - bg.get_height() - 60, tooltip_pos[1] - bg.get_height() // 2))
            screen.blit(bg, (bx, by))
        # --- NEXT 按钮：在 Reroll 下面单独一行 ---
        close = pygame.Rect(0, 0, 220, 56)
        if reroll_rect is not None:
            next_y = reroll_rect.bottom + 40
        else:
            next_y = y + card_h + 120
        close.center = (VIEW_W // 2, next_y)
        pygame.draw.rect(screen, (50, 50, 50), close, border_radius=10)
        pygame.draw.rect(screen, (120, 120, 120), close, 2, border_radius=10)
        txt = btn_font.render("NEXT", True, (230, 230, 230))
        screen.blit(txt, txt.get_rect(center=close.center))
        if overlay_surf:
            overlay_surf.set_alpha(overlay_alpha)
            screen.blit(overlay_surf, overlay_surf.get_rect(center=(VIEW_W // 2, VIEW_H // 2)))
        if not did_menu_hex:
            run_pending_menu_transition(screen)
            did_menu_hex = True
        pygame.display.flip()
        # --- input ---
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                # Pause menu over the shop; continue/settings return to shop
                bg = screen.copy()
                choice = pause_from_overlay(screen, bg)
                if choice in (None, "continue", "settings"):
                    flush_events()
                    break
                if choice == "restart":
                    queue_menu_transition(screen.copy())
                    globals()["_restart_from_shop"] = True
                if choice == "home":
                    queue_menu_transition(screen.copy())
                flush_events()
                return choice  # home / restart / exit
            if ev.type == pygame.MOUSEMOTION:
                hovered_uid = None
                for r, it, dyn_cost, is_capped, uid, lock_rect, slot_idx in rects:
                    if r.collidepoint(ev.pos):
                        hovered_uid = uid
                        break
            if ev.type == pygame.MOUSEBUTTONDOWN:
                if close.collidepoint(ev.pos):
                    # animation add if needed
                    flush_events()
                    # Show Golden Interest payout before biome selection (only if owned)
                    if int(META.get("golden_interest_level", 0)) > 0:
                        gain = apply_golden_interest_payout()
                        show_golden_interest_popup(screen, gain, int(META.get("spoils", 0)))
                    # <<< 在 NEXT 之后弹出“场景四选一” >>>
                    # animation add if needed
                    loan_outcome = apply_shady_loan_repayment()
                    if loan_outcome:
                        show_shady_loan_popup(screen, loan_outcome)
                    chosen_biome = show_biome_picker_in_shop(screen)
                    # 识别从翻卡界面透传出来的暂停菜单选择
                    if chosen_biome in ("__HOME__", "__RESTART__", "__EXIT__"):
                        if chosen_biome == "__RESTART__":
                            globals()["_restart_from_shop"] = True
                        return {"__HOME__": "home",
                                "__RESTART__": "restart",
                                "__EXIT__": "exit"}[chosen_biome]
                    globals()["_next_biome"] = chosen_biome  # 正常选择到场景名
                    _clear_shop_cache()
                    return None  # 照常结束商店，进入下一关
                # 1) lock toggle check – click on small lock box
                handled_lock = False
                for r, it, dyn_cost, is_capped, uid, lock_rect, slot_idx in rects:
                    if lock_rect and lock_rect.collidepoint(ev.pos):
                        card_id = it.get("id")
                        if card_id:
                            if card_id in locked_ids:
                                locked_ids.remove(card_id)
                            else:
                                locked_ids.append(card_id)
                            _persist_locked_ids()
                        handled_lock = True
                        break
                if handled_lock:
                    continue
                for r, it, dyn_cost, is_capped, uid, lock_rect, slot_idx in rects:
                    # don't allow buying a capped item any further, but reroll is always allowed
                    is_reroll = (it.get("id") == "reroll"
                                 or it.get("key") == "reroll"
                                 or it.get("name") == "Reroll Offers")
                    if not is_reroll and is_capped:
                        continue
                    if r.collidepoint(ev.pos) and META["spoils"] >= dyn_cost:
                        coins_before_buy = int(META.get("spoils", 0))
                        META["spoils"] -= dyn_cost
                        card_id = it.get("id")
                        if card_id and card_id in locked_ids:
                            locked_ids.remove(card_id)
                            _persist_locked_ids()
                        if is_reroll or it.get("apply") == "reroll":
                            offers = roll_offers()  # Price stays the same
                            normal_slots, reroll_offer = _split_offers(offers)
                            # update caches with id lists
                            globals()["_shop_slot_ids_cache"] = [o.get("id") if o else None for o in normal_slots]
                            globals()["_shop_reroll_id_cache"] = reroll_offer.get("id") if reroll_offer else None
                            _save_slots()
                        else:
                            it["apply"]()
                            if card_id == "lockbox":
                                lockbox_msg = "lockbox"
                                lockbox_msg_until = pygame.time.get_ticks() + lockbox_msg_life
                            # Remove the purchased card from its slot (leave blank space)
                            if 0 <= slot_idx < len(normal_slots):
                                normal_slots[slot_idx] = None
                            hovered_uid = None
                            # If all slots are empty, auto-reroll a fresh set
                            if all(s is None for s in normal_slots):
                                offers = roll_offers()
                                normal_slots, reroll_offer = _split_offers(offers)
                                globals()["_shop_slot_ids_cache"] = [o.get("id") if o else None for o in normal_slots]
                                globals()["_shop_reroll_id_cache"] = reroll_offer.get("id") if reroll_offer else None
                                _save_slots()
                            else:
                                globals()["_shop_slot_ids_cache"] = [o.get("id") if o else None for o in normal_slots]
                                globals()["_shop_reroll_id_cache"] = reroll_offer.get("id") if reroll_offer else None
                                _save_slots()
                clock.tick(60)


def show_biome_picker_in_shop(screen) -> str:
    """在商店 NEXT 之后弹出的“下关场景”四选一卡面。返回被选择的场景名。"""
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont(None, 56)
    font = pygame.font.SysFont(None, 26)
    back_font = pygame.font.SysFont(None, 48)
    # 随机打乱四张卡的排列顺序（卡面名称固定）
    names = list(SCENE_BIOMES)
    random.shuffle(names)
    # 卡片布局
    card_w, card_h = 180, 240
    gap = 20
    total_w = len(names) * card_w + (len(names) - 1) * gap
    start_x = (VIEW_W - total_w) // 2
    y = 160
    # 卡片对象
    cards = []
    for i, name in enumerate(names):
        x = start_x + i * (card_w + gap)
        rect = pygame.Rect(x, y, card_w, card_h)
        cards.append({"name": name, "rect": rect, "revealed": False})
    chosen = None  # 只允许选择一张
    # 确认按钮
    confirm = pygame.Rect(0, 0, 240, 56)
    confirm.center = (VIEW_W // 2, y + card_h + 90)
    start_menu_surf = None

    def draw():
        screen.fill((16, 16, 18))
        # 标题
        title = title_font.render("CHOOSE NEXT DOMAIN", True, (235, 235, 235))
        screen.blit(title, title.get_rect(center=(VIEW_W // 2, 90)))
        # 画四张卡
        for c in cards:
            r = c["rect"]
            if c["revealed"]:
                # 正面：高亮的卡面 + 名称
                pygame.draw.rect(screen, (60, 66, 70), r, border_radius=12)
                pygame.draw.rect(screen, (200, 200, 210), r, 2, border_radius=12)
                name = c["name"].upper()
                # 名称可能较长，分两行居中
                parts = name.split()
                text_lines = [" ".join(parts[:2]), " ".join(parts[2:])] if len(parts) > 2 else [name]
                ty = r.centery - (len(text_lines) * 22) // 2
                for line in text_lines:
                    surf = font.render(line, True, (240, 240, 240))
                    screen.blit(surf, surf.get_rect(center=(r.centerx, ty)))
                    ty += 28
                # 若是被选中的卡，再加一道边框
                if chosen == c["name"]:
                    pygame.draw.rect(screen, (255, 215, 120), r.inflate(6, 6), 3, border_radius=14)
            else:
                # 背面：深色 + “？”
                pygame.draw.rect(screen, (36, 38, 42), r, border_radius=12)
                pygame.draw.rect(screen, (80, 80, 84), r, 2, border_radius=12)
                q = back_font.render("?", True, (180, 180, 190))
                screen.blit(q, q.get_rect(center=r.center))
        # 确认按钮（未选时灰掉）
        if chosen:
            pygame.draw.rect(screen, (50, 50, 50), confirm, border_radius=10)
            txt = pygame.font.SysFont(None, 32).render("CONFIRM", True, (235, 235, 235))
        else:
            pygame.draw.rect(screen, (35, 35, 35), confirm, border_radius=10)
            txt = pygame.font.SysFont(None, 32).render("CONFIRM", True, (120, 120, 120))
        screen.blit(txt, txt.get_rect(center=confirm.center))
        run_pending_menu_transition(screen)
        pygame.display.flip()

    while True:
        draw()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit();
                sys.exit()
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                bg = screen.copy()
                pick = pause_from_overlay(screen, bg)
                if pick in (None, "continue", "settings"):
                    flush_events()
                    continue  # 回到翻卡界面
                if pick == "home":
                    queue_menu_transition(pygame.display.get_surface().copy())
                    flush_events()
                    return "__HOME__"
                if pick == "restart":
                    queue_menu_transition(pygame.display.get_surface().copy())
                    flush_events()
                    return "__RESTART__"
                if pick == "exit":
                    pygame.quit()
                    sys.exit()
            if ev.type == pygame.MOUSEBUTTONDOWN:
                # 点击卡片：若还未选中任何卡，则把这张翻开并选中；其他保持背面
                if chosen is None:
                    for c in cards:
                        if c["rect"].collidepoint(ev.pos):
                            c["revealed"] = True
                            chosen = c["name"]
                            break
                # 点击确认：只有当 chosen 存在（即至少翻开并选择了一张）才生效
                if chosen and confirm.collidepoint(ev.pos):
                    # animation add if needed
                    queue_menu_transition(pygame.display.get_surface().copy())
                    flush_events()
                    return chosen
        clock.tick(60)


def is_boss_level(level_idx_zero_based: int) -> bool:
    # UI shows Lv = level_idx_zero_based + 1
    return ((level_idx_zero_based + 1) % BOSS_EVERY_N_LEVELS) == 0


def budget_for_level(level_idx_zero_based: int) -> int:
    # Identical within level; exponential per level (clamped to a sane minimum)
    return max(THREAT_BUDGET_MIN,
               int(round(THREAT_BUDGET_BASE * (THREAT_BUDGET_EXP ** level_idx_zero_based))))


def _pick_type_by_budget(rem: int, level_idx_zero_based: int) -> Optional[str]:
    def _unlocked(t: str) -> bool:
        if t == "splinter":
            return level_idx_zero_based >= SPLINTER_UNLOCK_LEVEL
        return True  # others always unlocked

    choices = [(t, w) for t, w in THREAT_WEIGHTS.items()
               if THREAT_COSTS.get(t, 999) <= rem and _unlocked(t)]
    if not choices:
        return None
    total = sum(w for _, w in choices)
    r = random.uniform(0, total)
    acc = 0.0
    for t, w in choices:
        acc += w
        if r <= acc:
            return t
    return choices[-1][0]


def _spawn_positions(game_state: "GameState", player: "Player", enemies: List["Enemy"], want: int) -> List[
    Tuple[int, int]]:
    """Reuse your existing constraints: not blocked, not too close to player, not overlapping enemies."""
    all_pos = [(x, y) for x in range(GRID_SIZE) for y in range(GRID_SIZE)]
    blocked = set(game_state.obstacles.keys()) | set((i.x, i.y) for i in getattr(game_state, "items", []))
    px, py = int(player.rect.centerx // CELL_SIZE), int((player.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE)
    # Manhattan ≥ 6 tiles from player like before
    cand = [p for p in all_pos if p not in blocked and abs(p[0] - px) + abs(p[1] - py) >= 6]
    random.shuffle(cand)
    zcells = {(int((z.x + z.size // 2) // CELL_SIZE), int((z.y + z.size // 2) // CELL_SIZE)) for z in enemies}
    out = []
    for p in cand:
        if p in zcells:
            continue
        out.append(p)
        if len(out) >= want:
            break
    return out


def promote_to_boss(z: "Enemy"):
    """Promote a single enemy instance to boss (stats on top of current scaling)."""
    z.is_boss = True
    z.max_hp = int(z.max_hp * BOSS_HP_MULT_EXTRA)
    z.hp = z.max_hp
    z.attack = int(z.attack * BOSS_ATK_MULT_EXTRA)
    z.speed += BOSS_SPD_ADD_EXTRA
    # === enlarge physical footprint ===
    # 把 BOSS 的 AABB 拉大到 ~1.6 格高（等距里观感是“很占屏”）
    old_cx, old_cy = z.rect.center
    z.size = int(CELL_SIZE * 1.6)  # 占屏与卡位都更像“BOSS”
    z.rect = pygame.Rect(0, 0, z.size, z.size)
    z.rect.center = (old_cx, old_cy)
    # 同步世界坐标（你的 move/渲染有用到 x/y）
    z.x = float(z.rect.x)
    z.y = float(z.rect.y - INFO_BAR_HEIGHT)


def spawn_wave_with_budget(game_state: "GameState",
                           player: "Player",
                           current_level: int,
                           wave_index: int,
                           enemies: List["Enemy"],
                           cap: int) -> int:
    """
    Spend the per-level budget on new enemies, respecting cap.
    Returns the number spawned.
    """
    if len(enemies) >= cap:
        return 0
    # base budget for this level (identical every spawn this level)
    budget = budget_for_level(current_level)
    # boss level first spawn: extra budget & force exactly one boss
    force_boss = is_boss_level(current_level) and (wave_index == 0)
    if force_boss:
        budget = int(budget * THREAT_BOSS_BONUS)
    # optimistic position pool (ask for up to budget cells)
    spots = _spawn_positions(game_state, player, enemies, want=budget)
    spawned = 0
    boss_done = False
    # ==== 金币大盗：随机在非Boss关卡与波次出现（每关最多一只；Lv1-2不出现）====
    try:
        level_idx = int(globals().get("current_level", 0))
    except Exception:
        level_idx = 0
    # 当前对局剩余时间（秒），没有的话就用默认关卡时长兜底
    tleft = float(globals().get("_time_left_runtime", LEVEL_TIME_LIMIT))
    if (tleft > 20.0  # ★ 剩余时间不足 20 秒，不再刷 Bandit
            and level_idx >= BANDIT_MIN_LEVEL_IDX
            and not is_boss_level(level_idx)
            and not getattr(game_state, "bandit_spawned_this_level", False)
            and random.random() < BANDIT_SPAWN_CHANCE_PER_WAVE
            and spots):
        gx, gy = spots.pop()  # 占用一个出生点
        cx = int(gx * CELL_SIZE + CELL_SIZE * 0.5)
        cy = int(gy * CELL_SIZE + CELL_SIZE * 0.5 + INFO_BAR_HEIGHT)
        bandit = make_coin_bandit((cx, cy), level_idx, wave_index, int(budget),
                                  player_dps=compute_player_dps(player))
        lb_lvl = int(META.get("lockbox_level", 0))
        if lb_lvl > 0:
            baseline_coins = max(0, int(META.get("spoils", 0)) + int(getattr(game_state, "spoils_gained", 0)))
            bandit.lockbox_level = lb_lvl
            bandit.lockbox_baseline = baseline_coins
            bandit.lockbox_floor = lockbox_protected_min(baseline_coins, lb_lvl)
        radar_lvl = int(META.get("bandit_radar_level", 0))
        if radar_lvl > 0:
            bandit.radar_tagged = True
            bandit.radar_level = radar_lvl
            bandit._radar_base_speed = float(bandit.speed)
            mult = BANDIT_RADAR_SLOW_MULT[min(radar_lvl - 1, len(BANDIT_RADAR_SLOW_MULT) - 1)]
            dur = BANDIT_RADAR_SLOW_DUR[min(radar_lvl - 1, len(BANDIT_RADAR_SLOW_DUR) - 1)]
            bandit.speed = float(bandit.speed) * float(mult)
            bandit.radar_slow_left = float(dur)
            bandit.radar_ring_period = 2.0
            bandit.radar_ring_phase = 0.0
        enemies.append(bandit)
        game_state.bandit_spawned_this_level = True
        game_state.pending_focus = ("bandit", (cx, cy))
        # 视觉提示：使用屏幕横幅确保可见；若不可用则退化为飘字
        if hasattr(game_state, "flash_banner"):
            game_state.flash_banner("COIN BANDIT!", sec=1.5)
        else:
            game_state.add_damage_text(cx, cy, "COIN BANDIT!", crit=True, kind="shield")
        # 可选：地面金色提示圈（用 TelegraphCircle）
        if hasattr(game_state, "telegraphs"):
            game_state.telegraphs.append(
                TelegraphCircle(cx, cy, int(CELL_SIZE * 1.1), 0.9, kind="bandit", color=(255, 215, 0)))
        apply_biome_on_enemy_spawn(bandit, game_state)
    # spend budget until no type fits or cap/positions exhausted
    i = 0
    while i < len(spots) and len(enemies) < cap:
        gx, gy = spots[i]
        i += 1
        # if we must place a boss, do it once, then continue budget spending
        if force_boss and not boss_done:
            gx0 = max(0, min(gx, GRID_SIZE - BOSS_FOOTPRINT_TILES))
            gy0 = max(0, min(gy, GRID_SIZE - BOSS_FOOTPRINT_TILES))
            # 第5关采用 Twin；其余 Boss 关单体
            if ENABLE_TWIN_BOSS and (current_level in TWIN_BOSS_LEVELS):
                # Clamp 2x2 footprints fully inside the grid and keep 2 tiles between them
                gx2 = max(0, min(gx0 + BOSS_FOOTPRINT_TILES, GRID_SIZE - BOSS_FOOTPRINT_TILES))
                gy2 = gy0
                b1 = create_memory_devourer((gx0, gy0), current_level)
                b2 = create_memory_devourer((gx2, gy2), current_level)
                twin_id = random.randint(1000, 9999)
                # opposite lanes so they don’t body-block each other
                b1.twin_slot = +1
                b2.twin_slot = -1

                # Clear any obstacles inside their initial 2×2 footprints
                def _clear_footprint(ent):
                    r = pygame.Rect(int(ent.x), int(ent.y + INFO_BAR_HEIGHT), int(ent.size), int(ent.size))
                    for gp, ob in list(game_state.obstacles.items()):
                        if ob.rect.colliderect(r):
                            del game_state.obstacles[gp]

                _clear_footprint(b1)
                _clear_footprint(b2)
                # domain spawn effects (Stone shields, etc.)
                apply_biome_on_enemy_spawn(b1, game_state)
                apply_biome_on_enemy_spawn(b2, game_state)
                # (optional) start the HUD smoothing at the current fraction
                for _b in (b1, b2):
                    if getattr(_b, "shield_hp", 0) > 0 and getattr(_b, "max_hp", 0) > 0:
                        _b._hud_shield_vis = _b.shield_hp / float(max(1, _b.max_hp))
                if hasattr(b1, "bind_twin"):
                    b1.bind_twin(b2, twin_id)
                else:
                    b1.twin_id = twin_id
                    b2.twin_id = twin_id
                    b1._twin_partner_ref = b2
                    b2._twin_partner_ref = b1
                b1._spawn_wave_tag = wave_index
                b2._spawn_wave_tag = wave_index
                # --- NEW: queue boss spawn camera focuses (both bosses)
                # Prefer rect centers if available; otherwise derive from tiles:
                try:
                    c1 = (int(b1.rect.centerx), int(b1.rect.centery))
                    c2 = (int(b2.rect.centerx), int(b2.rect.centery))
                except Exception:
                    c1 = (int((gx0 + 1.0) * CELL_SIZE), int((gy0 + 1.0) * CELL_SIZE + INFO_BAR_HEIGHT))
                    c2 = (int((gx2 + 1.0) * CELL_SIZE), int((gy2 + 1.0) * CELL_SIZE + INFO_BAR_HEIGHT))
                game_state.focus_queue = getattr(game_state, "focus_queue", [])
                game_state.focus_queue += [("boss", c1), ("boss", c2)]
                enemies.append(b1);
                enemies.append(b2)
                boss_done = True
            elif current_level in MISTWEAVER_LEVELS:
                # Mistweaver：第10关
                z = MistweaverBoss((gx0, gy0), current_level)
                r = pygame.Rect(int(z.x), int(z.y + INFO_BAR_HEIGHT), int(z.size), int(z.size))
                for gp, ob in list(game_state.obstacles.items()):
                    if ob.rect.colliderect(r):
                        del game_state.obstacles[gp]
                apply_biome_on_enemy_spawn(z, game_state)
                z._hud_shield_vis = (z.shield_hp / float(max(1, z.max_hp))) if getattr(z, "shield_hp", 0) > 0 else 0.0
                z._spawn_wave_tag = wave_index
                enemies.append(z)
                # After enemies.append(mist)
                cx, cy = (int(z.rect.centerx), int(z.rect.centery))
                game_state.focus_queue = getattr(game_state, "focus_queue", [])
                game_state.focus_queue.append(("boss", (cx, cy)))
                boss_done = True
                # 让本关启动雾场（GameState 里会响应）
                if hasattr(game_state, "request_fog_field"):
                    game_state.request_fog_field(player)
            else:
                # 其它 Boss 关：单体 Memory Devourer
                z = create_memory_devourer((gx0, gy0), current_level)
                r = pygame.Rect(int(z.x), int(z.y + INFO_BAR_HEIGHT), int(z.size), int(z.size))
                for gp, ob in list(game_state.obstacles.items()):
                    if ob.rect.colliderect(r):
                        del game_state.obstacles[gp]
                apply_biome_on_enemy_spawn(z, game_state)
                z._hud_shield_vis = (z.shield_hp / float(max(1, z.max_hp))) if getattr(z, "shield_hp", 0) > 0 else 0.0
                z._spawn_wave_tag = wave_index
                # NEW: queue single boss focus
                try:
                    c = (int(z.rect.centerx), int(z.rect.centery))
                except Exception:
                    c = (int((gx0 + 1.0) * CELL_SIZE), int((gy0 + 1.0) * CELL_SIZE + INFO_BAR_HEIGHT))
                game_state.focus_queue = getattr(game_state, "focus_queue", [])
                game_state.focus_queue.append(("boss", c))
                enemies.append(z)
                boss_done = True
            continue
        # choose a type that fits remaining budget
        remaining = budget - sum(THREAT_COSTS.get(getattr(z, "type", "basic"), 0) for z in enemies if
                                 getattr(z, "_spawn_wave_tag", -1) == wave_index)
        t = _pick_type_by_budget(max(1, remaining), current_level)
        if not t:
            break  # can't afford any type
        z = make_scaled_enemy((gx, gy), t,
                               current_level,
                               # IMPORTANT: if this is a boss level first wave,
                               # pass wave_index=1 for non-boss spawns to avoid accidental boss flag in older code
                               (1 if (is_boss_level(current_level) and wave_index == 0) else wave_index))
        # mark which wave inserted this enemy (used above to compute remaining)
        z._spawn_wave_tag = wave_index
        apply_biome_on_enemy_spawn(z, game_state)
        enemies.append(z)
        spawned += 1
    return spawned


def trigger_twin_enrage(dead_boss, enemies, game_state):
    """当一只 Twin Boss 死亡时，令存活的孪生体回满血并进入狂暴。"""
    if not getattr(dead_boss, "is_boss", False):
        return
    tid = getattr(dead_boss, "twin_id", None)
    if tid is None:
        # 若没 twin_id，尝试用绑定的引用取另一只
        ref = getattr(dead_boss, "_twin_partner_ref", None)
        partner = ref() if callable(ref) else ref
    else:
        partner = None
        ref = getattr(dead_boss, "_twin_partner_ref", None)
        if callable(ref):
            partner = ref()
        if partner is None:
            # 在场上按 twin_id 搜索另一只
            for z in enemies:
                if z is not dead_boss and getattr(z, "is_boss", False) and getattr(z, "twin_id", None) == tid:
                    partner = z
                    break
    if partner and getattr(partner, "hp", 0) > 0 and not getattr(partner, "_twin_powered", False):
        if hasattr(partner, "on_twin_partner_death"):
            partner.on_twin_partner_death()
        else:
            # 兜底：没有方法也直接赋值
            partner.hp = int(getattr(partner, "max_hp", partner.hp))
            partner.attack = int(partner.attack * TWIN_ENRAGE_ATK_MULT)
            partner.speed = int(partner.speed + TWIN_ENRAGE_SPD_ADD)
            partner._twin_powered = True
        # 小提示：给点飘字/特效
        try:
            game_state.add_damage_text(partner.rect.centerx, partner.rect.centery, "ENRAGED", crit=False, kind="shield")
        except Exception:
            pass


# ==================== 数据结构 ====================
class Graph:
    def __init__(self):
        self.edges: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        self.weights: Dict[Tuple[Tuple[int, int], Tuple[int, int]], float] = {}

    def add_edge(self, a, b, w):
        self.edges.setdefault(a, []).append(b)
        self.weights[(a, b)] = w

    def neighbors(self, node): return self.edges.get(node, [])

    def cost(self, a, b): return self.weights.get((a, b), float('inf'))


class Obstacle:
    def __init__(self, x: int, y: int, obstacle_type: str, health: Optional[int] = None):
        px = x * CELL_SIZE;
        py = y * CELL_SIZE + INFO_BAR_HEIGHT
        self.rect = pygame.Rect(px, py, CELL_SIZE, CELL_SIZE)
        self.type: str = obstacle_type
        self.health: Optional[int] = health

    def is_destroyed(self) -> bool:
        return self.type == "Destructible" and self.health <= 0

    @property
    def grid_pos(self):
        return self.rect.x // CELL_SIZE, (self.rect.y - INFO_BAR_HEIGHT) // CELL_SIZE


class FogLantern(Obstacle):
    def __init__(self, x: int, y: int, hp: int = FOG_LANTERN_HP):
        super().__init__(x, y, "Lantern", health=hp)
        self.nonblocking = False  # 关键：不参与移动碰撞
        # 更明显一点的可视尺寸
        self.rect = pygame.Rect(self.rect.x + 6, self.rect.y + 6, CELL_SIZE - 12, CELL_SIZE - 12)

    @property
    def alive(self):
        return self.health is None or self.health > 0


class MainBlock(Obstacle):
    def __init__(self, x: int, y: int, health: Optional[int] = MAIN_BLOCK_HEALTH):
        super().__init__(x, y, "Destructible", health)
        self.is_main_block = True


class Item:
    def __init__(self, x: int, y: int, is_main=False):
        self.x = x
        self.y = y
        self.is_main = is_main
        self.radius = CELL_SIZE // 3
        self.center = (self.x * CELL_SIZE + CELL_SIZE // 2, self.y * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT)
        self.rect = pygame.Rect(self.center[0] - self.radius, self.center[1] - self.radius, self.radius * 2,
                                self.radius * 2)


class Player:
    def __init__(self, pos: Tuple[int, int], speed: int = PLAYER_SPEED):
        self.x = pos[0] * CELL_SIZE
        self.y = pos[1] * CELL_SIZE
        self.speed = float(speed)
        self.size = int(CELL_SIZE * 0.6)
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)
        self.max_hp = int(PLAYER_MAX_HP)
        self.hp = int(PLAYER_MAX_HP)
        # 暴击：base + 附加
        self.crit_chance = max(0.0,
                               min(0.95, float(META.get("base_crit", CRIT_CHANCE_BASE)) + float(META.get("crit", 0.0))))
        self.crit_mult = float(CRIT_MULT_BASE)
        self.slow_t = 0.0
        self.slow_mult = 1.0  #
        self._slow_frac = 0.0
        self.hit_cd = 0.0  # contact invulnerability timer (seconds)
        self.radius = PLAYER_RADIUS
        # progression
        self.level = 1
        self.xp = 0
        self.xp_to_next = player_xp_required(self.level)
        self.xp_to_next = player_xp_required(self.level)
        self.levelup_pending = 0  # NEW: # of level-up selections to show
        self.xp_gain_mult = 1.0
        # per-run upgrades from shop (applied on spawn)
        self.bullet_damage = int(META.get("base_dmg", BULLET_DAMAGE_ENEMY)) + int(META.get("dmg", 0))
        self.fire_rate_mult = float(META.get("firerate_mult", 1.0))
        # bullet behavior
        self.bullet_pierce = int(META.get("pierce_level", 0))
        self.bullet_ricochet = int(META.get("ricochet_level", 0))
        # on-kill shrapnel splashes
        self.shrapnel_level = int(META.get("shrapnel_level", 0))
        self.explosive_rounds_level = int(META.get("explosive_rounds_level", 0))
        self.dot_rounds_level = int(META.get("dot_rounds_level", 0))
        self.aegis_pulse_level = int(META.get("aegis_pulse_level", 0))
        if self.aegis_pulse_level > 0:
            _, _, cd = aegis_pulse_stats(self.aegis_pulse_level, self.max_hp)
            self._aegis_pulse_cd = float(cd)
        else:
            self._aegis_pulse_cd = 0.0
        # 射程：base × mult
        self.range_base = clamp_player_range(META.get("base_range", PLAYER_RANGE_DEFAULT))
        self.range = compute_player_range(self.range_base, META.get("range_mult", 1.0))
        spd0 = float(META.get("base_speed", PLAYER_SPEED))
        spd_mult = float(META.get("speed_mult", 1.0))
        spd_add = float(META.get("speed", 0))
        self.speed = min(PLAYER_SPEED_CAP, max(1.0, spd0 * spd_mult + spd_add))
        # 生命：base + 附加
        hp0 = int(META.get("base_maxhp", PLAYER_MAX_HP))
        self.max_hp = hp0 + int(META.get("maxhp", 0))
        self.hp = min(self.max_hp, self.max_hp)  # 刚生成满血
        self._hit_flash = 0.0
        self._flash_prev_hp = int(self.hp)
        # Shield state: per-level shield plus persistent Carapace reserve
        self.shield_hp = 0
        self.shield_max = 0
        self._hud_shield_vis = 0.0
        self.carapace_hp = int(META.get("carapace_shield_hp", 0))
        if self.carapace_hp > 0:
            self._hud_shield_vis = self.carapace_hp / float(max(1, self.max_hp))
        self.bone_plating_level = int(META.get("bone_plating_level", 0))
        self.bone_plating_hp = 0
        self._bone_plating_cd = float(BONE_PLATING_GAIN_INTERVAL)
        self._bone_plating_glow = 0.0
        self.acid_dot_timer = 0.0  # 还剩多少秒的DoT
        self.acid_dot_dps = 0.0  # 当前DoT每秒伤害（根据最近踩到的酸池设置）
        self._acid_dmg_accum = 0.0  # 在池中时的“本帧累计伤害”浮点缓存
        self._acid_dot_accum = 0.0  # 离开池后DoT的累计伤害缓存
        self.dot_ticks = []  # list[(dps, t_left)]
        self.apply_slow_extra = 0.0  # extra slow gathered each frame (hazards add to this)
        # Active skills
        self.blast_cd = 0.0
        self.teleport_cd = 0.0
        self.targeting_skill = None  # "blast" | "teleport" | None
        self.skill_target_pos = (self.rect.centerx, self.rect.centery)
        self.skill_target_valid = False
        self.skill_target_origin = None  # anchor for range clamp (blast stays stable vs forces)
        self.skill_flash = {"blast": 0.0, "teleport": 0.0}

    @property
    def pos(self):
        return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)

    def apply_dot(self, dps: float, duration: float):
        """Stackable DoT: each new source adds another ticking entry."""
        self.dot_ticks.append((float(dps), float(duration)))

    def reset_bone_plating(self):
        self.bone_plating_hp = 0
        self._bone_plating_cd = float(BONE_PLATING_GAIN_INTERVAL)
        self._bone_plating_glow = 0.0

    def on_level_start(self):
        self.reset_bone_plating()

    def update_bone_plating(self, dt: float):
        lvl = int(getattr(self, "bone_plating_level", 0))
        glow = float(getattr(self, "_bone_plating_glow", 0.0))
        if lvl <= 0:
            self._bone_plating_glow = max(0.0, glow - dt * 0.6)
            return
        cd = float(getattr(self, "_bone_plating_cd", BONE_PLATING_GAIN_INTERVAL))
        cd -= dt
        gained = False
        while cd <= 0.0:
            cd += BONE_PLATING_GAIN_INTERVAL
            self.bone_plating_hp = int(self.bone_plating_hp) + max(1, lvl) * BONE_PLATING_STACK_HP
            gained = True
        self._bone_plating_cd = cd
        if gained:
            glow = 0.85
        else:
            glow = max(0.0, glow - dt * 0.6)
        self._bone_plating_glow = glow

    def take_damage(self, amount: int):
        """Used by enemy projectiles / hazards that call player.take_damage."""
        if self.hit_cd <= 0.0:
            before = int(self.hp)
            self.hp = max(0, self.hp - int(amount))
            if self.hp < before:
                self._hit_flash = float(HIT_FLASH_DURATION)
                self._flash_prev_hp = int(self.hp)
            self.hit_cd = float(PLAYER_HIT_COOLDOWN)

    def move(self, keys, obstacles, dt):
        # reset frame-accumulated slow from hazards
        self.apply_slow_extra = 0.0
        lingering_slow = float(getattr(self, "_slow_frac", 0.0))
        if lingering_slow > 0.0:
            self.apply_slow_extra = max(self.apply_slow_extra, lingering_slow)
        # tick active DoTs (stackable)
        if self.dot_ticks:
            total = 0.0
            for i in range(len(self.dot_ticks) - 1, -1, -1):
                dps, t = self.dot_ticks[i]
                dtick = min(dt, t)
                total += dps * dtick
                t -= dt
                if t <= 0:
                    self.dot_ticks.pop(i)
                else:
                    self.dot_ticks[i] = (dps, t)
            if total > 0:
                # integers feel better in this game; keep float if you prefer
                self.hp = max(0, self.hp - int(total))
        # --- ISO 控制映射---
        mx = my = 0
        if binding_pressed(keys, "move_up"):
            mx -= 1;
            my -= 1  # 屏幕↑
        if binding_pressed(keys, "move_down"):
            mx += 1;
            my += 1  # 屏幕↓
        if binding_pressed(keys, "move_left"):
            mx -= 1;
            my += 1  # 屏幕←
        if binding_pressed(keys, "move_right"):
            mx += 1;
            my -= 1  # 屏幕→
        if mx != 0 or my != 0:
            # 归一化保证对角速度一致
            length = (mx * mx + my * my) ** 0.5
            dx = (mx / length)
            dy = (my / length)
        else:
            dx = dy = 0.0
        frame_scale = dt * 60.0  # keep speed tuned for a 60 FPS baseline
        # 基础速度
        spd = int(self.speed)
        # 处于减速状态 → 应用减速（例如 35% 减速 = 速度*0.65）
        # hazards (acid) add extra slow this frame
        if getattr(self, "apply_slow_extra", 0.0) > 0.0:
            spd = max(1, int(spd * (1.0 - min(0.85, float(self.apply_slow_extra)))))
        # 把“减速后的速度”喂给步进与碰撞
        prev_cx, prev_cy = self.rect.centerx, self.rect.centery
        step_x, step_y = iso_equalized_step(dx, dy, spd * frame_scale)
        collide_and_slide_circle(self, obstacles.values(), step_x, step_y)
        self._last_move_vec = (self.rect.centerx - prev_cx, self.rect.centery - prev_cy)

    def fire_cooldown(self) -> float:
        eff = min(MAX_FIRERATE_MULT, float(self.fire_rate_mult))
        return max(MIN_FIRE_COOLDOWN, FIRE_COOLDOWN / max(1.0, eff))

    def add_xp(self, amount: int):
        gain = max(0, amount)
        gain = int(round(gain * max(0.0, float(getattr(self, "xp_gain_mult", 1.0)))))
        self.xp += gain
        leveled = 0
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.level += 1
            self.hp = min(self.max_hp, self.hp + 3)
            self.xp_to_next = player_xp_required(self.level)
            leveled += 1
        # queue that many picker opens (consumed in the main loop)
        self.levelup_pending = getattr(self, "levelup_pending", 0) + leveled

    def draw(self, screen):
        pygame.draw.rect(screen, (0, 255, 0), self.rect)


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


class AfterImageGhost:
    def __init__(self, x, y, w, h, base_color, ttl=AFTERIMAGE_TTL):
        self.x = int(x);
        self.y = int(y)  # 脚底世界像素
        self.w = int(w);
        self.h = int(h)
        r, g, b = base_color if base_color else (120, 220, 160)
        MIX = 0.42  # 0..1, how much to pull toward white
        r = int(r + (255 - r) * MIX)
        g = int(g + (255 - g) * MIX)
        b = int(b + (255 - b) * MIX)
        self.color = (r, g, b)
        self.ttl = float(ttl);
        self.life0 = float(ttl)

    def update(self, dt):
        self.ttl -= dt
        return self.ttl > 0

    # —— Top-down：屏幕=世界−相机，按 midbottom 对齐 ——
    def draw_topdown(self, screen, cam_x, cam_y):
        if self.ttl <= 0: return
        alpha = max(0, min(255, int(255 * (self.ttl / self.life0))))
        rect = pygame.Rect(0, 0, self.w, self.h)
        rect.midbottom = (int(self.x - cam_x), int(self.y - cam_y))
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        s.fill((*self.color, alpha))
        screen.blit(s, rect.topleft)

    # —— ISO：脚底世界像素 → 世界格 → 等距投影坐标（再设 midbottom）——
    def draw_iso(self, screen, camx, camy):
        if self.ttl <= 0: return
        alpha = max(0, min(255, int(255 * (self.ttl / self.life0))))
        wx = self.x / CELL_SIZE
        wy = (self.y - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
        rect = pygame.Rect(0, 0, self.w, self.h)
        rect.midbottom = (int(sx), int(sy))
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        s.fill((*self.color, alpha))
        screen.blit(s, rect.topleft)

    # 兜底（仍有旧调用时，尽量别用它）
    def draw(self, screen):
        pass


class Enemy:
    def __init__(self, pos: Tuple[int, int], attack: int = ENEMY_ATTACK, speed: int = ENEMY_SPEED,
                 ztype: str = "basic", hp: Optional[int] = None):
        self.x = pos[0] * CELL_SIZE
        self.y = pos[1] * CELL_SIZE
        self._vx = 0.0
        self._vy = 0.0
        self.attack = attack
        self.speed = speed
        self.type = ztype
        self.color = ENEMY_COLORS.get(self.type, (255, 60, 60))
        # === special type state ===
        # Suicide types start unarmed; fuse begins when near the player
        self.fuse = None
        self.suicide_armed = False
        self.buff_cd = 0.0 if ztype == "buffer" else None
        self.shield_cd = 0.0 if ztype == "shielder" else None
        self.shield_hp = 0  # 当前护盾值
        self.shield_t = 0.0  # 护盾剩余时间
        self.ranged_cd = 0.0 if ztype in ("ranged", "spitter") else None
        self.buff_t = 0.0  # 自身被增益剩余时间
        self.buff_atk_mult = 1.0
        self.buff_spd_add = 0
        # XP & rank
        self.z_level = 1
        self.xp = 0
        self.xp_to_next = ENEMY_XP_TO_LEVEL
        self.is_elite = False
        self.is_boss = False
        self.radius = ENEMY_RADIUS
        # ABS
        self._stuck_t = 0.0  # 被卡住累计时长
        self._avoid_t = 0.0  # 侧移剩余时间
        self._avoid_side = 1  # 侧移方向（1 或 -1）
        self._focus_block = None  # 当前决定优先破坏的可破坏物
        self._last_xy = (self.x, self.y)
        # —— 路径跟随（懒 A*）所需的轻量状态 ——
        self._path = []  # 路径里的网格路点列表（不含起点）
        self._path_step = 0  # 当前要走向的路点索引
        # Spoil
        self.spoils = 0  # 当前持有金币
        self._gold_glow_t = 0.0  # 金色拾取光晕计时器
        # D.O.T. Rounds stacks (per-enemy)
        self.dot_rounds_stacks = []
        self._dot_rounds_tick_t = float(DOT_ROUNDS_TICK_INTERVAL)
        self._dot_rounds_accum = 0.0
        self.speed = float(self.speed)  # 改成 float，支持 +0.5 的增速
        # split flags (only for splinter)
        self._can_split = (self.type == "splinter")
        self._split_done = False
        base_hp = 30 if hp is None else hp
        # type tweaks
        if ztype == "fast":
            self.speed = max(int(self.speed + 1), int(self.speed * 1.5))
            base_hp = int(base_hp * 0.7)
        if ztype == "tank":
            self.attack = int(self.attack * 0.6)
            base_hp = int(base_hp * 1.8)
        self.hp = max(1, base_hp)
        self.max_hp = self.hp
        self._hit_flash = 0.0
        self._flash_prev_hp = int(self.hp)
        self.size = int(CELL_SIZE * 0.6)
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)
        # track trailing foot points for afterimage
        self._foot_prev = (self.rect.centerx, self.rect.bottom)
        self._foot_curr = (self.rect.centerx, self.rect.bottom)
        self.spawn_delay = 0.6
        self._enrage_cd_mult = 1.0

    def draw(self, screen):
        color = getattr(self, "_current_color", self.color)
        pygame.draw.rect(screen, color, self.rect)
        self._spawn_elapsed = 0.0

    @property
    def pos(self):
        return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)

    def gain_xp(self, amount: int):
        self.xp += int(max(0, amount))
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.z_level += 1
            self.xp_to_next = int(self.xp_to_next * 1.25 + 0.5)
            # stat bumps
            self.attack = int(self.attack * 1.08 + 1)
            self.max_hp = int(self.max_hp * 1.10 + 1)
            self.hp = min(self.max_hp, self.hp + 2)
        if not getattr(self, "is_boss", False):
            # Keep regular enemies at player size to avoid path-sticking; Ravager keeps its larger override.
            if getattr(self, "type", "") == "ravager":
                base = getattr(self, "_size_override", int(CELL_SIZE * RAVAGER_SIZE_MULT))
            else:
                base = int(CELL_SIZE * 0.6)  # match player footprint
            new_size = base
            if new_size != self.size:
                cx, cy = self.rect.center
                self.size = new_size
                self.rect = pygame.Rect(0, 0, self.size, self.size)
                self.rect.center = (cx, cy)
                self.x = float(self.rect.x)
                self.y = float(self.rect.y - INFO_BAR_HEIGHT)
                # 用最终矩形重置残影足点，保证轨迹贴合
                self._foot_prev = (self.rect.centerx, self.rect.bottom)
                self._foot_curr = (self.rect.centerx, self.rect.bottom)

    def add_spoils(self, n: int):
        """僵尸拾取金币后的即时强化。"""
        n = int(max(0, n))
        if n <= 0:
            return
        # 逐枚处理，确保跨阈值时触发攻击/速度加成
        for _ in range(n):
            self.spoils += 1
            # +HP 与 +MaxHP
            self.max_hp += Z_SPOIL_HP_PER
            self.hp = min(self.max_hp, self.hp + Z_SPOIL_HP_PER)
            # 攻击阈值
            if self.spoils % Z_SPOIL_ATK_STEP == 0:
                self.attack += 1
            # 速度阈值
            if self.spoils % Z_SPOIL_SPD_STEP == 0:
                self.speed = min(Z_SPOIL_SPD_CAP, float(self.speed) + float(Z_SPOIL_SPD_ADD))
        # 触发拾取光晕
        self._gold_glow_t = float(Z_GLOW_TIME)

    # ==== 通用：把朝向向量分解到等距基向量（e1=(1,1), e2=(1,-1)）====
    @staticmethod
    def iso_chase_step(from_xy, to_xy, speed):
        fx, fy = from_xy
        tx, ty = to_xy
        vx, vy = tx - fx, ty - fy
        L = (vx * vx + vy * vy) ** 0.5 or 1.0
        ux, uy = vx / L, vy / L
        # use the same equalized speed you use for the player
        return iso_equalized_step(ux, uy, speed)

    @staticmethod
    def feet_xy(entity):
        # “脚底”坐标：用底边中心点（避免因为sprite高度导致距离判断穿帮）
        return (entity.x + entity.size * 0.5, entity.y + entity.size)

    @staticmethod
    def first_obstacle_on_grid_line(a_cell, b_cell, obstacles_dict):
        x0, y0 = a_cell;
        x1, y1 = b_cell
        dx = abs(x1 - x0);
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0);
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            ob = obstacles_dict.get((x0, y0))
            if ob: return ob
            if x0 == x1 and y0 == y1: break
            e2 = 2 * err
            if e2 >= dy: err += dy; x0 += sx
            if e2 <= dx: err += dx; y0 += sy
        return None

    def _choose_bypass_cell(self, ob_cell, player_cell, obstacles_dict):
        """Pick a simple side cell next to the blocking obstacle to go around it."""
        ox, oy = ob_cell
        px, py = player_cell
        # Prefer going around the obstacle on the side perpendicular
        # to the main player-obstacle axis (very simple wall-hug).
        if abs(px - ox) >= abs(py - oy):
            primary = [(ox, oy - 1), (ox, oy + 1)]
        else:
            primary = [(ox - 1, oy), (ox + 1, oy)]

        def free(c):
            x, y = c
            return (0 <= x < GRID_SIZE) and (0 <= y < GRID_SIZE) and (c not in obstacles_dict)

        cands = [c for c in primary if free(c)]
        if not cands:
            # Fallback: try the four diagonals
            diag = [(ox + 1, oy + 1), (ox + 1, oy - 1), (ox - 1, oy + 1), (ox - 1, oy - 1)]

            def diag_valid(c):
                cx, cy = c
                # NEW: reject diagonal if both side-adjacents are blocked (corner)
                side1 = (ox, cy) in obstacles_dict
                side2 = (cx, oy) in obstacles_dict
                return free(c) and not (side1 and side2)

            cands = [c for c in diag if free(c)]
        if not cands:
            return None
        # Choose the one closer to the player.
        return min(cands, key=lambda c: (c[0] - px) ** 2 + (c[1] - py) ** 2)

    def move_and_attack(self, player, obstacles, game_state, attack_interval=0.5, dt=1 / 60):
        # shift last → prev at frame start
        self._foot_prev = getattr(self, "_foot_curr", (self.rect.centerx, self.rect.bottom))
        frame_scale = dt * 60.0  # convert 60 FPS-tuned speeds into this frame's step
        # ---- BUFF/生成延迟/速度上限：与原逻辑一致 ----
        base_attack = self.attack
        # Hell Domain: generic attack scaler for melee/block hits/skill uses
        if getattr(game_state, "biome_active", None) == "Scorched Hell":
            base_attack = int(base_attack * (1.5 if getattr(self, "is_boss", False) else 2.0))
        base_speed = float(self.speed)
        if getattr(self, "buff_t", 0.0) > 0.0:
            base_attack = int(base_attack * getattr(self, "buff_atk_mult", 1.0))
            base_speed = float(base_speed) + float(getattr(self, "buff_spd_add", 0))
            self.buff_t = max(0.0, self.buff_t - dt)
        base_speed *= float(getattr(self, "_hurricane_slow_mult", 1.0))
        speed = float(min(Z_SPOIL_SPD_CAP, max(0.5, base_speed)))
        is_bandit = (getattr(self, "type", "") == "bandit")
        bandit_break_t = 0.0
        bandit_wind_trapped = False
        if is_bandit:
            bandit_break_t = max(0.0, float(getattr(self, "bandit_break_t", 0.0)) - dt)
            self.bandit_break_t = bandit_break_t
            bandit_wind_trapped = bool(getattr(self, "_wind_trapped", False))
        bandit_prev_pos = getattr(self, "_bandit_last_pos", (self.x, self.y))
        if not hasattr(self, "attack_timer"): self.attack_timer = 0.0
        self.attack_timer += dt
        # Cooldown between applying contact damage to blocking destructible tiles
        self._block_contact_cd = max(0.0, float(getattr(self, "_block_contact_cd", 0.0)) - dt)
        # simple bypass lifetime
        self._bypass_t = max(0.0, getattr(self, "_bypass_t", 0.0) - dt)
        # wipe last-hit each frame (esp. when we skip collide due to no_clip)
        self._hit_ob = None
        # if our previous focus block was destroyed last frame, drop it
        if getattr(self, "_focus_block", None):
            gp = getattr(self._focus_block, "grid_pos", None)
            if (gp is not None) and (gp not in game_state.obstacles):
                self._focus_block = None
        if is_bandit:
            self.mode = getattr(self, "mode", "FLEE")
            self.last_collision_tile = getattr(self, "last_collision_tile", None)
            self.frames_on_same_tile = int(getattr(self, "frames_on_same_tile", 0))
            self.stuck_origin_pos = tuple(getattr(self, "stuck_origin_pos", (self.x, self.y)))
            esc_dir = getattr(self, "escape_dir", (0.0, 0.0))
            if not (isinstance(esc_dir, (tuple, list)) and len(esc_dir) == 2):
                esc_dir = (0.0, 0.0)
            self.escape_dir = esc_dir
            self.escape_timer = float(getattr(self, "escape_timer", 0.0))
        if is_bandit and getattr(self, "bandit_triggered", False):
            # While fleeing, never stick to a focus target or bypass side cell
            self._focus_block = None
            self._bypass_t = 0.0
            self._bypass_cell = None
        # 目标（默认追玩家；若锁定了一块挡路的可破坏物，则追它的中心）
        zx, zy = Enemy.feet_xy(self)
        px, py = player.rect.centerx, player.rect.centery
        player_move_dx, player_move_dy = getattr(player, "_last_move_vec", (0.0, 0.0))
        target_cx, target_cy = px, py
        # Distance to player (used by bandit flee logic)
        dxp = px - zx
        dyp = py - zy
        dist2_to_player = dxp * dxp + dyp * dyp
        # one-time trigger – once bandit enters flee radius, it stays in flee mode
        if is_bandit and dist2_to_player <= (BANDIT_FLEE_RADIUS * BANDIT_FLEE_RADIUS):
            # only set once
            if not getattr(self, "bandit_triggered", False):
                self.bandit_triggered = True
        bandit_flee = is_bandit and getattr(self, "bandit_triggered", False)
        if bandit_flee:
            speed *= BANDIT_FLEE_SPEED_MULT
            if bandit_break_t > 0.0:
                speed *= BANDIT_BREAK_SLOW_MULT
            # steer toward the farthest corner away from the player
            pcx = int(player.rect.centerx // CELL_SIZE)
            pcy = int((player.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE)
            corners = [(0, 0), (0, GRID_SIZE - 1), (GRID_SIZE - 1, 0), (GRID_SIZE - 1, GRID_SIZE - 1)]
            tx, ty = max(corners, key=lambda c: (c[0] - pcx) ** 2 + (c[1] - pcy) ** 2)
            target_cx = tx * CELL_SIZE + CELL_SIZE * 0.5
            target_cy = ty * CELL_SIZE + CELL_SIZE * 0.5 + INFO_BAR_HEIGHT
            # drop any previous chase commitment when fleeing
            self._ff_commit = None
            self._ff_commit_t = 0.0
        speed_step = speed * frame_scale
        # --- Twin “lane” offset and mild separation so they don’t block each other ---
        if getattr(self, "is_boss", False) and getattr(self, "twin_id", None) is not None:
            cx0 = self.x + self.size * 0.5
            cy0 = self.y + self.size * 0.5 + INFO_BAR_HEIGHT
            # direction to player/focus target
            dxp, dyp = target_cx - cx0, target_cy - cy0
            mag = (dxp * dxp + dyp * dyp) ** 0.5 or 1.0
            nx, ny = dxp / mag, dyp / mag
            # pick a lane: perpendicular offset (left/right by slot)
            px, py = -ny, nx
            slot = float(getattr(self, "twin_slot", +1))
            lane_offset = 0.45 * CELL_SIZE * slot
            target_cx += px * lane_offset
            target_cy += py * lane_offset
            # soft separation from partner if we’re too close
            partner = None
            ref = getattr(self, "_twin_partner_ref", None)
            if callable(ref):
                partner = ref()
            if partner and getattr(partner, "hp", 1) > 0:
                pcx, pcy = partner.rect.centerx, partner.rect.centery
                ddx, ddy = cx0 - pcx, cy0 - pcy
                d2 = ddx * ddx + ddy * ddy
                too_close = (1.2 * CELL_SIZE) ** 2
                if d2 < too_close:
                    k = (too_close - d2) / too_close
                    target_cx += ddx * 0.35 * k
                    target_cy += ddy * 0.35 * k
        # 若之前撞到了可破坏物，则临时聚焦（更积极地砍）
        if getattr(self, "_hit_ob", None):
            if getattr(self, "can_crush_all_blocks", False) or getattr(self._hit_ob, "type", "") == "Destructible":
                self._focus_block = self._hit_ob
        # 视线被障碍挡住：
        # - 若是红色(Destructible) → 把它当“门”，优先破坏
        # - 否则：普通僵尸(basic) 尝试一个极简的“旁路”目标格
        if not self._focus_block:
            gz = (int((self.x + self.size * 0.5) // CELL_SIZE),
                  int((self.y + self.size * 0.5) // CELL_SIZE))
            if bandit_flee:
                gp = (int(target_cx // CELL_SIZE),
                      int((target_cy - INFO_BAR_HEIGHT) // CELL_SIZE))
            else:
                gp = (int(player.rect.centerx // CELL_SIZE),
                      int((player.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE))  # <- use rect center
            ob = self.first_obstacle_on_grid_line(gz, gp, game_state.obstacles)
            self._focus_block = None
            if ob:
                if bandit_flee:
                    # pick a neighboring free cell of the blocking obstacle that increases distance to player
                    ox, oy = ob.grid_pos
                    free = []
                    for nx, ny in ((ox + 1, oy), (ox - 1, oy), (ox, oy + 1), (ox, oy - 1)):
                        if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE and (nx, ny) not in game_state.obstacles:
                            free.append((nx, ny))
                    if free:
                        bx, by = max(free, key=lambda c: (c[0] - pcx) ** 2 + (c[1] - pcy) ** 2)
                        self._bypass_cell = (bx, by)
                        self._bypass_t = 0.60
                elif getattr(ob, "type", "") == "Destructible":
                    # red block: break it
                    self._focus_block = ob
                elif not getattr(self, "is_boss", False):
                    # grey block: pick a side cell and follow it for a short time
                    bypass = self._choose_bypass_cell(ob.grid_pos, gp, game_state.obstacles)
                    if bypass:
                        self._bypass_cell = bypass
                        self._bypass_t = 0.50  # ~0.5s of commitment to the side cell
        if self._focus_block and not bandit_flee:
            target_cx, target_cy = self._focus_block.rect.centerx, self._focus_block.rect.centery
        fd = None  # flow-distance field; stays None if we skip FF steering (e.g., during escape override)
        escape_override = False
        if bandit_flee and getattr(self, "mode", "FLEE") == "ESCAPE_CORNER":
            ex, ey = self.escape_dir
            mag = (ex * ex + ey * ey) ** 0.5
            if mag < 1e-4:
                ex, ey = -dxp, -dyp
                mag = (ex * ex + ey * ey) ** 0.5 or 1.0
            ux, uy = ex / mag, ey / mag
            vx_des, vy_des = chase_step(ux, uy, speed_step)
            tau = 0.12
            alpha = 1.0 - pow(0.001, dt / tau)
            self._vx = (1.0 - alpha) * getattr(self, "_vx", 0.0) + alpha * vx_des
            self._vy = (1.0 - alpha) * getattr(self, "_vy", 0.0) + alpha * vy_des
            vx, vy = self._vx, self._vy
            dx, dy = vx, vy
            oldx, oldy = self.x, self.y
            escape_override = True
            self.escape_timer = max(0.0, float(getattr(self, "escape_timer", 0.0)) - dt)
            if self.escape_timer <= 0.0:
                self.mode = "FLEE"
                self.last_collision_tile = None
                self.frames_on_same_tile = 0
        if not escape_override:
            # —— 若已有“临时路径”，把目标切换到下一个路点（脚底中心） ——
            # 当前“脚底”所在格
            gx = int((self.x + self.size * 0.5) // CELL_SIZE)
            gy = int((self.y + self.size) // CELL_SIZE)
            if self._path_step < len(self._path):
                nx, ny = self._path[self._path_step]
                # 到达该格就推进
                if gx == nx and gy == ny:
                    self._path_step += 1
                    if self._path_step < len(self._path):
                        nx, ny = self._path[self._path_step]
                # 仍有路点：将追踪目标改成这个路点的“脚底”
                if self._path_step < len(self._path):
                    target_cx = nx * CELL_SIZE + CELL_SIZE * 0.5
                    target_cy = ny * CELL_SIZE + CELL_SIZE
            # === 4) FLOW-FIELD STEER (preferred) ===
            cx0, cy0 = self.rect.centerx, self.rect.centery
            gx = int(cx0 // CELL_SIZE)
            gy = int((cy0 - INFO_BAR_HEIGHT) // CELL_SIZE)
            ff = getattr(game_state, "ff_next", None)
            fd = getattr(game_state, "ff_dist", None)
            # 1) primary: read next step from the 2-D flow field
            step = ff[gx][gy] if (ff is not None and 0 <= gx < GRID_SIZE and 0 <= gy < GRID_SIZE) else None
            boss_simple = (getattr(self, "is_boss", False)
                           or getattr(self, "type", "") in ("boss_mist", "boss_mem"))
            if boss_simple:
                step = None  # stay on simple-chase
                self._ff_commit = None  # <-- critical: use None, not 0.0
                self._ff_commit_t = 0.0
                self._avoid_t = 0.0
            # If this is a bandit that has triggered flee mode, invert FF preference to run away
            bandit_escape_step = None
            if bandit_flee and fd is not None:
                best = None
                bestd = -1
                for nx in (gx - 1, gx, gx + 1):
                    for ny in (gy - 1, gy + 1):
                        if nx == gx and ny == gy:
                            continue
                        if not (0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE):
                            continue
                        if (nx, ny) in game_state.obstacles:
                            continue
                        if nx != gx and ny != gy:
                            if (gx, ny) in game_state.obstacles or (nx, gy) in game_state.obstacles:
                                continue
                        d = fd[ny][nx]
                        if d > bestd and not Enemy.first_obstacle_on_grid_line((gx, gy), (nx, ny), game_state.obstacles):
                            bestd = d
                            best = (nx, ny)
                bandit_escape_step = best
                if bandit_escape_step is not None:
                    step = bandit_escape_step
            # 2) fallback: pick the neighbor with the smallest distance (row-major: fd[ny][nx])
            if step is None and fd is not None and not boss_simple:
                best = None
                bestd = 10 ** 9
                for nx in (gx - 1, gx, gx + 1):
                    for ny in (gy - 1, gy + 1):
                        if nx == gx and ny == gy:
                            continue
                        if not (0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE):
                            continue
                        # 1) skip blocked target cells
                        if (nx, ny) in game_state.obstacles:
                            continue
                        # 2) forbid cutting corners on diagonals
                        if nx != gx and ny != gy:
                            if (gx, ny) in game_state.obstacles or (nx, gy) in game_state.obstacles:
                                continue
                        d = fd[ny][nx]
                        if d < bestd:
                            if nx != gx and ny != gy:
                                if ((gx, ny) in game_state.obstacles) and ((nx, gy) in game_state.obstacles):
                                    continue
                                # existing “no-hidden-corner” / LoS check
                            if not Enemy.first_obstacle_on_grid_line((gx, gy), (nx, ny), game_state.obstacles):
                                bestd = d
                                best = (nx, ny)
                step = best
                # --- smooth FF steering: commit briefly to avoid oscillation (applies to all) ---
                if step is not None:
                    prev = getattr(self, "_ff_commit", None)
                    # Make sure prev is a (x,y) cell, otherwise treat as no commit
                    if not (isinstance(prev, (tuple, list)) and len(prev) == 2):
                        prev = None
                    if prev is None:
                        self._ff_commit = step
                        self._ff_commit_t = 0.25
                    else:
                        if step != prev:
                            pcx = prev[0] * CELL_SIZE + CELL_SIZE * 0.5
                            pcy = prev[1] * CELL_SIZE + CELL_SIZE * 0.5 + INFO_BAR_HEIGHT
                            d2 = (pcx - cx0) ** 2 + (pcy - cy0) ** 2
                            if d2 <= (CELL_SIZE * 0.35) ** 2 or getattr(self, "_ff_commit_t", 0.0) <= 0.0:
                                self._ff_commit = step
                                self._ff_commit_t = 0.25
                            else:
                                step = prev
                        else:
                            self._ff_commit_t = max(0.0, getattr(self, "_ff_commit_t", 0.0) - dt)
                # else:
                #     # bosses take simple-chase path (ignore FF)
                #     step = step if not is_boss_simple else None
            # Simple-bypass override for regular enemies
            if getattr(self, "_bypass_t", 0.0) > 0.0 and getattr(self, "_bypass_cell", None) is not None:
                # drop it if we already reached the side cell or LoS is now clear
                if (gx, gy) == self._bypass_cell or not self.first_obstacle_on_grid_line((gx, gy), gp,
                                                                                         game_state.obstacles):
                    self._bypass_t = 0.0
                    self._bypass_cell = None
                else:
                    step = self._bypass_cell
            if step is not None:
                nx, ny = step
                # world-pixel center of the recommended next cell
                next_cx = nx * CELL_SIZE + CELL_SIZE * 0.5
                next_cy = ny * CELL_SIZE + CELL_SIZE * 0.5 + INFO_BAR_HEIGHT
                dx = next_cx - cx0
                dy = next_cy - cy0
                L = (dx * dx + dy * dy) ** 0.5 or 1.0
                ux, uy = dx / L, dy / L
                # desired velocity this frame
                vx_des, vy_des = chase_step(ux, uy, speed_step)
                # light steering smoothing (≈ 120 ms time constant)
                tau = 0.12
                alpha = 1.0 - pow(0.001, dt / tau)  # stable, dt-based lerp factor
                self._vx = (1.0 - alpha) * getattr(self, "_vx", 0.0) + alpha * vx_des
                self._vy = (1.0 - alpha) * getattr(self, "_vy", 0.0) + alpha * vy_des
                # use smoothed velocity as this frame’s step
                vx, vy = self._vx, self._vy
                dx, dy = vx, vy
                oldx, oldy = self.x, self.y
            else:
                # Fallback: keep your existing target-point chase (path step / LOS)
                dx = target_cx - cx0
                dy = target_cy - cy0
                L = (dx * dx + dy * dy) ** 0.5 or 1.0
                ux, uy = dx / L, dy / L
                # Bandit logic: once flee has triggered, always run AWAY from the player
                if bandit_flee:
                    flee_x, flee_y = -dxp, -dyp  # straight away from player
                    # if still near-zero (standing on the player), pick a perpendicular shove
                    if abs(flee_x) < 1e-4 and abs(flee_y) < 1e-4:
                        flee_x, flee_y = -dy, dx
                    mag = (flee_x * flee_x + flee_y * flee_y) ** 0.5 or 1.0
                    ux, uy = flee_x / mag, flee_y / mag
                # desired velocity this frame
                vx_des, vy_des = chase_step(ux, uy, speed_step)
                # light steering smoothing (≈ 120 ms time constant)
                tau = 0.12
                alpha = 1.0 - pow(0.001, dt / tau)  # stable, dt-based lerp factor
                self._vx = (1.0 - alpha) * getattr(self, "_vx", 0.0) + alpha * vx_des
                self._vy = (1.0 - alpha) * getattr(self, "_vy", 0.0) + alpha * vy_des
                # use smoothed velocity as this frame’s step
                vx, vy = self._vx, self._vy
                dx, dy = vx, vy
                oldx, oldy = self.x, self.y
        # If target is exactly on us this frame, dodge sideways deterministically
        if not getattr(self, "is_boss", False):
            if abs(dx) < 1e-3 and abs(dy) < 1e-3:
                slot = float(getattr(self, "twin_slot", 1.0))
                dx, dy = 0.0, slot * max(0.6, min(speed, 1.2)) * frame_scale
        # —— 侧移（反卡住）：被卡住一小会儿就沿着法向 90° 滑行 ——
        if self._avoid_t > 0.0:
            # 左右各一条切线，选择预先决定的那一边
            if self._avoid_side > 0:
                ax, ay = -dy, dx  # 向左
            else:
                ax, ay = dy, -dx  # 向右
            dx, dy = ax, ay
            self._avoid_t = max(0.0, self._avoid_t - dt)
        # Bosses: no side-slip shimmy
        if (not getattr(self, "is_boss", False)) and self._avoid_t > 0.0:
            if self._avoid_side > 0:
                ax, ay = -dy, dx
            else:
                ax, ay = dy, -dx
            dx, dy = ax, ay
            self._avoid_t = max(0.0, self._avoid_t - dt)
        # --- no-clip phase: skip collision resolution for a few frames after bulldozing
        if getattr(self, "no_clip_t", 0.0) > 0.0:
            self.no_clip_t = max(0.0, self.no_clip_t - dt)
            self.x += dx
            self.y += dy
            # sync rect and bail directly into post-move logic
            self.rect.x = int(self.x)
            self.rect.y = int(self.y + INFO_BAR_HEIGHT)
            # OPTIONAL tiny forward nudge to defeat integer clamp remnants
            if abs(dx) < 0.5 and abs(dy) < 0.5:
                self.x += 0.8 * (1 if (self.rect.centerx < player.rect.centerx) else -1)
            goto_post_move = True
        else:
            goto_post_move = False
        if not goto_post_move:
            collide_and_slide_circle(self, obstacles, dx, dy)
        if bandit_flee:
            # if barely moved this frame, sidestep perpendicular to player to break jitter
            moved_x = self.x - oldx
            moved_y = self.y - oldy
            if abs(moved_x) < 0.25 and abs(moved_y) < 0.25:
                self._avoid_side = 1 if dxp >= 0 else -1
                self._avoid_t = max(self._avoid_t, 0.25)
            ob = getattr(self, "_hit_ob", None)
            if ob and getattr(ob, "type", "") == "Destructible":
                gp = getattr(ob, "grid_pos", None)
                if gp in game_state.obstacles:
                    del game_state.obstacles[gp]
                if getattr(ob, "health", None) is not None:
                    ob.health = 0
                cx2, cy2 = ob.rect.centerx, ob.rect.centery
                if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                    game_state.spawn_spoils(cx2, cy2, 1)
                self.gain_xp(XP_ENEMY_BLOCK)
                if random.random() < HEAL_DROP_CHANCE_BLOCK:
                    game_state.spawn_heal(cx2, cy2, HEAL_POTION_AMOUNT)
                self.bandit_break_t = max(float(getattr(self, "bandit_break_t", 0.0)), BANDIT_BREAK_SLOW_TIME)
                self._focus_block = None
        if is_bandit:
            moved_len = ((self.x - bandit_prev_pos[0]) ** 2 + (self.y - bandit_prev_pos[1]) ** 2) ** 0.5
            if moved_len < 1.0:
                self._bandit_stuck_t = float(getattr(self, "_bandit_stuck_t", 0.0)) + dt
            else:
                self._bandit_stuck_t = 0.0
            self._bandit_last_pos = (self.x, self.y)
            # Watchdog: if the bandit barely changes position over time, force a sidestep to break jitter.
            idle_pos = getattr(self, "_bandit_idle_pos", (self.x, self.y))
            idle_t = float(getattr(self, "_bandit_idle_t", 0.0)) + dt
            idle_d = ((self.x - idle_pos[0]) ** 2 + (self.y - idle_pos[1]) ** 2) ** 0.5
            if idle_d >= 30.0:
                self._bandit_idle_pos = (self.x, self.y)
                self._bandit_idle_t = 0.0
            else:
                self._bandit_idle_t = idle_t
                if idle_t >= 2.0:
                    self._avoid_side = random.choice((-1, 1))
                    self._avoid_t = max(self._avoid_t, 0.45)
                    self._ff_commit = None
                    self._ff_commit_t = 0.0
                    self._bypass_t = 0.0
                    self._bandit_idle_pos = (self.x, self.y)
                    self._bandit_idle_t = 0.0
            if bandit_flee and getattr(self, "_bandit_stuck_t", 0.0) > 0.6 and fd is not None:
                best = None
                bestd = -1
                for ny, row in enumerate(fd):
                    for nx, d in enumerate(row):
                        if (nx, ny) in game_state.obstacles:
                            continue
                        if d > bestd:
                            bestd = d
                            best = (nx, ny)
                if best:
                    self._bypass_cell = best
                    self._bypass_t = 1.2
                    self._ff_commit = None
                    self._ff_commit_t = 0.0
                    self._bandit_stuck_t = 0.0
        # Bulldozer cleanup: crush anything we hit during sweep-collision
        if getattr(self, "can_crush_all_blocks", False) and getattr(self, "_crush_queue", None):
            for ob in list(self._crush_queue):
                gp = getattr(ob, "grid_pos", None)
                if gp in game_state.obstacles:
                    del game_state.obstacles[gp]  # works for all types, incl. Indestructible & MainBlock
            self._crush_queue.clear()
            self._focus_block = None  # no longer blocked
            # Ensure 2x2 footprint is fully clear (fixes “stuck after breaking grey block”)
            try:
                r = int(getattr(self, "radius", max(8, CELL_SIZE // 3)))
                cx = self.x + self.size * 0.5
                cy = self.y + self.size * 0.5 + INFO_BAR_HEIGHT
                bb = pygame.Rect(int(cx - r), int(cy - r), int(2 * r), int(2 * r))
                crushed_any = False
                for gp, ob in list(game_state.obstacles.items()):
                    # If the obstacle touches our collision circle’s bounding box, delete it.
                    if ob.rect.colliderect(bb):
                        del game_state.obstacles[gp]
                        crushed_any = True
                        # Only Destructible blocks drop spoils / heal, keep existing rules
                        if getattr(ob, "type", "") == "Destructible":
                            if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                                game_state.spawn_spoils(ob.rect.centerx, ob.rect.centery, 1)
                            self.gain_xp(XP_ENEMY_BLOCK)
                    if random.random() < HEAL_DROP_CHANCE_BLOCK:
                        game_state.spawn_heal(ob.rect.centerx, ob.rect.centery, HEAL_POTION_AMOUNT)
                if crushed_any:
                    self._focus_block = None
                    # prevent “stuck” heuristics from kicking in right after we bulldozed
                    if hasattr(self, "_stuck_t"):
                        self._stuck_t = 0.0
                    self.no_clip_t = max(getattr(self, 'no_clip_t', 0.0), 0.10)
            except Exception:
                pass
        # —— Bandit corner escape detection ——
        if bandit_flee:
            MIN_FRAMES_STUCK = 4
            STUCK_MOVE_THRESHOLD = CELL_SIZE * 0.30
            ESCAPE_DURATION = 0.55
            ESCAPE_TEST_STEP = CELL_SIZE * 0.6
            ob = getattr(self, "_hit_ob", None)
            collided_tile = None
            if ob and not getattr(ob, "nonblocking", False):
                gp = getattr(ob, "grid_pos", None)
                if gp is not None:
                    collided_tile = tuple(gp)
                else:
                    collided_tile = (int(ob.rect.centerx // CELL_SIZE),
                                     int((ob.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE))
            bandit_pos = (self.rect.centerx, self.rect.centery)
            if collided_tile is not None:
                if collided_tile != getattr(self, "last_collision_tile", None):
                    self.last_collision_tile = collided_tile
                    self.frames_on_same_tile = 1
                    self.stuck_origin_pos = (self.x, self.y)
                else:
                    self.frames_on_same_tile = int(getattr(self, "frames_on_same_tile", 0)) + 1
                disp = ((self.x - self.stuck_origin_pos[0]) ** 2 + (self.y - self.stuck_origin_pos[1]) ** 2) ** 0.5
                if self.frames_on_same_tile >= MIN_FRAMES_STUCK and disp <= STUCK_MOVE_THRESHOLD and getattr(self, "mode", "FLEE") != "ESCAPE_CORNER":
                    bx, by = bandit_pos
                    flee_dx, flee_dy = bx - px, by - py
                    mag = (flee_dx * flee_dx + flee_dy * flee_dy) ** 0.5 or 1.0
                    base_dir = (flee_dx / mag, flee_dy / mag)
                    left_dir = (-base_dir[1], base_dir[0])
                    right_dir = (base_dir[1], -base_dir[0])
                    # also consider directly away from obstacle center (bounce)
                    ox, oy = collided_tile
                    ob_cx = ox * CELL_SIZE + CELL_SIZE * 0.5
                    ob_cy = oy * CELL_SIZE + CELL_SIZE * 0.5 + INFO_BAR_HEIGHT
                    away_dx, away_dy = bx - ob_cx, by - ob_cy
                    away_mag = (away_dx * away_dx + away_dy * away_dy) ** 0.5 or 1.0
                    bounce_dir = (away_dx / away_mag, away_dy / away_mag)
                    candidates = [base_dir, left_dir, right_dir, bounce_dir]

                    def _dir_clear(vec):
                        tx = bx + vec[0] * ESCAPE_TEST_STEP
                        ty = by + vec[1] * ESCAPE_TEST_STEP
                        cell = (int(tx // CELL_SIZE), int((ty - INFO_BAR_HEIGHT) // CELL_SIZE))
                        if not (0 <= cell[0] < GRID_SIZE and 0 <= cell[1] < GRID_SIZE):
                            return False
                        return cell not in game_state.obstacles

                    best_dir = None
                    best_d2 = -1
                    for vec in candidates:
                        if not _dir_clear(vec):
                            continue
                        tx = bx + vec[0] * ESCAPE_TEST_STEP
                        ty = by + vec[1] * ESCAPE_TEST_STEP
                        d2p = (tx - px) ** 2 + (ty - py) ** 2
                        if d2p > best_d2:
                            best_d2 = d2p
                            best_dir = vec
                    if best_dir is None:
                        # fallback: pick any perpendicular dir that isn't blocked
                        if _dir_clear(left_dir):
                            best_dir = left_dir
                        elif _dir_clear(right_dir):
                            best_dir = right_dir
                        else:
                            best_dir = bounce_dir
                    self.escape_dir = best_dir
                    self.escape_timer = ESCAPE_DURATION
                    self.mode = "ESCAPE_CORNER"
            else:
                self.last_collision_tile = None
                self.frames_on_same_tile = 0
        # —— 卡住检测（只有“被挡住”或“无进展”才累计）——
        blocked = (self._hit_ob is not None)
        moved2 = (self.x - oldx) ** 2 + (self.y - oldy) ** 2
        min_move = 0.15 * speed_step
        min_move2 = max(0.04 * frame_scale * frame_scale, min_move * min_move)  # speed-scaled
        # 目标距离是否在本帧没有明显下降（允许轻微抖动）
        dist2 = (self.rect.centerx - int(target_cx)) ** 2 + (self.rect.centery - int(target_cy)) ** 2
        prev_d2 = getattr(self, "_prev_d2", float("inf"))
        no_progress = (dist2 > prev_d2 - 1.0)
        self._prev_d2 = dist2
        if (blocked and moved2 < min_move2) or (no_progress and moved2 < min_move2):
            self._stuck_t = getattr(self, "_stuck_t", 0.0) + dt
        else:
            self._stuck_t = 0.0
        # progress to current target (player or focus block) this frame
        dist2 = (self.rect.centerx - int(target_cx)) ** 2 + (self.rect.centery - int(target_cy)) ** 2
        prev_d2 = getattr(self, "_prev_d2", float("inf"))
        no_progress = (dist2 > prev_d2 - 1.0)  # allow tiny jitter
        self._prev_d2 = dist2
        if (blocked and moved2 < min_move2) or (no_progress and moved2 < min_move2):
            self._stuck_t = getattr(self, "_stuck_t", 0.0) + dt
        else:
            self._stuck_t = 0.0
        # 卡住 0.25s 以上：触发一次侧移（仅在“被挡住”或无进展时）
        if self._stuck_t > 0.25 and self._avoid_t <= 0.0 and (blocked or no_progress):
            self._avoid_t = random.uniform(0.25, 0.45)
            self._avoid_side = random.choice((-1, 1))
        # —— 懒 A* 兜底：长时间卡住再寻一次短路径 ——
        if self._stuck_t > 0.7 and self._avoid_t <= 0.0 and self._path_step >= len(self._path):
            # 起点：当前脚底；终点：玩家或“被锁定的可破坏物”脚底网格
            start = (gx, gy)
            if self._focus_block:
                gp = getattr(self._focus_block, "grid_pos", None)
                if gp is None:
                    cx2, cy2 = self._focus_block.rect.centerx, self._focus_block.rect.centery
                    goal = (int(cx2 // CELL_SIZE), int((cy2 - INFO_BAR_HEIGHT) // CELL_SIZE))
                else:
                    goal = gp
            else:
                goal = (int(player.rect.centerx // CELL_SIZE),
                        int((player.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE))
            # 构图 + A*
            graph = build_graph(GRID_SIZE, game_state.obstacles)
            came, _ = a_star_search(graph, start, goal, game_state.obstacles)
            path = reconstruct_path(came, start, goal)
            # 生成“短路径”：去掉起点，只取前 6 个路点
            if len(path) > 1:
                self._path = path[1:7]
                self._path_step = 0
            # 避免立刻再次触发
            self._stuck_t = 0.0
        # 焦点块被打掉/消失 → 解除聚焦
        if self._focus_block and (self._focus_block.health is not None and self._focus_block.health <= 0):
            self._focus_block = None
        # 路径走完了就清空（下次卡住再算）
        if self._path_step >= len(self._path):
            self._path = []
            self._path_step = 0
        # 同步矩形
        self.rect.x = int(self.x)
        self.rect.y = int(self.y) + INFO_BAR_HEIGHT
        # record this frame's foot point
        self._foot_curr = (self.rect.centerx, self.rect.bottom)
        # Let non-boss contact damage also chew through red blocks so they don't get stuck
        if not getattr(self, "is_boss", False) and self._block_contact_cd <= 0.0:
            ob_contact = getattr(self, "_hit_ob", None)
            if ob_contact and getattr(ob_contact, "type", "") == "Destructible" and getattr(ob_contact, "health",
                                                                                            None) is not None:
                mult = getattr(game_state, "biome_enemy_contact_mult", 1.0)
                block_dmg = int(round(ENEMY_CONTACT_DAMAGE * max(1.0, mult)))
                ob_contact.health -= block_dmg
                self._block_contact_cd = float(PLAYER_HIT_COOLDOWN)
                if ob_contact.health <= 0:
                    gp = getattr(ob_contact, "grid_pos", None)
                    if gp in game_state.obstacles:
                        del game_state.obstacles[gp]
                    cx2, cy2 = ob_contact.rect.centerx, ob_contact.rect.centery
                    if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                        game_state.spawn_spoils(cx2, cy2, 1)
                    self.gain_xp(XP_ENEMY_BLOCK)
                    if random.random() < HEAL_DROP_CHANCE_BLOCK:
                        game_state.spawn_heal(cx2, cy2, HEAL_POTION_AMOUNT)
                    self._focus_block = None
        # 圆心是否触到障碍 → Boss可直接碾碎，否则按原CD打可破坏物
        if self.attack_timer >= attack_interval:
            cx = self.x + self.size * 0.5
            cy = self.y + self.size * 0.5 + INFO_BAR_HEIGHT
            for ob in list(obstacles):
                if ob.rect.inflate(self.radius * 2, self.radius * 2).collidepoint(cx, cy):
                    if getattr(self, "can_crush_all_blocks", False):
                        # Bulldozer path: remove ANY obstacle it touches
                        gp = getattr(ob, "grid_pos", None)
                        if gp in game_state.obstacles:
                            del game_state.obstacles[gp]
                        # keep drops only for destructible; indestructible gives nothing
                        if getattr(ob, "type", "") == "Destructible":
                            cx2, cy2 = ob.rect.centerx, ob.rect.centery
                            if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                                game_state.spawn_spoils(cx2, cy2, 1)
                            self.gain_xp(XP_ENEMY_BLOCK)
                            if random.random() < HEAL_DROP_CHANCE_BLOCK:
                                game_state.spawn_heal(cx2, cy2, HEAL_POTION_AMOUNT)
                        self.attack_timer = 0.0
                        self._focus_block = None
                    else:
                        # Non-boss: original behavior vs. Destructible
                        if getattr(ob, "type", "") == "Destructible":
                            ob.health -= self.attack
                            self.attack_timer = 0.0
                            if ob.health <= 0:
                                gp = ob.grid_pos
                                if gp in game_state.obstacles: del game_state.obstacles[gp]
                                cx2, cy2 = ob.rect.centerx, ob.rect.centery
                                if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                                    game_state.spawn_spoils(cx2, cy2, 1)
                                self.gain_xp(XP_ENEMY_BLOCK)
                                if random.random() < HEAL_DROP_CHANCE_BLOCK:
                                    game_state.spawn_heal(cx2, cy2, HEAL_POTION_AMOUNT)
                    break

    def update_special(self, dt: float, player: 'Player', enemies: List['Enemy'],
                       enemy_shots: List['EnemyShot'], game_state: 'GameState' = None):
        # --- frame-local centers (avoid UnboundLocal on cx/cy/px/py) ---
        cx, cy = self.rect.centerx, self.rect.centery
        px, py = player.rect.centerx, player.rect.centery
        # --- Splinter passive split when HP <= 50% (non-lethal path) ---
        if self._can_split and not self._split_done and self.hp > 0 and self.hp <= int(self.max_hp * 0.5):
            # 标记已分裂，生成子体并移除自己
            self._split_done = True
            self._can_split = False
            spawn_splinter_children(
                self, enemies, game_state,
                level_idx=getattr(game_state, "current_level", 0),
                wave_index=0
            )
            # 将自己“杀死”以便主循环移除（或者直接把 hp 置 0）
            self.hp = 0
            return
        if self.type == "ravager":
            cd_min, cd_max = RAVAGER_DASH_CD_RANGE
            if not hasattr(self, "_dash_state"):
                self._dash_state = "idle"
                self._dash_cd = random.uniform(cd_min, cd_max)
                self._dash_t = 0.0
                self._dash_speed_hold = float(self.speed)
                self._ghost_accum = 0.0
            if getattr(self, "_dash_state", "") != "go" and getattr(self, "can_crush_all_blocks", False):
                self.can_crush_all_blocks = False
            self._dash_cd = max(0.0, (self._dash_cd or 0.0) - dt)
            if self._dash_state == "idle" and self._dash_cd <= 0.0:
                vx, vy = px - cx, py - cy
                L = (vx * vx + vy * vy) ** 0.5 or 1.0
                self._dash_dir = (vx / L, vy / L)
                self._dash_state = "wind"
                self._dash_t = RAVAGER_DASH_WINDUP
                self._dash_speed_hold = float(self.speed)
                self._ghost_accum = 0.0
                self.speed = max(0.2, self._dash_speed_hold * 0.35)
                if game_state:
                    game_state.spawn_telegraph(cx, cy, r=int(getattr(self, "radius", self.size * 0.5) * 0.9),
                                               life=self._dash_t, kind="ravager_dash", payload=None)
            elif self._dash_state == "wind":
                self._dash_t -= dt
                self.speed = max(0.2, self._dash_speed_hold * 0.35)
                if self._dash_t <= 0.0:
                    self._dash_state = "go"
                    self._dash_t = RAVAGER_DASH_TIME
                    self.speed = self._dash_speed_hold
                    self.buff_spd_add = float(getattr(self, "buff_spd_add", 0.0)) + float(self._dash_speed_hold) * (
                                RAVAGER_DASH_SPEED_MULT - 1.0)
                    self.buff_t = max(getattr(self, "buff_t", 0.0), self._dash_t)
                    self.no_clip_t = max(getattr(self, "no_clip_t", 0.0), self._dash_t + 0.05)
                    self.can_crush_all_blocks = True
                    self._dash_cd = random.uniform(cd_min, cd_max)
            elif self._dash_state == "go":
                self._dash_t -= dt
                self.can_crush_all_blocks = True
                self.no_clip_t = max(getattr(self, "no_clip_t", 0.0), 0.05)
                self._ghost_accum += dt
                f0 = getattr(self, "_foot_prev", (self.rect.centerx, self.rect.bottom))
                f1 = getattr(self, "_foot_curr", (self.rect.centerx, self.rect.bottom))
                n = int(self._ghost_accum // AFTERIMAGE_INTERVAL)
                if n > 0:
                    self._ghost_accum -= n * AFTERIMAGE_INTERVAL
                    for i in range(n):
                        t = (i + 1) / (n + 1)
                        gx = f0[0] * (1 - t) + f1[0] * t
                        gy = f0[1] * (1 - t) + f1[1] * t
                        game_state.ghosts.append(
                            AfterImageGhost(gx, gy, self.size, self.size, ENEMY_COLORS.get("ravager", self.color),
                                            ttl=AFTERIMAGE_TTL))
                if self._dash_t <= 0.0:
                    self._dash_state = "idle"
                    self.can_crush_all_blocks = False
            else:
                self.can_crush_all_blocks = False
        if getattr(self, "is_boss", False) and getattr(self, "hp", 0) <= 0:
            trigger_twin_enrage(self, enemies, game_state)
        # 远程怪：发射投射物
        if self.type in ("ranged", "spitter"):
            self.ranged_cd = max(0.0, (self.ranged_cd or 0.0) - dt)
            if self.ranged_cd <= 0.0:
                # 朝玩家中心发射
                cx, cy = self.rect.centerx, self.rect.centery
                px, py = player.rect.centerx, player.rect.centery
                dx, dy = px - cx, py - cy
                L = (dx * dx + dy * dy) ** 0.5 or 1.0
                vx, vy = dx / L * RANGED_PROJ_SPEED, dy / L * RANGED_PROJ_SPEED
                enemy_shots.append(EnemyShot(cx, cy, vx, vy, RANGED_PROJ_DAMAGE))
                self.ranged_cd = RANGED_COOLDOWN
        # 自爆怪：接近玩家后才启动引信；到时爆炸
        if self.type in ("suicide", "bomber"):
            cx, cy = self.rect.centerx, self.rect.centery
            pr = player.rect
            dx, dy = pr.centerx - cx, pr.centery - cy
            dist = (dx * dx + dy * dy) ** 0.5
            # Arm when close enough
            if (not getattr(self, "suicide_armed", False)) and dist <= SUICIDE_ARM_DIST:
                self.suicide_armed = True
                self.fuse = float(SUICIDE_FUSE)
            # Ticking fuse
            if getattr(self, "suicide_armed", False) and (self.fuse is not None):
                self.fuse -= dt
                if self.fuse <= 0.0:
                    # explode
                    if dist <= SUICIDE_RADIUS and player.hit_cd <= 0.0:
                        game_state.damage_player(player, SUICIDE_DAMAGE)
                        player.hit_cd = float(PLAYER_HIT_COOLDOWN)
                    self.hp = 0  # remove self
        if self.type == "ravager":
            cd_min, cd_max = RAVAGER_DASH_CD_RANGE
            if not hasattr(self, "_dash_state"):
                self._dash_state = "idle"
                self._dash_cd = random.uniform(cd_min, cd_max)
                self._dash_t = 0.0
                self._dash_speed_hold = float(self.speed)
                self._ghost_accum = 0.0
            if getattr(self, "_dash_state", "") != "go" and getattr(self, "can_crush_all_blocks", False):
                self.can_crush_all_blocks = False
            self._dash_cd = max(0.0, (self._dash_cd or 0.0) - dt)
            if self._dash_state == "idle" and self._dash_cd <= 0.0:
                vx, vy = px - cx, py - cy
                L = (vx * vx + vy * vy) ** 0.5 or 1.0
                self._dash_dir = (vx / L, vy / L)
                self._dash_state = "wind"
                self._dash_t = RAVAGER_DASH_WINDUP
                self._dash_speed_hold = float(self.speed)
                self._ghost_accum = 0.0
                self.speed = max(0.2, self._dash_speed_hold * 0.35)
                if game_state:
                    game_state.spawn_telegraph(cx, cy, r=int(getattr(self, "radius", self.size * 0.5) * 0.9),
                                               life=self._dash_t, kind="ravager_dash", payload=None)
            elif self._dash_state == "wind":
                self._dash_t -= dt
                self.speed = max(0.2, self._dash_speed_hold * 0.35)
                if self._dash_t <= 0.0:
                    self._dash_state = "go"
                    self._dash_t = RAVAGER_DASH_TIME
                    self.speed = self._dash_speed_hold
                    self.buff_spd_add = float(getattr(self, "buff_spd_add", 0.0)) + float(self._dash_speed_hold) * (
                                RAVAGER_DASH_SPEED_MULT - 1.0)
                    self.buff_t = max(getattr(self, "buff_t", 0.0), self._dash_t)
                    self.no_clip_t = max(getattr(self, "no_clip_t", 0.0), self._dash_t + 0.05)
                    self.can_crush_all_blocks = True
                    self._dash_cd = random.uniform(cd_min, cd_max)
            elif self._dash_state == "go":
                self._dash_t -= dt
                self.can_crush_all_blocks = True
                self.no_clip_t = max(getattr(self, "no_clip_t", 0.0), 0.05)
                self._ghost_accum += dt
                f0 = getattr(self, "_foot_prev", (self.rect.centerx, self.rect.bottom))
                f1 = getattr(self, "_foot_curr", (self.rect.centerx, self.rect.bottom))
                n = int(self._ghost_accum // AFTERIMAGE_INTERVAL)
                if n > 0:
                    self._ghost_accum -= n * AFTERIMAGE_INTERVAL
                    for i in range(n):
                        t = (i + 1) / (n + 1)
                        gx = f0[0] * (1 - t) + f1[0] * t
                        gy = f0[1] * (1 - t) + f1[1] * t
                        game_state.ghosts.append(
                            AfterImageGhost(gx, gy, self.size, self.size, ENEMY_COLORS.get("ravager", self.color),
                                            ttl=AFTERIMAGE_TTL))
                if self._dash_t <= 0.0:
                    self._dash_state = "idle"
                    self.can_crush_all_blocks = False
            else:
                self.can_crush_all_blocks = False
        if getattr(self, "is_boss", False) and getattr(self, "hp", 0) <= 0:
            trigger_twin_enrage(self, enemies, game_state)
        # 增益怪：周期性为周围友军加 BUFF
        if self.type == "buffer":
            self.buff_cd = max(0.0, (self.buff_cd or 0.0) - dt)
            if self.buff_cd <= 0.0:
                cx, cy = self.rect.centerx, self.rect.centery
                for z in enemies:
                    zx, zy = z.rect.centerx, z.rect.centery
                    if (zx - cx) ** 2 + (zy - cy) ** 2 <= BUFF_RADIUS ** 2:
                        z.buff_t = BUFF_DURATION
                        z.buff_atk_mult = BUFF_ATK_MULT
                        z.buff_spd_add = BUFF_SPD_ADD
                self.buff_cd = BUFF_COOLDOWN
        # 护盾怪：周期性给周围友军加护盾
        if self.type == "shielder":
            self.shield_cd = max(0.0, (self.shield_cd or 0.0) - dt)
            # 同时衰减自身护盾
            if self.shield_hp > 0:
                self.shield_t -= dt
                if self.shield_t <= 0:
                    self.shield_hp = 0
                if self.shield_cd <= 0.0:
                    cx, cy = self.rect.centerx, self.rect.centery
                    for z in enemies:
                        zx, zy = z.rect.centerx, z.rect.centery
                        if (zx - cx) ** 2 + (zy - cy) ** 2 <= SHIELD_RADIUS ** 2:
                            z.shield_hp = SHIELD_AMOUNT
                            z.shield_t = SHIELD_DURATION
                    self.shield_cd = SHIELD_COOLDOWN
        # ==== 金币大盗：持续偷钱、计时逃脱 ====
        if getattr(self, "type", "") == "bandit":
            bandit_wind_trapped = bool(getattr(self, "_wind_trapped", False))
            # 光环动画相位（1.2s 一次完整扩散）
            self._aura_t = (getattr(self, "_aura_t", 0.0) + dt / 1.2) % 1.0
            # 持续闪金光（维持金色淡晕）
            self._gold_glow_t = max(self._gold_glow_t, 0.2)
            if getattr(self, "radar_slow_left", 0.0) > 0.0:
                self.radar_slow_left = max(0.0, float(getattr(self, "radar_slow_left", 0.0)) - dt)
                if self.radar_slow_left <= 0.0 and hasattr(self, "_radar_base_speed"):
                    self.speed = float(getattr(self, "_radar_base_speed", self.speed))
            if getattr(self, "radar_tagged", False):
                self.radar_ring_phase = (float(getattr(self, "radar_ring_phase", 0.0)) + dt) % float(getattr(self, "radar_ring_period", 2.0))
            # 偷钱累积：以秒为单位的离散扣除，避免浮点抖动
            self._steal_accum += float(getattr(self, "steal_per_sec", BANDIT_STEAL_RATE_MIN)) * dt
            steal_units = int(self._steal_accum)
            if steal_units >= 1 and game_state is not None:
                self._steal_accum -= steal_units
                # steal from total (level spoils + bank), prefer draining level spoils first
                lvl = int(getattr(game_state, "spoils_gained", 0))
                bank = int(META.get("spoils", 0))
                total_avail = max(0, lvl + bank)
                lb_lvl = int(getattr(self, "lockbox_level", META.get("lockbox_level", 0)))
                lock_floor = 0
                if lb_lvl > 0:
                    lock_floor = int(getattr(self, "lockbox_floor", 0))
                    if lock_floor <= 0:
                        baseline = int(getattr(self, "lockbox_baseline", total_avail))
                        lock_floor = lockbox_protected_min(baseline, lb_lvl)
                        self.lockbox_level = lb_lvl
                        self.lockbox_baseline = baseline
                        self.lockbox_floor = lock_floor
                    lock_floor = min(lock_floor, total_avail)
                stealable_cap = max(0, total_avail - lock_floor)
                got = min(steal_units, stealable_cap)
                if got > 0:
                    take_lvl = min(lvl, got)
                    if take_lvl:
                        game_state.spoils_gained = lvl - take_lvl
                    rest = got - take_lvl
                    if rest:
                        META["spoils"] = max(0, bank - rest)
                    self._stolen_total = int(getattr(self, "_stolen_total", 0)) + got
                    game_state._bandit_stolen = int(getattr(game_state, "_bandit_stolen", 0)) + got
                    # 飘字提示（-金币）
                    cx, cy = self.rect.centerx, self.rect.centery
                    game_state.add_damage_text(cx, cy - 18, f"-{got}", crit=True, kind="hp")
            # 逃跑计时
            current_escape = float(getattr(self, "escape_t", BANDIT_ESCAPE_TIME_BASE))
            if bandit_wind_trapped:
                # Freeze the escape timer while trapped in wind to prevent fleeing
                self.escape_t = max(0.0, current_escape)
            else:
                self.escape_t = max(0.0, current_escape - dt)
            if self.escape_t <= 0.0 and not bandit_wind_trapped:
                if game_state is not None:
                    # 小飘字（保留）
                    game_state.add_damage_text(self.rect.centerx, self.rect.centery, "ESCAPED", crit=False,
                                               kind="shield")
                    stolen = int(getattr(self, "_stolen_total", 0))
                    game_state.flash_banner(f"BANDIT ESCAPED — STOLEN {stolen} COINS", sec=1.0)
                try:
                    enemies.remove(self)
                except Exception:
                    pass
                return
        # 小雾妖：可被攻击；死时自爆；计时≥10s 会被 Boss 收回（由 Boss 侧结算回血）
        if self.type == "mistling":
            # 计时
            self._life = getattr(self, "_life", 0.0) + dt
            # 被击杀 → 自爆（一次性）
            if self.hp <= 0 and not getattr(self, "_boom_done", False):
                cx, cy = self.rect.centerx, self.rect.centery
                pr = player.rect
                if (pr.centerx - cx) ** 2 + (pr.centery - cy) ** 2 <= (MISTLING_BLAST_RADIUS ** 2):
                    if player.hit_cd <= 0.0:
                        game_state.damage_player(player, MISTLING_BLAST_DAMAGE)
                        player.hit_cd = float(PLAYER_HIT_COOLDOWN)
                self._boom_done = True
                # 允许主循环正常移除
        # 腐蚀幼体：死亡留酸；计时>15s 可被BOSS吸回
        if self.type == "corruptling":
            self._life = getattr(self, "_life", 0.0) + dt
            if self.hp <= 0 and not getattr(self, "_acid_on_death", False):
                game_state.spawn_acid_pool(self.rect.centerx, self.rect.centery, r=20, life=4.0, dps=ACID_DPS * 0.8)
                self._acid_on_death = True  # 让后续移除流程照常进行
            # 吸附由 BOSS 侧发起，这里只负责寿命记录
        # 记忆吞噬者（boss_mem）
        if getattr(self, "is_boss", False) and getattr(self, "type", "") == "boss_mem":
            enraged = bool(getattr(self, "is_enraged", False))
            hp_pct = max(0.0, self.hp / max(1, self.max_hp))
            hp_pct_effective = 0.0 if enraged else hp_pct  # enraged: ignore HP gates for skills
            cd_mult = float(getattr(self, "_enrage_cd_mult", 1.0))
            # 阶段切换
            if enraged:
                self.phase = 3
            else:
                if hp_pct > 0.70:
                    self.phase = 1
                elif hp_pct > 0.40:
                    self.phase = 2
                else:
                    self.phase = 3
            # 基础冷却
            self._spit_cd = max(0.0, getattr(self, "_spit_cd", 0.0) - dt)
            self._split_cd = max(0.0, getattr(self, "_split_cd", 0.0) - dt)

            # Higher stages retain lower-stage skills (2 keeps 1; 3 keeps 1+2)
            phase1_ok = enraged or self.phase >= 1
            phase2_ok = enraged or self.phase >= 2
            phase3_ok = enraged or self.phase >= 3
            # 阶段1：腐蚀喷吐 + 小怪 2 个/20s
            if phase1_ok:
                if self._spit_cd <= 0.0:
                    # 以玩家方向的扇形在地面“预警→落酸”
                    px, py = player.rect.centerx, player.rect.centery
                    ang = math.atan2(py - cy, px - cx)
                    points = []
                    for w in range(SPIT_WAVES_P1):
                        for i in range(SPIT_PUDDLES_PER_WAVE):
                            off_ang = ang + math.radians(random.uniform(-SPIT_CONE_DEG / 2, SPIT_CONE_DEG / 2))
                            dist = (SPIT_RANGE * (i + 1) / SPIT_PUDDLES_PER_WAVE) * random.uniform(0.6, 1.0)
                            points.append((cx + math.cos(off_ang) * dist, cy + math.sin(off_ang) * dist))
                    game_state.spawn_telegraph(cx, cy, r=28, life=ACID_TELEGRAPH_T, kind="acid",
                                               payload={"points": points, "radius": 24, "life": ACID_LIFETIME,
                                                        "dps": ACID_DPS, "slow": ACID_SLOW_FRAC})
                    self._spit_cd = 5.0 * cd_mult
                if self._split_cd <= 0.0:
                    for _ in range(2):
                        enemies.append(spawn_corruptling_at(cx + random.randint(-20, 20), cy + random.randint(-20, 20)))
                    self._split_cd = SPLIT_CD_P1 * cd_mult
            # 阶段2：移动略快；喷吐“连续两次”；召唤 3 个/15s；吸附融合
            if phase2_ok:
                self.speed = max(MEMDEV_SPEED, MEMDEV_SPEED + 0.5)
                if self._spit_cd <= 0.0:
                    for _ in range(2):  # 连续两次
                        px, py = player.rect.centerx, player.rect.centery
                        ang = math.atan2(py - cy, px - cx)
                        points = []
                        for w in range(SPIT_WAVES_P1):
                            for i in range(SPIT_PUDDLES_PER_WAVE):
                                off_ang = ang + math.radians(random.uniform(-SPIT_CONE_DEG / 2, SPIT_CONE_DEG / 2))
                                dist = (SPIT_RANGE * (i + 1) / SPIT_PUDDLES_PER_WAVE) * random.uniform(0.6, 1.0)
                                points.append((cx + math.cos(off_ang) * dist, cy + math.sin(off_ang) * dist))
                        game_state.spawn_telegraph(cx, cy, r=32, life=ACID_TELEGRAPH_T, kind="acid",
                                                   payload={"points": points, "radius": 26, "life": ACID_LIFETIME,
                                                            "dps": ACID_DPS, "slow": ACID_SLOW_FRAC})
                    self._spit_cd = 4.0 * cd_mult
                if self._split_cd <= 0.0:
                    for _ in range(3):
                        enemies.append(spawn_corruptling_at(cx + random.randint(-20, 20), cy + random.randint(-20, 20)))
                    self._split_cd = SPLIT_CD_P2 * cd_mult
                # 吸附融合：场上活过 15s 的腐蚀幼体被拉回并回血
                pull_any = False
                for z in list(enemies):
                    if getattr(z, "type", "") == "corruptling" and getattr(z, "_life", 0.0) >= FUSION_LIFETIME:
                        zx, zy = z.rect.centerx, z.rect.centery
                        if (zx - cx) ** 2 + (zy - cy) ** 2 <= FUSION_PULL_RADIUS ** 2:
                            z.hp = 0  # kill
                            self.hp = min(self.max_hp, self.hp + FUSION_HEAL)
                            pull_any = True
                if pull_any:
                    # 可选：加一个小数字飘字：+HP
                    game_state.add_damage_text(cx, cy, +FUSION_HEAL, crit=False, kind="shield")  # 蓝色表示护盾/回复
            # 阶段3：全屏酸爆(每降 10%一次) + 继续召唤；<10% 濒死冲锋
            if phase3_ok:
                # 全屏酸爆：按阈值触发
                next_pct = getattr(self, "_rain_next_pct", 0.40)
                while hp_pct_effective <= next_pct and next_pct >= 0.0:
                    # 随机铺点（带预警）
                    pts = []
                    for _ in range(RAIN_PUDDLES):
                        gx = random.randint(0, GRID_SIZE - 1)
                        gy = random.randint(0, GRID_SIZE - 1)
                        pts.append((gx * CELL_SIZE + CELL_SIZE // 2, gy * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT))
                    game_state.spawn_telegraph(cx, cy, r=36, life=RAIN_TELEGRAPH_T, kind="acid",
                                               payload={"points": pts, "radius": 22, "life": ACID_LIFETIME,
                                                        "dps": ACID_DPS, "slow": ACID_SLOW_FRAC})
                    next_pct -= RAIN_STEP
                    self._rain_next_pct = next_pct
                # 继续召唤（比P2略低频防爆场）
                if self._split_cd <= 0.0:
                    for _ in range(2):
                        enemies.append(spawn_corruptling_at(cx + random.randint(-20, 20), cy + random.randint(-20, 20)))
                    self._split_cd = 12.0 * cd_mult
                # 濒死冲锋
                if hp_pct_effective <= CHARGE_THRESH and not getattr(self, "_charging", False):
                    self._charging = True
                    # 直接朝玩家方向加速移动，不受可破坏物阻挡（移动层会处理破坏）
                    self.speed = CHARGE_SPEED
            # ===== Boss：蓄力冲刺（全阶段可触发） =====
            if not hasattr(self, "_dash_state"):
                self._dash_state = "idle"
                self._dash_cd = random.uniform(4.5, 6.0) * cd_mult
                # initial dash cooldown already scaled by cd_mult
                self._dash_t = 0.0
                self._dash_speed_hold = float(self.speed)
                self._ghost_accum = 0.0  # 残影生成计时器
            # 冷却推进
            self._dash_cd = max(0.0, self._dash_cd - dt)
            # 进入“蓄力”
            if self._dash_state == "idle" and self._dash_cd <= 0.0 and not getattr(self, "_charging", False):
                px, py = player.rect.centerx, player.rect.centery
                cx, cy = self.rect.centerx, self.rect.centery
                vx, vy = px - cx, py - cy
                L = (vx * vx + vy * vy) ** 0.5 or 1.0
                self._dash_dir = (vx / L, vy / L)
                self._dash_state = "wind"
                self._dash_t = BOSS_DASH_WINDUP
                self._dash_speed_hold = float(self.speed)
                self._ghost_accum = 0.0
                # 蓄力时显著减速
                self.speed = max(0.2, self._dash_speed_hold * 0.25)
                # 视觉预警：中心圈（可保留；不想要可以注释）
                game_state.spawn_telegraph(cx, cy, r=int(getattr(self, "radius", self.size * 0.5) * 0.9),
                                           life=self._dash_t, kind="acid", payload=None)
            elif self._dash_state == "wind":
                self._dash_t -= dt
                self.speed = max(0.2, self._dash_speed_hold * 0.25)
                if self._dash_t <= 0.0:
                    self._dash_state = "go"
                    self._dash_t = BOSS_DASH_GO_TIME
                    self.speed = self._dash_speed_hold  # 恢复基础，实际提速走 buff
                    dash_mult = BOSS_DASH_SPEED_MULT_ENRAGED if getattr(self, "is_enraged",
                                                                        False) else BOSS_DASH_SPEED_MULT
                    self.buff_spd_add = float(getattr(self, "buff_spd_add", 0.0)) + float(self._dash_speed_hold) * (
                            dash_mult - 1.0)
                    self.buff_t = max(getattr(self, "buff_t", 0.0), self._dash_t)
                    # 短暂无视碰撞：冲刺更“果断”
                    self.no_clip_t = max(getattr(self, "no_clip_t", 0.0), self._dash_t + 0.05)
                    # 预设下次冷却，稍后在 go 结束时生效（避免 wind 期间被改动）
                    self._dash_cd_next = random.uniform(4.5, 6.0)
            elif self._dash_state == "go":
                self._dash_t -= dt
                # emit ghosts along the actual path covered this frame (trailing)
                self._ghost_accum += dt
                f0 = getattr(self, "_foot_prev", (self.rect.centerx, self.rect.bottom))  # last frame foot
                f1 = getattr(self, "_foot_curr", (self.rect.centerx, self.rect.bottom))  # this frame foot
                n = int(self._ghost_accum // AFTERIMAGE_INTERVAL)
                if n > 0:
                    self._ghost_accum -= n * AFTERIMAGE_INTERVAL
                    # place n ghosts between f0→f1 (closer to f0 = looks behind)
                    for i in range(n):
                        t = (i + 1) / (n + 1)  # 0 < t < 1
                        gx = f0[0] * (1 - t) + f1[0] * t
                        gy = f0[1] * (1 - t) + f1[1] * t
                        game_state.ghosts.append(
                            AfterImageGhost(gx, gy, self.size, self.size, self.color, ttl=AFTERIMAGE_TTL))
                if self._dash_t <= 0.0:
                    self._dash_state = "idle"
                    next_cd = getattr(self, "_dash_cd_next", None)
                    if next_cd is None:
                        next_cd = random.uniform(4.5, 6.0)
                    self._dash_cd = next_cd * cd_mult
                    self._dash_cd_next = None

    def draw(self, screen):
        if getattr(self, "type", "") == "bandit":
            cx, cy = self.rect.centerx, self.rect.bottom
            t = float(getattr(self, "_aura_t", 0.0)) % 1.0
            base_r = max(16, int(self.radius * 7.0))
            r = int(base_r + (self.radius * 1.2) * t)
            alpha = int(210 - 150 * t)
            s = pygame.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
            pygame.draw.circle(s, (255, 215, 0, int(alpha * 0.35)), (r + 3, r + 3), r)
            pygame.draw.circle(s, (255, 215, 0, alpha), (r + 3, r + 3), r, width=5)
            screen.blit(s, (cx - r - 3, cy - r - 3))
            if getattr(self, "radar_tagged", False):
                rr = max(20, int(self.radius * 3.0))
                ring = pygame.Surface((rr * 2 + 10, rr * 2 + 10), pygame.SRCALPHA)
                pygame.draw.circle(ring, (255, 60, 60, 220), (rr + 5, rr + 5), rr, width=6)
                screen.blit(ring, (self.rect.centerx - rr - 5, self.rect.centery - rr - 5))
        fallback = ENEMY_COLORS.get(getattr(self, "type", "basic"), (255, 60, 60))
        color = getattr(self, "_current_color", fallback)
        pygame.draw.rect(screen, color, self.rect)
        if getattr(self, "is_enraged", False):
            pad = 6
            glow_rect = self.rect.inflate(pad * 2, pad * 2)
            glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
            pulse = 150 + int(60 * math.sin(pygame.time.get_ticks() * 0.02))
            pygame.draw.rect(glow,
                             (min(255, max(0, color[0])),
                              min(255, max(0, color[1])),
                              min(255, max(0, color[2])),
                              min(255, max(80, pulse))),
                             glow.get_rect(),
                             width=3,
                             border_radius=8)
            screen.blit(glow, glow_rect.topleft)


class MemoryDevourerBoss(Enemy):
    """独立 Boss：更大体型/更大脚底圆/更高血攻；仍复用 Enemy 的大多数行为。"""

    def __init__(self, grid_pos: tuple[int, int], level_idx: int):
        gx, gy = grid_pos
        # 计算血量：沿用你原先“第5关为基准 + 关卡成长”的口径
        boss_hp = int(MEMDEV_BASE_HP * (1 + 0.15 * max(0, level_idx - 1)))
        self.skill_last = {"dash": -99, "vomit": -99, "summon": -99, "ring": -99}
        self.skill_phase = None  # None | "dash_wind" | "dash_go"
        self.skill_t = 0.0
        # 用父类构造出一个 type='boss_mem' 的单位，再整体重写体型与半径
        super().__init__((gx, gy),
                         attack=int(MEMDEV_CONTACT_DAMAGE),
                         speed=int(max(1, MEMDEV_SPEED)),
                         ztype="boss_mem",
                         hp=boss_hp)
        self.color = ENEMY_COLORS.get('boss_mem', (170, 40, 200))
        self._current_color = self.color
        self.is_boss = True
        self.boss_name = "Memory Devourer"
        # Footprint/radius aligned with Mistweaver so bullets collide with the visible body
        self.size = int(CELL_SIZE * 1.6)
        self.rect = pygame.Rect(self.x,
                                self.y + INFO_BAR_HEIGHT,
                                self.size, self.size)
        self.radius = int(self.size * 0.50)
        # Twin boss bulldozer: can crush any obstacle
        self.can_crush_all_blocks = True
        self.no_clip_t = 0.0  # ghost through collisions for a few frames after crush
        self._stuck_t = 0.0  # watch-dog for anti-stuck
        self.twin_slot = getattr(self, "twin_slot", +1)  # +1 or -1 (assigned when binding)
        self._last_pos = (float(self.x), float(self.y))
        self._twin_powered = False
        self.is_enraged = False
        # 出生延迟维持一致
        self.spawn_delay = 0.6

    def bind_twin(self, other, twin_id):
        import weakref
        self.twin_id = twin_id
        self._twin_partner_ref = weakref.ref(other)
        other.twin_id = twin_id
        other._twin_partner_ref = weakref.ref(self)

    def on_twin_partner_death(self):
        # 已触发过就不再触发
        if getattr(self, "_twin_powered", False) or self.hp <= 0:
            return
        # 回满血并狂暴
        self.hp = int(getattr(self, "max_hp", self.hp))
        self.attack = int(self.attack * TWIN_ENRAGE_ATK_MULT)
        self.speed = int(self.speed + TWIN_ENRAGE_SPD_ADD)
        self._twin_powered = True
        self.is_enraged = True
        self._enrage_cd_mult = 0.65
        enraged_color = ENEMY_COLORS.get("boss_mem_enraged", BOSS_MEM_ENRAGED_COLOR)
        self._current_color = enraged_color
        self.color = enraged_color
        if hasattr(self, "_dash_cd"):
            self._dash_cd *= self._enrage_cd_mult
        # 可选：改名/标记，方便UI显示
        self.boss_name = (getattr(self, "boss_name", "BOSS") + " [ENRAGED]")
    # （可选）你也可以覆盖 draw，画个大圆/贴图；目前沿用矩形色块就行


class MistClone(Enemy):
    def __init__(self, gx: int, gy: int):
        super().__init__((gx, gy), attack=8, speed=int(MIST_SPEED * CELL_SIZE / CELL_SIZE), ztype="mist_clone", hp=1)
        self.color = ENEMY_COLORS["mist_clone"]
        self.size = int(CELL_SIZE * 0.6)
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)
        self.is_illusion = True

    def update_special(self, dt, player, enemies, enemy_shots, game_state=None):
        # 命中即散，死亡时留一个小雾爆
        if self.hp <= 0 and not getattr(self, "_mist_boom", False):
            game_state.spawn_acid_pool(self.rect.centerx, self.rect.centery,
                                       r=int(CELL_SIZE * 0.6), life=1.2, dps=8, slow_frac=0.25)
            self._mist_boom = True


class MistweaverBoss(Enemy):
    def __init__(self, grid_pos: tuple[int, int], level_idx: int):
        gx, gy = grid_pos
        super().__init__((gx, gy),
                         attack=MIST_CONTACT_DAMAGE,
                         speed=int(MIST_SPEED),
                         ztype="boss_mist",
                         hp=int(MIST_BASE_HP * (1 + 0.12 * max(0, level_idx - 9))))
        self.is_boss = True
        self.boss_name = "Mistweaver"
        self.color = ENEMY_COLORS["boss_mist"]
        # 体型稍大（比普通僵尸更有压迫感）
        self.size = int(CELL_SIZE * 1.6)
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)
        self.radius = int(self.size * 0.50)
        # 阶段
        self.phase = 1
        self._storm_cd = 2.0
        self._blade_cd = 1.5
        self._blink_cd = MIST_BLINK_CD
        self._sonar_next = 1.0  # 下一个“HP 比例阈值”（先置 100%→70% 时触发）
        self._clone_ids = set()
        self.can_crush_all_blocks = True
        self.no_clip_t = 0.0  # 推平后的短暂无视碰撞（你已有清理）
        # 启动时请求雾场（GameState 每帧会判定并开启）
        self._want_fog = True
        # 弹幕
        self._ring_cd = random.uniform(2.0, 3.5)
        self._ring_bursts_left = 0
        self._ring_burst_t = 0.0
        self.is_boss_shot = True

    def _has_clones(self, enemies):
        n = 0
        for z in enemies:
            if getattr(z, "is_illusion", False) and getattr(z, "hp", 0) > 0:
                n += 1
        return n

    def _ensure_clones(self, enemies, game_state):
        # 至多 2 个分身存在
        need = max(0, 2 - self._has_clones(enemies))
        while need > 0:
            # 随机在本体附近 2~3 格生成
            gx = int((self.x + self.size * 0.5) // CELL_SIZE) + random.choice((-3, -2, 2, 3))
            gy = int((self.y + self.size * 0.5) // CELL_SIZE) + random.choice((-3, -2, 2, 3))
            if 0 <= gx < GRID_SIZE and 0 <= gy < GRID_SIZE and (gx, gy) not in game_state.obstacles:
                enemies.append(MistClone(gx, gy))
                need -= 1

    def _do_blink(self, game_state):
        # 在两处随机门之间闪现一次，并在原地留下 2 秒雾门减速/DoT
        cx, cy = self.rect.centerx, self.rect.centery
        # 随机另一个位置（边缘附近）
        gx = random.choice((2, GRID_SIZE - 3))
        gy = random.randint(2, GRID_SIZE - 3)
        tx = gx * CELL_SIZE + CELL_SIZE // 2
        ty = gy * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT
        # 两处门的提示圈 + 伤害池（2秒）
        # 雾门
        game_state.spawn_acid_pool(cx, cy, r=int(CELL_SIZE * 0.9), life=MIST_DOOR_STAY,
                                   dps=MIST_DOOR_DPS, slow_frac=MIST_DOOR_SLOW, style="mist_door")
        game_state.spawn_acid_pool(tx, ty, r=int(CELL_SIZE * 0.9), life=MIST_DOOR_STAY,
                                   dps=MIST_DOOR_DPS, slow_frac=MIST_DOOR_SLOW, style="mist_door")
        # 把自己瞬移到对门
        self.x = tx - self.size * 0.5
        self.y = ty - self.size * 0.5 - INFO_BAR_HEIGHT
        self.rect.x = int(self.x)
        self.rect.y = int(self.y) + INFO_BAR_HEIGHT

    def update_special(self, dt, player, enemies, enemy_shots, game_state=None):
        hp_pct = max(0.0, self.hp / max(1, self.max_hp))
        self.phase = 1 if hp_pct > 0.70 else (2 if hp_pct > 0.35 else 3)
        # 保持分身
        self._ensure_clones(enemies, game_state)
        # 雾门闪现 CD
        self._blink_cd -= dt
        if self._blink_cd <= 0:
            self._do_blink(game_state)
            self._blink_cd = MIST_BLINK_CD
        # P1：雾刃扇形 + 召唤雾妖（wormlings）
        if self.phase == 1:
            self._blade_cd -= dt
            if self._blade_cd <= 0:
                ang0 = math.atan2(player.rect.centery - self.rect.centery, player.rect.centerx - self.rect.centerx)
                spread = math.radians(40)
                for i in range(-1, 2):  # -1,0,1
                    ang = ang0 + i * spread
                    # 用 4~5 个小池子拼“雾带”
                    for k in range(1, 5):
                        d = k * CELL_SIZE * 1.0
                        x = self.rect.centerx + math.cos(ang) * d
                        y = self.rect.centery + math.sin(ang) * d
                        # P1 雾刃：雾带小池子 -> 统一 style='mist'
                        game_state.spawn_acid_pool(x, y, r=int(CELL_SIZE * 0.45),
                                                   life=MIST_P1_STRIP_TIME, dps=MIST_P1_STRIP_DPS,
                                                   slow_frac=MIST_P1_STRIP_SLOW, style="mist")  # ★
                self._blade_cd = MIST_P1_BLADE_CD
            # 召唤
            self._storm_cd -= dt
            if self._storm_cd <= 0:
                # Mistweaver 召唤（原来追加 Wormling 的地方）
                for _ in range(MIST_SUMMON_IMPS):
                    ox = random.randint(-24, 24);
                    oy = random.randint(-24, 24)
                    enemies.append(spawn_mistling_at(self.rect.centerx + ox, self.rect.centery + oy,
                                                     level_idx=getattr(game_state, "current_level", 0)))
                self._storm_cd = 6.5
        # P2：白化风暴（0.8s 后落 8 个雾池）+ 静默领域
        if self.phase == 2:
            self._storm_cd -= dt
            if self._storm_cd <= 0:
                # 先做一个“全屏白雾”预警（用 acid telegraph 也行）
                pts = []
                for _ in range(MIST_P2_STORM_POINTS):
                    gx = random.randint(1, GRID_SIZE - 2)
                    gy = random.randint(1, GRID_SIZE - 2)
                    x = gx * CELL_SIZE + CELL_SIZE // 2
                    y = gy * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT
                    pts.append((x, y))
                # 直接在 0.8s 后落雾池（用 telegraph 的 payload 或者简单延迟）
                for (x, y) in pts:
                    game_state.spawn_telegraph(self.rect.centerx, self.rect.centery,
                                               r=22, life=MIST_P2_STORM_WIND, kind="dash_mist",
                                               payload={"points": [(x, y)], "radius": int(CELL_SIZE * 0.5),
                                                        "life": 4.0, "dps": MIST_P2_POOL_DPS,
                                                        "slow": MIST_P2_POOL_SLOW}, color=HAZARD_STYLES["mist"]["ring"])
                self._storm_cd = MIST_P2_STORM_CD
            # 静默领域：随机一个圆区 3 秒，里面额外减速（简化成强减速代替“禁技能”）
            if random.random() < 0.007:  # 低频随机触发
                rx = random.randint(CELL_SIZE * 3, WINDOW_SIZE - CELL_SIZE * 3)
                ry = random.randint(CELL_SIZE * 3, WINDOW_SIZE - CELL_SIZE * 3) + INFO_BAR_HEIGHT
                game_state.spawn_acid_pool(rx, ry, r=MIST_SILENCE_RADIUS, life=MIST_SILENCE_TIME,
                                           dps=0, slow_frac=0.50, style="mist")
        # P3：声纳圈；被命中者“被标记”，Boss 追击加速
        if self.phase == 3:
            next_pct = getattr(self, "_sonar_next", 0.70)
            while hp_pct <= next_pct and next_pct >= 0.0:
                game_state.spawn_telegraph(self.rect.centerx, self.rect.centery,
                                           r=int(self.radius * 1.8), life=0.6, kind="dash_mist",
                                           payload={"note": "mist_sonar"}, color=HAZARD_STYLES["mist"]["ring"])
                self._sonar_next = next_pct - MIST_SONAR_STEP
                next_pct = self._sonar_next
            # 如果玩家处于“标记”，给予追击加速
            if getattr(player, "_mist_mark_t", 0.0) > 0.0:
                self.buff_t = max(self.buff_t, dt)
                self.buff_spd_add = max(self.buff_spd_add, MIST_CHASE_BOOST)
        # P4： —— 自身为圆心的三连发散射 ——
        self._ring_cd = max(0.0, self._ring_cd - dt)
        if self._ring_bursts_left > 0:
            self._ring_burst_t -= dt
            if self._ring_burst_t <= 0.0:
                # 发一环
                for i in range(MIST_RING_PROJECTILES):
                    ang = (2 * math.pi) * (i / MIST_RING_PROJECTILES)
                    vx = math.cos(ang) * MIST_RING_SPEED
                    vy = math.sin(ang) * MIST_RING_SPEED
                    enemy_shots.append(
                        MistShot(self.rect.centerx, self.rect.centery, vx, vy,
                                 MIST_RING_DAMAGE, radius=10, color=HAZARD_STYLES["mist"]["ring"])
                    )
                self._ring_bursts_left -= 1
                self._ring_burst_t = 0.20  # 连发间隔（秒）
                # 给一点白紫预警圈（可选）
                game_state.spawn_telegraph(self.rect.centerx, self.rect.centery, r=int(self.radius * 0.95), life=0.20,
                                           kind="acid", color=HAZARD_STYLES["mist"]["ring"])
        else:
            if self._ring_cd <= 0.0:
                self._ring_bursts_left = MIST_RING_BURSTS
                self._ring_burst_t = 0.0  # 立刻发第一环
                self._ring_cd = MIST_RING_CD
        # --- Mistling 回收：在 Boss 周围半径内的雾妖会被回收并为 Boss 回血 ---
        pull_any = False
        cx, cy = self.rect.center  # ← 确保有中心坐标可用
        for z in list(enemies):
            if getattr(z, "type", "") == "mistling":
                zx, zy = z.rect.centerx, z.rect.centery
                # 进入回收半径：直接被回收（相当于被击杀），标记发生回收
                if (zx - cx) ** 2 + (zy - cy) ** 2 <= (MISTLING_PULL_RADIUS ** 2):
                    z.hp = 0
                    pull_any = True
        if pull_any:
            # Boss 回血，并在 Boss 中心飘字（白紫色的“护盾/治疗”风格）
            self.hp = min(self.max_hp, self.hp + MISTLING_HEAL)
            game_state.add_damage_text(cx, cy, f"+{MISTLING_HEAL}", crit=False, kind="shield")


class Bullet:
    def __init__(self, x: float, y: float, vx: float, vy: float, max_dist: float = MAX_FIRE_RANGE,
                 damage: int = BULLET_DAMAGE_ENEMY, source: str = "player"):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.alive = True
        self.traveled = 0.0
        self.max_dist = clamp_player_range(max_dist)
        self.damage = int(damage)
        self.r = bullet_radius_for_damage(self.damage)
        self.source = source

    def update(self, dt: float, game_state: 'GameState', enemies: List['Enemy'], player: 'Player' = None):
        if not self.alive:
            return
        nx = self.x + self.vx * dt
        ny = self.y + self.vy * dt
        self.traveled += ((nx - self.x) ** 2 + (ny - self.y) ** 2) ** 0.5
        self.x, self.y = nx, ny
        if self.traveled >= self.max_dist:
            self.alive = False
            return
        _rr = int(getattr(self, "r", BULLET_RADIUS))
        r = pygame.Rect(int(self.x - _rr), int(self.y - _rr), _rr * 2, _rr * 2)

        # try ricochet helper (player bullets only)
        def try_ricochet(hit_x: float, hit_y: float) -> bool:
            """Try to bounce this bullet toward the nearest enemy. Return True if bounced."""
            if getattr(self, "source", "player") != "player":
                return False
            remaining = int(getattr(self, "ricochet_left", 0))
            if remaining <= 0:
                return False
            target = None
            best_d2 = None
            for z in enemies:
                if getattr(z, "hp", 0) <= 0:
                    continue
                dx = z.rect.centerx - hit_x
                dy = z.rect.centery - hit_y
                d2 = dx * dx + dy * dy
                if d2 <= 0:
                    continue
                if best_d2 is None or d2 < best_d2:
                    best_d2 = d2
                    target = (dx, dy)
            if target is None:
                return False
            dx, dy = target
            L = (dx * dx + dy * dy) ** 0.5 or 1.0
            speed = (self.vx * self.vx + self.vy * self.vy) ** 0.5 or BULLET_SPEED
            self.vx = dx / L * speed
            self.vy = dy / L * speed
            self.x = hit_x
            self.y = hit_y
            self.ricochet_left = remaining - 1
            return True

        # 1) enemies
        for z in list(enemies):
            if r.colliderect(z.rect):
                # --- crit roll (use player's stats if available) ---
                crit_p = float(getattr(player, "crit_chance", CRIT_CHANCE_BASE))
                crit_m = float(getattr(player, "crit_mult", CRIT_MULT_BASE))
                is_crit = (random.random() < max(0.0, min(0.99, crit_p)))
                base = int(self.damage)
                dealt = int(round(base * (crit_m if is_crit else 1.0)))
                cx, cy = z.rect.centerx, z.rect.centery
                # ==== Mistweaver 专属：远程抗性 + 受击雾化 ====
                if getattr(z, "type", "") == "boss_mist":
                    # 受击雾化：直接免伤并瞬位
                    if random.random() < MIST_PHASE_CHANCE:
                        # 取消这发伤害
                        game_state.add_damage_text(z.rect.centerx, z.rect.centery, "TELEPORT", crit=False, kind="shield")
                        # 向远离玩家的方向瞬位 2 格
                        dx = z.rect.centerx - player.rect.centerx
                        dy = z.rect.centery - player.rect.centery
                        L = (dx * dx + dy * dy) ** 0.5 or 1.0
                        ox = dx / L * (MIST_PHASE_TELE_TILES * CELL_SIZE)
                        oy = dy / L * (MIST_PHASE_TELE_TILES * CELL_SIZE)
                        z.x += ox;
                        z.y += oy - INFO_BAR_HEIGHT
                        z.rect.x = int(z.x);
                        z.rect.y = int(z.y + INFO_BAR_HEIGHT)
                        self.alive = False
                        return
                    # 远程伤害抗性（≥5格）
                    dist_tiles = math.hypot((z.rect.centerx - self.x) / CELL_SIZE,
                                            (z.rect.centery - self.y) / CELL_SIZE)
                    if dist_tiles >= MIST_RANGED_REDUCE_TILES:
                        dealt = int(dealt * MIST_RANGED_MULT)
                dealt = apply_vuln_bonus(z, dealt)
                # --- apply to shield first, overflow to HP ---
                hp_before = z.hp
                if getattr(z, "shield_hp", 0) > 0:
                    blocked = min(dealt, z.shield_hp)
                    z.shield_hp -= dealt
                    # 飘字：护盾伤害（蓝色）
                    game_state.add_damage_text(cx, cy, blocked, crit=is_crit, kind="shield")
                    overflow = dealt - blocked
                    if z.shield_hp < 0:
                        # 已在一行里把溢出算进去了，这里不再额外处理
                        pass
                    if overflow > 0:
                        z.hp -= overflow
                        # 飘字：HP 伤害（红/金）
                        game_state.add_damage_text(cx, cy - 10, overflow, crit=is_crit, kind="hp_player")
                else:
                    z.hp -= dealt
                    game_state.add_damage_text(cx, cy, dealt, crit=is_crit, kind="hp_player")
                hp_lost = max(0, hp_before - max(z.hp, 0))
                if hp_lost > 0:
                    z._hit_flash = float(HIT_FLASH_DURATION)
                    z._flash_prev_hp = int(max(0, z.hp))
                if getattr(self, "source", "player") == "player":
                    dot_lvl = int(META.get("dot_rounds_level", 0))
                    if dot_lvl > 0:
                        if player is not None:
                            bullet_base = int(getattr(player, "bullet_damage", base))
                        else:
                            bullet_base = int(META.get("base_dmg", BULLET_DAMAGE_ENEMY)) + int(META.get("dmg", 0))
                        dmg_per_tick, duration, max_stacks = dot_rounds_stats(dot_lvl, bullet_base)
                        apply_dot_rounds_stack(z, dmg_per_tick, duration, max_stacks)
                        spawn_dot_rounds_hit_vfx(game_state, cx, cy)
                if z.hp <= 0 and not getattr(z, "_death_processed", False):
                    z._death_processed = True  # Prevent duplicate death processing
                    # --- DEATH EXPLOSION (only when Explosive Rounds is owned) ---
                    cx, cy = z.rect.centerx, z.rect.centery
                    if int(META.get("explosive_rounds_level", 0)) > 0:
                        if getattr(z, "is_boss", False):
                            # Huge Red/Gold explosion for boss
                            game_state.fx.spawn_explosion(cx, cy, (255, 100, 50), count=150)
                        else:
                            # Standard enemy death (Green/Purple)
                            game_state.fx.spawn_explosion(cx, cy, z.color, count=25)

                    _bandit_death_notice(z, game_state)
                    # --- Shrapnel Shells: on enemy death, spawn shrapnel splashes ---
                    shrap_lvl = int(META.get("shrapnel_level", 0))
                    if (shrap_lvl > 0
                            and hp_lost > 0
                            and getattr(self, "source", "player") == "player"):
                        # chance scaling per level: 25%, 35%, 45% (cap at 80% if you later increase max_level)
                        base_chance = 0.25
                        per_level = 0.10
                        chance = min(0.80, base_chance + per_level * (shrap_lvl - 1))
                        if random.random() < chance:
                            count = random.randint(3, 4)
                            shrap_dmg = max(1, int(round(hp_lost * 0.4)))  # 40% of lethal HP damage
                            for _ in range(count):
                                ang = random.uniform(0.0, 2.0 * math.pi)
                                speed = BULLET_SPEED * 0.85  # a bit slower than main shot
                                vx = math.cos(ang) * speed
                                vy = math.sin(ang) * speed
                                sb = Bullet(
                                    cx, cy,
                                    vx, vy,
                                    max_dist=player.range * 0.5,  # shorter range splashes
                                    damage=shrap_dmg,
                                    source="player",
                                )
                                # shrapnel itself doesn’t pierce/ricochet (keeps it readable)
                                sb.pierce_left = 0
                                sb.ricochet_left = 0
                                sb.is_shrapnel = True  # optional, for future VFX
                                # queue into GameState; main loop will attach to bullets
                                if not hasattr(game_state, "pending_bullets"):
                                    game_state.pending_bullets = []
                                game_state.pending_bullets.append(sb)
                    # --- Explosive Rounds: on bullet kill, splash and chain ---
                    if getattr(self, "source", "player") == "player" and player is not None:
                        bullet_base = int(getattr(player, "bullet_damage", base))
                        trigger_explosive_rounds(player, game_state, enemies, (cx, cy), bullet_base=bullet_base)
                    if getattr(z, "is_boss", False) and getattr(z, "twin_id", None) is not None:
                        trigger_twin_enrage(z, enemies, game_state)
                    # --- Splinter: if not yet split, split on death instead of dropping loot now ---
                # --- Death-only handling: split, bandit refund, or normal loot/xp ---
                if z.hp <= 0:
                    # --- Splinter: if not yet split, split on death instead of dropping loot now ---
                    if getattr(z, "_can_split", False) and not getattr(z, "_split_done", False) and getattr(z, "type", "") == "splinter":
                        z._split_done = True
                        z._can_split = False
                        # 生成子体；父体不掉落金币（避免三倍通胀），XP也交给后续击杀子体获得
                        spawn_splinter_children(z, enemies, game_state, level_idx=0, wave_index=0)
                        # 从场上移除父体
                        if z in enemies:
                            enemies.remove(z)
                        self.alive = False
                        return
                    # ==== Coin Bandit：返还所有已偷 META 币 + 奖励 ====
                    elif getattr(z, "type", "") == "bandit":
                        stolen = int(getattr(z, "_stolen_total", 0))
                        bonus = (int(stolen * BANDIT_BONUS_RATE) + int(BANDIT_BONUS_FLAT)) if stolen > 0 else 0
                        refund = stolen + bonus
                        # Ensure death banner runs once (skips if wanted poster is active)
                        if not getattr(z, "_bandit_notice_done", False):
                            _bandit_death_notice(z, game_state)
                        if refund > 0:
                            game_state.spawn_spoils(cx, cy, refund)  # 掉一袋钱：玩家自己去捡
                        if META.get("wanted_active", False):
                            bounty = int(WANTED_POSTER_BOUNTY_BASE + stolen * 1.0)
                            META["spoils"] = int(META.get("spoils", 0)) + bounty
                            META["wanted_active"] = False
                            META["wanted_poster_waves"] = 0  # one poster only pays once; remaining waves void
                            game_state.wanted_wave_active = False
                            game_state.flash_banner(f"Bounty Claimed! +{bounty}", sec=1.0)
                            game_state.add_damage_text(z.rect.centerx, z.rect.centery, f"+{bounty}", crit=True,
                                                       kind="hp")
                        # bandit 的普通随机掉落就不要叠加了，直接走移除流程
                        if player:
                            base_xp = XP_PER_ENEMY_TYPE.get("bandit", XP_PLAYER_KILL)
                            player.add_xp(base_xp)
                            setattr(z, "_xp_awarded", True)
                        transfer_xp_to_neighbors(z, enemies)
                        if z in enemies:
                            enemies.remove(z)
                        # Bullet fate after a kill (pierce/ricochet handling matches normal deaths)
                        if getattr(self, "source", "player") == "player":
                            used_ricochet = False
                            if try_ricochet(cx, cy):
                                used_ricochet = True
                            remaining_pierce = int(getattr(self, "pierce_left", 0))
                            if remaining_pierce > 0:
                                self.pierce_left = remaining_pierce - 1
                                break
                            if used_ricochet:
                                break
                        self.alive = False
                        return
                    else:
                        # --- normal death (non-splinter or already split) ---
                        drop_n = roll_spoils_for_enemy(z)
                        drop_n += int(getattr(z, "spoils", 0))
                        if drop_n > 0:
                            game_state.spawn_spoils(cx, cy, drop_n)
                        # Bosses: guaranteed heal potions; regular enemies: random chance
                        if getattr(z, "is_boss", False):
                            for _ in range(BOSS_HEAL_POTIONS):
                                game_state.spawn_heal(cx, cy, HEAL_POTION_AMOUNT)
                        elif random.random() < HEAL_DROP_CHANCE_ENEMY:
                            game_state.spawn_heal(cx, cy, HEAL_POTION_AMOUNT)
                        if player:
                            base_xp = XP_PER_ENEMY_TYPE.get(getattr(z, "type", "basic"), XP_PLAYER_KILL)
                            bonus = max(0, z.z_level - 1) * XP_ZLEVEL_BONUS
                            extra_by_spoils = int(getattr(z, "spoils", 0)) * int(Z_SPOIL_XP_BONUS_PER)
                            if getattr(z, "is_elite", False):
                                base_xp = int(base_xp * 1.5)
                            if getattr(z, "is_boss", False):
                                base_xp = int(base_xp * 3.0)
                            player.add_xp(base_xp + bonus + extra_by_spoils)
                            setattr(z, "_xp_awarded", True)
                            if getattr(z, "is_boss", False):
                                trigger_twin_enrage(z, enemies, game_state)
                        transfer_xp_to_neighbors(z, enemies)
                        if z in enemies:
                            enemies.remove(z)
                        # --- Bullet fate after hitting this enemy (hit, not just kill) ---
                        if getattr(self, "source", "player") == "player":
                            used_ricochet = False
                            # 1) Ricochet Scope: try to bounce toward another enemy
                            #    Ricochet is independent of piercing.
                            if try_ricochet(cx, cy):
                                used_ricochet = True
                            # 2) Piercing Rounds: every *hit* on a enemy consumes one charge.
                            remaining_pierce = int(getattr(self, "pierce_left", 0))
                            if remaining_pierce > 0:
                                self.pierce_left = remaining_pierce - 1
                                # Bullet stays alive (continues in whatever direction it now has:
                                # original or bounced).
                                break
                            # 3) If we bounced but had no pierce_left, still let the bullet fly
                            #    along the bounced direction.
                            if used_ricochet:
                                break
                        # 4) No special effects left → bullet disappears after this hit.
                        self.alive = False
                        return
        # 2) obstacles
        for gp, ob in list(game_state.obstacles.items()):
            if r.colliderect(ob.rect):
                hit_x, hit_y = self.x, self.y
                if ob.type == "Lantern":
                    # 灯笼：像不可破坏墙一样挡子弹，但不掉血
                    if getattr(self, "source", "player") == "player" and try_ricochet(hit_x, hit_y):
                        # 成功弹射后，子弹沿新方向继续飞
                        break
                    # 没有弹射或弹射失败：子弹在灯笼处消失
                    self.alive = False
                    return
                elif ob.type == "Indestructible":
                    # Ricochet off walls if possible, otherwise die
                    if getattr(self, "source", "player") == "player" and try_ricochet(hit_x, hit_y):
                        break
                    self.alive = False
                    return
                elif ob.type == "Destructible":
                    ob.health = (ob.health or 0) - BULLET_DAMAGE_BLOCK
                    if ob.health <= 0:
                        cx, cy = ob.rect.centerx, ob.rect.centery
                        del game_state.obstacles[gp]
                        if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                            game_state.spawn_spoils(cx, cy, 1)
                        if player:
                            player.add_xp(XP_PLAYER_BLOCK)
                    # After damaging a block, we can also ricochet once
                    if getattr(self, "source", "player") == "player" and try_ricochet(hit_x, hit_y):
                        break
                    self.alive = False
                    return

    def draw(self, screen, cam_x, cam_y):
        src = getattr(self, "source", "player")
        if src == "turret":
            color = (0, 255, 255)  # cyan for all turret bullets
        else:
            color = (255, 255, 255)  # default player bullet color (top-down)
        pygame.draw.circle(
            screen,
            color,
            (int(self.x - cam_x), int(self.y - cam_y)),
            int(getattr(self, "r", BULLET_RADIUS)),
        )


class AutoTurret:
    """
    Simple auto-turret that orbits near the player and fires weak bullets
    at the nearest enemy within range.
    """

    def __init__(self, owner: "Player", offset: Tuple[float, float],
                 fire_interval: float = AUTO_TURRET_FIRE_INTERVAL,
                 damage: int = AUTO_TURRET_BASE_DAMAGE,
                 range_mult: float = AUTO_TURRET_RANGE_MULT):
        self.owner = owner
        self.offset_x, self.offset_y = offset
        self.fire_interval = float(fire_interval)
        self.damage = int(damage)
        self.range_mult = float(range_mult)
        self.angle = math.atan2(self.offset_y, self.offset_x) if (self.offset_x or self.offset_y) else 0.0
        self.orbit_radius = (self.offset_x ** 2 + self.offset_y ** 2) ** 0.5 or AUTO_TURRET_OFFSET_RADIUS
        # world position (px)
        cx, cy = owner.rect.center
        self.x = float(cx + self.offset_x)
        self.y = float(cy + self.offset_y)
        # desync a bit so multiple turrets don't fire in perfect sync
        self.cd = random.random() * self.fire_interval

    def _follow_owner(self, dt: float):
        # advance orbit angle
        self.angle += AUTO_TURRET_ORBIT_SPEED * dt
        cx, cy = self.owner.rect.center
        self.x = float(cx + math.cos(self.angle) * self.orbit_radius)
        self.y = float(cy + math.sin(self.angle) * self.orbit_radius)

    def update(self, dt: float, game_state: "GameState",
               enemies: List["Enemy"], bullets: List["Bullet"]):
        # Stick near the player
        self._follow_owner(dt)
        # Cooldown
        self.cd -= dt
        if self.cd > 0.0:
            return
        # Turret firing range based on player's range
        owner_range = clamp_player_range(getattr(self.owner, "range", PLAYER_RANGE_DEFAULT))
        max_range = clamp_player_range(owner_range * self.range_mult)
        max_r2 = max_range * max_range
        # Find nearest enemy in range
        best = None
        best_d2 = max_r2
        tx, ty = self.x, self.y
        for z in enemies:
            cx, cy = z.rect.centerx, z.rect.centery
            dx, dy = cx - tx, cy - ty
            d2 = dx * dx + dy * dy
            if d2 <= best_d2:
                best_d2 = d2
                best = (dx, dy)
        if best is None:
            # nothing to shoot at
            return
        dx, dy = best
        dist = (dx * dx + dy * dy) ** 0.5 or 1.0
        speed = BULLET_SPEED * 0.8  # a bit slower than player shots
        vx = (dx / dist) * speed
        vy = (dy / dist) * speed
        bullets.append(
            Bullet(
                tx, ty,
                vx, vy,
                max_dist=max_range,
                damage=self.damage,
                source="turret",
            )
        )
        self.cd = self.fire_interval


class StationaryTurret:
    """
    Stationary turret placed on the map.
    Fires weak bullets (same default damage as AutoTurret)
    at the nearest enemy within range every level.
    """

    def __init__(self, x: float, y: float,
                 fire_interval: float = AUTO_TURRET_FIRE_INTERVAL,
                 damage: int = AUTO_TURRET_BASE_DAMAGE,
                 range_mult: float = AUTO_TURRET_RANGE_MULT):
        self.x = float(x)
        self.y = float(y)
        self.fire_interval = float(fire_interval)
        self.damage = int(damage)
        self.range_mult = float(range_mult)
        # desync cooldown a bit so multiple turrets don't fire in perfect sync
        self.cd = random.random() * self.fire_interval

    def update(self, dt: float, game_state: "GameState",
               enemies: List["Enemy"], bullets: List["Bullet"]):
        # cooldown
        self.cd -= dt
        if self.cd > 0.0:
            return
        # use player's base range + range_mult so it scales with range upgrades
        base_range = clamp_player_range(META.get("base_range", PLAYER_RANGE_DEFAULT))
        player_range = compute_player_range(base_range, float(META.get("range_mult", 1.0)))
        total_range = clamp_player_range(player_range * self.range_mult)
        max_r2 = total_range * total_range
        # find nearest enemy in range around this turret
        best = None
        best_d2 = max_r2
        tx, ty = self.x, self.y
        for z in enemies:
            cx, cy = z.rect.centerx, z.rect.centery
            dx, dy = cx - tx, cy - ty
            d2 = dx * dx + dy * dy
            if d2 <= best_d2:
                best_d2 = d2
                best = (dx, dy)
        if best is None:
            return
        dx, dy = best
        dist = (dx * dx + dy * dy) ** 0.5 or 1.0
        speed = BULLET_SPEED * 0.8  # same feel as auto-turret bullets
        vx = (dx / dist) * speed
        vy = (dy / dist) * speed
        bullets.append(
            Bullet(
                tx, ty,
                vx, vy,
                max_dist=total_range,
                damage=self.damage,
            )
        )
        self.cd = self.fire_interval


class Spoil:
    """A coin-like pickup that pops up and bounces in place."""

    def __init__(self, x_px: float, y_px: float, value: int = 1):
        # ground/world position where the coin lives
        self.base_x = float(x_px)
        self.base_y = float(y_px)
        # vertical offset (screen-space "height")
        self.h = 0.0
        self.vh = float(COIN_POP_VY)  # vertical speed for bounce
        self.value = int(value)
        self.r = 6
        self.rect = pygame.Rect(0, 0, self.r * 2, self.r * 2)
        self._update_rect()

    def _update_rect(self):
        # draw/world position is base minus height
        cx = int(self.base_x)
        cy = int(self.base_y - self.h)
        self.rect.center = (cx, cy)

    def update(self, dt: float):
        # simple vertical bounce around base_y
        self.vh += COIN_GRAVITY * dt
        self.h += self.vh * dt
        if self.h >= 0.0:
            # hit "ground" -> bounce
            self.h = 0.0
            if abs(self.vh) > COIN_MIN_BOUNCE:
                self.vh = -self.vh * COIN_RESTITUTION
            else:
                self.vh = 0.0
        self._update_rect()


class HealPickup:
    """A small health potion pickup with the same bounce feel as coins."""

    def __init__(self, x_px: float, y_px: float, heal: int = HEAL_POTION_AMOUNT):
        self.base_x = float(x_px)
        self.base_y = float(y_px)
        self.h = 0.0
        self.vh = float(COIN_POP_VY)  # reuse coin bounce values
        self.heal = int(heal)
        self.r = 7
        self.rect = pygame.Rect(0, 0, self.r * 2, self.r * 2)
        self._update_rect()

    def _update_rect(self):
        self.rect.center = (int(self.base_x), int(self.base_y - self.h))

    def update(self, dt: float):
        self.vh += COIN_GRAVITY * dt
        self.h += self.vh * dt
        if self.h >= 0.0:
            self.h = 0.0
            if abs(self.vh) > COIN_MIN_BOUNCE:
                self.vh = -self.vh * COIN_RESTITUTION
            else:
                self.vh = 0.0
        self._update_rect()


class AcidPool:
    def __init__(self, x, y, r, dps, slow_frac, life):
        self.x, self.y, self.r = x, y, r
        self.dps, self.slow_frac = dps, slow_frac
        self.t = life  # remaining time

    def contains(self, px, py):
        return (px - self.x) ** 2 + (py - self.y) ** 2 <= self.r ** 2


class TelegraphCircle:
    def __init__(self, x, y, r, life, kind="acid", payload=None, color=(255, 60, 60)):
        self.x, self.y, self.r = x, y, r
        self.t = life
        self.kind = kind
        self.payload = payload or {}
        self.color = color


# ==================== NEW HIGH-FIDELITY COMET SYSTEM ====================

class NeuroParticle:
    """
    A 3D-aware particle for the comet system. 
    Tracks x,y (ground) and z (height) separately for proper Iso projection.
    """
    __slots__ = ('x', 'y', 'z', 'vx', 'vy', 'vz', 'life', 'life0', 'size', 'color', 'drag')

    def __init__(self, x, y, z, vx, vy, vz, life, size, color, drag=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)
        self.vx, self.vy, self.vz = float(vx), float(vy), float(vz)
        self.life, self.life0 = float(life), float(life)
        self.size = float(size)
        self.color = color
        self.drag = drag

    def update(self, dt: float) -> bool:
        self.life -= dt
        if self.life <= 0: return False
        
        # Physics
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.z += self.vz * dt
        
        # Gravity/Drag
        if self.z > 0: self.vz -= 980.0 * dt # Heavy gravity
        if self.z < 0: self.z = 0 # Floor bounce (optional, usually kill)
        
        if self.drag > 0:
            self.vx *= (1.0 - self.drag * dt)
            self.vy *= (1.0 - self.drag * dt)
            
        return True

    def draw(self, screen, camx, camy):
        # Calculate fade ratio
        prog = self.life / self.life0
        cur_size = int(self.size * prog)
        if cur_size < 1: return

        # ISO PROJECTION WITH Z-HEIGHT
        # Convert world pixels -> grid coords
        gx = self.x / CELL_SIZE
        gy = (self.y - INFO_BAR_HEIGHT) / CELL_SIZE
        # Project using the Z parameter
        sx, sy = iso_world_to_screen(gx, gy, self.z, camx, camy)

        # Draw Glow
        # We assume GlowCache is available from your effects module
        glow = GlowCache.get_glow_surf(cur_size, self.color)
        screen.blit(glow, (sx - cur_size, sy - cur_size), special_flags=pygame.BLEND_ADD)


class CometCorpse:
    """Replaces the old corpse with a digital dissolution effect."""
    def __init__(self, x, y, color, size):
        self.particles = []
        # Explode into digital cubes/pixels
        for _ in range(15):
            angle = random.uniform(0, 6.28)
            speed = random.uniform(50, 180)
            self.particles.append(NeuroParticle(
                x, y, 10, # Start slightly off ground
                math.cos(angle)*speed, math.sin(angle)*speed, random.uniform(100, 300),
                life=random.uniform(0.4, 0.7),
                size=random.uniform(4, 8),
                color=color
            ))

    def update(self, dt):
        self.particles = [p for p in self.particles if p.update(dt)]
        return len(self.particles) > 0

    def draw_iso(self, screen, camx, camy):
        for p in self.particles:
            p.draw(screen, camx, camy)


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
    candidates = [
        os.path.join(BASE_DIR, "assets", "Effect", filename),
        os.path.join(os.getcwd(), "assets", "Effect", filename),
        os.path.join(BASE_DIR, "assets", filename),  # legacy fallback
        os.path.join(os.getcwd(), "assets", filename),
    ]
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


class CometBlast:
    """
    The 'Q' Skill. 
    Visually represents a high-energy neural packet arcing through the air.
    """
    def __init__(self, target: tuple[float, float], start: tuple[float, float],
                 travel: float, on_impact=None, fx=None):
        self.tx, self.ty = target # Ground target
        self.sx, self.sy = start  # Ground start (virtual)
        self.travel = max(0.1, float(travel))
        self.elapsed = 0.0
        self.state = "flight"
        self._impact_cb = on_impact
        self.fx = fx
        
        # Flight Physics
        self.arc_height = 350.0 # Peak height in pixels
        
        # Visuals
        self.particles = [] # Tail particles
        self.impact_rings = [] # Expanding shockwaves on ground

    @staticmethod
    def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
        t = max(0.0, min(1.0, float(t)))
        return tuple(int(aa + (bb - aa) * t) for aa, bb in zip(a, b))
        
    def get_current_pos_3d(self):
        t = self.elapsed / self.travel
        # Linear Ground movement
        cx = self.sx + (self.tx - self.sx) * t
        cy = self.sy + (self.ty - self.sy) * t
        # Parabolic Z arc: sin(pi * t) * height
        cz = math.sin(t * math.pi) * self.arc_height
        return cx, cy, cz

    def update(self, dt):
        self.elapsed += dt
        
        if self.state == "flight":
            cx, cy, cz = self.get_current_pos_3d()
            
            # Spawn Trail (High density for smooth look)
            # We spawn multiple per frame to fill gaps
            steps = 2
            for i in range(steps):
                # Interpolate slightly back in time to fill gaps
                sub_t = dt * (i / steps)
                # Jitter
                jx = random.uniform(-5, 5)
                jy = random.uniform(-5, 5)
                jz = random.uniform(-5, 5)
                
                # Core (White/Cyan)
                self.particles.append(NeuroParticle(
                    cx + jx, cy + jy, cz + jz,
                    0, 0, 0, # Stationary relative to world
                    life=0.25, size=14, color=(200, 255, 255)
                ))
                # Outer Glow (Blue)
                self.particles.append(NeuroParticle(
                    cx + jx*2, cy + jy*2, cz + jz*2,
                    random.uniform(-20,20), random.uniform(-20,20), random.uniform(-20,20),
                    life=0.4, size=20, color=(0, 100, 255)
                ))

            if self.elapsed >= self.travel:
                self._do_impact()

        # Update particles
        self.particles = [p for p in self.particles if p.update(dt)]
        
        # Update shockwaves
        for r in self.impact_rings:
            r['r'] += r['speed'] * dt
            r['life'] -= dt
        self.impact_rings = [r for r in self.impact_rings if r['life'] > 0]

    def _do_impact(self):
        self.state = "impact"
        _play_comet_sfx()
        if self._impact_cb: self._impact_cb()
        
        # 1. Ground Shockwaves (Purely visual rings)
        self.impact_rings.append({'r': 10, 'speed': 600, 'life': 0.4, 'w': 6, 'col': (0, 255, 255)})
        self.impact_rings.append({'r': 10, 'speed': 300, 'life': 0.6, 'w': 3, 'col': (0, 100, 255)})
        
        # 2. Vertical Energy Pillar (Particles shooting UP)
        for _ in range(40):
            self.particles.append(NeuroParticle(
                self.tx, self.ty, 10,
                random.uniform(-150, 150), random.uniform(-150, 150), random.uniform(200, 800), # High Z velocity
                life=random.uniform(0.5, 1.0),
                size=random.uniform(6, 16),
                color=(150, 255, 255),
                drag=1.5
            ))
            
        # 3. Ground debris
        for _ in range(30):
            angle = random.uniform(0, 6.28)
            speed = random.uniform(200, 500)
            self.particles.append(NeuroParticle(
                self.tx, self.ty, 5,
                math.cos(angle)*speed, math.sin(angle)*speed, random.uniform(50, 200),
                life=random.uniform(0.3, 0.6),
                size=random.uniform(4, 10),
                color=(0, 200, 255)
            ))

    def done(self) -> bool:
        return self.state == "impact" and len(self.particles) == 0 and len(self.impact_rings) == 0

    def draw(self, screen, camx, camy):
        # 1. Draw Targeting Ring (Ground Level)
        # Pulse alpha
        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.01)
        
        # Only draw target ring if still flying (comet color seed-of-life)
        if self.state == "flight":
            comet_col = (80, 210, 255)
            t = pygame.time.get_ticks() * 0.001
            rot = t * 0.6
            orbit_r = BLAST_RADIUS * 0.5
            draw_iso_ground_ellipse(screen, self.tx, self.ty, BLAST_RADIUS, comet_col, 110 + 70 * pulse,
                                    camx, camy, fill=False, width=4)
            draw_iso_ground_ellipse(screen, self.tx, self.ty, orbit_r, comet_col, 90, camx, camy,
                                    fill=False, width=3)
            for i in range(6):
                ang = rot + math.tau * i / 6.0
                ox = self.tx + math.cos(ang) * orbit_r
                oy = self.ty + math.sin(ang) * orbit_r
                draw_iso_ground_ellipse(screen, ox, oy, orbit_r, comet_col, 90, camx, camy, fill=False, width=3)

        # 2. Draw Impact Shockwaves (Ground Level)
        for r in self.impact_rings:
            alpha = int(255 * (r['life'] / 0.5))
            alpha = max(0, min(255, alpha))
            seed_col = self._lerp((70, 210, 255), (255, 120, 60), 1.0)
            col = r.get('col', seed_col)
            if not isinstance(col, (tuple, list)) or len(col) < 3:
                col = seed_col
            col = tuple(max(0, min(255, int(c))) for c in col[:3])
            draw_iso_ground_ellipse(screen, self.tx, self.ty, r.get('r', BLAST_RADIUS),
                                    col, alpha, camx, camy, fill=False, width=int(max(1, r.get('w', 3))))

        # 3. Draw Comet Head (If flying)
        if self.state == "flight":
            cx, cy, cz = self.get_current_pos_3d()
            # Draw Head Glow
            head_size = 40
            gx = cx / CELL_SIZE
            gy = (cy - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(gx, gy, cz, camx, camy)
            
            glow = GlowCache.get_glow_surf(head_size, (200, 255, 255))
            screen.blit(glow, (sx - head_size, sy - head_size), special_flags=pygame.BLEND_ADD)

        # 4. Draw Particles (Trails, Explosion Debris)
        # Z-sorting particles makes it look better, but standard painter's algo is fine for add-blend
        for p in self.particles:
            p.draw(screen, camx, camy)

class AegisPulseRing:
    """Lightweight visual token for recent Aegis Pulse waves."""
    def __init__(self, x: float, y: float, r: float, delay: float, expand_time: float,
                 fade_time: float, damage: int):
        self.x = float(x)
        self.y = float(y)
        self.r = float(r)
        self.delay = float(delay)
        self.expand_time = float(expand_time)
        self.fade_time = float(fade_time)
        self.damage = int(damage)
        self.hit_done = False
        # store remaining life; total life includes delay so we can reuse the existing timer logic
        self.t = float(delay + expand_time + fade_time)
        self.life0 = float(self.t)
        
    @property
    def age(self) -> float:
        return float(self.life0 - self.t)


class EnemyShot:
    def __init__(self, x: float, y: float, vx: float, vy: float, dmg: int, max_dist: float = MAX_FIRE_RANGE, radius=4,
                 color=(255, 120, 50)):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.dmg = int(dmg)
        self.traveled = 0.0
        self.r = int(radius)
        self.max_dist = max_dist
        self.color = tuple(color)
        self.alive = True

    def update(self, dt: float, player: 'Player', game_state: 'GameState'):
        if not self.alive:
            return
        # 运动
        nx = self.x + self.vx * dt
        ny = self.y + self.vy * dt
        self.traveled += ((nx - self.x) ** 2 + (ny - self.y) ** 2) ** 0.5
        self.x, self.y = nx, ny
        if self.traveled >= self.max_dist:
            self.alive = False
            return
        # Hell-only: scale enemy-shot radius from its damage
        if getattr(game_state, "biome_active", None) == "Scorched Hell":
            self.r = enemy_shot_radius_for_damage(int(self.dmg))
        else:
            # keep whatever radius it was created with (default small)
            self.r = int(getattr(self, "r", BULLET_RADIUS))
        # 本帧碰撞 AABB（优先用自身半径）
        _rr = int(getattr(self, "r", BULLET_RADIUS))
        r = pygame.Rect(int(self.x - _rr), int(self.y - _rr), _rr * 2, _rr * 2)
        # 1) 先撞障碍（会阻挡子弹）
        for gp, ob in list(game_state.obstacles.items()):
            if r.colliderect(ob.rect):
                # 伤害数值（主方块与可破坏块统一，若需要可单独给主方块一个常量）
                dmg_block = int(globals().get("ENEMY_SHOT_DAMAGE_BLOCK", BULLET_DAMAGE_BLOCK))
                # 主方块：现在可受伤
                if getattr(ob, 'is_main_block', False):
                    # 主方块有 health
                    ob.health = (ob.health or 0) - dmg_block
                    if ob.health <= 0:
                        # 移除主方块（下方主碎片若有，将自然暴露）
                        del game_state.obstacles[gp]
                    self.alive = False
                    return
                # 不可破坏：只阻挡不掉血
                if getattr(ob, "type", None) == "Indestructible":
                    self.alive = False
                    return
                # 可破坏：扣血→可能打碎
                if getattr(ob, "type", None) == "Destructible":
                    ob.health = (ob.health or 0) - dmg_block
                    if ob.health <= 0:
                        del game_state.obstacles[gp]
                    self.alive = False
                    return
                # EnemyShot.update(...) 内，判玩家前插入：
                for lan in list(getattr(game_state, "fog_lanterns", [])):
                    if not getattr(lan, "alive", True):
                        continue
                    gx, gy = lan.grid_pos
                    cx = int(gx * CELL_SIZE + CELL_SIZE * 0.5)
                    cy = int(gy * CELL_SIZE + CELL_SIZE * 0.5 + INFO_BAR_HEIGHT)
                    if r.collidepoint(cx, cy):
                        lan.hp = max(0, getattr(lan, "hp", 1) - self.dmg)
                        if lan.hp == 0:
                            lan.alive = False
                        self.alive = False
                        return
                # 其他未知类型：默认阻挡
                self.alive = False
                return
        # 2) 再判玩家
        if r.colliderect(player.rect):
            if getattr(player, "hit_cd", 0.0) <= 0.0:
                mult = getattr(game_state, "biome_enemy_contact_mult", 1.0)
                dmg = int(round(self.dmg * max(1.0, mult)))
                game_state.damage_player(player, dmg, kind="hp_enemy")
                player.hit_cd = float(PLAYER_HIT_COOLDOWN)
            self.alive = False

    def draw_topdown(self, screen, camx, camy):
        pygame.draw.circle(screen, self.color,
                           (int(self.x - camx), int(self.y - camy)), self.r)

    def draw_iso(self, screen, camx, camy):
        wx = self.x / CELL_SIZE
        wy = (self.y - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0.0, camx, camy)
        pygame.draw.circle(screen, self.color, (int(sx), int(sy)), self.r)


class MistShot(EnemyShot):
    """Mistweaver 专用弹幕：自带半径/颜色，不影响普通 EnemyShot。"""

    def __init__(self, x, y, vx, vy, damage, radius=10, color=None):
        super().__init__(x, y, vx, vy, damage)
        self.r = int(radius)
        self.color = color or HAZARD_STYLES["mist"]["ring"]


class DamageText:
    """世界坐标下的飘字（x,y 为像素，含 INFO_BAR_HEIGHT），按时间上浮并淡出。"""

    def __init__(self, x_px: float, y_px: float, amount: int,
                 crit: bool = False, kind: str = "hp"):
        self.x = float(x_px)
        self.y = float(y_px)
        if isinstance(amount, (int, float)):
            self.amount = int(amount)
        else:
            self.amount = str(amount)
        self.crit = bool(crit)
        self.kind = kind  # "hp"|"shield"
        self.t = 0.0
        self.ttl = float(DMG_TEXT_TTL)

    def alive(self) -> bool:
        return self.t < self.ttl

    def step(self, dt: float):
        self.t += dt

    def screen_offset_y(self) -> float:
        # 线性上升
        return -DMG_TEXT_RISE * (self.t / self.ttl)

    def alpha(self) -> int:
        # 后段逐渐淡出
        p = self.t / self.ttl
        if p <= (1.0 - DMG_TEXT_FADE):
            return 255
        tail = (p - (1.0 - DMG_TEXT_FADE)) / max(1e-4, DMG_TEXT_FADE)
        return max(0, int(255 * (1.0 - tail)))


# ==================== 算法函数 ====================
def sign(v): return 1 if v > 0 else (-1 if v < 0 else 0)


# simple movement helper: use iso equalization only when using ISO view
def chase_step(ux: float, uy: float, speed: float):
    return iso_equalized_step(ux, uy, speed) if USE_ISO else (ux * speed, uy * speed)


def heuristic(a, b): return abs(a[0] - b[0]) + abs(a[1] - b[1])


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
    # ← cap final move speed
    z.speed = min(ENEMY_SPEED_MAX, max(1, z.speed))
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
    # --- 生命值 = max(基础血, 玩家DPS × 4) ---
    dps = float(player_dps) if player_dps is not None else float(compute_player_dps(None))
    target_hp = int(math.ceil(BANDIT_BASE_HP + dps * 3.5))
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


def trigger_twin_enrage(dead_boss, enemies, game_state):
    """If a bonded twin dies, power up the partner exactly once."""
    # locate partner
    partner = None
    ref = getattr(dead_boss, "_twin_partner_ref", None)
    if callable(ref):
        partner = ref()
    elif ref is not None:
        partner = ref
    if partner is None:  # fall back: search by twin_id
        tid = getattr(dead_boss, "twin_id", None)
        if tid is not None:
            for z in enemies:
                if getattr(z, "is_boss", False) and getattr(z, "twin_id", None) == tid and z is not dead_boss:
                    partner = z
                    break
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
    # floating label (now safe—accepts strings)
    game_state.add_damage_text(partner.rect.centerx,
                               partner.rect.top - 10,
                               "ENRAGE!",  # string OK after step #1/#2
                               crit=True, kind="hp")


def a_star_search(graph: Graph, start: Tuple[int, int], goal: Tuple[int, int],
                  obstacles: Dict[Tuple[int, int], Obstacle]):
    frontier = PriorityQueue()
    frontier.put((0, start))
    came_from = {start: None}
    cost_so_far = {start: 0}
    while not frontier.empty():
        _, current = frontier.get()
        if current == goal: break
        for neighbor in graph.neighbors(current):
            new_cost = cost_so_far[current] + graph.cost(current, neighbor)
            if neighbor in obstacles:
                obstacle = obstacles[neighbor]
                if obstacle.type == "Indestructible":
                    continue
                elif obstacle.type == "Destructible":
                    k_factor = (math.ceil(obstacle.health / ENEMY_ATTACK)) * 0.1
                    new_cost = cost_so_far[current] + 1 + k_factor
            if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                cost_so_far[neighbor] = new_cost
                priority = new_cost + heuristic(goal, neighbor)
                frontier.put((priority, neighbor))
                # came_from[current] = current if current not in came_from else came_from[current]
                came_from[neighbor] = current
    return came_from, cost_so_far


def is_not_edge(pos, grid_size):
    x, y = pos
    return 1 <= x < grid_size - 1 and 1 <= y < grid_size - 1


def get_level_config(level: int) -> dict:
    if level < len(LEVELS):
        return LEVELS[level]
    return {
        "obstacle_count": 20 + level,
        "item_count": 5,
        "enemy_count": min(5, 1 + level // 3),
        "block_hp": int(10 * 1.2 ** (level - len(LEVELS) + 1)),
        "enemy_types": ["basic", "strong", "fire"][level % 3:],
    }


def reconstruct_path(came_from: Dict, start: Tuple[int, int], goal: Tuple[int, int]) -> List[Tuple[int, int]]:
    if goal not in came_from: return [start]
    path = []
    current = goal
    while current != start:
        path.append(current)
        current = came_from[current]
    path.append(start)
    path.reverse()
    return path


# ==================== 游戏初始化函数 ====================
def generate_game_entities(grid_size: int, obstacle_count: int, item_count: int, enemy_count: int, main_block_hp: int,
                           level_idx: int = 0):
    """
    Generate entities with map-fill: obstacle clusters, ample items, and non-blocking decorations.
    Main block removed — all items are collectible when touched.
    """
    all_positions = [(x, y) for x in range(grid_size) for y in range(grid_size)]
    corners = [(0, 0), (0, grid_size - 1), (grid_size - 1, 0), (grid_size - 1, grid_size - 1)]
    forbidden = set(corners)

    def pick_valid_positions(min_distance: int, count: int):
        empty = [p for p in all_positions if p not in forbidden]
        while True:
            picks = random.sample(empty, count + 1)
            player_pos, enemies = picks[0], picks[1:]
            if all(abs(player_pos[0] - z[0]) + abs(player_pos[1] - z[1]) >= min_distance for z in enemies):
                return player_pos, enemies

    # center spawn if possible
    center_pos = (grid_size // 2, grid_size // 2)
    if center_pos not in forbidden:
        player_pos = center_pos
        far_candidates = [p for p in all_positions if
                          p not in forbidden and (abs(p[0] - center_pos[0]) + abs(p[1] - center_pos[1]) >= 6)]
        enemy_pos_list = random.sample(far_candidates, enemy_count)
    else:
        player_pos, enemy_pos_list = pick_valid_positions(min_distance=5, count=enemy_count)
    forbidden |= {player_pos}
    forbidden |= set(enemy_pos_list)
    # Keep a small ring around the player completely free of obstacles
    SAFE_RADIUS = 1  # 1 tile in each direction = 3x3 area
    px, py = player_pos
    for dx in range(-SAFE_RADIUS, SAFE_RADIUS + 1):
        for dy in range(-SAFE_RADIUS, SAFE_RADIUS + 1):
            nx, ny = px + dx, py + dy
            if 0 <= nx < grid_size and 0 <= ny < grid_size:
                forbidden.add((nx, ny))
    # --- obstacle fill with clusters (NO pre-placed main block now) ---
    obstacles: Dict[Tuple[int, int], Obstacle] = {}
    area = grid_size * grid_size
    target_obstacles = max(obstacle_count, int(area * OBSTACLE_DENSITY))
    rest_needed = target_obstacles
    base_candidates = [p for p in all_positions if p not in forbidden]
    random.shuffle(base_candidates)
    placed = 0
    # cluster seeds
    cluster_seeds = base_candidates[:max(1, rest_needed // 6)]
    for seed in cluster_seeds:
        if placed >= rest_needed: break
        cluster_size = random.randint(3, 6)
        wave = [seed]
        visited = set()
        while wave and placed < rest_needed and len(visited) < cluster_size:
            cur = wave.pop()
            if cur in visited or cur in obstacles or cur in forbidden: continue
            visited.add(cur)
            typ = "Indestructible" if random.random() < 0.65 else "Destructible"
            hp = OBSTACLE_HEALTH if typ == "Destructible" else None
            obstacles[cur] = Obstacle(cur[0], cur[1], typ, health=hp)
            placed += 1
            x, y = cur
            neigh = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
            random.shuffle(neigh)
            for nb in neigh:
                if 0 <= nb[0] < grid_size and 0 <= nb[1] < grid_size and nb not in visited:
                    wave.append(nb)
    # if still short, scatter
    if placed < rest_needed:
        more = [p for p in base_candidates if p not in obstacles]
        random.shuffle(more)
        for pos in more[:(rest_needed - placed)]:
            typ = "Indestructible" if random.random() < 0.5 else "Destructible"
            hp = OBSTACLE_HEALTH if typ == "Destructible" else None
            obstacles[pos] = Obstacle(pos[0], pos[1], typ, health=hp)
    forbidden |= set(obstacles.keys())
    # --- items (all are normal) ---
    item_target = random.randint(9, 19)
    item_candidates = [p for p in all_positions if p not in forbidden]
    items = [Item(x, y, is_main=False) for (x, y) in
             random.sample(item_candidates, min(len(item_candidates), item_target))]
    # --- decorations ---
    decor_target = int(area * DECOR_DENSITY)
    decor_candidates = [p for p in all_positions if p not in forbidden]
    random.shuffle(decor_candidates)
    decorations = decor_candidates[:decor_target]
    # keep return shape the same: last “main_item_list” is now empty list
    return obstacles, items, player_pos, enemy_pos_list, [], decorations


def build_graph(grid_size: int, obstacles: Dict[Tuple[int, int], Obstacle]) -> Graph:
    graph = Graph()
    for x in range(grid_size):
        for y in range(grid_size):
            current_pos = (x, y)
            if current_pos in obstacles and obstacles[current_pos].type == "Indestructible": continue
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                neighbor_pos = (x + dx, y + dy)
                if not (0 <= neighbor_pos[0] < grid_size and 0 <= neighbor_pos[1] < grid_size): continue
                if neighbor_pos in obstacles and obstacles[neighbor_pos].type == "Indestructible": continue
                weight = 1
                if neighbor_pos in obstacles and obstacles[neighbor_pos].type == "Destructible":
                    weight = 10
                graph.add_edge(current_pos, neighbor_pos, weight)
    return graph


# --- Simple grid Dijkstra from goal -> all cells (shared flow field) ---
def build_flow_field(grid_size, obstacles, goal_xy, pad=0):
    INF = 10 ** 9
    goal_x, goal_y = goal_xy
    # Precompute a padded "blocked" set (Indestructible + MainBlock only)
    hard = {(gx, gy) for (gx, gy), ob in obstacles.items()
            if getattr(ob, "type", "") in ("Indestructible", "MainBlock")}
    blocked = set(hard)
    if pad > 0:
        for gx, gy in list(hard):
            for dx in range(-pad, pad + 1):
                for dy in range(-pad, pad + 1):
                    nx, ny = gx + dx, gy + dy
                    if 0 <= nx < grid_size and 0 <= ny < grid_size:
                        blocked.add((nx, ny))

    def cell_cost(x, y):
        if (x, y) in blocked:
            return INF
        ob = obstacles.get((x, y))
        # Destructible: passable but slightly expensive, keeps paths from grazing edges
        if ob and getattr(ob, "type", "") == "Destructible":
            return 4
        return 1

    # Dijkstra from goal (your existing logic, but skip blocked cells)
    dist = [[INF] * grid_size for _ in range(grid_size)]
    next_step = [[None] * grid_size for _ in range(grid_size)]
    pq = []
    if 0 <= goal_x < grid_size and 0 <= goal_y < grid_size and cell_cost(goal_x, goal_y) < INF:
        dist[goal_x][goal_y] = 0
        heapq.heappush(pq, (0, goal_x, goal_y))
    while pq:
        d, x, y = heapq.heappop(pq)
        if d != dist[x][y]:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < grid_size and 0 <= ny < grid_size):
                continue
            c = cell_cost(nx, ny)
            if c >= INF:
                continue
            nd = d + c
            if nd < dist[nx][ny]:
                dist[nx][ny] = nd
                next_step[nx][ny] = (x, y)
                heapq.heappush(pq, (nd, nx, ny))
    return dist, next_step


# ==================== 新增游戏状态类 ====================
class SpatialHash:
    def __init__(self, cell=64):
        self.cell = int(cell)
        self.buckets = {}

    def _key(self, x, y):
        return (int(x) // self.cell, int(y) // self.cell)

    def rebuild(self, enemies):
        self.buckets.clear()
        for z in enemies:
            k = self._key(z.rect.centerx, z.rect.centery)
            self.buckets.setdefault(k, []).append(z)

    def query_circle(self, x, y, r):
        cx, cy = self._key(x, y)
        out = []
        rr = r + max(16, CELL_SIZE // 2)
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for z in self.buckets.get((gx, gy), []):
                    dx = z.rect.centerx - x
                    dy = z.rect.centery - y
                    if dx * dx + dy * dy <= rr * rr:
                        out.append(z)
        return out


def crush_blocks_in_rect(sweep_rect: pygame.Rect, game_state) -> int:
    """Remove ANY obstacle cell whose rect intersects sweep_rect. Return removed count."""
    removed = 0
    if not hasattr(game_state, "obstacles") or not game_state.obstacles:
        return 0
    # 遍历拷贝，安全删除
    for gp, ob in list(game_state.obstacles.items()):
        if sweep_rect.colliderect(ob.rect):
            # 无视类型，直接移除（包含 Indestructible / MainBlock）
            # 如需震屏/音效/粒子，在这里加
            del game_state.obstacles[gp]
            if hasattr(game_state, "mark_nav_dirty"): game_state.mark_nav_dirty()
            removed += 1
    return removed


class TornadoEntity:
    def __init__(self, x, y, r=HURRICANE_START_RADIUS):
        self.x = float(x)
        self.y = float(y)
        self.r = float(r)
        self.t = random.uniform(0, 100) # Animation phase
        self.spin_dir = random.choice([-1.0, 1.0]) # Random rotation direction
        ang = random.uniform(0, math.tau)
        self.move_speed = random.uniform(16.0, 40.0)  # slight speed boost for drifting
        self.vx = math.cos(ang) * self.move_speed
        self.vy = math.sin(ang) * self.move_speed
        self._bound_margin = HURRICANE_MAX_RADIUS * 1.2

        # Initialize Wind Particles (Debris + Wind Streaks)
        self._base_particles = 35
        self._extra_particles = 30  # only affects visuals (outer wind gets busier as it grows)
        self.particles = [self._make_particle() for _ in range(self._base_particles)]
        # Swoosh arcs that randomly appear in the outer influence ring (purely visual)
        self._ring_swooshes = [self._make_swoosh() for _ in range(9)]

    def _make_particle(self):
        return {
            "type": "wind" if random.random() < 0.7 else "debris",
            "ang": random.uniform(0, math.tau),
            "h": random.uniform(0.05, 1.2), # Height ratio
            "dist": random.uniform(0.6, 1.6), # Distance from funnel center (1.0+ sits in the influence ring)
            "speed": random.uniform(3.0, 6.0),
            "len": random.uniform(0.15, 0.45),
            "color": random.choice(WIND_PARTICLE_COLORS)
        }

    def _make_swoosh(self):
        swoosh_colors = [
            (200, 240, 255),  # white
            (160, 210, 230),  # grey-blue
            (120, 210, 255),  # cyan
        ]
        return {
            "ang": random.uniform(0, math.tau),
            "rad_ratio": random.uniform(0.3, 1.05),   # placement anywhere inside the influence ring
            "len_ratio": random.uniform(0.12, 0.20),  # shorter max length (half previous max)
            "thick": random.randint(2, 4),
            "alpha": random.randint(140, 210),
            "color": random.choice(swoosh_colors),
            "t": 0.0,
            "ttl": random.uniform(0.7, 1.3),
        }

    def update(self, dt):
        # Grow to max radius
        self.r = min(HURRICANE_MAX_RADIUS, self.r + HURRICANE_GROWTH_RATE * dt)
        self.t += dt * 5.0 # Animation speed

        # Cosmetics only: scale wind particle count with the influence ring size
        target = int(self._base_particles + self._extra_particles * min(1.0, self.r / HURRICANE_MAX_RADIUS))
        while len(self.particles) < target:
            self.particles.append(self._make_particle())
        if len(self.particles) > target:
            self.particles = self.particles[:target]

        # Slow drift across the map; bounce off bounds to stay inside
        map_w = GRID_SIZE * CELL_SIZE
        map_h = GRID_SIZE * CELL_SIZE
        min_x = self._bound_margin
        max_x = map_w - self._bound_margin
        min_y = INFO_BAR_HEIGHT + self._bound_margin
        max_y = INFO_BAR_HEIGHT + map_h - self._bound_margin
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.x < min_x or self.x > max_x:
            self.x = max(min_x, min(self.x, max_x))
            self.vx *= -1
        if self.y < min_y or self.y > max_y:
            self.y = max(min_y, min(self.y, max_y))
            self.vy *= -1

        # Update particles (orbiting)
        vis_dir = -self.spin_dir  # visuals swirl opposite if physics feels reversed
        spin_growth = min(1.0, self.r / HURRICANE_MAX_RADIUS)
        vis_spin_scale = 0.6 + 0.9 * spin_growth  # start slower, speed up as it grows
        for p in self.particles:
            # Physics: Spin faster near the bottom (conservation of angular momentum feel)
            spin = p['speed'] * (1.8 - min(1.0, p['h']))
            p['ang'] += spin * dt * vis_dir * vis_spin_scale

        # Update ring swooshes (outer influence band streaks)
        for s in list(self._ring_swooshes):
            s["t"] += dt
            if s["t"] >= s["ttl"]:
                self._ring_swooshes.remove(s)
        while len(self._ring_swooshes) < 9:
            self._ring_swooshes.append(self._make_swoosh())

    def apply_vortex_physics(self, ent, dt, resist_scale=1.0):
        """
        Calculates spiral flow: Objects orbit FAST while slowly drifting inward.
        Returns tuple (dx, dy) to be applied to the entity.
        """
        # Vector from entity to tornado center
        ecx, ecy = ent.rect.centerx, ent.rect.centery
        dx = self.x - ecx
        dy = self.y - ecy
        dist = math.hypot(dx, dy)
        
        # Range check (Influence radius)
        effect_radius = self.r * HURRICANE_RANGE_MULT
        if dist <= 10.0 or dist > effect_radius:
            return 0.0, 0.0

        # Normalized direction vectors
        nx, ny = dx / dist, dy / dist   # Normal (Toward center)
        tx, ty = -ny, nx                # Tangent (Orbit direction)
        
        # Flip tangent if tornado spins clockwise
        if self.spin_dir < 0:
            tx, ty = -tx, -ty

        # --- Flow Logic ---
        # 1. Suction Strength (increases as you get closer, but drops at the very eye)
        suction_mult = min(1.0, dist / 60.0) 
        radial_force = HURRICANE_PULL_STRENGTH * suction_mult
        
        # 2. Orbital Strength (stronger near center)
        rot_mult = 1.0 + (1.0 - min(1.0, dist / effect_radius)) * 2.0
        tangential_force = HURRICANE_VORTEX_POWER * rot_mult

        # Combine forces
        vx = (nx * radial_force) + (tx * tangential_force)
        vy = (ny * radial_force) + (ty * tangential_force)

        # Apply ISO perspective flattening to Y axis (2.0 ratio)
        vy *= 0.5 

        return vx * dt * resist_scale, vy * dt * resist_scale

    def draw(self, screen, camx, camy):
        """Draws the Neuro-styled tornado with glitch effects and wind streaks."""
        # Base screen coordinates
        cx, cy = iso_world_to_screen(self.x / CELL_SIZE, (self.y - INFO_BAR_HEIGHT) / CELL_SIZE, 0, camx, camy)

        vis_dir = -self.spin_dir  # visuals follow the perceived rotation direction
        spin_growth = min(1.0, self.r / HURRICANE_MAX_RADIUS)
        vis_spin_scale = 0.6 + 0.9 * spin_growth
        base_w = self.r * 1.6

        # Influence ring: ground glow + cyan rim to highlight the affected zone
        effect_radius = self.r * HURRICANE_RANGE_MULT
        rx_zone, ry_zone = iso_circle_radii_screen(effect_radius)
        zone = pygame.Surface((rx_zone * 2, ry_zone * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(zone, (40, 60, 80, 50), zone.get_rect())  # subtle ground fill
        pygame.draw.ellipse(zone, (120, 220, 255, 110), zone.get_rect(), width=3)  # cyan rim

        # Rotating ground streaks follow the hurricane spin direction
        streaks = 8
        for i in range(streaks):
            ang = self.t * 0.6 * vis_spin_scale * vis_dir + i * (math.tau / streaks)
            px = rx_zone + math.cos(ang) * rx_zone * 0.82
            py = ry_zone + math.sin(ang) * ry_zone * 0.82
            tx = -math.sin(ang) * 10 * vis_dir
            ty = math.cos(ang) * 6 * vis_dir
            pygame.draw.line(zone, (140, 220, 255, 140), (px - tx, py - ty), (px + tx, py + ty), 2)

        # Brighter swoosh arcs randomly scattered in the influence ring
        for s in self._ring_swooshes:
            fade = max(0.0, 1.0 - (s["t"] / max(0.001, s["ttl"])))
            if fade <= 0:
                continue
            arc_ang = s["ang"] + math.pi + self.t * 0.35 * vis_dir  # reversed arc direction
            r_ratio = s["rad_ratio"]
            arc_len = rx_zone * s["len_ratio"]
            x0 = rx_zone + math.cos(arc_ang) * rx_zone * r_ratio
            y0 = ry_zone + math.sin(arc_ang) * ry_zone * r_ratio
            tx = -math.sin(arc_ang) * arc_len * vis_dir
            ty = math.cos(arc_ang) * arc_len * 0.55 * vis_dir

            # Quadratic bezier-like curve, tapered ends (thin) with thicker mid
            start = (x0 - tx * 0.5, y0 - ty * 0.5)
            end = (x0 + tx * 0.5, y0 + ty * 0.5)
            curve_mag = arc_len * 0.25
            cx_mid = x0 + (-ty) * 0.2 + math.cos(arc_ang) * 4
            cy_mid = y0 + (tx) * 0.2 + math.sin(arc_ang) * 2

            steps = 12
            col = s["color"]
            alpha = int(s["alpha"] * fade)
            for j in range(steps):
                t = j / (steps - 1)
                # Quadratic interpolation
                ax = (1 - t) * start[0] + t * cx_mid
                ay = (1 - t) * start[1] + t * cy_mid
                bx = (1 - t) * cx_mid + t * end[0]
                by = (1 - t) * cy_mid + t * end[1]
                px = (1 - t) * ax + t * bx
                py = (1 - t) * ay + t * by

                # Thickness taper: thin at ends, thickest at center
                taper = 1.0 - abs(t * 2 - 1)
                radius = max(1, int(s["thick"] * (0.5 + 0.8 * taper)))
                pygame.draw.circle(zone, (*col, alpha), (px, py), radius)

        screen.blit(zone, (cx - rx_zone, cy - ry_zone))

        # --- 1. Draw Funnel Layers (Bottom to Top) ---
        for i in range(TORNADO_LAYER_COUNT):
            ratio = i / float(TORNADO_LAYER_COUNT) # 0.0 (bottom) -> 1.0 (top)

            # Non-linear width: Wide top, narrow base
            width = base_w * (0.25 + 0.8 * (ratio ** 1.8))
            
            # "Neuro" Glitch Effect: Occasional horizontal offset
            glitch_x = 0
            if random.random() < 0.05: 
                glitch_x = random.randint(-4, 4)

            # Wobble animation (Sine wave that moves up)
            wobble = math.sin(self.t + ratio * 4.0) * (15 * ratio)
            
            draw_x = cx + wobble + glitch_x
            draw_y = cy - (ratio * TORNADO_FUNNEL_HEIGHT)
            
            # Iso projection for ellipse
            rx, ry = iso_circle_radii_screen(width * 0.5)
            
            # Color Gradient: Dark Blue (Edge) -> Light Blue (Center) -> Alpha Fade
            alpha = 170 if i < TORNADO_LAYER_COUNT - 1 else 90
            color = (
                int(TORNADO_EDGE_COLOR[0] + (TORNADO_CORE_COLOR[0] - TORNADO_EDGE_COLOR[0]) * ratio),
                int(TORNADO_EDGE_COLOR[1] + (TORNADO_CORE_COLOR[1] - TORNADO_EDGE_COLOR[1]) * ratio),
                int(TORNADO_EDGE_COLOR[2] + (TORNADO_CORE_COLOR[2] - TORNADO_EDGE_COLOR[2]) * ratio),
            )

            s = pygame.Surface((rx*2, ry*2), pygame.SRCALPHA)
            pygame.draw.ellipse(s, (*color, alpha), s.get_rect())

            # Add a cyan rim to highlight each slice and fill space between layers
            pygame.draw.ellipse(s, (120, 220, 255, int(alpha * 0.9)), s.get_rect(), width=2)

            screen.blit(s, (draw_x - rx, draw_y - ry))

        # Cyan contour rings to emphasize internal layers
        for r_ratio in (0.2, 0.45, 0.7, 0.9):
            width = base_w * (0.25 + 0.75 * (r_ratio ** 1.5))
            rx, ry = iso_circle_radii_screen(width * 0.5)
            y = cy - (r_ratio * TORNADO_FUNNEL_HEIGHT)
            pulse = 0.7 + 0.3 * math.sin(self.t * 0.8 + r_ratio * 4.0)
            pygame.draw.ellipse(
                screen,
                (140, 230, 255, int(80 * pulse)),
                pygame.Rect(cx - rx, y - ry, rx * 2, ry * 2),
                width=2,
            )

        # --- 2. Draw Wind Particles (Debris & Streaks) ---
        for p in self.particles:
            # Calculate particle screen position
            h_px = p['h'] * TORNADO_FUNNEL_HEIGHT
            # Width at this height
            w_at_h = base_w * (0.25 + 0.8 * (p['h'] ** 1.8)) * p['dist']
            
            # Orbit math
            px_off = math.cos(p['ang']) * (w_at_h * 0.5)
            py_off = math.sin(p['ang']) * (w_at_h * 0.25) # Flattened Y
            
            wobble_at_h = math.sin(self.t + p['h'] * 4.0) * (15 * p['h'])
            
            px = cx + wobble_at_h + px_off
            py = cy - h_px + py_off
            
            # Z-Sort: Darker/smaller if "behind" the tornado
            is_behind = math.sin(p['ang']) < 0

            if p['type'] == 'wind':
                # Draw "Wind Streaks" (Curved, multi-point swoosh)
                size_scale = 1.0 + 0.6 * min(1.0, self.r / HURRICANE_MAX_RADIUS)
                length = 12 * size_scale * (0.6 + 0.4 * p.get("len", 0.25))
                # Calculate tail based on rotation direction
                dir_ang = p['ang'] + math.pi/2 * vis_dir
                tail_x = px - math.cos(dir_ang) * length
                tail_y = py - math.sin(dir_ang) * (length * 0.5)
                mid_x = (px + tail_x) * 0.5
                mid_y = (py + tail_y) * 0.5
                # Bend outward slightly for a tapered curve
                bend = 6 * size_scale
                bx = mid_x + math.cos(dir_ang + math.pi/2) * bend
                by = mid_y + math.sin(dir_ang + math.pi/2) * (bend * 0.6)

                col = p['color']
                alpha = 90 if is_behind else 230
                pygame.draw.lines(screen, (*col, alpha), False, [(px, py), (bx, by), (tail_x, tail_y)], 2)

            else:
                # Draw Debris (Rocks)
                col = (40, 50, 60) if is_behind else (200, 220, 230)
                size = 2 if is_behind else 4
                pygame.draw.circle(screen, col, (int(px), int(py)), size)

class GameState:
    def __init__(self, obstacles: Dict, items: Set, main_item_pos: List[Tuple[int, int]], decorations: list):
        self.obstacles = obstacles
        self.items = items
        self.destructible_count = self.count_destructible_obstacles()
        self.main_item_pos = main_item_pos
        self.items_total = len(items)  # track total at start
        # non-colliding visual fillers
        self.decorations = decorations  # list[Tuple[int,int]] grid coords
        self.spoils = []  # List[Spoil]
        self.heals = []  # List[HealPickup]
        self.dmg_texts = []  # List[DamageText]
        self.acids = []  # List[AcidPool]
        self.telegraphs = []  # List[TelegraphCircle]
        self.aegis_pulses = []  # List[AegisPulseRing]
        self.ghosts = []  # 冲刺残影列表
        self.fog_on = False
        self.fog_radius_px = FOG_VIEW_TILES * CELL_SIZE
        self.fog_enabled: bool = False
        self.fog_alpha = FOG_OVERLAY_ALPHA
        self.fog_lanterns: list = []  # FogLantern 实例
        self._fog_pulse_t: float = 0.0  # 呼吸脉冲
        self.spoils_gained = 0  # 本关临时获得
        self._bandit_stolen = 0  # 本关被盗总额（只用于提示）
        self.level_coin_delta = 0  # 本关净金币变化（拾取-流失），仅用于内部计算
        self._spoils_settled = False  # 本关是否已完成“成功结算”
        self.bandit_spawned_this_level = False
        self.banner_text = None  # 当前横幅文字
        self.banner_t = 0.0  # 横幅剩余时间（秒）
        self._banner_tick_ms = None  # 用于计时的上一帧时间戳
        self.focus_queue = []  # NEW: queue of [("boss",(x,y)), ...] for multi-focus
        self.ff_dist = None
        self.ff_next = None
        self._ff_goal = None  # (gx, gy) of player last time
        self._ff_dirty = True
        self._ff_timer = 0.0  # cooldown to throttle rebuilds
        self._ff_tacc = 0.0
        # bullets spawned during bullet update (e.g. shrapnel from on-kill effects)
        self.pending_bullets: List["Bullet"] = []
        # Mark of Vulnerability state
        self._vuln_mark_cd: float = 0.0
        # Wind biome: hurricanes (vortices)
        self.hurricanes: list[dict] = []
        # --- PARTICLE SYSTEM ---
        self.fx = ParticleSystem()
        # --- Comet Blast VFX ---
        self.comet_blasts: list[CometBlast] = []
        self.comet_corpses: list[CometCorpse] = []
        self._cam_shake_t = 0.0
        self._cam_shake_total = 0.001
        self._cam_shake_mag = 0.0

    def count_destructible_obstacles(self) -> int:
        return sum(1 for obs in self.obstacles.values() if obs.type == "Destructible")

    def spawn_spoils(self, x_px: float, y_px: float, count: int = 1):
        for _ in range(int(max(0, count))):
            # tiny jitter so multiple coins don't overlap perfectly
            jx = random.uniform(-6, 6)
            jy = random.uniform(-6, 6)
            self.spoils.append(Spoil(x_px + jx, y_px + jy, 1))

    def update_spoils(self, dt: float, player: "Player"):
        """
        Update coin bounce, and if Coin Magnet is bought, gently pull coins toward the player.
        Actual pickup still happens in collect_spoils when a coin overlaps the player.
        """
        # 1) basic vertical bounce
        for s in self.spoils:
            s.update(dt)
        # 2) magnet attraction — only if the shop item has added a radius
        magnet_radius = int(META.get("coin_magnet_radius", 0) or 0)
        if magnet_radius <= 0:
            return
        px, py = player.rect.center
        pull_speed = 480.0  # px/s, tweak for feel
        r2 = float(magnet_radius * magnet_radius)
        for s in self.spoils:
            cx, cy = s.rect.center
            dx = px - cx
            dy = py - cy
            dist2 = dx * dx + dy * dy
            if dist2 > r2:
                continue
            # Move a small step toward the player; collect_spoils will finish pickup
            dist = max(1.0, dist2 ** 0.5)
            step = min(pull_speed * dt, dist)
            nx = cx + dx / dist * step
            ny = cy + dy / dist * step
            # translate base_x/base_y by the same delta as the rect center movement
            s.base_x += (nx - cx)
            s.base_y += (ny - cy)
            s._update_rect()

    def collect_item(self, player_rect: pygame.Rect) -> bool:
        """Collect one item if the player overlaps it. Returns True if collected."""
        for it in list(self.items):
            if player_rect.colliderect(it.rect):
                self.items.remove(it)
                try:
                    META["run_items_collected"] = int(META.get("run_items_collected", 0)) + 1
                except Exception:
                    pass
                return True
        return False

    def collect_spoils(self, player_rect: pygame.Rect) -> int:
        """Collect spoils that actually touch the player."""
        gained = 0
        pickup_rect = player_rect
        for s in list(self.spoils):
            if pickup_rect.colliderect(s.rect):
                self.spoils.remove(s)
                self.spoils_gained += s.value
                self.level_coin_delta += s.value
                gained += s.value
        return gained

    def collect_spoils_for_enemy(self, enemy: "Enemy") -> int:
        """让某个僵尸收集与其相交的金币，返回本次收集数量。"""
        gained = 0
        zr = enemy.rect
        for s in list(self.spoils):
            if zr.colliderect(s.rect):
                self.spoils.remove(s)
                gained += s.value
        return gained

    def lose_coins(self, amount: int) -> int:
        """Drain run coins first, then banked META coins; returns amount removed. Respects Lockbox protection."""
        amt = int(max(0, amount))
        if amt <= 0:
            return 0
        taken = 0
        meta = globals().get("META", {})
        level_spoils = int(getattr(self, "spoils_gained", 0))
        try:
            bank = int(meta.get("spoils", 0))
        except Exception:
            meta = {}
            bank = 0
        coins_before = max(0, level_spoils + bank)
        lb_lvl = 0
        try:
            lb_lvl = int(meta.get("lockbox_level", 0))
        except Exception:
            lb_lvl = 0
        amt = clamp_coin_loss_with_lockbox(coins_before, amt, lb_lvl)
        # 优先扣本局
        g = level_spoils
        d = min(g, amt)
        self.spoils_gained = g - d
        taken += d
        amt -= d
        # 再扣金库
        if amt > 0 and isinstance(meta, dict):
            rest = min(max(0, bank), amt)
            meta["spoils"] = bank - rest
            taken += rest
        try:
            self.level_coin_delta -= taken
        except Exception:
            pass
        return taken

    def spawn_heal(self, x_px: float, y_px: float, amount: int = HEAL_POTION_AMOUNT):
        # Prevent runaway heal stacks (can happen in long boss fights).
        if len(self.heals) >= HEAL_MAX_ON_FIELD:
            return
        jx = random.uniform(-6, 6);
        jy = random.uniform(-6, 6)
        self.heals.append(HealPickup(x_px + jx, y_px + jy, amount))

    def update_heals(self, dt: float):
        for h in self.heals:
            h.update(dt)

    def collect_heals(self, player: "Player") -> int:
        healed = 0
        for h in list(self.heals):
            if player.rect.colliderect(h.rect):
                self.heals.remove(h)
                before = player.hp
                player.hp = min(player.max_hp, player.hp + h.heal)
                healed += (player.hp - before)
        return healed

    def flash_banner(self, text: str, sec: float = 1.0):
        """在屏幕中央显示一条横幅 sec 秒。"""
        self.banner_text = str(text)
        self.banner_t = float(max(0.0, sec))
        self._banner_tick_ms = None  # 让绘制处在下一帧重置基线

    # ---- 地面腐蚀池 ----w
    # 在 GameState 内，替换/保留为 ↓ 这个版本
    # ---- 地面腐蚀池（兼容旧/新参数名）----
    def spawn_acid_pool(self,
                        x, y,
                        r=24,
                        dps=ACID_DPS,
                        life=ACID_LIFETIME,
                        slow_frac=None,  # 新参数名
                        slow=None,  # 旧参数名（向后兼容）
                        style="acid"):  # 可用于雾池/雾门上色
        # 兼容处理：优先采用 slow_frac；否则用 slow；最后回退到默认常量
        if slow_frac is None and slow is not None:
            slow_frac = slow
        if slow_frac is None:
            slow_frac = ACID_SLOW_FRAC
        a = AcidPool(float(x), float(y), float(r), float(dps), float(slow_frac), float(life))
        # 可选：让绘制侧能按风格自定义颜色/粒子
        setattr(a, "style", style)
        setattr(a, "life0", float(life))
        self.acids.append(a)

    def spawn_projectile(self, proj):
        self.projectiles.append(proj)

    def update_acids(self, dt: float, player: "Player"):
        # 衰减 slow / DoT 计时
        player.slow_t = max(0.0, getattr(player, "slow_t", 0.0) - dt)
        player.acid_dot_timer = max(0.0, getattr(player, "acid_dot_timer", 0.0) - dt)
        # 维护一个按秒结算的累计器（避免帧率依赖）
        if not hasattr(player, "_acid_dmg_accum"):
            player._acid_dmg_accum = 0.0
        if not hasattr(player, "_slow_frac"):
            player._slow_frac = 0.0
        # 只取当前踩到的酸池里“最强”的那个，而不是累加（防止重叠酸池爆表）
        px, py = player.rect.centerx, player.rect.centery
        max_dps = 0.0
        max_slow = 0.0
        touching = False
        # 更新酸池寿命，同时检查是否踩中
        alive = []
        for a in self.acids:
            a.t -= dt
            if a.t > 0:
                alive.append(a)
                if a.contains(px, py):
                    touching = True
                    if a.dps > max_dps: max_dps = a.dps
                    if a.slow_frac > max_slow: max_slow = a.slow_frac
        self.acids = alive
        if touching:
            # 站在池里：按秒累加 dps（仅取最强那一摊）
            player._acid_dmg_accum += max_dps * dt
            ticks = int(player._acid_dmg_accum)  # 每满1点血扣一次
            if ticks > 0:
                self.damage_player(player, ticks)
                player._acid_dmg_accum -= ticks
            # 施加减速（刷新时长，让它留存一点点）
            player.slow_t = max(player.slow_t, 0.40)  # 可调：0.3~0.5
            # 刷新离开后的持续 DoT（占总 dps 的一部分）
            player.acid_dot_timer = ACID_DOT_DURATION
            player.acid_dot_dps = max_dps * ACID_DOT_MULT
            player._slow_frac = max(float(getattr(player, "_slow_frac", 0.0)), float(max_slow))
        else:
            if getattr(player, "slow_t", 0.0) <= 0.0:
                player._slow_frac = 0.0
        # 不在池里：不做直接伤害；离开后的 DoT 由主循环统一结算

    def damage_player(self, player, dmg, kind="hp"):
        dmg = int(max(0, dmg))
        if dmg <= 0:
            return 0
        # Stone (or any) shield first
        sh = int(getattr(player, "shield_hp", 0))
        if sh > 0:
            blocked = min(dmg, sh)
            player.shield_hp = sh - blocked
            self.add_damage_text(
                player.rect.centerx,
                player.rect.top - 10,
                blocked,
                crit=False,
                kind="shield",
            )
            dmg -= blocked
        plating_lvl = int(getattr(player, "bone_plating_level", 0))
        plating_hp = int(getattr(player, "bone_plating_hp", 0))
        if dmg > 0 and plating_lvl > 0 and plating_hp > 0:
            enhanced = plating_lvl >= BONE_PLATING_MAX_LEVEL
            if enhanced:
                consume = BONE_PLATING_STACK_HP if plating_hp >= BONE_PLATING_STACK_HP else plating_hp
                blocked = dmg
                player.bone_plating_hp = max(0, plating_hp - consume)
                dmg = 0
                text = "Bone"
            else:
                blocked = min(dmg, plating_hp)
                player.bone_plating_hp = max(0, plating_hp - blocked)
                dmg -= blocked
                text = blocked
            if blocked > 0:
                self.add_damage_text(
                    player.rect.centerx,
                    player.rect.top - 24,
                    text,
                    kind="shield",
                )
                player._bone_plating_glow = max(0.4, float(getattr(player, "_bone_plating_glow", 0.0)))
        # Carapace: 20 HP chunks stored in META["carapace_shield_hp"]
        carapace_hp = int(META.get("carapace_shield_hp", 0))
        if dmg > 0 and carapace_hp > 0:
            absorbed = min(dmg, carapace_hp)
            dmg -= absorbed
            carapace_hp -= absorbed
            META["carapace_shield_hp"] = carapace_hp
            player.carapace_hp = carapace_hp
            self.add_damage_text(
                player.rect.centerx,
                player.rect.top - 10,
                "Carapace",
                kind="shield",
            )
        if dmg > 0:
            hp_before = int(player.hp)
            player.hp = max(0, player.hp - dmg)
            if player.hp < hp_before:
                player._hit_flash = float(HIT_FLASH_DURATION)
                player._flash_prev_hp = int(player.hp)
            self.add_damage_text(
                player.rect.centerx,
                player.rect.centery,
                dmg,
                crit=False,
                kind=kind or "hp",
            )
        return dmg

    def mark_nav_dirty(self):
        self._ff_dirty = True

    def refresh_flow_field(self, player_tile, dt=0.0):
        # throttle rebuilds to ~0.3s or on dirty/goal change
        self._ff_timer = max(0.0, self._ff_timer - dt)
        self._ff_tacc = min(1.0, float(getattr(self, "_ff_tacc", 0.0)) + float(dt or 0.0))
        if self._ff_dirty or self._ff_timer <= 0.0 or self._ff_goal != player_tile:
            self.ff_dist, self.ff_next = build_flow_field(GRID_SIZE, self.obstacles, player_tile)
            self._ff_goal = player_tile
            self._ff_dirty = False
            self._ff_timer = 0.30
            self._ff_tacc = 0.0
        if self._ff_tacc >= 0.30 or self._ff_dirty:
            goal = self._ff_goal or player_tile
            # pad=1 uses the optional arg from build_flow_field(...) signature
            self.ff_dist, self.ff_next = build_flow_field(GRID_SIZE, self.obstacles, goal, pad=1)
            self._ff_dirty = False
            self._ff_tacc = 0.0

    # ---- 攻击前的提示圈（到时后生成酸池等）----
    def spawn_telegraph(self, x, y, r, life, kind="acid", payload=None, color=(255, 60, 60)):
        self.telegraphs.append(TelegraphCircle(float(x), float(y), float(r), float(life), kind, payload, color))

    def update_telegraphs(self, dt: float):
        for t in list(self.telegraphs):
            t.t -= dt
            if t.t <= 0:
                # 触发
                if t.kind == "acid" and t.payload:
                    # payload: dict with {count, radius, life, dps, slow}
                    for px, py in t.payload.get("points", []):
                        self.spawn_acid_pool(px, py,
                                             r=t.payload.get("radius", 24),
                                             dps=t.payload.get("dps", ACID_DPS),
                                             slow_frac=t.payload.get("slow", ACID_SLOW_FRAC),
                                             life=t.payload.get("life", ACID_LIFETIME))
                self.telegraphs.remove(t)

    def update_aegis_pulses(self, dt: float, player=None, enemies=None):
        if not getattr(self, "aegis_pulses", None):
            self.aegis_pulses = []
            return
        alive = []
        for p in self.aegis_pulses:
            p.t -= dt
            if p.t > 0:
                # keep the ripple centered on the current player position so it travels with you
                if player is not None:
                    p.x = float(player.rect.centerx)
                    p.y = float(player.rect.centery)
                # each layer applies its damage once when it becomes active
                if (not getattr(p, "hit_done", False)
                        and (p.life0 - p.t) >= float(getattr(p, "delay", 0.0))
                        and enemies is not None):
                    _apply_aegis_pulse_damage(player, self, enemies, p.x, p.y, float(getattr(p, "r", 0.0)),
                                              int(getattr(p, "damage", 0)))
                    p.hit_done = True
                alive.append(p)
        self.aegis_pulses = alive

    def add_damage_text(self, x, y, amount, crit=False, kind="hp"):
        # allow string labels ("ENRAGE!", "IMMUNE", etc.)
        if isinstance(amount, (int, float)):
            amount = int(amount)
            if amount <= 0:
                return
            self.dmg_texts.append(DamageText(x, y, amount, crit, kind))
        else:
            # label path
            self.dmg_texts.append(DamageText(x, y, str(amount), True if crit else False, kind))

    def update_damage_texts(self, dt: float):
        for d in list(self.dmg_texts):
            d.step(dt)
            if not d.alive():
                self.dmg_texts.remove(d)

    # --- Comet Blast helpers ---
    def add_cam_shake(self, magnitude: float, duration: float = 0.25):
        mag = max(0.0, float(magnitude))
        dur = max(0.05, float(duration))
        self._cam_shake_mag = max(self._cam_shake_mag, mag)
        self._cam_shake_t = max(self._cam_shake_t, dur)
        self._cam_shake_total = max(self._cam_shake_total, dur)

    def update_camera_shake(self, dt: float):
        self._cam_shake_t = max(0.0, float(getattr(self, "_cam_shake_t", 0.0)) - dt)
        if self._cam_shake_t <= 0.0:
            self._cam_shake_mag = 0.0

    def camera_shake_offset(self) -> tuple[int, int]:
        t = float(getattr(self, "_cam_shake_t", 0.0))
        mag = float(getattr(self, "_cam_shake_mag", 0.0))
        tot = float(getattr(self, "_cam_shake_total", 0.001))
        if t <= 0.0 or mag <= 0.0:
            return 0, 0
        strength = mag * (t / max(0.001, tot))
        ang = random.random() * math.tau
        return int(math.cos(ang) * strength), int(math.sin(ang) * strength)

    def spawn_comet_blast(self, target_pos: tuple[float, float], start_pos: tuple[float, float],
                          travel: float, impact_cb=None) -> CometBlast:
        cb = CometBlast(target_pos, start_pos, travel, on_impact=impact_cb, fx=self.fx)
        self.comet_blasts.append(cb)
        return cb

    def update_comet_blasts(self, dt: float, player=None, enemies=None):
        for b in list(self.comet_blasts):
            b.update(dt)
            if b.done():
                self.comet_blasts.remove(b)
        # decay comet hit flash/shake on enemies
        if enemies is not None:
            for z in enemies:
                flash = float(getattr(z, "_comet_flash", 0.0))
                if flash > 0.0:
                    z._comet_flash = max(0.0, flash - dt * 4.5)
                shake = float(getattr(z, "_comet_shake", 0.0))
                if shake > 0.0:
                    z._comet_shake = max(0.0, shake - dt * 4.0)
        # corpses
        self.comet_corpses = [c for c in self.comet_corpses if c.update(dt)]

    def draw_comet_blasts(self, screen: pygame.Surface, camx: float, camy: float):
        for b in getattr(self, "comet_blasts", []):
            b.draw(screen, camx, camy)

    def draw_comet_corpses(self, screen: pygame.Surface, camx: float, camy: float):
        for c in getattr(self, "comet_corpses", []):
            c.draw_iso(screen, camx, camy)

    def spawn_hurricane(self, x: float, y: float, r: float | None = None):
        if not hasattr(self, "hurricanes"):
            self.hurricanes = []
        # Creates a class instance now, not a dict
        self.hurricanes.append(TornadoEntity(x, y, r if r is not None else HURRICANE_START_RADIUS))

    def _apply_pull(self, pos_x, pos_y, radius, hx, hy, range_r, strength, dt, resist_scale=1.0):
        dx = hx - pos_x
        dy = hy - pos_y
        dist = math.hypot(dx, dy)
        if dist <= 1e-3 or dist > range_r:
            return pos_x, pos_y
        influence = max(0.0, 1.0 - dist / range_r)
        # Non-linear falloff so pull weakens more as you get farther away
        influence *= influence
        pull = strength * influence * resist_scale
        step = pull * dt
        step = min(step, dist * 0.95)
        nx, ny = dx / dist, dy / dist
        return pos_x + nx * step, pos_y + ny * step

    def update_hurricanes(self, dt: float, player, enemies, bullets, enemy_shots=None):
        # reset per-frame bandit trap flag; only re-enabled if actually in a wind influence ring this frame
        for z in enemies:
            if getattr(z, "type", "") == "bandit":
                z._wind_trapped = False
        if not getattr(self, "hurricanes", None):
            return
        
        # --- Helper for mass-based resistance ---
        def _vortex_resist(ent):
            resist = 0.8  # base dampening so pull feels lighter for everyone
            # Faster/larger entities resist more
            if float(getattr(ent, "speed", 0.0)) >= HURRICANE_ESCAPE_SPEED:
                resist *= 0.4
            if getattr(ent, "is_boss", False):
                resist *= 0.15 # Bosses barely move
            return resist
            
        for h in list(self.hurricanes):
            # Back-compat: old hurricanes stored as dicts or missing spin attrs
            if isinstance(h, dict):
                hx_raw = float(h.get("x", 0.0))
                hy_raw = float(h.get("y", 0.0))
                rr_raw = float(h.get("r", HURRICANE_START_RADIUS))
                spin_dir = h.get("dir", None)
                spin_rate = h.get("spin", None)
                new_h = TornadoEntity(hx_raw, hy_raw, rr_raw, spin_rate=spin_rate, spin_dir=spin_dir)
                self.hurricanes.remove(h)
                self.hurricanes.append(new_h)
                h = new_h
            # Ensure spin defaults exist (in case of partially constructed objects)
            if not hasattr(h, "spin_rate"):
                jitter = random.uniform(1.0 - HURRICANE_SPIN_VARIANCE, 1.0 + HURRICANE_SPIN_VARIANCE)
                h.spin_rate = max(0.05, HURRICANE_SPIN_BASE * jitter)
            if not hasattr(h, "spin_dir"):
                h.spin_dir = random.choice((-1.0, 1.0))
            h.update(dt)
            effect_radius = h.r * HURRICANE_RANGE_MULT
            
            # 1. Pull Player
            dx, dy = h.apply_vortex_physics(player, dt, resist_scale=_vortex_resist(player))
            if dx or dy:
                collide_and_slide_circle(player, self.obstacles.values(), dx, dy)
            
            # 2. Pull Enemies
            for z in enemies:
                if getattr(z, "type", "") == "bandit":
                    dist_bandit = math.hypot(h.x - z.rect.centerx, h.y - z.rect.centery)
                    if dist_bandit <= effect_radius:
                        z._wind_trapped = True
                dx, dy = h.apply_vortex_physics(z, dt, resist_scale=_vortex_resist(z))
                if dx or dy:
                    collide_and_slide_circle(z, self.obstacles.values(), dx, dy)
                
                # Apply slow effect if near center
                dist = math.hypot(h.x - z.rect.centerx, h.y - z.rect.centery)
                if dist < h.r * 1.5:
                    z._hurricane_slow_mult = 0.7 
                else:
                    z._hurricane_slow_mult = 1.0

            # 3. Spin Bullets (Visual only, no collision)
            all_shots = list(bullets)
            if enemy_shots: all_shots.extend(enemy_shots)
            
            for b in all_shots:
                # Bullets are lighter; apply simplified radial + tangential force without collision checks
                bx = getattr(b, "x", None)
                by = getattr(b, "y", None)
                if bx is None or by is None:
                    continue
                dx = h.x - bx
                dy = h.y - by
                dist = math.hypot(dx, dy)
                effect_radius = h.r * HURRICANE_RANGE_MULT
                if dist <= 1e-4 or dist > effect_radius:
                    continue
                influence = max(0.0, 1.0 - dist / effect_radius)
                nx, ny = dx / dist, dy / dist
                tx, ty = -ny, nx
                if h.spin_dir < 0:
                    tx, ty = -tx, -ty
                # radial pull
                pull = HURRICANE_BULLET_PULL * influence
                b.vx += nx * pull * dt
                b.vy += ny * pull * dt
                # tangential swirl toward target tangential speed
                target_tan = h.spin_rate * dist * influence
                current_tan = b.vx * tx + b.vy * ty
                delta_tan = target_tan - current_tan
                steer = delta_tan * HURRICANE_BULLET_SPIN_STEER * dt
                b.vx += tx * steer
                b.vy += ty * steer

    def update_vulnerability_marks(self, enemies, dt: float):
        lvl = int(META.get("vuln_mark_level", 0))
        if lvl <= 0:
            # clean stale marks if the prop is not owned
            for z in enemies:
                if hasattr(z, "_vuln_mark_t"):
                    z._vuln_mark_t = 0.0
            self._vuln_mark_cd = 0.0
            return
        # global pulse
        globals()["mark_pulse_time"] = globals().get("mark_pulse_time", 0.0) + dt
        interval, bonus, duration = mark_of_vulnerability_stats(lvl)
        # decay marks and small hit flash
        for z in enemies:
            t = float(getattr(z, "_vuln_mark_t", 0.0))
            if t > 0.0:
                z._vuln_mark_t = max(0.0, t - dt)
                z._vuln_mark_bonus = bonus
                z._vuln_mark_level = lvl
            flash = float(getattr(z, "_vuln_hit_flash", 0.0))
            if flash > 0.0:
                z._vuln_hit_flash = max(0.0, flash - dt * 4.0)
        cd = float(getattr(self, "_vuln_mark_cd", 0.0))
        cd -= dt
        # allow multiple triggers in a long frame without runaway loops
        triggers = 0
        while cd <= 0.0 and triggers < 3:
            triggers += 1
            cd += interval
            alive_unmarked = [
                z for z in enemies
                if getattr(z, "hp", 0) > 0 and float(getattr(z, "_vuln_mark_t", 0.0)) <= 0.0
            ]
            if not alive_unmarked:
                continue

            def _priority(z):
                if getattr(z, "is_boss", False):
                    return 0
                if getattr(z, "is_elite", False):
                    return 1
                return 2

            buckets = {0: [], 1: [], 2: []}
            for z in alive_unmarked:
                buckets[_priority(z)].append(z)
            target_group = next((g for g in (buckets[0], buckets[1], buckets[2]) if g), None)
            if not target_group:
                continue
            z = random.choice(target_group)
            z._vuln_mark_t = duration
            z._vuln_mark_bonus = bonus
            z._vuln_mark_level = lvl
            z._vuln_hit_flash = max(0.0, float(getattr(z, "_vuln_hit_flash", 0.0)))
        self._vuln_mark_cd = cd

    def update_dot_rounds(self, enemies, dt: float) -> None:
        lvl = int(META.get("dot_rounds_level", 0))
        if lvl <= 0:
            for z in enemies:
                if getattr(z, "dot_rounds_stacks", None):
                    z.dot_rounds_stacks = []
                    z._dot_rounds_tick_t = float(DOT_ROUNDS_TICK_INTERVAL)
                    z._dot_rounds_accum = 0.0
            return
        tick_interval = float(DOT_ROUNDS_TICK_INTERVAL)
        for z in enemies:
            if getattr(z, "hp", 0) <= 0:
                continue
            stacks = getattr(z, "dot_rounds_stacks", None)
            if not stacks:
                continue
            for s in stacks:
                s["t"] = float(s.get("t", 0.0)) - dt
            stacks[:] = [s for s in stacks if s.get("t", 0.0) > 0.0]
            if not stacks:
                z._dot_rounds_tick_t = tick_interval
                z._dot_rounds_accum = 0.0
                continue
            tick_t = float(getattr(z, "_dot_rounds_tick_t", tick_interval))
            tick_t -= dt
            if tick_t <= 0.0:
                ticks = int(abs(tick_t) // tick_interval) + 1
                tick_t += tick_interval * ticks
                total = 0.0
                for s in stacks:
                    total += float(s.get("dmg", 0.0)) * ticks
                if total > 0.0:
                    if getattr(z, "is_boss", False):
                        total *= DOT_ROUNDS_BOSS_MULT
                    accum = float(getattr(z, "_dot_rounds_accum", 0.0)) + total
                    deal = int(accum)
                    if deal > 0:
                        z.hp -= deal
                        self.add_damage_text(
                            z.rect.centerx,
                            z.rect.centery - 8,
                            deal,
                            crit=False,
                            kind="dot",
                        )
                        z._dot_rounds_accum = accum - deal
                    else:
                        z._dot_rounds_accum = accum
            z._dot_rounds_tick_t = tick_t

    def enable_fog_field(self):
        if self.fog_on:
            return
        self.fog_on = True
        # 随机放置 3 个“非阻挡”的驱雾灯笼
        spawned = 0
        tried = 0
        while spawned < FOG_LANTERN_COUNT and tried < 200:
            tried += 1
            gx = random.randint(2, GRID_SIZE - 3)
            gy = random.randint(2, GRID_SIZE - 3)
            if (gx, gy) in self.obstacles:
                continue
            # 避免放在玩家脚下：用主角出生点近似
            self.obstacles[(gx, gy)] = FogLantern(gx, gy)
            spawned += 1

    def disable_fog_field(self):
        if not self.fog_on:
            return
        self.fog_on = False
        # 清理已死的灯笼；保留其它障碍不动
        for gp, ob in list(self.obstacles.items()):
            if getattr(ob, "type", "") == "Lantern":
                del self.obstacles[gp]

    # --- GameState ---
    def request_fog_field(self, player=None):
        """首次启动雾场 & 刷新灯笼。player 可选（首次刷 Boss 时可能还没 self.player）。"""
        if getattr(self, "_fog_inited", False):
            return
        self._fog_inited = True
        self.fog_enabled = True
        if not hasattr(self, "fog_lanterns"):
            self.fog_lanterns = []
        self.spawn_fog_lanterns(player)

    def spawn_fog_lanterns(self, player=None):
        """把 FOG_LANTERN_COUNT 个灯笼刷在可走格上，尽量离玩家远；无玩家时以地图中心为基准。"""
        if not hasattr(self, "fog_lanterns"):
            self.fog_lanterns = []
        self.fog_lanterns.clear()
        # 已占用：障碍 + 物品
        taken = set(self.obstacles.keys()) | {(it.x, it.y) for it in getattr(self, "items", [])}
        # 取玩家网格坐标（若无，则用地图中心）
        if player is None and hasattr(self, "player"):
            player = self.player
        if player is not None and hasattr(player, "rect"):
            px = int(player.rect.centerx // CELL_SIZE)
            py = int((player.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE)
        else:
            px = GRID_SIZE // 2
            py = GRID_SIZE // 2
        # 候选格：可走、且与玩家的曼哈顿距离≥6
        cells = [(x, y) for y in range(GRID_SIZE) for x in range(GRID_SIZE)
                 if (x, y) not in taken and abs(x - px) + abs(y - py) >= 6]
        random.shuffle(cells)
        want = int(FOG_LANTERN_COUNT)
        for _ in range(want):
            if not cells:
                break
            gx, gy = cells.pop()
            lan = FogLantern(gx, gy, hp=FOG_LANTERN_HP)  # ★ 真正创建
            self.fog_lanterns.append(lan)  # ★ 放进列表
            self.obstacles[(gx, gy)] = lan  # ★ 作为障碍注册（有碰撞体积）

    def draw_lanterns_iso(self, screen, camx, camy):
        for lan in list(self.fog_lanterns):
            if not lan.alive:
                continue
            gx, gy = lan.grid_pos
            sx, sy = iso_world_to_screen(gx + 0.5, gy + 0.5, 0, camx, camy)
            # 柔光圈
            glow = pygame.Surface((int(CELL_SIZE * 2.2), int(CELL_SIZE * 1.4)), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (255, 240, 120, 90), glow.get_rect())
            screen.blit(glow, glow.get_rect(center=(int(sx), int(sy + 6))).topleft)
            # 方灯体
            body = pygame.Rect(0, 0, int(CELL_SIZE * 0.55), int(CELL_SIZE * 0.55))
            body.center = (int(sx), int(sy - 4))
            pygame.draw.rect(screen, (255, 230, 120), body, border_radius=6)
            pygame.draw.rect(screen, (120, 80, 20), body, 2, border_radius=6)

    def draw_lanterns_topdown(self, screen, camx, camy):
        for lan in list(self.fog_lanterns):
            if not lan.alive:
                continue
            gx, gy = lan.grid_pos
            cx = int(gx * CELL_SIZE + CELL_SIZE * 0.5 - camx)
            cy = int(gy * CELL_SIZE + CELL_SIZE * 0.5 + INFO_BAR_HEIGHT - camy)
            body = pygame.Rect(0, 0, int(CELL_SIZE * 0.55), int(CELL_SIZE * 0.55))
            body.center = (cx, cy)
            pygame.draw.rect(screen, (255, 230, 120), body, border_radius=6)
            pygame.draw.rect(screen, (120, 80, 20), body, 2, border_radius=6)

    def draw_hazards_iso(self, screen, cam_x, cam_y):
        # 1) Telegraph（空心圈）
        for t in list(getattr(self, "telegraphs", [])):
            # 颜色/透明度由 telegraph 自带
            draw_iso_ground_ellipse(
                screen, t.x, t.y, t.r,
                color=getattr(t, "color", (255, 80, 80)), alpha=180,
                camx=cam_x, camy=cam_y, fill=False, width=2
            )
        for p in list(getattr(self, "aegis_pulses", [])):
            life0 = max(0.001, float(getattr(p, "life0", AEGIS_PULSE_TTL)))
            fade = max(0.0, min(1.0, float(getattr(p, "t", 0.0)) / life0))
            draw_iso_hex_ring(
                screen, p.x, p.y, p.r,
                AEGIS_PULSE_COLOR, int(AEGIS_PULSE_RING_ALPHA * fade),
                cam_x, cam_y,
                sides=6,
                fill_alpha=int(AEGIS_PULSE_FILL_ALPHA * fade),
                width=3
            )
        # 2) Acid/Mist Pools（实体椭圆）
        for a in list(getattr(self, "acids", [])):
            style = getattr(a, "style", "acid")
            st = HAZARD_STYLES.get(style, HAZARD_STYLES.get("acid", {"fill": (90, 255, 120), "ring": (30, 160, 60)}))
            # 使用寿命比例做淡出
            life0 = max(0.001, float(getattr(a, "life0", getattr(a, "t", 1.0))))
            alpha = int(150 * max(0.15, min(1.0, a.t / life0)))
            # 填充
            draw_iso_ground_ellipse(screen, a.x, a.y, a.r, st["fill"], alpha, cam_x, cam_y, fill=True)
            # 细边
            draw_iso_ground_ellipse(screen, a.x, a.y, a.r, st["ring"], 180, cam_x, cam_y, fill=False, width=2)

    def draw_fog_overlay(self, screen, camx, camy, player, obstacles):
        """在世界层上方绘制一层‘黑雾’，对玩家与灯笼的范围挖透明洞。"""
        if not self.fog_enabled:
            return
        w, h = screen.get_size()
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        # 整屏覆雾
        mask.fill((0, 0, 0, FOG_OVERLAY_ALPHA))
        # === 挖‘清晰洞’ ===
        clear_r = FOG_VIEW_TILES * CELL_SIZE
        # 1) 玩家
        psx, psy = iso_world_to_screen(player.rect.centerx / CELL_SIZE,
                                       (player.rect.centery - INFO_BAR_HEIGHT) / CELL_SIZE,
                                       0, camx, camy)
        pygame.draw.circle(mask, (0, 0, 0, 0), (int(psx), int(psy)), int(clear_r))
        # 2) 每个存活的雾灯笼
        for lan in self.fog_lanterns:
            if not lan.alive:
                continue
            gx, gy = lan.grid_pos
            sx, sy = iso_world_to_screen(gx + 0.5, gy + 0.5, 0, camx, camy)
            pygame.draw.circle(mask, (0, 0, 0, 0), (int(sx), int(sy)), int(FOG_LANTERN_CLEAR_RADIUS))
        # 可选：微弱的呼吸脉冲，让雾面有生命感
        self._fog_pulse_t = (self._fog_pulse_t + 0.016) % 1.0
        pulse = int(14 * (0.5 + 0.5 * math.sin(self._fog_pulse_t * math.tau)))
        if pulse > 0:
            edge = pygame.Surface((w, h), pygame.SRCALPHA)
            edge.fill((220, 220, 240, pulse))
            mask.blit(edge, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        # 覆盖到屏幕
        screen.blit(mask, (0, 0))


# ==================== 相机 ====================
def compute_cam_for_center_iso(cx_px: int, cy_px: int) -> tuple[int, int]:
    """给定世界像素（含 INFO_BAR_HEIGHT 的 y），返回 iso 渲染用的 (cam_x, cam_y)。"""
    gx = cx_px / float(CELL_SIZE)
    gy = (cy_px - INFO_BAR_HEIGHT) / float(CELL_SIZE)
    sx, sy = iso_world_to_screen(gx, gy, 0, 0, 0)
    cam_x = int(sx - VIEW_W // 2)
    cam_y = int(sy - (VIEW_H - INFO_BAR_HEIGHT) // 2)
    return cam_x, cam_y


# --- Chained boss focus: pan through many targets, then back to player once ---
def play_focus_chain_iso(screen, clock, game_state, player, enemies, bullets, enemy_shots, targets,
                         hold_time=0.9, label="BOSS"):
    """
    targets: list of (x_px, y_px) world-pixel centers (e.g., rect.centerx, rect.centery).
    Plays boss → boss → … → player (once).
    """
    last_cam = None
    for i, pos in enumerate(targets):
        fx, fy = pos
        focus_cam = compute_cam_for_center_iso(int(fx), int(fy))
        show_label = label if i == 0 else None
        play_focus_cinematic_iso(
            screen, clock, game_state, player, enemies, bullets, enemy_shots,
            (int(fx), int(fy)), label=show_label, hold_time=hold_time,
            return_to_player=False, start_cam=last_cam
        )
        last_cam = focus_cam
    # final glide back to player (one time)
    pcenter = (int(player.rect.centerx), int(player.rect.centery))
    play_focus_cinematic_iso(
        screen, clock, game_state, player, enemies, bullets, enemy_shots,
        pcenter, label=None, hold_time=0.0,
        return_to_player=False, start_cam=last_cam
    )


def play_focus_cinematic_iso(screen, clock,
                             game_state, player,
                             enemies, bullets, enemy_shots,
                             focus_world_px: tuple[int, int],
                             hold_time: float = 0.35,
                             duration_each: float = 0.70,
                             label: str | None = None,
                             return_to_player: bool = True,
                             start_cam: tuple[int, int] | None = None):
    """
    等距过场镜头：
    - 相机从 start_cam(若无则玩家) → 焦点；可选 焦点 → 玩家。
    - 冻结时间与世界更新，仅渲染。
    """

    def _cam_for_world_px(wx: float, wy: float) -> tuple[int, int]:
        gx = wx / CELL_SIZE
        gy = (wy - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(gx, gy, 0.0, 0.0, 0.0)
        camx = int(sx - VIEW_W // 2)
        camy = int(sy - (VIEW_H - INFO_BAR_HEIGHT) // 2)
        return camx, camy

    def _cam_for_player() -> tuple[int, int]:
        return calculate_iso_camera(player.x + player.size * 0.5,
                                    player.y + player.size * 0.5 + INFO_BAR_HEIGHT)

    def _lerp(a: float, b: float, t: float) -> float:
        return a + (b - a) * max(0.0, min(1.0, t))

    def _do_pan(cam_a: tuple[int, int], cam_b: tuple[int, int], dur: float):
        start = pygame.time.get_ticks()
        frozen_time = float(globals().get("_time_left_runtime", LEVEL_TIME_LIMIT))
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit();
                    sys.exit()
            now = pygame.time.get_ticks()
            t = min(1.0, (now - start) / max(1.0, dur * 1000.0))
            camx = int(_lerp(cam_a[0], cam_b[0], t))
            camy = int(_lerp(cam_a[1], cam_b[1], t))
            render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots,
                            game_state.obstacles, override_cam=(camx, camy))
            if label:
                font = pygame.font.SysFont(None, 42)
                txt = font.render(label, True, (255, 230, 120))
                screen.blit(txt, txt.get_rect(center=(VIEW_W // 2, INFO_BAR_HEIGHT + 50)))
                pygame.display.flip()
            clock.tick(60)
            if t >= 1.0:
                break

    # cams
    player_cam = _cam_for_player()
    fx, fy = focus_world_px
    focus_cam = _cam_for_world_px(fx, fy)
    start_from = start_cam if start_cam is not None else player_cam
    # start → focus
    _do_pan(start_from, focus_cam, duration_each)
    # hold on focus
    frozen_time = float(globals().get("_time_left_runtime", LEVEL_TIME_LIMIT))
    hold_start = pygame.time.get_ticks()
    while (pygame.time.get_ticks() - hold_start) < int(hold_time * 1000):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit();
                sys.exit()
        render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots,
                        game_state.obstacles, override_cam=focus_cam)
        if label:
            font = pygame.font.SysFont(None, 42)
            txt = font.render(label, True, (255, 230, 120))
            screen.blit(txt, txt.get_rect(center=(VIEW_W // 2, INFO_BAR_HEIGHT + 50)))
            pygame.display.flip()
        clock.tick(60)
    # optional focus → player
    if return_to_player:
        _do_pan(focus_cam, player_cam, duration_each)
    flush_events()


# ==================== 游戏渲染函数 ====================
def render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots, obstacles,
                    override_cam: tuple[int, int] | None = None):
    # 1) 计算以“玩家所在格”为中心的相机
    px_grid = (player.x + player.size / 2) / CELL_SIZE
    py_grid = (player.y + player.size / 2) / CELL_SIZE
    # 将玩家的等距投影放到屏幕中心，得到 cam 偏移d
    pxs, pys = iso_world_to_screen(px_grid, py_grid, 0, 0, 0)
    camx = pxs - VIEW_W // 2
    camy = pys - (VIEW_H - INFO_BAR_HEIGHT) // 2
    # 改为：
    if override_cam is not None:
        camx, camy = override_cam
    else:
        camx, camy = calculate_iso_camera(player.x + player.size * 0.5,
                                          player.y + player.size * 0.5 + INFO_BAR_HEIGHT)
    if hasattr(game_state, "camera_shake_offset"):
        dx, dy = game_state.camera_shake_offset()
        camx += dx
        camy += dy
    screen.fill(MAP_BG)
    # 2) 画“地面网格”（只画视口周围一圈，避免全图遍历）
    #   估算可见格范围
    margin = 3
    # 用一个大致的逆投影范围（足够覆盖屏幕）
    gx_min = max(0, int(px_grid - VIEW_W // ISO_CELL_W) - margin)
    gx_max = min(GRID_SIZE - 1, int(px_grid + VIEW_W // ISO_CELL_W) + margin)
    gy_min = max(0, int(py_grid - VIEW_H // ISO_CELL_H) - margin)
    gy_max = min(GRID_SIZE - 1, int(py_grid + VIEW_H // ISO_CELL_H) + margin)
    grid_col = MAP_GRID
    for gx in range(gx_min, gx_max + 1):
        for gy in range(gy_min, gy_max + 1):
            draw_iso_tile(screen, gx, gy, grid_col, camx, camy, border=1)
    # 2.5) 地面覆盖层：落点提示圈 + 酸池
    # 先画提示圈（空心，颜色来自 TelegraphCircle.color）
    for t in getattr(game_state, "telegraphs", []):
        draw_iso_ground_ellipse(
            screen, t.x, t.y, t.r,
            color=t.color, alpha=180,
            camx=camx, camy=camy,
            fill=False, width=3
        )
    # Skill targeting overlay (range + target marker)
    if getattr(player, "targeting_skill", None):
        skill = player.targeting_skill
        origin = getattr(player, "skill_target_origin", None)
        px, py = origin if (skill == "blast" and origin) else player.rect.center
        cast_range = _skill_cast_range(skill, player) if skill == "blast" else float(TELEPORT_RANGE)
        ring_col = (255, 140, 70) if skill == "blast" else (90, 190, 255)
        draw_iso_ground_ellipse(screen, px, py, cast_range, ring_col, 60, camx, camy, fill=False, width=3)
        tx, ty = getattr(player, "skill_target_pos", (px, py))
        valid = bool(getattr(player, "skill_target_valid", False))
        col_valid = (255, 120, 60) if skill == "blast" else (80, 210, 255)
        col_invalid = (230, 60, 60)
        col = col_valid if valid else col_invalid
        if skill == "blast":
            draw_iso_ground_ellipse(screen, tx, ty, BLAST_RADIUS, col, 90 if valid else 60, camx, camy, fill=False, width=4)
            draw_iso_ground_ellipse(screen, tx, ty, BLAST_RADIUS * 0.4, col, 80 if valid else 50, camx, camy, fill=True)
        else:
            draw_iso_ground_ellipse(screen, tx, ty, max(20, player.size), col, 80 if valid else 50, camx, camy, fill=False, width=4)

    # [UPDATED] Hurricanes (Wind Biome) - Now draws the 3D TornadoEntity
    for h in getattr(game_state, "hurricanes", []):
        # Draw the base ground shadow/influence ring
        pulse = 0.6 + 0.4 * math.sin(pygame.time.get_ticks() * 0.008)
        alpha = int(40 + 60 * pulse)
        draw_iso_ground_ellipse(
            screen, h.x, h.y, h.r * HURRICANE_RANGE_MULT,
            color=(100, 120, 150), alpha=alpha,
            camx=camx, camy=camy,
            fill=False, width=2
        )
        
        # Delegate actual model drawing to the class
        if hasattr(h, "draw"):
            h.draw(screen, camx, camy)
        else:
            # Fallback for old save compatibility if h is a dict
            hx, hy = float(h.get("x", 0)), float(h.get("y", 0))
            draw_iso_ground_ellipse(screen, hx, hy, 40, (100,100,100), 200, camx, camy)

    # Aegis Pulse rings (ground-level hexes)
    for p in getattr(game_state, "aegis_pulses", []):
        age = max(0.0, float(getattr(p, "age", 0.0)))
        delay = max(0.0, float(getattr(p, "delay", 0.0)))
        expand_time = max(0.001, float(getattr(p, "expand_time", AEGIS_PULSE_BASE_EXPAND_TIME)))
        fade_time = max(0.001, float(getattr(p, "fade_time", AEGIS_PULSE_RING_FADE)))
        if age < delay:
            continue
        grow_progress = max(0.0, min(1.0, (age - delay) / expand_time))
        fade_age = age - (delay + expand_time)
        fade = 1.0 if fade_age <= 0 else max(0.0, 1.0 - fade_age / fade_time)
        if fade <= 0:
            continue
        current_r = max(AEGIS_PULSE_MIN_START_R, float(getattr(p, "r", 0.0)) * grow_progress)
        
        draw_iso_hex_ring(
            screen, p.x, p.y, current_r,
            AEGIS_PULSE_COLOR, int(AEGIS_PULSE_RING_ALPHA * fade),
            camx, camy,
            sides=6,
            fill_alpha=int(AEGIS_PULSE_FILL_ALPHA * fade),
            width=2
        )
    # 再画酸池（实心，微透明绿；你也可以做成分层：外圈更亮）
    for a in getattr(game_state, "acids", []):
        draw_iso_ground_ellipse(
            screen, a.x, a.y, a.r,
            color=(60, 200, 90), alpha=110,
            camx=camx, camy=camy,
            fill=True
        )
    # 3) 收集需要按底部Y排序的可绘制体
    drawables = []
    # 3.1 障碍（立体墙砖，按“底边 y + 墙高”排）
    for (gx, gy), ob in game_state.obstacles.items():
        base_col = (120, 120, 120) if ob.type == "Indestructible" else (200, 80, 80)
        if ob.type == "Destructible" and ob.health is not None:
            t = max(0.4, min(1.0, ob.health / float(max(1, OBSTACLE_HEALTH))))
            base_col = (int(200 * t), int(80 * t), int(80 * t))
        top_pts = iso_tile_points(gx, gy, camx, camy)
        sort_y = top_pts[2][1] + (ISO_WALL_Z if WALL_STYLE == "prism" else (12 if WALL_STYLE == "hybrid" else 0))
        if getattr(ob, "type", "") == "Lantern":
            continue
        drawables.append(("wall", sort_y, {"gx": gx, "gy": gy, "color": base_col}))
    # 3.2 地面上的小物：金币 / 治疗（存屏幕像素坐标）
    for s in getattr(game_state, "spoils", []):
        wx, wy = s.base_x / CELL_SIZE, (s.base_y - s.h - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
        drawables.append(("coin", sy, {"cx": sx, "cy": sy, "r": s.r}))
    # auto-turrets (iso)
    for t in getattr(game_state, "turrets", []):
        wx, wy = t.x / CELL_SIZE, (t.y - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
        drawables.append(("turret", sy, {"cx": sx, "cy": sy}))
    for h in getattr(game_state, "heals", []):
        wx, wy = h.base_x / CELL_SIZE, (h.base_y - h.h - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
        drawables.append(("heal", sy, {"cx": sx, "cy": sy, "r": h.r}))
    for it in getattr(game_state, "items", []):
        wx = it.center[0] / CELL_SIZE
        wy = (it.center[1] - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
        drawables.append(("item", sy, {"cx": sx, "cy": sy, "r": it.radius, "main": it.is_main}))
    # 3.3 僵尸 & 玩家（以“脚底点”排序/投影；与残影一致）
    for z in enemies:
        wx = z.rect.centerx / CELL_SIZE
        wy = (z.rect.bottom - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
        drawables.append(("enemy", sy, {"cx": sx, "cy": sy, "z": z}))
    wx = player.rect.centerx / CELL_SIZE
    wy = (player.rect.bottom - INFO_BAR_HEIGHT) / CELL_SIZE
    psx, psy = iso_world_to_screen(wx, wy, 0, camx, camy)
    drawables.append(("player", psy, {"cx": psx, "cy": psy, "p": player}))
    # 3.4 子弹/敌弹（位置也投影后按底部排序）
    if bullets:
        for b in bullets:
            wx, wy = b.x / CELL_SIZE, (b.y - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append((
                "bullet",
                sy,
                {
                    "cx": sx,
                    "cy": sy,
                    "r": int(getattr(b, "r", BULLET_RADIUS)),
                    "src": getattr(b, "source", "player"),
                },
            ))
            drawables.append(("bullet", sy, {"cx": sx, "cy": sy, "r": int(getattr(b, "r", BULLET_RADIUS))}))
    if enemy_shots:
        for es in enemy_shots:
            wx, wy = es.x / CELL_SIZE, (es.y - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            if isinstance(es, MistShot):
                drawables.append(("mistshot", sy, {"cx": sx, "cy": sy, "obj": es}))
            else:
                drawables.append(("eshot", sy, {
                    "cx": sx, "cy": sy,
                    "r": int(getattr(es, "r", BULLET_RADIUS))
                }))
    # 4) 排序后统一绘制（只保留这一段循环）
    drawables.sort(key=lambda x: x[1])
    hell = (getattr(game_state, "biome_active", "") == "Scorched Hell")
    COL_PLAYER_BULLET = (199, 68, 12) if hell else (120, 204, 121)  # color in Hell, white elsewhere
    COL_ENEMY_SHOT = (255, 80, 80) if hell else (255, 120, 50)  # hot red in Hell, orange elsewhere
    for kind, _, data in drawables:
        if kind == "wall":
            gx, gy, col = data["gx"], data["gy"], data["color"]
            if WALL_STYLE == "prism":
                draw_iso_prism(screen, gx, gy, col, camx, camy, wall_h=ISO_WALL_Z)
            elif WALL_STYLE == "hybrid":
                # 1) 低矮“棱台”底座（12px 高）
                draw_iso_prism(screen, gx, gy, col, camx, camy, wall_h=12)
                # 2) 直立占位柱（将来替换为贴图），锚点=脚底 midbottom
                wx, wy = gx + 0.5, gy + 0.5
                sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
                rect_h = int(ISO_CELL_H * 1.8)
                rect_w = int(ISO_CELL_W * 0.35)
                pillar = pygame.Rect(0, 0, rect_w, rect_h)
                pillar.midbottom = (sx, sy)
                pygame.draw.rect(screen, col, pillar, border_radius=rect_w // 3)
            else:
                # billboard：只画顶面，类似《饥荒》平面贴图风格
                draw_iso_tile(screen, gx, gy, col, camx, camy, border=0)
        elif kind == "coin":
            cx, cy, r = data["cx"], data["cy"], data["r"]
            shadow = pygame.Surface((r * 4, r * 2), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, ISO_SHADOW_ALPHA), shadow.get_rect())
            screen.blit(shadow, shadow.get_rect(center=(cx, cy + 6)))
            pygame.draw.circle(screen, (255, 215, 80), (cx, cy), r)
            pygame.draw.circle(screen, (255, 245, 200), (cx, cy), r, 1)
        elif kind == "heal":
            cx, cy, r = data["cx"], data["cy"], data["r"]
            shadow = pygame.Surface((r * 4, r * 2), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, ISO_SHADOW_ALPHA), shadow.get_rect())
            screen.blit(shadow, shadow.get_rect(center=(cx, cy + 6)))
            pygame.draw.circle(screen, (225, 225, 225), (cx, cy), r)
            pygame.draw.rect(screen, (220, 60, 60), pygame.Rect(cx - 2, cy - r + 3, 4, r * 2 - 6))
            pygame.draw.rect(screen, (200, 40, 40), pygame.Rect(cx - r + 3, cy - 2, r * 2 - 6, 4))
        elif kind == "item":
            cx, cy, r = data["cx"], data["cy"], data["r"]
            shadow = pygame.Surface((r * 4, r * 2), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, ISO_SHADOW_ALPHA), shadow.get_rect())
            screen.blit(shadow, shadow.get_rect(center=(cx, cy + 6)))
            # 你可以按 is_main 改颜色/样式
            # 轻微地面辉光
            glow = pygame.Surface((r * 4, r * 2), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (255, 240, 120, 90), glow.get_rect())
            screen.blit(glow, glow.get_rect(center=(cx, cy + 6)))
            # 本体：明黄色
            pygame.draw.circle(screen, (255, 224, 0), (cx, cy), r)
            pygame.draw.circle(screen, (255, 255, 180), (cx, cy), r, 2)
        elif kind == "turret":
            cx, cy = data["cx"], data["cy"]
            base_r = 10
            pygame.draw.circle(screen, (80, 180, 255), (cx, cy), base_r)
            pygame.draw.circle(screen, (250, 250, 255), (cx, cy), base_r - 4, 2)
        elif kind == "bullet":
            cx, cy = data["cx"], data["cy"]
            rad = int(data.get("r", BULLET_RADIUS))
            src = data.get("src", "player")
            if src == "turret":
                color = (0, 255, 255)  # cyan turret bullets (iso)
            else:
                color = COL_PLAYER_BULLET
            pygame.draw.circle(screen, color, (cx, cy), rad)
        elif kind == "eshot":
            rad = int(data.get("r", BULLET_RADIUS))
            pygame.draw.circle(screen, COL_ENEMY_SHOT, (data["cx"], data["cy"]), rad)
        elif kind == "mistshot":
            es = data.get("obj")
            rad = int(getattr(es, "r", BULLET_RADIUS))
            col = getattr(es, "color", HAZARD_STYLES["mist"]["ring"])
            pygame.draw.circle(screen, col, (data["cx"], data["cy"]), rad)
        elif kind == "enemy":
            z, cx, cy = data["z"], float(data["cx"]), float(data["cy"])
            if getattr(z, "type", "") == "bandit" and getattr(z, "radar_tagged", False):
                base_rr = max(24, int(getattr(z, "radius", 0) * 4.0))
                phase = float(getattr(z, "radar_ring_phase", 0.0))
                pulse = 1.0 + 0.10 * math.sin(math.tau * phase)
                ring_r = max(20, int(base_rr * pulse))
                draw_iso_ground_ellipse(
                    screen,
                    z.rect.centerx,
                    z.rect.centery,
                    ring_r,
                    (255, 60, 60),
                    220,
                    camx,
                    camy,
                    fill=False,
                    width=4,
                )
            shake = float(getattr(z, "_comet_shake", 0.0))
            if shake > 0.0:
                amp = min(6.0, 10.0 * shake)
                t = pygame.time.get_ticks() * 0.02 + z.rect.x * 0.03 + z.rect.y * 0.01
                cx += math.sin(t) * amp
                cy += math.cos(t * 1.4) * amp * 0.6
            cx = int(round(cx))
            cy = int(round(cy))
            player_size = int(CELL_SIZE * 0.6)
            if getattr(z, "is_boss", False) or getattr(z, "type", "") == "ravager":
                draw_size = max(player_size, int(z.rect.w))
            else:
                draw_size = player_size  # match player footprint to avoid getting stuck
            # shadow scaled to body size
            sh_w = max(8, int(draw_size * 0.9))
            sh_h = max(4, int(draw_size * 0.45))
            sh = pygame.Surface((sh_w, sh_h), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, ISO_SHADOW_ALPHA), sh.get_rect())
            screen.blit(sh, sh.get_rect(center=(cx, cy + 6)))
            body = pygame.Rect(0, 0, draw_size, draw_size)
            body.midbottom = (cx, cy)
            # 拾取光晕（金色）
            if getattr(z, "_gold_glow_t", 0.0) > 0.0:
                glow = pygame.Surface((int(draw_size * 1.6), int(draw_size * 1.0)), pygame.SRCALPHA)
                alpha = int(120 * (z._gold_glow_t / Z_GLOW_TIME))
                pygame.draw.ellipse(glow, (255, 220, 90, max(30, alpha)), glow.get_rect())
                screen.blit(glow, glow.get_rect(center=(cx, cy)))
            # 本体
            base_col = ENEMY_COLORS.get(getattr(z, "type", "basic"), (255, 60, 60))
            col = getattr(z, "_current_color", getattr(z, "color", base_col))
            flash = float(getattr(z, "_comet_flash", 0.0))
            if flash > 0.0:
                f = min(1.0, flash * 2.8)
                col = (
                    min(255, int(col[0] + (255 - col[0]) * f)),
                    min(255, int(col[1] + (255 - col[1]) * f)),
                    min(255, int(col[2] + (255 - col[2]) * f)),
                )
            pygame.draw.rect(screen, col, body)
            if not getattr(z, "is_boss", False):
                outline_rect = body.inflate(6, 6)
                pygame.draw.rect(screen, (230, 210, 230), outline_rect, 2, border_radius=4)
            if getattr(z, "shield_hp", 0) > 0:
                draw_shield_outline(screen, body)
            # 强化视觉：持币较多时加金色外轮廓
            coins = int(getattr(z, "spoils", 0))
            if coins >= Z_SPOIL_SPD_STEP:
                pygame.draw.rect(screen, (255, 215, 0), body, 3)
            elif coins >= Z_SPOIL_ATK_STEP:
                pygame.draw.rect(screen, (220, 180, 80), body, 2)
            dot_ratio, dot_count = dot_rounds_visual_state(z)
            if dot_ratio > 0.0:
                glow_w = max(12, int(draw_size * 1.1))
                glow_h = max(8, int(draw_size * 0.7))
                glow_alpha = int(120 * dot_ratio)
                glow = pygame.Surface((glow_w, glow_h), pygame.SRCALPHA)
                pygame.draw.ellipse(
                    glow,
                    (DOT_ROUNDS_GLOW_COLOR[0], DOT_ROUNDS_GLOW_COLOR[1], DOT_ROUNDS_GLOW_COLOR[2], glow_alpha),
                    glow.get_rect(),
                    width=2,
                )
                glow_rect = glow.get_rect(center=(cx, body.centery - 4))
                screen.blit(glow, glow_rect)
                orb_count = min(2, dot_count)
                if orb_count > 0:
                    orb_surf = pygame.Surface((glow_w, glow_h), pygame.SRCALPHA)
                    orb_alpha = int(200 * dot_ratio)
                    ocx, ocy = glow_w // 2, glow_h // 2
                    orbit_r = max(6, int(draw_size * 0.45))
                    t = pygame.time.get_ticks() * 0.004
                    for i in range(orb_count):
                        ang = t + i * math.tau / max(1, orb_count)
                        ox = int(math.cos(ang) * orbit_r)
                        oy = int(math.sin(ang) * orbit_r * 0.6)
                        pygame.draw.circle(
                            orb_surf, (200, 255, 255, orb_alpha),
                            (ocx + ox, ocy + oy), 2,
                        )
                        pygame.draw.circle(
                            orb_surf, (255, 255, 255, max(40, orb_alpha - 80)),
                            (ocx + ox, ocy + oy), 1,
                        )
                    screen.blit(orb_surf, glow_rect.topleft)
            # Bandit-only HP bar for readability
            if getattr(z, "type", "") == "bandit":
                bar_w = draw_size
                bar_h = 5
                bar_bg = pygame.Rect(0, 0, bar_w, bar_h)
                bar_bg.midbottom = (cx, body.top - 6)
                pygame.draw.rect(screen, (30, 30, 30), bar_bg, border_radius=2)
                mhp = float(max(1, getattr(z, "max_hp", 1)))
                hp_ratio = 0.0 if mhp <= 0 else max(0.0, min(1.0, float(getattr(z, "hp", 0)) / mhp))
                if hp_ratio > 0:
                    fill = pygame.Rect(bar_bg.left + 1, bar_bg.top + 1, int((bar_w - 2) * hp_ratio), bar_h - 2)
                    pygame.draw.rect(screen, (210, 70, 70), fill, border_radius=2)
            # 头顶显示金币数量
            if coins > 0:
                f = pygame.font.SysFont(None, 18)
                txt = f.render(f"{coins}", True, (255, 225, 120))
                screen.blit(txt, txt.get_rect(midbottom=(cx, body.top - 4)))
            if z.is_boss: pygame.draw.rect(screen, (255, 215, 0), body.inflate(4, 4), 3)
            pygame.draw.rect(screen, col, body)
            flash_t = float(getattr(z, "_hit_flash", 0.0))
            if flash_t > 0.0 and HIT_FLASH_DURATION > 0:
                flash_ratio = min(1.0, flash_t / HIT_FLASH_DURATION)
                overlay = pygame.Surface(body.size, pygame.SRCALPHA)
                overlay.fill((255, 255, 255, int(200 * flash_ratio)))
                screen.blit(overlay, body.topleft)
            mark_t = float(getattr(z, "_vuln_mark_t", 0.0))
            if mark_t > 0.0:
                flash = float(getattr(z, "_vuln_hit_flash", 0.0))
                lvl_vis = int(getattr(z, "_vuln_mark_level", 1))
                lvl_vis = max(1, min(lvl_vis, len(VULN_MARK_DURATIONS)))
                dur_vis = VULN_MARK_DURATIONS[lvl_vis - 1]
                rem_ratio = max(0.0, min(1.0, mark_t / max(0.001, dur_vis)))
                phase = (globals().get("mark_pulse_time", 0.0) % MARK_PULSE_PERIOD) / MARK_PULSE_PERIOD
                pulse = 0.5 + 0.5 * math.sin(phase * math.tau)
                scale = MARK_PULSE_MIN_SCALE + (MARK_PULSE_MAX_SCALE - MARK_PULSE_MIN_SCALE) * pulse
                base_size = max(18, int(draw_size * 0.9))
                size = int(base_size * scale)
                alpha = int(
                    (MARK_PULSE_MIN_ALPHA + (MARK_PULSE_MAX_ALPHA - MARK_PULSE_MIN_ALPHA) * pulse)
                    * rem_ratio
                )
                alpha = int(min(255, alpha + int(80 * min(1.0, flash))))
                mark_rect = pygame.Rect(0, 0, size, size)
                mark_rect.midbottom = (cx, body.top - 6)

                def draw_tapered_line(surf, color_rgba, p0, p1, w0, w1):
                    # build a quad whose width tapers from w0 at p0 to w1 at p1
                    dx, dy = (p1[0] - p0[0], p1[1] - p0[1])
                    L = (dx * dx + dy * dy) ** 0.5 or 1.0
                    nx, ny = -dy / L, dx / L
                    hw0 = w0 * 0.5
                    hw1 = w1 * 0.5
                    pts = [
                        (p0[0] + nx * hw0, p0[1] + ny * hw0),
                        (p0[0] - nx * hw0, p0[1] - ny * hw0),
                        (p1[0] - nx * hw1, p1[1] - ny * hw1),
                        (p1[0] + nx * hw1, p1[1] + ny * hw1),
                    ]
                    pygame.draw.polygon(surf, color_rgba, pts)

                def draw_tapered_x(surf, size_px, outline_col, fill_col):
                    c = size_px * 0.5
                    a = size_px * 0.2
                    b = size_px * 0.8
                    thick_center = max(3.0, size_px * 0.22)
                    thin_tip = max(1.5, thick_center * 0.35)
                    # outline (larger)
                    draw_tapered_line(surf, outline_col, (a, a), (b, b), thin_tip * 1.8, thick_center * 1.85)
                    draw_tapered_line(surf, outline_col, (b, a), (a, b), thin_tip * 1.8, thick_center * 1.85)
                    # inner fill (smaller)
                    draw_tapered_line(surf, fill_col, (a, a), (b, b), thin_tip, thick_center)
                    draw_tapered_line(surf, fill_col, (b, a), (a, b), thin_tip, thick_center)

                red_col = (
                    int(MARK_PULSE_DARK[0] + (MARK_PULSE_BRIGHT[0] - MARK_PULSE_DARK[0]) * pulse),
                    int(MARK_PULSE_DARK[1] + (MARK_PULSE_BRIGHT[1] - MARK_PULSE_DARK[1]) * pulse),
                    int(MARK_PULSE_DARK[2] + (MARK_PULSE_BRIGHT[2] - MARK_PULSE_DARK[2]) * pulse),
                    max(0, min(255, alpha)),
                )
                black_col = (0, 0, 0, max(0, min(255, alpha)))
                mark = pygame.Surface(mark_rect.size, pygame.SRCALPHA)
                draw_tapered_x(mark, size, black_col, red_col)
                screen.blit(mark, mark_rect)
            if getattr(z, "shield_hp", 0) > 0:
                draw_shield_outline(screen, body)
        elif kind == "player":
            p, cx, cy = data["p"], data["cx"], data["cy"]
            player_size = int(CELL_SIZE * 0.6)  # match footprint used in collisions
            sh_w = max(8, int(player_size * 0.9))
            sh_h = max(4, int(player_size * 0.45))
            sh = pygame.Surface((sh_w, sh_h), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, ISO_SHADOW_ALPHA), sh.get_rect())
            screen.blit(sh, sh.get_rect(center=(cx, cy + 6)))
            rect = pygame.Rect(0, 0, player_size, player_size);
            rect.midbottom = (cx, cy)
            col = (240, 80, 80) if (p.hit_cd > 0 and (pygame.time.get_ticks() // 80) % 2 == 0) else (0, 255, 0)
            pygame.draw.rect(screen, col, rect)
            pygame.draw.rect(screen, (80, 220, 255), rect.inflate(6, 6), 2, border_radius=4)
            flash_t = float(getattr(p, "_hit_flash", 0.0))
            if flash_t > 0.0 and HIT_FLASH_DURATION > 0:
                flash_ratio = min(1.0, flash_t / HIT_FLASH_DURATION)
                overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
                overlay.fill((255, 255, 255, int(200 * flash_ratio)))
                screen.blit(overlay, rect.topleft)
            carapace_hp = int(getattr(p, "carapace_hp", 0))
            total_shield = int(getattr(p, "shield_hp", 0)) + carapace_hp
            if total_shield > 0:
                draw_shield_outline(screen, rect)
            if carapace_hp > 0:
                glow_rect = rect.inflate(18, 18)
                glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
                alpha = min(200, 80 + carapace_hp * 3 // 2)
                pygame.draw.ellipse(glow, (70, 200, 255, max(60, alpha - 40)), glow.get_rect(), width=4)
                fill_alpha = max(30, alpha - 100)
                pygame.draw.ellipse(glow, (40, 140, 255, fill_alpha), glow.get_rect())
                screen.blit(glow, glow_rect)
            plating_hp = int(getattr(p, "bone_plating_hp", 0))
            if plating_hp > 0:
                armor_rect = rect.inflate(16, 10)
                armor = pygame.Surface(armor_rect.size, pygame.SRCALPHA)
                glow_ratio = max(0.43, min(1.0, float(getattr(p, "_bone_plating_glow", 0.0))))
                edge_alpha = min(220, 80 + plating_hp // 2)
                inner_alpha = int((BONE_PLATING_GLOW[3] if len(BONE_PLATING_GLOW) > 3 else 140) * glow_ratio)
                pygame.draw.rect(
                    armor,
                    (BONE_PLATING_COLOR[0], BONE_PLATING_COLOR[1], BONE_PLATING_COLOR[2], edge_alpha),
                    armor.get_rect(),
                    width=2,
                    border_radius=10
                )
                pygame.draw.rect(
                    armor,
                    (BONE_PLATING_GLOW[0], BONE_PLATING_GLOW[1], BONE_PLATING_GLOW[2], inner_alpha),
                    armor.get_rect(),
                    border_radius=10
                )
                screen.blit(armor, armor_rect)
                if int(getattr(p, "bone_plating_level", 0)) >= BONE_PLATING_MAX_LEVEL:
                    cx, cy = rect.centerx, rect.top - 6
                    sparkle = [
                        (cx, cy - 3),
                        (cx + 3, cy),
                        (cx, cy + 3),
                        (cx - 3, cy)
                    ]
                    pygame.draw.polygon(screen, BONE_PLATING_COLOR, sparkle, width=1)
    # --- damage numbers (iso) ---
    for d in getattr(game_state, "dmg_texts", []):
        # 世界像素 -> 格 -> 等距投影
        wx = d.x / CELL_SIZE
        wy = (d.y - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
        sy += d.screen_offset_y()
        # 颜色：HP=红/白，护盾=蓝
        color_map = {
            "shield": ((120, 200, 255), (120, 200, 255)),
            "aegis": (AEGIS_PULSE_COLOR, AEGIS_PULSE_COLOR),
            "hp_player": ((255, 255, 255), (255, 255, 220)),
            "dot": ((86, 141, 86), (86, 141, 86)),
            "hp_enemy": ((255, 60, 60), (255, 140, 140)),
        }
        normal, crit = color_map.get(d.kind, ((255, 100, 100), (255, 240, 120)))
        col = crit if d.crit else normal
        size = DMG_TEXT_SIZE_NORMAL if not d.crit else DMG_TEXT_SIZE_CRIT
        font = pygame.font.SysFont(None, size, bold=d.crit)
        surf = font.render(str(d.amount), True, col)
        surf.set_alpha(d.alpha())
        screen.blit(surf, surf.get_rect(center=(int(sx), int(sy))))
    # Skill targeting overlay drawn on top of obstacles so it never appears blocked
    _draw_skill_overlay(screen, player, camx, camy)
    for g in getattr(game_state, "ghosts", []):
        g.draw_iso(screen, camx, camy)
    game_state.draw_hazards_iso(screen, camx, camy)
    if hasattr(game_state, "draw_comet_blasts"):
        game_state.draw_comet_blasts(screen, camx, camy)
    if hasattr(game_state, "draw_comet_corpses"):
        game_state.draw_comet_corpses(screen, camx, camy)
    if getattr(game_state, "fog_enabled", False):
        game_state.draw_fog_overlay(screen, camx, camy, player, obstacles)
    if USE_ISO:
        game_state.draw_lanterns_iso(screen, camx, camy)
    else:
        game_state.draw_lanterns_topdown(screen, camx, camy)
    # --- DRAW PARTICLES (ISO CORRECTED) ---
    if hasattr(game_state, "fx"):
        # We manually iterate particles to apply Isometric Projection
        for p in game_state.fx.particles:
            if p.size < 1: continue
            
            # 1. Convert World Pixels -> Grid Coordinates
            gx = p.x / CELL_SIZE
            gy = (p.y - INFO_BAR_HEIGHT) / CELL_SIZE
            
            # 2. Project Grid -> Isometric Screen Coordinates
            # (Using the same function your walls/enemies use)
            sx, sy = iso_world_to_screen(gx, gy, 0, camx, camy)
            
            # 3. Draw the glow
            # We access GlowCache directly (imported from effects)
            glow = GlowCache.get_glow_surf(p.size, p.color)
            
            # Center the particle image at the projected screen coordinates
            screen.blit(glow, (sx - p.size, sy - p.size), special_flags=pygame.BLEND_ADD)
    # 5) 顶层 HUD（沿用你现有 HUD 代码即可）
    #    直接调用原 render_game 里“顶栏 HUD 的那段”（从画黑色 InfoBar 开始，到金币/物品文字结束）
    #    —— 为避免重复代码，可以把那段 HUD 抽成一个小函数，这里调用即可。
    draw_ui_topbar(screen, game_state, player, time_left=globals().get("_time_left_runtime"))
    bosses = _find_all_bosses(enemies)
    if len(bosses) >= 2:
        draw_boss_hp_bars_twin(screen, bosses[:2])
    elif len(bosses) == 1:
        draw_boss_hp_bar(screen, bosses[0])
    run_pending_menu_transition(screen)
    pygame.display.flip()
    return screen.copy()


def render_game(screen: pygame.Surface, game_state, player: Player, enemies: List[Enemy],
                bullets: Optional[List['Bullet']] = None,
                enemy_shots: Optional[List[EnemyShot]] = None,
                override_cam: tuple[int, int] | None = None) -> pygame.Surface:
    """
    Legacy top-down renderer.
    We now use the isometric renderer for everything, but keep this wrapper
    so old call sites (fail screen, etc.) still work without errors.
    """
    if bullets is None:
        bullets = []
    if enemy_shots is None:
        enemy_shots = []
    # Ignore override_cam and just use the main iso renderer
    return render_game_iso(
        screen, game_state, player, enemies, bullets, enemy_shots,
        obstacles=game_state.obstacles,
        override_cam=override_cam
    )


# ==================== GAMESOUND ====================
class GameSound:
    """
    Background BGM loader/controller.
    It probes several likely paths so ZGAME.wav is found regardless of where ZGame.py runs from.
    """

    def __init__(self, music_path: str = None, volume: float = 0.6):
        self.volume = max(0.0, min(1.0, float(volume)))
        self._ready = False
        # --- pick a path ---
        here = os.path.dirname(__file__) if "__file__" in globals() else os.getcwd()
        candidates = [
            # preferred intro BGM
            os.path.join(here, "assets", "Intro_V0.wav"),
            os.path.join(here, "Z_Game", "assets", "Intro_V0.wav"),
            os.path.join(os.getcwd(), "assets", "Intro_V0.wav"),
            os.path.join(os.getcwd(), "Z_Game", "assets", "Intro_V0.wav"),
            # project-typical
            os.path.join(here, "Z_Game", "assets", "ZGAME.wav"),
            os.path.join(here, "assets", "ZGAME.wav"),
            # run-from-working-dir
            os.path.join(os.getcwd(), "Z_Game", "assets", "ZGAME.wav"),
            os.path.join(os.getcwd(), "assets", "ZGAME.wav"),
            # user-provided absolute-like hint (DON'T rely on drive root)
            r"C:\Users\%USERNAME%\Z_Game\assets\ZGAME.wav".replace("%USERNAME%", os.environ.get("USERNAME", "")),
        ]
        if music_path:
            candidates.insert(0, music_path)
        self.music_path = None
        for p in candidates:
            if p and os.path.exists(p):
                self.music_path = p
                break
        if not self.music_path:
            print("[Audio] ZGAME.wav not found in expected locations.")
            return
        # --- init mixer (make sure it's initialized even if pygame.init() already ran) ---
        try:
            if not pygame.mixer.get_init():
                # pre_init only helps if called before pygame.init(); guard anyway
                pygame.mixer.pre_init(44100, -16, 2, 512)
                pygame.mixer.init(44100, -16, 2, 512)
        except Exception as e:
            print(f"[Audio] mixer init failed: {e}")
            return
        # --- load file ---
        try:
            pygame.mixer.music.load(self.music_path)
            pygame.mixer.music.set_volume(self.volume)
            self._ready = True
            print(f"[Audio] Loaded BGM: {self.music_path}")
        except Exception as e:
            print(f"[Audio] load music failed: {e} (path tried: {self.music_path})")

    def playBackGroundMusic(self, loops: int = -1, fade_ms: int = 500):
        """loops=-1 means infinite loop"""
        if not self._ready:
            return
        try:
            pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)
        except Exception as e:
            print(f"[Audio] play failed: {e}")

    def stop(self, fade_ms: int = 300):
        if not self._ready: return
        try:
            if fade_ms > 0:
                pygame.mixer.music.fadeout(fade_ms)
            else:
                pygame.mixer.music.stop()
        except Exception as e:
            print(f"[Audio] stop failed: {e}")

    def pause(self):
        if self._ready:
            try:
                pygame.mixer.music.pause()
            except Exception as e:
                print(f"[Audio] pause failed: {e}")

    def resume(self):
        if self._ready:
            try:
                pygame.mixer.music.unpause()
            except Exception as e:
                print(f"[Audio] resume failed: {e}")

    def set_volume(self, volume: float):
        self.volume = max(0.0, min(1.0, float(volume)))
        if self._ready:
            try:
                pygame.mixer.music.set_volume(self.volume)
            except Exception as e:
                print(f"[Audio] set_volume failed: {e}")


def _play_bgm_candidates(candidates: list[str], volume: float = 0.6, fadeout_ms: int = 400):
    """Stop current BGM and play the first existing file in candidates."""
    global _bgm, _neuro_viz, _neuro_viz_loader, _neuro_viz_loader_path
    try:
        if "_bgm" in globals() and getattr(_bgm, "stop", None):
            try:
                _bgm.stop(fade_ms=fadeout_ms)
            except Exception:
                pass
        path = next((p for p in candidates if p and os.path.exists(p)), None)
        if not path:
            return False
        _bgm = GameSound(music_path=path, volume=volume)
        _bgm.playBackGroundMusic()
        
        # --- MODIFIED: Load into NeuroVisualizer instead of intro_envelope ---
        # Heavy librosa analysis can hitch the first frame; load it asynchronously.
        def _kickoff_load(p: str):
            global _neuro_viz_loader, _neuro_viz_loader_path
            if not _neuro_viz:
                return
            # Avoid duplicate loaders on the same path
            if _neuro_viz_loader and _neuro_viz_loader.is_alive() and _neuro_viz_loader_path == p:
                return
            def _worker():
                try:
                    _neuro_viz.load_music(p)
                except Exception as e:
                    print(f"[AudioAnalyzer] async load failed for {p}: {e}")
            _neuro_viz_loader_path = p
            _neuro_viz_loader = threading.Thread(target=_worker, daemon=True)
            _neuro_viz_loader.start()
        
        _kickoff_load(path)
            
        return True
    except Exception as e:
        print(f"[Audio] bgm swap failed: {e}")
        return False



def play_intro_bgm():
    """Play Intro_V0 if present (home/start), fallback to ZGAME.wav."""
    here = os.path.dirname(__file__) if "__file__" in globals() else os.getcwd()
    intro_candidates = [
        os.path.join(here, "assets", "Intro_V0.wav"),
        os.path.join(here, "Z_Game", "assets", "Intro_V0.wav"),
        os.path.join(os.getcwd(), "assets", "Intro_V0.wav"),
        os.path.join(os.getcwd(), "Z_Game", "assets", "Intro_V0.wav"),
        # fallback
        os.path.join(here, "assets", "ZGAME.wav"),
        os.path.join(here, "Z_Game", "assets", "ZGAME.wav"),
        os.path.join(os.getcwd(), "assets", "ZGAME.wav"),
        os.path.join(os.getcwd(), "Z_Game", "assets", "ZGAME.wav"),
    ]
    _play_bgm_candidates(intro_candidates, volume=BGM_VOLUME / 100.0)


def play_combat_bgm():
    """Play the main combat/shop track (ZGAME.wav)."""
    here = os.path.dirname(__file__) if "__file__" in globals() else os.getcwd()
    combat_candidates = [
        os.path.join(here, "assets", "ZGAME.wav"),
        os.path.join(here, "Z_Game", "assets", "ZGAME.wav"),
        os.path.join(os.getcwd(), "assets", "ZGAME.wav"),
        os.path.join(os.getcwd(), "Z_Game", "assets", "ZGAME.wav"),
    ]
    _play_bgm_candidates(combat_candidates, volume=BGM_VOLUME / 100.0)


# ==================== 游戏主循环 ====================
def main_run_level(config, chosen_enemy_type: str) -> Tuple[str, Optional[str], pygame.Surface]:
    pygame.display.set_caption("Enemy Card Game – Level")
    screen = pygame.display.get_surface()
    clock = pygame.time.Clock()
    game_state = None
    wanted_active_for_level = False
    # --- initialize time_left before creating game_state, using global current_level ---
    level_idx = int(globals().get("current_level", 0))
    if level_idx == 0:
        META["run_items_spawned"] = 0
        META["run_items_collected"] = 0
    globals()["_run_items_spawned_start"] = int(META.get("run_items_spawned", 0))
    globals()["_run_items_collected_start"] = int(META.get("run_items_collected", 0))
    time_left = float(BOSS_TIME_LIMIT) if is_boss_level(level_idx) else float(LEVEL_TIME_LIMIT)
    globals()["_time_left_runtime"] = time_left
    globals()["_coins_at_level_start"] = int(META.get("spoils", 0))
    play_combat_bgm()
   
    spatial = SpatialHash(SPATIAL_CELL)
    obstacles, items, player_start, enemy_starts, main_item_list, decorations = generate_game_entities(
        grid_size=GRID_SIZE,
        obstacle_count=config["obstacle_count"],
        item_count=config["item_count"],
        enemy_count=config["enemy_count"],
        main_block_hp=config["block_hp"],
        level_idx=level_idx
    )
    last_counted_level = globals().get("_items_counted_level")
    if last_counted_level != level_idx:
        META["run_items_spawned"] = int(META.get("run_items_spawned", 0)) + len(items)
        globals()["_items_counted_level"] = level_idx
    # 生成完 obstacles 后 —— 调用兜底
    ensure_passage_budget(obstacles, GRID_SIZE, player_start)
    game_state = GameState(obstacles, items, main_item_list, decorations)
    game_state.current_level = current_level
    game_state.bandit_spawned_this_level = False
    wp = int(META.get("wanted_poster_waves", 0))
    if wp > 0:
        META["wanted_poster_waves"] = max(0, wp - 1)
        META["wanted_active"] = True
        wanted_active_for_level = True
    else:
        META["wanted_active"] = False
    game_state.wanted_wave_active = bool(META.get("wanted_active", False))
    # --- use boss-specific time limit AFTER game_state exists ---
    level_idx = int(getattr(game_state, "current_level", 0))  # 0-based inside code
    time_left = float(BOSS_TIME_LIMIT) if is_boss_level(level_idx) else float(LEVEL_TIME_LIMIT)
    globals()["_time_left_runtime"] = time_left
    player = Player(player_start, speed=PLAYER_SPEED)
    player.fire_cd = 0.0
    apply_player_carry(player, globals().get("_carry_player_state"))
    # If we're re-entering the same level, reuse its biome so restarts keep the environment/buffs
    if int(globals().get("_baseline_for_level", -1)) == int(current_level):
        baseline = globals().get("_player_level_baseline", None)
        if isinstance(baseline, dict) and baseline.get("biome") is not None:
            globals()["_next_biome"] = baseline.get("biome")
    apply_domain_buffs_for_level(game_state, player)
    if hasattr(player, "on_level_start"):
        player.on_level_start()
    globals()["_next_biome"] = None
    # --- Auto-turrets from META ---
    turret_level = int(META.get("auto_turret_level", 0))
    turrets: List[AutoTurret] = []
    if turret_level > 0:
        # place N turrets evenly around the player
        for i in range(turret_level):
            angle = 2.0 * math.pi * i / max(1, turret_level)
            off_x = math.cos(angle) * AUTO_TURRET_OFFSET_RADIUS
            off_y = math.sin(angle) * AUTO_TURRET_OFFSET_RADIUS
            turrets.append(AutoTurret(player, (off_x, off_y)))
    # --- Stationary turrets from META ---
    stationary_count = int(META.get("stationary_turret_count", 0))
    if stationary_count > 0:
        for _ in range(stationary_count):
            # try a few times to find a clear tile (no obstacle)
            for _attempt in range(40):
                gx = random.randrange(GRID_SIZE)
                gy = random.randrange(GRID_SIZE)
                if (gx, gy) in game_state.obstacles:
                    continue  # tile blocked by obstacle, retry
                # center of the tile in world coords (respect INFO_BAR_HEIGHT)
                wx = gx * CELL_SIZE + CELL_SIZE // 2
                wy = gy * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT
                turrets.append(StationaryTurret(wx, wy))
                break
    game_state.turrets = turrets
    ztype_map = {
        "enemy_fast": "fast",
        "enemy_tank": "tank",
        "enemy_strong": "strong",
        "basic": "basic"
    }
    zt = ztype_map.get(chosen_enemy_type, "basic")
    enemies = [Enemy(pos, speed=ENEMY_SPEED, ztype=zt) for pos in enemy_starts]
    bullets: List[Bullet] = []
    enemy_shots: List[EnemyShot] = []
    # wave spawn state
    spawn_timer = 0.0
    wave_index = 0

    def player_center():
        return player.x + player.size / 2, player.y + player.size / 2 + INFO_BAR_HEIGHT

    def pick_enemy_type_weighted():
        # 可按关卡/波次调整，这里给一个基础权重
        table = [
            ("basic", 50),
            ("fast", 15),
            ("tank", 10),
            ("ranged", 12),
            ("suicide", 8),
            ("buffer", 3),
            ("shielder", 2),
        ]
        r = random.uniform(0, sum(w for _, w in table))
        acc = 0
        for t, w in table:
            acc += w
            if r <= acc:
                return t
        return "basic"

    def find_spawn_positions(n: int) -> List[Tuple[int, int]]:
        # 不在阻挡、玩家、主物品位置；尽量远离玩家
        all_pos = [(x, y) for x in range(GRID_SIZE) for y in range(GRID_SIZE)]
        blocked = set(game_state.obstacles.keys()) | set((i.x, i.y) for i in game_state.items)
        px, py = player.pos
        cand = [p for p in all_pos if p not in blocked and abs(p[0] - px) + abs(p[1] - py) >= 6]
        random.shuffle(cand)
        # 也避免直接与现有僵尸重叠
        zcells = {(int((z.x + z.size // 2) // CELL_SIZE), int((z.y + z.size // 2) // CELL_SIZE)) for z in enemies}
        out = []
        for p in cand:
            if p in zcells: continue
            out.append(p)
            if len(out) >= n: break
        return out

    def find_target():
        # 玩家中心（像素）
        px, py = player.rect.centerx, player.rect.centery
        # 玩家格坐标（用于“两格内”判断）
        pgx = int(px // CELL_SIZE)
        pgy = int((py - INFO_BAR_HEIGHT) // CELL_SIZE)
        # 1) 两格内是否有可破坏障碍？有 → 直接优先最近的那一个
        force_blocks = []
        for gp, ob in game_state.obstacles.items():
            if getattr(ob, "type", "") != "Destructible":
                continue
            gx, gy = gp
            manh = abs(gx - pgx) + abs(gy - pgy)  # 曼哈顿距离（格）
            if manh <= int(PLAYER_BLOCK_FORCE_RANGE_TILES):
                cx, cy = ob.rect.centerx, ob.rect.centery
                d2 = (cx - px) ** 2 + (cy - py) ** 2
                force_blocks.append((d2, ('block', gp, ob, cx, cy)))
        if force_blocks:
            force_blocks.sort(key=lambda t: t[0])  # 最近优先
            best_tuple = force_blocks[0][1]
            d = (force_blocks[0][0]) ** 0.5
            return best_tuple, d
        # 2) 正常权重选择（仅考虑“射程内”的目标）
        cur_range = clamp_player_range(getattr(player, "range", PLAYER_RANGE_DEFAULT))
        R2 = cur_range ** 2
        # 收集候选：僵尸（射程内）
        z_cands = []
        for z in enemies:
            cx, cy = z.rect.centerx, z.rect.centery
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 <= R2:
                z_cands.append((z, cx, cy, d2))
        # 收集候选：可破坏障碍（射程内）
        b_cands = []
        for gp, ob in game_state.obstacles.items():
            if getattr(ob, "type", "") != "Destructible":
                continue
            cx, cy = ob.rect.centerx, ob.rect.centery
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 <= R2:
                b_cands.append((gp, ob, cx, cy, d2))
        # 射程内什么都没有 → 没目标
        if not z_cands and not b_cands:
            return (None, None)
        # 权重评分：
        # - 基于距离的衰减：基础分 = -d2 * k（d2 越小，分越高）
        # - 僵尸优先：加较高常数；障碍其次：加较低常数
        #   （权重不要过大，否则完全遮蔽距离差异）
        DIST_K = 1e-4
        W_ENEMY = 1200.0
        W_BLOCK = 800.0
        best = None
        best_score = -1e18
        # 僵尸优先（仍受距离影响）
        for z, cx, cy, d2 in z_cands:
            s = -d2 * DIST_K + W_ENEMY
            # 若想进一步区分类型，可在此额外加分（例如自爆怪、远程怪等）
            if s > best_score:
                best_score = s
                best = ('enemy', None, z, cx, cy, d2)
        # 障碍次之（仍受距离影响）
        for gp, ob, cx, cy, d2 in b_cands:
            s = -d2 * DIST_K + W_BLOCK
            if s > best_score:
                best_score = s
                best = ('block', gp, ob, cx, cy, d2)
        if best is None:
            return (None, None)
        kind, gp_or_none, obj, cx, cy, d2 = best
        return (kind, gp_or_none, obj, cx, cy), (d2 ** 0.5)

    # Back-compat: if we have a baseline for this level but no consumable snapshot (older saves),
    # seed it from current META so restarts can still restore shields/charges.
    if (int(globals().get("_baseline_for_level", -999)) == int(current_level)
            and "_consumable_baseline" not in globals()):
        globals()["_consumable_baseline"] = {
            "carapace_shield_hp": int(META.get("carapace_shield_hp", 0)),
            "wanted_poster_waves": int(META.get("wanted_poster_waves", 0)),
            "wanted_active": bool(META.get("wanted_active", False)),
        }

    # Assume current_level is the 0-based level index used everywhere else
    if int(globals().get("_baseline_for_level", -999)) != int(current_level):
        # First time entering this level in this run → capture
        _capture_level_start_baseline(current_level, player, game_state)
    else:
        # We had already entered this same level earlier in this run → restore for a clean restart
        _restore_level_start_baseline(current_level, player, game_state)
    # Initial spawn: use threat budget once
    spawned = spawn_wave_with_budget(game_state, player, current_level, wave_index, enemies, ENEMY_CAP)
    if spawned > 0:
        wave_index += 1
        globals()["_max_wave_reached"] = max(globals().get("_max_wave_reached", 0), wave_index)
    player._hit_flash = 0.0
    player._flash_prev_hp = int(player.hp)
    for z in enemies:
        z._hit_flash = 0.0
        z._flash_prev_hp = int(getattr(z, "hp", 0))
    running = True
    game_result = None
    last_frame = None
    clock.tick(60)
    entry_freeze = 0.4  # pause briefly on entry to prevent over-firing bursts
    while running:
        dt = clock.tick(60) / 1000.0
        if entry_freeze > 0:
            entry_freeze = max(0.0, entry_freeze - dt)
            for event in pygame.event.get():
                if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            update_hit_flash_timer(player, dt)
            for z in enemies:
                update_hit_flash_timer(z, dt)
            last_frame = render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots,
                                         obstacles=game_state.obstacles)
            continue
        # ==== 消费镜头聚焦请求：完全暂停游戏与计时 ====
        pf = getattr(game_state, "pending_focus", None)
        if pf:
            fkind, (fx, fy) = pf
            play_focus_cinematic_iso(
                screen, clock,
                game_state, player,
                enemies, bullets, enemy_shots,
                (fx, fy),
                label=("BANDIT!" if fkind == "bandit" else "BOSS!")
            )
            game_state.pending_focus = None  # 演出结束清空
        # --- Consume camera focus queue (bandit & bosses) ---
        fq = getattr(game_state, "focus_queue", None)
        if fq:
            # Batch all leading BOSSES: boss → boss → … → player (once)
            if fq[0][0] == "boss":
                boss_targets = []
                while fq and fq[0][0] == "boss":
                    _, pos = fq.pop(0)
                    boss_targets.append(pos)
                play_focus_chain_iso(screen, clock, game_state, player, enemies, bullets, enemy_shots, boss_targets)
            else:
                # Non-boss singletons (e.g., bandit) keep existing one-shot behavior
                tag, pos = fq.pop(0)
                lbl = "COIN BANDIT!" if tag == "bandit" else None
                play_focus_cinematic_iso(
                    screen, clock, game_state, player, enemies, bullets, enemy_shots,
                    pos, label=lbl, return_to_player=True
                )
        # countdown timer
        time_left -= dt
        globals()["_time_left_runtime"] = time_left
        if time_left <= 0:
            game_result = "success" if 'game_result' in locals() else "success"
            running = False
        # === wave spawning ===
        spawn_timer += dt
        if spawn_timer >= SPAWN_INTERVAL:
            spawn_timer = 0.0
            if len(enemies) < ENEMY_CAP:
                spawned = spawn_wave_with_budget(game_state, player, current_level, wave_index, enemies, ENEMY_CAP)
                if spawned > 0:
                    wave_index += 1
                    globals()["_max_wave_reached"] = max(globals().get("_max_wave_reached", 0), wave_index)
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if is_action_event(event, "blast") and getattr(player, "targeting_skill", None) == "blast":
                player.targeting_skill = None
                player.skill_target_origin = None
                continue
            if is_action_event(event, "teleport") and getattr(player, "targeting_skill", None) == "teleport":
                player.targeting_skill = None
                player.skill_target_origin = None
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and getattr(player, "targeting_skill", None):
                player.targeting_skill = None
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                bg = last_frame or render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots,
                                                   obstacles=game_state.obstacles)
                choice, time_left = pause_game_modal(screen, bg, clock, time_left, player)
                if choice == 'continue':
                    pass  # just resume
                elif choice == 'restart':
                    queue_menu_transition(pygame.display.get_surface().copy())
                    return 'restart', config.get('reward', None), bg
                elif choice == 'home':
                    queue_menu_transition(pygame.display.get_surface().copy())
                    # carry your current level/xp forward
                    globals()["_carry_player_state"] = capture_player_carry(player)
                    # write a progress save (this contains META + carry)
                    save_progress(current_level=current_level,
                                  max_wave_reached=wave_index)
                    globals()["_skip_intro_once"] = True
                    return 'home', config.get('reward', None), bg
                elif choice == 'exit':
                    # write a progress save so Homepage shows CONTINUE
                    save_progress(current_level=current_level,
                                  max_wave_reached=wave_index)
                    return 'exit', config.get('reward', None), bg
            if is_action_event(event, "blast"):
                if getattr(player, "blast_cd", 0.0) <= 0.0:
                    player.targeting_skill = "blast"
                    player.skill_target_origin = None
                    _update_skill_target(player, game_state)
                else:
                    player.skill_flash["blast"] = 0.35
            if is_action_event(event, "teleport"):
                if getattr(player, "teleport_cd", 0.0) <= 0.0:
                    player.targeting_skill = "teleport"
                    player.skill_target_origin = None
                    _update_skill_target(player, game_state)
                else:
                    player.skill_flash["teleport"] = 0.35
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and getattr(player, "targeting_skill", None):
                _update_skill_target(player, game_state)
                if player.targeting_skill == "blast":
                    if player.skill_target_valid and _cast_fixed_point_blast(player, game_state, enemies, player.skill_target_pos):
                        player.blast_cd = float(BLAST_COOLDOWN)
                        player.targeting_skill = None
                    else:
                        player.skill_flash["blast"] = 0.35
                elif player.targeting_skill == "teleport":
                    if player.skill_target_valid and _teleport_player_to(player, game_state, player.skill_target_pos):
                        player.teleport_cd = float(TELEPORT_COOLDOWN)
                        player.targeting_skill = None
                        player.skill_target_origin = None
                    else:
                        player.skill_flash["teleport"] = 0.35
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and getattr(player, "targeting_skill", None):
                player.targeting_skill = None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and getattr(player, "targeting_skill", None):
                player.targeting_skill = None
        if getattr(player, "targeting_skill", None):
            _update_skill_target(player, game_state)
        keys = pygame.key.get_pressed()
        # ---- slow 计时衰减 + 电告圈与酸池更新（在移动之前）----
        player.slow_t = max(0.0, getattr(player, "slow_t", 0.0) - dt)
        game_state.update_telegraphs(dt)  # 到时生成酸池
        game_state.update_acids(dt, player)  # 结算DoT并刷新 slow_t
        game_state.update_vulnerability_marks(enemies, dt)
        game_state.update_hurricanes(dt, player, enemies, bullets, enemy_shots)
        # -----------------------------------------------
        player.move(keys, game_state.obstacles, dt)

        # --- UPDATE PARTICLES ---
        game_state.fx.update(dt)
        game_state.update_comet_blasts(dt, player, enemies)
        game_state.update_camera_shake(dt)
        # --- Flow field refresh (rebuild ~each 0.30s or when goal/obstacles changed)
        ptile = (int(player.rect.centerx // CELL_SIZE),
                 int((player.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE))
        game_state.refresh_flow_field(ptile, dt)
        game_state.collect_item(player.rect)
        game_state.update_spoils(dt, player)
        for z in enemies:
            got = game_state.collect_spoils_for_enemy(z)
            if got > 0:
                z.add_spoils(got)
            # 衰减拾取光晕
            z._gold_glow_t = max(0.0, getattr(z, "_gold_glow_t", 0.0) - dt)
        game_state.collect_spoils(player.rect)
        game_state.update_heals(dt)
        game_state.update_damage_texts(dt)
        game_state.update_aegis_pulses(dt, player, enemies)
        game_state.collect_heals(player)
        player.update_bone_plating(dt)
        # Active skill cooldowns
        player.blast_cd = max(0.0, getattr(player, "blast_cd", 0.0) - dt)
        player.teleport_cd = max(0.0, getattr(player, "teleport_cd", 0.0) - dt)
        player.skill_flash["blast"] = max(0.0, float(player.skill_flash.get("blast", 0.0)) - dt)
        player.skill_flash["teleport"] = max(0.0, float(player.skill_flash.get("teleport", 0.0)) - dt)
        # --- NEW: Telegraph/Acid 更新 + 减速衰减 ---
        game_state.update_telegraphs(dt)  # 倒计时→到时生成酸池
        game_state.update_acids(dt, player)  # 酸池伤害&施加 slow_t
        player.slow_t = max(0.0, getattr(player, "slow_t", 0.0) - dt)  # 每帧自然恢复
        # —— 结算离开酸池后的 DoT（中毒） ——
        if player.acid_dot_timer > 0.0:
            player.acid_dot_timer = max(0.0, player.acid_dot_timer - dt)
            player._acid_dot_accum += player.acid_dot_dps * dt
            whole = int(player._acid_dot_accum)
            if whole > 0:
                game_state.damage_player(player, whole)
                player._acid_dot_accum -= whole
            # （可选）当计时走完，清空 DoT dps
            if player.acid_dot_timer <= 0.0:
                player.acid_dot_dps = 0.0
        player.update_bone_plating(dt)
        tick_aegis_pulse(player, game_state, enemies, dt)
        # ===== Level-up picker (freeze gameplay & timer like Pause) =====
        while getattr(player, "levelup_pending", 0) > 0:
            bg = last_frame or render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots, obstacles)
            time_left = levelup_modal(screen, bg, clock, time_left, player)
            player.levelup_pending -= 1
            # redraw a fresh gameplay frame behind us for a seamless return
            last_frame = render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots, obstacles)
        # Autofire handling
        player.fire_cd = getattr(player, 'fire_cd', 0.0) - dt
        target, dist = find_target()
        if target and player.fire_cd <= 0 and (dist is None or dist <= player.range):
            _, gp, ob_or_z, cx, cy = target
            px, py = player_center()
            dx, dy = cx - px, cy - py
            L = (dx * dx + dy * dy) ** 0.5 or 1.0
            vx, vy = (dx / L) * BULLET_SPEED, (dy / L) * BULLET_SPEED
            b = Bullet(px, py, vx, vy, player.range, damage=player.bullet_damage)
            # Give this bullet its own pierce/ricochet charges from current player upgrades
            b.pierce_left = int(getattr(player, "bullet_pierce", 0))
            b.ricochet_left = int(getattr(player, "bullet_ricochet", 0))
            bullets.append(b)
            player.fire_cd += player.fire_cooldown()
        # Auto-turrets firing
        for t in getattr(game_state, "turrets", []):
            t.update(dt, game_state, enemies, bullets)
        # Update bullets
        for b in list(bullets):
            b.update(dt, game_state, enemies, player)
            if not b.alive:
                bullets.remove(b)
        player.hit_cd = max(0.0, player.hit_cd - dt)
        # Attach any bullets spawned during updates (e.g., Shrapnel Shells)
        if getattr(game_state, "pending_bullets", None):
            bullets.extend(game_state.pending_bullets)
            game_state.pending_bullets.clear()
        for enemy in list(enemies):
            enemy.move_and_attack(player, list(game_state.obstacles.values()), game_state, dt=dt)
            if player.hit_cd <= 0.0 and circle_touch(enemy, player):
                mult = getattr(game_state, "biome_enemy_contact_mult", 1.0)
                dmg_mult = getattr(enemy, "contact_damage_mult", 1.0)
                dmg = int(round(ENEMY_CONTACT_DAMAGE * max(1.0, mult) * max(0.1, dmg_mult)))
                game_state.damage_player(player, dmg)
                player.hit_cd = float(PLAYER_HIT_COOLDOWN)
                if player.hp <= 0:
                    game_result = "fail"
                    running = False
                    break
        # special behaviors & enemy shots
        game_state.update_dot_rounds(enemies, dt)
        for z in list(enemies):
            z.update_special(dt, player, enemies, enemy_shots, game_state)
            if z.hp <= 0 and not getattr(z, "_death_processed", False):
                z._death_processed = True  # Prevent duplicate death processing
                _bandit_death_notice(z, game_state)
                if getattr(z, "_comet_death", False) and not getattr(z, "_comet_fx_done", False):
                    z._comet_fx_done = True
                    if hasattr(game_state, "comet_corpses"):
                        body_size = max(int(z.rect.w), int(z.rect.h))
                        game_state.comet_corpses.append(
                            CometCorpse(z.rect.centerx, z.rect.centery, getattr(z, "color", (255, 60, 60)),
                                        body_size)
                        )
                if getattr(z, "is_boss", False) and getattr(z, "twin_id", None) is not None:
                    trigger_twin_enrage(z, enemies, game_state)
                total_drop = int(SPOILS_PER_KILL) + int(getattr(z, "spoils", 0))
                if total_drop > 0:
                    game_state.spawn_spoils(z.rect.centerx, z.rect.centery, total_drop)
                # Bosses: guaranteed heal potions; regular enemies: random chance
                if getattr(z, "is_boss", False):
                    for _ in range(BOSS_HEAL_POTIONS):
                        game_state.spawn_heal(z.rect.centerx, z.rect.centery, HEAL_POTION_AMOUNT)
                elif random.random() < HEAL_DROP_CHANCE_ENEMY:
                    game_state.spawn_heal(z.rect.centerx, z.rect.centery, HEAL_POTION_AMOUNT)
                # 额外经验（非子弹击杀时）
                if not getattr(z, "_xp_awarded", False):  # <-- add this guard
                    try:
                        player.add_xp(int(getattr(z, "spoils", 0)) * int(Z_SPOIL_XP_BONUS_PER))
                        setattr(z, "_xp_awarded", True)  # <-- mark as paid
                    except Exception:
                        pass
                transfer_xp_to_neighbors(z, enemies)
                enemies.remove(z)
        # enemy shots update
        for es in list(enemy_shots):
            es.update(dt, player, game_state)
            if not es.alive:
                enemy_shots.remove(es)
        update_hit_flash_timer(player, dt)
        for z in enemies:
            update_hit_flash_timer(z, dt)
        # afterimages (update & prune)
        if game_state.ghosts:
            game_state.ghosts[:] = [g for g in game_state.ghosts if g.update(dt)]
        # Fog
        boss_now = _find_current_boss(enemies)
        if boss_now and getattr(boss_now, "type", "") == "boss_mist":
            if not getattr(game_state, "fog_on", False):
                game_state.enable_fog_field()
        else:
            # Boss 不在了 → 收雾
            if getattr(game_state, "fog_on", False):
                game_state.disable_fog_field()
        # >>> FAIL CONDITION <<<
        if player.hp <= 0:
            game_result = "fail"
            running = False
            # Make a final frame so HUD shows 0 HP on the fail screen
            if USE_ISO:
                last_frame = render_game_iso(
                    pygame.display.get_surface(),
                    game_state, player, enemies, bullets, enemy_shots,
                    obstacles=obstacles
                )
            else:
                last_frame = render_game(
                    pygame.display.get_surface(),
                    game_state, player, enemies, bullets, enemy_shots
                )
            continue
        if USE_ISO:
            last_frame = render_game_iso(
                pygame.display.get_surface(),
                game_state, player, enemies, bullets, enemy_shots,
                obstacles
            )
        else:
            last_frame = render_game(
                pygame.display.get_surface(),
                game_state, player, enemies, bullets, enemy_shots
            )
        # else:
        #     last_frame = render_game(pygame.display.get_surface(), game_state, player, enemies, bullets, enemy_shots)
        if game_result == "success":
            globals()["_last_spoils"] = getattr(game_state, "spoils_gained", 0)
            globals()["_carry_player_state"] = capture_player_carry(player)
    return game_result, config.get("reward", None), last_frame


def run_from_snapshot(save_data: dict) -> Tuple[str, Optional[str], pygame.Surface]:
    """Resume a game from a snapshot in save_data; same return contract as main_run_level."""
    assert save_data.get("mode") == "snapshot"
    meta = save_data.get("meta", {})
    snap = save_data.get("snapshot", {})
    # Use the saved level index when scaling spawns
    level_idx = int(meta.get("current_level", current_level))
    # Recreate entities
    obstacles: Dict[Tuple[int, int], Obstacle] = {}
    for o in snap.get("obstacles", []):
        typ = o.get("type", "Indestructible")
        x, y = int(o.get("x", 0)), int(o.get("y", 0))
        if o.get("main", False):
            ob = MainBlock(x, y, health=o.get("health", MAIN_BLOCK_HEALTH))
        else:
            ob = Obstacle(x, y, typ, health=o.get("health", None))
        obstacles[(x, y)] = ob
    # Items & decorations
    items = [Item(int(it.get("x", 0)), int(it.get("y", 0)), bool(it.get("is_main", False)))
             for it in snap.get("items", [])]
    decorations = [tuple(d) for d in snap.get("decorations", [])]
    game_state = GameState(obstacles, items,
                           [(i.x, i.y) for i in items if getattr(i, 'is_main', False)],
                           decorations)
    game_state.current_level = level_idx
    # Player
    p = snap.get("player", {})
    player = Player((0, 0), speed=int(p.get("speed", PLAYER_SPEED)))
    player.x = float(p.get("x", 0.0));
    player.y = float(p.get("y", 0.0))
    player.rect.x = int(player.x);
    player.rect.y = int(player.y) + INFO_BAR_HEIGHT
    player.fire_cd = float(p.get("fire_cd", 0.0))
    player.max_hp = int(p.get("max_hp", PLAYER_MAX_HP))
    player.hp = int(p.get("hp", PLAYER_MAX_HP))
    player.hit_cd = float(p.get("hit_cd", 0.0))
    player.level = int(p.get("level", 1))
    player.xp = int(p.get("xp", 0))
    player.xp_to_next = player_xp_required(player.level)
    player.bone_plating_hp = int(p.get("bone_plating_hp", 0))
    player._bone_plating_cd = float(p.get("bone_plating_cd", BONE_PLATING_GAIN_INTERVAL))
    player._bone_plating_glow = 0.0
    player.aegis_pulse_level = int(meta.get("aegis_pulse_level", META.get("aegis_pulse_level", 0)))
    if player.aegis_pulse_level > 0:
        _, _, cd = aegis_pulse_stats(player.aegis_pulse_level, player.max_hp)
        player._aegis_pulse_cd = float(p.get("aegis_pulse_cd", cd))
    else:
        player._aegis_pulse_cd = 0.0
    if not hasattr(player, 'fire_cd'): player.fire_cd = 0.0
    player._hit_flash = 0.0
    player._flash_prev_hp = int(player.hp)
    # Auto-turrets when resuming (use saved meta if present, else global META)
    turret_level = int(meta.get("auto_turret_level", META.get("auto_turret_level", 0)))
    turrets: List[AutoTurret] = []
    if turret_level > 0:
        for i in range(turret_level):
            angle = 2.0 * math.pi * i / max(1, turret_level)
            off_x = math.cos(angle) * AUTO_TURRET_OFFSET_RADIUS
            off_y = math.sin(angle) * AUTO_TURRET_OFFSET_RADIUS
            turrets.append(AutoTurret(player, (off_x, off_y)))
    # Stationary turrets from META on resume
    stationary_count = int(meta.get("stationary_turret_count", 0))
    if stationary_count > 0:
        for _ in range(stationary_count):
            for _attempt in range(40):
                gx = random.randrange(GRID_SIZE)
                gy = random.randrange(GRID_SIZE)
                if (gx, gy) in game_state.obstacles:
                    continue
                wx = gx * CELL_SIZE + CELL_SIZE // 2
                wy = gy * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT
                turrets.append(StationaryTurret(wx, wy))
                break
    game_state.turrets = turrets
    # Enemies
    enemies: List[Enemy] = []
    for z in snap.get("enemies", []):
        zobj = Enemy((0, 0),
                      attack=int(z.get("attack", ENEMY_ATTACK)),
                      speed=int(z.get("speed", ENEMY_SPEED)),
                      ztype=z.get("type", "basic"),
                      hp=int(z.get("hp", 30)))
        zobj.max_hp = int(z.get("max_hp", int(z.get("hp", 30))))
        zobj.x = float(z.get("x", 0.0));
        zobj.y = float(z.get("y", 0.0))
        zobj.rect.x = int(zobj.x);
        zobj.rect.y = int(zobj.y) + INFO_BAR_HEIGHT
        zobj._spawn_elapsed = float(z.get("spawn_elapsed", 0.0))
        zobj.attack_timer = float(z.get("attack_timer", 0.0))
        # clamp restored speed so resumed runs don't create super-speed enemies
        zobj.speed = min(ENEMY_SPEED_MAX, max(1, int(zobj.speed)))
        zobj._hit_flash = 0.0
        zobj._flash_prev_hp = int(zobj.hp)
        enemies.append(zobj)
    # Bullets
    bullets: List[Bullet] = []
    for b in snap.get("bullets", []):
        bobj = Bullet(float(b.get("x", 0.0)), float(b.get("y", 0.0)),
                      float(b.get("vx", 0.0)), float(b.get("vy", 0.0)),
                      clamp_player_range(getattr(player, "range", PLAYER_RANGE_DEFAULT)))
        bobj.traveled = float(b.get("traveled", 0.0))
        # approximate current upgrades
        bobj.pierce_left = int(getattr(player, "bullet_pierce", 0))
        bobj.ricochet_left = int(getattr(player, "bullet_ricochet", 0))
        bullets.append(bobj)
    enemy_shots: List[EnemyShot] = []
    # Timer
    time_left = float(snap.get("time_left", LEVEL_TIME_LIMIT))
    globals()["_time_left_runtime"] = time_left  # keep global for HUD
    screen = pygame.display.get_surface()
    clock = pygame.time.Clock()
    running = True
    last_frame = None
    chosen_enemy_type = meta.get("chosen_enemy_type", "basic")
    # Spawner state
    spawn_timer = 0.0
    wave_index = 0

    def player_center():
        return player.x + player.size / 2, player.y + player.size / 2 + INFO_BAR_HEIGHT

    def find_target():
        # 玩家中心（像素）
        px, py = player.rect.centerx, player.rect.centery
        # 玩家格坐标（用于“两格内”判断）
        pgx = int(px // CELL_SIZE)
        pgy = int((py - INFO_BAR_HEIGHT) // CELL_SIZE)
        # 1) 两格内是否有可破坏障碍？有 → 直接优先最近的那一个
        force_blocks = []
        for gp, ob in game_state.obstacles.items():
            if getattr(ob, "type", "") != "Destructible":
                continue
            gx, gy = gp
            manh = abs(gx - pgx) + abs(gy - pgy)  # 曼哈顿距离（格）
            if manh <= int(PLAYER_BLOCK_FORCE_RANGE_TILES):
                cx, cy = ob.rect.centerx, ob.rect.centery
                d2 = (cx - px) ** 2 + (cy - py) ** 2
                force_blocks.append((d2, ('block', gp, ob, cx, cy)))
        if force_blocks:
            force_blocks.sort(key=lambda t: t[0])  # 最近优先
            best_tuple = force_blocks[0][1]
            d = (force_blocks[0][0]) ** 0.5
            return best_tuple, d
        # 2) 正常权重选择（仅考虑“射程内”的目标）
        cur_range = clamp_player_range(getattr(player, "range", PLAYER_RANGE_DEFAULT))
        R2 = cur_range ** 2
        # 收集候选：僵尸（射程内）
        z_cands = []
        for z in enemies:
            cx, cy = z.rect.centerx, z.rect.centery
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 <= R2:
                z_cands.append((z, cx, cy, d2))
        # 收集候选：可破坏障碍（射程内）
        b_cands = []
        for gp, ob in game_state.obstacles.items():
            if getattr(ob, "type", "") != "Destructible":
                continue
            cx, cy = ob.rect.centerx, ob.rect.centery
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 <= R2:
                b_cands.append((gp, ob, cx, cy, d2))
        # 射程内什么都没有 → 没目标
        if not z_cands and not b_cands:
            return (None, None)
        # 权重评分：
        # - 基于距离的衰减：基础分 = -d2 * k（d2 越小，分越高）
        # - 僵尸优先：加较高常数；障碍其次：加较低常数
        #   （权重不要过大，否则完全遮蔽距离差异）
        DIST_K = 1e-4
        W_ENEMY = 1200.0
        W_BLOCK = 800.0
        best = None
        best_score = -1e18
        # 僵尸优先（仍受距离影响）
        for z, cx, cy, d2 in z_cands:
            s = -d2 * DIST_K + W_ENEMY
            # 若想进一步区分类型，可在此额外加分（例如自爆怪、远程怪等）
            if s > best_score:
                best_score = s
                best = ('enemy', None, z, cx, cy, d2)
        # 障碍次之（仍受距离影响）
        for gp, ob, cx, cy, d2 in b_cands:
            s = -d2 * DIST_K + W_BLOCK
            if s > best_score:
                best_score = s
                best = ('block', gp, ob, cx, cy, d2)
        if best is None:
            return (None, None)
        kind, gp_or_none, obj, cx, cy, d2 = best
        return (kind, gp_or_none, obj, cx, cy), (d2 ** 0.5)

    player._hit_flash = 0.0
    player._flash_prev_hp = int(player.hp)
    for z in enemies:
        z._hit_flash = 0.0
        z._flash_prev_hp = int(getattr(z, "hp", 0))
    while running:
        dt = clock.tick(60) / 1000.0
        # survival timer
        time_left -= dt
        globals()["_time_left_runtime"] = time_left
        if time_left <= 0:
            # win on survival
            chosen = show_success_screen(
                screen,
                last_frame or render_game(screen, game_state, player, enemies, bullets, enemy_shots),
                reward_choices=[]
            )
            return "success", None, last_frame or screen.copy()
        # input
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if is_action_event(event, "blast") and getattr(player, "targeting_skill", None) == "blast":
                player.targeting_skill = None
                continue
            if is_action_event(event, "teleport") and getattr(player, "targeting_skill", None) == "teleport":
                player.targeting_skill = None
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and getattr(player, "targeting_skill", None):
                player.targeting_skill = None
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                bg = last_frame or render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots,
                                                   obstacles=game_state.obstacles)
                choice, time_left = pause_game_modal(screen, bg, clock, time_left, player)
                if choice == 'continue':
                    pass
                elif choice == 'restart':
                    queue_menu_transition(pygame.display.get_surface().copy())
                    return 'restart', None, bg
                elif choice == 'home':
                    queue_menu_transition(pygame.display.get_surface().copy())
                    snap2 = capture_snapshot(
                        game_state, player, enemies, level_idx,
                        chosen_enemy_type, bullets
                    )
                    save_snapshot(snap2)
                    globals()["_skip_intro_once"] = True
                    return 'home', None, bg
                elif choice == 'exit':
                    # also save progress from a snapshot resume
                    save_progress(
                        current_level=level_idx,
                        max_wave_reached=wave_index
                    )
                    return 'exit', None, bg
            if is_action_event(event, "blast"):
                if getattr(player, "blast_cd", 0.0) <= 0.0:
                    player.targeting_skill = "blast"
                    _update_skill_target(player, game_state)
                else:
                    player.skill_flash["blast"] = 0.35
            if is_action_event(event, "teleport"):
                if getattr(player, "teleport_cd", 0.0) <= 0.0:
                    player.targeting_skill = "teleport"
                    _update_skill_target(player, game_state)
                else:
                    player.skill_flash["teleport"] = 0.35
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and getattr(player, "targeting_skill", None):
                _update_skill_target(player, game_state)
                if player.targeting_skill == "blast":
                    if player.skill_target_valid and _cast_fixed_point_blast(player, game_state, enemies, player.skill_target_pos):
                        player.blast_cd = float(BLAST_COOLDOWN)
                        player.targeting_skill = None
                    else:
                        player.skill_flash["blast"] = 0.35
                elif player.targeting_skill == "teleport":
                    if player.skill_target_valid and _teleport_player_to(player, game_state, player.skill_target_pos):
                        player.teleport_cd = float(TELEPORT_COOLDOWN)
                        player.targeting_skill = None
                    else:
                        player.skill_flash["teleport"] = 0.35
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and getattr(player, "targeting_skill", None):
                player.targeting_skill = None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and getattr(player, "targeting_skill", None):
                player.targeting_skill = None
        # movement & pickups
        if getattr(player, "targeting_skill", None):
            _update_skill_target(player, game_state)
        keys = pygame.key.get_pressed()
        # ---- slow 计时衰减 + 电告圈与酸池更新（在移动之前）----
        player.slow_t = max(0.0, getattr(player, "slow_t", 0.0) - dt)
        game_state.update_telegraphs(dt)  # 到时生成酸池
        game_state.update_acids(dt, player)  # 结算DoT并刷新 slow_t
        game_state.update_vulnerability_marks(enemies, dt)
        # -----------------------------------------------
        player.move(keys, game_state.obstacles, dt)
        game_state.fx.update(dt)
        game_state.update_comet_blasts(dt, player, enemies)
        game_state.update_camera_shake(dt)
        game_state.collect_item(player.rect)
        game_state.update_spoils(dt, player)
        game_state.collect_spoils(player.rect)
        game_state.update_heals(dt)
        game_state.update_damage_texts(dt)
        game_state.update_aegis_pulses(dt, player, enemies)
        game_state.collect_heals(player)
        tick_aegis_pulse(player, game_state, enemies, dt)
        # Active skill cooldowns
        player.blast_cd = max(0.0, getattr(player, "blast_cd", 0.0) - dt)
        player.teleport_cd = max(0.0, getattr(player, "teleport_cd", 0.0) - dt)
        player.skill_flash["blast"] = max(0.0, float(player.skill_flash.get("blast", 0.0)) - dt)
        player.skill_flash["teleport"] = max(0.0, float(player.skill_flash.get("teleport", 0.0)) - dt)
        # Autofire
        player.fire_cd = getattr(player, 'fire_cd', 0.0) - dt
        target, dist = find_target()
        if target and player.fire_cd <= 0 and (dist is None or dist <= player.range):
            _, gp, ob_or_z, cx, cy = target
            px, py = player_center()
            dx, dy = cx - px, cy - py
            L = (dx * dx + dy * dy) ** 2 ** 0.5 if False else ((dx * dx + dy * dy) ** 0.5)  # keep readable
            L = L or 1.0
            vx, vy = (dx / L) * BULLET_SPEED, (dy / L) * BULLET_SPEED
            b = Bullet(px, py, vx, vy, player.range, damage=player.bullet_damage)
            # per-bullet Piercing & Ricochet charges
            b.pierce_left = int(getattr(player, "bullet_pierce", 0))
            b.ricochet_left = int(getattr(player, "bullet_ricochet", 0))
            bullets.append(b)
            player.fire_cd += player.fire_cooldown()
        # Auto-turrets firing
        for t in getattr(game_state, "turrets", []):
            t.update(dt, game_state, enemies, bullets)
        # Update bullets
        for b in list(bullets):
            b.update(dt, game_state, enemies, player)
            if not b.alive:
                bullets.remove(b)
        # === wave spawning (budget-based ONLY) ===
        spawn_timer += dt
        if spawn_timer >= SPAWN_INTERVAL:
            spawn_timer = 0.0
            if len(enemies) < ENEMY_CAP:
                spawned = spawn_wave_with_budget(game_state, player, level_idx, wave_index, enemies, ENEMY_CAP)
                if spawned > 0:
                    wave_index += 1
                    globals()["_max_wave_reached"] = max(globals().get("_max_wave_reached", 0), wave_index)
        # Enemies update & contact damage
        player.hit_cd = max(0.0, player.hit_cd - dt)
        # --- nav refresh (shared Dijkstra flow field) ---
        pgx = int(player.rect.centerx // CELL_SIZE)
        pgy = int((player.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE)
        game_state.refresh_flow_field((pgx, pgy), dt)
        for enemy in list(enemies):
            enemy.move_and_attack(player, list(game_state.obstacles.values()), game_state, dt=dt)
            if player.hit_cd <= 0.0 and circle_touch(enemy, player):
                mult = getattr(game_state, "biome_enemy_contact_mult", 1.0)
                dmg_mult = getattr(enemy, "contact_damage_mult", 1.0)
                dmg = int(round(ENEMY_CONTACT_DAMAGE * max(1.0, mult) * max(0.1, dmg_mult)))
                game_state.damage_player(player, dmg)
                player.hit_cd = float(PLAYER_HIT_COOLDOWN)
                if player.hp <= 0:
                    clear_save()
                    # Fresh frame with HP = 0 for fail background
                    bg = render_game_iso(
                        screen, game_state, player, enemies, bullets, enemy_shots,
                        obstacles=game_state.obstacles
                    )
                    last_frame = bg.copy()
                    action = show_fail_screen(screen, bg)
                    if action == "home":
                        clear_save();
                        flush_events()
                        return "home", None, last_frame or screen.copy()
                    elif action == "retry":
                        clear_save();
                        flush_events()
                        return "restart", None, last_frame or screen.copy()
        # Special behaviors & enemy shots
        game_state.update_dot_rounds(enemies, dt)
        for z in list(enemies):
            z.update_special(dt, player, enemies, enemy_shots, game_state)
            if z.hp <= 0 and not getattr(z, "_death_processed", False):
                z._death_processed = True  # Prevent duplicate death processing
                _bandit_death_notice(z, game_state)
                if getattr(z, "_comet_death", False) and not getattr(z, "_comet_fx_done", False):
                    z._comet_fx_done = True
                    if hasattr(game_state, "comet_corpses"):
                        body_size = max(int(z.rect.w), int(z.rect.h))
                        game_state.comet_corpses.append(
                            CometCorpse(z.rect.centerx, z.rect.centery, getattr(z, "color", (255, 60, 60)),
                                        body_size)
                        )
                total_drop = int(SPOILS_PER_KILL) + int(getattr(z, "spoils", 0))
                if total_drop > 0:
                    game_state.spawn_spoils(z.rect.centerx, z.rect.centery, total_drop)
                # Bosses: guaranteed heal potions; regular enemies: random chance
                if getattr(z, "is_boss", False):
                    for _ in range(BOSS_HEAL_POTIONS):
                        game_state.spawn_heal(z.rect.centerx, z.rect.centery, HEAL_POTION_AMOUNT)
                elif random.random() < HEAL_DROP_CHANCE_ENEMY:
                    game_state.spawn_heal(z.rect.centerx, z.rect.centery, HEAL_POTION_AMOUNT)
                # 额外经验（非子弹击杀时）
                try:
                    player.add_xp(int(getattr(z, "spoils", 0)) * int(Z_SPOIL_XP_BONUS_PER))
                except Exception:
                    pass
                transfer_xp_to_neighbors(z, enemies)
                enemies.remove(z)
        for es in list(enemy_shots):
            es.update(dt, player, game_state)
            if not es.alive:
                enemy_shots.remove(es)
        update_hit_flash_timer(player, dt)
        for z in enemies:
            update_hit_flash_timer(z, dt)
        # Fail check (redundant guard)
        if player.hp <= 0:
            clear_save()
            action = show_fail_screen(screen,
                                      last_frame or render_game(screen, game_state, player, enemies, bullets,
                                                                enemy_shots))
            if action == "home":
                clear_save();
                flush_events()
                return "home", None, last_frame or screen.copy()
            elif action == "retry":
                clear_save();
                flush_events()
                return "restart", None, last_frame or screen.copy()
        if USE_ISO:
            last_frame = render_game_iso(pygame.display.get_surface(), game_state, player, enemies, bullets,
                                         enemy_shots)
        else:
            last_frame = render_game(pygame.display.get_surface(), game_state, player, enemies, bullets, enemy_shots)
    return "home", None, last_frame or screen.copy()


# ==================== 入口 ====================
if __name__ == "__main__":
    os.environ['SDL_VIDEO_CENTERED'] = '0'
    os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
    pygame.init()
    info = pygame.display.Info()
    # Create the window first (safer on some systems)
    screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.NOFRAME)
    pygame.display.set_caption(GAME_TITLE)
    VIEW_W, VIEW_H = info.current_w, info.current_h
    # Make the world at least as big as what we can see (removes “non-playable band”)
    resize_world_to_view()
    # Now start BGM using Settings default (BGM_VOLUME 0-100)
    try:
        play_intro_bgm()
    except Exception as e:
        print(f"[Audio] background music not started: {e}")
    # Borderless fullscreen to avoid display mode flicker
    screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.NOFRAME)
    pygame.display.set_caption(GAME_TITLE)
    VIEW_W, VIEW_H = info.current_w, info.current_h
    # Make the world at least as big as what we can see (removes “non-playable band”)
    resize_world_to_view()
    # Enter start menu
    flush_events()
    selection = show_start_menu(screen)
    if not selection:
        sys.exit()
    mode, save_data = selection
    # Initialize progress holders (module-level for snapshot helpers)
    if mode == "continue" and save_data:
        # restore shop upgrades and carry for a fresh run at the stored level
        if save_data:
            _load_meta_from_save(save_data)
            globals()["_carry_player_state"] = save_data.get("carry_player", None)
            globals()["_pending_shop"] = bool(save_data.get("pending_shop", False))
            globals()["_next_biome"] = save_data.get("biome")
        else:
            globals()["_carry_player_state"] = None
        if save_data.get("mode") == "snapshot":
            # pull meta
            meta = save_data.get("meta", {})
            current_level = int(meta.get("current_level", 0))
            globals()["_next_biome"] = save_data.get("biome")
        else:
            current_level = int(save_data.get("current_level", 0))
    else:
        clear_save()
        reset_run_state()
        current_level = 0
        globals()["_carry_player_state"] = None
        globals()["_pending_shop"] = False
        globals().pop("_last_spoils", None)
        globals().pop("_next_biome", None)
        globals().pop("_last_biome", None)
    while True:
        # If we saved while in the shop last time, reopen the shop first
        if globals().get("_pending_shop", False):
            META["spoils"] += int(globals().pop("_last_spoils", 0))
            globals()["_coins_at_shop_entry"] = int(META.get("spoils", 0))
            action = show_shop_screen(screen)
            globals()["_pending_shop"] = False
            if action in (None,):  # user clicked NEXT (closed shop normally)
                globals()["_pending_shop"] = False
                current_level += 1
                globals().pop("_coins_at_level_start", None)
                globals().pop("_coins_at_shop_entry", None)
                save_progress(current_level)
                # fall through to start the next level immediately
            elif action == "home":
                # keep the shop pending so CONTINUE returns here again
                save_progress(current_level, pending_shop=True)
                flush_events()
                selection = show_start_menu(screen, skip_intro=True)
                if not selection: sys.exit()
                mode, save_data = selection
                if mode == "continue" and save_data:
                    _load_meta_from_save(save_data)
                    globals()["_carry_player_state"] = save_data.get("carry_player", None)
                    globals()["_pending_shop"] = bool(save_data.get("pending_shop", False))
                    globals()["_next_biome"] = save_data.get("biome")
                    current_level = int(save_data.get("current_level", 0))
                else:
                    clear_save()
                    reset_run_state()
                    current_level = 0
                    globals()["_carry_player_state"] = None
                    globals()["_pending_shop"] = False
                    globals().pop("_last_spoils", None)
                    globals().pop("_next_biome", None)
                    globals().pop("_last_biome", None)
                    globals().pop("_last_biome", None)
                    globals().pop("_next_biome", None)
                continue  # back to loop top
            elif action == "restart":
                META["spoils"] = int(globals().get("_coins_at_level_start", META.get("spoils", 0)))
                globals().pop("_last_spoils", None)
                flush_events()
                continue
            elif action == "exit":
                save_progress(current_level, pending_shop=True)
                pygame.quit();
                sys.exit()
        config = get_level_config(current_level)
        chosen_enemy = "basic"
        # --- snapshot coins at first entry to this level ---
        if "_coins_at_level_start" not in globals():
            globals()["_coins_at_level_start"] = int(META.get("spoils", 0))
        if globals().get("_menu_transition_frame") is None:
            flush_events()
        result, reward, bg = main_run_level(config, chosen_enemy)
        if result == "restart":
            META["spoils"] = int(globals().get("_coins_at_level_start", META.get("spoils", 0)))
            META["run_items_spawned"] = int(globals().get("_run_items_spawned_start", META.get("run_items_spawned", 0)))
            META["run_items_collected"] = int(globals().get("_run_items_collected_start", META.get("run_items_collected", 0)))
            cb = globals().get("_consumable_baseline", {})
            if isinstance(cb, dict):
                META["carapace_shield_hp"] = int(cb.get("carapace_shield_hp", META.get("carapace_shield_hp", 0)))
                META["wanted_poster_waves"] = int(cb.get("wanted_poster_waves", META.get("wanted_poster_waves", 0)))
                META["wanted_active"] = bool(cb.get("wanted_active", False))
            globals().pop("_items_counted_level", None)
            globals().pop("_last_spoils", None)
            flush_events()
            continue
        if result == "home":
            flush_events()
            selection = show_start_menu(screen, skip_intro=True)
            if not selection:
                sys.exit()
            mode, save_data = selection
            if mode == "continue" and save_data:
                # restore shop upgrades and carry for a fresh run at the stored level
                if save_data:
                    _load_meta_from_save(save_data)
                    globals()["_carry_player_state"] = save_data.get("carry_player", None)
                    globals()["_next_biome"] = save_data.get("biome")
                else:
                    globals()["_carry_player_state"] = None
                # Update progress trackers
                if save_data.get("mode") == "snapshot":
                    meta = save_data.get("meta", {})
                    current_level = int(meta.get("current_level", 0))
                    globals()["_next_biome"] = save_data.get("biome")
                else:
                    current_level = int(save_data.get("current_level", 0))
                globals()["_pending_shop"] = bool(save_data.get("pending_shop", False))
            else:
                clear_save()
                reset_run_state()
                current_level = 0
                globals()["_carry_player_state"] = None
                globals()["_pending_shop"] = False
                globals().pop("_last_spoils", None)
            continue
        if result == "exit":
            # quit to OS; snapshot saving already done inside the loop
            pygame.quit()
            sys.exit()
        if result == "fail":
            clear_save()
            action = show_fail_screen(screen, bg)
            flush_events()
            if action == "home":
                # NEW: reset per-run carry
                globals()["_carry_player_state"] = None
                selection = show_start_menu(screen, skip_intro=True)
                if not selection:
                    sys.exit()
                mode, save_data = selection
                # After a fail we always start fresh
                clear_save()
                reset_run_state()
                current_level = 0
                continue
            else:
                # action == "retry" -> restart this level as a fresh run
                cb = globals().get("_consumable_baseline", {})
                if isinstance(cb, dict):
                    META["carapace_shield_hp"] = int(cb.get("carapace_shield_hp", META.get("carapace_shield_hp", 0)))
                    META["wanted_poster_waves"] = int(cb.get("wanted_poster_waves", META.get("wanted_poster_waves", 0)))
                    META["wanted_active"] = bool(cb.get("wanted_active", False))
                # globals()["_carry_player_state"] = capture_player_carry(player)
                continue
        elif result == "success":
            # bank coins from this level
            META["spoils"] += int(globals().get("_last_spoils", 0))
            globals()["_last_spoils"] = 0
            action = show_success_screen(screen, bg, [])
            if action == "home":
                flush_events()
                selection = show_start_menu(screen, skip_intro=True)
                if not selection:
                    sys.exit()
                mode, save_data = selection
                if mode == "continue" and save_data:
                    if save_data:
                        _load_meta_from_save(save_data)
                        globals()["_carry_player_state"] = save_data.get("carry_player", None)
                        globals()["_next_biome"] = save_data.get("biome")
                    else:
                        globals()["_carry_player_state"] = None
                    if save_data.get("mode") == "snapshot":
                        meta = save_data.get("meta", {})
                        current_level = int(meta.get("current_level", 0))
                    else:
                        current_level = int(save_data.get("current_level", 0))
                    globals()["_pending_shop"] = bool(save_data.get("pending_shop", False))
                else:
                    clear_save()
                    reset_run_state()
                    current_level = 0
                    globals()["_carry_player_state"] = None
                    globals()["_pending_shop"] = False
                    globals().pop("_last_spoils", None)
                continue
            # if player pressed Restart on the success page, do NOT enter the shop.
            if action in ("restart", "retry"):
                META["spoils"] = int(globals().get("_coins_at_level_start", META.get("spoils", 0)))
                globals().pop("_last_spoils", None)
                flush_events()
                continue
            # Only when actually entering the shop do we snapshot shop-entry coins:
            globals()["_coins_at_shop_entry"] = int(META.get("spoils", 0))
            action = show_shop_screen(screen)
            # React to pause-menu choices made from inside the shop
            if action == "home":
                save_progress(current_level, pending_shop=True)
                flush_events()
                selection = show_start_menu(screen, skip_intro=True)
                if not selection: sys.exit()
                mode, save_data = selection
                # keep your existing homepage handling logic
                if mode == "continue" and save_data:
                    # restore shop upgrades and carry for a fresh run at the stored level
                    if save_data:
                        _load_meta_from_save(save_data)
                        globals()["_carry_player_state"] = save_data.get("carry_player", None)
                    else:
                        globals()["_carry_player_state"] = None
                    if save_data.get("mode") == "snapshot":
                        meta = save_data.get("meta", {})
                        current_level = int(meta.get("current_level", 0))
                    else:
                        current_level = int(save_data.get("current_level", 0))
                    globals()["_pending_shop"] = bool(save_data.get("pending_shop", False))
                else:
                    clear_save()
                    reset_run_state()
                    current_level = 0
                    globals()["_carry_player_state"] = None
                    globals()["_pending_shop"] = False
                    globals().pop("_next_biome", None)
                    globals().pop("_last_biome", None)
                continue  # back to the top-level loop
            elif action in ("restart", "retry"):
                # restart this level as a fresh run
                META["spoils"] = int(globals().get("_coins_at_shop_entry", META.get("spoils", 0)))
                META["run_items_spawned"] = int(globals().get("_run_items_spawned_start", META.get("run_items_spawned", 0)))
                META["run_items_collected"] = int(globals().get("_run_items_collected_start", META.get("run_items_collected", 0)))
                globals().pop("_items_counted_level", None)
                globals().pop("_last_spoils", None)
                continue
            elif action == "exit":
                # save where we were (in the shop) and quit
                save_progress(current_level, pending_shop=True)
                pygame.quit()
                sys.exit()
            else:
                # user clicked NEXT (closed shop normally) -> go to next level
                current_level += 1
                globals().pop("_coins_at_level_start", None)
                globals().pop("_coins_at_shop_entry", None)
                save_progress(current_level)
        else:
            # Unknown state -> go home
            selection = show_start_menu(screen, skip_intro=True)
            if not selection:
                sys.exit()
            mode, save_data = selection
            if mode == "continue" and save_data:
                # restore shop upgrades and carry for a fresh run at the stored level
                if save_data:
                    _load_meta_from_save(save_data)
                    globals()["_carry_player_state"] = save_data.get("carry_player", None)
                else:
                    globals()["_carry_player_state"] = None
                if save_data.get("mode") == "snapshot":
                    meta = save_data.get("meta", {})
                    if mode == "continue" and save_data and save_data.get("mode") == "snapshot":
                        current_level = int(meta.get("current_level", 0))
                else:
                    current_level = int(save_data.get("current_level", 0))
            else:
                clear_save()
                reset_run_state()
                current_level = 0
                globals()["_carry_player_state"] = None
                globals().pop("_next_biome", None)
                globals().pop("_last_biome", None)
# TODO
# Attack MODE need to figure out
# The item collection system can be hugely impact this game to next level
# Player and Enemy both can collect item to upgrade, after kill enemy, player can get the experience to upgrade, and
# I set a timer each game for winning condition, as long as player still alive, after the time is running out
# player won, vice versa. And after each combat, shop( roguelike feature) will appear for player to trade with item
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
