import sys

import pygame
import math
import random
from queue import PriorityQueue
from typing import Dict, List, Set, Tuple, Optional

# ==================== 游戏常量配置 ====================

INFO_BAR_HEIGHT = 40
GRID_SIZE = 18
CELL_SIZE = 40
WINDOW_SIZE = GRID_SIZE * CELL_SIZE
TOTAL_HEIGHT = WINDOW_SIZE + INFO_BAR_HEIGHT
OBSTACLES = 25
OBSTACLE_HEALTH = 20  # 可破坏障碍物初始血量
MAIN_BLOCK_HEALTH = 40
DESTRUCTIBLE_RATIO = 0.3
PLAYER_SPEED = 5
ZOMBIE_SPEED = 2
ZOMBIE_ATTACK = 10  # 僵尸攻击力
ZOMBIE_NUM = 2
ITEMS = 10

LEVELS = [
    {"obstacle_count": 15, "item_count": 3, "zombie_count": 1, "block_hp": 10, "zombie_types": ["basic"],
     "reward": "zombie_fast"},
    {"obstacle_count": 18, "item_count": 4, "zombie_count": 2, "block_hp": 15, "zombie_types": ["basic", "strong"],
     "reward": "zombie_strong"},
    # 可以继续添加更多关
]

# 方向向量
DIRECTIONS = {
    pygame.K_a: (-1, 0),  # 左
    pygame.K_d: (1, 0),  # 右
    pygame.K_w: (0, -1),  # 上
    pygame.K_s: (0, 1),  # 下
}


# ==================== 数据结构 ====================
class Graph:
    """表示游戏地图的图结构，用于路径查找"""

    def __init__(self):
        self.edges: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        self.weights: Dict[Tuple[Tuple[int, int], Tuple[int, int]], float] = {}

    def add_edge(self, from_node: Tuple[int, int], to_node: Tuple[int, int], weight: float) -> None:
        """添加一条边到图中"""
        if from_node not in self.edges:
            self.edges[from_node] = []
        self.edges[from_node].append(to_node)
        self.weights[(from_node, to_node)] = weight

    def neighbors(self, node: Tuple[int, int]) -> List[Tuple[int, int]]:
        """获取节点的邻居"""
        return self.edges.get(node, [])

    def cost(self, from_node: Tuple[int, int], to_node: Tuple[int, int]) -> float:
        """获取两个节点之间的移动代价"""
        return self.weights.get((from_node, to_node), float('inf'))


class Obstacle:
    """表示游戏中的障碍物"""

    def __init__(self, x: int, y: int, obstacle_type: str, health: Optional[int] = None):
        # def __init__(self, pos: Tuple[int, int], obstacle_type: str, health: Optional[int] = None):
        """
        初始化障碍物

        Args:
            pos: 障碍物位置 (x, y)
            obstacle_type: 障碍物类型 ("Destructible" 或 "Indestructible")
            health: 可破坏障碍物的生命值 (仅对可破坏障碍物有效)
        """
        px = x * CELL_SIZE
        py = y * CELL_SIZE + INFO_BAR_HEIGHT
        self.rect = pygame.Rect(px, py, CELL_SIZE, CELL_SIZE)
        self.type: str = obstacle_type
        self.health: Optional[int] = health

    def is_destroyed(self) -> bool:
        """检查障碍物是否已被破坏"""
        return self.type == "Destructible" and self.health <= 0

    @property
    def grid_pos(self):
        return self.rect.x // CELL_SIZE, (self.rect.y - INFO_BAR_HEIGHT) // CELL_SIZE


class MainBlock(Obstacle):
    def __init__(self, x: int, y: int, health: Optional[int] = MAIN_BLOCK_HEALTH):
        # def __init__(self, pos: Tuple[int, int], health: Optional[int] = MAIN_BLOCK_HEALTH):
        super().__init__(x, y, "Destructible", health)
        self.is_main_block = True


