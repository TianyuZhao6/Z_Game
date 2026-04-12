from __future__ import annotations

import asyncio
import sys

import pygame
from zgame.browser import is_escape_event, is_web_interaction_event
from zgame import runtime_state as rs


def _sync_bgm_volume(game, bgm_value: int) -> None:
    bgm = rs.runtime(game).get("_bgm")
    if bgm is not None and getattr(bgm, "set_volume", None):
        bgm.set_volume(float(bgm_value) / 100.0)


def _browser_runtime_summary(game) -> str:
    if not getattr(game, "IS_WEB", False):
        return ""
    try:
        stats = game.web_storage_stats()
    except Exception:
        stats = {}
    backend = str(stats.get("backend", "localStorage") or "localStorage")
    used_kb = float(stats.get("used_bytes", 0) or 0) / 1024.0
    save_label = "save ready" if bool(stats.get("has_save", False)) else "save empty"
    quality = str(getattr(game, "_web_quality_profile", getattr(game, "WEB_DEFAULT_QUALITY", "full")) or "full").upper()
    return f"Chrome {backend}: {used_kb:.1f} KB, {save_label}, quality {quality}"


async def show_settings_popup_web(game, screen, background_surf):
    clock = pygame.time.Clock()
    dim = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 170))
    bg_scaled = pygame.transform.smoothscale(background_surf, (game.VIEW_W, game.VIEW_H))
    panel_w, panel_h = min(520, game.VIEW_W - 80), min(520, game.VIEW_H - 160)
    panel = pygame.Rect(0, 0, panel_w, panel_h)
    panel.center = (game.VIEW_W // 2, game.VIEW_H // 2)
    title_font = pygame.font.SysFont(None, 56)
    font = pygame.font.SysFont(None, 26)
    btn_font = pygame.font.SysFont(None, 32)
    status_font = pygame.font.SysFont("Consolas", 18)
    fx_val = int(game.FX_VOLUME)
    bgm_val = int(game.BGM_VOLUME)
    dragging = None
    page = "root"
    waiting_action = None
    status_msg = ""
    status_color = (170, 210, 230)
    ctrl_buttons: list[tuple[pygame.Rect, str]] = []
    runtime_summary = _browser_runtime_summary(game)

    control_actions = [
        ("Move Up", "move_up"),
        ("Move Left", "move_left"),
        ("Move Down", "move_down"),
        ("Move Right", "move_right"),
        ("Blast", "blast"),
        ("Teleport", "teleport"),
    ]

    def draw_slider(label, value, top_y):
        screen.blit(font.render(f"{label}: {value}", True, game.UI_TEXT), (panel.left + 40, top_y))
        bar = pygame.Rect(panel.left + 40, top_y + 24, panel_w - 80, 10)
        knob_x = bar.x + int((value / 100) * bar.width)
        pygame.draw.rect(screen, (60, 70, 90), bar, border_radius=6)
        pygame.draw.circle(screen, game.UI_ACCENT, (knob_x, bar.y + 5), 8)
        return bar

    def val_from_bar(bar, mx):
        return max(0, min(100, int(((mx - bar.x) / max(1, bar.width)) * 100)))

    def draw_root():
        screen.blit(bg_scaled, (0, 0))
        screen.blit(dim, (0, 0))
        pygame.draw.rect(screen, game.UI_PANEL, panel, border_radius=16)
        pygame.draw.rect(screen, game.UI_BORDER, panel, width=3, border_radius=16)
        title = title_font.render("Settings", True, game.UI_TEXT)
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 60)))
        btn_w, btn_h = 220, 56
        audio_btn = pygame.Rect(0, 0, btn_w, btn_h)
        ctrl_btn = pygame.Rect(0, 0, btn_w, btn_h)
        export_btn = pygame.Rect(0, 0, btn_w, btn_h)
        close_btn = pygame.Rect(0, 0, btn_w, btn_h)
        audio_btn.center = (panel.centerx, panel.top + 160)
        ctrl_btn.center = (panel.centerx, panel.top + 230)
        export_btn.center = (panel.centerx, panel.top + 300)
        close_btn.center = (panel.centerx, panel.bottom - 60)
        mouse_pos = pygame.mouse.get_pos()
        game.draw_neuro_button(screen, audio_btn, "Audio", btn_font, hovered=audio_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        game.draw_neuro_button(screen, ctrl_btn, "Controls", btn_font, hovered=ctrl_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        game.draw_neuro_button(screen, export_btn, "Export Save", btn_font, hovered=export_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        game.draw_neuro_button(screen, close_btn, "Close", btn_font, hovered=close_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        if runtime_summary:
            summary = status_font.render(runtime_summary[:68], True, (140, 195, 220))
            screen.blit(summary, summary.get_rect(center=(panel.centerx, panel.bottom - 136)))
        if status_msg:
            status = status_font.render(status_msg[:64], True, status_color)
            screen.blit(status, status.get_rect(center=(panel.centerx, panel.bottom - 110)))
        pygame.display.flip()
        return audio_btn, ctrl_btn, export_btn, close_btn

    def draw_audio():
        screen.blit(bg_scaled, (0, 0))
        screen.blit(dim, (0, 0))
        pygame.draw.rect(screen, game.UI_PANEL, panel, border_radius=16)
        pygame.draw.rect(screen, game.UI_BORDER, panel, width=3, border_radius=16)
        title = title_font.render("Audio", True, game.UI_TEXT)
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 60)))
        nonlocal fx_bar, bgm_bar
        fx_bar = draw_slider("Effects Volume", fx_val, panel.top + 120)
        bgm_bar = draw_slider("BGM Volume", bgm_val, panel.top + 180)
        btn_w, btn_h = 180, 52
        back_btn = pygame.Rect(0, 0, btn_w, btn_h)
        close_btn = pygame.Rect(0, 0, btn_w, btn_h)
        back_btn.center = (panel.centerx - 100, panel.bottom - 60)
        close_btn.center = (panel.centerx + 100, panel.bottom - 60)
        mouse_pos = pygame.mouse.get_pos()
        game.draw_neuro_button(screen, back_btn, "Back", btn_font, hovered=back_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        game.draw_neuro_button(screen, close_btn, "Save", btn_font, hovered=close_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        pygame.display.flip()
        return back_btn, close_btn

    def draw_controls():
        screen.blit(bg_scaled, (0, 0))
        screen.blit(dim, (0, 0))
        pygame.draw.rect(screen, game.UI_PANEL, panel, border_radius=16)
        pygame.draw.rect(screen, game.UI_BORDER, panel, width=3, border_radius=16)
        title = title_font.render("Controls", True, game.UI_TEXT)
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 52)))
        hint = font.render("Click an action, then press a key to rebind.", True, game.UI_TEXT)
        screen.blit(hint, hint.get_rect(center=(panel.centerx, panel.top + 92)))
        ctrl_buttons.clear()
        start_y = panel.top + 130
        row_h = 46
        btn_w, btn_h = 180, 34
        mouse_pos = pygame.mouse.get_pos()
        for idx, (label, action) in enumerate(control_actions):
            y = start_y + idx * row_h
            screen.blit(font.render(label, True, game.UI_TEXT), (panel.left + 36, y))
            btn = pygame.Rect(0, 0, btn_w, btn_h)
            btn.center = (panel.centerx + 80, y + btn_h // 2)
            ctrl_buttons.append((btn, action))
            text = "Press a key..." if waiting_action == action else game.binding_name(action)
            game.draw_neuro_button(screen, btn, text, font, hovered=btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        back_btn = pygame.Rect(0, 0, 160, 48)
        close_btn = pygame.Rect(0, 0, 160, 48)
        back_btn.center = (panel.centerx - 90, panel.bottom - 60)
        close_btn.center = (panel.centerx + 90, panel.bottom - 60)
        game.draw_neuro_button(screen, back_btn, "Back", btn_font, hovered=back_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        game.draw_neuro_button(screen, close_btn, "Save", btn_font, hovered=close_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        pygame.display.flip()
        return back_btn, close_btn

    fx_bar = bgm_bar = None
    audio_btn = ctrl_btn = export_btn = close_btn = None
    while True:
        if page == "root":
            audio_btn, ctrl_btn, export_btn, close_btn = draw_root()
        elif page == "audio":
            back_btn, close_btn = draw_audio()
        elif page == "controls":
            back_btn, close_btn = draw_controls()
        else:
            page = "root"
            continue

        for event in pygame.event.get():
            screen = game._handle_web_window_event(event) or screen
            game._sync_web_input_event(event)
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.IS_WEB and is_web_interaction_event(event):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if is_escape_event(event) and waiting_action:
                waiting_action = None
                continue
            if is_escape_event(event):
                game.FX_VOLUME = fx_val
                game.BGM_VOLUME = bgm_val
                _sync_bgm_volume(game, bgm_val)
                game.flush_events()
                return "close"

            if page == "root":
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    if audio_btn and audio_btn.collidepoint((mx, my)):
                        page = "audio"
                        dragging = None
                    elif ctrl_btn and ctrl_btn.collidepoint((mx, my)):
                        page = "controls"
                        waiting_action = None
                    elif export_btn and export_btn.collidepoint((mx, my)):
                        ok, msg = game.export_current_save()
                        status_msg = msg
                        status_color = (120, 230, 160) if ok else (255, 150, 150)
                        runtime_summary = _browser_runtime_summary(game)
                    elif close_btn and close_btn.collidepoint((mx, my)):
                        game.FX_VOLUME = fx_val
                        game.BGM_VOLUME = bgm_val
                        _sync_bgm_volume(game, bgm_val)
                        game.flush_events()
                        return "close"

            elif page == "audio":
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    if fx_bar and fx_bar.collidepoint((mx, my)):
                        fx_val = val_from_bar(fx_bar, mx)
                        game.FX_VOLUME = fx_val
                        dragging = "fx"
                    elif bgm_bar and bgm_bar.collidepoint((mx, my)):
                        bgm_val = val_from_bar(bgm_bar, mx)
                        game.BGM_VOLUME = bgm_val
                        _sync_bgm_volume(game, bgm_val)
                        dragging = "bgm"
                    elif back_btn and back_btn.collidepoint((mx, my)):
                        page = "root"
                        dragging = None
                    elif close_btn and close_btn.collidepoint((mx, my)):
                        game.FX_VOLUME = fx_val
                        game.BGM_VOLUME = bgm_val
                        _sync_bgm_volume(game, bgm_val)
                        game.flush_events()
                        return "close"
                if event.type == pygame.MOUSEBUTTONUP:
                    dragging = None
                if event.type == pygame.MOUSEMOTION and dragging:
                    mx, my = event.pos
                    if dragging == "fx" and fx_bar:
                        fx_val = val_from_bar(fx_bar, mx)
                        game.FX_VOLUME = fx_val
                    elif dragging == "bgm" and bgm_bar:
                        bgm_val = val_from_bar(bgm_bar, mx)
                        game.BGM_VOLUME = bgm_val
                        _sync_bgm_volume(game, bgm_val)

            elif page == "controls":
                if waiting_action and event.type == pygame.KEYDOWN:
                    if is_escape_event(event):
                        waiting_action = None
                    else:
                        game.set_binding(waiting_action, event.key)
                        waiting_action = None
                    continue
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    clicked_any = False
                    for rect, action in ctrl_buttons:
                        if rect.collidepoint((mx, my)):
                            waiting_action = action
                            clicked_any = True
                            break
                    if clicked_any:
                        continue
                    if back_btn and back_btn.collidepoint((mx, my)):
                        waiting_action = None
                        page = "root"
                    elif close_btn and close_btn.collidepoint((mx, my)):
                        game.FX_VOLUME = fx_val
                        game.BGM_VOLUME = bgm_val
                        _sync_bgm_volume(game, bgm_val)
                        game.flush_events()
                        return "close"

        clock.tick(60)
        await asyncio.sleep(0)


async def show_levelup_overlay_web(game, screen, background_surf, player):
    import random

    clock = pygame.time.Clock()
    pool = [
        {"key": "dmg", "title": "+1 Damage", "desc": "Increase your bullet damage by 1."},
        {"key": "firerate", "title": "+5% Fire Rate", "desc": "Shoot slightly faster (multiplicative)."},
        {"key": "range", "title": "+10% Range", "desc": "Longer effective range for shots."},
        {"key": "speed", "title": "+5% Speed", "desc": "Move faster."},
        {"key": "maxhp", "title": "+5 Max HP", "desc": "Increase max HP and heal 10."},
        {"key": "crit", "title": "+2% Crit", "desc": "Increase critical hit chance slightly"},
    ]
    speed_cap = getattr(game, "PLAYER_SPEED_CAP", None)
    if speed_cap is not None and player is not None:
        try:
            cur_spd = float(getattr(player, "speed", 0.0))
            if cur_spd >= float(speed_cap) - 1e-6:
                pool = [p for p in pool if p.get("key") != "speed"]
        except Exception:
            pass
    if player is not None:
        try:
            cur_crit = float(getattr(player, "crit_chance", 0.0))
            if cur_crit >= 0.75 - 1e-6:
                pool = [p for p in pool if p.get("key") != "crit"]
        except Exception:
            pass
    if not pool:
        pool = [
            {"key": "dmg", "title": "+1 Damage", "desc": "Increase your bullet damage by 1."},
            {"key": "maxhp", "title": "+5 Max HP", "desc": "Increase max HP and heal 10."},
            {"key": "firerate", "title": "+5% Fire Rate", "desc": "Shoot slightly faster (multiplicative)."},
            {"key": "range", "title": "+10% Range", "desc": "Longer effective range for shots."},
        ]
    cards = random.sample(pool, k=min(4, len(pool)))
    title_font = pygame.font.SysFont(None, 64)
    head_font = pygame.font.SysFont(None, 30)
    body_font = pygame.font.SysFont(None, 24)
    hover = -1

    def _layout():
        w, h = screen.get_size()
        card_w, card_h = 420, 140
        gap_x, gap_y = 32, 28
        total_w = 2 * card_w + gap_x
        total_h = 2 * card_h + gap_y
        base_x = (w - total_w) // 2
        base_y = (h - total_h) // 2 + 10
        rects = []
        for i in range(len(cards)):
            cx = base_x + (i % 2) * (card_w + gap_x)
            cy = base_y + (i // 2) * (card_h + gap_y)
            rects.append(pygame.Rect(cx, cy, card_w, card_h))
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 140))
        title = title_font.render("LEVEL UP - CHOOSE ONE", True, (235, 235, 235))
        title_rect = title.get_rect(center=(w // 2, base_y - 48))
        return rects, dim, title, title_rect

    while True:
        rects, dim, title, title_rect = _layout()
        mx, my = pygame.mouse.get_pos()
        hover = -1
        for i, rect in enumerate(rects):
            if rect.collidepoint(mx, my):
                hover = i
                break
        screen.blit(background_surf, (0, 0))
        screen.blit(dim, (0, 0))
        screen.blit(title, title_rect)
        for i, (rect, card) in enumerate(zip(rects, cards)):
            shadow = rect.inflate(18, 18)
            pygame.draw.rect(screen, (0, 0, 0, 90), shadow, border_radius=18)
            pygame.draw.rect(screen, (35, 36, 38), rect, border_radius=14)
            border_col = (200, 200, 200) if i == hover else (120, 120, 120)
            pygame.draw.rect(screen, border_col, rect, width=2, border_radius=14)
            idx_lbl = head_font.render(str(i + 1), True, (210, 210, 210))
            screen.blit(idx_lbl, idx_lbl.get_rect(midleft=(rect.left + 14, rect.top + 18)))
            title_surf = head_font.render(card["title"], True, (230, 230, 230))
            screen.blit(title_surf, title_surf.get_rect(topleft=(rect.left + 44, rect.top + 12)))
            desc_surf = body_font.render(card["desc"], True, (195, 195, 195))
            screen.blit(desc_surf, desc_surf.get_rect(topleft=(rect.left + 20, rect.top + 56)))
        pygame.display.flip()
        for event in pygame.event.get():
            screen = game._handle_web_window_event(event) or screen
            game._sync_web_input_event(event)
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if is_web_interaction_event(event):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_1, pygame.K_KP_1) and len(cards) >= 1:
                    return cards[0]["key"]
                if event.key in (pygame.K_2, pygame.K_KP_2) and len(cards) >= 2:
                    return cards[1]["key"]
                if event.key in (pygame.K_3, pygame.K_KP_3) and len(cards) >= 3:
                    return cards[2]["key"]
                if event.key in (pygame.K_4, pygame.K_KP_4) and len(cards) >= 4:
                    return cards[3]["key"]
                if is_escape_event(event):
                    continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and hover != -1:
                return cards[hover]["key"]
        clock.tick(60)
        await asyncio.sleep(0)


async def levelup_modal_web(game, screen, bg_surface, clock, time_left, player):
    key = await show_levelup_overlay_web(game, screen, bg_surface, player)
    if key:
        game._apply_levelup_choice(player, key)
    rs.runtime(game)["_time_left_runtime"] = time_left
    clock.tick(60)
    game.flush_events()
    return time_left


async def show_fail_screen(game, screen, background_surf):
    def _draw_overlay() -> tuple[pygame.Rect, pygame.Rect]:
        dim = pygame.Surface((game.VIEW_W, game.VIEW_H))
        dim.set_alpha(180)
        dim.fill((0, 0, 0))
        screen.blit(pygame.transform.smoothscale(background_surf, (game.VIEW_W, game.VIEW_H)), (0, 0))
        screen.blit(dim, (0, 0))
        title = pygame.font.SysFont(None, 80).render("YOU WERE CORRUPTED!", True, (255, 60, 60))
        screen.blit(title, title.get_rect(center=(game.VIEW_W // 2, 140)))
        retry_rect = game.draw_button(screen, "RETRY", (game.VIEW_W // 2 - 200, 300))
        home_rect = game.draw_button(screen, "HOME", (game.VIEW_W // 2 + 20, 300))
        pygame.display.flip()
        return retry_rect, home_rect

    retry, home = _draw_overlay()
    start_menu_surf = None
    while True:
        for event in pygame.event.get():
            screen = game._handle_web_window_event(event) or screen
            game._sync_web_input_event(event)
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.IS_WEB and is_web_interaction_event(event):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if is_escape_event(event):
                bg = pygame.display.get_surface().copy()
                if game.IS_WEB:
                    pick = await game.pause_from_overlay_web(screen, bg)
                else:
                    pick = game.pause_from_overlay(screen, bg)
                if pick == "continue":
                    retry, home = _draw_overlay()
                    continue
                if pick == "home":
                    game.queue_menu_transition(pygame.display.get_surface().copy())
                    start_menu_surf = start_menu_surf or game.render_start_menu_surface(game.has_save())
                    game.flush_events()
                    return "home"
                if pick == "restart":
                    game.queue_menu_transition(pygame.display.get_surface().copy())
                    game.flush_events()
                    return "retry"
                if pick == "exit":
                    if game.IS_WEB:
                        game.queue_menu_transition(pygame.display.get_surface().copy())
                        game.flush_events()
                        return "home"
                    pygame.quit()
                    sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if retry.collidepoint(event.pos):
                    game.queue_menu_transition(pygame.display.get_surface().copy())
                    game.flush_events()
                    return "retry"
                if home.collidepoint(event.pos):
                    game.queue_menu_transition(pygame.display.get_surface().copy())
                    start_menu_surf = start_menu_surf or game.render_start_menu_surface(game.has_save())
                    game.flush_events()
                    return "home"
        if game.IS_WEB:
            retry, home = _draw_overlay()
            await asyncio.sleep(0)


async def show_success_screen(game, screen, background_surf, reward_choices):
    dim = pygame.Surface((game.VIEW_W, game.VIEW_H))
    dim.set_alpha(150)
    dim.fill((0, 0, 0))
    screen.blit(pygame.transform.smoothscale(background_surf, (game.VIEW_W, game.VIEW_H)), (0, 0))
    screen.blit(dim, (0, 0))
    title = pygame.font.SysFont(None, 80).render("MEMORY RESTORED!", True, (0, 255, 120))
    screen.blit(title, title.get_rect(center=(game.VIEW_W // 2, 100)))
    card_rects = []
    for index, card in enumerate(reward_choices):
        x = game.VIEW_W // 2 - (len(reward_choices) * 140) // 2 + index * 140
        rect = pygame.Rect(x, 180, 120, 160)
        pygame.draw.rect(screen, (220, 220, 220), rect)
        name = pygame.font.SysFont(None, 24).render(card.replace("_", " ").upper(), True, (20, 20, 20))
        screen.blit(name, name.get_rect(center=(rect.centerx, rect.bottom - 18)))
        pygame.draw.rect(screen, (40, 40, 40), rect, 3)
        pygame.draw.rect(screen, (70, 90, 90), rect.inflate(-30, -50))
        card_rects.append((rect, card))
    next_btn = game.draw_button(screen, "CONFIRM", (game.VIEW_W // 2 - 90, 370))
    chosen = None
    pygame.display.flip()
    while True:
        for event in pygame.event.get():
            if getattr(game, "IS_WEB", False):
                screen = game._handle_web_window_event(event) or screen
                game._sync_web_input_event(event)
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.IS_WEB and is_web_interaction_event(event):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if is_escape_event(event):
                bg = pygame.display.get_surface().copy()
                if game.IS_WEB:
                    pick = await game.pause_from_overlay_web(screen, bg)
                else:
                    pick = game.pause_from_overlay(screen, bg)
                if pick == "continue":
                    dim = pygame.Surface((game.VIEW_W, game.VIEW_H))
                    dim.set_alpha(150)
                    dim.fill((0, 0, 0))
                    screen.blit(pygame.transform.smoothscale(background_surf, (game.VIEW_W, game.VIEW_H)), (0, 0))
                    screen.blit(dim, (0, 0))
                    title = pygame.font.SysFont(None, 80).render("MEMORY RESTORED!", True, (0, 255, 120))
                    screen.blit(title, title.get_rect(center=(game.VIEW_W // 2, 100)))
                    card_rects = []
                    for index, card in enumerate(reward_choices):
                        x = game.VIEW_W // 2 - (len(reward_choices) * 140) // 2 + index * 140
                        rect = pygame.Rect(x, 180, 120, 160)
                        pygame.draw.rect(screen, (220, 220, 220), rect)
                        name = pygame.font.SysFont(None, 24).render(card.replace("_", " ").upper(), True, (20, 20, 20))
                        screen.blit(name, name.get_rect(center=(rect.centerx, rect.bottom - 18)))
                        pygame.draw.rect(screen, (40, 40, 40), rect, 3)
                        pygame.draw.rect(screen, (70, 90, 90), rect.inflate(-30, -50))
                        card_rects.append((rect, card))
                    next_btn = game.draw_button(screen, "CONFIRM", (game.VIEW_W // 2 - 90, 370))
                    pygame.display.flip()
                    continue
                if pick == "home":
                    game.queue_menu_transition(pygame.display.get_surface().copy())
                    game.flush_events()
                    return "home"
                if pick == "restart":
                    game.queue_menu_transition(pygame.display.get_surface().copy())
                    game.flush_events()
                    return "restart"
                if pick == "exit":
                    if game.IS_WEB:
                        game.queue_menu_transition(pygame.display.get_surface().copy())
                        game.flush_events()
                        return "home"
                    pygame.quit()
                    sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                if chosen or len(reward_choices) == 0:
                    game.flush_events()
                    return chosen
            if event.type == pygame.MOUSEBUTTONDOWN:
                for rect, card in card_rects:
                    if rect.collidepoint(event.pos):
                        chosen = card
                if next_btn.collidepoint(event.pos) and (chosen or len(reward_choices) == 0):
                    game.flush_events()
                    return chosen
        if game.IS_WEB:
            await asyncio.sleep(0)


def show_settings_popup(game, screen, background_surf):
    clock = pygame.time.Clock()
    dim = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 170))
    bg_scaled = pygame.transform.smoothscale(background_surf, (game.VIEW_W, game.VIEW_H))
    panel_w, panel_h = min(520, game.VIEW_W - 80), min(520, game.VIEW_H - 160)
    panel = pygame.Rect(0, 0, panel_w, panel_h)
    panel.center = (game.VIEW_W // 2, game.VIEW_H // 2)
    title_font = pygame.font.SysFont(None, 56)
    font = pygame.font.SysFont(None, 26)
    btn_font = pygame.font.SysFont(None, 32)
    status_font = pygame.font.SysFont("Consolas", 18)
    fx_val = int(game.FX_VOLUME)
    bgm_val = int(game.BGM_VOLUME)
    dragging = None
    page = "root"
    waiting_action = None
    status_msg = ""
    status_color = (170, 210, 230)
    ctrl_buttons: list[tuple[pygame.Rect, str]] = []
    runtime_summary = _browser_runtime_summary(game)

    control_actions = [
        ("Move Up", "move_up"),
        ("Move Left", "move_left"),
        ("Move Down", "move_down"),
        ("Move Right", "move_right"),
        ("Blast", "blast"),
        ("Teleport", "teleport"),
    ]

    def draw_slider(label, value, top_y):
        screen.blit(font.render(f"{label}: {value}", True, game.UI_TEXT), (panel.left + 40, top_y))
        bar = pygame.Rect(panel.left + 40, top_y + 24, panel_w - 80, 10)
        knob_x = bar.x + int((value / 100) * bar.width)
        pygame.draw.rect(screen, (60, 70, 90), bar, border_radius=6)
        pygame.draw.circle(screen, game.UI_ACCENT, (knob_x, bar.y + 5), 8)
        return bar

    def val_from_bar(bar, mx):
        return max(0, min(100, int(((mx - bar.x) / max(1, bar.width)) * 100)))

    def draw_root():
        screen.blit(bg_scaled, (0, 0))
        screen.blit(dim, (0, 0))
        pygame.draw.rect(screen, game.UI_PANEL, panel, border_radius=16)
        pygame.draw.rect(screen, game.UI_BORDER, panel, width=3, border_radius=16)
        title = title_font.render("Settings", True, game.UI_TEXT)
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 60)))
        btn_w, btn_h = 220, 56
        audio_btn = pygame.Rect(0, 0, btn_w, btn_h)
        ctrl_btn = pygame.Rect(0, 0, btn_w, btn_h)
        export_btn = pygame.Rect(0, 0, btn_w, btn_h)
        close_btn = pygame.Rect(0, 0, btn_w, btn_h)
        audio_btn.center = (panel.centerx, panel.top + 160)
        ctrl_btn.center = (panel.centerx, panel.top + 230)
        export_btn.center = (panel.centerx, panel.top + 300)
        close_btn.center = (panel.centerx, panel.bottom - 60)
        mouse_pos = pygame.mouse.get_pos()
        game.draw_neuro_button(screen, audio_btn, "Audio", btn_font, hovered=audio_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        game.draw_neuro_button(screen, ctrl_btn, "Controls", btn_font, hovered=ctrl_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        game.draw_neuro_button(screen, export_btn, "Export Save", btn_font, hovered=export_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        game.draw_neuro_button(screen, close_btn, "Close", btn_font, hovered=close_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        if runtime_summary:
            summary = status_font.render(runtime_summary[:68], True, (140, 195, 220))
            screen.blit(summary, summary.get_rect(center=(panel.centerx, panel.bottom - 136)))
        if status_msg:
            status = status_font.render(status_msg[:64], True, status_color)
            screen.blit(status, status.get_rect(center=(panel.centerx, panel.bottom - 110)))
        pygame.display.flip()
        return audio_btn, ctrl_btn, export_btn, close_btn

    def draw_audio():
        screen.blit(bg_scaled, (0, 0))
        screen.blit(dim, (0, 0))
        pygame.draw.rect(screen, game.UI_PANEL, panel, border_radius=16)
        pygame.draw.rect(screen, game.UI_BORDER, panel, width=3, border_radius=16)
        title = title_font.render("Audio", True, game.UI_TEXT)
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 60)))
        nonlocal fx_bar, bgm_bar
        fx_bar = draw_slider("Effects Volume", fx_val, panel.top + 120)
        bgm_bar = draw_slider("BGM Volume", bgm_val, panel.top + 180)
        btn_w, btn_h = 180, 52
        back_btn = pygame.Rect(0, 0, btn_w, btn_h)
        close_btn = pygame.Rect(0, 0, btn_w, btn_h)
        back_btn.center = (panel.centerx - 100, panel.bottom - 60)
        close_btn.center = (panel.centerx + 100, panel.bottom - 60)
        mouse_pos = pygame.mouse.get_pos()
        game.draw_neuro_button(screen, back_btn, "Back", btn_font, hovered=back_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        game.draw_neuro_button(screen, close_btn, "Save", btn_font, hovered=close_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        pygame.display.flip()
        return back_btn, close_btn

    def draw_controls():
        screen.blit(bg_scaled, (0, 0))
        screen.blit(dim, (0, 0))
        pygame.draw.rect(screen, game.UI_PANEL, panel, border_radius=16)
        pygame.draw.rect(screen, game.UI_BORDER, panel, width=3, border_radius=16)
        title = title_font.render("Controls", True, game.UI_TEXT)
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 52)))
        hint = font.render("Click an action, then press a key to rebind.", True, game.UI_TEXT)
        screen.blit(hint, hint.get_rect(center=(panel.centerx, panel.top + 92)))
        ctrl_buttons.clear()
        start_y = panel.top + 130
        row_h = 46
        btn_w, btn_h = 180, 34
        mouse_pos = pygame.mouse.get_pos()
        for idx, (label, action) in enumerate(control_actions):
            y = start_y + idx * row_h
            screen.blit(font.render(label, True, game.UI_TEXT), (panel.left + 36, y))
            btn = pygame.Rect(0, 0, btn_w, btn_h)
            btn.center = (panel.centerx + 80, y + btn_h // 2)
            ctrl_buttons.append((btn, action))
            text = "Press a key..." if waiting_action == action else game.binding_name(action)
            game.draw_neuro_button(screen, btn, text, font, hovered=btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        back_btn = pygame.Rect(0, 0, 160, 48)
        close_btn = pygame.Rect(0, 0, 160, 48)
        back_btn.center = (panel.centerx - 90, panel.bottom - 60)
        close_btn.center = (panel.centerx + 90, panel.bottom - 60)
        game.draw_neuro_button(screen, back_btn, "Back", btn_font, hovered=back_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        game.draw_neuro_button(screen, close_btn, "Save", btn_font, hovered=close_btn.collidepoint(mouse_pos), disabled=False, t=pygame.time.get_ticks() * 0.001, show_spike=False)
        pygame.display.flip()
        return back_btn, close_btn

    fx_bar = bgm_bar = None
    audio_btn = ctrl_btn = export_btn = close_btn = None
    while True:
        if page == "root":
            audio_btn, ctrl_btn, export_btn, close_btn = draw_root()
        elif page == "audio":
            back_btn, close_btn = draw_audio()
        elif page == "controls":
            back_btn, close_btn = draw_controls()
        else:
            page = "root"
            continue

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.IS_WEB and is_web_interaction_event(event):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if is_escape_event(event) and waiting_action:
                waiting_action = None
                continue
            if is_escape_event(event):
                game.FX_VOLUME = fx_val
                game.BGM_VOLUME = bgm_val
                _sync_bgm_volume(game, bgm_val)
                game.flush_events()
                return "close"

            if page == "root":
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    if audio_btn and audio_btn.collidepoint((mx, my)):
                        page = "audio"
                        dragging = None
                    elif ctrl_btn and ctrl_btn.collidepoint((mx, my)):
                        page = "controls"
                        waiting_action = None
                    elif export_btn and export_btn.collidepoint((mx, my)):
                        ok, msg = game.export_current_save()
                        status_msg = msg
                        status_color = (120, 230, 160) if ok else (255, 150, 150)
                        runtime_summary = _browser_runtime_summary(game)
                    elif close_btn and close_btn.collidepoint((mx, my)):
                        game.FX_VOLUME = fx_val
                        game.BGM_VOLUME = bgm_val
                        _sync_bgm_volume(game, bgm_val)
                        game.flush_events()
                        return "close"

            elif page == "audio":
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    if fx_bar and fx_bar.collidepoint((mx, my)):
                        fx_val = val_from_bar(fx_bar, mx)
                        game.FX_VOLUME = fx_val
                        dragging = "fx"
                    elif bgm_bar and bgm_bar.collidepoint((mx, my)):
                        bgm_val = val_from_bar(bgm_bar, mx)
                        game.BGM_VOLUME = bgm_val
                        _sync_bgm_volume(game, bgm_val)
                        dragging = "bgm"
                    elif back_btn and back_btn.collidepoint((mx, my)):
                        page = "root"
                        dragging = None
                    elif close_btn and close_btn.collidepoint((mx, my)):
                        game.FX_VOLUME = fx_val
                        game.BGM_VOLUME = bgm_val
                        _sync_bgm_volume(game, bgm_val)
                        game.flush_events()
                        return "close"
                if event.type == pygame.MOUSEBUTTONUP:
                    dragging = None
                if event.type == pygame.MOUSEMOTION and dragging:
                    mx, my = event.pos
                    if dragging == "fx" and fx_bar:
                        fx_val = val_from_bar(fx_bar, mx)
                        game.FX_VOLUME = fx_val
                    elif dragging == "bgm" and bgm_bar:
                        bgm_val = val_from_bar(bgm_bar, mx)
                        game.BGM_VOLUME = bgm_val
                        _sync_bgm_volume(game, bgm_val)

            elif page == "controls":
                if waiting_action and event.type == pygame.KEYDOWN:
                    if is_escape_event(event):
                        waiting_action = None
                    else:
                        game.set_binding(waiting_action, event.key)
                        waiting_action = None
                    continue
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    clicked_any = False
                    for rect, action in ctrl_buttons:
                        if rect.collidepoint((mx, my)):
                            waiting_action = action
                            clicked_any = True
                            break
                    if clicked_any:
                        continue
                    if back_btn and back_btn.collidepoint((mx, my)):
                        waiting_action = None
                        page = "root"
                    elif close_btn and close_btn.collidepoint((mx, my)):
                        game.FX_VOLUME = fx_val
                        game.BGM_VOLUME = bgm_val
                        _sync_bgm_volume(game, bgm_val)
                        game.flush_events()
                        return "close"

        clock.tick(60)
