"""Enemy projectile classes extracted from ZGame.py."""
from __future__ import annotations
import math
import random
from typing import Dict, List, Optional, Tuple
import pygame

def install(game):

    class EnemyShot:

        def __init__(self, x: float, y: float, vx: float, vy: float, dmg: int, max_dist: float=game.MAX_FIRE_RANGE, radius=4, color=(255, 120, 50)):
            self.x, self.y = (x, y)
            self.vx, self.vy = (vx, vy)
            self.dmg = int(dmg)
            self.traveled = 0.0
            self.r = int(radius)
            self.max_dist = max_dist
            self.color = tuple(color)
            self.alive = True

        def update(self, dt: float, player: 'Player', game_state: 'GameState'):
            if not self.alive:
                return
            nx = self.x + self.vx * dt
            ny = self.y + self.vy * dt
            self.traveled += ((nx - self.x) ** 2 + (ny - self.y) ** 2) ** 0.5
            self.x, self.y = (nx, ny)
            if self.traveled >= self.max_dist:
                self.alive = False
                return
            if getattr(game_state, 'biome_active', None) == 'Scorched Hell':
                self.r = game.enemy_shot_radius_for_damage(int(self.dmg))
            else:
                self.r = int(getattr(self, 'r', game.BULLET_RADIUS))
            _rr = int(getattr(self, 'r', game.BULLET_RADIUS))
            r = pygame.Rect(int(self.x - _rr), int(self.y - _rr), _rr * 2, _rr * 2)
            for gp, ob in list(game_state.obstacles.items()):
                if r.colliderect(ob.rect):
                    dmg_block = int(game.__dict__.get('ENEMY_SHOT_DAMAGE_BLOCK', game.BULLET_DAMAGE_BLOCK))
                    if getattr(ob, 'is_main_block', False):
                        ob.health = (ob.health or 0) - dmg_block
                        if ob.health <= 0:
                            del game_state.obstacles[gp]
                        self.alive = False
                        return
                    if getattr(ob, 'type', None) == 'Indestructible':
                        self.alive = False
                        return
                    if getattr(ob, 'type', None) == 'Destructible':
                        ob.health = (ob.health or 0) - dmg_block
                        if ob.health <= 0:
                            del game_state.obstacles[gp]
                        self.alive = False
                        return
                    for lan in list(getattr(game_state, 'fog_lanterns', [])):
                        if not getattr(lan, 'alive', True):
                            continue
                        gx, gy = lan.grid_pos
                        cx = int(gx * game.CELL_SIZE + game.CELL_SIZE * 0.5)
                        cy = int(gy * game.CELL_SIZE + game.CELL_SIZE * 0.5 + game.INFO_BAR_HEIGHT)
                        if r.collidepoint(cx, cy):
                            lan.hp = max(0, getattr(lan, 'hp', 1) - self.dmg)
                            if lan.hp == 0:
                                lan.alive = False
                            self.alive = False
                            return
                    self.alive = False
                    return
            if r.colliderect(player.rect):
                if getattr(player, 'hit_cd', 0.0) <= 0.0:
                    mult = getattr(game_state, 'biome_enemy_contact_mult', 1.0)
                    dmg = int(round(self.dmg * max(1.0, mult)))
                    game_state.damage_player(player, dmg, kind='hp_enemy')
                    player.hit_cd = float(game.PLAYER_HIT_COOLDOWN)
                self.alive = False

        def draw_topdown(self, screen, camx, camy):
            pygame.draw.circle(screen, self.color, (int(self.x - camx), int(self.y - camy)), self.r)

        def draw_iso(self, screen, camx, camy):
            wx = self.x / game.CELL_SIZE
            wy = (self.y - game.INFO_BAR_HEIGHT) / game.CELL_SIZE
            sx, sy = game.iso_world_to_screen(wx, wy, 0.0, camx, camy)
            pygame.draw.circle(screen, self.color, (int(sx), int(sy)), self.r)
    game.__dict__.update({'EnemyShot': EnemyShot})
    return EnemyShot
