from __future__ import annotations

import random
import time

import pygame
from zgame import runtime_state as rs


def _state(game):
    return rs.runtime(game)


def _meta(game):
    return rs.meta(game)


def is_boss_level(game, level_idx_zero_based: int) -> bool:
    return ((level_idx_zero_based + 1) % game.BOSS_EVERY_N_LEVELS) == 0


def budget_for_level(game, level_idx_zero_based: int) -> int:
    budget = max(
        game.THREAT_BUDGET_MIN,
        int(round(game.THREAT_BUDGET_BASE * (game.THREAT_BUDGET_EXP ** level_idx_zero_based))),
    )
    if getattr(game, "IS_WEB", False):
        mult = float(getattr(game, "WEB_THREAT_BUDGET_MULT", 1.0) or 1.0)
        budget = max(1, int(round(budget * mult)))
    return budget


def pick_type_by_budget(game, rem: int, level_idx_zero_based: int):
    def _unlocked(enemy_type: str) -> bool:
        if enemy_type == "splinter":
            return level_idx_zero_based >= game.SPLINTER_UNLOCK_LEVEL
        return True

    choices = [
        (enemy_type, weight)
        for enemy_type, weight in game.THREAT_WEIGHTS.items()
        if game.THREAT_COSTS.get(enemy_type, 999) <= rem and _unlocked(enemy_type)
    ]
    if not choices:
        return None
    total = sum(weight for _, weight in choices)
    roll = random.uniform(0, total)
    acc = 0.0
    for enemy_type, weight in choices:
        acc += weight
        if roll <= acc:
            return enemy_type
    return choices[-1][0]


