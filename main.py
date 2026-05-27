import asyncio
import sys
import traceback


def _show_fatal_error(traceback_text: str) -> None:
    try:
        import pygame
    except Exception:
        return

    try:
        if not pygame.get_init():
            pygame.init()
        screen = pygame.display.get_surface()
        if screen is None:
            screen = pygame.display.set_mode((1280, 720))
        screen.fill((35, 10, 10))
        title_font = pygame.font.SysFont(None, 40)
        body_font = pygame.font.SysFont("Consolas", 20)
        title = title_font.render("Startup Error", True, (255, 210, 210))
        screen.blit(title, (24, 20))
        y = 80
        for line in traceback_text.splitlines()[-24:]:
            surf = body_font.render(line[:140], True, (255, 230, 230))
            screen.blit(surf, (24, y))
            y += surf.get_height() + 4
            if y > 690:
                break
        pygame.display.flip()
    except Exception:
        return


if __name__ == "__main__":
    try:
        from ZGame import app_main

        asyncio.run(app_main())
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        _show_fatal_error(tb)
        if sys.platform == "emscripten":
            async def _hold_error_screen() -> None:
                while True:
                    await asyncio.sleep(1)

            asyncio.run(_hold_error_screen())
        raise
