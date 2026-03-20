"""Visual/runtime effect classes extracted from ZGame.py."""

from __future__ import annotations

import math
import random

import pygame


def install(game):
    class HexCell:
        __slots__ = ("cx", "cy", "max_r", "trigger_delay", "current_scale", "points")

        def __init__(self, cx, cy, r):
            self.cx = float(cx)
            self.cy = float(cy)
            self.max_r = float(r)
            self.trigger_delay = 0.0
            self.current_scale = 0.0
            self.points = game.hex_points_flat(self.cx, self.cy, self.max_r)

    class HexTransition:
        def __init__(self, grid: list[HexCell]):
            self.grid = grid
            self.COLOR_FILL = (6, 10, 16)
            self.COLOR_OUTLINE = (70, 230, 255)
            self.OUTLINE_WIDTH = 2
            self.duration_in = 0.25
            self.duration_hold = 0.10
            self.duration_out = 0.25
            self.timer = 0.0
            self.state = "IDLE"
            self.midpoint_triggered = False

        def _get_delay(self, cell):
            if random.random() < 0.5:
                cx, cy = game.VIEW_W // 2, game.VIEW_H // 2
                dist = abs(cell.cy - cy)
                max_dist = (game.VIEW_H / 2.0) or 1.0
                norm_band = min(1.0, dist / max_dist)
                return norm_band * 0.55 + random.random() * 0.06
            cx, cy = game.VIEW_W // 2, game.VIEW_H // 2
            dist = math.hypot(cell.cx - cx, cell.cy - cy)
            max_dist = math.hypot(game.VIEW_W, game.VIEW_H) / 2.0
            norm_dist = min(1.0, dist / max_dist)
            return norm_dist * 0.55 + random.uniform(0, 0.08)

        def start(self):
            self.timer = 0.0
            self.state = "CLOSING"
            self.midpoint_triggered = False
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
            if self.state == "IDLE":
                return
            self.timer += dt
            if self.state == "CLOSING":
                done_count = 0
                for cell in self.grid:
                    start_t = cell.trigger_delay * 0.65
                    actual_t = (self.timer - start_t) / max(0.001, self.duration_in * 0.7)
                    t_clamped = max(0.0, min(1.0, actual_t))
                    ease = t_clamped * t_clamped * (3.0 - 2.0 * t_clamped)
                    cell.current_scale = min(1.0, ease)
                    if cell.current_scale >= 0.995:
                        done_count += 1
                if done_count >= len(self.grid) or self.timer > self.duration_in + 0.4:
                    self.state = "HOLDING"
                    self.timer = 0.0
            elif self.state == "HOLDING":
                for cell in self.grid:
                    cell.current_scale = 1.2
                if self.timer >= self.duration_hold:
                    self.state = "OPENING"
                    self.timer = 0.0
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
            if self.state == "IDLE":
                return
            angles = [math.radians(a) for a in (0, 60, 120, 180, 240, 300)]
            overlay = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
            veil = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
            if self.state == "CLOSING":
                cover_alpha = 230
            elif self.state == "HOLDING":
                cover_alpha = 255
            else:
                cover_alpha = int(200 * max(0.0, 1.0 - self.timer / max(0.001, self.duration_out)))
            veil.fill((0, 0, 0, cover_alpha))
            screen.blit(veil, (0, 0))
            for cell in self.grid:
                if cell.current_scale <= 0.01:
                    continue
                cx, cy = cell.cx, cell.cy
                outline_points = cell.points
                draw_scale = max(0.0, min(1.0, cell.current_scale)) * 0.92
                fill_points = []
                for ang in angles:
                    px = cx + cell.max_r * math.cos(ang)
                    py = cy + cell.max_r * math.sin(ang)
                    fill_points.append((cx + (px - cx) * draw_scale, cy + (py - cy) * draw_scale))
                dist_center = math.hypot(cell.cx - game.VIEW_W // 2, cell.cy - game.VIEW_H // 2)
                band_factor = 1.0 - min(1.0, dist_center / (game.VIEW_H * 0.6))
                fill_alpha = int(max(0, min(255, 255 * max(0.6, draw_scale))))
                pygame.draw.polygon(overlay, (*self.COLOR_FILL, fill_alpha), fill_points)
                outline_alpha = int(
                    max(0, min(255, 220 * (0.5 + 0.5 * band_factor) * max(0.3, draw_scale)))
                )
                pygame.draw.polygon(
                    overlay,
                    (*self.COLOR_OUTLINE, outline_alpha),
                    outline_points,
                    self.OUTLINE_WIDTH,
                )
            screen.blit(overlay, (0, 0))

    class NeuroParticle:
        __slots__ = ("x", "y", "z", "vx", "vy", "vz", "life", "life0", "size", "color", "drag")

        def __init__(self, x, y, z, vx, vy, vz, life, size, color, drag=0.0):
            self.x, self.y, self.z = float(x), float(y), float(z)
            self.vx, self.vy, self.vz = float(vx), float(vy), float(vz)
            self.life, self.life0 = float(life), float(life)
            self.size = float(size)
            self.color = color
            self.drag = drag

        def update(self, dt: float) -> bool:
            self.life -= dt
            if self.life <= 0:
                return False
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.z += self.vz * dt
            if self.z > 0:
                self.vz -= 980.0 * dt
            if self.z < 0:
                self.z = 0
            if self.drag > 0:
                self.vx *= (1.0 - self.drag * dt)
                self.vy *= (1.0 - self.drag * dt)
            return True

        def draw(self, screen, camx, camy):
            prog = self.life / self.life0
            cur_size = int(self.size * prog)
            if cur_size < 1:
                return
            gx = self.x / game.CELL_SIZE
            gy = (self.y - game.INFO_BAR_HEIGHT) / game.CELL_SIZE
            sx, sy = game.iso_world_to_screen(gx, gy, self.z, camx, camy)
            glow = game.GlowCache.get_glow_surf(cur_size, self.color)
            screen.blit(glow, (sx - cur_size, sy - cur_size), special_flags=pygame.BLEND_ADD)

    class CometCorpse:
        def __init__(self, x, y, color, size):
            self.particles = []
            for _ in range(15):
                angle = random.uniform(0, 6.28)
                speed = random.uniform(50, 180)
                self.particles.append(
                    NeuroParticle(
                        x,
                        y,
                        10,
                        math.cos(angle) * speed,
                        math.sin(angle) * speed,
                        random.uniform(100, 300),
                        life=random.uniform(0.4, 0.7),
                        size=random.uniform(4, 8),
                        color=color,
                    )
                )

        def update(self, dt):
            self.particles = [p for p in self.particles if p.update(dt)]
            return len(self.particles) > 0

        def draw_iso(self, screen, camx, camy):
            for p in self.particles:
                p.draw(screen, camx, camy)

    class CometBlast:
        def __init__(self, target: tuple[float, float], start: tuple[float, float], travel: float, on_impact=None, fx=None):
            self.tx, self.ty = target
            self.sx, self.sy = start
            self.travel = max(0.1, float(travel))
            self.elapsed = 0.0
            self.state = "flight"
            self._impact_cb = on_impact
            self.fx = fx
            self.arc_height = 350.0
            self.particles = []
            self.impact_rings = []

        @staticmethod
        def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
            t = max(0.0, min(1.0, float(t)))
            return tuple(int(aa + (bb - aa) * t) for aa, bb in zip(a, b))

        def get_current_pos_3d(self):
            t = self.elapsed / self.travel
            cx = self.sx + (self.tx - self.sx) * t
            cy = self.sy + (self.ty - self.sy) * t
            cz = math.sin(t * math.pi) * self.arc_height
            return cx, cy, cz

        def update(self, dt):
            self.elapsed += dt
            if self.state == "flight":
                cx, cy, cz = self.get_current_pos_3d()
                for _ in range(2):
                    jx = random.uniform(-5, 5)
                    jy = random.uniform(-5, 5)
                    jz = random.uniform(-5, 5)
                    self.particles.append(
                        NeuroParticle(cx + jx, cy + jy, cz + jz, 0, 0, 0, life=0.25, size=14, color=(200, 255, 255))
                    )
                    self.particles.append(
                        NeuroParticle(
                            cx + jx * 2,
                            cy + jy * 2,
                            cz + jz * 2,
                            random.uniform(-20, 20),
                            random.uniform(-20, 20),
                            random.uniform(-20, 20),
                            life=0.4,
                            size=20,
                            color=(0, 100, 255),
                        )
                    )
                if self.elapsed >= self.travel:
                    self._do_impact()
            self.particles = [p for p in self.particles if p.update(dt)]
            for ring in self.impact_rings:
                ring["r"] += ring["speed"] * dt
                ring["life"] -= dt
            self.impact_rings = [ring for ring in self.impact_rings if ring["life"] > 0]

        def _do_impact(self):
            self.state = "impact"
            game._play_comet_sfx()
            if self._impact_cb:
                self._impact_cb()
            self.impact_rings.append({"r": 10, "speed": 600, "life": 0.4, "w": 6, "col": (0, 255, 255)})
            self.impact_rings.append({"r": 10, "speed": 300, "life": 0.6, "w": 3, "col": (0, 100, 255)})
            for _ in range(40):
                self.particles.append(
                    NeuroParticle(
                        self.tx,
                        self.ty,
                        10,
                        random.uniform(-150, 150),
                        random.uniform(-150, 150),
                        random.uniform(200, 800),
                        life=random.uniform(0.5, 1.0),
                        size=random.uniform(6, 16),
                        color=(150, 255, 255),
                        drag=1.5,
                    )
                )
            for _ in range(30):
                angle = random.uniform(0, 6.28)
                speed = random.uniform(200, 500)
                self.particles.append(
                    NeuroParticle(
                        self.tx,
                        self.ty,
                        5,
                        math.cos(angle) * speed,
                        math.sin(angle) * speed,
                        random.uniform(50, 200),
                        life=random.uniform(0.3, 0.6),
                        size=random.uniform(4, 10),
                        color=(0, 200, 255),
                    )
                )

        def done(self) -> bool:
            return self.state == "impact" and len(self.particles) == 0 and len(self.impact_rings) == 0

        def draw(self, screen, camx, camy):
            pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.01)
            if self.state == "flight":
                comet_col = (80, 210, 255)
                t = pygame.time.get_ticks() * 0.001
                rot = t * 0.6
                orbit_r = game.BLAST_RADIUS * 0.5
                game.draw_iso_ground_ellipse(screen, self.tx, self.ty, game.BLAST_RADIUS, comet_col, 110 + 70 * pulse, camx, camy, fill=False, width=4)
                game.draw_iso_ground_ellipse(screen, self.tx, self.ty, orbit_r, comet_col, 90, camx, camy, fill=False, width=3)
                for i in range(6):
                    ang = rot + math.tau * i / 6.0
                    ox = self.tx + math.cos(ang) * orbit_r
                    oy = self.ty + math.sin(ang) * orbit_r
                    game.draw_iso_ground_ellipse(screen, ox, oy, orbit_r, comet_col, 90, camx, camy, fill=False, width=3)
            for ring in self.impact_rings:
                alpha = int(255 * (ring["life"] / 0.5))
                alpha = max(0, min(255, alpha))
                seed_col = self._lerp((70, 210, 255), (255, 120, 60), 1.0)
                col = ring.get("col", seed_col)
                if not isinstance(col, (tuple, list)) or len(col) < 3:
                    col = seed_col
                col = tuple(max(0, min(255, int(c))) for c in col[:3])
                game.draw_iso_ground_ellipse(screen, self.tx, self.ty, ring.get("r", game.BLAST_RADIUS), col, alpha, camx, camy, fill=False, width=int(max(1, ring.get("w", 3))))
            if self.state == "flight":
                cx, cy, cz = self.get_current_pos_3d()
                head_size = 40
                gx = cx / game.CELL_SIZE
                gy = (cy - game.INFO_BAR_HEIGHT) / game.CELL_SIZE
                sx, sy = game.iso_world_to_screen(gx, gy, cz, camx, camy)
                glow = game.GlowCache.get_glow_surf(head_size, (200, 255, 255))
                screen.blit(glow, (sx - head_size, sy - head_size), special_flags=pygame.BLEND_ADD)
            for particle in self.particles:
                particle.draw(screen, camx, camy)

    class AegisPulseRing:
        def __init__(self, x: float, y: float, r: float, delay: float, expand_time: float, fade_time: float, damage: int):
            self.x = float(x)
            self.y = float(y)
            self.r = float(r)
            self.delay = float(delay)
            self.expand_time = float(expand_time)
            self.fade_time = float(fade_time)
            self.damage = int(damage)
            self.hit_done = False
            self.t = float(delay + expand_time + fade_time)
            self.life0 = float(self.t)

        @property
        def age(self) -> float:
            return float(self.life0 - self.t)

    game.__dict__.update(
        {
            "HexCell": HexCell,
            "HexTransition": HexTransition,
            "NeuroParticle": NeuroParticle,
            "CometCorpse": CometCorpse,
            "CometBlast": CometBlast,
            "AegisPulseRing": AegisPulseRing,
        }
    )
    return HexCell, HexTransition, NeuroParticle, CometCorpse, CometBlast, AegisPulseRing
