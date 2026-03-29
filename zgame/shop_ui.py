"""Extracted UI flow from ZGame.py."""
from __future__ import annotations
import copy
import math
import random
import sys
from typing import Optional
import pygame
from zgame.browser import is_web_interaction_event
from zgame import shop_support
from zgame import runtime_state as rs


def _runtime(game):
    return rs.runtime(game)


def _meta(game):
    return rs.meta(game)

def show_shop_screen(game, screen) -> Optional[str]:
    """Spend META['spoils'] on small upgrades. ESC opens Pause; return action or None when closed."""
    runtime = _runtime(game)
    meta = _meta(game)
    if not runtime.get('_resume_shop_cache', False):
        game._clear_shop_cache()
    runtime['_resume_shop_cache'] = False
    game.play_combat_bgm()
    runtime['_coins_at_shop_entry'] = int(meta.get('spoils', 0))
    runtime['_in_shop_ui'] = True
    try:
        clock = pygame.time.Clock()
        font = pygame.font.SysFont(None, 30)
        desc_font = pygame.font.SysFont(None, 24)
        title_font = pygame.font.SysFont(None, 56)
        btn_font = pygame.font.SysFont(None, 32)
        did_menu_hex = False
        SHOP_BOX_BG = game.UI_PANEL
        SHOP_BOX_BORDER = game.UI_BORDER
        SHOP_BOX_BG_HOVER = (32, 40, 56)
        SHOP_BOX_BORDER_HOVER = game.UI_BORDER_HOVER
        SHOP_BOX_BG_DISABLED = game.UI_PANEL_DARK
        SHOP_BOX_BORDER_DISABLED = (70, 90, 120)
        auto_turret_sprite = game._load_shop_sprite('prop-icon/auto-turret.png', (150, 110))
        stationary_turret_sprite = game._load_shop_sprite('prop-icon/Stationary Turret.png', (150, 110))
        catalog = shop_support.build_shop_catalog(game)
    finally:
        runtime.pop('_in_shop_ui', None)
    locked_ids = shop_support.load_locked_ids(game)

    def _persist_locked_ids():
        shop_support.persist_locked_ids(game, locked_ids)
    _persist_locked_ids()

    def _prop_level(it):
        return shop_support.prop_level(game, it)

    def _owned_live_text(it, lvl: int | None):
        return shop_support.owned_live_text(game, it, lvl)

    def _prop_max_level(it):
        return shop_support.prop_max_level(it)

    def _prop_at_cap(it):
        return shop_support.prop_at_cap(game, it)

    def roll_offers():
        return shop_support.roll_offers(game, catalog, locked_ids)
    offers = roll_offers()

    def _is_reroll_item(it):
        return shop_support.is_reroll_item(it)

    def _split_offers(current):
        return shop_support.split_offers(current)

    def _save_slots():
        runtime['_shop_slots_cache'] = copy.deepcopy(normal_slots)
        runtime['_shop_reroll_cache'] = copy.deepcopy(reroll_offer)
    slots_cache = runtime.get('_shop_slots_cache')
    reroll_cache = runtime.get('_shop_reroll_cache')
    if slots_cache is not None or reroll_cache is not None:
        normal_slots = copy.deepcopy(slots_cache) if slots_cache is not None else []
        reroll_offer = copy.deepcopy(reroll_cache)
        normal_slots = [c for c in normal_slots if c and (not _prop_at_cap(c))]
        if not normal_slots:
            offers = roll_offers()
            normal_slots, reroll_offer = _split_offers(offers)
    else:
        normal_slots, reroll_offer = _split_offers(offers)
        _save_slots()
    hovered_uid: Optional[str] = None
    lockbox_msg: Optional[str] = None
    lockbox_msg_until = 0
    lockbox_msg_life = 2200
    owned_rows: list = []
    while True:
        screen.fill((16, 16, 18))
        mx, my = pygame.mouse.get_pos()
        title_surf = title_font.render('TRADER', True, (235, 235, 235))
        screen.blit(title_surf, title_surf.get_rect(center=(game.VIEW_W // 2, 80)))
        money_surf = font.render(f"Coins: {meta['spoils']}", True, (255, 230, 120))
        screen.blit(money_surf, money_surf.get_rect(center=(game.VIEW_W // 2, 130)))
        now_ms = pygame.time.get_ticks()
        overlay_surf = None
        overlay_alpha = 255
        if lockbox_msg and now_ms < lockbox_msg_until:
            t = max(0.0, min(1.0, (lockbox_msg_until - now_ms) / float(lockbox_msg_life)))
            if lockbox_msg == 'lockbox':
                lb_lvl = int(meta.get('lockbox_level', 0))
                if lb_lvl > 0:
                    protected = game.lockbox_protected_min(max(0, int(meta.get('spoils', 0))), lb_lvl)
                    msg_txt = f'{protected} coins restored'
                    overlay_surf = pygame.font.SysFont('Franklin Gothic Medium', 96).render(msg_txt, True, (255, 230, 160))
                    overlay_alpha = int(255 * t)
            else:
                msg_txt = str(lockbox_msg)
                overlay_surf = pygame.font.SysFont('Franklin Gothic Medium', 46).render(msg_txt, True, (210, 235, 255))
                overlay_alpha = int(255 * t)
        card_w, card_h = (220, 180)
        gap = 22
        y = 200
        total_w = len(normal_slots) * card_w + max(0, len(normal_slots) - 1) * gap
        start_x = (game.VIEW_W - total_w) // 2 if len(normal_slots) > 0 else game.VIEW_W // 2
        rects = []
        x = start_x
        for slot_idx, it in enumerate(normal_slots):
            r = pygame.Rect(x, y, card_w, card_h)
            x += card_w + gap
            if it is None:
                continue
            level_idx = int(runtime.get('current_level', 0))
            cur_lvl = _prop_level(it)
            dyn_cost = game.shop_price(int(it['cost']), level_idx, kind='normal', prop_level=cur_lvl)
            max_lvl = _prop_max_level(it)
            is_capped = max_lvl is not None and cur_lvl is not None and (cur_lvl >= max_lvl)
            uid = it.get('id') or it.get('name')
            is_hover = uid == hovered_uid
            path_border = game.prop_path_border_color(it.get('id'))
            lock_rect = pygame.Rect(0, 0, 22, 22)
            lock_rect.topright = (r.right - 8, r.top + 8)
            if is_capped:
                bg_col = SHOP_BOX_BG_DISABLED
                border_col = game._mix_rgb(path_border, SHOP_BOX_BORDER_DISABLED, 0.65)
            elif is_hover:
                bg_col = SHOP_BOX_BG_HOVER
                border_col = game._scale_rgb(path_border, 1.25)
            else:
                bg_col = SHOP_BOX_BG
                border_col = path_border
            pygame.draw.rect(screen, bg_col, r, border_radius=14)
            pygame.draw.rect(screen, border_col, r, 2, border_radius=14)
            accent = pygame.Rect(r.x + 10, r.y + 32, r.w - 20, 3)
            pygame.draw.rect(screen, border_col, accent, border_radius=2)
            if is_hover:
                title_s = font.render(it['name'], True, (235, 235, 235))
                desc_text = str(it.get('desc', '')).strip()
                if not desc_text:
                    desc_text = str(game.detailed_prop_tooltip_text(it, cur_lvl, meta) or '').strip()
                words = desc_text.split()
                lines_wrap = []
                if words:
                    max_w = r.width - 28
                    line = ''
                    for w2 in words:
                        test = (line + ' ' + w2).strip()
                        test_surf = desc_font.render(test, True, (210, 210, 210))
                        if test_surf.get_width() > max_w and line:
                            lines_wrap.append(line)
                            line = w2
                        else:
                            line = test
                    if line:
                        lines_wrap.append(line)
                if len(lines_wrap) > 6:
                    lines_wrap = lines_wrap[:6]
                    lines_wrap[-1] = game._truncate_inline(lines_wrap[-1], 44)
                line_h = desc_font.get_linesize()
                block_h = title_s.get_height() + 4 + len(lines_wrap) * line_h
                top_y = r.centery - block_h // 2
                title_rect = title_s.get_rect(midtop=(r.centerx, top_y))
                screen.blit(title_s, title_rect)
                yy = title_rect.bottom + 4
                for ln in lines_wrap:
                    ln_surf = desc_font.render(ln, True, (210, 210, 210))
                    screen.blit(ln_surf, ln_surf.get_rect(midtop=(r.centerx, yy)))
                    yy += line_h
            else:
                name_surf = font.render(it['name'], True, (235, 235, 235))
                screen.blit(name_surf, name_surf.get_rect(midtop=(r.centerx, r.y + 10)))
                if it.get('id') == 'auto_turret' and auto_turret_sprite:
                    sprite_top = r.y + 36
                    sprite_bottom = r.bottom - 36
                    sprite_center_y = (sprite_top + sprite_bottom) // 2
                    sprite_rect = auto_turret_sprite.get_rect(center=(r.centerx, sprite_center_y))
                    screen.blit(auto_turret_sprite, sprite_rect)
                elif it.get('id') == 'stationary_turret' and stationary_turret_sprite:
                    sprite_top = r.y + 36
                    sprite_bottom = r.bottom - 36
                    sprite_center_y = (sprite_top + sprite_bottom) // 2
                    sprite_rect = stationary_turret_sprite.get_rect(center=(r.centerx, sprite_center_y))
                    screen.blit(stationary_turret_sprite, sprite_rect)
                col = (255, 230, 120) if meta['spoils'] >= dyn_cost else (160, 140, 120)
                price_txt = f'$ {dyn_cost}'
                price_surf = font.render(price_txt, True, col)
                screen.blit(price_surf, price_surf.get_rect(midbottom=(r.centerx, r.bottom - 10)))
                rarity = int(it.get('rarity', 1))
                dot_r = 4
                for j in range(rarity):
                    cx = r.left + 14 + j * (dot_r * 2 + 6)
                    cy = r.bottom - 18
                    pygame.draw.circle(screen, (180, 160, 220), (cx, cy), dot_r)
            if (not is_hover) and max_lvl is not None and cur_lvl is not None:
                lvl_text = f'{cur_lvl}/{max_lvl}'
                lvl_color = (180, 230, 255) if not is_capped else (140, 150, 160)
                lvl_surf = font.render(lvl_text, True, lvl_color)
                screen.blit(lvl_surf, lvl_surf.get_rect(bottomright=(r.right - 8, r.bottom - 6)))
            locked = it.get('id') in locked_ids
            if locked:
                bg_col = SHOP_BOX_BORDER_HOVER
                border_col = SHOP_BOX_BG
                icon_col = (20, 20, 22)
            else:
                bg_col = SHOP_BOX_BG
                border_col = SHOP_BOX_BORDER
                icon_col = (235, 235, 235)
            pygame.draw.rect(screen, bg_col, lock_rect, border_radius=6)
            pygame.draw.rect(screen, border_col, lock_rect, 2, border_radius=6)
            icon = desc_font.render('L', True, icon_col)
            screen.blit(icon, icon.get_rect(center=lock_rect.center))
            rects.append((r, it, dyn_cost, is_capped, uid, lock_rect, slot_idx))
        owned = []
        for itm in catalog:
            lvl = _prop_level(itm)
            if itm.get('id') == 'shady_loan':
                status = meta.get('shady_loan_status')
                if status in ('repaid', 'defaulted') and (lvl is None or lvl <= 0):
                    lvl = max(1, int(meta.get('shady_loan_last_level', 1)))
            max_lvl = _prop_max_level(itm)
            if lvl is not None and lvl > 0 and (itm.get('id') != 'reroll'):
                owned.append({'itm': itm, 'lvl': lvl, 'max': max_lvl})
        if owned:
            margin_side = 40
            margin_bottom = 70
            line_h = font.get_linesize()
            name_w_max = max((font.render(ent['itm']['name'], True, (0, 0, 0)).get_width() for ent in owned))
            col_w = max(170, name_w_max + 60)
            col_gap = 14
            cols = 1
            if len(owned) > 8:
                cols = 2
            if len(owned) > 16:
                cols = 3
            rows = max(1, math.ceil(len(owned) / cols))
            panel_w = col_w * cols + col_gap * (cols - 1) + 28
            header_h = line_h
            panel_h = 16 + header_h + rows * line_h + 12
            panel_x = max(margin_side, int(game.VIEW_W * 0.075))
            base_y = y + card_h + 220
            panel_y = min(game.VIEW_H - panel_h - margin_bottom, base_y)
            panel = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
            pygame.draw.rect(screen, SHOP_BOX_BG, panel, border_radius=14)
            pygame.draw.rect(screen, SHOP_BOX_BORDER, panel, 2, border_radius=14)
            header = font.render('Possession', True, (220, 220, 230))
            screen.blit(header, header.get_rect(left=panel.x + 14, top=panel.y + 8))
            base_y = panel.y + 8 + header_h + 4
            owned_rows.clear()
            for idx, ent in enumerate(owned):
                name = ent['itm']['name']
                lvl = ent['lvl']
                max_lvl = ent['max']
                col = idx % cols
                row = idx // cols
                x0 = panel.x + 14 + col * (col_w + col_gap)
                y0 = base_y + row * line_h
                name_color = (210, 210, 210)
                lvl_color = (180, 230, 255)
                if ent['itm'].get('id') == 'shady_loan' and meta.get('shady_loan_status') == 'defaulted':
                    name_color = (200, 80, 80)
                    lvl_color = (220, 120, 120)
                name_surf = font.render(name, True, name_color)
                lvl_str = f'{lvl}/{max_lvl}' if max_lvl is not None else f'x{lvl}'
                lvl_surf = font.render(lvl_str, True, lvl_color)
                screen.blit(name_surf, (x0, y0))
                screen.blit(lvl_surf, lvl_surf.get_rect(right=x0 + col_w, top=y0))
                owned_rows.append((pygame.Rect(x0, y0, col_w, line_h), ent))
        reroll_rect = None
        if reroll_offer is not None:
            level_idx = int(runtime.get('current_level', 0))
            reroll_dyn_cost = game.shop_price(int(reroll_offer['cost']), level_idx, kind='reroll')
            reroll_rect = pygame.Rect(0, 0, 220, 52)
            reroll_rect.center = (game.VIEW_W // 2, y + card_h + 70)
            can_afford = meta.get('spoils', 0) >= reroll_dyn_cost
            if not can_afford:
                bg = SHOP_BOX_BG_DISABLED
                border = SHOP_BOX_BORDER_DISABLED
            elif reroll_rect.collidepoint((mx, my)):
                bg = SHOP_BOX_BG_HOVER
                border = SHOP_BOX_BORDER_HOVER
            else:
                bg = SHOP_BOX_BG
                border = SHOP_BOX_BORDER
            pygame.draw.rect(screen, bg, reroll_rect, border_radius=14)
            pygame.draw.rect(screen, border, reroll_rect, 2, border_radius=14)
            label = btn_font.render('Reroll', True, (235, 235, 235))
            label_rect = label.get_rect(center=(reroll_rect.centerx, reroll_rect.centery - 8))
            screen.blit(label, label_rect)
            cost_col = (255, 230, 120) if can_afford else (160, 140, 120)
            cost_surf = font.render(f'$ {reroll_dyn_cost}', True, cost_col)
            cost_rect = cost_surf.get_rect(center=(reroll_rect.centerx, reroll_rect.centery + 12))
            screen.blit(cost_surf, cost_rect)
            uid = reroll_offer.get('id') or reroll_offer.get('name')
            rects.append((reroll_rect, reroll_offer, reroll_dyn_cost, False, uid, None, None))
        tooltip_txt = None
        tooltip_pos = None
        if owned_rows:
            for row_rect, ent in owned_rows:
                if row_rect.collidepoint((mx, my)):
                    tooltip_txt = _owned_live_text(ent['itm'], ent['lvl'])
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
        close = pygame.Rect(0, 0, 220, 56)
        if reroll_rect is not None:
            next_y = reroll_rect.bottom + 40
        else:
            next_y = y + card_h + 120
        close.center = (game.VIEW_W // 2, next_y)
        pygame.draw.rect(screen, (50, 50, 50), close, border_radius=10)
        pygame.draw.rect(screen, (120, 120, 120), close, 2, border_radius=10)
        txt = btn_font.render('NEXT', True, (230, 230, 230))
        screen.blit(txt, txt.get_rect(center=close.center))
        if overlay_surf:
            overlay_surf.set_alpha(overlay_alpha)
            screen.blit(overlay_surf, overlay_surf.get_rect(center=(game.VIEW_W // 2, game.VIEW_H // 2)))
        if not did_menu_hex:
            game.run_pending_menu_transition(screen)
            did_menu_hex = True
        pygame.display.flip()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.IS_WEB and is_web_interaction_event(ev):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                bg = screen.copy()
                choice = game.pause_from_overlay(screen, bg)
                if choice in (None, 'continue', 'settings'):
                    game.flush_events()
                    break
                if choice == 'restart':
                    game.queue_menu_transition(screen.copy())
                    runtime['_restart_from_shop'] = True
                if choice == 'home':
                    game.queue_menu_transition(screen.copy())
                game.flush_events()
                return choice
            if ev.type == pygame.MOUSEMOTION:
                hovered_uid = None
                for r, it, dyn_cost, is_capped, uid, lock_rect, slot_idx in rects:
                    if r.collidepoint(ev.pos):
                        hovered_uid = uid
                        break
            if ev.type == pygame.MOUSEBUTTONDOWN:
                if close.collidepoint(ev.pos):
                    game.flush_events()
                    if int(meta.get('golden_interest_level', 0)) > 0:
                        gain = game.apply_golden_interest_payout()
                        game.show_golden_interest_popup(screen, gain, int(meta.get('spoils', 0)))
                    loan_outcome = game.apply_shady_loan_repayment()
                    if loan_outcome:
                        game.show_shady_loan_popup(screen, loan_outcome)
                    chosen_biome = game.show_biome_picker_in_shop(screen)
                    if chosen_biome in ('__HOME__', '__RESTART__', '__EXIT__'):
                        if chosen_biome == '__RESTART__':
                            runtime['_restart_from_shop'] = True
                        return {'__HOME__': 'home', '__RESTART__': 'restart', '__EXIT__': 'exit'}[chosen_biome]
                    runtime['_next_biome'] = chosen_biome
                    game._clear_shop_cache()
                    return None
                handled_lock = False
                for r, it, dyn_cost, is_capped, uid, lock_rect, slot_idx in rects:
                    if lock_rect and lock_rect.collidepoint(ev.pos):
                        card_id = it.get('id')
                        if card_id:
                            if card_id in locked_ids:
                                locked_ids.remove(card_id)
                            else:
                                locked_ids.append(card_id)
                            _persist_locked_ids()
                        handled_lock = True
                        break
                if handled_lock:
                    continue
                for r, it, dyn_cost, is_capped, uid, lock_rect, slot_idx in rects:
                    is_reroll = it.get('id') == 'reroll' or it.get('key') == 'reroll' or it.get('name') == 'Reroll Offers'
                    if not is_reroll and is_capped:
                        continue
                    if r.collidepoint(ev.pos) and meta['spoils'] >= dyn_cost:
                        coins_before_buy = int(meta.get('spoils', 0))
                        meta['spoils'] -= dyn_cost
                        card_id = it.get('id')
                        if card_id and card_id in locked_ids:
                            locked_ids.remove(card_id)
                            _persist_locked_ids()
                        if is_reroll or it.get('apply') == 'reroll':
                            offers = roll_offers()
                            normal_slots, reroll_offer = _split_offers(offers)
                            runtime['_shop_slot_ids_cache'] = [o.get('id') if o else None for o in normal_slots]
                            runtime['_shop_reroll_id_cache'] = reroll_offer.get('id') if reroll_offer else None
                            _save_slots()
                        else:
                            it['apply']()
                            if card_id == 'lockbox':
                                lockbox_msg = 'lockbox'
                                lockbox_msg_until = pygame.time.get_ticks() + lockbox_msg_life
                            if 0 <= slot_idx < len(normal_slots):
                                normal_slots[slot_idx] = None
                            hovered_uid = None
                            if all((s is None for s in normal_slots)):
                                offers = roll_offers()
                                normal_slots, reroll_offer = _split_offers(offers)
                                runtime['_shop_slot_ids_cache'] = [o.get('id') if o else None for o in normal_slots]
                                runtime['_shop_reroll_id_cache'] = reroll_offer.get('id') if reroll_offer else None
                                _save_slots()
                            else:
                                runtime['_shop_slot_ids_cache'] = [o.get('id') if o else None for o in normal_slots]
                                runtime['_shop_reroll_id_cache'] = reroll_offer.get('id') if reroll_offer else None
                                _save_slots()
                clock.tick(60)

def show_biome_picker_in_shop(game, screen) -> str:
    """在商店 NEXT 之后弹出的“下关场景”四选一卡面。返回被选择的场景名。"""
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont(None, 56)
    font = pygame.font.SysFont(None, 26)
    back_font = pygame.font.SysFont(None, 48)
    if getattr(game, "WEB_DEMO", False):
        names = list(getattr(game, "WEB_DEMO_SCENE_BIOMES", ()) or game.SCENE_BIOMES)
    else:
        names = list(game.SCENE_BIOMES)
    random.shuffle(names)
    card_w, card_h = (180, 240)
    gap = 20
    total_w = len(names) * card_w + (len(names) - 1) * gap
    start_x = (game.VIEW_W - total_w) // 2
    y = 160
    cards = []
    for i, name in enumerate(names):
        x = start_x + i * (card_w + gap)
        rect = pygame.Rect(x, y, card_w, card_h)
        cards.append({'name': name, 'rect': rect, 'revealed': False})
    chosen = None
    confirm = pygame.Rect(0, 0, 240, 56)
    confirm.center = (game.VIEW_W // 2, y + card_h + 90)
    start_menu_surf = None

    def draw():
        screen.fill((16, 16, 18))
        title = title_font.render('CHOOSE NEXT DOMAIN', True, (235, 235, 235))
        screen.blit(title, title.get_rect(center=(game.VIEW_W // 2, 90)))
        for c in cards:
            r = c['rect']
            if c['revealed']:
                pygame.draw.rect(screen, (60, 66, 70), r, border_radius=12)
                pygame.draw.rect(screen, (200, 200, 210), r, 2, border_radius=12)
                name = c['name'].upper()
                parts = name.split()
                text_lines = [' '.join(parts[:2]), ' '.join(parts[2:])] if len(parts) > 2 else [name]
                ty = r.centery - len(text_lines) * 22 // 2
                for line in text_lines:
                    surf = font.render(line, True, (240, 240, 240))
                    screen.blit(surf, surf.get_rect(center=(r.centerx, ty)))
                    ty += 28
                if chosen == c['name']:
                    pygame.draw.rect(screen, (255, 215, 120), r.inflate(6, 6), 3, border_radius=14)
            else:
                pygame.draw.rect(screen, (36, 38, 42), r, border_radius=12)
                pygame.draw.rect(screen, (80, 80, 84), r, 2, border_radius=12)
                q = back_font.render('?', True, (180, 180, 190))
                screen.blit(q, q.get_rect(center=r.center))
        if chosen:
            pygame.draw.rect(screen, (50, 50, 50), confirm, border_radius=10)
            txt = pygame.font.SysFont(None, 32).render('CONFIRM', True, (235, 235, 235))
        else:
            pygame.draw.rect(screen, (35, 35, 35), confirm, border_radius=10)
            txt = pygame.font.SysFont(None, 32).render('CONFIRM', True, (120, 120, 120))
        screen.blit(txt, txt.get_rect(center=confirm.center))
        game.run_pending_menu_transition(screen)
        pygame.display.flip()
    while True:
        draw()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game.IS_WEB and is_web_interaction_event(ev):
                game._resume_bgm_if_needed(min_interval_s=0.0)
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                bg = screen.copy()
                pick = game.pause_from_overlay(screen, bg)
                if pick in (None, 'continue', 'settings'):
                    game.flush_events()
                    continue
                if pick == 'home':
                    game.queue_menu_transition(pygame.display.get_surface().copy())
                    game.flush_events()
                    return '__HOME__'
                if pick == 'restart':
                    game.queue_menu_transition(pygame.display.get_surface().copy())
                    game.flush_events()
                    return '__RESTART__'
                if pick == 'exit':
                    pygame.quit()
                    sys.exit()
            if ev.type == pygame.MOUSEBUTTONDOWN:
                if chosen is None:
                    for c in cards:
                        if c['rect'].collidepoint(ev.pos):
                            c['revealed'] = True
                            chosen = c['name']
                            break
                if chosen and confirm.collidepoint(ev.pos):
                    game.queue_menu_transition(pygame.display.get_surface().copy())
                    game.flush_events()
                    return chosen
        clock.tick(60)
