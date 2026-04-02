"""Menu visual and transition helpers extracted from ZGame.py."""

from __future__ import annotations

import math
import random

import pygame

from zgame import runtime_state as rs


INSTRUCTION_LINES = [
    "WASD to move. Survive until the timer hits 00:00 to win.",
    "Enemies deal contact damage. Avoid or kite them.",
    "Auto-fire targets the closest enemy/block in range.",
    "Bandits: Radar tags them in red; intercept before they flee.",
    "Shop between levels to upgrade (turrets, bullets, economy).",
    "Pause: ESC to open menu.",
]

NEURO_SYSTEM_MESSAGES = [
    "link stable. awaiting neural sync...",
    "bioscan: green. cortex latency 12ms.",
    "encryption tunnel alive. tracing ghosts...",
    "memory shards indexed. ready for run.",
    "diagnostics clean. no corruption detected.",
    "entropy pool topped. firing neurons.",
]


def install(game):
    def _runtime():
        return rs.runtime(game)

    def _view_size() -> tuple[int, int]:
        return int(game.VIEW_W), int(game.VIEW_H)

    def _ensure_neuro_log_seed() -> int:
        runtime = _runtime()
        seed = runtime.get("_neuro_log_seed")
        if not isinstance(seed, int):
            seed = random.getrandbits(24)
            runtime["_neuro_log_seed"] = seed
        return seed

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
            ang = math.radians(-60 * i)
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        return pts

    def build_hex_grid(view_w: int, view_h: int, r: int = 50) -> list[object]:
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
                if x < -margin * 2 or x > view_w + margin * 2:
                    continue
                if y < -margin * 2 or y > view_h + margin * 2:
                    continue
                cells.append(game.HexCell(x, y, size))
        return cells

    def ensure_hex_transition():
        runtime = _runtime()
        view_size = _view_size()
        grid = runtime.get("_hex_grid_cache")
        if grid is None or runtime.get("_hex_grid_view_size") != view_size:
            grid = build_hex_grid(game.VIEW_W, game.VIEW_H, r=int(max(90, game.VIEW_W * 0.075)))
            runtime["_hex_grid_cache"] = grid
            runtime["_hex_grid_view_size"] = view_size
            runtime["_hex_transition"] = None
            runtime["_hex_bg_surface"] = None
        for cell in grid:
            if not hasattr(cell, "points"):
                try:
                    cell.points = hex_points_flat(cell.cx, cell.cy, cell.max_r)
                except Exception:
                    pass
        trans = runtime.get("_hex_transition")
        if trans is None or getattr(trans, "grid", None) is not grid:
            trans = game.HexTransition(grid)
            runtime["_hex_transition"] = trans
        return trans

    def ensure_hex_background():
        runtime = _runtime()
        view_size = _view_size()
        surf = runtime.get("_hex_bg_surface")
        if surf is not None and surf.get_size() == view_size:
            return surf
        grid = runtime.get("_hex_grid_cache")
        if grid is None or runtime.get("_hex_grid_view_size") != view_size:
            grid = build_hex_grid(game.VIEW_W, game.VIEW_H, r=int(max(90, game.VIEW_W * 0.08)))
            runtime["_hex_grid_cache"] = grid
            runtime["_hex_grid_view_size"] = view_size
            runtime["_hex_transition"] = None
        for cell in grid:
            if not hasattr(cell, "points"):
                cell.points = hex_points_flat(cell.cx, cell.cy, cell.max_r)
        surf = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
        top_col = (12, 26, 32)
        bot_col = (6, 88, 110)
        for y in range(game.VIEW_H):
            t = y / max(1, game.VIEW_H - 1)
            col = (
                int(top_col[0] * (1 - t) + bot_col[0] * t),
                int(top_col[1] * (1 - t) + bot_col[1] * t),
                int(top_col[2] * (1 - t) + bot_col[2] * t),
            )
            pygame.draw.line(surf, col, (0, y), (game.VIEW_W, y))
        outline_col = (70, 230, 255, 170)
        for cell in grid:
            pygame.draw.polygon(surf, outline_col, cell.points, width=2)
        runtime["_hex_bg_surface"] = surf
        return surf

    def queue_menu_transition(frame: pygame.Surface):
        """Cache a menu frame so the next scene can transition from it."""
        runtime = _runtime()
        runtime["_menu_transition_frame"] = frame
        runtime["_web_hex_transition_state"] = None

    def clear_menu_transition_state():
        runtime = _runtime()
        runtime["_menu_transition_frame"] = None
        runtime["_web_hex_transition_state"] = None

    def run_pending_menu_transition(screen: pygame.Surface):
        """Play a queued menu transition onto the already-rendered screen frame."""
        runtime = _runtime()
        from_surf = runtime.get("_menu_transition_frame")
        if game.IS_WEB:
            web_state = runtime.get("_web_hex_transition_state")
            if from_surf is None and not web_state:
                return
            now_ms = pygame.time.get_ticks()
            if web_state is None:
                trans = ensure_hex_transition()
                trans.start()
                trans.duration_in = min(float(getattr(trans, "duration_in", 0.25)), 0.16)
                trans.duration_hold = min(float(getattr(trans, "duration_hold", 0.10)), 0.04)
                trans.duration_out = min(float(getattr(trans, "duration_out", 0.25)), 0.18)
                web_state = {
                    "transition": trans,
                    "from_surface": from_surf,
                    "last_tick_ms": now_ms,
                }
                runtime["_web_hex_transition_state"] = web_state
            trans = web_state.get("transition")
            if trans is None:
                runtime["_menu_transition_frame"] = None
                runtime["_web_hex_transition_state"] = None
                return
            last_tick_ms = int(web_state.get("last_tick_ms", now_ms))
            dt = max(0.0, min(0.05, (now_ms - last_tick_ms) / 1000.0))
            web_state["last_tick_ms"] = now_ms
            trans.update(dt)
            trans.should_swap_screens()
            current_bg = web_state.get("from_surface")
            if current_bg is not None and not getattr(trans, "midpoint_triggered", False):
                screen.blit(current_bg, (0, 0))
            trans.draw(screen)
            if not trans.is_active():
                runtime["_menu_transition_frame"] = None
                runtime["_web_hex_transition_state"] = None
                game.flush_events()
            return
        if from_surf is None:
            return
        to_surf = screen.copy()
        play_hex_transition(screen, from_surf, to_surf, direction="down")
        runtime["_menu_transition_frame"] = None

    def play_hex_transition(screen: pygame.Surface, from_surface: pygame.Surface, to_surface: pygame.Surface, direction: str = "down"):
        """
        Blocking helper that plays the full hex animation.
        1. Close over from_surface.
        2. Swap to to_surface at the midpoint.
        3. Open over to_surface.
        """
        del direction
        if game.IS_WEB:
            runtime = _runtime()
            runtime["_menu_transition_frame"] = from_surface.copy() if from_surface is not None else None
            runtime["_web_hex_transition_state"] = None
            if to_surface is not None:
                screen.blit(to_surface, (0, 0))
            run_pending_menu_transition(screen)
            pygame.display.flip()
            return
        trans = ensure_hex_transition()
        trans.start()
        clock = pygame.time.Clock()
        current_bg = from_surface
        while trans.is_active():
            dt = clock.tick(60) / 1000.0
            pygame.event.pump()
            trans.update(dt)
            if trans.should_swap_screens():
                current_bg = to_surface
            if current_bg:
                screen.blit(current_bg, (0, 0))
            trans.draw(screen)
            pygame.display.flip()
        game.flush_events()

    def neuro_instruction_layout():
        panel_rect = pygame.Rect(int(game.VIEW_W * 0.14), int(game.VIEW_H * 0.26), int(game.VIEW_W * 0.72), int(game.VIEW_H * 0.48))
        back_rect = pygame.Rect(0, 0, 220, 60)
        back_rect.center = (game.VIEW_W // 2, panel_rect.bottom + 70)
        return panel_rect, back_rect

    def draw_neuro_instruction(surface: pygame.Surface, t: float, *, hover_back: bool, title_font, body_font, btn_font):
        panel_rect, back_rect = neuro_instruction_layout()
        draw_neuro_waves(surface, t)
        title = title_font.render("INSTRUCTION", True, (220, 240, 255))
        surface.blit(title, title.get_rect(center=(game.VIEW_W // 2, int(game.VIEW_H * 0.16))))
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (14, 32, 50, 140), panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, (80, 200, 255, 180), panel.get_rect(), width=2, border_radius=18)
        y = 26
        for line in INSTRUCTION_LINES:
            txt = body_font.render(line, True, (200, 225, 245))
            panel.blit(txt, (24, y))
            y += txt.get_height() + 12
        surface.blit(panel, panel_rect.topleft)
        return draw_neuro_button(surface, back_rect, "BACK", btn_font, hovered=hover_back, disabled=False, t=t)

    def render_instruction_surface():
        surf = ensure_neuro_background().copy()
        body_font = pygame.font.SysFont("Consolas", 20)
        title_font = pygame.font.SysFont("Consolas", 34, bold=True)
        btn_font = pygame.font.SysFont(None, 30)
        draw_neuro_instruction(
            surf,
            0.0,
            hover_back=False,
            title_font=title_font,
            body_font=body_font,
            btn_font=btn_font,
        )
        return surf

    def _seed_intro_layers():
        """Lazily build procedural starfield/column seeds so the intro stays image-free."""
        runtime = _runtime()
        view_size = _view_size()
        if runtime.get("_intro_view_size") != view_size:
            runtime["_intro_star_far"] = []
            runtime["_intro_star_near"] = []
            runtime["_intro_columns"] = []
            runtime["_intro_view_size"] = view_size
        seed = _ensure_neuro_log_seed()
        rng = random.Random(seed ^ 0xA51D)
        star_far = runtime.get("_intro_star_far") or []
        if not star_far:
            star_far = [
                (rng.uniform(0, game.VIEW_W), rng.uniform(0, game.VIEW_H), rng.random() * math.tau, rng.choice([1, 1, 2]))
                for _ in range(180)
            ]
            runtime["_intro_star_far"] = star_far
        star_near = runtime.get("_intro_star_near") or []
        if not star_near:
            star_near = [
                (rng.uniform(0, game.VIEW_W), rng.uniform(0, game.VIEW_H), rng.random() * math.tau, rng.choice([2, 3]))
                for _ in range(110)
            ]
            runtime["_intro_star_near"] = star_near
        columns = runtime.get("_intro_columns") or []
        if not columns:
            columns = [
                (rng.uniform(0.05, 0.95) * game.VIEW_W, rng.uniform(0.45, 0.75), rng.random() * math.tau)
                for _ in range(11)
            ]
            runtime["_intro_columns"] = columns
        return star_far, star_near, columns

    def ensure_neuro_background():
        """Procedural neon backdrop; no external art required."""
        runtime = _runtime()
        view_size = _view_size()
        surf = runtime.get("_neuro_bg_surface")
        if surf is not None and surf.get_size() == view_size:
            return surf
        _seed_intro_layers()
        seed = _ensure_neuro_log_seed()
        surf = pygame.Surface((game.VIEW_W, game.VIEW_H))
        for y in range(game.VIEW_H):
            t = y / max(1, game.VIEW_H - 1)
            col = (
                int(6 + 14 * (1 - t) + 6 * t),
                int(12 + 44 * t),
                int(24 + 82 * t),
            )
            pygame.draw.line(surf, col, (0, y), (game.VIEW_W, y))
        horizon = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
        glow_center = (game.VIEW_W // 2, int(game.VIEW_H * 0.70))
        max_r = int(math.hypot(game.VIEW_W, game.VIEW_H) * 0.60)
        for r in range(max_r, 0, -12):
            fade = max(0.0, 1.0 - r / max_r)
            alpha = int(110 * (fade ** 1.25))
            if alpha <= 0:
                continue
            color = (20, 90 + int(60 * fade), 190 + int(26 * fade), alpha)
            pygame.draw.circle(horizon, color, glow_center, r)
        surf.blit(horizon, (0, 0), special_flags=pygame.BLEND_ADD)
        ribbon = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
        rng = random.Random(seed ^ 0x8A11)
        for i in range(7):
            x0 = int(-game.VIEW_W * 0.25 + i * game.VIEW_W * 0.22 + rng.randint(-30, 30))
            x1 = x0 + int(game.VIEW_W * 0.65)
            y0 = int(game.VIEW_H * (0.15 + 0.02 * i))
            y1 = int(game.VIEW_H * 0.9)
            col = (38 + i * 6, 140 + i * 8, 220, 16 + i * 5)
            pygame.draw.polygon(ribbon, col, [(x0, y0), (x1, y0 + 40), (x1 - 120, y1), (x0 - 80, y1 - 60)])
        surf.blit(ribbon, (0, 0), special_flags=pygame.BLEND_ADD)
        grid = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
        spacing = 32
        for y in range(0, game.VIEW_H, spacing):
            alpha = max(10, int(36 * (1 - abs((y - game.VIEW_H * 0.55) / (game.VIEW_H * 0.7)))))
            pygame.draw.line(grid, (18, 60, 86, alpha), (0, y), (game.VIEW_W, y))
        for x in range(0, game.VIEW_W, spacing):
            alpha = max(8, int(32 * (1 - abs((x - game.VIEW_W * 0.5) / (game.VIEW_W * 0.7)))))
            pygame.draw.line(grid, (18, 60, 86, alpha), (x, 0), (x, game.VIEW_H))
        surf.blit(grid, (0, 0))
        dust = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
        for _ in range(180):
            px, py = rng.randrange(game.VIEW_W), rng.randrange(game.VIEW_H)
            alpha = rng.randrange(12, 44)
            pygame.draw.circle(dust, (60, 150, 210, alpha), (px, py), 1)
        surf.blit(dust, (0, 0), special_flags=pygame.BLEND_ADD)
        depth_mask = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
        for y in range(game.VIEW_H):
            fade = abs((y - game.VIEW_H * 0.55) / (game.VIEW_H * 0.55))
            alpha = int(95 * (fade ** 1.25))
            if alpha <= 0:
                continue
            pygame.draw.line(depth_mask, (0, 0, 0, alpha), (0, y), (game.VIEW_W, y))
        surf.blit(depth_mask, (0, 0))
        vignette = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
        edge_r = int(math.hypot(game.VIEW_W * 0.5, game.VIEW_H * 0.5))
        for r in range(edge_r, 0, -28):
            fade = 1.0 - r / edge_r
            alpha = int(120 * (fade ** 1.35))
            if alpha <= 0:
                continue
            pygame.draw.circle(vignette, (0, 0, 0, alpha), (game.VIEW_W // 2, game.VIEW_H // 2), r)
        surf.blit(vignette, (0, 0))
        runtime["_neuro_bg_surface"] = surf
        return surf

    def _draw_intro_starfield(surface: pygame.Surface, t: float) -> None:
        """Animated parallax starfield for the intro."""
        star_far, star_near, _ = _seed_intro_layers()
        overlay = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
        for x, y, phase, size in star_far:
            px = (x + t * 12.0) % game.VIEW_W
            twinkle = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(phase + t * 0.55))
            alpha = int(48 * twinkle)
            pygame.draw.circle(overlay, (70, 130, 180, alpha), (int(px), int(y)), size)
        for x, y, phase, size in star_near:
            px = (x - t * 26.0) % game.VIEW_W
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
        """Tall translucent pillars that feel like stacked neural towers."""
        _, _, columns = _seed_intro_layers()
        overlay = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
        base_col = (60, 170, 220)
        for idx, (x0, h_factor, phase) in enumerate(columns):
            sway = math.sin(t * (0.7 + idx * 0.05) + phase) * (24 + idx * 1.5)
            x = int(x0 + sway)
            h = int(game.VIEW_H * h_factor)
            top = game.VIEW_H - h
            width = 14 + (idx % 3) * 6
            alpha = max(40, min(140, int(100 + 60 * math.sin(t * 1.4 + phase * 1.7))))
            col = (base_col[0] - idx * 2, base_col[1], 235, alpha)
            pts = [
                (x - width, game.VIEW_H),
                (x + width, game.VIEW_H),
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
        cx, cy = game.VIEW_W // 2, int(game.VIEW_H * 0.46)
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
            pygame.draw.arc(
                orb,
                col,
                (oc - r, oc - r, 2 * r, 2 * r),
                start + math.pi * 1.05,
                start + math.pi * 1.05 + span * 0.7,
                2,
            )
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
        overlay = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
        stripe_h = 90
        sweep_y = (t * 120.0) % (game.VIEW_H + stripe_h) - stripe_h
        rect = pygame.Rect(0, int(sweep_y), game.VIEW_W, stripe_h)
        pygame.draw.rect(overlay, (20, 80, 120, 38), rect)
        pygame.draw.rect(overlay, (80, 200, 255, 48), rect, 2)
        surface.blit(overlay, (0, 0), special_flags=pygame.BLEND_ADD)

    def _neuro_outline_points(cx: int, cy: int) -> list[tuple[float, float]]:
        """Return the current NeuroViz polygon points, falling back to a circle."""
        viz = game._get_neuro_viz()
        try:
            if getattr(viz, "bars", None):
                pts = []
                for bar in viz.bars:
                    r = viz.radius + bar.get("val", 0.0)
                    rad = math.radians(bar.get("angle", 0.0) - 90)
                    pts.append((cx + math.cos(rad) * r, cy + math.sin(rad) * r))
                if len(pts) >= 3:
                    return pts
        except Exception:
            pass
        pts = []
        base_r = 140
        for i in range(36):
            ang = math.radians(i * 10.0)
            pts.append((cx + math.cos(ang) * base_r, cy + math.sin(ang) * base_r))
        return pts

    def draw_intro_waves(target: pygame.Surface, t: float):
        """Start-screen waves: radial ripples running forever until any key is pressed."""
        overlay = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
        cx, cy = game.VIEW_W // 2, int(game.VIEW_H * 0.52)
        max_r = math.hypot(game.VIEW_W, game.VIEW_H) * 0.55
        ripple_freq_hz = 0.9
        ripple_speed = 320.0
        max_age = max_r / ripple_speed
        active_ripples = int(max_age * ripple_freq_hz) + (2 if game.IS_WEB else 4)
        wave_period = 1.0 / ripple_freq_hz
        loop_window = max_age + wave_period
        energy = 0.0
        viz = game._get_neuro_viz()
        try:
            if getattr(viz, "bars", None):
                energy = sum(b.get("val", 0.0) for b in viz.bars) / max(1, len(viz.bars))
        except Exception:
            pass
        energy_norm = max(0.0, min(1.0, energy / 70.0))
        base_alpha = 130 + int(90 * energy_norm)
        base_thickness = 2 + int(3 * energy_norm)
        hue_shift = int(40 * energy_norm)
        for i in range(active_ripples):
            age = (t + i * wave_period) % loop_window
            if age > max_age:
                continue
            radius = age * ripple_speed
            if radius <= 0 or radius > max_r:
                continue
            fade = max(0.0, 1.0 - radius / max_r)
            alpha = int(base_alpha * fade)
            if alpha <= 0:
                continue
            thickness = max(1, int(base_thickness + (1 if game.IS_WEB else 2) * fade))
            col = (70, 200 + hue_shift, 255, alpha)
            pygame.draw.circle(overlay, col, (cx, cy), int(radius), thickness)
            shimmer_radius = radius + (6 + energy_norm * 6) * math.sin(age * math.tau * 0.33)
            if (not game.IS_WEB) and 0 < shimmer_radius < max_r:
                pygame.draw.circle(overlay, (col[0], col[1], col[2], int(alpha * 0.6)), (cx, cy), int(shimmer_radius), 1)
        target.blit(overlay, (0, 0))

    def draw_neuro_waves(target: pygame.Surface, t: float):
        """Home/menus: infinite outline ripples based on the current NeuroViz shape and color."""
        overlay = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
        cx, cy = game.VIEW_W // 2, int(game.VIEW_H * 0.52)
        base_pts = _neuro_outline_points(cx, cy)
        if len(base_pts) < 3:
            return
        ripple_freq_hz = 0.95
        scale_speed = 0.85
        max_scale = 4.5
        max_age = (max_scale - 1.0) / scale_speed
        active_ripples = int(max_age * ripple_freq_hz) + (2 if game.IS_WEB else 4)
        wave_period = 1.0 / ripple_freq_hz
        loop_window = max_age + wave_period
        energy = 0.0
        viz = game._get_neuro_viz()
        try:
            if getattr(viz, "bars", None):
                energy = sum(b.get("val", 0.0) for b in viz.bars) / max(1, len(viz.bars))
        except Exception:
            pass
        energy_norm = max(0.0, min(1.0, energy / 70.0))
        base_alpha = 140 + int(80 * energy_norm)
        base_thickness = 2 + int(2 * energy_norm)
        col_base = tuple(int(c) for c in getattr(viz, "poly_color", (70, 230, 255)))
        for i in range(active_ripples):
            age = (t + i * wave_period) % loop_window
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
            shimmer_scale = scale + 0.05 + 0.02 * math.sin(age * math.tau * 0.5)
            if (not game.IS_WEB) and shimmer_scale < max_scale and len(base_pts) >= 3:
                pts_shimmer = [
                    (int(round(cx + (x - cx) * shimmer_scale)), int(round(cy + (y - cy) * shimmer_scale)))
                    for x, y in base_pts
                ]
                r, g, b = [max(0, min(255, int(v))) for v in col_base[:3]]
                a = max(0, min(255, int(alpha * 0.5)))
                pygame.draw.polygon(overlay, (r, g, b, a), pts_shimmer, 1)
        line_cols = [
            (max(0, min(255, col_base[0])), max(0, min(255, col_base[1])), max(0, min(255, col_base[2])), 130),
            (max(0, min(255, col_base[0] + 20)), max(0, min(255, col_base[1] - 20)), max(0, min(255, col_base[2])), 110),
        ]
        if game.IS_WEB:
            line_cols = line_cols[:1]
        for i, col in enumerate(line_cols):
            mid_y = int(game.VIEW_H * (0.34 + i * 0.18))
            amp = 14 + i * 5
            freq = 0.018 + i * 0.007
            speed = 80 + i * 40
            pts = []
            for x in range(0, game.VIEW_W + 12, 16 if game.IS_WEB else 8):
                phase = t * speed * 0.05 + x * freq
                w = math.sin(phase) * amp + math.sin(phase * 0.35 + i) * amp * 0.24
                pts.append((x, int(round(mid_y + w))))
            if len(pts) >= 2:
                pygame.draw.lines(overlay, col, False, pts, 2)
        target.blit(overlay, (0, 0))

    def draw_neuro_hover_spike(target: pygame.Surface, rect: pygame.Rect, t: float):
        spike = pygame.Surface(rect.size, pygame.SRCALPHA)
        x = rect.width * (0.5 + 0.35 * math.sin(t * 9.0))
        pygame.draw.line(spike, (140, 255, 255, 170), (x, rect.height * 0.18), (x, rect.height * 0.82), 2)
        pygame.draw.circle(spike, (140, 255, 255, 190), (int(x), int(rect.height * 0.5)), 3)
        target.blit(spike, rect.topleft)

    def draw_neuro_button(surface: pygame.Surface, rect: pygame.Rect, label: str, font, *, hovered: bool, disabled: bool, t: float, fill_col=None, border_col=None, text_col=None, show_spike: bool = True) -> pygame.Rect:
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
        """Return button rects for the vertical menu stack around the visualizer."""
        center_x = int(game.VIEW_W * 0.52)
        base_y = int(game.VIEW_H * 0.52)
        width, height = 320, 68
        ids = ["start", "instruction", "settings", "exit"]
        if include_continue:
            ids.insert(1, "continue")
        count = len(ids)
        spacing = 78 if count >= 5 else 88
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
        col_rect = pygame.Rect(int(game.VIEW_W * 0.78), 80, int(game.VIEW_W * 0.17), game.VIEW_H - 160)
        panel = pygame.Surface(col_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (12, 30, 50, 120), panel.get_rect(), border_radius=14)
        pygame.draw.rect(panel, (70, 180, 230, 170), panel.get_rect(), width=2, border_radius=14)
        surface.blit(panel, col_rect.topleft)

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

        seed = _ensure_neuro_log_seed()
        lines = [
            f"run time: {t:6.2f}s",
            f"seed: 0x{seed:06X}",
            f"save slot: {'ready' if saved_exists else 'empty'}",
            "build: neuro-console",
            NEURO_SYSTEM_MESSAGES[int(t * 0.75) % len(NEURO_SYSTEM_MESSAGES)],
        ]
        y = col_rect.top + 14
        text_max_w = col_rect.width - 28
        for line in lines:
            for seg in _wrap_text(line, text_max_w):
                surf_line = font.render(seg, True, (150, 200, 230))
                surface.blit(surf_line, (col_rect.left + 14, y))
                y += surf_line.get_height() + 6

    def draw_neuro_title_intro(surface: pygame.Surface, title_font, prompt_font, t: float):
        """Intro screen title aligned to the holo core, with a pulsing prompt line."""
        cx_core = game.VIEW_W // 2
        cy_core = int(game.VIEW_H * 0.46)
        title_text = game.GAME_TITLE.upper()
        title = title_font.render(title_text, True, (220, 236, 250))
        ghost = title_font.render(title_text, True, (60, 160, 210))
        title_rect = title.get_rect(center=(cx_core, cy_core - 12))
        surface.blit(ghost, title_rect.move(3, 3))
        surface.blit(title, title_rect)
        underline = pygame.Surface((title_rect.width, 8), pygame.SRCALPHA)
        for x in range(0, underline.get_width(), 6):
            alpha = 90 + int(60 * math.sin(t * 3.5 + x * 0.08))
            pygame.draw.rect(underline, (90, 220, 255, alpha), pygame.Rect(x, 0, 4, 3))
        surface.blit(underline, (title_rect.left, title_rect.bottom + 8))
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
        left_line = pygame.Surface((side_len, seg_h), pygame.SRCALPHA)
        for x in range(0, side_len, seg_gap):
            alpha = 80 + int(70 * math.sin(t * 3.5 + x * 0.09))
            pygame.draw.rect(left_line, (*line_col, alpha), pygame.Rect(x, 2, seg_w, 3))
        surface.blit(left_line, (cx_core - gap - side_len, line_y - seg_h // 2))
        right_line = pygame.Surface((side_len, seg_h), pygame.SRCALPHA)
        for x in range(0, side_len, seg_gap):
            alpha = 80 + int(70 * math.sin(t * 3.5 + (side_len - x) * 0.09))
            pygame.draw.rect(right_line, (*line_col, alpha), pygame.Rect(x, 2, seg_w, 3))
        surface.blit(right_line, (cx_core + gap, line_y - seg_h // 2))
        surface.blit(grad, prompt_rect.topleft)

    def draw_neuro_home_header(surface: pygame.Surface, font):
        """Homepage header rendered with the house style title font when available."""
        try:
            sekuya = game._get_sekuya_font(font.get_height())
        except Exception:
            sekuya = font
        surface.blit(sekuya.render(f"> {game.GAME_TITLE}", True, (170, 230, 255)), (50, 70))

    def _draw_loading_screen(screen: pygame.Surface, title: str, subtitle: str = "") -> None:
        """Simple non-blocking loading frame for browser builds."""
        screen.blit(ensure_neuro_background(), (0, 0))
        _draw_intro_scanlines(screen, pygame.time.get_ticks() / 1000.0)
        title_font = game._get_sekuya_font(42)
        body_font = pygame.font.SysFont("Consolas", 22)
        accent = (70, 230, 255)
        panel = pygame.Rect(0, 0, min(720, game.VIEW_W - 120), 170)
        panel.center = (game.VIEW_W // 2, game.VIEW_H // 2)
        pygame.draw.rect(screen, (8, 18, 30), panel, border_radius=22)
        pygame.draw.rect(screen, accent, panel, 2, border_radius=22)
        title_surf = title_font.render(title, True, (220, 245, 255))
        screen.blit(title_surf, title_surf.get_rect(center=(panel.centerx, panel.y + 58)))
        if subtitle:
            body_surf = body_font.render(subtitle, True, (170, 215, 235))
            screen.blit(body_surf, body_surf.get_rect(center=(panel.centerx, panel.y + 108)))
        bar_rect = pygame.Rect(panel.x + 54, panel.bottom - 44, panel.width - 108, 10)
        pygame.draw.rect(screen, (22, 42, 58), bar_rect, border_radius=8)
        fill_w = max(
            18,
            int((bar_rect.width - 6) * (0.25 + 0.75 * (0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.008)))),
        )
        pygame.draw.rect(
            screen,
            accent,
            pygame.Rect(bar_rect.x + 3, bar_rect.y + 3, fill_w, max(1, bar_rect.height - 6)),
            border_radius=8,
        )

    return (
        draw_button,
        hex_points_flat,
        build_hex_grid,
        ensure_hex_transition,
        ensure_hex_background,
        queue_menu_transition,
        clear_menu_transition_state,
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
    )
