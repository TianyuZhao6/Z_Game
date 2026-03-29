from __future__ import annotations

import asyncio
import sys

import pygame
from zgame.browser import is_web_interaction_event
from zgame import runtime_state as rs


def _state(game):
    return rs.runtime(game)


def _meta(game):
    return rs.meta(game)


def _viz(game):
    return game._get_neuro_viz()


async def run_neuro_intro(game, screen: pygame.Surface):
    """Show one-time minimal intro (background + link prompt)."""
    clock = pygame.time.Clock()
    title_font = game._get_sekuya_font(64)
    prompt_font = pygame.font.SysFont("Consolas", 24)
    t = 0.0
    while True:
        dt = clock.tick(game.WEB_TARGET_FPS if game.IS_WEB else 60) / 1000.0
        t += dt
        screen.blit(game.ensure_neuro_background(), (0, 0))
        game._draw_intro_starfield(screen, t)
        game._draw_intro_datastreams(screen, t)
        game.draw_intro_waves(screen, t)
        game._draw_intro_holo_core(screen, t)
        game._draw_intro_scanlines(screen, t)
        game.draw_neuro_title_intro(screen, title_font, prompt_font, t)
        pygame.display.flip()
        for event in pygame.event.get():
            screen = game._handle_web_window_event(event) or screen
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                return
            if event.type == pygame.MOUSEBUTTONDOWN:
                return
        if game.IS_WEB:
            await asyncio.sleep(0)


