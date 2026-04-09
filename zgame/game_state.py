"""GameState extracted from ZGame.py."""
from __future__ import annotations
import math
import random
from typing import Dict, List, Optional, Set, Tuple
import pygame
from zgame import runtime_state as rs

def install(game):
    meta = rs.meta(game)
    runtime = rs.runtime(game)

    class GameState:

        def __init__(self, obstacles: Dict, items: Set, main_item_pos: List[Tuple[int, int]], decorations: list):
            self.obstacles = obstacles
            self.items = items
            self.destructible_count = self.count_destructible_obstacles()
            self.main_item_pos = main_item_pos
            self.items_total = len(items)
            self.decorations = decorations
            self.spoils = []
            self.heals = []
            self.dmg_texts = []
            self.acids = []
            self.ground_spikes = []
            self._ground_spike_t = 0.0
            self._ground_spike_d = 0.0
            self.curing_paint = []
            self._curing_paint_t = 0.0
            self._curing_paint_d = 0.0
            self._curing_paint_tick_t = float(game.CURING_PAINT_TICK_INTERVAL)
            self._curing_paint_bins = {}
            self._curing_paint_max_r = 0.0
            self._curing_paint_recent = []
            self.biome_curing_paint_bonus = 0
            self.paint_grid = [[game.PaintTile() for _ in range(game.GRID_SIZE)] for _ in range(game.GRID_SIZE)]
            self.paint_active = set()
            self.telegraphs = []
            self.aegis_pulses = []
            self.ghosts = []
            self.fog_on = False
            self.fog_radius_px = game.FOG_VIEW_TILES * game.CELL_SIZE
            self.fog_enabled: bool = False
            self.fog_alpha = game.FOG_OVERLAY_ALPHA
            self.fog_lanterns: list = []
            self._fog_pulse_t: float = 0.0
            self.spoils_gained = 0
            self._bandit_stolen = 0
            self.level_coin_delta = 0
            self._spoils_settled = False
            self.bandit_spawned_this_level = False
            self.banner_text = None
            self.banner_t = 0.0
            self._banner_tick_ms = None
            self.focus_queue = []
            self.ff_dist = None
            self.ff_next = None
            self._ff_goal = None
            self._ff_dirty = True
            self._obstacle_revision = 0
            self._ff_timer = 0.0
            self._ff_tacc = 0.0
            self.projectiles = []
            self.pending_bullets: List['Bullet'] = []
            self._vuln_mark_cd: float = 0.0
            self.hurricanes: list[dict] = []
            self.fx = game.ParticleSystem()
            self.comet_blasts: list[game.CometBlast] = []
            self.comet_corpses: list[game.CometCorpse] = []
            self._cam_shake_t = 0.0
            self._cam_shake_total = 0.001
            self._cam_shake_mag = 0.0

        def count_destructible_obstacles(self) -> int:
            return sum((1 for obs in self.obstacles.values() if obs.type == 'Destructible'))

        def spawn_spoils(self, x_px: float, y_px: float, count: int=1):
            remaining = int(max(0, count))
            if remaining <= 0:
                return
            max_spoils = int(getattr(game, "WEB_MAX_SPOILS_ON_FIELD", 0) or 0) if game.IS_WEB else 0
            if max_spoils > 0:
                slots_left = max(0, max_spoils - len(self.spoils))
                if slots_left <= 0 and self.spoils:
                    nearest = min(
                        self.spoils,
                        key=lambda spoil: (spoil.base_x - float(x_px)) ** 2 + (spoil.base_y - float(y_px)) ** 2,
                    )
                    nearest.value += remaining
                    return
                spawn_count = min(remaining, max(1, slots_left))
                bundle = max(1, int(math.ceil(remaining / float(max(1, spawn_count)))))
            else:
                spawn_count = remaining
                bundle = 1
            for _ in range(spawn_count):
                value = min(bundle, remaining)
                jx = random.uniform(-6, 6)
                jy = random.uniform(-6, 6)
                self.spoils.append(game.Spoil(x_px + jx, y_px + jy, value))
                remaining -= value
            if remaining > 0 and self.spoils:
                self.spoils[-1].value += remaining

        def update_spoils(self, dt: float, player: 'Player'):
            """
        Update coin bounce, and gently pull coins toward the player within pickup range.
        Actual pickup still happens in collect_spoils when a coin overlaps the player.
        """
            for s in self.spoils:
                s.update(dt)
            magnet_radius = int(meta.get('coin_magnet_radius', 0) or 0)
            pull_radius = max(0, int(game.COIN_PICKUP_RADIUS_BASE + magnet_radius))
            if pull_radius <= 0:
                return
            px, py = player.rect.center
            pull_speed = 480.0
            r2 = float(pull_radius * pull_radius)
            for s in self.spoils:
                cx, cy = s.rect.center
                dx = px - cx
                dy = py - cy
                dist2 = dx * dx + dy * dy
                if dist2 > r2:
                    continue
                dist = max(1.0, dist2 ** 0.5)
                step = min(pull_speed * dt, dist)
                nx = cx + dx / dist * step
                ny = cy + dy / dist * step
                s.base_x += nx - cx
                s.base_y += ny - cy
                s._update_rect()

        def collect_item(self, player_rect: pygame.Rect) -> bool:
            """Collect one item if the player overlaps it. Returns True if collected."""
            for it in list(self.items):
                if player_rect.colliderect(it.rect):
                    self.items.remove(it)
                    try:
                        meta['run_items_collected'] = int(meta.get('run_items_collected', 0)) + 1
                    except Exception:
                        pass
                    return True
            return False

        def collect_spoils(self, player_rect: pygame.Rect) -> int:
            """Collect spoils that touch the player."""
            gained = 0
            pickup_rect = player_rect
            for s in list(self.spoils):
                if pickup_rect.colliderect(s.rect):
                    self.spoils.remove(s)
                    self.spoils_gained += s.value
                    self.level_coin_delta += s.value
                    gained += s.value
            return gained

        def collect_spoils_for_enemy(self, enemy: 'Enemy') -> int:
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
            meta_store = meta
            level_spoils = int(getattr(self, 'spoils_gained', 0))
            try:
                bank = int(meta_store.get('spoils', 0))
            except Exception:
                meta_store = {}
                bank = 0
            coins_before = max(0, level_spoils + bank)
            lb_lvl = 0
            try:
                lb_lvl = int(meta_store.get('lockbox_level', 0))
            except Exception:
                lb_lvl = 0
            amt = game.clamp_coin_loss_with_lockbox(coins_before, amt, lb_lvl)
            g = level_spoils
            d = min(g, amt)
            self.spoils_gained = g - d
            taken += d
            amt -= d
            if amt > 0 and meta_store is not None:
                rest = min(max(0, bank), amt)
                meta_store['spoils'] = bank - rest
                taken += rest
            try:
                self.level_coin_delta -= taken
            except Exception:
                pass
            return taken

        def spawn_heal(self, x_px: float, y_px: float, amount: int=game.HEAL_POTION_AMOUNT):
            if len(self.heals) >= game.HEAL_MAX_ON_FIELD:
                return
            jx = random.uniform(-6, 6)
            jy = random.uniform(-6, 6)
            self.heals.append(game.HealPickup(x_px + jx, y_px + jy, amount))

        def update_heals(self, dt: float):
            for h in self.heals:
                h.update(dt)

        def collect_heals(self, player: 'Player') -> int:
            healed = 0
            for h in list(self.heals):
                if player.rect.colliderect(h.rect):
                    self.heals.remove(h)
                    before = player.hp
                    player.hp = min(player.max_hp, player.hp + h.heal)
                    healed += player.hp - before
            return healed

        def flash_banner(self, text: str, sec: float=1.0):
            """在屏幕中央显示一条横幅 sec 秒。"""
            self.banner_text = str(text)
            self.banner_t = float(max(0.0, sec))
            self._banner_tick_ms = None

        def spawn_acid_pool(self, x, y, r=24, dps=game.ACID_DPS, life=game.ACID_LIFETIME, slow_frac=None, slow=None, style='acid'):
            if slow_frac is None and slow is not None:
                slow_frac = slow
            if slow_frac is None:
                slow_frac = game.ACID_SLOW_FRAC
            a = game.AcidPool(float(x), float(y), float(r), float(dps), float(slow_frac), float(life))
            setattr(a, 'style', style)
            setattr(a, 'life0', float(life))
            self.acids.append(a)

        def spawn_projectile(self, proj):
            self.projectiles.append(proj)

        def update_acids(self, dt: float, player: 'Player'):
            player.slow_t = max(0.0, getattr(player, 'slow_t', 0.0) - dt)
            player.acid_dot_timer = max(0.0, getattr(player, 'acid_dot_timer', 0.0) - dt)
            if not hasattr(player, '_acid_dmg_accum'):
                player._acid_dmg_accum = 0.0
            if not hasattr(player, '_slow_frac'):
                player._slow_frac = 0.0
            px, py = (player.rect.centerx, player.rect.centery)
            max_dps = 0.0
            max_slow = 0.0
            touching = False
            alive = []
            for a in self.acids:
                a.t -= dt
                if a.t > 0:
                    alive.append(a)
                    if a.contains(px, py):
                        touching = True
                        if a.dps > max_dps:
                            max_dps = a.dps
                        if a.slow_frac > max_slow:
                            max_slow = a.slow_frac
            self.acids = alive
            if touching:
                player._acid_dmg_accum += max_dps * dt
                ticks = int(player._acid_dmg_accum)
                if ticks > 0:
                    self.damage_player(player, ticks)
                    player._acid_dmg_accum -= ticks
                player.slow_t = max(player.slow_t, 0.4)
                player.acid_dot_timer = game.ACID_DOT_DURATION
                player.acid_dot_dps = max_dps * game.ACID_DOT_MULT
                player._slow_frac = max(float(getattr(player, '_slow_frac', 0.0)), float(max_slow))
            elif getattr(player, 'slow_t', 0.0) <= 0.0:
                player._slow_frac = 0.0

        def paint_tile_at_world(self, x_px: float, y_px: float) -> Optional[game.PaintTile]:
            gx = int(x_px // game.CELL_SIZE)
            gy = int((y_px - game.INFO_BAR_HEIGHT) // game.CELL_SIZE)
            if not (0 <= gx < game.GRID_SIZE and 0 <= gy < game.GRID_SIZE):
                return None
            return self.paint_grid[gy][gx]

        def paint_intensity_at_world(self, x_px: float, y_px: float, owner: int=2) -> float:
            tile = self.paint_tile_at_world(x_px, y_px)
            if tile is None:
                return 0.0
            if getattr(tile, 'paint_owner', 0) != int(owner):
                return 0.0
            return float(getattr(tile, 'paint_intensity', 0.0))

        def player_paint_lifetime(self, level_override: int | None=None) -> float:
            if level_override is None:
                lvl = int(meta.get('curing_paint_level', 0))
                lvl += int(getattr(self, 'biome_curing_paint_bonus', 0))
            else:
                lvl = int(level_override)
            if lvl <= 0:
                return float(game.CURING_PAINT_LIFETIMES[0]) if game.CURING_PAINT_LIFETIMES else float(game.ENEMY_PAINT_LIFETIME)
            idx = max(0, min(lvl - 1, len(game.CURING_PAINT_LIFETIMES) - 1))
            return float(game.CURING_PAINT_LIFETIMES[idx])

        def apply_paint(self, x_px: float, y_px: float, radius_px: float, owner: int, paint_type: Optional[str]=None, lifetime_s: Optional[float]=None, paint_color: Optional[tuple[int, int, int]]=None) -> None:
            if owner <= 0:
                return
            r = max(1.0, float(radius_px))
            y_world = y_px - game.INFO_BAR_HEIGHT
            min_gx = int(max(0, (x_px - r) // game.CELL_SIZE))
            max_gx = int(min(game.GRID_SIZE - 1, (x_px + r) // game.CELL_SIZE))
            min_gy = int(max(0, (y_world - r) // game.CELL_SIZE))
            max_gy = int(min(game.GRID_SIZE - 1, (y_world + r) // game.CELL_SIZE))
            r2 = r * r
            life0 = float(lifetime_s) if lifetime_s is not None else 0.0
            if life0 <= 0.0:
                if owner == 1:
                    life0 = self.player_paint_lifetime()
                elif owner == 2:
                    life0 = float(game.ENEMY_PAINT_LIFETIME)
            for gx in range(min_gx, max_gx + 1):
                for gy in range(min_gy, max_gy + 1):
                    cx = gx * game.CELL_SIZE + game.CELL_SIZE * 0.5
                    cy = gy * game.CELL_SIZE + game.CELL_SIZE * 0.5 + game.INFO_BAR_HEIGHT
                    dx = cx - x_px
                    dy = cy - y_px
                    if dx * dx + dy * dy > r2:
                        continue
                    tile = self.paint_grid[gy][gx]
                    tile.paint_owner = int(owner)
                    tile.paint_intensity = 1.0
                    tile.paint_age = 0.0
                    tile.paint_type = paint_type
                    tile.paint_life0 = life0
                    tile.paint_color = tuple((int(c) for c in paint_color[:3])) if paint_color else None
                    tile.paint_radius = r
                    tile.refresh_visuals()
                    self.paint_active.add((gx, gy))

        def apply_enemy_paint(self, x_px: float, y_px: float, radius_px: float, paint_type: str='corrupt_trail', paint_color: Optional[tuple[int, int, int]]=None) -> None:
            self.apply_paint(x_px, y_px, radius_px, owner=2, paint_type=paint_type, paint_color=paint_color)

        def apply_player_paint(self, x_px: float, y_px: float, radius_px: float, paint_type: str='curing_paint') -> None:
            lifetime = self.player_paint_lifetime()
            self.apply_paint(x_px, y_px, radius_px, owner=1, paint_type=paint_type, lifetime_s=lifetime)

        def update_paint_tiles(self, dt: float) -> None:
            if not self.paint_active:
                return
            hell = getattr(self, 'biome_active', None) == 'Scorched Hell'
            for gx, gy in list(self.paint_active):
                if not (0 <= gx < game.GRID_SIZE and 0 <= gy < game.GRID_SIZE):
                    self.paint_active.discard((gx, gy))
                    continue
                tile = self.paint_grid[gy][gx]
                owner = int(getattr(tile, 'paint_owner', 0))
                if owner <= 0:
                    self.paint_active.discard((gx, gy))
                    continue
                life0 = float(getattr(tile, 'paint_life0', 0.0))
                if life0 <= 0.0:
                    if owner == 1:
                        life0 = self.player_paint_lifetime()
                    elif owner == 2:
                        life0 = float(game.ENEMY_PAINT_LIFETIME)
                    tile.paint_life0 = life0
                if life0 <= 0.0:
                    tile.paint_owner = 0
                    tile.paint_intensity = 0.0
                    tile.paint_age = 0.0
                    tile.paint_type = None
                    tile.paint_color = None
                    tile.paint_radius = 0.0
                    self.paint_active.discard((gx, gy))
                    continue
                tile.paint_age = float(getattr(tile, 'paint_age', 0.0)) + float(dt)
                if hell:
                    tile.paint_intensity = 1.0
                    continue
                tile.paint_intensity = max(0.0, 1.0 - tile.paint_age / life0)
                if tile.paint_intensity <= 0.0:
                    tile.paint_owner = 0
                    tile.paint_intensity = 0.0
                    tile.paint_age = 0.0
                    tile.paint_life0 = 0.0
                    tile.paint_type = None
                    tile.paint_color = None
                    self.paint_active.discard((gx, gy))

        def update_enemy_paint(self, dt: float, player: 'Player') -> None:
            self.update_paint_tiles(dt)
            if player is None:
                return
            player._enemy_paint_vignette_t = max(0.0, float(getattr(player, '_enemy_paint_vignette_t', 0.0)) - float(dt))
            intensity = self.paint_intensity_at_world(player.rect.centerx, player.rect.centery, owner=2)
            if intensity > 0.0:
                player._enemy_paint_slow = game.ENEMY_PAINT_PLAYER_SLOW * intensity
                tick_t = float(getattr(player, '_enemy_paint_dot_t', 0.0)) + float(dt)
                interval = float(game.ENEMY_PAINT_DOT_INTERVAL)
                if interval > 0.0 and tick_t >= interval:
                    ticks = int(tick_t // interval)
                    tick_t -= interval * ticks
                    dmg_per_tick = float(game.ENEMY_PAINT_DOT_HP_FRAC) * float(getattr(player, 'max_hp', 0)) * intensity
                    if dmg_per_tick > 0.0 and ticks > 0:
                        accum = float(getattr(player, '_enemy_paint_dot_accum', 0.0)) + dmg_per_tick * ticks
                        deal = int(accum)
                        if deal > 0:
                            self.damage_player(player, deal, kind='hp_enemy')
                            player._enemy_paint_vignette_t = max(float(getattr(player, '_enemy_paint_vignette_t', 0.0)), 0.18)
                            accum -= deal
                        player._enemy_paint_dot_accum = accum
                player._enemy_paint_dot_t = tick_t
            else:
                player._enemy_paint_slow = 0.0
                player._enemy_paint_dot_t = 0.0
                player._enemy_paint_dot_accum = 0.0

        def update_curing_paint(self, dt: float, player: 'Player', enemies: list) -> None:
            lvl = int(meta.get('curing_paint_level', 0))
            lvl += int(getattr(self, 'biome_curing_paint_bonus', 0))
            if lvl > 0 and game.CURING_PAINT_LIFETIMES:
                lvl = min(lvl, len(game.CURING_PAINT_LIFETIMES))
            hell = getattr(self, 'biome_active', None) == 'Scorched Hell'
            if lvl <= 0 or player is None:
                if self.curing_paint:
                    self.curing_paint = []
                self._curing_paint_bins = {}
                self._curing_paint_max_r = 0.0
                self._curing_paint_recent = []
                self._curing_paint_t = 0.0
                self._curing_paint_d = 0.0
                self._curing_paint_tick_t = float(game.CURING_PAINT_TICK_INTERVAL)
                if enemies:
                    for z in enemies:
                        if hasattr(z, '_curing_paint_accum'):
                            z._curing_paint_accum = 0.0
                return
            lvl_idx = max(0, min(lvl - 1, len(game.CURING_PAINT_LIFETIMES) - 1))
            radius = game.curing_paint_radius(lvl)
            mvx, mvy = getattr(player, '_last_move_vec', (0.0, 0.0))
            moved = math.hypot(mvx, mvy)
            if moved > 0.05:
                self._curing_paint_t += dt
                self._curing_paint_d += moved
                if self._curing_paint_t >= game.CURING_PAINT_SPAWN_INTERVAL or self._curing_paint_d >= game.CURING_PAINT_SPAWN_DIST:
                    lifetime = float(game.CURING_PAINT_LIFETIMES[lvl_idx])
                    px, py = (player.rect.centerx, player.rect.centery)
                    base_color = game.curing_paint_base_color(player)
                    new_paint = game.CuringPaintFootprint(px, py, radius, lifetime, lvl, base_color)
                    self.curing_paint.append(new_paint)
                    self._curing_paint_max_r = max(float(self._curing_paint_max_r), float(radius))
                    if hell:
                        gx = int(new_paint.x // game.CELL_SIZE)
                        gy = int((new_paint.y - game.INFO_BAR_HEIGHT) // game.CELL_SIZE)
                        self._curing_paint_bins.setdefault((gx, gy), []).append(new_paint)
                        recent = getattr(self, '_curing_paint_recent', None)
                        if recent is None:
                            recent = []
                            self._curing_paint_recent = recent
                        recent.append(new_paint)
                    self.apply_player_paint(px, py, radius, paint_type='curing_paint')
                    self._curing_paint_t = 0.0
                    self._curing_paint_d = 0.0
            if hell:
                lifetime = float(self.player_paint_lifetime())
                denom = max(0.01, float(game.CURING_PAINT_SPAWN_INTERVAL))
                anim_limit = max(6, int(math.ceil(lifetime / denom)))
                recent = getattr(self, '_curing_paint_recent', []) or []
                if not recent and self.curing_paint:
                    recent = list(self.curing_paint[-anim_limit:])
                if len(recent) > anim_limit:
                    recent = recent[-anim_limit:]
                spark_chance = float(game.CURING_PAINT_SPARK_RATE) * dt
                if recent:
                    alive_recent = []
                    for p in recent:
                        tile = self.paint_tile_at_world(p.x, p.y)
                        if tile is not None and getattr(tile, 'paint_owner', 0) != 1:
                            continue
                        if random.random() < spark_chance:
                            game.spawn_curing_paint_spark_vfx(self, p.x, p.y, 1.0)
                        alive_recent.append(p)
                    self._curing_paint_recent = alive_recent
                else:
                    self._curing_paint_recent = recent
            else:
                alive = []
                new_bins = {}
                spark_chance = float(game.CURING_PAINT_SPARK_RATE) * dt
                for p in self.curing_paint:
                    tile = self.paint_tile_at_world(p.x, p.y)
                    if tile is not None and getattr(tile, 'paint_owner', 0) != 1:
                        continue
                    p.t -= dt
                    if p.t <= 0:
                        continue
                    intensity = p.intensity
                    if intensity >= 0.1 and random.random() < spark_chance * intensity ** 1.35:
                        game.spawn_curing_paint_spark_vfx(self, p.x, p.y, intensity)
                    alive.append(p)
                    gx = int(p.x // game.CELL_SIZE)
                    gy = int((p.y - game.INFO_BAR_HEIGHT) // game.CELL_SIZE)
                    new_bins.setdefault((gx, gy), []).append(p)
                self.curing_paint = alive
                self._curing_paint_bins = new_bins
            tick_interval = float(game.CURING_PAINT_TICK_INTERVAL)
            tick_t = float(getattr(self, '_curing_paint_tick_t', tick_interval)) - dt
            if tick_t > 0.0:
                self._curing_paint_tick_t = tick_t
                return
            ticks = int(abs(tick_t) // tick_interval) + 1
            tick_t += tick_interval * ticks
            self._curing_paint_tick_t = tick_t
            if not enemies or not self.curing_paint:
                return
            paint_bins = getattr(self, '_curing_paint_bins', {})
            if not paint_bins:
                return
            bullet_base = int(getattr(player, 'bullet_damage', game.BULLET_DAMAGE_ENEMY))
            dmg_per_tick, _, _ = game.curing_paint_stats(lvl, bullet_base)
            base_dmg = float(dmg_per_tick) * float(ticks)
            kill_bonus = game.curing_paint_kill_bonus(int(meta.get('kill_count', 0)))
            max_r = max(float(self._curing_paint_max_r), float(radius))
            for z in enemies:
                if getattr(z, 'hp', 0) <= 0:
                    continue
                zx, zy = z.rect.center
                zr = float(getattr(z, 'radius', getattr(z, 'size', game.CELL_SIZE) * 0.5))
                search_r = max_r + zr
                gx_min = max(0, int((zx - search_r) // game.CELL_SIZE) - 1)
                gx_max = min(game.GRID_SIZE - 1, int((zx + search_r) // game.CELL_SIZE) + 1)
                gy_min = max(0, int((zy - search_r - game.INFO_BAR_HEIGHT) // game.CELL_SIZE) - 1)
                gy_max = min(game.GRID_SIZE - 1, int((zy + search_r - game.INFO_BAR_HEIGHT) // game.CELL_SIZE) + 1)
                max_intensity = 0.0
                for gx in range(gx_min, gx_max + 1):
                    for gy in range(gy_min, gy_max + 1):
                        for p in paint_bins.get((gx, gy), []):
                            tile = self.paint_tile_at_world(p.x, p.y)
                            if tile is not None and getattr(tile, 'paint_owner', 0) != 1:
                                continue
                            intensity = 1.0 if hell else p.intensity
                            if intensity <= 0.0:
                                continue
                            dx = zx - p.x
                            dy = zy - p.y
                            rsum = float(p.r) + zr
                            if dx * dx + dy * dy <= rsum * rsum:
                                if intensity > max_intensity:
                                    max_intensity = intensity
                if max_intensity <= 0.0:
                    continue
                total = base_dmg * kill_bonus * max_intensity
                if getattr(z, 'is_boss', False):
                    total *= game.CURING_PAINT_BOSS_MULT
                if total <= 0.0:
                    continue
                accum = float(getattr(z, '_curing_paint_accum', 0.0)) + total
                deal = int(accum)
                if deal > 0:
                    z.hp -= deal
                    self.add_damage_text(zx, zy - 8, deal, crit=False, kind='dot')
                    z._curing_paint_glow_t = max(0.0, float(getattr(z, '_curing_paint_glow_t', 0.0)), 0.14)
                    z._curing_paint_glow_intensity = max(float(getattr(z, '_curing_paint_glow_intensity', 0.0)), max_intensity)
                    z._curing_paint_accum = accum - deal
                else:
                    z._curing_paint_accum = accum

        def update_ground_spikes(self, dt: float, player: 'Player', enemies: list) -> None:
            lvl = int(meta.get('ground_spikes_level', 0))
            if lvl <= 0 or player is None:
                if self.ground_spikes:
                    self.ground_spikes = []
                self._ground_spike_t = 0.0
                self._ground_spike_d = 0.0
                return
            mvx, mvy = getattr(player, '_last_move_vec', (0.0, 0.0))
            moved = math.hypot(mvx, mvy)
            if moved > 0.05:
                self._ground_spike_t += dt
                self._ground_spike_d += moved
                if self._ground_spike_t >= game.GROUND_SPIKES_SPAWN_INTERVAL or self._ground_spike_d >= game.GROUND_SPIKES_SPAWN_DIST:
                    bullet_base = int(getattr(player, 'bullet_damage', int(meta.get('base_dmg', game.BULLET_DAMAGE_ENEMY)) + int(meta.get('dmg', 0))))
                    damage, lifetime, max_active = game.ground_spikes_stats(lvl, bullet_base)
                    if damage > 0.0 and lifetime > 0.0:
                        px, py = (player.rect.centerx, player.rect.centery)
                        self.ground_spikes.append(game.GroundSpike(px, py, damage, lifetime, game.GROUND_SPIKES_RADIUS, lvl))
                        while len(self.ground_spikes) > max_active:
                            self.ground_spikes.pop(0)
                        game.spawn_ground_spike_spawn_vfx(self, px, py)
                    self._ground_spike_t = 0.0
                    self._ground_spike_d = 0.0
            alive = []
            for s in self.ground_spikes:
                s.t -= dt
                if s.t > 0:
                    alive.append(s)
            self.ground_spikes = alive
            if not enemies or not self.ground_spikes:
                return
            remaining = []
            for s in self.ground_spikes:
                hit = False
                for z in enemies:
                    if getattr(z, 'hp', 0) <= 0:
                        continue
                    zx, zy = z.rect.center
                    zr = float(getattr(z, 'radius', getattr(z, 'size', game.CELL_SIZE) * 0.5))
                    if (zx - s.x) ** 2 + (zy - s.y) ** 2 <= (s.r + zr) ** 2:
                        dealt = int(round(s.damage))
                        if dealt > 0:
                            dealt = game.apply_vuln_bonus(z, dealt)
                        if dealt > 0:
                            hp_before = int(getattr(z, 'hp', 0))
                            if getattr(z, 'shield_hp', 0) > 0:
                                blocked = min(dealt, z.shield_hp)
                                z.shield_hp -= dealt
                                if blocked > 0:
                                    self.add_damage_text(zx, zy, blocked, crit=False, kind='shield')
                                overflow = dealt - blocked
                                if overflow > 0:
                                    z.hp -= overflow
                                    self.add_damage_text(zx, zy - 10, overflow, crit=False, kind='hp_player')
                            else:
                                z.hp -= dealt
                                self.add_damage_text(zx, zy, dealt, crit=False, kind='hp_player')
                            if z.hp < hp_before:
                                z._hit_flash = float(game.HIT_FLASH_DURATION)
                                z._flash_prev_hp = int(max(0, z.hp))
                        z._ground_spike_slow_t = max(float(getattr(z, '_ground_spike_slow_t', 0.0)), float(game.GROUND_SPIKES_SLOW_DURATION))
                        z._comet_shake = max(0.12, float(getattr(z, '_comet_shake', 0.0)))
                        game.spawn_ground_spike_hit_vfx(self, s.x, s.y)
                        hit = True
                        break
                if not hit:
                    remaining.append(s)
            self.ground_spikes = remaining

        def damage_player(self, player, dmg, kind='hp'):
            if getattr(player, '_ultimate_debug', False):
                player.hp = max(player.hp, getattr(player, 'max_hp', game.PLAYER_MAX_HP))
                return 0
            dmg = int(max(0, dmg))
            if dmg <= 0:
                return 0
            sh = int(getattr(player, 'shield_hp', 0))
            if sh > 0:
                blocked = min(dmg, sh)
                player.shield_hp = sh - blocked
                self.add_damage_text(player.rect.centerx, player.rect.top - 10, blocked, crit=False, kind='shield')
                dmg -= blocked
            plating_lvl = int(getattr(player, 'bone_plating_level', 0))
            plating_hp = int(getattr(player, 'bone_plating_hp', 0))
            if dmg > 0 and plating_lvl > 0 and (plating_hp > 0):
                enhanced = plating_lvl >= game.BONE_PLATING_MAX_LEVEL
                if enhanced:
                    consume = game.BONE_PLATING_STACK_HP if plating_hp >= game.BONE_PLATING_STACK_HP else plating_hp
                    blocked = dmg
                    player.bone_plating_hp = max(0, plating_hp - consume)
                    dmg = 0
                    text = 'Bone'
                else:
                    blocked = min(dmg, plating_hp)
                    player.bone_plating_hp = max(0, plating_hp - blocked)
                    dmg -= blocked
                    text = blocked
                if blocked > 0:
                    self.add_damage_text(player.rect.centerx, player.rect.top - 24, text, kind='shield')
                    player._bone_plating_glow = max(0.4, float(getattr(player, '_bone_plating_glow', 0.0)))
            carapace_hp = int(meta.get('carapace_shield_hp', 0))
            if dmg > 0 and carapace_hp > 0:
                absorbed = min(dmg, carapace_hp)
                dmg -= absorbed
                carapace_hp -= absorbed
                meta['carapace_shield_hp'] = carapace_hp
                player.carapace_hp = carapace_hp
                self.add_damage_text(player.rect.centerx, player.rect.top - 10, 'Carapace', kind='shield')
            if dmg > 0:
                hp_before = int(player.hp)
                player.hp = max(0, player.hp - dmg)
                if player.hp < hp_before:
                    player._hit_flash = float(game.HIT_FLASH_DURATION)
                    player._flash_prev_hp = int(player.hp)
                self.add_damage_text(player.rect.centerx, player.rect.centery, dmg, crit=False, kind=kind or 'hp')
            return dmg

        def mark_nav_dirty(self):
            self._ff_dirty = True
            self._obstacle_revision = int(getattr(self, '_obstacle_revision', 0) or 0) + 1

        def refresh_flow_field(self, player_tile, dt=0.0):
            rebuild_interval = game.WEB_FLOW_REFRESH_INTERVAL if game.IS_WEB else 0.3
            self._ff_timer = max(0.0, self._ff_timer - dt)
            self._ff_tacc = min(1.0, float(getattr(self, '_ff_tacc', 0.0)) + float(dt or 0.0))
            needs_rebuild = bool(self._ff_dirty or self._ff_goal != player_tile or self.ff_dist is None or self.ff_next is None)
            if (not game.IS_WEB) and self._ff_timer <= 0.0:
                needs_rebuild = True
            if needs_rebuild:
                self.ff_dist, self.ff_next = game.build_flow_field(game.GRID_SIZE, self.obstacles, player_tile)
                self._ff_goal = player_tile
                self._ff_dirty = False
                self._ff_timer = rebuild_interval
                self._ff_tacc = 0.0
                if game.IS_WEB:
                    return
            if self._ff_tacc >= rebuild_interval or self._ff_dirty:
                goal = self._ff_goal or player_tile
                self.ff_dist, self.ff_next = game.build_flow_field(game.GRID_SIZE, self.obstacles, goal, pad=1)
                self._ff_dirty = False
                self._ff_tacc = 0.0

        def spawn_telegraph(self, x, y, r, life, kind='acid', payload=None, color=(255, 60, 60)):
            self.telegraphs.append(game.TelegraphCircle(float(x), float(y), float(r), float(life), kind, payload, color))

        def update_telegraphs(self, dt: float):
            for t in list(self.telegraphs):
                t.t -= dt
                if t.t <= 0:
                    if t.kind == 'acid' and t.payload:
                        for px, py in t.payload.get('points', []):
                            self.spawn_acid_pool(px, py, r=t.payload.get('radius', 24), dps=t.payload.get('dps', game.ACID_DPS), slow_frac=t.payload.get('slow', game.ACID_SLOW_FRAC), life=t.payload.get('life', game.ACID_LIFETIME))
                    self.telegraphs.remove(t)

        def update_aegis_pulses(self, dt: float, player=None, enemies=None):
            if not getattr(self, 'aegis_pulses', None):
                self.aegis_pulses = []
                return
            alive = []
            for p in self.aegis_pulses:
                p.t -= dt
                if p.t > 0:
                    if player is not None:
                        p.x = float(player.rect.centerx)
                        p.y = float(player.rect.centery)
                    if not getattr(p, 'hit_done', False) and p.life0 - p.t >= float(getattr(p, 'delay', 0.0)) and (enemies is not None):
                        game._apply_aegis_pulse_damage(player, self, enemies, p.x, p.y, float(getattr(p, 'r', 0.0)), int(getattr(p, 'damage', 0)))
                        p.hit_done = True
                    alive.append(p)
            self.aegis_pulses = alive

        def add_damage_text(self, x, y, amount, crit=False, kind='hp'):
            max_texts = int(getattr(game, "WEB_MAX_DAMAGE_TEXTS", 0) or 0) if game.IS_WEB else 0
            if max_texts > 0 and len(self.dmg_texts) >= max_texts:
                if (not crit) and kind in {'dot', 'shield'}:
                    return
                drop_index = 0
                for idx, existing in enumerate(self.dmg_texts):
                    if (not getattr(existing, 'crit', False)) and getattr(existing, 'kind', '') in {'dot', 'shield'}:
                        drop_index = idx
                        break
                try:
                    self.dmg_texts.pop(drop_index)
                except Exception:
                    if self.dmg_texts:
                        self.dmg_texts.pop(0)
            if isinstance(amount, (int, float)):
                amount = int(amount)
                if amount <= 0:
                    return
                self.dmg_texts.append(game.DamageText(x, y, amount, crit, kind))
            else:
                self.dmg_texts.append(game.DamageText(x, y, str(amount), True if crit else False, kind))

        def update_damage_texts(self, dt: float):
            for d in list(self.dmg_texts):
                d.step(dt)
                if not d.alive():
                    self.dmg_texts.remove(d)

        def add_cam_shake(self, magnitude: float, duration: float=0.25):
            mag = max(0.0, float(magnitude))
            dur = max(0.05, float(duration))
            self._cam_shake_mag = max(self._cam_shake_mag, mag)
            self._cam_shake_t = max(self._cam_shake_t, dur)
            self._cam_shake_total = max(self._cam_shake_total, dur)

        def update_camera_shake(self, dt: float):
            self._cam_shake_t = max(0.0, float(getattr(self, '_cam_shake_t', 0.0)) - dt)
            if self._cam_shake_t <= 0.0:
                self._cam_shake_mag = 0.0

        def camera_shake_offset(self) -> tuple[int, int]:
            t = float(getattr(self, '_cam_shake_t', 0.0))
            mag = float(getattr(self, '_cam_shake_mag', 0.0))
            tot = float(getattr(self, '_cam_shake_total', 0.001))
            if t <= 0.0 or mag <= 0.0:
                return (0, 0)
            strength = mag * (t / max(0.001, tot))
            ang = random.random() * math.tau
            return (int(math.cos(ang) * strength), int(math.sin(ang) * strength))

        def spawn_comet_blast(self, target_pos: tuple[float, float], start_pos: tuple[float, float], travel: float, impact_cb=None) -> game.CometBlast:
            cb = game.CometBlast(target_pos, start_pos, travel, on_impact=impact_cb, fx=self.fx)
            self.comet_blasts.append(cb)
            return cb

        def update_comet_blasts(self, dt: float, player=None, enemies=None):
            for b in list(self.comet_blasts):
                b.update(dt)
                if b.done():
                    self.comet_blasts.remove(b)
            if enemies is not None:
                for z in enemies:
                    flash = float(getattr(z, '_comet_flash', 0.0))
                    if flash > 0.0:
                        z._comet_flash = max(0.0, flash - dt * 4.5)
                    shake = float(getattr(z, '_comet_shake', 0.0))
                    if shake > 0.0:
                        z._comet_shake = max(0.0, shake - dt * 4.0)
            self.comet_corpses = [c for c in self.comet_corpses if c.update(dt)]

        def draw_comet_blasts(self, screen: pygame.Surface, camx: float, camy: float):
            for b in getattr(self, 'comet_blasts', []):
                b.draw(screen, camx, camy)

        def draw_comet_corpses(self, screen: pygame.Surface, camx: float, camy: float):
            for c in getattr(self, 'comet_corpses', []):
                c.draw_iso(screen, camx, camy)

        def spawn_hurricane(self, x: float, y: float, r: float | None=None):
            if not hasattr(self, 'hurricanes'):
                self.hurricanes = []
            self.hurricanes.append(game.TornadoEntity(x, y, r if r is not None else game.HURRICANE_START_RADIUS))

        def _apply_pull(self, pos_x, pos_y, radius, hx, hy, range_r, strength, dt, resist_scale=1.0):
            dx = hx - pos_x
            dy = hy - pos_y
            dist = math.hypot(dx, dy)
            if dist <= 0.001 or dist > range_r:
                return (pos_x, pos_y)
            influence = max(0.0, 1.0 - dist / range_r)
            influence *= influence
            pull = strength * influence * resist_scale
            step = pull * dt
            step = min(step, dist * 0.95)
            nx, ny = (dx / dist, dy / dist)
            return (pos_x + nx * step, pos_y + ny * step)

        def update_hurricanes(self, dt: float, player, enemies, bullets, enemy_shots=None):
            for z in enemies:
                if getattr(z, 'type', '') == 'bandit':
                    z._wind_trapped = False
            if not getattr(self, 'hurricanes', None):
                return

            def _vortex_resist(ent):
                resist = 0.8
                if float(getattr(ent, 'speed', 0.0)) >= game.HURRICANE_ESCAPE_SPEED:
                    resist *= 0.4
                if getattr(ent, 'is_boss', False):
                    resist *= 0.15
                return resist
            for h in list(self.hurricanes):
                if isinstance(h, dict):
                    hx_raw = float(h.get('x', 0.0))
                    hy_raw = float(h.get('y', 0.0))
                    rr_raw = float(h.get('r', game.HURRICANE_START_RADIUS))
                    spin_dir = h.get('dir', None)
                    spin_rate = h.get('spin', None)
                    new_h = game.TornadoEntity(hx_raw, hy_raw, rr_raw, spin_rate=spin_rate, spin_dir=spin_dir)
                    self.hurricanes.remove(h)
                    self.hurricanes.append(new_h)
                    h = new_h
                if not hasattr(h, 'spin_rate'):
                    jitter = random.uniform(1.0 - game.HURRICANE_SPIN_VARIANCE, 1.0 + game.HURRICANE_SPIN_VARIANCE)
                    h.spin_rate = max(0.05, game.HURRICANE_SPIN_BASE * jitter)
                if not hasattr(h, 'spin_dir'):
                    h.spin_dir = random.choice((-1.0, 1.0))
                h.update(dt)
                effect_radius = h.r * game.HURRICANE_RANGE_MULT
                dx, dy = h.apply_vortex_physics(player, dt, resist_scale=_vortex_resist(player))
                if dx or dy:
                    game.collide_and_slide_circle(player, self.obstacles.values(), dx, dy)
                for z in enemies:
                    if getattr(z, 'type', '') == 'bandit':
                        dist_bandit = math.hypot(h.x - z.rect.centerx, h.y - z.rect.centery)
                        if dist_bandit <= effect_radius:
                            z._wind_trapped = True
                    dx, dy = h.apply_vortex_physics(z, dt, resist_scale=_vortex_resist(z))
                    if dx or dy:
                        game.collide_and_slide_circle(z, self.obstacles.values(), dx, dy)
                    dist = math.hypot(h.x - z.rect.centerx, h.y - z.rect.centery)
                    if dist < h.r * 1.5:
                        z._hurricane_slow_mult = 0.7
                    else:
                        z._hurricane_slow_mult = 1.0
                all_shots = list(bullets)
                if enemy_shots:
                    all_shots.extend(enemy_shots)
                for b in all_shots:
                    bx = getattr(b, 'x', None)
                    by = getattr(b, 'y', None)
                    if bx is None or by is None:
                        continue
                    dx = h.x - bx
                    dy = h.y - by
                    dist = math.hypot(dx, dy)
                    effect_radius = h.r * game.HURRICANE_RANGE_MULT
                    if dist <= 0.0001 or dist > effect_radius:
                        continue
                    influence = max(0.0, 1.0 - dist / effect_radius)
                    nx, ny = (dx / dist, dy / dist)
                    tx, ty = (-ny, nx)
                    if h.spin_dir < 0:
                        tx, ty = (-tx, -ty)
                    pull = game.HURRICANE_BULLET_PULL * influence
                    b.vx += nx * pull * dt
                    b.vy += ny * pull * dt
                    target_tan = h.spin_rate * dist * influence
                    current_tan = b.vx * tx + b.vy * ty
                    delta_tan = target_tan - current_tan
                    steer = delta_tan * game.HURRICANE_BULLET_SPIN_STEER * dt
                    b.vx += tx * steer
                    b.vy += ty * steer

        def update_vulnerability_marks(self, enemies, dt: float):
            lvl = int(meta.get('vuln_mark_level', 0))
            if lvl <= 0:
                for z in enemies:
                    if hasattr(z, '_vuln_mark_t'):
                        z._vuln_mark_t = 0.0
                self._vuln_mark_cd = 0.0
                return
            runtime['mark_pulse_time'] = float(runtime.get('mark_pulse_time', 0.0)) + dt
            interval, bonus, duration = game.mark_of_vulnerability_stats(lvl)
            for z in enemies:
                t = float(getattr(z, '_vuln_mark_t', 0.0))
                if t > 0.0:
                    z._vuln_mark_t = max(0.0, t - dt)
                    z._vuln_mark_bonus = bonus
                    z._vuln_mark_level = lvl
                flash = float(getattr(z, '_vuln_hit_flash', 0.0))
                if flash > 0.0:
                    z._vuln_hit_flash = max(0.0, flash - dt * 4.0)
            cd = float(getattr(self, '_vuln_mark_cd', 0.0))
            cd -= dt
            triggers = 0
            while cd <= 0.0 and triggers < 3:
                triggers += 1
                cd += interval
                alive_unmarked = [z for z in enemies if getattr(z, 'hp', 0) > 0 and float(getattr(z, '_vuln_mark_t', 0.0)) <= 0.0]
                if not alive_unmarked:
                    continue

                def _priority(z):
                    if getattr(z, 'is_boss', False):
                        return 0
                    if getattr(z, 'is_elite', False):
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
                z._vuln_hit_flash = max(0.0, float(getattr(z, '_vuln_hit_flash', 0.0)))
            self._vuln_mark_cd = cd

        def update_dot_rounds(self, enemies, dt: float) -> None:
            lvl = int(meta.get('dot_rounds_level', 0))
            if lvl <= 0:
                for z in enemies:
                    if getattr(z, 'dot_rounds_stacks', None):
                        z.dot_rounds_stacks = []
                        z._dot_rounds_tick_t = float(game.DOT_ROUNDS_TICK_INTERVAL)
                        z._dot_rounds_accum = 0.0
                return
            tick_interval = float(game.DOT_ROUNDS_TICK_INTERVAL)
            for z in enemies:
                if getattr(z, 'hp', 0) <= 0:
                    continue
                stacks = getattr(z, 'dot_rounds_stacks', None)
                if not stacks:
                    continue
                for s in stacks:
                    s['t'] = float(s.get('t', 0.0)) - dt
                stacks[:] = [s for s in stacks if s.get('t', 0.0) > 0.0]
                if not stacks:
                    z._dot_rounds_tick_t = tick_interval
                    z._dot_rounds_accum = 0.0
                    continue
                tick_t = float(getattr(z, '_dot_rounds_tick_t', tick_interval))
                tick_t -= dt
                if tick_t <= 0.0:
                    ticks = int(abs(tick_t) // tick_interval) + 1
                    tick_t += tick_interval * ticks
                    total = 0.0
                    for s in stacks:
                        total += float(s.get('dmg', 0.0)) * ticks
                    if total > 0.0:
                        if getattr(z, 'is_boss', False):
                            total *= game.DOT_ROUNDS_BOSS_MULT
                        accum = float(getattr(z, '_dot_rounds_accum', 0.0)) + total
                        deal = int(accum)
                        if deal > 0:
                            z.hp -= deal
                            self.add_damage_text(z.rect.centerx, z.rect.centery - 8, deal, crit=False, kind='dot')
                            z._dot_rounds_accum = accum - deal
                        else:
                            z._dot_rounds_accum = accum
                z._dot_rounds_tick_t = tick_t

        def enable_fog_field(self):
            if self.fog_on:
                return
            self.fog_on = True
            spawned = 0
            tried = 0
            while spawned < game.FOG_LANTERN_COUNT and tried < 200:
                tried += 1
                gx = random.randint(2, game.GRID_SIZE - 3)
                gy = random.randint(2, game.GRID_SIZE - 3)
                if (gx, gy) in self.obstacles:
                    continue
                self.obstacles[gx, gy] = game.FogLantern(gx, gy)
                spawned += 1
            if spawned > 0:
                self.mark_nav_dirty()

        def disable_fog_field(self):
            if not self.fog_on:
                return
            self.fog_on = False
            removed = False
            for gp, ob in list(self.obstacles.items()):
                if getattr(ob, 'type', '') == 'Lantern':
                    del self.obstacles[gp]
                    removed = True
            if removed:
                self.mark_nav_dirty()

        def request_fog_field(self, player=None):
            """首次启动雾场 & 刷新灯笼。player 可选（首次刷 Boss 时可能还没 self.player）。"""
            if getattr(self, '_fog_inited', False):
                return
            self._fog_inited = True
            self.fog_enabled = True
            if not hasattr(self, 'fog_lanterns'):
                self.fog_lanterns = []
            self.spawn_fog_lanterns(player)

        def spawn_fog_lanterns(self, player=None):
            """把 FOG_LANTERN_COUNT 个灯笼刷在可走格上，尽量离玩家远；无玩家时以地图中心为基准。"""
            if not hasattr(self, 'fog_lanterns'):
                self.fog_lanterns = []
            self.fog_lanterns.clear()
            taken = set(self.obstacles.keys()) | {(it.x, it.y) for it in getattr(self, 'items', [])}
            if player is None and hasattr(self, 'player'):
                player = self.player
            if player is not None and hasattr(player, 'rect'):
                px = int(player.rect.centerx // game.CELL_SIZE)
                py = int((player.rect.centery - game.INFO_BAR_HEIGHT) // game.CELL_SIZE)
            else:
                px = game.GRID_SIZE // 2
                py = game.GRID_SIZE // 2
            cells = [(x, y) for y in range(game.GRID_SIZE) for x in range(game.GRID_SIZE) if (x, y) not in taken and abs(x - px) + abs(y - py) >= 6]
            random.shuffle(cells)
            want = int(game.FOG_LANTERN_COUNT)
            for _ in range(want):
                if not cells:
                    break
                gx, gy = cells.pop()
                lan = game.FogLantern(gx, gy, hp=game.FOG_LANTERN_HP)
                self.fog_lanterns.append(lan)
                self.obstacles[gx, gy] = lan

        def draw_lanterns_iso(self, screen, camx, camy):
            for lan in list(self.fog_lanterns):
                if not lan.alive:
                    continue
                gx, gy = lan.grid_pos
                sx, sy = game.iso_world_to_screen(gx + 0.5, gy + 0.5, 0, camx, camy)
                glow = pygame.Surface((int(game.CELL_SIZE * 2.2), int(game.CELL_SIZE * 1.4)), pygame.SRCALPHA)
                pygame.draw.ellipse(glow, (255, 240, 120, 90), glow.get_rect())
                screen.blit(glow, glow.get_rect(center=(int(sx), int(sy + 6))).topleft)
                body = pygame.Rect(0, 0, int(game.CELL_SIZE * 0.55), int(game.CELL_SIZE * 0.55))
                body.center = (int(sx), int(sy - 4))
                pygame.draw.rect(screen, (255, 230, 120), body, border_radius=6)
                pygame.draw.rect(screen, (120, 80, 20), body, 2, border_radius=6)

        def draw_lanterns_topdown(self, screen, camx, camy):
            for lan in list(self.fog_lanterns):
                if not lan.alive:
                    continue
                gx, gy = lan.grid_pos
                cx = int(gx * game.CELL_SIZE + game.CELL_SIZE * 0.5 - camx)
                cy = int(gy * game.CELL_SIZE + game.CELL_SIZE * 0.5 + game.INFO_BAR_HEIGHT - camy)
                body = pygame.Rect(0, 0, int(game.CELL_SIZE * 0.55), int(game.CELL_SIZE * 0.55))
                body.center = (cx, cy)
                pygame.draw.rect(screen, (255, 230, 120), body, border_radius=6)
                pygame.draw.rect(screen, (120, 80, 20), body, 2, border_radius=6)

        def draw_paint_iso(self, screen, cam_x, cam_y):
            corners = (game.iso_screen_to_world_px(0, 0, cam_x, cam_y), game.iso_screen_to_world_px(game.VIEW_W, 0, cam_x, cam_y), game.iso_screen_to_world_px(0, game.VIEW_H, cam_x, cam_y), game.iso_screen_to_world_px(game.VIEW_W, game.VIEW_H, cam_x, cam_y))
            min_x = min((p[0] for p in corners))
            max_x = max((p[0] for p in corners))
            min_y = min((p[1] for p in corners))
            max_y = max((p[1] for p in corners))
            pad_px = int(game.CELL_SIZE * 2)
            min_x -= pad_px
            max_x += pad_px
            min_y -= pad_px
            max_y += pad_px
            margin = 2
            gx_min = max(0, int(min_x // game.CELL_SIZE) - margin)
            gx_max = min(game.GRID_SIZE - 1, int(max_x // game.CELL_SIZE) + margin)
            gy_min = max(0, int((min_y - game.INFO_BAR_HEIGHT) // game.CELL_SIZE) - margin)
            gy_max = min(game.GRID_SIZE - 1, int((max_y - game.INFO_BAR_HEIGHT) // game.CELL_SIZE) + margin)
            hell = getattr(self, 'biome_active', None) == 'Scorched Hell'
            static_enemy = hell and game.HELL_ENEMY_PAINT_STATIC
            curing_paint = getattr(self, 'curing_paint', ())
            anim_start = 0
            recent_paints = None
            if hell and curing_paint:
                lifetime = float(self.player_paint_lifetime())
                denom = max(0.01, float(game.CURING_PAINT_SPAWN_INTERVAL))
                anim_limit = max(6, int(math.ceil(lifetime / denom)))
                anim_start = max(0, len(curing_paint) - anim_limit)
                recent_paints = set(curing_paint[anim_start:])
            if hasattr(self, 'paint_active') and hasattr(self, 'paint_grid'):
                for gx, gy in getattr(self, 'paint_active', ()):
                    if gx < gx_min or gx > gx_max or gy < gy_min or (gy > gy_max):
                        continue
                    if not (0 <= gx < game.GRID_SIZE and 0 <= gy < game.GRID_SIZE):
                        continue
                    tile = self.paint_grid[gy][gx]
                    if getattr(tile, 'paint_owner', 0) != 2:
                        continue
                    game.draw_enemy_paint_tile_iso(screen, gx, gy, tile, cam_x, cam_y, static=static_enemy)
            paint_bins = getattr(self, '_curing_paint_bins', {})
            if paint_bins:
                for gx in range(gx_min, gx_max + 1):
                    for gy in range(gy_min, gy_max + 1):
                        for p in paint_bins.get((gx, gy), []):
                            if p.x < min_x or p.x > max_x or p.y < min_y or (p.y > max_y):
                                continue
                            tile = self.paint_tile_at_world(p.x, p.y)
                            if tile is not None and getattr(tile, 'paint_owner', 0) != 1:
                                continue
                            static_paint = bool(hell and recent_paints is not None and (p not in recent_paints))
                            game.draw_curing_paint_iso(screen, p, cam_x, cam_y, static=static_paint)
            else:
                for idx, p in enumerate(curing_paint):
                    if p.x < min_x or p.x > max_x or p.y < min_y or (p.y > max_y):
                        continue
                    tile = self.paint_tile_at_world(p.x, p.y)
                    if tile is not None and getattr(tile, 'paint_owner', 0) != 1:
                        continue
                    game.draw_curing_paint_iso(screen, p, cam_x, cam_y, static=hell and idx < anim_start)

        def draw_hazards_iso(self, screen, cam_x, cam_y):
            for p in list(getattr(self, 'aegis_pulses', [])):
                life0 = max(0.001, float(getattr(p, 'life0', game.AEGIS_PULSE_TTL)))
                fade = max(0.0, min(1.0, float(getattr(p, 't', 0.0)) / life0))
                game.draw_iso_hex_ring(screen, p.x, p.y, p.r, game.AEGIS_PULSE_COLOR, int(game.AEGIS_PULSE_RING_ALPHA * fade), cam_x, cam_y, sides=6, fill_alpha=int(game.AEGIS_PULSE_FILL_ALPHA * fade), width=3)
            for a in list(getattr(self, 'acids', [])):
                style = getattr(a, 'style', 'acid')
                st = game.HAZARD_STYLES.get(style, game.HAZARD_STYLES.get('acid', {'fill': (90, 255, 120), 'ring': (30, 160, 60)}))
                life0 = max(0.001, float(getattr(a, 'life0', getattr(a, 't', 1.0))))
                alpha = int(150 * max(0.15, min(1.0, a.t / life0)))
                game.draw_iso_ground_ellipse(screen, a.x, a.y, a.r, st['fill'], alpha, cam_x, cam_y, fill=True)
                game.draw_iso_ground_ellipse(screen, a.x, a.y, a.r, st['ring'], 180, cam_x, cam_y, fill=False, width=2)
            for s in list(getattr(self, 'ground_spikes', [])):
                game.draw_ground_spike_iso(screen, s, cam_x, cam_y)

        def draw_fog_overlay(self, screen, camx, camy, player, obstacles):
            """在世界层上方绘制一层‘黑雾’，对玩家与灯笼的范围挖透明洞。"""
            if not self.fog_enabled:
                return
            w, h = screen.get_size()
            mask = pygame.Surface((w, h), pygame.SRCALPHA)
            mask.fill((0, 0, 0, game.FOG_OVERLAY_ALPHA))
            clear_r = game.FOG_VIEW_TILES * game.CELL_SIZE
            psx, psy = game.iso_world_to_screen(player.rect.centerx / game.CELL_SIZE, (player.rect.centery - game.INFO_BAR_HEIGHT) / game.CELL_SIZE, 0, camx, camy)
            pygame.draw.circle(mask, (0, 0, 0, 0), (int(psx), int(psy)), int(clear_r))
            for lan in self.fog_lanterns:
                if not lan.alive:
                    continue
                gx, gy = lan.grid_pos
                sx, sy = game.iso_world_to_screen(gx + 0.5, gy + 0.5, 0, camx, camy)
                pygame.draw.circle(mask, (0, 0, 0, 0), (int(sx), int(sy)), int(game.FOG_LANTERN_CLEAR_RADIUS))
            self._fog_pulse_t = (self._fog_pulse_t + 0.016) % 1.0
            pulse = int(14 * (0.5 + 0.5 * math.sin(self._fog_pulse_t * math.tau)))
            if pulse > 0:
                edge = pygame.Surface((w, h), pygame.SRCALPHA)
                edge.fill((220, 220, 240, pulse))
                mask.blit(edge, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
            screen.blit(mask, (0, 0))
    game.__dict__.update({'GameState': GameState})
    return GameState
