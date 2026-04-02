"""Enemy base classes extracted from ZGame.py."""
from __future__ import annotations
import math
import random
from typing import Dict, List, Optional, Tuple
import pygame

def install(game):
    def _meta():
        if hasattr(game, "_meta_state"):
            return game._meta_state()
        return game.META

    class AfterImageGhost:

        def __init__(self, x, y, w, h, base_color, ttl=game.AFTERIMAGE_TTL, sprite: pygame.Surface | None=None):
            self.x = int(x)
            self.y = int(y)
            self.w = int(w)
            self.h = int(h)
            r, g, b = base_color if base_color else (120, 220, 160)
            self.color = (int(r), int(g), int(b))
            self.ttl = float(ttl)
            self.life0 = float(ttl)
            self.sprite = sprite

        def update(self, dt):
            self.ttl -= dt
            return self.ttl > 0

        def draw_topdown(self, screen, cam_x, cam_y):
            if self.ttl <= 0:
                return
            alpha = max(0, min(255, int(255 * (self.ttl / self.life0))))
            rect = pygame.Rect(0, 0, self.w, self.h)
            rect.midbottom = (int(self.x - cam_x), int(self.y - cam_y))
            s = pygame.Surface(rect.size, pygame.SRCALPHA)
            s.fill((*self.color, alpha))
            screen.blit(s, rect.topleft)

        def draw_iso(self, screen, camx, camy):
            if self.ttl <= 0:
                return
            alpha = max(0, min(255, int(255 * (self.ttl / self.life0))))
            wx = self.x / game.CELL_SIZE
            wy = (self.y - game.INFO_BAR_HEIGHT) / game.CELL_SIZE
            sx, sy = game.iso_world_to_screen(wx, wy, 0, camx, camy)
            rect = pygame.Rect(0, 0, self.w, self.h)
            rect.midbottom = (int(sx), int(sy))
            if self.sprite:
                tint = pygame.Surface(self.sprite.get_size(), pygame.SRCALPHA)
                tint.fill((*self.color, alpha))
                mask = game._sprite_alpha_mask(self.sprite)
                tint.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                screen.blit(tint, self.sprite.get_rect(midbottom=rect.midbottom))
            else:
                s = pygame.Surface(rect.size, pygame.SRCALPHA)
                s.fill((*self.color, alpha))
                screen.blit(s, rect.topleft)

        def draw(self, screen):
            pass

    class Enemy:

        def __init__(self, pos: Tuple[int, int], attack: int=game.ENEMY_ATTACK, speed: int=game.ENEMY_SPEED, ztype: str='basic', hp: Optional[int]=None):
            self.x = pos[0] * game.CELL_SIZE
            self.y = pos[1] * game.CELL_SIZE
            self._vx = 0.0
            self._vy = 0.0
            self.attack = attack
            self.speed = speed
            self.type = 'fast' if ztype == 'trailrunner' else ztype
            self.color = game.ENEMY_COLORS.get(self.type, (255, 60, 60))
            self.size_category = game.ENEMY_SIZE_NORMAL
            self.fuse = None
            self.suicide_armed = False
            self.buff_cd = 0.0 if ztype == 'buffer' else None
            self.shield_cd = 0.0 if ztype == 'shielder' else None
            self.shield_hp = 0
            self.shield_t = 0.0
            self.ranged_cd = 0.0 if ztype in ('ranged', 'spitter') else None
            self.buff_t = 0.0
            self.buff_atk_mult = 1.0
            self.buff_spd_add = 0
            self.coins_absorbed = 0
            self.z_level = 1
            self.xp = 0
            self.xp_to_next = game.ENEMY_XP_TO_LEVEL
            self.is_elite = False
            self.is_boss = False
            self.radius = game.ENEMY_RADIUS
            self._stuck_t = 0.0
            self._avoid_t = 0.0
            self._avoid_side = 1
            self._focus_block = None
            self._last_xy = (self.x, self.y)
            self._path = []
            self._path_step = 0
            self.spoils = 0
            self._gold_glow_t = 0.0
            self.dot_rounds_stacks = []
            self._dot_rounds_tick_t = float(game.DOT_ROUNDS_TICK_INTERVAL)
            self._dot_rounds_accum = 0.0
            self.speed = float(self.speed)
            self._can_split = self.type == 'splinter'
            self._split_done = False
            base_hp = 30 if hp is None else hp
            if ztype == 'fast':
                self.speed = max(int(self.speed + 1), int(self.speed * 1.5))
                base_hp = int(base_hp * 0.7)
            if self.type == 'strong':
                base_hp = int(base_hp * 1.35)
                self.attack = max(1, int(self.attack * 1.15))
            if ztype == 'tank':
                self.attack = int(self.attack * 0.6)
                base_hp = int(base_hp * 1.8)
            self.hp = max(1, base_hp)
            self.max_hp = self.hp
            self._hit_flash = 0.0
            self._flash_prev_hp = int(self.hp)
            base_size = int(game.CELL_SIZE * 0.6)
            if self.type == 'tank':
                base_size = int(game.CELL_SIZE * game.TANK_SIZE_MULT)
                self._size_override = base_size
            elif self.type == 'strong':
                base_size = int(game.CELL_SIZE * game.STRONG_SIZE_MULT)
                self._size_override = base_size
            elif self.type == 'shielder':
                base_size = int(game.CELL_SIZE * game.SHIELDER_SIZE_MULT)
                self._size_override = base_size
            self.size = base_size
            self.rect = pygame.Rect(self.x, self.y + game.INFO_BAR_HEIGHT, self.size, self.size)
            self.radius = int(self.size * 0.5)
            self._base_size = int(self.size)
            game.set_enemy_size_category(self)
            self._foot_prev = (self.rect.centerx, self.rect.bottom)
            self._foot_curr = (self.rect.centerx, self.rect.bottom)
            self.spawn_delay = 0.6
            self._enrage_cd_mult = 1.0
            self._ground_spike_slow_t = 0.0
            self._paint_contact_mult = 1.0
            self.enemy_trace_timer = 0.0
            self.last_paint_pos = None
            self._hell_paint_t = 0.0
            self._hell_paint_pos = None

        def draw(self, screen):
            color = getattr(self, '_current_color', self.color)
            pygame.draw.rect(screen, color, self.rect)
            self._spawn_elapsed = 0.0

        @property
        def pos(self):
            return (int((self.x + self.size // 2) // game.CELL_SIZE), int((self.y + self.size // 2) // game.CELL_SIZE))

        def gain_xp(self, amount: int):
            self.xp += int(max(0, amount))
            while self.xp >= self.xp_to_next:
                self.xp -= self.xp_to_next
                self.z_level += 1
                self.xp_to_next = int(self.xp_to_next * 1.25 + 0.5)
                self.attack = int(self.attack * 1.08 + 1)
                self.max_hp = int(self.max_hp * 1.1 + 1)
                self.hp = min(self.max_hp, self.hp + 2)
            if not getattr(self, 'is_boss', False):
                base_override = getattr(self, '_size_override', None)
                if base_override is not None:
                    base = int(base_override)
                elif getattr(self, 'type', '') == 'ravager':
                    base = int(game.CELL_SIZE * game.RAVAGER_SIZE_MULT)
                else:
                    base = int(game.CELL_SIZE * 0.6)
                new_size = base
                if new_size != self.size:
                    cx, cy = self.rect.center
                    self.size = new_size
                    self.rect = pygame.Rect(0, 0, self.size, self.size)
                    self.rect.center = (cx, cy)
                    self.x = float(self.rect.x)
                    self.y = float(self.rect.y - game.INFO_BAR_HEIGHT)
                    self._foot_prev = (self.rect.centerx, self.rect.bottom)
                    self._foot_curr = (self.rect.centerx, self.rect.bottom)
                    game.apply_coin_absorb_scale(self)
                    game.set_enemy_size_category(self)

        def add_spoils(self, n: int):
            """僵尸拾取金币后的即时强化。"""
            n = int(max(0, n))
            if n <= 0:
                return
            self.coins_absorbed = int(getattr(self, 'coins_absorbed', 0)) + n
            for _ in range(n):
                self.spoils += 1
                self.max_hp += game.Z_SPOIL_HP_PER
                self.hp = min(self.max_hp, self.hp + game.Z_SPOIL_HP_PER)
                if self.spoils % game.Z_SPOIL_ATK_STEP == 0:
                    self.attack += 1
                if self.spoils % game.Z_SPOIL_SPD_STEP == 0:
                    self.speed = min(game.Z_SPOIL_SPD_CAP, float(self.speed) + float(game.Z_SPOIL_SPD_ADD))
            game.apply_coin_absorb_scale(self)
            self._gold_glow_t = float(game.Z_GLOW_TIME)

        @staticmethod
        def iso_chase_step(from_xy, to_xy, speed):
            fx, fy = from_xy
            tx, ty = to_xy
            vx, vy = (tx - fx, ty - fy)
            L = (vx * vx + vy * vy) ** 0.5 or 1.0
            ux, uy = (vx / L, vy / L)
            return game.iso_equalized_step(ux, uy, speed)

        @staticmethod
        def feet_xy(entity):
            return (entity.x + entity.size * 0.5, entity.y + entity.size)

        @staticmethod
        def first_obstacle_on_grid_line(a_cell, b_cell, obstacles_dict):
            x0, y0 = a_cell
            x1, y1 = b_cell
            dx = abs(x1 - x0)
            sx = 1 if x0 < x1 else -1
            dy = -abs(y1 - y0)
            sy = 1 if y0 < y1 else -1
            err = dx + dy
            while True:
                ob = obstacles_dict.get((x0, y0))
                if ob:
                    return ob
                if x0 == x1 and y0 == y1:
                    break
                e2 = 2 * err
                if e2 >= dy:
                    err += dy
                    x0 += sx
                if e2 <= dx:
                    err += dx
                    y0 += sy
            return None

        def _choose_bypass_cell(self, ob_cell, player_cell, obstacles_dict):
            """Pick a simple side cell next to the blocking obstacle to go around it."""
            ox, oy = ob_cell
            px, py = player_cell
            if abs(px - ox) >= abs(py - oy):
                primary = [(ox, oy - 1), (ox, oy + 1)]
            else:
                primary = [(ox - 1, oy), (ox + 1, oy)]

            def free(c):
                x, y = c
                return 0 <= x < game.GRID_SIZE and 0 <= y < game.GRID_SIZE and (c not in obstacles_dict)
            cands = [c for c in primary if free(c)]
            if not cands:
                diag = [(ox + 1, oy + 1), (ox + 1, oy - 1), (ox - 1, oy + 1), (ox - 1, oy - 1)]

                def diag_valid(c):
                    cx, cy = c
                    side1 = (ox, cy) in obstacles_dict
                    side2 = (cx, oy) in obstacles_dict
                    return free(c) and (not (side1 and side2))
                cands = [c for c in diag if free(c)]
            if not cands:
                return None
            return min(cands, key=lambda c: (c[0] - px) ** 2 + (c[1] - py) ** 2)

        def move_and_attack(self, player, obstacles, game_state, attack_interval=0.5, dt=1 / 60):
            self._foot_prev = getattr(self, '_foot_curr', (self.rect.centerx, self.rect.bottom))
            frame_scale = dt * 60.0
            base_attack = self.attack
            if getattr(game_state, 'biome_active', None) == 'Scorched Hell':
                base_attack = int(base_attack * (1.5 if getattr(self, 'is_boss', False) else 2.0))
            base_speed = float(self.speed)
            if getattr(self, 'buff_t', 0.0) > 0.0:
                base_attack = int(base_attack * getattr(self, 'buff_atk_mult', 1.0))
                base_speed = float(base_speed) + float(getattr(self, 'buff_spd_add', 0))
                self.buff_t = max(0.0, self.buff_t - dt)
            paint_intensity = 0.0
            if game_state is not None and hasattr(game_state, 'paint_intensity_at_world'):
                paint_intensity = game_state.paint_intensity_at_world(self.rect.centerx, self.rect.centery, owner=2)
            self._paint_contact_mult = 1.0 + game.ENEMY_PAINT_DAMAGE_BONUS * paint_intensity
            base_speed *= 1.0 + game.ENEMY_PAINT_SPEED_BONUS * paint_intensity
            base_speed *= float(getattr(self, '_hurricane_slow_mult', 1.0))
            spike_slow_t = float(getattr(self, '_ground_spike_slow_t', 0.0))
            if spike_slow_t > 0.0:
                spike_slow_t = max(0.0, spike_slow_t - dt)
                self._ground_spike_slow_t = spike_slow_t
                base_speed *= game.GROUND_SPIKES_SLOW_MULT
            speed = float(min(game.Z_SPOIL_SPD_CAP, max(0.5, base_speed)))
            is_bandit = getattr(self, 'type', '') == 'bandit'
            bandit_break_t = 0.0
            bandit_wind_trapped = False
            if is_bandit:
                bandit_break_t = max(0.0, float(getattr(self, 'bandit_break_t', 0.0)) - dt)
                self.bandit_break_t = bandit_break_t
                bandit_wind_trapped = bool(getattr(self, '_wind_trapped', False))
            bandit_prev_pos = getattr(self, '_bandit_last_pos', (self.x, self.y))
            if not hasattr(self, 'attack_timer'):
                self.attack_timer = 0.0
            self.attack_timer += dt
            self._block_contact_cd = max(0.0, float(getattr(self, '_block_contact_cd', 0.0)) - dt)
            self._bypass_t = max(0.0, getattr(self, '_bypass_t', 0.0) - dt)
            self._hit_ob = None
            if getattr(self, '_focus_block', None):
                gp = getattr(self._focus_block, 'grid_pos', None)
                if gp is not None and gp not in game_state.obstacles:
                    self._focus_block = None
            if is_bandit:
                self.mode = getattr(self, 'mode', 'FLEE')
                self.last_collision_tile = getattr(self, 'last_collision_tile', None)
                self.frames_on_same_tile = int(getattr(self, 'frames_on_same_tile', 0))
                self.stuck_origin_pos = tuple(getattr(self, 'stuck_origin_pos', (self.x, self.y)))
                esc_dir = getattr(self, 'escape_dir', (0.0, 0.0))
                if not (isinstance(esc_dir, (tuple, list)) and len(esc_dir) == 2):
                    esc_dir = (0.0, 0.0)
                self.escape_dir = esc_dir
                self.escape_timer = float(getattr(self, 'escape_timer', 0.0))
            if is_bandit and getattr(self, 'bandit_triggered', False):
                self._focus_block = None
                self._bypass_t = 0.0
                self._bypass_cell = None
            zx, zy = game.Enemy.feet_xy(self)
            px, py = (player.rect.centerx, player.rect.centery)
            player_move_dx, player_move_dy = getattr(player, '_last_move_vec', (0.0, 0.0))
            target_cx, target_cy = (px, py)
            dxp = px - zx
            dyp = py - zy
            dist2_to_player = dxp * dxp + dyp * dyp
            if is_bandit and dist2_to_player <= game.BANDIT_FLEE_RADIUS * game.BANDIT_FLEE_RADIUS:
                if not getattr(self, 'bandit_triggered', False):
                    self.bandit_triggered = True
            bandit_flee = is_bandit and getattr(self, 'bandit_triggered', False)
            if bandit_flee:
                speed *= game.BANDIT_FLEE_SPEED_MULT
                if bandit_break_t > 0.0:
                    speed *= game.BANDIT_BREAK_SLOW_MULT
                pcx = int(player.rect.centerx // game.CELL_SIZE)
                pcy = int((player.rect.centery - game.INFO_BAR_HEIGHT) // game.CELL_SIZE)
                corners = [(0, 0), (0, game.GRID_SIZE - 1), (game.GRID_SIZE - 1, 0), (game.GRID_SIZE - 1, game.GRID_SIZE - 1)]
                tx, ty = max(corners, key=lambda c: (c[0] - pcx) ** 2 + (c[1] - pcy) ** 2)
                target_cx = tx * game.CELL_SIZE + game.CELL_SIZE * 0.5
                target_cy = ty * game.CELL_SIZE + game.CELL_SIZE * 0.5 + game.INFO_BAR_HEIGHT
                self._ff_commit = None
                self._ff_commit_t = 0.0
            speed_step = speed * frame_scale
            if getattr(self, 'is_boss', False) and getattr(self, 'twin_id', None) is not None:
                cx0 = self.x + self.size * 0.5
                cy0 = self.y + self.size * 0.5 + game.INFO_BAR_HEIGHT
                dxp, dyp = (target_cx - cx0, target_cy - cy0)
                mag = (dxp * dxp + dyp * dyp) ** 0.5 or 1.0
                nx, ny = (dxp / mag, dyp / mag)
                px, py = (-ny, nx)
                slot = float(getattr(self, 'twin_slot', +1))
                lane_offset = 0.45 * game.CELL_SIZE * slot
                target_cx += px * lane_offset
                target_cy += py * lane_offset
                partner = None
                ref = getattr(self, '_twin_partner_ref', None)
                if callable(ref):
                    partner = ref()
                if partner and getattr(partner, 'hp', 1) > 0:
                    pcx, pcy = (partner.rect.centerx, partner.rect.centery)
                    ddx, ddy = (cx0 - pcx, cy0 - pcy)
                    d2 = ddx * ddx + ddy * ddy
                    too_close = (1.2 * game.CELL_SIZE) ** 2
                    if d2 < too_close:
                        k = (too_close - d2) / too_close
                        target_cx += ddx * 0.35 * k
                        target_cy += ddy * 0.35 * k
            if getattr(self, '_hit_ob', None):
                if getattr(self, 'can_crush_all_blocks', False) or getattr(self._hit_ob, 'type', '') == 'Destructible':
                    self._focus_block = self._hit_ob
            if not self._focus_block:
                gz = (int((self.x + self.size * 0.5) // game.CELL_SIZE), int((self.y + self.size * 0.5) // game.CELL_SIZE))
                if bandit_flee:
                    gp = (int(target_cx // game.CELL_SIZE), int((target_cy - game.INFO_BAR_HEIGHT) // game.CELL_SIZE))
                else:
                    gp = (int(player.rect.centerx // game.CELL_SIZE), int((player.rect.centery - game.INFO_BAR_HEIGHT) // game.CELL_SIZE))
                ob = self.first_obstacle_on_grid_line(gz, gp, game_state.obstacles)
                self._focus_block = None
                if ob:
                    if bandit_flee:
                        ox, oy = ob.grid_pos
                        free = []
                        for nx, ny in ((ox + 1, oy), (ox - 1, oy), (ox, oy + 1), (ox, oy - 1)):
                            if 0 <= nx < game.GRID_SIZE and 0 <= ny < game.GRID_SIZE and ((nx, ny) not in game_state.obstacles):
                                free.append((nx, ny))
                        if free:
                            bx, by = max(free, key=lambda c: (c[0] - pcx) ** 2 + (c[1] - pcy) ** 2)
                            self._bypass_cell = (bx, by)
                            self._bypass_t = 0.6
                    elif getattr(ob, 'type', '') == 'Destructible':
                        self._focus_block = ob
                    elif not getattr(self, 'is_boss', False):
                        bypass = self._choose_bypass_cell(ob.grid_pos, gp, game_state.obstacles)
                        if bypass:
                            self._bypass_cell = bypass
                            self._bypass_t = 0.5
            if self._focus_block and (not bandit_flee):
                target_cx, target_cy = (self._focus_block.rect.centerx, self._focus_block.rect.centery)
            fd = None
            escape_override = False
            if bandit_flee and getattr(self, 'mode', 'FLEE') == 'ESCAPE_CORNER':
                ex, ey = self.escape_dir
                mag = (ex * ex + ey * ey) ** 0.5
                if mag < 0.0001:
                    ex, ey = (-dxp, -dyp)
                    mag = (ex * ex + ey * ey) ** 0.5 or 1.0
                ux, uy = (ex / mag, ey / mag)
                vx_des, vy_des = game.chase_step(ux, uy, speed_step)
                tau = 0.12
                alpha = 1.0 - pow(0.001, dt / tau)
                self._vx = (1.0 - alpha) * getattr(self, '_vx', 0.0) + alpha * vx_des
                self._vy = (1.0 - alpha) * getattr(self, '_vy', 0.0) + alpha * vy_des
                vx, vy = (self._vx, self._vy)
                dx, dy = (vx, vy)
                oldx, oldy = (self.x, self.y)
                escape_override = True
                self.escape_timer = max(0.0, float(getattr(self, 'escape_timer', 0.0)) - dt)
                if self.escape_timer <= 0.0:
                    self.mode = 'FLEE'
                    self.last_collision_tile = None
                    self.frames_on_same_tile = 0
            if not escape_override:
                gx = int((self.x + self.size * 0.5) // game.CELL_SIZE)
                gy = int((self.y + self.size) // game.CELL_SIZE)
                if self._path_step < len(self._path):
                    nx, ny = self._path[self._path_step]
                    if gx == nx and gy == ny:
                        self._path_step += 1
                        if self._path_step < len(self._path):
                            nx, ny = self._path[self._path_step]
                    if self._path_step < len(self._path):
                        target_cx = nx * game.CELL_SIZE + game.CELL_SIZE * 0.5
                        target_cy = ny * game.CELL_SIZE + game.CELL_SIZE
                cx0, cy0 = (self.rect.centerx, self.rect.centery)
                gx = int(cx0 // game.CELL_SIZE)
                gy = int((cy0 - game.INFO_BAR_HEIGHT) // game.CELL_SIZE)
                ff = getattr(game_state, 'ff_next', None)
                fd = getattr(game_state, 'ff_dist', None)
                step = ff[gx][gy] if ff is not None and 0 <= gx < game.GRID_SIZE and (0 <= gy < game.GRID_SIZE) else None
                boss_simple = getattr(self, 'is_boss', False) or getattr(self, 'type', '') in ('boss_mist', 'boss_mem')
                if boss_simple:
                    step = None
                    self._ff_commit = None
                    self._ff_commit_t = 0.0
                    self._avoid_t = 0.0
                bandit_escape_step = None
                if bandit_flee and fd is not None:
                    best = None
                    bestd = -1
                    for nx in (gx - 1, gx, gx + 1):
                        for ny in (gy - 1, gy + 1):
                            if nx == gx and ny == gy:
                                continue
                            if not (0 <= nx < game.GRID_SIZE and 0 <= ny < game.GRID_SIZE):
                                continue
                            if (nx, ny) in game_state.obstacles:
                                continue
                            if nx != gx and ny != gy:
                                if (gx, ny) in game_state.obstacles or (nx, gy) in game_state.obstacles:
                                    continue
                            d = fd[ny][nx]
                            if d > bestd and (not game.Enemy.first_obstacle_on_grid_line((gx, gy), (nx, ny), game_state.obstacles)):
                                bestd = d
                                best = (nx, ny)
                    bandit_escape_step = best
                    if bandit_escape_step is not None:
                        step = bandit_escape_step
                if step is None and fd is not None and (not boss_simple):
                    best = None
                    bestd = 10 ** 9
                    for nx in (gx - 1, gx, gx + 1):
                        for ny in (gy - 1, gy + 1):
                            if nx == gx and ny == gy:
                                continue
                            if not (0 <= nx < game.GRID_SIZE and 0 <= ny < game.GRID_SIZE):
                                continue
                            if (nx, ny) in game_state.obstacles:
                                continue
                            if nx != gx and ny != gy:
                                if (gx, ny) in game_state.obstacles or (nx, gy) in game_state.obstacles:
                                    continue
                            d = fd[ny][nx]
                            if d < bestd:
                                if nx != gx and ny != gy:
                                    if (gx, ny) in game_state.obstacles and (nx, gy) in game_state.obstacles:
                                        continue
                                if not game.Enemy.first_obstacle_on_grid_line((gx, gy), (nx, ny), game_state.obstacles):
                                    bestd = d
                                    best = (nx, ny)
                    step = best
                    if step is not None:
                        prev = getattr(self, '_ff_commit', None)
                        if not (isinstance(prev, (tuple, list)) and len(prev) == 2):
                            prev = None
                        if prev is None:
                            self._ff_commit = step
                            self._ff_commit_t = 0.25
                        elif step != prev:
                            pcx = prev[0] * game.CELL_SIZE + game.CELL_SIZE * 0.5
                            pcy = prev[1] * game.CELL_SIZE + game.CELL_SIZE * 0.5 + game.INFO_BAR_HEIGHT
                            d2 = (pcx - cx0) ** 2 + (pcy - cy0) ** 2
                            if d2 <= (game.CELL_SIZE * 0.35) ** 2 or getattr(self, '_ff_commit_t', 0.0) <= 0.0:
                                self._ff_commit = step
                                self._ff_commit_t = 0.25
                            else:
                                step = prev
                        else:
                            self._ff_commit_t = max(0.0, getattr(self, '_ff_commit_t', 0.0) - dt)
                if getattr(self, '_bypass_t', 0.0) > 0.0 and getattr(self, '_bypass_cell', None) is not None:
                    if (gx, gy) == self._bypass_cell or not self.first_obstacle_on_grid_line((gx, gy), gp, game_state.obstacles):
                        self._bypass_t = 0.0
                        self._bypass_cell = None
                    else:
                        step = self._bypass_cell
                if step is not None:
                    nx, ny = step
                    next_cx = nx * game.CELL_SIZE + game.CELL_SIZE * 0.5
                    next_cy = ny * game.CELL_SIZE + game.CELL_SIZE * 0.5 + game.INFO_BAR_HEIGHT
                    dx = next_cx - cx0
                    dy = next_cy - cy0
                    L = (dx * dx + dy * dy) ** 0.5 or 1.0
                    ux, uy = (dx / L, dy / L)
                    vx_des, vy_des = game.chase_step(ux, uy, speed_step)
                    tau = 0.12
                    alpha = 1.0 - pow(0.001, dt / tau)
                    self._vx = (1.0 - alpha) * getattr(self, '_vx', 0.0) + alpha * vx_des
                    self._vy = (1.0 - alpha) * getattr(self, '_vy', 0.0) + alpha * vy_des
                    vx, vy = (self._vx, self._vy)
                    dx, dy = (vx, vy)
                    oldx, oldy = (self.x, self.y)
                else:
                    dx = target_cx - cx0
                    dy = target_cy - cy0
                    L = (dx * dx + dy * dy) ** 0.5 or 1.0
                    ux, uy = (dx / L, dy / L)
                    if bandit_flee:
                        flee_x, flee_y = (-dxp, -dyp)
                        if abs(flee_x) < 0.0001 and abs(flee_y) < 0.0001:
                            flee_x, flee_y = (-dy, dx)
                        mag = (flee_x * flee_x + flee_y * flee_y) ** 0.5 or 1.0
                        ux, uy = (flee_x / mag, flee_y / mag)
                    vx_des, vy_des = game.chase_step(ux, uy, speed_step)
                    tau = 0.12
                    alpha = 1.0 - pow(0.001, dt / tau)
                    self._vx = (1.0 - alpha) * getattr(self, '_vx', 0.0) + alpha * vx_des
                    self._vy = (1.0 - alpha) * getattr(self, '_vy', 0.0) + alpha * vy_des
                    vx, vy = (self._vx, self._vy)
                    dx, dy = (vx, vy)
                    oldx, oldy = (self.x, self.y)
            if not getattr(self, 'is_boss', False):
                if abs(dx) < 0.001 and abs(dy) < 0.001:
                    slot = float(getattr(self, 'twin_slot', 1.0))
                    dx, dy = (0.0, slot * max(0.6, min(speed, 1.2)) * frame_scale)
            if self._avoid_t > 0.0:
                if self._avoid_side > 0:
                    ax, ay = (-dy, dx)
                else:
                    ax, ay = (dy, -dx)
                dx, dy = (ax, ay)
                self._avoid_t = max(0.0, self._avoid_t - dt)
            if not getattr(self, 'is_boss', False) and self._avoid_t > 0.0:
                if self._avoid_side > 0:
                    ax, ay = (-dy, dx)
                else:
                    ax, ay = (dy, -dx)
                dx, dy = (ax, ay)
                self._avoid_t = max(0.0, self._avoid_t - dt)
            if getattr(self, 'no_clip_t', 0.0) > 0.0:
                self.no_clip_t = max(0.0, self.no_clip_t - dt)
                self.x += dx
                self.y += dy
                self.rect.x = int(self.x)
                self.rect.y = int(self.y + game.INFO_BAR_HEIGHT)
                if abs(dx) < 0.5 and abs(dy) < 0.5:
                    self.x += 0.8 * (1 if self.rect.centerx < player.rect.centerx else -1)
                goto_post_move = True
            else:
                goto_post_move = False
            if not goto_post_move:
                game.collide_and_slide_circle(self, obstacles, dx, dy)
            if bandit_flee:
                moved_x = self.x - oldx
                moved_y = self.y - oldy
                if abs(moved_x) < 0.25 and abs(moved_y) < 0.25:
                    self._avoid_side = 1 if dxp >= 0 else -1
                    self._avoid_t = max(self._avoid_t, 0.25)
                ob = getattr(self, '_hit_ob', None)
                if ob and getattr(ob, 'type', '') == 'Destructible':
                    gp = getattr(ob, 'grid_pos', None)
                    if gp in game_state.obstacles:
                        del game_state.obstacles[gp]
                    if getattr(ob, 'health', None) is not None:
                        ob.health = 0
                    cx2, cy2 = (ob.rect.centerx, ob.rect.centery)
                    if random.random() < game.SPOILS_BLOCK_DROP_CHANCE:
                        game_state.spawn_spoils(cx2, cy2, 1)
                    self.gain_xp(game.XP_ENEMY_BLOCK)
                    if random.random() < game.HEAL_DROP_CHANCE_BLOCK:
                        game_state.spawn_heal(cx2, cy2, game.HEAL_POTION_AMOUNT)
                    self.bandit_break_t = max(float(getattr(self, 'bandit_break_t', 0.0)), game.BANDIT_BREAK_SLOW_TIME)
                    self._focus_block = None
            if is_bandit:
                moved_len = ((self.x - bandit_prev_pos[0]) ** 2 + (self.y - bandit_prev_pos[1]) ** 2) ** 0.5
                if moved_len < 1.0:
                    self._bandit_stuck_t = float(getattr(self, '_bandit_stuck_t', 0.0)) + dt
                else:
                    self._bandit_stuck_t = 0.0
                self._bandit_last_pos = (self.x, self.y)
                idle_pos = getattr(self, '_bandit_idle_pos', (self.x, self.y))
                idle_t = float(getattr(self, '_bandit_idle_t', 0.0)) + dt
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
                if bandit_flee and getattr(self, '_bandit_stuck_t', 0.0) > 0.6 and (fd is not None):
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
            if getattr(self, 'can_crush_all_blocks', False) and getattr(self, '_crush_queue', None):
                for ob in list(self._crush_queue):
                    gp = getattr(ob, 'grid_pos', None)
                    if gp in game_state.obstacles:
                        del game_state.obstacles[gp]
                self._crush_queue.clear()
                self._focus_block = None
                try:
                    r = int(getattr(self, 'radius', max(8, game.CELL_SIZE // 3)))
                    cx = self.x + self.size * 0.5
                    cy = self.y + self.size * 0.5 + game.INFO_BAR_HEIGHT
                    bb = pygame.Rect(int(cx - r), int(cy - r), int(2 * r), int(2 * r))
                    crushed_any = False
                    for gp, ob in list(game_state.obstacles.items()):
                        if ob.rect.colliderect(bb):
                            del game_state.obstacles[gp]
                            crushed_any = True
                            if getattr(ob, 'type', '') == 'Destructible':
                                if random.random() < game.SPOILS_BLOCK_DROP_CHANCE:
                                    game_state.spawn_spoils(ob.rect.centerx, ob.rect.centery, 1)
                                self.gain_xp(game.XP_ENEMY_BLOCK)
                        if random.random() < game.HEAL_DROP_CHANCE_BLOCK:
                            game_state.spawn_heal(ob.rect.centerx, ob.rect.centery, game.HEAL_POTION_AMOUNT)
                    if crushed_any:
                        self._focus_block = None
                        if hasattr(self, '_stuck_t'):
                            self._stuck_t = 0.0
                        self.no_clip_t = max(getattr(self, 'no_clip_t', 0.0), 0.1)
                except Exception:
                    pass
            if bandit_flee:
                MIN_FRAMES_STUCK = 4
                STUCK_MOVE_THRESHOLD = game.CELL_SIZE * 0.3
                ESCAPE_DURATION = 0.55
                ESCAPE_TEST_STEP = game.CELL_SIZE * 0.6
                ob = getattr(self, '_hit_ob', None)
                collided_tile = None
                if ob and (not getattr(ob, 'nonblocking', False)):
                    gp = getattr(ob, 'grid_pos', None)
                    if gp is not None:
                        collided_tile = tuple(gp)
                    else:
                        collided_tile = (int(ob.rect.centerx // game.CELL_SIZE), int((ob.rect.centery - game.INFO_BAR_HEIGHT) // game.CELL_SIZE))
                bandit_pos = (self.rect.centerx, self.rect.centery)
                if collided_tile is not None:
                    if collided_tile != getattr(self, 'last_collision_tile', None):
                        self.last_collision_tile = collided_tile
                        self.frames_on_same_tile = 1
                        self.stuck_origin_pos = (self.x, self.y)
                    else:
                        self.frames_on_same_tile = int(getattr(self, 'frames_on_same_tile', 0)) + 1
                    disp = ((self.x - self.stuck_origin_pos[0]) ** 2 + (self.y - self.stuck_origin_pos[1]) ** 2) ** 0.5
                    if self.frames_on_same_tile >= MIN_FRAMES_STUCK and disp <= STUCK_MOVE_THRESHOLD and (getattr(self, 'mode', 'FLEE') != 'ESCAPE_CORNER'):
                        bx, by = bandit_pos
                        flee_dx, flee_dy = (bx - px, by - py)
                        mag = (flee_dx * flee_dx + flee_dy * flee_dy) ** 0.5 or 1.0
                        base_dir = (flee_dx / mag, flee_dy / mag)
                        left_dir = (-base_dir[1], base_dir[0])
                        right_dir = (base_dir[1], -base_dir[0])
                        ox, oy = collided_tile
                        ob_cx = ox * game.CELL_SIZE + game.CELL_SIZE * 0.5
                        ob_cy = oy * game.CELL_SIZE + game.CELL_SIZE * 0.5 + game.INFO_BAR_HEIGHT
                        away_dx, away_dy = (bx - ob_cx, by - ob_cy)
                        away_mag = (away_dx * away_dx + away_dy * away_dy) ** 0.5 or 1.0
                        bounce_dir = (away_dx / away_mag, away_dy / away_mag)
                        candidates = [base_dir, left_dir, right_dir, bounce_dir]

                        def _dir_clear(vec):
                            tx = bx + vec[0] * ESCAPE_TEST_STEP
                            ty = by + vec[1] * ESCAPE_TEST_STEP
                            cell = (int(tx // game.CELL_SIZE), int((ty - game.INFO_BAR_HEIGHT) // game.CELL_SIZE))
                            if not (0 <= cell[0] < game.GRID_SIZE and 0 <= cell[1] < game.GRID_SIZE):
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
                            if _dir_clear(left_dir):
                                best_dir = left_dir
                            elif _dir_clear(right_dir):
                                best_dir = right_dir
                            else:
                                best_dir = bounce_dir
                        self.escape_dir = best_dir
                        self.escape_timer = ESCAPE_DURATION
                        self.mode = 'ESCAPE_CORNER'
                else:
                    self.last_collision_tile = None
                    self.frames_on_same_tile = 0
            blocked = self._hit_ob is not None
            moved2 = (self.x - oldx) ** 2 + (self.y - oldy) ** 2
            min_move = 0.15 * speed_step
            min_move2 = max(0.04 * frame_scale * frame_scale, min_move * min_move)
            dist2 = (self.rect.centerx - int(target_cx)) ** 2 + (self.rect.centery - int(target_cy)) ** 2
            prev_d2 = getattr(self, '_prev_d2', float('inf'))
            no_progress = dist2 > prev_d2 - 1.0
            self._prev_d2 = dist2
            if blocked and moved2 < min_move2 or (no_progress and moved2 < min_move2):
                self._stuck_t = getattr(self, '_stuck_t', 0.0) + dt
            else:
                self._stuck_t = 0.0
            if self._stuck_t > 0.25 and self._avoid_t <= 0.0 and (blocked or no_progress):
                self._avoid_t = random.uniform(0.25, 0.45)
                self._avoid_side = random.choice((-1, 1))
            if self._stuck_t > 0.7 and self._avoid_t <= 0.0 and (self._path_step >= len(self._path)):
                if game.IS_WEB and not getattr(game, "WEB_ENABLE_ASTAR_RECOVERY", False):
                    self._avoid_t = max(float(getattr(self, '_avoid_t', 0.0)), random.uniform(0.45, 0.70))
                    self._avoid_side = random.choice((-1, 1))
                    self._path = []
                    self._path_step = 0
                else:
                    start = (gx, gy)
                    if self._focus_block:
                        gp = getattr(self._focus_block, 'grid_pos', None)
                        if gp is None:
                            cx2, cy2 = (self._focus_block.rect.centerx, self._focus_block.rect.centery)
                            goal = (int(cx2 // game.CELL_SIZE), int((cy2 - game.INFO_BAR_HEIGHT) // game.CELL_SIZE))
                        else:
                            goal = gp
                    else:
                        goal = (int(player.rect.centerx // game.CELL_SIZE), int((player.rect.centery - game.INFO_BAR_HEIGHT) // game.CELL_SIZE))
                    graph = game.build_graph(game.GRID_SIZE, game_state.obstacles)
                    came, _ = game.a_star_search(graph, start, goal, game_state.obstacles)
                    path = game.reconstruct_path(came, start, goal)
                    if len(path) > 1:
                        self._path = path[1:7]
                        self._path_step = 0
                self._stuck_t = 0.0
            if self._focus_block and (self._focus_block.health is not None and self._focus_block.health <= 0):
                self._focus_block = None
            if self._path_step >= len(self._path):
                self._path = []
                self._path_step = 0
            self.rect.x = int(self.x)
            self.rect.y = int(self.y) + game.INFO_BAR_HEIGHT
            self._foot_curr = (self.rect.centerx, self.rect.bottom)
            if game_state is not None and getattr(game_state, 'biome_active', None) == 'Scorched Hell':
                if getattr(self, 'hp', 0) > 0:
                    f0 = getattr(self, '_foot_prev', (self.rect.centerx, self.rect.bottom))
                    f1 = getattr(self, '_foot_curr', (self.rect.centerx, self.rect.bottom))
                    moved = math.hypot(f1[0] - f0[0], f1[1] - f0[1])
                    if moved > 0.05:
                        hell_t = float(getattr(self, '_hell_paint_t', 0.0)) + float(dt)
                        last_pos = getattr(self, '_hell_paint_pos', None)
                        if not (isinstance(last_pos, (tuple, list)) and len(last_pos) == 2):
                            last_pos = (f1[0], f1[1])
                        dx = f1[0] - float(last_pos[0])
                        dy = f1[1] - float(last_pos[1])
                        dist = math.hypot(dx, dy)
                        if hell_t >= game.HELL_ENEMY_PAINT_SPAWN_INTERVAL or dist >= game.HELL_ENEMY_PAINT_SPAWN_DIST:
                            paint_r = game.enemy_paint_radius_for(self)
                            game_state.apply_enemy_paint(f1[0], f1[1], paint_r, paint_type='hell_trail', paint_color=getattr(self, 'color', None))
                            hell_t = 0.0
                            last_pos = (f1[0], f1[1])
                        self._hell_paint_t = hell_t
                        self._hell_paint_pos = last_pos
            if not getattr(self, 'is_boss', False) and self._block_contact_cd <= 0.0:
                ob_contact = getattr(self, '_hit_ob', None)
                if ob_contact and getattr(ob_contact, 'type', '') == 'Destructible' and (getattr(ob_contact, 'health', None) is not None):
                    mult = getattr(game_state, 'biome_enemy_contact_mult', 1.0)
                    block_dmg = int(round(game.ENEMY_CONTACT_DAMAGE * max(1.0, mult)))
                    ob_contact.health -= block_dmg
                    self._block_contact_cd = float(game.PLAYER_HIT_COOLDOWN)
                    if ob_contact.health <= 0:
                        gp = getattr(ob_contact, 'grid_pos', None)
                        if gp in game_state.obstacles:
                            del game_state.obstacles[gp]
                        cx2, cy2 = (ob_contact.rect.centerx, ob_contact.rect.centery)
                        if random.random() < game.SPOILS_BLOCK_DROP_CHANCE:
                            game_state.spawn_spoils(cx2, cy2, 1)
                        self.gain_xp(game.XP_ENEMY_BLOCK)
                        if random.random() < game.HEAL_DROP_CHANCE_BLOCK:
                            game_state.spawn_heal(cx2, cy2, game.HEAL_POTION_AMOUNT)
                        self._focus_block = None
            if self.attack_timer >= attack_interval:
                cx = self.x + self.size * 0.5
                cy = self.y + self.size * 0.5 + game.INFO_BAR_HEIGHT
                for ob in list(obstacles):
                    if ob.rect.inflate(self.radius * 2, self.radius * 2).collidepoint(cx, cy):
                        if getattr(self, 'can_crush_all_blocks', False):
                            gp = getattr(ob, 'grid_pos', None)
                            if gp in game_state.obstacles:
                                del game_state.obstacles[gp]
                            if getattr(ob, 'type', '') == 'Destructible':
                                cx2, cy2 = (ob.rect.centerx, ob.rect.centery)
                                if random.random() < game.SPOILS_BLOCK_DROP_CHANCE:
                                    game_state.spawn_spoils(cx2, cy2, 1)
                                self.gain_xp(game.XP_ENEMY_BLOCK)
                                if random.random() < game.HEAL_DROP_CHANCE_BLOCK:
                                    game_state.spawn_heal(cx2, cy2, game.HEAL_POTION_AMOUNT)
                            self.attack_timer = 0.0
                            self._focus_block = None
                        elif getattr(ob, 'type', '') == 'Destructible':
                            ob.health -= self.attack
                            self.attack_timer = 0.0
                            if ob.health <= 0:
                                gp = ob.grid_pos
                                if gp in game_state.obstacles:
                                    del game_state.obstacles[gp]
                                cx2, cy2 = (ob.rect.centerx, ob.rect.centery)
                                if random.random() < game.SPOILS_BLOCK_DROP_CHANCE:
                                    game_state.spawn_spoils(cx2, cy2, 1)
                                self.gain_xp(game.XP_ENEMY_BLOCK)
                                if random.random() < game.HEAL_DROP_CHANCE_BLOCK:
                                    game_state.spawn_heal(cx2, cy2, game.HEAL_POTION_AMOUNT)
                        break

        def update_special(self, dt: float, player: 'Player', enemies: List['Enemy'], enemy_shots: List['EnemyShot'], game_state: 'GameState'=None):
            cx, cy = (self.rect.centerx, self.rect.centery)
            px, py = (player.rect.centerx, player.rect.centery)
            if self._can_split and (not self._split_done) and (self.hp > 0) and (self.hp <= int(self.max_hp * 0.5)):
                self._split_done = True
                self._can_split = False
                game.spawn_splinter_children(self, enemies, game_state, level_idx=getattr(game_state, 'current_level', 0), wave_index=0)
                self.hp = 0
                return
            if self.type == 'ravager':
                cd_min, cd_max = game.RAVAGER_DASH_CD_RANGE
                if not hasattr(self, '_dash_state'):
                    self._dash_state = 'idle'
                    self._dash_cd = random.uniform(cd_min, cd_max)
                    self._dash_t = 0.0
                    self._dash_speed_hold = float(self.speed)
                    self._ghost_accum = 0.0
                if getattr(self, '_dash_state', '') != 'go' and getattr(self, 'can_crush_all_blocks', False):
                    self.can_crush_all_blocks = False
                self._dash_cd = max(0.0, (self._dash_cd or 0.0) - dt)
                if self._dash_state == 'idle' and self._dash_cd <= 0.0:
                    vx, vy = (px - cx, py - cy)
                    L = (vx * vx + vy * vy) ** 0.5 or 1.0
                    self._dash_dir = (vx / L, vy / L)
                    self._dash_state = 'wind'
                    self._dash_t = game.RAVAGER_DASH_WINDUP
                    self._dash_speed_hold = float(self.speed)
                    self._ghost_accum = 0.0
                    self.speed = max(0.2, self._dash_speed_hold * 0.35)
                    if game_state:
                        game_state.spawn_telegraph(cx, cy, r=int(getattr(self, 'radius', self.size * 0.5) * 0.9), life=self._dash_t, kind='ravager_dash', payload=None)
                elif self._dash_state == 'wind':
                    self._dash_t -= dt
                    self.speed = max(0.2, self._dash_speed_hold * 0.35)
                    if self._dash_t <= 0.0:
                        self._dash_state = 'go'
                        self._dash_t = game.RAVAGER_DASH_TIME
                        self.speed = self._dash_speed_hold
                        self.buff_spd_add = float(getattr(self, 'buff_spd_add', 0.0)) + float(self._dash_speed_hold) * (game.RAVAGER_DASH_SPEED_MULT - 1.0)
                        self.buff_t = max(getattr(self, 'buff_t', 0.0), self._dash_t)
                        self.no_clip_t = max(getattr(self, 'no_clip_t', 0.0), self._dash_t + 0.05)
                        self.can_crush_all_blocks = True
                        self._dash_cd = random.uniform(cd_min, cd_max)
                elif self._dash_state == 'go':
                    self._dash_t -= dt
                    self.can_crush_all_blocks = True
                    self.no_clip_t = max(getattr(self, 'no_clip_t', 0.0), 0.05)
                    self._ghost_accum += dt
                    f0 = getattr(self, '_foot_prev', (self.rect.centerx, self.rect.bottom))
                    f1 = getattr(self, '_foot_curr', (self.rect.centerx, self.rect.bottom))
                    n = int(self._ghost_accum // game.AFTERIMAGE_INTERVAL)
                    if n > 0:
                        self._ghost_accum -= n * game.AFTERIMAGE_INTERVAL
                        for i in range(n):
                            t = (i + 1) / (n + 1)
                            gx = f0[0] * (1 - t) + f1[0] * t
                            gy = f0[1] * (1 - t) + f1[1] * t
                            ghost_size = int(self.size * 2)
                            ghost_sprite = game._enemy_sprite('ravager', ghost_size)
                            game_state.ghosts.append(game.AfterImageGhost(gx, gy, ghost_size, ghost_size, game.ENEMY_COLORS.get('ravager', self.color), ttl=game.AFTERIMAGE_TTL, sprite=ghost_sprite))
                    if self._dash_t <= 0.0:
                        self._dash_state = 'idle'
                        self.can_crush_all_blocks = False
                else:
                    self.can_crush_all_blocks = False
            if getattr(self, 'is_boss', False) and getattr(self, 'hp', 0) <= 0:
                game.trigger_twin_enrage(self, enemies, game_state)
            if self.type in ('ranged', 'spitter'):
                self.ranged_cd = max(0.0, (self.ranged_cd or 0.0) - dt)
                if self.ranged_cd <= 0.0:
                    cx, cy = (self.rect.centerx, self.rect.centery)
                    px, py = (player.rect.centerx, player.rect.centery)
                    dx, dy = (px - cx, py - cy)
                    L = (dx * dx + dy * dy) ** 0.5 or 1.0
                    vx, vy = (dx / L * game.RANGED_PROJ_SPEED, dy / L * game.RANGED_PROJ_SPEED)
                    enemy_shots.append(game.EnemyShot(cx, cy, vx, vy, game.RANGED_PROJ_DAMAGE))
                    self.ranged_cd = game.RANGED_COOLDOWN
            if self.type in ('suicide', 'bomber'):
                cx, cy = (self.rect.centerx, self.rect.centery)
                pr = player.rect
                dx, dy = (pr.centerx - cx, pr.centery - cy)
                dist = (dx * dx + dy * dy) ** 0.5
                if not getattr(self, 'suicide_armed', False) and dist <= game.SUICIDE_ARM_DIST:
                    self.suicide_armed = True
                    self.fuse = float(game.SUICIDE_FUSE)
                if getattr(self, 'suicide_armed', False) and self.fuse is not None:
                    self.fuse -= dt
                    if self.fuse <= 0.0:
                        if dist <= game.SUICIDE_RADIUS and player.hit_cd <= 0.0:
                            game_state.damage_player(player, game.SUICIDE_DAMAGE)
                            player.hit_cd = float(game.PLAYER_HIT_COOLDOWN)
                        self.hp = 0
            if self.type == 'ravager':
                cd_min, cd_max = game.RAVAGER_DASH_CD_RANGE
                if not hasattr(self, '_dash_state'):
                    self._dash_state = 'idle'
                    self._dash_cd = random.uniform(cd_min, cd_max)
                    self._dash_t = 0.0
                    self._dash_speed_hold = float(self.speed)
                    self._ghost_accum = 0.0
                if getattr(self, '_dash_state', '') != 'go' and getattr(self, 'can_crush_all_blocks', False):
                    self.can_crush_all_blocks = False
                self._dash_cd = max(0.0, (self._dash_cd or 0.0) - dt)
                if self._dash_state == 'idle' and self._dash_cd <= 0.0:
                    vx, vy = (px - cx, py - cy)
                    L = (vx * vx + vy * vy) ** 0.5 or 1.0
                    self._dash_dir = (vx / L, vy / L)
                    self._dash_state = 'wind'
                    self._dash_t = game.RAVAGER_DASH_WINDUP
                    self._dash_speed_hold = float(self.speed)
                    self._ghost_accum = 0.0
                    self.speed = max(0.2, self._dash_speed_hold * 0.35)
                    if game_state:
                        game_state.spawn_telegraph(cx, cy, r=int(getattr(self, 'radius', self.size * 0.5) * 0.9), life=self._dash_t, kind='ravager_dash', payload=None)
                elif self._dash_state == 'wind':
                    self._dash_t -= dt
                    self.speed = max(0.2, self._dash_speed_hold * 0.35)
                    if self._dash_t <= 0.0:
                        self._dash_state = 'go'
                        self._dash_t = game.RAVAGER_DASH_TIME
                        self.speed = self._dash_speed_hold
                        self.buff_spd_add = float(getattr(self, 'buff_spd_add', 0.0)) + float(self._dash_speed_hold) * (game.RAVAGER_DASH_SPEED_MULT - 1.0)
                        self.buff_t = max(getattr(self, 'buff_t', 0.0), self._dash_t)
                        self.no_clip_t = max(getattr(self, 'no_clip_t', 0.0), self._dash_t + 0.05)
                        self.can_crush_all_blocks = True
                        self._dash_cd = random.uniform(cd_min, cd_max)
                elif self._dash_state == 'go':
                    self._dash_t -= dt
                    self.can_crush_all_blocks = True
                    self.no_clip_t = max(getattr(self, 'no_clip_t', 0.0), 0.05)
                    self._ghost_accum += dt
                    f0 = getattr(self, '_foot_prev', (self.rect.centerx, self.rect.bottom))
                    f1 = getattr(self, '_foot_curr', (self.rect.centerx, self.rect.bottom))
                    n = int(self._ghost_accum // game.AFTERIMAGE_INTERVAL)
                    if n > 0:
                        self._ghost_accum -= n * game.AFTERIMAGE_INTERVAL
                        for i in range(n):
                            t = (i + 1) / (n + 1)
                            gx = f0[0] * (1 - t) + f1[0] * t
                            gy = f0[1] * (1 - t) + f1[1] * t
                            game_state.ghosts.append(game.AfterImageGhost(gx, gy, self.size, self.size, game.ENEMY_COLORS.get('ravager', self.color), ttl=game.AFTERIMAGE_TTL))
                    if self._dash_t <= 0.0:
                        self._dash_state = 'idle'
                        self.can_crush_all_blocks = False
                else:
                    self.can_crush_all_blocks = False
            if getattr(self, 'is_boss', False) and getattr(self, 'hp', 0) <= 0:
                game.trigger_twin_enrage(self, enemies, game_state)
            if self.type == 'buffer':
                self.buff_cd = max(0.0, (self.buff_cd or 0.0) - dt)
                if self.buff_cd <= 0.0:
                    cx, cy = (self.rect.centerx, self.rect.centery)
                    for z in enemies:
                        zx, zy = (z.rect.centerx, z.rect.centery)
                        if (zx - cx) ** 2 + (zy - cy) ** 2 <= game.BUFF_RADIUS ** 2:
                            z.buff_t = game.BUFF_DURATION
                            z.buff_atk_mult = game.BUFF_ATK_MULT
                            z.buff_spd_add = game.BUFF_SPD_ADD
                    self.buff_cd = game.BUFF_COOLDOWN
            if self.type == 'shielder':
                self.shield_cd = max(0.0, (self.shield_cd or 0.0) - dt)
                if self.shield_hp > 0:
                    self.shield_t -= dt
                    if self.shield_t <= 0:
                        self.shield_hp = 0
                    if self.shield_cd <= 0.0:
                        cx, cy = (self.rect.centerx, self.rect.centery)
                        for z in enemies:
                            zx, zy = (z.rect.centerx, z.rect.centery)
                            if (zx - cx) ** 2 + (zy - cy) ** 2 <= game.SHIELD_RADIUS ** 2:
                                z.shield_hp = game.SHIELD_AMOUNT
                                z.shield_t = game.SHIELD_DURATION
                        self.shield_cd = game.SHIELD_COOLDOWN
            if getattr(self, 'type', '') == 'bandit':
                bandit_wind_trapped = bool(getattr(self, '_wind_trapped', False))
                self._aura_t = (getattr(self, '_aura_t', 0.0) + dt / 1.2) % 1.0
                self._gold_glow_t = max(self._gold_glow_t, 0.2)
                if getattr(self, 'radar_slow_left', 0.0) > 0.0:
                    self.radar_slow_left = max(0.0, float(getattr(self, 'radar_slow_left', 0.0)) - dt)
                    if self.radar_slow_left <= 0.0 and hasattr(self, '_radar_base_speed'):
                        self.speed = float(getattr(self, '_radar_base_speed', self.speed))
                if getattr(self, 'radar_tagged', False):
                    self.radar_ring_phase = (float(getattr(self, 'radar_ring_phase', 0.0)) + dt) % float(getattr(self, 'radar_ring_period', 2.0))
                self._steal_accum += float(getattr(self, 'steal_per_sec', game.BANDIT_STEAL_RATE_MIN)) * dt
                steal_units = int(self._steal_accum)
                if steal_units >= 1 and game_state is not None:
                    meta = _meta()
                    self._steal_accum -= steal_units
                    lvl = int(getattr(game_state, 'spoils_gained', 0))
                    bank = int(meta.get('spoils', 0))
                    total_avail = max(0, lvl + bank)
                    lb_lvl = int(getattr(self, 'lockbox_level', meta.get('lockbox_level', 0)))
                    lock_floor = 0
                    if lb_lvl > 0:
                        lock_floor = int(getattr(self, 'lockbox_floor', 0))
                        if lock_floor <= 0:
                            baseline = int(getattr(self, 'lockbox_baseline', total_avail))
                            lock_floor = game.lockbox_protected_min(baseline, lb_lvl)
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
                            meta['spoils'] = max(0, bank - rest)
                        self._stolen_total = int(getattr(self, '_stolen_total', 0)) + got
                        game_state._bandit_stolen = int(getattr(game_state, '_bandit_stolen', 0)) + got
                        cx, cy = (self.rect.centerx, self.rect.centery)
                        game_state.add_damage_text(cx, cy - 18, f'-{got}', crit=True, kind='hp')
                current_escape = float(getattr(self, 'escape_t', game.BANDIT_ESCAPE_TIME_BASE))
                if bandit_wind_trapped:
                    self.escape_t = max(0.0, current_escape)
                else:
                    self.escape_t = max(0.0, current_escape - dt)
                if self.escape_t <= 0.0 and (not bandit_wind_trapped):
                    if game_state is not None:
                        game_state.add_damage_text(self.rect.centerx, self.rect.centery, 'ESCAPED', crit=False, kind='shield')
                        stolen = int(getattr(self, '_stolen_total', 0))
                        game_state.flash_banner(f'BANDIT ESCAPED — STOLEN {stolen} COINS', sec=1.0)
                    try:
                        enemies.remove(self)
                    except Exception:
                        pass
                    return
            if self.type == 'mistling':
                self._life = getattr(self, '_life', 0.0) + dt
                if self.hp <= 0 and (not getattr(self, '_boom_done', False)):
                    cx, cy = (self.rect.centerx, self.rect.centery)
                    pr = player.rect
                    if (pr.centerx - cx) ** 2 + (pr.centery - cy) ** 2 <= game.MISTLING_BLAST_RADIUS ** 2:
                        if player.hit_cd <= 0.0:
                            game_state.damage_player(player, game.MISTLING_BLAST_DAMAGE)
                            player.hit_cd = float(game.PLAYER_HIT_COOLDOWN)
                    self._boom_done = True
            if self.type == 'corruptling':
                self._life = getattr(self, '_life', 0.0) + dt
                if self.hp <= 0 and (not getattr(self, '_acid_on_death', False)):
                    game_state.spawn_acid_pool(self.rect.centerx, self.rect.centery, r=20, life=4.0, dps=game.ACID_DPS * 0.8)
                    self._acid_on_death = True
            if getattr(self, 'is_boss', False) and getattr(self, 'type', '') == 'boss_mem':
                enraged = bool(getattr(self, 'is_enraged', False))
                hp_pct = max(0.0, self.hp / max(1, self.max_hp))
                hp_pct_effective = 0.0 if enraged else hp_pct
                cd_mult = float(getattr(self, '_enrage_cd_mult', 1.0))
                if enraged:
                    self.phase = 3
                elif hp_pct > 0.7:
                    self.phase = 1
                elif hp_pct > 0.4:
                    self.phase = 2
                else:
                    self.phase = 3
                self._spit_cd = max(0.0, getattr(self, '_spit_cd', 0.0) - dt)
                self._split_cd = max(0.0, getattr(self, '_split_cd', 0.0) - dt)
                phase1_ok = enraged or self.phase >= 1
                phase2_ok = enraged or self.phase >= 2
                phase3_ok = enraged or self.phase >= 3
                if phase1_ok:
                    if self._spit_cd <= 0.0:
                        px, py = (player.rect.centerx, player.rect.centery)
                        ang = math.atan2(py - cy, px - cx)
                        points = []
                        for w in range(game.SPIT_WAVES_P1):
                            for i in range(game.SPIT_PUDDLES_PER_WAVE):
                                off_ang = ang + math.radians(random.uniform(-game.SPIT_CONE_DEG / 2, game.SPIT_CONE_DEG / 2))
                                dist = game.SPIT_RANGE * (i + 1) / game.SPIT_PUDDLES_PER_WAVE * random.uniform(0.6, 1.0)
                                points.append((cx + math.cos(off_ang) * dist, cy + math.sin(off_ang) * dist))
                        game_state.spawn_telegraph(cx, cy, r=28, life=game.ACID_TELEGRAPH_T, kind='acid', payload={'points': points, 'radius': 24, 'life': game.ACID_LIFETIME, 'dps': game.ACID_DPS, 'slow': game.ACID_SLOW_FRAC})
                        self._spit_cd = 5.0 * cd_mult
                    if self._split_cd <= 0.0:
                        for _ in range(2):
                            enemies.append(game.spawn_corruptling_at(cx + random.randint(-20, 20), cy + random.randint(-20, 20)))
                        self._split_cd = game.SPLIT_CD_P1 * cd_mult
                if phase2_ok:
                    self.speed = max(game.MEMDEV_SPEED, game.MEMDEV_SPEED + 0.5)
                    if self._spit_cd <= 0.0:
                        for _ in range(2):
                            px, py = (player.rect.centerx, player.rect.centery)
                            ang = math.atan2(py - cy, px - cx)
                            points = []
                            for w in range(game.SPIT_WAVES_P1):
                                for i in range(game.SPIT_PUDDLES_PER_WAVE):
                                    off_ang = ang + math.radians(random.uniform(-game.SPIT_CONE_DEG / 2, game.SPIT_CONE_DEG / 2))
                                    dist = game.SPIT_RANGE * (i + 1) / game.SPIT_PUDDLES_PER_WAVE * random.uniform(0.6, 1.0)
                                    points.append((cx + math.cos(off_ang) * dist, cy + math.sin(off_ang) * dist))
                            game_state.spawn_telegraph(cx, cy, r=32, life=game.ACID_TELEGRAPH_T, kind='acid', payload={'points': points, 'radius': 26, 'life': game.ACID_LIFETIME, 'dps': game.ACID_DPS, 'slow': game.ACID_SLOW_FRAC})
                        self._spit_cd = 4.0 * cd_mult
                    if self._split_cd <= 0.0:
                        for _ in range(3):
                            enemies.append(game.spawn_corruptling_at(cx + random.randint(-20, 20), cy + random.randint(-20, 20)))
                        self._split_cd = game.SPLIT_CD_P2 * cd_mult
                    pull_any = False
                    for z in list(enemies):
                        if getattr(z, 'type', '') == 'corruptling' and getattr(z, '_life', 0.0) >= game.FUSION_LIFETIME:
                            zx, zy = (z.rect.centerx, z.rect.centery)
                            if (zx - cx) ** 2 + (zy - cy) ** 2 <= game.FUSION_PULL_RADIUS ** 2:
                                z.hp = 0
                                self.hp = min(self.max_hp, self.hp + game.FUSION_HEAL)
                                pull_any = True
                    if pull_any:
                        game_state.add_damage_text(cx, cy, +game.FUSION_HEAL, crit=False, kind='shield')
                if phase3_ok:
                    next_pct = getattr(self, '_rain_next_pct', 0.4)
                    while hp_pct_effective <= next_pct and next_pct >= 0.0:
                        pts = []
                        for _ in range(game.RAIN_PUDDLES):
                            gx = random.randint(0, game.GRID_SIZE - 1)
                            gy = random.randint(0, game.GRID_SIZE - 1)
                            pts.append((gx * game.CELL_SIZE + game.CELL_SIZE // 2, gy * game.CELL_SIZE + game.CELL_SIZE // 2 + game.INFO_BAR_HEIGHT))
                        game_state.spawn_telegraph(cx, cy, r=36, life=game.RAIN_TELEGRAPH_T, kind='acid', payload={'points': pts, 'radius': 22, 'life': game.ACID_LIFETIME, 'dps': game.ACID_DPS, 'slow': game.ACID_SLOW_FRAC})
                        next_pct -= game.RAIN_STEP
                        self._rain_next_pct = next_pct
                    if self._split_cd <= 0.0:
                        for _ in range(2):
                            enemies.append(game.spawn_corruptling_at(cx + random.randint(-20, 20), cy + random.randint(-20, 20)))
                        self._split_cd = 12.0 * cd_mult
                    if hp_pct_effective <= game.CHARGE_THRESH and (not getattr(self, '_charging', False)):
                        self._charging = True
                        self.speed = game.CHARGE_SPEED
                if not hasattr(self, '_dash_state'):
                    self._dash_state = 'idle'
                    self._dash_cd = random.uniform(4.5, 6.0) * cd_mult
                    self._dash_t = 0.0
                    self._dash_speed_hold = float(self.speed)
                    self._ghost_accum = 0.0
                self._dash_cd = max(0.0, self._dash_cd - dt)
                if self._dash_state == 'idle' and self._dash_cd <= 0.0 and (not getattr(self, '_charging', False)):
                    px, py = (player.rect.centerx, player.rect.centery)
                    cx, cy = (self.rect.centerx, self.rect.centery)
                    vx, vy = (px - cx, py - cy)
                    L = (vx * vx + vy * vy) ** 0.5 or 1.0
                    self._dash_dir = (vx / L, vy / L)
                    self._dash_state = 'wind'
                    self._dash_t = game.BOSS_DASH_WINDUP
                    self._dash_speed_hold = float(self.speed)
                    self._ghost_accum = 0.0
                    self.speed = max(0.2, self._dash_speed_hold * 0.25)
                    game_state.spawn_telegraph(cx, cy, r=int(getattr(self, 'radius', self.size * 0.5) * 0.9), life=self._dash_t, kind='acid', payload=None)
                elif self._dash_state == 'wind':
                    self._dash_t -= dt
                    self.speed = max(0.2, self._dash_speed_hold * 0.25)
                    if self._dash_t <= 0.0:
                        self._dash_state = 'go'
                        self._dash_t = game.BOSS_DASH_GO_TIME
                        self.speed = self._dash_speed_hold
                        dash_mult = game.BOSS_DASH_SPEED_MULT_ENRAGED if getattr(self, 'is_enraged', False) else game.BOSS_DASH_SPEED_MULT
                        self.buff_spd_add = float(getattr(self, 'buff_spd_add', 0.0)) + float(self._dash_speed_hold) * (dash_mult - 1.0)
                        self.buff_t = max(getattr(self, 'buff_t', 0.0), self._dash_t)
                        self.no_clip_t = max(getattr(self, 'no_clip_t', 0.0), self._dash_t + 0.05)
                        self._dash_cd_next = random.uniform(4.5, 6.0)
                elif self._dash_state == 'go':
                    self._dash_t -= dt
                    self._ghost_accum += dt
                    f0 = getattr(self, '_foot_prev', (self.rect.centerx, self.rect.bottom))
                    f1 = getattr(self, '_foot_curr', (self.rect.centerx, self.rect.bottom))
                    n = int(self._ghost_accum // game.AFTERIMAGE_INTERVAL)
                    if n > 0:
                        self._ghost_accum -= n * game.AFTERIMAGE_INTERVAL
                        for i in range(n):
                            t = (i + 1) / (n + 1)
                            gx = f0[0] * (1 - t) + f1[0] * t
                            gy = f0[1] * (1 - t) + f1[1] * t
                            game_state.ghosts.append(game.AfterImageGhost(gx, gy, self.size, self.size, self.color, ttl=game.AFTERIMAGE_TTL))
                    if self._dash_t <= 0.0:
                        self._dash_state = 'idle'
                        next_cd = getattr(self, '_dash_cd_next', None)
                        if next_cd is None:
                            next_cd = random.uniform(4.5, 6.0)
                        self._dash_cd = next_cd * cd_mult
                        self._dash_cd_next = None

        def draw(self, screen):
            if getattr(self, 'type', '') == 'bandit':
                cx, cy = (self.rect.centerx, self.rect.bottom)
                t = float(getattr(self, '_aura_t', 0.0)) % 1.0
                base_r = max(16, int(self.radius * 7.0))
                r = int(base_r + self.radius * 1.2 * t)
                alpha = int(210 - 150 * t)
                s = pygame.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
                pygame.draw.circle(s, (255, 215, 0, int(alpha * 0.35)), (r + 3, r + 3), r)
                pygame.draw.circle(s, (255, 215, 0, alpha), (r + 3, r + 3), r, width=5)
                screen.blit(s, (cx - r - 3, cy - r - 3))
                if getattr(self, 'radar_tagged', False):
                    rr = max(20, int(self.radius * 3.0))
                    ring = pygame.Surface((rr * 2 + 10, rr * 2 + 10), pygame.SRCALPHA)
                    pygame.draw.circle(ring, (255, 60, 60, 220), (rr + 5, rr + 5), rr, width=6)
                    screen.blit(ring, (self.rect.centerx - rr - 5, self.rect.centery - rr - 5))
            fallback = game.ENEMY_COLORS.get(getattr(self, 'type', 'basic'), (255, 60, 60))
            color = getattr(self, '_current_color', fallback)
            pygame.draw.rect(screen, color, self.rect)
            if getattr(self, 'is_enraged', False):
                pad = 6
                glow_rect = self.rect.inflate(pad * 2, pad * 2)
                glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
                pulse = 150 + int(60 * math.sin(pygame.time.get_ticks() * 0.02))
                pygame.draw.rect(glow, (min(255, max(0, color[0])), min(255, max(0, color[1])), min(255, max(0, color[2])), min(255, max(80, pulse))), glow.get_rect(), width=3, border_radius=8)
                screen.blit(glow, glow_rect.topleft)
    game.__dict__.update({'AfterImageGhost': AfterImageGhost, 'Enemy': Enemy})
    return (AfterImageGhost, Enemy)
