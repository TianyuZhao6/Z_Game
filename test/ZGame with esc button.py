import sys
import pygame
import math
import random
from queue import PriorityQueue
from typing import Dict, List, Set, Tuple, Optional

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

# Audio volumes (placeholders; no audio wired yet)
FX_VOLUME = 70  # 0-100
BGM_VOLUME = 60  # 0-100

CARD_POOL = ["zombie_fast", "zombie_strong", "zombie_tank", "zombie_spitter", "zombie_leech"]

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
        x1 = int(cx + 10 * math.cos(rad));
        y1 = int(cy + 10 * math.sin(rad))
        x2 = int(cx + 14 * math.cos(rad));
        y2 = int(cy + 14 * math.sin(rad))
        pygame.draw.line(screen, (200, 200, 200), (x1, y1), (x2, y2), 2)
    return rect


def show_start_menu(screen):
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
        # buttons
        start_rect = draw_button(screen, "START", (VIEW_W // 2 - 200, 260))
        how_rect = draw_button(screen, "HOW TO PLAY", (VIEW_W // 2 + 20, 260))
        exit_rect = draw_button(screen, "EXIT", (VIEW_W // 2 - 90, 340))
        gear_rect = draw_settings_gear(screen, VIEW_W - 44, 8)
        pygame.display.flip()

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit();
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if gear_rect.collidepoint(event.pos):
                    show_settings_popup(screen, screen.copy())
                if start_rect.collidepoint(event.pos):
                    door_transition(screen)
                    return True
                if exit_rect.collidepoint(event.pos):
                    pygame.quit();
                    sys.exit()
                if how_rect.collidepoint(event.pos):
                    show_help(screen)
        clock.tick(60)


def show_help(screen):
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 28)
    big = pygame.font.SysFont(None, 40)
    while True:
        screen.fill((18, 18, 18))
        screen.blit(big.render("How to Play", True, (240, 240, 240)), (40, 40))
        lines = [
            "WASD to move. Collect all memory fragments to win.",
            "Breakable yellow blocks block the final fragment.",
            "Zombies chase you. Touch = defeat.",
            "After each win: pick a zombie card as reward.",
            "Before the next level: choose which zombie type spawns.",
            "Transitions use the classic 'two doors' animation."
        ]
        y = 100
        for s in lines:
            screen.blit(font.render(s, True, (200, 200, 200)), (40, y));
            y += 36
        back = draw_button(screen, "BACK", (VIEW_W // 2 - 90, VIEW_H - 120))
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                # gear click detection (top-right HUD)
                hud_gear = pygame.Rect(VIEW_W - 44, 8, 32, 24)
                if hud_gear.collidepoint(event.pos):
                    bg = pygame.display.get_surface().copy()
                    # open settings first, then show pause menu (settings pre-selected feel)
                    show_settings_popup(screen, bg)
                    pause_choice = show_pause_menu(screen, bg)
                    if pause_choice == 'continue':
                        pass
                    elif pause_choice == 'restart':
                        return 'restart', config.get('reward', None), bg
                    elif pause_choice == 'settings':
                        show_settings_popup(screen, bg)
                    elif pause_choice == 'home':
                        return 'home', config.get('reward', None), bg
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                door_transition(screen);
                return
            if event.type == pygame.MOUSEBUTTONDOWN and back.collidepoint(event.pos):
                door_transition(screen);
                return
        clock.tick(60)


def show_fail_screen(screen, background_surf):
    dim = pygame.Surface((VIEW_W, VIEW_H));
    dim.set_alpha(180);
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
            if event.type == pygame.MOUSEBUTTONDOWN:
                # gear click detection (top-right HUD)
                hud_gear = pygame.Rect(VIEW_W - 44, 8, 32, 24)
                if hud_gear.collidepoint(event.pos):
                    bg = pygame.display.get_surface().copy()
                    # open settings first, then show pause menu (settings pre-selected feel)
                    show_settings_popup(screen, bg)
                    pause_choice = show_pause_menu(screen, bg)
                    if pause_choice == 'continue':
                        pass
                    elif pause_choice == 'restart':
                        return 'restart', config.get('reward', None), bg
                    elif pause_choice == 'settings':
                        show_settings_popup(screen, bg)
                    elif pause_choice == 'home':
                        return 'home', config.get('reward', None), bg
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                door_transition(screen);
                return
            if event.type == pygame.MOUSEBUTTONDOWN:
                if retry.collidepoint(event.pos): door_transition(screen); return "retry"
                if home.collidepoint(event.pos): door_transition(screen); return "home"


def show_success_screen(screen, background_surf, reward_choices):
    dim = pygame.Surface((VIEW_W, VIEW_H));
    dim.set_alpha(150);
    dim.fill((0, 0, 0))
    screen.blit(pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H)), (0, 0))
    screen.blit(dim, (0, 0))
    title = pygame.font.SysFont(None, 80).render("MEMORY RESTORED!", True, (0, 255, 120))
    screen.blit(title, title.get_rect(center=(VIEW_W // 2, 100)))
    # cards
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
            if event.type == pygame.MOUSEBUTTONDOWN:
                # gear click detection (top-right HUD)
                hud_gear = pygame.Rect(VIEW_W - 44, 8, 32, 24)
                if hud_gear.collidepoint(event.pos):
                    bg = pygame.display.get_surface().copy()
                    # open settings first, then show pause menu (settings pre-selected feel)
                    show_settings_popup(screen, bg)
                    pause_choice = show_pause_menu(screen, bg)
                    if pause_choice == 'continue':
                        pass
                    elif pause_choice == 'restart':
                        return 'restart', config.get('reward', None), bg
                    elif pause_choice == 'settings':
                        show_settings_popup(screen, bg)
                    elif pause_choice == 'home':
                        return 'home', config.get('reward', None), bg
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                door_transition(screen);
                return
            if event.type == pygame.MOUSEBUTTONDOWN:
                for rect, card in card_rects:
                    if rect.collidepoint(event.pos): chosen = card
                if next_btn.collidepoint(event.pos) and (chosen or len(reward_choices) == 0):
                    door_transition(screen);
                    return chosen


def show_pause_menu(screen, background_surf):
    dim = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 170))  # semi-transparent
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

    # Buttons stacked in panel
    btn_w, btn_h = 300, 56
    spacing = 14
    start_y = panel.top + 110
    btns = []
    labels = [("CONTINUE  (ESC)", "continue"),
              ("RESTART", "restart"),
              ("SETTINGS", "settings"),
              ("BACK TO HOMEPAGE", "home"),
              ("EXIT GAME", "exit")]
    for i, (label, tag) in enumerate(labels):
        x = panel.centerx - btn_w // 2
        y = start_y + i * (btn_h + spacing)
        rect = pygame.Rect(x, y, btn_w, btn_h)
        pygame.draw.rect(screen, (15, 15, 15), rect.inflate(6, 6), border_radius=10)
        if tag == "exit":
            pygame.draw.rect(screen, (120, 40, 40), rect, border_radius=10)  # red
        else:
            pygame.draw.rect(screen, (50, 50, 50), rect, border_radius=10)
        txt = pygame.font.SysFont(None, 32).render(label, True, (235, 235, 235))
        screen.blit(txt, txt.get_rect(center=rect.center))
        btns.append((rect, tag))

    pygame.display.flip()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit();
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return "continue"
            if event.type == pygame.MOUSEBUTTONDOWN:
                for rect, tag in btns:
                    if rect.collidepoint(event.pos):
                        return tag


def show_settings_popup(screen, background_surf):
    global FX_VOLUME, BGM_VOLUME
    dim = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 170))
    bg_scaled = pygame.transform.smoothscale(background_surf, (VIEW_W, VIEW_H))
    screen.blit(bg_scaled, (0, 0))
    screen.blit(dim, (0, 0))

    panel_w, panel_h = min(520, VIEW_W - 80), min(360, VIEW_H - 160)
    panel = pygame.Rect(0, 0, panel_w, panel_h)
    panel.center = (VIEW_W // 2, VIEW_H // 2)
    pygame.draw.rect(screen, (30, 30, 30), panel, border_radius=16)
    pygame.draw.rect(screen, (60, 60, 60), panel, width=3, border_radius=16)

    title = pygame.font.SysFont(None, 56).render("Settings", True, (230, 230, 230))
    screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 48)))
    font = pygame.font.SysFont(None, 30)

    def draw_slider(label, value, top_y):
        screen.blit(font.render(f"{label}: {value}", True, (230, 230, 230)), (panel.left + 40, top_y))
        bar = pygame.Rect(panel.left + 40, top_y + 26, panel_w - 80, 10)
        knob_x = bar.x + int((value / 100) * bar.width)
        pygame.draw.rect(screen, (80, 80, 80), bar, border_radius=6)
        pygame.draw.circle(screen, (220, 220, 220), (knob_x, bar.y + 5), 8)
        return bar

    fx_val = FX_VOLUME
    bgm_val = BGM_VOLUME

    fx_bar = draw_slider("Effects Volume", fx_val, panel.top + 110)
    bgm_bar = draw_slider("BGM Volume", bgm_val, panel.top + 160)

    # Close button
    btn_w, btn_h = 200, 56
    close = pygame.Rect(0, 0, btn_w, btn_h)
    close.center = (panel.centerx, panel.bottom - 50)
    pygame.draw.rect(screen, (15, 15, 15), close.inflate(6, 6), border_radius=10)
    pygame.draw.rect(screen, (50, 50, 50), close, border_radius=10)
    ctxt = pygame.font.SysFont(None, 32).render("CLOSE", True, (235, 235, 235))
    screen.blit(ctxt, ctxt.get_rect(center=close.center))

    pygame.display.flip()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return "close"
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                for which, bar in (('fx', fx_bar), ('bgm', bgm_bar)):
                    if bar.collidepoint((mx, my)):
                        val = int(((mx - bar.x) / bar.width) * 100);
                        val = max(0, min(100, val))
                        if which == 'fx': fx_val = val
                        if which == 'bgm': bgm_val = val
                if close.collidepoint((mx, my)):
                    FX_VOLUME = fx_val
                    BGM_VOLUME = bgm_val
                    return "close"


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
        self.x = x;
        self.y = y;
        self.is_main = is_main
        self.radius = CELL_SIZE // 3
        self.center = (self.x * CELL_SIZE + CELL_SIZE // 2, self.y * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT)
        self.rect = pygame.Rect(self.center[0] - self.radius, self.center[1] - self.radius, self.radius * 2,
                                self.radius * 2)


class Player:
    def __init__(self, pos: Tuple[int, int], speed: int = PLAYER_SPEED):
        self.x = pos[0] * CELL_SIZE;
        self.y = pos[1] * CELL_SIZE
        self.speed = speed;
        self.size = CELL_SIZE - 6
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)

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
        self.rect.x = int(self.x);
        self.rect.y = int(self.y) + INFO_BAR_HEIGHT

    def draw(self, screen):
        pygame.draw.rect(screen, (0, 255, 0), self.rect)


class Zombie:
    def __init__(self, pos: Tuple[int, int], attack: int = ZOMBIE_ATTACK, speed: int = ZOMBIE_SPEED,
                 ztype: str = "basic"):
        self.x = pos[0] * CELL_SIZE;
        self.y = pos[1] * CELL_SIZE
        self.attack = attack;
        self.speed = speed;
        self.type = ztype
        if ztype == "fast": self.speed = max(self.speed + 1, self.speed * 1.5)
        if ztype == "tank": self.attack = int(self.attack * 0.5)
        self.size = CELL_SIZE - 6
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)
        self.spawn_delay = 0.6
        self._spawn_elapsed = 0.0

    @property
    def pos(self):
        return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)

    def move_and_attack(self, player, obstacles, game_state, attack_interval=0.5, dt=1 / 60):
        if not hasattr(self, 'attack_timer'): self.attack_timer = 0
        self.attack_timer += dt
        # initial spawn delay
        if self._spawn_elapsed < self.spawn_delay:
            self._spawn_elapsed += dt
            return
        dx = player.x - self.x;
        dy = player.y - self.y;
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
                            ob.health -= self.attack;
                            self.attack_timer = 0
                            if ob.health <= 0:
                                gp = ob.grid_pos
                                if gp in game_state.obstacles: del game_state.obstacles[gp]
                        blocked = True;
                        break
                    elif ob.type == "Indestructible":
                        blocked = True;
                        break
            if not blocked:
                self.x += ddx * speed;
                self.y += ddy * speed
                self.rect.x = int(self.x);
                self.rect.y = int(self.y) + INFO_BAR_HEIGHT
                break

    def draw(self, screen):
        pygame.draw.rect(screen, (255, 60, 60), self.rect)


