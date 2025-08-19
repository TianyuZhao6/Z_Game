import sys
import pygame
import math
import random
import json
import os
from queue import PriorityQueue
from typing import Dict, List, Set, Tuple, Optional


# --- Event queue helper to prevent ghost clicks ---
def flush_events():
    try:
        pygame.event.clear()
    except Exception:
        pass


# --- UI helper ---
def pause_settings_only(screen, background_surf):
    """
    Show the Pause menu but only let the player go into Settings and then come back.
    Returns only when the user chooses CONTINUE (or closes the menu).
    """
    while True:
        choice = show_pause_menu(screen, background_surf)
        if choice == 'settings':
            show_settings_popup(screen, background_surf)
            # when settings closes, show pause again
            continue
        # treat anything else as 'continue'
        break
    flush_events()


def pause_from_overlay(screen, bg_surface):
    # Show pause; loop when settings closes so we land back on pause.
    while True:
        choice = show_pause_menu(screen, bg_surface)
        if choice in (None, "continue"):
            return "continue"
        if choice == "settings":
            show_settings_popup(screen, bg_surface)
            flush_events()
            continue  # back to pause
        return choice  # "home" | "exit" | "restart"


# --- Font helper ---
def mono_font(size: int) -> "pygame.font.Font":
    # Try common monospaced fonts; fall back safely
    candidates = ["Consolas", "Menlo", "DejaVu Sans Mono", "Courier New", "monospace"]
    try:
        name = pygame.font.match_font(candidates)
        if name:
            return pygame.font.Font(name, size)
    except Exception:
        pass
    return pygame.font.SysFont("monospace", size)


def pause_game_modal(screen, bg_surface, clock, time_left):
    """
    Show Pause (and Settings) while freezing the survival timer.
    Returns (choice, updated_time_left) where choice is:
    'continue' | 'restart' | 'home' | 'exit'
    """
    # 1) start wall-clock for how long we stay paused
    pause_start_ms = pygame.time.get_ticks()

    # 2) loop Pause → (optional Settings) → back to Pause
    while True:
        choice = show_pause_menu(screen, bg_surface)
        if choice == 'settings':
            show_settings_popup(screen, bg_surface)
            flush_events()
            continue
        break

    globals()["_time_left_runtime"] = time_left  # keep HUD in sync

    # 4) reset the clock baseline so the next tick doesn't produce a huge dt
    clock.tick(60)
    flush_events()
    return choice, time_left

def resize_world_to_view():
    """Expand GRID_SIZE so the simulated world covers the whole visible area."""
    global GRID_SIZE, WINDOW_SIZE, TOTAL_HEIGHT
    # how many cells are visible horizontally/vertically
    cols_needed = math.ceil(VIEW_W / CELL_SIZE)
    rows_needed = math.ceil((VIEW_H - INFO_BAR_HEIGHT) / CELL_SIZE)
    # keep using a square grid; pick the max so both axes are covered
    new_size = max(GRID_SIZE, cols_needed, rows_needed)
    if new_size != GRID_SIZE:
        GRID_SIZE = new_size
        WINDOW_SIZE = GRID_SIZE * CELL_SIZE
        TOTAL_HEIGHT = WINDOW_SIZE + INFO_BAR_HEIGHT


# ==================== 游戏常量配置 ====================
# NOTE: Keep design notes & TODOs below; do not delete when refactoring.
# - Card system UI polish (later pass)
# - Sprite/animation pipeline to be added
# - Balance obstacle density via OBSTACLE_DENSITY/DECOR_DENSITY

GAME_TITLE = "Neuroscape: Mind Runner"
INFO_BAR_HEIGHT = 40
GRID_SIZE = 36
CELL_SIZE = 40
WINDOW_SIZE = GRID_SIZE * CELL_SIZE
TOTAL_HEIGHT = WINDOW_SIZE + INFO_BAR_HEIGHT
# Viewport (overridden at runtime when display is created)
VIEW_W = WINDOW_SIZE
VIEW_H = TOTAL_HEIGHT

OBSTACLE_HEALTH = 20
MAIN_BLOCK_HEALTH = 40
# --- map fill tuning ---
OBSTACLE_DENSITY = 0.14  # proportion of tiles to become obstacles (including clusters)
DECOR_DENSITY = 0.06  # proportion of tiles to place non-blocking decorations
MIN_ITEMS = 8  # ensure enough items on larger maps
DESTRUCTIBLE_RATIO = 0.3
PLAYER_SPEED = 5
ZOMBIE_SPEED = 2
ZOMBIE_ATTACK = 10
# ----- meta progression -----
SPOILS_PER_KILL = 3
SPOILS_PER_BLOCK = 1

XP_PLAYER_KILL = 6
XP_PLAYER_BLOCK = 2
XP_ZOMBIE_BLOCK = 3
XP_TRANSFER_RATIO = 0.7       # special → survivors

ZOMBIE_XP_TO_LEVEL = 15       # per level step for monsters
PLAYER_XP_TO_LEVEL = 20       # base; scales by +20%

ELITE_HP_MULT = 2.0
ELITE_ATK_MULT = 1.5
ELITE_SPD_ADD = 1

BOSS_EVERY_N_LEVELS = 5
BOSS_HP_MULT = 4.0
BOSS_ATK_MULT = 2.0
BOSS_SPD_ADD = 1

# persistent (per run) upgrades bought in shop
META = {"spoils": 0, "dmg": 0, "firerate_mult": 1.0, "speed": 0, "maxhp": 0}

# --- zombie type colors (for rendering) ---
ZOMBIE_COLORS = {
    "basic": (200, 70, 70),
    "fast": (255, 160, 60),
    "tank": (120, 180, 255),
    "strong": (220, 60, 140),
    "ranged": (255, 120, 50),
    "suicide": (255, 90, 90),
    "bomber": (255, 90, 90),
    "buffer": (80, 200, 140),
    "shielder": (60, 160, 255),
}

# --- wave spawning ---
SPAWN_INTERVAL = 8.0
SPAWN_BASE = 3
SPAWN_GROWTH = 1
ZOMBIE_CAP = 30
# --- new zombie types tuning ---
RANGED_COOLDOWN = 1.2  # 远程怪开火间隔
RANGED_PROJ_SPEED = 520.0
RANGED_PROJ_DAMAGE = 12

SUICIDE_FUSE = 4.0  # 自爆怪引信时长（生成后计时）
SUICIDE_FLICKER = 0.8  # 引信末端闪烁时长
SUICIDE_RADIUS = 90  # 自爆半径（像素）
SUICIDE_DAMAGE = 35  # 对玩家伤害

BUFF_RADIUS = 220  # 增益怪范围
BUFF_DURATION = 4.0
BUFF_COOLDOWN = 7.0
BUFF_ATK_MULT = 1.3  # 攻击乘区
BUFF_SPD_ADD = 1  # 额外速度（像素/帧）

SHIELD_RADIUS = 220  # 护盾怪范围
SHIELD_AMOUNT = 25  # 护盾值
SHIELD_DURATION = 5.0
SHIELD_COOLDOWN = 9.0
# --- combat tuning (Brotato-like) ---
FIRE_RATE = None  # shots per second; if None, derive from BULLET_SPACING_PX
BULLET_SPEED = 1000.0  # pixels per second (controls travel speed)
BULLET_SPACING_PX = 260.0  # desired spacing between bullets along their path
BULLET_RADIUS = 4
BULLET_DAMAGE_ZOMBIE = 12
BULLET_DAMAGE_BLOCK = 10
ENEMY_SHOT_DAMAGE_BLOCK = BULLET_DAMAGE_BLOCK
MAX_FIRE_RANGE = 800.0  # pixels
# --- survival mode & player health ---
LEVEL_TIME_LIMIT = 45.0  # seconds per run
PLAYER_MAX_HP = 40  # player total health
ZOMBIE_CONTACT_DAMAGE = 20  # damage per contact tick
PLAYER_HIT_COOLDOWN = 0.6  # seconds of i-frames after taking contact damage

# derive cooldown from either explicit FIRE_RATE or SPACING
if FIRE_RATE:
    FIRE_COOLDOWN = 1.0 / float(FIRE_RATE)
else:
    FIRE_COOLDOWN = float(BULLET_SPACING_PX) / float(BULLET_SPEED)

# Audio volumes (placeholders; no audio wired yet)
FX_VOLUME = 70  # 0-100
BGM_VOLUME = 60  # 0-100

CARD_POOL = ["zombie_fast", "zombie_strong", "zombie_tank"]

LEVELS = [
    {"obstacle_count": 15, "item_count": 3, "zombie_count": 1, "block_hp": 10, "zombie_types": ["basic"],
     "reward": "zombie_fast"},
    {"obstacle_count": 18, "item_count": 4, "zombie_count": 2, "block_hp": 15, "zombie_types": ["basic", "strong"],
     "reward": "zombie_strong"},
]

# 方向向量
DIRECTIONS = {
    pygame.K_a: (-1, 0),
    pygame.K_d: (1, 0),
    pygame.K_w: (0, -1),
    pygame.K_s: (0, 1),
}

# ==================== Save/Load Helpers ====================
BASE_DIR = os.path.dirname(__file__) if "__file__" in globals() else os.getcwd()
SAVE_DIR = os.path.join(BASE_DIR, "TEMP")
os.makedirs(SAVE_DIR, exist_ok=True)
SAVE_FILE = os.path.join(SAVE_DIR, "savegame.json")


