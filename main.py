import pygame
from core.level import get_level_config, generate_game_entities
from core.state import GameState
from core.entities import Player, Zombie
from ui.menu import show_start_menu
from ui.game_render import render_game
from ui.result_screen import render_game_result

from core.utils import CELL_SIZE, INFO_BAR_HEIGHT

GRID_SIZE = 18
WINDOW_SIZE = GRID_SIZE * CELL_SIZE
TOTAL_HEIGHT = WINDOW_SIZE + INFO_BAR_HEIGHT
PLAYER_SPEED = 5
ZOMBIE_SPEED = 2


def main_game_loop(config, zombie_cards_collected):
    pygame.display.set_caption("Zombie Card Game")
    screen = pygame.display.set_mode((WINDOW_SIZE, TOTAL_HEIGHT))
    clock = pygame.time.Clock()
    restart_img = pygame.image.load("assets/restart.png").convert_alpha()
    next_img = pygame.image.load("assets/next.png").convert_alpha()
    icon_size = 64
    restart_img = pygame.transform.smoothscale(restart_img, (icon_size, icon_size))
    next_img = pygame.transform.smoothscale(next_img, (icon_size, icon_size))

    obstacles, items, player_start, zombie_starts, main_item_list = generate_game_entities(
        grid_size=GRID_SIZE,
        obstacle_count=config["obstacle_count"],
        item_count=config["item_count"],
        zombie_count=config["zombie_count"],
        main_block_hp=config["block_hp"]
    )
    game_state = GameState(obstacles, items, main_item_list)
    player = Player(player_start, speed=PLAYER_SPEED)
    zombies = [Zombie(pos, attack=10, speed=ZOMBIE_SPEED) for pos in zombie_starts]
    running = True
    game_result = None

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()

        keys = pygame.key.get_pressed()
        player.move(keys, game_state.obstacles)
        game_state.collect_item(player.rect)
        for zombie in zombies:
            zombie.move_and_attack(player, list(game_state.obstacles.values()), game_state)
            player_rect = pygame.Rect(int(player.x), int(player.y) + INFO_BAR_HEIGHT, player.size, player.size)
            if zombie.rect.colliderect(player_rect):
                game_result = "fail"
                running = False
        if not game_state.items:
            game_result = "success"
            running = False
        render_game(screen, game_state, player, zombies)
        pygame.display.flip()
        clock.tick(60)
    restart_rect, next_rect = render_game_result(screen, game_result, restart_img, next_img)
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if restart_rect.collidepoint(event.pos):
                    return "restart", None
                if next_rect.collidepoint(event.pos) and game_result == "success":
                    return "next", config.get("reward", None)

if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_SIZE, TOTAL_HEIGHT))
    if not show_start_menu(screen):
        exit()
    current_level = 0
    zombie_cards_collected = set()
    while True:
        config = get_level_config(current_level)
        result, reward = main_game_loop(config, zombie_cards_collected)
        if result == "next":
            current_level += 1
            if reward:
                zombie_cards_collected.add(reward)
                print(f"获得新卡牌：{reward}")
        elif result == "restart":
            continue
        else:
            break
