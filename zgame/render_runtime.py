"""Top-level render/HUD runtime helpers extracted from ZGame.py."""

from __future__ import annotations

import math
import sys
import time
from typing import List, Optional

import pygame

from zgame import runtime_state as rs


def install(game):
    # Mirror the live game module namespace so this extracted layer can keep
    # using the existing helper/constant names without rewriting every draw path.
    for key, value in game.__dict__.items():
        if not str(key).startswith("__"):
            globals()[key] = value

    def _runtime():
        return rs.runtime(game)

    def _web_feature_enabled(flag_name: str) -> bool:
        if not getattr(game, "IS_WEB", False):
            return True
        return bool(getattr(game, flag_name, False))

    _ellipse_surface_cache: dict[tuple[int, int, tuple[int, ...], int], pygame.Surface] = {}
    _iso_tile_surface_cache: dict[tuple[int, int, tuple[int, ...], int], pygame.Surface] = {}
    _iso_wall_surface_cache: dict[tuple[str, int, tuple[int, ...]], tuple[pygame.Surface, int, int]] = {}
    _text_surface_cache: dict[tuple[int, bool, tuple[int, ...], str], pygame.Surface] = {}
    _filled_surface_cache: dict[tuple[int, int, tuple[int, ...]], pygame.Surface] = {}
    _rounded_rect_surface_cache: dict[tuple[int, int, tuple[int, ...], int, int], pygame.Surface] = {}
    _sprite_tint_surface_cache: dict[tuple[int, tuple[int, int], tuple[int, ...]], pygame.Surface] = {}
    _sprite_outline_surface_cache: dict[tuple[int, tuple[int, int], tuple[int, ...], int], pygame.Surface] = {}
    _ground_spike_icon_cache: dict[int, pygame.Surface] = {}
    _vuln_mark_surface_cache: dict[tuple[int, tuple[int, int, int], int], pygame.Surface] = {}

    def _normalize_rgba(color: tuple[int, ...], *, alpha_step: int = 1) -> tuple[int, ...]:
        rgba = tuple(max(0, min(255, int(v))) for v in color)
        if len(rgba) == 3:
            rgba = (*rgba, 255)
        if alpha_step > 1:
            alpha = int(round(rgba[3] / float(alpha_step))) * int(alpha_step)
            rgba = (rgba[0], rgba[1], rgba[2], max(0, min(255, alpha)))
        return rgba

    def _cached_filled_surface(size: tuple[int, int], color: tuple[int, ...]) -> pygame.Surface:
        w = max(1, int(size[0]))
        h = max(1, int(size[1]))
        rgba = _normalize_rgba(color, alpha_step=12 if IS_WEB else 1)
        key = (w, h, rgba)
        surf = _filled_surface_cache.get(key)
        if surf is None:
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            surf.fill(rgba)
            try:
                surf = surf.convert_alpha()
            except Exception:
                pass
            _filled_surface_cache[key] = surf
        return surf

    def _cached_rounded_rect_surface(
        size: tuple[int, int],
        color: tuple[int, ...],
        *,
        border_radius: int = 0,
        line_width: int = 0,
    ) -> pygame.Surface:
        w = max(1, int(size[0]))
        h = max(1, int(size[1]))
        rgba = _normalize_rgba(color, alpha_step=12 if IS_WEB else 1)
        border = max(0, int(border_radius))
        line = max(0, int(line_width))
        key = (w, h, rgba, border, line)
        surf = _rounded_rect_surface_cache.get(key)
        if surf is None:
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(surf, rgba, surf.get_rect(), width=line, border_radius=border)
            try:
                surf = surf.convert_alpha()
            except Exception:
                pass
            _rounded_rect_surface_cache[key] = surf
        return surf

    def _cached_sprite_tint_surface(sprite: pygame.Surface | None, color: tuple[int, ...]) -> pygame.Surface | None:
        if sprite is None:
            return None
        rgba = _normalize_rgba(color, alpha_step=12 if IS_WEB else 1)
        key = (id(sprite), sprite.get_size(), rgba)
        surf = _sprite_tint_surface_cache.get(key)
        if surf is None:
            surf = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
            surf.fill(rgba)
            surf.blit(_sprite_alpha_mask(sprite), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            try:
                surf = surf.convert_alpha()
            except Exception:
                pass
            _sprite_tint_surface_cache[key] = surf
        return surf

    def _blit_cached_sprite_tint(screen: pygame.Surface, sprite: pygame.Surface | None,
                                 dest_pos: tuple[int, int], color: tuple[int, ...]) -> None:
        tint = _cached_sprite_tint_surface(sprite, color)
        if tint is not None:
            screen.blit(tint, dest_pos)

    def _cached_sprite_outline_surface(sprite: pygame.Surface | None, color: tuple[int, ...],
                                       *, width: int = 3) -> pygame.Surface | None:
        if sprite is None:
            return None
        pts = _sprite_outline_points(sprite)
        if not pts:
            return None
        rgba = _normalize_rgba(color, alpha_step=12 if IS_WEB else 1)
        outline_w = max(1, int(width))
        key = (id(sprite), sprite.get_size(), rgba, outline_w)
        surf = _sprite_outline_surface_cache.get(key)
        if surf is None:
            surf = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
            pygame.draw.lines(surf, rgba, True, pts, outline_w)
            try:
                surf = surf.convert_alpha()
            except Exception:
                pass
            _sprite_outline_surface_cache[key] = surf
        return surf

    def _blit_cached_sprite_outline(screen: pygame.Surface, sprite: pygame.Surface | None,
                                    dest_pos: tuple[int, int], color: tuple[int, ...], *,
                                    width: int = 3) -> None:
        outline = _cached_sprite_outline_surface(sprite, color, width=width)
        if outline is not None:
            screen.blit(outline, dest_pos)

    def _cached_ground_spike_icon(alpha: int) -> pygame.Surface:
        a = _normalize_rgba((255, 255, 255, alpha), alpha_step=12 if IS_WEB else 1)[3]
        surf = _ground_spike_icon_cache.get(a)
        if surf is None:
            surf = pygame.Surface((12, 10), pygame.SRCALPHA)
            arrow = [(6, 8), (2, 2), (10, 2)]
            pygame.draw.polygon(
                surf,
                (GROUND_SPIKES_COLOR[0], GROUND_SPIKES_COLOR[1], GROUND_SPIKES_COLOR[2], a),
                arrow,
            )
            pygame.draw.polygon(surf, (255, 255, 255, max(60, a - 80)), arrow, 1)
            try:
                surf = surf.convert_alpha()
            except Exception:
                pass
            _ground_spike_icon_cache[a] = surf
        return surf

    def _draw_tapered_line_local(surf: pygame.Surface, color_rgba: tuple[int, ...],
                                 p0: tuple[float, float], p1: tuple[float, float],
                                 w0: float, w1: float) -> None:
        dx, dy = (p1[0] - p0[0], p1[1] - p0[1])
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        nx, ny = -dy / length, dx / length
        hw0 = w0 * 0.5
        hw1 = w1 * 0.5
        pts = [
            (p0[0] + nx * hw0, p0[1] + ny * hw0),
            (p0[0] - nx * hw0, p0[1] - ny * hw0),
            (p1[0] - nx * hw1, p1[1] - ny * hw1),
            (p1[0] + nx * hw1, p1[1] + ny * hw1),
        ]
        pygame.draw.polygon(surf, color_rgba, pts)

    def _draw_tapered_x_local(surf: pygame.Surface, size_px: int,
                              outline_col: tuple[int, ...], fill_col: tuple[int, ...]) -> None:
        a = size_px * 0.2
        b = size_px * 0.8
        thick_center = max(3.0, size_px * 0.22)
        thin_tip = max(1.5, thick_center * 0.35)
        _draw_tapered_line_local(surf, outline_col, (a, a), (b, b), thin_tip * 1.8, thick_center * 1.85)
        _draw_tapered_line_local(surf, outline_col, (b, a), (a, b), thin_tip * 1.8, thick_center * 1.85)
        _draw_tapered_line_local(surf, fill_col, (a, a), (b, b), thin_tip, thick_center)
        _draw_tapered_line_local(surf, fill_col, (b, a), (a, b), thin_tip, thick_center)

    def _cached_vuln_mark_surface(size: int, fill_rgb: tuple[int, int, int], alpha: int) -> pygame.Surface | None:
        size_px = max(8, int(size))
        alpha_q = _normalize_rgba((0, 0, 0, alpha), alpha_step=12 if IS_WEB else 1)[3]
        if alpha_q <= 0:
            return None
        rgb = tuple(max(0, min(255, int(round(c / 8.0) * 8))) for c in fill_rgb[:3])
        key = (size_px, rgb, alpha_q)
        surf = _vuln_mark_surface_cache.get(key)
        if surf is None:
            surf = pygame.Surface((size_px, size_px), pygame.SRCALPHA)
            _draw_tapered_x_local(surf, size_px, (0, 0, 0, alpha_q), (rgb[0], rgb[1], rgb[2], alpha_q))
            try:
                surf = surf.convert_alpha()
            except Exception:
                pass
            _vuln_mark_surface_cache[key] = surf
        return surf

    def _cached_ellipse_surface(width: int, height: int, color: tuple[int, ...], *, line_width: int = 0) -> pygame.Surface:
        w = max(1, int(width))
        h = max(1, int(height))
        lw = max(0, int(line_width))
        rgba = tuple(max(0, min(255, int(v))) for v in color)
        key = (w, h, rgba, lw)
        surf = _ellipse_surface_cache.get(key)
        if surf is None:
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            if lw > 0:
                pygame.draw.ellipse(surf, rgba, surf.get_rect(), lw)
            else:
                pygame.draw.ellipse(surf, rgba, surf.get_rect())
            _ellipse_surface_cache[key] = surf
        return surf

    def _blit_cached_ellipse(screen: pygame.Surface, center: tuple[int, int], width: int, height: int,
                             color: tuple[int, ...], *, line_width: int = 0) -> None:
        surf = _cached_ellipse_surface(width, height, color, line_width=line_width)
        screen.blit(surf, surf.get_rect(center=(int(center[0]), int(center[1]))))

    def _cached_text_surface(text: str, color: tuple[int, ...], *, size: int = 18, bold: bool = False) -> pygame.Surface:
        rgba = tuple(max(0, min(255, int(v))) for v in color)
        key = (max(1, int(size)), bool(bold), rgba, str(text))
        surf = _text_surface_cache.get(key)
        if surf is None:
            font = cached_sys_font(size, bold=bold)
            surf = font.render(str(text), True, rgba)
            try:
                surf = surf.convert_alpha()
            except Exception:
                pass
            _text_surface_cache[key] = surf
        return surf

    def _draw_web_lite_ui_topbar(screen: pygame.Surface, game_state, player, *, time_left: float | None = None) -> None:
        view_w, view_h = screen.get_size()
        runtime = _runtime()
        meta = rs.meta(game)
        pygame.draw.rect(screen, (0, 0, 0), (0, 0, view_w, INFO_BAR_HEIGHT))

        timer_left = max(0.0, float(time_left if time_left is not None else runtime.get("_time_left_runtime", LEVEL_TIME_LIMIT)))
        mins = int(timer_left // 60)
        secs = int(timer_left % 60)
        level_idx = int(getattr(game_state, "current_level", 0))
        timer_surf = _cached_text_surface(f"{mins:02d}:{secs:02d}", (255, 255, 255), size=28, bold=True)
        level_surf = _cached_text_surface(f"LV {level_idx + 1:02d}", (255, 255, 255), size=22, bold=True)
        bdg_surf = _cached_text_surface(f"BDG {budget_for_level(level_idx)}", (220, 220, 230), size=22, bold=True)
        center_x = view_w // 2
        screen.blit(timer_surf, timer_surf.get_rect(midtop=(center_x, 8)))
        screen.blit(level_surf, level_surf.get_rect(midtop=(center_x - timer_surf.get_width() // 2 - level_surf.get_width() // 2 - 12, 8)))
        screen.blit(bdg_surf, bdg_surf.get_rect(midtop=(center_x + timer_surf.get_width() // 2 + bdg_surf.get_width() // 2 + 12, 8)))

        hp_bar_w, hp_bar_h = 240, 12
        hp_x, hp_y = 16, 14
        hp_now = int(getattr(player, "hp", 0))
        hp_max = max(1, int(getattr(player, "max_hp", 1)))
        hp_ratio = max(0.0, min(1.0, hp_now / float(hp_max)))
        pygame.draw.rect(screen, (56, 56, 56), (hp_x - 2, hp_y - 2, hp_bar_w + 4, hp_bar_h + 4), border_radius=4)
        pygame.draw.rect(screen, (34, 34, 34), (hp_x, hp_y, hp_bar_w, hp_bar_h), border_radius=3)
        pygame.draw.rect(screen, (0, 210, 90), (hp_x, hp_y, int(hp_bar_w * hp_ratio), hp_bar_h), border_radius=3)
        hp_text = _cached_text_surface(f"{hp_now}/{hp_max}", (16, 16, 16), size=20, bold=True)
        screen.blit(hp_text, hp_text.get_rect(center=(hp_x + hp_bar_w // 2, hp_y + hp_bar_h // 2 + 1)))

        xp_bar_w, xp_bar_h = hp_bar_w, 6
        xp_x, xp_y = hp_x, hp_y + hp_bar_h + 8
        xp_now = int(getattr(player, "xp", 0))
        xp_need = max(1, int(getattr(player, "xp_to_next", 1)))
        xp_ratio = max(0.0, min(1.0, xp_now / float(xp_need)))
        pygame.draw.rect(screen, (56, 56, 56), (xp_x - 2, xp_y - 2, xp_bar_w + 4, xp_bar_h + 4), border_radius=4)
        pygame.draw.rect(screen, (34, 34, 34), (xp_x, xp_y, xp_bar_w, xp_bar_h), border_radius=3)
        pygame.draw.rect(screen, (120, 110, 255), (xp_x, xp_y, int(xp_bar_w * xp_ratio), xp_bar_h), border_radius=3)
        lvl_surf = _cached_text_surface(f"Lv {int(getattr(player, 'level', 1))}", (220, 220, 235), size=18, bold=True)
        screen.blit(lvl_surf, (xp_x + xp_bar_w + 8, xp_y - 7))

        icon_x = view_w - 112
        icon_y = 10
        pygame.draw.circle(screen, (255, 255, 0), (icon_x, icon_y + 8), 8)
        items_surf = _cached_text_surface(f"{int(meta.get('run_items_collected', 0))}", (255, 255, 255), size=24, bold=True)
        screen.blit(items_surf, (icon_x + 16, icon_y - 2))
        coin_x = view_w - 208
        pygame.draw.circle(screen, (255, 215, 80), (coin_x, icon_y + 8), 8)
        pygame.draw.circle(screen, (255, 245, 200), (coin_x, icon_y + 8), 8, 1)
        spoils_total = int(meta.get("spoils", 0)) + int(getattr(game_state, "spoils_gained", 0))
        spoils_surf = _cached_text_surface(f"{spoils_total}", (255, 255, 255), size=24, bold=True)
        screen.blit(spoils_surf, (coin_x + 14, icon_y - 2))

        def _draw_skill_card(x: int, y: int, label: str, key_txt: str, cd: float, cd_total: float, palette: dict[str, tuple[int, int, int]]):
            w, h = 84, 56
            rect = pygame.Rect(x, y, w, h)
            pygame.draw.rect(screen, palette["bg"], rect, border_radius=10)
            pygame.draw.rect(screen, palette["border"], rect, 2, border_radius=10)
            cx = x + w - 18
            cy = y + 18
            if label == "BLAST":
                pygame.draw.circle(screen, palette["accent"], (cx, cy), 9, 2)
                pygame.draw.line(screen, palette["accent"], (cx, cy - 12), (cx, cy + 12), 2)
                pygame.draw.line(screen, palette["accent"], (cx - 12, cy), (cx + 12, cy), 2)
            else:
                pygame.draw.rect(screen, palette["accent"], (cx - 2, cy - 12, 4, 24))
                pygame.draw.rect(screen, palette["accent"], (cx - 12, cy - 2, 24, 4))
                pygame.draw.circle(screen, palette["accent_dim"], (cx, cy), 9, 2)
            label_surf = _cached_text_surface(label, palette["text"], size=13, bold=True)
            key_surf = _cached_text_surface(key_txt, palette["key"], size=13, bold=True)
            screen.blit(label_surf, (x + 8, y + h - 28))
            screen.blit(key_surf, (x + 8, y + h - 14))
            if cd > 0.0 and cd_total > 0.0:
                ratio = max(0.0, min(1.0, cd / cd_total))
                cover_h = int(h * ratio)
                if cover_h > 0:
                    pygame.draw.rect(screen, (0, 0, 0), (x, y, w, cover_h), border_radius=10)
                cd_surf = _cached_text_surface(f"{int(math.ceil(cd))}", palette["text"], size=16, bold=True)
                screen.blit(cd_surf, cd_surf.get_rect(center=(x + w - 14, y + h // 2)))

        bottom_margin = 10
        right_x = view_w - 96
        bottom_y = view_h - 56 - bottom_margin
        _draw_skill_card(
            right_x,
            bottom_y - 62,
            "BLAST",
            "Q",
            float(getattr(player, "blast_cd", 0.0)),
            BLAST_COOLDOWN,
            {
                "bg": (30, 16, 16),
                "border": (200, 96, 52),
                "accent": (255, 128, 64),
                "accent_dim": (200, 96, 52),
                "text": (240, 200, 180),
                "key": (255, 180, 130),
            },
        )
        _draw_skill_card(
            right_x,
            bottom_y,
            "TELEPORT",
            "E",
            float(getattr(player, "teleport_cd", 0.0)),
            TELEPORT_COOLDOWN,
            {
                "bg": (16, 26, 38),
                "border": (72, 150, 215),
                "accent": (96, 208, 255),
                "accent_dim": (72, 150, 215),
                "text": (216, 232, 250),
                "key": (150, 220, 255),
            },
        )

    def _cached_iso_tile_surface(color: tuple[int, ...], *, border: int = 0) -> pygame.Surface:
        rgba = tuple(max(0, min(255, int(v))) for v in color)
        key = (int(ISO_CELL_W), int(ISO_CELL_H), rgba, max(0, int(border)))
        surf = _iso_tile_surface_cache.get(key)
        if surf is None:
            w = int(ISO_CELL_W) + 2
            h = int(ISO_CELL_H) + 2
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            cx = w // 2
            pts = [
                (cx, 1),
                (w - 1, h // 2),
                (cx, h - 1),
                (1, h // 2),
            ]
            pygame.draw.polygon(surf, rgba, pts, max(0, int(border)))
            try:
                surf = surf.convert_alpha()
            except Exception:
                pass
            _iso_tile_surface_cache[key] = surf
        return surf

    def _blit_cached_iso_tile(screen: pygame.Surface, gx: int, gy: int, color: tuple[int, ...],
                              camx: float, camy: float, *, border: int = 0) -> None:
        surf = _cached_iso_tile_surface(color, border=border)
        sx, sy = iso_world_to_screen(gx, gy, 0, camx, camy)
        screen.blit(surf, (int(sx - ISO_CELL_W // 2 - 1), int(sy - 1)))

    def _cached_iso_wall_surface(style: str, color: tuple[int, ...], *, wall_h: int) -> tuple[pygame.Surface, int, int]:
        rgba = tuple(max(0, min(255, int(v))) for v in color)
        style_name = str(style or "billboard")
        wall_h = max(0, int(wall_h))
        key = (style_name, wall_h, rgba)
        cached = _iso_wall_surface_cache.get(key)
        if cached is not None:
            return cached
        if style_name == "billboard":
            surf = _cached_iso_tile_surface(rgba, border=0)
            cached = (surf, int(ISO_CELL_W // 2 + 1), 1)
            _iso_wall_surface_cache[key] = cached
            return cached

        pad_top = 0
        rect_w = rect_h = 0
        if style_name == "hybrid":
            rect_h = int(ISO_CELL_H * 1.8)
            rect_w = int(ISO_CELL_W * 0.35)
            pad_top = max(0, rect_h - ISO_CELL_H // 2)
        w = int(ISO_CELL_W) + 2
        h = int(ISO_CELL_H) + wall_h + pad_top + 2
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        cx = w // 2
        top_y = pad_top + 1
        top = [
            (cx, top_y),
            (w - 1, top_y + ISO_CELL_H // 2),
            (cx, top_y + ISO_CELL_H),
            (1, top_y + ISO_CELL_H // 2),
        ]
        r = [
            top[1],
            (top[1][0], top[1][1] + wall_h),
            (top[2][0], top[2][1] + wall_h),
            top[2],
        ]
        l = [
            top[3],
            top[2],
            (top[2][0], top[2][1] + wall_h),
            (top[3][0], top[3][1] + wall_h),
        ]
        c_top = rgba
        c_r = tuple(max(0, int(c * 0.78)) for c in rgba[:3])
        c_l = tuple(max(0, int(c * 0.58)) for c in rgba[:3])
        pygame.draw.polygon(surf, c_l, l)
        pygame.draw.polygon(surf, c_r, r)
        pygame.draw.polygon(surf, c_top, top)
        if style_name == "hybrid":
            pillar = pygame.Rect(0, 0, max(2, rect_w), max(2, rect_h))
            pillar.midbottom = (cx, top_y + ISO_CELL_H // 2)
            pygame.draw.rect(surf, rgba, pillar, border_radius=max(1, rect_w // 3))
        try:
            surf = surf.convert_alpha()
        except Exception:
            pass
        cached = (surf, cx, top_y)
        _iso_wall_surface_cache[key] = cached
        return cached

    def _blit_cached_iso_wall(screen: pygame.Surface, gx: int, gy: int, color: tuple[int, ...],
                              camx: float, camy: float, *, wall_h: int | None = None) -> None:
        if wall_h is None:
            wall_h = ISO_WALL_Z if WALL_STYLE == "prism" else (12 if WALL_STYLE == "hybrid" else 0)
        surf, anchor_x, anchor_y = _cached_iso_wall_surface(WALL_STYLE, color, wall_h=wall_h)
        sx, sy = iso_world_to_screen(gx, gy, 0, camx, camy)
        screen.blit(surf, (int(sx - anchor_x), int(sy - anchor_y)))

    def _get_iso_floor_cache() -> dict[str, object]:
        runtime = _runtime()
        key = (
            int(GRID_SIZE),
            int(ISO_CELL_W),
            int(ISO_CELL_H),
            int(INFO_BAR_HEIGHT),
            tuple(max(0, min(255, int(v))) for v in MAP_GRID),
        )
        cached = runtime.get("_iso_floor_cache")
        if isinstance(cached, dict) and cached.get("key") == key:
            return cached
        started = time.perf_counter()
        half_w = ISO_CELL_W * 0.5
        half_h = ISO_CELL_H * 0.5
        min_x = max_x = min_y = max_y = None
        for gx in range(GRID_SIZE):
            for gy in range(GRID_SIZE):
                cx = (gx - gy) * half_w
                cy = (gx + gy) * half_h + INFO_BAR_HEIGHT
                pts = (
                    (cx, cy),
                    (cx + ISO_CELL_W * 0.5, cy + ISO_CELL_H * 0.5),
                    (cx, cy + ISO_CELL_H),
                    (cx - ISO_CELL_W * 0.5, cy + ISO_CELL_H * 0.5),
                )
                for px, py in pts:
                    min_x = px if min_x is None else min(min_x, px)
                    max_x = px if max_x is None else max(max_x, px)
                    min_y = py if min_y is None else min(min_y, py)
                    max_y = py if max_y is None else max(max_y, py)
        x0 = int(math.floor(float(min_x or 0.0))) - 2
        y0 = int(math.floor(float(min_y or 0.0))) - 2
        width = max(1, int(math.ceil(float(max_x or 0.0))) - x0 + 3)
        height = max(1, int(math.ceil(float(max_y or 0.0))) - y0 + 3)
        surface = pygame.Surface((width, height))
        surface.fill(MAP_BG)
        tile = _cached_iso_tile_surface(MAP_GRID, border=1)
        for gx in range(GRID_SIZE):
            for gy in range(GRID_SIZE):
                sx, sy = iso_world_to_screen(gx, gy, 0, 0, 0)
                surface.blit(tile, (int(sx - ISO_CELL_W // 2 - 1 - x0), int(sy - 1 - y0)))
        try:
            surface = surface.convert()
        except Exception:
            pass
        cached = {"key": key, "surface": surface, "x0": x0, "y0": y0}
        runtime["_iso_floor_cache"] = cached
        _record_runtime_timing("iso_floor_build", (time.perf_counter() - started) * 1000.0)
        return cached

    def _blit_iso_floor(screen: pygame.Surface, camx: float, camy: float) -> None:
        if not getattr(game, "IS_WEB", False):
            return
        cache = _get_iso_floor_cache()
        surface = cache.get("surface")
        if not isinstance(surface, pygame.Surface):
            return
        dest_x = int(cache.get("x0", 0) - camx)
        dest_y = int(cache.get("y0", 0) - camy)
        view_w, view_h = screen.get_size()
        src_x = max(0, -dest_x)
        src_y = max(0, -dest_y)
        src_w = min(surface.get_width() - src_x, max(0, view_w - max(0, dest_x)))
        src_h = min(surface.get_height() - src_y, max(0, view_h - max(0, dest_y)))
        if src_w <= 0 or src_h <= 0:
            return
        screen.blit(
            surface,
            (dest_x + src_x, dest_y + src_y),
            area=pygame.Rect(int(src_x), int(src_y), int(src_w), int(src_h)),
        )

    def _wall_sort_world_y(gx: int, gy: int) -> int:
        _, sy = iso_world_to_screen(gx, gy, 0, 0, 0)
        wall_h = ISO_WALL_Z if WALL_STYLE == "prism" else (12 if WALL_STYLE == "hybrid" else 0)
        return int(sy + ISO_CELL_H + wall_h)

    def _wall_visual_color(ob) -> tuple[int, int, int]:
        base_col = (120, 120, 120) if getattr(ob, "type", "") == "Indestructible" else (200, 80, 80)
        if getattr(ob, "type", "") == "Destructible" and getattr(ob, "health", None) is not None:
            t = max(0.4, min(1.0, float(ob.health) / float(max(1, OBSTACLE_HEALTH))))
            base_col = (int(200 * t), int(80 * t), int(80 * t))
        return base_col

    def _get_web_wall_order(game_state) -> list[tuple[int, int, int]]:
        if not IS_WEB:
            return []
        key = (
            int(getattr(game_state, "_obstacle_revision", 0) or 0),
            int(GRID_SIZE),
            str(WALL_STYLE),
            int(ISO_CELL_H),
            int(ISO_WALL_Z),
        )
        cached = getattr(game_state, "_web_wall_order_cache", None)
        if isinstance(cached, dict) and cached.get("key") == key:
            return list(cached.get("entries", ()))
        entries: list[tuple[int, int, int]] = []
        for (gx, gy), ob in getattr(game_state, "obstacles", {}).items():
            if getattr(ob, "type", "") in {"Lantern", "StationaryTurret"}:
                continue
            entries.append((_wall_sort_world_y(gx, gy), int(gx), int(gy)))
        entries.sort(key=lambda item: item[0])
        setattr(game_state, "_web_wall_order_cache", {"key": key, "entries": entries})
        return entries

    def _get_web_wall_layer_cache(game_state, *, wall_h: int) -> dict[str, object]:
        key = (
            int(getattr(game_state, "_obstacle_revision", 0) or 0),
            int(wall_h),
            int(GRID_SIZE),
            int(ISO_CELL_W),
            int(ISO_CELL_H),
            str(WALL_STYLE),
        )
        cached = getattr(game_state, "_web_wall_layer_cache", None)
        if isinstance(cached, dict) and cached.get("key") == key:
            return cached
        started = time.perf_counter()
        entries = _get_web_wall_order(game_state)
        blits: list[tuple[pygame.Surface, int, int]] = []
        min_x = min_y = max_x = max_y = None
        for _, gx, gy in entries:
            ob = getattr(game_state, "obstacles", {}).get((gx, gy))
            if ob is None:
                continue
            surf, anchor_x, anchor_y = _cached_iso_wall_surface(
                WALL_STYLE,
                _wall_visual_color(ob),
                wall_h=wall_h,
            )
            sx, sy = iso_world_to_screen(gx, gy, 0, 0, 0)
            left = int(sx - anchor_x)
            top = int(sy - anchor_y)
            right = left + surf.get_width()
            bottom = top + surf.get_height()
            min_x = left if min_x is None else min(min_x, left)
            min_y = top if min_y is None else min(min_y, top)
            max_x = right if max_x is None else max(max_x, right)
            max_y = bottom if max_y is None else max(max_y, bottom)
            blits.append((surf, left, top))
        if not blits:
            cached = {"key": key, "surface": None, "x0": 0, "y0": 0}
            setattr(game_state, "_web_wall_layer_cache", cached)
            return cached
        x0 = int(min_x) - 2
        y0 = int(min_y) - 2
        width = max(1, int(max_x) - x0 + 3)
        height = max(1, int(max_y) - y0 + 3)
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        for surf, left, top in blits:
            surface.blit(surf, (left - x0, top - y0))
        try:
            surface = surface.convert_alpha()
        except Exception:
            pass
        cached = {"key": key, "surface": surface, "x0": x0, "y0": y0}
        setattr(game_state, "_web_wall_layer_cache", cached)
        _record_runtime_timing("web_wall_build", (time.perf_counter() - started) * 1000.0)
        return cached

    def _blit_web_wall_layer(screen: pygame.Surface, game_state, camx: float, camy: float, *, wall_h: int) -> None:
        cache = _get_web_wall_layer_cache(game_state, wall_h=wall_h)
        surface = cache.get("surface")
        if not isinstance(surface, pygame.Surface):
            return
        dest_x = int(cache.get("x0", 0) - camx)
        dest_y = int(cache.get("y0", 0) - camy)
        view_w, view_h = screen.get_size()
        src_x = max(0, -dest_x)
        src_y = max(0, -dest_y)
        src_w = min(surface.get_width() - src_x, max(0, view_w - max(0, dest_x)))
        src_h = min(surface.get_height() - src_y, max(0, view_h - max(0, dest_y)))
        if src_w <= 0 or src_h <= 0:
            return
        screen.blit(
            surface,
            (dest_x + src_x, dest_y + src_y),
            area=pygame.Rect(int(src_x), int(src_y), int(src_w), int(src_h)),
        )

    def _blit_web_wall_layer_slice(
        screen: pygame.Surface,
        game_state,
        camx: float,
        camy: float,
        *,
        wall_h: int,
        clip_top_px: int,
        clip_bottom_px: int,
    ) -> None:
        cache = _get_web_wall_layer_cache(game_state, wall_h=wall_h)
        surface = cache.get("surface")
        if not isinstance(surface, pygame.Surface):
            return
        view_w, view_h = screen.get_size()
        clip_top = max(0, min(int(view_h), int(clip_top_px)))
        clip_bottom = max(clip_top, min(int(view_h), int(clip_bottom_px)))
        if clip_bottom <= clip_top:
            return
        dest_x = int(cache.get("x0", 0) - camx)
        dest_y = int(cache.get("y0", 0) - camy)
        slice_rect = pygame.Rect(0, clip_top, int(view_w), int(clip_bottom - clip_top))
        wall_rect = pygame.Rect(dest_x, dest_y, surface.get_width(), surface.get_height())
        overlap = slice_rect.clip(wall_rect)
        if overlap.width <= 0 or overlap.height <= 0:
            return
        src = pygame.Rect(
            int(overlap.x - dest_x),
            int(overlap.y - dest_y),
            int(overlap.width),
            int(overlap.height),
        )
        screen.blit(surface, overlap.topleft, area=src)

    def _get_web_static_background_cache(game_state, *, wall_h: int) -> dict[str, object]:
        floor_cache = _get_iso_floor_cache()
        wall_cache = _get_web_wall_layer_cache(game_state, wall_h=wall_h)
        floor_surface = floor_cache.get("surface")
        wall_surface = wall_cache.get("surface")
        floor_key = tuple(floor_cache.get("key", ()))
        wall_key = tuple(wall_cache.get("key", ()))
        key = (floor_key, wall_key)
        cached = getattr(game_state, "_web_static_bg_cache", None)
        if isinstance(cached, dict) and cached.get("key") == key:
            return cached
        started = time.perf_counter()
        if not isinstance(floor_surface, pygame.Surface):
            cached = {"key": key, "surface": None, "x0": 0, "y0": 0}
            setattr(game_state, "_web_static_bg_cache", cached)
            return cached
        x0 = int(floor_cache.get("x0", 0))
        y0 = int(floor_cache.get("y0", 0))
        max_x = x0 + floor_surface.get_width()
        max_y = y0 + floor_surface.get_height()
        if isinstance(wall_surface, pygame.Surface):
            wall_x0 = int(wall_cache.get("x0", 0))
            wall_y0 = int(wall_cache.get("y0", 0))
            x0 = min(x0, wall_x0)
            y0 = min(y0, wall_y0)
            max_x = max(max_x, wall_x0 + wall_surface.get_width())
            max_y = max(max_y, wall_y0 + wall_surface.get_height())
        surface = pygame.Surface((max(1, max_x - x0), max(1, max_y - y0)))
        surface.fill(MAP_BG)
        surface.blit(floor_surface, (int(floor_cache.get("x0", 0)) - x0, int(floor_cache.get("y0", 0)) - y0))
        if isinstance(wall_surface, pygame.Surface):
            surface.blit(wall_surface, (int(wall_cache.get("x0", 0)) - x0, int(wall_cache.get("y0", 0)) - y0))
        try:
            surface = surface.convert()
        except Exception:
            pass
        cached = {"key": key, "surface": surface, "x0": x0, "y0": y0}
        setattr(game_state, "_web_static_bg_cache", cached)
        _record_runtime_timing("web_static_bg_build", (time.perf_counter() - started) * 1000.0)
        return cached

    def _blit_web_static_background(screen: pygame.Surface, game_state, camx: float, camy: float, *, wall_h: int) -> None:
        cache = _get_web_static_background_cache(game_state, wall_h=wall_h)
        surface = cache.get("surface")
        if not isinstance(surface, pygame.Surface):
            return
        dest_x = int(cache.get("x0", 0) - camx)
        dest_y = int(cache.get("y0", 0) - camy)
        view_w, view_h = screen.get_size()
        src_x = max(0, -dest_x)
        src_y = max(0, -dest_y)
        src_w = min(surface.get_width() - src_x, max(0, view_w - max(0, dest_x)))
        src_h = min(surface.get_height() - src_y, max(0, view_h - max(0, dest_y)))
        if src_w <= 0 or src_h <= 0:
            return
        screen.blit(
            surface,
            (dest_x + src_x, dest_y + src_y),
            area=pygame.Rect(int(src_x), int(src_y), int(src_w), int(src_h)),
        )

    def _screen_visible_point(x: float, y: float, *, margin: int = 48) -> bool:
        mx = max(0, int(margin))
        return (-mx <= int(x) <= int(game.VIEW_W) + mx) and ((INFO_BAR_HEIGHT - mx) <= int(y) <= int(game.VIEW_H) + mx)

    def _web_profiler():
        profiler = getattr(game, "_web_profiler", None)
        if not getattr(game, "IS_WEB", False):
            return None
        return profiler if profiler is not None and hasattr(profiler, "counter") else None

    def _render_counter(profiler, name: str, started_at: float) -> None:
        if profiler is None:
            return
        elapsed_ms = max(0.0, (time.perf_counter() - started_at) * 1000.0)
        profiler.counter(str(name), round(elapsed_ms, 3))

    def _record_runtime_timing(name: str, elapsed_ms: float) -> None:
        runtime = _runtime()
        runtime[f"_{name}_ms"] = max(0.0, float(elapsed_ms))
        runtime[f"_{name}_at_ms"] = int(pygame.time.get_ticks())

    def _emit_recent_runtime_timing(profiler, counter_name: str, runtime_name: str, *, ttl_ms: int = 250) -> None:
        if profiler is None:
            return
        runtime = _runtime()
        stamp = int(runtime.get(f"_{runtime_name}_at_ms", -999999) or -999999)
        if (int(pygame.time.get_ticks()) - stamp) > int(ttl_ms):
            return
        value = runtime.get(f"_{runtime_name}_ms", None)
        if isinstance(value, (int, float)):
            profiler.counter(counter_name, round(float(value), 3))

    def _emit_actor_subcounters(profiler, samples: dict[str, float]) -> None:
        if profiler is None:
            return
        name_map = {
            "wall": "r_wall_actor_ms",
            "pickup": "r_pickup_actor_ms",
            "turret": "r_turret_actor_ms",
            "projectile": "r_projectile_actor_ms",
            "enemy": "r_enemy_actor_ms",
            "player": "r_player_actor_ms",
        }
        for key, counter_name in name_map.items():
            value = float(samples.get(key, 0.0) or 0.0)
            profiler.counter(counter_name, round(max(0.0, value), 3))

    def _transition_ready_for_short_circuit() -> bool:
        if not getattr(game, "IS_WEB", False):
            return False
        runtime = _runtime()
        web_state = runtime.get("_web_hex_transition_state")
        if isinstance(web_state, dict):
            return True
        if runtime.get("_menu_transition_frame") is None:
            return False
        return runtime.get("_menu_transition_target_frame") is not None

    def _screen_visible_circle(x: float, y: float, radius: float, *, margin: int = 0) -> bool:
        return _screen_visible_point(x, y, margin=max(int(margin), int(radius)))

    def _iso_view_world_rect(camx: float, camy: float, *, pad_px: int = 0) -> pygame.Rect:
        corners = (
            game.iso_screen_to_world_px(0, 0, camx, camy),
            game.iso_screen_to_world_px(game.VIEW_W, 0, camx, camy),
            game.iso_screen_to_world_px(0, game.VIEW_H, camx, camy),
            game.iso_screen_to_world_px(game.VIEW_W, game.VIEW_H, camx, camy),
        )
        min_x = min((p[0] for p in corners)) - int(pad_px)
        max_x = max((p[0] for p in corners)) + int(pad_px)
        min_y = min((p[1] for p in corners)) - int(pad_px)
        max_y = max((p[1] for p in corners)) + int(pad_px)
        return pygame.Rect(
            int(min_x),
            int(min_y),
            max(1, int(max_x - min_x)),
            max(1, int(max_y - min_y)),
        )

    def _cap_visible_entries(entries: list, cap: int, *, key=None) -> list:
        if cap > 0 and len(entries) > cap:
            if key is not None:
                entries.sort(key=key)
            del entries[cap:]
        return entries

    def _draw_web_profiler_overlay(screen: pygame.Surface) -> None:
        if not IS_WEB:
            return
        profiler = getattr(game, "_web_profiler", None)
        lines = profiler.overlay_lines() if profiler is not None and hasattr(profiler, "overlay_lines") else []
        if not lines:
            return
        font = mono_font(14)
        pad = 8
        line_h = font.get_linesize()
        width = max(font.size(line)[0] for line in lines) + pad * 2
        height = line_h * len(lines) + pad * 2
        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        panel.fill((8, 14, 26, 210))
        pygame.draw.rect(panel, (80, 210, 255, 220), panel.get_rect(), 1, border_radius=6)
        y = pad
        for idx, line in enumerate(lines):
            color = (185, 230, 255) if idx < 2 else (235, 245, 250)
            panel.blit(font.render(line, True, color), (pad, y))
            y += line_h
        screen.blit(panel, (10, max(INFO_BAR_HEIGHT + 6, 42)))

    def _begin_web_gameplay_render(screen: pygame.Surface) -> tuple[pygame.Surface, pygame.Surface | None, tuple[int, int] | None]:
        if not IS_WEB:
            return screen, None, None
        display_surface = pygame.display.get_surface() or screen
        display_size = display_surface.get_size()
        game.VIEW_W, game.VIEW_H = display_size
        return display_surface, None, None

    def _present_gameplay_render(render_surface: pygame.Surface, display_surface: pygame.Surface | None,
                                 prev_view: tuple[int, int] | None, *, copy_frame: bool) -> pygame.Surface | None:
        try:
            if display_surface is not None and render_surface is not display_surface:
                pygame.transform.scale(render_surface, display_surface.get_size(), display_surface)
                pygame.display.flip()
                return display_surface.copy() if copy_frame else None
            pygame.display.flip()
            return render_surface.copy() if copy_frame else None
        finally:
            if prev_view is not None:
                game.VIEW_W, game.VIEW_H = prev_view

    def draw_settings_gear(screen, x, y):
        """Draw a simple gear icon at (x,y) top-left; returns its rect."""
        rect = pygame.Rect(x, y, 32, 24)
        pygame.draw.rect(screen, (50, 50, 50), rect, 2)
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

    def _current_music_pos_ms() -> int | None:
        """Safe wrapper for pygame.mixer.music.get_pos(), returning None if not playing."""
        runtime = _runtime()
        bgm = runtime.get("_bgm")
        if bgm is not None and hasattr(bgm, "position_ms"):
            try:
                pos = bgm.position_ms()
                if pos is not None:
                    return int(pos)
            except Exception:
                pass
        try:
            pos = pygame.mixer.music.get_pos()
            if pos is None or pos < 0:
                return None
            return int(pos)
        except Exception:
            return None

    def _music_is_busy() -> bool:
        """Safe wrapper for pygame.mixer.music.get_busy()."""
        runtime = _runtime()
        bgm = runtime.get("_bgm")
        if bgm is not None and hasattr(bgm, "is_busy"):
            try:
                return bool(bgm.is_busy())
            except Exception:
                pass
        try:
            if not pygame.mixer.get_init():
                return False
            return bool(pygame.mixer.music.get_busy())
        except Exception:
            return False

    def _resume_bgm_if_needed(min_interval_s: float = 1.25) -> bool:
        """Retry BGM playback when browser autoplay or a scene swap left music stopped."""
        if _music_is_busy() or _current_music_pos_ms() is not None:
            return True
        runtime = _runtime()
        bgm = runtime.get("_bgm")
        if bgm is None or not getattr(bgm, "_ready", False):
            return False
        if IS_WEB:
            min_interval_s = max(float(min_interval_s), 0.35)
        now_s = pygame.time.get_ticks() / 1000.0
        last_retry_s = float(runtime.get("_last_bgm_resume_retry_s", -999.0))
        if (now_s - last_retry_s) < float(min_interval_s):
            return False
        runtime["_last_bgm_resume_retry_s"] = now_s
        try:
            bgm.playBackGroundMusic(loops=-1, fade_ms=0)
            return True
        except Exception as e:
            print(f"[Audio] resume retry failed: {e}")
            return False

    def play_focus_chain_iso(screen, clock, game_state, player, enemies, bullets, enemy_shots, targets,
                             hold_time=0.9, label="BOSS"):
        """
        targets: list of (x_px, y_px) world-pixel centers (e.g., rect.centerx, rect.centery).
        Plays boss -> boss -> ... -> player (once).
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
        - 相机从 start_cam(若无则玩家) -> 焦点；可选 焦点 -> 玩家。
        - 冻结时间与世界更新，仅渲染。
        """
        web_focus = bool(IS_WEB)
        if web_focus:
            duration_each = min(float(duration_each), float(getattr(game, "WEB_FOCUS_PAN_DURATION", 0.18) or 0.18))
            hold_time = min(float(hold_time), float(getattr(game, "WEB_FOCUS_HOLD_TIME", 0.08) or 0.08))

        def _cam_for_world_px(wx: float, wy: float) -> tuple[int, int]:
            gx = wx / CELL_SIZE
            gy = (wy - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(gx, gy, 0.0, 0.0, 0.0)
            camx = int(sx - game.VIEW_W // 2)
            camy = int(sy - (game.VIEW_H - INFO_BAR_HEIGHT) // 2)
            return camx, camy

        def _cam_for_player() -> tuple[int, int]:
            return calculate_iso_camera(player.x + player.size * 0.5,
                                        player.y + player.size * 0.5 + INFO_BAR_HEIGHT)

        def _lerp(a: float, b: float, t: float) -> float:
            return a + (b - a) * max(0.0, min(1.0, t))

        def _do_pan(cam_a: tuple[int, int], cam_b: tuple[int, int], dur: float):
            if web_focus:
                steps = max(2, min(6, int(round(max(0.06, dur) * 24.0))))
                for idx in range(steps + 1):
                    for ev in pygame.event.get():
                        if ev.type == pygame.QUIT:
                            pygame.quit()
                            sys.exit()
                    t = float(idx) / float(max(1, steps))
                    camx = int(_lerp(cam_a[0], cam_b[0], t))
                    camy = int(_lerp(cam_a[1], cam_b[1], t))
                    render_game_iso(
                        screen,
                        game_state,
                        player,
                        enemies,
                        bullets,
                        enemy_shots,
                        game_state.obstacles,
                        override_cam=(camx, camy),
                    )
                    if label:
                        font = pygame.font.SysFont(None, 42)
                        txt = font.render(label, True, (255, 230, 120))
                        screen.blit(txt, txt.get_rect(center=(game.VIEW_W // 2, INFO_BAR_HEIGHT + 50)))
                        pygame.display.flip()
                return
            start = pygame.time.get_ticks()
            while True:
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        pygame.quit()
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
                    screen.blit(txt, txt.get_rect(center=(game.VIEW_W // 2, INFO_BAR_HEIGHT + 50)))
                    pygame.display.flip()
                clock.tick(60)
                if t >= 1.0:
                    break

        player_cam = _cam_for_player()
        fx, fy = focus_world_px
        focus_cam = _cam_for_world_px(fx, fy)
        start_from = start_cam if start_cam is not None else player_cam
        _do_pan(start_from, focus_cam, duration_each)
        if web_focus:
            hold_frames = max(0, min(2, int(round(hold_time * 20.0))))
            for _ in range(hold_frames):
                render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots,
                                game_state.obstacles, override_cam=focus_cam)
                if label:
                    font = pygame.font.SysFont(None, 42)
                    txt = font.render(label, True, (255, 230, 120))
                    screen.blit(txt, txt.get_rect(center=(game.VIEW_W // 2, INFO_BAR_HEIGHT + 50)))
                    pygame.display.flip()
        else:
            hold_start = pygame.time.get_ticks()
            while (pygame.time.get_ticks() - hold_start) < int(hold_time * 1000):
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        pygame.quit()
                        sys.exit()
                render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots,
                                game_state.obstacles, override_cam=focus_cam)
                if label:
                    font = pygame.font.SysFont(None, 42)
                    txt = font.render(label, True, (255, 230, 120))
                    screen.blit(txt, txt.get_rect(center=(game.VIEW_W // 2, INFO_BAR_HEIGHT + 50)))
                    pygame.display.flip()
                clock.tick(60)
        if return_to_player:
            _do_pan(focus_cam, player_cam, duration_each)
        flush_events()

    def render_game_iso_web_lite(screen, game_state, player, enemies, bullets, enemy_shots, obstacles=None,
                                 override_cam: tuple[int, int] | None = None,
                                 copy_frame: bool = True) -> pygame.Surface | None:
        obstacles = obstacles if obstacles is not None else getattr(game_state, "obstacles", {})
        screen, display_surface, prev_view = _begin_web_gameplay_render(screen)
        view_w, view_h = screen.get_size()
        profiler = _web_profiler()
        if _transition_ready_for_short_circuit():
            transition_started = time.perf_counter()
            screen.fill(MAP_BG)
            run_pending_menu_transition(screen)
            _render_counter(profiler, "r_transition_ms", transition_started)
            _draw_web_profiler_overlay(screen)
            return _present_gameplay_render(screen, display_surface, prev_view, copy_frame=copy_frame)
        pickup_cap = int(getattr(game, "WEB_LITE_RENDER_PICKUP_CAP", 0) or 0)
        turret_cap = int(getattr(game, "WEB_LITE_RENDER_TURRET_CAP", 0) or 0)
        enemy_cap = int(getattr(game, "WEB_LITE_RENDER_ENEMY_CAP", 0) or 0)
        bullet_cap = int(getattr(game, "WEB_LITE_RENDER_BULLET_CAP", 0) or 0)
        enemy_shot_cap = int(getattr(game, "WEB_LITE_RENDER_ENEMY_SHOT_CAP", 0) or 0)
        px_grid = (player.x + player.size / 2) / CELL_SIZE
        py_grid = (player.y + player.size / 2) / CELL_SIZE
        if override_cam is not None:
            camx, camy = override_cam
        else:
            camx, camy = calculate_iso_camera(
                player.x + player.size * 0.5,
                player.y + player.size * 0.5 + INFO_BAR_HEIGHT,
            )
        if hasattr(game_state, "camera_shake_offset"):
            dx, dy = game_state.camera_shake_offset()
            camx += dx
            camy += dy

        player_cx = float(player.rect.centerx)
        player_cy = float(player.rect.centery)
        view_world_rect = _iso_view_world_rect(camx, camy, pad_px=int(CELL_SIZE * 2))
        bg_total_started = time.perf_counter()
        segment_started = time.perf_counter()
        screen.fill(MAP_BG)
        _render_counter(profiler, "r_bg_fill_ms", segment_started)
        segment_started = time.perf_counter()
        _blit_web_static_background(screen, game_state, camx, camy, wall_h=max(12, int(ISO_WALL_Z * 0.7)))
        _render_counter(profiler, "r_bg_static_ms", segment_started)
        _emit_recent_runtime_timing(profiler, "r_bg_floor_build_ms", "iso_floor_build")
        _emit_recent_runtime_timing(profiler, "r_bg_wall_build_ms", "web_wall_build")
        _emit_recent_runtime_timing(profiler, "r_bg_compose_build_ms", "web_static_bg_build")
        _render_counter(profiler, "r_bg_ms", bg_total_started)
        margin = 2
        gx_min = max(0, int(px_grid - game.VIEW_W // max(1, ISO_CELL_W)) - margin)
        gx_max = min(GRID_SIZE - 1, int(px_grid + game.VIEW_W // max(1, ISO_CELL_W)) + margin)
        gy_min = max(0, int(py_grid - game.VIEW_H // max(1, ISO_CELL_H)) - margin)
        gy_max = min(GRID_SIZE - 1, int(py_grid + game.VIEW_H // max(1, ISO_CELL_H)) + margin)

        if getattr(player, "targeting_skill", None):
            _draw_skill_overlay(screen, player, camx, camy)

        spoil_iter = (
            game_state.query_spoils_near_rect(view_world_rect, pad_px=CELL_SIZE)
            if hasattr(game_state, "query_spoils_near_rect")
            else getattr(game_state, "spoils", ())
        )
        visible_spoils = []
        for s in spoil_iter:
            wx = s.base_x / CELL_SIZE
            wy = (s.base_y - s.h - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            if not _screen_visible_point(sx, sy, margin=24):
                continue
            dx = float(getattr(s, "base_x", 0.0)) - player_cx
            dy = float(getattr(s, "base_y", 0.0)) - player_cy
            visible_spoils.append((dx * dx + dy * dy, sx, sy, s))
        _cap_visible_entries(visible_spoils, pickup_cap, key=lambda item: item[0])
        pickup_draw_ms = 0.0
        for _, sx, sy, s in visible_spoils:
            draw_started = time.perf_counter()
            pygame.draw.circle(screen, (255, 215, 80), (int(sx), int(sy)), int(s.r))
            pickup_draw_ms += (time.perf_counter() - draw_started) * 1000.0

        heal_iter = (
            game_state.query_heals_near_rect(view_world_rect, pad_px=CELL_SIZE)
            if hasattr(game_state, "query_heals_near_rect")
            else getattr(game_state, "heals", ())
        )
        visible_heals = []
        for h in heal_iter:
            wx = h.base_x / CELL_SIZE
            wy = (h.base_y - h.h - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            if not _screen_visible_point(sx, sy, margin=24):
                continue
            dx = float(getattr(h, "base_x", 0.0)) - player_cx
            dy = float(getattr(h, "base_y", 0.0)) - player_cy
            visible_heals.append((dx * dx + dy * dy, sx, sy, h))
        _cap_visible_entries(visible_heals, pickup_cap, key=lambda item: item[0])
        for _, sx, sy, h in visible_heals:
            draw_started = time.perf_counter()
            pygame.draw.circle(screen, (225, 225, 225), (int(sx), int(sy)), int(h.r))
            pickup_draw_ms += (time.perf_counter() - draw_started) * 1000.0

        items = getattr(game_state, "items", ())
        visible_items = []
        for it in items:
            wx = it.center[0] / CELL_SIZE
            wy = (it.center[1] - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            if not _screen_visible_point(sx, sy, margin=24):
                continue
            dx = float(it.center[0]) - player_cx
            dy = float(it.center[1]) - player_cy
            visible_items.append((dx * dx + dy * dy, sx, sy, it))
        _cap_visible_entries(visible_items, pickup_cap, key=lambda item: item[0])
        for _, sx, sy, it in visible_items:
            draw_started = time.perf_counter()
            col = (255, 224, 0) if getattr(it, "is_main", False) else (240, 210, 90)
            pygame.draw.circle(screen, col, (int(sx), int(sy)), int(it.radius))
            pickup_draw_ms += (time.perf_counter() - draw_started) * 1000.0

        player_size = int(CELL_SIZE * 0.6)
        player_sprite = _load_shop_sprite(
            "characters/player/sheets/player.png",
            (
                int(player_size * 2.0 * PLAYER_SPRITE_SCALE),
                int(player_size * 2.4 * PLAYER_SPRITE_SCALE),
            ),
            allow_upscale=False,
        )
        stationary_sprite, _, _ = get_stationary_turret_assets()

        actors = []
        turrets = getattr(game_state, "turrets", ())
        visible_turrets = []
        for turret in turrets:
            wx = turret.x / CELL_SIZE
            wy = (turret.y - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            if not _screen_visible_point(sx, sy, margin=96):
                continue
            dx = float(getattr(turret, "x", 0.0)) - player_cx
            dy = float(getattr(turret, "y", 0.0)) - player_cy
            visible_turrets.append((dx * dx + dy * dy, sy, turret, sx, sy))
        _cap_visible_entries(visible_turrets, turret_cap, key=lambda item: item[0])
        for _, sy, turret, sx, sy2 in visible_turrets:
            actors.append((sy, "turret", turret, sx, sy2))

        enemy_iter = (
            getattr(game_state, "spatial").query_rect(view_world_rect, pad_px=CELL_SIZE * 2)
            if getattr(game_state, "spatial", None) is not None
            else enemies
        )
        visible_enemies = []
        for enemy in enemy_iter:
            wx = enemy.rect.centerx / CELL_SIZE
            wy = (enemy.rect.bottom - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            if not _screen_visible_point(sx, sy, margin=128):
                continue
            dx = float(enemy.rect.centerx) - player_cx
            dy = float(enemy.rect.centery) - player_cy
            visible_enemies.append((dx * dx + dy * dy, sy, enemy, sx, sy))
        _cap_visible_entries(visible_enemies, enemy_cap, key=lambda item: item[0])
        for _, sy, enemy, sx, sy2 in visible_enemies:
            actors.append((sy, "enemy", enemy, sx, sy2))

        wx = player.rect.centerx / CELL_SIZE
        wy = (player.rect.bottom - INFO_BAR_HEIGHT) / CELL_SIZE
        psx, psy = iso_world_to_screen(wx, wy, 0, camx, camy)
        actors.append((psy, "player", player, psx, psy))
        actors.sort(key=lambda item: item[0])

        segment_started = time.perf_counter()
        actor_subsamples = {"wall": 0.0, "pickup": pickup_draw_ms, "turret": 0.0, "projectile": 0.0, "enemy": 0.0, "player": 0.0}
        for _, kind, obj, sx, sy in actors:
            item_started = time.perf_counter()
            cx = int(sx)
            cy = int(sy)
            if kind == "turret":
                if isinstance(obj, StationaryTurret):
                    if stationary_sprite:
                        rect = stationary_sprite.get_rect(midbottom=(cx, cy))
                        screen.blit(stationary_sprite, rect)
                    else:
                        pygame.draw.circle(screen, (80, 180, 255), (cx, cy - 6), max(7, CELL_SIZE // 5))
                elif isinstance(obj, AutoTurret):
                    owner = getattr(obj, "owner", None)
                    dir_key = None
                    facing = getattr(owner, "facing", None)
                    if facing in ("E", "SE", "NE"):
                        dir_key = "right"
                    elif facing in ("W", "SW", "NW"):
                        dir_key = "left"
                    elif facing == "N":
                        dir_key = "up"
                    elif facing == "S":
                        dir_key = "down"
                    if dir_key is None:
                        if owner and hasattr(owner, "rect"):
                            ox, oy = owner.rect.center
                            dx, dy = cx - ox, cy - oy
                        else:
                            dx = dy = 0
                        dir_key = ("right" if dx >= 0 else "left") if abs(dx) >= abs(dy) else ("down" if dy >= 0 else "up")
                    sprite = _auto_turret_sprite(dir_key)
                    if sprite:
                        rect = sprite.get_rect(midbottom=(cx, cy))
                        screen.blit(sprite, rect)
                    else:
                        pygame.draw.circle(screen, (80, 180, 255), (cx, cy - 6), max(7, CELL_SIZE // 5))
                else:
                    pygame.draw.circle(screen, (80, 180, 255), (cx, cy - 6), max(7, CELL_SIZE // 5))
                actor_subsamples["turret"] += (time.perf_counter() - item_started) * 1000.0
            elif kind == "enemy":
                draw_size = max(int(CELL_SIZE * 0.6), int(getattr(obj, "rect", pygame.Rect(0, 0, CELL_SIZE, CELL_SIZE)).w))
                if getattr(obj, "is_boss", False) or getattr(obj, "type", "") == "ravager":
                    draw_size = max(draw_size * 2, int(getattr(obj, "rect", pygame.Rect(0, 0, CELL_SIZE, CELL_SIZE)).w * 2))
                enemy_sprite = _enemy_sprite(getattr(obj, "type", ""), draw_size)
                if enemy_sprite:
                    rect = enemy_sprite.get_rect(midbottom=(cx, cy))
                    screen.blit(enemy_sprite, rect)
                    body_r = max(8, int(draw_size * 0.18))
                    hp_anchor_y = rect.top
                else:
                    body_r = max(8, int(getattr(obj, "size", CELL_SIZE * 0.6) * 0.34))
                    body_y = int(cy - max(10, int(getattr(obj, "size", CELL_SIZE * 0.6) * 0.45)))
                    pygame.draw.circle(screen, getattr(obj, "color", (220, 90, 90)), (cx, body_y), body_r)
                    pygame.draw.circle(screen, (16, 26, 40), (cx, body_y), body_r, 2)
                    hp_anchor_y = body_y - body_r
                hp = max(0, int(getattr(obj, "hp", 0)))
                hp_max = max(1, int(getattr(obj, "max_hp", hp or 1)))
                if hp < hp_max:
                    bar_w = max(18, body_r * 2)
                    top = hp_anchor_y - 10
                    pygame.draw.rect(screen, (24, 34, 48), (cx - bar_w // 2, top, bar_w, 4))
                    pygame.draw.rect(screen, (90, 220, 120), (cx - bar_w // 2, top, int(bar_w * hp / hp_max), 4))
                flash_t = float(getattr(obj, "_hit_flash", 0.0))
                if flash_t > 0.0 and HIT_FLASH_DURATION > 0:
                    flash_ratio = min(1.0, flash_t / HIT_FLASH_DURATION)
                    flash_alpha = int(200 * flash_ratio)
                    if flash_alpha > 0:
                        if enemy_sprite:
                            _blit_cached_sprite_tint(screen, enemy_sprite, rect.topleft, (255, 255, 255, flash_alpha))
                        else:
                            overlay = _cached_filled_surface((body_r * 2 + 4, body_r * 2 + 4), (255, 255, 255, flash_alpha))
                            screen.blit(overlay, overlay.get_rect(center=(cx, body_y)).topleft)
                actor_subsamples["enemy"] += (time.perf_counter() - item_started) * 1000.0
            else:
                if player_sprite:
                    rect = player_sprite.get_rect(midbottom=(cx, cy))
                    screen.blit(player_sprite, rect)
                else:
                    body_y = int(cy - max(10, int(getattr(obj, "size", CELL_SIZE * 0.6) * 0.45)))
                    body_r = max(9, int(getattr(obj, "size", CELL_SIZE * 0.6) * 0.36))
                    pygame.draw.circle(screen, getattr(obj, "color", (110, 250, 170)), (cx, body_y), body_r)
                    pygame.draw.circle(screen, (12, 24, 40), (cx, body_y), body_r, 2)
                flash_t = float(getattr(obj, "_hit_flash", 0.0))
                if flash_t > 0.0 and HIT_FLASH_DURATION > 0:
                    flash_ratio = min(1.0, flash_t / HIT_FLASH_DURATION)
                    flash_alpha = int(200 * flash_ratio)
                    if flash_alpha > 0:
                        if player_sprite:
                            _blit_cached_sprite_tint(screen, player_sprite, rect.topleft, (255, 255, 255, flash_alpha))
                        else:
                            overlay = _cached_filled_surface((body_r * 2 + 4, body_r * 2 + 4), (255, 255, 255, flash_alpha))
                            screen.blit(overlay, overlay.get_rect(center=(cx, body_y)).topleft)
                actor_subsamples["player"] += (time.perf_counter() - item_started) * 1000.0
        _render_counter(profiler, "r_actor_ms", segment_started)
        _emit_actor_subcounters(profiler, actor_subsamples)

        segment_started = time.perf_counter()
        visible_bullets = []
        for bullet in (bullets or ()):
            wx = bullet.x / CELL_SIZE
            wy = (bullet.y - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            if not _screen_visible_point(sx, sy, margin=16):
                continue
            dx = float(getattr(bullet, "x", 0.0)) - player_cx
            dy = float(getattr(bullet, "y", 0.0)) - player_cy
            visible_bullets.append((dx * dx + dy * dy, sx, sy, bullet))
        _cap_visible_entries(visible_bullets, bullet_cap, key=lambda item: item[0])
        for _, sx, sy, bullet in visible_bullets:
            draw_started = time.perf_counter()
            col = (0, 255, 255) if getattr(bullet, "source", "player") == "turret" else (120, 204, 121)
            pygame.draw.circle(screen, col, (int(sx), int(sy)), max(2, int(getattr(bullet, "r", BULLET_RADIUS))))
            actor_subsamples["projectile"] += (time.perf_counter() - draw_started) * 1000.0

        visible_enemy_shots = []
        for shot in (enemy_shots or ()):
            wx = shot.x / CELL_SIZE
            wy = (shot.y - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            if not _screen_visible_point(sx, sy, margin=16):
                continue
            dx = float(getattr(shot, "x", 0.0)) - player_cx
            dy = float(getattr(shot, "y", 0.0)) - player_cy
            visible_enemy_shots.append((dx * dx + dy * dy, sx, sy, shot))
        _cap_visible_entries(visible_enemy_shots, enemy_shot_cap, key=lambda item: item[0])
        for _, sx, sy, shot in visible_enemy_shots:
            draw_started = time.perf_counter()
            pygame.draw.circle(
                screen,
                getattr(shot, "color", (255, 120, 50)),
                (int(sx), int(sy)),
                max(2, int(getattr(shot, "r", BULLET_RADIUS))),
            )
            actor_subsamples["projectile"] += (time.perf_counter() - draw_started) * 1000.0
        _emit_actor_subcounters(profiler, actor_subsamples)
        _render_counter(profiler, "r_projectile_ms", segment_started)

        segment_started = time.perf_counter()
        if _web_feature_enabled("WEB_ENABLE_DAMAGE_TEXTS"):
            for d in getattr(game_state, "dmg_texts", []):
                wx = d.x / CELL_SIZE
                wy = (d.y - INFO_BAR_HEIGHT) / CELL_SIZE
                sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
                sy += d.screen_offset_y()
                if not _screen_visible_point(sx, sy, margin=24):
                    continue
                d.draw_iso(screen, sx, sy)
        _render_counter(profiler, "r_overlay_ms", segment_started)

        segment_started = time.perf_counter()
        _draw_web_lite_ui_topbar(
            screen,
            game_state,
            player,
            time_left=_runtime().get("_time_left_runtime"),
        )
        bosses = _find_all_bosses(enemies)
        if len(bosses) >= 2:
            draw_boss_hp_bars_twin(screen, bosses[:2])
        elif len(bosses) == 1:
            draw_boss_hp_bar(screen, bosses[0])
        _render_counter(profiler, "r_ui_ms", segment_started)
        segment_started = time.perf_counter()
        run_pending_menu_transition(screen)
        _render_counter(profiler, "r_transition_ms", segment_started)
        _draw_web_profiler_overlay(screen)
        return _present_gameplay_render(screen, display_surface, prev_view, copy_frame=copy_frame)

    def render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots, obstacles=None,
                        override_cam: tuple[int, int] | None = None,
                        copy_frame: bool = True):
        obstacles = obstacles if obstacles is not None else getattr(game_state, "obstacles", {})
        if (
            IS_WEB
            and getattr(game, "WEB_ALLOW_LITE_RENDER", False)
            and getattr(game, "WEB_USE_LITE_RENDER", False)
        ):
            return render_game_iso_web_lite(
                screen, game_state, player, enemies, bullets, enemy_shots, obstacles,
                override_cam=override_cam,
                copy_frame=copy_frame,
            )
        screen, display_surface, prev_view = _begin_web_gameplay_render(screen)
        view_w, view_h = screen.get_size()
        profiler = _web_profiler()
        if _transition_ready_for_short_circuit():
            transition_started = time.perf_counter()
            screen.fill(MAP_BG)
            run_pending_menu_transition(screen)
            _render_counter(profiler, "r_transition_ms", transition_started)
            _draw_web_profiler_overlay(screen)
            return _present_gameplay_render(screen, display_surface, prev_view, copy_frame=copy_frame)
        px_grid = (player.x + player.size / 2) / CELL_SIZE
        py_grid = (player.y + player.size / 2) / CELL_SIZE
        pxs, pys = iso_world_to_screen(px_grid, py_grid, 0, 0, 0)
        camx = pxs - game.VIEW_W // 2
        camy = pys - (game.VIEW_H - INFO_BAR_HEIGHT) // 2
        if override_cam is not None:
            camx, camy = override_cam
        else:
            camx, camy = calculate_iso_camera(player.x + player.size * 0.5,
                                              player.y + player.size * 0.5 + INFO_BAR_HEIGHT)
        if hasattr(game_state, "camera_shake_offset"):
            dx, dy = game_state.camera_shake_offset()
            camx += dx
            camy += dy
        bg_total_started = time.perf_counter()
        segment_started = time.perf_counter()
        screen.fill(MAP_BG)
        _render_counter(profiler, "r_bg_fill_ms", segment_started)
        margin = 3
        gx_min = max(0, int(px_grid - game.VIEW_W // ISO_CELL_W) - margin)
        gx_max = min(GRID_SIZE - 1, int(px_grid + game.VIEW_W // ISO_CELL_W) + margin)
        gy_min = max(0, int(py_grid - game.VIEW_H // ISO_CELL_H) - margin)
        gy_max = min(GRID_SIZE - 1, int(py_grid + game.VIEW_H // ISO_CELL_H) + margin)
        grid_col = MAP_GRID
        if IS_WEB:
            segment_started = time.perf_counter()
            _blit_iso_floor(screen, camx, camy)
            _render_counter(profiler, "r_bg_floor_ms", segment_started)
            _emit_recent_runtime_timing(profiler, "r_bg_floor_build_ms", "iso_floor_build")
        else:
            segment_started = time.perf_counter()
            for gx in range(gx_min, gx_max + 1):
                for gy in range(gy_min, gy_max + 1):
                    _blit_cached_iso_tile(screen, gx, gy, grid_col, camx, camy, border=1)
            _render_counter(profiler, "r_bg_floor_ms", segment_started)
        _render_counter(profiler, "r_bg_ms", bg_total_started)
        view_margin = max(int(CELL_SIZE), int(ISO_CELL_W))
        view_world_rect = _iso_view_world_rect(camx, camy, pad_px=int(CELL_SIZE * 2))
        segment_started = time.perf_counter()
        for t in getattr(game_state, "telegraphs", []):
            sx, sy = iso_world_to_screen(t.x / CELL_SIZE, (t.y - INFO_BAR_HEIGHT) / CELL_SIZE, 0, camx, camy)
            if not _screen_visible_circle(sx, sy, float(getattr(t, "r", 0.0)), margin=view_margin):
                continue
            draw_iso_ground_ellipse(
                screen, t.x, t.y, t.r,
                color=t.color, alpha=180,
                camx=camx, camy=camy,
                fill=False, width=3
            )
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
        _render_counter(profiler, "r_targeting_ms", segment_started)

        segment_started = time.perf_counter()
        if _web_feature_enabled("WEB_ENABLE_HURRICANES"):
            for h in getattr(game_state, "hurricanes", []):
                hsx, hsy = iso_world_to_screen(h.x / CELL_SIZE, (h.y - INFO_BAR_HEIGHT) / CELL_SIZE, 0, camx, camy)
                if not _screen_visible_circle(hsx, hsy, float(getattr(h, "r", 0.0)) * HURRICANE_RANGE_MULT, margin=view_margin):
                    continue
                hint_started = time.perf_counter()
                if IS_WEB and hasattr(h, "draw"):
                    # The cached web tornado surface already includes the range zone.
                    # Drawing a second large translucent hint costs several ms/frame.
                    pass
                elif hasattr(h, "draw_range_hint"):
                    h.draw_range_hint(screen, camx, camy)
                else:
                    pulse = 0.6 + 0.4 * math.sin(pygame.time.get_ticks() * 0.008)
                    alpha = int(40 + 60 * pulse)
                    draw_iso_ground_ellipse(
                        screen, h.x, h.y, h.r * HURRICANE_RANGE_MULT,
                        color=(100, 120, 150), alpha=alpha,
                        camx=camx, camy=camy,
                        fill=False, width=2
                    )
                _render_counter(profiler, "r_hurricane_hint_ms", hint_started)
                draw_started = time.perf_counter()
                if hasattr(h, "draw"):
                    h.draw(screen, camx, camy)
                else:
                    hx, hy = float(h.get("x", 0)), float(h.get("y", 0))
                    draw_iso_ground_ellipse(screen, hx, hy, 40, (100, 100, 100), 200, camx, camy)
                _render_counter(profiler, "r_hurricane_draw_ms", draw_started)
        _render_counter(profiler, "r_hurricane_ms", segment_started)

        segment_started = time.perf_counter()
        if _web_feature_enabled("WEB_ENABLE_AEGIS_PULSES"):
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
                sx, sy = iso_world_to_screen(p.x / CELL_SIZE, (p.y - INFO_BAR_HEIGHT) / CELL_SIZE, 0, camx, camy)
                if not _screen_visible_circle(sx, sy, current_r, margin=view_margin):
                    continue
                draw_iso_hex_ring(
                    screen, p.x, p.y, current_r,
                    AEGIS_PULSE_COLOR, int(AEGIS_PULSE_RING_ALPHA * fade),
                    camx, camy,
                    sides=6,
                    fill_alpha=int(AEGIS_PULSE_FILL_ALPHA * fade),
                    width=2
                )
        visible_acids = []
        max_visible_acids = int(getattr(game, "WEB_MAX_VISIBLE_ACIDS", 0) or 0) if IS_WEB else 0
        for a in getattr(game_state, "acids", []):
            sx, sy = iso_world_to_screen(a.x / CELL_SIZE, (a.y - INFO_BAR_HEIGHT) / CELL_SIZE, 0, camx, camy)
            if not _screen_visible_circle(sx, sy, float(getattr(a, "r", 0.0)), margin=view_margin):
                continue
            dx = float(getattr(a, "x", 0.0)) - float(player.rect.centerx)
            dy = float(getattr(a, "y", 0.0)) - float(player.rect.centery)
            visible_acids.append((dx * dx + dy * dy, a))
        _cap_visible_entries(visible_acids, max_visible_acids, key=lambda item: item[0])
        for _, a in visible_acids:
            draw_iso_ground_ellipse(
                screen, a.x, a.y, a.r,
                color=(60, 200, 90), alpha=110,
                camx=camx, camy=camy,
                fill=True
            )
        _render_counter(profiler, "r_ground_ms", segment_started)
        player_rect = getattr(player, "rect", None)
        enemy_rects = [getattr(z, "rect", None) for z in enemies if getattr(z, "rect", None)]
        segment_started = time.perf_counter()
        visible_ghosts = []
        for g in getattr(game_state, "ghosts", []):
            gsx, gsy = iso_world_to_screen(
                float(getattr(g, "x", 0.0)) / CELL_SIZE,
                (float(getattr(g, "y", 0.0)) - INFO_BAR_HEIGHT) / CELL_SIZE,
                0,
                camx,
                camy,
            )
            if not _screen_visible_point(gsx, gsy, margin=view_margin):
                continue
            gw = getattr(g, "w", 0)
            gh = getattr(g, "h", 0)
            if gw and gh:
                ghost_rect = pygame.Rect(0, 0, int(gw), int(gh))
                ghost_rect.midbottom = (int(getattr(g, "x", 0)), int(getattr(g, "y", 0)))
                if player_rect and ghost_rect.colliderect(player_rect):
                    continue
                if enemy_rects and any(ghost_rect.colliderect(er) for er in enemy_rects if er):
                    continue
            dx = float(getattr(g, "x", 0.0)) - float(player.rect.centerx)
            dy = float(getattr(g, "y", 0.0)) - float(player.rect.centery)
            visible_ghosts.append((dx * dx + dy * dy, g))
        _cap_visible_entries(
            visible_ghosts,
            int(getattr(game, "WEB_MAX_GHOSTS", 0) or 0) if IS_WEB else 0,
            key=lambda item: item[0],
        )
        for _, g in visible_ghosts:
            g.draw_iso(screen, camx, camy)
        _render_counter(profiler, "r_ghost_ms", segment_started)
        segment_started = time.perf_counter()
        wind_web = bool(IS_WEB and getattr(game_state, "biome_active", "") == "Domain of Wind")
        if (not wind_web) and _web_feature_enabled("WEB_ENABLE_ENEMY_PAINT") and hasattr(game_state, "draw_paint_iso"):
            game_state.draw_paint_iso(screen, camx, camy)
        _render_counter(profiler, "r_paint_ms", segment_started)
        wall_h_current = ISO_WALL_Z if WALL_STYLE == "prism" else (12 if WALL_STYLE == "hybrid" else 0)
        drawables = []
        wall_drawables = []
        if IS_WEB:
            for sort_y, gx, gy in _get_web_wall_order(game_state):
                if gx < gx_min - 1 or gx > gx_max + 1 or gy < gy_min - 1 or gy > gy_max + 1:
                    continue
                ob = game_state.obstacles.get((gx, gy))
                if ob is None:
                    continue
                wall_drawables.append(("wall", sort_y, {"gx": gx, "gy": gy, "color": _wall_visual_color(ob)}))
        else:
            for (gx, gy), ob in game_state.obstacles.items():
                if gx < gx_min - 1 or gx > gx_max + 1 or gy < gy_min - 1 or gy > gy_max + 1:
                    continue
                if getattr(ob, "type", "") == "Lantern":
                    continue
                if getattr(ob, "type", "") == "StationaryTurret":
                    continue
                top_pts = iso_tile_points(gx, gy, camx, camy)
                sort_y = top_pts[2][1] + wall_h_current
                drawables.append(("wall", sort_y, {"gx": gx, "gy": gy, "color": _wall_visual_color(ob)}))
        spoil_iter = (
            game_state.query_spoils_near_rect(view_world_rect, pad_px=CELL_SIZE)
            if hasattr(game_state, "query_spoils_near_rect")
            else getattr(game_state, "spoils", ())
        )
        for s in spoil_iter:
            wx, wy = s.base_x / CELL_SIZE, (s.base_y - s.h - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            if not _screen_visible_point(sx, sy, margin=view_margin):
                continue
            drawables.append(("coin", sy, {"cx": sx, "cy": sy, "r": s.r}))
        for t in getattr(game_state, "turrets", []):
            wx, wy = t.x / CELL_SIZE, (t.y - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            if not _screen_visible_point(sx, sy, margin=view_margin):
                continue
            drawables.append(("turret", sy, {"cx": sx, "cy": sy, "obj": t}))
        heal_iter = (
            game_state.query_heals_near_rect(view_world_rect, pad_px=CELL_SIZE)
            if hasattr(game_state, "query_heals_near_rect")
            else getattr(game_state, "heals", ())
        )
        for h in heal_iter:
            wx, wy = h.base_x / CELL_SIZE, (h.base_y - h.h - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            if not _screen_visible_point(sx, sy, margin=view_margin):
                continue
            drawables.append(("heal", sy, {"cx": sx, "cy": sy, "r": h.r}))
        for it in getattr(game_state, "items", []):
            wx = it.center[0] / CELL_SIZE
            wy = (it.center[1] - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            if not _screen_visible_point(sx, sy, margin=view_margin):
                continue
            drawables.append(("item", sy, {"cx": sx, "cy": sy, "r": it.radius, "main": it.is_main}))
        enemy_iter = (
            getattr(game_state, "spatial").query_rect(view_world_rect, pad_px=CELL_SIZE * 2)
            if getattr(game_state, "spatial", None) is not None
            else enemies
        )
        for z in enemy_iter:
            wx = z.rect.centerx / CELL_SIZE
            wy = (z.rect.bottom - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            if not _screen_visible_point(sx, sy, margin=view_margin):
                continue
            drawables.append(("enemy", sy, {"cx": sx, "cy": sy, "z": z}))
        wx = player.rect.centerx / CELL_SIZE
        wy = (player.rect.bottom - INFO_BAR_HEIGHT) / CELL_SIZE
        psx, psy = iso_world_to_screen(wx, wy, 0, camx, camy)
        drawables.append(("player", psy, {"cx": psx, "cy": psy, "p": player}))
        if bullets:
            for b in bullets:
                wx, wy = b.x / CELL_SIZE, (b.y - INFO_BAR_HEIGHT) / CELL_SIZE
                sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
                if not _screen_visible_point(sx, sy, margin=view_margin):
                    continue
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
        if enemy_shots:
            for es in enemy_shots:
                wx, wy = es.x / CELL_SIZE, (es.y - INFO_BAR_HEIGHT) / CELL_SIZE
                sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
                if not _screen_visible_point(sx, sy, margin=view_margin):
                    continue
                if isinstance(es, MistShot):
                    drawables.append(("mistshot", sy, {"cx": sx, "cy": sy, "obj": es}))
                else:
                    drawables.append(("eshot", sy, {
                        "cx": sx, "cy": sy,
                        "r": int(getattr(es, "r", BULLET_RADIUS))
                    }))
        drawables.sort(key=lambda x: x[1])
        web_wall_static_top: tuple[int, int] | None = None
        web_wall_static_bottom: tuple[int, int] | None = None
        if wall_drawables:
            if IS_WEB:
                player_gx = int(player.rect.centerx // CELL_SIZE)
                player_gy = int((player.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE)
                near_wall_cells = max(0, int(getattr(game, "WEB_WALL_NEAR_RADIUS_CELLS", 0) or 0))
                core_sorts = [
                    int(sy)
                    for kind, sy, _ in drawables
                    if kind in ("enemy", "player", "turret", "item")
                ]
                if not core_sorts:
                    core_sorts = [int(sy) for _, sy, _ in drawables]
                if core_sorts:
                    wall_band_margin = max(144, int(CELL_SIZE * 3), int(wall_h_current + ISO_CELL_H * 3))
                    band_top = max(int(INFO_BAR_HEIGHT), int(min(core_sorts)) - wall_band_margin)
                    band_bottom = min(int(view_h), int(max(core_sorts)) + wall_band_margin)
                else:
                    band_top = int(INFO_BAR_HEIGHT)
                    band_bottom = int(view_h)
                wall_drawables = [
                    item for item in wall_drawables
                    if (
                        band_top <= int(item[1]) <= band_bottom
                        or (
                            near_wall_cells > 0
                            and max(
                                abs(int(item[2]["gx"]) - player_gx),
                                abs(int(item[2]["gy"]) - player_gy),
                            ) <= near_wall_cells
                        )
                    )
                ]
                if band_top > int(INFO_BAR_HEIGHT):
                    web_wall_static_top = (int(INFO_BAR_HEIGHT), band_top)
                if band_bottom < int(view_h):
                    web_wall_static_bottom = (band_bottom, int(view_h))
            merged = []
            wall_idx = 0
            dyn_idx = 0
            while wall_idx < len(wall_drawables) or dyn_idx < len(drawables):
                wall_sort = wall_drawables[wall_idx][1] if wall_idx < len(wall_drawables) else None
                dyn_sort = drawables[dyn_idx][1] if dyn_idx < len(drawables) else None
                if dyn_sort is None or (wall_sort is not None and wall_sort <= dyn_sort):
                    merged.append(wall_drawables[wall_idx])
                    wall_idx += 1
                else:
                    merged.append(drawables[dyn_idx])
                    dyn_idx += 1
            drawables = merged
        hell = (getattr(game_state, "biome_active", "") == "Scorched Hell")
        COL_PLAYER_BULLET = (199, 68, 12) if hell else (120, 204, 121)
        COL_ENEMY_SHOT = (255, 80, 80) if hell else (255, 120, 50)
        segment_started = time.perf_counter()
        ticks_ms = pygame.time.get_ticks()
        shield_pulse_t = ticks_ms * 0.006
        comet_shake_t = ticks_ms * 0.02
        dot_orbit_t = ticks_ms * 0.003
        spike_icon_t = ticks_ms * 0.01
        hit_blink_on = ((ticks_ms // 80) % 2 == 0)
        runtime = _runtime()
        mark_pulse_time = float(runtime.get("mark_pulse_time", 0.0) or 0.0)
        paint_lookup_cache: dict[tuple[int, int, int], float] = {}
        actor_subsamples = {"wall": 0.0, "pickup": 0.0, "turret": 0.0, "projectile": 0.0, "enemy": 0.0, "player": 0.0}

        if IS_WEB and web_wall_static_top is not None:
            wall_started = time.perf_counter()
            _blit_web_wall_layer_slice(
                screen,
                game_state,
                camx,
                camy,
                wall_h=wall_h_current,
                clip_top_px=web_wall_static_top[0],
                clip_bottom_px=web_wall_static_top[1],
            )
            actor_subsamples["wall"] += (time.perf_counter() - wall_started) * 1000.0

        def _cached_paint_intensity_at_world(x_px: float, y_px: float, owner: int = 2) -> float:
            gx = int(float(x_px) // CELL_SIZE)
            gy = int((float(y_px) - INFO_BAR_HEIGHT) // CELL_SIZE)
            key = (gx, gy, int(owner))
            cached = paint_lookup_cache.get(key)
            if cached is not None:
                return cached
            value = 0.0
            if 0 <= gx < GRID_SIZE and 0 <= gy < GRID_SIZE:
                try:
                    tile = game_state.paint_grid[gy][gx]
                    if getattr(tile, "paint_owner", 0) == int(owner):
                        value = float(getattr(tile, "paint_intensity", 0.0))
                except Exception:
                    value = 0.0
            paint_lookup_cache[key] = value
            return value

        for kind, _, data in drawables:
            item_started = time.perf_counter()
            if kind == "wall":
                gx, gy, col = data["gx"], data["gy"], data["color"]
                _blit_cached_iso_wall(screen, gx, gy, col, camx, camy)
                actor_subsamples["wall"] += (time.perf_counter() - item_started) * 1000.0
            elif kind == "coin":
                cx, cy, r = data["cx"], data["cy"], data["r"]
                _blit_cached_ellipse(screen, (cx, cy + 6), r * 4, r * 2, (0, 0, 0, ISO_SHADOW_ALPHA))
                pygame.draw.circle(screen, (255, 215, 80), (cx, cy), r)
                pygame.draw.circle(screen, (255, 245, 200), (cx, cy), r, 1)
                actor_subsamples["pickup"] += (time.perf_counter() - item_started) * 1000.0
            elif kind == "heal":
                cx, cy, r = data["cx"], data["cy"], data["r"]
                _blit_cached_ellipse(screen, (cx, cy + 6), r * 4, r * 2, (0, 0, 0, ISO_SHADOW_ALPHA))
                pygame.draw.circle(screen, (225, 225, 225), (cx, cy), r)
                pygame.draw.rect(screen, (220, 60, 60), pygame.Rect(cx - 2, cy - r + 3, 4, r * 2 - 6))
                pygame.draw.rect(screen, (200, 40, 40), pygame.Rect(cx - r + 3, cy - 2, r * 2 - 6, 4))
                actor_subsamples["pickup"] += (time.perf_counter() - item_started) * 1000.0
            elif kind == "item":
                cx, cy, r = data["cx"], data["cy"], data["r"]
                _blit_cached_ellipse(screen, (cx, cy + 6), r * 4, r * 2, (0, 0, 0, ISO_SHADOW_ALPHA))
                _blit_cached_ellipse(screen, (cx, cy + 6), r * 4, r * 2, (255, 240, 120, 90))
                pygame.draw.circle(screen, (255, 224, 0), (cx, cy), r)
                pygame.draw.circle(screen, (255, 255, 180), (cx, cy), r, 2)
                actor_subsamples["pickup"] += (time.perf_counter() - item_started) * 1000.0
            elif kind == "turret":
                cx, cy = int(data["cx"]), int(data["cy"])
                obj = data.get("obj")
                if isinstance(obj, StationaryTurret):
                    sprite, foot_w, foot_h = get_stationary_turret_assets()
                    if sprite:
                        shadow_w = max(int(foot_w * 1.4), int(CELL_SIZE * 0.9))
                        shadow_h = max(int(foot_h * 0.8), int(CELL_SIZE * 0.4))
                        _blit_cached_ellipse(screen, (cx, cy + 6), shadow_w, shadow_h, (0, 0, 0, ISO_SHADOW_ALPHA))
                        rect = sprite.get_rect(midbottom=(cx, cy))
                        screen.blit(sprite, rect)
                    else:
                        base_r = 10
                        pygame.draw.circle(screen, (80, 180, 255), (cx, cy), base_r)
                        pygame.draw.circle(screen, (250, 250, 255), (cx, cy), base_r - 4, 2)
                elif isinstance(obj, AutoTurret):
                    owner = getattr(obj, "owner", None)
                    dir_key = None
                    facing = getattr(owner, "facing", None)
                    if facing:
                        if facing in ("E", "SE", "NE"):
                            dir_key = "right"
                        elif facing in ("W", "SW", "NW"):
                            dir_key = "left"
                        elif facing in ("N",):
                            dir_key = "up"
                        elif facing in ("S",):
                            dir_key = "down"
                    if dir_key is None:
                        if owner and hasattr(owner, "rect"):
                            ox, oy = owner.rect.center
                            dx, dy = cx - ox, cy - oy
                        else:
                            dx = dy = 0
                        if abs(dx) >= abs(dy):
                            dir_key = "right" if dx >= 0 else "left"
                        else:
                            dir_key = "down" if dy >= 0 else "up"
                    sprite = _auto_turret_sprite(dir_key)
                    if sprite:
                        shadow_w = max(int(sprite.get_width() * 0.6), int(CELL_SIZE * 0.6))
                        shadow_h = max(int(sprite.get_height() * 0.32), int(CELL_SIZE * 0.28))
                        _blit_cached_ellipse(screen, (cx, cy + 6), shadow_w, shadow_h, (0, 0, 0, ISO_SHADOW_ALPHA))
                        rect = sprite.get_rect(midbottom=(cx, cy))
                        screen.blit(sprite, rect)
                    else:
                        base_r = 9
                        pygame.draw.circle(screen, (80, 200, 255), (cx, cy), base_r)
                        pygame.draw.circle(screen, (240, 240, 255), (cx, cy), base_r - 3, 2)
                else:
                    base_r = 10
                    pygame.draw.circle(screen, (80, 180, 255), (cx, cy), base_r)
                    pygame.draw.circle(screen, (250, 250, 255), (cx, cy), base_r - 4, 2)
                actor_subsamples["turret"] += (time.perf_counter() - item_started) * 1000.0
            elif kind == "bullet":
                cx, cy = data["cx"], data["cy"]
                rad = int(data.get("r", BULLET_RADIUS))
                src = data.get("src", "player")
                color = (0, 255, 255) if src == "turret" else COL_PLAYER_BULLET
                pygame.draw.circle(screen, color, (cx, cy), rad)
                actor_subsamples["projectile"] += (time.perf_counter() - item_started) * 1000.0
            elif kind == "eshot":
                rad = int(data.get("r", BULLET_RADIUS))
                pygame.draw.circle(screen, COL_ENEMY_SHOT, (data["cx"], data["cy"]), rad)
                actor_subsamples["projectile"] += (time.perf_counter() - item_started) * 1000.0
            elif kind == "mistshot":
                es = data.get("obj")
                rad = int(getattr(es, "r", BULLET_RADIUS))
                col = getattr(es, "color", HAZARD_STYLES["mist"]["ring"])
                pygame.draw.circle(screen, col, (data["cx"], data["cy"]), rad)
                actor_subsamples["projectile"] += (time.perf_counter() - item_started) * 1000.0
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
                glow_t = float(getattr(z, "_curing_paint_glow_t", 0.0))
                if glow_t > 0.0:
                    glow_ratio = max(0.0, min(1.0, glow_t / 0.14))
                    glow_int = max(0.0, float(getattr(z, "_curing_paint_glow_intensity", 0.0)))
                    alpha = int(110 * glow_ratio * (0.5 + 0.5 * glow_int))
                    if alpha > 0:
                        glow_r = max(10, int(getattr(z, "radius", CELL_SIZE * 0.3) * 1.1))
                        draw_iso_ground_ellipse(
                            screen,
                            z.rect.centerx,
                            z.rect.centery,
                            glow_r,
                            CURING_PAINT_SPARK_COLORS[0],
                            alpha,
                            camx,
                            camy,
                            fill=True,
                        )
                shake = float(getattr(z, "_comet_shake", 0.0))
                if shake > 0.0:
                    amp = min(6.0, 10.0 * shake)
                    t = comet_shake_t + z.rect.x * 0.03 + z.rect.y * 0.01
                    cx += math.sin(t) * amp
                    cy += math.cos(t * 1.4) * amp * 0.6
                cx = int(round(cx))
                cy = int(round(cy))
                player_size = int(CELL_SIZE * 0.6)
                if getattr(z, "is_boss", False) or getattr(z, "type", "") == "ravager":
                    draw_size = max(player_size * 2, int(z.rect.w * 2))
                else:
                    draw_size = max(player_size, int(z.rect.w))
                body = pygame.Rect(0, 0, draw_size, draw_size)
                body.midbottom = (cx, cy)
                enemy_sprite = _enemy_sprite(getattr(z, "type", ""), draw_size)
                sh_w = max(8, int(draw_size * 0.9))
                sh_h = max(4, int(draw_size * 0.45))
                _blit_cached_ellipse(screen, (cx, cy + 6), sh_w, sh_h, (0, 0, 0, ISO_SHADOW_ALPHA))
                sprite_rect = body
                if getattr(z, "_gold_glow_t", 0.0) > 0.0:
                    alpha = int(120 * (z._gold_glow_t / Z_GLOW_TIME))
                    _blit_cached_ellipse(
                        screen,
                        (cx, cy),
                        int(draw_size * 1.6),
                        int(draw_size * 1.0),
                        (255, 220, 90, max(30, alpha)),
                    )
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
                if enemy_sprite:
                    sprite_rect = enemy_sprite.get_rect(midbottom=body.midbottom)
                    screen.blit(enemy_sprite, sprite_rect)
                else:
                    pygame.draw.rect(screen, col, body)
                    if not getattr(z, "is_boss", False):
                        outline_rect = body.inflate(6, 6)
                        pygame.draw.rect(screen, (230, 210, 230), outline_rect, 2, border_radius=4)
                if flash > 0.0 and enemy_sprite:
                    flash_ratio = min(1.0, flash * 2.8)
                    flash_alpha = int(200 * flash_ratio)
                    if flash_alpha > 0:
                        _blit_cached_sprite_tint(screen, enemy_sprite, sprite_rect.topleft, (255, 255, 255, flash_alpha))
                if getattr(z, "shield_hp", 0) > 0:
                    a = 120 + int(80 * (0.5 + 0.5 * math.sin(shield_pulse_t)))
                    if enemy_sprite:
                        _blit_cached_sprite_outline(
                            screen,
                            enemy_sprite,
                            sprite_rect.topleft,
                            (90, 180, 255, a),
                            width=3,
                        )
                dot_ratio, dot_count = dot_rounds_visual_state(z)
                if dot_ratio > 0.0:
                    glow_w = max(12, int(draw_size * 1.1))
                    glow_h = max(8, int(draw_size * 0.7))
                    tick_interval = float(DOT_ROUNDS_TICK_INTERVAL)
                    tick_t = float(getattr(z, "_dot_rounds_tick_t", tick_interval))
                    if tick_interval > 0.0:
                        phase = 1.0 - max(0.0, min(1.0, tick_t / tick_interval))
                        pulse = 0.7 + 0.3 * math.sin(phase * math.tau)
                    else:
                        pulse = 1.0
                    glow_alpha = int(120 * dot_ratio * pulse)
                    fill_alpha = int(55 * dot_ratio * pulse)
                    glow_center = (cx, body.centery - 4)
                    _blit_cached_ellipse(
                        screen,
                        glow_center,
                        glow_w,
                        glow_h,
                        (DOT_ROUNDS_GLOW_COLOR[0], DOT_ROUNDS_GLOW_COLOR[1], DOT_ROUNDS_GLOW_COLOR[2], fill_alpha),
                    )
                    _blit_cached_ellipse(
                        screen,
                        glow_center,
                        glow_w,
                        glow_h,
                        (DOT_ROUNDS_GLOW_COLOR[0], DOT_ROUNDS_GLOW_COLOR[1], DOT_ROUNDS_GLOW_COLOR[2], glow_alpha),
                        line_width=2,
                    )
                    orb_count = 0
                    if dot_count > 0:
                        orb_count = 2 if dot_count < 2 else 3
                    if orb_count > 0:
                        orb_alpha = int(190 * dot_ratio * pulse)
                        orbit_r = max(6, int(draw_size * 0.45))
                        for i in range(orb_count):
                            ang = dot_orbit_t + i * math.tau / max(1, orb_count)
                            ox = int(math.cos(ang) * orbit_r)
                            oy = int(math.sin(ang) * orbit_r * 0.6)
                            _blit_cached_ellipse(
                                screen,
                                (glow_center[0] + ox, glow_center[1] + oy),
                                4,
                                4,
                                (DOT_ROUNDS_GLOW_COLOR[0], DOT_ROUNDS_GLOW_COLOR[1], DOT_ROUNDS_GLOW_COLOR[2], orb_alpha),
                            )
                            _blit_cached_ellipse(
                                screen,
                                (glow_center[0] + ox, glow_center[1] + oy),
                                2,
                                2,
                                (255, 255, 255, max(40, orb_alpha - 90)),
                            )
                spike_slow_t = float(getattr(z, "_ground_spike_slow_t", 0.0))
                if spike_slow_t > 0.0:
                    ratio = max(0.0, min(1.0, spike_slow_t / max(0.001, GROUND_SPIKES_SLOW_DURATION)))
                    alpha = int(200 * ratio)
                    bob = int(2 * math.sin(spike_icon_t + z.rect.x * 0.03))
                    icon = _cached_ground_spike_icon(alpha)
                    screen.blit(icon, icon.get_rect(center=(cx, body.top - 12 + bob)))
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
                coins = int(getattr(z, "spoils", 0))
                if coins > 0:
                    txt = _cached_text_surface(f"{coins}", (255, 225, 120), size=18)
                    screen.blit(txt, txt.get_rect(midbottom=(cx, body.top - 4)))
                if z.is_boss and not enemy_sprite:
                    pygame.draw.rect(screen, (255, 215, 0), body.inflate(4, 4), 3)
                if not enemy_sprite:
                    pygame.draw.rect(screen, col, body)
                paint_intensity = 0.0
                paint_bonus = float(getattr(game, "ENEMY_PAINT_DAMAGE_BONUS", 0.0) or 0.0)
                if paint_bonus > 0.0:
                    paint_intensity = max(
                        0.0,
                        min(1.0, (float(getattr(z, "_paint_contact_mult", 1.0)) - 1.0) / paint_bonus),
                    )
                elif hasattr(game_state, "paint_intensity_at_world"):
                    paint_intensity = _cached_paint_intensity_at_world(z.rect.centerx, z.rect.centery, owner=2)
                if paint_intensity > 0.0:
                    tint_alpha = int(70 * paint_intensity)
                    if tint_alpha > 0:
                        tint_h = max(4, int(draw_size * 0.38))
                        tint = _cached_filled_surface((draw_size, tint_h), (20, 80, 50, tint_alpha))
                        screen.blit(tint, (body.left, body.bottom - tint_h))
                flash_t = float(getattr(z, "_hit_flash", 0.0))
                if flash_t > 0.0 and HIT_FLASH_DURATION > 0:
                    flash_ratio = min(1.0, flash_t / HIT_FLASH_DURATION)
                    if enemy_sprite:
                        _blit_cached_sprite_tint(
                            screen,
                            enemy_sprite,
                            sprite_rect.topleft,
                            (255, 255, 255, int(200 * flash_ratio)),
                        )
                    else:
                        overlay = _cached_filled_surface(body.size, (255, 255, 255, int(200 * flash_ratio)))
                        screen.blit(overlay, body.topleft)
                mark_t = float(getattr(z, "_vuln_mark_t", 0.0))
                if mark_t > 0.0:
                    flash = float(getattr(z, "_vuln_hit_flash", 0.0))
                    lvl_vis = int(getattr(z, "_vuln_mark_level", 1))
                    lvl_vis = max(1, min(lvl_vis, len(VULN_MARK_DURATIONS)))
                    dur_vis = VULN_MARK_DURATIONS[lvl_vis - 1]
                    rem_ratio = max(0.0, min(1.0, mark_t / max(0.001, dur_vis)))
                    phase = (mark_pulse_time % MARK_PULSE_PERIOD) / MARK_PULSE_PERIOD
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
                    red_rgb = (
                        int(MARK_PULSE_DARK[0] + (MARK_PULSE_BRIGHT[0] - MARK_PULSE_DARK[0]) * pulse),
                        int(MARK_PULSE_DARK[1] + (MARK_PULSE_BRIGHT[1] - MARK_PULSE_DARK[1]) * pulse),
                        int(MARK_PULSE_DARK[2] + (MARK_PULSE_BRIGHT[2] - MARK_PULSE_DARK[2]) * pulse),
                    )
                    mark = _cached_vuln_mark_surface(size, red_rgb, alpha)
                    if mark is not None:
                        screen.blit(mark, mark_rect)
                if getattr(z, "shield_hp", 0) > 0 and not enemy_sprite:
                    a = 120 + int(80 * (0.5 + 0.5 * math.sin(shield_pulse_t)))
                    shield_sprite = _rect_sprite(body.width, body.height)
                    _blit_cached_sprite_outline(
                        screen,
                        shield_sprite,
                        body.topleft,
                        (90, 180, 255, a),
                        width=3,
                    )
                actor_subsamples["enemy"] += (time.perf_counter() - item_started) * 1000.0
            elif kind == "player":
                p, cx, cy = data["p"], data["cx"], data["cy"]
                player_size = int(CELL_SIZE * 0.6)
                paint_intensity = 0.0
                slow_frac = float(getattr(game, "ENEMY_PAINT_PLAYER_SLOW", 0.0) or 0.0)
                if slow_frac > 0.0:
                    paint_intensity = max(
                        0.0,
                        min(1.0, float(getattr(p, "_enemy_paint_slow", 0.0)) / slow_frac),
                    )
                elif hasattr(game_state, "paint_intensity_at_world"):
                    paint_intensity = _cached_paint_intensity_at_world(p.rect.centerx, p.rect.centery, owner=2)
                if paint_intensity > 0.0:
                    aura_r = max(10, int(player_size * 0.6)) * (0.85 + 0.3 * paint_intensity)
                    aura_alpha = int(110 * paint_intensity)
                    if aura_alpha > 0:
                        draw_iso_ground_ellipse(
                            screen,
                            p.rect.centerx,
                            p.rect.centery,
                            aura_r,
                            (12, 40, 20),
                            aura_alpha,
                            camx,
                            camy,
                            fill=True,
                        )
                sh_w = max(8, int(player_size * 0.9))
                sh_h = max(4, int(player_size * 0.45))
                _blit_cached_ellipse(screen, (cx, cy + 6), sh_w, sh_h, (0, 0, 0, ISO_SHADOW_ALPHA))
                rect = pygame.Rect(0, 0, player_size, player_size)
                rect.midbottom = (cx, cy)
                sprite_w = int(player_size * 2.0 * PLAYER_SPRITE_SCALE)
                sprite_h = int(player_size * 2.4 * PLAYER_SPRITE_SCALE)
                player_sprite = _load_shop_sprite(
                    "characters/player/sheets/player.png",
                    (sprite_w, sprite_h),
                    allow_upscale=True,
                )
                sprite_rect = rect
                hit_blink = (p.hit_cd > 0 and hit_blink_on)
                if player_sprite:
                    sprite_rect = player_sprite.get_rect(midbottom=rect.midbottom)
                    screen.blit(player_sprite, sprite_rect)
                    if hit_blink:
                        _blit_cached_sprite_tint(screen, player_sprite, sprite_rect.topleft, (240, 80, 80, 120))
                else:
                    col = (240, 80, 80) if hit_blink else (0, 255, 0)
                    pygame.draw.rect(screen, col, rect)
                flash_t = float(getattr(p, "_hit_flash", 0.0))
                if flash_t > 0.0 and HIT_FLASH_DURATION > 0:
                    flash_ratio = min(1.0, flash_t / HIT_FLASH_DURATION)
                    if player_sprite:
                        _blit_cached_sprite_tint(
                            screen,
                            player_sprite,
                            sprite_rect.topleft,
                            (255, 255, 255, int(200 * flash_ratio)),
                        )
                    else:
                        overlay = _cached_filled_surface(sprite_rect.size, (255, 255, 255, int(200 * flash_ratio)))
                        screen.blit(overlay, sprite_rect.topleft)
                carapace_hp = int(getattr(p, "carapace_hp", 0))
                total_shield = int(getattr(p, "shield_hp", 0)) + carapace_hp
                if total_shield > 0 and player_sprite:
                    a = 120 + int(80 * (0.5 + 0.5 * math.sin(shield_pulse_t)))
                    _blit_cached_sprite_outline(
                        screen,
                        player_sprite,
                        sprite_rect.topleft,
                        (90, 180, 255, a),
                        width=3,
                    )
                if carapace_hp > 0:
                    glow_rect = rect.inflate(18, 18)
                    alpha = min(200, 80 + carapace_hp * 3 // 2)
                    fill_alpha = max(30, alpha - 100)
                    _blit_cached_ellipse(screen, glow_rect.center, glow_rect.width, glow_rect.height, (40, 140, 255, fill_alpha))
                    _blit_cached_ellipse(screen, glow_rect.center, glow_rect.width, glow_rect.height, (70, 200, 255, max(60, alpha - 40)), line_width=4)
                plating_hp = int(getattr(p, "bone_plating_hp", 0))
                if plating_hp > 0:
                    armor_rect = rect.inflate(16, 10)
                    glow_ratio = max(0.43, min(1.0, float(getattr(p, "_bone_plating_glow", 0.0))))
                    edge_alpha = min(220, 80 + plating_hp // 2)
                    inner_alpha = int((BONE_PLATING_GLOW[3] if len(BONE_PLATING_GLOW) > 3 else 140) * glow_ratio)
                    armor_fill = _cached_rounded_rect_surface(
                        armor_rect.size,
                        (BONE_PLATING_GLOW[0], BONE_PLATING_GLOW[1], BONE_PLATING_GLOW[2], inner_alpha),
                        border_radius=10,
                    )
                    armor_outline = _cached_rounded_rect_surface(
                        armor_rect.size,
                        (BONE_PLATING_COLOR[0], BONE_PLATING_COLOR[1], BONE_PLATING_COLOR[2], edge_alpha),
                        border_radius=10,
                        line_width=2,
                    )
                    screen.blit(armor_fill, armor_rect)
                    screen.blit(armor_outline, armor_rect)
                    if int(getattr(p, "bone_plating_level", 0)) >= BONE_PLATING_MAX_LEVEL:
                        cx, cy = rect.centerx, rect.top - 6
                        sparkle = [
                            (cx, cy - 3),
                            (cx + 3, cy),
                            (cx, cy + 3),
                            (cx - 3, cy)
                        ]
                        pygame.draw.polygon(screen, BONE_PLATING_COLOR, sparkle, width=1)
                actor_subsamples["player"] += (time.perf_counter() - item_started) * 1000.0
        if IS_WEB and web_wall_static_bottom is not None:
            wall_started = time.perf_counter()
            _blit_web_wall_layer_slice(
                screen,
                game_state,
                camx,
                camy,
                wall_h=wall_h_current,
                clip_top_px=web_wall_static_bottom[0],
                clip_bottom_px=web_wall_static_bottom[1],
            )
            actor_subsamples["wall"] += (time.perf_counter() - wall_started) * 1000.0
        _render_counter(profiler, "r_actor_ms", segment_started)
        _emit_actor_subcounters(profiler, actor_subsamples)
        segment_started = time.perf_counter()
        if _web_feature_enabled("WEB_ENABLE_DAMAGE_TEXTS"):
            visible_dmg_texts = []
            for d in getattr(game_state, "dmg_texts", []):
                wx = d.x / CELL_SIZE
                wy = (d.y - INFO_BAR_HEIGHT) / CELL_SIZE
                sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
                sy += d.screen_offset_y()
                if not _screen_visible_point(sx, sy, margin=view_margin):
                    continue
                dx = float(getattr(d, "x", 0.0)) - float(player.rect.centerx)
                dy = float(getattr(d, "y", 0.0)) - float(player.rect.centery)
                visible_dmg_texts.append((dx * dx + dy * dy, d, sx, sy))
            _cap_visible_entries(
                visible_dmg_texts,
                int(getattr(game, "WEB_MAX_DAMAGE_TEXTS", 0) or 0) if IS_WEB else 0,
                key=lambda item: item[0],
            )
            for _, d, sx, sy in visible_dmg_texts:
                d.draw_iso(screen, sx, sy)
        _render_counter(profiler, "r_text_ms", segment_started)
        _draw_skill_overlay(screen, player, camx, camy)
        segment_started = time.perf_counter()
        for s in list(getattr(game_state, "ground_spikes", [])):
            sx, sy = iso_world_to_screen(s.x / CELL_SIZE, (s.y - INFO_BAR_HEIGHT) / CELL_SIZE, 0, camx, camy)
            if not _screen_visible_circle(sx, sy, float(getattr(s, "r", 0.0)), margin=view_margin):
                continue
            draw_ground_spike_iso(screen, s, camx, camy)
        if hasattr(game_state, "draw_comet_blasts"):
            game_state.draw_comet_blasts(screen, camx, camy)
        if hasattr(game_state, "draw_comet_corpses"):
            game_state.draw_comet_corpses(screen, camx, camy)
        _render_counter(profiler, "r_hazard_ms", segment_started)
        segment_started = time.perf_counter()
        if getattr(game_state, "fog_enabled", False) and _web_feature_enabled("WEB_ENABLE_FOG"):
            game_state.draw_fog_overlay(screen, camx, camy, player, obstacles)
        _render_counter(profiler, "r_fog_ms", segment_started)
        segment_started = time.perf_counter()
        if USE_ISO:
            game_state.draw_lanterns_iso(screen, camx, camy)
        else:
            game_state.draw_lanterns_topdown(screen, camx, camy)
        _render_counter(profiler, "r_lantern_ms", segment_started)
        segment_started = time.perf_counter()
        if hasattr(game_state, "fx"):
            visible_particles = []
            for p in game_state.fx.particles:
                if p.size < 1:
                    continue
                gx = p.x / CELL_SIZE
                gy = (p.y - INFO_BAR_HEIGHT) / CELL_SIZE
                sx, sy = iso_world_to_screen(gx, gy, 0, camx, camy)
                if not _screen_visible_point(sx, sy, margin=view_margin):
                    continue
                dx = float(getattr(p, "x", 0.0)) - float(player.rect.centerx)
                dy = float(getattr(p, "y", 0.0)) - float(player.rect.centery)
                visible_particles.append((dx * dx + dy * dy, p, sx, sy))
            _cap_visible_entries(
                visible_particles,
                int(getattr(game, "WEB_MAX_FX_PARTICLES", 0) or 0) if IS_WEB else 0,
                key=lambda item: item[0],
            )
            for _, p, sx, sy in visible_particles:
                glow = GlowCache.get_glow_surf(p.size, p.color)
                screen.blit(glow, (sx - p.size, sy - p.size), special_flags=pygame.BLEND_ADD)
        _render_counter(profiler, "r_fx_ms", segment_started)
        vignette_t = float(getattr(player, "_enemy_paint_vignette_t", 0.0))
        if vignette_t > 0.0:
            ratio = max(0.0, min(1.0, vignette_t / 0.18))
            alpha = int(80 * ratio)
            if alpha > 0:
                w, h = screen.get_size()
                edge = int(16 + 14 * ratio)
                overlay = pygame.Surface((w, h), pygame.SRCALPHA)
                overlay.fill((10, 30, 18, int(22 * ratio)))
                pygame.draw.rect(overlay, (10, 40, 20, alpha), pygame.Rect(0, 0, w, edge))
                pygame.draw.rect(overlay, (10, 40, 20, alpha), pygame.Rect(0, h - edge, w, edge))
                pygame.draw.rect(overlay, (10, 40, 20, alpha), pygame.Rect(0, 0, edge, h))
                pygame.draw.rect(overlay, (10, 40, 20, alpha), pygame.Rect(w - edge, 0, edge, h))
                screen.blit(overlay, (0, 0))
        segment_started = time.perf_counter()
        draw_ui_topbar(
            screen,
            game_state,
            player,
            time_left=_runtime().get("_time_left_runtime"),
            enemies=enemies,
        )
        bosses = _find_all_bosses(enemies)
        if len(bosses) >= 2:
            draw_boss_hp_bars_twin(screen, bosses[:2])
        elif len(bosses) == 1:
            draw_boss_hp_bar(screen, bosses[0])
        _render_counter(profiler, "r_ui_ms", segment_started)
        segment_started = time.perf_counter()
        run_pending_menu_transition(screen)
        _render_counter(profiler, "r_transition_ms", segment_started)
        _draw_web_profiler_overlay(screen)
        return _present_gameplay_render(screen, display_surface, prev_view, copy_frame=copy_frame)

    def render_game(screen: pygame.Surface, game_state, player: Player, enemies: List[Enemy],
                    bullets: Optional[List['Bullet']] = None,
                    enemy_shots: Optional[List[EnemyShot]] = None,
                    override_cam: tuple[int, int] | None = None,
                    copy_frame: bool = True) -> pygame.Surface | None:
        """
        Legacy top-down renderer.
        We now use the isometric renderer for everything, but keep this wrapper
        so old call sites (fail screen, etc.) still work without errors.
        """
        if bullets is None:
            bullets = []
        if enemy_shots is None:
            enemy_shots = []
        return render_game_iso(
            screen, game_state, player, enemies, bullets, enemy_shots,
            obstacles=game_state.obstacles,
            override_cam=override_cam,
            copy_frame=copy_frame,
        )

    game.__dict__.update({
        "draw_settings_gear": draw_settings_gear,
        "_current_music_pos_ms": _current_music_pos_ms,
        "_music_is_busy": _music_is_busy,
        "_resume_bgm_if_needed": _resume_bgm_if_needed,
        "play_focus_chain_iso": play_focus_chain_iso,
        "play_focus_cinematic_iso": play_focus_cinematic_iso,
        "render_game_iso_web_lite": render_game_iso_web_lite,
        "render_game_iso": render_game_iso,
        "render_game": render_game,
    })
    return (
        draw_settings_gear,
        _current_music_pos_ms,
        _music_is_busy,
        _resume_bgm_if_needed,
        play_focus_chain_iso,
        play_focus_cinematic_iso,
        render_game_iso_web_lite,
        render_game_iso,
        render_game,
    )
