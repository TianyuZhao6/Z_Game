"""Paired before/after vessel-layer timings, alternating order to limit drift.

Like benchmark_environment_render.py, this may replace main.py in an isolated
web fixture. It measures the changed branch layer, not whole-game frame rate.
The before path is the individual SDL2/RLE stamps used before phase batching.
"""
import asyncio
import json
import math
import os
from pathlib import Path
import random
import sys
import time

if sys.platform != 'emscripten':
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pygame
import ZGame as game
from zgame import neural_environment as art


async def main():
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    random.seed(947)
    obs, *_ = game.generate_game_entities(game.GRID_SIZE, 70, 10, 6, game.MAIN_BLOCK_HEALTH)
    state = game.GameState(obs, [], [], [])
    raw = []
    batch = art.batch_network_stamps
    def record(stamps):
        raw[:] = [(im.copy(), pos, phase) for im, pos, phase in stamps]
        return batch(stamps)
    art.batch_network_stamps = record
    width, height = game.ISO_CELL_W, game.ISO_CELL_H
    x0 = -game.GRID_SIZE * width // 2
    rows = []
    for region in ('Domain of Wind', 'Misty Forest'):
        _, grouped = art.network_material(game.GRID_SIZE, width, height, game.INFO_BAR_HEIGHT,
                                         (game.GRID_SIZE*width+1, game.GRID_SIZE*height+81),
                                         x0, 0, region, state.network_seed, state.network_obstacles)
        camera = (-640, game.GRID_SIZE*height/2-360)
        offset = (x0-camera[0], -camera[1])
        viewport = screen.get_rect()
        visible = lambda items: [(im, im.get_rect(topleft=(pos[0]+offset[0], pos[1]+offset[1])), phase)
                                for im, pos, phase in items
                                if im.get_rect(topleft=(pos[0]+offset[0], pos[1]+offset[1])).colliderect(viewport)]
        before, after = visible(raw), visible(grouped)
        modes = ('before', 'after', 'after_sdl', 'after_rle')
        variants = {mode: [(image.copy(), rect, phase) for image, rect, phase in after]
                    for mode in modes[1:]}
        costs = {mode: [] for mode in modes}
        for frame in range(90):
            ticks = 1000+frame*17
            for mode in (modes if frame%2 else modes[::-1]):
                screen.fill((30,40,60))
                started = time.perf_counter()
                if mode == 'before':
                    for image, rect, phase in before:
                        image.set_alpha(art.branch_alpha(phase,ticks),pygame.RLEACCEL)
                        screen.blit(image,rect,special_flags=pygame.BLEND_ALPHA_SDL2)
                else:
                    alphas = {i*math.tau/art.NETWORK_PHASES: art.branch_alpha(i*math.tau/art.NETWORK_PHASES,ticks)
                              for i in range(art.NETWORK_PHASES)}
                    operations = []
                    for image, rect, phase in variants[mode]:
                        image.set_alpha(alphas[phase],pygame.RLEACCEL if mode=='after_rle' else 0)
                        operations.append((image,rect,None,0 if mode=='after' else pygame.BLEND_ALPHA_SDL2))
                    screen.blits(operations,doreturn=False)
                elapsed = (time.perf_counter()-started)*1000
                if frame >= 10: costs[mode].append(elapsed)
            await asyncio.sleep(0)
        row = dict(region=region,visible_before=len(before),visible_after=len(after),
                   total_before=len(raw),total_after=len(grouped))
        for mode, values in costs.items():
            values.sort()
            row[mode] = dict(mean_ms=round(sum(values)/len(values),3),
                             p50_ms=round(values[len(values)//2],3),p95_ms=round(values[int(len(values)*.95)],3))
        rows.append(row)
    result = dict(runtime=sys.platform,seed=947,viewport=[1280,720],samples_per_mode=80,
                  scope='branch layer only; same geometry, alternating measurement order',scenes=rows)
    print('__NETWORK_BATCH_REVIEW__'+json.dumps(result),flush=True)
    if sys.platform == 'emscripten':
        import platform
        platform.window.__env_render_review=json.dumps(result)
        while True: await asyncio.sleep(1)
    pygame.quit()


if __name__ == '__main__':
    asyncio.run(main())