def spawn_positions(game, game_state, player, enemies, want: int):
    all_pos = [(x, y) for x in range(game.GRID_SIZE) for y in range(game.GRID_SIZE)]
    blocked = set(game_state.obstacles.keys()) | set((item.x, item.y) for item in getattr(game_state, "items", []))
    px = int(player.rect.centerx // game.CELL_SIZE)
    py = int((player.rect.centery - game.INFO_BAR_HEIGHT) // game.CELL_SIZE)
    candidates = [pos for pos in all_pos if pos not in blocked and abs(pos[0] - px) + abs(pos[1] - py) >= 6]
    random.shuffle(candidates)
    occupied_cells = {
        (int((enemy.x + enemy.size // 2) // game.CELL_SIZE), int((enemy.y + enemy.size // 2) // game.CELL_SIZE))
        for enemy in enemies
    }
    out = []
    for pos in candidates:
        if pos in occupied_cells:
            continue
        out.append(pos)
        if len(out) >= want:
            break
    return out


def promote_to_boss(game, enemy):
    enemy.is_boss = True
    enemy.max_hp = int(enemy.max_hp * game.BOSS_HP_MULT_EXTRA)
    enemy.hp = enemy.max_hp
    enemy.attack = int(enemy.attack * game.BOSS_ATK_MULT_EXTRA)
    enemy.speed += game.BOSS_SPD_ADD_EXTRA
    old_cx, old_cy = enemy.rect.center
    enemy.size = int(game.CELL_SIZE * 1.6)
    enemy.rect = pygame.Rect(0, 0, enemy.size, enemy.size)
    enemy.rect.center = (old_cx, old_cy)
    enemy.x = float(enemy.rect.x)
    enemy.y = float(enemy.rect.y - game.INFO_BAR_HEIGHT)
    enemy._base_size = int(enemy.size)
    game.set_enemy_size_category(enemy)


def spawn_wave_with_budget(game, game_state, player, current_level: int, wave_index: int, enemies, cap: int) -> int:
    if len(enemies) >= cap:
        return 0
    budget = budget_for_level(game, current_level)
    web_diag = bool(getattr(game, "IS_WEB", False) and getattr(game, "WEB_DIAG_MODE", False))
    wave_started_at = time.perf_counter()
    force_boss = is_boss_level(game, current_level) and (wave_index == 0)
    if force_boss:
        budget = int(budget * game.THREAT_BOSS_BONUS)
    if web_diag:
        print(
            f"[WebSpawn] begin wave={int(wave_index)} level={int(current_level)} "
            f"enemies={len(enemies)} cap={int(cap)} budget={int(budget)}"
        )
    spots_started_at = time.perf_counter()
    spots = spawn_positions(game, game_state, player, enemies, want=budget)
    spots_elapsed_ms = (time.perf_counter() - spots_started_at) * 1000.0
    if web_diag:
        print(f"[WebSpawn] spots wave={int(wave_index)} count={len(spots)} took={spots_elapsed_ms:.1f}ms")
    spawned = 0
    boss_done = False
    spawned_types: list[str] = []
    state = _state(game)
    meta = _meta(game)
    try:
        level_idx = int(state.get("current_level", 0))
    except Exception:
        level_idx = 0
    time_left = float(state.get("_time_left_runtime", game.LEVEL_TIME_LIMIT))
    if (
        time_left > 20.0
        and level_idx >= game.BANDIT_MIN_LEVEL_IDX
        and not is_boss_level(game, level_idx)
        and not getattr(game_state, "bandit_spawned_this_level", False)
        and random.random() < game.BANDIT_SPAWN_CHANCE_PER_WAVE
        and spots
    ):
        gx, gy = spots.pop()
        cx = int(gx * game.CELL_SIZE + game.CELL_SIZE * 0.5)
        cy = int(gy * game.CELL_SIZE + game.CELL_SIZE * 0.5 + game.INFO_BAR_HEIGHT)
        bandit = game.make_coin_bandit((cx, cy), level_idx, wave_index, int(budget), player_dps=game.compute_player_dps(player))
        lockbox_level = int(meta.get("lockbox_level", 0))
        if lockbox_level > 0:
            baseline_coins = max(0, int(meta.get("spoils", 0)) + int(getattr(game_state, "spoils_gained", 0)))
            bandit.lockbox_level = lockbox_level
            bandit.lockbox_baseline = baseline_coins
            bandit.lockbox_floor = game.lockbox_protected_min(baseline_coins, lockbox_level)
        radar_level = int(meta.get("bandit_radar_level", 0))
        if radar_level > 0:
            bandit.radar_tagged = True
            bandit.radar_level = radar_level
            bandit._radar_base_speed = float(bandit.speed)
            mult = game.BANDIT_RADAR_SLOW_MULT[min(radar_level - 1, len(game.BANDIT_RADAR_SLOW_MULT) - 1)]
            dur = game.BANDIT_RADAR_SLOW_DUR[min(radar_level - 1, len(game.BANDIT_RADAR_SLOW_DUR) - 1)]
            bandit.speed = float(bandit.speed) * float(mult)
            bandit.radar_slow_left = float(dur)
            bandit.radar_ring_period = 2.0
            bandit.radar_ring_phase = 0.0
        enemies.append(bandit)
        spawned_types.append("bandit")
        game_state.bandit_spawned_this_level = True
        game_state.pending_focus = ("bandit", (cx, cy))
        if hasattr(game_state, "flash_banner"):
            game_state.flash_banner("COIN BANDIT!", sec=1.5)
        else:
            game_state.add_damage_text(cx, cy, "COIN BANDIT!", crit=True, kind="shield")
        game_state.bandit_countdown_center_t = float(game.BANDIT_COUNTDOWN_CENTER_TIME)
        game_state._bandit_countdown_tick_ms = None
        if hasattr(game_state, "telegraphs"):
            game_state.telegraphs.append(
                game.TelegraphCircle(cx, cy, int(game.CELL_SIZE * 1.1), 0.9, kind="bandit", color=(255, 215, 0))
            )
        game.apply_biome_on_enemy_spawn(bandit, game_state)

    i = 0
    while i < len(spots) and len(enemies) < cap:
        gx, gy = spots[i]
        i += 1
        if force_boss and not boss_done:
            gx0 = max(0, min(gx, game.GRID_SIZE - game.BOSS_FOOTPRINT_TILES))
            gy0 = max(0, min(gy, game.GRID_SIZE - game.BOSS_FOOTPRINT_TILES))
            if game.ENABLE_TWIN_BOSS and (current_level in game.TWIN_BOSS_LEVELS):
                gx2 = max(0, min(gx0 + game.BOSS_FOOTPRINT_TILES, game.GRID_SIZE - game.BOSS_FOOTPRINT_TILES))
                gy2 = gy0
                boss_one = game.create_memory_devourer((gx0, gy0), current_level)
                boss_two = game.create_memory_devourer((gx2, gy2), current_level)
                twin_id = random.randint(1000, 9999)
                boss_one.twin_slot = +1
                boss_two.twin_slot = -1

                def _clear_footprint(ent):
                    rect = pygame.Rect(int(ent.x), int(ent.y + game.INFO_BAR_HEIGHT), int(ent.size), int(ent.size))
                    for gp, obstacle in list(game_state.obstacles.items()):
                        if obstacle.rect.colliderect(rect):
                            del game_state.obstacles[gp]

                _clear_footprint(boss_one)
                _clear_footprint(boss_two)
                game.apply_biome_on_enemy_spawn(boss_one, game_state)
                game.apply_biome_on_enemy_spawn(boss_two, game_state)
                for boss in (boss_one, boss_two):
                    if getattr(boss, "shield_hp", 0) > 0 and getattr(boss, "max_hp", 0) > 0:
                        boss._hud_shield_vis = boss.shield_hp / float(max(1, boss.max_hp))
                if hasattr(boss_one, "bind_twin"):
                    boss_one.bind_twin(boss_two, twin_id)
                else:
                    boss_one.twin_id = twin_id
                    boss_two.twin_id = twin_id
                    boss_one._twin_partner_ref = boss_two
                    boss_two._twin_partner_ref = boss_one
                boss_one._spawn_wave_tag = wave_index
                boss_two._spawn_wave_tag = wave_index
                try:
                    focus_one = (int(boss_one.rect.centerx), int(boss_one.rect.centery))
                    focus_two = (int(boss_two.rect.centerx), int(boss_two.rect.centery))
                except Exception:
                    focus_one = (
                        int((gx0 + 1.0) * game.CELL_SIZE),
                        int((gy0 + 1.0) * game.CELL_SIZE + game.INFO_BAR_HEIGHT),
                    )
                    focus_two = (
                        int((gx2 + 1.0) * game.CELL_SIZE),
                        int((gy2 + 1.0) * game.CELL_SIZE + game.INFO_BAR_HEIGHT),
                    )
                game_state.focus_queue = getattr(game_state, "focus_queue", [])
                game_state.focus_queue += [("boss", focus_one), ("boss", focus_two)]
                enemies.append(boss_one)
                enemies.append(boss_two)
                spawned_types.extend(["boss_mem_twin", "boss_mem_twin"])
                boss_done = True
            elif current_level in game.MISTWEAVER_LEVELS:
                boss = game.MistweaverBoss((gx0, gy0), current_level)
                rect = pygame.Rect(int(boss.x), int(boss.y + game.INFO_BAR_HEIGHT), int(boss.size), int(boss.size))
                for gp, obstacle in list(game_state.obstacles.items()):
                    if obstacle.rect.colliderect(rect):
                        del game_state.obstacles[gp]
                game.apply_biome_on_enemy_spawn(boss, game_state)
                boss._hud_shield_vis = (
                    boss.shield_hp / float(max(1, boss.max_hp)) if getattr(boss, "shield_hp", 0) > 0 else 0.0
                )
                boss._spawn_wave_tag = wave_index
                enemies.append(boss)
                spawned_types.append("boss_mist")
                focus = (int(boss.rect.centerx), int(boss.rect.centery))
                game_state.focus_queue = getattr(game_state, "focus_queue", [])
                game_state.focus_queue.append(("boss", focus))
                boss_done = True
                if hasattr(game_state, "request_fog_field"):
                    game_state.request_fog_field(player)
            else:
                boss = game.create_memory_devourer((gx0, gy0), current_level)
                rect = pygame.Rect(int(boss.x), int(boss.y + game.INFO_BAR_HEIGHT), int(boss.size), int(boss.size))
                for gp, obstacle in list(game_state.obstacles.items()):
                    if obstacle.rect.colliderect(rect):
                        del game_state.obstacles[gp]
                game.apply_biome_on_enemy_spawn(boss, game_state)
                boss._hud_shield_vis = (
                    boss.shield_hp / float(max(1, boss.max_hp)) if getattr(boss, "shield_hp", 0) > 0 else 0.0
                )
                boss._spawn_wave_tag = wave_index
                try:
                    focus = (int(boss.rect.centerx), int(boss.rect.centery))
                except Exception:
                    focus = (
                        int((gx0 + 1.0) * game.CELL_SIZE),
                        int((gy0 + 1.0) * game.CELL_SIZE + game.INFO_BAR_HEIGHT),
                    )
                game_state.focus_queue = getattr(game_state, "focus_queue", [])
                game_state.focus_queue.append(("boss", focus))
                enemies.append(boss)
                spawned_types.append("boss_mem")
                boss_done = True
            continue

        remaining = budget - sum(
            game.THREAT_COSTS.get(getattr(enemy, "type", "basic"), 0)
            for enemy in enemies
            if getattr(enemy, "_spawn_wave_tag", -1) == wave_index
        )
        enemy_type = pick_type_by_budget(game, max(1, remaining), current_level)
        if not enemy_type:
            break
        enemy = game.make_scaled_enemy(
            (gx, gy),
            enemy_type,
            current_level,
            (1 if (is_boss_level(game, current_level) and wave_index == 0) else wave_index),
        )
        enemy._spawn_wave_tag = wave_index
        game.apply_biome_on_enemy_spawn(enemy, game_state)
        enemies.append(enemy)
        spawned_types.append(str(enemy_type or getattr(enemy, "type", "unknown")))
        spawned += 1
    total_elapsed_ms = (time.perf_counter() - wave_started_at) * 1000.0
    if web_diag or total_elapsed_ms >= 120.0:
        type_summary = ",".join(spawned_types[:8])
        if len(spawned_types) > 8:
            type_summary += ",..."
        print(
            f"[WebSpawn] end wave={int(wave_index)} spawned={int(spawned)} total={len(enemies)} "
            f"took={total_elapsed_ms:.1f}ms types={type_summary}"
        )
    return spawned
