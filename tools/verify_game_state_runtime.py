from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pygame

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ZGame


class DummyEnemy:
    def __init__(self, x=64, y=64, hp=30, shield_hp=0, etype="basic", is_boss=False, speed=1.0):
        self.rect = pygame.Rect(int(x), int(y), 20, 20)
        self.x = float(self.rect.x)
        self.y = float(self.rect.y - ZGame.INFO_BAR_HEIGHT)
        self.hp = hp
        self.max_hp = max(hp, 1)
        self.shield_hp = shield_hp
        self.type = etype
        self.is_boss = is_boss
        self.is_elite = False
        self.radius = 10
        self.size = 20
        self.color = (100, 120, 140)
        self.dot_rounds_stacks = []
        self.speed = speed


@contextlib.contextmanager
def patched_game():
    names = [
        "META",
        "ParticleSystem",
        "curing_paint_radius",
        "curing_paint_base_color",
        "curing_paint_stats",
        "curing_paint_kill_bonus",
        "spawn_curing_paint_spark_vfx",
        "ground_spikes_stats",
        "spawn_ground_spike_spawn_vfx",
        "spawn_ground_spike_hit_vfx",
        "apply_vuln_bonus",
        "_apply_aegis_pulse_damage",
        "mark_of_vulnerability_stats",
        "build_flow_field",
        "collide_and_slide_circle",
        "draw_curing_paint_iso",
        "draw_enemy_paint_tile_iso",
        "draw_ground_spike_iso",
        "draw_iso_ground_ellipse",
        "draw_iso_hex_ring",
        "iso_screen_to_world_px",
        "iso_world_to_screen",
        "HELL_ENEMY_PAINT_STATIC",
    ]
    old = {name: getattr(ZGame, name) for name in names}
    sink = SimpleNamespace(vfx=[], aegis=[], flow=[], collide=[])

    class DummyParticleSystem:
        def __init__(self):
            self.particles = []

    ZGame.META = {
        "coin_magnet_radius": 40,
        "curing_paint_level": 1,
        "ground_spikes_level": 1,
        "base_dmg": ZGame.BULLET_DAMAGE_ENEMY,
        "dmg": 0,
        "carapace_shield_hp": 0,
        "vuln_mark_level": 1,
        "dot_rounds_level": 1,
        "kill_count": 0,
        "run_items_collected": 0,
        "spoils": 50,
        "lockbox_level": 0,
    }
    ZGame.ParticleSystem = DummyParticleSystem
    ZGame.curing_paint_radius = lambda lvl: 24.0
    ZGame.curing_paint_base_color = lambda player: (20, 200, 120)
    ZGame.curing_paint_stats = lambda lvl, bullet_base: (3.0, 1.0, 1)
    ZGame.curing_paint_kill_bonus = lambda kill_count: 1.0
    ZGame.spawn_curing_paint_spark_vfx = lambda gs, x, y, intensity: sink.vfx.append(("spark", x, y, intensity))
    ZGame.ground_spikes_stats = lambda lvl, bullet_base: (5.0, 1.0, 3)
    ZGame.spawn_ground_spike_spawn_vfx = lambda gs, x, y: sink.vfx.append(("spike_spawn", x, y))
    ZGame.spawn_ground_spike_hit_vfx = lambda gs, x, y: sink.vfx.append(("spike_hit", x, y))
    ZGame.apply_vuln_bonus = lambda z, dmg: dmg + int(getattr(z, "_vuln_mark_bonus", 0.0) > 0)
    ZGame._apply_aegis_pulse_damage = lambda player, gs, enemies, x, y, r, damage: sink.aegis.append(
        (x, y, r, damage, len(enemies or []))
    )
    ZGame.mark_of_vulnerability_stats = lambda lvl: (0.25, 0.5, 1.0)
    ZGame.build_flow_field = lambda grid_size, obstacles, goal_xy, pad=0: ({goal_xy: 0}, {goal_xy: goal_xy})
    ZGame.collide_and_slide_circle = lambda ent, obstacles, dx, dy: sink.collide.append(
        (type(ent).__name__, round(dx, 3), round(dy, 3))
    )
    ZGame.draw_curing_paint_iso = lambda screen, p, camx, camy, static=False: sink.vfx.append(("draw_curing", static))
    ZGame.draw_enemy_paint_tile_iso = lambda screen, gx, gy, tile, camx, camy, static=False: sink.vfx.append(
        ("draw_enemy_paint", gx, gy, static)
    )
    ZGame.draw_ground_spike_iso = lambda screen, s, camx, camy: sink.vfx.append(("draw_spike", s.x, s.y))
    ZGame.draw_iso_ground_ellipse = lambda *args, **kwargs: sink.vfx.append(("draw_ellipse", kwargs.get("fill", False)))
    ZGame.draw_iso_hex_ring = lambda *args, **kwargs: sink.vfx.append(("draw_hex", kwargs.get("sides", 0)))
    ZGame.iso_screen_to_world_px = lambda sx, sy, camx, camy: (sx + camx, sy + camy)
    ZGame.iso_world_to_screen = lambda wx, wy, wz=0, camx=0, camy=0: (
        int(wx * ZGame.CELL_SIZE - camx),
        int(wy * ZGame.CELL_SIZE + ZGame.INFO_BAR_HEIGHT - camy - wz),
    )
    ZGame.HELL_ENEMY_PAINT_STATIC = True
    try:
        yield sink
    finally:
        for name, value in old.items():
            setattr(ZGame, name, value)