class Item:
    def __init__(self, x: int, y: int, is_main=False):
        self.x = x
        self.y = y
        self.is_main = is_main
        self.radius = CELL_SIZE // 3
        # 以中心点为主，方便后续像素判定
        self.center = (
            self.x * CELL_SIZE + CELL_SIZE // 2,
            self.y * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT
        )
        self.rect = pygame.Rect(
            self.center[0] - self.radius,
            self.center[1] - self.radius,
            self.radius * 2,
            self.radius * 2
        )


# ---------- OO 角色定义 ----------
# class Player:
#     """玩家角色"""
#
#     def __init__(self, pos: Tuple[int, int], speed: int = PLAYER_SPEED):
#         """
#         初始化玩家
#
#         Args:
#             pos: 初始位置 (x, y)
#             speed: 移动速度 (值越大移动越慢)
#         """
#         self.pos: Tuple[int, int] = pos
#         self.speed: int = speed
#         self.move_cooldown: int = 0
#
#     def move(self, direction: Tuple[int, int], obstacles: Dict[Tuple[int, int], Obstacle]) -> None:
#         """在指定方向上移动玩家
#
#         Args:
#             direction: 移动方向 (dx, dy)
#             obstacles: 障碍物字典
#         """
#         if self.move_cooldown <= 0:
#             x, y = self.pos
#             dx, dy = direction
#             new_x, new_y = x + dx, y + dy
#
#             # 检查新位置是否有效
#             if (0 <= new_x < GRID_SIZE and
#                     0 <= new_y < GRID_SIZE and
#                     (new_x, new_y) not in obstacles):
#                 self.pos = (new_x, new_y)
#                 self.move_cooldown = self.speed

class Player:
    """玩家角色（像素自由移动版）"""

    def __init__(self, pos: Tuple[int, int], speed: int = PLAYER_SPEED):
        """
        pos: 初始格子 (x, y)
        speed: 每帧像素速度（整数越大越快）
        """
        self.x = pos[0] * CELL_SIZE
        self.y = pos[1] * CELL_SIZE
        self.speed = speed
        self.size = CELL_SIZE - 6  # 角色实际占位像素，略小于格子便于走位
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)

    @property
    def pos(self):
        """返回当前所处格子的格子坐标（int）"""
        return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)

    def move(self, keys, obstacles):
        dx = dy = 0
        if keys[pygame.K_w]:
            dy -= 1
        if keys[pygame.K_s]:
            dy += 1
        if keys[pygame.K_a]:
            dx -= 1
        if keys[pygame.K_d]:
            dx += 1
        # 斜向归一化
        if dx != 0 and dy != 0:
            dx *= 0.7071
            dy *= 0.7071

        nx = self.x + dx * self.speed
        ny = self.y + dy * self.speed

        # 预测下一帧碰撞盒
        next_rect = pygame.Rect(int(nx), int(ny) + INFO_BAR_HEIGHT, self.size, self.size)
        can_move = True
        for ob in obstacles.values():
            if next_rect.colliderect(ob.rect):
                can_move = False
                break

        if can_move and 0 <= nx < WINDOW_SIZE - self.size and 0 <= ny < WINDOW_SIZE - self.size:
            self.x = nx
            self.y = ny
            self.rect.x = int(self.x)
            self.rect.y = int(self.y) + INFO_BAR_HEIGHT

    def draw(self, screen):
        pygame.draw.rect(screen, (0, 255, 0), self.rect)

        # 检测“新像素位置”是否进入障碍格
    #     grid_x = int((nx + self.size // 2) // CELL_SIZE)
    #     grid_y = int((ny + self.size // 2) // CELL_SIZE)
    #     if (0 <= grid_x < GRID_SIZE and 0 <= grid_y < GRID_SIZE and
    #             (grid_x, grid_y) not in obstacles):
    #         self.x = nx
    #         self.y = ny
    #
    # def draw(self, screen):
    #     player_rect = pygame.Rect(int(self.x), int(self.y) + INFO_BAR_HEIGHT, self.size, self.size)
    #     pygame.draw.rect(screen, (0, 255, 0), player_rect)


