import pygame


def show_start_menu(screen):
    background = pygame.image.load("assets/start_bg.png").convert()
    background = pygame.transform.scale(background, screen.get_size())
    start_button_img = pygame.image.load("assets/start_button.png").convert_alpha()
    start_button_rect = start_button_img.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2))

    while True:
        screen.blit(background, (0, 0))
        screen.blit(start_button_img, start_button_rect)
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if start_button_rect.collidepoint(event.pos):
                    return True
