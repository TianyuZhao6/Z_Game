"""Player projectile classes extracted from ZGame.py."""
from __future__ import annotations
import math
import random
from typing import List
import pygame
from zgame import runtime_state as rs

def install(game):
    meta = rs.meta(game)

    class Bullet:

        def __init__(self, x: float, y: float, vx: float, vy: float, max_dist: float=game.MAX_FIRE_RANGE, damage: int=game.BULLET_DAMAGE_ENEMY, source: str='player'):
            self.x = x
            self.y = y
            self.vx = vx
            self.vy = vy
            self.alive = True
            self.traveled = 0.0
            self.max_dist = game.clamp_player_range(max_dist)
            self.damage = int(damage)
            self.r = game.bullet_radius_for_damage(self.damage)
            self.source = source

        def update(self, dt: float, game_state: 'GameState', enemies: List['Enemy'], player: 'Player'=None):
            if not self.alive:
                return
            if hasattr(game, "verify_bullet_runtime") and (not game.verify_bullet_runtime(self, player)):
                return
            nx = self.x + self.vx * dt
            ny = self.y + self.vy * dt
            self.traveled += ((nx - self.x) ** 2 + (ny - self.y) ** 2) ** 0.5
            self.x, self.y = (nx, ny)
            if self.traveled >= self.max_dist:
                self.alive = False
                return
            if hasattr(game, "verify_bullet_runtime") and (not game.verify_bullet_runtime(self, player)):
                return
            _rr = int(getattr(self, 'r', game.BULLET_RADIUS))
            r = pygame.Rect(int(self.x - _rr), int(self.y - _rr), _rr * 2, _rr * 2)
            spatial = getattr(game_state, 'spatial', None)
            if spatial:
                cached_r = int(getattr(game_state, 'spatial_query_radius', 0) or 0)
                if cached_r <= 0:
                    if player is not None:
                        cached_r = int(game.clamp_player_range(getattr(player, 'range', game.PLAYER_RANGE_DEFAULT)))
                    else:
                        cached_r = int(game.PLAYER_RANGE_MAX)
                query_r = max(_rr, cached_r)
                nearby_enemies = spatial.query_circle(self.x, self.y, query_r)
            else:
                nearby_enemies = list(enemies)

            def try_ricochet(hit_x: float, hit_y: float) -> bool:
                """Try to bounce this bullet toward the nearest enemy. Return True if bounced."""
                if getattr(self, 'source', 'player') != 'player':
                    return False
                remaining = int(getattr(self, 'ricochet_left', 0))
                if remaining <= 0:
                    return False
                target = None
                best_d2 = None
                for z in enemies:
                    if getattr(z, 'hp', 0) <= 0:
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
                speed = (self.vx * self.vx + self.vy * self.vy) ** 0.5 or game.BULLET_SPEED
                self.vx = dx / L * speed
                self.vy = dy / L * speed
                self.x = hit_x
                self.y = hit_y
                self.ricochet_left = remaining - 1
                return True
            for z in list(nearby_enemies):
                if r.colliderect(z.rect):
                    crit_p = float(getattr(player, 'crit_chance', game.CRIT_CHANCE_BASE))
                    crit_m = float(getattr(player, 'crit_mult', game.CRIT_MULT_BASE))
                    is_crit = random.random() < max(0.0, min(0.99, crit_p))
                    base = int(self.damage)
                    dealt = int(round(base * (crit_m if is_crit else 1.0)))
                    cx, cy = (z.rect.centerx, z.rect.centery)
                    if getattr(z, 'type', '') == 'boss_mist':
                        if random.random() < game.MIST_PHASE_CHANCE:
                            game_state.add_damage_text(z.rect.centerx, z.rect.centery, 'TELEPORT', crit=False, kind='shield')
                            dx = z.rect.centerx - player.rect.centerx
                            dy = z.rect.centery - player.rect.centery
                            L = (dx * dx + dy * dy) ** 0.5 or 1.0
                            ox = dx / L * (game.MIST_PHASE_TELE_TILES * game.CELL_SIZE)
                            oy = dy / L * (game.MIST_PHASE_TELE_TILES * game.CELL_SIZE)
                            z.x += ox
                            z.y += oy - game.INFO_BAR_HEIGHT
                            z.rect.x = int(z.x)
                            z.rect.y = int(z.y + game.INFO_BAR_HEIGHT)
                            self.alive = False
                            return
                        dist_tiles = math.hypot((z.rect.centerx - self.x) / game.CELL_SIZE, (z.rect.centery - self.y) / game.CELL_SIZE)
                        if dist_tiles >= game.MIST_RANGED_REDUCE_TILES:
                            dealt = int(dealt * game.MIST_RANGED_MULT)
                    dealt = game.apply_vuln_bonus(z, dealt)
                    hp_before = z.hp
                    if getattr(z, 'shield_hp', 0) > 0:
                        blocked = min(dealt, z.shield_hp)
                        z.shield_hp -= dealt
                        game_state.add_damage_text(cx, cy, blocked, crit=is_crit, kind='shield')
                        overflow = dealt - blocked
                        if z.shield_hp < 0:
                            pass
                        if overflow > 0:
                            z.hp -= overflow
                            game_state.add_damage_text(cx, cy - 10, overflow, crit=is_crit, kind='hp_player')
                    else:
                        z.hp -= dealt
                        game_state.add_damage_text(cx, cy, dealt, crit=is_crit, kind='hp_player')
                    hp_lost = max(0, hp_before - max(z.hp, 0))
                    if hp_lost > 0:
                        z._hit_flash = float(game.HIT_FLASH_DURATION)
                        z._flash_prev_hp = int(max(0, z.hp))
                    if getattr(self, 'source', 'player') == 'player':
                        dot_lvl = int(meta.get('dot_rounds_level', 0))
                        if dot_lvl > 0:
                            if player is not None:
                                bullet_base = int(getattr(player, 'bullet_damage', base))
                            else:
                                bullet_base = int(meta.get('base_dmg', game.BULLET_DAMAGE_ENEMY)) + int(meta.get('dmg', 0))
                            dmg_per_tick, duration, max_stacks = game.dot_rounds_stats(dot_lvl, bullet_base)
                            game.apply_dot_rounds_stack(z, dmg_per_tick, duration, max_stacks)
                            game.spawn_dot_rounds_hit_vfx(game_state, cx, cy)
                    if z.hp > 0:
                        if getattr(self, 'source', 'player') == 'player':
                            used_ricochet = False
                            if try_ricochet(cx, cy):
                                used_ricochet = True
                            remaining_pierce = int(getattr(self, 'pierce_left', 0))
                            if remaining_pierce > 0:
                                self.pierce_left = remaining_pierce - 1
                                break
                            if used_ricochet:
                                break
                        self.alive = False
                        return
                    if z.hp <= 0 and (not getattr(z, '_death_processed', False)):
                        z._death_processed = True
                        game.increment_kill_count()
                        cx, cy = (z.rect.centerx, z.rect.centery)
                        if int(meta.get('explosive_rounds_level', 0)) > 0:
                            if getattr(z, 'is_boss', False):
                                game_state.fx.spawn_explosion(cx, cy, (255, 100, 50), count=150)
                            else:
                                game_state.fx.spawn_explosion(cx, cy, z.color, count=25)
                        game._bandit_death_notice(z, game_state)
                        shrap_lvl = int(meta.get('shrapnel_level', 0))
                        if shrap_lvl > 0 and hp_lost > 0 and (getattr(self, 'source', 'player') == 'player'):
                            base_chance = 0.25
                            per_level = 0.1
                            chance = min(0.8, base_chance + per_level * (shrap_lvl - 1))
                            if random.random() < chance:
                                count = random.randint(3, 4)
                                shrap_dmg = max(1, int(round(hp_lost * 0.4)))
                                for _ in range(count):
                                    ang = random.uniform(0.0, 2.0 * math.pi)
                                    speed = game.BULLET_SPEED * 0.85
                                    vx = math.cos(ang) * speed
                                    vy = math.sin(ang) * speed
                                    sb = game.Bullet(cx, cy, vx, vy, max_dist=player.range * 0.5, damage=shrap_dmg, source='player')
                                    sb.pierce_left = 0
                                    sb.ricochet_left = 0
                                    sb.is_shrapnel = True
                                    if not hasattr(game_state, 'pending_bullets'):
                                        game_state.pending_bullets = []
                                    game_state.pending_bullets.append(sb)
                        if getattr(self, 'source', 'player') == 'player' and player is not None:
                            bullet_base = int(getattr(player, 'bullet_damage', base))
                            game.trigger_explosive_rounds(player, game_state, enemies, (cx, cy), bullet_base=bullet_base)
                        if getattr(z, 'is_boss', False) and getattr(z, 'twin_id', None) is not None:
                            game.trigger_twin_enrage(z, enemies, game_state)
                    if z.hp <= 0:
                        if getattr(z, '_can_split', False) and (not getattr(z, '_split_done', False)) and (getattr(z, 'type', '') == 'splinter'):
                            z._split_done = True
                            z._can_split = False
                            game.spawn_splinter_children(z, enemies, game_state, level_idx=0, wave_index=0)
                            if z in enemies:
                                enemies.remove(z)
                            self.alive = False
                            return
                        elif getattr(z, 'type', '') == 'bandit':
                            stolen = int(getattr(z, '_stolen_total', 0))
                            bonus = int(stolen * game.BANDIT_BONUS_RATE) + int(game.BANDIT_BONUS_FLAT) if stolen > 0 else 0
                            refund = stolen + bonus
                            if not getattr(z, '_bandit_notice_done', False):
                                game._bandit_death_notice(z, game_state)
                            if refund > 0:
                                game_state.spawn_spoils(cx, cy, refund)
                            if meta.get('wanted_active', False):
                                bounty = int(game.WANTED_POSTER_BOUNTY_BASE + stolen * 1.0)
                                meta['spoils'] = int(meta.get('spoils', 0)) + bounty
                                meta['wanted_active'] = False
                                meta['wanted_poster_waves'] = 0
                                game_state.wanted_wave_active = False
                                game_state.flash_banner(f'Bounty Claimed! +{bounty}', sec=1.0)
                                game_state.add_damage_text(z.rect.centerx, z.rect.centery, f'+{bounty}', crit=True, kind='hp')
                            if player:
                                base_xp = game.XP_PER_ENEMY_TYPE.get('bandit', game.XP_PLAYER_KILL)
                                player.add_xp(base_xp)
                                setattr(z, '_xp_awarded', True)
                            game.transfer_xp_to_neighbors(z, enemies)
                            if z in enemies:
                                enemies.remove(z)
                            if getattr(self, 'source', 'player') == 'player':
                                used_ricochet = False
                                if try_ricochet(cx, cy):
                                    used_ricochet = True
                                remaining_pierce = int(getattr(self, 'pierce_left', 0))
                                if remaining_pierce > 0:
                                    self.pierce_left = remaining_pierce - 1
                                    break
                                if used_ricochet:
                                    break
                            self.alive = False
                            return
                        else:
                            drop_n = game.roll_spoils_for_enemy(z)
                            drop_n += int(getattr(z, 'spoils', 0))
                            if drop_n > 0:
                                game_state.spawn_spoils(cx, cy, drop_n)
                            if getattr(z, 'is_boss', False):
                                for _ in range(game.BOSS_HEAL_POTIONS):
                                    game_state.spawn_heal(cx, cy, game.HEAL_POTION_AMOUNT)
                            elif random.random() < game.HEAL_DROP_CHANCE_ENEMY:
                                game_state.spawn_heal(cx, cy, game.HEAL_POTION_AMOUNT)
                            if player:
                                base_xp = game.XP_PER_ENEMY_TYPE.get(getattr(z, 'type', 'basic'), game.XP_PLAYER_KILL)
                                bonus = max(0, z.z_level - 1) * game.XP_ZLEVEL_BONUS
                                extra_by_spoils = int(getattr(z, 'spoils', 0)) * int(game.Z_SPOIL_XP_BONUS_PER)
                                if getattr(z, 'is_elite', False):
                                    base_xp = int(base_xp * 1.5)
                                if getattr(z, 'is_boss', False):
                                    base_xp = int(base_xp * 3.0)
                                player.add_xp(base_xp + bonus + extra_by_spoils)
                                setattr(z, '_xp_awarded', True)
                                if getattr(z, 'is_boss', False):
                                    game.trigger_twin_enrage(z, enemies, game_state)
                            game.transfer_xp_to_neighbors(z, enemies)
                            if z in enemies:
                                enemies.remove(z)
                            if getattr(self, 'source', 'player') == 'player':
                                used_ricochet = False
                                if try_ricochet(cx, cy):
                                    used_ricochet = True
                                remaining_pierce = int(getattr(self, 'pierce_left', 0))
                                if remaining_pierce > 0:
                                    self.pierce_left = remaining_pierce - 1
                                    break
                                if used_ricochet:
                                    break
                            self.alive = False
                            return
            for gp, ob in list(game_state.obstacles.items()):
                if r.colliderect(ob.rect):
                    hit_x, hit_y = (self.x, self.y)
                    if ob.type == 'Lantern':
                        if getattr(self, 'source', 'player') == 'player' and try_ricochet(hit_x, hit_y):
                            break
                        self.alive = False
                        return
                    elif ob.type == 'Indestructible':
                        if getattr(self, 'source', 'player') == 'player' and try_ricochet(hit_x, hit_y):
                            break
                        self.alive = False
                        return
                    elif ob.type == 'Destructible':
                        ob.health = (ob.health or 0) - game.BULLET_DAMAGE_BLOCK
                        if ob.health <= 0:
                            cx, cy = (ob.rect.centerx, ob.rect.centery)
                            del game_state.obstacles[gp]
                            if hasattr(game_state, 'mark_nav_dirty'):
                                game_state.mark_nav_dirty()
                            if random.random() < game.SPOILS_BLOCK_DROP_CHANCE:
                                game_state.spawn_spoils(cx, cy, 1)
                            if player:
                                player.add_xp(game.XP_PLAYER_BLOCK)
                        if getattr(self, 'source', 'player') == 'player' and try_ricochet(hit_x, hit_y):
                            break
                        self.alive = False
                        return
            if (self.vx * self.vx + self.vy * self.vy) <= 1e-6:
                # Allow one-frame overlap hits for spawned-on-target tests and
                # edge cases, but do not let zero-velocity bullets linger.
                self.alive = False
                return

        def draw(self, screen, cam_x, cam_y):
            src = getattr(self, 'source', 'player')
            if src == 'turret':
                color = (0, 255, 255)
            else:
                color = (255, 255, 255)
            pygame.draw.circle(screen, color, (int(self.x - cam_x), int(self.y - cam_y)), int(getattr(self, 'r', game.BULLET_RADIUS)))
    game.__dict__.update({'Bullet': Bullet})
    return Bullet
