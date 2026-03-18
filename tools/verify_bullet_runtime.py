from __future__ import annotations

import contextlib
import sys
from types import SimpleNamespace
from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ZGame
import zgame.player_projectiles as player_projectiles


class DummyFX:
    def __init__(self):
        self.explosions = []

    def spawn_explosion(self, *args, **kwargs):
        self.explosions.append((args, kwargs))


class DummyGameState:
    def __init__(self):
        self.obstacles = {}
        self.spatial = None
        self.spatial_query_radius = 0
        self.fx = DummyFX()
        self.texts = []
        self.spoils = []
        self.heals = []
        self.banners = []
        self.pending_bullets = []
        self.wanted_wave_active = False

    def add_damage_text(self, *args, **kwargs):
        self.texts.append((args, kwargs))

    def spawn_spoils(self, *args):
        self.spoils.append(args)

    def spawn_heal(self, *args):
        self.heals.append(args)

    def flash_banner(self, *args, **kwargs):
        self.banners.append((args, kwargs))


class DummyPlayer:
    def __init__(self):
        self.crit_chance = 0.0
        self.crit_mult = 2.0
        self.range = 400
        self.bullet_damage = 10
        self.rect = pygame.Rect(0, 0, 20, 20)
        self.rect.center = (0, 0)
        self.xp = 0

    def add_xp(self, amount):
        self.xp += int(amount)


class DummyEnemy:
    def __init__(
        self,
        *,
        x=40,
        y=40,
        hp=20,
        shield_hp=0,
        etype="basic",
        spoils=0,
        z_level=1,
        is_boss=False,
        is_elite=False,
    ):
        self.x = float(x)
        self.y = float(y)
        self.rect = pygame.Rect(int(x), int(y), 20, 20)
        self.hp = hp
        self.max_hp = max(hp, 1)
        self.shield_hp = shield_hp
        self.type = etype
        self.spoils = spoils
        self.z_level = z_level
        self.is_boss = is_boss
        self.is_elite = is_elite
        self.color = (10, 20, 30)
        self.attack = 1
        self.speed = 1


@contextlib.contextmanager
def patched_random(random_values=None, randint_value=None, uniform_value=None):
    old_random = player_projectiles.random.random
    old_randint = player_projectiles.random.randint
    old_uniform = player_projectiles.random.uniform
    values = list(random_values or [])

    def fake_random():
        if values:
            return values.pop(0)
        return 1.0

    def fake_randint(a, b):
        return randint_value if randint_value is not None else a

    def fake_uniform(a, b):
        return uniform_value if uniform_value is not None else a

    player_projectiles.random.random = fake_random
    player_projectiles.random.randint = fake_randint
    player_projectiles.random.uniform = fake_uniform
    try:
        yield
    finally:
        player_projectiles.random.random = old_random
        player_projectiles.random.randint = old_randint
        player_projectiles.random.uniform = old_uniform


