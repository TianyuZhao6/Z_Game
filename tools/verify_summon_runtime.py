"""Headless integration checks; no writes to the player's saves or run state."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch
import asyncio
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pygame
import ZGame as game
from zgame import summons, shop_support, shop_ui, persistence, app_flow


class SkullTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1280, 720))

    def setUp(self):
        self.original_meta = copy.deepcopy(game.META)
        self.original_level = getattr(game, "current_level", 0)
        self.original_view = game.VIEW_W, game.VIEW_H
        game.reset_run_state()
        game.current_level = 0
        game.VIEW_W, game.VIEW_H = 1280, 720
        random.seed(123)
        self.gs = game.GameState({}, [], [], [])
        self.gs.current_level = 0
        self.player = game.Player((8, 8), speed=game.PLAYER_SPEED)
        self.enemies = []

    def tearDown(self):
        game.META.clear()
        game.META.update(self.original_meta)
        game.current_level = self.original_level
        game.VIEW_W, game.VIEW_H = self.original_view

    def skull(self, level=6):
        for _ in range(level):
            summons.purchase(game.META)
        summons.start_level(game, self.gs, self.player)
        return self.gs.companions[0]

    def enemy(self, x=12, y=8, hp=100000, kind="basic"):
        enemy = game.Enemy((x,y),speed=game.ENEMY_SPEED,ztype=kind,hp=hp)
        enemy.hp = enemy.max_hp = hp
        self.enemies.append(enemy)
        return enemy

    def test_progression_and_purchase_cap(self):
        expected = [(1,"Bloombone"),(3,"Bloombone"),(3,"Soulflame"),(3,"Soulflame"),(3,"Soulflame"),(5,"Rift Skull")]
        for level,(count,name) in enumerate(expected,1):
            summons.purchase(game.META)
            self.assertEqual(game.META["skull_level"],level)
            self.assertEqual(summons.VOLLEY[level-1],count)
            self.assertEqual(summons.form(level),name)
        summons.purchase(game.META)
        self.assertEqual(game.META["skull_level"],6)
        self.assertEqual(game.META["equipped_companions"],[summons.SKULL_ID])

    def test_volley_spreads_and_lone_target_focuses(self):
        skull = self.skull(6)
        a,b = self.enemy(),self.enemy(12,9)
        skull.update(1/60,self.enemies)
        self.assertEqual(len(skull.shots),5)
        self.assertEqual({s["target"] for s in skull.shots},{a,b})
        skull.shots.clear()
        self.enemies.remove(b)
        skull.fire_cd=0
        skull.update(1/60,self.enemies)
        self.assertTrue(all(s["target"] is a for s in skull.shots))

    def test_harvest_ratio_caps_and_no_banking(self):
        skull = self.skull(3)
        skull.hp = skull.max_hp*.4
        for _ in range(140):
            skull.on_kill(True)
        self.assertEqual(skull.harvest,100)
        self.assertAlmostEqual(skull.hp/skull.max_hp,.4)
        skull.level=6
        self.assertEqual(skull.harvest,100)
        for _ in range(150):
            skull.on_kill(True)
        self.assertEqual(skull.harvest,200)
        self.assertEqual(skull.charge,15)

    def test_bloombone_cannot_harvest(self):
        skull=self.skull(2)
        skull.on_kill(True)
        self.assertEqual((skull.harvest,skull.charge),(0,0))

    def test_charge_requires_normal_kills(self):
        skull=self.skull()
        for _ in range(20):
            skull.on_kill(False)
        self.assertEqual(skull.charge,0)
        for _ in range(30):
            skull.on_kill(True)
        self.assertEqual(skull.charge,15)
        harvest=skull.harvest
        skull.cast()
        self.assertEqual((skull.charge,skull.harvest),(0,harvest))

    def test_trigger_and_boss_exception(self):
        skull=self.skull()
        boss=self.enemy()
        boss.is_boss=True
        skull.charge=14
        skull.update(.01,self.enemies)
        self.assertEqual(skull.cast_left,0)
        skull.charge=15
        skull.update(.01,self.enemies)
        self.assertGreater(skull.cast_left,0)
        skull.charge=15
        old=skull.procession
        skull.update(.01,self.enemies)
        self.assertIs(skull.procession,old)
        self.assertEqual(skull.charge,15)

    def test_waits_with_four_and_casts_with_five(self):
        skull=self.skull()
        for i in range(4):
            self.enemy(12,i+5)
        skull.charge=15
        skull.update(.01,self.enemies)
        self.assertEqual(skull.cast_left,0)
        self.enemy(13,9)
        skull.update(.01,self.enemies)
        self.assertGreater(skull.cast_left,0)

    def test_downing_finishes_cast_without_rewards_to_owner(self):
        skull=self.skull()
        skull.harvest=80
        skull.cast()
        damage=skull.procession[0][6]
        skull.take_damage(99999)
        self.assertEqual((skull.hp,skull.harvest,skull.charge),(0,0,0))
        self.assertEqual(skull.procession[0][6],damage)
        skull.on_kill(True)
        skull.on_kill(False)
        self.assertEqual((skull.harvest,skull.charge),(0,0))
        skull.update(1,self.enemies)
        self.assertGreater(skull.cast_left,0)
        skull.update(2,self.enemies)
        self.assertFalse(skull.procession)
        self.assertEqual(skull.hp,0)

    def test_save_resume_and_next_level(self):
        skull=self.skull()
        skull.harvest=40
        skull.hp=skull.max_hp*.5
        skull.charge=12
        skull.persist()
        payload=game.capture_snapshot(self.gs,self.player,self.enemies,0)
        payload=game._sanitize_resume_save_data(json.loads(json.dumps(payload)))
        self.assertEqual(payload["meta"]["skull_combat"]["charge"],12)
        game._load_meta_from_save(payload)
        summons.start_level(game,self.gs,self.player)
        resumed=self.gs.companions[0]
        self.assertEqual(resumed.charge,12)
        self.assertAlmostEqual(resumed.hp/resumed.max_hp,.5)
        resumed.take_damage(99999)
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].hp,0)
        self.gs.current_level=1
        summons.start_level(game,self.gs,self.player)
        rebuilt=self.gs.companions[0]
        self.assertEqual(rebuilt.hp,rebuilt.max_hp)
        self.assertEqual((rebuilt.charge,rebuilt.harvest),(0,0))

    def test_harvest_survives_levels_and_storage(self):
        skull=self.skull()
        skull.harvest=45
        skull.charge=14
        skull.persist()
        summons.toggle_equipped(game.META)
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions,[])
        summons.toggle_equipped(game.META)
        self.gs.current_level=1
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].harvest,45)
        self.assertEqual(self.gs.companions[0].charge,0)

    def test_regeneration_and_damage_reset(self):
        skull=self.skull()
        skull.hp=skull.max_hp*.5
        hp=skull.hp
        skull.update(4,self.enemies)
        self.assertEqual(skull.hp,hp)
        skull.update(1,self.enemies)
        self.assertGreater(skull.hp,hp)
        skull.take_damage(1)
        self.assertEqual(skull.quiet,0)

    def test_damage_independent_of_player_weapon(self):
        skull=self.skull()
        before=skull.damage
        game.META.update(base_dmg=99999,dmg=99999)
        self.player.bullet_damage=99999
        self.assertEqual(skull.damage,before)

    def test_wall_blocks_before_enemy_and_wall_break_no_harvest(self):
        skull=self.skull()
        target=self.enemy(12,8,hp=1)
        c=game.CELL_SIZE
        wall=game.Obstacle(11,8,"Destructible",1)
        self.gs.obstacles[11,8]=wall
        skull.shots=[dict(x=10*c,y=wall.rect.centery,vx=4*c,vy=0,target=None,damage=100,life=3,trail=[])]
        skull.update_shots(1,self.enemies)
        self.assertNotIn((11,8),self.gs.obstacles)
        self.assertEqual(target.hp,1)
        self.assertEqual((skull.harvest,skull.charge),(0,0))

    def test_shared_contact_gap_and_spectral_wall_passage(self):
        skull=self.skull()
        target=self.enemy(12,8)
        x,y=target.rect.center
        skull.cast_left=3
        skull.procession=[[x,y,0,0,0,3,10,0] for _ in range(3)]
        skull.clock=1
        skull.update_procession(.01,self.enemies)
        self.assertEqual(target.hp,99990)
        skull.clock+=.2
        skull.update_procession(.01,self.enemies)
        self.assertEqual(target.hp,99990)
        skull.clock+=.11
        skull.update_procession(.01,self.enemies)
        self.assertEqual(target.hp,99980)
        wall=game.Obstacle(12,8,"Destructible",5)
        self.gs.obstacles[12,8]=wall
        skull.clock+=.31
        skull.update_procession(.01,self.enemies)
        self.assertNotIn((12,8),self.gs.obstacles)
        wall=game.Obstacle(12,8,"Indestructible")
        self.gs.obstacles[12,8]=wall
        skull.clock+=.31
        skull.update_procession(.01,self.enemies)
        self.assertIs(self.gs.obstacles[12,8],wall)

    def test_personal_kill_once_and_skill_kill_does_not_charge(self):
        skull=self.skull()
        target=self.enemy(hp=1)
        summons.damage_enemy(game,self.gs,self.enemies,target,100,skull,True)
        summons.damage_enemy(game,self.gs,self.enemies,target,100,skull,True)
        self.assertEqual((skull.harvest,skull.charge),(1,1))
        target=self.enemy(hp=1)
        summons.damage_enemy(game,self.gs,self.enemies,target,100,skull,False)
        self.assertEqual((skull.harvest,skull.charge),(2,1))
        self.assertEqual(game.META["kill_count"],2)

    def test_retarget_dead_target(self):
        skull=self.skull()
        dead=self.enemy()
        replacement=self.enemy(13,9)
        skull.update(.01,self.enemies)
        dead.hp=0
        skull.update_shots(.01,self.enemies)
        self.assertTrue(all(s["target"] is replacement for s in skull.shots))

    def test_enemy_target_and_damage_routing(self):
        skull=self.skull()
        enemy=self.enemy(10,8)
        self.assertIs(summons.enemy_target(game,self.gs,enemy,self.player),skull)
        before=self.player.hp
        self.gs.damage_player(skull,10)
        self.assertEqual(self.player.hp,before)
        self.assertEqual(skull.hp,skull.max_hp-10)
        enemy.move_and_attack(self.player,(),self.gs,dt=.016)
        enemy.update_special(.016,self.player,self.enemies,[],self.gs)
        app_flow._web_simple_enemy_move(game,enemy,self.player,self.gs,(),dt=.016)
        shot=game.EnemyShot(*skull.rect.center,0,0,10)
        shot.update(.01,self.player,self.gs)
        self.assertFalse(shot.alive)

    def test_shop_guarantees_rerolls_locks_and_cap(self):
        catalog=shop_support.build_shop_catalog(game)
        for i in range(3):
            game.current_level=i
            summons.enter_shop(game)
        visits=game.META["summon_shop_visits"]
        summons.enter_shop(game)
        self.assertEqual(visits,game.META["summon_shop_visits"])
        for _ in range(30):
            offers=shop_support.roll_offers(game,catalog,[])
            self.assertIn(summons.SKULL_ID,[c["id"] for c in offers])
        locked=[c["id"] for c in catalog if c["id"] not in (summons.SKULL_ID,"reroll")][:4]
        offers=shop_support.roll_offers(game,catalog,locked)
        self.assertTrue(set(locked+[summons.SKULL_ID]).issubset({c["id"] for c in offers}))
        game.META["skull_level"]=6
        offers=shop_support.roll_offers(game,catalog,[])
        self.assertNotIn(summons.SKULL_ID,[c["id"] for c in offers])

    def test_navigation_compact_body_does_not_cross_wall(self):
        skull=self.skull()
        c=game.CELL_SIZE
        gx=int(skull.rect.centerx//c)
        gy=int((skull.rect.centery-game.INFO_BAR_HEIGHT)//c)
        wall=game.Obstacle(gx+1,gy,"Indestructible")
        self.gs.obstacles[gx+1,gy]=wall
        goal=((gx+3.5)*c,(gy+.5)*c+game.INFO_BAR_HEIGHT)
        for _ in range(180):
            skull.navigate(goal,1/60)
            self.assertFalse(skull.rect.colliderect(wall.rect))
        self.assertLess(summons.math.dist(skull.rect.center,goal),c)
        self.assertLess(skull.size,c/2)

    def test_reset_and_old_save_compatibility(self):
        self.skull()
        game.reset_run_state()
        self.assertEqual(game.META["skull_level"],0)
        self.assertIsNone(game.META["skull_combat"])
        self.assertEqual(game.META["equipped_companions"],[])
        old={}
        summons.ensure_meta(old)
        self.assertEqual(old["skull_level"],0)

    def test_active_cast_snapshot_and_cleanup(self):
        skull=self.skull()
        skull.cast()
        skull.update_procession(.7,self.enemies)
        skull.persist()
        rows=copy.deepcopy(skull.procession)
        summons.start_level(game,self.gs,self.player)
        skull=self.gs.companions[0]
        self.assertEqual(skull.procession,rows)
        self.assertAlmostEqual(skull.cast_left,2.3)
        for _ in range(140):
            skull.update(1/60,self.enemies)
        self.assertEqual(skull.cast_left,0)
        self.assertFalse(skull.procession)
        self.assertFalse(skull.hit_times)
        skull.cast()
        self.assertEqual(len(skull.procession),summons.PROCESSION_COUNT)
        self.gs.current_level=1
        summons.start_level(game,self.gs,self.player)
        self.assertFalse(self.gs.companions[0].procession)

    def test_skill_hits_offscreen_and_capped_harvest_still_charges(self):
        skull=self.skull()
        skull.harvest=200
        for _ in range(15):
            skull.on_kill(True)
        self.assertEqual((skull.harvest,skull.charge),(200,15))
        target=self.enemy(32,32,hp=1)
        x,y=target.rect.center
        skull.cast_left=3
        skull.procession=[[x,y,0,0,0,3,10,0]]
        skull.update_procession(.1,self.enemies)
        self.assertNotIn(target,self.enemies)
        self.assertEqual(skull.harvest,200)

    def test_renderers_and_sprite_alpha(self):
        skull=self.skull()
        self.enemy()
        skull.cast()
        skull.update(.8,self.enemies)
        screen=pygame.display.get_surface()
        game.render_game_iso(screen,self.gs,self.player,self.enemies,[],[])
        game.render_game_iso_web_lite(screen,self.gs,self.player,self.enemies,[],[])
        for i in range(4):
            art=summons.sprite(i,120)
            self.assertEqual(art.get_at((0,0)).a,0)
        summons.loadout_button(game,screen)

    def test_actual_shop_purchase_desktop_and_async(self):
        for web in (False, True):
            game.reset_run_state()
            game.META.update(spoils=1000,summon_shop_visits=2,summon_shop_last_level=-1)
            events=iter([
                [pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=(277,290))],
                [pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=(640,170))],
                [pygame.event.Event(pygame.KEYDOWN,key=pygame.K_ESCAPE)],
            ])
            before=game.Player((0,0),speed=game.PLAYER_SPEED).bullet_damage
            with patch.object(pygame.event,"get",side_effect=lambda:next(events,[])), patch.object(game,"play_combat_bgm"), patch.object(game,"flush_events"), patch.object(game,"pause_from_overlay",return_value="home"), patch.object(game,"pause_from_overlay_web",return_value="home"):
                if web:
                    result=asyncio.run(shop_ui.show_shop_screen_web(game,pygame.display.get_surface()))
                else:
                    result=shop_ui.show_shop_screen(game,pygame.display.get_surface())
            self.assertEqual(result,"home")
            self.assertEqual(game.META["skull_level"],1)
            self.assertLess(game.META["spoils"],1000)
            self.assertEqual(game.META["equipped_companions"],[])
            self.assertEqual(before,game.Player((0,0),speed=game.PLAYER_SPEED).bullet_damage)

    def test_disk_save_living_and_downed(self):
        skull=self.skull()
        with tempfile.TemporaryDirectory(prefix="summon-save-") as folder, patch.object(game,"SAVE_FILE",str(Path(folder)/"save.json")):
            for downed in (False,True):
                skull.charge=11
                if downed:
                    skull.take_damage(99999)
                skull.persist()
                payload=game.capture_snapshot(self.gs,self.player,self.enemies,0)
                persistence.save_snapshot(game,payload)
                loaded=persistence.load_save(game)
                game._load_meta_from_save(loaded)
                summons.start_level(game,self.gs,self.player)
                restored=self.gs.companions[0]
                self.assertEqual(restored.hp==0,downed)
                self.assertEqual(restored.charge,0 if downed else 11)

    def test_enemy_variants_and_boss_target_preservation(self):
        skull=self.skull()
        for kind in ("basic","fast","tank","ranged","suicide","buffer","shielder","ravager","mistling","bandit"):
            if kind == "bandit":
                enemy=game.make_coin_bandit((10*game.CELL_SIZE,8*game.CELL_SIZE+game.INFO_BAR_HEIGHT),0,0,10)
                self.enemies.append(enemy)
            else:
                enemy=self.enemy(10,8,kind=kind)
            for _ in range(5):
                enemy.move_and_attack(self.player,(),self.gs,dt=1/60)
                enemy.update_special(1/60,self.player,self.enemies,[],self.gs)
        boss=game.MemoryDevourerBoss((12,8),4)
        self.enemies.append(boss)
        self.assertIs(summons.enemy_target(game,self.gs,boss,self.player),self.player)
        for _ in range(60):
            boss.move_and_attack(self.player,(),self.gs,dt=1/60)
            boss.update_special(1/60,self.player,self.enemies,[],self.gs)
        target=self.enemy(hp=100)
        target.shield_hp=10
        summons.damage_enemy(game,self.gs,self.enemies,target,15,skull)
        self.assertEqual((target.hp,target.shield_hp),(95,0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
