"""
Vampire-Survivors–like prototype in Pygame
- Pixel-art style via low-res render surface
- Player/monsters both earn XP and level up
- Special enemies (elites/bosses) redistribute a large portion of their accumulated XP to all surviving enemies when killed (inheritance)
- Enemies also gain XP by destroying scene obstacles
- End-of-wave shop with pseudo-random items purchasable using loot dropped from combat/destruction
- Normal game features: homepage, pause (ESC) panel, rollback (reload checkpoint at wave start), BGM hooks

This file is a single-file prototype with no external assets required. If you put an
audio file at ./bgm.ogg it will play as background music.

Tested against pygame 2.5+. Python 3.10+
"""
from __future__ import annotations
import math
import os
import json
import random
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional

import pygame

# ------------------------------ Config ---------------------------------
WIDTH, HEIGHT = 960, 540         # window size
VW, VH = 320, 180                # virtual low-res surface for pixel look (scaled up)
SCALE_X, SCALE_Y = WIDTH / VW, HEIGHT / VH
FPS = 60

# Gameplay
WAVE_OBSTACLES = (8, 14)         # range of obstacles per wave
ENEMY_BASE_COUNT = (10, 16)      # range of enemies per normal wave
BOSS_WAVE_EVERY = 5
SPECIAL_XP_REDISTRIB_RATIO = 0.7 # 70% of special's XP redistributed to survivors
GENERIC_ENEMY_XP_REDISTRIB_RATIO = 0.6 # generic death XP redistribution
NON_BOSS_RADIUS_CAP = 8.0
ENEMY_BASE_XP = {
    "melee": 12.0,
    "ranged": 10.0,
    "suicide": 8.0,
    "buffer": 10.0,
    "boss": 30.0,
}
PLAYER_START_LOOT = 0
RUN_SAVE_FILE = "savegame.json"
# Spawning and timing
MIN_ENEMY_SPAWN_DIST = 50
CENTER_SAFE_RADIUS = 12
FIRST_WAVE_SILENCE = 0.6
NORMAL_WAVE_TIME = 30
BOSS_WAVE_TIME_BASE = 45
BOSS_WAVE_TIME_STEP = 5  # each subsequent boss wave +5s

# Elite rewards
ELITE_XP_THRESHOLD = 40.0
ELITE_KILL_BONUS_NORMAL = 4
ELITE_KILL_BONUS_SPECIAL = 6

# Colors
WHITE=(255,255,255); BLACK=(0,0,0); GRAY=(80,80,80); DARKGRAY=(30,30,30);
RED=(200,60,60); GREEN=(60,200,60); BLUE=(60,60,200); YELLOW=(230,210,70);
ORANGE=(245,140,40); CYAN=(60,200,200); MAGENTA=(200,60,200)
OBST_COLOR   = (90, 90, 120)
OBST_OUTLINE = (220, 220, 240)

# Utility
Vec2 = pygame.math.Vector2


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

# ---- Collision helpers ----
def closest_point_on_rect(rect: pygame.Rect, p: Vec2) -> Vec2:
    return Vec2(clamp(p.x, rect.left, rect.right), clamp(p.y, rect.top, rect.bottom))

def circle_rect_intersect(p: Vec2, r: float, rect: pygame.Rect) -> bool:
    q = closest_point_on_rect(rect, p)
    return p.distance_to(q) <= r

def resolve_circle_rect(p: Vec2, r: float, rect: pygame.Rect) -> Vec2:
    # If center inside rect, push toward nearest edge
    if rect.collidepoint(int(p.x), int(p.y)):
        left = abs(p.x - rect.left)
        right = abs(rect.right - p.x)
        top = abs(p.y - rect.top)
        bottom = abs(rect.bottom - p.y)
        m = min(left, right, top, bottom)
        if m == left:
            p.x = rect.left - r
        elif m == right:
            p.x = rect.right + r
        elif m == top:
            p.y = rect.top - r
        else:
            p.y = rect.bottom + r
        return p
    # Otherwise push out from closest point if overlapping
    q = closest_point_on_rect(rect, p)
    d = p - q
    dist = d.length()
    if dist < r and dist != 0:
        p += d.normalize() * (r - dist)
    return p

# --------------------------- Stats & Items ------------------------------
@dataclass
class Stats:
    max_hp: float = 80
    hp: float = 80
    speed: float = 1.6
    damage: float = 4
    attack_cooldown: float = 0.7  # seconds
    projectile_speed: float = 100
    crit_chance: float = 0.03
    crit_mult: float = 1.8
    regen: float = 0.15           # hp/s
    range: float = 50

    def to_dict(self):
        return asdict(self)

    def apply_level(self, lvl: int):
        # Basic scaling on level up
        self.max_hp *= 1.05
        self.hp = min(self.max_hp, self.hp + self.max_hp * 0.25)
        self.damage *= 1.06
        self.speed *= 1.02
        self.range *= 1.02
        self.regen *= 1.04
        self.attack_cooldown *= 0.99

# --------------------------- Entities ----------------------------------
class Entity:
    def __init__(self, pos: Tuple[float,float], radius: float, color: Tuple[int,int,int]):
        self.pos = Vec2(pos)
        self.radius = radius
        self.color = color
        self.alive = True
        self.xp: float = 0.0
        self.xp_total: float = 0.0
        self.level: int = 1
        self.xp_next: float = 25.0

    def gain_xp(self, amount: float):
        if amount <= 0: return
        self.xp_total += amount
        self.xp += amount
        while self.xp >= self.xp_next:
            self.xp -= self.xp_next
            self.level += 1
            self.on_level_up()
            self.xp_next *= 1.35

    def on_level_up(self):
        pass

    def update(self, dt: float):
        pass

    def draw(self, surf: pygame.Surface):
        pygame.draw.circle(surf, self.color, self.pos, self.radius)

    def dist_to(self, other: Entity) -> float:
        return self.pos.distance_to(other.pos)