def render_start_menu_surface(game, saved_exists: bool):
    """Static snapshot of the Neuro Console menu (used for transitions)."""
    can_continue = bool(saved_exists and not getattr(game, "WEB_DEMO_DISABLE_CONTINUE", False))
    surf = game.ensure_neuro_background().copy()
    viz = _viz(game)
    wave_t = 0.0
    game.draw_neuro_waves(surf, wave_t)
    header_font = game._get_sekuya_font(26)
    btn_font = pygame.font.SysFont(None, 30)
    info_font = pygame.font.SysFont("Consolas", 18)
    game.draw_neuro_home_header(surf, header_font)
    rects = game.neuro_menu_layout(include_continue=can_continue)
    if getattr(game, "WEB_DEMO", False):
        start_label = "START DEMO"
    else:
        start_label = "START NEW" if can_continue else "START"
    game.draw_neuro_button(surf, rects["start"], start_label, btn_font, hovered=False, disabled=False, t=wave_t)
    if can_continue:
        game.draw_neuro_button(
            surf,
            rects["continue"],
            "CONTINUE",
            btn_font,
            hovered=False,
            disabled=False,
            t=wave_t,
        )
    game.draw_neuro_button(surf, rects["instruction"], "INSTRUCTION", btn_font, hovered=False, disabled=False, t=wave_t)
    game.draw_neuro_button(surf, rects["settings"], "SETTINGS", btn_font, hovered=False, disabled=False, t=wave_t)
    game.draw_neuro_button(surf, rects["exit"], "EXIT", btn_font, hovered=False, disabled=False, t=wave_t)
    viz.draw(surf, surf.get_width() // 2, int(surf.get_height() * 0.52))
    game.draw_neuro_info_column(surf, info_font, wave_t, can_continue)
    return surf


async def show_start_menu(game, screen, *, skip_intro: bool = False):
    """Return ('new', None) or ('continue', save_data) based on the player's choice."""
    state = _state(game)
    viz = _viz(game)
    game.flush_events()
    intro_flag = state.pop("_skip_intro_once", False)
    skip_intro = bool(skip_intro or getattr(game, "WEB_DEMO_SKIP_INTRO", False))
    if not skip_intro and not intro_flag:
        await run_neuro_intro(game, screen)
    try:
        bgm = state.get("_bgm")
        cur = getattr(bgm, "music_path", "") if bgm is not None else ""
        cur_lower = cur.lower()
        if "intro_v0.wav" not in cur_lower and "intro_v0.ogg" not in cur_lower:
            game.play_intro_bgm()
    except Exception:
        try:
            game.play_intro_bgm()
        except Exception:
            pass
    game._resume_bgm_if_needed(min_interval_s=0.0)
    clock = pygame.time.Clock()
    header_font = game._get_sekuya_font(22)
    btn_font = pygame.font.SysFont(None, 30)
    info_font = pygame.font.SysFont("Consolas", 18)
    t = 0.0
    while True:
        dt = clock.tick(game.WEB_TARGET_FPS if game.IS_WEB else 60) / 1000.0
        t += dt

        pos_ms = game._current_music_pos_ms()
        if pos_ms is not None:
            viz.update(dt, pos_ms / 1000.0)
        else:
            viz.update(dt, t)

        saved_exists = game.has_save()
        can_continue = bool(saved_exists and not getattr(game, "WEB_DEMO_DISABLE_CONTINUE", False))
        base_rects = game.neuro_menu_layout(include_continue=can_continue)
        mouse_pos = pygame.mouse.get_pos()
        hover_id = None
        for ident, rect in base_rects.items():
            if ident == "continue" and not saved_exists:
                continue
            if rect.inflate(int(rect.width * 0.08), int(rect.height * 0.08)).collidepoint(mouse_pos):
                hover_id = ident
                break
        screen.blit(game.ensure_neuro_background(), (0, 0))
        game.draw_neuro_waves(screen, t)
        viz.draw(screen, game.VIEW_W // 2, int(game.VIEW_H * 0.52))

        game.draw_neuro_home_header(screen, header_font)
        drawn_rects = {}
        if getattr(game, "WEB_DEMO", False):
            start_label = "START DEMO"
        else:
            start_label = "START NEW" if can_continue else "START"
        drawn_rects["start"] = game.draw_neuro_button(
            screen,
            base_rects["start"],
            start_label,
            btn_font,
            hovered=hover_id == "start",
            disabled=False,
            t=t,
        )
        if can_continue:
            drawn_rects["continue"] = game.draw_neuro_button(
                screen,
                base_rects["continue"],
                "CONTINUE",
                btn_font,
                hovered=hover_id == "continue",
                disabled=False,
                t=t,
            )
        drawn_rects["instruction"] = game.draw_neuro_button(
            screen,
            base_rects["instruction"],
            "INSTRUCTION",
            btn_font,
            hovered=hover_id == "instruction",
            disabled=False,
            t=t,
        )
        drawn_rects["settings"] = game.draw_neuro_button(
            screen,
            base_rects["settings"],
            "SETTINGS",
            btn_font,
            hovered=hover_id == "settings",
            disabled=False,
            t=t,
        )
        drawn_rects["exit"] = game.draw_neuro_button(
            screen,
            base_rects["exit"],
            "EXIT",
            btn_font,
            hovered=hover_id == "exit",
            disabled=False,
            t=t,
        )
        game.draw_neuro_info_column(screen, info_font, t, can_continue)
        game.run_pending_menu_transition(screen)
        pygame.display.flip()
        for event in pygame.event.get():
            screen = game._handle_web_window_event(event) or screen
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if event.type == pygame.MOUSEBUTTONDOWN:
                if drawn_rects["start"].collidepoint(event.pos):
                    if game.IS_WEB:
                        try:
                            game.play_combat_bgm()
                            game._resume_bgm_if_needed(min_interval_s=0.0)
                        except Exception:
                            pass
                    game.clear_save()
                    game.reset_run_state()
                    game.queue_menu_transition(screen.copy())
                    game.flush_events()
                    return ("new", None)
                cont_rect = drawn_rects.get("continue")
                if cont_rect and can_continue and cont_rect.collidepoint(event.pos):
                    data = game.load_save()
                    if data:
                        if game.IS_WEB:
                            try:
                                game.play_combat_bgm()
                                game._resume_bgm_if_needed(min_interval_s=0.0)
                            except Exception:
                                pass
                        game.queue_menu_transition(screen.copy())
                        game.flush_events()
                        return ("continue", data)
                if drawn_rects["instruction"].collidepoint(event.pos):
                    from_surf = screen.copy()
                    instr_surf = game.render_instruction_surface()
                    game.play_hex_transition(screen, from_surf, instr_surf, direction="down")
                    game.flush_events()
                    if game.IS_WEB:
                        await show_instruction_web(game, screen)
                    else:
                        show_instruction(game, screen)
                    game.flush_events()
                if drawn_rects["settings"].collidepoint(event.pos):
                    if game.IS_WEB:
                        await game.show_settings_popup_web(screen, screen.copy())
                    else:
                        game.show_settings_popup(screen, screen.copy())
                    game.flush_events()
                if drawn_rects["exit"].collidepoint(event.pos):
                    pygame.quit()
                    sys.exit()
        if game.IS_WEB:
            await asyncio.sleep(0)


def show_instruction(game, screen):
    clock = pygame.time.Clock()
    body_font = pygame.font.SysFont("Consolas", 20)
    title_font = pygame.font.SysFont("Consolas", 34, bold=True)
    btn_font = pygame.font.SysFont(None, 30)
    t = 0.0
    while True:
        dt = clock.tick(60) / 1000.0
        t += dt
        _, back_rect = game.neuro_instruction_layout()
        hover_back = back_rect.inflate(int(back_rect.width * 0.08), int(back_rect.height * 0.08)).collidepoint(
            pygame.mouse.get_pos()
        )
        screen.blit(game.ensure_neuro_background(), (0, 0))
        back = game.draw_neuro_instruction(
            screen,
            t,
            hover_back=hover_back,
            title_font=title_font,
            body_font=body_font,
            btn_font=btn_font,
        )
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.IS_WEB and is_web_interaction_event(event):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                from_surf = screen.copy()
                to_surf = render_start_menu_surface(game, game.has_save())
                game.play_hex_transition(screen, from_surf, to_surf, direction="up")
                return
            if event.type == pygame.MOUSEBUTTONDOWN and back.collidepoint(event.pos):
                from_surf = screen.copy()
                to_surf = render_start_menu_surface(game, game.has_save())
                game.play_hex_transition(screen, from_surf, to_surf, direction="up")
                return


async def show_instruction_web(game, screen):
    clock = pygame.time.Clock()
    body_font = pygame.font.SysFont("Consolas", 18)
    title_font = pygame.font.SysFont("Consolas", 30, bold=True)
    btn_font = pygame.font.SysFont(None, 28)
    t = 0.0
    while True:
        dt = clock.tick(game.WEB_TARGET_FPS) / 1000.0
        t += dt
        _, back_rect = game.neuro_instruction_layout()
        hover_back = back_rect.inflate(int(back_rect.width * 0.08), int(back_rect.height * 0.08)).collidepoint(
            pygame.mouse.get_pos()
        )
        screen.blit(game.ensure_neuro_background(), (0, 0))
        back = game.draw_neuro_instruction(
            screen,
            t,
            hover_back=hover_back,
            title_font=title_font,
            body_font=body_font,
            btn_font=btn_font,
        )
        pygame.display.flip()
        for event in pygame.event.get():
            screen = game._handle_web_window_event(event) or screen
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.IS_WEB and is_web_interaction_event(event):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                from_surf = screen.copy()
                to_surf = render_start_menu_surface(game, game.has_save())
                game.play_hex_transition(screen, from_surf, to_surf, direction="up")
                return
            if event.type == pygame.MOUSEBUTTONDOWN and back.collidepoint(event.pos):
                from_surf = screen.copy()
                to_surf = render_start_menu_surface(game, game.has_save())
                game.play_hex_transition(screen, from_surf, to_surf, direction="up")
                return
        await asyncio.sleep(0)


def show_pause_menu(game, screen, background_surf):
    """Draw pause overlay with build info in the dimmed background, keeping buttons centered."""
    state = _state(game)
    meta = _meta(game)
    dim = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
    dim.fill((4, 6, 10, 180))
    bg_scaled = pygame.transform.smoothscale(background_surf, (game.VIEW_W, game.VIEW_H))
    screen.blit(bg_scaled, (0, 0))
    screen.blit(dim, (0, 0))
    font_small = pygame.font.SysFont(None, 28)
    font_tiny = pygame.font.SysFont(None, 22)
    desc_font = pygame.font.SysFont(None, 24)
    left_margin = 30
    top_margin = 30
    y_offset = top_margin
    title = font_small.render("Player Stats", True, game.UI_TEXT)
    screen.blit(title, (left_margin, y_offset))
    y_offset += 40
    p = state.get("_pause_player_ref", None)
    base_dmg = int(meta.get("base_dmg", game.BULLET_DAMAGE_ENEMY))
    base_cd = float(meta.get("base_fire_cd", game.FIRE_COOLDOWN))
    base_range = game.clamp_player_range(meta.get("base_range", game.PLAYER_RANGE_DEFAULT))
    base_speed = float(meta.get("base_speed", game.PLAYER_SPEED))
    base_hp = int(meta.get("base_maxhp", game.PLAYER_MAX_HP))
    base_crit = float(meta.get("base_crit", game.CRIT_CHANCE_BASE))
    cur_dmg = int(getattr(p, "bullet_damage", base_dmg + meta.get("dmg", 0)))
    bonus_dmg = max(0, cur_dmg - base_dmg)
    dmg_text = font_tiny.render(
        f"Damage: {cur_dmg}  (Lv1 {base_dmg}, +{bonus_dmg} bonus)",
        True,
        (230, 100, 100),
    )
    screen.blit(dmg_text, (left_margin, y_offset))
    y_offset += 30
    if p:
        cur_cd = p.fire_cooldown()
    else:
        cur_cd = max(game.MIN_FIRE_COOLDOWN, base_cd / max(1.0, float(meta.get("firerate_mult", 1.0))))
    cur_sps = 1.0 / cur_cd
    base_sps = 1.0 / max(game.MIN_FIRE_COOLDOWN, base_cd)
    fr_mult = float(meta.get("firerate_mult", 1.0))
    fr_text = font_tiny.render(
        f"Fire Rate: {fr_mult:.2f}x  ({cur_sps:.2f}/s, Lv1 {base_sps:.2f}/s)",
        True,
        (100, 200, 100),
    )
    screen.blit(fr_text, (left_margin, y_offset))
    y_offset += 30
    rng_mult = float(meta.get("range_mult", 1.0))
    cur_range = game.clamp_player_range(getattr(p, "range", game.compute_player_range(base_range, rng_mult)))
    eff_rng_mult = cur_range / base_range if base_range else rng_mult
    rng_text = font_tiny.render(
        f"Range: {eff_rng_mult:.2f}x  ({int(cur_range)} px, Lv1 {int(base_range)} px)",
        True,
        (200, 200, 100),
    )
    screen.blit(rng_text, (left_margin, y_offset))
    y_offset += 30
    spd_mult = float(meta.get("speed_mult", 1.0))
    cur_speed = float(base_speed * spd_mult)
    bonus_speed = cur_speed - base_speed
    spd_text = font_tiny.render(
        f"Speed: {cur_speed:.1f}  (Lv1 {base_speed:.1f}, {bonus_speed:+.1f} levelup)",
        True,
        (100, 100, 230),
    )
    screen.blit(spd_text, (left_margin, y_offset))
    y_offset += 30
    cur_mhp = int(getattr(p, "max_hp", base_hp + meta.get("maxhp", 0)))
    bonus_hp = max(0, cur_mhp - base_hp)
    hp_text = font_tiny.render(
        f"Max HP: {cur_mhp}  (Lv1 {base_hp}, +{bonus_hp} bonus)",
        True,
        (230, 150, 100),
    )
    screen.blit(hp_text, (left_margin, y_offset))
    y_offset += 30
    cur_crit = float(getattr(p, "crit_chance", base_crit + meta.get("crit", 0.0)))
    bonus_crit = cur_crit - base_crit
    crit_text = font_tiny.render(
        f"Crit Chance: {int(cur_crit * 100)}%  (Lv1 {int(base_crit * 100)}%, +{int(bonus_crit * 100)}%)",
        True,
        (255, 220, 120),
    )
    screen.blit(crit_text, (left_margin, y_offset))
    y_offset += 30
    dps_val = game.compute_player_dps(p)
    dps_text = font_tiny.render(f"DPS: {dps_val:.2f}", True, (230, 230, 230))
    screen.blit(dps_text, (left_margin, y_offset))
    y_offset += 30
    path_title = font_tiny.render("Path Focus:", True, (180, 220, 255))
    screen.blit(path_title, (left_margin, y_offset))
    y_offset += 24
    for line in game.path_focus_summary_lines(meta, max_lines=3):
        line_surf = font_tiny.render(f"- {line}", True, (170, 205, 230))
        screen.blit(line_surf, (left_margin, y_offset))
        y_offset += 22

    right_margin = game.VIEW_W - 30
    y_offset = top_margin
    title = font_small.render("Possessions", True, game.UI_TEXT)
    title_rect = title.get_rect(right=right_margin, top=y_offset)
    screen.blit(title, title_rect)
    y_offset += 40
    pos_font = pygame.font.SysFont(None, 24)
    catalog = state.get("_pause_shop_catalog")
    if catalog is None:
        catalog = [
            {"id": "coin_magnet", "name": "Coin Magnet", "max_level": 5},
            {"id": "auto_turret", "name": "Auto-Turret", "max_level": 5},
            {"id": "stationary_turret", "name": "Stationary Turret", "max_level": 99},
            {"id": "ricochet_scope", "name": "Ricochet Scope", "max_level": 3},
            {"id": "piercing_rounds", "name": "Piercing Rounds", "max_level": 5},
            {"id": "shrapnel_shells", "name": "Shrapnel Shells", "max_level": 3},
            {"id": "explosive_rounds", "name": "Explosive Rounds", "max_level": 3},
            {"id": "dot_rounds", "name": "D.O.T. Rounds", "max_level": 3},
            {"id": "curing_paint", "name": "Curing Paint", "max_level": 3},
            {"id": "ground_spikes", "name": "Ground Spikes", "max_level": 3},
            {"id": "bone_plating", "name": "Bone Plating", "max_level": 5},
            {"id": "carapace", "name": "Carapace", "max_level": None},
            {"id": "aegis_pulse", "name": "Aegis Pulse", "max_level": 5},
            {"id": "bandit_radar", "name": "Bandit Radar", "max_level": 4},
            {"id": "lockbox", "name": "Lockbox", "max_level": game.LOCKBOX_MAX_LEVEL},
            {
                "id": "mark_vulnerability",
                "name": "Mark of Vulnerability",
                "desc": "Every 5/4/3s mark a priority enemy for 5/6/7s; marked take +15/22/30% damage.",
                "cost": 25,
                "rarity": 3,
                "max_level": 3,
                "apply": lambda: meta.update(vuln_mark_level=min(3, int(meta.get("vuln_mark_level", 0)) + 1)),
            },
            {"id": "golden_interest", "name": "Golden Interest", "max_level": game.GOLDEN_INTEREST_MAX_LEVEL},
            {"id": "wanted_poster", "name": "Wanted Poster", "max_level": None},
            {"id": "shady_loan", "name": "Shady Loan", "max_level": game.SHADY_LOAN_MAX_LEVEL},
            {"id": "coupon", "name": "Coupon", "max_level": game.COUPON_MAX_LEVEL},
        ]
        state["_pause_shop_catalog"] = catalog
    if state.get("_shop_catalog_version") != game.SHOP_CATALOG_VERSION:
        for key in (
            "_shop_slot_ids_cache",
            "_shop_slots_cache",
            "_shop_reroll_id_cache",
            "_shop_reroll_cache",
            "_resume_shop_cache",
        ):
            state.pop(key, None)
        state["_shop_catalog_version"] = game.SHOP_CATALOG_VERSION

    def _pause_prop_level(item):
        return game.prop_level_from_meta(item.get("id"), meta)

    owned = []
    for item in catalog:
        lvl = _pause_prop_level(item)
        max_lvl = item.get("max_level")
        if lvl and lvl > 0:
            owned.append({"itm": item, "lvl": lvl, "max": max_lvl})
    owned_rows = []
    if owned:
        line_h = max(22, pos_font.get_height())
        for ent in owned:
            name = ent["itm"]["name"]
            lvl = ent["lvl"]
            max_lvl = ent["max"]
            lvl_str = f"{lvl}/{max_lvl}" if max_lvl else f"x{lvl}"
            text = f"{name}: {lvl_str}"
            surf = pos_font.render(text, True, game.UI_TEXT)
            rect = surf.get_rect(right=right_margin, top=y_offset)
            screen.blit(surf, rect)
            owned_rows.append((rect, ent))
            y_offset += line_h

    pause_bg = screen.copy()
    panel_w, panel_h = min(520, game.VIEW_W - 80), min(500, game.VIEW_H - 160)
    panel = pygame.Rect(0, 0, panel_w, panel_h)
    panel.center = (game.VIEW_W // 2, game.VIEW_H // 2)
    title_surf = pygame.font.SysFont(None, 72).render("Paused", True, game.UI_TEXT)
    btn_w, btn_h = 300, 56
    spacing = 14
    start_y = panel.top + 110
    labels = [
        ("CONTINUE", "continue"),
        ("RESTART", "restart"),
        ("SETTINGS", "settings"),
        ("BACK TO HOMEPAGE", "home"),
        ("EXIT GAME (Save & Quit)", "exit"),
    ]
    btns = [
        (pygame.Rect(panel.centerx - btn_w // 2, start_y + i * (btn_h + spacing), btn_w, btn_h), tag, label)
        for i, (label, tag) in enumerate(labels)
    ]

    def redraw(hover_tag: str | None):
        pygame.draw.rect(screen, game.UI_PANEL, panel, border_radius=16)
        pygame.draw.rect(screen, game.UI_BORDER, panel, width=3, border_radius=16)
        screen.blit(title_surf, title_surf.get_rect(center=(panel.centerx, panel.top + 58)))
        for rect, tag, label in btns:
            hover = tag == hover_tag
            fill = None
            border = None
            if tag == "exit":
                fill = (200, 50, 50)
                border = (255, 120, 120)
            game.draw_neuro_button(
                screen,
                rect,
                label,
                pygame.font.SysFont(None, 32),
                hovered=hover,
                disabled=False,
                t=pygame.time.get_ticks() * 0.001,
                fill_col=fill,
                border_col=border,
                show_spike=False,
            )

    pygame.display.flip()
    while True:
        mx, my = pygame.mouse.get_pos()
        hover_tag = None
        for rect, tag, _ in btns:
            if rect.collidepoint((mx, my)):
                hover_tag = tag
                break
        screen.blit(pause_bg, (0, 0))
        redraw(hover_tag)
        tooltip_txt = None
        tooltip_pos = None
        if owned_rows:
            for row_rect, ent in owned_rows:
                if row_rect.collidepoint((mx, my)):
                    tooltip_txt = game.detailed_prop_tooltip_text(ent["itm"], ent["lvl"], meta)
                    tooltip_pos = (row_rect.right + 10, row_rect.centery)
                    break
        if tooltip_txt:
            tip_surf = desc_font.render(tooltip_txt, True, (235, 235, 235))
            pad = 8
            bg = pygame.Surface((tip_surf.get_width() + pad * 2, tip_surf.get_height() + pad * 2), pygame.SRCALPHA)
            pygame.draw.rect(bg, (30, 30, 36, 230), bg.get_rect(), border_radius=10)
            pygame.draw.rect(bg, (120, 150, 210, 240), bg.get_rect(), 2, border_radius=10)
            bg.blit(tip_surf, (pad, pad))
            bx = min(game.VIEW_W - bg.get_width() - 10, tooltip_pos[0])
            by = max(60, min(game.VIEW_H - bg.get_height() - 60, tooltip_pos[1] - bg.get_height() // 2))
            screen.blit(bg, (bx, by))
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.IS_WEB and is_web_interaction_event(event):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                game.flush_events()
                return "continue"
            if event.type == pygame.MOUSEBUTTONDOWN:
                for rect, tag, _ in btns:
                    if rect.collidepoint(event.pos):
                        game.flush_events()
                        return tag
