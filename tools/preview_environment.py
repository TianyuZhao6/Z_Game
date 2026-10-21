"""Render the actual random-map game scene without touching the user's save.

Run python tools/preview_environment.py; outputs actual renderer captures and
timings to TEMP/environment-preview. --visible opens a review window.
"""
import argparse
import os
from pathlib import Path
import random
import sys
import time
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument('--visible', action='store_true')
parser.add_argument('--reference-review', action='store_true',
                    help='Capture center/edge compositions and a breathing animation from the real renderer.')
args = parser.parse_args()
if not args.visible:
    os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pygame
import ZGame as game
from zgame import neural_environment as art, render_runtime, summons

pygame.init()
screen = pygame.display.set_mode((1536,1024) if args.reference_review else (1280,720))
game.VIEW_W, game.VIEW_H = screen.get_size()
game.reset_run_state()
random.seed(41)
obstacles,items,pos,enemy_positions,_,decor = game.generate_game_entities(
    game.GRID_SIZE, 70, 10, 6, game.MAIN_BLOCK_HEALTH)
state = game.GameState(obstacles,items,[],decor)
state.current_level = 0
player = game.Player(pos)
enemies = [game.Enemy(p,speed=game.ENEMY_SPEED,ztype='basic') for p in enemy_positions]
for _ in range(3):
    summons.purchase(game.META)
summons.start_level(game,state,player)
skull = state.companions[0]
skull.x = player.x + game.CELL_SIZE*2
skull.y = player.y
skull.rect.topleft = (round(skull.x),round(skull.y)+game.INFO_BAR_HEIGHT)
out = ROOT/'TEMP'/'environment-preview'
out.mkdir(parents=True,exist_ok=True)
if args.reference_review:
    # Normal generated collision layout. Only review camera/actor placement and
    # frozen times are controlled; no painted screenshot or replacement map.
    state.biome_active = art.DEFAULT_REGION
    state.fog_enabled = False
    state.items.clear()
    for label,pos in (('center',(18,18)),('abyss',(20,4))):
        free = min((p for p in ((x,y) for x in range(2,34) for y in range(2,34))
                    if p not in state.obstacles),key=lambda p:abs(p[0]-pos[0])+abs(p[1]-pos[1]))
        player = game.Player(free)
        skull.x,skull.y = player.x+game.CELL_SIZE*2,player.y
        skull.rect.topleft = (round(skull.x),round(skull.y)+game.INFO_BAR_HEIGHT)
        with patch.object(game,'IS_WEB',False),patch.object(render_runtime,'IS_WEB',False), \
             patch.object(pygame.time,'get_ticks',return_value=1600):
            game.render_game_iso(screen,state,player,[],[],[],copy_frame=False)
        pygame.image.save(screen,str(out/f'refined-{label}.png'))
    # A captured frame sequence demonstrates animation independently of the
    # static floor; animation encoding changes no game artwork.
    from PIL import Image
    frames=[]
    for ticks in range(0,6400,200):
        with patch.object(pygame.time,'get_ticks',return_value=ticks):
            game.render_game_iso(screen,state,player,[],[],[],copy_frame=False)
        frames.append(Image.frombytes('RGB',screen.get_size(),pygame.image.tobytes(screen,'RGB')))
    frames[0].save(out/'refined-breathing.webp',save_all=True,append_images=frames[1:],
                   duration=200,loop=0,quality=82,method=4)
    print('Reference review captures:',out)
    pygame.quit()
    sys.exit(0)
for biome in art.REGIONS:
    state.biome_active = biome
    # Presentation comparison excludes fog/hazards, whose gameplay is unchanged.
    state.fog_enabled = False
    for lite in (False,True):
        renderer = game.render_game_iso_web_lite if lite else game.render_game_iso
        with patch.object(game,'IS_WEB',lite), patch.object(render_runtime,'IS_WEB',lite), \
             patch.object(game,'WEB_ENABLE_FOG',False), patch.object(pygame.time,'get_ticks',return_value=1000):
            renderer(screen,state,player,enemies,[],[],copy_frame=False)
            times = []
            for _ in range(15):
                start = time.perf_counter()
                renderer(screen,state,player,enemies,[],[],copy_frame=False)
                times.append((time.perf_counter()-start)*1000)
            name = art.region_name(biome).lower()+('-lite' if lite else '')
            pygame.image.save(screen,str(out/f'{name}.png'))
            print(f'{name}: warm render {sum(times)/len(times):.1f} ms')
if args.visible:
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or ev.type == pygame.KEYDOWN:
                running = False
        pygame.display.flip()
        pygame.time.wait(30)
pygame.quit()
