"""Top-level render/HUD runtime helpers extracted from ZGame.py."""

from __future__ import annotations

import math
import sys
from typing import List, Optional

import pygame

from zgame import runtime_state as rs


def install(game):
    # Mirror the live game module namespace so this extracted layer can keep
    # using the existing helper/constant names without rewriting every draw path.
    for key, value in game.__dict__.items():
        if not str(key).startswith("__"):
            globals()[key] = value

    def _runtime():
        return rs.runtime(game)

    def _web_feature_enabled(flag_name: str) -> bool:
        if not getattr(game, "IS_WEB", False):
            return True
        return bool(getattr(game, flag_name, False))

    def draw_settings_gear(screen, x, y):
        """Draw a simple gear icon at (x,y) top-left; returns its rect."""
        rect = pygame.Rect(x, y, 32, 24)
        pygame.draw.rect(screen, (50, 50, 50), rect, 2)
        cx, cy = x + 16, y + 12
        pygame.draw.circle(screen, (200, 200, 200), (cx, cy), 8, 2)
        pygame.draw.circle(screen, (200, 200, 200), (cx, cy), 3)
        for ang in (0, 60, 120, 180, 240, 300):
            rad = math.radians(ang)
            x1 = int(cx + 10 * math.cos(rad))
            y1 = int(cy + 10 * math.sin(rad))
            x2 = int(cx + 14 * math.cos(rad))
            y2 = int(cy + 14 * math.sin(rad))
            pygame.draw.line(screen, (200, 200, 200), (x1, y1), (x2, y2), 2)
        return rect

    def _current_music_pos_ms() -> int | None:
        """Safe wrapper for pygame.mixer.music.get_pos(), returning None if not playing."""
        try:
            pos = pygame.mixer.music.get_pos()
            if pos is None or pos < 0:
                return None
            return int(pos)
        except Exception:
            return None

    def _music_is_busy() -> bool:
        """Safe wrapper for pygame.mixer.music.get_busy()."""
        try:
            if not pygame.mixer.get_init():
                return False
            return bool(pygame.mixer.music.get_busy())
        except Exception:
            return False

    def _resume_bgm_if_needed(min_interval_s: float = 1.25) -> bool:
        """Retry BGM playback when browser autoplay or a scene swap left music stopped."""
        if _music_is_busy() or _current_music_pos_ms() is not None:
            return True
        runtime = _runtime()
        bgm = runtime.get("_bgm")
        if bgm is None or not getattr(bgm, "_ready", False):
            return False
        now_s = pygame.time.get_ticks() / 1000.0
        last_retry_s = float(runtime.get("_last_bgm_resume_retry_s", -999.0))
        if (now_s - last_retry_s) < float(min_interval_s):
            return False
        runtime["_last_bgm_resume_retry_s"] = now_s
        try:
            bgm.playBackGroundMusic(loops=-1, fade_ms=0)
            return True
        except Exception as e:
            print(f"[Audio] resume retry failed: {e}")
            return False

    def play_focus_chain_iso(screen, clock, game_state, player, enemies, bullets, enemy_shots, targets,
                             hold_time=0.9, label="BOSS"):
        """
        targets: list of (x_px, y_px) world-pixel centers (e.g., rect.centerx, rect.centery).
        Plays boss -> boss -> ... -> player (once).
        """
        if IS_WEB:
            flush_events()
            return
        last_cam = None
        for i, pos in enumerate(targets):
            fx, fy = pos
            focus_cam = compute_cam_for_center_iso(int(fx), int(fy))
            show_label = label if i == 0 else None
            play_focus_cinematic_iso(
                screen, clock, game_state, player, enemies, bullets, enemy_shots,
                (int(fx), int(fy)), label=show_label, hold_time=hold_time,
                return_to_player=False, start_cam=last_cam
            )
            last_cam = focus_cam
        pcenter = (int(player.rect.centerx), int(player.rect.centery))
        play_focus_cinematic_iso(
            screen, clock, game_state, player, enemies, bullets, enemy_shots,
            pcenter, label=None, hold_time=0.0,
            return_to_player=False, start_cam=last_cam
        )

    def play_focus_cinematic_iso(screen, clock,
                                 game_state, player,
                                 enemies, bullets, enemy_shots,
                                 focus_world_px: tuple[int, int],
                                 hold_time: float = 0.35,
                                 duration_each: float = 0.70,
                                 label: str | None = None,
                                 return_to_player: bool = True,
                                 start_cam: tuple[int, int] | None = None):
        """
        等距过场镜头：
        - 相机从 start_cam(若无则玩家) -> 焦点；可选 焦点 -> 玩家。
        - 冻结时间与世界更新，仅渲染。
        """
        if IS_WEB:
            flush_events()
            return

        def _cam_for_world_px(wx: float, wy: float) -> tuple[int, int]:
            gx = wx / CELL_SIZE
            gy = (wy - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(gx, gy, 0.0, 0.0, 0.0)
            camx = int(sx - game.VIEW_W // 2)
            camy = int(sy - (game.VIEW_H - INFO_BAR_HEIGHT) // 2)
            return camx, camy

        def _cam_for_player() -> tuple[int, int]:
            return calculate_iso_camera(player.x + player.size * 0.5,
                                        player.y + player.size * 0.5 + INFO_BAR_HEIGHT)

        def _lerp(a: float, b: float, t: float) -> float:
            return a + (b - a) * max(0.0, min(1.0, t))

        def _do_pan(cam_a: tuple[int, int], cam_b: tuple[int, int], dur: float):
            start = pygame.time.get_ticks()
            while True:
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        pygame.quit()
                        sys.exit()
                now = pygame.time.get_ticks()
                t = min(1.0, (now - start) / max(1.0, dur * 1000.0))
                camx = int(_lerp(cam_a[0], cam_b[0], t))
                camy = int(_lerp(cam_a[1], cam_b[1], t))
                render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots,
                                game_state.obstacles, override_cam=(camx, camy))
                if label:
                    font = pygame.font.SysFont(None, 42)
                    txt = font.render(label, True, (255, 230, 120))
                    screen.blit(txt, txt.get_rect(center=(game.VIEW_W // 2, INFO_BAR_HEIGHT + 50)))
                    pygame.display.flip()
                clock.tick(60)
                if t >= 1.0:
                    break

        player_cam = _cam_for_player()
        fx, fy = focus_world_px
        focus_cam = _cam_for_world_px(fx, fy)
        start_from = start_cam if start_cam is not None else player_cam
        _do_pan(start_from, focus_cam, duration_each)
        hold_start = pygame.time.get_ticks()
        while (pygame.time.get_ticks() - hold_start) < int(hold_time * 1000):
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
            render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots,
                            game_state.obstacles, override_cam=focus_cam)
            if label:
                font = pygame.font.SysFont(None, 42)
                txt = font.render(label, True, (255, 230, 120))
                screen.blit(txt, txt.get_rect(center=(game.VIEW_W // 2, INFO_BAR_HEIGHT + 50)))
                pygame.display.flip()
            clock.tick(60)
        if return_to_player:
            _do_pan(focus_cam, player_cam, duration_each)
        flush_events()

    def render_game_iso_web_lite(screen, game_state, player, enemies, bullets, enemy_shots, obstacles=None,
                                 override_cam: tuple[int, int] | None = None,
                                 copy_frame: bool = True) -> pygame.Surface | None:
        obstacles = obstacles if obstacles is not None else getattr(game_state, "obstacles", {})
        demo_mode = bool(getattr(game, "WEB_DEMO", False))
        pickup_cap = int(getattr(game, "WEB_DEMO_RENDER_PICKUP_CAP", 0)) if demo_mode else 0
        turret_cap = int(getattr(game, "WEB_DEMO_RENDER_TURRET_CAP", 0)) if demo_mode else 0
        enemy_cap = int(getattr(game, "WEB_DEMO_RENDER_ENEMY_CAP", 0)) if demo_mode else 0
        bullet_cap = int(getattr(game, "WEB_DEMO_RENDER_BULLET_CAP", 0)) if demo_mode else 0
        enemy_shot_cap = int(getattr(game, "WEB_DEMO_RENDER_ENEMY_SHOT_CAP", 0)) if demo_mode else 0
        px_grid = (player.x + player.size / 2) / CELL_SIZE
        py_grid = (player.y + player.size / 2) / CELL_SIZE
        if override_cam is not None:
            camx, camy = override_cam
        else:
            camx, camy = calculate_iso_camera(player.x + player.size * 0.5,
                                              player.y + player.size * 0.5 + INFO_BAR_HEIGHT)
        if hasattr(game_state, "camera_shake_offset"):
            dx, dy = game_state.camera_shake_offset()
            camx += dx
            camy += dy

        screen.fill(MAP_BG)
        margin = 2
        gx_min = max(0, int(px_grid - game.VIEW_W // max(1, ISO_CELL_W)) - margin)
        gx_max = min(GRID_SIZE - 1, int(px_grid + game.VIEW_W // max(1, ISO_CELL_W)) + margin)
        gy_min = max(0, int(py_grid - game.VIEW_H // max(1, ISO_CELL_H)) - margin)
        gy_max = min(GRID_SIZE - 1, int(py_grid + game.VIEW_H // max(1, ISO_CELL_H)) + margin)

        if getattr(player, "targeting_skill", None):
            _draw_skill_overlay(screen, player, camx, camy)

        drawables = []
        for (gx, gy), ob in obstacles.items():
            if not (gx_min <= gx <= gx_max and gy_min <= gy <= gy_max):
                continue
            if getattr(ob, "type", "") in ("Lantern", "StationaryTurret"):
                continue
            base_col = (120, 120, 120) if getattr(ob, "type", "") == "Indestructible" else (200, 80, 80)
            if getattr(ob, "type", "") == "Destructible" and getattr(ob, "health", None) is not None:
                t = max(0.4, min(1.0, ob.health / float(max(1, OBSTACLE_HEALTH))))
                base_col = (int(200 * t), int(80 * t), int(80 * t))
            top_pts = iso_tile_points(gx, gy, camx, camy)
            drawables.append(("wall", top_pts[2][1], {"gx": gx, "gy": gy, "color": base_col}))

        spoils = list(getattr(game_state, "spoils", []))
        if pickup_cap > 0:
            spoils = spoils[:pickup_cap]
        for s in spoils:
            wx, wy = s.base_x / CELL_SIZE, (s.base_y - s.h - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("coin", sy, {"cx": sx, "cy": sy, "r": s.r}))
        heals = list(getattr(game_state, "heals", []))
        if pickup_cap > 0:
            heals = heals[:pickup_cap]
        for h in heals:
            wx, wy = h.base_x / CELL_SIZE, (h.base_y - h.h - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("heal", sy, {"cx": sx, "cy": sy, "r": h.r}))
        items = list(getattr(game_state, "items", []))
        if pickup_cap > 0:
            items = items[:pickup_cap]
        for it in items:
            wx = it.center[0] / CELL_SIZE
            wy = (it.center[1] - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("item", sy, {"cx": sx, "cy": sy, "r": it.radius, "main": it.is_main}))
        turrets = list(getattr(game_state, "turrets", []))
        if turret_cap > 0:
            turrets = turrets[:turret_cap]
        for t in turrets:
            wx, wy = t.x / CELL_SIZE, (t.y - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("turret", sy, {"cx": sx, "cy": sy, "obj": t}))
        web_enemies = list(enemies)
        if enemy_cap > 0:
            web_enemies = web_enemies[:enemy_cap]
        for z in web_enemies:
            wx = z.rect.centerx / CELL_SIZE
            wy = (z.rect.bottom - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("enemy", sy, {"cx": sx, "cy": sy, "z": z}))
        wx = player.rect.centerx / CELL_SIZE
        wy = (player.rect.bottom - INFO_BAR_HEIGHT) / CELL_SIZE
        psx, psy = iso_world_to_screen(wx, wy, 0, camx, camy)
        drawables.append(("player", psy, {"cx": psx, "cy": psy, "p": player}))
        web_bullets = list(bullets or [])
        if bullet_cap > 0:
            web_bullets = web_bullets[:bullet_cap]
        for b in web_bullets:
            wx, wy = b.x / CELL_SIZE, (b.y - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("bullet", sy, {
                "cx": sx,
                "cy": sy,
                "r": int(getattr(b, "r", BULLET_RADIUS)),
                "src": getattr(b, "source", "player"),
            }))
        web_enemy_shots = list(enemy_shots or [])
        if enemy_shot_cap > 0:
            web_enemy_shots = web_enemy_shots[:enemy_shot_cap]
        for es in web_enemy_shots:
            wx, wy = es.x / CELL_SIZE, (es.y - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("eshot", sy, {
                "cx": sx,
                "cy": sy,
                "r": int(getattr(es, "r", BULLET_RADIUS)),
                "col": getattr(es, "color", (255, 120, 50)),
            }))

        drawables.sort(key=lambda x: x[1])
        for kind, _, data in drawables:
            if kind == "wall":
                draw_iso_tile(screen, data["gx"], data["gy"], data["color"], camx, camy, border=0)
            elif kind == "coin":
                pygame.draw.circle(screen, (255, 215, 80), (int(data["cx"]), int(data["cy"])), int(data["r"]))
            elif kind == "heal":
                pygame.draw.circle(screen, (225, 225, 225), (int(data["cx"]), int(data["cy"])), int(data["r"]))
            elif kind == "item":
                col = (255, 224, 0) if data.get("main", False) else (240, 210, 90)
                pygame.draw.circle(screen, col, (int(data["cx"]), int(data["cy"])), int(data["r"]))
            elif kind == "turret":
                obj = data.get("obj")
                cx = int(data["cx"])
                cy = int(data["cy"])
                if isinstance(obj, StationaryTurret):
                    sprite, _, _ = get_stationary_turret_assets()
                    if sprite:
                        rect = sprite.get_rect(midbottom=(cx, cy))
                        screen.blit(sprite, rect)
                    else:
                        pygame.draw.circle(screen, (80, 180, 255), (cx, cy - 6), max(7, CELL_SIZE // 5))
                elif isinstance(obj, AutoTurret):
                    owner = getattr(obj, "owner", None)
                    dir_key = None
                    facing = getattr(owner, "facing", None)
                    if facing:
                        if facing in ("E", "SE", "NE"):
                            dir_key = "right"
                        elif facing in ("W", "SW", "NW"):
                            dir_key = "left"
                        elif facing in ("N",):
                            dir_key = "up"
                        elif facing in ("S",):
                            dir_key = "down"
                    if dir_key is None:
                        if owner and hasattr(owner, "rect"):
                            ox, oy = owner.rect.center
                            dx, dy = cx - ox, cy - oy
                        else:
                            dx = dy = 0
                        if abs(dx) >= abs(dy):
                            dir_key = "right" if dx >= 0 else "left"
                        else:
                            dir_key = "down" if dy >= 0 else "up"
                    sprite = _auto_turret_sprite(dir_key)
                    if sprite:
                        rect = sprite.get_rect(midbottom=(cx, cy))
                        screen.blit(sprite, rect)
                    else:
                        pygame.draw.circle(screen, (80, 180, 255), (cx, cy - 6), max(7, CELL_SIZE // 5))
                else:
                    pygame.draw.circle(screen, (80, 180, 255), (cx, cy - 6), max(7, CELL_SIZE // 5))
            elif kind == "bullet":
                col = (0, 255, 255) if data.get("src") == "turret" else (120, 204, 121)
                pygame.draw.circle(screen, col, (int(data["cx"]), int(data["cy"])), max(2, int(data["r"])))
            elif kind == "eshot":
                pygame.draw.circle(screen, data.get("col", (255, 120, 50)),
                                   (int(data["cx"]), int(data["cy"])), max(2, int(data["r"])))
            elif kind == "enemy":
                z = data["z"]
                cx = int(data["cx"])
                cy = int(data["cy"] - max(10, int(getattr(z, "size", CELL_SIZE * 0.6) * 0.45)))
                draw_size = max(int(CELL_SIZE * 0.6), int(getattr(z, "rect", pygame.Rect(0, 0, CELL_SIZE, CELL_SIZE)).w))
                if getattr(z, "is_boss", False) or getattr(z, "type", "") == "ravager":
                    draw_size = max(draw_size * 2, int(getattr(z, "rect", pygame.Rect(0, 0, CELL_SIZE, CELL_SIZE)).w * 2))
                enemy_sprite = _enemy_sprite(getattr(z, "type", ""), draw_size)
                if enemy_sprite:
                    rect = enemy_sprite.get_rect(midbottom=(cx, int(data["cy"])))
                    screen.blit(enemy_sprite, rect)
                    body_r = max(8, int(draw_size * 0.18))
                    hp_anchor_y = rect.top
                else:
                    body_r = max(8, int(getattr(z, "size", CELL_SIZE * 0.6) * 0.34))
                    pygame.draw.circle(screen, getattr(z, "color", (220, 90, 90)), (cx, cy), body_r)
                    pygame.draw.circle(screen, (16, 26, 40), (cx, cy), body_r, 2)
                    hp_anchor_y = cy - body_r
                hp = max(0, int(getattr(z, "hp", 0)))
                hp_max = max(1, int(getattr(z, "max_hp", hp or 1)))
                if hp < hp_max:
                    bar_w = max(18, body_r * 2)
                    top = hp_anchor_y - 10
                    pygame.draw.rect(screen, (24, 34, 48), (cx - bar_w // 2, top, bar_w, 4))
                    pygame.draw.rect(screen, (90, 220, 120), (cx - bar_w // 2, top, int(bar_w * hp / hp_max), 4))
            elif kind == "player":
                p = data["p"]
                cx = int(data["cx"])
                player_size = int(CELL_SIZE * 0.6)
                sprite_w = int(player_size * 2.0 * PLAYER_SPRITE_SCALE)
                sprite_h = int(player_size * 2.4 * PLAYER_SPRITE_SCALE)
                player_sprite = _load_shop_sprite(
                    "characters/player/sheets/player.png",
                    (sprite_w, sprite_h),
                    allow_upscale=False,
                )
                if player_sprite:
                    rect = player_sprite.get_rect(midbottom=(cx, int(data["cy"])))
                    screen.blit(player_sprite, rect)
                else:
                    cy = int(data["cy"] - max(10, int(getattr(p, "size", CELL_SIZE * 0.6) * 0.45)))
                    body_r = max(9, int(getattr(p, "size", CELL_SIZE * 0.6) * 0.36))
                    pygame.draw.circle(screen, getattr(p, "color", (110, 250, 170)), (cx, cy), body_r)
                    pygame.draw.circle(screen, (12, 24, 40), (cx, cy), body_r, 2)

        draw_ui_topbar(
            screen,
            game_state,
            player,
            time_left=_runtime().get("_time_left_runtime"),
            enemies=enemies,
        )
        bosses = _find_all_bosses(enemies)
        if len(bosses) >= 2:
            draw_boss_hp_bars_twin(screen, bosses[:2])
        elif len(bosses) == 1:
            draw_boss_hp_bar(screen, bosses[0])
        run_pending_menu_transition(screen)
        pygame.display.flip()
        return screen.copy() if copy_frame else None

    def render_game_iso(screen, game_state, player, enemies, bullets, enemy_shots, obstacles=None,
                        override_cam: tuple[int, int] | None = None,
                        copy_frame: bool = True):
        obstacles = obstacles if obstacles is not None else getattr(game_state, "obstacles", {})
        if IS_WEB and getattr(game, "WEB_USE_LITE_RENDER", False):
            return render_game_iso_web_lite(
                screen, game_state, player, enemies, bullets, enemy_shots, obstacles,
                override_cam=override_cam,
                copy_frame=copy_frame,
            )
        px_grid = (player.x + player.size / 2) / CELL_SIZE
        py_grid = (player.y + player.size / 2) / CELL_SIZE
        pxs, pys = iso_world_to_screen(px_grid, py_grid, 0, 0, 0)
        camx = pxs - game.VIEW_W // 2
        camy = pys - (game.VIEW_H - INFO_BAR_HEIGHT) // 2
        if override_cam is not None:
            camx, camy = override_cam
        else:
            camx, camy = calculate_iso_camera(player.x + player.size * 0.5,
                                              player.y + player.size * 0.5 + INFO_BAR_HEIGHT)
        if hasattr(game_state, "camera_shake_offset"):
            dx, dy = game_state.camera_shake_offset()
            camx += dx
            camy += dy
        screen.fill(MAP_BG)
        margin = 2 if IS_WEB else 3
        gx_min = max(0, int(px_grid - game.VIEW_W // ISO_CELL_W) - margin)
        gx_max = min(GRID_SIZE - 1, int(px_grid + game.VIEW_W // ISO_CELL_W) + margin)
        gy_min = max(0, int(py_grid - game.VIEW_H // ISO_CELL_H) - margin)
        gy_max = min(GRID_SIZE - 1, int(py_grid + game.VIEW_H // ISO_CELL_H) + margin)
        grid_col = MAP_GRID
        for gx in range(gx_min, gx_max + 1):
            for gy in range(gy_min, gy_max + 1):
                draw_iso_tile(screen, gx, gy, grid_col, camx, camy, border=1)
        for t in getattr(game_state, "telegraphs", []):
            draw_iso_ground_ellipse(
                screen, t.x, t.y, t.r,
                color=t.color, alpha=180,
                camx=camx, camy=camy,
                fill=False, width=3
            )
        if getattr(player, "targeting_skill", None):
            skill = player.targeting_skill
            origin = getattr(player, "skill_target_origin", None)
            px, py = origin if (skill == "blast" and origin) else player.rect.center
            cast_range = _skill_cast_range(skill, player) if skill == "blast" else float(TELEPORT_RANGE)
            ring_col = (255, 140, 70) if skill == "blast" else (90, 190, 255)
            draw_iso_ground_ellipse(screen, px, py, cast_range, ring_col, 60, camx, camy, fill=False, width=3)
            tx, ty = getattr(player, "skill_target_pos", (px, py))
            valid = bool(getattr(player, "skill_target_valid", False))
            col_valid = (255, 120, 60) if skill == "blast" else (80, 210, 255)
            col_invalid = (230, 60, 60)
            col = col_valid if valid else col_invalid
            if skill == "blast":
                draw_iso_ground_ellipse(screen, tx, ty, BLAST_RADIUS, col, 90 if valid else 60, camx, camy, fill=False, width=4)
                draw_iso_ground_ellipse(screen, tx, ty, BLAST_RADIUS * 0.4, col, 80 if valid else 50, camx, camy, fill=True)
            else:
                draw_iso_ground_ellipse(screen, tx, ty, max(20, player.size), col, 80 if valid else 50, camx, camy, fill=False, width=4)

        if _web_feature_enabled("WEB_ENABLE_HURRICANES"):
            for h in getattr(game_state, "hurricanes", []):
                pulse = 0.6 + 0.4 * math.sin(pygame.time.get_ticks() * 0.008)
                alpha = int(40 + 60 * pulse)
                draw_iso_ground_ellipse(
                    screen, h.x, h.y, h.r * HURRICANE_RANGE_MULT,
                    color=(100, 120, 150), alpha=alpha,
                    camx=camx, camy=camy,
                    fill=False, width=2
                )
                if hasattr(h, "draw"):
                    h.draw(screen, camx, camy)
                else:
                    hx, hy = float(h.get("x", 0)), float(h.get("y", 0))
                    draw_iso_ground_ellipse(screen, hx, hy, 40, (100, 100, 100), 200, camx, camy)

        if _web_feature_enabled("WEB_ENABLE_AEGIS_PULSES"):
            for p in getattr(game_state, "aegis_pulses", []):
                age = max(0.0, float(getattr(p, "age", 0.0)))
                delay = max(0.0, float(getattr(p, "delay", 0.0)))
                expand_time = max(0.001, float(getattr(p, "expand_time", AEGIS_PULSE_BASE_EXPAND_TIME)))
                fade_time = max(0.001, float(getattr(p, "fade_time", AEGIS_PULSE_RING_FADE)))
                if age < delay:
                    continue
                grow_progress = max(0.0, min(1.0, (age - delay) / expand_time))
                fade_age = age - (delay + expand_time)
                fade = 1.0 if fade_age <= 0 else max(0.0, 1.0 - fade_age / fade_time)
                if fade <= 0:
                    continue
                current_r = max(AEGIS_PULSE_MIN_START_R, float(getattr(p, "r", 0.0)) * grow_progress)
                draw_iso_hex_ring(
                    screen, p.x, p.y, current_r,
                    AEGIS_PULSE_COLOR, int(AEGIS_PULSE_RING_ALPHA * fade),
                    camx, camy,
                    sides=6,
                    fill_alpha=int(AEGIS_PULSE_FILL_ALPHA * fade),
                    width=2
                )
        for a in getattr(game_state, "acids", []):
            draw_iso_ground_ellipse(
                screen, a.x, a.y, a.r,
                color=(60, 200, 90), alpha=110,
                camx=camx, camy=camy,
                fill=True
            )
        player_rect = getattr(player, "rect", None)
        enemy_rects = [getattr(z, "rect", None) for z in enemies if getattr(z, "rect", None)]
        if not IS_WEB:
            for g in getattr(game_state, "ghosts", []):
                gw = getattr(g, "w", 0)
                gh = getattr(g, "h", 0)
                if gw and gh:
                    ghost_rect = pygame.Rect(0, 0, int(gw), int(gh))
                    ghost_rect.midbottom = (int(getattr(g, "x", 0)), int(getattr(g, "y", 0)))
                    if player_rect and ghost_rect.colliderect(player_rect):
                        continue
                    if enemy_rects and any(ghost_rect.colliderect(er) for er in enemy_rects if er):
                        continue
                g.draw_iso(screen, camx, camy)
        if _web_feature_enabled("WEB_ENABLE_ENEMY_PAINT") and hasattr(game_state, "draw_paint_iso"):
            game_state.draw_paint_iso(screen, camx, camy)
        drawables = []
        for (gx, gy), ob in game_state.obstacles.items():
            if getattr(ob, "type", "") == "Lantern":
                continue
            if getattr(ob, "type", "") == "StationaryTurret":
                continue
            base_col = (120, 120, 120) if ob.type == "Indestructible" else (200, 80, 80)
            if ob.type == "Destructible" and ob.health is not None:
                t = max(0.4, min(1.0, ob.health / float(max(1, OBSTACLE_HEALTH))))
                base_col = (int(200 * t), int(80 * t), int(80 * t))
            top_pts = iso_tile_points(gx, gy, camx, camy)
            sort_y = top_pts[2][1] + (ISO_WALL_Z if WALL_STYLE == "prism" else (12 if WALL_STYLE == "hybrid" else 0))
            drawables.append(("wall", sort_y, {"gx": gx, "gy": gy, "color": base_col}))
        for s in getattr(game_state, "spoils", []):
            wx, wy = s.base_x / CELL_SIZE, (s.base_y - s.h - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("coin", sy, {"cx": sx, "cy": sy, "r": s.r}))
        for t in getattr(game_state, "turrets", []):
            wx, wy = t.x / CELL_SIZE, (t.y - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("turret", sy, {"cx": sx, "cy": sy, "obj": t}))
        for h in getattr(game_state, "heals", []):
            wx, wy = h.base_x / CELL_SIZE, (h.base_y - h.h - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("heal", sy, {"cx": sx, "cy": sy, "r": h.r}))
        for it in getattr(game_state, "items", []):
            wx = it.center[0] / CELL_SIZE
            wy = (it.center[1] - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("item", sy, {"cx": sx, "cy": sy, "r": it.radius, "main": it.is_main}))
        for z in enemies:
            wx = z.rect.centerx / CELL_SIZE
            wy = (z.rect.bottom - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("enemy", sy, {"cx": sx, "cy": sy, "z": z}))
        wx = player.rect.centerx / CELL_SIZE
        wy = (player.rect.bottom - INFO_BAR_HEIGHT) / CELL_SIZE
        psx, psy = iso_world_to_screen(wx, wy, 0, camx, camy)
        drawables.append(("player", psy, {"cx": psx, "cy": psy, "p": player}))
        if bullets:
            for b in bullets:
                wx, wy = b.x / CELL_SIZE, (b.y - INFO_BAR_HEIGHT) / CELL_SIZE
                sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
                drawables.append((
                    "bullet",
                    sy,
                    {
                        "cx": sx,
                        "cy": sy,
                        "r": int(getattr(b, "r", BULLET_RADIUS)),
                        "src": getattr(b, "source", "player"),
                    },
                ))
        if enemy_shots:
            for es in enemy_shots:
                wx, wy = es.x / CELL_SIZE, (es.y - INFO_BAR_HEIGHT) / CELL_SIZE
                sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
                if isinstance(es, MistShot):
                    drawables.append(("mistshot", sy, {"cx": sx, "cy": sy, "obj": es}))
                else:
                    drawables.append(("eshot", sy, {
                        "cx": sx, "cy": sy,
                        "r": int(getattr(es, "r", BULLET_RADIUS))
                    }))
        drawables.sort(key=lambda x: x[1])
        hell = (getattr(game_state, "biome_active", "") == "Scorched Hell")
        COL_PLAYER_BULLET = (199, 68, 12) if hell else (120, 204, 121)
        COL_ENEMY_SHOT = (255, 80, 80) if hell else (255, 120, 50)
        for kind, _, data in drawables:
            if kind == "wall":
                gx, gy, col = data["gx"], data["gy"], data["color"]
                if WALL_STYLE == "prism":
                    draw_iso_prism(screen, gx, gy, col, camx, camy, wall_h=ISO_WALL_Z)
                elif WALL_STYLE == "hybrid":
                    draw_iso_prism(screen, gx, gy, col, camx, camy, wall_h=12)
                    wx, wy = gx + 0.5, gy + 0.5
                    sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
                    rect_h = int(ISO_CELL_H * 1.8)
                    rect_w = int(ISO_CELL_W * 0.35)
                    pillar = pygame.Rect(0, 0, rect_w, rect_h)
                    pillar.midbottom = (sx, sy)
                    pygame.draw.rect(screen, col, pillar, border_radius=rect_w // 3)
                else:
                    draw_iso_tile(screen, gx, gy, col, camx, camy, border=0)
            elif kind == "coin":
                cx, cy, r = data["cx"], data["cy"], data["r"]
                shadow = pygame.Surface((r * 4, r * 2), pygame.SRCALPHA)
                pygame.draw.ellipse(shadow, (0, 0, 0, ISO_SHADOW_ALPHA), shadow.get_rect())
                screen.blit(shadow, shadow.get_rect(center=(cx, cy + 6)))
                pygame.draw.circle(screen, (255, 215, 80), (cx, cy), r)
                pygame.draw.circle(screen, (255, 245, 200), (cx, cy), r, 1)
            elif kind == "heal":
                cx, cy, r = data["cx"], data["cy"], data["r"]
                shadow = pygame.Surface((r * 4, r * 2), pygame.SRCALPHA)
                pygame.draw.ellipse(shadow, (0, 0, 0, ISO_SHADOW_ALPHA), shadow.get_rect())
                screen.blit(shadow, shadow.get_rect(center=(cx, cy + 6)))
                pygame.draw.circle(screen, (225, 225, 225), (cx, cy), r)
                pygame.draw.rect(screen, (220, 60, 60), pygame.Rect(cx - 2, cy - r + 3, 4, r * 2 - 6))
                pygame.draw.rect(screen, (200, 40, 40), pygame.Rect(cx - r + 3, cy - 2, r * 2 - 6, 4))
            elif kind == "item":
                cx, cy, r = data["cx"], data["cy"], data["r"]
                shadow = pygame.Surface((r * 4, r * 2), pygame.SRCALPHA)
                pygame.draw.ellipse(shadow, (0, 0, 0, ISO_SHADOW_ALPHA), shadow.get_rect())
                screen.blit(shadow, shadow.get_rect(center=(cx, cy + 6)))
                glow = pygame.Surface((r * 4, r * 2), pygame.SRCALPHA)
                pygame.draw.ellipse(glow, (255, 240, 120, 90), glow.get_rect())
                screen.blit(glow, glow.get_rect(center=(cx, cy + 6)))
                pygame.draw.circle(screen, (255, 224, 0), (cx, cy), r)
                pygame.draw.circle(screen, (255, 255, 180), (cx, cy), r, 2)
            elif kind == "turret":
                cx, cy = int(data["cx"]), int(data["cy"])
                obj = data.get("obj")
                if isinstance(obj, StationaryTurret):
                    sprite, foot_w, foot_h = get_stationary_turret_assets()
                    if sprite:
                        shadow_w = max(int(foot_w * 1.4), int(CELL_SIZE * 0.9))
                        shadow_h = max(int(foot_h * 0.8), int(CELL_SIZE * 0.4))
                        shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
                        pygame.draw.ellipse(shadow, (0, 0, 0, ISO_SHADOW_ALPHA), shadow.get_rect())
                        screen.blit(shadow, shadow.get_rect(center=(cx, cy + 6)))
                        rect = sprite.get_rect(midbottom=(cx, cy))
                        screen.blit(sprite, rect)
                    else:
                        base_r = 10
                        pygame.draw.circle(screen, (80, 180, 255), (cx, cy), base_r)
                        pygame.draw.circle(screen, (250, 250, 255), (cx, cy), base_r - 4, 2)
                elif isinstance(obj, AutoTurret):
                    owner = getattr(obj, "owner", None)
                    dir_key = None
                    facing = getattr(owner, "facing", None)
                    if facing:
                        if facing in ("E", "SE", "NE"):
                            dir_key = "right"
                        elif facing in ("W", "SW", "NW"):
                            dir_key = "left"
                        elif facing in ("N",):
                            dir_key = "up"
                        elif facing in ("S",):
                            dir_key = "down"
                    if dir_key is None:
                        if owner and hasattr(owner, "rect"):
                            ox, oy = owner.rect.center
                            dx, dy = cx - ox, cy - oy
                        else:
                            dx = dy = 0
                        if abs(dx) >= abs(dy):
                            dir_key = "right" if dx >= 0 else "left"
                        else:
                            dir_key = "down" if dy >= 0 else "up"
                    sprite = _auto_turret_sprite(dir_key)
                    if sprite:
                        shadow_w = max(int(sprite.get_width() * 0.6), int(CELL_SIZE * 0.6))
                        shadow_h = max(int(sprite.get_height() * 0.32), int(CELL_SIZE * 0.28))
                        shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
                        pygame.draw.ellipse(shadow, (0, 0, 0, ISO_SHADOW_ALPHA), shadow.get_rect())
                        screen.blit(shadow, shadow.get_rect(center=(cx, cy + 6)))
                        rect = sprite.get_rect(midbottom=(cx, cy))
                        screen.blit(sprite, rect)
                    else:
                        base_r = 9
                        pygame.draw.circle(screen, (80, 200, 255), (cx, cy), base_r)
                        pygame.draw.circle(screen, (240, 240, 255), (cx, cy), base_r - 3, 2)
                else:
                    base_r = 10
                    pygame.draw.circle(screen, (80, 180, 255), (cx, cy), base_r)
                    pygame.draw.circle(screen, (250, 250, 255), (cx, cy), base_r - 4, 2)
            elif kind == "bullet":
                cx, cy = data["cx"], data["cy"]
                rad = int(data.get("r", BULLET_RADIUS))
                src = data.get("src", "player")
                color = (0, 255, 255) if src == "turret" else COL_PLAYER_BULLET
                pygame.draw.circle(screen, color, (cx, cy), rad)
            elif kind == "eshot":
                rad = int(data.get("r", BULLET_RADIUS))
                pygame.draw.circle(screen, COL_ENEMY_SHOT, (data["cx"], data["cy"]), rad)
            elif kind == "mistshot":
                es = data.get("obj")
                rad = int(getattr(es, "r", BULLET_RADIUS))
                col = getattr(es, "color", HAZARD_STYLES["mist"]["ring"])
                pygame.draw.circle(screen, col, (data["cx"], data["cy"]), rad)
            elif kind == "enemy":
                z, cx, cy = data["z"], float(data["cx"]), float(data["cy"])
                if getattr(z, "type", "") == "bandit" and getattr(z, "radar_tagged", False):
                    base_rr = max(24, int(getattr(z, "radius", 0) * 4.0))
                    phase = float(getattr(z, "radar_ring_phase", 0.0))
                    pulse = 1.0 + 0.10 * math.sin(math.tau * phase)
                    ring_r = max(20, int(base_rr * pulse))
                    draw_iso_ground_ellipse(
                        screen,
                        z.rect.centerx,
                        z.rect.centery,
                        ring_r,
                        (255, 60, 60),
                        220,
                        camx,
                        camy,
                        fill=False,
                        width=4,
                    )
                glow_t = float(getattr(z, "_curing_paint_glow_t", 0.0))
                if glow_t > 0.0:
                    glow_ratio = max(0.0, min(1.0, glow_t / 0.14))
                    glow_int = max(0.0, float(getattr(z, "_curing_paint_glow_intensity", 0.0)))
                    alpha = int(110 * glow_ratio * (0.5 + 0.5 * glow_int))
                    if alpha > 0:
                        glow_r = max(10, int(getattr(z, "radius", CELL_SIZE * 0.3) * 1.1))
                        draw_iso_ground_ellipse(
                            screen,
                            z.rect.centerx,
                            z.rect.centery,
                            glow_r,
                            CURING_PAINT_SPARK_COLORS[0],
                            alpha,
                            camx,
                            camy,
                            fill=True,
                        )
                shake = float(getattr(z, "_comet_shake", 0.0))
                if shake > 0.0:
                    amp = min(6.0, 10.0 * shake)
                    t = pygame.time.get_ticks() * 0.02 + z.rect.x * 0.03 + z.rect.y * 0.01
                    cx += math.sin(t) * amp
                    cy += math.cos(t * 1.4) * amp * 0.6
                cx = int(round(cx))
                cy = int(round(cy))
                player_size = int(CELL_SIZE * 0.6)
                if getattr(z, "is_boss", False) or getattr(z, "type", "") == "ravager":
                    draw_size = max(player_size * 2, int(z.rect.w * 2))
                else:
                    draw_size = max(player_size, int(z.rect.w))
                body = pygame.Rect(0, 0, draw_size, draw_size)
                body.midbottom = (cx, cy)
                enemy_sprite = _enemy_sprite(getattr(z, "type", ""), draw_size)
                sh_w = max(8, int(draw_size * 0.9))
                sh_h = max(4, int(draw_size * 0.45))
                sh = pygame.Surface((sh_w, sh_h), pygame.SRCALPHA)
                pygame.draw.ellipse(sh, (0, 0, 0, ISO_SHADOW_ALPHA), sh.get_rect())
                screen.blit(sh, sh.get_rect(center=(cx, cy + 6)))
                sprite_rect = body
                if getattr(z, "_gold_glow_t", 0.0) > 0.0:
                    glow = pygame.Surface((int(draw_size * 1.6), int(draw_size * 1.0)), pygame.SRCALPHA)
                    alpha = int(120 * (z._gold_glow_t / Z_GLOW_TIME))
                    pygame.draw.ellipse(glow, (255, 220, 90, max(30, alpha)), glow.get_rect())
                    screen.blit(glow, glow.get_rect(center=(cx, cy)))
                base_col = ENEMY_COLORS.get(getattr(z, "type", "basic"), (255, 60, 60))
                col = getattr(z, "_current_color", getattr(z, "color", base_col))
                flash = float(getattr(z, "_comet_flash", 0.0))
                if flash > 0.0:
                    f = min(1.0, flash * 2.8)
                    col = (
                        min(255, int(col[0] + (255 - col[0]) * f)),
                        min(255, int(col[1] + (255 - col[1]) * f)),
                        min(255, int(col[2] + (255 - col[2]) * f)),
                    )
                if enemy_sprite:
                    sprite_rect = enemy_sprite.get_rect(midbottom=body.midbottom)
                    screen.blit(enemy_sprite, sprite_rect)
                else:
                    pygame.draw.rect(screen, col, body)
                    if not getattr(z, "is_boss", False):
                        outline_rect = body.inflate(6, 6)
                        pygame.draw.rect(screen, (230, 210, 230), outline_rect, 2, border_radius=4)
                if flash > 0.0 and enemy_sprite:
                    flash_ratio = min(1.0, flash * 2.8)
                    flash_alpha = int(200 * flash_ratio)
                    if flash_alpha > 0:
                        blit_sprite_tint(screen, enemy_sprite, sprite_rect.topleft, (255, 255, 255, flash_alpha))
                if getattr(z, "shield_hp", 0) > 0:
                    t = pygame.time.get_ticks() * 0.006
                    a = 120 + int(80 * (0.5 + 0.5 * math.sin(t)))
                    if enemy_sprite:
                        draw_sprite_outline(
                            screen,
                            enemy_sprite,
                            sprite_rect.topleft,
                            (90, 180, 255, a),
                            width=3,
                        )
                dot_ratio, dot_count = dot_rounds_visual_state(z)
                if dot_ratio > 0.0:
                    glow_w = max(12, int(draw_size * 1.1))
                    glow_h = max(8, int(draw_size * 0.7))
                    tick_interval = float(DOT_ROUNDS_TICK_INTERVAL)
                    tick_t = float(getattr(z, "_dot_rounds_tick_t", tick_interval))
                    if tick_interval > 0.0:
                        phase = 1.0 - max(0.0, min(1.0, tick_t / tick_interval))
                        pulse = 0.7 + 0.3 * math.sin(phase * math.tau)
                    else:
                        pulse = 1.0
                    glow_alpha = int(120 * dot_ratio * pulse)
                    fill_alpha = int(55 * dot_ratio * pulse)
                    glow = pygame.Surface((glow_w, glow_h), pygame.SRCALPHA)
                    pygame.draw.ellipse(
                        glow,
                        (DOT_ROUNDS_GLOW_COLOR[0], DOT_ROUNDS_GLOW_COLOR[1], DOT_ROUNDS_GLOW_COLOR[2], fill_alpha),
                        glow.get_rect(),
                    )
                    pygame.draw.ellipse(
                        glow,
                        (DOT_ROUNDS_GLOW_COLOR[0], DOT_ROUNDS_GLOW_COLOR[1], DOT_ROUNDS_GLOW_COLOR[2], glow_alpha),
                        glow.get_rect(),
                        width=2,
                    )
                    glow_rect = glow.get_rect(center=(cx, body.centery - 4))
                    screen.blit(glow, glow_rect)
                    orb_count = 0
                    if dot_count > 0:
                        orb_count = 2 if dot_count < 2 else 3
                    if orb_count > 0:
                        orb_surf = pygame.Surface((glow_w, glow_h), pygame.SRCALPHA)
                        orb_alpha = int(190 * dot_ratio * pulse)
                        ocx, ocy = glow_w // 2, glow_h // 2
                        orbit_r = max(6, int(draw_size * 0.45))
                        t = pygame.time.get_ticks() * 0.003
                        for i in range(orb_count):
                            ang = t + i * math.tau / max(1, orb_count)
                            ox = int(math.cos(ang) * orbit_r)
                            oy = int(math.sin(ang) * orbit_r * 0.6)
                            pygame.draw.circle(
                                orb_surf, (DOT_ROUNDS_GLOW_COLOR[0], DOT_ROUNDS_GLOW_COLOR[1], DOT_ROUNDS_GLOW_COLOR[2], orb_alpha),
                                (ocx + ox, ocy + oy), 2,
                            )
                            pygame.draw.circle(
                                orb_surf, (255, 255, 255, max(40, orb_alpha - 90)),
                                (ocx + ox, ocy + oy), 1,
                            )
                        screen.blit(orb_surf, glow_rect.topleft)
                spike_slow_t = float(getattr(z, "_ground_spike_slow_t", 0.0))
                if spike_slow_t > 0.0:
                    ratio = max(0.0, min(1.0, spike_slow_t / max(0.001, GROUND_SPIKES_SLOW_DURATION)))
                    alpha = int(200 * ratio)
                    bob = int(2 * math.sin(pygame.time.get_ticks() * 0.01 + z.rect.x * 0.03))
                    icon = pygame.Surface((12, 10), pygame.SRCALPHA)
                    arrow = [(6, 8), (2, 2), (10, 2)]
                    pygame.draw.polygon(
                        icon,
                        (GROUND_SPIKES_COLOR[0], GROUND_SPIKES_COLOR[1], GROUND_SPIKES_COLOR[2], alpha),
                        arrow,
                    )
                    pygame.draw.polygon(icon, (255, 255, 255, max(60, alpha - 80)), arrow, 1)
                    screen.blit(icon, icon.get_rect(center=(cx, body.top - 12 + bob)))
                if getattr(z, "type", "") == "bandit":
                    bar_w = draw_size
                    bar_h = 5
                    bar_bg = pygame.Rect(0, 0, bar_w, bar_h)
                    bar_bg.midbottom = (cx, body.top - 6)
                    pygame.draw.rect(screen, (30, 30, 30), bar_bg, border_radius=2)
                    mhp = float(max(1, getattr(z, "max_hp", 1)))
                    hp_ratio = 0.0 if mhp <= 0 else max(0.0, min(1.0, float(getattr(z, "hp", 0)) / mhp))
                    if hp_ratio > 0:
                        fill = pygame.Rect(bar_bg.left + 1, bar_bg.top + 1, int((bar_w - 2) * hp_ratio), bar_h - 2)
                        pygame.draw.rect(screen, (210, 70, 70), fill, border_radius=2)
                coins = int(getattr(z, "spoils", 0))
                if coins > 0:
                    f = pygame.font.SysFont(None, 18)
                    txt = f.render(f"{coins}", True, (255, 225, 120))
                    screen.blit(txt, txt.get_rect(midbottom=(cx, body.top - 4)))
                if z.is_boss and not enemy_sprite:
                    pygame.draw.rect(screen, (255, 215, 0), body.inflate(4, 4), 3)
                if not enemy_sprite:
                    pygame.draw.rect(screen, col, body)
                paint_intensity = 0.0
                if hasattr(game_state, "paint_intensity_at_world"):
                    paint_intensity = game_state.paint_intensity_at_world(z.rect.centerx, z.rect.centery, owner=2)
                if paint_intensity > 0.0:
                    tint_alpha = int(70 * paint_intensity)
                    if tint_alpha > 0:
                        tint_h = max(4, int(draw_size * 0.38))
                        tint = pygame.Surface((draw_size, tint_h), pygame.SRCALPHA)
                        tint.fill((20, 80, 50, tint_alpha))
                        screen.blit(tint, (body.left, body.bottom - tint_h))
                flash_t = float(getattr(z, "_hit_flash", 0.0))
                if flash_t > 0.0 and HIT_FLASH_DURATION > 0:
                    flash_ratio = min(1.0, flash_t / HIT_FLASH_DURATION)
                    if enemy_sprite:
                        blit_sprite_tint(
                            screen,
                            enemy_sprite,
                            sprite_rect.topleft,
                            (255, 255, 255, int(200 * flash_ratio)),
                        )
                    else:
                        overlay = pygame.Surface(body.size, pygame.SRCALPHA)
                        overlay.fill((255, 255, 255, int(200 * flash_ratio)))
                        screen.blit(overlay, body.topleft)
                mark_t = float(getattr(z, "_vuln_mark_t", 0.0))
                if mark_t > 0.0:
                    flash = float(getattr(z, "_vuln_hit_flash", 0.0))
                    lvl_vis = int(getattr(z, "_vuln_mark_level", 1))
                    lvl_vis = max(1, min(lvl_vis, len(VULN_MARK_DURATIONS)))
                    dur_vis = VULN_MARK_DURATIONS[lvl_vis - 1]
                    rem_ratio = max(0.0, min(1.0, mark_t / max(0.001, dur_vis)))
                    phase = (_runtime().get("mark_pulse_time", 0.0) % MARK_PULSE_PERIOD) / MARK_PULSE_PERIOD
                    pulse = 0.5 + 0.5 * math.sin(phase * math.tau)
                    scale = MARK_PULSE_MIN_SCALE + (MARK_PULSE_MAX_SCALE - MARK_PULSE_MIN_SCALE) * pulse
                    base_size = max(18, int(draw_size * 0.9))
                    size = int(base_size * scale)
                    alpha = int(
                        (MARK_PULSE_MIN_ALPHA + (MARK_PULSE_MAX_ALPHA - MARK_PULSE_MIN_ALPHA) * pulse)
                        * rem_ratio
                    )
                    alpha = int(min(255, alpha + int(80 * min(1.0, flash))))
                    mark_rect = pygame.Rect(0, 0, size, size)
                    mark_rect.midbottom = (cx, body.top - 6)

                    def draw_tapered_line(surf, color_rgba, p0, p1, w0, w1):
                        dx, dy = (p1[0] - p0[0], p1[1] - p0[1])
                        L = (dx * dx + dy * dy) ** 0.5 or 1.0
                        nx, ny = -dy / L, dx / L
                        hw0 = w0 * 0.5
                        hw1 = w1 * 0.5
                        pts = [
                            (p0[0] + nx * hw0, p0[1] + ny * hw0),
                            (p0[0] - nx * hw0, p0[1] - ny * hw0),
                            (p1[0] - nx * hw1, p1[1] - ny * hw1),
                            (p1[0] + nx * hw1, p1[1] + ny * hw1),
                        ]
                        pygame.draw.polygon(surf, color_rgba, pts)

                    def draw_tapered_x(surf, size_px, outline_col, fill_col):
                        a = size_px * 0.2
                        b = size_px * 0.8
                        thick_center = max(3.0, size_px * 0.22)
                        thin_tip = max(1.5, thick_center * 0.35)
                        draw_tapered_line(surf, outline_col, (a, a), (b, b), thin_tip * 1.8, thick_center * 1.85)
                        draw_tapered_line(surf, outline_col, (b, a), (a, b), thin_tip * 1.8, thick_center * 1.85)
                        draw_tapered_line(surf, fill_col, (a, a), (b, b), thin_tip, thick_center)
                        draw_tapered_line(surf, fill_col, (b, a), (a, b), thin_tip, thick_center)

                    red_col = (
                        int(MARK_PULSE_DARK[0] + (MARK_PULSE_BRIGHT[0] - MARK_PULSE_DARK[0]) * pulse),
                        int(MARK_PULSE_DARK[1] + (MARK_PULSE_BRIGHT[1] - MARK_PULSE_DARK[1]) * pulse),
                        int(MARK_PULSE_DARK[2] + (MARK_PULSE_BRIGHT[2] - MARK_PULSE_DARK[2]) * pulse),
                        max(0, min(255, alpha)),
                    )
                    black_col = (0, 0, 0, max(0, min(255, alpha)))
                    mark = pygame.Surface(mark_rect.size, pygame.SRCALPHA)
                    draw_tapered_x(mark, size, black_col, red_col)
                    screen.blit(mark, mark_rect)
                if getattr(z, "shield_hp", 0) > 0 and not enemy_sprite:
                    t = pygame.time.get_ticks() * 0.006
                    a = 120 + int(80 * (0.5 + 0.5 * math.sin(t)))
                    shield_sprite = _rect_sprite(body.width, body.height)
                    draw_sprite_outline(
                        screen,
                        shield_sprite,
                        body.topleft,
                        (90, 180, 255, a),
                        width=3,
                    )
            elif kind == "player":
                p, cx, cy = data["p"], data["cx"], data["cy"]
                player_size = int(CELL_SIZE * 0.6)
                paint_intensity = 0.0
                if hasattr(game_state, "paint_intensity_at_world"):
                    paint_intensity = game_state.paint_intensity_at_world(p.rect.centerx, p.rect.centery, owner=2)
                if paint_intensity > 0.0:
                    aura_r = max(10, int(player_size * 0.6)) * (0.85 + 0.3 * paint_intensity)
                    aura_alpha = int(110 * paint_intensity)
                    if aura_alpha > 0:
                        draw_iso_ground_ellipse(
                            screen,
                            p.rect.centerx,
                            p.rect.centery,
                            aura_r,
                            (12, 40, 20),
                            aura_alpha,
                            camx,
                            camy,
                            fill=True,
                        )
                sh_w = max(8, int(player_size * 0.9))
                sh_h = max(4, int(player_size * 0.45))
                sh = pygame.Surface((sh_w, sh_h), pygame.SRCALPHA)
                pygame.draw.ellipse(sh, (0, 0, 0, ISO_SHADOW_ALPHA), sh.get_rect())
                screen.blit(sh, sh.get_rect(center=(cx, cy + 6)))
                rect = pygame.Rect(0, 0, player_size, player_size)
                rect.midbottom = (cx, cy)
                sprite_w = int(player_size * 2.0 * PLAYER_SPRITE_SCALE)
                sprite_h = int(player_size * 2.4 * PLAYER_SPRITE_SCALE)
                player_sprite = _load_shop_sprite(
                    "characters/player/sheets/player.png",
                    (sprite_w, sprite_h),
                    allow_upscale=True,
                )
                sprite_rect = rect
                hit_blink = (p.hit_cd > 0 and (pygame.time.get_ticks() // 80) % 2 == 0)
                if player_sprite:
                    sprite_rect = player_sprite.get_rect(midbottom=rect.midbottom)
                    screen.blit(player_sprite, sprite_rect)
                    if hit_blink:
                        blit_sprite_tint(screen, player_sprite, sprite_rect.topleft, (240, 80, 80, 120))
                else:
                    col = (240, 80, 80) if hit_blink else (0, 255, 0)
                    pygame.draw.rect(screen, col, rect)
                flash_t = float(getattr(p, "_hit_flash", 0.0))
                if flash_t > 0.0 and HIT_FLASH_DURATION > 0:
                    flash_ratio = min(1.0, flash_t / HIT_FLASH_DURATION)
                    if player_sprite:
                        blit_sprite_tint(
                            screen,
                            player_sprite,
                            sprite_rect.topleft,
                            (255, 255, 255, int(200 * flash_ratio)),
                        )
                    else:
                        overlay = pygame.Surface(sprite_rect.size, pygame.SRCALPHA)
                        overlay.fill((255, 255, 255, int(200 * flash_ratio)))
                        screen.blit(overlay, sprite_rect.topleft)
                carapace_hp = int(getattr(p, "carapace_hp", 0))
                total_shield = int(getattr(p, "shield_hp", 0)) + carapace_hp
                if total_shield > 0 and player_sprite:
                    t = pygame.time.get_ticks() * 0.006
                    a = 120 + int(80 * (0.5 + 0.5 * math.sin(t)))
                    draw_sprite_outline(
                        screen,
                        player_sprite,
                        sprite_rect.topleft,
                        (90, 180, 255, a),
                        width=3,
                    )
                if carapace_hp > 0:
                    glow_rect = rect.inflate(18, 18)
                    glow = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
                    alpha = min(200, 80 + carapace_hp * 3 // 2)
                    pygame.draw.ellipse(glow, (70, 200, 255, max(60, alpha - 40)), glow.get_rect(), width=4)
                    fill_alpha = max(30, alpha - 100)
                    pygame.draw.ellipse(glow, (40, 140, 255, fill_alpha), glow.get_rect())
                    screen.blit(glow, glow_rect)
                plating_hp = int(getattr(p, "bone_plating_hp", 0))
                if plating_hp > 0:
                    armor_rect = rect.inflate(16, 10)
                    armor = pygame.Surface(armor_rect.size, pygame.SRCALPHA)
                    glow_ratio = max(0.43, min(1.0, float(getattr(p, "_bone_plating_glow", 0.0))))
                    edge_alpha = min(220, 80 + plating_hp // 2)
                    inner_alpha = int((BONE_PLATING_GLOW[3] if len(BONE_PLATING_GLOW) > 3 else 140) * glow_ratio)
                    pygame.draw.rect(
                        armor,
                        (BONE_PLATING_COLOR[0], BONE_PLATING_COLOR[1], BONE_PLATING_COLOR[2], edge_alpha),
                        armor.get_rect(),
                        width=2,
                        border_radius=10
                    )
                    pygame.draw.rect(
                        armor,
                        (BONE_PLATING_GLOW[0], BONE_PLATING_GLOW[1], BONE_PLATING_GLOW[2], inner_alpha),
                        armor.get_rect(),
                        border_radius=10
                    )
                    screen.blit(armor, armor_rect)
                    if int(getattr(p, "bone_plating_level", 0)) >= BONE_PLATING_MAX_LEVEL:
                        cx, cy = rect.centerx, rect.top - 6
                        sparkle = [
                            (cx, cy - 3),
                            (cx + 3, cy),
                            (cx, cy + 3),
                            (cx - 3, cy)
                        ]
                        pygame.draw.polygon(screen, BONE_PLATING_COLOR, sparkle, width=1)
        if _web_feature_enabled("WEB_ENABLE_DAMAGE_TEXTS"):
            for d in getattr(game_state, "dmg_texts", []):
                wx = d.x / CELL_SIZE
                wy = (d.y - INFO_BAR_HEIGHT) / CELL_SIZE
                sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
                sy += d.screen_offset_y()
                color_map = {
                    "shield": ((120, 200, 255), (120, 200, 255)),
                    "aegis": (AEGIS_PULSE_COLOR, AEGIS_PULSE_COLOR),
                    "hp_player": ((255, 255, 255), (255, 255, 220)),
                    "dot": ((80, 220, 255), (140, 255, 255)),
                    "hp_enemy": ((255, 60, 60), (255, 140, 140)),
                }
                normal, crit = color_map.get(d.kind, ((255, 100, 100), (255, 240, 120)))
                col = crit if d.crit else normal
                if d.kind == "dot":
                    size = max(14, DMG_TEXT_SIZE_NORMAL - 6)
                else:
                    size = DMG_TEXT_SIZE_NORMAL if not d.crit else DMG_TEXT_SIZE_CRIT
                font = pygame.font.SysFont(None, size, bold=d.crit)
                surf = font.render(str(d.amount), True, col)
                surf.set_alpha(d.alpha())
                screen.blit(surf, surf.get_rect(center=(int(sx), int(sy))))
        _draw_skill_overlay(screen, player, camx, camy)
        game_state.draw_hazards_iso(screen, camx, camy)
        if hasattr(game_state, "draw_comet_blasts"):
            game_state.draw_comet_blasts(screen, camx, camy)
        if hasattr(game_state, "draw_comet_corpses"):
            game_state.draw_comet_corpses(screen, camx, camy)
        if (not IS_WEB) and getattr(game_state, "fog_enabled", False):
            game_state.draw_fog_overlay(screen, camx, camy, player, obstacles)
        if (not IS_WEB) and USE_ISO:
            game_state.draw_lanterns_iso(screen, camx, camy)
        elif (not IS_WEB):
            game_state.draw_lanterns_topdown(screen, camx, camy)
        if (not IS_WEB) and hasattr(game_state, "fx"):
            for p in game_state.fx.particles:
                if p.size < 1:
                    continue
                gx = p.x / CELL_SIZE
                gy = (p.y - INFO_BAR_HEIGHT) / CELL_SIZE
                sx, sy = iso_world_to_screen(gx, gy, 0, camx, camy)
                glow = GlowCache.get_glow_surf(p.size, p.color)
                screen.blit(glow, (sx - p.size, sy - p.size), special_flags=pygame.BLEND_ADD)
        vignette_t = float(getattr(player, "_enemy_paint_vignette_t", 0.0))
        if (not IS_WEB) and vignette_t > 0.0:
            ratio = max(0.0, min(1.0, vignette_t / 0.18))
            alpha = int(80 * ratio)
            if alpha > 0:
                w, h = screen.get_size()
                edge = int(16 + 14 * ratio)
                overlay = pygame.Surface((w, h), pygame.SRCALPHA)
                overlay.fill((10, 30, 18, int(22 * ratio)))
                pygame.draw.rect(overlay, (10, 40, 20, alpha), pygame.Rect(0, 0, w, edge))
                pygame.draw.rect(overlay, (10, 40, 20, alpha), pygame.Rect(0, h - edge, w, edge))
                pygame.draw.rect(overlay, (10, 40, 20, alpha), pygame.Rect(0, 0, edge, h))
                pygame.draw.rect(overlay, (10, 40, 20, alpha), pygame.Rect(w - edge, 0, edge, h))
                screen.blit(overlay, (0, 0))
        draw_ui_topbar(
            screen,
            game_state,
            player,
            time_left=_runtime().get("_time_left_runtime"),
            enemies=enemies,
        )
        bosses = _find_all_bosses(enemies)
        if len(bosses) >= 2:
            draw_boss_hp_bars_twin(screen, bosses[:2])
        elif len(bosses) == 1:
            draw_boss_hp_bar(screen, bosses[0])
        run_pending_menu_transition(screen)
        pygame.display.flip()
        return screen.copy() if copy_frame else None

    def render_game(screen: pygame.Surface, game_state, player: Player, enemies: List[Enemy],
                    bullets: Optional[List['Bullet']] = None,
                    enemy_shots: Optional[List[EnemyShot]] = None,
                    override_cam: tuple[int, int] | None = None,
                    copy_frame: bool = True) -> pygame.Surface | None:
        """
        Legacy top-down renderer.
        We now use the isometric renderer for everything, but keep this wrapper
        so old call sites (fail screen, etc.) still work without errors.
        """
        if bullets is None:
            bullets = []
        if enemy_shots is None:
            enemy_shots = []
        return render_game_iso(
            screen, game_state, player, enemies, bullets, enemy_shots,
            obstacles=game_state.obstacles,
            override_cam=override_cam,
            copy_frame=copy_frame,
        )

    game.__dict__.update({
        "draw_settings_gear": draw_settings_gear,
        "_current_music_pos_ms": _current_music_pos_ms,
        "_music_is_busy": _music_is_busy,
        "_resume_bgm_if_needed": _resume_bgm_if_needed,
        "play_focus_chain_iso": play_focus_chain_iso,
        "play_focus_cinematic_iso": play_focus_cinematic_iso,
        "render_game_iso_web_lite": render_game_iso_web_lite,
        "render_game_iso": render_game_iso,
        "render_game": render_game,
    })
    return (
        draw_settings_gear,
        _current_music_pos_ms,
        _music_is_busy,
        _resume_bgm_if_needed,
        play_focus_chain_iso,
        play_focus_cinematic_iso,
        render_game_iso_web_lite,
        render_game_iso,
        render_game,
    )
