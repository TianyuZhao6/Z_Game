import pygame


def render_game_result(screen, result, restart_img, next_img):
    screen.fill((0, 0, 0))
    font = pygame.font.SysFont(None, 80)
    if result == "success":
        text = font.render("CONGRATULATIONS!", True, (0, 255, 0))
    elif result == "fail":
        text = font.render("GAME OVER!", True, (255, 60, 60))
    else:
        text = font.render("Result Unknown", True, (200, 200, 200))

    text_rect = text.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 - 60))
    screen.blit(text, text_rect)

    margin = 40
    icon_size = 64
    restart_pos = (margin, screen.get_width() - icon_size - margin)
    restart_rect = pygame.Rect(restart_pos, (icon_size, icon_size))
    screen.blit(restart_img, restart_rect)
    next_pos = (margin + icon_size + 32, screen.get_width() - icon_size - margin)
    next_rect = pygame.Rect(next_pos, (icon_size, icon_size))
    screen.blit(next_img, next_rect)
    pygame.display.flip()
    return restart_rect, next_rect
