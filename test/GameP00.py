
import sys
import pygame
import math
import random
from queue import PriorityQueue
from typing import Dict, List, Set, Tuple, Optional

# ==================== 游戏常量配置 ====================
GAME_TITLE = "Neuroscape: Mind Runner"
INFO_BAR_HEIGHT = 40
GRID_SIZE = 18
CELL_SIZE = 40
WINDOW_SIZE = GRID_SIZE * CELL_SIZE
TOTAL_HEIGHT = WINDOW_SIZE + INFO_BAR_HEIGHT
OBSTACLES = 25
OBSTACLE_HEALTH = 20
MAIN_BLOCK_HEALTH = 40
DESTRUCTIBLE_RATIO = 0.3
PLAYER_SPEED = 5
ZOMBIE_SPEED = 2
ZOMBIE_ATTACK = 10
ZOMBIE_NUM = 2
ITEMS = 10

CARD_POOL = ["zombie_fast", "zombie_strong", "zombie_tank", "zombie_spitter", "zombie_leech"]

LEVELS = [
    {"obstacle_count": 15, "item_count": 3, "zombie_count": 1, "block_hp": 10, "zombie_types": ["basic"], "reward": "zombie_fast"},
    {"obstacle_count": 18, "item_count": 4, "zombie_count": 2, "block_hp": 15, "zombie_types": ["basic", "strong"], "reward": "zombie_strong"},
]

# 方向向量
DIRECTIONS = {
    pygame.K_a: (-1, 0),
    pygame.K_d: (1, 0),
    pygame.K_w: (0, -1),
    pygame.K_s: (0, 1),
}

# ==================== UI Helpers ====================
def draw_button(screen, label, pos, size=(180, 56), bg=(40,40,40), fg=(240,240,240), border=(15,15,15)):
    rect = pygame.Rect(pos, size)
    pygame.draw.rect(screen, border, rect.inflate(6,6))
    pygame.draw.rect(screen, bg, rect)
    font = pygame.font.SysFont(None, 32)
    txt = font.render(label, True, fg)
    screen.blit(txt, txt.get_rect(center=rect.center))
    return rect

def door_transition(screen, color=(0,0,0), duration=500):
    door_width = WINDOW_SIZE // 2
    left_rect = pygame.Rect(0, 0, 0, TOTAL_HEIGHT)
    right_rect = pygame.Rect(WINDOW_SIZE, 0, 0, TOTAL_HEIGHT)
    clock = pygame.time.Clock()
    start_time = pygame.time.get_ticks()
    while True:
        elapsed = pygame.time.get_ticks() - start_time
        progress = min(1, elapsed / duration)
        lw = int(door_width * progress)
        rw = int(door_width * progress)
        left_rect.width = lw
        right_rect.x = WINDOW_SIZE - rw
        right_rect.width = rw
        screen.fill((0,0,0))
        pygame.draw.rect(screen, color, left_rect)
        pygame.draw.rect(screen, color, right_rect)
        pygame.display.flip()
        if progress >= 1: break
        clock.tick(60)