class Zombie:
    """僵尸角色"""

    # def __init__(self, pos: Tuple[int, int], attack: int = ZOMBIE_ATTACK, speed: int = ZOMBIE_SPEED):
    #     """
    #     初始化僵尸
    #
    #     Args:
    #         pos: 初始位置 (x, y)
    #         attack: 攻击力
    #         speed: 移动速度 (值越大移动越慢)
    #     """
    #     self.pos: Tuple[int, int] = pos
    #     self.attack: int = attack
    #     self.speed: int = speed
    #     self.move_cooldown: int = random.randint(0, speed - 1)  # 让僵尸移动不完全同步
    #     self.breaking_obstacle: Optional[Tuple[int, int]] = None
    """像素自由移动版僵尸"""

    def __init__(self, pos: Tuple[int, int], attack: int = ZOMBIE_ATTACK, speed: int = ZOMBIE_SPEED):
        # 初始格子坐标转像素
        self.x = pos[0] * CELL_SIZE
        self.y = pos[1] * CELL_SIZE
        self.attack = attack
        self.speed = speed
        self.size = CELL_SIZE - 6  # 可微调
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)

    @property
    def pos(self) -> Tuple[int, int]:
        """返回当前所处格子的格子坐标（兼容原A*寻路）"""
        return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)

    def move_and_attack(self, player, obstacles, game_state, attack_interval=0.5, dt=1 / 60):
        # attack_interval 秒攻击一次（例如 0.5s），dt 是本帧时长
        if not hasattr(self, 'attack_timer'):
            self.attack_timer = 0
        self.attack_timer += dt

        dx = player.x - self.x
        dy = player.y - self.y
        speed = self.speed

        # 按主方向、次方向、正交方向尝试
        dirs = []
        if abs(dx) > abs(dy):
            dirs = [(sign(dx), 0), (0, sign(dy)), (sign(dx), sign(dy)), (-sign(dx), 0), (0, -sign(dy))]
        else:
            dirs = [(0, sign(dy)), (sign(dx), 0), (sign(dx), sign(dy)), (0, -sign(dy)), (-sign(dx), 0)]

        moved = False
        for ddx, ddy in dirs:
            if ddx == 0 and ddy == 0:
                continue
            next_rect = self.rect.move(ddx * speed, ddy * speed)
            blocked = False
            for ob in obstacles:
                if next_rect.colliderect(ob.rect):
                    if ob.type == "Destructible":
                        if self.attack_timer >= attack_interval:
                            ob.health -= self.attack
                            self.attack_timer = 0
                            if ob.health <= 0:
                                grid_pos = ob.grid_pos
                                if grid_pos in game_state.obstacles:
                                    del game_state.obstacles[grid_pos]
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
                moved = True
                break  # 已经移动成功
        return moved

    def draw(self, screen):
        pygame.draw.rect(screen, (255, 60, 60), self.rect)


# ==================== 算法函数 ====================
def sign(v):
    if v > 0:
        return 1
    if v < 0:
        return -1
    return 0


def heuristic(a, b):
    # 曼哈顿距离，适合格子图
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def a_star_search(graph: Graph, start: Tuple[int, int], goal: Tuple[int, int],
                  obstacles: Dict[Tuple[int, int], Obstacle]) -> Tuple[Dict, Dict]:
    """
    A*寻路算法实现

    Args:
        graph: 地图图结构
        start: 起始位置
        goal: 目标位置
        obstacles: 障碍物字典

    Returns:
        (路径字典, 代价字典)
    """
    frontier = PriorityQueue()
    frontier.put((0, start))
    came_from = {start: None}
    cost_so_far = {start: 0}

    while not frontier.empty():
        _, current = frontier.get()

        # 找到目标位置，结束搜索
        if current == goal:
            break

        # 探索邻居节点
        for neighbor in graph.neighbors(current):
            # 计算新代价
            new_cost = cost_so_far[current] + graph.cost(current, neighbor)

            # 处理障碍物
            if neighbor in obstacles:
                obstacle = obstacles[neighbor]

                # 不可破坏障碍物，跳过
                if obstacle.type == "Indestructible":
                    continue

                # 可破坏障碍物，增加额外代价
                elif obstacle.type == "Destructible":
                    # 计算破坏障碍物所需的额外代价
                    k_factor = (math.ceil(obstacle.health / ZOMBIE_ATTACK)) * 0.1
                    new_cost = cost_so_far[current] + 1 + k_factor

            # 更新节点代价
            if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                cost_so_far[neighbor] = new_cost
                priority = new_cost + heuristic(goal, neighbor)
                frontier.put((priority, neighbor))
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
        "reward": f"zombie_special_{level}"
    }