def make_player():
    player = ZGame.Player((0, 0))
    player.rect.center = (64, 64)
    player.x = player.rect.x
    player.y = player.rect.y - ZGame.INFO_BAR_HEIGHT
    player._last_move_vec = (20.0, 0.0)
    player.max_hp = 100
    player.hp = 100
    player.bullet_damage = 10
    player.shield_hp = 0
    player.bone_plating_level = 0
    player.bone_plating_hp = 0
    return player


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
        def case_spawn_projectile():
            gs = ZGame.GameState({}, set(), [], [])
            gs.spawn_projectile("p1")
            assert gs.projectiles == ["p1"]

        def case_collect_and_lose_coins():
            gs = ZGame.GameState({}, set(), [], [])
            gs.spawn_spoils(64, 64, 2)
            player = make_player()
            gained = gs.collect_spoils(player.rect)
            taken = gs.lose_coins(1)
            assert gained == 2
            assert taken == 1

        def case_items_and_heals():
            item = ZGame.Item(0, 0)
            gs = ZGame.GameState({}, {item}, [], [])
            player = make_player()
            player.rect = item.rect.copy()
            assert gs.collect_item(player.rect) is True
            gs.spawn_heal(64, 64, 5)
            player.rect.center = gs.heals[0].rect.center
            player.hp = 90
            healed = gs.collect_heals(player)
            assert healed == 5

        def case_acid_damage():
            gs = ZGame.GameState({}, set(), [], [])
            player = make_player()
            gs.spawn_acid_pool(player.rect.centerx, player.rect.centery, r=18, dps=10, life=1.0)
            gs.update_acids(0.5, player)
            assert player.acid_dot_timer > 0.0
            assert player.slow_t > 0.0

        def case_enemy_paint():
            gs = ZGame.GameState({}, set(), [], [])
            player = make_player()
            gs.apply_enemy_paint(player.rect.centerx, player.rect.centery, 24)
            gs.update_enemy_paint(0.25, player)
            assert getattr(player, "_enemy_paint_slow", 0.0) > 0.0

        def case_curing_paint():
            gs = ZGame.GameState({}, set(), [], [])
            player = make_player()
            enemy = DummyEnemy(x=64, y=64, hp=20)
            gs.update_curing_paint(0.3, player, [enemy])
            gs.update_curing_paint(0.3, player, [enemy])
            assert gs.curing_paint
            assert enemy.hp < 20

        def case_ground_spikes():
            gs = ZGame.GameState({}, set(), [], [])
            player = make_player()
            enemy = DummyEnemy(x=64, y=64, hp=20)
            gs.update_ground_spikes(0.3, player, [enemy])
            gs.update_ground_spikes(0.3, player, [enemy])
            assert enemy.hp < 20

        def case_telegraph_and_acid():
            gs = ZGame.GameState({}, set(), [], [])
            gs.spawn_telegraph(
                10,
                20,
                8,
                0.1,
                kind="acid",
                payload={"points": [(5, 6)], "radius": 7, "dps": 2, "slow": 0.3, "life": 1.2},
            )
            gs.update_telegraphs(0.2)
            assert len(gs.telegraphs) == 0
            assert len(gs.acids) == 1

        def case_aegis():
            gs = ZGame.GameState({}, set(), [], [])
            player = make_player()
            gs.aegis_pulses = [SimpleNamespace(t=1.0, life0=1.0, delay=0.0, x=10.0, y=20.0, r=30.0, damage=4, hit_done=False)]
            gs.update_aegis_pulses(0.1, player, [DummyEnemy()])
            assert sink.aegis
            assert gs.aegis_pulses

        def case_damage_player():
            gs = ZGame.GameState({}, set(), [], [])
            player = make_player()
            ZGame.META["carapace_shield_hp"] = 3
            player.carapace_hp = 3
            player.shield_hp = 2
            remaining = gs.damage_player(player, 7)
            assert remaining >= 0
            assert player.hp == 98
            assert ZGame.META["carapace_shield_hp"] == 0

        def case_flow_field():
            gs = ZGame.GameState({}, set(), [], [])
            gs.refresh_flow_field((1, 2), dt=0.1)
            assert gs.ff_dist[(1, 2)] == 0
            assert gs.ff_next[(1, 2)] == (1, 2)

        def case_vuln_and_dot():
            gs = ZGame.GameState({}, set(), [], [])
            enemy = DummyEnemy(hp=20)
            gs.update_vulnerability_marks([enemy], 0.3)
            assert getattr(enemy, "_vuln_mark_t", 0.0) > 0.0
            enemy.dot_rounds_stacks = [{"dmg": 2.5, "t": 1.0}]
            gs.update_dot_rounds([enemy], 0.5)
            assert enemy.hp < 20

        def case_fog_and_draws():
            gs = ZGame.GameState({}, set(), [], [])
            player = make_player()
            gs.request_fog_field(player)
            screen = pygame.Surface((320, 240), pygame.SRCALPHA)
            gs.spawn_acid_pool(20, 20, r=10, dps=2, life=1.0)
            gs.ground_spikes.append(ZGame.GroundSpike(30, 30, 2, 1.0, 8, 1))
            gs.aegis_pulses.append(SimpleNamespace(t=1.0, life0=1.0, x=20.0, y=20.0, r=16.0))
            gs.apply_enemy_paint(40, 40, 18)
            gs.apply_player_paint(60, 60, 18)
            gs.draw_paint_iso(screen, 0, 0)
            gs.draw_hazards_iso(screen, 0, 0)
            gs.draw_lanterns_iso(screen, 0, 0)
            gs.draw_lanterns_topdown(screen, 0, 0)
            gs.draw_fog_overlay(screen, 0, 0, player, gs.obstacles)
            assert len(gs.fog_lanterns) > 0

        cases = [
            ("spawn_projectile", case_spawn_projectile),
            ("collect_and_lose_coins", case_collect_and_lose_coins),
            ("items_and_heals", case_items_and_heals),
            ("acid_damage", case_acid_damage),
            ("enemy_paint", case_enemy_paint),
            ("curing_paint", case_curing_paint),
            ("ground_spikes", case_ground_spikes),
            ("telegraph_and_acid", case_telegraph_and_acid),
            ("aegis", case_aegis),
            ("damage_player", case_damage_player),
            ("flow_field", case_flow_field),
            ("vuln_and_dot", case_vuln_and_dot),
            ("fog_and_draws", case_fog_and_draws),
        ]
        for name, fn in cases:
            run_case(name, fn)
    print("all gamestate runtime scenarios passed")


if __name__ == "__main__":
    main()
