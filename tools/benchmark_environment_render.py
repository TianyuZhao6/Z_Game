"""Fixed render-only fixture for matched CPython/pygbag measurements.

Run locally with Python, or substitute this file for assets/main.py in a COPY
of the web APK. Never modify the playable bundle or the user's save. Reports
cold cost separately, then 60 warmed frames with no recording/game profiler.
This isolates rendering; it is not a live-combat FPS benchmark.
"""
import asyncio
import json
import os
from pathlib import Path
import random
import sys
import time

if sys.platform != 'emscripten':
    os.environ.setdefault('SDL_VIDEODRIVER','dummy')
    os.environ.setdefault('SDL_AUDIODRIVER','dummy')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pygame
import ZGame as game
from zgame import render_runtime, summons, browser


async def main():
    pygame.init()
    # Both runtimes exercise the SAME full web-renderer path and quality.
    game.IS_WEB = render_runtime.IS_WEB = True
    browser.apply_web_quality_profile(game,'full',reason='fixed-fixture')
    screen=pygame.display.set_mode((1280,720))
    game.VIEW_W,game.VIEW_H=screen.get_size()
    game.reset_run_state()
    game.clear_menu_transition_state()
    game._web_profiler=None
    game.current_level=0
    random.seed(947)
    obs,items,pos,positions,_,decor=game.generate_game_entities(game.GRID_SIZE,70,10,6,game.MAIN_BLOCK_HEALTH)
    state=game.GameState(obs,items,[],decor)
    state.current_level=0
    player=game.Player(pos)
    enemies=[game.Enemy(p,speed=game.ENEMY_SPEED,ztype='basic') for p in positions]
    for _ in range(3): summons.purchase(game.META)
    summons.start_level(game,state,player)
    rows=[]
    original_ticks=pygame.time.get_ticks
    for label,position,region,moving in (
        ('center',(18,18),'Domain of Wind',False),
        ('edge',(20,4),'Domain of Wind',False),
        ('moving-edge',(20,4),'Domain of Wind',True),
        ('forest',(18,18),'Misty Forest',False)):
        player=game.Player(position)
        state.biome_active=region
        state.fog_enabled=region=='Misty Forest'
        state._fog_biome_forced=state.fog_enabled
        companion=state.companions[0]
        companion.x,companion.y=player.x+game.CELL_SIZE*2,player.y
        companion.rect.topleft=(round(companion.x),round(companion.y)+game.INFO_BAR_HEIGHT)
        base=game.calculate_iso_camera(*player.rect.center)
        costs=[]
        for frame in range(69):
            ticks=1000+frame*17
            pygame.time.get_ticks=lambda: ticks
            camera=(base[0]+frame*2,base[1]+frame) if moving else base
            pygame.event.pump()
            start=time.perf_counter()
            game.render_game_iso(screen,state,player,enemies,[],[],override_cam=camera,copy_frame=False)
            pygame.display.flip()
            costs.append((time.perf_counter()-start)*1000)
            await asyncio.sleep(0)
        warm=sorted(costs[9:])
        rows.append(dict(scene=label,cold_ms=round(costs[0],3),
                         warm_mean_ms=round(sum(warm)/len(warm),3),
                         warm_p50_ms=round(warm[30],3),warm_p95_ms=round(warm[57],3)))
    pygame.time.get_ticks=original_ticks
    result=dict(runtime=sys.platform,viewport=[1280,720],seed=947,quality='full',
                walls=len(obs),enemies=len(enemies),frames_per_scene=60,scenes=rows,
                recording=False,game_profiler=False)
    print('__ENV_RENDER_REVIEW__'+json.dumps(result),flush=True)
    if sys.platform=='emscripten':
        import platform
        platform.window.__env_render_review=json.dumps(result)
        while True: await asyncio.sleep(1)
    pygame.quit()


if __name__=='__main__':
    asyncio.run(main())
