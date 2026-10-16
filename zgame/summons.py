"""Run-owned skull companion. Combat simulation is independent of render/FX budgets."""
from __future__ import annotations

from collections import deque
from functools import lru_cache
import math
import random

import pygame
from zgame.paths import asset_candidates, first_existing_path

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
        combat.update(charge=0, cast_left=0, procession=[], shots=[])


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
    path = first_existing_path(asset_candidates("sprites", "summons", "skull-atlas.png"))
    atlas = pygame.image.load(path).convert_alpha()
    w, h = atlas.get_width() // 2, atlas.get_height() // 2
    cell = atlas.subsurface((index % 2 * w, index // 2 * h, w, h))
    out = pygame.transform.scale(cell, (size, size))
    return pygame.transform.flip(out, True, False) if flip else out


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


def damage_enemy(game, state, enemies, target, damage, skull, normal=False):
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
    skull.on_kill(normal)
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
        self.hp = self.max_hp
        self.charge = 0
        self.hit_cd = self.quiet = self.fire_cd = self.clock = 0.0
        self.path = []
        self.path_cd = 0.0
        self.shots = []
        self.procession = []
        self.cast_left = 0.0
        self.hit_times = {}
        if isinstance(saved, dict):
            self.hp = number(saved.get("hp", self.max_hp), self.max_hp, high=self.max_hp)
            self.charge = int(number(saved.get("charge", 0), high=15)) if self.level == 6 else 0
            self.quiet = number(saved.get("quiet", 0), high=REGEN_DELAY)
            self.fire_cd = number(saved.get("fire_cd", 0), high=FIRE_INTERVAL)
            self.hit_cd = number(saved.get("hit_cd", 0), high=1)
            self.x = number(saved.get("x", self.x), self.x, high=game.GRID_SIZE*game.CELL_SIZE-self.size)
            self.y = number(saved.get("y", self.y), self.y, high=game.GRID_SIZE*game.CELL_SIZE-self.size)
            self.sync_rect()
            if any(self.rect.colliderect(ob.rect) for _, ob in nearby_walls(game, state, self.rect.topleft, self.rect.bottomright)):
                self.rect.center = player.rect.center
                self.x, self.y = float(self.rect.x), float(self.rect.y-game.INFO_BAR_HEIGHT)
            self.cast_left = number(saved.get("cast_left", 0), high=CAST_DURATION)
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
            "x": self.x, "y": self.y, "cast_left": self.cast_left,
            "procession": [list(row) for row in self.procession],
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
        self.persist()
        return amount

    def on_kill(self, normal):
        if self.hp <= 0:
            return
        if self.level >= 3:
            ratio = self.hp / self.max_hp
            self.harvest = min(200 if self.level == 6 else 100, self.harvest+1)
            self.hp = self.max_hp*ratio
        if normal and self.level == 6:
            self.charge = min(15, self.charge+1)

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

    def cast(self):
        game = self.game
        self.charge = 0
        self.cast_left = CAST_DURATION
        self.hit_times.clear()
        self.procession = []
        width, top = game.GRID_SIZE*game.CELL_SIZE, game.INFO_BAR_HEIGHT
        for i in range(PROCESSION_COUNT):
            side = random.randrange(4)
            a, b = random.uniform(0, width), random.uniform(0, width)
            endpoints = (((0, top+a),(width, top+b)), ((width,top+a),(0,top+b)), ((a,top),(b,top+width)), ((a,top+width),(b,top)))
            start, end = endpoints[side]
            delay = i/(PROCESSION_COUNT-1)*.75
            duration = CAST_DURATION-delay
            # x, y, velocity, spawn delay, remaining crossing, snapshot damage, age
            self.procession.append([*start, (end[0]-start[0])/duration, (end[1]-start[1])/duration, delay, duration, self.damage*PROCESSION_DAMAGE_MULT, 0.0])

    def update(self, dt, enemies):
        game, state = self.game, self.state
        self.clock += dt
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
                    self.shots.append(dict(x=float(self.rect.centerx), y=float(self.rect.centery), vx=math.cos(angle)*speed, vy=math.sin(angle)*speed, target=target, damage=self.damage, life=PROJECTILE_LIFETIME, trail=[]))
                self.fire_cd = FIRE_INTERVAL
            if self.level == 6 and self.charge == 15 and self.cast_left <= 0 and (len(alive) >= 5 or any(getattr(e,"is_boss",False) or getattr(e,"type","")=="bandit" for e in alive)):
                self.cast()
            for e in alive:
                if self.hit_cd <= 0 and game.circle_touch(e, self):
                    self.take_damage(max(1, getattr(e,"attack",game.ENEMY_ATTACK))*getattr(state,"biome_enemy_contact_mult",1))
                    self.hit_cd = .6
        self.update_shots(dt, enemies)
        self.update_procession(dt, enemies)
        self.persist()

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
            shot["trail"] = (shot["trail"]+[start])[-8:]
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
            start = s[0],s[1]
            s[0] += s[2]*step
            s[1] += s[3]*step
            s[5] -= step
            s[7] += step
            end = s[0],s[1]
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

    def draw(self, screen, sx, sy):
        size = int(self.game.CELL_SIZE*2.8)
        index = 2 if self.level == 6 else 1 if self.level >= 3 else 0
        art = sprite(index,size)
        if self.hp <= 0:
            art = art.copy()
            art.set_alpha(55)
        bob = math.sin(self.clock*3)*3
        screen.blit(art,art.get_rect(midbottom=(int(sx),int(sy-8+bob))))
        width = 60
        y = int(sy-size+5+bob)
        pygame.draw.rect(screen,(35,20,45),(int(sx-width/2),y,width,5))
        pygame.draw.rect(screen,(135,230,186),(int(sx-width/2),y,int(width*self.hp/self.max_hp),5))
        label = "DOWN" if self.hp <= 0 else f"{form(self.level)} +{self.harvest}%" + (f"  {self.charge}/15" if self.level==6 else "")
        if 0 < self.hp < self.max_hp and self.quiet >= REGEN_DELAY:
            label += "  REGEN"
        font = hud_font()
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
        for shot in skull.shots:
            points = [project(*p) for p in shot["trail"]]+[project(shot["x"],shot["y"])]
            if len(points)>1:
                pygame.draw.lines(screen,(191,108,232),False,points,2)
            pygame.draw.circle(screen,(255,190,232),points[-1],4)
        for s in skull.procession:
            if s[4] > 0 or s[5] <= 0:
                continue
            sx,sy = project(s[0],s[1])
            if not screen.get_rect().inflate(350,350).collidepoint(sx,sy):
                continue
            prev = project(s[0]-s[2]*.025,s[1]-s[3]*.025)
            art = sprite(3,int(game.CELL_SIZE*2.8),sx<prev[0]).copy()
            art.set_alpha(int(115*min(1,s[5]/.25,s[7]/.12)))
            for i in range(1,7):
                tx,ty = project(s[0]-s[2]*i*.018,s[1]-s[3]*i*.018)
                tile = trail_tile(i)
                screen.blit(tile,tile.get_rect(center=(int(tx),int(ty))))
            screen.blit(art,art.get_rect(center=(int(sx),int(sy-20))))


@lru_cache(maxsize=6)
def trail_tile(index):
    tile = pygame.Surface((26,16),pygame.SRCALPHA)
    pygame.draw.polygon(tile,(171,114,196,90-index*11),((13,0),(26,8),(13,16),(0,8)))
    return tile