@contextlib.contextmanager
def patched_game():
    names = [
        "apply_vuln_bonus",
        "dot_rounds_stats",
        "apply_dot_rounds_stack",
        "spawn_dot_rounds_hit_vfx",
        "increment_kill_count",
        "_bandit_death_notice",
        "roll_spoils_for_enemy",
        "spawn_splinter_children",
        "transfer_xp_to_neighbors",
        "trigger_explosive_rounds",
        "trigger_twin_enrage",
        "META",
        "HEAL_DROP_CHANCE_ENEMY",
        "SPOILS_BLOCK_DROP_CHANCE",
        "MIST_PHASE_CHANCE",
    ]
    old = {name: getattr(ZGame, name) for name in names}
    sink = SimpleNamespace(
        kills=0,
        bandit_notices=0,
        splinters=0,
        transfers=0,
        explosive=0,
        twin=0,
        dots=[],
        dot_vfx=[],
    )
    ZGame.apply_vuln_bonus = lambda z, dmg: dmg
    ZGame.dot_rounds_stats = lambda level, bullet_base: (1.0, 2.0, 3)
    ZGame.apply_dot_rounds_stack = (
        lambda target, damage_per_tick, duration, max_stacks: sink.dots.append(
            (target.type, damage_per_tick, duration, max_stacks)
        )
    )
    ZGame.spawn_dot_rounds_hit_vfx = lambda game_state, x, y: sink.dot_vfx.append((x, y))
    ZGame.increment_kill_count = lambda amount=1: setattr(sink, "kills", sink.kills + amount)
    ZGame._bandit_death_notice = lambda z, game_state: setattr(
        sink, "bandit_notices", sink.bandit_notices + 1
    )
    ZGame.roll_spoils_for_enemy = lambda z: 2
    ZGame.spawn_splinter_children = lambda parent, enemies, game_state, level_idx, wave_index: setattr(
        sink, "splinters", sink.splinters + 1
    ) or 3
    ZGame.transfer_xp_to_neighbors = lambda z, enemies: setattr(sink, "transfers", sink.transfers + 1)
    ZGame.trigger_explosive_rounds = lambda player, game_state, enemies, pos, bullet_base=0: setattr(
        sink, "explosive", sink.explosive + 1
    )
    ZGame.trigger_twin_enrage = lambda z, enemies, game_state: setattr(sink, "twin", sink.twin + 1)
    ZGame.META = {
        "dot_rounds_level": 0,
        "explosive_rounds_level": 0,
        "shrapnel_level": 0,
        "wanted_active": False,
        "spoils": 0,
        "wanted_poster_waves": 0,
    }
    ZGame.HEAL_DROP_CHANCE_ENEMY = 0.0
    ZGame.SPOILS_BLOCK_DROP_CHANCE = 0.0
    ZGame.MIST_PHASE_CHANCE = 0.0
    try:
        yield sink
    finally:
        for name, value in old.items():
            setattr(ZGame, name, value)


def make_bullet(dmg=10, x=50, y=50, vx=0, vy=0, source="player"):
    bullet = ZGame.Bullet(x, y, vx, vy, max_dist=400, damage=dmg, source=source)
    bullet.r = 6
    return bullet


def run_case(name, fn):
    try:
        fn()
        print(f"{name}: ok")
    except Exception as exc:
        print(f"{name}: FAIL: {type(exc).__name__}: {exc}")
        raise


