"""Level and app flow extracted from ZGame.py."""
from __future__ import annotations
import asyncio
import builtins
import copy
import math
import os
import random
import sys
from typing import Dict, List, Optional, Set, Tuple
import pygame
from zgame.browser import (
    WebRuntimeProfiler,
    _set_browser_profiler_phase,
    _set_browser_profiler_metrics,
    browser_now_s,
    clamp_web_dt,
    is_escape_event,
    is_web_interaction_event,
)
from zgame import runtime_state as rs


def _append_verified_bullet(game, bullets, bullet, player=None) -> None:
    if bullet is None:
        return
    if hasattr(game, "verify_bullet_runtime") and (not game.verify_bullet_runtime(bullet, player)):
        return
    bullets.append(bullet)


def _flush_pending_bullets(game, bullets, game_state, player=None) -> None:
    pending = getattr(game_state, "pending_bullets", None)
    if not pending:
        return
    for bullet in list(pending):
        if hasattr(game, "verify_bullet_runtime") and (not game.verify_bullet_runtime(bullet, player)):
            continue
        bullets.append(bullet)
    pending.clear()


def _sanitize_enemy_shots(game, enemy_shots) -> None:
    if not hasattr(game, "verify_enemy_shot_runtime"):
        return
    enemy_shots[:] = [shot for shot in enemy_shots if game.verify_enemy_shot_runtime(shot)]


def _frame_dt(game, clock: pygame.time.Clock) -> float:
    runtime = rs.runtime(game)
    if not game.IS_WEB:
        raw_dt = clock.tick(60) / 1000.0
        runtime["_last_raw_frame_dt_s"] = raw_dt
        return raw_dt
    # Avoid blocking SDL sleep on web; let the browser event loop drive cadence.
    now_s = browser_now_s()
    last_s = float(runtime.get("_web_last_frame_s", now_s) or now_s)
    raw_dt = max(0.0, now_s - last_s)
    runtime["_web_last_frame_s"] = now_s
    if raw_dt <= 0.0:
        raw_dt = 1.0 / max(30.0, float(getattr(game, "WEB_TARGET_FPS", 30) or 30))
    runtime["_last_raw_frame_dt_s"] = raw_dt
    target_dt = 1.0 / max(1.0, float(getattr(game, "WEB_TARGET_FPS", 30) or 30))
    accum = float(runtime.get("_web_frame_accum_s", 0.0) or 0.0) + raw_dt
    idle_loops = int(runtime.get("_web_idle_loops", 0) or 0)
    if accum + 1e-6 < target_dt:
        idle_loops += 1
        runtime["_web_frame_accum_s"] = accum
        runtime["_web_idle_loops"] = idle_loops
        try:
            _set_browser_profiler_metrics(idle_loops=idle_loops, accum_ms=accum * 1000.0)
        except Exception:
            pass
        # Fallback heartbeat: if the browser/runtime keeps resuming us but the
        # accumulated delta never crosses target_dt, force one simulation step
        # after a short burst so gameplay does not dead-freeze.
        if idle_loops < 8:
            return 0.0
        runtime["_web_frame_accum_s"] = 0.0
        runtime["_web_idle_loops"] = 0
        return clamp_web_dt(max(target_dt, accum))
    runtime["_web_frame_accum_s"] = 0.0
    runtime["_web_idle_loops"] = 0
    # Browser tabs can resume with a very large frame delta; clamp that so
    # movement, timers, and spawn logic do not fast-forward in one frame.
    return clamp_web_dt(accum)


async def _yield_web_frame(game) -> None:
    if not getattr(game, "IS_WEB", False):
        return
    # Follow pygbag's own scheduling model instead of yielding unconditionally.
    # On wasm builds, embed.sched_yield() decides when it's safe/necessary to
    # hand control back to the browser loop.
    sched = getattr(builtins, "sched_yield", None)
    try:
        should_yield = True if sched is None else bool(sched())
    except Exception:
        should_yield = True
    if should_yield:
        await asyncio.sleep(0)


def _pump_web_idle_events(game, screen, on_focus_lost=None):
    for event in pygame.event.get():
        screen = game._handle_web_window_event(event) or screen
        game._sync_web_input_event(event)
        _resume_web_audio_on_event(game, event)
        if getattr(event, "type", None) in {
            getattr(pygame, "WINDOWFOCUSLOST", None),
        }:
            if on_focus_lost is not None:
                try:
                    on_focus_lost()
                except Exception:
                    pass
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
    return screen


def _resume_web_audio_on_event(game, event) -> None:
    if (not getattr(game, "IS_WEB", False)) or (not is_web_interaction_event(event)):
        return
    try:
        game._resume_bgm_if_needed(min_interval_s=0.0)
    except Exception:
        pass


def _web_feature_enabled(game, flag_name: str) -> bool:
    if not getattr(game, "IS_WEB", False):
        return True
    return bool(getattr(game, flag_name, False))


def _web_profiler(game) -> WebRuntimeProfiler | None:
    if not getattr(game, "IS_WEB", False):
        return None
    profiler = getattr(game, "_web_profiler", None)
    if not isinstance(profiler, WebRuntimeProfiler):
        profiler = WebRuntimeProfiler()
        setattr(game, "_web_profiler", profiler)
    return profiler


def _profile_begin(game, dt_s: float) -> WebRuntimeProfiler | None:
    profiler = _web_profiler(game)
    if profiler is not None:
        raw_dt_s = float(rs.runtime(game).get("_last_raw_frame_dt_s", dt_s) or dt_s)
        profiler.begin_frame(dt_s, raw_dt_s=raw_dt_s)
    return profiler


def _profile_mark(profiler: WebRuntimeProfiler | None, phase: str) -> None:
    if profiler is not None:
        profiler.mark(phase)


def _profile_set_counters(game, profiler: WebRuntimeProfiler | None, game_state, enemies, bullets, enemy_shots,
                          *, wave_index: int = 0, rendered: bool = False) -> None:
    if profiler is None:
        return
    profiler.counter("obs", len(getattr(game_state, "obstacles", {}) or {}))
    profiler.counter("en", len(enemies or ()))
    profiler.counter("b", len(bullets or ()))
    profiler.counter("es", len(enemy_shots or ()))
    profiler.counter("wave", int(wave_index))
    runtime = rs.runtime(game)
    profiler.counter(
        "trans",
        int(bool(runtime.get("_web_hex_transition_state") is not None or runtime.get("_menu_transition_frame") is not None)),
    )
    profiler.counter("rendered", int(bool(rendered)))
    bgm = runtime.get("_bgm")
    if bgm is None:
        profiler.counter("audio", "none")
    else:
        path = str(getattr(bgm, "music_path", "") or "").lower()
        if "intro_v0" in path:
            track = "intro"
        elif "zgame" in path:
            track = "combat"
        else:
            track = "other"
        backend = "html" if bool(getattr(bgm, "_native_web_audio", False)) else "mixer"
        profiler.counter("audio", f"{backend}:{track}")


def _profile_finish(game, profiler: WebRuntimeProfiler | None, game_state, enemies, bullets, enemy_shots,
                    *, wave_index: int = 0, rendered: bool = False) -> None:
    if profiler is None:
        return
    _profile_set_counters(
        game,
        profiler,
        game_state,
        enemies,
        bullets,
        enemy_shots,
        wave_index=wave_index,
        rendered=rendered,
    )
    profiler.finish(rendered=rendered)


def _combat_bgm_selected(game) -> bool:
    runtime = rs.runtime(game)
    bgm = runtime.get("_bgm")
    path = str(getattr(bgm, "music_path", "") or "").lower()
    return any(token in path for token in ("zgame.wav", "zgame.ogg"))


def _web_snapshot_autosave(game, runtime, game_state, player, enemies, current_level: int, chosen_enemy_type: str,
                           bullets=None, *, force: bool = False) -> None:
    if not getattr(game, "IS_WEB", False):
        return
    interval = float(getattr(game, "WEB_AUTOSAVE_INTERVAL", 0.0) or 0.0)
    if (not force) and interval <= 0.0:
        return
    now_s = pygame.time.get_ticks() / 1000.0
    last_s = float(runtime.get("_last_web_autosave_s", -999.0))
    if (not force) and interval > 0.0 and (now_s - last_s) < interval:
        return
    try:
        runtime["_carry_player_state"] = game.capture_player_carry(player)
        game.save_progress(current_level, max_wave_reached=runtime.get("_max_wave_reached", None))
        runtime["_last_web_autosave_s"] = now_s
    except Exception:
        pass


async def _yield_web_boot_frame(game, screen, runtime=None, *, fill_black: bool = True, count: int = 1) -> None:
    if not getattr(game, "IS_WEB", False):
        return
    runtime = runtime or rs.runtime(game)
    loops = max(1, int(count))
    for _ in range(loops):
        if fill_black:
            screen.fill((0, 0, 0))
        pygame.display.flip()
        await asyncio.sleep(0)


async def _show_web_boot_surface(game, screen, runtime=None, *, count: int = 1) -> None:
    if not getattr(game, "IS_WEB", False):
        return
    try:
        screen.blit(game.ensure_hex_background(), (0, 0))
    except Exception:
        screen.fill((0, 0, 0))
    await _yield_web_boot_frame(game, screen, runtime, fill_black=False, count=count)


