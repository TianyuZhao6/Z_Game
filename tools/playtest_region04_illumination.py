"""Desktop fixture: live dense combat, camera movement, wall break, render timings.

Uses the existing real-level-loop harness. Only fixture inputs/observations are
injected; no player saves, combat rules or production artwork are modified.
"""
import asyncio
import json
import math
from pathlib import Path
import time

import playtest_summon as test
from review_region04_illumination import Counters, NetworkScreen
from zgame import neural_environment as art
from zgame.vessel_network import network_geometry


def main():
    out=Path('TEMP/region04-light'); out.mkdir(parents=True,exist_ok=True)
    elapsed=0; layout=None; records={}; timings=[]; current=Counters()
    original_update=test.summons.update
    original_start=test.summons.start_level
    original_render=test.game.render_game_iso
    original_network=art.draw_network
    cells=dict(zip(original_render.__code__.co_freevars,original_render.__closure__))
    profiler=cells['_web_profiler']; previous_profiler=profiler.cell_contents
    profiler.cell_contents=lambda:current
    def network(target,*a,**kw):
        start=time.perf_counter()
        original_network(NetworkScreen(target,current),*a,**kw)
        current.counter('network_total_ms',(time.perf_counter()-start)*1000)
    def render(*a,**kw):
        nonlocal current
        current=Counters(); start=time.perf_counter()
        result=original_render(*a,**kw)
        current.counter('render_total_ms',(time.perf_counter()-start)*1000)
        timings.append(dict(current.values))
        return result
    def update(g,state,dt,enemies):
        nonlocal elapsed,layout
        elapsed+=dt
        geometry=network_geometry(g.GRID_SIZE,'Mountain',state.network_seed,state.network_obstacles)
        if layout is None: layout=geometry
        assert layout is geometry,'Layout rebuilt during gameplay'
        if elapsed>=3 and 'wall_destroyed' not in records:
            p=state._review_player
            pos,wall=min(((pos,ob) for pos,ob in state.obstacles.items() if ob.type=='Destructible'),
                         key=lambda item:math.dist(item[1].rect.center,p.rect.center))
            hits=0
            while pos in state.obstacles:
                bullet=g.Bullet(*wall.rect.center,0,0,max_dist=400,damage=10)
                bullet.update(0,state,enemies,p); hits+=1
                assert hits<40
            records.update(wall_destroyed=pos,real_projectile_hits=hits,network_seed=state.network_seed,
                           initial_blockers_preserved=pos in state.network_obstacles)
        original_update(g,state,dt,enemies)
    def start(g,state,p):
        original_start(g,state,p); state._review_player=p
    test.summons.update=update; test.summons.start_level=start
    test.game.render_game_iso=render; art.draw_network=network
    test.args.environment_stress=True; test.args.edge_motion=True
    test.pygame.init(); test.pygame.display.set_mode((1280,720))
    test.game.VIEW_W,test.game.VIEW_H=1280,720
    test.random.seed(947)
    try:
        asyncio.run(test.scenario('region04-illumination-live',6,3,'Bastion of Stone'))
        assert records['initial_blockers_preserved']
        warm=timings[20:]
        metrics={}
        for key in sorted(set().union(*(row.keys() for row in warm))):
            values=sorted(row.get(key,0) for row in warm)
            metrics[key]={'mean':round(sum(values)/len(values),3),'p95':round(values[int(len(values)*.95)],3)}
        records.update(topology_unchanged_every_update=True,render_samples=len(warm),metrics=metrics,
                       note='Actual dense level-loop render timings, excluding screenshot encoding. Simulation uses fixed 1/60 dt; this is not a display-refresh or whole-loop FPS measurement.')
        (out/'live.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    finally:
        test.summons.update=original_update; test.summons.start_level=original_start
        test.game.render_game_iso=original_render; art.draw_network=original_network
        profiler.cell_contents=previous_profiler
        test.pygame.quit()


if __name__=='__main__': main()
