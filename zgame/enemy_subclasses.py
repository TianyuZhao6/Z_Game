"""Boss subclasses extracted from ZGame.py."""
from __future__ import annotations

import math
import random

import pygame


def install(game):
    class MemoryDevourerBoss(game.Enemy):
        """Standalone boss variant with larger size, higher HP, and boss-specific pacing."""

        def __init__(self, grid_pos: tuple[int, int], level_idx: int):
            gx, gy = grid_pos
            boss_hp = int(game.MEMDEV_BASE_HP * (1 + 0.15 * max(0, level_idx - 1)))
            self.skill_last = {"dash": -99, "vomit": -99, "summon": -99, "ring": -99}
            self.skill_phase = None
            self.skill_t = 0.0
            super().__init__(
                (gx, gy),
                attack=int(game.MEMDEV_CONTACT_DAMAGE),
                speed=int(max(1, game.MEMDEV_SPEED)),
                ztype="boss_mem",
                hp=boss_hp,
            )
            self.color = game.ENEMY_COLORS.get("boss_mem", (170, 40, 200))
            self._current_color = self.color
            self.is_boss = True
            self.boss_name = "Memory Devourer"
            self.size = int(game.CELL_SIZE * 1.6)
            self.rect = pygame.Rect(self.x, self.y + game.INFO_BAR_HEIGHT, self.size, self.size)
            self.radius = int(self.size * 0.5)
            self._base_size = int(self.size)
            self.can_crush_all_blocks = True
            self.no_clip_t = 0.0
            self._stuck_t = 0.0
            self.twin_slot = getattr(self, "twin_slot", +1)
            self._last_pos = (float(self.x), float(self.y))
            self._twin_powered = False
            self.is_enraged = False
            self.spawn_delay = 0.6
            game.set_enemy_size_category(self)

        def bind_twin(self, other, twin_id):
            import weakref

            self.twin_id = twin_id
            self._twin_partner_ref = weakref.ref(other)
            other.twin_id = twin_id
            other._twin_partner_ref = weakref.ref(self)

        def on_twin_partner_death(self):
            if getattr(self, "_twin_powered", False) or self.hp <= 0:
                return
            self.hp = int(getattr(self, "max_hp", self.hp))
            self.attack = int(self.attack * game.TWIN_ENRAGE_ATK_MULT)
            self.speed = int(self.speed + game.TWIN_ENRAGE_SPD_ADD)
            self._twin_powered = True
            self.is_enraged = True
            self._enrage_cd_mult = 0.65
            enraged_color = game.ENEMY_COLORS.get("boss_mem_enraged", game.BOSS_MEM_ENRAGED_COLOR)
            self._current_color = enraged_color
            self.color = enraged_color
            if hasattr(self, "_dash_cd"):
                self._dash_cd *= self._enrage_cd_mult
            self.boss_name = getattr(self, "boss_name", "BOSS") + " [ENRAGED]"

    class MistClone(game.Enemy):
        def __init__(self, gx: int, gy: int):
            super().__init__(
                (gx, gy),
                attack=8,
                speed=int(game.MIST_SPEED * game.CELL_SIZE / game.CELL_SIZE),
                ztype="mist_clone",
                hp=1,
            )
            self.color = game.ENEMY_COLORS["mist_clone"]
            self.size = int(game.CELL_SIZE * 0.6)
            self.rect = pygame.Rect(self.x, self.y + game.INFO_BAR_HEIGHT, self.size, self.size)
            self.is_illusion = True

        def update_special(self, dt, player, enemies, enemy_shots, game_state=None):
            if self.hp <= 0 and (not getattr(self, "_mist_boom", False)):
                game_state.spawn_acid_pool(
                    self.rect.centerx,
                    self.rect.centery,
                    r=int(game.CELL_SIZE * 0.6),
                    life=1.2,
                    dps=8,
                    slow_frac=0.25,
                )
                self._mist_boom = True

    class MistweaverBoss(game.Enemy):
        def __init__(self, grid_pos: tuple[int, int], level_idx: int):
            gx, gy = grid_pos
            super().__init__(
                (gx, gy),
                attack=game.MIST_CONTACT_DAMAGE,
                speed=int(game.MIST_SPEED),
                ztype="boss_mist",
                hp=int(game.MIST_BASE_HP * (1 + 0.12 * max(0, level_idx - 9))),
            )
            self.is_boss = True
            self.boss_name = "Mistweaver"
            self.color = game.ENEMY_COLORS["boss_mist"]
            self.size = int(game.CELL_SIZE * 1.6)
            self.rect = pygame.Rect(self.x, self.y + game.INFO_BAR_HEIGHT, self.size, self.size)
            self.radius = int(self.size * 0.5)
            self._base_size = int(self.size)
            self.phase = 1
            self._storm_cd = 2.0
            self._blade_cd = 1.5
            self._blink_cd = game.MIST_BLINK_CD
            self._sonar_next = 1.0
            self._clone_ids = set()
            self.can_crush_all_blocks = True
            self.no_clip_t = 0.0
            self._want_fog = True
            self._ring_cd = random.uniform(2.0, 3.5)
            self._ring_bursts_left = 0
            self._ring_burst_t = 0.0
            self.is_boss_shot = True
            game.set_enemy_size_category(self)

        def _has_clones(self, enemies):
            n = 0
            for z in enemies:
                if getattr(z, "is_illusion", False) and getattr(z, "hp", 0) > 0:
                    n += 1
            return n

        def _ensure_clones(self, enemies, game_state):
            need = max(0, 2 - self._has_clones(enemies))
            while need > 0:
                gx = int((self.x + self.size * 0.5) // game.CELL_SIZE) + random.choice((-3, -2, 2, 3))
                gy = int((self.y + self.size * 0.5) // game.CELL_SIZE) + random.choice((-3, -2, 2, 3))
                if 0 <= gx < game.GRID_SIZE and 0 <= gy < game.GRID_SIZE and ((gx, gy) not in game_state.obstacles):
                    enemies.append(game.MistClone(gx, gy))
                    need -= 1

        def _do_blink(self, game_state):
            cx, cy = (self.rect.centerx, self.rect.centery)
            gx = random.choice((2, game.GRID_SIZE - 3))
            gy = random.randint(2, game.GRID_SIZE - 3)
            tx = gx * game.CELL_SIZE + game.CELL_SIZE // 2
            ty = gy * game.CELL_SIZE + game.CELL_SIZE // 2 + game.INFO_BAR_HEIGHT
            game_state.spawn_acid_pool(
                cx,
                cy,
                r=int(game.CELL_SIZE * 0.9),
                life=game.MIST_DOOR_STAY,
                dps=game.MIST_DOOR_DPS,
                slow_frac=game.MIST_DOOR_SLOW,
                style="mist_door",
            )
            game_state.spawn_acid_pool(
                tx,
                ty,
                r=int(game.CELL_SIZE * 0.9),
                life=game.MIST_DOOR_STAY,
                dps=game.MIST_DOOR_DPS,
                slow_frac=game.MIST_DOOR_SLOW,
                style="mist_door",
            )
            self.x = tx - self.size * 0.5
            self.y = ty - self.size * 0.5 - game.INFO_BAR_HEIGHT
            self.rect.x = int(self.x)
            self.rect.y = int(self.y) + game.INFO_BAR_HEIGHT

        def update_special(self, dt, player, enemies, enemy_shots, game_state=None):
            hp_pct = max(0.0, self.hp / max(1, self.max_hp))
            self.phase = 1 if hp_pct > 0.7 else 2 if hp_pct > 0.35 else 3
            self._ensure_clones(enemies, game_state)
            self._blink_cd -= dt
            if self._blink_cd <= 0:
                self._do_blink(game_state)
                self._blink_cd = game.MIST_BLINK_CD
            if self.phase == 1:
                self._blade_cd -= dt
                if self._blade_cd <= 0:
                    ang0 = math.atan2(player.rect.centery - self.rect.centery, player.rect.centerx - self.rect.centerx)
                    spread = math.radians(40)
                    for i in range(-1, 2):
                        ang = ang0 + i * spread
                        for k in range(1, 5):
                            d = k * game.CELL_SIZE * 1.0
                            x = self.rect.centerx + math.cos(ang) * d
                            y = self.rect.centery + math.sin(ang) * d
                            game_state.spawn_acid_pool(
                                x,
                                y,
                                r=int(game.CELL_SIZE * 0.45),
                                life=game.MIST_P1_STRIP_TIME,
                                dps=game.MIST_P1_STRIP_DPS,
                                slow_frac=game.MIST_P1_STRIP_SLOW,
                                style="mist",
                            )
                    self._blade_cd = game.MIST_P1_BLADE_CD
                self._storm_cd -= dt
                if self._storm_cd <= 0:
                    for _ in range(game.MIST_SUMMON_IMPS):
                        ox = random.randint(-24, 24)
                        oy = random.randint(-24, 24)
                        enemies.append(game.spawn_mistling_at(self.rect.centerx + ox, self.rect.centery + oy, level_idx=getattr(game_state, "current_level", 0)))
                    self._storm_cd = 6.5
            if self.phase == 2:
                self._storm_cd -= dt
                if self._storm_cd <= 0:
                    pts = []
                    for _ in range(game.MIST_P2_STORM_POINTS):
                        gx = random.randint(1, game.GRID_SIZE - 2)
                        gy = random.randint(1, game.GRID_SIZE - 2)
                        x = gx * game.CELL_SIZE + game.CELL_SIZE // 2
                        y = gy * game.CELL_SIZE + game.CELL_SIZE // 2 + game.INFO_BAR_HEIGHT
                        pts.append((x, y))
                    for x, y in pts:
                        game_state.spawn_telegraph(
                            self.rect.centerx,
                            self.rect.centery,
                            r=22,
                            life=game.MIST_P2_STORM_WIND,
                            kind="dash_mist",
                            payload={
                                "points": [(x, y)],
                                "radius": int(game.CELL_SIZE * 0.5),
                                "life": 4.0,
                                "dps": game.MIST_P2_POOL_DPS,
                                "slow": game.MIST_P2_POOL_SLOW,
                            },
                            color=game.HAZARD_STYLES["mist"]["ring"],
                        )
                    self._storm_cd = game.MIST_P2_STORM_CD
                if random.random() < 0.007:
                    rx = random.randint(game.CELL_SIZE * 3, game.WINDOW_SIZE - game.CELL_SIZE * 3)
                    ry = random.randint(game.CELL_SIZE * 3, game.WINDOW_SIZE - game.CELL_SIZE * 3) + game.INFO_BAR_HEIGHT
                    game_state.spawn_acid_pool(
                        rx,
                        ry,
                        r=game.MIST_SILENCE_RADIUS,
                        life=game.MIST_SILENCE_TIME,
                        dps=0,
                        slow_frac=0.5,
                        style="mist",
                    )
            if self.phase == 3:
                next_pct = getattr(self, "_sonar_next", 0.7)
                while hp_pct <= next_pct and next_pct >= 0.0:
                    game_state.spawn_telegraph(
                        self.rect.centerx,
                        self.rect.centery,
                        r=int(self.radius * 1.8),
                        life=0.6,
                        kind="dash_mist",
                        payload={"note": "mist_sonar"},
                        color=game.HAZARD_STYLES["mist"]["ring"],
                    )
                    self._sonar_next = next_pct - game.MIST_SONAR_STEP
                    next_pct = self._sonar_next
                if getattr(player, "_mist_mark_t", 0.0) > 0.0:
                    self.buff_t = max(self.buff_t, dt)
                    self.buff_spd_add = max(self.buff_spd_add, game.MIST_CHASE_BOOST)
            self._ring_cd = max(0.0, self._ring_cd - dt)
            if self._ring_bursts_left > 0:
                self._ring_burst_t -= dt
                if self._ring_burst_t <= 0.0:
                    for i in range(game.MIST_RING_PROJECTILES):
                        ang = 2 * math.pi * (i / game.MIST_RING_PROJECTILES)
                        vx = math.cos(ang) * game.MIST_RING_SPEED
                        vy = math.sin(ang) * game.MIST_RING_SPEED
                        enemy_shots.append(
                            game.MistShot(
                                self.rect.centerx,
                                self.rect.centery,
                                vx,
                                vy,
                                game.MIST_RING_DAMAGE,
                                radius=10,
                                color=game.HAZARD_STYLES["mist"]["ring"],
                            )
                        )
                    self._ring_bursts_left -= 1
                    self._ring_burst_t = 0.2
                    game_state.spawn_telegraph(
                        self.rect.centerx,
                        self.rect.centery,
                        r=int(self.radius * 0.95),
                        life=0.2,
                        kind="acid",
                        color=game.HAZARD_STYLES["mist"]["ring"],
                    )
            elif self._ring_cd <= 0.0:
                self._ring_bursts_left = game.MIST_RING_BURSTS
                self._ring_burst_t = 0.0
                self._ring_cd = game.MIST_RING_CD
            pull_any = False
            cx, cy = self.rect.center
            for z in list(enemies):
                if getattr(z, "type", "") == "mistling":
                    zx, zy = (z.rect.centerx, z.rect.centery)
                    if (zx - cx) ** 2 + (zy - cy) ** 2 <= game.MISTLING_PULL_RADIUS ** 2:
                        z.hp = 0
                        pull_any = True
            if pull_any:
                self.hp = min(self.max_hp, self.hp + game.MISTLING_HEAL)
                game_state.add_damage_text(cx, cy, f"+{game.MISTLING_HEAL}", crit=False, kind="shield")

    game.__dict__.update(
        {
            "MemoryDevourerBoss": MemoryDevourerBoss,
            "MistClone": MistClone,
            "MistweaverBoss": MistweaverBoss,
        }
    )
    return (MemoryDevourerBoss, MistClone, MistweaverBoss)
