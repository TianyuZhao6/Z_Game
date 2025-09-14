import sys
import pygame
import math
import random
import json
import os
from queue import PriorityQueue
from collections import deque
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


def feet_center(ent):
    # 世界坐标（含 INFO_BAR_HEIGHT 的平移）
    return (ent.x + ent.size * 0.5, ent.y + ent.size * 0.5 + INFO_BAR_HEIGHT)


def circle_touch(a, b, extra=0.0) -> bool:
    ax, ay = feet_center(a)
    bx, by = feet_center(b)
    ra = getattr(a, "radius", a.size * 0.5)
    rb = getattr(b, "radius", b.size * 0.5)
    r = ra + rb + float(extra)
    dx = ax - bx;
    dy = ay - by
    return (dx * dx + dy * dy) <= (r * r)


def draw_ui_topbar(screen, game_state, player, time_left: float | None = None) -> None:
    """
    顶栏 HUD（绝对屏幕坐标，不受相机/等距相机影响）
    - 必须在世界/实体都画完之后再调用（最上层）
    - 不做 flip()；由外层渲染函数统一 flip
    """
    # 背板
    pygame.draw.rect(screen, (0, 0, 0), (0, 0, VIEW_W, INFO_BAR_HEIGHT))

    # 字体
    font_timer = pygame.font.SysFont(None, 28)
    mono_small = mono_font(22)
    font_hp = mono_font(22)

    # ===== 计时器（居中） =====
    tleft = float(time_left if time_left is not None else globals().get("_time_left_runtime", LEVEL_TIME_LIMIT))
    tleft = max(0.0, tleft)
    mins = int(tleft // 60)
    secs = int(tleft % 60)
    timer_txt = font_timer.render(f"{mins:02d}:{secs:02d}", True, (255, 255, 255))
    center_x = VIEW_W // 2
    screen.blit(timer_txt, (center_x - timer_txt.get_width() // 2, 10))

    # ===== 关卡 LV（在计时器左侧 12px）=====
    level_idx = int(getattr(game_state, "current_level", 0))  # 0-based
    level_img = mono_small.render(f"LV {level_idx + 1:02d}", True, (255, 255, 255))
    level_x = center_x - timer_txt.get_width() // 2 - level_img.get_width() - 12
    screen.blit(level_img, (level_x, 10))

    # ===== 威胁预算 BDG（在计时器右侧 12px）=====
    bdg_val = budget_for_level(level_idx)
    bdg_img = mono_small.render(f"BDG {bdg_val}", True, (200, 200, 220))
    bdg_x = center_x + timer_txt.get_width() // 2 + 12
    screen.blit(bdg_img, (bdg_x, 10))

    # ===== HP 条（左上角）=====
    bar_w, bar_h = 220, 12
    bx, by = 16, 14
    ratio = 0.0 if max(1, getattr(player, "max_hp", 1)) == 0 else max(
        0.0, min(1.0, float(getattr(player, "hp", 0)) / float(max(1, getattr(player, "max_hp", 1)))))
    # frame + bg + fill
    pygame.draw.rect(screen, (60, 60, 60), (bx - 2, by - 2, bar_w + 4, bar_h + 4), border_radius=4)
    pygame.draw.rect(screen, (40, 40, 40), (bx, by, bar_w, bar_h), border_radius=3)
    pygame.draw.rect(screen, (0, 200, 80), (bx, by, int(bar_w * ratio), bar_h), border_radius=3)
    # 数字覆盖在进度条中间
    hp_text = f"{int(getattr(player, 'hp', 0))}/{int(getattr(player, 'max_hp', 0))}"
    hp_img = font_hp.render(hp_text, True, (20, 20, 20))
    screen.blit(hp_img, hp_img.get_rect(center=(bx + bar_w // 2, by + bar_h // 2 + 1)))

    # ===== XP 条（紧贴 HP 条下方）=====
    xp_bar_w, xp_bar_h = bar_w, 6
    xp_bx, xp_by = bx, by + bar_h + 6
    xp_to_next = int(getattr(player, "xp_to_next", 0))
    xp_have = int(getattr(player, "xp", 0))
    xp_ratio = max(0.0, min(1.0, float(xp_have) / float(xp_to_next))) if xp_to_next > 0 else 0.0
    pygame.draw.rect(screen, (60, 60, 60), (xp_bx - 2, xp_by - 2, xp_bar_w + 4, xp_bar_h + 4), border_radius=4)
    pygame.draw.rect(screen, (40, 40, 40), (xp_bx, xp_by, xp_bar_w, xp_bar_h), border_radius=3)
    pygame.draw.rect(screen, (120, 110, 255), (xp_bx, xp_by, int(xp_bar_w * xp_ratio), xp_bar_h), border_radius=3)
    # 小标签（在条右侧显示等级）
    xp_label = mono_small.render(f"Lv {int(getattr(player, 'level', 1))}", True, (210, 210, 230))
    screen.blit(xp_label, (xp_bx + xp_bar_w + 8, xp_by - 6))

    # ===== 右上角：物品 & 金币 =====
    hud_font = font_timer  # 统一字号
    # 物品（最右）
    total_items = int(getattr(game_state, "items_total", len(getattr(game_state, "items", []))))
    collected = max(0, total_items - len(getattr(game_state, "items", [])))
    icon_x, icon_y = VIEW_W - 120, 10
    pygame.draw.circle(screen, (255, 255, 0), (icon_x, icon_y + 8), 8)
    items_text = hud_font.render(f"{collected}/{total_items}", True, (255, 255, 255))
    screen.blit(items_text, (icon_x + 18, icon_y))

    # 金币（物品左侧）
    spoils_total = int(META.get("spoils", 0)) + int(getattr(game_state, "spoils_gained", 0))
    coin_x, coin_y = VIEW_W - 220, 10
    pygame.draw.circle(screen, (255, 215, 80), (coin_x, coin_y + 8), 8)
    pygame.draw.circle(screen, (255, 245, 200), (coin_x, coin_y + 8), 8, 1)
    spoils_text = hud_font.render(f"{spoils_total}", True, (255, 255, 255))
    screen.blit(spoils_text, (coin_x + 14, coin_y))

def _find_current_boss(zombies):
    # 约定：任意 is_boss=True 的单位都当作 BOSS
    for z in zombies:
        if getattr(z, "is_boss", False):
            return z
    return None

def draw_boss_hp_bar(screen, boss):
    # ---- 尺寸与位置（顶栏下方一条大血条）----
    bar_w = min(720, max(420, int(VIEW_W * 0.55)))
    bar_h = 18
    bx = (VIEW_W - bar_w) // 2
    by = INFO_BAR_HEIGHT + 44
    # ---- 比例与文字 ----
    mhp = int(getattr(boss, "max_hp", max(1, boss.hp)))
    cur = max(0, int(boss.hp))
    ratio = 0.0 if mhp <= 0 else max(0.0, min(1.0, cur / float(mhp)))

    # 名称回退：优先 boss_name/_display_name → Memory Devourer → BOSS
    name = (getattr(boss, "boss_name", None)
            or getattr(boss, "_display_name", None)
            or ("Memory Devourer" if getattr(boss, "is_boss", False) else "BOSS"))

    # 背板/边框
    pygame.draw.rect(screen, (28, 28, 32), (bx-2, by-2, bar_w+4, bar_h+4), border_radius=8)
    pygame.draw.rect(screen, (52, 52, 60), (bx, by, bar_w, bar_h), border_radius=6)

    # 血量（红色填充）
    fill_w = int(bar_w * ratio)
    if fill_w > 0:
        pygame.draw.rect(screen, (210, 64, 64), (bx, by, fill_w, bar_h), border_radius=6)

    # 分段刻度（70%/40% 阶段线，方便读阶段）
    for t in (0.7, 0.4):
        tx = bx + int(bar_w * t)
        pygame.draw.line(screen, (90, 90, 96), (tx, by), (tx, by + bar_h), 1)

    # 标题与数值
    title_font = pygame.font.SysFont(None, 26, bold=True)
    small_font = pygame.font.SysFont(None, 22)
    title = title_font.render(str(name), True, (240, 240, 240))
    vals = small_font.render(f"{cur}/{mhp}", True, (235, 235, 235))

    title_shadow = pygame.font.SysFont(None, 26, bold=True).render(str(name), True, (0, 0, 0))
    screen.blit(title_shadow, title_shadow.get_rect(midbottom=(VIEW_W // 2 + 1, by - 3)))
    screen.blit(title, title.get_rect(midbottom=(VIEW_W // 2, by - 4)))

    screen.blit(vals, vals.get_rect(midleft=(bx + 8, by + bar_h + 4)))

def _find_all_bosses(zombies):
    return [z for z in zombies if getattr(z, "is_boss", False)]

def draw_boss_hp_bars_twin(screen, bosses):
    a, b = bosses[0], bosses[1]

    bar_w = min(720, max(420, int(VIEW_W * 0.55)))
    bar_h = 16
    bx = (VIEW_W - bar_w) // 2
    by = INFO_BAR_HEIGHT + 26   # 往下挪，避免和顶部信息重叠

    # —— 只显示一次标题（两只同名时不重复）——
    title_name = (getattr(a, "boss_name", None) or getattr(a, "_display_name", None)
                  or getattr(b, "boss_name", None) or getattr(b, "_display_name", None)
                  or "BOSS")
    title_font = pygame.font.SysFont(None, 26, bold=True)
    title = title_font.render(str(title_name), True, (240, 240, 240))
    screen.blit(title, title.get_rect(midbottom=(VIEW_W // 2, by - 6)))

    def draw_one(boss, y, color):
        mhp = max(1, int(getattr(boss, "max_hp", getattr(boss, "hp", 1))))
        cur = max(0, int(getattr(boss, "hp", 0)))
        ratio = max(0.0, min(1.0, cur / float(mhp)))

        # 背板/描边
        pygame.draw.rect(screen, (28, 28, 32), (bx-2, y-2, bar_w+4, bar_h+4), border_radius=8)
        pygame.draw.rect(screen, (52, 52, 60), (bx, y, bar_w, bar_h), border_radius=6)

        # 填充
        if ratio > 0:
            pygame.draw.rect(screen, color, (bx, y, int(bar_w * ratio), bar_h), border_radius=6)

        # 阶段刻度
        for t in (0.7, 0.4):
            tx = bx + int(bar_w * t)
            pygame.draw.line(screen, (90, 90, 96), (tx, y), (tx, y + bar_h), 1)

        # 右侧数值
        small = pygame.font.SysFont(None, 20)
        vals = small.render(f"{cur}/{mhp}", True, (235, 235, 235))
        screen.blit(vals, vals.get_rect(bottomright=(bx + bar_w - 6, y + bar_h + 16)))

    y1 = by
    y2 = by + bar_h + 12   # 两条之间 12px 间距
    draw_one(a, y1, (210, 64, 64))
    draw_one(b, y2, (230, 120, 70))


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


def _expanded_block_mask(obstacles: dict, grid_size: int, radius_px: int) -> list:
    """返回经过半径外扩后的阻挡掩码（True=不可走）"""
    # 把像素半径近似成网格曼哈顿半径：半格≈CELL_SIZE*0.5
    radius_cells = max(1, int(math.ceil(radius_px / (CELL_SIZE * 0.5))))
    mask = [[False] * grid_size for _ in range(grid_size)]
    # 原始脚印
    for (gx, gy) in obstacles.keys():
        mask[gy][gx] = True
    # 曼哈顿外扩
    if radius_cells > 0:
        base = [row[:] for row in mask]
        for y in range(grid_size):
            for x in range(grid_size):
                if not base[y][x]:
                    continue
                for dy in range(-radius_cells, radius_cells + 1):
                    for dx in range(-radius_cells, radius_cells + 1):
                        if abs(dx) + abs(dy) <= radius_cells:
                            nx, ny = x + dx, y + dy
                            if 0 <= nx < grid_size and 0 <= ny < grid_size:
                                mask[ny][nx] = True
    return mask


def _reachable_to_edge(start: tuple, mask: list) -> bool:
    """只在 mask 为 False 的格子上走，看能否走到外环"""
    n = len(mask)
    sx, sy = start
    if not (0 <= sx < n and 0 <= sy < n) or mask[sy][sx]:
        return False
    q = deque([(sx, sy)])
    seen = {(sx, sy)}
    while q:
        x, y = q.popleft()
        if x == 0 or y == 0 or x == n - 1 or y == n - 1:
            return True
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < n and 0 <= ny < n and not mask[ny][nx] and (nx, ny) not in seen:
                seen.add((nx, ny));
                q.append((nx, ny))
    return False


def ensure_passage_budget(obstacles: dict, grid_size: int, player_spawn: tuple, tries: int = 8):
    """
    若玩家出生点到外环不可达：随机移除 1-2 个可破坏障碍（最多 tries 次），保证可走。
    注意：只改 obstacles 这个 dict，不改其它东西。
    """
    # 预先收集可破坏障碍坐标
    destructibles = [pos for pos, ob in obstacles.items() if getattr(ob, "type", "") == "Destructible"]
    for _ in range(tries):
        mask = _expanded_block_mask(obstacles, grid_size, PLAYER_RADIUS)
        if _reachable_to_edge(player_spawn, mask):
            return  # OK
        if not destructibles:
            break
        # 随机挖一个试试（你也可以在这里用更聪明的挑选策略）
        pos = random.choice(destructibles)
        destructibles.remove(pos)
        obstacles.pop(pos, None)


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
# --- view style ---
USE_ISO = True  # True: 伪3D等距渲染；False: 保持现在的纯2D
ISO_CELL_W = 64  # 等距砖块在画面上的“菱形”宽
ISO_CELL_H = 32  # 等距砖块在画面上的“菱形”半高（顶点到中心）
ISO_WALL_Z = 22  # 障碍“墙体”抬起的高度（屏幕像素）
ISO_SHADOW_ALPHA = 90  # 椭圆阴影透明度
SPATIAL_CELL = int(CELL_SIZE * 1.25)  # 统一网格大小

WALL_STYLE = "hybrid"  # "billboard" | "prism" | "hybrid"

ISO_EQ_GAIN = math.sqrt(2) * (ISO_CELL_W * 0.5)
# 角色圆形碰撞半径
PLAYER_RADIUS = int(CELL_SIZE * 0.28)
ZOMBIE_RADIUS = int(CELL_SIZE * 0.28)

# 成长模式：'linear'（当前默认）或 'exp'（推荐）
MON_SCALE_MODE = "exp"  # "linear" / "exp"
MON_HP_GROWTH_PER_LEVEL = 0.08  # HP 每关 +8% 复利到软帽
MON_ATK_GROWTH_PER_LEVEL = 0.09  # ATK 每关 +9% 复利到软帽
MON_HP_GROWTH_PER_WAVE = 0.03  # HP 每波 +3% 复利
MON_ATK_GROWTH_PER_WAVE = 0.03  # ATK 每波 +3% 复利
MON_SOFTCAP_LEVEL = 10  # 关卡软帽起点
MON_SOFTCAP_FACTOR = 0.40  # 软帽后有效增长强度只有 40%

# --- map fill tuning ---
OBSTACLE_DENSITY = 0.14  # proportion of tiles to become obstacles (including clusters)
DECOR_DENSITY = 0.06  # proportion of tiles to place non-blocking decorations
MIN_ITEMS = 8  # ensure enough items on larger maps
DESTRUCTIBLE_RATIO = 0.3
PLAYER_SPEED = 5
PLAYER_SPEED_CAP = 7.0
ZOMBIE_SPEED = 2
ZOMBIE_SPEED_MAX = 4.5
ZOMBIE_ATTACK = 10


# --- next-level scene buff cards ---
SCENE_BIOMES = ["Domain of Wind", "Misty Forest", "Scorched Hell", "Bastion of Stone"]
_next_biome = None  # 记录玩家本关在商店后选择的“下关场景”

# --- Splinter family tuning ---
SPLINTER_CHILD_COUNT = 3
SPLINTER_CHILD_HP_RATIO = 0.20  # each child = 20% of parent's MAX HP
SPLINTERLING_ATK_RATIO = 0.60  # child attack ~60% of parent's attack
SPLINTERLING_SPD_ADD = 1  # child runs a bit faster
SPLINTER_UNLOCK_LEVEL = 2  # 0-based: unlock at Lv3 (after level 2)
# ----- meta progression -----
SPOILS_PER_KILL = 3
SPOILS_PER_BLOCK = 1
# ----- spoils UI & drop tuning -----
SPOILS_DROP_CHANCE = 0.35  # 35% drop chance on zombie deaths
SPOILS_BLOCK_DROP_CHANCE = 0.50  # 50% 概率掉 1 枚（必要时再调）
SPOILS_PER_TYPE = {  # average coins per zombie type (rounded when spawning)
    "basic": (1, 1),  # min, max
    "fast": (1, 2),
    "strong": (2, 3),
    "tank": (2, 4),
    "ranged": (1, 3),
    "suicide": (1, 2),
    "buffer": (2, 3),
    "shielder": (2, 3),
    "bomber": (1, 2),  # alias for suicide, if used
    "splinter": (1, 2),
    "splinterling": (0, 1),

}
# --- Twin Boss (Level 5 only) ---
ENABLE_TWIN_BOSS = True
TWIN_BOSS_LEVELS = {4}  # 关卡索引从0开始，4==第5关
TWIN_ENRAGE_ATK_MULT = 1.35
TWIN_ENRAGE_SPD_ADD  = 1
# --- boss footprint (2x2 tiles) ---
BOSS_FOOTPRINT_TILES = 2          # 占格：2x2
BOSS_VISUAL_MARGIN   = 6          # 视觉矩形边缘略收一点，避免贴边穿帮
BOSS_RADIUS_SHRINK   = 0.98       # 圆半径微缩，减少“卡像素”感


# coin bounce feel
COIN_POP_VY = -120.0  # initial vertical (screen-space) pop
COIN_GRAVITY = 400.0  # gravity pulling coin back to ground
COIN_RESTITUTION = 0.45  # energy kept on bounce
COIN_MIN_BOUNCE = 30.0  # stop bouncing when below this upward speed

XP_PLAYER_KILL = 6
XP_PLAYER_BLOCK = 2
XP_ZOMBIE_BLOCK = 3
XP_TRANSFER_RATIO = 0.7  # special → survivors
# --- shop pricing (level-scaled) ---
SHOP_PRICE_EXP = 1.12  # 每关指数涨幅（与 roguelite 节奏接近，10 关≈3.1x）
SHOP_PRICE_LINEAR = 0.02  # 每关线性微调（让早期也能感受到一点涨价）
SHOP_PRICE_STACK = 1.15  # 同一条目多次购买的叠加涨幅
SHOP_PRICE_REROLL_EXP = 1.06  # Reroll 的涨价更温和
SHOP_PRICE_REROLL_STACK = 1.25  # 多次 Reroll 叠加更贵（防刷）
# ----- healing drop tuning -----
HEAL_DROP_CHANCE_ZOMBIE = 0.12  # 12% when a zombie dies
HEAL_DROP_CHANCE_BLOCK = 0.08  # 8% when a destructible block is broken
HEAL_POTION_AMOUNT = 6  # HP restored on pickup (capped to player.max_hp)
# ----- player XP rewards by zombie type -----
XP_PER_ZOMBIE_TYPE = {
    "basic": 6,
    "fast": 7,
    "ranged": 7,
    "strong": 10,
    "tank": 12,
    "suicide": 9,  # if killed before it explodes
    "buffer": 6,
    "shielder": 8,
    "splinter": 8,
    "splinterling": 4,

}

XP_ZLEVEL_BONUS = 2  # bonus XP per zombie level above 1

ZOMBIE_XP_TO_LEVEL = 15  # per level step for monsters
PLAYER_XP_TO_LEVEL = 20  # base; scales by +20%
# --- zombie spoils empowerment ---
Z_SPOIL_HP_PER = 1  # 每 1 金币：+1 MaxHP & +1 当期HP
Z_SPOIL_ATK_STEP = 5  # 每 5 金币：+1 攻击
Z_SPOIL_SPD_STEP = 10  # 每 10 金币：+0.5 速度
Z_SPOIL_SPD_ADD = 0.5
Z_SPOIL_SPD_CAP = float(ZOMBIE_SPEED_MAX)  # 速度上限（保持与你总上限一致）
Z_SPOIL_XP_BONUS_PER = 1  # 击杀时额外经验=每枚金币+1 XP
Z_GLOW_TIME = 0.35  # 捡到金币时金色光晕持续时间（秒）

# ----- player XP curve tuning -----
# Requirement to go from level L -> L+1:
#   base * (exp_growth ** (L-1)) + linear_growth * L + softcap_bump(L)
XP_CURVE_EXP_GROWTH = 1.12  # 10–13% feels good for roguelites; we use 12%
XP_CURVE_LINEAR = 3  # small linear term to smooth gaps
XP_CURVE_SOFTCAP_START = 7  # start softly increasing after level 7
XP_CURVE_SOFTCAP_POWER = 1.6  # how sharp the softcap rises (1.4–1.8 typical)

# ----- monster global scaling (by game level & wave) -----
MON_HP_GROWTH_PER_LEVEL = 0.10  # +10% HP per game level
MON_ATK_GROWTH_PER_LEVEL = 0.08  # +8% ATK per game level
MON_SPD_ADD_EVERY_LEVELS = 4  # +1 speed every N levels (soft cap below)
MON_SOFTCAP_LEVEL = 10  # reduce growth beyond this (diminishing)
MON_SOFTCAP_FACTOR = 0.6  # scale growth beyond softcap by this factor

MON_HP_GROWTH_PER_WAVE = 0.06  # +6% HP per wave
MON_ATK_GROWTH_PER_WAVE = 0.05  # +5% ATK per wave
MON_SPD_ADD_EVERY_WAVES = 6  # +1 speed every N waves

# ----- elites & bosses -----
ELITE_BASE_CHANCE = 0.08  # 8% at level 1
ELITE_CHANCE_PER_LEVEL = 0.02  # +2% per game level (clamped)
ELITE_MAX_CHANCE = 0.35
ELITE_HP_MULT_EXTRA = 1.6  # multiplicative on top of normal scaling
ELITE_ATK_MULT_EXTRA = 1.4
ELITE_SPD_ADD_EXTRA = 1

BOSS_EVERY_N_LEVELS = 5
BOSS_HP_MULT_EXTRA = 3.0
BOSS_ATK_MULT_EXTRA = 2.0
BOSS_SPD_ADD_EXTRA = 1

# ===== Boss1: Memory Devourer (腐蚀集群之心) =====
# 数值：显著增厚血量与接触伤害
MEMDEV_BASE_HP = 4200       # 以第5关为基准：从 1200 → 4200
MEMDEV_CONTACT_DAMAGE = 60  # 接触伤害提高
MEMDEV_SPEED = 0.9          # 很慢（后续阶段再涨）

# Boss 外形/占格（仅碰撞与显示，不改变地图阻挡规则）
BOSS_SIZE_FACTOR = 3.65     # 可视尺寸 = 1.65 × 单格
BOSS_RADIUS_FACTOR = 1.80   # 脚底圆半径 = 0.90 × 单格（≈直径1.8格，能“卡住”单格通道）

# Boss 掉落（保证性掉落，额外返还它吞的金币）
BOSS_LOOT_MIN = 24
BOSS_LOOT_MAX = 36
BOSS_HEAL_POTIONS = 2       # 击杀掉落的治疗瓶数量

# P1 / P2 酸液喷吐（地面腐蚀池）
ACID_DPS = 15  # 站上去每秒伤害
ACID_SLOW_FRAC = 0.45  # 减速 45%
ACID_LIFETIME = 6.0
ACID_TELEGRAPH_T = 0.6  # 提示圈时长
ACID_DOT_DURATION = 2.0     # 离开酸池后继续掉血的持续时间(秒)
ACID_DOT_MULT = 0.6         # DoT 的每秒伤害 = ACID_DPS * 这个系数
SPIT_WAVES_P1 = 3
SPIT_WAVES_P2 = 2  # 连续两次喷吐（每次多波）
SPIT_CONE_DEG = 60
SPIT_PUDDLES_PER_WAVE = 6
SPIT_RANGE = 6.0 * CELL_SIZE  # 每波最远生成点

# 召唤小怪（腐蚀幼体）
SPLIT_CD_P1 = 20.0
SPLIT_CD_P2 = 15.0
CHILD_HP = 50
CHILD_ATK = 10
CHILD_SPEED = 2.2

# 吸附融合（小怪>15s被拉回，BOSS 恢复100）
FUSION_LIFETIME = 15.0
FUSION_HEAL = 100
FUSION_PULL_RADIUS = 8.0 * CELL_SIZE

# P3 全屏酸爆（每掉 10% 触发一次）
RAIN_STEP = 0.10
RAIN_PUDDLES = 18
RAIN_TELEGRAPH_T = 0.5

# 濒死冲锋（<10%）
CHARGE_THRESH = 0.10
CHARGE_SPEED = 3.0

# ----- affixes (small random spice) -----
AFFIX_CHANCE_BASE = 0.10
AFFIX_CHANCE_PER_LEVEL = 0.02
AFFIX_CHANCE_MAX = 0.45

# ----- spoils & XP inheritance tuning -----
XP_INHERIT_RADIUS = 240  # px: who is "nearby" to inherit XP
ZOMBIE_SIZE_MAX = int(CELL_SIZE * 1.8)  # cap size when buffed by XP
SPOIL_POP_VY = -30  # initial pop-up velocity for coin
SPOIL_GRAVITY = 80  # settle speed for coin pop

BOSS_EVERY_N_LEVELS = 5
BOSS_HP_MULT = 4.0
BOSS_ATK_MULT = 2.0
BOSS_SPD_ADD = 1

# persistent (per run) upgrades bought in shop
META = {"spoils": 0, "dmg": 0, "firerate_mult": 1.0, "speed": 0, "maxhp": 0, "crit": 0.0}


def reset_run_state():
    """开新局时把本轮相关的所有进度归零（不影响设置里的音量等）。"""
    META.clear()
    META.update({
        "spoils": 0,  # 本轮金币
        "dmg": 0,
        "firerate_mult": 1.0,
        "speed": 0,
        "maxhp": 0,
        "crit": 0.0
    })
    globals()["_carry_player_state"] = None  # 不带上一次的等级/经验
    globals()["_pending_shop"] = False  # 不从商店续开
    globals().pop("_last_spoils", None)  # 清掉关末结算缓存


def shop_price(base_cost: int, level_idx: int, kind: str = "normal") -> int:
    """
    同一关内价格固定；进入下一关时按曲线整体上调。
    kind = "reroll" 时保持恒定，不随关卡变化。
    """
    if kind == "reroll":
        return int(base_cost)  # 恒定不变

    # 只按关卡指数+线性项调整；不再叠加“同一条目已购买次数”的涨幅
    exp = (SHOP_PRICE_EXP ** level_idx)
    lin = (1.0 + SHOP_PRICE_LINEAR * level_idx)
    price = int(round(base_cost * exp * lin))
    return max(1, price)


# resume flags
_pending_shop = False  # if True, CONTINUE should open the shop first

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
    "splinter": (180, 120, 250),
    "splinterling": (210, 160, 255),

}
# --- colors (add) ---
ZOMBIE_COLORS.update({
    "boss_mem": (170, 40, 200),  # 紫红色
    "corruptling": (120, 220, 120),  # 浅绿
})

# --- XP rewards (add) ---
XP_PER_ZOMBIE_TYPE.update({
    "boss_mem": 40,  # base 给足奖励；击杀时还有 is_boss 3x 乘区
    "corruptling": 5,
})

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
# ----- threat budget spawning -----
THREAT_BUDGET_BASE = 6  # base points for level 0 (Lv1 in UI)
THREAT_BUDGET_EXP = 1.18  # exponential growth per level (≈+18%/lvl feels roguelite)
THREAT_BUDGET_MIN = 5  # never below this
THREAT_BOSS_BONUS = 1.5  # first spawn on boss level gets +50% budget

# cost per zombie type (integer points)
THREAT_COSTS = {
    "basic": 1,
    "fast": 2,
    "ranged": 3,
    "suicide": 2,
    "buffer": 3,
    "shielder": 3,
    "strong": 4,
    "tank": 5,
    "splinter": 4,

}
# (Optional) relative preference if multiple types fit the remaining budget
THREAT_WEIGHTS = {
    "basic": 50,
    "fast": 20,
    "ranged": 16,
    "suicide": 14,
    "buffer": 10,
    "shielder": 10,
    "strong": 8,
    "tank": 6,
    "splinter": 10,

}

# --- combat tuning (Brotato-like) ---
FIRE_RATE = None  # shots per second; if None, derive from BULLET_SPACING_PX
BULLET_SPEED = 1000.0  # pixels per second (controls travel speed)
BULLET_SPACING_PX = 260.0  # desired spacing between bullets along their path
BULLET_RADIUS = 4
BULLET_DAMAGE_ZOMBIE = 12
BULLET_DAMAGE_BLOCK = 10
ENEMY_SHOT_DAMAGE_BLOCK = BULLET_DAMAGE_BLOCK
MAX_FIRE_RANGE = 800.0  # pixels
# --- targeting / auto-aim (new) ---
PLAYER_TARGET_RANGE = MAX_FIRE_RANGE        # 射程内才会当候选（默认=子弹射程）
PLAYER_BLOCK_FORCE_RANGE_TILES = 2          # 玩家两格内遇到可破坏物 → 强制优先
# --- CRIT & damage text ---
CRIT_CHANCE_BASE = 0.05  # 基础暴击率=5%
CRIT_MULT_BASE = 1.8  # 暴击伤害倍数，后续可以做商店项
DMG_TEXT_TTL = 0.8  # 飘字存活时长（秒）
DMG_TEXT_RISE = 42.0  # 垂直上升速度（像素/秒）
DMG_TEXT_FADE = 0.25  # 尾段淡出比例（最后 25% 时间开始透明）
DMG_TEXT_SIZE_NORMAL = 28
DMG_TEXT_SIZE_CRIT = 38

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


def save_progress(current_level: int,
                  zombie_cards_collected: list,
                  max_wave_reached: int | None = None,
                  pending_shop: bool = False):
    """Persist minimal progress plus META upgrades and player carry."""
    data = {
        "mode": "progress",
        "current_level": int(current_level),
        "zombie_cards_collected": list(zombie_cards_collected),
        "meta": dict(META),  # dmg, firerate_mult, speed, maxhp, spoils
        "carry_player": globals().get("_carry_player_state", None),
        "pending_shop": bool(pending_shop)  # <<< NEW
    }
    if max_wave_reached is not None:
        data["max_wave_reached"] = int(max_wave_reached)
    try:
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save_progress error:", e)


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
                       "hit_cd": float(getattr(player, "hit_cd", 0.0)),
                       "level": int(getattr(player, "level", 1)),
                       "xp": int(getattr(player, "xp", 0))},
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
def iso_equalized_step(dx: float, dy: float, speed: float) -> tuple[float, float]:
    """
    在等距投影下，将单位方向(dx,dy)缩放到“屏幕上恒定速度= speed 像素/帧（或/步）”。
    非等距则直接返回 dx*speed, dy*speed。
    """
    if not USE_ISO:
        return dx * speed, dy * speed

    half_w = ISO_CELL_W * 0.5
    half_h = ISO_CELL_H * 0.5
    # 这个方向对应的屏幕位移长度
    sx = (dx - dy) * half_w
    sy = (dx + dy) * half_h
    screen_mag = math.hypot(sx, sy) or 1.0
    scale = float(speed) * float(ISO_EQ_GAIN) / screen_mag
    return dx * scale, dy * scale


def collide_and_slide_circle(entity, obstacles_iter, dx, dy):
    """
    以“圆心 + Minkowski 外扩”的方式，做【扫掠式】轴分离碰撞：
    - X 轴先扫：用线段(cx0 → cx1)与每个扩张矩形的左右边做一次1D相交测试，命中则把终点夹到边界；
    - Y 轴再扫：同理对上下边；
    这样即便步长较大/从角上斜切也不会穿过去。
    """
    entity._hit_ob = None
    r = getattr(entity, "radius", max(8, CELL_SIZE // 3))
    size = entity.size

    # 起点（圆心，世界像素）
    cx0 = entity.x + size * 0.5
    cy0 = entity.y + size * 0.5 + INFO_BAR_HEIGHT

    # ---------- X 轴扫掠 ----------
    cx1 = cx0 + dx
    hit_x = None
    # 向右：找所有满足 cy0 ∈ [top, bottom] 且 线段跨过 left 的矩形，取最靠近的边
    if dx > 0:
        min_left = None
        for ob in obstacles_iter:
            exp = ob.rect.inflate(r * 2, r * 2)
            if exp.top <= cy0 <= exp.bottom and cx0 <= exp.left <= cx1:
                if (min_left is None) or (exp.left < min_left[0]):
                    min_left = (exp.left, ob)
        if min_left:
            cx1 = min_left[0]
            hit_x = min_left[1]
    # 向左：对 right 边做相同处理
    elif dx < 0:
        max_right = None
        for ob in obstacles_iter:
            exp = ob.rect.inflate(r * 2, r * 2)
            if exp.top <= cy0 <= exp.bottom and cx1 <= exp.right <= cx0:
                if (max_right is None) or (exp.right > max_right[0]):
                    max_right = (exp.right, ob)
        if max_right:
            cx1 = max_right[0]
            hit_x = max_right[1]

    if hit_x is not None:
        entity._hit_ob = hit_x
    x_min, y_min, x_max, y_max = play_bounds_for_circle(r)
    cx1 = max(x_min, min(cx1, x_max))

    entity.x = cx1 - size * 0.5  # 应用X位移（已夹到边界）

    # 更新圆心（X 已经改变）
    cx0 = entity.x + size * 0.5
    cy0 = entity.y + size * 0.5 + INFO_BAR_HEIGHT

    # ---------- Y 轴扫掠 ----------
    cy1 = cy0 + dy
    hit_y = None
    if dy > 0:
        min_top = None
        for ob in obstacles_iter:
            exp = ob.rect.inflate(r * 2, r * 2)
            if exp.left <= cx0 <= exp.right and cy0 <= exp.top <= cy1:
                if (min_top is None) or (exp.top < min_top[0]):
                    min_top = (exp.top, ob)
        if min_top:
            cy1 = min_top[0]
            hit_y = min_top[1]
    elif dy < 0:
        max_bottom = None
        for ob in obstacles_iter:
            exp = ob.rect.inflate(r * 2, r * 2)
            if exp.left <= cx0 <= exp.right and cy1 <= exp.bottom <= cy0:
                if (max_bottom is None) or (exp.bottom > max_bottom[0]):
                    max_bottom = (exp.bottom, ob)
        if max_bottom:
            cy1 = max_bottom[0]
            hit_y = max_bottom[1]

    if hit_y is not None:
        entity._hit_ob = hit_y
    x_min, y_min, x_max, y_max = play_bounds_for_circle(r)
    cy1 = max(y_min, min(cy1, y_max))
    # 应用Y位移（注意把 INFO_BAR_HEIGHT 减回去）
    entity.y = cy1 - size * 0.5 - INFO_BAR_HEIGHT

    # 同步 AABB（仅用于渲染/命中盒）
    entity.rect.x = int(entity.x)
    entity.rect.y = int(entity.y) + INFO_BAR_HEIGHT


# === NEW: 等距相机偏移（基于玩家像素中心 → 网格中心 → 屏幕等距投影） ===
def calculate_iso_camera(player_x_px: float, player_y_px: float) -> tuple[int, int]:
    px_grid = player_x_px / CELL_SIZE
    py_grid = player_y_px / CELL_SIZE
    # 投到屏幕（不带 cam 偏移）
    pxs, pys = iso_world_to_screen(px_grid, py_grid, 0.0, 0.0, 0.0)
    camx = pxs - VIEW_W // 2
    camy = pys - (VIEW_H - INFO_BAR_HEIGHT) // 2
    return int(camx), int(camy)


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
                    # hard reset the run state the instant START NEW is clicked
                    clear_save()  # delete savegame.json if it exists
                    reset_run_state()  # zero META, clear carry, cancel pending shop, drop _last_spoils
                    door_transition(screen)
                    flush_events()
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
    """Draw pause overlay with build info in the dimmed background, keeping buttons centered."""
    # 创建半透明背景
    dim = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 170))
    bg_scaled = pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H))
    screen.blit(bg_scaled, (0, 0))
    screen.blit(dim, (0, 0))

    # 在变暗的背景中显示玩家build信息
    font_small = pygame.font.SysFont(None, 28)
    font_tiny = pygame.font.SysFont(None, 22)

    # 左上角显示基本属性
    left_margin = 30
    top_margin = 30
    y_offset = top_margin

    # 标题
    title = font_small.render("Player Stats", True, (230, 230, 230))
    screen.blit(title, (left_margin, y_offset))
    y_offset += 40

    # 伤害加成
    dmg_text = font_tiny.render(f"Damage: +{META['dmg']}", True, (230, 100, 100))
    screen.blit(dmg_text, (left_margin, y_offset))
    y_offset += 30

    # 射速加成
    fr_text = font_tiny.render(f"Fire Rate: {META['firerate_mult']:.2f}x", True, (100, 200, 100))
    screen.blit(fr_text, (left_margin, y_offset))
    y_offset += 30

    # 速度加成
    speed_text = font_tiny.render(f"Speed: +{META['speed']}", True, (100, 100, 230))
    screen.blit(speed_text, (left_margin, y_offset))
    y_offset += 30

    # 生命值加成
    hp_text = font_tiny.render(f"Max HP: +{META['maxhp']}", True, (230, 150, 100))
    screen.blit(hp_text, (left_margin, y_offset))
    y_offset += 30

    # 暴击加成
    crit_pct = int((CRIT_CHANCE_BASE + META.get("crit", 0.0)) * 100)
    crit_text = font_tiny.render(f"Crit Chance: {crit_pct}%", True, (255, 220, 120))
    screen.blit(crit_text, (left_margin, y_offset));
    y_offset += 30

    # 右上角显示收集的卡牌
    right_margin = VIEW_W - 30
    y_offset = top_margin

    # 标题
    title = font_small.render("Zombie Cards", True, (230, 230, 230))
    title_rect = title.get_rect(right=right_margin, top=y_offset)
    screen.blit(title, title_rect)
    y_offset += 40

    if zombie_cards_collected:
        for i, card in enumerate(zombie_cards_collected):
            if y_offset < VIEW_H - 100:  # 确保不会超出屏幕
                card_text = font_tiny.render(f"• {card.replace('_', ' ').title()}", True, (200, 200, 200))
                card_rect = card_text.get_rect(right=right_margin, top=y_offset)
                screen.blit(card_text, card_rect)
                y_offset += 30
    else:
        no_cards_text = font_tiny.render("None collected yet", True, (150, 150, 150))
        no_cards_rect = no_cards_text.get_rect(right=right_margin, top=y_offset)
        screen.blit(no_cards_text, no_cards_rect)
        y_offset += 30

    # 保持原有暂停菜单面板和按钮布局不变
    panel_w, panel_h = min(520, VIEW_W - 80), min(500, VIEW_H - 160)
    panel = pygame.Rect(0, 0, panel_w, panel_h)
    panel.center = (VIEW_W // 2, VIEW_H // 2)
    pygame.draw.rect(screen, (30, 30, 30), panel, border_radius=16)
    pygame.draw.rect(screen, (60, 60, 60), panel, width=3, border_radius=16)

    title = pygame.font.SysFont(None, 72).render("Paused", True, (230, 230, 230))
    screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 58)))

    # 按钮保持原有位置和样式
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


def show_shop_screen(screen) -> Optional[str]:
    """Spend META['spoils'] on small upgrades. ESC opens Pause; return action or None when closed."""
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 30)
    title_font = pygame.font.SysFont(None, 56)
    btn_font = pygame.font.SysFont(None, 32)

    # pseudo-random offers
    catalog = [
        {"name": "+1 Damage", "key": "dmg", "cost": 6, "apply": lambda: META.update(dmg=META["dmg"] + 1)},
        {"name": "+5% Fire Rate", "key": "firerate", "cost": 7,
         "apply": lambda: META.update(firerate_mult=META["firerate_mult"] * 1.10)},
        {"name": "+1 Speed", "key": "speed", "cost": 8, "apply": lambda: META.update(speed=META["speed"] + 1)},
        {"name": "+5 Max HP", "key": "maxhp", "cost": 8, "apply": lambda: META.update(maxhp=META["maxhp"] + 5)},
        {"name": "+5% Crit", "key": "crit", "cost": 9,
         "apply": lambda: META.update(crit=min(0.75, META.get("crit", 0.0) + 0.05))},

        {"name": "Reroll Offers", "key": "reroll", "cost": 3, "apply": "reroll"},
    ]

    def roll_offers():
        pool = [c for c in catalog if c["name"] != "Reroll Offers"]
        offers = random.sample(pool, k=min(4, len(pool)))
        offers.append(next(c for c in catalog if c["name"] == "Reroll Offers"))
        return offers

    offers = roll_offers()

    while True:
        # --- draw ---
        screen.fill((16, 16, 18))

        # Title (center)
        title_surf = title_font.render("TRADER", True, (235, 235, 235))
        screen.blit(title_surf, title_surf.get_rect(center=(VIEW_W // 2, 80)))

        # Spoils (center under title)
        money_surf = font.render(f"Spoils: {META['spoils']}", True, (255, 230, 120))
        screen.blit(money_surf, money_surf.get_rect(center=(VIEW_W // 2, 130)))

        # Offers row — centered as a group
        card_w, card_h = 170, 120
        gap = 18
        total_w = len(offers) * card_w + (len(offers) - 1) * gap
        start_x = (VIEW_W - total_w) // 2
        y = 200

        rects = []
        for i, it in enumerate(offers):
            x = start_x + i * (card_w + gap)
            r = pygame.Rect(x, y, card_w, card_h)

            pygame.draw.rect(screen, (40, 40, 42), r, border_radius=10)
            pygame.draw.rect(screen, (80, 80, 84), r, 2, border_radius=10)

            # 关卡索引（0-based），如果没取到就当 0 关
            level_idx = int(globals().get("current_level", 0))
            kind = "reroll" if it["apply"] == "reroll" else "normal"
            dyn_cost = shop_price(int(it["cost"]), level_idx, kind=kind)

            name = font.render(it["name"], True, (230, 230, 230))
            cost = font.render(f"{dyn_cost}¥", True, (255, 210, 130))
            screen.blit(name, name.get_rect(midleft=(r.x + 12, r.y + 34)))
            screen.blit(cost, cost.get_rect(midleft=(r.x + 12, r.y + 78)))

            # 保存“点击用的价格”
            rects.append((r, it, dyn_cost))

        # NEXT button — centered under cards
        close = pygame.Rect(0, 0, 220, 56)
        close.center = (VIEW_W // 2, y + card_h + 80)
        pygame.draw.rect(screen, (50, 50, 50), close, border_radius=10)
        ctxt = btn_font.render("NEXT", True, (235, 235, 235))
        screen.blit(ctxt, ctxt.get_rect(center=close.center))

        pygame.display.flip()

        # --- input ---
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit();
                sys.exit()

            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                # Pause menu over the shop; continue/settings return to shop
                bg = screen.copy()
                choice = pause_from_overlay(screen, bg)
                if choice in (None, "continue", "settings"):
                    flush_events()
                    break
                flush_events()
                return choice  # home / restart / exit

            if ev.type == pygame.MOUSEBUTTONDOWN:
                if close.collidepoint(ev.pos):
                    flush_events()
                    # <<< 在 NEXT 之后弹出“场景四选一” >>>
                    chosen_biome = show_biome_picker_in_shop(screen)
                    # 识别从翻卡界面透传出来的暂停菜单选择
                    if chosen_biome in ("__HOME__", "__RESTART__", "__EXIT__"):
                        return {"__HOME__": "home", "__RESTART__": "restart", "__EXIT__": "exit"}[chosen_biome]

                    globals()["_next_biome"] = chosen_biome  # 正常选择到场景名
                    return None  # 照常结束商店，进入下一关

                for r, it, dyn_cost in rects:
                    if r.collidepoint(ev.pos) and META["spoils"] >= dyn_cost:
                        META["spoils"] -= dyn_cost
                        if it["apply"] == "reroll":
                            offers = roll_offers()  # 价格保持原样
                        else:
                            it["apply"]()

        clock.tick(60)


def show_biome_picker_in_shop(screen) -> str:
    """在商店 NEXT 之后弹出的“下关场景”四选一卡面。返回被选择的场景名。"""
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont(None, 56)
    font = pygame.font.SysFont(None, 26)
    back_font = pygame.font.SysFont(None, 48)

    # 随机打乱四张卡的排列顺序（卡面名称固定）
    names = list(SCENE_BIOMES)
    random.shuffle(names)

    # 卡片布局
    card_w, card_h = 180, 240
    gap = 20
    total_w = len(names) * card_w + (len(names) - 1) * gap
    start_x = (VIEW_W - total_w) // 2
    y = 160

    # 卡片对象
    cards = []
    for i, name in enumerate(names):
        x = start_x + i * (card_w + gap)
        rect = pygame.Rect(x, y, card_w, card_h)
        cards.append({"name": name, "rect": rect, "revealed": False})

    chosen = None  # 只允许选择一张

    # 确认按钮
    confirm = pygame.Rect(0, 0, 240, 56)
    confirm.center = (VIEW_W // 2, y + card_h + 90)

    def draw():
        screen.fill((16, 16, 18))
        # 标题
        title = title_font.render("CHOOSE NEXT DOMAIN", True, (235, 235, 235))
        screen.blit(title, title.get_rect(center=(VIEW_W // 2, 90)))

        # 画四张卡
        for c in cards:
            r = c["rect"]
            if c["revealed"]:
                # 正面：高亮的卡面 + 名称
                pygame.draw.rect(screen, (60, 66, 70), r, border_radius=12)
                pygame.draw.rect(screen, (200, 200, 210), r, 2, border_radius=12)
                name = c["name"].upper()
                # 名称可能较长，分两行居中
                parts = name.split()
                text_lines = [" ".join(parts[:2]), " ".join(parts[2:])] if len(parts) > 2 else [name]
                ty = r.centery - (len(text_lines) * 22) // 2
                for line in text_lines:
                    surf = font.render(line, True, (240, 240, 240))
                    screen.blit(surf, surf.get_rect(center=(r.centerx, ty)))
                    ty += 28
                # 若是被选中的卡，再加一道边框
                if chosen == c["name"]:
                    pygame.draw.rect(screen, (255, 215, 120), r.inflate(6, 6), 3, border_radius=14)
            else:
                # 背面：深色 + “？”
                pygame.draw.rect(screen, (36, 38, 42), r, border_radius=12)
                pygame.draw.rect(screen, (80, 80, 84), r, 2, border_radius=12)
                q = back_font.render("?", True, (180, 180, 190))
                screen.blit(q, q.get_rect(center=r.center))

        # 确认按钮（未选时灰掉）
        if chosen:
            pygame.draw.rect(screen, (50, 50, 50), confirm, border_radius=10)
            txt = pygame.font.SysFont(None, 32).render("CONFIRM", True, (235, 235, 235))
        else:
            pygame.draw.rect(screen, (35, 35, 35), confirm, border_radius=10)
            txt = pygame.font.SysFont(None, 32).render("CONFIRM", True, (120, 120, 120))
        screen.blit(txt, txt.get_rect(center=confirm.center))

        pygame.display.flip()

    while True:
        draw()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit();
                sys.exit()
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                bg = screen.copy()
                pick = pause_from_overlay(screen, bg)
                if pick in (None, "continue", "settings"):
                    flush_events()
                    continue  # 回到翻卡界面
                if pick == "home":
                    door_transition(screen)
                    flush_events()
                    return "__HOME__"
                if pick == "restart":
                    door_transition(screen)
                    flush_events()
                    return "__RESTART__"
                if pick == "exit":
                    pygame.quit()
                    sys.exit()

            if ev.type == pygame.MOUSEBUTTONDOWN:
                # 点击卡片：若还未选中任何卡，则把这张翻开并选中；其他保持背面
                if chosen is None:
                    for c in cards:
                        if c["rect"].collidepoint(ev.pos):
                            c["revealed"] = True
                            chosen = c["name"]
                            break
                # 点击确认：只有当 chosen 存在（即至少翻开并选择了一张）才生效
                if chosen and confirm.collidepoint(ev.pos):
                    flush_events()
                    return chosen
        clock.tick(60)


def is_boss_level(level_idx_zero_based: int) -> bool:
    # UI shows Lv = level_idx_zero_based + 1
    return ((level_idx_zero_based + 1) % BOSS_EVERY_N_LEVELS) == 0


def budget_for_level(level_idx_zero_based: int) -> int:
    # Identical within level; exponential per level (clamped to a sane minimum)
    return max(THREAT_BUDGET_MIN,
               int(round(THREAT_BUDGET_BASE * (THREAT_BUDGET_EXP ** level_idx_zero_based))))


def _pick_type_by_budget(rem: int, level_idx_zero_based: int) -> Optional[str]:
    def _unlocked(t: str) -> bool:
        if t == "splinter":
            return level_idx_zero_based >= SPLINTER_UNLOCK_LEVEL
        return True  # others always unlocked

    choices = [(t, w) for t, w in THREAT_WEIGHTS.items()
               if THREAT_COSTS.get(t, 999) <= rem and _unlocked(t)]
    if not choices:
        return None
    total = sum(w for _, w in choices)
    r = random.uniform(0, total)
    acc = 0.0
    for t, w in choices:
        acc += w
        if r <= acc:
            return t
    return choices[-1][0]


def _spawn_positions(game_state: "GameState", player: "Player", zombies: List["Zombie"], want: int) -> List[
    Tuple[int, int]]:
    """Reuse your existing constraints: not blocked, not too close to player, not overlapping zombies."""
    all_pos = [(x, y) for x in range(GRID_SIZE) for y in range(GRID_SIZE)]
    blocked = set(game_state.obstacles.keys()) | set((i.x, i.y) for i in getattr(game_state, "items", []))
    px, py = int(player.rect.centerx // CELL_SIZE), int((player.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE)
    # Manhattan ≥ 6 tiles from player like before
    cand = [p for p in all_pos if p not in blocked and abs(p[0] - px) + abs(p[1] - py) >= 6]
    random.shuffle(cand)
    zcells = {(int((z.x + z.size // 2) // CELL_SIZE), int((z.y + z.size // 2) // CELL_SIZE)) for z in zombies}
    out = []
    for p in cand:
        if p in zcells:
            continue
        out.append(p)
        if len(out) >= want:
            break
    return out


def promote_to_boss(z: "Zombie"):
    """Promote a single zombie instance to boss (stats on top of current scaling)."""
    z.is_boss = True
    z.max_hp = int(z.max_hp * BOSS_HP_MULT_EXTRA); z.hp = z.max_hp
    z.attack = int(z.attack * BOSS_ATK_MULT_EXTRA)
    z.speed += BOSS_SPD_ADD_EXTRA

    # === NEW: enlarge physical footprint ===
    # 把 BOSS 的 AABB 拉大到 ~1.6 格高（等距里观感是“很占屏”）
    old_cx, old_cy = z.rect.center
    z.size = int(CELL_SIZE * 1.6)          # 占屏与卡位都更像“BOSS”
    z.rect = pygame.Rect(0, 0, z.size, z.size)
    z.rect.center = (old_cx, old_cy)
    # 同步世界坐标（你的 move/渲染有用到 x/y）
    z.x = float(z.rect.x)
    z.y = float(z.rect.y - INFO_BAR_HEIGHT)


def spawn_wave_with_budget(game_state: "GameState",
                           player: "Player",
                           current_level: int,
                           wave_index: int,
                           zombies: List["Zombie"],
                           cap: int) -> int:
    """
    Spend the per-level budget on new zombies, respecting cap.
    Returns the number spawned.
    """
    if len(zombies) >= cap:
        return 0

    # base budget for this level (identical every spawn this level)
    budget = budget_for_level(current_level)

    # boss level first spawn: extra budget & force exactly one boss
    force_boss = is_boss_level(current_level) and (wave_index == 0)
    if force_boss:
        budget = int(budget * THREAT_BOSS_BONUS)

    # optimistic position pool (ask for up to budget cells)
    spots = _spawn_positions(game_state, player, zombies, want=budget)
    spawned = 0
    boss_done = False

    # spend budget until no type fits or cap/positions exhausted
    i = 0
    while i < len(spots) and len(zombies) < cap:
        gx, gy = spots[i]
        i += 1
        # if we must place a boss, do it once, then continue budget spending
        if force_boss and not boss_done:
            # 第5关采用 Twin；其余 Boss 关单体
            if ENABLE_TWIN_BOSS and (current_level in TWIN_BOSS_LEVELS):
                (gx1, gy1) = gx, gy
                (gx2, gy2) = min(gx + 2, GRID_SIZE - 1), gy  # 简单平移，避免重叠
                b1 = create_memory_devourer((gx1, gy1), current_level)
                b2 = create_memory_devourer((gx2, gy2), current_level)
                twin_id = random.randint(1000, 9999)
                #bind twins
                b1._spawn_wave_tag = wave_index
                b2._spawn_wave_tag = wave_index
                zombies.append(b1)
                zombies.append(b2)
                boss_done = True

            else:
                z = create_memory_devourer((gx, gy), current_level)
                z._spawn_wave_tag = wave_index
                zombies.append(z)
                boss_done = True


        # choose a type that fits remaining budget
        remaining = budget - sum(THREAT_COSTS.get(getattr(z, "type", "basic"), 0) for z in zombies if
                                 getattr(z, "_spawn_wave_tag", -1) == wave_index)
        t = _pick_type_by_budget(max(1, remaining), current_level)

        if not t:
            break  # can't afford any type

        z = make_scaled_zombie((gx, gy), t,
                               current_level,
                               # IMPORTANT: if this is a boss level first wave,
                               # pass wave_index=1 for non-boss spawns to avoid accidental boss flag in older code
                               (1 if (is_boss_level(current_level) and wave_index == 0) else wave_index))
        # mark which wave inserted this zombie (used above to compute remaining)
        z._spawn_wave_tag = wave_index

        zombies.append(z)
        spawned += 1

    return spawned


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
        # if USE_ISO:
        #     # 先收一点，近似菱形脚印
        #     w_in = int(CELL_SIZE * 0.20)
        #     h_in = int(CELL_SIZE * 0.30)
        #     foot = self.rect.inflate(-w_in, -h_in)
        #
        #     self.rect = foot

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
        self.speed = float(speed)
        self.size = CELL_SIZE - 6
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)
        self.max_hp = int(PLAYER_MAX_HP)
        self.hp = int(PLAYER_MAX_HP)
        # --- crit stats ---
        self.crit_chance = max(0.0, min(0.95, CRIT_CHANCE_BASE + float(META.get("crit", 0.0))))
        self.crit_mult = float(CRIT_MULT_BASE)
        self.slow_t = 0.0
        self.slow_mult = 1.0  #

        self.hit_cd = 0.0  # contact invulnerability timer (seconds)
        self.radius = PLAYER_RADIUS

        # progression
        self.level = 1
        self.xp = 0
        self.xp_to_next = player_xp_required(self.level)

        # per-run upgrades from shop (applied on spawn)
        self.bullet_damage = BULLET_DAMAGE_ZOMBIE + META.get("dmg", 0)
        self.fire_rate_mult = META.get("firerate_mult", 1.0)
        self.speed = min(PLAYER_SPEED_CAP, max(1.0, self.speed + float(META.get("speed", 0))))
        self.max_hp += META.get("maxhp", 0)
        self.hp = min(self.hp + META.get("maxhp", 0), self.max_hp)
        self.acid_dot_timer = 0.0  # 还剩多少秒的DoT
        self.acid_dot_dps = 0.0  # 当前DoT每秒伤害（根据最近踩到的酸池设置）
        self._acid_dmg_accum = 0.0  # 在池中时的“本帧累计伤害”浮点缓存
        self._acid_dot_accum = 0.0  # 离开池后DoT的累计伤害缓存

    @property
    def pos(self):
        return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)

    def move(self, keys, obstacles):
        # --- ISO 控制映射---
        mx = my = 0
        if keys[pygame.K_w]:
            mx -= 1;
            my -= 1  # 屏幕↑
        if keys[pygame.K_s]:
            mx += 1;
            my += 1  # 屏幕↓
        if keys[pygame.K_a]:
            mx -= 1;
            my += 1  # 屏幕←
        if keys[pygame.K_d]:
            mx += 1;
            my -= 1  # 屏幕→
        if mx != 0 or my != 0:
            # 归一化保证对角速度一致
            length = (mx * mx + my * my) ** 0.5
            dx = (mx / length)
            dy = (my / length)
        else:
            dx = dy = 0.0

        # 基础速度
        spd = int(self.speed)
        # 处于减速状态 → 应用减速（例如 35% 减速 = 速度*0.65）
        if getattr(self, "slow_t", 0.0) > 0.0:
            spd = max(1, int(spd * (1.0 - ACID_SLOW_FRAC)))  # ACID_SLOW_FRAC 建议 0.35~0.45

        # 把“减速后的速度”喂给步进与碰撞
        step_x, step_y = iso_equalized_step(dx, dy, spd)
        collide_and_slide_circle(self, obstacles.values(), step_x, step_y)

    def fire_cooldown(self) -> float:
        # smaller is faster; clamp to avoid abuse
        return FIRE_COOLDOWN / max(0.25, float(self.fire_rate_mult))

    def add_xp(self, amount: int):
        self.xp += int(max(0, amount))
        # multiple level-ups if a big XP spike arrives
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.level += 1

            # small, reasonable level-up benefits
            self.bullet_damage += 1  # steady firepower growth
            self.max_hp += 2  # tiny durability growth
            self.hp = min(self.max_hp, self.hp + 3)  # low heal on level-up

            # recompute requirement from the curve for the NEW level
            self.xp_to_next = player_xp_required(self.level)

    def draw(self, screen):
        pygame.draw.rect(screen, (0, 255, 0), self.rect)


# --- module-level helper: split parent into 3 splinterlings ---
def spawn_splinter_children(parent: "Zombie",
                            zombies: list,
                            game_state: "GameState",
                            level_idx: int,
                            wave_index: int):
    gx = int((parent.x + parent.size * 0.5) // CELL_SIZE)
    gy = int((parent.y + parent.size) // CELL_SIZE)
    neighbors = [(gx + dx, gy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if not (dx == 0 and dy == 0)]
    random.shuffle(neighbors)

    child_hp = max(1, int(parent.max_hp * SPLINTER_CHILD_HP_RATIO))
    child_atk = max(1, int(parent.attack * SPLINTERLING_ATK_RATIO))
    child_speed = min(ZOMBIE_SPEED_MAX, int(parent.speed) + int(SPLINTERLING_SPD_ADD))

    spawned = 0
    for nx, ny in neighbors:
        if spawned >= SPLINTER_CHILD_COUNT:
            break
        if not (0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE):
            continue
        if (nx, ny) in game_state.obstacles:
            continue
        occupied = False
        for z in zombies:
            zx = int((z.x + z.size * 0.5) // CELL_SIZE)
            zy = int((z.y + z.size * 0.5) // CELL_SIZE)
            if zx == nx and zy == ny:
                occupied = True
                break
        if occupied:
            continue

        child = Zombie((nx, ny), attack=child_atk, speed=child_speed, ztype="splinterling", hp=child_hp)
        child._can_split = False
        child._split_done = True
        zombies.append(child)
        spawned += 1

    return spawned


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
        self.radius = ZOMBIE_RADIUS
        # ABS
        self._stuck_t = 0.0  # 被卡住累计时长
        self._avoid_t = 0.0  # 侧移剩余时间
        self._avoid_side = 1  # 侧移方向（1 或 -1）
        self._focus_block = None  # 当前决定优先破坏的可破坏物
        self._last_xy = (self.x, self.y)
        # —— 路径跟随（懒 A*）所需的轻量状态 ——
        self._path = []  # 路径里的网格路点列表（不含起点）
        self._path_step = 0  # 当前要走向的路点索引
        # Spoil
        self.spoils = 0  # 当前持有金币
        self._gold_glow_t = 0.0  # 金色拾取光晕计时器
        self.speed = float(self.speed)  # 改成 float，支持 +0.5 的增速
        # split flags (only for splinter)
        self._can_split = (self.type == "splinter")
        self._split_done = False

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
            # stat bumps
            self.attack = int(self.attack * 1.08 + 1)
            self.max_hp = int(self.max_hp * 1.10 + 1)
            self.hp = min(self.max_hp, self.hp + 2)
            # SIZE growth (keep center & clamp)
            base = CELL_SIZE - 6
            new_size = min(ZOMBIE_SIZE_MAX, base + (self.z_level - 1) * 2)
            if new_size != self.size:
                cx, cy = self.rect.center
                self.size = new_size
                self.rect = pygame.Rect(0, 0, self.size, self.size)
                self.rect.center = (cx, cy)
                self.x = float(self.rect.x)
                self.y = float(self.rect.y - INFO_BAR_HEIGHT)

    def add_spoils(self, n: int):
        """僵尸拾取金币后的即时强化。"""
        n = int(max(0, n))
        if n <= 0:
            return
        # 逐枚处理，确保跨阈值时触发攻击/速度加成
        for _ in range(n):
            self.spoils += 1
            # +HP 与 +MaxHP
            self.max_hp += Z_SPOIL_HP_PER
            self.hp = min(self.max_hp, self.hp + Z_SPOIL_HP_PER)
            # 攻击阈值
            if self.spoils % Z_SPOIL_ATK_STEP == 0:
                self.attack += 1
            # 速度阈值
            if self.spoils % Z_SPOIL_SPD_STEP == 0:
                self.speed = min(Z_SPOIL_SPD_CAP, float(self.speed) + float(Z_SPOIL_SPD_ADD))
        # 触发拾取光晕
        self._gold_glow_t = float(Z_GLOW_TIME)

    # ==== 通用：把朝向向量分解到等距基向量（e1=(1,1), e2=(1,-1)）====
    @staticmethod
    def iso_chase_step(from_xy, to_xy, speed):
        fx, fy = from_xy
        tx, ty = to_xy
        vx, vy = (tx - fx), (ty - fy)
        if vx == 0 and vy == 0:
            return 0.0, 0.0
        # 投影到等距基 → 用符号决定“屏幕上的上下左右”
        a = (vx + vy) * 0.5  # e1分量
        b = (vx - vy) * 0.5  # e2分量
        mx = (1 if a > 0 else -1 if a < 0 else 0) + (1 if b > 0 else -1 if b < 0 else 0)
        my = (1 if a > 0 else -1 if a < 0 else 0) - (1 if b > 0 else -1 if b < 0 else 0)
        # 归一化再乘速度
        l = (mx * mx + my * my) ** 0.5
        dx, dy = (mx / l * speed, my / l * speed) if l != 0 else (0.0, 0.0)
        return dx, dy

    @staticmethod
    def feet_xy(entity):
        # “脚底”坐标：用底边中心点（避免因为sprite高度导致距离判断穿帮）
        return (entity.x + entity.size * 0.5, entity.y + entity.size)

    @staticmethod
    def first_obstacle_on_grid_line(a_cell, b_cell, obstacles_dict):
        x0, y0 = a_cell;
        x1, y1 = b_cell
        dx = abs(x1 - x0);
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0);
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            ob = obstacles_dict.get((x0, y0))
            if ob: return ob
            if x0 == x1 and y0 == y1: break
            e2 = 2 * err
            if e2 >= dy: err += dy; x0 += sx
            if e2 <= dx: err += dx; y0 += sy
        return None

    def move_and_attack(self, player, obstacles, game_state, attack_interval=0.5, dt=1 / 60):
        # ---- BUFF/生成延迟/速度上限：与原逻辑一致 ----
        base_attack = self.attack
        base_speed = float(self.speed)
        if getattr(self, "buff_t", 0.0) > 0.0:
            base_attack = int(base_attack * getattr(self, "buff_atk_mult", 1.0))
            base_speed = float(base_speed) + float(getattr(self, "buff_spd_add", 0))
            self.buff_t = max(0.0, self.buff_t - dt)
        speed = float(min(Z_SPOIL_SPD_CAP, max(0.5, base_speed)))

        if not hasattr(self, "attack_timer"): self.attack_timer = 0.0
        self.attack_timer += dt
        if self._spawn_elapsed < self.spawn_delay:
            self._spawn_elapsed += dt
            return

            # 目标（默认追玩家；若锁定了一块挡路的可破坏物，则追它的中心）
        zx, zy = Zombie.feet_xy(self)
        px, py = Zombie.feet_xy(player)
        target_cx, target_cy = px, py

        # 若之前撞到了可破坏物，则临时聚焦（更积极地砍）
        if getattr(self, "_hit_ob", None) and getattr(self._hit_ob, "type", "") == "Destructible":
            self._focus_block = self._hit_ob

        # 视线被“可破坏物”先挡住 → 把它当作“门”优先破坏
        if not self._focus_block:
            gz = (int((self.x + self.size * 0.5) // CELL_SIZE), int((self.y + self.size * 0.5) // CELL_SIZE))
            gp = (int((player.x + player.size * 0.5) // CELL_SIZE), int((player.y + player.size * 0.5) // CELL_SIZE))
            ob = self.first_obstacle_on_grid_line(gz, gp, game_state.obstacles)
            if ob and getattr(ob, "type", "") == "Destructible":
                self._focus_block = ob

        if self._focus_block:
            target_cx, target_cy = self._focus_block.rect.centerx, self._focus_block.rect.centery

        # —— 若已有“临时路径”，把目标切换到下一个路点（脚底中心） ——
        # 当前“脚底”所在格
        gx = int((self.x + self.size * 0.5) // CELL_SIZE)
        gy = int((self.y + self.size) // CELL_SIZE)

        if self._path_step < len(self._path):
            nx, ny = self._path[self._path_step]
            # 到达该格就推进
            if gx == nx and gy == ny:
                self._path_step += 1
                if self._path_step < len(self._path):
                    nx, ny = self._path[self._path_step]
            # 仍有路点：将追踪目标改成这个路点的“脚底”
            if self._path_step < len(self._path):
                target_cx = nx * CELL_SIZE + CELL_SIZE * 0.5
                target_cy = ny * CELL_SIZE + CELL_SIZE

        # —— 连续向量追踪（不再用 8 向离散步进）——
        vx = target_cx - (self.x + self.size * 0.5)
        vy = target_cy - (self.y + self.size * 0.5 + INFO_BAR_HEIGHT)
        L = (vx * vx + vy * vy) ** 0.5 or 1.0
        dx = (vx / L) * speed
        dy = (vy / L) * speed

        # —— 侧移（反卡住）：被卡住一小会儿就沿着法向 90° 滑行 ——
        if self._avoid_t > 0.0:
            # 左右各一条切线，选择预先决定的那一边
            if self._avoid_side > 0:
                ax, ay = -dy, dx  # 向左
            else:
                ax, ay = dy, -dx  # 向右
            dx, dy = ax, ay
            self._avoid_t = max(0.0, self._avoid_t - dt)

        oldx, oldy = self.x, self.y
        collide_and_slide_circle(self, obstacles, dx, dy)

        # —— 卡住检测 ——
        moved2 = (self.x - oldx) ** 2 + (self.y - oldy) ** 2
        if moved2 < 0.25:  # 本帧几乎没动
            self._stuck_t += dt
        else:
            self._stuck_t = 0.0

        # 卡住 0.25s 以上：触发一次侧移，引导绕开凸角/窄门
        if self._stuck_t > 0.25 and self._avoid_t <= 0.0:
            self._avoid_t = random.uniform(0.25, 0.45)
            self._avoid_side = random.choice((-1, 1))

        # —— 懒 A* 兜底：长时间卡住再寻一次短路径 ——
        if self._stuck_t > 0.7 and self._avoid_t <= 0.0 and self._path_step >= len(self._path):
            # 起点：当前脚底；终点：玩家或“被锁定的可破坏物”脚底网格
            start = (gx, gy)
            if self._focus_block:
                gp = getattr(self._focus_block, "grid_pos", None)
                if gp is None:
                    cx2, cy2 = self._focus_block.rect.centerx, self._focus_block.rect.centery
                    goal = (int(cx2 // CELL_SIZE), int((cy2 - INFO_BAR_HEIGHT) // CELL_SIZE))
                else:
                    goal = gp
            else:
                goal = (int(player.rect.centerx // CELL_SIZE),
                        int((player.rect.centery - INFO_BAR_HEIGHT) // CELL_SIZE))

            # 构图 + A*
            graph = build_graph(GRID_SIZE, game_state.obstacles)
            came, _ = a_star_search(graph, start, goal, game_state.obstacles)
            path = reconstruct_path(came, start, goal)

            # 生成“短路径”：去掉起点，只取前 6 个路点
            if len(path) > 1:
                self._path = path[1:7]
                self._path_step = 0

            # 避免立刻再次触发
            self._stuck_t = 0.0

        # 焦点块被打掉/消失 → 解除聚焦
        if self._focus_block and (self._focus_block.health is not None and self._focus_block.health <= 0):
            self._focus_block = None

        # 路径走完了就清空（下次卡住再算）
        if self._path_step >= len(self._path):
            self._path = []
            self._path_step = 0

        # 同步矩形
        self.rect.x = int(self.x)
        self.rect.y = int(self.y) + INFO_BAR_HEIGHT
        # 圆心是否触到可破坏障碍 → 按CD扣血
        if self.attack_timer >= attack_interval:
            cx = self.x + self.size * 0.5
            cy = self.y + self.size * 0.5 + INFO_BAR_HEIGHT
            for ob in obstacles:
                if ob.type == "Destructible" and ob.rect.inflate(self.radius * 2, self.radius * 2).collidepoint(cx, cy):
                    ob.health -= self.attack
                    self.attack_timer = 0.0
                    if ob.health <= 0:
                        gp = ob.grid_pos
                        if gp in game_state.obstacles: del game_state.obstacles[gp]
                        cx2, cy2 = ob.rect.centerx, ob.rect.centery
                        # 概率掉落
                        if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                            game_state.spawn_spoils(cx2, cy2, 1)
                        self.gain_xp(XP_ZOMBIE_BLOCK)
                        if random.random() < HEAL_DROP_CHANCE_BLOCK:
                            game_state.spawn_heal(cx2, cy2, HEAL_POTION_AMOUNT)
                    break

    def update_special(self, dt: float, player: 'Player', zombies: List['Zombie'],
                       enemy_shots: List['EnemyShot'], game_state: 'GameState' = None):

        # --- Splinter passive split when HP <= 50% (non-lethal path) ---
        if self._can_split and not self._split_done and self.hp > 0 and self.hp <= int(self.max_hp * 0.5):
            # 标记已分裂，生成子体并移除自己
            self._split_done = True
            self._can_split = False
            spawn_splinter_children(
                self, zombies, game_state,
                level_idx=getattr(game_state, "current_level", 0),
                wave_index=0
            )

            # 将自己“杀死”以便主循环移除（或者直接把 hp 置 0）
            self.hp = 0
            return

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
                        game_state.add_damage_text(player.rect.centerx, player.rect.centery, SUICIDE_DAMAGE, crit=False,
                                                   kind="hp")
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

        # 腐蚀幼体：死亡留酸；计时>15s 可被BOSS吸回
        if self.type == "corruptling":
            self._life = getattr(self, "_life", 0.0) + dt
            if self.hp <= 0 and not getattr(self, "_acid_on_death", False):
                game_state.spawn_acid_pool(self.rect.centerx, self.rect.centery, r=20, life=4.0, dps=ACID_DPS*0.8)
                self._acid_on_death = True  # 让后续移除流程照常进行
            # 吸附由 BOSS 侧发起，这里只负责寿命记录
        # 记忆吞噬者（boss_mem）
        if getattr(self, "is_boss", False) and getattr(self, "type", "") == "boss_mem":
            hp_pct = max(0.0, self.hp / max(1, self.max_hp))

            # 阶段切换
            if hp_pct > 0.70:
                self.phase = 1
            elif hp_pct > 0.40:
                self.phase = 2
            else:
                self.phase = 3

            # 基础冷却
            self._spit_cd  = max(0.0, getattr(self, "_spit_cd", 0.0)  - dt)
            self._split_cd = max(0.0, getattr(self, "_split_cd", 0.0) - dt)

            cx, cy = self.rect.centerx, self.rect.centery

            # 阶段1：腐蚀喷吐 + 小怪 2 个/20s
            if self.phase == 1:
                if self._spit_cd <= 0.0:
                    # 以玩家方向的扇形在地面“预警→落酸”
                    px, py = player.rect.centerx, player.rect.centery
                    ang = math.atan2(py - cy, px - cx)
                    points = []
                    for w in range(SPIT_WAVES_P1):
                        for i in range(SPIT_PUDDLES_PER_WAVE):
                            off_ang = ang + math.radians(random.uniform(-SPIT_CONE_DEG/2, SPIT_CONE_DEG/2))
                            dist = (SPIT_RANGE * (i+1) / SPIT_PUDDLES_PER_WAVE) * random.uniform(0.6, 1.0)
                            points.append((cx + math.cos(off_ang)*dist, cy + math.sin(off_ang)*dist))
                    game_state.spawn_telegraph(cx, cy, r=28, life=ACID_TELEGRAPH_T, kind="acid",
                        payload={"points": points, "radius": 24, "life": ACID_LIFETIME, "dps": ACID_DPS, "slow": ACID_SLOW_FRAC})
                    self._spit_cd = 5.0

                if self._split_cd <= 0.0:
                    for _ in range(2):
                        zombies.append(spawn_corruptling_at(cx + random.randint(-20,20), cy + random.randint(-20,20)))
                    self._split_cd = SPLIT_CD_P1

            # 阶段2：移动略快；喷吐“连续两次”；召唤 3 个/15s；吸附融合
            if self.phase == 2:
                self.speed = max(MEMDEV_SPEED, MEMDEV_SPEED + 0.5)
                if self._spit_cd <= 0.0:
                    for _ in range(2):  # 连续两次
                        px, py = player.rect.centerx, player.rect.centery
                        ang = math.atan2(py - cy, px - cx)
                        points = []
                        for w in range(SPIT_WAVES_P1):
                            for i in range(SPIT_PUDDLES_PER_WAVE):
                                off_ang = ang + math.radians(random.uniform(-SPIT_CONE_DEG/2, SPIT_CONE_DEG/2))
                                dist = (SPIT_RANGE * (i+1) / SPIT_PUDDLES_PER_WAVE) * random.uniform(0.6, 1.0)
                                points.append((cx + math.cos(off_ang)*dist, cy + math.sin(off_ang)*dist))
                        game_state.spawn_telegraph(cx, cy, r=32, life=ACID_TELEGRAPH_T, kind="acid",
                            payload={"points": points, "radius": 26, "life": ACID_LIFETIME, "dps": ACID_DPS, "slow": ACID_SLOW_FRAC})
                    self._spit_cd = 5.0

                if self._split_cd <= 0.0:
                    for _ in range(3):
                        zombies.append(spawn_corruptling_at(cx + random.randint(-20,20), cy + random.randint(-20,20)))
                    self._split_cd = SPLIT_CD_P2

                # 吸附融合：场上活过 15s 的腐蚀幼体被拉回并回血
                pull_any = False
                for z in list(zombies):
                    if getattr(z, "type", "") == "corruptling" and getattr(z, "_life", 0.0) >= FUSION_LIFETIME:
                        zx, zy = z.rect.centerx, z.rect.centery
                        if (zx - cx)**2 + (zy - cy)**2 <= FUSION_PULL_RADIUS**2:
                            z.hp = 0  # kill
                            self.hp = min(self.max_hp, self.hp + FUSION_HEAL)
                            pull_any = True
                if pull_any:
                    # 可选：加一个小数字飘字：+HP
                    game_state.add_damage_text(cx, cy, +FUSION_HEAL, crit=False, kind="shield")  # 蓝色表示护盾/回复

            # 阶段3：全屏酸爆(每降 10%一次) + 继续召唤；<10% 濒死冲锋
            if self.phase == 3:
                # 全屏酸爆：按阈值触发
                next_pct = getattr(self, "_rain_next_pct", 0.40)
                while hp_pct <= next_pct and next_pct >= 0.0:
                    # 随机铺点（带预警）
                    pts = []
                    for _ in range(RAIN_PUDDLES):
                        gx = random.randint(0, GRID_SIZE-1)
                        gy = random.randint(0, GRID_SIZE-1)
                        pts.append((gx*CELL_SIZE + CELL_SIZE//2, gy*CELL_SIZE + CELL_SIZE//2 + INFO_BAR_HEIGHT))
                    game_state.spawn_telegraph(cx, cy, r=36, life=RAIN_TELEGRAPH_T, kind="acid",
                        payload={"points": pts, "radius": 22, "life": ACID_LIFETIME, "dps": ACID_DPS, "slow": ACID_SLOW_FRAC})
                    next_pct -= RAIN_STEP
                    self._rain_next_pct = next_pct

                # 继续召唤（比P2略低频防爆场）
                if self._split_cd <= 0.0:
                    for _ in range(2):
                        zombies.append(spawn_corruptling_at(cx + random.randint(-20,20), cy + random.randint(-20,20)))
                    self._split_cd = 16.0

                # 濒死冲锋
                if hp_pct <= CHARGE_THRESH and not getattr(self, "_charging", False):
                    self._charging = True
                    # 直接朝玩家方向加速移动，不受可破坏物阻挡（移动层会处理破坏）
                    self.speed = CHARGE_SPEED


    def draw(self, screen):
        color = ZOMBIE_COLORS.get(getattr(self, "type", "basic"), (255, 60, 60))
        pygame.draw.rect(screen, color, self.rect)

class MemoryDevourerBoss(Zombie):
    """独立 Boss：更大体型/更大脚底圆/更高血攻；仍复用 Zombie 的大多数行为。"""
    def __init__(self, grid_pos: tuple[int,int], level_idx: int):
        gx, gy = grid_pos
        # 计算血量：沿用你原先“第5关为基准 + 关卡成长”的口径
        boss_hp = int(MEMDEV_BASE_HP * (1 + 0.15 * max(0, level_idx - 1)))

        # 用父类构造出一个 type='boss_mem' 的单位，再整体重写体型与半径
        super().__init__((gx, gy),
                         attack=int(MEMDEV_CONTACT_DAMAGE),
                         speed=int(max(1, MEMDEV_SPEED)),
                         ztype="boss_mem",
                         hp=boss_hp)
        # 例：按比例放大到 1.8~2.2 倍 CELL_SIZE（按你项目常量来）
        boss_size = int(CELL_SIZE * BOSS_SIZE_FACTOR)  # 或你自己的命名
        cx, cy = self.rect.center

        self.size = boss_size
        self.rect.width = self.rect.height = self.size
        self.rect.center = (cx, cy)

        # 半径用同一套规则（保持与碰撞逻辑一致）
        self.radius = int(self.size * 0.45)  # 或用你已有的常量/函数

        self.is_boss = True
        self.boss_name = "Memory Devourer"
        # —— 可视尺寸 & 脚底圆半径（2×2 占格）——
        # 可视矩形 ≈ 2*CELL_SIZE，略收边
        self.size = int(BOSS_FOOTPRINT_TILES * CELL_SIZE - BOSS_VISUAL_MARGIN)

        # 圆碰撞半径：让直径≈2*CELL_SIZE（正好“堵死”单格通道）
        self.radius = int(BOSS_FOOTPRINT_TILES * CELL_SIZE * 0.5 * BOSS_RADIUS_SHRINK)

        # 以 2×2 的几何中心为锚点摆放（grid_pos 视为这块 2×2 的“左上角格”）
        cx = int((gx + 0.5 * BOSS_FOOTPRINT_TILES) * CELL_SIZE)
        cy = int((gy + 0.5 * BOSS_FOOTPRINT_TILES) * CELL_SIZE) + INFO_BAR_HEIGHT

        self.rect = pygame.Rect(0, 0, self.size, self.size)
        self.rect.center = (cx, cy)
        self.x = float(self.rect.x)
        self.y = float(self.rect.y - INFO_BAR_HEIGHT)

        # 出生延迟维持一致
        self.spawn_delay = 0.6

    def bind_twin(self, other, twin_id):
            import weakref
            self.twin_id = twin_id
            self._twin_partner_ref = weakref.ref(other)
            other.twin_id = twin_id
            other._twin_partner_ref = weakref.ref(self)

    def on_twin_partner_death(self):
            # 已触发过就不再触发
            if self._twin_powered or self.hp <= 0:
                return
            # 回满血并狂暴
            self.hp = int(getattr(self, "max_hp", self.hp))
            self.attack = int(self.attack * TWIN_ENRAGE_ATK_MULT)
            self.speed = int(self.speed + TWIN_ENRAGE_SPD_ADD)
            self._twin_powered = True
            # 可选：改名/标记，方便UI显示
            self.boss_name = (getattr(self, "boss_name", "BOSS") + " [ENRAGED]")

    # （可选）你也可以覆盖 draw，画个大圆/贴图；目前沿用矩形色块就行

class Bullet:
    def __init__(self, x: float, y: float, vx: float, vy: float, max_dist: float = MAX_FIRE_RANGE,
                 damage: int = BULLET_DAMAGE_ZOMBIE):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.alive = True
        self.traveled = 0.0
        self.max_dist = max_dist
        self.damage = int(damage)

    def update(self, dt: float, game_state: 'GameState', zombies: List['Zombie'], player: 'Player' = None):
        if not self.alive:
            return
        nx = self.x + self.vx * dt
        ny = self.y + self.vy * dt
        self.traveled += ((nx - self.x) ** 2 + (ny - self.y) ** 2) ** 0.5
        self.x, self.y = nx, ny
        if self.traveled >= self.max_dist:
            self.alive = False
            return

        r = pygame.Rect(int(self.x - BULLET_RADIUS), int(self.y - BULLET_RADIUS), BULLET_RADIUS * 2, BULLET_RADIUS * 2)

        # 1) zombies
        for z in list(zombies):
            if r.colliderect(z.rect):
                # --- crit roll (use player's stats if available) ---
                crit_p = float(getattr(player, "crit_chance", CRIT_CHANCE_BASE))
                crit_m = float(getattr(player, "crit_mult", CRIT_MULT_BASE))
                is_crit = (random.random() < max(0.0, min(0.99, crit_p)))
                base = int(self.damage)
                dealt = int(round(base * (crit_m if is_crit else 1.0)))

                cx, cy = z.rect.centerx, z.rect.centery

                # --- apply to shield first, overflow to HP ---
                if getattr(z, "shield_hp", 0) > 0:
                    blocked = min(dealt, z.shield_hp)
                    z.shield_hp -= dealt
                    # 飘字：护盾伤害（蓝色）
                    game_state.add_damage_text(cx, cy, blocked, crit=is_crit, kind="shield")
                    overflow = dealt - blocked
                    if z.shield_hp < 0:
                        # 已在一行里把溢出算进去了，这里不再额外处理
                        pass
                    if overflow > 0:
                        z.hp -= overflow
                        # 飘字：HP 伤害（红/金）
                        game_state.add_damage_text(cx, cy - 10, overflow, crit=is_crit, kind="hp")
                else:
                    z.hp -= dealt
                    game_state.add_damage_text(cx, cy, dealt, crit=is_crit, kind="hp")

                if z.hp <= 0:
                    cx, cy = z.rect.centerx, z.rect.centery
                    if getattr(z, "is_boss", False) and getattr(z, "twin_id", None) is not None:
                        trigger_twin_enrage(z, zombies, game_state)
                    # --- Splinter: if not yet split, split on death instead of dropping loot now ---
                    if getattr(z, "_can_split", False) and not getattr(z, "_split_done", False) and getattr(z, "type",
                                                                                                            "") == "splinter":
                        z._split_done = True
                        z._can_split = False
                        # 生成子体；父体不掉落金币（避免三倍通胀），XP也交给后续击杀子体获得
                        spawn_splinter_children(z, zombies, game_state, level_idx=0, wave_index=0)
                        # Twin：若死者是Boss且有存活的孪生体，让对方回满并狂暴
                        if getattr(z, "is_boss", False):
                            partner = None
                            ref = getattr(z, "_twin_partner_ref", None)
                            if callable(ref):  # weakref
                                partner = ref()
                            elif ref is not None:
                                partner = ref
                            # 如果没存ref，尝试在zombies里按twin_id搜
                            if partner is None and getattr(z, "twin_id", None) is not None:
                                for _cand in zombies:
                                    if getattr(_cand, "is_boss", False) and getattr(_cand, "twin_id",
                                                                                    None) == z.twin_id and _cand is not z:
                                        partner = _cand
                                        break

                            if partner and getattr(partner, "hp", 0) > 0 and not getattr(partner, "_twin_powered",
                                                                                         False):
                                if hasattr(partner, "on_twin_partner_death"):
                                    partner.on_twin_partner_death()
                                else:
                                    # 兜底：没有方法也强行赋值
                                    partner.hp = int(getattr(partner, "max_hp", partner.hp))
                                    partner.attack = int(partner.attack * TWIN_ENRAGE_ATK_MULT)
                                    partner.speed = int(partner.speed + TWIN_ENRAGE_SPD_ADD)
                                    partner._twin_powered = True
                        # 从场上移除父体
                        zombies.remove(z)
                        self.alive = False
                        return

                    # --- normal death (non-splinter or already split) ---
                    drop_n = roll_spoils_for_zombie(z)
                    drop_n += int(getattr(z, "spoils", 0))
                    if drop_n > 0:
                        game_state.spawn_spoils(cx, cy, drop_n)
                    if random.random() < HEAL_DROP_CHANCE_ZOMBIE:
                        game_state.spawn_heal(cx, cy, HEAL_POTION_AMOUNT)
                    if player:
                        base_xp = XP_PER_ZOMBIE_TYPE.get(getattr(z, "type", "basic"), XP_PLAYER_KILL)
                        bonus = max(0, z.z_level - 1) * XP_ZLEVEL_BONUS
                        extra_by_spoils = int(getattr(z, "spoils", 0)) * int(Z_SPOIL_XP_BONUS_PER)
                        if getattr(z, "is_elite", False):  base_xp = int(base_xp * 1.5)
                        if getattr(z, "is_boss", False):   base_xp = int(base_xp * 3.0)
                        player.add_xp(base_xp + bonus + extra_by_spoils)
                        if getattr(z, "is_boss", False):
                            trigger_twin_enrage(z, zombies, game_state)

                    transfer_xp_to_neighbors(z, zombies)
                    zombies.remove(z)
                    self.alive = False
                    return

        # 2) obstacles
        for gp, ob in list(game_state.obstacles.items()):
            if r.colliderect(ob.rect):
                if ob.type == "Indestructible":
                    self.alive = False
                    return
                elif ob.type == "Destructible":
                    ob.health = (ob.health or 0) - BULLET_DAMAGE_BLOCK
                    if ob.health <= 0:
                        cx, cy = ob.rect.centerx, ob.rect.centery
                        del game_state.obstacles[gp]
                        # drop spoils for block destruction
                        if random.random() < SPOILS_BLOCK_DROP_CHANCE:
                            game_state.spawn_spoils(cx, cy, 1)
                        if player: player.add_xp(XP_PLAYER_BLOCK)
                    self.alive = False
                    return

    def draw(self, screen, cam_x, cam_y):
        pygame.draw.circle(screen, (255, 255, 255), (int(self.x - cam_x), int(self.y - cam_y)), BULLET_RADIUS)


class Spoil:
    """A coin-like pickup that pops up and bounces in place."""

    def __init__(self, x_px: float, y_px: float, value: int = 1):
        # ground/world position where the coin lives
        self.base_x = float(x_px)
        self.base_y = float(y_px)
        # vertical offset (screen-space "height")
        self.h = 0.0
        self.vh = float(COIN_POP_VY)  # vertical speed for bounce
        self.value = int(value)
        self.r = 6
        self.rect = pygame.Rect(0, 0, self.r * 2, self.r * 2)
        self._update_rect()

    def _update_rect(self):
        # draw/world position is base minus height
        cx = int(self.base_x)
        cy = int(self.base_y - self.h)
        self.rect.center = (cx, cy)

    def update(self, dt: float):
        # simple vertical bounce around base_y
        self.vh += COIN_GRAVITY * dt
        self.h += self.vh * dt
        if self.h >= 0.0:
            # hit "ground" -> bounce
            self.h = 0.0
            if abs(self.vh) > COIN_MIN_BOUNCE:
                self.vh = -self.vh * COIN_RESTITUTION
            else:
                self.vh = 0.0
        self._update_rect()


class HealPickup:
    """A small health potion pickup with the same bounce feel as coins."""

    def __init__(self, x_px: float, y_px: float, heal: int = HEAL_POTION_AMOUNT):
        self.base_x = float(x_px)
        self.base_y = float(y_px)
        self.h = 0.0
        self.vh = float(COIN_POP_VY)  # reuse coin bounce values
        self.heal = int(heal)
        self.r = 7
        self.rect = pygame.Rect(0, 0, self.r * 2, self.r * 2)
        self._update_rect()

    def _update_rect(self):
        self.rect.center = (int(self.base_x), int(self.base_y - self.h))

    def update(self, dt: float):
        self.vh += COIN_GRAVITY * dt
        self.h += self.vh * dt
        if self.h >= 0.0:
            self.h = 0.0
            if abs(self.vh) > COIN_MIN_BOUNCE:
                self.vh = -self.vh * COIN_RESTITUTION
            else:
                self.vh = 0.0
        self._update_rect()


class AcidPool:
    def __init__(self, x, y, r, dps, slow_frac, life):
        self.x, self.y, self.r = x, y, r
        self.dps, self.slow_frac = dps, slow_frac
        self.t = life  # remaining time

    def contains(self, px, py):
        return (px - self.x) ** 2 + (py - self.y) ** 2 <= self.r ** 2


class TelegraphCircle:
    def __init__(self, x, y, r, life, kind="acid", payload=None, color=(255, 60, 60)):
        self.x, self.y, self.r = x, y, r
        self.t = life
        self.kind = kind
        self.payload = payload or {}
        self.color = color


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
            # 显示玩家受伤数字（红色，大号），敌人攻击不参与暴击
            game_state.add_damage_text(player.rect.centerx, player.rect.centery, self.dmg, crit=False, kind="hp")
            self.alive = False

    def draw(self, screen, cam_x, cam_y):
        pygame.draw.circle(screen, (255, 120, 50), (int(self.x - cam_x), int(self.y - cam_y)), BULLET_RADIUS)


class DamageText:
    """世界坐标下的飘字（x,y 为像素，含 INFO_BAR_HEIGHT），按时间上浮并淡出。"""

    def __init__(self, x_px: float, y_px: float, amount: int,
                 crit: bool = False, kind: str = "hp"):
        self.x = float(x_px)
        self.y = float(y_px)
        if isinstance(amount, (int, float)):
            self.amount = int(amount)
        else:
            self.amount = str(amount)
        self.crit = bool(crit)
        self.kind = kind  # "hp"|"shield"
        self.t = 0.0
        self.ttl = float(DMG_TEXT_TTL)

    def alive(self) -> bool:
        return self.t < self.ttl

    def step(self, dt: float):
        self.t += dt

    def screen_offset_y(self) -> float:
        # 线性上升
        return -DMG_TEXT_RISE * (self.t / self.ttl)

    def alpha(self) -> int:
        # 后段逐渐淡出
        p = self.t / self.ttl
        if p <= (1.0 - DMG_TEXT_FADE):
            return 255
        tail = (p - (1.0 - DMG_TEXT_FADE)) / max(1e-4, DMG_TEXT_FADE)
        return max(0, int(255 * (1.0 - tail)))


# ==================== 算法函数 ====================

def sign(v): return 1 if v > 0 else (-1 if v < 0 else 0)


def heuristic(a, b): return abs(a[0] - b[0]) + abs(a[1] - b[1])


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


def play_bounds_for_circle(radius: float) -> tuple[float, float, float, float]:
    """返回【圆心】在当前关卡内允许的最小/最大坐标 (x_min, y_min, x_max, y_max)。"""
    w = GRID_SIZE * CELL_SIZE  # 地图像素宽
    h = GRID_SIZE * CELL_SIZE  # 地图像素高（不包含顶部信息栏）
    x_min = radius
    x_max = w - radius
    y_min = INFO_BAR_HEIGHT + radius
    y_max = INFO_BAR_HEIGHT + h - radius
    return x_min, y_min, x_max, y_max


def iso_world_to_screen(wx: float, wy: float, wz: float = 0.0,
                        camx: float = 0.0, camy: float = 0.0) -> tuple[int, int]:
    """
    把【世界格坐标】(wx, wy, wz) 投到屏幕像素坐标。
    - wx, wy 以“格”为单位（像素请先 / CELL_SIZE 再传）
    - wz 额外竖向抬高（像素，向上为正），例如墙体高度/跳跃
    - camx, camy 是等距相机的屏幕偏移（像素）
    注意：UI 绝对不传 cam 偏移；UI 始终使用屏幕绝对坐标。
    """
    half_w = ISO_CELL_W * 0.5
    half_h = ISO_CELL_H * 0.5
    sx = (wx - wy) * half_w - camx
    sy = (wx + wy) * half_h - wz - camy + INFO_BAR_HEIGHT
    return int(sx), int(sy)


def iso_tile_points(gx: int, gy: int, camx: float, camy: float) -> list[tuple[int, int]]:
    """返回等距地砖菱形四个顶点（上、右、下、左）。"""
    cx, cy = iso_world_to_screen(gx, gy, 0, camx, camy)
    return [
        (cx, cy),
        (cx + ISO_CELL_W // 2, cy + ISO_CELL_H // 2),
        (cx, cy + ISO_CELL_H),
        (cx - ISO_CELL_W // 2, cy + ISO_CELL_H // 2),
    ]


def draw_iso_tile(surface, gx, gy, color, camx, camy, border=0):
    pts = iso_tile_points(gx, gy, camx, camy)
    pygame.draw.polygon(surface, color, pts, border)


def draw_iso_prism(surface, gx, gy, top_color, camx, camy, wall_h=ISO_WALL_Z):
    """
    画“墙砖”：带顶面和两个侧面（简单着色），用来替代 Destructible/Indestructible 方块。
    """
    top = iso_tile_points(gx, gy, camx, camy)
    # 侧面（右侧、左侧）
    r = [top[1], (top[1][0], top[1][1] + wall_h),
         (top[2][0], top[2][1] + wall_h), top[2]]
    l = [top[3], top[2], (top[2][0], top[2][1] + wall_h), (top[3][0], top[3][1] + wall_h)]
    # 颜色：顶面亮，右侧中，左侧暗
    c_top = top_color
    c_r = tuple(max(0, int(c * 0.78)) for c in top_color)
    c_l = tuple(max(0, int(c * 0.58)) for c in top_color)
    pygame.draw.polygon(surface, c_l, l)
    pygame.draw.polygon(surface, c_r, r)
    pygame.draw.polygon(surface, c_top, top)

# === ISO ground ellipse helpers ===

def iso_circle_radii_screen(r_px: float) -> tuple[int, int]:
    """
    把“世界平面半径 r_px（像素）”转换成屏幕上的椭圆半径 (rx, ry)（像素）。
    推导：沿屏幕水平轴的世界方向为 (dx,dy)=(t,-t)，垂直轴为 (t,t)，
    由 iso_world_to_screen 的线性部分可得：
      rx = r * ISO_CELL_W / (sqrt(2) * CELL_SIZE)
      ry = r * ISO_CELL_H / (sqrt(2) * CELL_SIZE)
    """
    rx = int(r_px * (ISO_CELL_W / (math.sqrt(2) * CELL_SIZE)))
    ry = int(r_px * (ISO_CELL_H / (math.sqrt(2) * CELL_SIZE)))
    return max(1, rx), max(1, ry)

def draw_iso_ground_ellipse(surface: pygame.Surface, x_px: float, y_px: float,
                            r_px: float, color: tuple, alpha: int,
                            camx: float, camy: float,
                            *, fill: bool = True, width: int = 2) -> None:
    """
    在地面(等距)绘制一个椭圆：中心传入世界像素坐标 (x_px, y_px)，半径 r_px（世界像素）。
    color=(R,G,B)，alpha=0..255。
    """
    # 世界“格”单位（iso_world_to_screen 需要传格坐标）
    wx = x_px / CELL_SIZE
    wy = (y_px - INFO_BAR_HEIGHT) / CELL_SIZE
    cx, cy = iso_world_to_screen(wx, wy, 0, camx, camy)

    rx, ry = iso_circle_radii_screen(float(r_px))

    # 用一张带透明通道的小画布来画椭圆，再贴到主画面
    surf = pygame.Surface((rx * 2 + 2, ry * 2 + 2), pygame.SRCALPHA)
    rgba = (int(color[0]), int(color[1]), int(color[2]), int(alpha))
    rect = pygame.Rect(1, 1, rx * 2, ry * 2)
    if fill:
        pygame.draw.ellipse(surf, rgba, rect)
    else:
        pygame.draw.ellipse(surf, rgba, rect, max(1, int(width)))

    surface.blit(surf, (cx - rx - 1, cy - ry - 1))

def roll_spoils_for_zombie(z: "Zombie") -> int:
    """Return number of coins to drop for a killed zombie, applying drop chance."""
    if random.random() > SPOILS_DROP_CHANCE:
        return 0
    t = getattr(z, "type", "basic")
    lo, hi = SPOILS_PER_TYPE.get(t, (1, 1))
    return random.randint(int(lo), int(hi))


def player_xp_required(level: int) -> int:
    """
    XP required to go from `level` -> `level+1`.
    Early levels are quick; later levels ramp reasonably (like mature ARPG/roguelites).
    """
    L = max(1, int(level))
    base = PLAYER_XP_TO_LEVEL
    exp_part = base * (XP_CURVE_EXP_GROWTH ** (L - 1))
    linear_part = XP_CURVE_LINEAR * L
    softcap_part = 0.0
    if L >= XP_CURVE_SOFTCAP_START:
        softcap_part = (L - XP_CURVE_SOFTCAP_START) ** XP_CURVE_SOFTCAP_POWER
    return int(exp_part + linear_part + softcap_part + 0.5)


def _diminish_growth(level: int, per_level: float) -> float:
    """Apply softcap to per-level growth after MON_SOFTCAP_LEVEL."""
    if level <= MON_SOFTCAP_LEVEL:
        return per_level * level
    base = per_level * MON_SOFTCAP_LEVEL
    extra = (level - MON_SOFTCAP_LEVEL) * per_level * MON_SOFTCAP_FACTOR
    return base + extra


# ---- Per-run carry-over of player's growth between levels ----
# ---- Per-run carry-over of player's growth between levels ----
def capture_player_carry(player) -> dict:
    """Carry only progression: level and leftover XP. HP is NOT carried across levels."""
    return {
        "level": int(getattr(player, "level", 1)),
        "xp": int(getattr(player, "xp", 0)),  # leftover XP toward next level
    }


def apply_player_carry(player, carry: dict | None):
    """Rebuild level-based growth, then start the level at FULL HP."""
    if not carry:
        # Still start full HP each level, even with no carry
        player.hp = player.max_hp
        return

    target_level = max(1, int(carry.get("level", 1)))
    leftover_xp = max(0, int(carry.get("xp", 0)))

    # reset to level 1 baseline, then feed XP for target_level + leftover
    player.level = 1
    player.xp = 0
    player.xp_to_next = player_xp_required(1)

    total_xp = 0
    for L in range(1, target_level):
        total_xp += player_xp_required(L)
    total_xp += leftover_xp
    if total_xp > 0:
        player.add_xp(total_xp)

    # ALWAYS start a new level at full HP
    player.hp = player.max_hp


def monster_scalars_for(game_level: int, wave_index: int) -> Dict[str, int | float]:
    """
    Return additive/multipliers for zombie stats based on the current game level & wave.
    We return {'hp_mult', 'atk_mult', 'spd_add', 'elite?', 'boss?'}.
    """
    L = max(0, int(game_level))
    W = max(0, int(wave_index))

    # 原处在 monster_scalars_for 内
    if MON_SCALE_MODE == "exp":
        # 关卡指数成长 + 软帽后降低“有效年化”
        pre = min(L, MON_SOFTCAP_LEVEL)
        post = max(0, L - MON_SOFTCAP_LEVEL)

        # 例：每关 8%（HP）/ 9%（ATK），软帽后仅按 40% 的强度继续复利
        hp_mult_lvl = (1.0 + MON_HP_GROWTH_PER_LEVEL) ** pre \
                      * (1.0 + MON_HP_GROWTH_PER_LEVEL * MON_SOFTCAP_FACTOR) ** post
        atk_mult_lvl = (1.0 + MON_ATK_GROWTH_PER_LEVEL) ** pre \
                       * (1.0 + MON_ATK_GROWTH_PER_LEVEL * MON_SOFTCAP_FACTOR) ** post

        # 波次也改为复利（更平滑），不想动可保留原来的线性乘子
        hp_mult_wave = (1.0 + MON_HP_GROWTH_PER_WAVE) ** W
        atk_mult_wave = (1.0 + MON_ATK_GROWTH_PER_WAVE) ** W

        hp_mult = hp_mult_lvl * hp_mult_wave
        atk_mult = atk_mult_lvl * atk_mult_wave
    else:
        # ← 保留你现在的线性+软帽逻辑
        hp_mult = (1.0 + _diminish_growth(L, MON_HP_GROWTH_PER_LEVEL)) * (1.0 + W * MON_HP_GROWTH_PER_WAVE)
        atk_mult = (1.0 + _diminish_growth(L, MON_ATK_GROWTH_PER_LEVEL)) * (1.0 + W * MON_ATK_GROWTH_PER_WAVE)

    # additive speed bumps
    spd_add = (L // MON_SPD_ADD_EVERY_LEVELS) + (W // MON_SPD_ADD_EVERY_WAVES)

    # elites (chance increases with game level)
    elite_p = min(ELITE_MAX_CHANCE, ELITE_BASE_CHANCE + L * ELITE_CHANCE_PER_LEVEL)
    is_elite = (random.random() < elite_p)

    # boss only on boss levels (your global const already exists)
    is_boss = is_boss_level(game_level) and (wave_index == 0)  # first wave of boss level

    # apply elite/boss extras to the multipliers
    if is_elite:
        hp_mult *= ELITE_HP_MULT_EXTRA
        atk_mult *= ELITE_ATK_MULT_EXTRA
        spd_add += ELITE_SPD_ADD_EXTRA
    if is_boss:
        hp_mult *= BOSS_HP_MULT_EXTRA
        atk_mult *= BOSS_ATK_MULT_EXTRA
        spd_add += BOSS_SPD_ADD_EXTRA

    return {"hp_mult": hp_mult, "atk_mult": atk_mult, "spd_add": spd_add, "elite": is_elite, "boss": is_boss}


def roll_affix(game_level: int) -> Optional[str]:
    """Roll a lightweight affix occasionally; return name or None."""
    p = min(AFFIX_CHANCE_MAX, AFFIX_CHANCE_BASE + game_level * AFFIX_CHANCE_PER_LEVEL)
    if random.random() >= p:
        return None
    # three simple mature affixes
    return random.choice(["frenzied", "armored", "veteran"])


def apply_affix(z: "Zombie", affix: Optional[str]):
    """Mutate a zombie with the chosen affix. Small, readable bonuses."""
    if not affix:
        return
    if affix == "frenzied":
        z.attack = int(z.attack * 1.15)
        z.speed = int(z.speed + 1)
        z._affix_tag = "F"  # tag for draw
    elif affix == "armored":
        z.max_hp = int(z.max_hp * 1.35)
        z.hp = int(z.hp * 1.35)
        z.speed = max(1, z.speed - 1)
        z._affix_tag = "A"
    elif affix == "veteran":
        z.z_level += 1
        z.attack = int(z.attack * 1.08 + 1)
        z.max_hp = int(z.max_hp * 1.10 + 1)
        z.hp = min(z.max_hp, z.hp + 2)
        z._affix_tag = "V"


def create_memory_devourer(grid_xy: Tuple[int, int], level_idx: int) -> "MemoryDevourerBoss":
    return MemoryDevourerBoss(grid_xy, level_idx)



def spawn_corruptling_at(x_px: float, y_px: float) -> "Zombie":
    """
    从屏幕像素坐标生成腐蚀幼体（近战小怪）。
    注意 y_px 包含了 INFO_BAR_HEIGHT，需要在换算格子时减掉。
    """
    # 像素 -> 格子；y 要扣掉信息栏偏移
    gx = int(max(0, min(GRID_SIZE - 1, x_px // CELL_SIZE)))
    gy = int(max(0, min(GRID_SIZE - 1, (y_px - INFO_BAR_HEIGHT) // CELL_SIZE)))

    z = Zombie((gx, gy),
               attack=int(CHILD_ATK),
               speed=int(max(1, CHILD_SPEED)),
               ztype="corruptling",
               hp=int(CHILD_HP))

    # 幼体更快进入战斗
    z.spawn_delay = 0.25
    return z



def make_scaled_zombie(pos: Tuple[int, int], ztype: str, game_level: int, wave_index: int) -> "Zombie":
    """Factory: spawn a zombie already scaled, with elite/boss & affixes applied."""
    z = Zombie(pos, speed=ZOMBIE_SPEED, ztype=ztype)
    s = monster_scalars_for(game_level, wave_index)
    # bake stats
    z.attack = max(1, int(z.attack * s["atk_mult"]))
    z.max_hp = max(1, int(z.max_hp * s["hp_mult"]))
    z.hp = z.max_hp
    z.speed = int(z.speed + s["spd_add"])
    z.is_elite = bool(s["elite"])
    z.is_boss = bool(s["boss"])

    # small affix roll
    aff = roll_affix(game_level)
    apply_affix(z, aff)
    z._affix_name = aff

    # ← cap final move speed
    z.speed = min(ZOMBIE_SPEED_MAX, max(1, z.speed))
    return z


def transfer_xp_to_neighbors(dead_z: "Zombie", zombies: List["Zombie"],
                             ratio: float = XP_TRANSFER_RATIO,
                             radius: int = XP_INHERIT_RADIUS):
    """On death, share a portion of dead_z's XP to nearby survivors."""
    if not zombies or ratio <= 0:
        return
    cx, cy = dead_z.rect.centerx, dead_z.rect.centery
    r2 = radius * radius
    near = [zz for zz in zombies
            if zz is not dead_z and (zz.rect.centerx - cx) ** 2 + (zz.rect.centery - cy) ** 2 <= r2]
    if not near:
        return
    portion = int(max(0, dead_z.xp) * ratio)
    if portion <= 0:
        return
    share = max(1, portion // len(near))
    for t in near:
        t.gain_xp(share)

def _find_twin_partner(z, zombies):
    partner = None
    ref = getattr(z, "_twin_partner_ref", None)
    if callable(ref):
        partner = ref()
    elif ref is not None:
        partner = ref
    if partner is None and getattr(z, "twin_id", None) is not None:
        for cand in zombies:
            if getattr(cand, "is_boss", False) and getattr(cand, "twin_id", None) == z.twin_id and cand is not z:
                partner = cand
                break
    return partner

def trigger_twin_enrage(dead_boss, zombies, game_state):
    """If a bonded twin dies, power up the partner exactly once."""
    # locate partner
    partner = None
    ref = getattr(dead_boss, "_twin_partner_ref", None)
    if callable(ref):
        partner = ref()
    elif ref is not None:
        partner = ref
    if partner is None:  # fall back: search by twin_id
        tid = getattr(dead_boss, "twin_id", None)
        if tid is not None:
            for z in zombies:
                if getattr(z, "is_boss", False) and getattr(z, "twin_id", None) == tid and z is not dead_boss:
                    partner = z
                    break
    if not partner or getattr(partner, "hp", 0) <= 0:
        return

    # already enraged? do nothing
    if getattr(partner, "_twin_powered", False):
        return

    # heal to full and buff
    partner.hp = int(getattr(partner, "max_hp", partner.hp))
    partner.attack = int(partner.attack * TWIN_ENRAGE_ATK_MULT)
    partner.speed  = int(partner.speed  + TWIN_ENRAGE_SPD_ADD)
    partner._twin_powered = True
    # optional: mark name so the UI can show it's angry
    try:
        partner.boss_name = (getattr(partner, "boss_name", "BOSS") + " [ENRAGED]")
    except Exception:
        pass

    # floating label (now safe—accepts strings)
    game_state.add_damage_text(partner.rect.centerx,
                               partner.rect.top - 10,
                               "ENRAGE!",  # string OK after step #1/#2
                               crit=True, kind="hp")


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
    items = [Item(x, y, is_main=False) for (x, y) in
             random.sample(item_candidates, min(len(item_candidates), item_target))]

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
class SpatialHash:
    def __init__(self, cell=64):
        self.cell = int(cell)
        self.buckets = {}

    def _key(self, x, y):
        return (int(x) // self.cell, int(y) // self.cell)

    def rebuild(self, zombies):
        self.buckets.clear()
        for z in zombies:
            k = self._key(z.rect.centerx, z.rect.centery)
            self.buckets.setdefault(k, []).append(z)

    def query_circle(self, x, y, r):
        cx, cy = self._key(x, y)
        out = []
        rr = r + max(16, CELL_SIZE // 2)
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for z in self.buckets.get((gx, gy), []):
                    dx = z.rect.centerx - x
                    dy = z.rect.centery - y
                    if dx * dx + dy * dy <= rr * rr:
                        out.append(z)
        return out

def crush_blocks_in_rect(sweep_rect: pygame.Rect, game_state) -> int:
    """Remove ANY obstacle cell whose rect intersects sweep_rect. Return removed count."""
    removed = 0
    if not hasattr(game_state, "obstacles") or not game_state.obstacles:
        return 0
    # 遍历拷贝，安全删除
    for gp, ob in list(game_state.obstacles.items()):
        if sweep_rect.colliderect(ob.rect):
            # 无视类型，直接移除（包含 Indestructible / MainBlock）
            # 如需震屏/音效/粒子，在这里加
            del game_state.obstacles[gp]
            removed += 1
    return removed


class GameState:
    def __init__(self, obstacles: Dict, items: Set, main_item_pos: List[Tuple[int, int]], decorations: list):
        self.obstacles = obstacles
        self.items = items
        self.destructible_count = self.count_destructible_obstacles()
        self.main_item_pos = main_item_pos
        self.items_total = len(items)  # track total at start
        # non-colliding visual fillers
        self.decorations = decorations  # list[Tuple[int,int]] grid coords
        self.spoils = []  # List[Spoil]
        self.spoils_gained = 0
        self.heals = []  # List[HealPickup]
        self.dmg_texts = []  # List[DamageText]
        self.acids = []  # List[AcidPool]
        self.telegraphs = []  # List[TelegraphCircle]

    def count_destructible_obstacles(self) -> int:
        return sum(1 for obs in self.obstacles.values() if obs.type == "Destructible")

    def spawn_spoils(self, x_px: float, y_px: float, count: int = 1):
        for _ in range(int(max(0, count))):
            # tiny jitter so multiple coins don't overlap perfectly
            jx = random.uniform(-6, 6)
            jy = random.uniform(-6, 6)
            self.spoils.append(Spoil(x_px + jx, y_px + jy, 1))

    def update_spoils(self, dt: float):
        for s in self.spoils:
            s.update(dt)

    def collect_item(self, player_rect: pygame.Rect) -> bool:
        """Collect one item if the player overlaps it. Returns True if collected."""
        for it in list(self.items):
            if player_rect.colliderect(it.rect):
                self.items.remove(it)
                return True
        return False

    def collect_spoils(self, player_rect: pygame.Rect) -> int:
        gained = 0
        for s in list(self.spoils):
            if player_rect.colliderect(s.rect):
                self.spoils.remove(s)
                self.spoils_gained += s.value
                gained += s.value
        return gained

    def collect_spoils_for_zombie(self, zombie: "Zombie") -> int:
        """让某个僵尸收集与其相交的金币，返回本次收集数量。"""
        gained = 0
        zr = zombie.rect
        for s in list(self.spoils):
            if zr.colliderect(s.rect):
                self.spoils.remove(s)
                gained += s.value
        return gained

    def spawn_heal(self, x_px: float, y_px: float, amount: int = HEAL_POTION_AMOUNT):
        jx = random.uniform(-6, 6);
        jy = random.uniform(-6, 6)
        self.heals.append(HealPickup(x_px + jx, y_px + jy, amount))

    def update_heals(self, dt: float):
        for h in self.heals:
            h.update(dt)

    def collect_heals(self, player: "Player") -> int:
        healed = 0
        for h in list(self.heals):
            if player.rect.colliderect(h.rect):
                self.heals.remove(h)
                before = player.hp
                player.hp = min(player.max_hp, player.hp + h.heal)
                healed += (player.hp - before)
        return healed

    # ---- 地面腐蚀池 ----
    def spawn_acid_pool(self, x, y, r=24, dps=ACID_DPS, slow_frac=ACID_SLOW_FRAC, life=ACID_LIFETIME):
        self.acids.append(AcidPool(float(x), float(y), float(r), float(dps), float(slow_frac), float(life)))

    def update_acids(self, dt: float, player: "Player"):
        # 衰减 slow / DoT 计时
        player.slow_t = max(0.0, getattr(player, "slow_t", 0.0) - dt)
        player.acid_dot_timer = max(0.0, getattr(player, "acid_dot_timer", 0.0) - dt)

        # 维护一个按秒结算的累计器（避免帧率依赖）
        if not hasattr(player, "_acid_dmg_accum"):
            player._acid_dmg_accum = 0.0

        # 只取当前踩到的酸池里“最强”的那个，而不是累加（防止重叠酸池爆表）
        px, py = player.rect.centerx, player.rect.centery
        max_dps = 0.0
        max_slow = 0.0
        touching = False

        # 更新酸池寿命，同时检查是否踩中
        alive = []
        for a in self.acids:
            a.t -= dt
            if a.t > 0:
                alive.append(a)
                if a.contains(px, py):
                    touching = True
                    if a.dps > max_dps: max_dps = a.dps
                    if a.slow_frac > max_slow: max_slow = a.slow_frac
        self.acids = alive

        if touching:
            # 站在池里：按秒累加 dps（仅取最强那一摊）
            player._acid_dmg_accum += max_dps * dt
            ticks = int(player._acid_dmg_accum)  # 每满1点血扣一次
            if ticks > 0:
                player.hp -= ticks
                player._acid_dmg_accum -= ticks
                self.add_damage_text(px, player.rect.top - 10, ticks, crit=False, kind="hp")

            # 施加减速（刷新时长，让它留存一点点）
            player.slow_t = max(player.slow_t, 0.40)  # 可调：0.3~0.5
            # 刷新离开后的持续 DoT（占总 dps 的一部分）
            player.acid_dot_timer = ACID_DOT_DURATION
            player.acid_dot_dps = max_dps * ACID_DOT_MULT
        # 不在池里：不做直接伤害；离开后的 DoT 由主循环统一结算

    # ---- 攻击前的提示圈（到时后生成酸池等）----
    def spawn_telegraph(self, x, y, r, life, kind="acid", payload=None, color=(255, 60, 60)):
        self.telegraphs.append(TelegraphCircle(float(x), float(y), float(r), float(life), kind, payload, color))

    def update_telegraphs(self, dt: float):
        for t in list(self.telegraphs):
            t.t -= dt
            if t.t <= 0:
                # 触发
                if t.kind == "acid" and t.payload:
                    # payload: dict with {count, radius, life, dps, slow}
                    for px, py in t.payload.get("points", []):
                        self.spawn_acid_pool(px, py,
                                             r=t.payload.get("radius", 24),
                                             dps=t.payload.get("dps", ACID_DPS),
                                             slow_frac=t.payload.get("slow", ACID_SLOW_FRAC),
                                             life=t.payload.get("life", ACID_LIFETIME))
                self.telegraphs.remove(t)

    def add_damage_text(self, x, y, amount, crit=False, kind="hp"):
        # allow string labels ("ENRAGE!", "IMMUNE", etc.)
        if isinstance(amount, (int, float)):
            amount = int(amount)
            if amount <= 0:
                return
            self.dmg_texts.append(DamageText(x, y, amount, crit, kind))
        else:
            # label path
            self.dmg_texts.append(DamageText(x, y, str(amount), True if crit else False, kind))

    def update_damage_texts(self, dt: float):
        for d in list(self.dmg_texts):
            d.step(dt)
            if not d.alive():
                self.dmg_texts.remove(d)


# ==================== 游戏渲染函数 ====================
def render_game_iso(screen: pygame.Surface, game_state, player, zombies,
                    bullets=None, enemy_shots=None) -> pygame.Surface:
    # 1) 计算以“玩家所在格”为中心的相机
    px_grid = (player.x + player.size / 2) / CELL_SIZE
    py_grid = (player.y + player.size / 2) / CELL_SIZE
    # 将玩家的等距投影放到屏幕中心，得到 cam 偏移
    pxs, pys = iso_world_to_screen(px_grid, py_grid, 0, 0, 0)
    camx = pxs - VIEW_W // 2
    camy = pys - (VIEW_H - INFO_BAR_HEIGHT) // 2

    screen.fill((22, 22, 22))

    # 2) 画“地面网格”（只画视口周围一圈，避免全图遍历）
    #   估算可见格范围
    margin = 3
    # 用一个大致的逆投影范围（足够覆盖屏幕）
    gx_min = max(0, int(px_grid - VIEW_W // ISO_CELL_W) - margin)
    gx_max = min(GRID_SIZE - 1, int(px_grid + VIEW_W // ISO_CELL_W) + margin)
    gy_min = max(0, int(py_grid - VIEW_H // ISO_CELL_H) - margin)
    gy_max = min(GRID_SIZE - 1, int(py_grid + VIEW_H // ISO_CELL_H) + margin)
    grid_col = (46, 48, 46)
    for gx in range(gx_min, gx_max + 1):
        for gy in range(gy_min, gy_max + 1):
            draw_iso_tile(screen, gx, gy, grid_col, camx, camy, border=1)

    # 2.5) 地面覆盖层：落点提示圈 + 酸池
    # 先画提示圈（空心，颜色来自 TelegraphCircle.color）
    for t in getattr(game_state, "telegraphs", []):
        draw_iso_ground_ellipse(
            screen, t.x, t.y, t.r,
            color=t.color, alpha=180,
            camx=camx, camy=camy,
            fill=False, width=3
        )

    # 再画酸池（实心，微透明绿；你也可以做成分层：外圈更亮）
    for a in getattr(game_state, "acids", []):
        draw_iso_ground_ellipse(
            screen, a.x, a.y, a.r,
            color=(60, 200, 90), alpha=110,
            camx=camx, camy=camy,
            fill=True
        )

    # 3) 收集需要按底部Y排序的可绘制体
    drawables = []

    # 3.1 障碍（立体墙砖，按“底边 y + 墙高”排）
    for (gx, gy), ob in game_state.obstacles.items():
        base_col = (120, 120, 120) if ob.type == "Indestructible" else (200, 80, 80)
        if ob.type == "Destructible" and ob.health is not None:
            t = max(0.4, min(1.0, ob.health / float(max(1, OBSTACLE_HEALTH))))
            base_col = (int(200 * t), int(80 * t), int(80 * t))
        top_pts = iso_tile_points(gx, gy, camx, camy)
        sort_y = top_pts[2][1] + (ISO_WALL_Z if WALL_STYLE == "prism" else (12 if WALL_STYLE == "hybrid" else 0))
        drawables.append(("wall", sort_y, {"gx": gx, "gy": gy, "color": base_col}))

    # 3.2 地面上的小物：金币 / 治疗（存屏幕像素坐标）
    for s in getattr(game_state, "spoils", []):
        wx, wy = s.base_x / CELL_SIZE, (s.base_y - s.h - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
        drawables.append(("coin", sy, {"cx": sx, "cy": sy, "r": s.r}))

    for h in getattr(game_state, "heals", []):
        wx, wy = h.base_x / CELL_SIZE, (h.base_y - h.h - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
        drawables.append(("heal", sy, {"cx": sx, "cy": sy, "r": h.r}))

    for it in getattr(game_state, "items", []):
        wx = it.center[0] / CELL_SIZE
        wy = (it.center[1] - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
        drawables.append(("item", sy, {"cx": sx, "cy": sy, "r": it.radius, "main": it.is_main}))

    # 3.3 僵尸 & 玩家（以脚底点排序）
    for z in zombies:
        wx, wy = (z.x + z.size / 2) / CELL_SIZE, (z.y + z.size / 2) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
        drawables.append(("zombie", sy, {"cx": sx, "cy": sy, "z": z}))

    wx, wy = (player.x + player.size / 2) / CELL_SIZE, (player.y + player.size / 2) / CELL_SIZE
    psx, psy = iso_world_to_screen(wx, wy, 0, camx, camy)
    drawables.append(("player", psy, {"cx": psx, "cy": psy, "p": player}))

    # 3.4 子弹/敌弹（位置也投影后按底部排序）
    if bullets:
        for b in bullets:
            wx, wy = b.x / CELL_SIZE, (b.y - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("bullet", sy, {"cx": sx, "cy": sy}))
    if enemy_shots:
        for es in enemy_shots:
            wx, wy = es.x / CELL_SIZE, (es.y - INFO_BAR_HEIGHT) / CELL_SIZE
            sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
            drawables.append(("eshot", sy, {"cx": sx, "cy": sy}))

    # 4) 排序后统一绘制（只保留这一段循环）
    drawables.sort(key=lambda x: x[1])
    for kind, _, data in drawables:
        if kind == "wall":
            gx, gy, col = data["gx"], data["gy"], data["color"]
            if WALL_STYLE == "prism":
                draw_iso_prism(screen, gx, gy, col, camx, camy, wall_h=ISO_WALL_Z)
            elif WALL_STYLE == "hybrid":
                # 1) 低矮“棱台”底座（12px 高）
                draw_iso_prism(screen, gx, gy, col, camx, camy, wall_h=12)
                # 2) 直立占位柱（将来替换为贴图），锚点=脚底 midbottom
                wx, wy = gx + 0.5, gy + 0.5
                sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
                rect_h = int(ISO_CELL_H * 1.8)
                rect_w = int(ISO_CELL_W * 0.35)
                pillar = pygame.Rect(0, 0, rect_w, rect_h)
                pillar.midbottom = (sx, sy)
                pygame.draw.rect(screen, col, pillar, border_radius=rect_w // 3)
            else:
                # billboard：只画顶面，类似《饥荒》平面贴图风格
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
            pygame.draw.circle(screen, (220, 60, 60), (cx, cy), r)
            pygame.draw.rect(screen, (255, 255, 255), pygame.Rect(cx - 2, cy - r + 3, 4, r * 2 - 6))
            pygame.draw.rect(screen, (255, 255, 255), pygame.Rect(cx - r + 3, cy - 2, r * 2 - 6, 4))
        elif kind == "item":
            cx, cy, r = data["cx"], data["cy"], data["r"]
            shadow = pygame.Surface((r * 4, r * 2), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, ISO_SHADOW_ALPHA), shadow.get_rect())
            screen.blit(shadow, shadow.get_rect(center=(cx, cy + 6)))
            # 你可以按 is_main 改颜色/样式
            # 轻微地面辉光
            glow = pygame.Surface((r * 4, r * 2), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (255, 240, 120, 90), glow.get_rect())
            screen.blit(glow, glow.get_rect(center=(cx, cy + 6)))

            # 本体：明黄色
            pygame.draw.circle(screen, (255, 224, 0), (cx, cy), r)
            pygame.draw.circle(screen, (255, 255, 180), (cx, cy), r, 2)

        elif kind == "bullet":
            pygame.draw.circle(screen, (255, 255, 255), (data["cx"], data["cy"]), BULLET_RADIUS)
        elif kind == "eshot":
            pygame.draw.circle(screen, (255, 120, 50), (data["cx"], data["cy"]), BULLET_RADIUS)
        elif kind == "zombie":
            z, cx, cy = data["z"], data["cx"], data["cy"]
            sh = pygame.Surface((ISO_CELL_W // 2, ISO_CELL_H // 2), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, ISO_SHADOW_ALPHA), sh.get_rect())
            screen.blit(sh, sh.get_rect(center=(cx, cy + 6)))

            base = int(CELL_SIZE * 0.6)
            draw_size = base if not getattr(z, "is_boss", False) else max(base, int(z.rect.w))  # use boss rect

            body = pygame.Rect(0, 0, draw_size, draw_size)
            body.midbottom = (cx, cy)

            # 拾取光晕（金色）
            if getattr(z, "_gold_glow_t", 0.0) > 0.0:
                glow = pygame.Surface((int(draw_size * 1.6), int(draw_size * 1.0)), pygame.SRCALPHA)
                alpha = int(120 * (z._gold_glow_t / Z_GLOW_TIME))
                pygame.draw.ellipse(glow, (255, 220, 90, max(30, alpha)), glow.get_rect())
                screen.blit(glow, glow.get_rect(center=(cx, cy)))

            # 本体
            base = int(CELL_SIZE * 0.6)
            draw_size = base if not getattr(z, "is_boss", False) else max(base, int(z.rect.w))  # use boss rect

            body = pygame.Rect(0, 0, draw_size, draw_size)
            body.midbottom = (cx, cy)
            col = ZOMBIE_COLORS.get(getattr(z, "type", "basic"), (255, 60, 60))
            pygame.draw.rect(screen, col, body)

            # 强化视觉：持币较多时加金色外轮廓
            coins = int(getattr(z, "spoils", 0))
            if coins >= Z_SPOIL_SPD_STEP:
                pygame.draw.rect(screen, (255, 215, 0), body, 3)
            elif coins >= Z_SPOIL_ATK_STEP:
                pygame.draw.rect(screen, (220, 180, 80), body, 2)

            # 头顶显示金币数量
            if coins > 0:
                f = pygame.font.SysFont(None, 18)
                txt = f.render(f"{coins}", True, (255, 225, 120))
                screen.blit(txt, txt.get_rect(midbottom=(cx, body.top - 4)))

            col = ZOMBIE_COLORS.get(getattr(z, "type", "basic"), (255, 60, 60))
            if z.is_boss: pygame.draw.rect(screen, (255, 215, 0), body.inflate(4, 4), 3)
            pygame.draw.rect(screen, col, body)
        elif kind == "player":
            p, cx, cy = data["p"], data["cx"], data["cy"]
            sh = pygame.Surface((ISO_CELL_W // 2, ISO_CELL_H // 2), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, ISO_SHADOW_ALPHA), sh.get_rect())
            screen.blit(sh, sh.get_rect(center=(cx, cy + 6)))
            size = int(CELL_SIZE * 0.6)
            rect = pygame.Rect(0, 0, size, size);
            rect.midbottom = (cx, cy)
            col = (240, 80, 80) if (p.hit_cd > 0 and (pygame.time.get_ticks() // 80) % 2 == 0) else (0, 255, 0)
            pygame.draw.rect(screen, col, rect)

    # --- damage numbers (iso) ---
    for d in getattr(game_state, "dmg_texts", []):
        # 世界像素 -> 格 -> 等距投影
        wx = d.x / CELL_SIZE
        wy = (d.y - INFO_BAR_HEIGHT) / CELL_SIZE
        sx, sy = iso_world_to_screen(wx, wy, 0, camx, camy)
        sy += d.screen_offset_y()

        # 颜色：HP=红/白，护盾=蓝
        if d.kind == "shield":
            col = (120, 200, 255)
        else:
            col = (255, 100, 100) if not d.crit else (255, 240, 120)

        size = DMG_TEXT_SIZE_NORMAL if not d.crit else DMG_TEXT_SIZE_CRIT
        font = pygame.font.SysFont(None, size, bold=d.crit)

        surf = font.render(str(d.amount), True, col)
        surf.set_alpha(d.alpha())
        screen.blit(surf, surf.get_rect(center=(int(sx), int(sy))))

    # 5) 顶层 HUD（沿用你现有 HUD 代码即可）
    #    直接调用原 render_game 里“顶栏 HUD 的那段”（从画黑色 InfoBar 开始，到金币/物品文字结束）
    #    —— 为避免重复代码，可以把那段 HUD 抽成一个小函数，这里调用即可。
    draw_ui_topbar(screen, game_state, player, time_left=globals().get("_time_left_runtime"))

    bosses = _find_all_bosses(zombies)
    if len(bosses) >= 2:
        draw_boss_hp_bars_twin(screen, bosses[:2])
    elif len(bosses) == 1:
        draw_boss_hp_bar(screen, bosses[0])

    pygame.display.flip()

    return screen.copy()


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

    # small yellow fragment icon
    icon_x = VIEW_W - 120
    icon_y = 10
    pygame.draw.circle(screen, (255, 255, 0), (icon_x, icon_y + 8), 8)

    # --- draw items ---
    for item in game_state.items:
        # convert world -> screen using camera offset
        sx = int(item.center[0] - cam_x)
        sy = int(item.center[1] - cam_y)
        color = (255, 255, 100) if item.is_main else (255, 255, 0)
        pygame.draw.circle(screen, color, (sx, sy), item.radius)
    # --- Telegraphs (top-down) ---
    for t in getattr(game_state, "telegraphs", []):
        pygame.draw.circle(screen, (255, 60, 60),
                           (int(t.x - cam_x), int(t.y - cam_y)), int(t.r), 2)

    # --- Acid pools (top-down) ---
    for a in getattr(game_state, "acids", []):
        s = pygame.Surface((int(a.r * 2), int(a.r * 2)), pygame.SRCALPHA)
        pygame.draw.circle(s, (60, 200, 90, 110), (int(a.r), int(a.r)), int(a.r))
        screen.blit(s, (int(a.x - a.r - cam_x), int(a.y - a.r - cam_y)))

    # decorations (non-colliding visual fillers)
    for gx, gy in getattr(game_state, 'decorations', []):
        cx = gx * CELL_SIZE + CELL_SIZE // 2 - cam_x
        cy = gy * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT - cam_y
        pygame.draw.circle(screen, (70, 80, 70), (cx, cy), max(2, CELL_SIZE // 8))

    # spoils (coins) on the ground
    for s in getattr(game_state, "spoils", []):
        sx = int(s.base_x - cam_x)
        sy = int((s.base_y - s.h) - cam_y)
        # shadow
        pygame.draw.ellipse(screen, (0, 0, 0, 80), pygame.Rect(sx - s.r, sy + 6, s.r * 2, 6))
        # coin
        pygame.draw.circle(screen, (255, 215, 80), (sx, sy), s.r)
        pygame.draw.circle(screen, (255, 245, 200), (sx, sy), s.r, 1)

    # healing potions (heals) on the ground
    for h in getattr(game_state, "heals", []):
        sx = int(h.base_x - cam_x)
        sy = int((h.base_y - h.h) - cam_y)
        # shadow
        pygame.draw.ellipse(screen, (0, 0, 0, 80), pygame.Rect(sx - h.r, sy + 6, h.r * 2, 6))
        # potion: red circle with white cross
        pygame.draw.circle(screen, (220, 60, 60), (sx, sy), h.r)
        pygame.draw.rect(screen, (255, 255, 255), pygame.Rect(sx - 2, sy - h.r + 3, 4, h.r * 2 - 6))
        pygame.draw.rect(screen, (255, 255, 255), pygame.Rect(sx - h.r + 3, sy - 2, h.r * 2 - 6, 4))

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
        # Elite/Boss outline
        if getattr(zombie, "is_boss", False):
            pygame.draw.rect(screen, (255, 215, 0), zr, 3)  # gold outline
        elif getattr(zombie, "is_elite", False):
            pygame.draw.rect(screen, (180, 220, 255), zr, 2)  # blue outline

        # Affix letter (tiny)
        tag = getattr(zombie, "_affix_tag", None)
        if tag:
            aff_font = pygame.font.SysFont(None, 18)
            screen.blit(aff_font.render(tag, True, (0, 0, 0)), (zr.x + 3, zr.y + 2))
        # 拾取光晕
        if getattr(zombie, "_gold_glow_t", 0.0) > 0.0:
            glow = pygame.Surface((int(zr.width * 1.6), int(zr.height * 1.0)), pygame.SRCALPHA)
            alpha = int(120 * (zombie._gold_glow_t / Z_GLOW_TIME))
            pygame.draw.ellipse(glow, (255, 220, 90, max(30, alpha)), glow.get_rect())
            screen.blit(glow, glow.get_rect(center=zr.midbottom))

        pygame.draw.rect(screen, color, zr)

        # 强化外轮廓
        coins = int(getattr(zombie, "spoils", 0))
        if coins >= Z_SPOIL_SPD_STEP:
            pygame.draw.rect(screen, (255, 215, 0), zr, 3)
        elif coins >= Z_SPOIL_ATK_STEP:
            pygame.draw.rect(screen, (220, 180, 80), zr, 2)

        # 头顶金币计数
        if coins > 0:
            aff_font = pygame.font.SysFont(None, 18)
            tip = aff_font.render(f"{coins}", True, (255, 225, 120))
            screen.blit(tip, tip.get_rect(midbottom=(zr.centerx, zr.top - 4)))

        # HP bar
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
    # --- damage numbers (2D) ---
    for d in getattr(game_state, "dmg_texts", []):
        sx = int(d.x - cam_x)
        sy = int(d.y - cam_y + d.screen_offset_y())
        if d.kind == "shield":
            col = (120, 200, 255)
        else:
            col = (255, 100, 100) if not d.crit else (255, 240, 120)

        size = DMG_TEXT_SIZE_NORMAL if not d.crit else DMG_TEXT_SIZE_CRIT
        font = pygame.font.SysFont(None, size, bold=d.crit)

        surf = font.render(str(d.amount), True, col)
        surf.set_alpha(d.alpha())
        screen.blit(surf, surf.get_rect(center=(sx, sy)))

    draw_ui_topbar(screen, game_state, player, time_left=globals().get("_time_left_runtime"))

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
    spatial = SpatialHash(SPATIAL_CELL)

    obstacles, items, player_start, zombie_starts, main_item_list, decorations = generate_game_entities(
        grid_size=GRID_SIZE,
        obstacle_count=config["obstacle_count"],
        item_count=config["item_count"],
        zombie_count=config["zombie_count"],
        main_block_hp=config["block_hp"]
    )
    # 生成完 obstacles 后 —— 调用兜底
    ensure_passage_budget(obstacles, GRID_SIZE, player_start)

    game_state = GameState(obstacles, items, main_item_list, decorations)
    game_state.current_level = current_level
    player = Player(player_start, speed=PLAYER_SPEED)
    player.fire_cd = 0.0
    apply_player_carry(player, globals().get("_carry_player_state"))

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
        # 玩家中心（像素）
        px, py = player.rect.centerx, player.rect.centery

        # 玩家格坐标（用于“两格内”判断）
        pgx = int(px // CELL_SIZE)
        pgy = int((py - INFO_BAR_HEIGHT) // CELL_SIZE)

        # 1) 两格内是否有可破坏障碍？有 → 直接优先最近的那一个
        force_blocks = []
        for gp, ob in game_state.obstacles.items():
            if getattr(ob, "type", "") != "Destructible":
                continue
            gx, gy = gp
            manh = abs(gx - pgx) + abs(gy - pgy)  # 曼哈顿距离（格）
            if manh <= int(PLAYER_BLOCK_FORCE_RANGE_TILES):
                cx, cy = ob.rect.centerx, ob.rect.centery
                d2 = (cx - px) ** 2 + (cy - py) ** 2
                force_blocks.append((d2, ('block', gp, ob, cx, cy)))

        if force_blocks:
            force_blocks.sort(key=lambda t: t[0])  # 最近优先
            best_tuple = force_blocks[0][1]
            d = (force_blocks[0][0]) ** 0.5
            return best_tuple, d

        # 2) 正常权重选择（仅考虑“射程内”的目标）
        R2 = float(PLAYER_TARGET_RANGE) ** 2

        # 收集候选：僵尸（射程内）
        z_cands = []
        for z in zombies:
            cx, cy = z.rect.centerx, z.rect.centery
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 <= R2:
                z_cands.append((z, cx, cy, d2))

        # 收集候选：可破坏障碍（射程内）
        b_cands = []
        for gp, ob in game_state.obstacles.items():
            if getattr(ob, "type", "") != "Destructible":
                continue
            cx, cy = ob.rect.centerx, ob.rect.centery
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 <= R2:
                b_cands.append((gp, ob, cx, cy, d2))

        # 射程内什么都没有 → 没目标
        if not z_cands and not b_cands:
            return (None, None)

        # 权重评分：
        # - 基于距离的衰减：基础分 = -d2 * k（d2 越小，分越高）
        # - 僵尸优先：加较高常数；障碍其次：加较低常数
        #   （权重不要过大，否则完全遮蔽距离差异）
        DIST_K = 1e-4
        W_ZOMBIE = 1200.0
        W_BLOCK = 800.0

        best = None
        best_score = -1e18

        # 僵尸优先（仍受距离影响）
        for z, cx, cy, d2 in z_cands:
            s = -d2 * DIST_K + W_ZOMBIE
            # 若想进一步区分类型，可在此额外加分（例如自爆怪、远程怪等）
            if s > best_score:
                best_score = s
                best = ('zombie', None, z, cx, cy, d2)

        # 障碍次之（仍受距离影响）
        for gp, ob, cx, cy, d2 in b_cands:
            s = -d2 * DIST_K + W_BLOCK
            if s > best_score:
                best_score = s
                best = ('block', gp, ob, cx, cy, d2)

        if best is None:
            return (None, None)

        kind, gp_or_none, obj, cx, cy, d2 = best
        return (kind, gp_or_none, obj, cx, cy), (d2 ** 0.5)

    # Initial spawn: use threat budget once
    # AFTER
    spawned = spawn_wave_with_budget(game_state, player, current_level, wave_index, zombies, ZOMBIE_CAP)
    if spawned > 0:
        wave_index += 1
        globals()["_max_wave_reached"] = max(globals().get("_max_wave_reached", 0), wave_index)

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
                spawned = spawn_wave_with_budget(game_state, player, current_level, wave_index, zombies, ZOMBIE_CAP)
                if spawned > 0:
                    wave_index += 1
                    globals()["_max_wave_reached"] = max(globals().get("_max_wave_reached", 0), wave_index)

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
                    # carry your current level/xp forward
                    globals()["_carry_player_state"] = capture_player_carry(player)
                    # write a progress save (this contains META + carry)
                    save_progress(current_level=current_level,
                                  zombie_cards_collected=zombie_cards_collected,
                                  max_wave_reached=wave_index)
                    return 'home', config.get('reward', None), bg

                elif choice == 'exit':
                    # write a progress save so Homepage shows CONTINUE
                    save_progress(current_level=current_level,
                                  zombie_cards_collected=zombie_cards_collected,
                                  max_wave_reached=wave_index)
                    return 'exit', config.get('reward', None), bg

        keys = pygame.key.get_pressed()
        # ---- slow 计时衰减 + 电告圈与酸池更新（在移动之前）----
        player.slow_t = max(0.0, getattr(player, "slow_t", 0.0) - dt)
        game_state.update_telegraphs(dt)  # 到时生成酸池
        game_state.update_acids(dt, player)  # 结算DoT并刷新 slow_t
        # -----------------------------------------------
        player.move(keys, game_state.obstacles)
        game_state.collect_item(player.rect)
        game_state.update_spoils(dt)
        for z in zombies:
            got = game_state.collect_spoils_for_zombie(z)
            if got > 0:
                z.add_spoils(got)
            # 衰减拾取光晕
            z._gold_glow_t = max(0.0, getattr(z, "_gold_glow_t", 0.0) - dt)
        game_state.collect_spoils(player.rect)
        game_state.update_heals(dt)
        game_state.update_damage_texts(dt)
        game_state.collect_heals(player)
        # --- NEW: Telegraph/Acid 更新 + 减速衰减 ---
        game_state.update_telegraphs(dt)              # 倒计时→到时生成酸池
        game_state.update_acids(dt, player)           # 酸池伤害&施加 slow_t
        player.slow_t = max(0.0, getattr(player, "slow_t", 0.0) - dt)  # 每帧自然恢复
        # —— 结算离开酸池后的 DoT（中毒） ——
        if player.acid_dot_timer > 0.0:
            player.acid_dot_timer = max(0.0, player.acid_dot_timer - dt)
            player._acid_dot_accum += player.acid_dot_dps * dt
            whole = int(player._acid_dot_accum)
            if whole > 0:
                player.hp -= whole
                game_state.add_damage_text(player.rect.centerx, player.rect.top - 8, whole, crit=False,
                                           kind="hp_player")
                player._acid_dot_accum -= whole
            # （可选）当计时走完，清空 DoT dps
            if player.acid_dot_timer <= 0.0:
                player.acid_dot_dps = 0.0


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
            if player.hit_cd <= 0.0 and circle_touch(zombie, player):
                player.hp -= int(ZOMBIE_CONTACT_DAMAGE)
                player.hit_cd = float(PLAYER_HIT_COOLDOWN)
                game_state.add_damage_text(player.rect.centerx, player.rect.centery, ZOMBIE_CONTACT_DAMAGE, crit=False,
                                           kind="hp")

                if player.hp <= 0:
                    game_result = "fail"
                    running = False
                    break
        # special behaviors & enemy shots
        for z in list(zombies):
            z.update_special(dt, player, zombies, enemy_shots, game_state)
            if z.hp <= 0:
                if getattr(z, "is_boss", False) and getattr(z, "twin_id", None) is not None:
                    trigger_twin_enrage(z, zombies, game_state)
                total_drop = int(SPOILS_PER_KILL) + int(getattr(z, "spoils", 0))
                if total_drop > 0:
                    game_state.spawn_spoils(z.rect.centerx, z.rect.centery, total_drop)
                if random.random() < HEAL_DROP_CHANCE_ZOMBIE:
                    game_state.spawn_heal(z.rect.centerx, z.rect.centery, HEAL_POTION_AMOUNT)

                # 额外经验（非子弹击杀时）
                try:
                    player.add_xp(int(getattr(z, "spoils", 0)) * int(Z_SPOIL_XP_BONUS_PER))
                except Exception:
                    pass

                transfer_xp_to_neighbors(z, zombies)
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

        if USE_ISO:
            last_frame = render_game_iso(pygame.display.get_surface(), game_state, player, zombies, bullets,
                                         enemy_shots)
        else:
            last_frame = render_game(pygame.display.get_surface(), game_state, player, zombies, bullets, enemy_shots)

        if game_result == "success":
            globals()["_last_spoils"] = getattr(game_state, "spoils_gained", 0)
            globals()["_carry_player_state"] = capture_player_carry(player)
        elif game_result == "fail":
            # NEW: save carry on death so 'Retry' keeps your levels/xp
            globals()["_carry_player_state"] = capture_player_carry(player)

    return game_result, config.get("reward", None), last_frame


def run_from_snapshot(save_data: dict) -> Tuple[str, Optional[str], pygame.Surface]:
    """Resume a game from a snapshot in save_data; same return contract as main_run_level."""
    assert save_data.get("mode") == "snapshot"
    meta = save_data.get("meta", {})
    snap = save_data.get("snapshot", {})

    # Use the saved level index when scaling spawns
    level_idx = int(meta.get("current_level", current_level))

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

    # Items & decorations
    items = [Item(int(it.get("x", 0)), int(it.get("y", 0)), bool(it.get("is_main", False)))
             for it in snap.get("items", [])]
    decorations = [tuple(d) for d in snap.get("decorations", [])]

    game_state = GameState(obstacles, items,
                           [(i.x, i.y) for i in items if getattr(i, 'is_main', False)],
                           decorations)
    game_state.current_level = level_idx

    # Player
    p = snap.get("player", {})
    player = Player((0, 0), speed=int(p.get("speed", PLAYER_SPEED)))
    player.x = float(p.get("x", 0.0));
    player.y = float(p.get("y", 0.0))
    player.rect.x = int(player.x);
    player.rect.y = int(player.y) + INFO_BAR_HEIGHT
    player.fire_cd = float(p.get("fire_cd", 0.0))
    player.max_hp = int(p.get("max_hp", PLAYER_MAX_HP))
    player.hp = int(p.get("hp", PLAYER_MAX_HP))
    player.hit_cd = float(p.get("hit_cd", 0.0))
    player.level = int(p.get("level", 1))
    player.xp = int(p.get("xp", 0))
    player.xp_to_next = player_xp_required(player.level)

    if not hasattr(player, 'fire_cd'): player.fire_cd = 0.0

    # Zombies
    zombies: List[Zombie] = []
    for z in snap.get("zombies", []):
        zobj = Zombie((0, 0),
                      attack=int(z.get("attack", ZOMBIE_ATTACK)),
                      speed=int(z.get("speed", ZOMBIE_SPEED)),
                      ztype=z.get("type", "basic"),
                      hp=int(z.get("hp", 30)))
        zobj.max_hp = int(z.get("max_hp", int(z.get("hp", 30))))
        zobj.x = float(z.get("x", 0.0));
        zobj.y = float(z.get("y", 0.0))
        zobj.rect.x = int(zobj.x);
        zobj.rect.y = int(zobj.y) + INFO_BAR_HEIGHT
        zobj._spawn_elapsed = float(z.get("spawn_elapsed", 0.0))
        zobj.attack_timer = float(z.get("attack_timer", 0.0))
        # clamp restored speed so resumed runs don't create super-speed zombies
        zobj.speed = min(ZOMBIE_SPEED_MAX, max(1, int(zobj.speed)))
        zombies.append(zobj)

    # Bullets
    bullets: List[Bullet] = []
    for b in snap.get("bullets", []):
        bobj = Bullet(float(b.get("x", 0.0)), float(b.get("y", 0.0)),
                      float(b.get("vx", 0.0)), float(b.get("vy", 0.0)),
                      MAX_FIRE_RANGE)
        bobj.traveled = float(b.get("traveled", 0.0))
        bullets.append(bobj)

    enemy_shots: List[EnemyShot] = []

    # Timer
    time_left = float(snap.get("time_left", LEVEL_TIME_LIMIT))
    globals()["_time_left_runtime"] = time_left  # keep global for HUD

    screen = pygame.display.get_surface()
    clock = pygame.time.Clock()
    running = True
    last_frame = None
    chosen_zombie_type = meta.get("chosen_zombie_type", "basic")

    # Spawner state
    spawn_timer = 0.0
    wave_index = 0

    def player_center():
        return player.x + player.size / 2, player.y + player.size / 2 + INFO_BAR_HEIGHT

    def find_target():
        # 玩家中心（像素）
        px, py = player.rect.centerx, player.rect.centery

        # 玩家格坐标（用于“两格内”判断）
        pgx = int(px // CELL_SIZE)
        pgy = int((py - INFO_BAR_HEIGHT) // CELL_SIZE)

        # 1) 两格内是否有可破坏障碍？有 → 直接优先最近的那一个
        force_blocks = []
        for gp, ob in game_state.obstacles.items():
            if getattr(ob, "type", "") != "Destructible":
                continue
            gx, gy = gp
            manh = abs(gx - pgx) + abs(gy - pgy)  # 曼哈顿距离（格）
            if manh <= int(PLAYER_BLOCK_FORCE_RANGE_TILES):
                cx, cy = ob.rect.centerx, ob.rect.centery
                d2 = (cx - px) ** 2 + (cy - py) ** 2
                force_blocks.append((d2, ('block', gp, ob, cx, cy)))

        if force_blocks:
            force_blocks.sort(key=lambda t: t[0])  # 最近优先
            best_tuple = force_blocks[0][1]
            d = (force_blocks[0][0]) ** 0.5
            return best_tuple, d

        # 2) 正常权重选择（仅考虑“射程内”的目标）
        R2 = float(PLAYER_TARGET_RANGE) ** 2

        # 收集候选：僵尸（射程内）
        z_cands = []
        for z in zombies:
            cx, cy = z.rect.centerx, z.rect.centery
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 <= R2:
                z_cands.append((z, cx, cy, d2))

        # 收集候选：可破坏障碍（射程内）
        b_cands = []
        for gp, ob in game_state.obstacles.items():
            if getattr(ob, "type", "") != "Destructible":
                continue
            cx, cy = ob.rect.centerx, ob.rect.centery
            d2 = (cx - px) ** 2 + (cy - py) ** 2
            if d2 <= R2:
                b_cands.append((gp, ob, cx, cy, d2))

        # 射程内什么都没有 → 没目标
        if not z_cands and not b_cands:
            return (None, None)

        # 权重评分：
        # - 基于距离的衰减：基础分 = -d2 * k（d2 越小，分越高）
        # - 僵尸优先：加较高常数；障碍其次：加较低常数
        #   （权重不要过大，否则完全遮蔽距离差异）
        DIST_K = 1e-4
        W_ZOMBIE = 1200.0
        W_BLOCK = 800.0

        best = None
        best_score = -1e18

        # 僵尸优先（仍受距离影响）
        for z, cx, cy, d2 in z_cands:
            s = -d2 * DIST_K + W_ZOMBIE
            # 若想进一步区分类型，可在此额外加分（例如自爆怪、远程怪等）
            if s > best_score:
                best_score = s
                best = ('zombie', None, z, cx, cy, d2)

        # 障碍次之（仍受距离影响）
        for gp, ob, cx, cy, d2 in b_cands:
            s = -d2 * DIST_K + W_BLOCK
            if s > best_score:
                best_score = s
                best = ('block', gp, ob, cx, cy, d2)

        if best is None:
            return (None, None)

        kind, gp_or_none, obj, cx, cy, d2 = best
        return (kind, gp_or_none, obj, cx, cy), (d2 ** 0.5)

    while running:
        dt = clock.tick(60) / 1000.0

        # survival timer
        time_left -= dt
        globals()["_time_left_runtime"] = time_left
        if time_left <= 0:
            # win on survival
            chosen = show_success_screen(
                screen,
                last_frame or render_game(screen, game_state, player, zombies, bullets, enemy_shots),
                reward_choices=[]
            )
            return "success", None, last_frame or screen.copy()

        # input
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
                    snap2 = capture_snapshot(
                        game_state, player, zombies, level_idx,
                        meta.get("zombie_cards_collected", []),
                        chosen_zombie_type, bullets
                    )
                    save_snapshot(snap2)
                    return 'home', None, bg

                elif choice == 'exit':
                    # also save progress from a snapshot resume
                    save_progress(
                        current_level=level_idx,
                        zombie_cards_collected=meta.get("zombie_cards_collected", []),
                        max_wave_reached=wave_index
                    )
                    return 'exit', None, bg

        # movement & pickups
        keys = pygame.key.get_pressed()
        # ---- slow 计时衰减 + 电告圈与酸池更新（在移动之前）----
        player.slow_t = max(0.0, getattr(player, "slow_t", 0.0) - dt)
        game_state.update_telegraphs(dt)  # 到时生成酸池
        game_state.update_acids(dt, player)  # 结算DoT并刷新 slow_t
        # -----------------------------------------------
        player.move(keys, game_state.obstacles)
        game_state.collect_item(player.rect)
        game_state.update_spoils(dt)
        game_state.collect_spoils(player.rect)
        game_state.update_heals(dt)
        game_state.update_damage_texts(dt)
        game_state.collect_heals(player)

        # Autofire
        player.fire_cd = getattr(player, 'fire_cd', 0.0) - dt
        target, dist = find_target()
        if target and player.fire_cd <= 0 and (dist is None or dist <= MAX_FIRE_RANGE):
            _, gp, ob_or_z, cx, cy = target
            px, py = player_center()
            dx, dy = cx - px, cy - py
            L = (dx * dx + dy * dy) ** 2 ** 0.5 if False else ((dx * dx + dy * dy) ** 0.5)  # keep readable
            L = L or 1.0
            vx, vy = (dx / L) * BULLET_SPEED, (dy / L) * BULLET_SPEED
            bullets.append(Bullet(px, py, vx, vy, MAX_FIRE_RANGE, damage=player.bullet_damage))
            player.fire_cd += player.fire_cooldown()

        # Update bullets
        for b in list(bullets):
            b.update(dt, game_state, zombies, player)
            if not b.alive:
                bullets.remove(b)

        # === wave spawning (budget-based ONLY) ===
        spawn_timer += dt
        if spawn_timer >= SPAWN_INTERVAL:
            spawn_timer = 0.0
            if len(zombies) < ZOMBIE_CAP:
                spawned = spawn_wave_with_budget(game_state, player, level_idx, wave_index, zombies, ZOMBIE_CAP)
                if spawned > 0:
                    wave_index += 1
                    globals()["_max_wave_reached"] = max(globals().get("_max_wave_reached", 0), wave_index)

        # Zombies update & contact damage
        player.hit_cd = max(0.0, player.hit_cd - dt)
        for zombie in list(zombies):
            zombie.move_and_attack(player, list(game_state.obstacles.values()), game_state, dt=dt)
            if player.hit_cd <= 0.0 and circle_touch(zombie, player):
                player.hp -= int(ZOMBIE_CONTACT_DAMAGE)
                player.hit_cd = float(PLAYER_HIT_COOLDOWN)
                game_state.add_damage_text(player.rect.centerx, player.rect.centery, ZOMBIE_CONTACT_DAMAGE, crit=False,
                                           kind="hp")

                if player.hp <= 0:
                    clear_save()
                    action = show_fail_screen(screen,
                                              last_frame or render_game(screen, game_state, player, zombies, bullets,
                                                                        enemy_shots))
                    if action == "home":
                        clear_save();
                        flush_events()
                        return "home", None, last_frame or screen.copy()
                    elif action == "retry":
                        clear_save();
                        flush_events()
                        return "restart", None, last_frame or screen.copy()

        # Special behaviors & enemy shots
        for z in list(zombies):
            z.update_special(dt, player, zombies, enemy_shots, game_state)

            if z.hp <= 0:
                total_drop = int(SPOILS_PER_KILL) + int(getattr(z, "spoils", 0))
                if total_drop > 0:
                    game_state.spawn_spoils(z.rect.centerx, z.rect.centery, total_drop)
                if random.random() < HEAL_DROP_CHANCE_ZOMBIE:
                    game_state.spawn_heal(z.rect.centerx, z.rect.centery, HEAL_POTION_AMOUNT)

                # 额外经验（非子弹击杀时）
                try:
                    player.add_xp(int(getattr(z, "spoils", 0)) * int(Z_SPOIL_XP_BONUS_PER))
                except Exception:
                    pass

                transfer_xp_to_neighbors(z, zombies)
                zombies.remove(z)

        for es in list(enemy_shots):
            es.update(dt, player, game_state)
            if not es.alive:
                enemy_shots.remove(es)

        # Fail check (redundant guard)
        if player.hp <= 0:
            clear_save()
            action = show_fail_screen(screen,
                                      last_frame or render_game(screen, game_state, player, zombies, bullets,
                                                                enemy_shots))
            if action == "home":
                clear_save();
                flush_events()
                return "home", None, last_frame or screen.copy()
            elif action == "retry":
                clear_save();
                flush_events()
                return "restart", None, last_frame or screen.copy()

        if USE_ISO:
            last_frame = render_game_iso(pygame.display.get_surface(), game_state, player, zombies, bullets,
                                         enemy_shots)
        else:
            last_frame = render_game(pygame.display.get_surface(), game_state, player, zombies, bullets, enemy_shots)

    return "home", None, last_frame or screen.copy()



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
        # restore shop upgrades and carry for a fresh run at the stored level
        if save_data:
            META.update(save_data.get("meta", META))
            globals()["_carry_player_state"] = save_data.get("carry_player", None)
            globals()["_pending_shop"] = bool(save_data.get("pending_shop", False))
        else:
            globals()["_carry_player_state"] = None
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
        reset_run_state()
        current_level = 0
        zombie_cards_collected = []
        globals()["_carry_player_state"] = None
        globals()["_pending_shop"] = False
        globals().pop("_last_spoils", None)

    while True:
        # If we saved while in the shop last time, reopen the shop first
        if globals().get("_pending_shop", False):
            action = show_shop_screen(screen)

            if action in (None,):  # user clicked NEXT (closed shop normally)
                globals()["_pending_shop"] = False
                current_level += 1
                save_progress(current_level, zombie_cards_collected)
                # fall through to start the next level immediately

            elif action == "home":
                # keep the shop pending so CONTINUE returns here again
                save_progress(current_level, zombie_cards_collected, pending_shop=True)
                flush_events()
                selection = show_start_menu(screen)
                if not selection: sys.exit()
                mode, save_data = selection
                if mode == "continue" and save_data:
                    META.update(save_data.get("meta", META))
                    globals()["_carry_player_state"] = save_data.get("carry_player", None)
                    globals()["_pending_shop"] = bool(save_data.get("pending_shop", False))
                    current_level = int(save_data.get("current_level", 0))
                    zombie_cards_collected = list(save_data.get("zombie_cards_collected", []))

                else:
                    clear_save()
                    reset_run_state()
                    current_level = 0
                    zombie_cards_collected = []
                    globals()["_carry_player_state"] = None
                    globals()["_pending_shop"] = False
                    globals().pop("_last_spoils", None)
                continue  # back to loop top

            elif action == "restart":
                # just re-show the shop again (still pending)
                continue

            elif action == "exit":
                save_progress(current_level, zombie_cards_collected, pending_shop=True)
                pygame.quit();
                sys.exit()

        config = get_level_config(current_level)
        chosen_zombie =  "basic"
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
                # restore shop upgrades and carry for a fresh run at the stored level
                if save_data:
                    META.update(save_data.get("meta", META))
                    globals()["_carry_player_state"] = save_data.get("carry_player", None)
                else:
                    globals()["_carry_player_state"] = None
                # Update progress trackers
                if save_data.get("mode") == "snapshot":
                    meta = save_data.get("meta", {})
                    current_level = int(meta.get("current_level", 0))
                    zombie_cards_collected = list(meta.get("zombie_cards_collected", []))

                else:
                    current_level = int(save_data.get("current_level", 0))
                    zombie_cards_collected = list(save_data.get("zombie_cards_collected", []))

                globals()["_pending_shop"] = bool(save_data.get("pending_shop", False))

            else:
                clear_save()
                reset_run_state()
                current_level = 0
                zombie_cards_collected = []
                globals()["_carry_player_state"] = None
                globals()["_pending_shop"] = False
                globals().pop("_last_spoils", None)
            continue

        if result == "exit":
            # quit to OS; snapshot saving already done inside the loop
            pygame.quit()
            sys.exit()

        if result == "fail":
            clear_save()
            action = show_fail_screen(screen, bg)
            flush_events()
            if action == "home":
                # NEW: reset per-run carry
                globals()["_carry_player_state"] = None
                selection = show_start_menu(screen)
                if not selection:
                    sys.exit()
                mode, save_data = selection
                # After a fail we always start fresh…
                clear_save()
                reset_run_state()
                current_level = 0
                zombie_cards_collected = []
                continue
            else:
                # action == "retry" → restart this level as a fresh run
                # globals()["_carry_player_state"] = capture_player_carry(player)
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
                    # restore shop upgrades and carry for a fresh run at the stored level
                    if save_data:
                        META.update(save_data.get("meta", META))
                        globals()["_carry_player_state"] = save_data.get("carry_player", None)
                    else:
                        globals()["_carry_player_state"] = None
                    if save_data.get("mode") == "snapshot":
                        meta = save_data.get("meta", {})
                        current_level = int(meta.get("current_level", 0))
                        zombie_cards_collected = list(meta.get("zombie_cards_collected", []))
                    else:
                        current_level = int(save_data.get("current_level", 0))
                        zombie_cards_collected = list(save_data.get("zombie_cards_collected", []))
                else:
                    clear_save()
                    reset_run_state()
                    current_level = 0
                    zombie_cards_collected = []
                    globals()["_carry_player_state"] = None
                continue  # 回到 while 重新开始流程

            elif chosen == "restart":
                # 不加关卡，不保存，直接重来这一关
                continue

            elif chosen in CARD_POOL:
                zombie_cards_collected.append(chosen)
                # bank spoils from this level, then open the shop
                META["spoils"] += int(globals().get("_last_spoils", 0))
                action = show_shop_screen(screen)
                # React to pause-menu choices made from inside the shop
                if action == "home":
                    save_progress(current_level, zombie_cards_collected, pending_shop=True)
                    flush_events()
                    selection = show_start_menu(screen)
                    if not selection: sys.exit()
                    mode, save_data = selection
                    # keep your existing homepage handling logic
                    if mode == "continue" and save_data:
                        # restore shop upgrades and carry for a fresh run at the stored level
                        if save_data:
                            META.update(save_data.get("meta", META))
                            globals()["_carry_player_state"] = save_data.get("carry_player", None)
                        else:
                            globals()["_carry_player_state"] = None
                        if save_data.get("mode") == "snapshot":
                            meta = save_data.get("meta", {})
                            current_level = int(meta.get("current_level", 0))
                            zombie_cards_collected = list(meta.get("zombie_cards_collected", []))
                        else:
                            current_level = int(save_data.get("current_level", 0))
                            zombie_cards_collected = list(save_data.get("zombie_cards_collected", []))
                        globals()["_pending_shop"] = bool(save_data.get("pending_shop", False))

                    else:
                        clear_save()
                        current_level = 0
                        zombie_cards_collected = []
                        globals()["_carry_player_state"] = None
                    continue  # back to the top-level loop
                if action == "restart":
                    # replay the current level (do not advance)
                    continue
                if action == "exit":
                    save_progress(current_level, zombie_cards_collected, pending_shop=True)
                    pygame.quit();
                    sys.exit()
                # Normal shop close → advance level
                current_level += 1
                save_progress(current_level, zombie_cards_collected)

            else:
                META["spoils"] += int(globals().get("_last_spoils", 0))
                action = show_shop_screen(screen)
                if action == "home":
                    save_progress(current_level, zombie_cards_collected, pending_shop=True)
                    flush_events()
                    selection = show_start_menu(screen)
                    if not selection: sys.exit()
                    mode, save_data = selection
                    if mode == "continue" and save_data:
                        # restore shop upgrades and carry for a fresh run at the stored level
                        if save_data:
                            META.update(save_data.get("meta", META))
                            globals()["_carry_player_state"] = save_data.get("carry_player", None)
                        else:
                            globals()["_carry_player_state"] = None
                        if save_data.get("mode") == "snapshot":
                            meta = save_data.get("meta", {})
                            current_level = int(meta.get("current_level", 0))
                            zombie_cards_collected = list(meta.get("zombie_cards_collected", []))
                        else:
                            current_level = int(save_data.get("current_level", 0))
                            zombie_cards_collected = list(save_data.get("zombie_cards_collected", []))
                        globals()["_pending_shop"] = bool(save_data.get("pending_shop", False))

                    else:
                        clear_save()
                        current_level = 0
                        zombie_cards_collected = []
                        globals()["_carry_player_state"] = None
                    continue

                if action == "restart":
                    continue

                if action == "exit":
                    save_progress(current_level, zombie_cards_collected, pending_shop=True)
                    pygame.quit();
                    sys.exit()

                current_level += 1
                save_progress(current_level, zombie_cards_collected)


        else:
            # Unknown state -> go home
            selection = show_start_menu(screen)
            if not selection:
                sys.exit()
            mode, save_data = selection
            if mode == "continue" and save_data:
                # restore shop upgrades and carry for a fresh run at the stored level
                if save_data:
                    META.update(save_data.get("meta", META))
                    globals()["_carry_player_state"] = save_data.get("carry_player", None)
                else:
                    globals()["_carry_player_state"] = None
                if save_data.get("mode") == "snapshot":
                    meta = save_data.get("meta", {})
                    if mode == "continue" and save_data and save_data.get("mode") == "snapshot":
                        current_level = int(meta.get("current_level", 0))
                        zombie_cards_collected = list(meta.get("zombie_cards_collected", []))
                else:
                    current_level = int(save_data.get("current_level", 0))
                    zombie_cards_collected = list(save_data.get("zombie_cards_collected", []))
            else:
                clear_save()
                current_level = 0
                zombie_cards_collected = []
                globals()["_carry_player_state"] = None

# TODO
# Attack MODE need to figure out
# The item collection system can be hugely impact this game to next level
# Player and Zombie both can collect item to upgrade, after kill zombie, player can get the experience to upgrade, and
# I set a timer each game for winning condition, as long as player still alive, after the time is running out
# player won, vice versa. And after each combat, shop( roguelike feature) will appear for player to trade with item
# using the item they collect in the combat

# zombie's health, attack accumulate via level increases
# Special weapon can be trade in shop using big items collected in game(GOLDCOLLECTOR, etc.) OR
# Just make it only unlock by defeating boss/elite
# set limit for player fire rate
# monster type increased:
# influencer: when player approach, decrease player's speed, damage

# Special weapon: GoldCollector, Razor, rage blade jingqiandao

# 模型穿模，调大障碍物脚底的圆形hitbox判定，玩家左右移动的速度会比上下移动速度快不是视错觉需要调整方向向量，heal的颜色可以修改一下容易和敌蛋弄混
# 引入场景buff肉鸽机制，每关开始前会有类似骰子的动画随机出本关的场景buff：暂时想到的风林火山， 敌我双方都会受到增益或debuff
# need more roguelike features
# 命名与分区注释
#
# 在大文件中加入清晰的“分区头”：
#
# Config & Balance
#
# Math & Utils
#
# Entity Classes（Player/Zombie/Bullet/Obstacle/Item/Boss）
#
# AI & Pathfinding（A* / Flow Field）
#
# Level Gen & Spawn
#
# Rendering（iso/ortho，内含 draw_hud）
#
# Screens（Shop/Domain/Success/Fail/Pause）
#
# Main loop / Main entry

# Add new type of boss: BOSS Ⅱ：「雾织母巫 · Mistweaver」
#
# 主题：大雾支配者，靠分身与迷雾错位压迫。
# 它教玩家什么：在视野受限与多目标干扰下，学会读预警、拉开站位，优先处理“视野物件”。
#
# 基本数值（以第10关为基准）
#
# HP：6500（成长系数≈ +12%/关）
#
# 接触伤害：28
# 移速：中等（玩家略快）
# 抗性：距离≥5格时，远程伤害×0.8（逼近打法）
# 机制概览
# 浓雾场（被动）：开场降雾，玩家与怪物显示距离被压到 ~6格；地图上会生成3个驱雾灯笼（可被打掉），点亮/保护时所在半径内清雾。
# 幻影分身：同时存在“本体+2个幻影”。幻影只有1HP，命中即散成雾弹；命中幻影会短暂暴露本体方向（白色箭头飘字提示）。
# 雾门闪现：每10秒在两处雾门间瞬移一次，残留雾门2秒，对穿越者造成小额减速与5点DOT/秒。
# 阶段流程
# P1（100%→70%）
# 技能：雾刃投掷（扇形3枚，地上留1.2s雾带；雾带内ACID风格的减速+每秒10点伤）。
# 召唤：雾妖×3（小型近战，死亡即放小雾爆）。
# 对策：先清幻影与雾妖→保护/占一个灯笼的明区。
# P2（70%→35%）
# 白化风暴：每8秒一次全屏白雾，0.8秒后收束为随机8个“雾标点”，点位落雾池（每秒14伤+减速）。
# 静默领域：随机圆区3秒，屏蔽冲刺/技能；投掷与走位配合压边。
# 召唤→幻影刷新为3个。
# 对策：靠灯笼明区与移动读点，优先踩离雾池。
# P3（35%→0%）
# 猎杀回响：每损失10% HP发一次声纳圈（环形预警），命中的玩家在3秒内留下脚印（被本体追击加速）。
# 雾身：受击后有15%概率瞬时“雾化”0.7s免疫并位移2格。
# 对策：持续移动+在明区内输出；抓住雾化结束的硬直窗口。
# 掉落与奖励
# 灯笼全保留可得视野型饰品（+感知半径/更亮地面指示）。
# 额外灵魂币与少量治疗。

# 金币大盗 (Coin Bandit) - 随机刷新小BOSS
# 设计概念
# 一个狡猾的盗贼型小BOSS，专门偷取玩家金币并在被击败后返还。
#
# 核心机制
# 随机出现：在非BOSS关卡中随机刷新，出现时有特殊音效和视觉提示
#
# 金币窃取：每次接触玩家会偷取一定比例的金币（5-10%）
#
# 敏捷逃避：高移动速度，会优先躲避玩家而不是直接对抗
#
# 财富返还：被击败后掉落一个钱袋，包含所有偷取的金币加上额外奖励
#
# 逃脱机制：如果在特定时间内未被击败，会带着金币逃离关卡