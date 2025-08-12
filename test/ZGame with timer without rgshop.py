
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

# ==================== 游戏常量配置 ====================
GAME_TITLE = "Neuroscape: Mind Runner"
INFO_BAR_HEIGHT = 40
GRID_SIZE = 28
CELL_SIZE = 40
WINDOW_SIZE = GRID_SIZE * CELL_SIZE
TOTAL_HEIGHT = WINDOW_SIZE + INFO_BAR_HEIGHT
VIEW_W = WINDOW_SIZE
VIEW_H = TOTAL_HEIGHT

# Map tuning
OBSTACLE_HEALTH = 22
MAIN_BLOCK_HEALTH = 40
OBSTACLE_DENSITY = 0.12
DECOR_DENSITY = 0.06
MIN_ITEMS = 8
PLAYER_SPEED = 5
ZOMBIE_SPEED = 2
ZOMBIE_ATTACK = 10

# === Survival & Player Health ===
GAME_TIMER_SECONDS = 45.0  # seconds per stage
PLAYER_MAX_HP = 100        # player's maximum HP
PLAYER_CONTACT_COOLDOWN = 0.6  # seconds of i-frames between contact hits

# --- combat tuning (Brotato-like) ---
FIRE_RATE = None            # shots per second; if None, derive from BULLET_SPACING_PX
BULLET_SPEED = 900.0        # pixels per second
BULLET_SPACING_PX = 260.0   # distance between bullets along their path
BULLET_RADIUS = 4
BULLET_DAMAGE_ZOMBIE = 12
BULLET_DAMAGE_BLOCK = 10
MAX_FIRE_RANGE = 800.0

if FIRE_RATE:
    FIRE_COOLDOWN = 1.0 / float(FIRE_RATE)
else:
    FIRE_COOLDOWN = float(BULLET_SPACING_PX) / float(BULLET_SPEED)

# Save/Load
BASE_DIR = os.path.dirname(__file__) if "__file__" in globals() else os.getcwd()
SAVE_DIR = os.path.join(BASE_DIR, "TEMP")
os.makedirs(SAVE_DIR, exist_ok=True)
SAVE_FILE = os.path.join(SAVE_DIR, "savegame.json")

CARD_POOL = ["zombie_fast", "zombie_strong", "zombie_tank", "zombie_spitter", "zombie_leech"]
LEVELS = [
    {"obstacle_count": 15, "item_count": 3, "zombie_count": 1, "block_hp": 10, "zombie_types": ["basic"], "reward": "zombie_fast"},
    {"obstacle_count": 18, "item_count": 4, "zombie_count": 2, "block_hp": 15, "zombie_types": ["basic", "strong"], "reward": "zombie_strong"},
]

DIRECTIONS = {pygame.K_a: (-1, 0), pygame.K_d: (1, 0), pygame.K_w: (0, -1), pygame.K_s: (0, 1)}

