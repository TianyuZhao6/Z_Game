"""Turret support classes extracted from ZGame.py."""

from __future__ import annotations

import math
import random
from typing import List, Tuple

import pygame
from zgame import runtime_state as rs


def install(game):
    meta = rs.meta(game)

    class AutoTurret:
        """
        Simple auto-turret that orbits near the player and fires weak bullets
        at the nearest enemy within range.
        """

        def __init__(
            self,
            owner: "game.Player",
            offset: Tuple[float, float],
            fire_interval: float = game.AUTO_TURRET_FIRE_INTERVAL,
            damage: int = game.AUTO_TURRET_BASE_DAMAGE,
            range_mult: float = game.AUTO_TURRET_RANGE_MULT,
        ):
            self.owner = owner
            self.offset_x, self.offset_y = offset
            self.fire_interval = float(fire_interval)
            self.damage = int(damage)
            self.range_mult = float(range_mult)
            self.angle = math.atan2(self.offset_y, self.offset_x) if (self.offset_x or self.offset_y) else 0.0
            self.orbit_radius = (self.offset_x ** 2 + self.offset_y ** 2) ** 0.5 or game.AUTO_TURRET_OFFSET_RADIUS
            cx, cy = owner.rect.center
            self.x = float(cx + self.offset_x)
            self.y = float(cy + self.offset_y)
            self.cd = random.random() * self.fire_interval
            self._target = None
            self._retarget_t = 0.0

        def _follow_owner(self, dt: float):
            self.angle += game.AUTO_TURRET_ORBIT_SPEED * dt
            cx, cy = self.owner.rect.center
            self.x = float(cx + math.cos(self.angle) * self.orbit_radius)
            self.y = float(cy + math.sin(self.angle) * self.orbit_radius)

        def _target_valid(self, target, max_range: float) -> bool:
            if target is None or getattr(target, "hp", 1) <= 0 or not hasattr(target, "rect"):
                return False
            dx = float(target.rect.centerx) - float(self.x)
            dy = float(target.rect.centery) - float(self.y)
            return (dx * dx + dy * dy) <= float(max_range * max_range)

        def _acquire_target(self, game_state: "game.GameState", enemies: List["game.Enemy"], max_range: float):
            spatial = getattr(game_state, "spatial", None)
            candidates = spatial.query_circle(self.x, self.y, max_range) if spatial is not None else enemies
            best = None
            best_d2 = float(max_range * max_range)
            tx, ty = self.x, self.y
            for z in candidates:
                if getattr(z, "hp", 1) <= 0 or not hasattr(z, "rect"):
                    continue
                cx, cy = z.rect.centerx, z.rect.centery
                dx, dy = cx - tx, cy - ty
                d2 = dx * dx + dy * dy
                if d2 <= best_d2:
                    best_d2 = d2
                    best = z
            self._target = best
            retarget = float(getattr(game, "WEB_TURRET_RETARGET_INTERVAL", 0.12 if getattr(game, "IS_WEB", False) else 0.06))
            idle_retarget = float(getattr(game, "WEB_TURRET_IDLE_RETARGET_INTERVAL", 0.2 if getattr(game, "IS_WEB", False) else 0.1))
            self._retarget_t = idle_retarget if best is None else retarget

        def update(self, dt: float, game_state: "game.GameState", enemies: List["game.Enemy"], bullets: List["game.Bullet"]):
            self._follow_owner(dt)
            self.cd -= dt
            owner_range = game.clamp_player_range(getattr(self.owner, "range", game.PLAYER_RANGE_DEFAULT))
            max_range = game.clamp_player_range(owner_range * self.range_mult)
            self._retarget_t -= dt
            if self._retarget_t <= 0.0 or not self._target_valid(self._target, max_range):
                self._acquire_target(game_state, enemies, max_range)
            if self.cd > 0.0 or not self._target_valid(self._target, max_range):
                return
            tx, ty = self.x, self.y
            dx = float(self._target.rect.centerx) - tx
            dy = float(self._target.rect.centery) - ty
            dist = (dx * dx + dy * dy) ** 0.5 or 1.0
            speed = game.BULLET_SPEED * 0.8
            vx = (dx / dist) * speed
            vy = (dy / dist) * speed
            bullets.append(
                game_state.acquire_bullet(
                    tx,
                    ty,
                    vx,
                    vy,
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

        def __init__(
            self,
            x: float,
            y: float,
            fire_interval: float = game.AUTO_TURRET_FIRE_INTERVAL,
            damage: int = game.AUTO_TURRET_BASE_DAMAGE,
            range_mult: float = game.AUTO_TURRET_RANGE_MULT,
        ):
            self.x = float(x)
            self.y = float(y)
            self.fire_interval = float(fire_interval)
            self.damage = int(damage)
            self.range_mult = float(range_mult)
            self.cd = random.random() * self.fire_interval
            self._target = None
            self._retarget_t = 0.0
            _, foot_w, foot_h = game.get_stationary_turret_assets()
            self.rect = pygame.Rect(0, 0, max(6, int(foot_w)), max(6, int(foot_h)))
            self.rect.midbottom = (int(self.x), int(self.y))
            self.grid_pos = (
                int(self.rect.centerx // game.CELL_SIZE),
                int((self.rect.centery - game.INFO_BAR_HEIGHT) // game.CELL_SIZE),
            )

        def _target_valid(self, target, max_range: float) -> bool:
            if target is None or getattr(target, "hp", 1) <= 0 or not hasattr(target, "rect"):
                return False
            dx = float(target.rect.centerx) - float(self.x)
            dy = float(target.rect.centery) - float(self.y)
            return (dx * dx + dy * dy) <= float(max_range * max_range)

        def _acquire_target(self, game_state: "game.GameState", enemies: List["game.Enemy"], max_range: float):
            spatial = getattr(game_state, "spatial", None)
            candidates = spatial.query_circle(self.x, self.y, max_range) if spatial is not None else enemies
            best = None
            best_d2 = float(max_range * max_range)
            tx, ty = self.x, self.y
            for z in candidates:
                if getattr(z, "hp", 1) <= 0 or not hasattr(z, "rect"):
                    continue
                cx, cy = z.rect.centerx, z.rect.centery
                dx, dy = cx - tx, cy - ty
                d2 = dx * dx + dy * dy
                if d2 <= best_d2:
                    best_d2 = d2
                    best = z
            self._target = best
            retarget = float(getattr(game, "WEB_TURRET_RETARGET_INTERVAL", 0.12 if getattr(game, "IS_WEB", False) else 0.06))
            idle_retarget = float(getattr(game, "WEB_TURRET_IDLE_RETARGET_INTERVAL", 0.2 if getattr(game, "IS_WEB", False) else 0.1))
            self._retarget_t = idle_retarget if best is None else retarget

        def update(self, dt: float, game_state: "game.GameState", enemies: List["game.Enemy"], bullets: List["game.Bullet"]):
            self.cd -= dt
            base_range = game.clamp_player_range(meta.get("base_range", game.PLAYER_RANGE_DEFAULT))
            player_range = game.compute_player_range(base_range, float(meta.get("range_mult", 1.0)))
            total_range = game.clamp_player_range(player_range * self.range_mult)
            self._retarget_t -= dt
            if self._retarget_t <= 0.0 or not self._target_valid(self._target, total_range):
                self._acquire_target(game_state, enemies, total_range)
            if self.cd > 0.0 or not self._target_valid(self._target, total_range):
                return
            tx, ty = self.x, self.y
            dx = float(self._target.rect.centerx) - tx
            dy = float(self._target.rect.centery) - ty
            dist = (dx * dx + dy * dy) ** 0.5 or 1.0
            speed = game.BULLET_SPEED * 0.8
            vx = (dx / dist) * speed
            vy = (dy / dist) * speed
            bullets.append(
                game_state.acquire_bullet(
                    tx,
                    ty,
                    vx,
                    vy,
                    max_dist=total_range,
                    damage=self.damage,
                )
            )
            self.cd = self.fire_interval

    class StationaryTurretObstacle:
        def __init__(self, rect: pygame.Rect):
            self.type = "StationaryTurret"
            self.health = None
            self.nonblocking = False
            self.rect = rect.copy()

        @property
        def grid_pos(self):
            return (
                int(self.rect.centerx // game.CELL_SIZE),
                int((self.rect.centery - game.INFO_BAR_HEIGHT) // game.CELL_SIZE),
            )

    game.__dict__.update(
        {
            "AutoTurret": AutoTurret,
            "StationaryTurret": StationaryTurret,
            "StationaryTurretObstacle": StationaryTurretObstacle,
        }
    )
    return AutoTurret, StationaryTurret, StationaryTurretObstacle