# ==================== 算法函数 ====================
def sign(v): return 1 if v > 0 else (-1 if v < 0 else 0)


def heuristic(a, b): return abs(a[0] - b[0]) + abs(a[1] - b[1])


def a_star_search(graph: Graph, start: Tuple[int, int], goal: Tuple[int, int],
                  obstacles: Dict[Tuple[int, int], Obstacle]):
    frontier = PriorityQueue();
    frontier.put((0, start))
    came_from = {start: None};
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
                came_from[current] = current if current not in came_from else came_from[current]
                came_from[neighbor] = current
    return came_from, cost_so_far


def is_not_edge(pos, grid_size):
    x, y = pos;
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
    path = [];
    current = goal
    while current != start:
        path.append(current);
        current = came_from[current]
    path.append(start);
    path.reverse();
    return path


# ==================== 游戏初始化函数 ====================

def generate_game_entities(grid_size: int, obstacle_count: int, item_count: int, zombie_count: int, main_block_hp: int):
    """
    Generate entities with map-fill: obstacle clusters, ample items, and non-blocking decorations.
    NOTE: keeps logic readable for future tweaks.
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
    forbidden |= {player_pos};
    forbidden |= set(zombie_pos_list)

    # main item + main block
    main_item_candidates = [p for p in all_positions if p not in forbidden and is_not_edge(p, grid_size)]
    main_item_pos = random.choice(main_item_candidates);
    forbidden.add(main_item_pos)
    obstacles = {main_item_pos: MainBlock(main_item_pos[0], main_item_pos[1], health=main_block_hp)}

    # --- obstacle fill with clusters ---
    area = grid_size * grid_size
    target_obstacles = max(obstacle_count, int(area * OBSTACLE_DENSITY))
    rest_needed = max(0, target_obstacles - 1)  # minus main block
    # seed positions away from forbidden
    base_candidates = [p for p in all_positions if p not in forbidden and p not in obstacles]
    cluster_seeds = random.sample(base_candidates, k=max(1, rest_needed // 6))
    placed = 0
    # fill clusters around seeds to avoid empty feel
    for seed in cluster_seeds:
        if placed >= rest_needed: break
        # small cluster size 3-6
        cluster_size = random.randint(3, 6)
        wave = [seed]
        visited = set()
        while wave and placed < rest_needed and len(visited) < cluster_size:
            cur = wave.pop()
            if cur in visited or cur in forbidden or cur in obstacles:
                continue
            visited.add(cur)
            # type assignment
            if random.random() < 0.65:
                obstacles[cur] = Obstacle(cur[0], cur[1], "Indestructible")
            else:
                obstacles[cur] = Obstacle(cur[0], cur[1], "Destructible", health=OBSTACLE_HEALTH)
            placed += 1
            # neighbors (4-dir)
            nx, ny = cur
            neigh = [(nx + 1, ny), (nx - 1, ny), (nx, ny + 1), (nx, ny - 1)]
            random.shuffle(neigh)
            for nb in neigh:
                if 0 <= nb[0] < grid_size and 0 <= nb[1] < grid_size and nb not in visited:
                    wave.append(nb)

    # if still short, place random scattered obstacles
    if placed < rest_needed:
        rest_candidates = [p for p in base_candidates if p not in obstacles]
        random.shuffle(rest_candidates)
        for pos in rest_candidates[:(rest_needed - placed)]:
            typ = "Indestructible" if random.random() < 0.5 else "Destructible"
            hp = OBSTACLE_HEALTH if typ == "Destructible" else None
            obstacles[pos] = Obstacle(pos[0], pos[1], typ, health=hp)

    forbidden |= set(obstacles.keys())

    # --- items: ensure minimum count on large maps ---
    item_target = max(item_count, MIN_ITEMS, grid_size // 2)
    item_candidates = [p for p in all_positions if p not in forbidden]
    other_items = random.sample(item_candidates, max(0, item_target - 1))
    items = [Item(pos[0], pos[1]) for pos in other_items]
    items.append(Item(main_item_pos[0], main_item_pos[1], is_main=True))

    # --- decorations (non-colliding) ---
    decor_target = int(area * DECOR_DENSITY)
    decor_candidates = [p for p in all_positions if p not in forbidden and p not in set((i.x, i.y) for i in items)]
    random.shuffle(decor_candidates)
    decorations = decor_candidates[:decor_target]

    return obstacles, items, player_pos, zombie_pos_list, [main_item_pos], decorations


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
        # non-colliding visual fillers
        self.decorations = decorations  # list[Tuple[int,int]] grid coords

    def count_destructible_obstacles(self) -> int:
        return sum(1 for obs in self.obstacles.values() if obs.type == "Destructible")

    def collect_item(self, player_rect):
        for item in list(self.items):
            if player_rect.colliderect(item.rect):
                if item.is_main and any(getattr(ob, "is_main_block", False) for ob in self.obstacles.values()):
                    return False
                self.items.remove(item);
                return True
        return False

    def destroy_obstacle(self, pos: Tuple[int, int]):
        if pos in self.obstacles:
            if self.obstacles[pos].type == "Destructible": self.destructible_count -= 1
            del self.obstacles[pos]


# ==================== 游戏渲染函数 ====================
def render_game(screen: pygame.Surface, game_state, player: Player, zombies: List[Zombie]) -> pygame.Surface:
    # Camera centers on player
    world_w = GRID_SIZE * CELL_SIZE
    world_h = GRID_SIZE * CELL_SIZE + INFO_BAR_HEIGHT
    cam_x = int(player.x + player.size // 2 - VIEW_W // 2)
    cam_y = int(player.y + player.size // 2 - (VIEW_H - INFO_BAR_HEIGHT) // 2)
    cam_x = max(0, min(cam_x, max(0, world_w - VIEW_W)))
    cam_y = max(0, min(cam_y, max(0, world_h - VIEW_H)))

    screen.fill((20, 20, 20))
    pygame.draw.rect(screen, (0, 0, 0), (0, 0, VIEW_W, INFO_BAR_HEIGHT))
    font = pygame.font.SysFont(None, 28)
    item_txt = font.render(f"ITEMS: {len(game_state.items)}", True, (255, 255, 80))
    screen.blit(item_txt, (12, 12))
    # settings icon (HUD)
    gear_rect = draw_settings_gear(screen, VIEW_W - 44, 8)

    # grid in view
    start_x = max(0, cam_x // CELL_SIZE)
    end_x = min(GRID_SIZE, (cam_x + VIEW_W) // CELL_SIZE + 2)
    start_y = max(0, (cam_y - INFO_BAR_HEIGHT) // CELL_SIZE)
    end_y = min(GRID_SIZE, ((cam_y - INFO_BAR_HEIGHT) + (VIEW_H - INFO_BAR_HEIGHT)) // CELL_SIZE + 2)
    for y in range(start_y, end_y):
        for x in range(start_x, end_x):
            rect = pygame.Rect(x * CELL_SIZE - cam_x, y * CELL_SIZE + INFO_BAR_HEIGHT - cam_y, CELL_SIZE, CELL_SIZE)
            pygame.draw.rect(screen, (50, 50, 50), rect, 1)

    # decorations (non-colliding visual fillers)
    for gx, gy in getattr(game_state, 'decorations', []):
        # draw small rubble/grass
        cx = gx * CELL_SIZE + CELL_SIZE // 2 - cam_x
        cy = gy * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT - cam_y
        pygame.draw.circle(screen, (70, 80, 70), (cx, cy), max(2, CELL_SIZE // 8))

    # items
    for item in game_state.items:
        draw_pos = (item.center[0] - cam_x, item.center[1] - cam_y)
        color = (255, 255, 100) if item.is_main else (255, 255, 0)
        pygame.draw.circle(screen, color, draw_pos, item.radius)

    # player
    player_draw = player.rect.copy();
    player_draw.x -= cam_x;
    player_draw.y -= cam_y
    pygame.draw.rect(screen, (0, 255, 0), player_draw)

    # zombies
    for zombie in zombies:
        zr = zombie.rect.copy();
        zr.x -= cam_x;
        zr.y -= cam_y
        pygame.draw.rect(screen, (255, 60, 60), zr)

    # obstacles
    for obstacle in game_state.obstacles.values():
        is_main = hasattr(obstacle, 'is_main_block') and obstacle.is_main_block
        if is_main:
            color = (255, 220, 80)
        elif obstacle.type == "Indestructible":
            color = (120, 120, 120)
        else:
            color = (200, 80, 80)
        draw_rect = obstacle.rect.copy();
        draw_rect.x -= cam_x;
        draw_rect.y -= cam_y
        pygame.draw.rect(screen, color, draw_rect)
        if obstacle.type == "Destructible":
            font2 = pygame.font.SysFont(None, 30)
            health_text = font2.render(str(obstacle.health), True, (255, 255, 255))
            screen.blit(health_text, (draw_rect.x + 6, draw_rect.y + 8))
        if is_main:
            star = pygame.font.SysFont(None, 32).render("★", True, (255, 255, 120))
            screen.blit(star, (draw_rect.x + 8, draw_rect.y + 8))

    pygame.display.flip()
    return screen.copy()


# ==================== 游戏主循环 ====================
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

    ztype_map = {
        "zombie_fast": "fast",
        "zombie_tank": "tank",
        "zombie_strong": "strong",
        "zombie_spitter": "spitter",
        "zombie_leech": "leech",
        "basic": "basic"
    }
    zt = ztype_map.get(chosen_zombie_type, "basic")
    zombies = [Zombie(pos, speed=ZOMBIE_SPEED, ztype=zt) for pos in zombie_starts]

    running = True;
    game_result = None;
    last_frame = None
    while running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                # gear click detection (top-right HUD)
                hud_gear = pygame.Rect(VIEW_W - 44, 8, 32, 24)
                if hud_gear.collidepoint(event.pos):
                    bg = pygame.display.get_surface().copy()
                    # open settings first, then show pause menu (settings pre-selected feel)
                    show_settings_popup(screen, bg)
                    pause_choice = show_pause_menu(screen, bg)
                    if pause_choice == 'continue':
                        pass
                    elif pause_choice == 'restart':
                        return 'restart', config.get('reward', None), bg
                    elif pause_choice == 'settings':
                        show_settings_popup(screen, bg)
                    elif pause_choice == 'home':
                        return 'home', config.get('reward', None), bg
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                pause_choice = show_pause_menu(screen, last_frame or render_game(screen, game_state, player, zombies))
                if pause_choice == 'continue':
                    pass
                elif pause_choice == 'restart':
                    return 'restart', config.get('reward', None), last_frame or screen.copy()
                elif pause_choice == 'settings':
                    show_settings_popup(screen, last_frame or render_game(screen, game_state, player, zombies))
                elif pause_choice == 'home':
                    return 'home', config.get('reward', None), last_frame or screen.copy()
        keys = pygame.key.get_pressed()
        player.move(keys, game_state.obstacles)
        game_state.collect_item(player.rect)
        for zombie in zombies:
            zombie.move_and_attack(player, list(game_state.obstacles.values()), game_state, dt=dt)
            player_rect = pygame.Rect(int(player.x), int(player.y) + INFO_BAR_HEIGHT, player.size, player.size)
            if zombie.rect.colliderect(player_rect):
                game_result = "fail";
                running = False;
                break
        if not game_state.items:
            game_result = "success";
            running = False
        last_frame = render_game(pygame.display.get_surface(), game_state, player, zombies)
    return game_result, config.get("reward", None), last_frame


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
                    door_transition(screen);
                    return chosen or owned_cards[0]
        clock.tick(60)


# ==================== 入口 ====================
if __name__ == "__main__":
    import os

    os.environ['SDL_VIDEO_CENTERED'] = '0'
    os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
    pygame.init()
    info = pygame.display.Info()
    # Borderless fullscreen to avoid display mode flicker
    screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.NOFRAME)
    pygame.display.set_caption(GAME_TITLE)
    VIEW_W, VIEW_H = info.current_w, info.current_h

    # Start menu
    if not show_start_menu(screen): sys.exit()

    current_level = 0
    zombie_cards_collected: List[str] = []

    while True:
        config = get_level_config(current_level)
        chosen_zombie = select_zombie_screen(screen, zombie_cards_collected) if zombie_cards_collected else "basic"
        door_transition(screen)
        result, reward, bg = main_run_level(config, chosen_zombie)
        if result == "restart":
            continue
        if result == "home":
            show_start_menu(screen);
            continue
        if result == "fail":
            action = show_fail_screen(screen, bg)
            if action == "home":
                show_start_menu(screen);
                continue
            else:
                continue
        elif result == "success":
            pool = [c for c in CARD_POOL if c not in zombie_cards_collected]
            reward_choices = random.sample(pool, k=min(3, len(pool))) if pool else []
            chosen = show_success_screen(screen, bg, reward_choices)
            if chosen:
                zombie_cards_collected.append(chosen)
            current_level += 1
        else:
            show_start_menu(screen)

# TODO
# I just figure out the main purpose of this game!
# The item collection system can be hugely impact this game to next level
# Player and Zombie both can collect item to upgrade, after kill zombie, player can get the experience to upgrade, and
# I set a timer each game for winning condition, as long as player still alive, after the time is running out
# player won, vice versa. And after each combat, shop( roguelike feature) will apear for player to trade with item
# using the item they collect in the combat
