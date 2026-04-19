"""Low-level world runtime helpers extracted from ZGame.py."""

from __future__ import annotations

import math
import random

import pygame


def install(game):
    class GridBuckets:
        def __init__(self, cell=64):
            self.cell = max(1, int(cell))
            self.buckets = {}
            self._object_keys = {}

        def _key(self, x, y):
            return (int(x) // self.cell, int(y) // self.cell)

        def _resolve_xy(self, obj):
            rect = getattr(obj, "rect", None)
            if rect is not None:
                return (float(rect.centerx), float(rect.centery))
            if hasattr(obj, "base_x") and hasattr(obj, "base_y"):
                return (float(getattr(obj, "base_x", 0.0)), float(getattr(obj, "base_y", 0.0)))
            return (float(getattr(obj, "x", 0.0)), float(getattr(obj, "y", 0.0)))

        def clear(self):
            self.buckets.clear()
            self._object_keys.clear()

        def rebuild(self, objects):
            self.clear()
            for obj in objects:
                self.insert(obj)

        def insert(self, obj, x=None, y=None):
            if obj is None:
                return
            if x is None or y is None:
                x, y = self._resolve_xy(obj)
            k = self._key(x, y)
            self.buckets.setdefault(k, []).append(obj)
            self._object_keys[id(obj)] = k

        def remove(self, obj):
            if obj is None:
                return
            obj_id = id(obj)
            key = self._object_keys.pop(obj_id, None)
            if key is None:
                return
            bucket = self.buckets.get(key)
            if not bucket:
                return
            try:
                bucket.remove(obj)
            except ValueError:
                pass
            if not bucket:
                self.buckets.pop(key, None)

        def update(self, obj, x=None, y=None):
            if obj is None:
                return
            if x is None or y is None:
                x, y = self._resolve_xy(obj)
            new_key = self._key(x, y)
            obj_id = id(obj)
            old_key = self._object_keys.get(obj_id)
            if old_key is None:
                self.insert(obj, x, y)
                return
            if old_key == new_key:
                return
            bucket = self.buckets.get(old_key)
            if bucket:
                try:
                    bucket.remove(obj)
                except ValueError:
                    pass
                if not bucket:
                    self.buckets.pop(old_key, None)
            self.buckets.setdefault(new_key, []).append(obj)
            self._object_keys[obj_id] = new_key

        def _query_keys(self, min_x, min_y, max_x, max_y):
            for gx in range(min_x, max_x + 1):
                for gy in range(min_y, max_y + 1):
                    for obj in self.buckets.get((gx, gy), ()):
                        yield obj

        def query_circle(self, x, y, r, *, pad_cells=0, inflate=0.0):
            cx, cy = self._key(x, y)
            out = []
            seen = set()
            rr = max(0.0, float(r)) + max(0.0, float(inflate))
            span = max(1, int(math.ceil(rr / float(self.cell))) + max(0, int(pad_cells)))
            for obj in self._query_keys(cx - span, cy - span, cx + span, cy + span):
                obj_id = id(obj)
                if obj_id in seen:
                    continue
                seen.add(obj_id)
                ox, oy = self._resolve_xy(obj)
                dx = ox - x
                dy = oy - y
                if dx * dx + dy * dy <= rr * rr:
                    out.append(obj)
            return out

        def query_rect(self, rect, *, pad_px=0.0, pad_cells=0):
            if rect is None:
                return []
            if pad_px:
                rect = rect.inflate(int(pad_px * 2), int(pad_px * 2))
            min_x, min_y = self._key(rect.left, rect.top)
            max_x, max_y = self._key(rect.right, rect.bottom)
            pad = max(0, int(pad_cells))
            out = []
            seen = set()
            for obj in self._query_keys(min_x - pad, min_y - pad, max_x + pad, max_y + pad):
                obj_id = id(obj)
                if obj_id in seen:
                    continue
                seen.add(obj_id)
                obj_rect = getattr(obj, "rect", None)
                if obj_rect is not None:
                    if rect.colliderect(obj_rect):
                        out.append(obj)
                    continue
                ox, oy = self._resolve_xy(obj)
                if rect.collidepoint(int(ox), int(oy)):
                    out.append(obj)
            return out

    class SpatialHash(GridBuckets):
        def rebuild(self, enemies):
            super().rebuild(enemies)

        def query_circle(self, x, y, r):
            return super().query_circle(
                x,
                y,
                r,
                pad_cells=1,
                inflate=max(16, game.CELL_SIZE // 2),
            )

    class TornadoEntity:
        def __init__(self, x, y, r=game.HURRICANE_START_RADIUS, *, spin_rate=None, spin_dir=None):
            self.x = float(x)
            self.y = float(y)
            self.r = float(r)
            self.t = random.uniform(0, 100)
            if spin_dir is None:
                spin_dir = random.choice((-1.0, 1.0))
            self.spin_dir = -1.0 if float(spin_dir) < 0.0 else 1.0
            if spin_rate is not None:
                self.spin_rate = max(0.05, float(spin_rate))
            ang = random.uniform(0, math.tau)
            self.move_speed = random.uniform(16.0, 40.0)
            self.vx = math.cos(ang) * self.move_speed
            self.vy = math.sin(ang) * self.move_speed
            self._bound_margin = game.HURRICANE_MAX_RADIUS * 1.2
            self._base_particles = 35
            self._extra_particles = 30
            self.particles = [self._make_particle() for _ in range(self._base_particles)]
            self._ring_swooshes = [self._make_swoosh() for _ in range(9)]
            self._zone_surface = None
            self._zone_surface_size = (0, 0)
            self._funnel_surface_cache = {}
            self._draw_cache_surface = None
            self._draw_cache_size = (0, 0)
            self._draw_cache_anchor = (0, 0)
            self._draw_cache_at_ms = -999999
            self._draw_cache_stamp = None

        def _make_particle(self):
            return {
                "type": "wind" if random.random() < 0.7 else "debris",
                "ang": random.uniform(0, math.tau),
                "h": random.uniform(0.05, 1.2),
                "dist": random.uniform(0.6, 1.6),
                "speed": random.uniform(3.0, 6.0),
                "len": random.uniform(0.15, 0.45),
                "color": random.choice(game.WIND_PARTICLE_COLORS),
            }

        def _make_swoosh(self):
            swoosh_colors = [
                (200, 240, 255),
                (160, 210, 230),
                (120, 210, 255),
            ]
            return {
                "ang": random.uniform(0, math.tau),
                "rad_ratio": random.uniform(0.3, 1.05),
                "len_ratio": random.uniform(0.12, 0.20),
                "thick": random.randint(2, 4),
                "alpha": random.randint(140, 210),
                "color": random.choice(swoosh_colors),
                "t": 0.0,
                "ttl": random.uniform(0.7, 1.3),
            }

        def update(self, dt):
            self.r = min(game.HURRICANE_MAX_RADIUS, self.r + game.HURRICANE_GROWTH_RATE * dt)
            self.t += dt * 5.0
            detail_mult = 0.6 if getattr(game, "IS_WEB", False) else 1.0
            target = int((self._base_particles + self._extra_particles * min(1.0, self.r / game.HURRICANE_MAX_RADIUS)) * detail_mult)
            target = max(14 if getattr(game, "IS_WEB", False) else 20, target)
            while len(self.particles) < target:
                self.particles.append(self._make_particle())
            if len(self.particles) > target:
                self.particles = self.particles[:target]
            map_w = game.GRID_SIZE * game.CELL_SIZE
            map_h = game.GRID_SIZE * game.CELL_SIZE
            min_x = self._bound_margin
            max_x = map_w - self._bound_margin
            min_y = game.INFO_BAR_HEIGHT + self._bound_margin
            max_y = game.INFO_BAR_HEIGHT + map_h - self._bound_margin
            self.x += self.vx * dt
            self.y += self.vy * dt
            if self.x < min_x or self.x > max_x:
                self.x = max(min_x, min(self.x, max_x))
                self.vx *= -1
            if self.y < min_y or self.y > max_y:
                self.y = max(min_y, min(self.y, max_y))
                self.vy *= -1
            vis_dir = -self.spin_dir
            spin_growth = min(1.0, self.r / game.HURRICANE_MAX_RADIUS)
            vis_spin_scale = 0.6 + 0.9 * spin_growth
            for particle in self.particles:
                spin = particle["speed"] * (1.8 - min(1.0, particle["h"]))
                particle["ang"] += spin * dt * vis_dir * vis_spin_scale
            for swoosh in list(self._ring_swooshes):
                swoosh["t"] += dt
                if swoosh["t"] >= swoosh["ttl"]:
                    self._ring_swooshes.remove(swoosh)
            swoosh_target = 5 if getattr(game, "IS_WEB", False) else 9
            if len(self._ring_swooshes) > swoosh_target:
                self._ring_swooshes = self._ring_swooshes[:swoosh_target]
            while len(self._ring_swooshes) < swoosh_target:
                self._ring_swooshes.append(self._make_swoosh())

        def apply_vortex_physics(self, ent, dt, resist_scale=1.0):
            ecx, ecy = ent.rect.centerx, ent.rect.centery
            dx = self.x - ecx
            dy = self.y - ecy
            dist = math.hypot(dx, dy)
            effect_radius = self.r * game.HURRICANE_RANGE_MULT
            if dist <= 10.0 or dist > effect_radius:
                return 0.0, 0.0
            nx, ny = (dx / dist, dy / dist)
            tx, ty = (-ny, nx)
            if self.spin_dir < 0:
                tx, ty = (-tx, -ty)
            suction_mult = min(1.0, dist / 60.0)
            radial_force = game.HURRICANE_PULL_STRENGTH * suction_mult
            rot_mult = 1.0 + (1.0 - min(1.0, dist / effect_radius)) * 2.0
            tangential_force = game.HURRICANE_VORTEX_POWER * rot_mult
            vx = (nx * radial_force) + (tx * tangential_force)
            vy = (ny * radial_force) + (ty * tangential_force)
            vy *= 0.5
            return vx * dt * resist_scale, vy * dt * resist_scale

        def _draw_to_surface(self, screen, cx, cy):
            vis_dir = -self.spin_dir
            spin_growth = min(1.0, self.r / game.HURRICANE_MAX_RADIUS)
            vis_spin_scale = 0.6 + 0.9 * spin_growth
            base_w = self.r * 1.6
            effect_radius = self.r * game.HURRICANE_RANGE_MULT
            rx_zone, ry_zone = game.iso_circle_radii_screen(effect_radius)
            zone_size = (rx_zone * 2, ry_zone * 2)
            zone = getattr(self, "_zone_surface", None)
            if zone is None or getattr(self, "_zone_surface_size", (0, 0)) != zone_size:
                zone = pygame.Surface(zone_size, pygame.SRCALPHA)
                self._zone_surface = zone
                self._zone_surface_size = zone_size
            zone.fill((0, 0, 0, 0))
            pygame.draw.ellipse(zone, (40, 60, 80, 50), zone.get_rect())
            pygame.draw.ellipse(zone, (120, 220, 255, 110), zone.get_rect(), width=3)
            streaks = 4 if getattr(game, "IS_WEB", False) else 8
            for i in range(streaks):
                ang = self.t * 0.6 * vis_spin_scale * vis_dir + i * (math.tau / streaks)
                px = rx_zone + math.cos(ang) * rx_zone * 0.82
                py = ry_zone + math.sin(ang) * ry_zone * 0.82
                tx = -math.sin(ang) * 10 * vis_dir
                ty = math.cos(ang) * 6 * vis_dir
                pygame.draw.line(zone, (140, 220, 255, 140), (px - tx, py - ty), (px + tx, py + ty), 2)
            for swoosh in self._ring_swooshes:
                fade = max(0.0, 1.0 - (swoosh["t"] / max(0.001, swoosh["ttl"])))
                if fade <= 0:
                    continue
                arc_ang = swoosh["ang"] + math.pi + self.t * 0.35 * vis_dir
                r_ratio = swoosh["rad_ratio"]
                arc_len = rx_zone * swoosh["len_ratio"]
                x0 = rx_zone + math.cos(arc_ang) * rx_zone * r_ratio
                y0 = ry_zone + math.sin(arc_ang) * ry_zone * r_ratio
                tx = -math.sin(arc_ang) * arc_len * vis_dir
                ty = math.cos(arc_ang) * arc_len * 0.55 * vis_dir
                start = (x0 - tx * 0.5, y0 - ty * 0.5)
                end = (x0 + tx * 0.5, y0 + ty * 0.5)
                cx_mid = x0 + (-ty) * 0.2 + math.cos(arc_ang) * 4
                cy_mid = y0 + (tx) * 0.2 + math.sin(arc_ang) * 2
                steps = 6 if getattr(game, "IS_WEB", False) else 12
                color = swoosh["color"]
                alpha = int(swoosh["alpha"] * fade)
                for j in range(steps):
                    t = j / (steps - 1)
                    ax = (1 - t) * start[0] + t * cx_mid
                    ay = (1 - t) * start[1] + t * cy_mid
                    bx = (1 - t) * cx_mid + t * end[0]
                    by = (1 - t) * cy_mid + t * end[1]
                    px = (1 - t) * ax + t * bx
                    py = (1 - t) * ay + t * by
                    taper = 1.0 - abs(t * 2 - 1)
                    radius = max(1, int(swoosh["thick"] * (0.5 + 0.8 * taper)))
                    pygame.draw.circle(zone, (*color, alpha), (px, py), radius)
            screen.blit(zone, (cx - rx_zone, cy - ry_zone))
            layer_step = 2 if getattr(game, "IS_WEB", False) else 1
            for i in range(0, game.TORNADO_LAYER_COUNT, layer_step):
                ratio = i / float(game.TORNADO_LAYER_COUNT)
                width = base_w * (0.25 + 0.8 * (ratio ** 1.8))
                glitch_x = 0
                if random.random() < 0.05:
                    glitch_x = random.randint(-4, 4)
                wobble = math.sin(self.t + ratio * 4.0) * (15 * ratio)
                draw_x = cx + wobble + glitch_x
                draw_y = cy - (ratio * game.TORNADO_FUNNEL_HEIGHT)
                rx, ry = game.iso_circle_radii_screen(width * 0.5)
                alpha = 170 if i < game.TORNADO_LAYER_COUNT - 1 else 90
                color = (
                    int(game.TORNADO_EDGE_COLOR[0] + (game.TORNADO_CORE_COLOR[0] - game.TORNADO_EDGE_COLOR[0]) * ratio),
                    int(game.TORNADO_EDGE_COLOR[1] + (game.TORNADO_CORE_COLOR[1] - game.TORNADO_EDGE_COLOR[1]) * ratio),
                    int(game.TORNADO_EDGE_COLOR[2] + (game.TORNADO_CORE_COLOR[2] - game.TORNADO_EDGE_COLOR[2]) * ratio),
                )
                cache = self._funnel_surface_cache
                key = (int(rx), int(ry), color, int(alpha))
                surf = cache.get(key)
                if surf is None:
                    surf = pygame.Surface((rx * 2, ry * 2), pygame.SRCALPHA)
                    pygame.draw.ellipse(surf, (*color, alpha), surf.get_rect())
                    pygame.draw.ellipse(surf, (120, 220, 255, int(alpha * 0.9)), surf.get_rect(), width=2)
                    if len(cache) > 96:
                        cache.clear()
                    cache[key] = surf
                screen.blit(surf, (draw_x - rx, draw_y - ry))
            ring_ratios = (0.3, 0.7) if getattr(game, "IS_WEB", False) else (0.2, 0.45, 0.7, 0.9)
            for r_ratio in ring_ratios:
                width = base_w * (0.25 + 0.75 * (r_ratio ** 1.5))
                rx, ry = game.iso_circle_radii_screen(width * 0.5)
                y = cy - (r_ratio * game.TORNADO_FUNNEL_HEIGHT)
                pulse = 0.7 + 0.3 * math.sin(self.t * 0.8 + r_ratio * 4.0)
                pygame.draw.ellipse(
                    screen,
                    (140, 230, 255, int(80 * pulse)),
                    pygame.Rect(cx - rx, y - ry, rx * 2, ry * 2),
                    width=2,
                )
            particle_iter = self.particles[::2] if getattr(game, "IS_WEB", False) and len(self.particles) > 18 else self.particles
            for particle in particle_iter:
                h_px = particle["h"] * game.TORNADO_FUNNEL_HEIGHT
                w_at_h = base_w * (0.25 + 0.8 * (particle["h"] ** 1.8)) * particle["dist"]
                px_off = math.cos(particle["ang"]) * (w_at_h * 0.5)
                py_off = math.sin(particle["ang"]) * (w_at_h * 0.25)
                wobble_at_h = math.sin(self.t + particle["h"] * 4.0) * (15 * particle["h"])
                px = cx + wobble_at_h + px_off
                py = cy - h_px + py_off
                is_behind = math.sin(particle["ang"]) < 0
                if particle["type"] == "wind":
                    size_scale = 1.0 + 0.6 * min(1.0, self.r / game.HURRICANE_MAX_RADIUS)
                    length = 12 * size_scale * (0.6 + 0.4 * particle.get("len", 0.25))
                    dir_ang = particle["ang"] + math.pi / 2 * vis_dir
                    tail_x = px - math.cos(dir_ang) * length
                    tail_y = py - math.sin(dir_ang) * (length * 0.5)
                    mid_x = (px + tail_x) * 0.5
                    mid_y = (py + tail_y) * 0.5
                    bend = 6 * size_scale
                    bx = mid_x + math.cos(dir_ang + math.pi / 2) * bend
                    by = mid_y + math.sin(dir_ang + math.pi / 2) * (bend * 0.6)
                    color = particle["color"]
                    alpha = 90 if is_behind else 230
                    pygame.draw.lines(screen, (*color, alpha), False, [(px, py), (bx, by), (tail_x, tail_y)], 2)
                else:
                    color = (40, 50, 60) if is_behind else (200, 220, 230)
                    size = 2 if is_behind else 4
                    pygame.draw.circle(screen, color, (int(px), int(py)), size)

        def draw(self, screen, camx, camy):
            cx, cy = game.iso_world_to_screen(
                self.x / game.CELL_SIZE,
                (self.y - game.INFO_BAR_HEIGHT) / game.CELL_SIZE,
                0,
                camx,
                camy,
            )
            refresh_ms = int(getattr(game, "WEB_HURRICANE_VISUAL_REFRESH_MS", 0) or 0)
            if getattr(game, "IS_WEB", False) and refresh_ms > 0:
                effect_radius = self.r * game.HURRICANE_RANGE_MULT
                rx_zone, ry_zone = game.iso_circle_radii_screen(effect_radius)
                margin = 24
                surf_w = max(int(rx_zone * 2 + 80), int(self.r * 2.2), 160) + margin * 2
                surf_h = int(game.TORNADO_FUNNEL_HEIGHT + ry_zone * 2 + 80) + margin * 2
                anchor_x = surf_w // 2
                anchor_y = margin + game.TORNADO_FUNNEL_HEIGHT + ry_zone
                phase_bucket = int(self.t * 10.0)
                cache_stamp = (
                    int(self.r // 6),
                    int(self.spin_dir),
                    int(len(self.particles)),
                    phase_bucket,
                    int(surf_w),
                    int(surf_h),
                )
                now_ms = pygame.time.get_ticks()
                if (
                    self._draw_cache_surface is None
                    or self._draw_cache_size != (surf_w, surf_h)
                    or self._draw_cache_stamp != cache_stamp
                    or (now_ms - int(self._draw_cache_at_ms)) >= refresh_ms
                ):
                    surface = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
                    self._draw_to_surface(surface, anchor_x, anchor_y)
                    self._draw_cache_surface = surface
                    self._draw_cache_size = (surf_w, surf_h)
                    self._draw_cache_anchor = (anchor_x, anchor_y)
                    self._draw_cache_at_ms = now_ms
                    self._draw_cache_stamp = cache_stamp
                screen.blit(
                    self._draw_cache_surface,
                    (
                        int(cx - self._draw_cache_anchor[0]),
                        int(cy - self._draw_cache_anchor[1]),
                    ),
                )
                return
            self._draw_to_surface(screen, cx, cy)

    game.__dict__.update({"GridBuckets": GridBuckets, "SpatialHash": SpatialHash, "TornadoEntity": TornadoEntity})
    return SpatialHash, TornadoEntity
