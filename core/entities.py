import pygame
from .utils import CELL_SIZE, INFO_BAR_HEIGHT


class Obstacle:
    def __init__(self, x, y, obstacle_type, health=None):
        px = x * CELL_SIZE
        py = y * CELL_SIZE + INFO_BAR_HEIGHT
        self.rect = pygame.Rect(px, py, CELL_SIZE, CELL_SIZE)
        self.type = obstacle_type
        self.health = health

    @property
    def grid_pos(self):
        return self.rect.x // CELL_SIZE, (self.rect.y - INFO_BAR_HEIGHT) // CELL_SIZE


class MainBlock(Obstacle):
    def __init__(self, x, y, health):
        super().__init__(x, y, "Destructible", health)
        self.is_main_block = True


class Item:
    def __init__(self, x, y, is_main=False):
        self.x = x
        self.y = y
        self.is_main = is_main
        self.radius = CELL_SIZE // 3
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


class Player:
    def __init__(self, pos, speed):
        self.x = pos[0] * CELL_SIZE
        self.y = pos[1] * CELL_SIZE
        self.speed = speed
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
        if dx != 0 and dy != 0:
            dx *= 0.7071
            dy *= 0.7071
        nx = self.x + dx * self.speed
        ny = self.y + dy * self.speed
        next_rect = pygame.Rect(int(nx), int(ny) + INFO_BAR_HEIGHT, self.size, self.size)
        can_move = True
        for ob in obstacles.values():
            if next_rect.colliderect(ob.rect):
                can_move = False
                break
        if can_move and 0 <= nx < CELL_SIZE * 18 - self.size and 0 <= ny < CELL_SIZE * 18 - self.size:
            self.x = nx
            self.y = ny
            self.rect.x = int(self.x)
            self.rect.y = int(self.y) + INFO_BAR_HEIGHT


class Zombie:
    def __init__(self, pos, attack, speed):
        self.x = pos[0] * CELL_SIZE
        self.y = pos[1] * CELL_SIZE
        self.attack = attack
        self.speed = speed
        self.size = CELL_SIZE - 6
        self.rect = pygame.Rect(self.x, self.y + INFO_BAR_HEIGHT, self.size, self.size)

    @property
    def pos(self):
        return int((self.x + self.size // 2) // CELL_SIZE), int((self.y + self.size // 2) // CELL_SIZE)

    def move_and_attack(self, player, obstacles, game_state, attack_interval=0.5, dt=1 / 60):
        if not hasattr(self, "attack_timer"):
            self.attack_timer = 0
        self.attack_timer += dt
        dx = player.x - self.x
        dy = player.y - self.y
        speed = self.speed
        dirs = []

        def sign(v):
            return (v > 0) - (v < 0)

        if abs(dx) > abs(dy):
            dirs = [(sign(dx), 0), (0, sign(dy)), (sign(dx), sign(dy)), (-sign(dx), 0), (0, -sign(dy))]
        else:
            dirs = [(0, sign(dy)), (sign(dx), 0), (sign(dx), sign(dy)), (0, -sign(dy)), (-sign(dx), 0)]
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
                break