def show_start_menu(screen):
    clock = pygame.time.Clock()
    # simple animated fog background
    t = 0
    title_font = pygame.font.SysFont(None, 64)
    subtitle_font = pygame.font.SysFont(None, 24)
    while True:
        t += 1
        # background
        screen.fill((26,28,24))
        for i in range(0, WINDOW_SIZE, 40):
            pygame.draw.rect(screen, (32 + (i//40%2)*6,34,30), (i, 0, 40, TOTAL_HEIGHT))
        # title
        title = title_font.render(GAME_TITLE, True, (230, 230, 210))
        screen.blit(title, title.get_rect(center=(WINDOW_SIZE//2, 140)))
        sub = subtitle_font.render("A pixel roguelite of memory and monsters", True, (160,160,150))
        screen.blit(sub, sub.get_rect(center=(WINDOW_SIZE//2, 180)))
        # buttons
        start_rect = draw_button(screen, "START", (WINDOW_SIZE//2-200, 260))
        how_rect = draw_button(screen, "HOW TO PLAY", (WINDOW_SIZE//2+20, 260))
        exit_rect = draw_button(screen, "EXIT", (WINDOW_SIZE//2-90, 340))
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if start_rect.collidepoint(event.pos):
                    door_transition(screen)
                    return True
                if exit_rect.collidepoint(event.pos):
                    pygame.quit(); sys.exit()
                if how_rect.collidepoint(event.pos):
                    show_help(screen)
        clock.tick(60)

def show_help(screen):
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 28)
    big = pygame.font.SysFont(None, 40)
    while True:
        screen.fill((18,18,18))
        screen.blit(big.render("How to Play", True, (240,240,240)), (40,40))
        lines = [
            "WASD to move. Collect all memory fragments to win.",
            "Breakable yellow blocks block the final fragment.",
            "Zombies chase you. Touch = defeat.",
            "After each win: pick a zombie card as reward.",
            "Before the next level: choose which zombie type spawns."
        ]
        y=100
        for s in lines:
            screen.blit(font.render(s, True, (200,200,200)), (40,y)); y+=36
        back = draw_button(screen, "BACK", (WINDOW_SIZE//2-90, TOTAL_HEIGHT-120))
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and back.collidepoint(event.pos):
                door_transition(screen); return
        clock.tick(60)

def show_fail_screen(screen, background_surf):
    dim = pygame.Surface((WINDOW_SIZE, TOTAL_HEIGHT)); dim.set_alpha(180); dim.fill((0,0,0))
    screen.blit(background_surf, (0,0)); screen.blit(dim, (0,0))
    title = pygame.font.SysFont(None, 80).render("YOU WERE CORRUPTED!", True, (255,60,60))
    screen.blit(title, title.get_rect(center=(WINDOW_SIZE//2, 140)))
    retry = draw_button(screen, "RETRY", (WINDOW_SIZE//2-200, 300))
    home  = draw_button(screen, "HOME", (WINDOW_SIZE//2+20, 300))
    pygame.display.flip()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if retry.collidepoint(event.pos): door_transition(screen); return "retry"
                if home.collidepoint(event.pos): door_transition(screen); return "home"

def show_success_screen(screen, background_surf, reward_choices):
    dim = pygame.Surface((WINDOW_SIZE, TOTAL_HEIGHT)); dim.set_alpha(150); dim.fill((0,0,0))
    screen.blit(background_surf, (0,0)); screen.blit(dim, (0,0))
    title = pygame.font.SysFont(None, 80).render("MEMORY RESTORED!", True, (0,255,120))
    screen.blit(title, title.get_rect(center=(WINDOW_SIZE//2, 100)))
    # cards
    card_rects = []
    for i, card in enumerate(reward_choices):
        x = WINDOW_SIZE//2 - (len(reward_choices)*140)//2 + i*140
        rect = pygame.Rect(x, 180, 120, 160)
        pygame.draw.rect(screen, (220,220,220), rect)
        name = pygame.font.SysFont(None, 24).render(card.replace("_"," ").upper(), True, (20,20,20))
        screen.blit(name, name.get_rect(center=(rect.centerx, rect.bottom-18)))
        # simple pixel face as placeholder
        pygame.draw.rect(screen, (40,40,40), rect, 3)
        pygame.draw.rect(screen, (70,90,90), rect.inflate(-30,-50))
        card_rects.append((rect, card))
    next_btn = draw_button(screen, "CONFIRM", (WINDOW_SIZE//2-90, 370))
    chosen = None
    pygame.display.flip()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                for rect, card in card_rects:
                    if rect.collidepoint(event.pos): chosen = card
                if next_btn.collidepoint(event.pos) and (chosen or len(reward_choices)==0):
                    door_transition(screen); return chosen

# ==================== 数据结构 ====================
class Graph:
    def __init__(self):
        self.edges: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        self.weights: Dict[Tuple[Tuple[int, int], Tuple[int, int]], float] = {}
    def add_edge(self, a, b, w):
        self.edges.setdefault(a, []).append(b)
        self.weights[(a,b)] = w
    def neighbors(self, node): return self.edges.get(node, [])
    def cost(self, a, b): return self.weights.get((a,b), float('inf'))

class Obstacle:
    def __init__(self, x: int, y: int, obstacle_type: str, health: Optional[int] = None):
        px = x * CELL_SIZE; py = y * CELL_SIZE + INFO_BAR_HEIGHT
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
        self.x = x; self.y = y; self.is_main = is_main
        self.radius = CELL_SIZE // 3
        self.center = (self.x*CELL_SIZE + CELL_SIZE//2, self.y*CELL_SIZE + CELL_SIZE//2 + INFO_BAR_HEIGHT)
        self.rect = pygame.Rect(self.center[0]-self.radius, self.center[1]-self.radius, self.radius*2, self.radius*2)

class Player:
    def __init__(self, pos: Tuple[int, int], speed: int = PLAYER_SPEED):
        self.x = pos[0] * CELL_SIZE; self.y = pos[1] * CELL_SIZE
        self.speed = speed; self.size = CELL_SIZE - 6
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)
    @property
    def pos(self):
        return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)
    def move(self, keys, obstacles):
        dx=dy=0
        if keys[pygame.K_w]: dy-=1
        if keys[pygame.K_s]: dy+=1
        if keys[pygame.K_a]: dx-=1
        if keys[pygame.K_d]: dx+=1
        if dx and dy: dx*=0.7071; dy*=0.7071
        nx = self.x + dx*self.speed; ny = self.y + dy*self.speed
        next_rect = pygame.Rect(int(nx), int(ny)+INFO_BAR_HEIGHT, self.size, self.size)
        can_move = True
        for ob in obstacles.values():
            if next_rect.colliderect(ob.rect): can_move=False; break
        if can_move and 0<=nx<WINDOW_SIZE-self.size and 0<=ny<WINDOW_SIZE-self.size:
            self.x=nx; self.y=ny; self.rect.x=int(self.x); self.rect.y=int(self.y)+INFO_BAR_HEIGHT
    def draw(self, screen):
        pygame.draw.rect(screen, (0, 255, 0), self.rect)

class Zombie:
    def __init__(self, pos: Tuple[int, int], attack: int = ZOMBIE_ATTACK, speed: int = ZOMBIE_SPEED, ztype: str="basic"):
        self.x = pos[0]*CELL_SIZE; self.y = pos[1]*CELL_SIZE
        self.attack=attack; self.speed=speed; self.type=ztype
        # adjust stats based on type
        if ztype=="fast": self.speed = max(self.speed+1, self.speed*1.5)
        if ztype=="tank": self.attack = int(self.attack*0.5)
        self.size=CELL_SIZE-6
        self.rect=pygame.Rect(self.x, self.y+INFO_BAR_HEIGHT, self.size, self.size)
    @property
    def pos(self): return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)
    def move_and_attack(self, player, obstacles, game_state, attack_interval=0.5, dt=1/60):
        if not hasattr(self, 'attack_timer'): self.attack_timer=0
        self.attack_timer += dt
        dx = player.x - self.x; dy = player.y - self.y; speed = self.speed
        dirs = []
        if abs(dx)>abs(dy): dirs=[(sign(dx),0),(0,sign(dy)),(sign(dx),sign(dy)),(-sign(dx),0),(0,-sign(dy))]
        else: dirs=[(0,sign(dy)),(sign(dx),0),(sign(dx),sign(dy)),(0,-sign(dy)),(-sign(dx),0)]
        for ddx, ddy in dirs:
            if ddx==0 and ddy==0: continue
            next_rect = self.rect.move(ddx*speed, ddy*speed)
            blocked=False
            for ob in obstacles:
                if next_rect.colliderect(ob.rect):
                    if ob.type=="Destructible":
                        if self.attack_timer>=attack_interval:
                            ob.health-=self.attack; self.attack_timer=0
                            if ob.health<=0:
                                gp=ob.grid_pos
                                if gp in game_state.obstacles: del game_state.obstacles[gp]
                        blocked=True; break
                    elif ob.type=="Indestructible":
                        blocked=True; break
            if not blocked:
                self.x+=ddx*speed; self.y+=ddy*speed
                self.rect.x=int(self.x); self.rect.y=int(self.y)+INFO_BAR_HEIGHT
                break
    def draw(self, screen):
        pygame.draw.rect(screen, (255, 60, 60), self.rect)

# ==================== 算法函数 ====================
def sign(v): return 1 if v>0 else (-1 if v<0 else 0)
def heuristic(a,b): return abs(a[0]-b[0]) + abs(a[1]-b[1])

def a_star_search(graph: Graph, start: Tuple[int, int], goal: Tuple[int, int], obstacles: Dict[Tuple[int, int], Obstacle]):
    frontier = PriorityQueue(); frontier.put((0, start))
    came_from = {start: None}; cost_so_far = {start: 0}
    while not frontier.empty():
        _, current = frontier.get()
        if current == goal: break
        for neighbor in graph.neighbors(current):
            new_cost = cost_so_far[current] + graph.cost(current, neighbor)
            if neighbor in obstacles:
                obstacle = obstacles[neighbor]
                if obstacle.type == "Indestructible": continue
                elif obstacle.type == "Destructible":
                    k_factor = (math.ceil(obstacle.health / ZOMBIE_ATTACK)) * 0.1
                    new_cost = cost_so_far[current] + 1 + k_factor
            if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                cost_so_far[neighbor] = new_cost
                priority = new_cost + heuristic(goal, neighbor)
                frontier.put((priority, neighbor))
                came_from[neighbor] = current
    return came_from, cost_so_far

def is_not_edge(pos, grid_size):
    x, y = pos; return 1 <= x < grid_size - 1 and 1 <= y < grid_size - 1

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
    path=[]; current=goal
    while current != start:
        path.append(current); current = came_from[current]
    path.append(start); path.reverse(); return path

# ==================== 游戏初始化函数 ====================
def generate_game_entities(grid_size: int, obstacle_count: int, item_count: int, zombie_count: int, main_block_hp: int):
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
    player_pos, zombie_pos_list = pick_valid_positions(min_distance=5, count=zombie_count)
    forbidden |= {player_pos}; forbidden |= set(zombie_pos_list)
    main_item_candidates = [p for p in all_positions if p not in forbidden and is_not_edge(p, grid_size)]
    main_item_pos = random.choice(main_item_candidates); forbidden.add(main_item_pos)
    obstacles = {main_item_pos: MainBlock(main_item_pos[0], main_item_pos[1], health=main_block_hp)}
    rest_obstacle_candidates = [p for p in all_positions if p not in forbidden]
    rest_count = obstacle_count - 1
    rest_obstacle_positions = random.sample(rest_obstacle_candidates, rest_count)
    destructible_count = int(rest_count * DESTRUCTIBLE_RATIO)
    indestructible_count = rest_count - destructible_count
    for pos in rest_obstacle_positions[:destructible_count]:
        obstacles[pos] = Obstacle(pos[0], pos[1], "Destructible", health=OBSTACLE_HEALTH)
    for pos in rest_obstacle_positions[destructible_count:]:
        obstacles[pos] = Obstacle(pos[0], pos[1], "Indestructible")
    forbidden |= set(obstacles.keys())
    item_candidates = [p for p in all_positions if p not in forbidden]
    other_items = random.sample(item_candidates, item_count - 1)
    items = [Item(pos[0], pos[1]) for pos in other_items]
    items.append(Item(main_item_pos[0], main_item_pos[1], is_main=True))
    return obstacles, items, player_pos, zombie_pos_list, [main_item_pos]

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
    def __init__(self, obstacles: Dict, items: Set, main_item_pos: List[Tuple[int, int]]):
        self.obstacles = obstacles
        self.items = items
        self.destructible_count = self.count_destructible_obstacles()
        self.main_item_pos = main_item_pos
    def count_destructible_obstacles(self) -> int:
        return sum(1 for obs in self.obstacles.values() if obs.type == "Destructible")
    def collect_item(self, player_rect):
        for item in list(self.items):
            if player_rect.colliderect(item.rect):
                if item.is_main and any(getattr(ob, "is_main_block", False) for ob in self.obstacles.values()):
                    return False
                self.items.remove(item); return True
        return False
    def destroy_obstacle(self, pos: Tuple[int, int]):
        if pos in self.obstacles:
            if self.obstacles[pos].type == "Destructible": self.destructible_count -= 1
            del self.obstacles[pos]

# ==================== 游戏渲染函数 ====================
def render_game(screen: pygame.Surface, game_state, player: Player, zombies: List[Zombie]) -> pygame.Surface:
    screen.fill((20, 20, 20))
    pygame.draw.rect(screen, (0, 0, 0), (0, 0, WINDOW_SIZE, INFO_BAR_HEIGHT))
    font = pygame.font.SysFont(None, 28)
    item_txt = font.render(f"ITEMS: {len(game_state.items)}", True, (255, 255, 80))
    screen.blit(item_txt, (12, 12))
    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE + INFO_BAR_HEIGHT, CELL_SIZE, CELL_SIZE)
            pygame.draw.rect(screen, (50, 50, 50), rect, 1)
    for item in game_state.items:
        color = (255, 255, 100) if item.is_main else (255, 255, 0)
        pygame.draw.circle(screen, color, item.center, item.radius)
    pygame.draw.rect(screen, (0, 255, 0), player.rect)
    for zombie in zombies: pygame.draw.rect(screen, (255, 60, 60), zombie.rect)
    for obstacle in game_state.obstacles.values():
        is_main = hasattr(obstacle, 'is_main_block') and obstacle.is_main_block
        if is_main: color = (255, 220, 80)
        elif obstacle.type == "Indestructible": color = (120, 120, 120)
        else: color = (200, 80, 80)
        pygame.draw.rect(screen, color, obstacle.rect)
        if obstacle.type == "Destructible":
            font = pygame.font.SysFont(None, 30)
            health_text = font.render(str(obstacle.health), True, (255, 255, 255))
            screen.blit(health_text, (obstacle.rect.x + 6, obstacle.rect.y + 8))
        if is_main:
            star = pygame.font.SysFont(None, 32).render("★", True, (255, 255, 120))
            screen.blit(star, (obstacle.rect.x + 8, obstacle.rect.y + 8))
    pygame.display.flip()
    # return a copy of the frame for dim overlay screens
    return screen.copy()

# ==================== 游戏主循环 ====================
def main_run_level(config, chosen_zombie_type:str) -> Tuple[str, Optional[str], pygame.Surface]:
    pygame.display.set_caption("Zombie Card Game – Level")
    screen = pygame.display.get_surface()
    clock = pygame.time.Clock()

    # 生成实体
    obstacles, items, player_start, zombie_starts, main_item_list = generate_game_entities(
        grid_size=GRID_SIZE,
        obstacle_count=config["obstacle_count"],
        item_count=config["item_count"],
        zombie_count=config["zombie_count"],
        main_block_hp=config["block_hp"]
    )

    game_state = GameState(obstacles, items, main_item_list)
    player = Player(player_start, speed=PLAYER_SPEED)
    # make zombies with chosen type
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

    running=True; game_result=None; last_frame=None
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
        keys = pygame.key.get_pressed()
        player.move(keys, game_state.obstacles)
        game_state.collect_item(player.rect)
        for zombie in zombies:
            zombie.move_and_attack(player, list(game_state.obstacles.values()), game_state)
            player_rect = pygame.Rect(int(player.x), int(player.y) + INFO_BAR_HEIGHT, player.size, player.size)
            if zombie.rect.colliderect(player_rect):
                game_result = "fail"; running=False; break
        if not game_state.items:
            game_result = "success"; running=False
        last_frame = render_game(pygame.display.get_surface(), game_state, player, zombies)
        clock.tick(60)
    return game_result, config.get("reward", None), last_frame

def select_zombie_screen(screen, owned_cards:List[str]) -> str:
    # Choose which zombie type spawns next level. If none owned -> 'basic'
    if not owned_cards: return "basic"
    clock = pygame.time.Clock()
    while True:
        screen.fill((18,18,18))
        title = pygame.font.SysFont(None, 48).render("Choose Next Level's Zombie", True, (230,230,230))
        screen.blit(title, title.get_rect(center=(WINDOW_SIZE//2, 110)))
        rects=[]
        for i, card in enumerate(owned_cards):
            x = WINDOW_SIZE//2 - (len(owned_cards)*140)//2 + i*140
            rect = pygame.Rect(x, 180, 120, 160)
            pygame.draw.rect(screen, (200,200,200), rect)
            name = pygame.font.SysFont(None, 24).render(card.replace("_"," ").upper(), True, (30,30,30))
            screen.blit(name, name.get_rect(center=(rect.centerx, rect.bottom-18)))
            pygame.draw.rect(screen, (40,40,40), rect, 3)
            rects.append((rect, card))
        confirm = draw_button(screen, "CONFIRM", (WINDOW_SIZE//2-90, 370))
        pygame.display.flip()
        chosen=None
        for event in pygame.event.get():
            if event.type==pygame.QUIT: pygame.quit(); sys.exit()
            if event.type==pygame.MOUSEBUTTONDOWN:
                for rect, card in rects:
                    if rect.collidepoint(event.pos): chosen=card
                if confirm.collidepoint(event.pos) and (chosen or owned_cards):
                    door_transition(screen); return chosen or owned_cards[0]
        clock.tick(60)

# ==================== 入口 ====================
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_SIZE, TOTAL_HEIGHT))
    pygame.display.set_caption(GAME_TITLE)

    # Start menu
    if not show_start_menu(screen): sys.exit()

    current_level = 0
    zombie_cards_collected: List[str] = []

    while True:
        config = get_level_config(current_level)
        # pre-level zombie selection
        chosen_zombie = select_zombie_screen(screen, zombie_cards_collected) if zombie_cards_collected else "basic"
        door_transition(screen)
        result, reward, bg = main_run_level(config, chosen_zombie)
        if result == "fail":
            action = show_fail_screen(screen, bg)
            if action == "home":
                show_start_menu(screen); continue
            else:
                # retry same level
                continue
        elif result == "success":
            # compute reward choices: up to 3 not yet owned
            pool = [c for c in CARD_POOL if c not in zombie_cards_collected]
            reward_choices = random.sample(pool, k=min(3, len(pool))) if pool else []
            chosen = show_success_screen(screen, bg, reward_choices)
            if chosen:
                zombie_cards_collected.append(chosen)
            current_level += 1
        else:
            # unknown result; back to menu
            show_start_menu(screen)