def main():
    pygame.init()

    with patched_game() as sink:
        def case_basic_hit():
            gs = DummyGameState()
            player = DummyPlayer()
            enemy = DummyEnemy(hp=20)
            bullet = make_bullet(dmg=7)
            with patched_random([1.0]):
                bullet.update(0.0, gs, [enemy], player)
            assert enemy.hp == 13
            assert bullet.alive is False
            assert len(gs.texts) == 1

        def case_shield_overflow():
            gs = DummyGameState()
            player = DummyPlayer()
            enemy = DummyEnemy(hp=20, shield_hp=3)
            bullet = make_bullet(dmg=10)
            with patched_random([1.0]):
                bullet.update(0.0, gs, [enemy], player)
            assert enemy.shield_hp == -7
            assert enemy.hp == 13
            assert len(gs.texts) == 2
            assert bullet.alive is False

        def case_normal_kill_rewards():
            gs = DummyGameState()
            player = DummyPlayer()
            enemy = DummyEnemy(hp=5, spoils=1, z_level=2)
            enemies = [enemy]
            bullet = make_bullet(dmg=10)
            with patched_random([1.0, 1.0]):
                bullet.update(0.0, gs, enemies, player)
            assert enemy not in enemies
            assert player.xp > 0
            assert gs.spoils and gs.spoils[0][2] == 3
            assert sink.kills >= 1 and sink.transfers >= 1

        def case_bandit_kill():
            gs = DummyGameState()
            player = DummyPlayer()
            enemy = DummyEnemy(hp=5, etype="bandit")
            enemy._stolen_total = 20
            enemies = [enemy]
            ZGame.META.update({"wanted_active": True, "spoils": 0, "wanted_poster_waves": 3})
            bullet = make_bullet(dmg=10)
            with patched_random([1.0]):
                bullet.update(0.0, gs, enemies, player)
            assert enemy not in enemies
            assert gs.spoils and gs.spoils[0][2] == 27
            assert ZGame.META["wanted_active"] is False
            assert ZGame.META["spoils"] == 50

        def case_splinter_kill():
            gs = DummyGameState()
            player = DummyPlayer()
            enemy = DummyEnemy(hp=5, etype="splinter")
            enemy._can_split = True
            enemy._split_done = False
            enemies = [enemy]
            bullet = make_bullet(dmg=10)
            with patched_random([1.0]):
                bullet.update(0.0, gs, enemies, player)
            assert enemy not in enemies
            assert sink.splinters >= 1
            assert gs.spoils == []

        def case_shrapnel_spawn():
            gs = DummyGameState()
            player = DummyPlayer()
            enemy = DummyEnemy(hp=5)
            enemies = [enemy]
            ZGame.META.update({"shrapnel_level": 1})
            bullet = make_bullet(dmg=10)
            with patched_random([1.0, 0.0], randint_value=3, uniform_value=0.0):
                bullet.update(0.0, gs, enemies, player)
            assert len(gs.pending_bullets) == 3
            assert all(type(sb).__name__ == "Bullet" for sb in gs.pending_bullets)

        def case_enemy_ricochet():
            gs = DummyGameState()
            player = DummyPlayer()
            enemy1 = DummyEnemy(x=40, y=40, hp=5)
            enemy2 = DummyEnemy(x=120, y=40, hp=50)
            enemies = [enemy1, enemy2]
            bullet = make_bullet(dmg=10)
            bullet.ricochet_left = 1
            with patched_random([1.0, 1.0]):
                bullet.update(0.0, gs, enemies, player)
            assert bullet.alive is True
            assert bullet.ricochet_left == 0
            assert bullet.vx > 0

        def case_destructible_obstacle():
            gs = DummyGameState()
            player = DummyPlayer()
            ob = SimpleNamespace(type="Destructible", health=5, rect=pygame.Rect(40, 40, 20, 20))
            gs.obstacles[(1, 1)] = ob
            bullet = make_bullet(dmg=10, x=50, y=50)
            with patched_random([1.0]):
                bullet.update(0.0, gs, [], player)
            assert (1, 1) not in gs.obstacles
            assert player.xp == ZGame.XP_PLAYER_BLOCK
            assert bullet.alive is False

        def case_mist_phase_teleport():
            gs = DummyGameState()
            player = DummyPlayer()
            player.rect.center = (0, 0)
            enemy = DummyEnemy(x=40, y=40, hp=50, etype="boss_mist")
            enemies = [enemy]
            ZGame.MIST_PHASE_CHANCE = 1.0
            bullet = make_bullet(dmg=10)
            with patched_random([1.0, 0.0]):
                bullet.update(0.0, gs, enemies, player)
            assert bullet.alive is False
            assert enemy.hp == 50
            assert any(args[2] == "TELEPORT" for args, kwargs in gs.texts)

        cases = [
            ("basic_hit", case_basic_hit),
            ("shield_overflow", case_shield_overflow),
            ("normal_kill_rewards", case_normal_kill_rewards),
            ("bandit_kill", case_bandit_kill),
            ("splinter_kill", case_splinter_kill),
            ("shrapnel_spawn", case_shrapnel_spawn),
            ("enemy_ricochet", case_enemy_ricochet),
            ("destructible_obstacle", case_destructible_obstacle),
            ("mist_phase_teleport", case_mist_phase_teleport),
        ]
        for name, fn in cases:
            run_case(name, fn)

    print("all bullet runtime scenarios passed")


if __name__ == "__main__":
    main()
