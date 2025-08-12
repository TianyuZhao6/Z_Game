import pygame
from core.utils import CELL_SIZE, INFO_BAR_HEIGHT


def render_game(screen, game_state, player, zombies):
    screen.fill((20, 20, 20))
    pygame.draw.rect(screen, (0, 0, 0), (0, 0, screen.get_width(), INFO_BAR_HEIGHT))
    font = pygame.font.SysFont(None, 28)
    item_txt = font.render(f"ITEMS: {len(game_state.items)}", True, (255, 255, 80))
    screen.blit(item_txt, (12, 12))

    for y in range(18):
        for x in range(18):
            rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE + INFO_BAR_HEIGHT, CELL_SIZE, CELL_SIZE)
            pygame.draw.rect(screen, (50, 50, 50), rect, 1)

    for item in game_state.items:
        color = (255, 255, 100) if item.is_main else (255, 255, 0)
        pygame.draw.circle(screen, color, item.center, item.radius)

    pygame.draw.rect(screen, (0, 255, 0), player.rect)

    for zombie in zombies:
        pygame.draw.rect(screen, (255, 60, 60), zombie.rect)

    for obstacle in game_state.obstacles.values():
        is_main = hasattr(obstacle, 'is_main_block') and obstacle.is_main_block
        if is_main:
            color = (255, 220, 80)
        elif obstacle.type == "Indestructible":
            color = (120, 120, 120)
        else:
            color = (200, 80, 80)
        pygame.draw.rect(screen, color, obstacle.rect)
        if obstacle.type == "Destructible":
            font = pygame.font.SysFont(None, 30)
            health_text = font.render(str(obstacle.health), True, (255, 255, 255))
            screen.blit(health_text, (obstacle.rect.x + 6, obstacle.rect.y + 8))
        if is_main:
            star = pygame.font.SysFont(None, 32).render("★", True, (255, 255, 120))
            screen.blit(star, (obstacle.rect.x + 8, obstacle.rect.y + 8))
