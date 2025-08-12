class GameState:
    """管理游戏状态和进度"""

    def __init__(self, obstacles, items, main_item_pos):
        self.obstacles = obstacles  # dict: pos -> Obstacle
        self.items = items          # list[Item]
        self.destructible_count = self.count_destructible_obstacles()
        self.main_item_pos = main_item_pos

    def count_destructible_obstacles(self):
        return sum(1 for obs in self.obstacles.values() if obs.type == "Destructible")

    def collect_item(self, player_rect):
        for item in list(self.items):
            if player_rect.colliderect(item.rect):
                if item.is_main and any(getattr(ob, "is_main_block", False) for ob in self.obstacles.values()):
                    return False  # 主障碍未破坏不能捡主道具
                self.items.remove(item)
                return True
        return False

    def destroy_obstacle(self, pos):
        if pos in self.obstacles:
            if self.obstacles[pos].type == "Destructible":
                self.destructible_count -= 1
            del self.obstacles[pos]
