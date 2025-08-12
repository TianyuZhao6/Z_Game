import random
from .entities import MainBlock, Obstacle, Item

LEVELS = [
    {"obstacle_count": 15, "item_count": 3, "zombie_count": 1, "block_hp": 10, "zombie_types": ["basic"],
     "reward": "zombie_fast"},
    {"obstacle_count": 18, "item_count": 4, "zombie_count": 2, "block_hp": 15, "zombie_types": ["basic", "strong"],
     "reward": "zombie_strong"},
]

DESTRUCTIBLE_RATIO = 0.3
OBSTACLE_HEALTH = 20


def is_not_edge(pos, grid_size):
    x, y = pos
    return 1 <= x < grid_size - 1 and 1 <= y < grid_size - 1


def get_level_config(level):
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


def generate_game_entities(grid_size, obstacle_count, item_count, zombie_count, main_block_hp):
    all_positions = [(x, y) for x in range(grid_size) for y in range(grid_size)]
    corners = [(0, 0), (0, grid_size - 1), (grid_size - 1, 0), (grid_size - 1, grid_size - 1)]
    forbidden = set(corners)

    def pick_valid_positions(min_distance, count):
        empty = [p for p in all_positions if p not in forbidden]
        while True:
            picks = random.sample(empty, count + 1)
            player_pos, zombies = picks[0], picks[1:]
            if all(abs(player_pos[0] - z[0]) + abs(player_pos[1] - z[1]) >= min_distance for z in zombies):
                return player_pos, zombies

    player_pos, zombie_pos_list = pick_valid_positions(min_distance=5, count=zombie_count)
    forbidden |= {player_pos}
    forbidden |= set(zombie_pos_list)
    main_item_candidates = [p for p in all_positions if p not in forbidden and is_not_edge(p, grid_size)]
    main_item_pos = random.choice(main_item_candidates)
    forbidden.add(main_item_pos)
    obstacles = {main_item_pos: MainBlock(main_item_pos[0], main_item_pos[1], health=main_block_hp)}
    rest_obstacle_candidates = [p for p in all_positions if p not in forbidden]
    rest_count = obstacle_count - 1
    rest_obstacle_positions = random.sample(rest_obstacle_candidates, rest_count)
    destructible_count = int(rest_count * DESTRUCTIBLE_RATIO)
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
