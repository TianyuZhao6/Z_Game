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


async def show_settings_popup_web(game, screen, background_surf):
    clock = pygame.time.Clock()
    panel = pygame.Rect(0, 0, min(560, game.VIEW_W - 60), min(360, game.VIEW_H - 80))
    panel.center = (game.VIEW_W // 2, game.VIEW_H // 2)
    title_font = pygame.font.SysFont(None, 48)
    label_font = pygame.font.SysFont(None, 28)
    btn_font = pygame.font.SysFont(None, 30)
    status_font = pygame.font.SysFont("Consolas", 18)
    fx_val = int(game.FX_VOLUME)
    bgm_val = int(game.BGM_VOLUME)
    status_msg = ""
    status_color = (170, 210, 230)

    while True:
        screen.blit(background_surf, (0, 0))
        dim = pygame.Surface((game.VIEW_W, game.VIEW_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 165))
        screen.blit(dim, (0, 0))
        pygame.draw.rect(screen, game.UI_PANEL, panel, border_radius=16)
        pygame.draw.rect(screen, game.UI_BORDER, panel, width=3, border_radius=16)
        title = title_font.render("Settings", True, game.UI_TEXT)
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 46)))

        info = label_font.render("Web demo settings: audio + save export", True, (180, 215, 235))
        screen.blit(info, info.get_rect(center=(panel.centerx, panel.top + 88)))
        if status_msg:
            status = status_font.render(status_msg[:48], True, status_color)
            screen.blit(status, status.get_rect(center=(panel.centerx, panel.top + 116)))

        fx_minus = pygame.Rect(panel.left + 54, panel.top + 146, 54, 42)
        fx_plus = pygame.Rect(panel.right - 108, panel.top + 146, 54, 42)
        bgm_minus = pygame.Rect(panel.left + 54, panel.top + 222, 54, 42)
        bgm_plus = pygame.Rect(panel.right - 108, panel.top + 222, 54, 42)
        export_btn = pygame.Rect(0, 0, 180, 50)
        close_btn = pygame.Rect(0, 0, 180, 50)
        export_btn.center = (panel.centerx - 104, panel.bottom - 46)
        close_btn.center = (panel.centerx + 104, panel.bottom - 46)

        fx_label = label_font.render(f"Effects Volume: {fx_val}", True, game.UI_TEXT)
        bgm_label = label_font.render(f"BGM Volume: {bgm_val}", True, game.UI_TEXT)
        screen.blit(fx_label, fx_label.get_rect(center=(panel.centerx, fx_minus.centery)))
        screen.blit(bgm_label, bgm_label.get_rect(center=(panel.centerx, bgm_minus.centery)))

        hover_pos = pygame.mouse.get_pos()
        for rect, text in (
            (fx_minus, "-"),
            (fx_plus, "+"),
            (bgm_minus, "-"),
            (bgm_plus, "+"),
            (export_btn, "Export Save"),
            (close_btn, "Close"),
        ):
            game.draw_neuro_button(
                screen,
                rect,
                text,
                btn_font,
                hovered=rect.collidepoint(hover_pos),
                disabled=False,
                t=pygame.time.get_ticks() * 0.001,
                show_spike=False,
            )
        pygame.display.flip()

        for event in pygame.event.get():
            screen = game._handle_web_window_event(event) or screen
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.IS_WEB and is_web_interaction_event(event):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if is_escape_event(event):
                game.FX_VOLUME = fx_val
                game.BGM_VOLUME = bgm_val
                _sync_bgm_volume(game, bgm_val)
                game.flush_events()
                return "close"
            if event.type == pygame.MOUSEBUTTONDOWN:
                if fx_minus.collidepoint(event.pos):
                    fx_val = max(0, fx_val - 10)
                    game.FX_VOLUME = fx_val
                elif fx_plus.collidepoint(event.pos):
                    fx_val = min(100, fx_val + 10)
                    game.FX_VOLUME = fx_val
                elif bgm_minus.collidepoint(event.pos):
                    bgm_val = max(0, bgm_val - 10)
                    game.BGM_VOLUME = bgm_val
                    _sync_bgm_volume(game, bgm_val)
                elif bgm_plus.collidepoint(event.pos):
                    bgm_val = min(100, bgm_val + 10)
                    game.BGM_VOLUME = bgm_val
                    _sync_bgm_volume(game, bgm_val)
                elif export_btn.collidepoint(event.pos):
                    ok, msg = game.export_current_save()
                    status_msg = msg
                    status_color = (120, 230, 160) if ok else (255, 150, 150)
                elif close_btn.collidepoint(event.pos):
                    game.FX_VOLUME = fx_val
                    game.BGM_VOLUME = bgm_val
                    _sync_bgm_volume(game, bgm_val)
                    game.flush_events()
                    return "close"
        await asyncio.sleep(0)


async def show_fail_screen(game, screen, background_surf):
    dim = pygame.Surface((game.VIEW_W, game.VIEW_H))
    dim.set_alpha(180)
    dim.fill((0, 0, 0))
    screen.blit(pygame.transform.smoothscale(background_surf, (game.VIEW_W, game.VIEW_H)), (0, 0))
    screen.blit(dim, (0, 0))
    title = pygame.font.SysFont(None, 80).render("YOU WERE CORRUPTED!", True, (255, 60, 60))
    screen.blit(title, title.get_rect(center=(game.VIEW_W // 2, 140)))
    retry = game.draw_button(screen, "RETRY", (game.VIEW_W // 2 - 200, 300))
    home = game.draw_button(screen, "HOME", (game.VIEW_W // 2 + 20, 300))
    pygame.display.flip()
    start_menu_surf = None
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.IS_WEB and is_web_interaction_event(event):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if is_escape_event(event):
                bg = pygame.display.get_surface().copy()
                pick = game.pause_from_overlay(screen, bg)
                if pick == "continue":
                    dim = pygame.Surface((game.VIEW_W, game.VIEW_H))
                    dim.set_alpha(180)
                    dim.fill((0, 0, 0))
                    screen.blit(pygame.transform.smoothscale(background_surf, (game.VIEW_W, game.VIEW_H)), (0, 0))
                    screen.blit(dim, (0, 0))
                    title = pygame.font.SysFont(None, 80).render("YOU WERE CORRUPTED!", True, (255, 60, 60))
                    screen.blit(title, title.get_rect(center=(game.VIEW_W // 2, 140)))
                    retry = game.draw_button(screen, "RETRY", (game.VIEW_W // 2 - 200, 300))
                    home = game.draw_button(screen, "HOME", (game.VIEW_W // 2 + 20, 300))
                    pygame.display.flip()
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
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.IS_WEB and is_web_interaction_event(event):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if is_escape_event(event):
                bg = pygame.display.get_surface().copy()
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