def reconstruct_path(came_from: Dict, start: Tuple[int, int], goal: Tuple[int, int]) -> List[Tuple[int, int]]:
    """根据A*算法的结果重建路径"""
    if goal not in came_from:
        return [start]

    path = []
    current = goal
    while current != start:
        path.append(current)
        current = came_from[current]
    path.append(start)
    path.reverse()
    return path


# ==================== 游戏初始化函数 ====================
def generate_game_entities(grid_size: int, obstacle_count: int, item_count: int,
                           zombie_count: int, main_block_hp: int) -> Tuple[Dict, Set, Tuple, List]:
    """
    生成游戏实体（障碍物、道具、玩家和僵尸位置）

    Returns:
         (障碍物字典, 道具集合, 玩家位置, 僵尸位置列表, 锁定物品位置)
         obstacles_dict: Dict[grid_pos, Obstacle]
        obstacle_pixel_list: List[Obstacle]  # 用于碰撞检测
        items: Set[Tuple[int, int]]
        player_start: (x, y)
        zombie_starts: List[(x, y)]
        main_item_pos: List[Tuple[int, int]]
    """
    all_positions = [(x, y) for x in range(grid_size) for y in range(grid_size)]
    corners = [(0, 0), (0, grid_size - 1), (grid_size - 1, 0), (grid_size - 1, grid_size - 1)]

    # 玩家、僵尸初始点不能在角落
    forbidden = set(corners)

    def pick_valid_positions(min_distance: int, count: int):
        empty = [p for p in all_positions if p not in forbidden]
        while True:
            picks = random.sample(empty, count + 1)
            player_pos, zombies = picks[0], picks[1:]
            if all(abs(player_pos[0] - z[0]) + abs(player_pos[1] - z[1]) >= min_distance for z in zombies):
                return player_pos, zombies

    player_pos, zombie_pos_list = pick_valid_positions(min_distance=5, count=zombie_count)
    forbidden |= {player_pos}
    forbidden |= set(zombie_pos_list)

    # 主道具点（不在 forbidden）
    main_item_candidates = [p for p in all_positions if p not in forbidden and is_not_edge(p, grid_size)]
    main_item_pos = random.choice(main_item_candidates)
    forbidden.add(main_item_pos)

    # 主障碍（MainBlock）
    # obstacles = {main_item_pos: MainBlock(main_item_pos, health=main_block_hp)}
    obstacles = {main_item_pos: MainBlock(main_item_pos[0], main_item_pos[1], health=main_block_hp)}

    rest_obstacle_candidates = [p for p in all_positions if p not in forbidden]
    rest_count = obstacle_count - 1
    rest_obstacle_positions = random.sample(rest_obstacle_candidates, rest_count)
    destructible_count = int(rest_count * DESTRUCTIBLE_RATIO)
    indestructible_count = rest_count - destructible_count

    # 可破坏障碍
    for pos in rest_obstacle_positions[:destructible_count]:
        obstacles[pos] = Obstacle(pos[0], pos[1], "Destructible", health=OBSTACLE_HEALTH)
    # 不可破坏障碍
    for pos in rest_obstacle_positions[destructible_count:]:
        obstacles[pos] = Obstacle(pos[0], pos[1], "Indestructible")
    forbidden |= set(obstacles.keys())

    # 其它道具
    item_candidates = [p for p in all_positions if p not in forbidden]
    other_items = random.sample(item_candidates, item_count - 1)
    items = [Item(pos[0], pos[1]) for pos in other_items]
    items.append(Item(main_item_pos[0], main_item_pos[1], is_main=True))  # MainBlock

    return obstacles, items, player_pos, zombie_pos_list, [main_item_pos]  # main_item_pos可为列表支持多关卡


