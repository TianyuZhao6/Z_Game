"""Run-owned skull companion. Combat simulation is independent of render/FX budgets."""
from __future__ import annotations

from collections import deque
from functools import lru_cache
import math
import random

import pygame
from zgame.paths import asset_candidates, first_existing_path
from zgame import summon_vfx

SKULL_ID = "evolving_skull"
MAX_COMPANIONS = 3
# First-pass balance, deliberately independent of player weapon stats.
BASE_DAMAGE = (10, 11, 14, 17, 20, 24)
BASE_HP = (80, 95, 120, 145, 175, 220)
VOLLEY = (1, 3, 3, 3, 3, 5)
FIRE_INTERVAL = 1.25
REGEN_DELAY = 5.0
REGEN_RATE = 0.02
CAST_DURATION = 3.0
CONTACT_GAP = 0.3
PROCESSION_COUNT = 24
ATTACK_RANGE_TILES = 7
FOLLOW_DISTANCE_TILES = 2.5
HOME_RADIUS_TILES = 6
PROJECTILE_SPEED_MULT = 0.75
HOMING_STRENGTH = 6.0
PROJECTILE_LIFETIME = 3.5
PROCESSION_DAMAGE_MULT = 1.5
PROCESSION_RADIUS_TILES = 0.8
BEAM_DURATION = 3.0
BEAM_COOLDOWN = 12.0
BEAM_DPS_MULT = 3.0
BEAM_TICK = .1


def number(value, default=0.0, low=0.0, high=1e6):
    try:
        value = float(value)
        return min(high, max(low, value)) if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def ensure_meta(meta):
    meta["skull_level"] = int(number(meta.get("skull_level", 0), high=6))
    cap = 200 if meta["skull_level"] == 6 else 100 if meta["skull_level"] >= 3 else 0
    meta["skull_harvest"] = int(number(meta.get("skull_harvest", 0), high=cap))
    meta["summon_shop_visits"] = int(number(meta.get("summon_shop_visits", 0)))
    raw = meta.get("equipped_companions", [])
    meta["equipped_companions"] = [SKULL_ID] if isinstance(raw, list) and SKULL_ID in raw and meta["skull_level"] else []
    meta.setdefault("skull_combat", None)


def purchase(meta):
    ensure_meta(meta)
    was_owned = meta["skull_level"] > 0
    meta["skull_level"] = min(6, meta["skull_level"] + 1)
    if not was_owned and len(meta["equipped_companions"]) < MAX_COMPANIONS:
        meta["equipped_companions"].append(SKULL_ID)


def form(level):
    return "Rift Skull" if level >= 6 else "Soulflame" if level >= 3 else "Bloombone"


def description(meta):
    level = max(1, min(6, int(meta.get("skull_level", 0))))
    return (f"{form(level)} L{level}/6 | {VOLLEY[level-1]} homing shots | "
            f"Harvest +{int(meta.get('skull_harvest', 0))}% | Evolves L3/L6")


def enter_shop(game):
    ensure_meta(game.META)
    level = int(getattr(game, "current_level", 0))
    if game.META.get("summon_shop_last_level", -1) != level:
        game.META["summon_shop_visits"] += 1
        game.META["summon_shop_last_level"] = level
    # The encounter has ended, even if the next map is not constructed yet.
    combat = game.META.get("skull_combat")
    if isinstance(combat, dict):
        combat.update(charge=0, cast_left=0, procession=[], shots=[], beam_left=0,
                      beam_cd=0, beam_credit=0, beam_tick=0, beam_target_hint=None)


