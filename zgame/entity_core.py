from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import pygame


def install(game):
    class Graph:
        def __init__(self):
            self.edges: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
            self.weights: Dict[Tuple[Tuple[int, int], Tuple[int, int]], float] = {}

        def add_edge(self, a, b, w):
            self.edges.setdefault(a, []).append(b)
            self.weights[(a, b)] = w

        def neighbors(self, node):
            return self.edges.get(node, [])

        def cost(self, a, b):
            return self.weights.get((a, b), float("inf"))

    class Obstacle:
        def __init__(self, x: int, y: int, obstacle_type: str, health: Optional[int] = None):
            px = x * game.CELL_SIZE
            py = y * game.CELL_SIZE + game.INFO_BAR_HEIGHT
            self.rect = pygame.Rect(px, py, game.CELL_SIZE, game.CELL_SIZE)
            self.type: str = obstacle_type
            self.health: Optional[int] = health

        def is_destroyed(self) -> bool:
            return self.type == "Destructible" and self.health <= 0

        @property
        def grid_pos(self):
            return self.rect.x // game.CELL_SIZE, (self.rect.y - game.INFO_BAR_HEIGHT) // game.CELL_SIZE

    class FogLantern(Obstacle):
        def __init__(self, x: int, y: int, hp: int = game.FOG_LANTERN_HP):
            super().__init__(x, y, "Lantern", health=hp)
            self.nonblocking = False
            self.rect = pygame.Rect(self.rect.x + 6, self.rect.y + 6, game.CELL_SIZE - 12, game.CELL_SIZE - 12)

        @property
        def alive(self):
            return self.health is None or self.health > 0

    class MainBlock(Obstacle):
        def __init__(self, x: int, y: int, health: Optional[int] = game.MAIN_BLOCK_HEALTH):
            super().__init__(x, y, "Destructible", health)
            self.is_main_block = True

    class Item:
        def __init__(self, x: int, y: int, is_main=False):
            self.x = x
            self.y = y
            self.is_main = is_main
            self.radius = game.CELL_SIZE // 3
            self.center = (
                self.x * game.CELL_SIZE + game.CELL_SIZE // 2,
                self.y * game.CELL_SIZE + game.CELL_SIZE // 2 + game.INFO_BAR_HEIGHT,
            )
            self.rect = pygame.Rect(
                self.center[0] - self.radius,
                self.center[1] - self.radius,
                self.radius * 2,
                self.radius * 2,
            )

    class Player:
        def __init__(self, pos: Tuple[int, int], speed: int = game.PLAYER_SPEED):
            self.x = pos[0] * game.CELL_SIZE
            self.y = pos[1] * game.CELL_SIZE
            self.speed = float(speed)
            self.size = int(game.CELL_SIZE * 0.6)
            self.rect = pygame.Rect(self.x, self.y + game.INFO_BAR_HEIGHT, self.size, self.size)
            self.max_hp = int(game.PLAYER_MAX_HP)
            self.hp = int(game.PLAYER_MAX_HP)
            self.crit_chance = max(
                0.0,
                min(
                    0.95,
                    float(game.META.get("base_crit", game.CRIT_CHANCE_BASE)) + float(game.META.get("crit", 0.0)),
                ),
            )
            self.crit_mult = float(game.CRIT_MULT_BASE)
            self.slow_t = 0.0
            self.slow_mult = 1.0
            self._slow_frac = 0.0
            self.hit_cd = 0.0
            self.radius = game.PLAYER_RADIUS
            self.level = 1
            self.xp = 0
            self.xp_to_next = game.player_xp_required(self.level)
            self.xp_to_next = game.player_xp_required(self.level)
            self.levelup_pending = 0
            self.xp_gain_mult = 1.0
            self.bullet_damage = int(game.META.get("base_dmg", game.BULLET_DAMAGE_ENEMY)) + int(game.META.get("dmg", 0))
            self.fire_rate_mult = float(game.META.get("firerate_mult", 1.0))
            self.bullet_pierce = int(game.META.get("pierce_level", 0))
            self.bullet_ricochet = int(game.META.get("ricochet_level", 0))
            self.shrapnel_level = int(game.META.get("shrapnel_level", 0))
            self.explosive_rounds_level = int(game.META.get("explosive_rounds_level", 0))
            self.dot_rounds_level = int(game.META.get("dot_rounds_level", 0))
            self.aegis_pulse_level = int(game.META.get("aegis_pulse_level", 0))
            if self.aegis_pulse_level > 0:
                _, _, cd = game.aegis_pulse_stats(self.aegis_pulse_level, self.max_hp)
                self._aegis_pulse_cd = float(cd)
            else:
                self._aegis_pulse_cd = 0.0
            self.range_base = game.clamp_player_range(game.META.get("base_range", game.PLAYER_RANGE_DEFAULT))
            self.range = game.compute_player_range(self.range_base, game.META.get("range_mult", 1.0))
            spd0 = float(game.META.get("base_speed", game.PLAYER_SPEED))
            spd_mult = float(game.META.get("speed_mult", 1.0))
            spd_add = float(game.META.get("speed", 0))
            self.speed = min(game.PLAYER_SPEED_CAP, max(1.0, spd0 * spd_mult + spd_add))
            hp0 = int(game.META.get("base_maxhp", game.PLAYER_MAX_HP))
            self.max_hp = hp0 + int(game.META.get("maxhp", 0))
            self.hp = min(self.max_hp, self.max_hp)
            self._hit_flash = 0.0
            self._flash_prev_hp = int(self.hp)
            self.shield_hp = 0
            self.shield_max = 0
            self._hud_shield_vis = 0.0
            self.carapace_hp = int(game.META.get("carapace_shield_hp", 0))
            if self.carapace_hp > 0:
                self._hud_shield_vis = self.carapace_hp / float(max(1, self.max_hp))
            self.bone_plating_level = int(game.META.get("bone_plating_level", 0))
            self.bone_plating_hp = 0
            self._bone_plating_cd = float(game.BONE_PLATING_GAIN_INTERVAL)
            self._bone_plating_glow = 0.0
            self.acid_dot_timer = 0.0
            self.acid_dot_dps = 0.0
            self._acid_dmg_accum = 0.0
            self._acid_dot_accum = 0.0
            self._enemy_paint_slow = 0.0
            self._enemy_paint_dot_t = 0.0
            self._enemy_paint_dot_accum = 0.0
            self._enemy_paint_vignette_t = 0.0
            self.dot_ticks = []
            self.apply_slow_extra = 0.0
            self.facing = "S"
            self.status = "S"
            self.is_moving = False
            self.blast_cd = 0.0
            self.teleport_cd = 0.0
            self.targeting_skill = None
            self.skill_target_pos = (self.rect.centerx, self.rect.centery)
            self.skill_target_valid = False
            self.skill_target_origin = None
            self.skill_flash = {"blast": 0.0, "teleport": 0.0}

        @staticmethod
        def _dir8_from_vec(dx: float, dy: float) -> Optional[str]:
            if dx == 0 and dy == 0:
                return None
            ang = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
            idx = int((ang + 22.5) // 45.0) % 8
            return ["E", "SE", "S", "SW", "W", "NW", "N", "NE"][idx]

        def _update_move_status(self, dx: float, dy: float) -> None:
            if dx == 0 and dy == 0:
                self.is_moving = False
                return
            self.is_moving = True
            if game.USE_ISO:
                screen_dx = dx - dy
                screen_dy = dx + dy
            else:
                screen_dx, screen_dy = dx, dy
            new_dir = self._dir8_from_vec(screen_dx, screen_dy)
            if new_dir:
                self.facing = new_dir
                self.status = new_dir

        @property
        def pos(self):
            return int((self.x + self.size // 2) // game.CELL_SIZE), int((self.y + self.size // 2) // game.CELL_SIZE)

        def apply_dot(self, dps: float, duration: float):
            self.dot_ticks.append((float(dps), float(duration)))

        def reset_bone_plating(self):
            self.bone_plating_hp = 0
            self._bone_plating_cd = float(game.BONE_PLATING_GAIN_INTERVAL)
            self._bone_plating_glow = 0.0

        def on_level_start(self):
            self.reset_bone_plating()

        def update_bone_plating(self, dt: float):
            lvl = int(getattr(self, "bone_plating_level", 0))
            glow = float(getattr(self, "_bone_plating_glow", 0.0))
            if lvl <= 0:
                self._bone_plating_glow = max(0.0, glow - dt * 0.6)
                return
            cd = float(getattr(self, "_bone_plating_cd", game.BONE_PLATING_GAIN_INTERVAL))
            cd -= dt
            gained = False
            while cd <= 0.0:
                cd += game.BONE_PLATING_GAIN_INTERVAL
                self.bone_plating_hp = int(self.bone_plating_hp) + max(1, lvl) * game.BONE_PLATING_STACK_HP
                gained = True
            self._bone_plating_cd = cd
            if gained:
                glow = 0.85
            else:
                glow = max(0.0, glow - dt * 0.6)
            self._bone_plating_glow = glow

        def take_damage(self, amount: int):
            if self.hit_cd <= 0.0:
                before = int(self.hp)
                self.hp = max(0, self.hp - int(amount))
                if self.hp < before:
                    self._hit_flash = float(game.HIT_FLASH_DURATION)
                    self._flash_prev_hp = int(self.hp)
                self.hit_cd = float(game.PLAYER_HIT_COOLDOWN)

        def move(self, keys, obstacles, dt):
            self.apply_slow_extra = 0.0
            lingering_slow = float(getattr(self, "_slow_frac", 0.0))
            if lingering_slow > 0.0:
                self.apply_slow_extra = max(self.apply_slow_extra, lingering_slow)
            paint_slow = float(getattr(self, "_enemy_paint_slow", 0.0))
            if paint_slow > 0.0:
                self.apply_slow_extra = max(self.apply_slow_extra, paint_slow)
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
                    self.hp = max(0, self.hp - int(total))
            mx = my = 0
            if game.binding_pressed(keys, "move_up"):
                mx -= 1
                my -= 1
            if game.binding_pressed(keys, "move_down"):
                mx += 1
                my += 1
            if game.binding_pressed(keys, "move_left"):
                mx -= 1
                my += 1
            if game.binding_pressed(keys, "move_right"):
                mx += 1
                my -= 1
            if mx != 0 or my != 0:
                length = (mx * mx + my * my) ** 0.5
                dx = mx / length
                dy = my / length
            else:
                dx = dy = 0.0
            self._update_move_status(dx, dy)
            frame_scale = dt * 60.0
            spd = int(self.speed)
            if getattr(self, "apply_slow_extra", 0.0) > 0.0:
                spd = max(1, int(spd * (1.0 - min(0.85, float(self.apply_slow_extra)))))
            prev_cx, prev_cy = self.rect.centerx, self.rect.centery
            step_x, step_y = game.iso_equalized_step(dx, dy, spd * frame_scale)
            game.collide_and_slide_circle(self, obstacles.values(), step_x, step_y)
            self._last_move_vec = (self.rect.centerx - prev_cx, self.rect.centery - prev_cy)

        def fire_cooldown(self) -> float:
            eff = min(game.MAX_FIRERATE_MULT, float(self.fire_rate_mult))
            return max(game.MIN_FIRE_COOLDOWN, game.FIRE_COOLDOWN / max(1.0, eff))

        def add_xp(self, amount: int):
            gain = max(0, amount)
            gain = int(round(gain * max(0.0, float(getattr(self, "xp_gain_mult", 1.0)))))
            self.xp += gain
            leveled = 0
            while self.xp >= self.xp_to_next:
                self.xp -= self.xp_to_next
                self.level += 1
                self.hp = min(self.max_hp, self.hp + 3)
                self.xp_to_next = game.player_xp_required(self.level)
                leveled += 1
            self.levelup_pending = getattr(self, "levelup_pending", 0) + leveled

        def draw(self, screen):
            pygame.draw.rect(screen, (0, 255, 0), self.rect)

    return Graph, Obstacle, FogLantern, MainBlock, Item, Player
