"""Desktop-only, real-renderer illumination evidence and paired profiling.

Compare against the saved checkpoint without checking out or editing its files.
The fixed-camera captures use real animation times, never forced global alpha.
"""
import argparse
from collections import defaultdict
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame
import ZGame as game
from zgame import neural_environment as art, render_runtime, summons
from zgame.vessel_network import network_geometry, breathing_profile


def baseline_module(revision):
    modules = []
    for filename in ('vessel_network', 'neural_environment'):
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader('review_'+filename, loader=None))
        code = subprocess.check_output(['git', 'show', f'{revision}:zgame/{filename}.py'], cwd=ROOT)
        exec(compile(code, f'{revision}/{filename}.py', 'exec'), module.__dict__)
        modules.append(module)
    modules[1].branch_alpha = modules[0].branch_alpha
    return modules[1], modules[0]


class Counters:
    def __init__(self): self.values = defaultdict(float)
    def counter(self, name, value): self.values[name] += value


class NetworkScreen:
    """Time compositing only, separately from lookup/culling/opacity overhead."""
    def __init__(self, surface, counters):
        self.surface, self.counters, self.first = surface, counters, True
    def get_rect(self): return self.surface.get_rect()
    def blit(self, *args, **kwargs):
        start = time.perf_counter()
        result = self.surface.blit(*args, **kwargs)
        self.counters.counter('network_base_ms' if self.first else 'network_nodes_ms', (time.perf_counter()-start)*1000)
        self.first = False
        return result
    def blits(self, *args, **kwargs):
        start = time.perf_counter()
        result = self.surface.blits(*args, **kwargs)
        self.counters.counter('network_glow_ms', (time.perf_counter()-start)*1000)
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', default='d7ecf82')
    parser.add_argument('--output', type=Path, default=ROOT/'docs/evidence/region04-shimmer')
    parser.add_argument('--profile-only', action='store_true')
    parser.add_argument('--captures-only', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    pygame.init()
    screen = pygame.display.set_mode((1280,720))
    game.VIEW_W, game.VIEW_H = screen.get_size()
    game.IS_WEB = render_runtime.IS_WEB = False
    game.reset_run_state(); game.clear_menu_transition_state(); game.current_level = 0
    random.seed(41)
    obs, items, pos, positions, _, decor = game.generate_game_entities(game.GRID_SIZE,70,10,6,game.MAIN_BLOCK_HEALTH)
    state = game.GameState(obs, [], [], decor)
    state.current_level = 0
    state.biome_active = 'Bastion of Stone'
    player = game.Player(min(((x,y) for x in range(15,22) for y in range(15,22) if (x,y) not in obs),
                             key=lambda p:abs(p[0]-18)+abs(p[1]-18)))
    for _ in range(3): summons.purchase(game.META)
    summons.start_level(game,state,player)
    skull = state.companions[0]
    skull.x,skull.y = player.x+game.CELL_SIZE*2,player.y
    skull.rect.topleft = (round(skull.x),round(skull.y)+game.INFO_BAR_HEIGHT)
    camera = game.calculate_iso_camera(*player.rect.center)
    before, old_geometry = baseline_module(args.baseline)
    modules = {'before':before,'after':art}
    paths,hubs = network_geometry(game.GRID_SIZE,'Mountain',state.network_seed,state.network_obstacles)
    assert (paths,hubs) == old_geometry.network_geometry(game.GRID_SIZE,'Mountain',state.network_seed,state.network_obstacles)
    primary = min((p for p in paths if p.main),key=lambda p:math.dist(p.points[len(p.points)//2],(18,18)))
    phase = round(primary.phase/math.tau*art.NETWORK_PHASES)%art.NETWORK_PHASES*math.tau/art.NETWORK_PHASES
    period,_ = breathing_profile(phase)
    dim = ((1.5*math.pi-phase)%math.tau)/math.tau*period*1000
    times = {'dim':round(dim),'rising':round(dim+period*250),'peak':round(dim+period*500)}
    def render(module, ticks, enemies=(), cam=camera):
        with patch.object(render_runtime,'neural_environment',module), patch.object(pygame.time,'get_ticks',return_value=ticks):
            game.render_game_iso(screen,state,player,list(enemies),[],[],override_cam=cam,copy_frame=False)
    metadata = dict(baseline=args.baseline,seed=41,region=state.biome_active,camera=camera,target_group_phase=phase,
                    period_seconds=period,times_ms=times,topology_matches_checkpoint=True)
    if not args.profile_only:
        for name,module in modules.items():
            for label,ticks in times.items():
                render(module,ticks)
                pygame.image.save(screen,str(args.output/f'{name}-{label}.png'))
        from PIL import Image
        frames=[]
        tracks=[]
        for node in hubs:
            sx=round((node.x-node.y)*game.ISO_CELL_W*.5-camera[0])
            sy=round((node.x+node.y)*game.ISO_CELL_H*.5+game.INFO_BAR_HEIGHT-camera[1])
            if node.rank==2 and 30<sx<1250 and 70<sy<690:
                tracks.append(dict(screen=[sx,sy],phase=node.phase,samples=[]))
        for ticks in range(times['dim'],times['dim']+8000,100):
            render(art,ticks)
            frames.append(Image.frombytes('RGB',screen.get_size(),pygame.image.tobytes(screen,'RGB')))
            for track in tracks:
                x,y=track['screen']
                rgb=screen.get_at((x,y))[:3]
                track['samples'].append(dict(ms=ticks,rgb=list(rgb)))
        # One continuous take. Do not create a misleading reset by looping
        # asynchronous groups whose periods do not share an eight-second cycle.
        frames[0].save(args.output/'breathing.webp',save_all=True,append_images=frames[1:],duration=100,loop=1,quality=90,method=3)
        (args.output/'breathing-metrics.json').write_text(json.dumps(tracks,indent=2),encoding='utf-8')
        # One compact overview of the established palettes, using actual renders.
        board=pygame.Surface((1280,760)); board.fill((10,14,25))
        font=pygame.font.Font(None,24)
        for index,region in enumerate(art.NETWORK_PALETTES):
            state.biome_active=region
            render(art,times['peak'])
            x,y=(index%2)*640,(index//2)*380
            board.blit(pygame.transform.smoothscale(screen,(640,360)),(x,y+20))
            label='Stone' if region=='Bastion of Stone' else art.region_name(region)
            board.blit(font.render(label,True,(205,220,244)),(x+8,y))
        pygame.image.save(board,str(args.output/'biome-palettes.png'))
        state.biome_active='Bastion of Stone'
        # Inspect actual rendered light on a quiet patch of the chosen trunk.
        # No thumbnail resize or added labels alter the capture pixels.
        x,y=primary.points[len(primary.points)//2]
        sx,sy=round((x-y)*game.ISO_CELL_W*.5-camera[0]),round((x+y)*game.ISO_CELL_H*.5+game.INFO_BAR_HEIGHT-camera[1])
        metadata['trunk_screen_point']=[sx,sy]
        (args.output/'capture-times.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    if args.captures_only:
        pygame.quit(); return
    # Enable the existing timing hooks without changing desktop feature flags.
    cells=dict(zip(game.render_game_iso.__code__.co_freevars,game.render_game_iso.__closure__))
    profiler_cell=cells['_web_profiler']; original_profiler=profiler_cell.cell_contents
    presentation_cell=cells['_present_gameplay_render']; original_present=presentation_cell.cell_contents
    floor_cell=cells['_blit_iso_floor']; original_floor=floor_cell.cell_contents
    current=Counters()
    profiler_cell.cell_contents=lambda:current
    def present(*a,**kw):
        start=time.perf_counter(); result=original_present(*a,**kw)
        current.counter('presentation_ms',(time.perf_counter()-start)*1000)
        return result
    presentation_cell.cell_contents=present
    def floor(*a,**kw):
        start=time.perf_counter(); result=original_floor(*a,**kw)
        current.counter('world_floor_including_abyss_ms',(time.perf_counter()-start)*1000)
        return result
    floor_cell.cell_contents=floor
    world_functions=[]
    for module in modules.values():
        for fn,label in (('draw_platform_rim','world_rim_ms'),('draw_abyss','world_abyss_ms')):
            original=getattr(module,fn); world_functions.append((module,fn,original))
            def measured(*a,_original=original,_label=label,**kw):
                start=time.perf_counter(); result=_original(*a,**kw)
                current.counter(_label,(time.perf_counter()-start)*1000)
                return result
            setattr(module,fn,measured)
    originals={name:module.draw_network for name,module in modules.items()}
    for name,module in modules.items():
        def instrumented(target,*a,_original=originals[name],**kw):
            start=time.perf_counter()
            _original(NetworkScreen(target,current),*a,**kw)
            current.counter('network_total_ms',(time.perf_counter()-start)*1000)
        module.draw_network=instrumented
    results=[]
    try:
        for scene,moving,dense in (('still',False,False),('moving',True,False),('dense',True,True)):
            enemies=[game.Enemy(p,speed=game.ENEMY_SPEED,ztype=('basic','tank','ranged')[i%3])
                     for i,p in enumerate([(x,y) for x in range(12,25) for y in range(12,25) if (x,y) not in obs][:72 if dense else 6])]
            samples={name:[] for name in modules}; cold={}
            for name,module in modules.items():
                if scene=='still':
                    module.network_surface.cache_clear(); module.network_material.cache_clear()
                current=Counters(); start=time.perf_counter(); render(module,1000,enemies)
                cold[name]=round((time.perf_counter()-start)*1000,3)
            for frame in range(90):
                for name in (('before','after') if frame%2 else ('after','before')):
                    current=Counters()
                    cam=(camera[0]+frame*2,camera[1]+frame) if moving else camera
                    start=time.perf_counter(); render(modules[name],1000+frame*67,enemies,cam)
                    current.counter('whole_frame_ms',(time.perf_counter()-start)*1000)
                    if frame>=10: samples[name].append(dict(current.values))
            for name in modules:
                rows=samples[name]; keys=set().union(*(r.keys() for r in rows))
                metrics={}
                for key in sorted(keys):
                    values=sorted(r.get(key,0) for r in rows)
                    metrics[key]={'mean':round(sum(values)/len(values),3),'p95':round(values[int(.95*len(values))],3)}
                results.append(dict(scene=scene,version=name,enemies=len(enemies),cold_frame_ms=cold[name],metrics=metrics))
    finally:
        profiler_cell.cell_contents=original_profiler; presentation_cell.cell_contents=original_present
        floor_cell.cell_contents=original_floor
        for module,fn,original in world_functions: setattr(module,fn,original)
        for name,module in modules.items(): module.draw_network=originals[name]
    metadata.update(runtime=sys.platform,viewport=[1280,720],driver=pygame.display.get_driver(),samples_per_scene=80,
                    note='Paired alternating desktop render timings; dense fixture is 72 static actors. Live combat is tested separately.',results=results)
    (args.output/'desktop-profile.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps([{'scene':r['scene'],'version':r['version'],'whole':r['metrics']['whole_frame_ms'],
                       'network':r['metrics']['network_total_ms']} for r in results]),flush=True)
    pygame.quit()


if __name__=='__main__': main()