# ----------- 生成开始界面 -----------

def show_start_menu(screen: pygame.Surface) -> bool:
    """显示开始菜单，点击START图像按钮后进入游戏"""
    background = pygame.image.load("assets/start_bg.png").convert()
    background = pygame.transform.scale(background, (WINDOW_SIZE, TOTAL_HEIGHT))

    start_button_img = pygame.image.load("assets/start_button.png").convert_alpha()
    button_width, button_height = start_button_img.get_size()

    # 居中摆放按钮
    start_button_rect = start_button_img.get_rect(center=(WINDOW_SIZE // 2, TOTAL_HEIGHT // 2))

    while True:
        screen.blit(background, (0, 0))
        screen.blit(start_button_img, start_button_rect)
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if start_button_rect.collidepoint(event.pos):
                    return True


# ----------- 生成格子地图 -----------
def build_graph(grid_size: int, obstacles: Dict[Tuple[int, int], Obstacle]) -> Graph:
    """构建游戏地图的图结构"""
    graph = Graph()

    for x in range(grid_size):
        for y in range(grid_size):
            current_pos = (x, y)

            # 跳过不可破坏障碍物
            if current_pos in obstacles and obstacles[current_pos].type == "Indestructible":
                continue

            # 检查四个方向
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                neighbor_pos = (x + dx, y + dy)

                # 确保邻居在网格范围内
                if not (0 <= neighbor_pos[0] < grid_size and 0 <= neighbor_pos[1] < grid_size):
                    continue

                # 跳过不可破坏障碍物
                if neighbor_pos in obstacles and obstacles[neighbor_pos].type == "Indestructible":
                    continue

                # 设置移动代价
                weight = 1

                # 如果是可破坏障碍物，增加移动代价
                if neighbor_pos in obstacles and obstacles[neighbor_pos].type == "Destructible":
                    weight = 10

                # 添加边
                graph.add_edge(current_pos, neighbor_pos, weight)

    return graph


# ==================== 新增游戏状态类 ====================
class GameState:
    """管理游戏状态和进度"""

    def __init__(self, obstacles: Dict, items: Set, main_item_pos: List[Tuple[int, int]]):
        self.obstacles = obstacles
        self.items = items
        self.destructible_count = self.count_destructible_obstacles()
        self.main_item_pos = main_item_pos

    def count_destructible_obstacles(self) -> int:
        """计算可破坏障碍物的数量"""
        return sum(1 for obs in self.obstacles.values() if obs.type == "Destructible")

    # def check_unlock_condition(self) -> bool:
    #     """检查是否满足解锁条件"""
    #     # 条件1: 所有其他物品已被收集
    #     # 条件2: 所有可破坏障碍物已被破坏
    #     return len(self.items) == 1 and self.destructible_count == 0

    # def collect_item(self, pos: Tuple[int, int]) -> bool:
    #     """收集物品，如果是主物品且未解锁则无法收集"""
    #     # 只有主障碍不在时才能收集主道具
    #     if pos in self.main_item_pos and pos in self.obstacles:
    #         return False
    #     if pos in self.items:
    #         self.items.remove(pos)
    #         return True
    #     return False
    def collect_item(self, player_rect):
        for item in list(self.items):  # 用 list 防止迭代时删
            if player_rect.colliderect(item.rect):
                if item.is_main and any(getattr(ob, "is_main_block", False) for ob in self.obstacles.values()):
                    return False  # 主障碍未破坏不能捡主道具
                self.items.remove(item)
                return True
        return False

    def destroy_obstacle(self, pos: Tuple[int, int]):
        """破坏障碍物并更新计数"""
        if pos in self.obstacles:
            # 如果是可破坏障碍物，更新计数
            if self.obstacles[pos].type == "Destructible":
                self.destructible_count -= 1
            del self.obstacles[pos]

        # # 每次破坏后检查是否满足解锁条件
        # self.unlocked = self.check_unlock_condition()


# ==================== 游戏渲染函数 ====================


def render_game(screen: pygame.Surface, game_state, player: Player, zombies: List[Zombie]) -> None:
    """渲染游戏画面"""
    # 清空屏幕
    screen.fill((20, 20, 20))

    # 顶部信息栏
    pygame.draw.rect(screen, (0, 0, 0), (0, 0, WINDOW_SIZE, INFO_BAR_HEIGHT))
    font = pygame.font.SysFont(None, 28)
    item_txt = font.render(f"ITEMS: {len(game_state.items)}", True, (255, 255, 80))
    screen.blit(item_txt, (12, 12))

    # 绘制网格
    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE + INFO_BAR_HEIGHT, CELL_SIZE, CELL_SIZE)
            pygame.draw.rect(screen, (50, 50, 50), rect, 1)

    # 绘制道具
    for item in game_state.items:
        color = (255, 255, 100) if item.is_main else (255, 255, 0)
        pygame.draw.circle(screen, color, item.center, item.radius)
        # is_main = item_pos in game_state.main_item_pos
        # color = (255, 255, 100) if is_main else (255, 255, 0)
        # center = (item_pos[0] * CELL_SIZE + CELL_SIZE // 2, item_pos[1] * CELL_SIZE + CELL_SIZE // 2 + INFO_BAR_HEIGHT)
        # pygame.draw.circle(screen, color, center, CELL_SIZE // 3)

    # 绘制玩家
    player_rect = pygame.Rect(
        player.pos[0] * CELL_SIZE,
        player.pos[1] * CELL_SIZE + INFO_BAR_HEIGHT,
        CELL_SIZE,
        CELL_SIZE
    )
    pygame.draw.rect(screen, (0, 255, 0), player.rect)

    # 绘制所有僵尸
    # for zombie in zombies:
    #     zombie_rect = pygame.Rect(
    #         zombie.pos[0] * CELL_SIZE,
    #         zombie.pos[1] * CELL_SIZE + INFO_BAR_HEIGHT,
    #         CELL_SIZE,
    #         CELL_SIZE
    #     )
    #     pygame.draw.rect(screen, (255, 60, 60), zombie_rect)
    for zombie in zombies:
        pygame.draw.rect(screen, (255, 60, 60), zombie.rect)

    # 绘制障碍物
    for obstacle in game_state.obstacles.values():
        is_main = hasattr(obstacle, 'is_main_block') and obstacle.is_main_block
        if is_main:
            color = (255, 220, 80)  # 主障碍：金黄
        elif obstacle.type == "Indestructible":
            color = (120, 120, 120)  # 灰色
        else:
            color = (200, 80, 80)  # 可破坏：红
        pygame.draw.rect(screen, color, obstacle.rect)
        if obstacle.type == "Destructible":
            font = pygame.font.SysFont(None, 30)
            health_text = font.render(str(obstacle.health), True, (255, 255, 255))
            screen.blit(health_text,
                        (obstacle.rect.x + 6, obstacle.rect.y + 8))
        if is_main:
            star = pygame.font.SysFont(None, 32).render("★", True, (255, 255, 120))
            screen.blit(star, (obstacle.rect.x + 8, obstacle.rect.y + 8))


def render_game_result(screen: pygame.Surface, result: str, restart_img, next_img) -> Tuple[pygame.Rect, pygame.Rect]:
    """渲染游戏结果画面"""
    screen.fill((0, 0, 0))
    font = pygame.font.SysFont(None, 80)

    if result == "success":
        # bg_color = (34, 163, 77)
        text = font.render("CONGRATULATIONS!", True, (0, 255, 0))
    elif result == "fail":
        # bg_color = (70, 18, 32)
        text = font.render("GAME OVER!", True, (255, 60, 60))
    else:
        # 防止result为None或其它未知值时报错
        text = font.render("Result Unknown", True, (200, 200, 200))

    text_rect = text.get_rect(center=(WINDOW_SIZE // 2, WINDOW_SIZE // 2 - 60))
    # screen.fill(bg_color)
    screen.blit(text, text_rect)

    # ---- 左下角按钮区 ----
    margin = 40
    icon_size = 64
    # Restart图标位置
    restart_pos = (margin, WINDOW_SIZE - icon_size - margin)
    restart_rect = pygame.Rect(restart_pos, (icon_size, icon_size))
    screen.blit(restart_img, restart_rect)
    # Next图标紧挨右边
    next_pos = (margin + icon_size + 32, WINDOW_SIZE - icon_size - margin)
    next_rect = pygame.Rect(next_pos, (icon_size, icon_size))
    screen.blit(next_img, next_rect)

    pygame.display.flip()

    return restart_rect, next_rect

    # pygame.time.wait(1500)


# ==================== 游戏主循环 ====================
def main(config, zombie_cards_collected: Set[str]) -> Tuple[str, Optional[str]]:
    """游戏主函数"""
    # 初始化pygame
    pygame.init()
    pygame.display.set_caption("Zombie Chase Game")
    screen = pygame.display.set_mode((WINDOW_SIZE, TOTAL_HEIGHT))
    clock = pygame.time.Clock()

    restart_img = pygame.image.load("assets/restart.png").convert_alpha()
    next_img = pygame.image.load("assets/next.png").convert_alpha()
    icon_size = 64
    restart_img = pygame.transform.smoothscale(restart_img, (icon_size, icon_size))
    next_img = pygame.transform.smoothscale(next_img, (icon_size, icon_size))

    # 生成游戏实体
    # obstacles, items, player_start, zombie_starts, main_item_list = generate_game_entities(
    #     grid_size=GRID_SIZE,
    #     obstacle_count=OBSTACLES,
    #     item_count=ITEMS,
    #     zombie_count=ZOMBIE_NUM
    # )
    obstacles, items, player_start, zombie_starts, main_item_list = generate_game_entities(
        grid_size=GRID_SIZE,
        obstacle_count=config["obstacle_count"],
        item_count=config["item_count"],
        zombie_count=config["zombie_count"],
        main_block_hp=config["block_hp"]
    )

    # 创建游戏状态管理器
    game_state = GameState(obstacles, items, main_item_list)

    # 创建玩家和僵尸
    player = Player(player_start, speed=PLAYER_SPEED)
    zombies = [Zombie(pos, speed=ZOMBIE_SPEED) for pos in zombie_starts]

    # 构建地图图结构
    graph = build_graph(GRID_SIZE, obstacles)

    # 主游戏循环
    running = True
    game_result = None

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        # 玩家移动
        # if player.move_cooldown > 0:
        #     player.move_cooldown -= 1
        #
        # keys = pygame.key.get_pressed()
        # for key, direction in DIRECTIONS.items():
        #     if keys[key]:
        #         player.move(direction, obstacles)
        #         break
        keys = pygame.key.get_pressed()
        player.move(keys, game_state.obstacles)

        # 检查玩家是否拾取道具
        game_state.collect_item(player.rect)

        for zombie in zombies:
            # 僵尸像素级追踪玩家
            zombie.move_and_attack(player, list(game_state.obstacles.values()), game_state)
            # 僵尸与玩家像素碰撞则失败
            player_rect = pygame.Rect(int(player.x), int(player.y) + INFO_BAR_HEIGHT, player.size, player.size)
            if zombie.rect.colliderect(player_rect):
                game_result = "fail"
                break
        # for zombie in zombies:
        #     if zombie.move_cooldown > 0:
        #         zombie.move_cooldown -= 1
        #         continue
        #
        #     action, target_pos = zombie.chase(player.pos, graph, obstacles)
        #
        #     # 处理障碍物被破坏的情况
        #     if action == "destroy":
        #         # 更新游戏状态
        #         game_state.destroy_obstacle(target_pos)
        #         # 重建图
        #         graph = build_graph(GRID_SIZE, game_state.obstacles)
        #
        #     # 处理僵尸移动
        #     if action == "move":
        #         zombie.pos = target_pos
        #
        #     zombie.move_cooldown = zombie.speed
        #
        #     # 检查僵尸是否抓到玩家
        #     if zombie.pos == player.pos:
        #         game_result = "fail"
        #         game_running = False
        #
        # 检查胜利条件（收集所有道具）
        if not game_state.items:
            game_result = "success"
            break

        # ...游戏内容渲染...
        render_game(screen, game_state, player, zombies)
        pygame.display.flip()
        clock.tick(60)

        # 胜负判断建议直接 break 出循环，不必设置 game_running/running 双变量
        if game_result:
            break

    # 渲染结算画面+等待点击Restart
    restart_rect, next_rect = render_game_result(screen, game_result, restart_img, next_img)
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if restart_rect.collidepoint(event.pos):
                    return "restart", None
                while True:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            pygame.quit()
                            sys.exit()
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            if restart_rect.collidepoint(event.pos):
                                return "restart", None
                            if next_rect.collidepoint(event.pos) and game_result == "success":
                                return "next", config.get("reward", None)
                if next_rect.collidepoint(event.pos):
                    return "next"


# ==================== 游戏主循环 ====================
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_SIZE, TOTAL_HEIGHT))
    pygame.display.set_caption("Zombie Card Game")

    # 开始界面
    if not show_start_menu(screen):
        sys.exit()

    # 主游戏循环
    current_level = 0
    zombie_cards_collected = set()

    while True:
        config = get_level_config(current_level)
        result, reward = main(config, zombie_cards_collected)

        if result == "next":
            current_level += 1
            if reward:
                zombie_cards_collected.add(reward)
                print(f"获得新卡牌：{reward}")
        elif result == "restart":
            continue
        else:
            break

# TODO
#  IMPROVE THE UI AND HINT  BUGS ABOUT LOCKED ITEM CANNOT SUCCESS/ block arrangement
#  ADDING MULTIPLE TYPE/ NUMBER OF / Balancing the speed of Zombies & Player
#  Adding more interaction with the blocks and other feature on map
#  Adding multiple chapters afterMONSTER AGAINST PLAYER  DONE
#  Possibly increase player ability completing single one
#  新怪物/AI
#  更多交互/可破坏物体
#  动画、特效、音效
#  UI按钮、菜单、地图选择等
#  Actually you know what I got I better idea about this game, Zombie and Obstacle,
#  We can make it have a much deeper connection with player, add them into the goal of the game
#  Revision: put the last item in the centre of walls surrounding, do not use the lock thing
#  , it has nothing to do directly with the game set
#  Add a potion to control zombie possess the body
#  Working on the aviator and main character design and map design today, getting a little inspired
#  Turn to pixel design, give up the block set.etc

# And btw still figuring the UI, Decide to add the full course UI for this game
# 核心设定：
#
# 玩家扮演 "Neuro Runner" - 拥有侵入他人意识能力的神经漫游者
#
# 游戏场景发生在 "Mindscape 心象空间" - 由人类潜意识构成的虚拟世界
#
# 僵尸是 "CogniCorrupted 认知腐化者" - 被病毒感染的记忆碎片
#
# 障碍物是 "Mental Blocks 心之壁" - 人类的心理防御机制
#
# 奖励物品是 "Memory Fragments 记忆碎片" - 包含关键信息的意识数据包
#
# 故事背景：
# 在2045年，全球神经网络被"NeuroVirus"感染，人类集体意识陷入混乱。玩家作为最后一批清醒的神经漫游者，必须潜入被感染的意识空间，
# 收集关键记忆碎片，重建人类认知防火墙。主障碍代表最深层的心理创伤，必须通过引导认知腐化者（僵尸）来解构。
