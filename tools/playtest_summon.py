"""Scripted input through the actual level loop; writes only local test evidence.

Run with --visible to watch, or default headless for CI. Does not load/save the
player's run. Fixtures seed upgrades/charge, then real AI, damage, navigation,
projectiles, hazards, shop catalog and renderers execute unchanged.
"""
from __future__ import annotations
import argparse
import asyncio
import copy
import os
from pathlib import Path
import random
import sys
import time
import faulthandler
from unittest.mock import patch

parser=argparse.ArgumentParser()
parser.add_argument("--visible",action="store_true")
args=parser.parse_args()
if not args.visible:
    os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pygame
import ZGame as game
from zgame import summons,app_flow,shop_support,render_runtime


async def scenario(name, tier, level, biome=None, lite=False, down=False):
    game.reset_run_state()
    game.current_level=level
    game._next_biome=biome
    game.META.update(aegis_pulse_level=1,carapace_shield_hp=40,bone_plating_level=1,
                     dot_rounds_level=1,curing_paint_level=1,ground_spikes_level=1,
                     auto_turret_level=1)
    card=next(c for c in shop_support.build_shop_catalog(game) if c["id"]==summons.SKULL_ID)
    for _ in range(tier):
        card["apply"]()
    capture={"time":0.0,"cast":False,"beam":False,"shot":False,"down":False,"frame":False,"frames":0,"max_enemies":0,"facings":set(),"cast_positions":set()}
    original_start=summons.start_level
    original_update=summons.update
    original_cast=summons.Skull.cast
    def checked_cast(skull):
        result=original_cast(skull)
        if result:
            assert skull.charge==0,"Skill release did not empty charge"
            assert game.META["skull_combat"]["charge"]==0,"Reset was not persisted"
        return result
    renderer=game.render_game_iso_web_lite if lite else game.render_game_iso
    evidence=ROOT/"TEMP"/"summon-playtest"
    evidence.mkdir(parents=True,exist_ok=True)

    def start(g,gs,p):
        original_start(g,gs,p)
        capture.update(state=gs,player=p,start_pos=p.rect.center,skull_start=gs.companions[0].rect.center)
        # Keep the player alive so the complete downed/cleanup timeline is tested.
        p._ultimate_debug=True
        p.xp_to_next=100000
        if tier==6:
            gs.companions[0].charge=summons.PROCESSION_KILL_THRESHOLD
        if biome=="Domain of Wind":
            gs.spawn_hurricane(p.rect.centerx+3*game.CELL_SIZE,p.rect.centery)

    def update(g,gs,dt,enemies):
        capture["time"]+=dt
        capture["max_enemies"]=max(capture["max_enemies"],len(enemies))
        t=capture["time"]
        skull=gs.companions[0]
        if down and t>=4.5 and not capture["down"]:
            skull.take_damage(skull.max_hp*5)
            capture["down"]=True
        original_update(g,gs,dt,enemies)
        capture["facings"].add(skull.facing)
        capture["cast"] |= skull.cast_left>0
        capture["beam"] |= skull.beam_left>0
        capture["shot"] |= bool(skull.shots)
        if capture["down"]:
            assert skull.hp==0 and skull.harvest==0 and skull.charge==0
            if t>8.1:
                assert not skull.shots
        capture["enemies"]=enemies

    def render(screen,gs,p,enemies,bullets,eshots,obstacles=None,**kw):
        # Exercise actual web wall caches when testing the lite renderer.
        with patch.object(game,"IS_WEB",lite), patch.object(render_runtime,"IS_WEB",lite):
            result=renderer(screen,gs,p,enemies,bullets,eshots,obstacles,**kw)
        capture["frames"]+=1
        t=capture["time"]
        if not capture["frame"] and (1.1<t<2.4):
            pygame.image.save(screen,str(evidence/f"{name}.png"))
            capture["frame"]=True
        skull=gs.companions[0]
        if tier==6 and skull.beam_left>0 and skull.beam_end and not skull.beam_wall and "beam_frame" not in capture:
            pygame.image.save(screen,str(evidence/f"{name}-beam.png"))
            capture["beam_frame"]=True
        if skull.cast_left>0 and skull.charge==0 and "empty_meter" not in capture:
            pygame.image.save(screen,str(evidence/f"{name}-empty-meter.png"))
            capture["empty_meter"]=True
        if skull.cast_left>0:
            capture["cast_positions"].add(p.rect.center)
            cam=game.calculate_iso_camera(*p.rect.center)
            # Check live paths against the moving camera, including delayed entries.
            for row in skull.procession:
                x,y=skull.procession_world(*row[:2])
                sx,sy=game.iso_world_to_screen(x/game.CELL_SIZE,(y-game.INFO_BAR_HEIGHT)/game.CELL_SIZE,0,*cam)
                assert abs(sx-row[0]*game.VIEW_W)<3
                assert abs(sy-(game.INFO_BAR_HEIGHT+row[1]*(game.VIEW_H-game.INFO_BAR_HEIGHT)))<3
            for label,remaining in (("entry",2.7),("moving",1.5),("exit",.4)):
                if skull.cast_left<remaining and label not in capture:
                    pygame.image.save(screen,str(evidence/f"{name}-procession-{label}.png"))
                    capture[label]=True
        if down and .45<skull.death_age<.55 and skull.hp<=0 and "dissolve_frame" not in capture:
            # Focus the real camera on the downed actor, without moving entities.
            sx,sy=game.iso_world_to_screen(skull.rect.centerx/game.CELL_SIZE,(skull.rect.centery-game.INFO_BAR_HEIGHT)/game.CELL_SIZE)
            renderer(screen,gs,p,enemies,bullets,eshots,obstacles,override_cam=(sx-640,sy-360))
            pygame.image.save(screen,str(evidence/f"{name}-dissolve.png"))
            capture["dissolve_frame"]=True
        if name=="bloombone" and 2<t<8:
            for label, directions in (("front",(1,7)),("rear",(3,5))):
                if skull.facing in directions and label not in capture:
                    pygame.image.save(screen,str(evidence/f"facing-{label}.png"))
                    capture[label]=True
        if down and capture["down"] and "down_frame" not in capture:
            pygame.image.save(screen,str(evidence/f"{name}-downed.png"))
            capture["down_frame"]=True
        return result

    def input_pressed(keys,action):
        t=capture["time"]
        direction=("move_right","move_down","move_left","move_up")[int(t/1.7)%4]
        return action==direction

    def step(g,clock):
        if args.visible:
            clock.tick(60)
        return 1/60

    started=time.perf_counter()
    with patch.object(summons.Skull,"cast",checked_cast), patch.object(summons,"start_level",side_effect=start), patch.object(summons,"update",side_effect=update), patch.object(game,"render_game_iso",side_effect=render), patch.object(game,"binding_pressed",side_effect=input_pressed), patch.object(app_flow,"_frame_dt",side_effect=step), patch.object(app_flow,"_effective_level_time_limit",return_value=9), patch.object(game,"play_combat_bgm"), patch.object(game,"play_focus_cinematic_iso"), patch.object(game,"play_focus_chain_iso"):
        result=await app_flow.main_run_level(game,game.get_level_config(level),"basic")
    skull=capture["state"].companions[0]
    assert result[0]=="success",result[0]
    assert len(capture["state"].companions)==1
    assert capture["frames"]>=500
    assert capture["player"].rect.center!=capture["start_pos"]
    assert skull.rect.center!=capture["skull_start"]
    assert len(capture["facings"])>=3, "Skull did not turn while navigating"
    assert capture["shot"],"No ordinary shots fired"
    if tier==6:
        assert capture["cast"],"Procession never triggered"
        assert capture["beam"],"Eye beam never triggered"
        points=capture["cast_positions"]
        assert len(points)>20,"Player did not move during Procession"
        assert max(x for x,y in points)-min(x for x,y in points)+max(y for x,y in points)-min(y for x,y in points)>game.CELL_SIZE
    assert skull.cast_left==0 and not skull.procession
    if down:
        print(f"{name}: level loop complete; checking snapshot resume",flush=True)
        payload=game.capture_snapshot(capture["state"],capture["player"],capture["enemies"],level)
        payload["snapshot"]["time_left"]=.5
        with patch.object(app_flow,"_frame_dt",side_effect=step), patch.object(game,"play_combat_bgm"), patch.object(game,"levelup_modal",side_effect=lambda screen,bg,clock,left,player:left), patch.object(game,"play_focus_cinematic_iso"), patch.object(game,"play_focus_chain_iso"), patch.object(game,"show_success_screen",return_value="continue"):
            resumed=await app_flow.run_from_snapshot(game,payload)
        assert game.META["skull_combat"]["hp"]==0
    print(f"{name}: PASS | {capture['frames']} frames, {capture['max_enemies']} enemies, cast={capture['cast']}, downed={capture['down']}, {time.perf_counter()-started:.2f}s wall time",flush=True)


async def main():
    pygame.init()
    pygame.display.set_mode((1280,720))
    game.VIEW_W,game.VIEW_H=1280,720
    random.seed(947)
    await scenario("bloombone",2,0)
    await scenario("soulflame-mist",3,1,"Misty Forest")
    await scenario("rift-hell",6,2,"Scorched Hell",down=True)
    await scenario("rift-lite-wind",6,3,"Domain of Wind",lite=True)
    await scenario("rift-stone",6,3,"Bastion of Stone")
    await scenario("rift-boss",6,4)
    print("Real level-loop scenarios passed. Evidence: TEMP/summon-playtest",flush=True)
    pygame.quit()


if __name__=="__main__":
    faulthandler.dump_traceback_later(120,repeat=True)
    asyncio.run(main())
    faulthandler.cancel_dump_traceback_later()