def loadout_button(game, screen):
    if not game.META.get("skull_level", 0):
        return pygame.Rect(0, 0, 0, 0)
    equipped = SKULL_ID in game.META.get("equipped_companions", [])
    text = f"Companions {int(equipped)}/3: {form(game.META['skull_level'])} - {'equipped' if equipped else 'stored'} (click)"
    label = hud_font().render(text, True, (228, 200, 248))
    rect = label.get_rect(center=(screen.get_width()//2, 170)).inflate(20, 12)
    pygame.draw.rect(screen, (43, 27, 61), rect, border_radius=6)
    screen.blit(label, label.get_rect(center=rect.center))
    return rect


def toggle_equipped(meta):
    ensure_meta(meta)
    if not meta["skull_level"]:
        return
    if SKULL_ID in meta["equipped_companions"]:
        meta["equipped_companions"].remove(SKULL_ID)
    elif len(meta["equipped_companions"]) < MAX_COMPANIONS:
        meta["equipped_companions"].append(SKULL_ID)


@lru_cache(maxsize=24)
def sprite(index, size=112, flip=False):
    if index < 3:
        art = directional_sprite(index, size, 1)
        return pygame.transform.flip(art, True, False) if flip else art
    path = first_existing_path(asset_candidates("sprites", "summons", "skull-atlas.png"))
    atlas = pygame.image.load(path).convert_alpha()
    w, h = atlas.get_width() // 2, atlas.get_height() // 2
    cell = atlas.subsurface((index % 2 * w, index // 2 * h, w, h))
    out = pygame.transform.scale(cell, (size, size))
    return pygame.transform.flip(out, True, False) if flip else out


@lru_cache(maxsize=12)
def shop_avatar(index, size=100):
    """User-supplied avatar strip; retain the original artwork, not game sprites."""
    path = first_existing_path(asset_candidates("sprites", "summons", "eidolon-shop-avatars.png"))
    strip = pygame.image.load(path).convert_alpha()
    # Three square cards in the supplied 107x465 screenshot; exclude dividers.
    top = (5,183,357)[index]
    cell = strip.subsurface((3,top,104,104))
    return pygame.transform.smoothscale(cell,(size,size))


@lru_cache(maxsize=1)
def _direction_atlas():
    path = first_existing_path(asset_candidates("sprites", "summons", "skull-option-b.png"))
    return pygame.image.load(path).convert_alpha()


@lru_cache(maxsize=72)
def directional_sprite(index, size, facing):
    """Eight upright yaw views: S, SE, E, NE, N, NW, W, SW.

    The atlas supplies five rightward views; the leftward views are mirrored.
    Keep a fixed cell/anchor instead of trimming each silhouette independently.
    """
    atlas = _direction_atlas()
    column = facing if facing <= 4 else 8 - facing
    w, h = atlas.get_size()
    cell = atlas.subsurface((column*w//5, index*h//3,
                            (column+1)*w//5-column*w//5, (index+1)*h//3-index*h//3))
    art = pygame.transform.smoothscale(cell, (int(size*.94), int(size*.94)))
    if facing > 4:
        art = pygame.transform.flip(art, True, False)
    out = pygame.Surface((size, size), pygame.SRCALPHA)
    out.blit(art, art.get_rect(center=(size//2, size//2)))
    return out


def movement_facing(dx, dy, previous):
    """World movement to isometric camera yaw, with a quiet sector boundary.

    Use unrounded displacement, not camera/screen positions. The 2:1 screen
    foreshortening must not turn a world diagonal into an incorrect side view.
    """
    if dx*dx + dy*dy < 1e-8:
        return previous
    angle = math.atan2(dx-dy, dx+dy)
    offset = (angle - previous*math.pi/4 + math.pi) % math.tau - math.pi
    if abs(offset) <= math.pi/8 + math.radians(6):
        return previous
    return int(math.floor(angle/(math.pi/4) + .5)) % 8


def segment_hit(rect, start, end, radius=0):
    hit = rect.inflate(int(radius * 2), int(radius * 2)).clipline(start, end)
    if not hit:
        return None
    return math.dist(start, hit[0])


def nearby_walls(game, state, start, end, radius=0):
    c, top = game.CELL_SIZE, game.INFO_BAR_HEIGHT
    for gx in range(max(0, int((min(start[0], end[0])-radius)//c)), min(game.GRID_SIZE-1, int((max(start[0], end[0])+radius)//c))+1):
        for gy in range(max(0, int((min(start[1], end[1])-top-radius)//c)), min(game.GRID_SIZE-1, int((max(start[1], end[1])-top+radius)//c))+1):
            ob = state.obstacles.get((gx, gy))
            if ob is not None and not getattr(ob, "nonblocking", False):
                yield (gx, gy), ob


def first_wall(game, state, start, end, radius=0):
    hits = [(distance, gp, ob) for gp, ob in nearby_walls(game, state, start, end, radius)
            if (distance := segment_hit(ob.rect, start, end, radius)) is not None]
    return min(hits, key=lambda entry: entry[0]) if hits else None


def damage_wall(game, state, gp, ob, damage, player):
    if ob.type != "Destructible" or state.obstacles.get(gp) is not ob:
        return
    ob.health = (ob.health or 0) - damage
    if ob.health <= 0:
        del state.obstacles[gp]
        if random.random() < game.SPOILS_BLOCK_DROP_CHANCE:
            state.spawn_spoils(*ob.rect.center, 1)
        player.add_xp(game.XP_PLAYER_BLOCK)


def damage_enemy(game, state, enemies, target, damage, skull, normal=False, beam=False):
    """Resolve a personal kill once, without applying player weapon proc effects."""
    if target.hp <= 0 or getattr(target, "_death_processed", False):
        return
    if normal and getattr(target, "type", "") == "boss_mist" and random.random() < game.MIST_PHASE_CHANCE:
        # Keep the existing Mist boss's projectile evasion, without changing AI.
        direction = pygame.Vector2(target.rect.center) - skull.rect.center
        if direction.length_squared():
            direction.scale_to_length(game.MIST_PHASE_TELE_TILES * game.CELL_SIZE)
            target.x += direction.x
            target.y += direction.y
            target.rect.topleft = int(target.x), int(target.y + game.INFO_BAR_HEIGHT)
        state.add_damage_text(*target.rect.center, "TELEPORT", kind="shield")
        return
    dealt = max(1, int(round(game.apply_vuln_bonus(target, damage))))
    shield = max(0, getattr(target, "shield_hp", 0))
    blocked = min(shield, dealt)
    target.shield_hp = shield - blocked
    target.hp -= dealt - blocked
    state.add_damage_text(*target.rect.center, dealt, kind="hp_player")
    target._hit_flash = game.HIT_FLASH_DURATION
    if target.hp > 0:
        return
    target._death_processed = True
    skull.on_kill(normal or beam)
    game.increment_kill_count()
    game._bandit_death_notice(target, state)
    x, y = target.rect.center
    if getattr(target, "_can_split", False) and not getattr(target, "_split_done", False):
        target._split_done = True
        target._can_split = False
        game.spawn_splinter_children(target, enemies, state, level_idx=getattr(state, "current_level", 0), wave_index=0)
    else:
        bandit = getattr(target, "type", "") == "bandit"
        stolen = int(getattr(target, "_stolen_total", 0))
        drop = (stolen + int(stolen * game.BANDIT_BONUS_RATE) + int(game.BANDIT_BONUS_FLAT) if stolen else 0) if bandit else game.roll_spoils_for_enemy(target) + int(getattr(target, "spoils", 0))
        if drop:
            state.spawn_spoils(x, y, drop)
        if bandit and game.META.get("wanted_active", False):
            bounty = int(game.WANTED_POSTER_BOUNTY_BASE + stolen)
            game.META.update(spoils=int(game.META.get("spoils", 0))+bounty, wanted_active=False, wanted_poster_waves=0)
            state.wanted_wave_active = False
            state.flash_banner(f"Bounty Claimed! +{bounty}", sec=1.0)
        boss = getattr(target, "is_boss", False)
        if boss:
            game.trigger_twin_enrage(target, enemies, state)
        for _ in range(game.BOSS_HEAL_POTIONS if boss else int(random.random() < game.HEAL_DROP_CHANCE_ENEMY)):
            state.spawn_heal(x, y, game.HEAL_POTION_AMOUNT)
        xp = game.XP_PER_ENEMY_TYPE.get(getattr(target, "type", "basic"), game.XP_PLAYER_KILL)
        xp = int(xp * (3 if boss else 1.5 if getattr(target, "is_elite", False) else 1))
        xp += max(0, getattr(target, "z_level", 1)-1)*game.XP_ZLEVEL_BONUS + int(getattr(target, "spoils", 0))*game.Z_SPOIL_XP_BONUS_PER
        skull.owner.add_xp(xp)
        target._xp_awarded = True
    game.transfer_xp_to_neighbors(target, enemies)
    if target in enemies:
        enemies.remove(target)


class Skull:
    is_companion = True

    def __init__(self, game, state, player, saved=None):
        self.game, self.state, self.owner = game, state, player
        self.level = game.META["skull_level"]
        self.harvest = game.META["skull_harvest"]
        self.size = max(10, int(game.CELL_SIZE * 0.44))
        self.radius = self.size / 2
        self.rect = pygame.Rect(0, 0, self.size, self.size)
        self.rect.center = player.rect.center
        c = game.CELL_SIZE
        origin = (int(player.rect.centerx//c), int((player.rect.centery-game.INFO_BAR_HEIGHT)//c))
        for dx, dy in ((1,0),(0,1),(-1,0),(0,-1)):
            gx, gy = origin[0]+dx, origin[1]+dy
            if 0 <= gx < game.GRID_SIZE and 0 <= gy < game.GRID_SIZE and (gx,gy) not in state.obstacles:
                self.rect.center = (gx+.5)*c, (gy+.5)*c+game.INFO_BAR_HEIGHT
                break
        self.x, self.y = float(self.rect.x), float(self.rect.y-game.INFO_BAR_HEIGHT)
        self.facing = 0
        self.death_age = summon_vfx.DEATH_DURATION
        self.hp = self.max_hp
        self.charge = 0
        self.hit_cd = self.quiet = self.fire_cd = self.clock = 0.0
        self.path = []
        self.path_cd = 0.0
        self.shots = []
        self.procession = []
        self.procession_relative = False  # Legacy saved casts use world coordinates.
        self.cast_left = 0.0
        self.hit_times = {}
        self.beam_left = self.beam_cd = self.beam_tick = self.beam_credit = 0.0
        self.beam_target = self.beam_target_hint = self.beam_end = None
        self.beam_wall = False
        self._beam_recipient = None
        if isinstance(saved, dict):
            self.hp = number(saved.get("hp", self.max_hp), self.max_hp, high=self.max_hp)
            self.charge = int(number(saved.get("charge", 0), high=15)) if self.level == 6 else 0
            self.quiet = number(saved.get("quiet", 0), high=REGEN_DELAY)
            self.fire_cd = number(saved.get("fire_cd", 0), high=FIRE_INTERVAL)
            self.hit_cd = number(saved.get("hit_cd", 0), high=1)
            self.facing = int(number(saved.get("facing", 0), high=7))
            self.death_age = number(saved.get("death_age", summon_vfx.DEATH_DURATION), high=summon_vfx.DEATH_DURATION)
            if self.level == 6:
                self.beam_left = number(saved.get("beam_left",0), high=BEAM_DURATION)
                self.beam_cd = number(saved.get("beam_cd",0), high=BEAM_COOLDOWN)
                self.beam_credit = number(saved.get("beam_credit",0), high=self.damage*BEAM_DPS_MULT*BEAM_TICK+1)
                self.beam_tick = number(saved.get("beam_tick",0), high=BEAM_TICK)
                hint = saved.get("beam_target_hint")
                if isinstance(hint,list) and len(hint)==3:
                    self.beam_target_hint = [number(hint[0]),number(hint[1]),str(hint[2])]
            self.x = number(saved.get("x", self.x), self.x, high=game.GRID_SIZE*game.CELL_SIZE-self.size)
            self.y = number(saved.get("y", self.y), self.y, high=game.GRID_SIZE*game.CELL_SIZE-self.size)
            self.sync_rect()
            if any(self.rect.colliderect(ob.rect) for _, ob in nearby_walls(game, state, self.rect.topleft, self.rect.bottomright)):
                self.rect.center = player.rect.center
                self.x, self.y = float(self.rect.x), float(self.rect.y-game.INFO_BAR_HEIGHT)
            self.cast_left = number(saved.get("cast_left", 0), high=CAST_DURATION)
            self.procession_relative = saved.get("procession_space") == "player_view"
            for row in saved.get("procession", [])[:PROCESSION_COUNT]:
                if isinstance(row, list) and len(row) == 8:
                    self.procession.append([number(v, low=-1e6) for v in row])
            for row in saved.get("shots", [])[:40]:
                if isinstance(row, list) and len(row) == 6:
                    self.shots.append(dict(zip(("x", "y", "vx", "vy", "life", "damage"), [number(v, low=-1e6) for v in row]), target=None, trail=[]))
            # Target identities may differ after loading; brief grace preserves hit spacing.
            self.resume_grace = CONTACT_GAP
        else:
            self.resume_grace = 0.0
        if self.hp <= 0:
            self.harvest = self.charge = 0
            self.stop_beam()
        self.persist()

    @property
    def max_hp(self):
        return BASE_HP[self.level-1] * (1+self.harvest/100) * max(0.1, number(self.game.META.get("summon_hp_mult", 1), 1))

    @property
    def damage(self):
        return BASE_DAMAGE[self.level-1] * (1+self.harvest/100) * max(0.1, number(self.game.META.get("summon_damage_mult", 1), 1))

    def sync_rect(self):
        self.rect.topleft = round(self.x), round(self.y+self.game.INFO_BAR_HEIGHT)

    def persist(self):
        self.game.META["skull_harvest"] = self.harvest
        self.game.META["skull_combat"] = {
            "level_index": int(getattr(self.state, "current_level", 0)), "hp": self.hp,
            "charge": self.charge, "quiet": self.quiet, "fire_cd": self.fire_cd, "hit_cd": self.hit_cd,
            "x": self.x, "y": self.y, "facing": self.facing, "death_age": self.death_age, "cast_left": self.cast_left,
            "procession": [list(row) for row in self.procession],
            "procession_space": "player_view" if self.procession_relative else "world",
            "beam_left": self.beam_left, "beam_cd": self.beam_cd,
            "beam_tick": self.beam_tick, "beam_credit": self.beam_credit,
            "beam_target_hint": ([*self.beam_target.rect.center,str(getattr(self.beam_target,"type","basic"))]
                                 if self.beam_target is not None else self.beam_target_hint),
            "shots": [[s[k] for k in ("x", "y", "vx", "vy", "life", "damage")] for s in self.shots],
        }

    def take_damage(self, amount):
        if self.hp <= 0:
            return 0
        amount = max(0, amount)
        self.hp = max(0, self.hp-amount)
        if amount:
            self.quiet = 0
        if self.hp <= 0:
            self.harvest = self.charge = 0
            self.death_age = 0
            self.facing = self.visual_facing
            self.stop_beam()
        self.persist()
        return amount

    def gain_procession_charge(self, amount=1):
        if self.hp > 0 and self.level == 6:
            self.charge = min(15, self.charge+max(0,int(amount)))
            self.persist()

    def on_kill(self, charges_skill):
        if self.hp <= 0:
            return
        if self.level >= 3:
            ratio = self.hp / self.max_hp
            self.harvest = min(200 if self.level == 6 else 100, self.harvest+1)
            self.hp = self.max_hp*ratio
        if charges_skill:
            self.gain_procession_charge()

    def navigate(self, goal, dt):
        game, state = self.game, self.state
        c = game.CELL_SIZE
        self.path_cd -= dt
        if self.path_cd <= 0:
            self.path_cd = 0.4
            start = (int(self.rect.centerx//c), int((self.rect.centery-game.INFO_BAR_HEIGHT)//c))
            dest = (max(0, min(game.GRID_SIZE-1, int(goal[0]//c))), max(0, min(game.GRID_SIZE-1, int((goal[1]-game.INFO_BAR_HEIGHT)//c))))
            queue, prev = deque([start]), {start: None}
            best = start
            while queue:
                p = queue.popleft()
                if math.dist(p, dest) < math.dist(best, dest):
                    best = p
                if p == dest:
                    break
                for q in ((p[0]+1,p[1]),(p[0]-1,p[1]),(p[0],p[1]+1),(p[0],p[1]-1)):
                    if q not in prev and 0 <= q[0] < game.GRID_SIZE and 0 <= q[1] < game.GRID_SIZE and q not in state.obstacles:
                        prev[q] = p
                        queue.append(q)
            self.path = []
            while best != start:
                self.path.append(((best[0]+.5)*c, (best[1]+.5)*c+game.INFO_BAR_HEIGHT))
                best = prev[best]
            self.path.reverse()
        if not self.path:
            return
        goal = self.path[0]
        delta = pygame.Vector2(goal)-self.rect.center
        distance = delta.length()
        step = min(distance, self.game.PLAYER_SPEED*60*.9*dt)
        if distance < 3:
            self.path.pop(0)
            return
        delta.scale_to_length(step)
        start_x, start_y = self.x, self.y
        for axis in (0, 1):
            old = self.x, self.y
            if axis == 0:
                self.x += delta.x
            else:
                self.y += delta.y
            self.sync_rect()
            if any(self.rect.colliderect(ob.rect) for _, ob in nearby_walls(game, state, self.rect.topleft, self.rect.bottomright)):
                self.x, self.y = old
                self.sync_rect()
                self.path_cd = 0
        self.facing = movement_facing(self.x-start_x, self.y-start_y, self.facing)

    def cast(self):
        self.charge = 0
        self.cast_left = CAST_DURATION
        self.hit_times.clear()
        self.procession = []
        self.procession_relative = True
        for i in range(PROCESSION_COUNT):
            side = random.randrange(4)
            a, b = random.random(), random.random()
            endpoints = (((0,a),(1,b)), ((1,a),(0,b)), ((a,0),(b,1)), ((a,1),(b,0)))
            start, end = endpoints[side]
            delay = i/(PROCESSION_COUNT-1)*.75
            duration = CAST_DURATION-delay
            # x, y, velocity, spawn delay, remaining crossing, snapshot damage, age
            self.procession.append([*start, (end[0]-start[0])/duration, (end[1]-start[1])/duration, delay, duration, self.damage*PROCESSION_DAMAGE_MULT, 0.0])

    def procession_world(self, x, y):
        """Convert viewport-relative paths to authoritative current world space.

        Anchoring to the owner (not this companion or the cast location) keeps
        delayed spawns, active skulls and collision together while moving. A
        teleport reanchors the field without sweeping damage across the map.
        """
        if not self.procession_relative:
            return x,y
        game = self.game
        px,py = self.owner.rect.center
        cam = game.calculate_iso_camera(px,py)
        sx,sy = game.iso_world_to_screen(px/game.CELL_SIZE,(py-game.INFO_BAR_HEIGHT)/game.CELL_SIZE,0,*cam)
        dx = x*game.VIEW_W-sx
        dy = game.INFO_BAR_HEIGHT+y*(game.VIEW_H-game.INFO_BAR_HEIGHT)-sy
        return (px+game.CELL_SIZE*(dx/game.ISO_CELL_W+dy/game.ISO_CELL_H),
                py+game.CELL_SIZE*(dy/game.ISO_CELL_H-dx/game.ISO_CELL_W))

    def update(self, dt, enemies):
        game, state = self.game, self.state
        self.clock += dt
        if self.hp <= 0:
            self.death_age = min(summon_vfx.DEATH_DURATION,self.death_age+dt)
        self.hit_cd = max(0, self.hit_cd-dt)
        self.resume_grace = max(0, self.resume_grace-dt)
        if self.hp > 0:
            self.quiet += dt
            if self.quiet >= REGEN_DELAY:
                self.hp = min(self.max_hp, self.hp+self.max_hp*REGEN_RATE*dt)
            c = game.CELL_SIZE
            alive = [e for e in enemies if e.hp > 0]
            targets = sorted((e for e in alive if math.dist(e.rect.center, self.rect.center) <= ATTACK_RANGE_TILES*c), key=lambda e: math.dist(e.rect.center, self.rect.center))
            far = math.dist(self.rect.center, self.owner.rect.center) > FOLLOW_DISTANCE_TILES*c
            retreat = self.hp/self.max_hp < .25
            wall = first_wall(game, state, self.rect.center, targets[0].rect.center) if targets else None
            if far or retreat:
                self.navigate(self.owner.rect.center, dt)
            elif targets and wall and wall[2].type != "Destructible" and math.dist(targets[0].rect.center, self.owner.rect.center) <= HOME_RADIUS_TILES*c:
                self.navigate(targets[0].rect.center, dt)
            else:
                self.path_cd = 0
            self.fire_cd -= dt
            if targets and self.fire_cd <= 0:
                count = VOLLEY[self.level-1]
                for i in range(count):
                    target = targets[i % len(targets)]
                    direction = pygame.Vector2(target.rect.center)-self.rect.center
                    angle = math.atan2(direction.y, direction.x)+(i-(count-1)/2)*.35+.35
                    speed = game.BULLET_SPEED*PROJECTILE_SPEED_MULT
                    self.shots.append(dict(x=float(self.rect.centerx), y=float(self.rect.centery), vx=math.cos(angle)*speed, vy=math.sin(angle)*speed, target=target, damage=self.damage, life=PROJECTILE_LIFETIME, trail=[], visual_origin=self.eye_offset()))
                self.fire_cd = FIRE_INTERVAL
            if self.level == 6 and self.charge == 15 and self.cast_left <= 0 and (len(alive) >= 5 or any(getattr(e,"is_boss",False) or getattr(e,"type","")=="bandit" for e in alive)):
                self.cast()
            for e in alive:
                if self.hit_cd <= 0 and game.circle_touch(e, self):
                    self.take_damage(max(1, getattr(e,"attack",game.ENEMY_ATTACK))*getattr(state,"biome_enemy_contact_mult",1))
                    self.hit_cd = .6
        self.update_shots(dt, enemies)
        self.update_beam(dt, enemies)
        self.update_procession(dt, enemies)
        self.persist()

    def stop_beam(self):
        self.beam_left = self.beam_tick = self.beam_credit = 0.0
        self.beam_cd = BEAM_COOLDOWN
        self.beam_target = self.beam_target_hint = self.beam_end = None
        self._beam_recipient = None

    def update_beam(self, dt, enemies):
        """Additional Stage 3 skill, independent of Shadow Procession's charge."""
        if self.level < 6 or self.hp <= 0:
            return
        game,state = self.game,self.state
        candidates = [e for e in enemies if e.hp>0 and
                      math.dist(e.rect.center,self.rect.center)<=ATTACK_RANGE_TILES*game.CELL_SIZE]
        if self.beam_left<=0:
            waiting = min(dt,self.beam_cd)
            self.beam_cd = max(0,self.beam_cd-waiting)
            dt -= waiting
            if self.beam_cd>0 or dt<=0 or not candidates:
                return
            self.beam_left = BEAM_DURATION
            self.beam_tick = self.beam_credit = 0.0
        if self.beam_target not in candidates:
            hint = self.beam_target_hint
            restored = [e for e in candidates if hint and getattr(e,"type","basic")==hint[2]
                        and math.dist(e.rect.center,hint[:2])<game.CELL_SIZE]
            self.beam_target = (min(restored,key=lambda e:math.dist(e.rect.center,hint[:2])) if restored else
                                min(candidates,key=lambda e:math.dist(e.rect.center,self.rect.center)) if candidates else None)
            self.beam_target_hint = None
        active_dt = min(dt,self.beam_left)
        self.beam_left = max(0,self.beam_left-active_dt)
        self.beam_tick += active_dt
        target = self.beam_target
        self.beam_end = None
        recipient = None
        wall = None
        if target is not None:
            wall = first_wall(game,state,self.rect.center,target.rect.center)
            self.beam_wall = wall is not None
            if wall:
                self.beam_end = wall[2].rect.clipline(self.rect.center,target.rect.center)[0]
                if wall[2].type == "Destructible":
                    recipient = wall[2]
            else:
                self.beam_end = target.rect.center
                recipient = target
        if self._beam_recipient is not None and self._beam_recipient is not recipient:
            self.beam_credit = 0.0
        self._beam_recipient = recipient
        if recipient is not None:
            self.beam_credit += self.damage*BEAM_DPS_MULT*active_dt
        else:
            self.beam_credit = 0.0
        # Accumulate fractions, then resolve normal kill/reward/shield handling
        # at 10 Hz. No minimum-one-per-frame damage or render-dependent damage.
        if self.beam_tick+1e-9>=BEAM_TICK or self.beam_left<=1e-9:
            dealt = int(self.beam_credit+1e-9)
            self.beam_credit -= dealt
            self.beam_tick = max(0,self.beam_tick-BEAM_TICK)
            if dealt>0 and recipient is not None:
                if wall:
                    damage_wall(game,state,wall[1],wall[2],dealt,self.owner)
                else:
                    damage_enemy(game,state,enemies,target,dealt,self,beam=True)
        if self.beam_left<=1e-9:
            self.stop_beam()

    def update_shots(self, dt, enemies):
        game, state = self.game, self.state
        for shot in list(self.shots):
            start = shot["x"], shot["y"]
            shot["life"] -= dt
            target = shot["target"]
            if target is None or target.hp <= 0 or target not in enemies:
                candidates = [e for e in enemies if e.hp > 0 and math.dist(e.rect.center,start) <= ATTACK_RANGE_TILES*game.CELL_SIZE]
                target = min(candidates, key=lambda e: math.dist(e.rect.center,start)) if candidates else None
                shot["target"] = target
            if target:
                direction = pygame.Vector2(target.rect.center)-start
                if direction.length_squared():
                    desired = direction.normalize()*game.BULLET_SPEED*PROJECTILE_SPEED_MULT
                    velocity = pygame.Vector2(shot["vx"],shot["vy"]).lerp(desired, min(1,dt*HOMING_STRENGTH))
                    shot["vx"],shot["vy"] = velocity
            end = start[0]+shot["vx"]*dt, start[1]+shot["vy"]*dt
            # Lifetime stamps bound trail length in time even at variable frame rates.
            shot["trail"] = [p for p in shot["trail"] if p[2]-shot["life"] <= summon_vfx.TRAIL_SECONDS][-47:]
            shot["trail"].append((*start,shot["life"]+dt))
            shot["x"],shot["y"] = end
            wall = first_wall(game, state, start, end, 3)
            hits = [(d,e) for e in enemies if e.hp > 0 and (d := segment_hit(e.rect,start,end,3)) is not None]
            hit = min(hits,key=lambda h:h[0]) if hits else None
            if wall and (hit is None or wall[0] <= hit[0]):
                damage_wall(game,state,wall[1],wall[2],shot["damage"],self.owner)
                self.shots.remove(shot)
            elif hit:
                damage_enemy(game,state,enemies,hit[1],shot["damage"],self,normal=True)
                self.shots.remove(shot)
            elif shot["life"] <= 0:
                self.shots.remove(shot)

    def update_procession(self, dt, enemies):
        if self.cast_left <= 0:
            return
        game, state = self.game, self.state
        active_dt = min(dt,self.cast_left)
        self.cast_left = max(0,self.cast_left-dt)
        for s in self.procession:
            step = max(0,active_dt-max(0,s[4]))
            s[4] -= active_dt
            if step <= 0 or s[5] <= 0:
                continue
            step = min(step,s[5])
            start = self.procession_world(s[0],s[1])
            s[0] += s[2]*step
            s[1] += s[3]*step
            s[5] -= step
            s[7] += step
            end = self.procession_world(s[0],s[1])
            radius = game.CELL_SIZE*PROCESSION_RADIUS_TILES
            contacts = [(e,e.rect) for e in list(enemies) if e.hp > 0]
            contacts += [(ob,ob.rect) for gp,ob in nearby_walls(game,state,start,end,radius) if ob.type == "Destructible"]
            for obj,rect in contacts:
                if self.resume_grace > 0 or self.clock-self.hit_times.get(obj,-999) < CONTACT_GAP:
                    continue
                if segment_hit(rect,start,end,radius) is None:
                    continue
                self.hit_times[obj] = self.clock
                if getattr(obj,"type",None) == "Destructible":
                    gp = (rect.x//game.CELL_SIZE,(rect.y-game.INFO_BAR_HEIGHT)//game.CELL_SIZE)
                    damage_wall(game,state,gp,obj,s[6],self.owner)
                else:
                    damage_enemy(game,state,enemies,obj,s[6],self)
        if self.cast_left <= 0:
            self.procession.clear()
            self.hit_times.clear()

    @property
    def visual_facing(self):
        if self.beam_left>0 and self.beam_target is not None:
            dx = self.beam_target.rect.centerx-self.rect.centerx
            dy = self.beam_target.rect.centery-self.rect.centery
            return movement_facing(dx,dy,self.facing)
        return self.facing

    def eye_offset(self):
        return summon_vfx.eye_offset(summon_vfx.canvas_size(self.level),self.visual_facing,
                                    math.sin(self.clock*3)*2,summon_vfx.stage_index(self.level))

    @property
    def render_margin(self):
        return summon_vfx.canvas_size(self.level)+summon_vfx.HOVER_HEIGHT+32

    def draw(self, screen, sx, sy):
        size = summon_vfx.canvas_size(self.level)
        index = 2 if self.level == 6 else 1 if self.level >= 3 else 0
        art = directional_sprite(index, size, self.visual_facing)
        bob = math.sin(self.clock*3)*2
        dest = art.get_rect(midbottom=(int(sx),int(sy-summon_vfx.HOVER_HEIGHT+bob)))
        if self.hp > 0:
            screen.blit(art,dest)
        elif self.death_age < summon_vfx.DEATH_DURATION:
            phase = int(self.death_age/summon_vfx.DEATH_DURATION*24)/24
            fragments = summon_vfx.dissolve_frame(art,phase)
            screen.blit(fragments,(dest.x-16,dest.y-16))
        width = min(48,size-8)
        font = hud_font()
        # The large final form can extend above the viewport. Keep its compact
        # status stack below the top HUD instead of losing both bars offscreen.
        y = max(self.game.INFO_BAR_HEIGHT+font.get_linesize()+4,dest.top-13)
        if self.hp <= 0:
            # A small persistent status marker, not a permanently faded living sprite.
            text = hud_font().render("DOWN",True,(132,99,148))
            screen.blit(text,text.get_rect(midbottom=(int(sx),int(sy-6))))
            return
        pygame.draw.rect(screen,(35,20,45),(int(sx-width/2),y,width,5))
        pygame.draw.rect(screen,(135,230,186),(int(sx-width/2),y,int(width*self.hp/self.max_hp),5))
        # Second bar is dim/empty until the final evolution unlocks Procession.
        pygame.draw.rect(screen,(45,30,60),(int(sx-width/2),y+8,width,5))
        if self.level == 6:
            color = (244,168,255) if self.charge == 15 else (174,95,232)
            pygame.draw.rect(screen,color,(int(sx-width/2),y+8,int(width*self.charge/15),5))
        label = f"Eidolon +{self.harvest}%"
        text = font.render(label,True,(228,200,248))
        screen.blit(text,text.get_rect(midbottom=(int(sx),y-2)))


@lru_cache(maxsize=1)
def hud_font():
    return pygame.font.Font(None,18)


def start_level(game, state, player):
    ensure_meta(game.META)
    state.companions = []
    if not game.META["skull_level"] or SKULL_ID not in game.META["equipped_companions"]:
        return
    saved = game.META.get("skull_combat")
    if not isinstance(saved,dict) or saved.get("level_index") != getattr(state,"current_level",0):
        saved = None
    state.companions.append(Skull(game,state,player,saved))


def update(game, state, dt, enemies):
    # Substep to maintain steering and hit timing when a frame is slow.
    steps = max(1,math.ceil(dt/(1/60)))
    for _ in range(steps):
        for skull in getattr(state,"companions",()):
            skull.update(dt/steps,enemies)


def enemy_target(game, state, enemy, player):
    if state is None or getattr(enemy,"is_boss",False) or getattr(enemy,"type","")=="bandit":
        return player
    best, distance = player, math.dist(player.rect.center,enemy.rect.center)
    for skull in getattr(state,"companions",()):
        d = math.dist(skull.rect.center,enemy.rect.center)
        if skull.hp > 0 and d < min(distance,game.CELL_SIZE*4) and first_wall(game,state,enemy.rect.center,skull.rect.center) is None:
            best,distance = skull,d
    previous = getattr(enemy, "_friendly_target", None)
    if previous is not best and previous in getattr(state, "companions", ()) and previous.hp > 0:
        previous_distance = math.dist(previous.rect.center, enemy.rect.center)
        if previous_distance < min(game.CELL_SIZE*4, distance*1.15) and first_wall(game,state,enemy.rect.center,previous.rect.center) is None:
            best = previous
    if previous is not best:
        enemy._friendly_target = best
        # Do not keep a cached route to the other friendly actor after switching.
        if previous is not None or best is not player:
            enemy._path = []
            enemy._path_step = 0
            enemy._ff_commit = None
            enemy._ff_commit_t = 0.0
    return best


def draw_effects(game,state,screen,camx,camy):
    def project(x,y):
        return game.iso_world_to_screen(x/game.CELL_SIZE,(y-game.INFO_BAR_HEIGHT)/game.CELL_SIZE,0,camx,camy)
    for skull in getattr(state,"companions",()):
        if skull.hp>0 and skull.beam_left>0 and skull.beam_end is not None:
            sx,sy = project(*skull.rect.center)
            dx,dy = skull.eye_offset()
            ex,ey = project(*skull.beam_end)
            summon_vfx.draw_beam(screen,(sx+dx,sy+dy),(ex,ey if skull.beam_wall else ey-10))
        for shot in skull.shots:
            offset = shot.get("visual_origin",skull.eye_offset())
            points = []
            for x,y,life in shot["trail"]+[(shot["x"],shot["y"],shot["life"])]:
                sx,sy = project(x,y)
                lift = max(0,1-(PROJECTILE_LIFETIME-life)/.22)
                points.append((sx+offset[0]*lift,sy+offset[1]*lift))
            summon_vfx.draw_orb(screen,points)
        for s in skull.procession:
            if s[4] > 0 or s[5] <= 0:
                continue
            sx,sy = project(*skull.procession_world(s[0],s[1]))
            if not screen.get_rect().inflate(350,350).collidepoint(sx,sy):
                continue
            prev = project(*skull.procession_world(s[0]-s[2]*.025,s[1]-s[3]*.025))
            art = sprite(3,int(game.CELL_SIZE*2.8),sx<prev[0]).copy()
            art.set_alpha(int(115*min(1,s[5]/.25,s[7]/.12)))
            for i in range(1,7):
                tx,ty = project(*skull.procession_world(s[0]-s[2]*i*.018,s[1]-s[3]*i*.018))
                tile = trail_tile(i)
                screen.blit(tile,tile.get_rect(center=(int(tx),int(ty))))
            screen.blit(art,art.get_rect(center=(int(sx),int(sy if skull.procession_relative else sy-20))))


@lru_cache(maxsize=6)
def trail_tile(index):
    tile = pygame.Surface((26,16),pygame.SRCALPHA)
    pygame.draw.polygon(tile,(171,114,196,90-index*11),((13,0),(26,8),(13,16),(0,8)))
    return tile