class Projectile:
    def __init__(self, pos: Vec2, vel: Vec2, damage: float, owner_is_player: bool, color: Tuple[int,int,int]=YELLOW, radius: int=2):
        self.pos = Vec2(pos)
        self.vel = Vec2(vel)
        self.damage = damage
        self.owner_is_player = owner_is_player
        self.color = color
        self.radius = radius
        self.alive = True
        self.life = 2.5  # seconds

    def update(self, dt: float):
        self.pos += self.vel * dt
        self.life -= dt
        if self.life <= 0:
            self.alive = False

    def draw(self, surf: pygame.Surface):
        pygame.draw.circle(surf, self.color, self.pos, self.radius)


class Pickup:
    def __init__(self, pos: Vec2, kind: str='heal', amount: float=20, radius: int=3):
        self.pos = Vec2(pos)
        self.kind = kind
        self.amount = amount
        self.radius = radius
        self.alive = True

    def draw(self, surf: pygame.Surface):
        pygame.draw.circle(surf, (120, 230, 120), self.pos, self.radius+1)
        pygame.draw.circle(surf, (30, 80, 30), self.pos, self.radius, 1)

class Obstacle:
    def __init__(self, rect: pygame.Rect, hp: float=40, loot_value: int=2, xp_value: float=6.0):
        self.rect = rect
        self.max_hp = hp
        self.hp = hp
        self.loot_value = loot_value
        self.xp_value = xp_value
        self.alive = True
        self.last_attacker_enemy: Optional[Enemy] = None
        self.dropped = False

    def take_damage(self, amount: float, attacker_enemy: Optional['Enemy']):
        if not self.alive: return
        self.hp -= amount
        if attacker_enemy:
            self.last_attacker_enemy = attacker_enemy
        if self.hp <= 0:
            self.alive = False

    def draw(self, surf: pygame.Surface):
        if not self.alive: return
        # shadow + fill + outline for better visibility
        shadow = pygame.Rect(self.rect.x + 1, self.rect.y + 1, self.rect.w, self.rect.h)
        pygame.draw.rect(surf, BLACK, shadow)
        pygame.draw.rect(surf, OBST_COLOR, self.rect)
        pygame.draw.rect(surf, OBST_OUTLINE, self.rect, 1)
        # hp bar
        w = int(self.rect.w * clamp(self.hp/self.max_hp, 0, 1))
        pygame.draw.rect(surf, RED,   pygame.Rect(self.rect.x, self.rect.y-3, self.rect.w, 3))
        pygame.draw.rect(surf, GREEN, pygame.Rect(self.rect.x, self.rect.y-3, w,             3))

# --------------------------- Player ------------------------------------
class Player(Entity):
    def __init__(self, pos: Tuple[float,float]):
        super().__init__(pos, radius=4, color=CYAN)
        self.stats = Stats()
        self.stats.hp = self.stats.max_hp
        self.fire_cd = 0.0
        self.loot: int = PLAYER_START_LOOT
        self.move_dir = Vec2(0,0)

    def handle_input(self, keys):
        self.move_dir.xy = 0,0
        if keys[pygame.K_w] or keys[pygame.K_UP]: self.move_dir.y = -1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]: self.move_dir.y = 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]: self.move_dir.x = -1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: self.move_dir.x = 1
        if self.move_dir.length_squared() > 0:
            self.move_dir = self.move_dir.normalize()

    def try_fire(self, dt: float, enemies: List['Enemy']) -> List[Projectile]:
        shots: List[Projectile] = []
        self.fire_cd -= dt
        if self.fire_cd > 0 or not enemies:
            return shots
        # auto target nearest enemy
        target = min(enemies, key=lambda e: self.dist_to(e))
        to = (target.pos - self.pos)
        dist = to.length() or 1
        if dist <= self.stats.range:
            vel = to.normalize() * self.stats.projectile_speed
            dmg = self.stats.damage
            # crit
            if random.random() < self.stats.crit_chance:
                dmg *= self.stats.crit_mult
            shots.append(Projectile(self.pos, vel, dmg, owner_is_player=True))
            self.fire_cd = self.stats.attack_cooldown
        return shots

    def take_damage(self, dmg: float):
        self.stats.hp -= dmg
        if self.stats.hp <= 0:
            self.alive = False

    def on_level_up(self):
        self.stats.apply_level(self.level)

    def update(self, dt: float):
        # regen
        self.stats.hp = clamp(self.stats.hp + self.stats.regen*dt, 0, self.stats.max_hp)
        # movement
        self.pos += self.move_dir * (self.stats.speed * 60) * dt
        # bounds (inside virtual area)
        self.pos.x = clamp(self.pos.x, 8, VW-8)
        self.pos.y = clamp(self.pos.y, 8, VH-8)