# def save_progress(current_level: int, zombie_cards_collected: List[str]) -> None:
#     """Save lightweight meta progress (resume from level start)."""
#     data = {
#         "mode": "meta",
#         "version": 2,
#         "current_level": int(current_level),
#         "zombie_cards_collected": list(zombie_cards_collected),
#     }
#     try:
#         with open(SAVE_FILE, 'w', encoding='utf-8') as f:
#             json.dump(data, f)
#     except Exception as e:
#         print(f"[Save] Failed to write save file: {e}", file=sys.stderr)
def save_progress(current_level: int = 0,
                  zombie_cards_collected: Optional[List[str]] = None,
                  *,
                  max_wave_reached: Optional[int] = None) -> None:
    """
    极简存档：保留当前关卡号 + 本次达到的最大波次。
    不再写入卡池/快照等冗余数据；用于 Exit 后下次进入时“在同一关重新开局”。

    写入格式：
        {"mode":"wave","version":1,"current_level":<int>,"max_wave_reached":<int>}
    """
    try:
        # 优先使用参数；否则尝试从全局兜底；最后为 0
        if max_wave_reached is None:
            gw = globals().get("_max_wave_reached", None)
            if gw is None:
                gw = globals().get("_wave_index", None)
            max_wave_reached = int(gw) if gw is not None else 0
        else:
            max_wave_reached = int(max_wave_reached)

        data = {
            "mode": "wave",
            "version": 1,
            "current_level": int(current_level),
            "max_wave_reached": max(0, int(max_wave_reached)),
        }
        with open(SAVE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[Save] Failed to write wave save: {e}", file=sys.stderr)


def capture_snapshot(game_state, player, zombies, current_level: int, zombie_cards_collected: List[str],
                     chosen_zombie_type: str = "basic", bullets: Optional[List['Bullet']] = None) -> dict:
    """Create a full mid-run snapshot of the current game state."""
    snap = {
        "mode": "snapshot",
        "version": 3,
        "meta": {
            "current_level": int(current_level),
            "zombie_cards_collected": list(zombie_cards_collected),
            "chosen_zombie_type": str(chosen_zombie_type or "basic"),
        },
        "snapshot": {
            "player": {"x": float(player.x), "y": float(player.y),
                       "speed": player.speed, "size": player.size,
                       "fire_cd": float(getattr(player, "fire_cd", 0.0)),
                       "hp": int(getattr(player, "hp", PLAYER_MAX_HP)),
                       "max_hp": int(getattr(player, "max_hp", PLAYER_MAX_HP)),
                       "hit_cd": float(getattr(player, "hit_cd", 0.0))},
            "zombies": [{
                "x": float(z.x), "y": float(z.y),
                "attack": int(getattr(z, "attack", 10)),
                "speed": int(getattr(z, "speed", 2)),
                "type": str(getattr(z, "type", "basic")),
                "hp": int(getattr(z, "hp", 30)),
                "max_hp": int(getattr(z, "max_hp", getattr(z, "hp", 30))),
                "spawn_elapsed": float(getattr(z, "_spawn_elapsed", 0.0)),
                "attack_timer": float(getattr(z, "attack_timer", 0.0)),
            } for z in zombies],
            "obstacles": [{
                "x": int(ob.rect.x // CELL_SIZE),
                "y": int((ob.rect.y - INFO_BAR_HEIGHT) // CELL_SIZE),
                "type": ob.type,
                "health": None if ob.health is None else int(ob.health),
                "main": bool(getattr(ob, "is_main_block", False)),
            } for ob in game_state.obstacles.values()],
            "items": [{
                "x": int(it.x),
                "y": int(it.y),
                "is_main": bool(it.is_main),
            } for it in game_state.items],
            "decorations": [[int(dx), int(dy)] for (dx, dy) in getattr(game_state, "decorations", [])],
            "bullets": [{
                "x": float(b.x), "y": float(b.y),
                "vx": float(b.vx), "vy": float(b.vy),
                "traveled": float(b.traveled)
            } for b in (bullets or []) if getattr(b, "alive", True)],
            "time_left": float(globals().get("_time_left_runtime", LEVEL_TIME_LIMIT))
        }
    }
    return snap


def save_snapshot(snapshot: dict) -> None:
    """Write a snapshot dict to disk."""
    try:
        with open(SAVE_FILE, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f)
    except Exception as e:
        print(f"[Save] Failed to write snapshot: {e}", file=sys.stderr)


def load_save() -> Optional[dict]:
    """Load either meta or snapshot save; returns dict with 'mode' field or None."""
    try:
        if not os.path.exists(SAVE_FILE):
            return None
        with open(SAVE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        # v1 compatibility (no mode)
        if "mode" not in data:
            data["mode"] = "meta"
        # normalize fields
        if data["mode"] == "meta":
            data.setdefault("current_level", 0)
            data.setdefault("zombie_cards_collected", [])
        elif data["mode"] == "snapshot":
            data.setdefault("meta", {})
            data["meta"].setdefault("current_level", 0)
            data["meta"].setdefault("zombie_cards_collected", [])
            data["meta"].setdefault("chosen_zombie_type", "basic")
            data.setdefault("snapshot", {})
        return data
    except Exception as e:
        print(f"[Save] Failed to read save file: {e}", file=sys.stderr)
        return None


def has_save() -> bool:
    return os.path.exists(SAVE_FILE)


def clear_save() -> None:
    try:
        if os.path.exists(SAVE_FILE):
            os.remove(SAVE_FILE)
    except Exception as e:
        print(f"[Save] Failed to delete save file: {e}", file=sys.stderr)


# ==================== UI Helpers ====================
def draw_button(screen, label, pos, size=(180, 56), bg=(40, 40, 40), fg=(240, 240, 240), border=(15, 15, 15)):
    rect = pygame.Rect(pos, size)
    pygame.draw.rect(screen, border, rect.inflate(6, 6))
    pygame.draw.rect(screen, bg, rect)
    font = pygame.font.SysFont(None, 32)
    txt = font.render(label, True, fg)
    screen.blit(txt, txt.get_rect(center=rect.center))
    return rect


def door_transition(screen, color=(0, 0, 0), duration=500):
    door_width = VIEW_W // 2
    left_rect = pygame.Rect(0, 0, 0, VIEW_H)
    right_rect = pygame.Rect(VIEW_W, 0, 0, VIEW_H)
    clock = pygame.time.Clock()
    start_time = pygame.time.get_ticks()
    while True:
        elapsed = pygame.time.get_ticks() - start_time
        progress = min(1, elapsed / duration)
        lw = int(door_width * progress)
        rw = int(door_width * progress)
        left_rect.width = lw
        right_rect.x = VIEW_W - rw
        right_rect.width = rw
        screen.fill((0, 0, 0))
        pygame.draw.rect(screen, color, left_rect)
        pygame.draw.rect(screen, color, right_rect)
        pygame.display.flip()
        if progress >= 1: break
        clock.tick(60)
    flush_events()


def draw_settings_gear(screen, x, y):
    """Draw a simple gear icon at (x,y) top-left; returns its rect."""
    rect = pygame.Rect(x, y, 32, 24)
    # outer
    pygame.draw.rect(screen, (50, 50, 50), rect, 2)
    # gear: circle + spokes
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


def show_start_menu(screen):
    """Return a tuple ('new', None) or ('continue', save_data) based on player's choice."""
    flush_events()
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont(None, 64)
    subtitle_font = pygame.font.SysFont(None, 24)
    while True:
        # background stripes
        screen.fill((26, 28, 24))
        for i in range(0, VIEW_W, 40):
            pygame.draw.rect(screen, (32 + (i // 40 % 2) * 6, 34, 30), (i, 0, 40, VIEW_H))
        # title
        title = title_font.render(GAME_TITLE, True, (230, 230, 210))
        screen.blit(title, title.get_rect(center=(VIEW_W // 2, 140)))
        sub = subtitle_font.render("A pixel roguelite of memory and monsters", True, (160, 160, 150))
        screen.blit(sub, sub.get_rect(center=(VIEW_W // 2, 180)))

        # structured layout
        gap_x = 36
        top_y = 260
        btn_w = 180
        # START (left) and HOW TO PLAY (right)
        saved_exists = has_save()
        start_label = "START NEW" if saved_exists else "START"
        start_rect = draw_button(screen, start_label, (VIEW_W // 2 - btn_w - gap_x // 2, top_y))
        how_rect = draw_button(screen, "HOW TO PLAY", (VIEW_W // 2 + gap_x // 2, top_y))

        cont_rect = None
        next_y = top_y + 80
        if saved_exists:
            # Centered CONTINUE if save exists
            cont_rect = draw_button(screen, "CONTINUE", (VIEW_W // 2 - btn_w // 2, next_y))
            next_y += 80

        # EXIT centered at bottom
        exit_rect = draw_button(screen, "EXIT", (VIEW_W // 2 - btn_w // 2, next_y))

        gear_rect = draw_settings_gear(screen, VIEW_W - 44, 8)
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if gear_rect.collidepoint(event.pos):
                    show_settings_popup(screen, screen.copy())
                    flush_events()
                elif start_rect.collidepoint(event.pos):
                    door_transition(screen)
                    flush_events()
                    # Starting new game clears any existing save
                    return ("new", None)
                elif cont_rect and cont_rect.collidepoint(event.pos):
                    data = load_save()
                    if data:
                        door_transition(screen)
                        flush_events()
                        return ("continue", data)
                elif exit_rect.collidepoint(event.pos):
                    pygame.quit()
                    sys.exit()
                elif how_rect.collidepoint(event.pos):
                    show_help(screen)
                    flush_events()
        clock.tick(60)


def show_help(screen):
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 28)
    big = pygame.font.SysFont(None, 40)
    while True:
        screen.fill((18, 18, 18))
        screen.blit(big.render("How to Play", True, (240, 240, 240)), (40, 40))
        lines = [
            "WASD to move. Survive until the timer hits 00:00 to win.",
            "Breakable yellow blocks block the final fragment (secondary).",
            "Zombies deal contact damage. Avoid or kite them.",
            "Auto-fire targets the closest enemy/block in range.",
            "Transitions use the classic 'two doors' animation."
        ]
        y = 100
        for s in lines:
            screen.blit(font.render(s, True, (200, 200, 200)), (40, y))
            y += 36
        back = draw_button(screen, "BACK", (VIEW_W // 2 - 90, VIEW_H - 120))
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                door_transition(screen)
                flush_events()
                return
            if event.type == pygame.MOUSEBUTTONDOWN and back.collidepoint(event.pos):
                door_transition(screen)
                flush_events()
                return
        clock.tick(60)


def show_fail_screen(screen, background_surf):
    dim = pygame.Surface((VIEW_W, VIEW_H))
    dim.set_alpha(180)
    dim.fill((0, 0, 0))
    screen.blit(pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H)), (0, 0))
    screen.blit(dim, (0, 0))
    title = pygame.font.SysFont(None, 80).render("YOU WERE CORRUPTED!", True, (255, 60, 60))
    screen.blit(title, title.get_rect(center=(VIEW_W // 2, 140)))
    retry = draw_button(screen, "RETRY", (VIEW_W // 2 - 200, 300))
    home = draw_button(screen, "HOME", (VIEW_W // 2 + 20, 300))
    pygame.display.flip()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                bg = pygame.display.get_surface().copy()
                pick = pause_from_overlay(screen, bg)
                if pick == "continue":
                    # Repaint this Fail screen and keep waiting for input
                    return_to_fail = True
                    # Re-draw the same Fail UI:
                    dim = pygame.Surface((VIEW_W, VIEW_H))
                    dim.set_alpha(180)
                    dim.fill((0, 0, 0))
                    screen.blit(pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H)), (0, 0))
                    screen.blit(dim, (0, 0))
                    title = pygame.font.SysFont(None, 80).render("YOU WERE CORRUPTED!", True, (255, 60, 60))
                    screen.blit(title, title.get_rect(center=(VIEW_W // 2, 140)))
                    retry = draw_button(screen, "RETRY", (VIEW_W // 2 - 200, 300))
                    home = draw_button(screen, "HOME", (VIEW_W // 2 + 20, 300))
                    pygame.display.flip()
                    continue
                if pick == "home":  door_transition(screen); flush_events(); return "home"
                if pick == "restart": door_transition(screen); flush_events(); return "retry"
                if pick == "exit": pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if retry.collidepoint(event.pos): door_transition(screen); flush_events(); return "retry"
                if home.collidepoint(event.pos): door_transition(screen); flush_events(); return "home"


def show_success_screen(screen, background_surf, reward_choices):
    dim = pygame.Surface((VIEW_W, VIEW_H))
    dim.set_alpha(150)
    dim.fill((0, 0, 0))
    screen.blit(pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H)), (0, 0))
    screen.blit(dim, (0, 0))
    title = pygame.font.SysFont(None, 80).render("MEMORY RESTORED!", True, (0, 255, 120))
    screen.blit(title, title.get_rect(center=(VIEW_W // 2, 100)))
    card_rects = []
    for i, card in enumerate(reward_choices):
        x = VIEW_W // 2 - (len(reward_choices) * 140) // 2 + i * 140
        rect = pygame.Rect(x, 180, 120, 160)
        pygame.draw.rect(screen, (220, 220, 220), rect)
        name = pygame.font.SysFont(None, 24).render(card.replace("_", " ").upper(), True, (20, 20, 20))
        screen.blit(name, name.get_rect(center=(rect.centerx, rect.bottom - 18)))
        pygame.draw.rect(screen, (40, 40, 40), rect, 3)
        pygame.draw.rect(screen, (70, 90, 90), rect.inflate(-30, -50))
        card_rects.append((rect, card))
    next_btn = draw_button(screen, "CONFIRM", (VIEW_W // 2 - 90, 370))
    chosen = None
    pygame.display.flip()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                bg = pygame.display.get_surface().copy()
                pick = pause_from_overlay(screen, bg)  # 只在暂停菜单里设置→返回暂停→继续
                if pick == "continue":
                    # —— 重新绘制“成功界面”，而不是失败界面 ——
                    dim = pygame.Surface((VIEW_W, VIEW_H))
                    dim.set_alpha(150)
                    dim.fill((0, 0, 0))
                    screen.blit(pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H)), (0, 0))
                    screen.blit(dim, (0, 0))
                    title = pygame.font.SysFont(None, 80).render("MEMORY RESTORED!", True, (0, 255, 120))
                    screen.blit(title, title.get_rect(center=(VIEW_W // 2, 100)))

                    card_rects = []
                    for i, card in enumerate(reward_choices):
                        x = VIEW_W // 2 - (len(reward_choices) * 140) // 2 + i * 140
                        rect = pygame.Rect(x, 180, 120, 160)
                        pygame.draw.rect(screen, (220, 220, 220), rect)
                        name = pygame.font.SysFont(None, 24).render(card.replace("_", " ").upper(), True, (20, 20, 20))
                        screen.blit(name, name.get_rect(center=(rect.centerx, rect.bottom - 18)))
                        pygame.draw.rect(screen, (40, 40, 40), rect, 3)
                        pygame.draw.rect(screen, (70, 90, 90), rect.inflate(-30, -50))
                        card_rects.append((rect, card))

                    next_btn = draw_button(screen, "CONFIRM", (VIEW_W // 2 - 90, 370))
                    pygame.display.flip()
                    continue  # 回到本界面等待点击
                if pick == "home":
                    door_transition(screen)
                    flush_events()
                    return "home"  # 让上层逻辑去处理“回主页”
                if pick == "restart":
                    door_transition(screen)
                    flush_events()
                    return "restart"  # 让上层逻辑去处理“重开本关”
                if pick == "exit":
                    pygame.quit()
                    sys.exit()

            if event.type == pygame.MOUSEBUTTONDOWN:
                for rect, card in card_rects:
                    if rect.collidepoint(event.pos): chosen = card
                if next_btn.collidepoint(event.pos) and (chosen or len(reward_choices) == 0):
                    door_transition(screen)
                    flush_events()
                    return chosen


def show_pause_menu(screen, background_surf):
    """Draw pause overlay and return an action tag."""
    dim = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 170))
    bg_scaled = pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H))
    screen.blit(bg_scaled, (0, 0))
    screen.blit(dim, (0, 0))

    panel_w, panel_h = min(520, VIEW_W - 80), min(500, VIEW_H - 160)
    panel = pygame.Rect(0, 0, panel_w, panel_h)
    panel.center = (VIEW_W // 2, VIEW_H // 2)
    pygame.draw.rect(screen, (30, 30, 30), panel, border_radius=16)
    pygame.draw.rect(screen, (60, 60, 60), panel, width=3, border_radius=16)

    title = pygame.font.SysFont(None, 72).render("Paused", True, (230, 230, 230))
    screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 58)))

    btn_w, btn_h = 300, 56
    spacing = 14
    start_y = panel.top + 110
    btns = []
    labels = [("CONTINUE", "continue"),
              ("RESTART", "restart"),
              ("SETTINGS", "settings"),
              ("BACK TO HOMEPAGE", "home"),
              ("EXIT GAME (Save & Quit)", "exit")]
    for i, (label, tag) in enumerate(labels):
        x = panel.centerx - btn_w // 2
        y = start_y + i * (btn_h + spacing)
        rect = pygame.Rect(x, y, btn_w, btn_h)
        pygame.draw.rect(screen, (15, 15, 15), rect.inflate(6, 6), border_radius=10)
        if tag == "exit":
            pygame.draw.rect(screen, (120, 40, 40), rect, border_radius=10)
        else:
            pygame.draw.rect(screen, (50, 50, 50), rect, border_radius=10)
        txt = pygame.font.SysFont(None, 32).render(label, True, (235, 235, 235))
        screen.blit(txt, txt.get_rect(center=rect.center))
        btns.append((rect, tag))

    pygame.display.flip()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                flush_events()
                return "continue"
            if event.type == pygame.MOUSEBUTTONDOWN:
                for rect, tag in btns:
                    if rect.collidepoint(event.pos):
                        flush_events()
                        return tag


def show_settings_popup(screen, background_surf):
    """Volume settings with LIVE BGM updates and proper slider dragging/visual refresh."""
    global FX_VOLUME, BGM_VOLUME

    clock = pygame.time.Clock()

    # background overlay
    dim = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 170))
    bg_scaled = pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H))

    panel_w, panel_h = min(520, VIEW_W - 80), min(360, VIEW_H - 160)
    panel = pygame.Rect(0, 0, panel_w, panel_h)
    panel.center = (VIEW_W // 2, VIEW_H // 2)

    title_font = pygame.font.SysFont(None, 56)
    font = pygame.font.SysFont(None, 30)
    btn_font = pygame.font.SysFont(None, 32)

    # local working values
    fx_val = int(FX_VOLUME)
    bgm_val = int(BGM_VOLUME)

    dragging = None  # None | "fx" | "bgm"

    def draw_slider(label, value, top_y):
        # label
        screen.blit(font.render(f"{label}: {value}", True, (230, 230, 230)), (panel.left + 40, top_y))
        # bar
        bar = pygame.Rect(panel.left + 40, top_y + 26, panel_w - 80, 10)
        knob_x = bar.x + int((value / 100) * bar.width)
        pygame.draw.rect(screen, (80, 80, 80), bar, border_radius=6)
        pygame.draw.circle(screen, (220, 220, 220), (knob_x, bar.y + 5), 8)
        return bar

    def val_from_bar(bar, mx):
        return max(0, min(100, int(((mx - bar.x) / max(1, bar.width)) * 100)))

    def draw_ui():
        # background & panel
        screen.blit(bg_scaled, (0, 0))
        screen.blit(dim, (0, 0))
        pygame.draw.rect(screen, (30, 30, 30), panel, border_radius=16)
        pygame.draw.rect(screen, (60, 60, 60), panel, width=3, border_radius=16)

        # title
        screen.blit(title_font.render("Settings", True, (230, 230, 230)),
                    (panel.centerx - 110, panel.top + 40))

        # sliders
        nonlocal fx_bar, bgm_bar, close_btn
        fx_bar = draw_slider("Effects Volume", fx_val, panel.top + 110)
        bgm_bar = draw_slider("BGM Volume", bgm_val, panel.top + 160)

        # close button
        btn_w, btn_h = 200, 56
        close_btn = pygame.Rect(0, 0, btn_w, btn_h)
        close_btn.center = (panel.centerx, panel.bottom - 50)
        pygame.draw.rect(screen, (15, 15, 15), close_btn.inflate(6, 6), border_radius=10)
        pygame.draw.rect(screen, (50, 50, 50), close_btn, border_radius=10)
        ctxt = btn_font.render("CLOSE", True, (235, 235, 235))
        screen.blit(ctxt, ctxt.get_rect(center=close_btn.center))

        pygame.display.flip()

    # initial draw
    fx_bar = bgm_bar = close_btn = None
    draw_ui()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit();
                sys.exit()

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                # keep current values and exit
                FX_VOLUME = fx_val;
                BGM_VOLUME = bgm_val
                if "_bgm" in globals() and getattr(_bgm, "set_volume", None):
                    _bgm.set_volume(BGM_VOLUME / 100.0)
                flush_events()
                return "close"

            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if fx_bar and fx_bar.collidepoint((mx, my)):
                    fx_val = val_from_bar(fx_bar, mx)
                    FX_VOLUME = fx_val  # live apply for future SFX
                    dragging = "fx"
                elif bgm_bar and bgm_bar.collidepoint((mx, my)):
                    bgm_val = val_from_bar(bgm_bar, mx)
                    BGM_VOLUME = bgm_val
                    if "_bgm" in globals() and getattr(_bgm, "set_volume", None):
                        _bgm.set_volume(BGM_VOLUME / 100.0)  # LIVE apply
                    dragging = "bgm"
                elif close_btn and close_btn.collidepoint((mx, my)):
                    FX_VOLUME = fx_val;
                    BGM_VOLUME = bgm_val
                    if "_bgm" in globals() and getattr(_bgm, "set_volume", None):
                        _bgm.set_volume(BGM_VOLUME / 100.0)
                    flush_events()
                    return "close"

            if event.type == pygame.MOUSEBUTTONUP:
                dragging = None

            if event.type == pygame.MOUSEMOTION and dragging:
                mx, my = event.pos
                if dragging == "fx" and fx_bar:
                    fx_val = val_from_bar(fx_bar, mx)
                    FX_VOLUME = fx_val
                elif dragging == "bgm" and bgm_bar:
                    bgm_val = val_from_bar(bgm_bar, mx)
                    BGM_VOLUME = bgm_val
                    if "_bgm" in globals() and getattr(_bgm, "set_volume", None):
                        _bgm.set_volume(BGM_VOLUME / 100.0)  # LIVE apply

        # redraw each frame for smooth knob follow
        draw_ui()
        clock.tick(60)

def show_shop_screen(screen) -> None:
    """Spend META['spoils'] on small upgrades. Press CLOSE to continue."""
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 30)
    title = pygame.font.SysFont(None, 56)

    # pseudo-random offers
    catalog = [
        {"name": "+1 Damage",       "cost": 6, "apply": lambda: META.update(dmg=META["dmg"] + 1)},
        {"name": "+5% Fire Rate",  "cost": 7, "apply": lambda: META.update(firerate_mult=META["firerate_mult"] * 1.10)},
        {"name": "+1 Speed",        "cost": 8, "apply": lambda: META.update(speed=META["speed"] + 1)},
        {"name": "+5 Max HP",       "cost": 8, "apply": lambda: META.update(maxhp=META["maxhp"] + 5)},
        {"name": "Reroll Offers",   "cost": 3, "apply": "reroll"},
    ]
    def roll_offers():
        pool = [c for c in catalog if c["name"] != "Reroll Offers"]
        offers = random.sample(pool, k=min(4, len(pool)))
        offers.append(next(c for c in catalog if c["name"] == "Reroll Offers"))
        return offers
    offers = roll_offers()

    while True:
        screen.fill((16, 16, 18))
        screen.blit(title.render("TRADER", True, (235, 235, 235)), (VIEW_W//2 - 90, 80))
        money = font.render(f"Spoils: {META['spoils']}", True, (255, 230, 120))
        screen.blit(money, (VIEW_W//2 - 70, 130))

        rects = []
        start_x = VIEW_W//2 - 2*160 + 20
        y = 200
        for i, it in enumerate(offers):
            r = pygame.Rect(start_x + i*160, y, 150, 120)
            pygame.draw.rect(screen, (40, 40, 42), r, border_radius=10)
            pygame.draw.rect(screen, (80, 80, 84), r, 2, border_radius=10)
            name = font.render(it["name"], True, (230, 230, 230))
            cost = font.render(f"{it['cost']}¥", True, (255, 210, 130))
            screen.blit(name, (r.x + 10, r.y + 18))
            screen.blit(cost, (r.x + 10, r.y + 60))
            rects.append((r, it))

        close = pygame.Rect(VIEW_W//2 - 100, 360, 200, 56)
        pygame.draw.rect(screen, (50, 50, 50), close, border_radius=10)
        ctxt = pygame.font.SysFont(None, 32).render("CLOSE", True, (235, 235, 235))
        screen.blit(ctxt, ctxt.get_rect(center=close.center))

        pygame.display.flip()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT: pygame.quit(); sys.exit()
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                return
            if ev.type == pygame.MOUSEBUTTONDOWN:
                if close.collidepoint(ev.pos):
                    return
                for r, it in rects:
                    if r.collidepoint(ev.pos):
                        if META["spoils"] >= it["cost"]:
                            META["spoils"] -= it["cost"]
                            if it["apply"] == "reroll":
                                offers = roll_offers()
                            else:
                                it["apply"]()
        clock.tick(60)


# ==================== 数据结构 ====================
class Graph:
    def __init__(self):
        self.edges: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        self.weights: Dict[Tuple[Tuple[int, int], Tuple[int, int]], float] = {}

    def add_edge(self, a, b, w):
        self.edges.setdefault(a, []).append(b)
        self.weights[(a, b)] = w

    def neighbors(self, node): return self.edges.get(node, [])

    def cost(self, a, b): return self.weights.get((a, b), float('inf'))


class Obstacle:
    def __init__(self, x: int, y: int, obstacle_type: str, health: Optional[int] = None):
        px = x * CELL_SIZE;
        py = y * CELL_SIZE + INFO_BAR_HEIGHT
        self.rect = pygame.Rect(px, py, CELL_SIZE, CELL_SIZE)
        self.type: str = obstacle_type
        self.health: Optional[int] = health

    def is_destroyed(self) -> bool:
        return self.type == "Destructible" and self.health <= 0

    @property
    def grid_pos(self):
        return self.rect.x // CELL_SIZE, (self.rect.y - INFO_BAR_HEIGHT) // CELL_SIZE


class MainBlock(Obstacle):
    def __init__(self, x: int, y: int, health: Optional[int] = MAIN_BLOCK_HEALTH):
        super().__init__(x, y, "Destructible", health)
        self.is_main_block = True


class Item:
    def __init__(self, x: int, y: int, is_main=False):
        self.x = x
        self.y = y
        self.is_main = is_main
        self.radius = CELL_SIZE // 3
        self.center = (self.x * CELL_SIZE + CELL_SIZE // 2, self.y * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT)
        self.rect = pygame.Rect(self.center[0] - self.radius, self.center[1] - self.radius, self.radius * 2,
                                self.radius * 2)


class Player:
    def __init__(self, pos: Tuple[int, int], speed: int = PLAYER_SPEED):
        self.x = pos[0] * CELL_SIZE
        self.y = pos[1] * CELL_SIZE
        self.speed = speed
        self.size = CELL_SIZE - 6
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)
        self.max_hp = int(PLAYER_MAX_HP)
        self.hp = int(PLAYER_MAX_HP)
        self.hit_cd = 0.0  # contact invulnerability timer (seconds)
        # progression
        self.level = 1
        self.xp = 0
        self.xp_to_next = PLAYER_XP_TO_LEVEL

        # per-run upgrades from shop (applied on spawn)
        self.bullet_damage = BULLET_DAMAGE_ZOMBIE + META.get("dmg", 0)
        self.fire_rate_mult = META.get("firerate_mult", 1.0)
        self.speed += META.get("speed", 0)
        self.max_hp += META.get("maxhp", 0)
        self.hp = min(self.hp + META.get("maxhp", 0), self.max_hp)

    @property
    def pos(self):
        return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)

    def move(self, keys, obstacles):
        dx = dy = 0
        if keys[pygame.K_w]: dy -= 1
        if keys[pygame.K_s]: dy += 1
        if keys[pygame.K_a]: dx -= 1
        if keys[pygame.K_d]: dx += 1
        if dx and dy: dx *= 0.7071; dy *= 0.7071
        # axis separated for smooth sliding
        nx = self.x + dx * self.speed
        rect_x = pygame.Rect(int(nx), int(self.y) + INFO_BAR_HEIGHT, self.size, self.size)
        for ob in obstacles.values():
            if rect_x.colliderect(ob.rect):
                if dx > 0:
                    nx = ob.rect.left - self.size
                elif dx < 0:
                    nx = ob.rect.right
                break
        self.x = max(0, min(nx, GRID_SIZE * CELL_SIZE - self.size))
        ny = self.y + dy * self.speed
        rect_y = pygame.Rect(int(self.x), int(ny) + INFO_BAR_HEIGHT, self.size, self.size)
        for ob in obstacles.values():
            if rect_y.colliderect(ob.rect):
                if dy > 0:
                    ny = ob.rect.top - self.size - INFO_BAR_HEIGHT
                elif dy < 0:
                    ny = ob.rect.bottom - INFO_BAR_HEIGHT
                break
        self.y = max(0, min(ny, GRID_SIZE * CELL_SIZE - self.size))
        self.rect.x = int(self.x)
        self.rect.y = int(self.y) + INFO_BAR_HEIGHT

    def fire_cooldown(self) -> float:
        # smaller is faster; clamp to avoid abuse
        return FIRE_COOLDOWN / max(0.25, float(self.fire_rate_mult))

    def add_xp(self, amount: int):
        self.xp += int(max(0, amount))
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.level += 1
            self.xp_to_next = int(self.xp_to_next * 1.2 + 0.5)
            # simple level-up buffs
            self.bullet_damage += 1
            self.max_hp += 2
            self.hp = min(self.hp + 2, self.max_hp)

    def draw(self, screen):
        pygame.draw.rect(screen, (0, 255, 0), self.rect)


class Zombie:
    def __init__(self, pos: Tuple[int, int], attack: int = ZOMBIE_ATTACK, speed: int = ZOMBIE_SPEED,
                 ztype: str = "basic", hp: Optional[int] = None):
        self.x = pos[0] * CELL_SIZE
        self.y = pos[1] * CELL_SIZE
        self.attack = attack
        self.speed = speed
        self.type = ztype
        # === special type state ===
        self.fuse = SUICIDE_FUSE if ztype in ("suicide", "bomber") else None
        self.buff_cd = 0.0 if ztype == "buffer" else None
        self.shield_cd = 0.0 if ztype == "shielder" else None
        self.shield_hp = 0  # 当前护盾值
        self.shield_t = 0.0  # 护盾剩余时间
        self.ranged_cd = 0.0 if ztype in ("ranged", "spitter") else None
        self.buff_t = 0.0  # 自身被增益剩余时间
        self.buff_atk_mult = 1.0
        self.buff_spd_add = 0
        # XP & rank
        self.z_level = 1
        self.xp = 0
        self.xp_to_next = ZOMBIE_XP_TO_LEVEL
        self.is_elite = False
        self.is_boss = False

        base_hp = 30 if hp is None else hp
        # type tweaks
        if ztype == "fast":
            self.speed = max(int(self.speed + 1), int(self.speed * 1.5))
            base_hp = int(base_hp * 0.7)
        if ztype == "tank":
            self.attack = int(self.attack * 0.6)
            base_hp = int(base_hp * 1.8)
        self.hp = max(1, base_hp)
        self.max_hp = self.hp
        self.size = CELL_SIZE - 6
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)
        self.spawn_delay = 0.6
        self._spawn_elapsed = 0.0

    @property
    def pos(self):
        return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)

    def gain_xp(self, amount: int):
        self.xp += int(max(0, amount))
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.z_level += 1
            self.xp_to_next = int(self.xp_to_next * 1.25 + 0.5)
            # small stat bumps
            self.attack = int(self.attack * 1.08 + 1)
            self.max_hp = int(self.max_hp * 1.10 + 1)
            self.hp = min(self.max_hp, self.hp + 2)
            self.speed += 0  # keep speed mostly stable (change if you want)

    def move_and_attack(self, player, obstacles, game_state, attack_interval=0.5, dt=1 / 60):
        base_attack = self.attack
        base_speed = self.speed
        # 应用来自 buffer 的临时增益
        if getattr(self, "buff_t", 0.0) > 0.0:
            base_attack = int(base_attack * getattr(self, "buff_atk_mult", 1.0))
            base_speed = base_speed + int(getattr(self, "buff_spd_add", 0))
            self.buff_t = max(0.0, self.buff_t - dt)

        speed = base_speed

        if not hasattr(self, 'attack_timer'): self.attack_timer = 0
        self.attack_timer += dt
        # initial spawn delay
        if self._spawn_elapsed < self.spawn_delay:
            self._spawn_elapsed += dt
            return
        dx = player.x - self.x
        dy = player.y - self.y
        speed = self.speed
        dirs = []
        if abs(dx) > abs(dy):
            dirs = [(sign(dx), 0), (0, sign(dy)), (sign(dx), sign(dy)), (-sign(dx), 0), (0, -sign(dy))]
        else:
            dirs = [(0, sign(dy)), (sign(dx), 0), (sign(dx), sign(dy)), (0, -sign(dy)), (-sign(dx), 0)]
        for ddx, ddy in dirs:
            if ddx == 0 and ddy == 0: continue
            next_rect = self.rect.move(ddx * speed, ddy * speed)
            blocked = False
            for ob in obstacles:
                if next_rect.colliderect(ob.rect):
                    if ob.type == "Destructible":
                        if self.attack_timer >= attack_interval:
                            ob.health -= self.attack
                            self.attack_timer = 0
                            if ob.health <= 0:
                                gp = ob.grid_pos
                                if gp in game_state.obstacles: del game_state.obstacles[gp]
                                game_state.spoils_gained += SPOILS_PER_BLOCK
                                self.gain_xp(XP_ZOMBIE_BLOCK)

                        blocked = True
                        break
                    elif ob.type == "Indestructible":
                        blocked = True
                        break
            if not blocked:
                self.x += ddx * speed
                self.y += ddy * speed
                self.rect.x = int(self.x)
                self.rect.y = int(self.y) + INFO_BAR_HEIGHT
                break

    def update_special(self, dt: float, player: 'Player', zombies: List['Zombie'],
                       enemy_shots: List['EnemyShot']):
        # 远程怪：发射投射物
        if self.type in ("ranged", "spitter"):
            self.ranged_cd = max(0.0, (self.ranged_cd or 0.0) - dt)
            if self.ranged_cd <= 0.0:
                # 朝玩家中心发射
                cx, cy = self.rect.centerx, self.rect.centery
                px, py = player.rect.centerx, player.rect.centery
                dx, dy = px - cx, py - cy
                L = (dx * dx + dy * dy) ** 0.5 or 1.0
                vx, vy = dx / L * RANGED_PROJ_SPEED, dy / L * RANGED_PROJ_SPEED
                enemy_shots.append(EnemyShot(cx, cy, vx, vy, RANGED_PROJ_DAMAGE))
                self.ranged_cd = RANGED_COOLDOWN

        # 自爆怪：引信倒计时，到时爆炸
        if self.type in ("suicide", "bomber"):
            if self.fuse is None: self.fuse = SUICIDE_FUSE
            self.fuse -= dt
            if self.fuse <= 0.0:
                # 结算爆炸
                cx, cy = self.rect.centerx, self.rect.centery
                pr = player.rect
                dx = pr.centerx - cx
                dy = pr.centery - cy
                if (dx * dx + dy * dy) ** 0.5 <= SUICIDE_RADIUS:
                    if player.hit_cd <= 0.0:
                        player.hp -= SUICIDE_DAMAGE
                        player.hit_cd = float(PLAYER_HIT_COOLDOWN)
                # （可选）对其它僵尸/可破坏障碍造成伤害，这里省略
                self.hp = 0  # 自身消失

        # 增益怪：周期性为周围友军加 BUFF
        if self.type == "buffer":
            self.buff_cd = max(0.0, (self.buff_cd or 0.0) - dt)
            if self.buff_cd <= 0.0:
                cx, cy = self.rect.centerx, self.rect.centery
                for z in zombies:
                    zx, zy = z.rect.centerx, z.rect.centery
                    if (zx - cx) ** 2 + (zy - cy) ** 2 <= BUFF_RADIUS ** 2:
                        z.buff_t = BUFF_DURATION
                        z.buff_atk_mult = BUFF_ATK_MULT
                        z.buff_spd_add = BUFF_SPD_ADD
                self.buff_cd = BUFF_COOLDOWN

        # 护盾怪：周期性给周围友军加护盾
        if self.type == "shielder":
            self.shield_cd = max(0.0, (self.shield_cd or 0.0) - dt)
            # 同时衰减自身护盾
            if self.shield_hp > 0:
                self.shield_t -= dt
                if self.shield_t <= 0:
                    self.shield_hp = 0
            if self.shield_cd <= 0.0:
                cx, cy = self.rect.centerx, self.rect.centery
                for z in zombies:
                    zx, zy = z.rect.centerx, z.rect.centery
                    if (zx - cx) ** 2 + (zy - cy) ** 2 <= SHIELD_RADIUS ** 2:
                        z.shield_hp = SHIELD_AMOUNT
                        z.shield_t = SHIELD_DURATION
                self.shield_cd = SHIELD_COOLDOWN

    def draw(self, screen):
        color = ZOMBIE_COLORS.get(getattr(self, "type", "basic"), (255, 60, 60))
        pygame.draw.rect(screen, color, self.rect)


class Bullet:
    def __init__(self, x: float, y: float, vx: float, vy: float, max_dist: float = MAX_FIRE_RANGE, damage: int = BULLET_DAMAGE_ZOMBIE):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.alive = True
        self.traveled = 0.0
        self.max_dist = max_dist
        self.damage = int(damage)

    def update(self, dt: float, game_state: 'GameState', zombies: List['Zombie'], player: 'Player' = None):
        if not self.alive: return
        nx = self.x + self.vx * dt
        ny = self.y + self.vy * dt
        self.traveled += ((nx - self.x) ** 2 + (ny - self.y) ** 2) ** 0.5
        self.x, self.y = nx, ny
        if self.traveled >= self.max_dist:
            self.alive = False;
            return

        r = pygame.Rect(int(self.x - BULLET_RADIUS), int(self.y - BULLET_RADIUS), BULLET_RADIUS * 2, BULLET_RADIUS * 2)

        # 1) zombies
        for z in list(zombies):
            if r.colliderect(z.rect):
                # shield first
                if getattr(z, "shield_hp", 0) > 0:
                    z.shield_hp -= self.damage
                    if z.shield_hp < 0:
                        z.hp += z.shield_hp
                        z.shield_hp = 0
                else:
                    z.hp -= self.damage

                if z.hp <= 0:
                    # spoils & player XP
                    game_state.spoils_gained += SPOILS_PER_KILL
                    if player: player.add_xp(XP_PLAYER_KILL + max(0, z.z_level - 1) * 2)

                    # XP inheritance: dead special gives a portion of XP to survivors
                    if getattr(z, "is_elite", False) or getattr(z, "is_boss", False):
                        if zombies:
                            portion = int(z.xp * XP_TRANSFER_RATIO)
                            if portion > 0:
                                share = max(1, portion // len(zombies))
                                for zz in zombies:
                                    if zz is not z:
                                        zz.gain_xp(share)

                    zombies.remove(z)
                self.alive = False
                return

        # 2) obstacles
        for gp, ob in list(game_state.obstacles.items()):
            if r.colliderect(ob.rect):
                if ob.type == "Indestructible":
                    self.alive = False;
                    return
                elif ob.type == "Destructible":
                    ob.health = (ob.health or 0) - BULLET_DAMAGE_BLOCK
                    if ob.health <= 0:
                        del game_state.obstacles[gp]
                        game_state.spoils_gained += SPOILS_PER_BLOCK
                        if player: player.add_xp(XP_PLAYER_BLOCK)
                    self.alive = False;
                    return

    def draw(self, screen, cam_x, cam_y):
        pygame.draw.circle(screen, (255, 255, 255), (int(self.x - cam_x), int(self.y - cam_y)), BULLET_RADIUS)


class EnemyShot:
    def __init__(self, x: float, y: float, vx: float, vy: float, dmg: int, max_dist: float = MAX_FIRE_RANGE):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.dmg = int(dmg)
        self.traveled = 0.0
        self.max_dist = max_dist
        self.alive = True

    def update(self, dt: float, player: 'Player', game_state: 'GameState'):
        if not self.alive:
            return

        # 运动
        nx = self.x + self.vx * dt
        ny = self.y + self.vy * dt
        self.traveled += ((nx - self.x) ** 2 + (ny - self.y) ** 2) ** 0.5
        self.x, self.y = nx, ny
        if self.traveled >= self.max_dist:
            self.alive = False
            return

        # 本帧碰撞 AABB
        r = pygame.Rect(int(self.x - BULLET_RADIUS), int(self.y - BULLET_RADIUS),
                        BULLET_RADIUS * 2, BULLET_RADIUS * 2)

        # 1) 先撞障碍（会阻挡子弹）
        for gp, ob in list(game_state.obstacles.items()):
            if r.colliderect(ob.rect):
                # 伤害数值（主方块与可破坏块统一，若需要可单独给主方块一个常量）
                dmg_block = int(globals().get("ENEMY_SHOT_DAMAGE_BLOCK", BULLET_DAMAGE_BLOCK))

                # 主方块：现在可受伤
                if getattr(ob, 'is_main_block', False):
                    # 主方块有 health
                    ob.health = (ob.health or 0) - dmg_block
                    if ob.health <= 0:
                        # 移除主方块（下方主碎片若有，将自然暴露）
                        del game_state.obstacles[gp]
                    self.alive = False
                    return

                # 不可破坏：只阻挡不掉血
                if getattr(ob, "type", None) == "Indestructible":
                    self.alive = False
                    return

                # 可破坏：扣血→可能打碎
                if getattr(ob, "type", None) == "Destructible":
                    ob.health = (ob.health or 0) - dmg_block
                    if ob.health <= 0:
                        del game_state.obstacles[gp]
                    self.alive = False
                    return

                # 其他未知类型：默认阻挡
                self.alive = False
                return

        # 2) 再判玩家
        if r.colliderect(player.rect):
            if getattr(player, "hit_cd", 0.0) <= 0.0:
                player.hp -= self.dmg
                if player.hp < 0:
                    player.hp = 0
                player.hit_cd = float(PLAYER_HIT_COOLDOWN)
            self.alive = False

    def draw(self, screen, cam_x, cam_y):
        pygame.draw.circle(screen, (255, 120, 50), (int(self.x - cam_x), int(self.y - cam_y)), BULLET_RADIUS)


# ==================== 算法函数 ====================

def sign(v): return 1 if v > 0 else (-1 if v < 0 else 0)


def heuristic(a, b): return abs(a[0] - b[0]) + abs(a[1] - b[1])


def a_star_search(graph: Graph, start: Tuple[int, int], goal: Tuple[int, int],
                  obstacles: Dict[Tuple[int, int], Obstacle]):
    frontier = PriorityQueue()
    frontier.put((0, start))
    came_from = {start: None}
    cost_so_far = {start: 0}
    while not frontier.empty():
        _, current = frontier.get()
        if current == goal: break
        for neighbor in graph.neighbors(current):
            new_cost = cost_so_far[current] + graph.cost(current, neighbor)
            if neighbor in obstacles:
                obstacle = obstacles[neighbor]
                if obstacle.type == "Indestructible":
                    continue
                elif obstacle.type == "Destructible":
                    k_factor = (math.ceil(obstacle.health / ZOMBIE_ATTACK)) * 0.1
                    new_cost = cost_so_far[current] + 1 + k_factor
            if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                cost_so_far[neighbor] = new_cost
                priority = new_cost + heuristic(goal, neighbor)
                frontier.put((priority, neighbor))
                # came_from[current] = current if current not in came_from else came_from[current]
                came_from[neighbor] = current
    return came_from, cost_so_far


def is_not_edge(pos, grid_size):
    x, y = pos
    return 1 <= x < grid_size - 1 and 1 <= y < grid_size - 1


def get_level_config(level: int) -> dict:
    if level < len(LEVELS):
        return LEVELS[level]
    return {
        "obstacle_count": 20 + level,
        "item_count": 5,
        "zombie_count": min(5, 1 + level // 3),
        "block_hp": int(10 * 1.2 ** (level - len(LEVELS) + 1)),
        "zombie_types": ["basic", "strong", "fire"][level % 3:],
        "reward": random.choice(CARD_POOL)
    }


def reconstruct_path(came_from: Dict, start: Tuple[int, int], goal: Tuple[int, int]) -> List[Tuple[int, int]]:
    if goal not in came_from: return [start]
    path = []
    current = goal
    while current != start:
        path.append(current)
        current = came_from[current]
    path.append(start)
    path.reverse()
    return path


# ==================== 游戏初始化函数 ====================

def generate_game_entities(grid_size: int, obstacle_count: int, item_count: int, zombie_count: int, main_block_hp: int):
    """
    Generate entities with map-fill: obstacle clusters, ample items, and non-blocking decorations.
    Main block removed — all items are collectible when touched.
    """
    all_positions = [(x, y) for x in range(grid_size) for y in range(grid_size)]
    corners = [(0, 0), (0, grid_size - 1), (grid_size - 1, 0), (grid_size - 1, grid_size - 1)]
    forbidden = set(corners)

    def pick_valid_positions(min_distance: int, count: int):
        empty = [p for p in all_positions if p not in forbidden]
        while True:
            picks = random.sample(empty, count + 1)
            player_pos, zombies = picks[0], picks[1:]
            if all(abs(player_pos[0] - z[0]) + abs(player_pos[1] - z[1]) >= min_distance for z in zombies):
                return player_pos, zombies

    # center spawn if possible
    center_pos = (grid_size // 2, grid_size // 2)
    if center_pos not in forbidden:
        player_pos = center_pos
        far_candidates = [p for p in all_positions if
                          p not in forbidden and (abs(p[0] - center_pos[0]) + abs(p[1] - center_pos[1]) >= 6)]
        zombie_pos_list = random.sample(far_candidates, zombie_count)
    else:
        player_pos, zombie_pos_list = pick_valid_positions(min_distance=5, count=zombie_count)
    forbidden |= {player_pos}
    forbidden |= set(zombie_pos_list)

    # --- obstacle fill with clusters (NO pre-placed main block now) ---
    obstacles: Dict[Tuple[int, int], Obstacle] = {}
    area = grid_size * grid_size
    target_obstacles = max(obstacle_count, int(area * OBSTACLE_DENSITY))
    rest_needed = target_obstacles

    base_candidates = [p for p in all_positions if p not in forbidden]
    random.shuffle(base_candidates)
    placed = 0

    # cluster seeds
    cluster_seeds = base_candidates[:max(1, rest_needed // 6)]
    for seed in cluster_seeds:
        if placed >= rest_needed: break
        cluster_size = random.randint(3, 6)
        wave = [seed]
        visited = set()
        while wave and placed < rest_needed and len(visited) < cluster_size:
            cur = wave.pop()
            if cur in visited or cur in obstacles or cur in forbidden: continue
            visited.add(cur)
            typ = "Indestructible" if random.random() < 0.65 else "Destructible"
            hp = OBSTACLE_HEALTH if typ == "Destructible" else None
            obstacles[cur] = Obstacle(cur[0], cur[1], typ, health=hp)
            placed += 1

            x, y = cur
            neigh = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
            random.shuffle(neigh)
            for nb in neigh:
                if 0 <= nb[0] < grid_size and 0 <= nb[1] < grid_size and nb not in visited:
                    wave.append(nb)

    # if still short, scatter
    if placed < rest_needed:
        more = [p for p in base_candidates if p not in obstacles]
        random.shuffle(more)
        for pos in more[:(rest_needed - placed)]:
            typ = "Indestructible" if random.random() < 0.5 else "Destructible"
            hp = OBSTACLE_HEALTH if typ == "Destructible" else None
            obstacles[pos] = Obstacle(pos[0], pos[1], typ, health=hp)

    forbidden |= set(obstacles.keys())

    # --- items (all are normal) ---
    item_target = max(item_count, MIN_ITEMS, grid_size // 2)
    item_candidates = [p for p in all_positions if p not in forbidden]
    items = [Item(x, y, is_main=False) for (x, y) in random.sample(item_candidates, min(len(item_candidates), item_target))]

    # --- decorations ---
    decor_target = int(area * DECOR_DENSITY)
    decor_candidates = [p for p in all_positions if p not in forbidden]
    random.shuffle(decor_candidates)
    decorations = decor_candidates[:decor_target]

    # keep return shape the same: last “main_item_list” is now empty list
    return obstacles, items, player_pos, zombie_pos_list, [], decorations



def build_graph(grid_size: int, obstacles: Dict[Tuple[int, int], Obstacle]) -> Graph:
    graph = Graph()
    for x in range(grid_size):
        for y in range(grid_size):
            current_pos = (x, y)
            if current_pos in obstacles and obstacles[current_pos].type == "Indestructible": continue
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                neighbor_pos = (x + dx, y + dy)
                if not (0 <= neighbor_pos[0] < grid_size and 0 <= neighbor_pos[1] < grid_size): continue
                if neighbor_pos in obstacles and obstacles[neighbor_pos].type == "Indestructible": continue
                weight = 1
                if neighbor_pos in obstacles and obstacles[neighbor_pos].type == "Destructible":
                    weight = 10
                graph.add_edge(current_pos, neighbor_pos, weight)
    return graph


# ==================== 新增游戏状态类 ====================
class GameState:
    def __init__(self, obstacles: Dict, items: Set, main_item_pos: List[Tuple[int, int]], decorations: list):
        self.obstacles = obstacles
        self.items = items
        self.destructible_count = self.count_destructible_obstacles()
        self.main_item_pos = main_item_pos
        self.items_total = len(items)  # track total at start
        # non-colliding visual fillers
        self.decorations = decorations  # list[Tuple[int,int]] grid coords
        self.spoils_gained = 0

    def count_destructible_obstacles(self) -> int:
        return sum(1 for obs in self.obstacles.values() if obs.type == "Destructible")

    def collect_item(self, player_rect):
        for item in list(self.items):
            if player_rect.colliderect(item.rect):
                self.items.remove(item)
                return True
        return False

    def destroy_obstacle(self, pos: Tuple[int, int]):
        if pos in self.obstacles:
            if self.obstacles[pos].type == "Destructible": self.destructible_count -= 1
            del self.obstacles[pos]


# ==================== 游戏渲染函数 ====================

def render_game(screen: pygame.Surface, game_state, player: Player, zombies: List[Zombie],
                bullets: Optional[List['Bullet']] = None,
                enemy_shots: Optional[List[EnemyShot]] = None) -> pygame.Surface:
    # Camera centers on player; add pillarbox if the viewport is wider/taller than the world
    world_w = GRID_SIZE * CELL_SIZE
    world_h = GRID_SIZE * CELL_SIZE + INFO_BAR_HEIGHT

    # initial (follow player)
    cam_x = int(player.x + player.size // 2 - VIEW_W // 2)
    cam_y = int(player.y + player.size // 2 - (VIEW_H - INFO_BAR_HEIGHT) // 2)

    # Horizontal: if the screen is wider than the world, center the world (pillarbox both sides)
    if VIEW_W > world_w:
        pad_x = (VIEW_W - world_w) // 2
        cam_x = -pad_x  # negative camera means "draw world centered"
    else:
        cam_x = max(0, min(cam_x, world_w - VIEW_W))

    # Vertical (rare): if the screen is taller than the world+HUD, center vertically too
    if VIEW_H > world_h:
        pad_y = (VIEW_H - world_h) // 2
        cam_y = -pad_y
    else:
        cam_y = max(0, min(cam_y, world_h - VIEW_H))

    screen.fill((20, 20, 20))
    font = pygame.font.SysFont(None, 28)
    font_small = pygame.font.SysFont(None, 22)

    # gear_rect = draw_settings_gear(screen, VIEW_W - 44, 8)

    # full-view grid aligned to world; covers pillar areas too
    grid_col = (50, 50, 50)

    # vertical lines
    x0 = (-cam_x) % CELL_SIZE  # align to world columns
    for x in range(x0, VIEW_W, CELL_SIZE):
        pygame.draw.line(screen, grid_col, (x, INFO_BAR_HEIGHT), (x, VIEW_H), 1)

    # horizontal lines (start just below HUD bar)
    y0 = (INFO_BAR_HEIGHT - cam_y) % CELL_SIZE
    y0 += INFO_BAR_HEIGHT
    for y in range(y0, VIEW_H, CELL_SIZE):
        pygame.draw.line(screen, grid_col, (0, y), (VIEW_W, y), 1)

    # --- Item/Fragment HUD (top-right) ---
    total_items = getattr(game_state, 'items_total', len(game_state.items))
    collected = max(0, total_items - len(game_state.items))

    # small yellow fragment icon
    icon_x = VIEW_W - 120
    icon_y = 10
    pygame.draw.circle(screen, (255, 255, 0), (icon_x, icon_y + 8), 8)

    # "collected/total" text
    items_text = font.render(f"{collected}/{total_items}", True, (255, 255, 255))
    screen.blit(items_text, (icon_x + 18, icon_y))

    # --- draw items ---
    for item in game_state.items:
        # convert world -> screen using camera offset
        sx = int(item.center[0] - cam_x)
        sy = int(item.center[1] - cam_y)
        color = (255, 255, 100) if item.is_main else (255, 255, 0)
        pygame.draw.circle(screen, color, (sx, sy), item.radius)

    # decorations (non-colliding visual fillers)
    for gx, gy in getattr(game_state, 'decorations', []):
        cx = gx * CELL_SIZE + CELL_SIZE // 2 - cam_x
        cy = gy * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT - cam_y
        pygame.draw.circle(screen, (70, 80, 70), (cx, cy), max(2, CELL_SIZE // 8))

    # player
    player_draw = player.rect.copy()
    player_draw.x -= cam_x
    player_draw.y -= cam_y
    if player.hit_cd > 0 and ((pygame.time.get_ticks() // 80) % 2 == 0):
        pygame.draw.rect(screen, (240, 80, 80), player_draw)  # flicker color
    else:
        pygame.draw.rect(screen, (0, 255, 0), player_draw)

    # zombies
    for zombie in zombies:
        zr = zombie.rect.copy()
        zr.x -= cam_x
        zr.y -= cam_y

        # 基于类型的底色
        base_color = ZOMBIE_COLORS.get(getattr(zombie, "type", "basic"), (255, 60, 60))
        color = base_color

        # 自爆怪：临爆前闪烁（覆盖底色）
        if zombie.type in ("suicide", "bomber") and getattr(zombie, "fuse", None) is not None:
            if zombie.fuse <= SUICIDE_FLICKER and (pygame.time.get_ticks() // 100) % 2 == 0:
                color = (255, 220, 100)

        pygame.draw.rect(screen, color, zr)

        # HP 条
        try:
            mhp = getattr(zombie, 'max_hp', None) or getattr(zombie, 'hp', 1)
            ratio = max(0.0, min(1.0, float(max(0, zombie.hp)) / float(mhp)))
            bar_w = zr.width
            bar_h = 4
            bx, by = zr.x, zr.y - (bar_h + 3)
            pygame.draw.rect(screen, (40, 40, 40), (bx, by, bar_w, bar_h))
            pygame.draw.rect(screen, (0, 220, 80), (bx, by, int(bar_w * ratio), bar_h))
        except Exception:
            pass

        # 护盾条（画在 HP 条上面）
        if getattr(zombie, "shield_hp", 0) > 0 and getattr(zombie, "shield_t", 0.0) > 0:
            sh_ratio = max(0.0, min(1.0, zombie.shield_hp / float(SHIELD_AMOUNT)))
            sby = by - (bar_h + 2)
            pygame.draw.rect(screen, (30, 30, 50), (bx, sby, bar_w, bar_h))
            pygame.draw.rect(screen, (60, 180, 255), (bx, sby, int(bar_w * sh_ratio), bar_h))

    # bullets
    if bullets:
        for b in bullets:
            b.draw(screen, cam_x, cam_y)

    # enemy shots
    if enemy_shots:
        for es in enemy_shots:
            es.draw(screen, cam_x, cam_y)

    # obstacles
    for obstacle in game_state.obstacles.values():
        # is_main = hasattr(obstacle, 'is_main_block') and obstacle.is_main_block
        # # if is_main:
        # #     color = (255, 220, 80)
        if obstacle.type == "Indestructible":
            color = (120, 120, 120)
        else:
            color = (200, 80, 80)
        draw_rect = obstacle.rect.copy()
        draw_rect.x -= cam_x
        draw_rect.y -= cam_y
        pygame.draw.rect(screen, color, draw_rect)
        if obstacle.type == "Destructible":
            font2 = pygame.font.SysFont(None, 30)
            health_text = font2.render(str(obstacle.health), True, (255, 255, 255))
            screen.blit(health_text, (draw_rect.x + 6, draw_rect.y + 8))
        # if is_main:
        #     star = pygame.font.SysFont(None, 32).render("★", True, (255, 255, 120))
        #     screen.blit(star, (draw_rect.x + 8, draw_rect.y + 8))

    pygame.draw.rect(screen, (0, 0, 0), (0, 0, VIEW_W, INFO_BAR_HEIGHT))
    font_timer = pygame.font.SysFont(None, 28)
    mono_small = mono_font(22)
    font_hp = mono_font(22)
    # -- TIMER --
    tleft = float(globals().get("_time_left_runtime", LEVEL_TIME_LIMIT))
    tleft = max(0.0, tleft)
    mins = int(tleft // 60)
    secs = int(tleft % 60)
    timer_txt = font_timer.render(f"{mins:02d}:{secs:02d}", True, (255, 255, 255))
    screen.blit(timer_txt, (VIEW_W // 2 - timer_txt.get_width() // 2, 10))

    # Level tag (left of timer) —— 显示当前关卡（人类从 1 开始）
    level_idx = int(getattr(game_state, "current_level", 0))
    level_txt_img = mono_small.render(f"LV {level_idx + 1:02d}", True, (255, 255, 255))

    # 放在计时器左侧 12px 处，不遮挡 HP 条
    level_x = (VIEW_W // 2 - timer_txt.get_width() // 2) - level_txt_img.get_width() - 12
    level_y = 10
    # 如果担心跟 HP 条重叠，也可以把它放在最左上角：level_x, level_y = 12, 10
    screen.blit(level_txt_img, (level_x, level_y))

    # Player HP bar (left) with digits inside
    bar_w, bar_h = 220, 12
    bx, by = 16, 14
    ratio = max(0.0, min(1.0, float(player.hp) / float(max(1, player.max_hp))))
    pygame.draw.rect(screen, (60, 60, 60), (bx - 2, by - 2, bar_w + 4, bar_h + 4), border_radius=4)
    pygame.draw.rect(screen, (40, 40, 40), (bx, by, bar_w, bar_h), border_radius=3)
    pygame.draw.rect(screen, (0, 200, 80), (bx, by, int(bar_w * ratio), bar_h), border_radius=3)

    hp_text = f"{int(player.hp)}/{int(player.max_hp)}"
    hp_img = font_hp.render(hp_text, True, (20, 20, 20))  # digits ON the bar
    screen.blit(hp_img, hp_img.get_rect(center=(bx + bar_w // 2, by + bar_h // 2 + 1)))

    pygame.display.flip()
    return screen.copy()


# ==================== GAMESOUND ====================

# ==================== GAMESOUND ====================

class GameSound:
    """
    Background BGM loader/controller.
    It probes several likely paths so ZGAME.wav is found regardless of where ZGame.py runs from.
    """

    def __init__(self, music_path: str = None, volume: float = 0.6):
        self.volume = max(0.0, min(1.0, float(volume)))
        self._ready = False

        # --- pick a path ---
        here = os.path.dirname(__file__) if "__file__" in globals() else os.getcwd()
        candidates = [
            # project-typical
            os.path.join(here, "Z_Game", "assets", "ZGAME.wav"),
            os.path.join(here, "assets", "ZGAME.wav"),
            # run-from-working-dir
            os.path.join(os.getcwd(), "Z_Game", "assets", "ZGAME.wav"),
            os.path.join(os.getcwd(), "assets", "ZGAME.wav"),
            # user-provided absolute-like hint (DON'T rely on drive root)
            r"C:\Users\%USERNAME%\Z_Game\assets\ZGAME.wav".replace("%USERNAME%", os.environ.get("USERNAME", "")),
        ]
        if music_path:
            candidates.insert(0, music_path)

        self.music_path = None
        for p in candidates:
            if p and os.path.exists(p):
                self.music_path = p
                break

        if not self.music_path:
            print("[Audio] ZGAME.wav not found in expected locations.")
            return

        # --- init mixer (make sure it's initialized even if pygame.init() already ran) ---
        try:
            if not pygame.mixer.get_init():
                # pre_init only helps if called before pygame.init(); guard anyway
                pygame.mixer.pre_init(44100, -16, 2, 512)
                pygame.mixer.init(44100, -16, 2, 512)
        except Exception as e:
            print(f"[Audio] mixer init failed: {e}")
            return

        # --- load file ---
        try:
            pygame.mixer.music.load(self.music_path)
            pygame.mixer.music.set_volume(self.volume)
            self._ready = True
            print(f"[Audio] Loaded BGM: {self.music_path}")
        except Exception as e:
            print(f"[Audio] load music failed: {e} (path tried: {self.music_path})")

    def playBackGroundMusic(self, loops: int = -1, fade_ms: int = 500):
        """loops=-1 means infinite loop"""
        if not self._ready:
            return
        try:
            pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)
        except Exception as e:
            print(f"[Audio] play failed: {e}")

    def stop(self, fade_ms: int = 300):
        if not self._ready: return
        try:
            if fade_ms > 0:
                pygame.mixer.music.fadeout(fade_ms)
            else:
                pygame.mixer.music.stop()
        except Exception as e:
            print(f"[Audio] stop failed: {e}")

    def pause(self):
        if self._ready:
            try:
                pygame.mixer.music.pause()
            except Exception as e:
                print(f"[Audio] pause failed: {e}")

    def resume(self):
        if self._ready:
            try:
                pygame.mixer.music.unpause()
            except Exception as e:
                print(f"[Audio] resume failed: {e}")

    def set_volume(self, volume: float):
        self.volume = max(0.0, min(1.0, float(volume)))
        if self._ready:
            try:
                pygame.mixer.music.set_volume(self.volume)
            except Exception as e:
                print(f"[Audio] set_volume failed: {e}")


# ==================== 游戏主循环 ====================


def main_run_level(config, chosen_zombie_type: str) -> Tuple[str, Optional[str], pygame.Surface]:
    pygame.display.set_caption("Zombie Card Game – Level")
    screen = pygame.display.get_surface()
    clock = pygame.time.Clock()
    time_left = float(LEVEL_TIME_LIMIT)
    globals()["_time_left_runtime"] = time_left

    obstacles, items, player_start, zombie_starts, main_item_list, decorations = generate_game_entities(
        grid_size=GRID_SIZE,
        obstacle_count=config["obstacle_count"],
        item_count=config["item_count"],
        zombie_count=config["zombie_count"],
        main_block_hp=config["block_hp"]
    )

    game_state = GameState(obstacles, items, main_item_list, decorations)
    game_state.current_level = current_level
    player = Player(player_start, speed=PLAYER_SPEED)
    player.fire_cd = 0.0

    ztype_map = {
        "zombie_fast": "fast",
        "zombie_tank": "tank",
        "zombie_strong": "strong",
        "basic": "basic"
    }
    zt = ztype_map.get(chosen_zombie_type, "basic")
    zombies = [Zombie(pos, speed=ZOMBIE_SPEED, ztype=zt) for pos in zombie_starts]

    bullets: List[Bullet] = []
    enemy_shots: List[EnemyShot] = []
    # wave spawn state
    spawn_timer = 0.0
    wave_index = 0

    def player_center():
        return player.x + player.size / 2, player.y + player.size / 2 + INFO_BAR_HEIGHT

    def pick_zombie_type_weighted():
        # 可按关卡/波次调整，这里给一个基础权重
        table = [
            ("basic", 50),
            ("fast", 15),
            ("tank", 10),
            ("ranged", 12),
            ("suicide", 8),
            ("buffer", 3),
            ("shielder", 2),
        ]
        r = random.uniform(0, sum(w for _, w in table))
        acc = 0
        for t, w in table:
            acc += w
            if r <= acc:
                return t
        return "basic"

    def find_spawn_positions(n: int) -> List[Tuple[int, int]]:
        # 不在阻挡、玩家、主物品位置；尽量远离玩家
        all_pos = [(x, y) for x in range(GRID_SIZE) for y in range(GRID_SIZE)]
        blocked = set(game_state.obstacles.keys()) | set((i.x, i.y) for i in game_state.items)
        px, py = player.pos
        cand = [p for p in all_pos if p not in blocked and abs(p[0] - px) + abs(p[1] - py) >= 6]
        random.shuffle(cand)
        # 也避免直接与现有僵尸重叠
        zcells = {(int((z.x + z.size // 2) // CELL_SIZE), int((z.y + z.size // 2) // CELL_SIZE)) for z in zombies}
        out = []
        for p in cand:
            if p in zcells: continue
            out.append(p)
            if len(out) >= n: break
        return out

    def find_target():
        px, py = player_center()
        best = None
        best_d2 = float('inf')
        # Prefer zombies first
        for z in zombies:
            cx, cy = z.rect.centerx, z.rect.centery
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best = ('zombie', None, z, cx, cy)
        # Then destructible blocks (non-main)
        for gp, ob in game_state.obstacles.items():
            if ob.type == 'Destructible' and not getattr(ob, 'is_main_block', False):
                cx, cy = ob.rect.centerx, ob.rect.centery
                d2 = (cx - px) ** 2 + (cy - py) ** 2
                if d2 < best_d2:
                    best_d2 = d2;
                    best = ('block', gp, ob, cx, cy)
        return best, (best_d2 ** 0.5) if best else None

    first_want = min(SPAWN_BASE + wave_index * SPAWN_GROWTH, ZOMBIE_CAP - len(zombies))  # wave_index is 0 here
    if len(zombies) < first_want:
        add_n = first_want - len(zombies)
        spots = find_spawn_positions(add_n)
        for gx, gy in spots:
            t = pick_zombie_type_weighted()
            z = Zombie((gx, gy), speed=ZOMBIE_SPEED, ztype=t)
            zombies.append(z)

    running = True
    game_result = None
    last_frame = None
    time_left = float(LEVEL_TIME_LIMIT)
    globals()["_time_left_runtime"] = time_left
    clock.tick(60)

    while running:
        dt = clock.tick(60) / 1000.0
        # countdown timer
        time_left -= dt
        globals()["_time_left_runtime"] = time_left
        if time_left <= 0:
            game_result = "success" if 'game_result' in locals() else "success"
            running = False

        # === wave spawning ===
        spawn_timer += dt
        if spawn_timer >= SPAWN_INTERVAL:
            spawn_timer = 0.0
            if len(zombies) < ZOMBIE_CAP:
                want = min(SPAWN_BASE + wave_index * SPAWN_GROWTH, ZOMBIE_CAP - len(zombies))
                spots = find_spawn_positions(want)
                for gx, gy in spots:
                    t = pick_zombie_type_weighted()
                    z = Zombie((gx, gy), speed=ZOMBIE_SPEED, ztype=t)
                    zombies.append(z)
                if spots:
                    wave_index += 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                bg = last_frame or render_game(screen, game_state, player, zombies, bullets, enemy_shots)
                choice, time_left = pause_game_modal(screen, bg, clock, time_left)

                if choice == 'continue':
                    pass  # just resume
                elif choice == 'restart':
                    return 'restart', config.get('reward', None), bg
                elif choice == 'home':
                    snap = capture_snapshot(game_state, player, zombies, current_level, zombie_cards_collected, zt,
                                            bullets)
                    save_snapshot(snap)
                    return 'home', config.get('reward', None), bg
                elif choice == 'exit':
                    save_progress(current_level=current_level, max_wave_reached=wave_index)
                    return 'exit', config.get('reward', None), bg

        keys = pygame.key.get_pressed()
        player.move(keys, game_state.obstacles)
        game_state.collect_item(player.rect)

        # Autofire handling
        player.fire_cd = getattr(player, 'fire_cd', 0.0) - dt
        target, dist = find_target()
        if target and player.fire_cd <= 0 and (dist is None or dist <= MAX_FIRE_RANGE):
            _, gp, ob_or_z, cx, cy = target
            px, py = player_center()
            dx, dy = cx - px, cy - py
            length = (dx * dx + dy * dy) ** 0.5 or 1.0
            vx, vy = (dx / length) * BULLET_SPEED, (dy / length) * BULLET_SPEED
            bullets.append(Bullet(px, py, vx, vy, MAX_FIRE_RANGE, damage=player.bullet_damage))
            player.fire_cd += player.fire_cooldown()

        # Update bullets
        for b in list(bullets):
            b.update(dt, game_state, zombies, player)
            if not b.alive:
                bullets.remove(b)

        player.hit_cd = max(0.0, player.hit_cd - dt)
        for zombie in list(zombies):
            zombie.move_and_attack(player, list(game_state.obstacles.values()), game_state, dt=dt)
            if zombie.rect.colliderect(player.rect) and player.hit_cd <= 0.0:
                player.hp -= int(ZOMBIE_CONTACT_DAMAGE)
                player.hit_cd = float(PLAYER_HIT_COOLDOWN)
                if player.hp <= 0:
                    game_result = "fail"
                    running = False
                    break
        # special behaviors & enemy shots
        for z in list(zombies):
            z.update_special(dt, player, zombies, enemy_shots)
            if z.hp <= 0:
                zombies.remove(z)

        # enemy shots update
        for es in list(enemy_shots):
            es.update(dt, player, game_state)
            if not es.alive:
                enemy_shots.remove(es)

        # >>> FAIL CONDITION <<<
        if player.hp <= 0:
            game_result = "fail"
            running = False
            continue

        last_frame = render_game(pygame.display.get_surface(), game_state, player, zombies, bullets, enemy_shots)
        if game_result == "success":
            globals()["_last_spoils"] = getattr(game_state, "spoils_gained", 0)

    return game_result, config.get("reward", None), last_frame


def run_from_snapshot(save_data: dict) -> Tuple[str, Optional[str], pygame.Surface]:
    """Resume a game from a snapshot in save_data; same return contract as main_run_level."""
    assert save_data.get("mode") == "snapshot"
    meta = save_data.get("meta", {})
    snap = save_data.get("snapshot", {})
    # Recreate entities
    obstacles: Dict[Tuple[int, int], Obstacle] = {}
    for o in snap.get("obstacles", []):
        typ = o.get("type", "Indestructible")
        x, y = int(o.get("x", 0)), int(o.get("y", 0))
        if o.get("main", False):
            ob = MainBlock(x, y, health=o.get("health", MAIN_BLOCK_HEALTH))
        else:
            ob = Obstacle(x, y, typ, health=o.get("health", None))
        obstacles[(x, y)] = ob
    # Items
    items = []
    for it in snap.get("items", []):
        items.append(Item(int(it.get("x", 0)), int(it.get("y", 0)), bool(it.get("is_main", False))))
    decorations = [tuple(d) for d in snap.get("decorations", [])]
    game_state = GameState(obstacles, items, [(i.x, i.y) for i in items if getattr(i, 'is_main', False)], decorations)
    game_state.current_level = current_level
    # Player
    p = snap.get("player", {})
    player = Player((0, 0), speed=int(p.get("speed", PLAYER_SPEED)))
    player.x = float(p.get("x", 0.0))
    player.y = float(p.get("y", 0.0))
    player.rect.x = int(player.x)
    player.rect.y = int(player.y) + INFO_BAR_HEIGHT
    player.fire_cd = float(p.get("fire_cd", 0.0))
    player.max_hp = int(p.get("max_hp", PLAYER_MAX_HP))
    player.hp = int(p.get("hp", PLAYER_MAX_HP))
    player.hit_cd = float(p.get("hit_cd", 0.0))
    # Zombies
    zombies: List[Zombie] = []
    for z in snap.get("zombies", []):
        zobj = Zombie((0, 0), attack=int(z.get("attack", ZOMBIE_ATTACK)), speed=int(z.get("speed", ZOMBIE_SPEED)),
                      ztype=z.get("type", "basic"), hp=int(z.get("hp", 30)))
        zobj.max_hp = int(z.get("max_hp", int(z.get("hp", 30))))
        zobj.x = float(z.get("x", 0.0))
        zobj.y = float(z.get("y", 0.0))
        zobj.rect.x = int(zobj.x)
        zobj.rect.y = int(zobj.y) + INFO_BAR_HEIGHT
        zobj._spawn_elapsed = float(z.get("spawn_elapsed", 0.0))
        zobj.attack_timer = float(z.get("attack_timer", 0.0))
        zombies.append(zobj)
    # Bullets
    bullets: List[Bullet] = []
    enemy_shots: List[EnemyShot] = []
    spawn_timer = 0.0
    wave_index = 0
    for b in snap.get("bullets", []):
        bobj = Bullet(float(b.get("x", 0.0)), float(b.get("y", 0.0)), float(b.get("vx", 0.0)), float(b.get("vy", 0.0)),
                      MAX_FIRE_RANGE)
        bobj.traveled = float(b.get("traveled", 0.0))
        bullets.append(bobj)
    # Timer
    time_left = float(snap.get("time_left", LEVEL_TIME_LIMIT))
    globals()["_time_left_runtime"] = time_left  # keep global for snapshot updates

    screen = pygame.display.get_surface()
    clock = pygame.time.Clock()
    running = True
    last_frame = None
    chosen_zombie_type = meta.get("chosen_zombie_type", "basic")

    def player_center():
        return player.x + player.size / 2, player.y + player.size / 2 + INFO_BAR_HEIGHT

    def find_target():
        px, py = player_center()
        best = None
        best_d2 = float('inf')
        # 1) zombies first
        for z in zombies:
            cx, cy = z.rect.centerx, z.rect.centery
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best = ('zombie', None, z, cx, cy)
        # 2) then destructible non-main blocks
        for gp, ob in game_state.obstacles.items():
            if ob.type == 'Destructible' and not getattr(ob, 'is_main_block', False):
                cx, cy = ob.rect.centerx, ob.rect.centery
                d2 = (cx - px) ** 2 + (cy - py) ** 2
                if d2 < best_d2:
                    best_d2 = d2
                    best = ('block', gp, ob, cx, cy)
        return best, (best_d2 ** 0.5) if best else None

    # ensure attribute
    if not hasattr(player, 'fire_cd'): player.fire_cd = 0.0

    while running:
        dt = clock.tick(60) / 1000.0
        time_left -= dt
        globals()["_time_left_runtime"] = time_left
        if time_left <= 0:
            # treat as success on survival
            chosen = show_success_screen(
                screen,
                last_frame or render_game(screen, game_state, player, zombies, bullets, enemy_shots),
                reward_choices=[]  # or real choices if you want
            )
            # push control back to caller like your success path
            return "success", None, last_frame or screen.copy()

        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                bg = last_frame or render_game(screen, game_state, player, zombies, bullets, enemy_shots)
                choice, time_left = pause_game_modal(screen, bg, clock, time_left)

                if choice == 'continue':
                    pass
                elif choice == 'restart':
                    return 'restart', None, bg
                elif choice == 'home':
                    snap2 = capture_snapshot(game_state, player, zombies, current_level, zombie_cards_collected,
                                             chosen_zombie_type, bullets)
                    save_snapshot(snap2)
                    return 'home', None, bg
                elif choice == 'exit':
                    save_progress(current_level=current_level, max_wave_reached=wave_index)
                    return 'exit', None, bg

        keys = pygame.key.get_pressed()
        player.move(keys, game_state.obstacles)
        game_state.collect_item(player.rect)

        # Autofire
        player.fire_cd = getattr(player, 'fire_cd', 0.0) - dt
        target, dist = find_target()
        if target and player.fire_cd <= 0 and (dist is None or dist <= MAX_FIRE_RANGE):
            _, gp, ob_or_z, cx, cy = target
            px, py = player_center()
            dx, dy = cx - px, cy - py
            length = (dx * dx + dy * dy) ** 0.5 or 1.0
            vx, vy = (dx / length) * BULLET_SPEED, (dy / length) * BULLET_SPEED
            bullets.append(Bullet(px, py, vx, vy, MAX_FIRE_RANGE, damage=player.bullet_damage))
            player.fire_cd += player.fire_cooldown()

        # Update bullets
        for b in list(bullets):
            b.update(dt, game_state, zombies, player)
            if not b.alive:
                bullets.remove(b)
        # Wave spawning
        spawn_timer += dt
        if spawn_timer >= SPAWN_INTERVAL:
            spawn_timer = 0.0
            if len(zombies) < ZOMBIE_CAP:
                want = min(SPAWN_BASE + wave_index * SPAWN_GROWTH, ZOMBIE_CAP - len(zombies))
                # use same helper logic as main_run_level :
                all_pos = [(x, y) for x in range(GRID_SIZE) for y in range(GRID_SIZE)]
                blocked = set(game_state.obstacles.keys()) | set((i.x, i.y) for i in game_state.items)
                px, py = player.pos
                cand = [p for p in all_pos if p not in blocked and abs(p[0] - px) + abs(p[1] - py) >= 6]
                random.shuffle(cand)
                zcells = {(int((z.x + z.size // 2) // CELL_SIZE), int((z.y + z.size // 2) // CELL_SIZE)) for z in
                          zombies}
                spots = []
                for p in cand:
                    if p in zcells: continue
                    spots.append(p)
                    if len(spots) >= want: break
                for gx, gy in spots:
                    # simple weighted pick to match main_run_level
                    table = [("basic", 50), ("fast", 15), ("tank", 10), ("ranged", 12), ("suicide", 8), ("buffer", 3),
                             ("shielder", 2)]
                    r = random.uniform(0, sum(w for _, w in table))
                    acc = 0
                    for t, w in table:
                        acc += w
                        if r <= acc:
                            ztype = t
                            break
                    zombies.append(Zombie((gx, gy), speed=ZOMBIE_SPEED, ztype=ztype))
                if spots:
                    wave_index += 1

        # zombies update & player collision
        player.hit_cd = max(0.0, player.hit_cd - dt)
        for zombie in list(zombies):
            zombie.move_and_attack(player, list(game_state.obstacles.values()), game_state, dt=dt)
            if zombie.rect.colliderect(player.rect) and player.hit_cd <= 0.0:
                player.hp -= int(ZOMBIE_CONTACT_DAMAGE)
                player.hit_cd = float(PLAYER_HIT_COOLDOWN)
                if player.hp <= 0:
                    clear_save()
                    action = show_fail_screen(screen,
                                              last_frame or render_game(screen, game_state, player, zombies, bullets,
                                                                        enemy_shots))
                    if action == "home":
                        clear_save()
                        flush_events()
                        return "home", None, last_frame or screen.copy()
                    elif action == "retry":
                        clear_save()
                        flush_events()
                        return "restart", None, last_frame or screen.copy()
        # 僵尸特殊行为（远程/自爆/增益/护盾）
        for z in list(zombies):
            z.update_special(dt, player, zombies, enemy_shots)
            if z.hp <= 0:
                zombies.remove(z)

        # 敌方弹幕更新
        for es in list(enemy_shots):
            es.update(dt, player, game_state)
            if not es.alive:
                enemy_shots.remove(es)
        # FAIL CONDITION
        if player.hp <= 0:
            clear_save()  # 与你当前失败流程一致
            action = show_fail_screen(screen,
                                      last_frame or render_game(screen, game_state, player, zombies, bullets,
                                                                enemy_shots))
            if action == "home":
                clear_save()
                flush_events()
                return "home", None, last_frame or screen.copy()
            elif action == "retry":
                clear_save()
                flush_events()
                return "restart", None, last_frame or screen.copy()

        last_frame = render_game(pygame.display.get_surface(), game_state, player, zombies, bullets, enemy_shots)
    return "home", None, last_frame or screen.copy()


def select_zombie_screen(screen, owned_cards: List[str]) -> str:
    if not owned_cards: return "basic"
    clock = pygame.time.Clock()
    while True:
        screen.fill((18, 18, 18))
        title = pygame.font.SysFont(None, 48).render("Choose Next Level's Zombie", True, (230, 230, 230))
        screen.blit(title, title.get_rect(center=(VIEW_W // 2, 110)))
        rects = []
        for i, card in enumerate(owned_cards):
            x = VIEW_W // 2 - (len(owned_cards) * 140) // 2 + i * 140
            rect = pygame.Rect(x, 180, 120, 160)
            pygame.draw.rect(screen, (200, 200, 200), rect)
            name = pygame.font.SysFont(None, 24).render(card.replace("_", " ").upper(), True, (30, 30, 30))
            screen.blit(name, name.get_rect(center=(rect.centerx, rect.bottom - 18)))
            pygame.draw.rect(screen, (40, 40, 40), rect, 3)
            rects.append((rect, card))
        confirm = draw_button(screen, "CONFIRM", (VIEW_W // 2 - 90, 370))
        pygame.display.flip()
        chosen = None
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                for rect, card in rects:
                    if rect.collidepoint(event.pos): chosen = card
                if confirm.collidepoint(event.pos) and (chosen or owned_cards):
                    door_transition(screen)
                    return chosen or owned_cards[0]
        clock.tick(60)


# ==================== 入口 ====================

if __name__ == "__main__":
    os.environ['SDL_VIDEO_CENTERED'] = '0'
    os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
    pygame.init()
    info = pygame.display.Info()

    # Create the window first (safer on some systems)
    screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.NOFRAME)
    pygame.display.set_caption(GAME_TITLE)
    VIEW_W, VIEW_H = info.current_w, info.current_h
    # Make the world at least as big as what we can see (removes “non-playable band”)
    resize_world_to_view()

    # Now start BGM using Settings default (BGM_VOLUME 0-100)
    try:
        _bgm = GameSound(volume=BGM_VOLUME / 100.0)
        _bgm.playBackGroundMusic()
    except Exception as e:
        print(f"[Audio] background music not started: {e}")

    # Borderless fullscreen to avoid display mode flicker
    screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.NOFRAME)
    pygame.display.set_caption(GAME_TITLE)
    VIEW_W, VIEW_H = info.current_w, info.current_h
    # Make the world at least as big as what we can see (removes “non-playable band”)
    resize_world_to_view()

    # Enter start menu
    flush_events()
    selection = show_start_menu(screen)
    if not selection:
        sys.exit()
    mode, save_data = selection

    # Initialize progress holders (module-level for snapshot helpers)
    if mode == "continue" and save_data:
        if save_data.get("mode") == "snapshot":
            # pull meta
            meta = save_data.get("meta", {})
            current_level = int(meta.get("current_level", 0))
            zombie_cards_collected = list(meta.get("zombie_cards_collected", []))
        else:
            current_level = int(save_data.get("current_level", 0))
            zombie_cards_collected = list(save_data.get("zombie_cards_collected", []))
    else:
        clear_save()
        current_level = 0
        zombie_cards_collected = []

    while True:
        # If we came from CONTINUE(snapshot), resume immediately
        if mode == "continue" and save_data and save_data.get("mode") == "snapshot":
            door_transition(screen)
            result, reward, bg = run_from_snapshot(save_data)
            # after run, reset mode to normal flow
            save_data = None
            mode = "new"
        else:
            config = get_level_config(current_level)
            chosen_zombie = select_zombie_screen(screen, zombie_cards_collected) if zombie_cards_collected else "basic"
            door_transition(screen)
            result, reward, bg = main_run_level(config, chosen_zombie)

        if result == "restart":
            flush_events()
            continue

        if result == "home":
            flush_events()
            selection = show_start_menu(screen)
            if not selection:
                sys.exit()
            mode, save_data = selection
            if mode == "continue" and save_data:
                # Update progress trackers
                if save_data.get("mode") == "snapshot":
                    meta = save_data.get("meta", {})
                    current_level = int(meta.get("current_level", 0))
                    zombie_cards_collected = list(meta.get("zombie_cards_collected", []))
                else:
                    current_level = int(save_data.get("current_level", 0))
                    zombie_cards_collected = list(save_data.get("zombie_cards_collected", []))
            else:
                # new game selected from menu
                clear_save()
                current_level = 0
                zombie_cards_collected = []
            continue

        if result == "exit":
            # quit to OS; snapshot saving already done inside the loop
            pygame.quit()
            sys.exit()

        if result == "fail":
            # On fail, wipe any save so there is NO CONTINUE on the homepage
            clear_save()
            action = show_fail_screen(screen, bg)
            flush_events()
            if action == "home":
                # ensure save is gone before drawing the menu
                clear_save()
                selection = show_start_menu(screen)
                if not selection:
                    sys.exit()
                mode, save_data = selection
                # After a fail we always start fresh; ignore any 'continue'
                clear_save()
                current_level = 0
                zombie_cards_collected = []
                continue
            else:
                continue

        elif result == "success":
            pool = [c for c in CARD_POOL if c not in zombie_cards_collected]
            reward_choices = random.sample(pool, k=min(3, len(pool))) if pool else []
            chosen = show_success_screen(screen, bg, reward_choices)

            # 成功界面可能返回三类：1) 选中的卡牌名；2) "home"；3) "restart"；还有可能 None（无卡牌时点确认）
            if chosen == "home":
                # 回到主页
                flush_events()
                selection = show_start_menu(screen)
                if not selection: sys.exit()
                mode, save_data = selection
                # 保持当前关卡/卡池或按你的设计重置，这里沿用你现有主页逻辑
                if mode == "continue" and save_data:
                    if save_data.get("mode") == "snapshot":
                        meta = save_data.get("meta", {})
                        current_level = int(meta.get("current_level", 0))
                        zombie_cards_collected = list(meta.get("zombie_cards_collected", []))
                    else:
                        current_level = int(save_data.get("current_level", 0))
                        zombie_cards_collected = list(save_data.get("zombie_cards_collected", []))
                else:
                    clear_save()
                    current_level = 0
                    zombie_cards_collected = []
                continue  # 回到 while 重新开始流程

            elif chosen == "restart":
                # 不加关卡，不保存，直接重来这一关
                continue


            elif chosen in CARD_POOL:
                zombie_cards_collected.append(chosen)
                # add spoils from the finished level, then open shop
                META["spoils"] += int(globals().get("_last_spoils", 0))
                show_shop_screen(screen)
                current_level += 1
                save_progress(current_level, zombie_cards_collected)


            else:
                # 没选到卡（比如卡池空），也推进到下一关
                META["spoils"] += int(globals().get("_last_spoils", 0))
                show_shop_screen(screen)

                current_level += 1
                save_progress(current_level, zombie_cards_collected)

        else:
            # Unknown state -> go home
            selection = show_start_menu(screen)
            if not selection:
                sys.exit()
            mode, save_data = selection
            if mode == "continue" and save_data:
                if save_data.get("mode") == "snapshot":
                    meta = save_data.get("meta", {})
                    current_level = int(meta.get("current_level", 0))
                    zombie_cards_collected = list(meta.get("zombie_cards_collected", []))
                else:
                    current_level = int(save_data.get("current_level", 0))
                    zombie_cards_collected = list(save_data.get("zombie_cards_collected", []))
            else:
                clear_save()
                current_level = 0
                zombie_cards_collected = []

# TODO
# Attack MODE need to figure out
# The item collection system can be hugely impact this game to next level
# Player and Zombie both can collect item to upgrade, after kill zombie, player can get the experience to upgrade, and
# I set a timer each game for winning condition, as long as player still alive, after the time is running out
# player won, vice versa. And after each combat, shop( roguelike feature) will apear for player to trade with item
# using the item they collect in the combat
