"""Worldgen, pathfinding, and collision helpers extracted from ZGame.py."""

from __future__ import annotations

import heapq
import math
import random
from collections import deque
from queue import PriorityQueue
from typing import Dict, List, Tuple

import pygame


def install(game):
    def _expanded_block_mask(obstacles: dict, grid_size: int, radius_px: int) -> list:
        """Return an expanded blocked-cell mask (True = blocked)."""
        radius_cells = max(1, int(math.ceil(radius_px / (game.CELL_SIZE * 0.5))))
        mask = [[False] * grid_size for _ in range(grid_size)]
        for gx, gy in obstacles.keys():
            mask[gy][gx] = True
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
        """Walk only on False cells and report whether an outer edge is reachable."""
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
                    seen.add((nx, ny))
                    q.append((nx, ny))
        return False

    def ensure_passage_budget(obstacles: dict, grid_size: int, player_spawn: tuple, tries: int = 8):
        """
        If the player spawn cannot reach the map edge, remove destructibles
        until a route exists or the retry budget is exhausted.
        """
        destructibles = [pos for pos, ob in obstacles.items() if getattr(ob, "type", "") == "Destructible"]
        for _ in range(tries):
            mask = _expanded_block_mask(obstacles, grid_size, game.NAV_CLEAR_RADIUS)
            if _reachable_to_edge(player_spawn, mask):
                return
            if not destructibles:
                break
            pos = random.choice(destructibles)
            destructibles.remove(pos)
            obstacles.pop(pos, None)

    def heuristic(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def a_star_search(graph, start: Tuple[int, int], goal: Tuple[int, int], obstacles):
        frontier = PriorityQueue()
        frontier.put((0, start))
        came_from = {start: None}
        cost_so_far = {start: 0}
        while not frontier.empty():
            _, current = frontier.get()
            if current == goal:
                break
            for neighbor in graph.neighbors(current):
                new_cost = cost_so_far[current] + graph.cost(current, neighbor)
                if neighbor in obstacles:
                    obstacle = obstacles[neighbor]
                    if obstacle.type == "Indestructible":
                        continue
                    if obstacle.type == "Destructible":
                        k_factor = math.ceil(obstacle.health / game.ENEMY_ATTACK) * 0.1
                        new_cost = cost_so_far[current] + 1 + k_factor
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
        if level < len(game.LEVELS):
            return game.LEVELS[level]
        return {
            "obstacle_count": 20 + level,
            "item_count": 5,
            "enemy_count": min(5, 1 + level // 3),
            "block_hp": int(10 * 1.2 ** (level - len(game.LEVELS) + 1)),
            "enemy_types": ["basic", "strong", "fire"][level % 3:],
        }

    def reconstruct_path(came_from: Dict, start: Tuple[int, int], goal: Tuple[int, int]) -> List[Tuple[int, int]]:
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

    def generate_game_entities(
        grid_size: int,
        obstacle_count: int,
        item_count: int,
        enemy_count: int,
        main_block_hp: int,
        level_idx: int = 0,
    ):
        """
        Generate entities with map-fill: obstacle clusters, ample items, and
        non-blocking decorations. Main block remains removed.
        """
        del item_count, main_block_hp, level_idx
        all_positions = [(x, y) for x in range(grid_size) for y in range(grid_size)]
        corners = [(0, 0), (0, grid_size - 1), (grid_size - 1, 0), (grid_size - 1, grid_size - 1)]
        forbidden = set(corners)

        def pick_valid_positions(min_distance: int, count: int):
            empty = [p for p in all_positions if p not in forbidden]
            while True:
                picks = random.sample(empty, count + 1)
                player_pos, enemies = picks[0], picks[1:]
                if all(abs(player_pos[0] - z[0]) + abs(player_pos[1] - z[1]) >= min_distance for z in enemies):
                    return player_pos, enemies

        center_pos = (grid_size // 2, grid_size // 2)
        if center_pos not in forbidden:
            player_pos = center_pos
            far_candidates = [
                p
                for p in all_positions
                if p not in forbidden and (abs(p[0] - center_pos[0]) + abs(p[1] - center_pos[1]) >= 6)
            ]
            enemy_pos_list = random.sample(far_candidates, enemy_count)
        else:
            player_pos, enemy_pos_list = pick_valid_positions(min_distance=5, count=enemy_count)
        forbidden |= {player_pos}
        forbidden |= set(enemy_pos_list)

        safe_radius = 1
        px, py = player_pos
        for dx in range(-safe_radius, safe_radius + 1):
            for dy in range(-safe_radius, safe_radius + 1):
                nx, ny = px + dx, py + dy
                if 0 <= nx < grid_size and 0 <= ny < grid_size:
                    forbidden.add((nx, ny))

        obstacles = {}
        area = grid_size * grid_size
        target_obstacles = max(obstacle_count, int(area * game.OBSTACLE_DENSITY))
        rest_needed = target_obstacles
        base_candidates = [p for p in all_positions if p not in forbidden]
        random.shuffle(base_candidates)
        placed = 0

        cluster_seeds = base_candidates[: max(1, rest_needed // 6)]
        for seed in cluster_seeds:
            if placed >= rest_needed:
                break
            cluster_size = random.randint(3, 6)
            wave = [seed]
            visited = set()
            while wave and placed < rest_needed and len(visited) < cluster_size:
                cur = wave.pop()
                if cur in visited or cur in obstacles or cur in forbidden:
                    continue
                visited.add(cur)
                typ = "Indestructible" if random.random() < 0.65 else "Destructible"
                hp = game.OBSTACLE_HEALTH if typ == "Destructible" else None
                obstacles[cur] = game.Obstacle(cur[0], cur[1], typ, health=hp)
                placed += 1
                x, y = cur
                neigh = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
                random.shuffle(neigh)
                for nb in neigh:
                    if 0 <= nb[0] < grid_size and 0 <= nb[1] < grid_size and nb not in visited:
                        wave.append(nb)

        if placed < rest_needed:
            more = [p for p in base_candidates if p not in obstacles]
            random.shuffle(more)
            for pos in more[: (rest_needed - placed)]:
                typ = "Indestructible" if random.random() < 0.5 else "Destructible"
                hp = game.OBSTACLE_HEALTH if typ == "Destructible" else None
                obstacles[pos] = game.Obstacle(pos[0], pos[1], typ, health=hp)

        forbidden |= set(obstacles.keys())
        item_target = random.randint(9, 19)
        item_candidates = [p for p in all_positions if p not in forbidden]
        items = [
            game.Item(x, y, is_main=False)
            for (x, y) in random.sample(item_candidates, min(len(item_candidates), item_target))
        ]

        decor_target = int(area * game.DECOR_DENSITY)
        decor_candidates = [p for p in all_positions if p not in forbidden]
        random.shuffle(decor_candidates)
        decorations = decor_candidates[:decor_target]
        return obstacles, items, player_pos, enemy_pos_list, [], decorations

    def build_graph(grid_size: int, obstacles) -> object:
        graph = game.Graph()
        for x in range(grid_size):
            for y in range(grid_size):
                current_pos = (x, y)
                if current_pos in obstacles and obstacles[current_pos].type == "Indestructible":
                    continue
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    neighbor_pos = (x + dx, y + dy)
                    if not (0 <= neighbor_pos[0] < grid_size and 0 <= neighbor_pos[1] < grid_size):
                        continue
                    if neighbor_pos in obstacles and obstacles[neighbor_pos].type == "Indestructible":
                        continue
                    weight = 1
                    if neighbor_pos in obstacles and obstacles[neighbor_pos].type == "Destructible":
                        weight = 10
                    graph.add_edge(current_pos, neighbor_pos, weight)
        return graph

    def build_flow_field(grid_size, obstacles, goal_xy, pad=0):
        inf = 10 ** 9
        goal_x, goal_y = goal_xy
        hard = {
            (gx, gy)
            for (gx, gy), ob in obstacles.items()
            if getattr(ob, "type", "") in ("Indestructible", "MainBlock")
        }
        blocked = set(hard)
        if pad > 0:
            for gx, gy in list(hard):
                for dx in range(-pad, pad + 1):
                    for dy in range(-pad, pad + 1):
                        nx, ny = gx + dx, gy + dy
                        if 0 <= nx < grid_size and 0 <= ny < grid_size:
                            blocked.add((nx, ny))

        def cell_cost(x, y):
            if (x, y) in blocked:
                return inf
            ob = obstacles.get((x, y))
            if ob and getattr(ob, "type", "") == "Destructible":
                return 4
            return 1

        dist = [[inf] * grid_size for _ in range(grid_size)]
        next_step = [[None] * grid_size for _ in range(grid_size)]
        pq = []
        if 0 <= goal_x < grid_size and 0 <= goal_y < grid_size and cell_cost(goal_x, goal_y) < inf:
            dist[goal_x][goal_y] = 0
            heapq.heappush(pq, (0, goal_x, goal_y))
        while pq:
            d, x, y = heapq.heappop(pq)
            if d != dist[x][y]:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < grid_size and 0 <= ny < grid_size):
                    continue
                c = cell_cost(nx, ny)
                if c >= inf:
                    continue
                nd = d + c
                if nd < dist[nx][ny]:
                    dist[nx][ny] = nd
                    next_step[nx][ny] = (x, y)
                    heapq.heappush(pq, (nd, nx, ny))
        return dist, next_step

    def crush_blocks_in_rect(sweep_rect: pygame.Rect, game_state) -> int:
        """Remove any obstacle cell whose rect intersects the given sweep rect."""
        removed = 0
        if not hasattr(game_state, "obstacles") or not game_state.obstacles:
            return 0
        for gp, ob in list(game_state.obstacles.items()):
            if sweep_rect.colliderect(ob.rect):
                del game_state.obstacles[gp]
                if hasattr(game_state, "mark_nav_dirty"):
                    game_state.mark_nav_dirty()
                removed += 1
        return removed

    def collide_and_slide_circle(entity, obstacles_iter, dx, dy):
        """Sweep/slide circle collision using axis-separated expanded rects."""
        entity._hit_ob = None
        if getattr(entity, "can_crush_all_blocks", False) and not hasattr(entity, "_crush_queue"):
            entity._crush_queue = []
        r = getattr(entity, "radius", max(8, game.CELL_SIZE // 3))
        size = entity.size
        cx0 = entity.x + size * 0.5
        cy0 = entity.y + size * 0.5 + game.INFO_BAR_HEIGHT

        cx1 = cx0 + dx
        hit_x = None
        if dx > 0:
            min_left = None
            for ob in obstacles_iter:
                if getattr(ob, "nonblocking", False):
                    continue
                exp = ob.rect.inflate(r * 2, r * 2)
                if exp.top <= cy0 <= exp.bottom and cx0 <= exp.left <= cx1:
                    if (min_left is None) or (exp.left < min_left[0]):
                        min_left = (exp.left, ob)
            if min_left:
                cx1 = min_left[0]
                hit_x = min_left[1]
                if getattr(entity, "can_crush_all_blocks", False):
                    entity._crush_queue.append(hit_x)
        elif dx < 0:
            max_right = None
            for ob in obstacles_iter:
                if getattr(ob, "nonblocking", False):
                    continue
                exp = ob.rect.inflate(r * 2, r * 2)
                if exp.top <= cy0 <= exp.bottom and cx1 <= exp.right <= cx0:
                    if (max_right is None) or (exp.right > max_right[0]):
                        max_right = (exp.right, ob)
            if max_right:
                cx1 = max_right[0]
                hit_x = max_right[1]
                if getattr(entity, "can_crush_all_blocks", False):
                    entity._crush_queue.append(hit_x)
        if hit_x is not None:
            entity._hit_ob = hit_x
        x_min, y_min, x_max, y_max = game.play_bounds_for_circle(r)
        cx1 = max(x_min, min(cx1, x_max))
        entity.x = cx1 - size * 0.5

        cx0 = entity.x + size * 0.5
        cy0 = entity.y + size * 0.5 + game.INFO_BAR_HEIGHT
        cy1 = cy0 + dy
        hit_y = None
        if dy > 0:
            min_top = None
            for ob in obstacles_iter:
                if getattr(ob, "nonblocking", False):
                    continue
                exp = ob.rect.inflate(r * 2, r * 2)
                if exp.left <= cx0 <= exp.right and cy0 <= exp.top <= cy1:
                    if (min_top is None) or (exp.top < min_top[0]):
                        min_top = (exp.top, ob)
            if min_top:
                cy1 = min_top[0]
                hit_y = min_top[1]
                if getattr(entity, "can_crush_all_blocks", False):
                    try:
                        entity._crush_queue.append(hit_y)
                    except Exception:
                        pass
        elif dy < 0:
            max_bottom = None
            for ob in obstacles_iter:
                if getattr(ob, "nonblocking", False):
                    continue
                exp = ob.rect.inflate(r * 2, r * 2)
                if exp.left <= cx0 <= exp.right and cy1 <= exp.bottom <= cy0:
                    if (max_bottom is None) or (exp.bottom > max_bottom[0]):
                        max_bottom = (exp.bottom, ob)
            if max_bottom:
                cy1 = max_bottom[0]
                hit_y = max_bottom[1]
                if getattr(entity, "can_crush_all_blocks", False):
                    try:
                        entity._crush_queue.append(hit_y)
                    except Exception:
                        pass
        if hit_y is not None:
            entity._hit_ob = hit_y
        x_min, y_min, x_max, y_max = game.play_bounds_for_circle(r)
        cy1 = max(y_min, min(cy1, y_max))
        entity.y = cy1 - size * 0.5 - game.INFO_BAR_HEIGHT
        entity.rect.x = int(entity.x)
        entity.rect.y = int(entity.y) + game.INFO_BAR_HEIGHT

    return (
        _expanded_block_mask,
        _reachable_to_edge,
        ensure_passage_budget,
        collide_and_slide_circle,
        heuristic,
        a_star_search,
        is_not_edge,
        get_level_config,
        reconstruct_path,
        generate_game_entities,
        build_graph,
        build_flow_field,
        crush_blocks_in_rect,
    )