# --------------------------- Enemies -----------------------------------
class Enemy(Entity):
    KIND_MELEE = "melee"
    KIND_RANGED = "ranged"
    KIND_SUICIDE = "suicide"
    KIND_BUFFER = "buffer"
    KIND_BOSS = "boss"

    def __init__(self, pos: Tuple[float,float], kind: str, special: bool=False):
        color = RED if not special else ORANGE
        if kind == Enemy.KIND_BUFFER: color = MAGENTA
        if kind == Enemy.KIND_RANGED: color = YELLOW
        if kind == Enemy.KIND_SUICIDE: color = BLUE
        if kind == Enemy.KIND_BOSS: color = (255,120,120)
        super().__init__(pos, radius=4 if kind!=Enemy.KIND_BOSS else 8, color=color)
        self.kind = kind
        self.special = special
        # base stats per kind
        self.max_hp = 40
        self.hp = self.max_hp
        self.speed = 0.75
        self.damage = 6
        self.melee_range = 6
        self.attack_cd = 0.8
        self.fire_cd = 1.2
        self.projectile_speed = 90
        self.buff_radius = 40
        self.buff_mult = 1.2
        if kind == Enemy.KIND_RANGED:
            self.max_hp, self.hp = 30, 30
            self.projectile_speed = 95
            self.attack_cd = 0.0
            self.fire_cd = 1.0
            self.speed = 0.65
        elif kind == Enemy.KIND_SUICIDE:
            self.max_hp, self.hp = 20, 20
            self.speed = 0.85
            self.melee_range = 8
            self.damage = 14
        elif kind == Enemy.KIND_BUFFER:
            self.max_hp, self.hp = 35, 35
            self.speed = 0.6
        elif kind == Enemy.KIND_BOSS:
            self.max_hp, self.hp = 220, 220
            self.speed = 1.0
            self.damage = 10
            self.melee_range = 10
            self.fire_cd = 0.9
            self.projectile_speed = 110
        if self.special:
            self.max_hp *= 1.6
            self.hp = self.max_hp
            self.damage *= 1.4
            self.speed *= 1.05
        self._atk_timer = 0.0
        self._fire_timer = 0.0
        self.spawn_silence = 0.0
        # baseline XP per kind -> immediate minor scaling so even不打障碍也会成长
        try:
            base_xp = ENEMY_BASE_XP.get(self.kind, 10.0)
            self.gain_xp(base_xp)
        except Exception:
            pass

    def apply_xp_scaling(self, amount: float):
        """Continuous, kind-dependent scaling per XP gained. Also heals and grows size (visual)."""
        u = amount / 10.0  # normalize unit
        # default multipliers
        mhp = dmg = spd = proj = aura = 0.0
        if self.kind == Enemy.KIND_MELEE:
            mhp, dmg, spd = 0.015, 0.012, 0.006
        elif self.kind == Enemy.KIND_RANGED:
            mhp, dmg, spd, proj = 0.010, 0.010, 0.006, 0.008
        elif self.kind == Enemy.KIND_SUICIDE:
            mhp, dmg, spd = 0.008, 0.018, 0.010
        elif self.kind == Enemy.KIND_BUFFER:
            mhp, dmg, spd, aura = 0.012, 0.008, 0.005, 0.010
        elif self.kind == Enemy.KIND_BOSS:
            mhp, dmg, spd, proj = 0.010, 0.010, 0.004, 0.006
        # apply
        self.max_hp *= (1.0 + mhp * u)
        # heal on gain
        self.hp = min(self.max_hp, self.hp + self.max_hp * (0.05 * u))
        self.damage *= (1.0 + dmg * u)
        self.speed *= (1.0 + spd * u)
        if self.kind in (Enemy.KIND_RANGED, Enemy.KIND_BOSS) and proj:
            self.projectile_speed *= (1.0 + proj * u)
        if self.kind == Enemy.KIND_BUFFER and aura:
            self.buff_mult *= (1.0 + aura * u * 0.5)
            self.buff_mult = clamp(self.buff_mult, 1.0, 1.6)
        # visual growth with caps
        if self.kind != Enemy.KIND_BOSS:
            self.radius = min(self.radius + 0.3 * u, NON_BOSS_RADIUS_CAP)
        else:
            self.radius = min(self.radius + 0.2 * u, 14)
        # keep sane speed cap
        self.speed = min(self.speed, 1.5)

    def gain_xp(self, amount: float):
        if amount <= 0: return
        # continuous scaling and heal
        self.apply_xp_scaling(amount)
        # update counters and trigger level-ups (discrete bonuses)
        super().gain_xp(amount)

    def on_level_up(self):
        # modest scaling per enemy level
        self.max_hp *= 1.08
        self.hp = min(self.max_hp, self.hp + self.max_hp*0.2)
        self.damage *= 1.07
        self.speed *= 1.015
        self.speed = min(self.speed, 1.15)
        self.melee_range *= 1.01
        self.fire_cd = max(0.55, self.fire_cd*0.98)
        self.projectile_speed *= 1.02

    def take_damage(self, dmg: float):
        self.hp -= dmg
        if self.hp <= 0:
            self.alive = False

    def try_projectile(self, player: Player) -> List[Projectile]:
        shots: List[Projectile] = []
        if self.kind not in (Enemy.KIND_RANGED, Enemy.KIND_BOSS):
            return shots
        if self._fire_timer <= 0:
            to = player.pos - self.pos
            if to.length() <= 80 or self.kind == Enemy.KIND_BOSS:
                vel = to.normalize() * self.projectile_speed
                shots.append(Projectile(self.pos, vel, self.damage*0.8, owner_is_player=False, color=WHITE))
                self._fire_timer = self.fire_cd
        return shots

    def update(self, dt: float, player: Player, enemies: List['Enemy']):
        # spawn silence: freeze actions & movement briefly
        if getattr(self, 'spawn_silence', 0.0) > 0:
            self.spawn_silence = max(0.0, self.spawn_silence - dt)
            self._atk_timer -= dt
            self._fire_timer -= dt
            return
        # buff aura for buffer type
        if self.kind == Enemy.KIND_BUFFER:
            for e in enemies:
                if e is self or not e.alive: continue
                if self.dist_to(e) <= self.buff_radius:
                    e.speed *= self.buff_mult ** (dt*0.2)  # gentler aura
                    e.damage *= self.buff_mult ** (dt*0.1)
                    e.speed = min(e.speed, 1.15)
        # approach player
        to = player.pos - self.pos
        d = to.length() or 1
        desire = to / d
        preferred_range = 30 if self.kind == Enemy.KIND_RANGED else 4
        if self.kind == Enemy.KIND_RANGED and d < 36:
            desire *= -1  # kite away if too close
        self.pos += desire * (self.speed * 60) * dt
        self.pos.x = clamp(self.pos.x, 6, VW-6)
        self.pos.y = clamp(self.pos.y, 6, VH-6)
        self._atk_timer -= dt
        self._fire_timer -= dt

    def try_attack(self, dt: float, player: Player) -> Tuple[bool, float]:
        if self.kind == Enemy.KIND_RANGED:
            return False, 0
        acted = False
        dmg_out = 0
        if self._atk_timer <= 0 and self.dist_to(player) <= self.melee_range:
            acted, dmg_out = True, self.damage
            self._atk_timer = self.attack_cd
            if self.kind == Enemy.KIND_SUICIDE:
                # explode
                self.alive = False
        return acted, dmg_out

    def draw(self, surf: pygame.Surface):
        super().draw(surf)
        # tiny health bar
        w = 10 if self.kind != Enemy.KIND_BOSS else 24
        h = 2
        hp_ratio = clamp(self.hp/self.max_hp, 0, 1)
        bar = pygame.Rect(int(self.pos.x-w//2), int(self.pos.y-self.radius-6), w, h)
        pygame.draw.rect(surf, RED, bar)
        inner = pygame.Rect(bar.x, bar.y, int(w*hp_ratio), h)
        pygame.draw.rect(surf, GREEN, inner)

# --------------------------- Level / Shop -------------------------------
class PseudoRandomBag:
    """Simple pseudo-random bag to reduce streaks.
    Items are tuples (id, weight). Each draw samples by weight, then reduces selected weight
    slightly to promote variety across a single shop refresh.
    """
    def __init__(self, rng: random.Random, items: List[Tuple[str, float]]):
        self.rng = rng
        self.items = list(items)

    def draw_n(self, n: int) -> List[str]:
        out: List[str] = []
        pool = self.items.copy()
        for _ in range(min(n, len(pool))):
            total = sum(w for _, w in pool)
            r = self.rng.random() * total
            cum = 0
            for i,(iid,w) in enumerate(pool):
                cum += w
                if r <= cum:
                    out.append(iid)
                    # reduce its weight to reduce repeats in same refresh
                    pool[i] = (iid, max(0.1, w*0.5))
                    break
        return out

SHOP_DB = {
    # id: (name, cost, apply_func)
    "dmg_up": ("+Damage", 12, lambda pl: setattr(pl.stats, "damage", pl.stats.damage + 2)),
    "atkspd": ("+Attack Speed", 14, lambda pl: setattr(pl.stats, "attack_cooldown", max(0.35, pl.stats.attack_cooldown*0.93))),
    "hp_up": ("+Max HP", 12, lambda pl: (setattr(pl.stats, "max_hp", pl.stats.max_hp + 15), setattr(pl.stats, "hp", min(pl.stats.max_hp, pl.stats.hp + 15)))),
    "move": ("+Move Speed", 10, lambda pl: setattr(pl.stats, "speed", pl.stats.speed*1.08)),
    "crit": ("+Crit Chance", 10, lambda pl: setattr(pl.stats, "crit_chance", min(0.7, pl.stats.crit_chance+0.03))),
    "range": ("+Range", 8, lambda pl: setattr(pl.stats, "range", pl.stats.range + 6)),
    "regen": ("+Regen", 8, lambda pl: setattr(pl.stats, "regen", pl.stats.regen + 0.05)),
}
# Dynamic pricing: low base cost + linear growth per wave
SHOP_BASE_COSTS = {"dmg_up": 8, "atkspd": 9, "hp_up": 8, "move": 7, "crit": 7, "range": 6, "regen": 6}
SHOP_COST_GROWTH_PER_WAVE = 1.5   # each wave adds ~1.5 to price


class Shop:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.slots: List[str] = []

    def get_cost(self, iid: str, wave: int) -> int:
        base = SHOP_BASE_COSTS.get(iid, 8)
        return int(math.ceil(base + SHOP_COST_GROWTH_PER_WAVE * max(0, wave - 1)))

    def roll(self, wave: int):
        bag = PseudoRandomBag(self.rng, [
            ("dmg_up", 1.0+wave*0.02),
            ("atkspd", 0.9+wave*0.02),
            ("hp_up", 1.0),
            ("move", 0.9),
            ("crit", 0.8),
            ("range", 0.7),
            ("regen", 0.7),
        ])
        self.slots = bag.draw_n(4)

    def purchase(self, idx: int, player: Player, wave: int) -> bool:
        if idx < 0 or idx >= len(self.slots): return False
        iid = self.slots[idx]
        name, _, apply = SHOP_DB[iid]
        cost = self.get_cost(iid, wave)
        if player.loot >= cost:
            player.loot -= cost
            # apply may return tuple; just ensure it's executed
            _ = apply(player)
            # remove purchased slot
            self.slots.pop(idx)
            return True
        return False

# --------------------------- LevelManager -------------------------------
class LevelManager:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.wave = 1
        self.enemies: List[Enemy] = []
        self.obstacles: List[Obstacle] = []
        self.shop = Shop(rng)

    def spawn_wave(self):
        self.enemies.clear()
        self.obstacles.clear()
        # obstacles
        nobs = self.rng.randint(*WAVE_OBSTACLES)
        center = Vec2(VW//2, VH//2)
        for _ in range(nobs):
            for _try in range(20):
                w = self.rng.randint(8, 18)
                h = self.rng.randint(8, 18)
                x = self.rng.randint(8, VW-8-w)
                y = self.rng.randint(16, VH-16-h)
                rect = pygame.Rect(x,y,w,h)
                if circle_rect_intersect(center, CENTER_SAFE_RADIUS, rect):
                    continue
                self.obstacles.append(Obstacle(rect, hp=self.rng.randint(30,60), loot_value=self.rng.randint(1,4), xp_value=self.rng.uniform(4,10)))
                break
        # enemies
        is_boss = (self.wave % BOSS_WAVE_EVERY == 0)
        count = self.rng.randint(*ENEMY_BASE_COUNT)
        kinds = [Enemy.KIND_MELEE, Enemy.KIND_RANGED, Enemy.KIND_SUICIDE, Enemy.KIND_BUFFER]
        if is_boss:
            # fewer trash, plus a boss
            count = max(8, count-4)
        for _ in range(count):
            kind = self.rng.choice(kinds)
            for _try in range(50):
                x = self.rng.randint(10, VW-10)
                y = self.rng.randint(20, VH-20)
                pos = Vec2(x,y)
                if pos.distance_to(Vec2(VW//2, VH//2)) >= MIN_ENEMY_SPAWN_DIST:
                    e = Enemy((x,y), kind, special=False)
                    if self.wave == 1:
                        e.spawn_silence = FIRST_WAVE_SILENCE
                    self.enemies.append(e)
                    break
        # champion (special strong)
        champ = self.rng.choice(self.enemies) if self.enemies else None
        if champ:
            champ.special = True
            champ.max_hp *= 1.4; champ.hp = champ.max_hp
            champ.damage *= 1.35; champ.speed *= 1.05
            champ.color = ORANGE
        # boss
        if is_boss:
            for _try in range(50):
                bx = self.rng.randint(20, VW-20)
                by = self.rng.randint(20, VH-20)
                if Vec2(bx,by).distance_to(Vec2(VW//2,VH//2)) >= MIN_ENEMY_SPAWN_DIST:
                    self.enemies.append(Enemy((bx,by), Enemy.KIND_BOSS, special=True))
                    break

    def next_wave(self):
        self.wave += 1
        self.spawn_wave()

# --------------------------- Game Core ---------------------------------
class Game:
    STATE_HOME = "home"
    STATE_PLAY = "play"
    STATE_PAUSE = "pause"
    STATE_SHOP = "shop"
    STATE_GAMEOVER = "gameover"

    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Neuroscape Survivors - Prototype")
                # create fullscreen scaled with desktop size (avoid 0-sized SCALED error)
        try:
            info = pygame.display.Info()
            dw, dh = (info.current_w or WIDTH, info.current_h or HEIGHT)
        except Exception:
            dw, dh = (WIDTH, HEIGHT)
        flags = pygame.FULLSCREEN | pygame.SCALED | pygame.DOUBLEBUF
        try:
            self.screen = pygame.display.set_mode((dw, dh), flags)
        except pygame.error:
            # fallback to windowed if SCALED fails on this platform
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE | pygame.DOUBLEBUF)
        self.windowed_size = (WIDTH, HEIGHT)
        self.fullscreen = True
        self.surface = pygame.Surface((VW, VH))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Consolas", 12)
        self.big_font = pygame.font.SysFont("Consolas", 18)

        # rng & run
        self.rng = random.Random()
        self.run_seed = random.randrange(1<<30)
        self.rng.seed(self.run_seed)

        self.level = LevelManager(self.rng)
        self.player = Player((VW//2, VH//2))
        self.projectiles: List[Projectile] = []
        self.enemy_projectiles: List[Projectile] = []
        self.pickups: List[Pickup] = []
        self.state = Game.STATE_HOME
        self.shop_selected = 0
        self.pause_selected = 0
        self.home_selected = 0
        self.wave_checkpoint: Optional[dict] = None
        self.prev_state_for_pause: Optional[str] = None
        self.wave_time_remaining: float = 0.0

        # BGM hook
        self.init_music()

    # ----------------- Persistence / Rollback -----------------
    def make_checkpoint(self) -> dict:
        # serialize minimal state to restart at wave start
        data = {
            "run_seed": self.run_seed,
            "wave": self.level.wave,
            "player": {
                "stats": self.player.stats.to_dict(),
                "loot": self.player.loot,
                "xp": self.player.xp,
                "level": self.player.level,
                "xp_next": self.player.xp_next,
            }
        }
        return data

    def apply_checkpoint(self, data: dict):
        self.run_seed = data.get("run_seed", self.run_seed)
        self.rng.seed(self.run_seed + data.get("wave",1))
        self.level.wave = data.get("wave", 1)
        # reset world to start of that wave
        self.level.spawn_wave()
        self.reset_wave_timer()
        self.projectiles.clear(); self.enemy_projectiles.clear()
        self.player = Player((VW//2, VH//2))
        self.reset_wave_timer()
        st = data.get("player",{})
        # apply stats
        s = self.player.stats
        ds = st.get("stats",{})
        for k,v in ds.items():
            setattr(s, k, v)
        self.player.loot = st.get("loot", 0)
        self.player.xp = st.get("xp", 0.0)
        self.player.level = st.get("level", 1)
        self.player.xp_next = st.get("xp_next", 25.0)
        self.player.stats.hp = min(self.player.stats.max_hp, self.player.stats.hp)
        self.player.alive = True

    def save_checkpoint_to_disk(self, data: dict):
        try:
            with open(RUN_SAVE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception:
            pass

    def load_checkpoint_from_disk(self) -> Optional[dict]:
        try:
            if os.path.exists(RUN_SAVE_FILE):
                with open(RUN_SAVE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            return None
        return None

    # ----------------- Audio -----------------
    def init_music(self):
        try:
            pygame.mixer.init()
            if os.path.exists("bgm.ogg"):
                pygame.mixer.music.load("bgm.ogg")
                pygame.mixer.music.set_volume(0.35)
                pygame.mixer.music.play(-1)
        except Exception:
            pass

    def reset_wave_timer(self):
        # decide wave duration
        if self.level.wave % BOSS_WAVE_EVERY == 0:
            boss_index = max(1, self.level.wave // BOSS_WAVE_EVERY)
            self.wave_time_remaining = float(BOSS_WAVE_TIME_BASE + (boss_index-1)*BOSS_WAVE_TIME_STEP)
        else:
            self.wave_time_remaining = float(NORMAL_WAVE_TIME)

    # ----------------- Run control -----------------
    def new_run(self):
        self.run_seed = random.randrange(1<<30)
        self.rng.seed(self.run_seed)
        self.level.wave = 1
        self.player = Player((VW//2, VH//2))
        self.level.spawn_wave()
        self.projectiles.clear(); self.enemy_projectiles.clear()
        self.wave_checkpoint = self.make_checkpoint()
        self.save_checkpoint_to_disk(self.wave_checkpoint)
        self.state = Game.STATE_PLAY

    def continue_run(self):
        data = self.load_checkpoint_from_disk()
        if data:
            self.apply_checkpoint(data)
            self.wave_checkpoint = data
            self.state = Game.STATE_PLAY
        else:
            self.new_run()

    def rollback_to_checkpoint(self):
        if self.wave_checkpoint:
            self.apply_checkpoint(self.wave_checkpoint)
            self.state = Game.STATE_PLAY

    # ----------------- Combat / Systems -----------------
    def kill_enemy(self, e: Enemy, killer_is_player: bool=True):
        e.alive = False
        # loot & xp to player
        if killer_is_player:
            loot = self.rng.randint(1,3) + (2 if e.special else 0)
            # elite bonus if special or high accumulated XP
            is_elite = e.special or getattr(e, 'xp_total', 0.0) >= ELITE_XP_THRESHOLD or getattr(e,'kind',None)==Enemy.KIND_BOSS
            if is_elite:
                loot += (ELITE_KILL_BONUS_SPECIAL if (e.special or getattr(e,'kind',None)==Enemy.KIND_BOSS) else ELITE_KILL_BONUS_NORMAL)
            self.player.loot += loot
            self.player.gain_xp(8 + (4 if e.special else 0))
        # redistribute XP on ANY enemy death; elites/bosses use higher ratio
        survivors = [x for x in self.level.enemies if x.alive and x is not e]
        if survivors:
            ratio = SPECIAL_XP_REDISTRIB_RATIO if (e.special or getattr(e, 'kind', None) == Enemy.KIND_BOSS) else GENERIC_ENEMY_XP_REDISTRIB_RATIO
            inherit = getattr(e, 'xp_total', 0.0) * ratio
            if inherit > 0:
                share = inherit / len(survivors)
                for s in survivors:
                    s.gain_xp(share)

    def enemy_destroyed_obstacle(self, e: Enemy, obs: Obstacle):
        # xp for enemy, plus maybe tiny heal
        e.gain_xp(obs.xp_value)
        e.hp = min(e.max_hp, e.hp + 0.05*e.max_hp)

    def resolve_projectiles(self, dt: float):
        # player projectiles -> enemies / obstacles
        for p in self.projectiles:
            p.update(dt)
            if not p.alive: continue
            # collide enemies
            for e in self.level.enemies:
                if not e.alive: continue
                if e.pos.distance_to(p.pos) <= (e.radius + p.radius):
                    e.take_damage(p.damage)
                    p.alive = False
                    if not e.alive:
                        self.kill_enemy(e, killer_is_player=True)
                    break
            if not p.alive: continue
            # collide obstacles
            for o in self.level.obstacles:
                if not o.alive: continue
                if o.rect.collidepoint(int(p.pos.x), int(p.pos.y)):
                    o.take_damage(p.damage, attacker_enemy=None)
                    if not o.alive:
                        self.maybe_drop_pickup(o)
                    p.alive = False
                    if not o.alive:
                        # player gets loot for obstacle too
                        self.player.loot += o.loot_value
                        self.player.gain_xp(o.xp_value*0.4)
                        self.maybe_drop_pickup(o)
                    break

        # enemy projectiles -> player / obstacles
        for p in self.enemy_projectiles:
            p.update(dt)
            if not p.alive: continue
            # player
            if self.player.alive and self.player.pos.distance_to(p.pos) <= (self.player.radius + p.radius):
                self.player.take_damage(p.damage)
                p.alive = False
                continue
            # obstacles (mark last attacker to grant xp if destroyed)
            for o in self.level.obstacles:
                if not o.alive: continue
                if o.rect.collidepoint(int(p.pos.x), int(p.pos.y)):
                    # find firing enemy not tracked; skip for simplicity
                    o.take_damage(p.damage, attacker_enemy=None)
                    p.alive = False
                    break

        # cleanup
        self.projectiles = [p for p in self.projectiles if p.alive]
        self.enemy_projectiles = [p for p in self.enemy_projectiles if p.alive]

    def update_enemies(self, dt: float):
        for e in self.level.enemies:
            if not e.alive: continue
            e.update(dt, self.player, self.level.enemies)
            # collide with obstacles (resolve position)
            for o in self.level.obstacles:
                if not o.alive: continue
                e.pos = resolve_circle_rect(e.pos, e.radius, o.rect)
            shot = e.try_projectile(self.player)
            self.enemy_projectiles.extend(shot)
            acted, dmg = e.try_attack(dt, self.player)
            if acted and dmg>0:
                self.player.take_damage(dmg)
        # enemies collide with and damage obstacles to gain xp
        for e in self.level.enemies:
            if not e.alive: continue
            for o in self.level.obstacles:
                if not o.alive: continue
                if circle_rect_intersect(e.pos, e.radius, o.rect):
                    o.take_damage(max(2, e.damage*0.6), attacker_enemy=e)
                    if not o.alive and o.last_attacker_enemy is e:
                        self.enemy_destroyed_obstacle(e, o)
                        self.maybe_drop_pickup(o)
        # dead enemies cleanup
        self.level.enemies = [e for e in self.level.enemies if e.alive]

    # ----------------- UI Helpers -----------------
    def draw_bar(self, surf, x,y,w,h, ratio, fg, bg):
        pygame.draw.rect(surf, bg, pygame.Rect(x,y,w,h))
        pygame.draw.rect(surf, fg, pygame.Rect(x,y,int(w*clamp(ratio,0,1)),h))

    def draw_text(self, surf, text, pos, color=WHITE, center=False, large=False):
        font = self.big_font if large else self.font
        img = font.render(text, True, color)
        r = img.get_rect()
        if center:
            r.center = pos
        else:
            r.topleft = pos
        surf.blit(img, r)
    def resolve_player_collisions(self):
        for o in self.level.obstacles:
            if not o.alive:
                continue
            self.player.pos = resolve_circle_rect(self.player.pos, self.player.radius, o.rect)

    def maybe_drop_pickup(self, obs: Obstacle):
        if getattr(obs, 'dropped', False):
            return
        obs.dropped = True
        wave = max(1, self.level.wave)
        # Drop chance scales with wave: 0.25 + 0.02*wave, capped at 0.60
        drop_chance = clamp(0.25 + 0.02*wave, 0.25, 0.60)
        if self.rng.random() < drop_chance:
            # Heal amount scales with wave: 12% + 1%/wave, capped at 35%
            heal_frac = clamp(0.12 + 0.01*wave, 0.12, 0.35)
            amt = max(8, int(self.player.stats.max_hp * heal_frac))
            self.pickups.append(Pickup(Vec2(obs.rect.center), 'heal', amt))

    # ----------------- Screens -----------------
    def draw_home(self):
        self.surface.fill((12,12,16))
        self.draw_text(self.surface, "NEUROSCAPE SURVIVORS", (VW//2, 40), YELLOW, center=True, large=True)
        opts = ["Start Run", "Continue", "Quit"]
        for i, t in enumerate(opts):
            color = WHITE if i != self.home_selected else CYAN
            self.draw_text(self.surface, t, (VW//2, 80+18*i), color, center=True)
        self.draw_text(self.surface, "WASD/Arrows to move, Auto-fire", (VW//2, VH-28), GRAY, center=True)
        self.draw_text(self.surface, "ESC: Pause (Resume/Rollback/Home)", (VW//2, VH-18), GRAY, center=True)

    def draw_hud(self):
        # HP bar
        self.draw_bar(self.surface, 6, 6, 80, 5, self.player.stats.hp/self.player.stats.max_hp, GREEN, RED)
        self.draw_text(self.surface, f"{int(self.player.stats.hp)}/{int(self.player.stats.max_hp)}", (90, 3), WHITE)
        # XP bar
        self.draw_bar(self.surface, 6, 14, 80, 4, self.player.xp/max(1,self.player.xp_next), CYAN, DARKGRAY)
        # Loot
        self.draw_text(self.surface, f"Loot: {self.player.loot}", (6, 22), YELLOW)
        self.draw_text(self.surface, f"Wave {self.level.wave}", (VW-70, 6), WHITE)
        # Timer (mm:ss)
        t = max(0, int(self.wave_time_remaining + 0.999))
        mm, ss = divmod(t, 60)
        self.draw_text(self.surface, f"{mm:02d}:{ss:02d}", (VW//2, 6), WHITE, center=True)

    def draw_pause(self):
        # overlay
        s = pygame.Surface((VW, VH), pygame.SRCALPHA)
        s.fill((0,0,0,160))
        self.surface.blit(s, (0,0))
        panel = pygame.Rect(VW//2-70, VH//2-60, 140, 120)
        pygame.draw.rect(self.surface, DARKGRAY, panel)
        pygame.draw.rect(self.surface, GRAY, panel, 2)
        opts = ["Resume", "Restart Wave", "Restart Run", "Home"]
        for i,t in enumerate(opts):
            c = WHITE if i != self.pause_selected else CYAN
            self.draw_text(self.surface, t, (panel.centerx, panel.y+18+20*i), c, center=True)

    def draw_shop(self):
        self.surface.fill((10,10,14))
        self.draw_text(self.surface, f"Wave {self.level.wave} Cleared! SHOP", (VW//2, 16), YELLOW, center=True, large=True)
        self.draw_text(self.surface, f"Loot: {self.player.loot}", (8, 8), WHITE)
        # list items
        for i, iid in enumerate(self.level.shop.slots):
            name, _, _ = SHOP_DB[iid]
            c = WHITE if i != self.shop_selected else CYAN
            cost = self.level.shop.get_cost(iid, self.level.wave)
            self.draw_text(self.surface, f"[{i+1}] {name} (${cost})", (VW//2, 60 + 16*i), c, center=True)
        self.draw_text(self.surface, "Enter/Buy  |  R: Reroll (-4)  |  Space: Next Wave", (VW//2, VH-22), GRAY, center=True)

    def draw_gameover(self):
        self.surface.fill((0,0,0))
        self.draw_text(self.surface, "YOU DIED", (VW//2, VH//2-10), RED, center=True, large=True)
        self.draw_text(self.surface, "Enter: Home", (VW//2, VH//2+10), WHITE, center=True)

    def present(self):
        sw, sh = self.screen.get_size()
        # integer scaling to avoid pixel shimmer
        factor = max(1, min(sw // VW, sh // VH))
        if factor <= 0:
            scaled = pygame.transform.scale(self.surface, (sw, sh))
            self.screen.blit(scaled, (0, 0))
        else:
            scaled_w, scaled_h = VW * factor, VH * factor
            x = (sw - scaled_w) // 2
            y = (sh - scaled_h) // 2
            scaled = pygame.transform.scale(self.surface, (scaled_w, scaled_h))
            self.screen.fill((0,0,0))
            self.screen.blit(scaled, (x, y))
        pygame.display.flip()

    # ----------------- Main Update/Draw -----------------
    def update_play(self, dt: float):
        keys = pygame.key.get_pressed()
        self.player.handle_input(keys)
        self.player.update(dt)
        self.resolve_player_collisions()
        # player fire
        self.projectiles.extend(self.player.try_fire(dt, [e for e in self.level.enemies if e.alive]))
        # enemies
        self.update_enemies(dt)
        # projectiles
        self.resolve_projectiles(dt)
        # collect pickups
        for it in list(self.pickups):
            if it.alive and self.player.pos.distance_to(it.pos) <= (self.player.radius + it.radius):
                if it.kind == 'heal':
                    self.player.stats.hp = min(self.player.stats.max_hp, self.player.stats.hp + it.amount)
                it.alive = False
        self.pickups = [it for it in self.pickups if it.alive]
        # cleanup obstacles
        self.level.obstacles = [o for o in self.level.obstacles if o.alive]
        # check death
        if not self.player.alive:
            self.state = Game.STATE_GAMEOVER
            return
        # timer & wave clear -> shop
        self.wave_time_remaining = max(0.0, self.wave_time_remaining - dt)
        if self.wave_time_remaining <= 0.0 or not self.level.enemies:
            self.level.shop.roll(self.level.wave)
            if self.wave_time_remaining <= 0.0:
                # clear remaining bullets/enemies when timer ends
                self.level.enemies.clear()
                self.projectiles.clear(); self.enemy_projectiles.clear()
            self.state = Game.STATE_SHOP

    def draw_play(self):
        self.surface.fill((20, 18, 22))
        # obstacles
        for o in self.level.obstacles:
            o.draw(self.surface)
        # pickups
        for it in self.pickups:
            it.draw(self.surface)
        # entities
        for p in self.projectiles:
            p.draw(self.surface)
        for p in self.enemy_projectiles:
            p.draw(self.surface)
        for e in self.level.enemies:
            e.draw(self.surface)
        if self.player.alive:
            self.player.draw(self.surface)
        self.draw_hud()

    # ----------------- Event Handling -----------------
    def handle_event(self, e: pygame.event.Event):
        if e.type == pygame.QUIT:
            pygame.quit()
            raise SystemExit

        if e.type == pygame.KEYDOWN:
            # Toggle fullscreen
            if e.key == pygame.K_F11:
                if self.fullscreen:
                    self.screen = pygame.display.set_mode(
                        self.windowed_size,
                        pygame.RESIZABLE | pygame.SCALED | pygame.DOUBLEBUF
                    )
                    self.fullscreen = False
                else:
                    # toggle to fullscreen using current desktop size (robust on SDL2)
                    try:
                        info = pygame.display.Info()
                        dw, dh = (info.current_w or WIDTH, info.current_h or HEIGHT)
                    except Exception:
                        dw, dh = (WIDTH, HEIGHT)
                    try:
                        self.screen = pygame.display.set_mode(
                            (dw, dh),
                            pygame.FULLSCREEN | pygame.SCALED | pygame.DOUBLEBUF
                        )
                        self.fullscreen = True
                    except pygame.error:
                        # fallback: windowed if scaled/fullscreen fails
                        self.screen = pygame.display.set_mode(
                            self.windowed_size,
                            pygame.RESIZABLE | pygame.DOUBLEBUF
                        )
                        self.fullscreen = False
                return

            # Global pause (except on home/gameover)
            if e.key == pygame.K_ESCAPE:
                if self.state not in (Game.STATE_HOME, Game.STATE_GAMEOVER):
                    if self.state != Game.STATE_PAUSE:
                        self.prev_state_for_pause = self.state
                        self.state = Game.STATE_PAUSE
                    else:
                        # resume to the state before pausing (play or shop)
                        self.state = self.prev_state_for_pause or Game.STATE_PLAY
                return

            # ---------- State-specific ----------
            if self.state == Game.STATE_HOME:
                if e.key in (pygame.K_UP, pygame.K_w):
                    self.home_selected = (self.home_selected - 1) % 3
                elif e.key in (pygame.K_DOWN, pygame.K_s):
                    self.home_selected = (self.home_selected + 1) % 3
                elif e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.home_selected == 0:  # Start Run
                        self.new_run()
                        self.reset_wave_timer()  # ensure timer set at run start
                    elif self.home_selected == 1:  # Continue
                        self.continue_run()
                    elif self.home_selected == 2:  # Quit
                        pygame.quit()
                        raise SystemExit

            elif self.state == Game.STATE_PAUSE:
                if e.key in (pygame.K_UP, pygame.K_w):
                    self.pause_selected = (self.pause_selected - 1) % 4
                elif e.key in (pygame.K_DOWN, pygame.K_s):
                    self.pause_selected = (self.pause_selected + 1) % 4
                elif e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.pause_selected == 0:
                        # Resume
                        self.state = self.prev_state_for_pause or Game.STATE_PLAY
                    elif self.pause_selected == 1:
                        # Restart Wave
                        self.rollback_to_checkpoint()
                    elif self.pause_selected == 2:
                        # Restart Run
                        self.new_run()
                        self.reset_wave_timer()
                    elif self.pause_selected == 3:
                        # Home
                        self.state = Game.STATE_HOME

            elif self.state == Game.STATE_SHOP:
                if e.key in (pygame.K_UP, pygame.K_w):
                    self.shop_selected = (self.shop_selected - 1) % max(1, len(self.level.shop.slots))
                elif e.key in (pygame.K_DOWN, pygame.K_s):
                    self.shop_selected = (self.shop_selected + 1) % max(1, len(self.level.shop.slots))
                elif e.key == pygame.K_r:
                    # Reroll costs 4 loot
                    if self.player.loot >= 4:
                        self.player.loot -= 4
                        self.level.shop.roll(self.level.wave)
                        self.shop_selected = 0
                elif e.key in (pygame.K_RETURN,):
                    # Buy selected
                    self.level.shop.purchase(self.shop_selected, self.player, self.level.wave)
                    if self.shop_selected >= len(self.level.shop.slots):
                        self.shop_selected = max(0, len(self.level.shop.slots) - 1)
                elif e.key == pygame.K_SPACE:
                    # proceed next wave
                    self.level.next_wave()
                    # center player at start of each wave
                    self.player.pos = Vec2(VW // 2, VH // 2)
                    # reset wave timer
                    self.reset_wave_timer()
                    # checkpoint at new wave start
                    self.wave_checkpoint = self.make_checkpoint()
                    self.save_checkpoint_to_disk(self.wave_checkpoint)
                    self.state = Game.STATE_PLAY

            elif self.state == Game.STATE_GAMEOVER:
                if e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.state = Game.STATE_HOME

    def run(self):
        # initial home
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            for ev in pygame.event.get():
                self.handle_event(ev)

            # Update
            if self.state == Game.STATE_PLAY:
                self.update_play(dt)

            # Draw
            if self.state == Game.STATE_HOME:
                self.draw_home()
            elif self.state == Game.STATE_PLAY:
                self.draw_play()
            elif self.state == Game.STATE_PAUSE:
                self.draw_play()
                self.draw_pause()
            elif self.state == Game.STATE_SHOP:
                self.draw_shop()
            elif self.state == Game.STATE_GAMEOVER:
                self.draw_gameover()

            # Present
            self.present()



if __name__ == "__main__":
    Game().run()