async def _preload_web_gameplay_assets(game, screen, runtime=None) -> None:
    if not getattr(game, "IS_WEB", False):
        return
    runtime = runtime or rs.runtime(game)
    if runtime.get("_web_gameplay_assets_ready", False):
        return
    base_size = int(game.CELL_SIZE * 0.6)
    player_target = (
        int(base_size * 2.0 * game.PLAYER_SPRITE_SCALE),
        int(base_size * 2.4 * game.PLAYER_SPRITE_SCALE),
    )
    enemy_types = ("basic", "fast", "tank", "strong", "ranged", "buffer", "shielder")
    boot_tasks = [
        lambda: game._load_shop_sprite("characters/player/sheets/player.png", player_target, allow_upscale=False),
        *(lambda zt=zt: game._enemy_sprite(zt, base_size) for zt in enemy_types),
        lambda: game._enemy_sprite("ravager", max(base_size * 2, base_size)),
        *(lambda d=direction: game._auto_turret_sprite(d) for direction in ("left", "right", "up", "down")),
        lambda: game.get_stationary_turret_assets(),
    ]
    for load in boot_tasks:
        try:
            load()
        except Exception:
            pass
        await _show_web_boot_surface(game, screen, runtime, count=1)
    runtime["_web_gameplay_assets_ready"] = True


def _demo_level_limit(game) -> int:
    if not getattr(game, "WEB_DEMO", False):
        return 0
    try:
        return max(0, int(getattr(game, "WEB_DEMO_LEVEL_LIMIT", 0)))
    except Exception:
        return 0


def _demo_complete_for_level(game, level_idx: int) -> bool:
    limit = _demo_level_limit(game)
    return limit > 0 and int(level_idx) >= (limit - 1)


def _effective_level_time_limit(game, level_idx: int) -> float:
    base_limit = float(game.BOSS_TIME_LIMIT) if game.is_boss_level(level_idx) else float(game.LEVEL_TIME_LIMIT)
    if not getattr(game, "WEB_DEMO", False):
        return base_limit
    demo_limit = float(game.WEB_DEMO_BOSS_TIME_LIMIT) if game.is_boss_level(level_idx) else float(game.WEB_DEMO_LEVEL_TIME_LIMIT)
    return min(base_limit, demo_limit)