# ==================== Save/Load Helpers ====================
def save_progress(current_level: int, zombie_cards_collected: List[str]) -> None:
    data = {"mode": "meta", "version": 3, "current_level": int(current_level), "zombie_cards_collected": list(zombie_cards_collected)}
    try:
        with open(SAVE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[Save] Failed to write save file: {e}", file=sys.stderr)

def capture_snapshot(game_state, player, zombies, current_level: int, zombie_cards_collected: List[str], chosen_zombie_type: str = "basic", bullets: Optional[List['Bullet']]=None, time_left: Optional[float]=None) -> dict:
    snap = {
        "mode": "snapshot",
        "version": 3,
        "meta": {"current_level": int(current_level), "zombie_cards_collected": list(zombie_cards_collected), "chosen_zombie_type": str(chosen_zombie_type or "basic")},
        "snapshot": {
            "player": {"x": float(player.x), "y": float(player.y), "speed": player.speed, "size": player.size,
                       "hp": int(getattr(player, "hp", PLAYER_MAX_HP)), "max_hp": int(getattr(player, "max_hp", PLAYER_MAX_HP)),
                       "fire_cd": float(getattr(player, "fire_cd", 0.0)), "damage_cd": float(getattr(player, "damage_cd", 0.0))},
            "zombies": [{
                "x": float(z.x), "y": float(z.y), "attack": int(getattr(z, "attack", 10)), "speed": int(getattr(z, "speed", 2)),
                "type": str(getattr(z, "type", "basic")), "hp": int(getattr(z, "hp", 30)), "max_hp": int(getattr(z, "max_hp", getattr(z, "hp", 30))),
                "spawn_elapsed": float(getattr(z, "_spawn_elapsed", 0.0)), "attack_timer": float(getattr(z, "attack_timer", 0.0)),
            } for z in zombies],
            "obstacles": [{
                "x": int(ob.rect.x // CELL_SIZE), "y": int((ob.rect.y - INFO_BAR_HEIGHT) // CELL_SIZE),
                "type": ob.type, "health": None if ob.health is None else int(ob.health), "main": bool(getattr(ob, "is_main_block", False)),
            } for ob in game_state.obstacles.values()],
            "items": [{"x": int(it.x), "y": int(it.y), "is_main": bool(it.is_main)} for it in game_state.items],
            "decorations": [[int(dx), int(dy)] for (dx, dy) in getattr(game_state, "decorations", [])],
            "bullets": [{"x": float(b.x), "y": float(b.y), "vx": float(b.vx), "vy": float(b.vy), "traveled": float(b.traveled)} for b in (bullets or []) if getattr(b, "alive", True)],
            "time_left": float(time_left) if time_left is not None else None
        }
    }
    return snap

def save_snapshot(snapshot: dict) -> None:
    try:
        with open(SAVE_FILE, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f)
    except Exception as e:
        print(f"[Save] Failed to write snapshot: {e}", file=sys.stderr)

def load_save() -> Optional[dict]:
    try:
        if not os.path.exists(SAVE_FILE):
            return None
        with open(SAVE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        if "mode" not in data:
            data["mode"] = "meta"
        if data["mode"] == "meta":
            data.setdefault("current_level", 0); data.setdefault("zombie_cards_collected", [])
        elif data["mode"] == "snapshot":
            data.setdefault("meta", {}); data["meta"].setdefault("current_level", 0); data["meta"].setdefault("zombie_cards_collected", []); data["meta"].setdefault("chosen_zombie_type", "basic")
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

def draw_settings_gear(screen, x, y):
    rect = pygame.Rect(x, y, 32, 24)
    pygame.draw.rect(screen, (50, 50, 50), rect, 2)
    cx, cy = x + 16, y + 12
    pygame.draw.circle(screen, (200, 200, 200), (cx, cy), 8, 2)
    pygame.draw.circle(screen, (200, 200, 200), (cx, cy), 3)
    for ang in (0, 60, 120, 180, 240, 300):
        rad = math.radians(ang)
        x1 = int(cx + 10 * math.cos(rad)); y1 = int(cy + 10 * math.sin(rad))
        x2 = int(cx + 14 * math.cos(rad)); y2 = int(cy + 14 * math.sin(rad))
        pygame.draw.line(screen, (200, 200, 200), (x1, y1), (x2, y2), 2)
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
        lw = int(door_width * progress); rw = int(door_width * progress)
        left_rect.width = lw; right_rect.x = VIEW_W - rw; right_rect.width = rw
        screen.fill((0, 0, 0))
        pygame.draw.rect(screen, color, left_rect); pygame.draw.rect(screen, color, right_rect)
        pygame.display.flip()
        if progress >= 1: break
        clock.tick(60)
    flush_events()

def show_start_menu(screen):
    flush_events()
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont(None, 64)
    subtitle_font = pygame.font.SysFont(None, 24)
    while True:
        screen.fill((26, 28, 24))
        for i in range(0, VIEW_W, 40):
            pygame.draw.rect(screen, (32 + (i // 40 % 2) * 6, 34, 30), (i, 0, 40, VIEW_H))
        title = title_font.render(GAME_TITLE, True, (230, 230, 210)); screen.blit(title, title.get_rect(center=(VIEW_W // 2, 140)))
        sub = subtitle_font.render("A pixel roguelite of memory and monsters", True, (160, 160, 150)); screen.blit(sub, sub.get_rect(center=(VIEW_W // 2, 180)))

        gap_x = 36; top_y = 260; btn_w = 180
        saved_exists = has_save()
        start_label = "START NEW" if saved_exists else "START"
        start_rect = draw_button(screen, start_label, (VIEW_W // 2 - btn_w - gap_x//2, top_y))
        how_rect = draw_button(screen, "HOW TO PLAY", (VIEW_W // 2 + gap_x//2, top_y))

        cont_rect = None; next_y = top_y + 80
        if saved_exists:
            cont_rect = draw_button(screen, "CONTINUE", (VIEW_W // 2 - btn_w//2, next_y)); next_y += 80

        exit_rect = draw_button(screen, "EXIT", (VIEW_W // 2 - btn_w//2, next_y))
        gear_rect = draw_settings_gear(screen, VIEW_W - 44, 8)
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if gear_rect.collidepoint(event.pos):
                    # simple settings placeholder
                    pass
                elif start_rect.collidepoint(event.pos):
                    door_transition(screen); flush_events(); return ("new", None)
                elif cont_rect and cont_rect.collidepoint(event.pos):
                    data = load_save()
                    if data:
                        door_transition(screen); flush_events(); return ("continue", data)
                elif exit_rect.collidepoint(event.pos):
                    pygame.quit(); sys.exit()
                elif how_rect.collidepoint(event.pos):
                    # basic help
                    flush_events()
        clock.tick(60)

def show_pause_menu(screen, background_surf):
    dim = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA); dim.fill((0, 0, 0, 170))
    bg_scaled = pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H))
    screen.blit(bg_scaled, (0, 0)); screen.blit(dim, (0, 0))

    panel_w, panel_h = min(520, VIEW_W - 80), min(500, VIEW_H - 160)
    panel = pygame.Rect(0, 0, panel_w, panel_h); panel.center = (VIEW_W // 2, VIEW_H // 2)
    pygame.draw.rect(screen, (30, 30, 30), panel, border_radius=16)
    pygame.draw.rect(screen, (60, 60, 60), panel, width=3, border_radius=16)

    title = pygame.font.SysFont(None, 72).render("Paused", True, (230, 230, 230)); screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 58)))

    btn_w, btn_h = 300, 56; spacing = 14; start_y = panel.top + 110
    btns = []
    labels = [("CONTINUE", "continue"), ("RESTART", "restart"), ("SETTINGS", "settings"), ("BACK TO HOMEPAGE", "home"), ("EXIT GAME (Save & Quit)", "exit")]
    for i, (label, tag) in enumerate(labels):
        x = panel.centerx - btn_w // 2; y = start_y + i * (btn_h + spacing)
        rect = pygame.Rect(x, y, btn_w, btn_h)
        pygame.draw.rect(screen, (15, 15, 15), rect.inflate(6, 6), border_radius=10)
        pygame.draw.rect(screen, (120, 40, 40) if tag == "exit" else (50, 50, 50), rect, border_radius=10)
        txt = pygame.font.SysFont(None, 32).render(label, True, (235, 235, 235)); screen.blit(txt, txt.get_rect(center=rect.center))
        btns.append((rect, tag))
    pygame.display.flip()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: flush_events(); return "continue"
            if event.type == pygame.MOUSEBUTTONDOWN:
                for rect, tag in btns:
                    if rect.collidepoint(event.pos): flush_events(); return tag

# ==================== 数据结构 ====================
class Obstacle:
    def __init__(self, x: int, y: int, obstacle_type: str, health: Optional[int] = None):
        px = x * CELL_SIZE; py = y * CELL_SIZE + INFO_BAR_HEIGHT
        self.rect = pygame.Rect(px, py, CELL_SIZE, CELL_SIZE)
        self.type: str = obstacle_type
        self.health: Optional[int] = health
        self.is_main_block = False

    def is_destroyed(self) -> bool:
        return self.type == "Destructible" and (self.health or 0) <= 0

    @property
    def grid_pos(self):
        return self.rect.x // CELL_SIZE, (self.rect.y - INFO_BAR_HEIGHT) // CELL_SIZE

class MainBlock(Obstacle):
    def __init__(self, x: int, y: int, health: Optional[int] = MAIN_BLOCK_HEALTH):
        super().__init__(x, y, "Destructible", health)
        self.is_main_block = True

class Item:
    def __init__(self, x: int, y: int, is_main=False):
        self.x = x; self.y = y; self.is_main = is_main
        self.radius = CELL_SIZE // 3
        self.center = (self.x * CELL_SIZE + CELL_SIZE // 2, self.y * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT)
        self.rect = pygame.Rect(self.center[0] - self.radius, self.center[1] - self.radius, self.radius * 2, self.radius * 2)

class Player:
    def __init__(self, pos: Tuple[int, int], speed: int = PLAYER_SPEED):
        self.x = pos[0] * CELL_SIZE; self.y = pos[1] * CELL_SIZE
        self.speed = speed; self.size = CELL_SIZE - 6
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)
        # Combat timers & health
        self.fire_cd = 0.0
        self.max_hp = PLAYER_MAX_HP
        self.hp = self.max_hp
        self.damage_cd = 0.0

    @property
    def pos(self):
        return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)

    def move(self, keys, obstacles: Dict[Tuple[int,int], Obstacle]):
        dx = dy = 0
        if keys[pygame.K_w]: dy -= 1
        if keys[pygame.K_s]: dy += 1
        if keys[pygame.K_a]: dx -= 1
        if keys[pygame.K_d]: dx += 1
        if dx and dy: dx *= 0.7071; dy *= 0.7071
        nx = self.x + dx * self.speed
        rect_x = pygame.Rect(int(nx), int(self.y) + INFO_BAR_HEIGHT, self.size, self.size)
        for ob in obstacles.values():
            if rect_x.colliderect(ob.rect):
                if dx > 0: nx = ob.rect.left - self.size
                elif dx < 0: nx = ob.rect.right
                break
        self.x = max(0, min(nx, GRID_SIZE * CELL_SIZE - self.size))
        ny = self.y + dy * self.speed
        rect_y = pygame.Rect(int(self.x), int(ny) + INFO_BAR_HEIGHT, self.size, self.size)
        for ob in obstacles.values():
            if rect_y.colliderect(ob.rect):
                if dy > 0: ny = ob.rect.top - self.size - INFO_BAR_HEIGHT
                elif dy < 0: ny = ob.rect.bottom - INFO_BAR_HEIGHT
                break
        self.y = max(0, min(ny, GRID_SIZE * CELL_SIZE - self.size))
        self.rect.x = int(self.x); self.rect.y = int(self.y) + INFO_BAR_HEIGHT

    def draw(self, screen):
        pygame.draw.rect(screen, (0, 255, 0), self.rect)

class Zombie:
    def __init__(self, pos: Tuple[int, int], attack: int = ZOMBIE_ATTACK, speed: int = ZOMBIE_SPEED, ztype: str = "basic", hp: Optional[int] = None):
        self.x = pos[0] * CELL_SIZE; self.y = pos[1] * CELL_SIZE
        self.attack = attack; self.speed = speed; self.type = ztype
        base_hp = 30 if hp is None else hp
        if ztype == "fast":
            self.speed = max(int(self.speed + 1), int(self.speed * 1.5)); base_hp = int(base_hp * 0.7)
        if ztype == "tank":
            self.attack = int(self.attack * 0.6); base_hp = int(base_hp * 1.8)
        self.hp = max(1, base_hp); self.max_hp = self.hp
        self.size = CELL_SIZE - 6
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)
        self.spawn_delay = 0.6; self._spawn_elapsed = 0.0
        self.attack_timer = 0.0

    @property
    def pos(self):
        return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)

    def move_and_attack(self, player, obstacles_list, game_state, attack_interval=0.5, dt=1/60):
        self.attack_timer += dt
        if self._spawn_elapsed < self.spawn_delay:
            self._spawn_elapsed += dt; return
        dx = player.x - self.x; dy = player.y - self.y
        dirs = []
        if abs(dx) > abs(dy):
            dirs = [(sign(dx), 0), (0, sign(dy)), (sign(dx), sign(dy)), (-sign(dx), 0), (0, -sign(dy))]
        else:
            dirs = [(0, sign(dy)), (sign(dx), 0), (sign(dx), sign(dy)), (0, -sign(dy)), (-sign(dx), 0)]
        for ddx, ddy in dirs:
            if ddx == 0 and ddy == 0: continue
            next_rect = self.rect.move(ddx * self.speed, ddy * self.speed)
            blocked = False
            for ob in obstacles_list:
                if next_rect.colliderect(ob.rect):
                    if ob.type == "Destructible":
                        if self.attack_timer >= attack_interval:
                            ob.health = (ob.health or 0) - self.attack; self.attack_timer = 0
                            if ob.health <= 0:
                                gp = ob.grid_pos
                                if gp in game_state.obstacles: del game_state.obstacles[gp]
                        blocked = True; break
                    elif ob.type == "Indestructible":
                        blocked = True; break
            if not blocked:
                self.x += ddx * self.speed; self.y += ddy * self.speed
                self.rect.x = int(self.x); self.rect.y = int(self.y) + INFO_BAR_HEIGHT
                break

class Bullet:
    def __init__(self, x: float, y: float, vx: float, vy: float, max_dist: float = MAX_FIRE_RANGE):
        self.x = x; self.y = y; self.vx = vx; self.vy = vy
        self.alive = True; self.traveled = 0.0; self.max_dist = max_dist

    def update(self, dt: float, game_state: 'GameState', zombies: List['Zombie']):
        if not self.alive: return
        nx = self.x + self.vx * dt; ny = self.y + self.vy * dt
        self.traveled += ((nx - self.x)**2 + (ny - self.y)**2) ** 0.5
        self.x, self.y = nx, ny
        if self.traveled >= self.max_dist: self.alive = False; return
        r = pygame.Rect(int(self.x - BULLET_RADIUS), int(self.y - BULLET_RADIUS), BULLET_RADIUS*2, BULLET_RADIUS*2)
        for z in list(zombies):
            if r.colliderect(z.rect):
                z.hp -= BULLET_DAMAGE_ZOMBIE
                if z.hp <= 0: zombies.remove(z)
                self.alive = False; return
        for gp, ob in list(game_state.obstacles.items()):
            if r.colliderect(ob.rect):
                if getattr(ob, 'is_main_block', False) or ob.type == "Indestructible":
                    self.alive = False; return
                if ob.type == "Destructible":
                    ob.health = (ob.health or 0) - BULLET_DAMAGE_BLOCK
                    if ob.health <= 0: del game_state.obstacles[gp]
                self.alive = False; return

    def draw(self, screen, cam_x, cam_y):
        pygame.draw.circle(screen, (255, 255, 255), (int(self.x - cam_x), int(self.y - cam_y)), BULLET_RADIUS)

# ==================== 算法函数 ====================
def sign(v): return 1 if v > 0 else (-1 if v < 0 else 0)

def is_not_edge(pos, grid_size):
    x, y = pos; return 1 <= x < grid_size - 1 and 1 <= y < grid_size - 1

def get_level_config(level: int) -> dict:
    if level < len(LEVELS): return LEVELS[level]
    return {"obstacle_count": 20 + level, "item_count": 5, "zombie_count": min(5, 1 + level // 3), "block_hp": int(10 * 1.2 ** (level - len(LEVELS) + 1)), "zombie_types": ["basic", "strong", "fire"][level % 3:], "reward": random.choice(CARD_POOL)}

# ==================== 游戏初始化函数 ====================
def generate_game_entities(grid_size: int, obstacle_count: int, item_count: int, zombie_count: int, main_block_hp: int):
    all_positions = [(x, y) for x in range(grid_size) for y in range(grid_size)]
    center_pos = (grid_size // 2, grid_size // 2)
    player_pos = center_pos
    far_candidates = [p for p in all_positions if (abs(p[0] - center_pos[0]) + abs(p[1] - center_pos[1]) >= 6)]
    zombie_pos_list = random.sample(far_candidates, min(len(far_candidates), zombie_count))

    main_item_candidates = [p for p in all_positions if is_not_edge(p, grid_size)]
    main_item_pos = random.choice(main_item_candidates)
    obstacles = {(main_item_pos[0], main_item_pos[1]): MainBlock(main_item_pos[0], main_item_pos[1], health=main_block_hp)}

    area = grid_size * grid_size
    target_obstacles = max(obstacle_count, int(area * OBSTACLE_DENSITY))
    base_candidates = [p for p in all_positions if p not in obstacles]
    random.shuffle(base_candidates)
    for pos in base_candidates[:max(0, target_obstacles - 1)]:
        typ = "Indestructible" if random.random() < 0.5 else "Destructible"
        hp = OBSTACLE_HEALTH if typ == "Destructible" else None
        obstacles[pos] = Obstacle(pos[0], pos[1], typ, health=hp)

    item_target = max(item_count, MIN_ITEMS, grid_size // 2)
    item_candidates = [p for p in all_positions if p not in obstacles]
    random.shuffle(item_candidates)
    others = item_candidates[:max(0, item_target - 1)]
    items = [Item(p[0], p[1]) for p in others] + [Item(main_item_pos[0], main_item_pos[1], is_main=True)]

    decorations = random.sample([p for p in all_positions if p not in set(obstacles.keys()) and p not in set((i.x, i.y) for i in items)], int(area * DECOR_DENSITY))
    return obstacles, set(items), player_pos, zombie_pos_list, [main_item_pos], decorations

# ==================== 游戏状态类 ====================
class GameState:
    def __init__(self, obstacles: Dict, items: Set, main_item_pos: List[Tuple[int, int]], decorations: list):
        self.obstacles = obstacles
        self.items = items
        self.main_item_pos = main_item_pos
        self.decorations = decorations

    def collect_item(self, player_rect):
        for item in list(self.items):
            if player_rect.colliderect(item.rect):
                if item.is_main and any(getattr(ob, "is_main_block", False) for ob in self.obstacles.values()):
                    return False
                self.items.remove(item); return True
        return False

# ==================== 渲染 ====================
def render_game(screen: pygame.Surface, game_state, player: Player, zombies: List[Zombie], bullets: Optional[List['Bullet']]=None, time_left: Optional[float]=None, player_hp_ratio: Optional[float]=None) -> pygame.Surface:
    world_w = GRID_SIZE * CELL_SIZE; world_h = GRID_SIZE * CELL_SIZE + INFO_BAR_HEIGHT
    cam_x = int(player.x + player.size // 2 - VIEW_W // 2); cam_y = int(player.y + player.size // 2 - (VIEW_H - INFO_BAR_HEIGHT) // 2)
    cam_x = max(0, min(cam_x, max(0, world_w - VIEW_W))); cam_y = max(0, min(cam_y, max(0, world_h - VIEW_H)))

    screen.fill((20, 20, 20))
    pygame.draw.rect(screen, (0, 0, 0), (0, 0, VIEW_W, INFO_BAR_HEIGHT))
    font = pygame.font.SysFont(None, 28)
    item_txt = font.render(f"ITEMS: {len(game_state.items)}", True, (255, 255, 80)); screen.blit(item_txt, (12, 12))
    gear_rect = draw_settings_gear(screen, VIEW_W - 44, 8)
    if time_left is not None:
        t = max(0, int(math.ceil(time_left))); timer_txt = font.render(f"TIME: {t}s", True, (200, 220, 255)); screen.blit(timer_txt, (VIEW_W - 170, 12))
    ratio = player_hp_ratio if player_hp_ratio is not None else (float(getattr(player, 'hp', PLAYER_MAX_HP)) / float(getattr(player, 'max_hp', PLAYER_MAX_HP)))
    bar_w, bar_h = 160, 12; bx, by = 140, 14
    pygame.draw.rect(screen, (40, 40, 40), (bx, by, bar_w, bar_h)); pygame.draw.rect(screen, (40, 180, 80), (bx, by, int(bar_w * max(0.0, min(1.0, ratio))), bar_h))

    start_x = max(0, cam_x // CELL_SIZE); end_x = min(GRID_SIZE, (cam_x + VIEW_W) // CELL_SIZE + 2)
    start_y = max(0, (cam_y - INFO_BAR_HEIGHT) // CELL_SIZE); end_y = min(GRID_SIZE, ((cam_y - INFO_BAR_HEIGHT) + (VIEW_H - INFO_BAR_HEIGHT)) // CELL_SIZE + 2)
    for y in range(start_y, end_y):
        for x in range(start_x, end_x):
            rect = pygame.Rect(x * CELL_SIZE - cam_x, y * CELL_SIZE + INFO_BAR_HEIGHT - cam_y, CELL_SIZE, CELL_SIZE)
            pygame.draw.rect(screen, (50, 50, 50), rect, 1)

    for gx, gy in getattr(game_state, 'decorations', []):
        cx = gx * CELL_SIZE + CELL_SIZE // 2 - cam_x; cy = gy * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT - cam_y
        pygame.draw.circle(screen, (70, 80, 70), (cx, cy), max(2, CELL_SIZE // 8))

    for item in game_state.items:
        draw_pos = (item.center[0] - cam_x, item.center[1] - cam_y)
        color = (255, 255, 100) if item.is_main else (255, 255, 0)
        pygame.draw.circle(screen, color, draw_pos, item.radius)

    player_draw = player.rect.copy(); player_draw.x -= cam_x; player_draw.y -= cam_y
    pygame.draw.rect(screen, (0, 255, 0), player_draw)

    for zombie in zombies:
        zr = zombie.rect.copy(); zr.x -= cam_x; zr.y -= cam_y
        pygame.draw.rect(screen, (255, 60, 60), zr)
        mhp = getattr(zombie, 'max_hp', None) or getattr(zombie, 'hp', 1)
        ratio_z = max(0.0, min(1.0, float(zombie.hp) / float(mhp)))
        bar_wz = zr.width; bar_hz = 4; bxz, byz = zr.x, zr.y - (bar_hz + 3)
        pygame.draw.rect(screen, (40, 40, 40), (bxz, byz, bar_wz, bar_hz))
        pygame.draw.rect(screen, (0, 220, 80), (bxz, byz, int(bar_wz * ratio_z), bar_hz))

    if bullets:
        for b in bullets:
            b.draw(screen, cam_x, cam_y)

    for obstacle in game_state.obstacles.values():
        is_main = getattr(obstacle, 'is_main_block', False)
        color = (255, 220, 80) if is_main else ((120, 120, 120) if obstacle.type == "Indestructible" else (200, 80, 80))
        draw_rect = obstacle.rect.copy(); draw_rect.x -= cam_x; draw_rect.y -= cam_y
        pygame.draw.rect(screen, color, draw_rect)
        if obstacle.type == "Destructible":
            font2 = pygame.font.SysFont(None, 30); health_text = font2.render(str(obstacle.health), True, (255, 255, 255))
            screen.blit(health_text, (draw_rect.x + 6, draw_rect.y + 8))
        if is_main:
            star = pygame.font.SysFont(None, 32).render("★", True, (255, 255, 120)); screen.blit(star, (draw_rect.x + 8, draw_rect.y + 8))

    pygame.display.flip()
    return screen.copy()

# ==================== 主循环 ====================
def main_run_level(config, chosen_zombie_type: str) -> Tuple[str, Optional[str], pygame.Surface]:
    pygame.display.set_caption("Zombie Card Game – Level")
    screen = pygame.display.get_surface()
    clock = pygame.time.Clock()

    obstacles, items, player_start, zombie_starts, main_item_list, decorations = generate_game_entities(
        grid_size=GRID_SIZE,
        obstacle_count=config["obstacle_count"],
        item_count=config["item_count"],
        zombie_count=config["zombie_count"],
        main_block_hp=config["block_hp"]
    )

    game_state = GameState(obstacles, items, main_item_list, decorations)
    player = Player(player_start, speed=PLAYER_SPEED)

    ztype_map = {"zombie_fast": "fast", "zombie_tank": "tank", "zombie_strong": "strong", "zombie_spitter": "spitter", "zombie_leech": "leech", "basic": "basic"}
    zt = ztype_map.get(chosen_zombie_type, "basic")
    zombies = [Zombie(pos, speed=ZOMBIE_SPEED, ztype=zt) for pos in zombie_starts]

    bullets: List[Bullet] = []
    time_left = GAME_TIMER_SECONDS

    def player_center():
        return player.x + player.size/2, player.y + player.size/2 + INFO_BAR_HEIGHT

    def find_target():
        px, py = player_center()
        best = None; best_d2 = float('inf')
        # Zombies first
        for z in zombies:
            cx, cy = z.rect.centerx, z.rect.centery
            d2 = (cx - px)**2 + (cy - py)**2
            if d2 < best_d2:
                best_d2 = d2; best = ('zombie', None, z, cx, cy)
        # Then destructible non-main blocks
        for gp, ob in game_state.obstacles.items():
            if ob.type == 'Destructible' and not getattr(ob, 'is_main_block', False):
                cx, cy = ob.rect.centerx, ob.rect.centery
                d2 = (cx - px)**2 + (cy - py)**2
                if d2 < best_d2:
                    best_d2 = d2; best = ('block', gp, ob, cx, cy)
        return best, (best_d2 ** 0.5) if best else None

    running = True; game_result = None; last_frame = None
    while running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                pause_choice = show_pause_menu(screen, last_frame or render_game(screen, game_state, player, zombies, bullets, time_left, float(player.hp)/float(player.max_hp)))
                if pause_choice == 'continue':
                    pass
                elif pause_choice == 'restart':
                    flush_events(); return 'restart', config.get('reward', None), last_frame or screen.copy()
                elif pause_choice == 'settings':
                    pass
                elif pause_choice == 'home':
                    snap = capture_snapshot(game_state, player, zombies, current_level, zombie_cards_collected, zt, bullets, time_left)
                    save_snapshot(snap); flush_events(); return 'home', config.get('reward', None), last_frame or screen.copy()
                elif pause_choice == 'exit':
                    snap = capture_snapshot(game_state, player, zombies, current_level, zombie_cards_collected, zt, bullets, time_left)
                    save_snapshot(snap); flush_events(); return 'exit', config.get('reward', None), last_frame or screen.copy()

        keys = pygame.key.get_pressed()
        player.move(keys, game_state.obstacles)
        game_state.collect_item(player.rect)

        # Timers
        time_left = max(0.0, time_left - dt)
        player.damage_cd = max(0.0, player.damage_cd - dt)
        player.fire_cd -= dt

        # Autofire
        target, dist = find_target()
        if target and player.fire_cd <= 0 and (dist is None or dist <= MAX_FIRE_RANGE):
            _, gp, ob_or_z, cx, cy = target
            px, py = player_center()
            dx, dy = cx - px, cy - py; length = (dx*dx + dy*dy) ** 0.5 or 1.0
            vx, vy = (dx/length)*BULLET_SPEED, (dy/length)*BULLET_SPEED
            bullets.append(Bullet(px, py, vx, vy, MAX_FIRE_RANGE))
            # enforce spacing cadence
            player.fire_cd += FIRE_COOLDOWN
            if player.fire_cd < 0: player.fire_cd = 0.0

        for b in list(bullets):
            b.update(dt, game_state, zombies)
            if not b.alive: bullets.remove(b)

        for zombie in list(zombies):
            zombie.move_and_attack(player, list(game_state.obstacles.values()), game_state, dt=dt)
            if zombie.rect.colliderect(player.rect):
                if player.damage_cd <= 0.0:
                    player.hp = max(0, int(player.hp) - int(getattr(zombie, 'attack', ZOMBIE_ATTACK)))
                    player.damage_cd = PLAYER_CONTACT_COOLDOWN
                if player.hp <= 0:
                    game_result = "fail"; running = False; break

        if time_left <= 0.0:
            game_result = "success"; running = False

        last_frame = render_game(pygame.display.get_surface(), game_state, player, zombies, bullets, time_left, float(player.hp)/float(player.max_hp))

    return game_result, config.get("reward", None), last_frame

def run_from_snapshot(save_data: dict) -> Tuple[str, Optional[str], pygame.Surface]:
    assert save_data.get("mode") == "snapshot"
    meta = save_data.get("meta", {}); snap = save_data.get("snapshot", {})
    # Obstacles
    obstacles: Dict[Tuple[int,int], Obstacle] = {}
    for o in snap.get("obstacles", []):
        typ = o.get("type", "Indestructible"); x, y = int(o.get("x", 0)), int(o.get("y", 0))
        if o.get("main", False): ob = MainBlock(x, y, health=o.get("health", MAIN_BLOCK_HEALTH))
        else: ob = Obstacle(x, y, typ, health=o.get("health", None))
        obstacles[(x, y)] = ob
    # Items
    items = set()
    for it in snap.get("items", []):
        items.add(Item(int(it.get("x", 0)), int(it.get("y", 0)), bool(it.get("is_main", False))))
    decorations = [tuple(d) for d in snap.get("decorations", [])]
    game_state = GameState(obstacles, items, [ (i.x, i.y) for i in items if getattr(i,'is_main', False) ], decorations)
    # Player
    p = snap.get("player", {})
    player = Player((0,0), speed=int(p.get("speed", PLAYER_SPEED)))
    player.x = float(p.get("x", 0.0)); player.y = float(p.get("y", 0.0))
    player.rect.x = int(player.x); player.rect.y = int(player.y) + INFO_BAR_HEIGHT
    player.max_hp = int(p.get("max_hp", PLAYER_MAX_HP)); player.hp = int(p.get("hp", player.max_hp))
    player.fire_cd = float(p.get("fire_cd", 0.0)); player.damage_cd = float(p.get("damage_cd", 0.0))
    # Zombies
    zombies: List[Zombie] = []
    for z in snap.get("zombies", []):
        zobj = Zombie((0,0), attack=int(z.get("attack", ZOMBIE_ATTACK)), speed=int(z.get("speed", ZOMBIE_SPEED)), ztype=z.get("type","basic"), hp=int(z.get("hp", 30)))
        zobj.max_hp = int(z.get("max_hp", int(z.get("hp", 30))))
        zobj.x = float(z.get("x", 0.0)); zobj.y = float(z.get("y", 0.0))
        zobj.rect.x = int(zobj.x); zobj.rect.y = int(zobj.y) + INFO_BAR_HEIGHT
        zobj._spawn_elapsed = float(z.get("spawn_elapsed", 0.0)); zobj.attack_timer = float(z.get("attack_timer", 0.0))
        zombies.append(zobj)
    # Bullets
    bullets: List[Bullet] = []
    for b in snap.get("bullets", []):
        bobj = Bullet(float(b.get("x",0.0)), float(b.get("y",0.0)), float(b.get("vx",0.0)), float(b.get("vy",0.0)), MAX_FIRE_RANGE)
        bobj.traveled = float(b.get("traveled", 0.0)); bullets.append(bobj)

    time_left = float(snap.get("time_left", GAME_TIMER_SECONDS)) if snap.get("time_left", None) is not None else GAME_TIMER_SECONDS

    screen = pygame.display.get_surface(); clock = pygame.time.Clock()
    running = True; last_frame = None; game_result = None
    chosen_zombie_type = meta.get("chosen_zombie_type", "basic")

    def player_center():
        return player.x + player.size/2, player.y + player.size/2 + INFO_BAR_HEIGHT

    def find_target():
        px, py = player_center()
        best = None; best_d2 = float('inf')
        for z in zombies:
            cx, cy = z.rect.centerx, z.rect.centery; d2 = (cx - px)**2 + (cy - py)**2
            if d2 < best_d2: best_d2 = d2; best = ('zombie', None, z, cx, cy)
        for gp, ob in game_state.obstacles.items():
            if ob.type == 'Destructible' and not getattr(ob, 'is_main_block', False):
                cx, cy = ob.rect.centerx, ob.rect.centery; d2 = (cx - px)**2 + (cy - py)**2
                if d2 < best_d2: best_d2 = d2; best = ('block', gp, ob, cx, cy)
        return best, (best_d2 ** 0.5) if best else None

    while running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                pause_choice = show_pause_menu(screen, last_frame or render_game(screen, game_state, player, zombies, bullets, time_left, float(player.hp)/float(player.max_hp)))
                if pause_choice == 'continue':
                    pass
                elif pause_choice == 'restart':
                    flush_events(); return 'restart', None, last_frame or screen.copy()
                elif pause_choice == 'settings':
                    pass
                elif pause_choice == 'home':
                    snap2 = capture_snapshot(game_state, player, zombies, current_level, zombie_cards_collected, chosen_zombie_type, bullets, time_left)
                    save_snapshot(snap2); flush_events(); return 'home', None, last_frame or screen.copy()
                elif pause_choice == 'exit':
                    snap2 = capture_snapshot(game_state, player, zombies, current_level, zombie_cards_collected, chosen_zombie_type, bullets, time_left)
                    save_snapshot(snap2); flush_events(); return 'exit', None, last_frame or screen.copy()

        keys = pygame.key.get_pressed()
        player.move(keys, game_state.obstacles)
        game_state.collect_item(player.rect)

        time_left = max(0.0, time_left - dt)
        player.damage_cd = max(0.0, player.damage_cd - dt)
        player.fire_cd -= dt

        target, dist = find_target()
        if target and player.fire_cd <= 0 and (dist is None or dist <= MAX_FIRE_RANGE):
            _, gp, ob_or_z, cx, cy = target
            px, py = player_center(); dx, dy = cx - px, cy - py; length = (dx*dx + dy*dy) ** 0.5 or 1.0
            vx, vy = (dx/length)*BULLET_SPEED, (dy/length)*BULLET_SPEED
            bullets.append(Bullet(px, py, vx, vy, MAX_FIRE_RANGE)); player.fire_cd += FIRE_COOLDOWN
            if player.fire_cd < 0: player.fire_cd = 0.0

        for b in list(bullets):
            b.update(dt, game_state, zombies)
            if not b.alive: bullets.remove(b)

        for zombie in list(zombies):
            zombie.move_and_attack(player, list(game_state.obstacles.values()), game_state, dt=dt)
            if zombie.rect.colliderect(player.rect):
                if player.damage_cd <= 0.0:
                    player.hp = max(0, int(player.hp) - int(getattr(zombie, 'attack', ZOMBIE_ATTACK)))
                    player.damage_cd = PLAYER_CONTACT_COOLDOWN
                if player.hp <= 0:
                    game_result = "fail"; running = False; break

        if time_left <= 0.0:
            game_result = "success"; running = False

        last_frame = render_game(pygame.display.get_surface(), game_state, player, zombies, bullets, time_left, float(player.hp)/float(player.max_hp))

    return game_result or "home", None, last_frame or screen.copy()

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
                    door_transition(screen); return chosen or owned_cards[0]
        clock.tick(60)

# ==================== 入口 ====================
if __name__ == "__main__":
    os.environ['SDL_VIDEO_CENTERED'] = '0'; os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
    pygame.init()
    info = pygame.display.Info()
    screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.NOFRAME)
    pygame.display.set_caption(GAME_TITLE)
    VIEW_W, VIEW_H = info.current_w, info.current_h

    flush_events()
    selection = show_start_menu(screen)
    if not selection: sys.exit()
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
        clear_save(); current_level = 0; zombie_cards_collected = []

    while True:
        if mode == "continue" and save_data and save_data.get("mode") == "snapshot":
            door_transition(screen)
            result, reward, bg = run_from_snapshot(save_data)
            save_data = None; mode = "new"
        else:
            config = get_level_config(current_level)
            chosen_zombie = select_zombie_screen(screen, zombie_cards_collected) if zombie_cards_collected else "basic"
            door_transition(screen)
            result, reward, bg = main_run_level(config, chosen_zombie)

        if result == "restart":
            flush_events(); continue
        if result == "home":
            flush_events()
            selection = show_start_menu(screen)
            if not selection: sys.exit()
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
                clear_save(); current_level = 0; zombie_cards_collected = []
            continue
        if result == "exit":
            pygame.quit(); sys.exit()
        if result == "fail":
            clear_save()
            # draw fail overlay
            dim = pygame.Surface((VIEW_W, VIEW_H)); dim.set_alpha(180); dim.fill((0, 0, 0))
            screen.blit(pygame.transform.smoothscale(bg, (VIEW_W, VIEW_H)), (0, 0)); screen.blit(dim, (0,0))
            title = pygame.font.SysFont(None, 80).render("YOU WERE CORRUPTED!", True, (255, 60, 60)); screen.blit(title, title.get_rect(center=(VIEW_W // 2, 140)))
            retry = draw_button(screen, "RETRY", (VIEW_W // 2 - 200, 300)); home = draw_button(screen, "HOME", (VIEW_W // 2 + 20, 300))
            pygame.display.flip()
            waiting = True
            while waiting:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT: pygame.quit(); sys.exit()
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        if retry.collidepoint(event.pos): waiting = False; action = "retry"
                        if home.collidepoint(event.pos): waiting = False; action = "home"
            flush_events()
            if action == "home":
                clear_save()
                selection = show_start_menu(screen)
                if not selection: sys.exit()
                mode, save_data = selection; clear_save(); current_level = 0; zombie_cards_collected = []; continue
            else:
                clear_save(); current_level = 0; continue
        if result == "success":
            pool = [c for c in CARD_POOL if c not in zombie_cards_collected]
            reward_choices = random.sample(pool, k=min(3, len(pool))) if pool else []
            # simple confirm
            dim = pygame.Surface((VIEW_W, VIEW_H)); dim.set_alpha(150); dim.fill((0, 0, 0))
            screen.blit(pygame.transform.smoothscale(bg, (VIEW_W, VIEW_H)), (0, 0)); screen.blit(dim, (0, 0))
            title = pygame.font.SysFont(None, 80).render("MEMORY RESTORED!", True, (0, 255, 120)); screen.blit(title, title.get_rect(center=(VIEW_W // 2, 100)))
            next_btn = draw_button(screen, "CONTINUE", (VIEW_W // 2 - 90, 370)); pygame.display.flip()
            waiting = True
            while waiting:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT: pygame.quit(); sys.exit()
                    if event.type == pygame.MOUSEBUTTONDOWN and next_btn.collidepoint(event.pos): waiting = False
            current_level += 1; save_progress(current_level, zombie_cards_collected)
        else:
            selection = show_start_menu(screen)
            if not selection: sys.exit()
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
                clear_save(); current_level = 0; zombie_cards_collected = []