async def main_run_level(game, config, chosen_enemy_type: str) -> Tuple[str, Optional[str], pygame.Surface]:
    runtime = rs.runtime(game)
    meta = rs.meta(game)
    pygame.display.set_caption('Enemy Card Game 闂?Level')
    screen = pygame.display.get_surface()
    clock = pygame.time.Clock()
    if game.IS_WEB and runtime.get("_menu_transition_frame") is not None:
        await asyncio.sleep(0)
    await _preload_web_gameplay_assets(game, screen, runtime)
    game_state = None
    wanted_active_for_level = False
    level_idx = int(runtime.get('current_level', 0))
    if level_idx == 0:
        meta['run_items_spawned'] = 0
        meta['run_items_collected'] = 0
    runtime['_run_items_spawned_start'] = int(meta.get('run_items_spawned', 0))
    runtime['_run_items_collected_start'] = int(meta.get('run_items_collected', 0))
    time_left = _effective_level_time_limit(game, level_idx)
    runtime['_time_left_runtime'] = time_left
    runtime['_coins_at_level_start'] = int(meta.get('spoils', 0))
    level_config = game._web_level_config(config)
    enemy_cap = game.WEB_ENEMY_CAP if game.IS_WEB else game.ENEMY_CAP
    combat_bgm_started = _combat_bgm_selected(game)
    if game.IS_WEB and bool(getattr(game, "WEB_SINGLE_BGM", False)):
        # Browser compatibility mode: avoid delayed mid-run track swaps.
        # Real browser repros consistently freeze at the first combat-track
        # switch, so keep the currently armed BGM alive for the whole session.
        combat_bgm_started = True
    if not game.IS_WEB:
        game.play_combat_bgm()
        combat_bgm_started = True
    else:
        await asyncio.sleep(0)
    spatial = game.SpatialHash(game.SPATIAL_CELL)
    obstacles, items, player_start, enemy_starts, main_item_list, decorations = game.generate_game_entities(
        grid_size=game.GRID_SIZE,
        obstacle_count=level_config['obstacle_count'],
        item_count=level_config['item_count'],
        enemy_count=level_config['enemy_count'],
        main_block_hp=level_config['block_hp'],
        level_idx=level_idx,
        use_density=not bool(getattr(game, "IS_WEB", False)),
    )
    if game.IS_WEB:
        await asyncio.sleep(0)
    last_counted_level = runtime.get('_items_counted_level')
    if last_counted_level != level_idx:
        meta['run_items_spawned'] = int(meta.get('run_items_spawned', 0)) + len(items)
        runtime['_items_counted_level'] = level_idx
    game.ensure_passage_budget(obstacles, game.GRID_SIZE, player_start)
    game_state = game.GameState(obstacles, items, main_item_list, decorations)
    if game.IS_WEB:
        await asyncio.sleep(0)
    game_state.spatial = spatial
    game_state.current_level = game.current_level
    game_state.bandit_spawned_this_level = False
    wp = int(meta.get('wanted_poster_waves', 0))
    if wp > 0:
        meta['wanted_poster_waves'] = max(0, wp - 1)
        meta['wanted_active'] = True
        wanted_active_for_level = True
    else:
        meta['wanted_active'] = False
    game_state.wanted_wave_active = bool(meta.get('wanted_active', False))
    level_idx = int(getattr(game_state, 'current_level', 0))
    time_left = _effective_level_time_limit(game, level_idx)
    runtime['_time_left_runtime'] = time_left
    player = game.Player(player_start, speed=game.PLAYER_SPEED)
    player.fire_cd = 0.0
    game.apply_player_carry(player, runtime.get('_carry_player_state'))
    if int(runtime.get('_baseline_for_level', -1)) == int(game.current_level):
        baseline = runtime.get('_player_level_baseline', None)
        if isinstance(baseline, dict) and baseline.get('biome') is not None:
            runtime['_next_biome'] = baseline.get('biome')
    game.apply_domain_buffs_for_level(game_state, player)
    if hasattr(player, 'on_level_start'):
        player.on_level_start()
    runtime['_next_biome'] = None
    turret_level = int(meta.get('auto_turret_level', 0))
    turrets: List[game.AutoTurret] = []
    if turret_level > 0:
        for i in range(turret_level):
            angle = 2.0 * math.pi * i / max(1, turret_level)
            off_x = math.cos(angle) * game.AUTO_TURRET_OFFSET_RADIUS
            off_y = math.sin(angle) * game.AUTO_TURRET_OFFSET_RADIUS
            turrets.append(game.AutoTurret(player, (off_x, off_y)))
    stationary_count = int(meta.get('stationary_turret_count', 0))
    added_stationary = False
    if stationary_count > 0:
        for _ in range(stationary_count):
            for _attempt in range(40):
                gx = random.randrange(game.GRID_SIZE)
                gy = random.randrange(game.GRID_SIZE)
                if (gx, gy) in game_state.obstacles:
                    continue
                wx = gx * game.CELL_SIZE + game.CELL_SIZE // 2
                wy = gy * game.CELL_SIZE + game.CELL_SIZE // 2 + game.INFO_BAR_HEIGHT
                turret = game.StationaryTurret(wx, wy)
                turrets.append(turret)
                game_state.obstacles[gx, gy] = game.StationaryTurretObstacle(turret.rect)
                added_stationary = True
                break
    if added_stationary and hasattr(game_state, 'mark_nav_dirty'):
        game_state.mark_nav_dirty()
    game_state.turrets = turrets
    ztype_map = {'enemy_fast': 'fast', 'enemy_tank': 'tank', 'enemy_strong': 'strong', 'basic': 'basic'}
    zt = ztype_map.get(chosen_enemy_type, 'basic')
    enemies = [game.Enemy(pos, speed=game.ENEMY_SPEED, ztype=zt) for pos in enemy_starts]
    bullets: List[game.Bullet] = []
    enemy_shots: List[game.EnemyShot] = []
    spawn_timer = 0.0
    wave_index = 0
    spatial_rebuild_t = 0.0
    spatial_enemy_count = -1
    combat_bgm_delay = 0.75 if game.IS_WEB else 0.0

    def player_center():
        return (player.x + player.size / 2, player.y + player.size / 2 + game.INFO_BAR_HEIGHT)

    def pick_enemy_type_weighted():
        table = [('basic', 50), ('fast', 15), ('tank', 10), ('ranged', 12), ('suicide', 8), ('buffer', 3), ('shielder', 2)]
        r = random.uniform(0, sum((w for _, w in table)))
        acc = 0
        for t, w in table:
            acc += w
            if r <= acc:
                return t
        return 'basic'

    def find_spawn_positions(n: int) -> List[Tuple[int, int]]:
        all_pos = [(x, y) for x in range(game.GRID_SIZE) for y in range(game.GRID_SIZE)]
        blocked = set(game_state.obstacles.keys()) | set(((i.x, i.y) for i in game_state.items))
        px, py = player.pos
        cand = [p for p in all_pos if p not in blocked and abs(p[0] - px) + abs(p[1] - py) >= 6]
        random.shuffle(cand)
        zcells = {(int((z.x + z.size // 2) // game.CELL_SIZE), int((z.y + z.size // 2) // game.CELL_SIZE)) for z in enemies}
        out = []
        for p in cand:
            if p in zcells:
                continue
            out.append(p)
            if len(out) >= n:
                break
        return out

    def find_target():
        px, py = (player.rect.centerx, player.rect.centery)
        pgx = int(px // game.CELL_SIZE)
        pgy = int((py - game.INFO_BAR_HEIGHT) // game.CELL_SIZE)
        force_blocks = []
        for gp, ob in game_state.obstacles.items():
            if getattr(ob, 'type', '') != 'Destructible':
                continue
            gx, gy = gp
            manh = abs(gx - pgx) + abs(gy - pgy)
            if manh <= int(game.PLAYER_BLOCK_FORCE_RANGE_TILES):
                cx, cy = (ob.rect.centerx, ob.rect.centery)
                d2 = (cx - px) ** 2 + (cy - py) ** 2
                force_blocks.append((d2, ('block', gp, ob, cx, cy)))
        if force_blocks:
            force_blocks.sort(key=lambda t: t[0])
            best_tuple = force_blocks[0][1]
            d = force_blocks[0][0] ** 0.5
            return (best_tuple, d)
        cur_range = game.clamp_player_range(getattr(player, 'range', game.PLAYER_RANGE_DEFAULT))
        R2 = cur_range ** 2
        z_cands = []
        for z in enemies:
            cx, cy = (z.rect.centerx, z.rect.centery)
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 <= R2:
                z_cands.append((z, cx, cy, d2))
        b_cands = []
        for gp, ob in game_state.obstacles.items():
            if getattr(ob, 'type', '') != 'Destructible':
                continue
            cx, cy = (ob.rect.centerx, ob.rect.centery)
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 <= R2:
                b_cands.append((gp, ob, cx, cy, d2))
        if not z_cands and (not b_cands):
            return (None, None)
        DIST_K = 0.0001
        W_ENEMY = 1200.0
        W_BLOCK = 800.0
        best = None
        best_score = -1e+18
        for z, cx, cy, d2 in z_cands:
            s = -d2 * DIST_K + W_ENEMY
            if s > best_score:
                best_score = s
                best = ('enemy', None, z, cx, cy, d2)
        for gp, ob, cx, cy, d2 in b_cands:
            s = -d2 * DIST_K + W_BLOCK
            if s > best_score:
                best_score = s
                best = ('block', gp, ob, cx, cy, d2)
        if best is None:
            return (None, None)
        kind, gp_or_none, obj, cx, cy, d2 = best
        return ((kind, gp_or_none, obj, cx, cy), d2 ** 0.5)
    if int(runtime.get('_baseline_for_level', -999)) == int(game.current_level) and '_consumable_baseline' not in runtime:
        runtime['_consumable_baseline'] = {'carapace_shield_hp': int(meta.get('carapace_shield_hp', 0)), 'wanted_poster_waves': int(meta.get('wanted_poster_waves', 0)), 'wanted_active': bool(meta.get('wanted_active', False))}
    if int(runtime.get('_baseline_for_level', -999)) != int(game.current_level):
        game._capture_level_start_baseline(game.current_level, player, game_state)
    else:
        game._restore_level_start_baseline(game.current_level, player, game_state)
    spawned = game.spawn_wave_with_budget(game_state, player, game.current_level, wave_index, enemies, enemy_cap)
    if spawned > 0:
        wave_index += 1
        runtime['_max_wave_reached'] = max(runtime.get('_max_wave_reached', 0), wave_index)
    if game.IS_WEB:
        await asyncio.sleep(0)
    player._hit_flash = 0.0
    player._flash_prev_hp = int(player.hp)
    for z in enemies:
        z._hit_flash = 0.0
        z._flash_prev_hp = int(getattr(z, 'hp', 0))
    _web_snapshot_autosave(game, runtime, game_state, player, enemies, game.current_level, chosen_enemy_type, bullets, force=True)
    running = True
    game_result = None
    last_frame = None
    render_cooldown = 0.0
    web_transition_guard_t = 0.65 if game.IS_WEB else 0.0
    profiler = _web_profiler(game)
    clock.tick(game.WEB_TARGET_FPS if game.IS_WEB else 60)
    entry_freeze = 0.4
    while running:
        dt = _frame_dt(game, clock)
        if game.IS_WEB and dt <= 0.0:
            screen = _pump_web_idle_events(
                game,
                screen,
                on_focus_lost=lambda: _web_snapshot_autosave(
                    game, runtime, game_state, player, enemies, game.current_level, chosen_enemy_type, bullets, force=True
                ),
            )
            await _yield_web_frame(game)
            continue
        profiler = _profile_begin(game, dt)
        render_cooldown = max(0.0, render_cooldown - dt)
        if web_transition_guard_t > 0.0:
            web_transition_guard_t = max(0.0, web_transition_guard_t - dt)
            if web_transition_guard_t <= 0.0 and (
                runtime.get("_web_hex_transition_state") is not None
                or runtime.get("_menu_transition_frame") is not None
            ):
                game.clear_menu_transition_state()
        if entry_freeze > 0:
            entry_freeze = max(0.0, entry_freeze - dt)
            _profile_mark(profiler, "events")
            for event in pygame.event.get():
                screen = game._handle_web_window_event(event) or screen
                game._sync_web_input_event(event)
                _resume_web_audio_on_event(game, event)
                if getattr(event, "type", None) in {
                    getattr(pygame, "WINDOWFOCUSLOST", None),
                }:
                    _web_snapshot_autosave(
                        game, runtime, game_state, player, enemies, game.current_level, chosen_enemy_type, bullets, force=True
                    )
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
            game.update_hit_flash_timer(player, dt)
            for z in enemies:
                game.update_hit_flash_timer(z, dt)
            _profile_mark(profiler, "render")
            rendered = False
            if (not game.IS_WEB) or render_cooldown <= 0.0 or last_frame is None:
                last_frame = game.render_game_iso(
                    screen,
                    game_state,
                    player,
                    enemies,
                    bullets,
                    enemy_shots,
                    obstacles=game_state.obstacles,
                    copy_frame=False,
                )
                render_cooldown = float(getattr(game, "WEB_RENDER_INTERVAL", 0.0) or 0.0)
                rendered = True
            _profile_finish(
                game,
                profiler,
                game_state,
                enemies,
                bullets,
                enemy_shots,
                wave_index=wave_index,
                rendered=rendered,
            )
            if game.IS_WEB:
                await _yield_web_frame(game)
            continue
        if game.IS_WEB and (not combat_bgm_started):
            combat_bgm_delay = max(0.0, combat_bgm_delay - dt)
            if combat_bgm_delay <= 0.0:
                game.play_combat_bgm()
                combat_bgm_started = True
        _profile_mark(profiler, "pre")
        pf = getattr(game_state, 'pending_focus', None)
        if pf:
            _profile_mark(profiler, "focus")
            fkind, (fx, fy) = pf
            game.play_focus_cinematic_iso(screen, clock, game_state, player, enemies, bullets, enemy_shots, (fx, fy), label='BANDIT!' if fkind == 'bandit' else 'BOSS!')
            game_state.pending_focus = None
        fq = getattr(game_state, 'focus_queue', None)
        if fq:
            _profile_mark(profiler, "focus")
            if fq[0][0] == 'boss':
                boss_targets = []
                while fq and fq[0][0] == 'boss':
                    _, pos = fq.pop(0)
                    boss_targets.append(pos)
                game.play_focus_chain_iso(screen, clock, game_state, player, enemies, bullets, enemy_shots, boss_targets)
            else:
                tag, pos = fq.pop(0)
                lbl = 'COIN BANDIT!' if tag == 'bandit' else None
                game.play_focus_cinematic_iso(screen, clock, game_state, player, enemies, bullets, enemy_shots, pos, label=lbl, return_to_player=True)
        time_left -= dt
        runtime['_time_left_runtime'] = time_left
        if time_left <= 0:
            game_result = 'success' if 'game_result' in locals() else 'success'
            running = False
        _profile_mark(profiler, "spawn")
        spawn_timer += dt
        if spawn_timer >= game.SPAWN_INTERVAL:
            spawn_timer = 0.0
            if len(enemies) < enemy_cap:
                spawned = game.spawn_wave_with_budget(game_state, player, game.current_level, wave_index, enemies, enemy_cap)
                if spawned > 0:
                    wave_index += 1
                    runtime['_max_wave_reached'] = max(runtime.get('_max_wave_reached', 0), wave_index)
        _profile_mark(profiler, "events")
        for event in pygame.event.get():
            screen = game._handle_web_window_event(event) or screen
            game._sync_web_input_event(event)
            _resume_web_audio_on_event(game, event)
            if getattr(event, "type", None) in {
                getattr(pygame, "WINDOWFOCUSLOST", None),
            }:
                _web_snapshot_autosave(
                    game, runtime, game_state, player, enemies, game.current_level, chosen_enemy_type, bullets, force=True
                )
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.is_action_event(event, 'blast') and getattr(player, 'targeting_skill', None) == 'blast':
                player.targeting_skill = None
                player.skill_target_origin = None
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_t:
                game.activate_ultimate_mode(player, game_state)
            if game.is_action_event(event, 'teleport') and getattr(player, 'targeting_skill', None) == 'teleport':
                player.targeting_skill = None
                player.skill_target_origin = None
                continue
            if is_escape_event(event) and getattr(player, 'targeting_skill', None):
                player.targeting_skill = None
                continue
            if is_escape_event(event):
                bg = last_frame or game.render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots, obstacles=game_state.obstacles)
                choice, time_left = game.pause_game_modal(screen, bg, clock, time_left, player)
                if choice == 'continue':
                    pass
                elif choice == 'restart':
                    game.queue_menu_transition(pygame.display.get_surface().copy())
                    return ('restart', config.get('reward', None), bg)
                elif choice == 'home':
                    game.queue_menu_transition(pygame.display.get_surface().copy())
                    runtime['_carry_player_state'] = game.capture_player_carry(player)
                    game.save_progress(game.current_level, max_wave_reached=runtime.get('_max_wave_reached', None))
                    runtime['_skip_intro_once'] = True
                    return ('home', config.get('reward', None), bg)
                elif choice == 'exit':
                    runtime['_carry_player_state'] = game.capture_player_carry(player)
                    game.save_progress(game.current_level, max_wave_reached=runtime.get('_max_wave_reached', None))
                    return ('exit', config.get('reward', None), bg)
            if game.is_action_event(event, 'blast'):
                if getattr(player, 'blast_cd', 0.0) <= 0.0:
                    player.targeting_skill = 'blast'
                    player.skill_target_origin = None
                    game._update_skill_target(player, game_state)
                else:
                    player.skill_flash['blast'] = 0.35
            if game.is_action_event(event, 'teleport'):
                if getattr(player, 'teleport_cd', 0.0) <= 0.0:
                    player.targeting_skill = 'teleport'
                    player.skill_target_origin = None
                    game._update_skill_target(player, game_state)
                else:
                    player.skill_flash['teleport'] = 0.35
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and getattr(player, 'targeting_skill', None):
                game._update_skill_target(player, game_state)
                if player.targeting_skill == 'blast':
                    if player.skill_target_valid and game._cast_fixed_point_blast(player, game_state, enemies, player.skill_target_pos):
                        player.blast_cd = float(game.BLAST_COOLDOWN)
                        player.targeting_skill = None
                    else:
                        player.skill_flash['blast'] = 0.35
                elif player.targeting_skill == 'teleport':
                    if player.skill_target_valid and game._teleport_player_to(player, game_state, player.skill_target_pos):
                        player.teleport_cd = float(game.TELEPORT_COOLDOWN)
                        player.targeting_skill = None
                        player.skill_target_origin = None
                    else:
                        player.skill_flash['teleport'] = 0.35
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and getattr(player, 'targeting_skill', None):
                player.targeting_skill = None
            if is_escape_event(event) and getattr(player, 'targeting_skill', None):
                player.targeting_skill = None
        _profile_mark(profiler, "update")
        if getattr(player, 'targeting_skill', None):
            game._update_skill_target(player, game_state)
        keys = pygame.key.get_pressed()
        player.slow_t = max(0.0, getattr(player, 'slow_t', 0.0) - dt)
        game_state.update_telegraphs(dt)
        game_state.update_acids(dt, player)
        if _web_feature_enabled(game, 'WEB_ENABLE_ENEMY_PAINT'):
            game_state.update_enemy_paint(dt, player)
        if _web_feature_enabled(game, 'WEB_ENABLE_VULNERABILITY_MARKS'):
            game_state.update_vulnerability_marks(enemies, dt)
        if _web_feature_enabled(game, 'WEB_ENABLE_HURRICANES'):
            game_state.update_hurricanes(dt, player, enemies, bullets, enemy_shots)
        player.move(keys, game_state.obstacles, dt)
        game_state.fx.update(dt)
        game_state.update_comet_blasts(dt, player, enemies)
        game_state.update_camera_shake(dt)
        ptile = (int(player.rect.centerx // game.CELL_SIZE), int((player.rect.centery - game.INFO_BAR_HEIGHT) // game.CELL_SIZE))
        _profile_mark(profiler, "flow")
        game_state.refresh_flow_field(ptile, dt)
        game_state.collect_item(player.rect)
        game_state.update_spoils(dt, player)
        for z in enemies:
            got = game_state.collect_spoils_for_enemy(z)
            if got > 0:
                z.add_spoils(got)
            z._gold_glow_t = max(0.0, getattr(z, '_gold_glow_t', 0.0) - dt)
        game_state.collect_spoils(player.rect)
        game_state.update_heals(dt)
        if _web_feature_enabled(game, 'WEB_ENABLE_DAMAGE_TEXTS'):
            game_state.update_damage_texts(dt)
        if _web_feature_enabled(game, 'WEB_ENABLE_AEGIS_PULSES'):
            game_state.update_aegis_pulses(dt, player, enemies)
        game_state.collect_heals(player)
        player.update_bone_plating(dt)
        player.blast_cd = max(0.0, getattr(player, 'blast_cd', 0.0) - dt)
        player.teleport_cd = max(0.0, getattr(player, 'teleport_cd', 0.0) - dt)
        player.skill_flash['blast'] = max(0.0, float(player.skill_flash.get('blast', 0.0)) - dt)
        player.skill_flash['teleport'] = max(0.0, float(player.skill_flash.get('teleport', 0.0)) - dt)
        if player.acid_dot_timer > 0.0:
            player.acid_dot_timer = max(0.0, player.acid_dot_timer - dt)
            player._acid_dot_accum += player.acid_dot_dps * dt
            whole = int(player._acid_dot_accum)
            if whole > 0:
                game_state.damage_player(player, whole)
                player._acid_dot_accum -= whole
            if player.acid_dot_timer <= 0.0:
                player.acid_dot_dps = 0.0
        player.update_bone_plating(dt)
        game.tick_aegis_pulse(player, game_state, enemies, dt)
        while getattr(player, 'levelup_pending', 0) > 0:
            bg = last_frame or game.render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots, obstacles)
            time_left = game.levelup_modal(screen, bg, clock, time_left, player)
            player.levelup_pending -= 1
            last_frame = game.render_game_iso(
                screen,
                game_state,
                player,
                enemies,
                bullets,
                enemy_shots,
                obstacles,
                copy_frame=False,
            )
        player.fire_cd = getattr(player, 'fire_cd', 0.0) - dt
        _profile_mark(profiler, "bullets")
        target, dist = find_target()
        if target and player.fire_cd <= 0 and (dist is None or dist <= player.range):
            _, gp, ob_or_z, cx, cy = target
            px, py = player_center()
            dx, dy = (cx - px, cy - py)
            L = (dx * dx + dy * dy) ** 0.5 or 1.0
            vx, vy = (dx / L * game.BULLET_SPEED, dy / L * game.BULLET_SPEED)
            b = game.Bullet(px, py, vx, vy, player.range, damage=player.bullet_damage)
            b.pierce_left = int(getattr(player, 'bullet_pierce', 0))
            b.ricochet_left = int(getattr(player, 'bullet_ricochet', 0))
            _append_verified_bullet(game, bullets, b, player)
            player.fire_cd += player.fire_cooldown()
        for t in getattr(game_state, 'turrets', []):
            t.update(dt, game_state, enemies, bullets)
        if getattr(game_state, 'spatial', None):
            game_state.spatial_query_radius = max(game.CELL_SIZE, int(game.clamp_player_range(getattr(player, 'range', game.PLAYER_RANGE_DEFAULT)) or game.PLAYER_RANGE_DEFAULT))
            if (not game.IS_WEB) or spatial_rebuild_t <= 0.0 or spatial_enemy_count != len(enemies):
                game_state.spatial.rebuild(enemies)
                spatial_rebuild_t = float(getattr(game, "WEB_SPATIAL_REFRESH_INTERVAL", 0.12))
                spatial_enemy_count = len(enemies)
            else:
                spatial_rebuild_t = max(0.0, spatial_rebuild_t - dt)
        for b in list(bullets):
            if hasattr(game, 'verify_bullet_runtime') and (not game.verify_bullet_runtime(b, player)):
                try:
                    bullets.remove(b)
                except ValueError:
                    pass
                continue
            b.update(dt, game_state, enemies, player)
            if (not getattr(b, 'alive', False)) or (hasattr(game, 'verify_bullet_runtime') and (not game.verify_bullet_runtime(b, player))):
                bullets.remove(b)
        player.hit_cd = max(0.0, player.hit_cd - dt)
        _flush_pending_bullets(game, bullets, game_state, player)
        _profile_mark(profiler, "enemy_move")
        obstacle_values = tuple(game_state.obstacles.values())
        for enemy in list(enemies):
            enemy.move_and_attack(player, obstacle_values, game_state, dt=dt)
            if player.hit_cd <= 0.0 and game.circle_touch(enemy, player):
                mult = getattr(game_state, 'biome_enemy_contact_mult', 1.0)
                base_mult = getattr(enemy, 'contact_damage_mult', 1.0)
                paint_mult = getattr(enemy, '_paint_contact_mult', 1.0)
                dmg_mult = base_mult * paint_mult
                dmg = int(round(game.ENEMY_CONTACT_DAMAGE * max(1.0, mult) * max(0.1, dmg_mult)))
                game_state.damage_player(player, dmg)
                player.hit_cd = float(game.PLAYER_HIT_COOLDOWN)
                if player.hp <= 0:
                    game_result = 'fail'
                    running = False
                    break
        _profile_mark(profiler, "enemy_special")
        if _web_feature_enabled(game, 'WEB_ENABLE_GROUND_SPIKES'):
            game_state.update_ground_spikes(dt, player, enemies)
        if _web_feature_enabled(game, 'WEB_ENABLE_CURING_PAINT'):
            game_state.update_curing_paint(dt, player, enemies)
        if _web_feature_enabled(game, 'WEB_ENABLE_DOT_ROUNDS'):
            game_state.update_dot_rounds(enemies, dt)
        for z in list(enemies):
            if hasattr(game, 'verify_enemy_special_runtime'):
                game.verify_enemy_special_runtime(z)
            z.update_special(dt, player, enemies, enemy_shots, game_state)
            if hasattr(game, 'verify_enemy_special_runtime'):
                game.verify_enemy_special_runtime(z)
            if z.hp <= 0 and (not getattr(z, '_death_processed', False)):
                z._death_processed = True
                game.increment_kill_count()
                game._bandit_death_notice(z, game_state)
                if getattr(z, '_comet_death', False) and (not getattr(z, '_comet_fx_done', False)):
                    z._comet_fx_done = True
                    if hasattr(game_state, 'comet_corpses'):
                        body_size = max(int(z.rect.w), int(z.rect.h))
                        game_state.comet_corpses.append(game.CometCorpse(z.rect.centerx, z.rect.centery, getattr(z, 'color', (255, 60, 60)), body_size))
                if getattr(z, 'is_boss', False) and getattr(z, 'twin_id', None) is not None:
                    game.trigger_twin_enrage(z, enemies, game_state)
                total_drop = int(game.SPOILS_PER_KILL) + int(getattr(z, 'spoils', 0))
                if total_drop > 0:
                    game_state.spawn_spoils(z.rect.centerx, z.rect.centery, total_drop)
                if getattr(z, 'is_boss', False):
                    for _ in range(game.BOSS_HEAL_POTIONS):
                        game_state.spawn_heal(z.rect.centerx, z.rect.centery, game.HEAL_POTION_AMOUNT)
                elif random.random() < game.HEAL_DROP_CHANCE_ENEMY:
                    game_state.spawn_heal(z.rect.centerx, z.rect.centery, game.HEAL_POTION_AMOUNT)
                if not getattr(z, '_xp_awarded', False):
                    try:
                        player.add_xp(int(getattr(z, 'spoils', 0)) * int(game.Z_SPOIL_XP_BONUS_PER))
                        setattr(z, '_xp_awarded', True)
                    except Exception:
                        pass
                game.transfer_xp_to_neighbors(z, enemies)
                enemies.remove(z)
        _profile_mark(profiler, "enemy_shots")
        _sanitize_enemy_shots(game, enemy_shots)
        for es in list(enemy_shots):
            es.update(dt, player, game_state)
            if (not getattr(es, 'alive', False)) or (hasattr(game, 'verify_enemy_shot_runtime') and (not game.verify_enemy_shot_runtime(es))):
                enemy_shots.remove(es)
        game.update_hit_flash_timer(player, dt)
        for z in enemies:
            game.update_hit_flash_timer(z, dt)
        if game_state.ghosts:
            game_state.ghosts[:] = [g for g in game_state.ghosts if g.update(dt)]
        boss_now = game._find_current_boss(enemies)
        if boss_now and getattr(boss_now, 'type', '') == 'boss_mist':
            if not getattr(game_state, 'fog_on', False):
                game_state.enable_fog_field()
        elif getattr(game_state, 'fog_on', False):
            game_state.disable_fog_field()
        if player.hp <= 0:
            game_result = 'fail'
            running = False
            if game.USE_ISO:
                last_frame = game.render_game_iso(pygame.display.get_surface(), game_state, player, enemies, bullets, enemy_shots, obstacles=obstacles)
            else:
                last_frame = game.render_game(pygame.display.get_surface(), game_state, player, enemies, bullets, enemy_shots)
            continue
        should_render = (not game.IS_WEB) or render_cooldown <= 0.0 or last_frame is None
        _profile_mark(profiler, "render")
        if should_render:
            if game.USE_ISO:
                last_frame = game.render_game_iso(
                    pygame.display.get_surface(),
                    game_state,
                    player,
                    enemies,
                    bullets,
                    enemy_shots,
                    obstacles,
                    copy_frame=False,
                )
            else:
                last_frame = game.render_game(
                    pygame.display.get_surface(),
                    game_state,
                    player,
                    enemies,
                    bullets,
                    enemy_shots,
                    copy_frame=False,
                )
            render_cooldown = float(getattr(game, "WEB_RENDER_INTERVAL", 0.0) or 0.0)
        if game_result == 'success':
            runtime['_last_spoils'] = getattr(game_state, 'spoils_gained', 0)
            runtime['_carry_player_state'] = game.capture_player_carry(player)
        _web_snapshot_autosave(game, runtime, game_state, player, enemies, game.current_level, chosen_enemy_type, bullets)
        _profile_finish(
            game,
            profiler,
            game_state,
            enemies,
            bullets,
            enemy_shots,
            wave_index=wave_index,
            rendered=should_render,
        )
        if game.IS_WEB:
            await _yield_web_frame(game)
    return (game_result, config.get('reward', None), last_frame or screen.copy())

async def run_from_snapshot(game, save_data: dict) -> Tuple[str, Optional[str], pygame.Surface]:
    runtime = rs.runtime(game)
    """Resume a game from a snapshot in save_data; same return contract as main_run_level."""
    if hasattr(game, '_sanitize_resume_save_data'):
        save_data = game._sanitize_resume_save_data(save_data)
    if not isinstance(save_data, dict) or save_data.get('mode') != 'snapshot':
        raise ValueError('run_from_snapshot requires validated snapshot save data')
    if hasattr(game, '_load_meta_from_save'):
        game._load_meta_from_save(save_data)
    saved_meta = save_data.get('meta', {})
    snap = save_data.get('snapshot', {})
    level_idx = int(saved_meta.get('current_level', game.current_level))
    obstacles: Dict[Tuple[int, int], game.Obstacle] = {}
    stationary_from_save: List[game.StationaryTurret] = []
    for o in snap.get('obstacles', []):
        typ = o.get('type', 'Indestructible')
        x, y = (int(o.get('x', 0)), int(o.get('y', 0)))
        if typ == 'StationaryTurret':
            cx = x * game.CELL_SIZE + game.CELL_SIZE // 2
            cy = y * game.CELL_SIZE + game.CELL_SIZE // 2 + game.INFO_BAR_HEIGHT
            turret = game.StationaryTurret(cx, cy)
            stationary_from_save.append(turret)
            ob = game.StationaryTurretObstacle(turret.rect)
        elif o.get('main', False):
            ob = game.MainBlock(x, y, health=o.get('health', game.MAIN_BLOCK_HEALTH))
        else:
            ob = game.Obstacle(x, y, typ, health=o.get('health', None))
        obstacles[x, y] = ob
    items = [game.Item(int(it.get('x', 0)), int(it.get('y', 0)), bool(it.get('is_main', False))) for it in snap.get('items', [])]
    decorations = [tuple(d) for d in snap.get('decorations', [])]
    game_state = game.GameState(obstacles, items, [(i.x, i.y) for i in items if getattr(i, 'is_main', False)], decorations)
    game_state.current_level = level_idx
    p = snap.get('player', {})
    player = game.Player((0, 0), speed=int(p.get('speed', game.PLAYER_SPEED)))
    player.x = float(p.get('x', 0.0))
    player.y = float(p.get('y', 0.0))
    player.rect.x = int(player.x)
    player.rect.y = int(player.y) + game.INFO_BAR_HEIGHT
    player.fire_cd = float(p.get('fire_cd', 0.0))
    player.max_hp = int(p.get('max_hp', game.PLAYER_MAX_HP))
    player.hp = int(p.get('hp', game.PLAYER_MAX_HP))
    player.hit_cd = float(p.get('hit_cd', 0.0))
    player.level = int(p.get('level', 1))
    player.xp = int(p.get('xp', 0))
    player.xp_to_next = game.player_xp_required(player.level)
    player.bone_plating_hp = int(p.get('bone_plating_hp', 0))
    player._bone_plating_cd = float(p.get('bone_plating_cd', game.BONE_PLATING_GAIN_INTERVAL))
    player._bone_plating_glow = 0.0
    player.aegis_pulse_level = int(saved_meta.get('aegis_pulse_level', 0))
    if player.aegis_pulse_level > 0:
        _, _, cd = game.aegis_pulse_stats(player.aegis_pulse_level, player.max_hp)
        player._aegis_pulse_cd = float(p.get('aegis_pulse_cd', cd))
    else:
        player._aegis_pulse_cd = 0.0
    if not hasattr(player, 'fire_cd'):
        player.fire_cd = 0.0
    player._hit_flash = 0.0
    player._flash_prev_hp = int(player.hp)
    turret_level = int(saved_meta.get('auto_turret_level', 0))
    turrets: List[game.AutoTurret | game.StationaryTurret] = []
    if turret_level > 0:
        for i in range(turret_level):
            angle = 2.0 * math.pi * i / max(1, turret_level)
            off_x = math.cos(angle) * game.AUTO_TURRET_OFFSET_RADIUS
            off_y = math.sin(angle) * game.AUTO_TURRET_OFFSET_RADIUS
            turrets.append(game.AutoTurret(player, (off_x, off_y)))
    turrets.extend(stationary_from_save)
    stationary_count = int(saved_meta.get('stationary_turret_count', 0))
    added_stationary = False
    remaining = max(0, stationary_count - len(stationary_from_save))
    if remaining > 0:
        for _ in range(remaining):
            for _attempt in range(40):
                gx = random.randrange(game.GRID_SIZE)
                gy = random.randrange(game.GRID_SIZE)
                if (gx, gy) in game_state.obstacles:
                    continue
                wx = gx * game.CELL_SIZE + game.CELL_SIZE // 2
                wy = gy * game.CELL_SIZE + game.CELL_SIZE // 2 + game.INFO_BAR_HEIGHT
                turret = game.StationaryTurret(wx, wy)
                turrets.append(turret)
                game_state.obstacles[gx, gy] = game.StationaryTurretObstacle(turret.rect)
                added_stationary = True
                break
    if (added_stationary or stationary_from_save) and hasattr(game_state, 'mark_nav_dirty'):
        game_state.mark_nav_dirty()
    game_state.turrets = turrets
    enemies: List[game.Enemy] = []
    for z in snap.get('enemies', []):
        zobj = game.Enemy((0, 0), attack=int(z.get('attack', game.ENEMY_ATTACK)), speed=int(z.get('speed', game.ENEMY_SPEED)), ztype=z.get('type', 'basic'), hp=int(z.get('hp', 30)))
        zobj.max_hp = int(z.get('max_hp', int(z.get('hp', 30))))
        zobj.x = float(z.get('x', 0.0))
        zobj.y = float(z.get('y', 0.0))
        zobj.rect.x = int(zobj.x)
        zobj.rect.y = int(zobj.y) + game.INFO_BAR_HEIGHT
        zobj._spawn_elapsed = float(z.get('spawn_elapsed', 0.0))
        zobj.attack_timer = float(z.get('attack_timer', 0.0))
        zobj.speed = min(game.ENEMY_SPEED_MAX, max(1, int(zobj.speed)))
        zobj._hit_flash = 0.0
        zobj._flash_prev_hp = int(zobj.hp)
        enemies.append(zobj)
    bullets: List[game.Bullet] = []
    for b in snap.get('bullets', []):
        bobj = game.Bullet(float(b.get('x', 0.0)), float(b.get('y', 0.0)), float(b.get('vx', 0.0)), float(b.get('vy', 0.0)), game.clamp_player_range(getattr(player, 'range', game.PLAYER_RANGE_DEFAULT)))
        bobj.traveled = float(b.get('traveled', 0.0))
        bobj.pierce_left = int(getattr(player, 'bullet_pierce', 0))
        bobj.ricochet_left = int(getattr(player, 'bullet_ricochet', 0))
        _append_verified_bullet(game, bullets, bobj, player)
    enemy_shots: List[game.EnemyShot] = []
    time_left = min(float(snap.get('time_left', _effective_level_time_limit(game, level_idx))), _effective_level_time_limit(game, level_idx))
    runtime['_time_left_runtime'] = time_left
    screen = pygame.display.get_surface()
    clock = pygame.time.Clock()
    if game.IS_WEB and runtime.get("_menu_transition_frame") is not None:
        await asyncio.sleep(0)
    await _preload_web_gameplay_assets(game, screen, runtime)
    running = True
    last_frame = None
    chosen_enemy_type = saved_meta.get('chosen_enemy_type', 'basic')
    enemy_cap = game.WEB_ENEMY_CAP if game.IS_WEB else game.ENEMY_CAP
    combat_bgm_started = _combat_bgm_selected(game)
    if game.IS_WEB and bool(getattr(game, "WEB_SINGLE_BGM", False)):
        combat_bgm_started = True
    if not game.IS_WEB:
        game.play_combat_bgm()
        combat_bgm_started = True
    spawn_timer = 0.0
    wave_index = 0
    combat_bgm_delay = 0.75 if game.IS_WEB else 0.0

    def player_center():
        return (player.x + player.size / 2, player.y + player.size / 2 + game.INFO_BAR_HEIGHT)

    def find_target():
        px, py = (player.rect.centerx, player.rect.centery)
        pgx = int(px // game.CELL_SIZE)
        pgy = int((py - game.INFO_BAR_HEIGHT) // game.CELL_SIZE)
        force_blocks = []
        for gp, ob in game_state.obstacles.items():
            if getattr(ob, 'type', '') != 'Destructible':
                continue
            gx, gy = gp
            manh = abs(gx - pgx) + abs(gy - pgy)
            if manh <= int(game.PLAYER_BLOCK_FORCE_RANGE_TILES):
                cx, cy = (ob.rect.centerx, ob.rect.centery)
                d2 = (cx - px) ** 2 + (cy - py) ** 2
                force_blocks.append((d2, ('block', gp, ob, cx, cy)))
        if force_blocks:
            force_blocks.sort(key=lambda t: t[0])
            best_tuple = force_blocks[0][1]
            d = force_blocks[0][0] ** 0.5
            return (best_tuple, d)
        cur_range = game.clamp_player_range(getattr(player, 'range', game.PLAYER_RANGE_DEFAULT))
        R2 = cur_range ** 2
        z_cands = []
        for z in enemies:
            cx, cy = (z.rect.centerx, z.rect.centery)
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 <= R2:
                z_cands.append((z, cx, cy, d2))
        b_cands = []
        for gp, ob in game_state.obstacles.items():
            if getattr(ob, 'type', '') != 'Destructible':
                continue
            cx, cy = (ob.rect.centerx, ob.rect.centery)
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 <= R2:
                b_cands.append((gp, ob, cx, cy, d2))
        if not z_cands and (not b_cands):
            return (None, None)
        DIST_K = 0.0001
        W_ENEMY = 1200.0
        W_BLOCK = 800.0
        best = None
        best_score = -1e+18
        for z, cx, cy, d2 in z_cands:
            s = -d2 * DIST_K + W_ENEMY
            if s > best_score:
                best_score = s
                best = ('enemy', None, z, cx, cy, d2)
        for gp, ob, cx, cy, d2 in b_cands:
            s = -d2 * DIST_K + W_BLOCK
            if s > best_score:
                best_score = s
                best = ('block', gp, ob, cx, cy, d2)
        if best is None:
            return (None, None)
        kind, gp_or_none, obj, cx, cy, d2 = best
        return ((kind, gp_or_none, obj, cx, cy), d2 ** 0.5)
    player._hit_flash = 0.0
    player._flash_prev_hp = int(player.hp)
    for z in enemies:
        z._hit_flash = 0.0
        z._flash_prev_hp = int(getattr(z, 'hp', 0))
    _web_snapshot_autosave(game, runtime, game_state, player, enemies, level_idx, chosen_enemy_type, bullets, force=True)
    render_cooldown = 0.0
    web_transition_guard_t = 0.65 if game.IS_WEB else 0.0
    profiler = _web_profiler(game)
    while running:
        dt = _frame_dt(game, clock)
        if game.IS_WEB and dt <= 0.0:
            screen = _pump_web_idle_events(
                game,
                screen,
                on_focus_lost=lambda: _web_snapshot_autosave(
                    game, runtime, game_state, player, enemies, level_idx, chosen_enemy_type, bullets, force=True
                ),
            )
            await _yield_web_frame(game)
            continue
        profiler = _profile_begin(game, dt)
        render_cooldown = max(0.0, render_cooldown - dt)
        if web_transition_guard_t > 0.0:
            web_transition_guard_t = max(0.0, web_transition_guard_t - dt)
            if web_transition_guard_t <= 0.0 and (
                runtime.get("_web_hex_transition_state") is not None
                or runtime.get("_menu_transition_frame") is not None
            ):
                game.clear_menu_transition_state()
        if game.IS_WEB and (not combat_bgm_started):
            combat_bgm_delay = max(0.0, combat_bgm_delay - dt)
            if combat_bgm_delay <= 0.0:
                game.play_combat_bgm()
                combat_bgm_started = True
        time_left -= dt
        runtime['_time_left_runtime'] = time_left
        if time_left <= 0:
            chosen = await game.show_success_screen(screen, last_frame or game.render_game(screen, game_state, player, enemies, bullets, enemy_shots), reward_choices=[])
            return ('success', None, last_frame or screen.copy())
        _profile_mark(profiler, "events")
        for event in pygame.event.get():
            screen = game._handle_web_window_event(event) or screen
            game._sync_web_input_event(event)
            _resume_web_audio_on_event(game, event)
            if getattr(event, "type", None) in {
                getattr(pygame, "WINDOWFOCUSLOST", None),
            }:
                _web_snapshot_autosave(game, runtime, game_state, player, enemies, level_idx, chosen_enemy_type, bullets, force=True)
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.is_action_event(event, 'blast') and getattr(player, 'targeting_skill', None) == 'blast':
                player.targeting_skill = None
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_t:
                game.activate_ultimate_mode(player, game_state)
            if game.is_action_event(event, 'teleport') and getattr(player, 'targeting_skill', None) == 'teleport':
                player.targeting_skill = None
                continue
            if is_escape_event(event) and getattr(player, 'targeting_skill', None):
                player.targeting_skill = None
                continue
            if is_escape_event(event):
                bg = last_frame or game.render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots, obstacles=game_state.obstacles)
                choice, time_left = game.pause_game_modal(screen, bg, clock, time_left, player)
                if choice == 'continue':
                    pass
                elif choice == 'restart':
                    game.queue_menu_transition(pygame.display.get_surface().copy())
                    return ('restart', None, bg)
                elif choice == 'home':
                    game.queue_menu_transition(pygame.display.get_surface().copy())
                    runtime['_carry_player_state'] = game.capture_player_carry(player)
                    game.save_progress(level_idx, max_wave_reached=runtime.get('_max_wave_reached', None))
                    runtime['_skip_intro_once'] = True
                    return ('home', None, bg)
                elif choice == 'exit':
                    runtime['_carry_player_state'] = game.capture_player_carry(player)
                    game.save_progress(level_idx, max_wave_reached=runtime.get('_max_wave_reached', None))
                    return ('exit', None, bg)
            if game.is_action_event(event, 'blast'):
                if getattr(player, 'blast_cd', 0.0) <= 0.0:
                    player.targeting_skill = 'blast'
                    game._update_skill_target(player, game_state)
                else:
                    player.skill_flash['blast'] = 0.35
            if game.is_action_event(event, 'teleport'):
                if getattr(player, 'teleport_cd', 0.0) <= 0.0:
                    player.targeting_skill = 'teleport'
                    game._update_skill_target(player, game_state)
                else:
                    player.skill_flash['teleport'] = 0.35
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and getattr(player, 'targeting_skill', None):
                game._update_skill_target(player, game_state)
                if player.targeting_skill == 'blast':
                    if player.skill_target_valid and game._cast_fixed_point_blast(player, game_state, enemies, player.skill_target_pos):
                        player.blast_cd = float(game.BLAST_COOLDOWN)
                        player.targeting_skill = None
                    else:
                        player.skill_flash['blast'] = 0.35
                elif player.targeting_skill == 'teleport':
                    if player.skill_target_valid and game._teleport_player_to(player, game_state, player.skill_target_pos):
                        player.teleport_cd = float(game.TELEPORT_COOLDOWN)
                        player.targeting_skill = None
                    else:
                        player.skill_flash['teleport'] = 0.35
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and getattr(player, 'targeting_skill', None):
                player.targeting_skill = None
            if is_escape_event(event) and getattr(player, 'targeting_skill', None):
                player.targeting_skill = None
        _profile_mark(profiler, "update")
        if getattr(player, 'targeting_skill', None):
            game._update_skill_target(player, game_state)
        keys = pygame.key.get_pressed()
        player.slow_t = max(0.0, getattr(player, 'slow_t', 0.0) - dt)
        game_state.update_telegraphs(dt)
        game_state.update_acids(dt, player)
        if _web_feature_enabled(game, 'WEB_ENABLE_ENEMY_PAINT'):
            game_state.update_enemy_paint(dt, player)
        if _web_feature_enabled(game, 'WEB_ENABLE_VULNERABILITY_MARKS'):
            game_state.update_vulnerability_marks(enemies, dt)
        player.move(keys, game_state.obstacles, dt)
        game_state.fx.update(dt)
        game_state.update_comet_blasts(dt, player, enemies)
        game_state.update_camera_shake(dt)
        game_state.collect_item(player.rect)
        game_state.update_spoils(dt, player)
        game_state.collect_spoils(player.rect)
        game_state.update_heals(dt)
        if _web_feature_enabled(game, 'WEB_ENABLE_DAMAGE_TEXTS'):
            game_state.update_damage_texts(dt)
        if _web_feature_enabled(game, 'WEB_ENABLE_AEGIS_PULSES'):
            game_state.update_aegis_pulses(dt, player, enemies)
        game_state.collect_heals(player)
        game.tick_aegis_pulse(player, game_state, enemies, dt)
        player.blast_cd = max(0.0, getattr(player, 'blast_cd', 0.0) - dt)
        player.teleport_cd = max(0.0, getattr(player, 'teleport_cd', 0.0) - dt)
        player.skill_flash['blast'] = max(0.0, float(player.skill_flash.get('blast', 0.0)) - dt)
        player.skill_flash['teleport'] = max(0.0, float(player.skill_flash.get('teleport', 0.0)) - dt)
        player.fire_cd = getattr(player, 'fire_cd', 0.0) - dt
        _profile_mark(profiler, "bullets")
        target, dist = find_target()
        if target and player.fire_cd <= 0 and (dist is None or dist <= player.range):
            _, gp, ob_or_z, cx, cy = target
            px, py = player_center()
            dx, dy = (cx - px, cy - py)
            L = (dx * dx + dy * dy) ** 2 ** 0.5 if False else (dx * dx + dy * dy) ** 0.5
            L = L or 1.0
            vx, vy = (dx / L * game.BULLET_SPEED, dy / L * game.BULLET_SPEED)
            b = game.Bullet(px, py, vx, vy, player.range, damage=player.bullet_damage)
            b.pierce_left = int(getattr(player, 'bullet_pierce', 0))
            b.ricochet_left = int(getattr(player, 'bullet_ricochet', 0))
            _append_verified_bullet(game, bullets, b, player)
            player.fire_cd += player.fire_cooldown()
        for t in getattr(game_state, 'turrets', []):
            t.update(dt, game_state, enemies, bullets)
        for b in list(bullets):
            if hasattr(game, 'verify_bullet_runtime') and (not game.verify_bullet_runtime(b, player)):
                try:
                    bullets.remove(b)
                except ValueError:
                    pass
                continue
            b.update(dt, game_state, enemies, player)
            if (not getattr(b, 'alive', False)) or (hasattr(game, 'verify_bullet_runtime') and (not game.verify_bullet_runtime(b, player))):
                bullets.remove(b)
        _flush_pending_bullets(game, bullets, game_state, player)
        _profile_mark(profiler, "spawn")
        spawn_timer += dt
        if spawn_timer >= game.SPAWN_INTERVAL:
            spawn_timer = 0.0
            if len(enemies) < enemy_cap:
                spawned = game.spawn_wave_with_budget(game_state, player, level_idx, wave_index, enemies, enemy_cap)
                if spawned > 0:
                    wave_index += 1
                    runtime['_max_wave_reached'] = max(runtime.get('_max_wave_reached', 0), wave_index)
        player.hit_cd = max(0.0, player.hit_cd - dt)
        pgx = int(player.rect.centerx // game.CELL_SIZE)
        pgy = int((player.rect.centery - game.INFO_BAR_HEIGHT) // game.CELL_SIZE)
        _profile_mark(profiler, "flow")
        game_state.refresh_flow_field((pgx, pgy), dt)
        obstacle_values = tuple(game_state.obstacles.values())
        _profile_mark(profiler, "enemy_move")
        for enemy in list(enemies):
            enemy.move_and_attack(player, obstacle_values, game_state, dt=dt)
            if player.hit_cd <= 0.0 and game.circle_touch(enemy, player):
                mult = getattr(game_state, 'biome_enemy_contact_mult', 1.0)
                base_mult = getattr(enemy, 'contact_damage_mult', 1.0)
                paint_mult = getattr(enemy, '_paint_contact_mult', 1.0)
                dmg_mult = base_mult * paint_mult
                dmg = int(round(game.ENEMY_CONTACT_DAMAGE * max(1.0, mult) * max(0.1, dmg_mult)))
                game_state.damage_player(player, dmg)
                player.hit_cd = float(game.PLAYER_HIT_COOLDOWN)
                if player.hp <= 0:
                    game.clear_save()
                    bg = game.render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots, obstacles=game_state.obstacles)
                    last_frame = bg.copy()
                    action = await game.show_fail_screen(screen, bg)
                    if action == 'home':
                        game.clear_save()
                        game.flush_events()
                        return ('home', None, last_frame or screen.copy())
                    elif action == 'retry':
                        game.clear_save()
                        game.flush_events()
                        return ('restart', None, last_frame or screen.copy())
        _profile_mark(profiler, "enemy_special")
        if _web_feature_enabled(game, 'WEB_ENABLE_GROUND_SPIKES'):
            game_state.update_ground_spikes(dt, player, enemies)
        if _web_feature_enabled(game, 'WEB_ENABLE_CURING_PAINT'):
            game_state.update_curing_paint(dt, player, enemies)
        if _web_feature_enabled(game, 'WEB_ENABLE_DOT_ROUNDS'):
            game_state.update_dot_rounds(enemies, dt)
        for z in list(enemies):
            if hasattr(game, 'verify_enemy_special_runtime'):
                game.verify_enemy_special_runtime(z)
            z.update_special(dt, player, enemies, enemy_shots, game_state)
            if hasattr(game, 'verify_enemy_special_runtime'):
                game.verify_enemy_special_runtime(z)
            if z.hp <= 0 and (not getattr(z, '_death_processed', False)):
                z._death_processed = True
                game.increment_kill_count()
                game._bandit_death_notice(z, game_state)
                if getattr(z, '_comet_death', False) and (not getattr(z, '_comet_fx_done', False)):
                    z._comet_fx_done = True
                    if hasattr(game_state, 'comet_corpses'):
                        body_size = max(int(z.rect.w), int(z.rect.h))
                        game_state.comet_corpses.append(game.CometCorpse(z.rect.centerx, z.rect.centery, getattr(z, 'color', (255, 60, 60)), body_size))
                total_drop = int(game.SPOILS_PER_KILL) + int(getattr(z, 'spoils', 0))
                if total_drop > 0:
                    game_state.spawn_spoils(z.rect.centerx, z.rect.centery, total_drop)
                if getattr(z, 'is_boss', False):
                    for _ in range(game.BOSS_HEAL_POTIONS):
                        game_state.spawn_heal(z.rect.centerx, z.rect.centery, game.HEAL_POTION_AMOUNT)
                elif random.random() < game.HEAL_DROP_CHANCE_ENEMY:
                    game_state.spawn_heal(z.rect.centerx, z.rect.centery, game.HEAL_POTION_AMOUNT)
                try:
                    player.add_xp(int(getattr(z, 'spoils', 0)) * int(game.Z_SPOIL_XP_BONUS_PER))
                except Exception:
                    pass
                game.transfer_xp_to_neighbors(z, enemies)
                enemies.remove(z)
        _profile_mark(profiler, "enemy_shots")
        _sanitize_enemy_shots(game, enemy_shots)
        for es in list(enemy_shots):
            es.update(dt, player, game_state)
            if (not getattr(es, 'alive', False)) or (hasattr(game, 'verify_enemy_shot_runtime') and (not game.verify_enemy_shot_runtime(es))):
                enemy_shots.remove(es)
        game.update_hit_flash_timer(player, dt)
        for z in enemies:
            game.update_hit_flash_timer(z, dt)
        if player.hp <= 0:
            game.clear_save()
            action = await game.show_fail_screen(screen, last_frame or game.render_game(screen, game_state, player, enemies, bullets, enemy_shots))
            if action == 'home':
                game.clear_save()
                game.flush_events()
                return ('home', None, last_frame or screen.copy())
            elif action == 'retry':
                game.clear_save()
                game.flush_events()
                return ('restart', None, last_frame or screen.copy())
        should_render = (not game.IS_WEB) or render_cooldown <= 0.0 or last_frame is None
        _profile_mark(profiler, "render")
        if should_render:
            if game.USE_ISO:
                last_frame = game.render_game_iso(
                    pygame.display.get_surface(),
                    game_state,
                    player,
                    enemies,
                    bullets,
                    enemy_shots,
                    obstacles=game_state.obstacles,
                    copy_frame=False,
                )
            else:
                last_frame = game.render_game(
                    pygame.display.get_surface(),
                    game_state,
                    player,
                    enemies,
                    bullets,
                    enemy_shots,
                    copy_frame=False,
                )
            render_cooldown = float(getattr(game, "WEB_RENDER_INTERVAL", 0.0) or 0.0)
        _web_snapshot_autosave(game, runtime, game_state, player, enemies, level_idx, chosen_enemy_type, bullets)
        _profile_finish(
            game,
            profiler,
            game_state,
            enemies,
            bullets,
            enemy_shots,
            wave_index=wave_index,
            rendered=should_render,
        )
        if game.IS_WEB:
            await _yield_web_frame(game)
    return ('home', None, last_frame or screen.copy())

async def app_main(game) -> None:
    runtime = rs.runtime(game)
    meta = rs.meta(game)
    if getattr(game, "IS_WEB", False):
        try:
            _set_browser_profiler_phase("startup:init")
        except Exception:
            pass
    os.environ['SDL_VIDEO_CENTERED'] = '0'
    os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
    pygame.init()
    info = pygame.display.Info()
    if game.IS_WEB:
        web_w, web_h = game.get_initial_web_window_size()
        screen = pygame.display.set_mode((web_w, web_h), pygame.RESIZABLE)
        game.VIEW_W, game.VIEW_H = screen.get_size()
    else:
        screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.NOFRAME)
        game.VIEW_W, game.VIEW_H = (info.current_w, info.current_h)
    pygame.display.set_caption(game.GAME_TITLE)
    game.resize_world_to_view()
    if getattr(game, "IS_WEB", False):
        try:
            _set_browser_profiler_phase("startup:bgm")
        except Exception:
            pass
    try:
        game.play_intro_bgm()
    except Exception as e:
        print(f'[Audio] background music not started: {e}')
    if not game.IS_WEB:
        screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.NOFRAME)
        pygame.display.set_caption(game.GAME_TITLE)
        game.VIEW_W, game.VIEW_H = (info.current_w, info.current_h)
    game.resize_world_to_view()
    game.flush_events()
    if getattr(game, "IS_WEB", False):
        try:
            _set_browser_profiler_phase("startup:menu")
        except Exception:
            pass

    def apply_menu_selection(selection_data):
        if not selection_data:
            sys.exit()
        mode_in, save_in = selection_data
        if mode_in == 'continue' and save_in:
            return game._apply_resume_save_data(save_in)
        game._reset_active_run_state(clear_save_file=True)
        return None

    if getattr(game, "IS_WEB", False) and bool(getattr(game, "WEB_AUTOSTART", False)):
        game._reset_active_run_state(clear_save_file=True)
    else:
        selection = await game.show_start_menu(screen, skip_intro=bool(getattr(game, 'WEB_DEMO_SKIP_INTRO', False)))
        apply_menu_selection(selection)
    START_IN_SHOP_FOR_TEST = False
    if START_IN_SHOP_FOR_TEST:
        runtime['_pending_shop'] = True
    while True:
        if _demo_level_limit(game) and int(game.current_level) >= _demo_level_limit(game):
            game._reset_active_run_state(clear_save_file=True)
            selection = await game.show_start_menu(screen, skip_intro=True)
            apply_menu_selection(selection)
            continue
        if runtime.get('_pending_shop', False):
            meta['spoils'] += int(runtime.pop('_last_spoils', 0))
            runtime['_coins_at_shop_entry'] = int(meta.get('spoils', 0))
            game.save_progress(game.current_level, pending_shop=True)
            action = game.show_shop_screen(screen)
            runtime['_pending_shop'] = False
            if action in (None,):
                runtime['_pending_shop'] = False
                game.current_level += 1
                runtime.pop('_coins_at_level_start', None)
                runtime.pop('_coins_at_shop_entry', None)
                game.save_progress(game.current_level)
            elif action == 'home':
                game.save_progress(game.current_level, pending_shop=True)
                game.flush_events()
                selection = await game.show_start_menu(screen, skip_intro=True)
                apply_menu_selection(selection)
                continue
            elif action == 'restart':
                meta['spoils'] = int(runtime.get('_coins_at_level_start', meta.get('spoils', 0)))
                runtime.pop('_last_spoils', None)
                game.flush_events()
                continue
            elif action == 'exit':
                game.save_progress(game.current_level, pending_shop=True)
                pygame.quit()
                sys.exit()
        resume_snapshot = runtime.pop('_resume_snapshot_data', None)
        if resume_snapshot:
            if runtime.get('_menu_transition_frame') is None:
                game.flush_events()
            result, reward, bg = await game.run_from_snapshot(resume_snapshot)
        else:
            config = game.get_level_config(game.current_level)
            chosen_enemy = 'basic'
            if '_coins_at_level_start' not in runtime:
                runtime['_coins_at_level_start'] = int(meta.get('spoils', 0))
            if runtime.get('_menu_transition_frame') is None:
                game.flush_events()
            result, reward, bg = await game.main_run_level(config, chosen_enemy)
        if result == 'restart':
            meta['spoils'] = int(runtime.get('_coins_at_level_start', meta.get('spoils', 0)))
            meta['run_items_spawned'] = int(runtime.get('_run_items_spawned_start', meta.get('run_items_spawned', 0)))
            meta['run_items_collected'] = int(runtime.get('_run_items_collected_start', meta.get('run_items_collected', 0)))
            cb = runtime.get('_consumable_baseline', {})
            if isinstance(cb, dict):
                meta['carapace_shield_hp'] = int(cb.get('carapace_shield_hp', meta.get('carapace_shield_hp', 0)))
                meta['wanted_poster_waves'] = int(cb.get('wanted_poster_waves', meta.get('wanted_poster_waves', 0)))
                meta['wanted_active'] = bool(cb.get('wanted_active', False))
            runtime.pop('_items_counted_level', None)
            runtime.pop('_last_spoils', None)
            game.flush_events()
            continue
        if result == 'home':
            game.flush_events()
            selection = await game.show_start_menu(screen, skip_intro=True)
            apply_menu_selection(selection)
            continue
        if result == 'exit':
            pygame.quit()
            sys.exit()
        if result == 'fail':
            game.clear_save()
            action = await game.show_fail_screen(screen, bg)
            game.flush_events()
            if action == 'home':
                selection = await game.show_start_menu(screen, skip_intro=True)
                apply_menu_selection(selection)
                continue
            else:
                cb = runtime.get('_consumable_baseline', {})
                if isinstance(cb, dict):
                    meta['carapace_shield_hp'] = int(cb.get('carapace_shield_hp', meta.get('carapace_shield_hp', 0)))
                    meta['wanted_poster_waves'] = int(cb.get('wanted_poster_waves', meta.get('wanted_poster_waves', 0)))
                    meta['wanted_active'] = bool(cb.get('wanted_active', False))
                continue
        elif result == 'success':
            meta['spoils'] += int(runtime.get('_last_spoils', 0))
            runtime['_last_spoils'] = 0
            action = await game.show_success_screen(screen, bg, [])
            if action == 'home':
                game.save_progress(game.current_level, pending_shop=True)
                game.flush_events()
                selection = await game.show_start_menu(screen, skip_intro=True)
                apply_menu_selection(selection)
                continue
            if action in ('restart', 'retry'):
                meta['spoils'] = int(runtime.get('_coins_at_level_start', meta.get('spoils', 0)))
                runtime.pop('_last_spoils', None)
                game.flush_events()
                continue
            if _demo_complete_for_level(game, game.current_level):
                game._reset_active_run_state(clear_save_file=True)
                game.flush_events()
                selection = await game.show_start_menu(screen, skip_intro=True)
                apply_menu_selection(selection)
                continue
            runtime['_coins_at_shop_entry'] = int(meta.get('spoils', 0))
            game.save_progress(game.current_level, pending_shop=True)
            action = game.show_shop_screen(screen)
            if action == 'home':
                game.save_progress(game.current_level, pending_shop=True)
                game.flush_events()
                selection = await game.show_start_menu(screen, skip_intro=True)
                apply_menu_selection(selection)
                continue
            elif action in ('restart', 'retry'):
                meta['spoils'] = int(runtime.get('_coins_at_shop_entry', meta.get('spoils', 0)))
                meta['run_items_spawned'] = int(runtime.get('_run_items_spawned_start', meta.get('run_items_spawned', 0)))
                meta['run_items_collected'] = int(runtime.get('_run_items_collected_start', meta.get('run_items_collected', 0)))
                runtime.pop('_items_counted_level', None)
                runtime.pop('_last_spoils', None)
                continue
            elif action == 'exit':
                game.save_progress(game.current_level, pending_shop=True)
                pygame.quit()
                sys.exit()
            else:
                game.current_level += 1
                runtime.pop('_coins_at_level_start', None)
                runtime.pop('_coins_at_shop_entry', None)
                game.save_progress(game.current_level)
        else:
            selection = await game.show_start_menu(screen, skip_intro=True)
            apply_menu_selection(selection)

