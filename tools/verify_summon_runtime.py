"""Headless integration checks; no writes to the player's saves or run state."""
from __future__ import annotations

import copy
import json
import math
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
from zgame import summons, summon_vfx, shop_support, shop_ui, persistence, app_flow, terrain_art, render_runtime


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
        # Shop tests queue transitions. A subsequent renderer test must exercise
        # gameplay instead of short-circuiting to the previous test's transition.
        game.clear_menu_transition_state()
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

    def test_hell_buffs_all_summon_attacks_once_and_does_not_leak(self):
        self.gs.biome_active="Scorched Hell"
        skull=self.skull()
        expected=summons.BASE_DAMAGE[5]*2
        self.assertEqual(skull.damage,expected)
        target=self.enemy()
        with patch.object(skull,"update_shots"):
            skull.update(.01,self.enemies)
        self.assertTrue(all(s["damage"]==expected for s in skull.shots))
        skull.cast()
        self.assertEqual(skull.procession[0][6],expected*summons.PROCESSION_DAMAGE_MULT)
        skull.beam_credit=skull.beam_tick=0
        skull.beam_left=3
        skull.beam_target=target
        hp=target.hp
        skull.update_beam(.1,self.enemies)
        self.assertAlmostEqual(hp-target.hp,int(expected*summons.BEAM_DPS_MULT*.1),delta=1)
        skull.persist()
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].damage,expected)
        self.gs.current_level+=1
        self.gs.biome_active=None
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].damage,summons.BASE_DAMAGE[5])

    def test_stone_shield_absorbs_overflows_and_does_not_harvest_refill(self):
        self.gs.biome_active="Bastion of Stone"
        skull=self.skull()
        hp=skull.hp
        self.assertEqual(skull.shield_hp,hp*.5)
        skull.quiet=4
        skull.take_damage(20)
        self.assertEqual(skull.hp,hp)
        self.assertEqual(skull.shield_hp,hp*.5-20)
        self.assertEqual(skull.quiet,0)
        shield=skull.shield_hp
        skull.on_kill(True)
        self.assertEqual(skull.shield_hp,shield)
        hp=skull.hp
        skull.take_damage(shield+7)
        self.assertEqual(skull.shield_hp,0)
        self.assertEqual(skull.hp,hp-7)
        skull.take_damage(99999)
        self.assertEqual(skull.hp,0)
        self.assertEqual(skull.shield_hp,0)

    def test_stone_shield_save_depletion_transition_and_legacy_save(self):
        self.gs.biome_active="Bastion of Stone"
        skull=self.skull()
        initial=skull.shield_hp
        skull.take_damage(17)
        with tempfile.TemporaryDirectory(prefix="eidolon-shield-") as folder,patch.object(game,"SAVE_FILE",str(Path(folder)/"save.json")):
            persistence.save_snapshot(game,game.capture_snapshot(self.gs,self.player,[],0))
            game._load_meta_from_save(persistence.load_save(game))
            summons.start_level(game,self.gs,self.player)
        skull=self.gs.companions[0]
        self.assertEqual(skull.shield_hp,initial-17)
        skull.take_damage(initial)
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].shield_hp,0)
        game.META["skull_combat"].pop("shield_hp")
        game.META["skull_combat"].pop("shield_max")
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].shield_hp,initial)
        self.gs.current_level+=1
        self.gs.biome_active=None
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].shield_hp,0)
        self.gs.current_level+=1
        self.gs.biome_active="Bastion of Stone"
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].shield_hp,initial)

    def test_wind_speed_is_temporary_and_mist_does_not_change_summon_stats(self):
        skull=self.skull()
        base=skull.movement_speed
        damage=skull.damage
        self.gs.biome_active="Domain of Wind"
        self.assertAlmostEqual(skull.movement_speed,base*1.12)
        start=skull.x
        skull.path_cd=10
        skull.path=[(skull.rect.centerx+100,skull.rect.centery)]
        skull.navigate(skull.path[0],.01)
        self.assertAlmostEqual(skull.x-start,base*1.12*.01)
        self.gs.biome_active="Misty Forest"
        self.assertEqual(skull.movement_speed,base)
        self.assertEqual(skull.damage,damage)

    def test_stone_outline_follows_all_stage_silhouettes_and_disappears(self):
        self.gs.biome_active="Bastion of Stone"
        skull=self.skull()
        for stage,level in enumerate((1,3,6)):
            skull.level=level
            for facing in range(8):
                skull.facing=facing
                art=summons.directional_sprite(stage,summon_vfx.canvas_size(level),facing)
                outline=summon_vfx.shield_outline(art)
                self.assertIs(outline,summon_vfx.shield_outline(art))
                body=pygame.mask.from_surface(art,32)
                border=pygame.mask.from_surface(outline,1)
                self.assertGreater(border.count(),0)
                self.assertIsNone(border.overlap(body,(3,3)))
        screen=pygame.Surface((1280,720),pygame.SRCALPHA)
        with patch.object(summon_vfx,"shield_outline",wraps=summon_vfx.shield_outline) as draw:
            skull.draw(screen,640,500)
            draw.assert_called_once()
            skull.shield_hp=0
            skull.draw(screen,640,500)
            draw.assert_called_once()

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
        self.assertEqual(skull.charge,150)

    def test_bloombone_cannot_harvest(self):
        skull=self.skull(2)
        skull.on_kill(True)
        self.assertEqual((skull.harvest,skull.charge),(0,0))

    def test_procession_kills_charge_once_and_cast_clears_surplus(self):
        skull=self.skull()
        for _ in range(35):
            target=self.enemy(hp=1)
            summons.damage_enemy(game,self.gs,self.enemies,target,100,skull)
            summons.damage_enemy(game,self.gs,self.enemies,target,100,skull)
        self.assertEqual(skull.charge,35)
        self.assertEqual(game.META["kill_count"],35)
        harvest=skull.harvest
        skull.cast()
        self.assertEqual((skull.charge,skull.harvest),(0,harvest))

    def test_trigger_and_boss_exception(self):
        self.assertEqual(summons.PROCESSION_KILL_THRESHOLD,40)
        skull=self.skull()
        boss=self.enemy()
        boss.is_boss=True
        skull.charge=summons.PROCESSION_KILL_THRESHOLD-1
        skull.update(.01,self.enemies)
        self.assertEqual(skull.cast_left,0)
        skull.charge=summons.PROCESSION_KILL_THRESHOLD
        skull.update(.01,self.enemies)
        self.assertGreater(skull.cast_left,0)
        skull.charge=summons.PROCESSION_KILL_THRESHOLD
        old=skull.procession
        skull.update(.01,self.enemies)
        self.assertIs(skull.procession,old)
        self.assertEqual(skull.charge,summons.PROCESSION_KILL_THRESHOLD)

    def test_waits_with_four_and_casts_with_five(self):
        skull=self.skull()
        for i in range(4):
            self.enemy(12,i+5)
        skull.charge=summons.PROCESSION_KILL_THRESHOLD
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
        skull.update(4,self.enemies)
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

    def test_personal_and_skill_kills_charge_once(self):
        skull=self.skull()
        target=self.enemy(hp=1)
        summons.damage_enemy(game,self.gs,self.enemies,target,100,skull,True)
        summons.damage_enemy(game,self.gs,self.enemies,target,100,skull,True)
        self.assertEqual((skull.harvest,skull.charge),(1,1))
        target=self.enemy(hp=1)
        summons.damage_enemy(game,self.gs,self.enemies,target,100,skull,False)
        self.assertEqual((skull.harvest,skull.charge),(2,2))
        self.assertEqual(game.META["kill_count"],2)

    def test_retarget_dead_target(self):
        skull=self.skull()
        dead=self.enemy()
        replacement=self.enemy(13,9)
        skull.update(.01,self.enemies)
        dead.hp=0
        skull.update_shots(.01,self.enemies)
        self.assertTrue(all(s["target"] is replacement for s in skull.shots))

    def test_player_and_eidolon_kills_share_charge_not_harvest(self):
        skull=self.skull()
        # Real player projectile death hook: a second update cannot count twice.
        target=self.enemy(hp=1)
        bullet=game.Bullet(*target.rect.center,0,0,max_dist=400,damage=100,source="player")
        bullet.update(.01,self.gs,self.enemies,self.player)
        bullet.update(.01,self.gs,self.enemies,self.player)
        self.assertEqual((skull.charge,skull.harvest),(1,0))
        self.assertEqual(game.META["kill_count"],1)
        target=self.enemy(hp=1)
        summons.damage_enemy(game,self.gs,self.enemies,target,100,skull,normal=True)
        self.assertEqual((skull.charge,skull.harvest),(2,1))
        # Player prop/DoT deaths use the same confirmed-death hook in both loops.
        game.increment_kill_count(20,game_state=self.gs)
        self.assertEqual((skull.charge,skull.harvest),(22,1))
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].charge,22)

    def test_player_charge_stage_down_storage_and_active_cast_rules(self):
        skull=self.skull(3)
        game.increment_kill_count(game_state=self.gs)
        self.assertEqual((skull.charge,skull.harvest),(0,0))
        skull.level=6
        skull.cast()
        game.increment_kill_count(15,game_state=self.gs)
        self.assertEqual(skull.charge,15)
        self.assertGreater(skull.cast_left,0)
        skull.take_damage(99999)
        game.increment_kill_count(game_state=self.gs)
        self.assertEqual(skull.charge,0)
        self.gs.companions=[]
        game.increment_kill_count(10,game_state=self.gs)
        self.assertEqual(game.META["skull_combat"]["charge"],0)

    def test_eidolon_label_and_two_status_bars(self):
        skull=self.skull()
        skull.harvest=58
        skull.hp=skull.max_hp/2
        skull.charge=summons.PROCESSION_KILL_THRESHOLD//4
        skull.quiet=10
        screen=pygame.Surface((400,500),pygame.SRCALPHA)
        font=summons.hud_font()
        from unittest.mock import Mock
        tracked_font=Mock(wraps=font)
        with patch.object(summons,"hud_font",return_value=tracked_font):
            skull.draw(screen,200,450)
        tracked_font.render.assert_called_once_with("Eidolon +58%",True,(228,200,248))
        y=450-summon_vfx.HOVER_HEIGHT-summon_vfx.canvas_size(6)-13
        self.assertEqual(screen.get_at((180,y))[:3],(135,230,186))
        self.assertEqual(screen.get_at((220,y))[:3],(35,20,45))
        self.assertEqual(screen.get_at((180,y+8))[:3],(174,95,232))
        self.assertEqual(screen.get_at((200,y+8))[:3],(45,30,60))
        skull.charge=summons.PROCESSION_KILL_THRESHOLD
        skull.draw(screen,200,450)
        self.assertEqual(screen.get_at((220,y+8))[:3],(244,168,255))
        screen.fill((0,0,0,0))
        skull.draw(screen,200,300)
        clamped_y=game.INFO_BAR_HEIGHT+font.get_linesize()+4
        self.assertEqual(screen.get_at((220,clamped_y+8))[:3],(244,168,255))
        skull.level=3
        screen.fill((0,0,0,0))
        skull.draw(screen,200,450)
        y=450-summon_vfx.HOVER_HEIGHT-summon_vfx.canvas_size(3)-13
        self.assertEqual(screen.get_at((180,y+8))[:3],(45,30,60))

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

    def test_facing_uses_all_eight_isometric_directions(self):
        # World axes project diagonally; screen-horizontal travel is a world diagonal.
        vectors = [(1,1),(1,0),(1,-1),(0,-1),(-1,-1),(-1,0),(-1,1),(0,1)]
        skull = self.skull()
        for expected, (dx,dy) in enumerate(vectors):
            with self.subTest(direction=expected):
                skull.path_cd = 10
                goal = (skull.rect.centerx+dx*100, skull.rect.centery+dy*100)
                skull.path = [goal]
                skull.navigate(goal, 1/60)
                self.assertEqual(skull.facing, expected)
        skull.path = []
        skull.navigate(skull.rect.center, 1/60)
        self.assertEqual(skull.facing, 7)
        for facing in range(8):
            self.assertEqual(summons.movement_facing(0,0,facing), facing)

    def test_blocked_motion_does_not_turn_skull(self):
        skull = self.skull()
        c = game.CELL_SIZE
        gx, gy = 10, 10
        wall = game.Obstacle(gx, gy, "Indestructible")
        self.gs.obstacles[gx,gy] = wall
        skull.x, skull.y = wall.rect.left-skull.size, wall.rect.centery-game.INFO_BAR_HEIGHT-skull.size/2
        skull.sync_rect()
        before = skull.x, skull.y
        skull.facing = 4
        skull.path_cd = 10
        skull.path = [(skull.rect.centerx+100,skull.rect.centery)]
        skull.navigate(skull.path[0],1/60)
        self.assertEqual((skull.x,skull.y), before)
        self.assertEqual(skull.facing, 4)

    def test_facing_roundtrips_and_accepts_old_saves(self):
        skull = self.skull()
        skull.facing = 5
        skull.persist()
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].facing, 5)
        del game.META["skull_combat"]["facing"]
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].facing, 0)

    def test_directional_atlas_unique_views_and_transparency(self):
        for stage in range(3):
            images = []
            for facing in range(8):
                art = summons.directional_sprite(stage,146,facing)
                self.assertEqual(art.get_size(),(146,146))
                self.assertEqual(art.get_at((0,0)).a,0)
                self.assertGreater(pygame.mask.from_surface(art).count(),4000)
                images.append(pygame.image.tobytes(art,"RGBA"))
            self.assertEqual(len(set(images)),8)

    def test_terrain_art_cached_deterministic_and_no_gameplay_rng(self):
        before = random.getstate()
        tiles = []
        for seed in range(16):
            art = terrain_art.floor_tile(game.ISO_CELL_W,game.ISO_CELL_H,seed)
            tiles.append(pygame.image.tobytes(art,"RGBA"))
            self.assertIs(art,terrain_art.floor_tile(game.ISO_CELL_W,game.ISO_CELL_H,seed))
            self.assertEqual(art.get_at((0,0)).a,0)
        self.assertEqual(len(set(tiles)),16)
        for color in ((80,101,117),(137,87,83)):
            for style in ("prism","hybrid"):
                art,ax,ay = terrain_art.wall_tile(game.ISO_CELL_W,game.ISO_CELL_H,game.ISO_WALL_Z,color,0,style)
                self.assertEqual(ax,art.get_width()//2)
                self.assertLessEqual(art.get_width(),math.ceil(game.ISO_CELL_W*1.35))
                self.assertGreaterEqual(ay,1)
                self.assertEqual(art.get_at((0,0)).a,0)
        self.assertEqual(before,random.getstate())

    def test_web_wall_material_refreshes_after_damage_and_removal(self):
        self.skull()
        wall = game.Obstacle(10,8,"Destructible")
        self.gs.obstacles[10,8] = wall
        screen = pygame.display.get_surface()
        with patch.object(game,"IS_WEB",True), patch.object(render_runtime,"IS_WEB",True):
            game.render_game_iso_web_lite(screen,self.gs,self.player,[],[],[])
            original = self.gs._web_wall_layer_cache
            self.assertIsNotNone(original["surface"])
            wall.health = game.OBSTACLE_HEALTH*.2
            game.render_game_iso_web_lite(screen,self.gs,self.player,[],[],[])
            self.assertNotEqual(original["key"],self.gs._web_wall_layer_cache["key"])
            del self.gs.obstacles[10,8]
            game.render_game_iso_web_lite(screen,self.gs,self.player,[],[],[])
            self.assertIsNone(self.gs._web_wall_layer_cache["surface"])

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
        self.assertTrue(skull.procession_relative)
        self.assertAlmostEqual(skull.cast_left,1.8)
        for _ in range(260):
            skull.update(1/60,self.enemies)
        self.assertEqual(skull.cast_left,0)
        self.assertFalse(skull.procession)
        self.assertFalse(skull.hit_times)
        skull.update_procession(summons.PROCESSION_COOLDOWN,[])
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

    def test_eidolon_stage_sizes_and_compact_collision(self):
        skull = self.skull()
        heights = []
        body_size = skull.size
        self.assertEqual(summon_vfx.VISUAL_SIZES,(96,144,216))
        for stage,level in enumerate((1,3,6)):
            skull.level = level
            size = summon_vfx.canvas_size(level)
            art = summons.directional_sprite(stage,size,0)
            heights.append(art.get_bounding_rect(min_alpha=100).height)
            self.assertLessEqual(abs(heights[-1]-summon_vfx.VISUAL_SIZES[stage]),
                                 summon_vfx.VISUAL_SIZES[stage]*.08)
            self.assertEqual(skull.size,body_size)
            self.assertGreater(skull.render_margin,size+summon_vfx.HOVER_HEIGHT)
        self.assertGreater(heights[0],89)  # Player sprite's nominal rendered height.
        self.assertAlmostEqual(heights[1]/heights[0],1.5,delta=.08)
        self.assertAlmostEqual(heights[2]/heights[1],1.5,delta=.08)

    def test_taller_walls_keep_ground_anchor_and_physics(self):
        wall=game.Obstacle(10,8,"Destructible")
        before=(wall.rect.copy(),wall.health)
        self.gs.obstacles[10,8]=wall
        sprite=game._load_shop_sprite("characters/player/sheets/player.png",
            (int(self.player.size*2*game.PLAYER_SPRITE_SCALE),
             int(self.player.size*2.4*game.PLAYER_SPRITE_SCALE)),allow_upscale=True)
        body_height=sprite.get_bounding_rect(min_alpha=100).height
        self.assertGreaterEqual(game.ISO_WALL_Z/body_height,1.8)
        self.assertLessEqual(game.ISO_WALL_Z/body_height,2.4)
        for color in ((80,101,117),(137,87,83)):
            art,ax,ay=terrain_art.wall_tile(game.ISO_CELL_W,game.ISO_CELL_H,game.ISO_WALL_Z,color,0)
            self.assertEqual(ay,1+game.ISO_WALL_Z)
            # Transparent sprite padding may differ; its foot stays on the
            # original tile, while extra height rises above the ground anchor.
            # Root cutouts extend a few pixels beyond the unchanged stone foot.
            foot = art.get_bounding_rect().bottom-ay
            self.assertGreaterEqual(foot,game.ISO_CELL_H-2)
            self.assertLessEqual(foot,game.ISO_CELL_H+14)
        screen=pygame.display.get_surface()
        game.render_game_iso(screen,self.gs,self.player,[],[],[])
        with patch.object(game,"IS_WEB",True),patch.object(render_runtime,"IS_WEB",True),patch.object(terrain_art,"wall_tile",wraps=terrain_art.wall_tile) as material:
            game.render_game_iso_web_lite(screen,self.gs,self.player,[],[],[])
            self.assertTrue(material.called)
            self.assertTrue(all(call.args[2]==game.ISO_WALL_Z for call in material.call_args_list))
        self.assertEqual((wall.rect,wall.health),before)

    def test_large_companions_render_at_all_screen_edges(self):
        skull=self.skull()
        screen=pygame.display.get_surface()
        cam=game.calculate_iso_camera(*self.player.rect.center)
        skull.procession_relative=True
        for level in (1,3,6):
            skull.level=level
            # Bottom cases would previously cull a large, still-visible sprite.
            points=((0,300),(1279,300),(640,80),(640,720+summon_vfx.canvas_size(level)//2),
                    (0,100),(1279,100),(0,760),(1279,760))
            for sx,sy in points:
                x,y=skull.procession_world(sx/1280,(sy-game.INFO_BAR_HEIGHT)/(720-game.INFO_BAR_HEIGHT))
                skull.x=x-skull.size/2
                skull.y=y-game.INFO_BAR_HEIGHT-skull.size/2
                skull.sync_rect()
                for renderer in (game.render_game_iso,game.render_game_iso_web_lite):
                    with patch.object(skull,"draw",wraps=skull.draw) as draw:
                        renderer(screen,self.gs,self.player,[],[],[],override_cam=cam)
                    self.assertTrue(draw.called,(level,sx,sy,renderer.__name__))

    def test_active_procession_disk_resume_moves_and_recasts(self):
        skull=self.skull()
        skull.cast()
        skull.update_procession(.4,[])
        skull.persist()
        with tempfile.TemporaryDirectory(prefix="eidolon-cast-") as folder,patch.object(game,"SAVE_FILE",str(Path(folder)/"save.json")):
            persistence.save_snapshot(game,game.capture_snapshot(self.gs,self.player,[],0))
            game._load_meta_from_save(persistence.load_save(game))
            summons.start_level(game,self.gs,self.player)
        restored=self.gs.companions[0]
        self.assertTrue(restored.procession_relative)
        before=restored.procession_world(*restored.procession[0][:2])
        self.player.rect.move_ip(260,156)
        after=restored.procession_world(*restored.procession[0][:2])
        self.assertAlmostEqual(after[0]-before[0],260,delta=2)
        self.assertAlmostEqual(after[1]-before[1],156,delta=2)
        restored.update_procession(5,[])
        restored.update_procession(summons.PROCESSION_COOLDOWN,[])
        restored.cast()
        self.assertTrue(restored.procession_relative)
        self.assertEqual(len(restored.procession),summons.PROCESSION_COUNT)

    def test_shop_uses_exact_supplied_eidolon_avatars(self):
        strip=pygame.image.load(ROOT/"assets/sprites/summons/eidolon-shop-avatars.png").convert_alpha()
        avatars=[]
        for stage,top in enumerate((5,183,357)):
            art=summons.shop_avatar(stage,104)
            raw=pygame.image.tobytes(art,"RGBA")
            self.assertEqual(raw,pygame.image.tobytes(strip.subsurface((3,top,104,104)),"RGBA"))
            avatars.append(raw)
        self.assertEqual(len(set(avatars)),3)
        self.assertEqual(shop_support.build_shop_catalog(game)[0]["name"],"Eidolon")

    def test_shop_evolution_avatars_in_both_real_screens(self):
        evidence=ROOT/"TEMP"/"summon-playtest"
        evidence.mkdir(parents=True,exist_ok=True)
        for web in (False,True):
            for stage,level in enumerate((0,2,5)):
                game.reset_run_state()
                for _ in range(level):
                    summons.purchase(game.META)
                game.META.update(spoils=1000,summon_shop_visits=2,summon_shop_last_level=-1)
                def events():
                    pygame.image.save(pygame.display.get_surface(),str(evidence/f"eidolon-shop-{stage+1}-{'lite' if web else 'desktop'}.png"))
                    return [pygame.event.Event(pygame.KEYDOWN,key=pygame.K_ESCAPE)]
                with patch.object(summons,"shop_avatar",wraps=summons.shop_avatar) as avatar,patch.object(pygame.event,"get",side_effect=events),patch.object(game,"play_combat_bgm"),patch.object(game,"flush_events"),patch.object(game,"pause_from_overlay",return_value="home"),patch.object(game,"pause_from_overlay_web",return_value="home"):
                    if web:
                        asyncio.run(shop_ui.show_shop_screen_web(game,pygame.display.get_surface()))
                    else:
                        shop_ui.show_shop_screen(game,pygame.display.get_surface())
                avatar.assert_called_with(stage,100)

    def test_procession_spawns_on_current_view_edges_and_tracks_player(self):
        skull=self.skull()
        skull.cast()
        for width,height in ((1280,720),(960,600)):
            game.VIEW_W,game.VIEW_H=width,height
            for dx,dy in ((0,0),(260,156),(-520,104)):
                self.player.rect.move_ip(dx,dy)
                cam=game.calculate_iso_camera(*self.player.rect.center)
                for row in skull.procession:
                    self.assertTrue(row[0]<0 or row[0]>1 or row[1]<0 or row[1]>1)
                    x,y=skull.procession_world(*row[:2])
                    screen=game.iso_world_to_screen(x/game.CELL_SIZE,(y-game.INFO_BAR_HEIGHT)/game.CELL_SIZE,0,*cam)
                    self.assertAlmostEqual(screen[0],row[0]*width,delta=2)
                    self.assertAlmostEqual(screen[1],game.INFO_BAR_HEIGHT+row[1]*(height-game.INFO_BAR_HEIGHT),delta=2)

    def test_procession_damage_follows_player_without_teleport_sweep(self):
        skull=self.skull()
        skull.cast()
        skull.procession=[[.5,.5,0,0,0,3,10,0]]
        old=self.enemy(hp=100)
        old.rect.center=skull.procession_world(.5,.5)
        self.player.rect.move_ip(520,520)
        new=self.enemy(hp=100)
        new.rect.center=skull.procession_world(.5,.5)
        between=self.enemy(hp=100)
        between.rect.center=((old.rect.centerx+new.rect.centerx)//2,(old.rect.centery+new.rect.centery)//2)
        skull.update_procession(.01,self.enemies)
        self.assertEqual((old.hp,new.hp,between.hp),(100,90,100))

    def test_old_world_space_cast_still_resumes(self):
        skull=self.skull()
        skull.cast_left=3
        skull.procession=[[100,200,30,40,0,3,10,0]]
        skull.persist()
        game.META["skull_combat"].pop("procession_space")
        summons.start_level(game,self.gs,self.player)
        restored=self.gs.companions[0]
        self.assertFalse(restored.procession_relative)
        self.player.rect.move_ip(520,520)
        self.assertEqual(restored.procession_world(100,200),(100,200))

    def test_beam_is_one_smooth_straight_ray(self):
        surface=pygame.Surface((400,150),pygame.SRCALPHA)
        summon_vfx.draw_beam(surface,(20,30),(380,110))
        alphas=set()
        for x in range(40,360):
            y=round(30+(x-20)*80/360)
            self.assertGreater(surface.get_at((x,y)).a,200)
            self.assertEqual(surface.get_at((x,y+12)).a,0)
            self.assertEqual(surface.get_at((x,y-12)).a,0)
            alphas.update(surface.get_at((x,y+dy)).a for dy in range(-8,9))
        self.assertGreater(len(alphas),8)  # Filtered edges, not three hard bands.
        straight=pygame.Surface((400,150),pygame.SRCALPHA)
        summon_vfx.draw_beam(straight,(20,70),(380,70))
        body=[y for y in range(150) if straight.get_at((200,y)).a>=150]
        self.assertGreaterEqual(len(body),8)  # Wider than the previous 6 px body.
        self.assertLessEqual(len(body),10)
        # Wider halo still clips safely at viewport edges.
        summon_vfx.draw_beam(straight,(-50,-1),(450,1))

    def test_procession_wake_is_long_directional_and_visual_only(self):
        screen=pygame.Surface((800,400),pygame.SRCALPHA)
        before=random.getstate()
        summon_vfx.draw_procession_wake(screen,(600,200),(10,0),140,1,2,0)
        bounds=screen.get_bounding_rect(min_alpha=5)
        self.assertGreater(bounds.left,240)
        self.assertLess(bounds.left,320)
        self.assertGreater(bounds.width,280)
        self.assertLess(bounds.width,360)
        self.assertLessEqual(bounds.right,610)
        # Left-going ghosts leave their wake on the right, not in front.
        screen.fill((0,0,0,0))
        summon_vfx.draw_procession_wake(screen,(100,200),(-10,0),140,1,2,0)
        self.assertGreater(screen.get_bounding_rect(min_alpha=5).right,400)
        # A head outside the screen must not prematurely cull its visible tail.
        screen.fill((0,0,0,0))
        summon_vfx.draw_procession_wake(screen,(900,200),(10,0),140,1,2,0)
        self.assertGreater(pygame.mask.from_surface(screen,5).count(),0)
        self.assertEqual(before,random.getstate())
        art=summon_vfx.procession_wake(140,0)
        self.assertIs(art,summon_vfx.procession_wake(140,0))

    def test_procession_wake_fades_and_does_not_change_combat(self):
        screen=pygame.Surface((800,400),pygame.SRCALPHA)
        summon_vfx.draw_procession_wake(screen,(600,200),(10,0),140,1,2,0)
        full=pygame.mask.from_surface(screen,40).count()
        screen.fill((0,0,0,0))
        summon_vfx.draw_procession_wake(screen,(600,200),(10,0),140,1,.03,0)
        self.assertLess(pygame.mask.from_surface(screen,40).count(),full)
        skull=self.skull()
        skull.cast()
        skull.update_procession(.5,[])
        rows=copy.deepcopy(skull.procession)
        before=random.getstate()
        summon_vfx.oriented_procession_wake.cache_clear()
        summons.draw_effects(game,self.gs,screen,*game.calculate_iso_camera(*self.player.rect.center))
        self.assertEqual(rows,skull.procession)
        self.assertEqual(before,random.getstate())
        self.assertEqual((skull.charge,skull.harvest),(0,0))

    def test_diagonal_routes_emit_through_two_and_half_seconds_and_exit_once(self):
        skull=self.skull()
        before=random.getstate()
        skull.cast()
        self.assertEqual(before,random.getstate())
        rows=copy.deepcopy(skull.procession)
        self.assertEqual(len(rows),36)
        self.assertEqual(skull.cast_left,2.5)
        self.assertGreater(max(s[4] for s in rows),2.4)
        self.assertLess(max(s[4] for s in rows),2.5)
        quadrants=set()
        for row in rows:
            vx,vy=row[2]*1280,row[3]*680
            angle=abs(math.degrees(math.atan2(abs(vy),abs(vx))))
            self.assertGreaterEqual(angle,27.9)
            self.assertLessEqual(angle,62.1)
            quadrants.add((vx>0,vy>0))
            self.assertGreater(row[5],1.0)
            self.assertLess(row[5],2.7)
            self.assertAlmostEqual(math.hypot(vx,vy),math.hypot(1280,680)*.65*.8)
            ex,ey=row[0]+row[2]*row[5],row[1]+row[3]*row[5]
            self.assertTrue(ex<0 or ex>1 or ey<0 or ey>1)
        self.assertEqual(len(quadrants),4)
        skull.update_procession(2,[])
        self.assertTrue(any(s[4]>0 for s in skull.procession))
        self.assertLess(len(skull.procession),36)  # Earlier crossings already removed.
        skull.update_procession(.5,[])
        self.assertEqual(skull.cast_left,0)
        self.assertTrue(skull.procession)  # Late emissions drain instead of disappearing.
        skull.update_procession(2,[])
        self.assertFalse(skull.procession)
        for i in range(36):
            self.assertEqual(summons.procession_route(i,1280,680,78),summons.procession_route(i,1280,680,78))

    def test_new_kills_wait_for_drain_and_survive_save(self):
        skull=self.skull()
        skull.gain_procession_charge(67)
        skull.cast()
        self.assertEqual(skull.charge,0)
        skull.gain_procession_charge(summons.PROCESSION_KILL_THRESHOLD+7)
        self.assertEqual(skull.charge,summons.PROCESSION_KILL_THRESHOLD+7)
        rows=copy.deepcopy(skull.procession)
        self.assertFalse(skull.cast())
        self.assertEqual(skull.procession,rows)
        skull.update_procession(3.05,[])
        self.assertEqual(skull.cast_left,0)
        self.assertFalse(skull.cast())
        skull.persist()
        summons.start_level(game,self.gs,self.player)
        skull=self.gs.companions[0]
        self.assertEqual(skull.charge,summons.PROCESSION_KILL_THRESHOLD+7)
        self.assertTrue(skull.procession)
        skull.update_procession(2,[])
        self.assertGreater(skull.procession_cd,0)
        self.assertFalse(skull.cast())
        skull.update_procession(summons.PROCESSION_COOLDOWN,[])
        boss=self.enemy(hp=100000)
        boss.is_boss=True
        skull.update(.01,self.enemies)
        self.assertGreater(skull.cast_left,0)
        self.assertEqual(skull.charge,0)
        self.assertEqual(len(skull.procession),36)
        with patch.object(summons,"PROCESSION_KILL_THRESHOLD",10):
            skull.update_procession(5,[])
            skull.update_procession(summons.PROCESSION_COOLDOWN,[])
            skull.gain_procession_charge(10)
            skull.update(.01,self.enemies)
            self.assertGreater(skull.cast_left,0)
            self.assertEqual(skull.charge,0)

    def test_hidden_cooldown_preserves_charge_and_disk_resume(self):
        skull=self.skull()
        skull.gain_procession_charge(60)
        skull.cast()
        finish=max(skull.cast_left,max(s[4]+s[5] for s in skull.procession))
        skull.update_procession(finish,[])
        self.assertFalse(skull.procession)
        self.assertAlmostEqual(skull.procession_cd,5)
        self.assertFalse(skull.cast())
        skull.gain_procession_charge(7)
        self.assertEqual(skull.charge,7)
        skull.update_procession(2,[])
        skull.persist()
        with tempfile.TemporaryDirectory(prefix="eidolon-cooldown-") as folder,patch.object(game,"SAVE_FILE",str(Path(folder)/"save.json")):
            persistence.save_snapshot(game,game.capture_snapshot(self.gs,self.player,[],0))
            game._load_meta_from_save(persistence.load_save(game))
            summons.start_level(game,self.gs,self.player)
        skull=self.gs.companions[0]
        self.assertAlmostEqual(skull.procession_cd,3)
        self.assertEqual(skull.charge,7)
        screen=pygame.Surface((1280,720),pygame.SRCALPHA)
        skull.draw(screen,640,500)
        with_cd=pygame.image.tobytes(screen,"RGBA")
        skull.update_procession(3,[])
        screen.fill((0,0,0,0))
        skull.draw(screen,640,500)
        self.assertEqual(with_cd,pygame.image.tobytes(screen,"RGBA"))
        skull.gain_procession_charge(summons.PROCESSION_KILL_THRESHOLD-7)
        boss=self.enemy()
        boss.is_boss=True
        skull.update(.01,self.enemies)
        self.assertGreater(skull.cast_left,0)
        self.assertEqual(skull.charge,0)

    def test_charge_bar_empties_on_cast_and_refills_only_from_new_kills(self):
        skull=self.skull()
        skull.gain_procession_charge(300)
        screen=pygame.Surface((1280,720),pygame.SRCALPHA)
        def meter_width():
            with patch.object(pygame.draw,"rect",wraps=pygame.draw.rect) as rect:
                skull.draw(screen,640,500)
            fills=[call.args[2][2] for call in rect.call_args_list if call.args[1] in ((244,168,255),(174,95,232))]
            return fills[0]
        self.assertEqual(meter_width(),48)
        skull.cast()
        self.assertEqual(meter_width(),0)
        self.assertEqual(game.META["skull_combat"]["charge"],0)
        for i in range(summons.PROCESSION_KILL_THRESHOLD//2):
            target=self.enemy(hp=1)
            summons.damage_enemy(game,self.gs,self.enemies,target,100,skull)
        self.assertEqual(meter_width(),24)
        self.assertFalse(skull.cast())  # Rejected requests must not clear progress.
        self.assertEqual(skull.charge,summons.PROCESSION_KILL_THRESHOLD//2)
        skull.persist()
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].charge,summons.PROCESSION_KILL_THRESHOLD//2)

    def test_cooldown_coarse_step_reset_and_old_save_defaults(self):
        skull=self.skull()
        skull.cast()
        finish=max(skull.cast_left,max(s[4]+s[5] for s in skull.procession))
        skull.update_procession(finish+2,[])
        self.assertAlmostEqual(skull.procession_cd,3)
        skull.persist()
        game.META["skull_combat"].pop("procession_cd")
        summons.start_level(game,self.gs,self.player)
        skull=self.gs.companions[0]
        self.assertEqual(skull.procession_cd,0)
        skull.procession_cd=4
        skull.persist()
        summons.enter_shop(game)
        self.assertEqual(game.META["skull_combat"]["procession_cd"],0)
        self.gs.current_level+=1
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].procession_cd,0)

    def test_head_rotation_matches_tail_heading_and_rear_attachment(self):
        skull=self.skull()
        skull.procession_relative=True
        screen=pygame.Surface((1280,720),pygame.SRCALPHA)
        for vx,vy in ((.5,.5),(-.5,.5),(.5,-.5),(-.5,-.5)):
            skull.procession=[[.5,.5,vx,vy,0,1,10,.5]]
            with patch.object(summon_vfx,"draw_procession_wake") as tail,patch.object(summons,"procession_head",wraps=summons.procession_head) as head:
                summons.draw_effects(game,self.gs,screen,*game.calculate_iso_camera(*self.player.rect.center))
            velocity=tail.call_args.args[2]
            sector,axis=summon_vfx.procession_heading(velocity)
            size=head.call_args.args[0]
            head.assert_called_once_with(size,sector)
            rear=pygame.Vector2(tail.call_args.args[1])
            self.assertAlmostEqual((pygame.Vector2(640,380)-rear).dot(axis),size*.24,delta=2)
            angle=sector*360/64
            source=summons.sprite(3,size)
            if axis.x<0:
                source=pygame.transform.flip(source,True,False)
                angle-=180
            # A tilted but upright crown: the artwork's up vector stays in
            # the upper half-plane while its nose still follows the route.
            self.assertGreater(math.cos(math.radians(angle)),0)
            expected=pygame.transform.rotate(source,-angle)
            self.assertEqual(pygame.image.tobytes(summons.procession_head(size,sector),"RGBA"),pygame.image.tobytes(expected,"RGBA"))

    def test_regular_shots_are_larger_deeper_and_twenty_percent_slower(self):
        skull=self.skull(1)
        self.enemy()
        with patch.object(skull,"update_shots"):
            skull.update(1/60,self.enemies)
        self.assertEqual(len(skull.shots),1)
        shot=skull.shots[0]
        self.assertAlmostEqual(math.hypot(shot["vx"],shot["vy"]),game.BULLET_SPEED*.75*.8)
        shot["target"]=None
        start=pygame.Vector2(shot["x"],shot["y"])
        skull.update_shots(.01,[])
        self.assertAlmostEqual(start.distance_to((shot["x"],shot["y"])),game.BULLET_SPEED*.60*.01)
        self.assertEqual(summon_vfx.ORB_RADIUS,9)
        screen=pygame.Surface((100,100),pygame.SRCALPHA)
        summon_vfx.draw_orb(screen,[(50,50)])
        self.assertGreater(screen.get_bounding_rect().w,13)
        body=screen.get_at((55,50))
        self.assertEqual(tuple(body),(151,43,226,220))

    def test_wake_rear_is_fainter_and_narrower(self):
        art=summon_vfx.procession_wake(140,0)
        def profile(lo,hi):
            values=[(y,art.get_at((x,y)).a) for x in range(lo,hi) for y in range(art.get_height())]
            ys=[y for y,a in values if a>5]
            return sum(a for y,a in values),max(ys)-min(ys)
        rear=profile(30,80)
        front=profile(260,310)
        self.assertLess(rear[0],front[0]*.5)
        self.assertLess(rear[1],front[1])

    def test_death_dissolves_once_and_resumes_without_replaying(self):
        skull = self.skull()
        skull.take_damage(99999)
        self.assertEqual(skull.death_age,0)
        skull.update(.5,[])
        skull.take_damage(99999)
        self.assertAlmostEqual(skull.death_age,.5)
        skull.persist()
        summons.start_level(game,self.gs,self.player)
        skull = self.gs.companions[0]
        self.assertAlmostEqual(skull.death_age,.5)
        skull.update(2,[])
        self.assertEqual(skull.death_age,summon_vfx.DEATH_DURATION)
        art = summons.directional_sprite(2,72,1)
        before = random.getstate()
        first = summon_vfx.dissolve_frame(art,0)
        late = summon_vfx.dissolve_frame(art,.9)
        end = summon_vfx.dissolve_frame(art,1)
        self.assertGreater(pygame.mask.from_surface(first).count(),pygame.mask.from_surface(late).count())
        self.assertEqual(pygame.mask.from_surface(end).count(),0)
        self.assertEqual(before,random.getstate())

    def test_orb_trail_longer_and_time_bounded(self):
        skull = self.skull(1)
        self.enemy(15,8)
        skull.update(1/60,self.enemies)
        shot = skull.shots[0]
        self.assertEqual(shot["visual_origin"],skull.eye_offset())
        for _ in range(22):
            skull.update_shots(1/60,self.enemies)
        self.assertIn(shot,skull.shots)
        self.assertGreater(len(shot["trail"]),8)
        self.assertLessEqual(len(shot["trail"]),19)
        screen = pygame.display.get_surface()
        before = random.getstate()
        summons.draw_effects(game,self.gs,screen,0,0)
        self.assertEqual(before,random.getstate())

    def test_beam_duration_damage_cooldown_and_stage_gate(self):
        skull = self.skull()
        enemy = self.enemy()
        initial = enemy.hp
        for _ in range(180):
            skull.update_beam(1/60,self.enemies)
        self.assertEqual(initial-enemy.hp,9*skull.damage)
        self.assertEqual(skull.beam_left,0)
        self.assertEqual(skull.beam_cd,12)
        skull.update_beam(11.9,self.enemies)
        self.assertEqual(enemy.hp,initial-9*skull.damage)
        skull.update_beam(.11,self.enemies)
        self.assertGreater(skull.beam_left,0)
        skull.stop_beam()
        skull.level = 3
        skull.beam_cd = 0
        skull.update_beam(1,self.enemies)
        self.assertEqual(skull.beam_left,0)

    def test_beam_lock_retarget_kill_harvest_and_charge(self):
        skull = self.skull()
        first = self.enemy(12,8,hp=1000)
        skull.update_beam(.1,self.enemies)
        second = self.enemy(11,8,hp=1000)
        skull.update_beam(.1,self.enemies)
        self.assertIs(skull.beam_target,first)
        first.hp = 1
        skull.update_beam(.1,self.enemies)
        self.assertNotIn(first,self.enemies)
        self.assertEqual((skull.harvest,skull.charge),(1,1))
        remaining = skull.beam_left
        skull.update_beam(.1,self.enemies)
        self.assertIs(skull.beam_target,second)
        self.assertLess(skull.beam_left,remaining)
        self.assertLess(second.hp,1000)

    def test_beam_wall_blocks_then_breaks_without_harvest(self):
        skull = self.skull()
        target = self.enemy(13,8)
        wall = game.Obstacle(11,8,"Destructible")
        wall.health = 10
        self.gs.obstacles[11,8] = wall
        original = target.hp
        skull.update_beam(.1,self.enemies)
        self.assertEqual(target.hp,original)
        self.assertLess(wall.health,10)
        skull.update_beam(.1,self.enemies)
        self.assertNotIn((11,8),self.gs.obstacles)
        self.assertEqual((skull.harvest,skull.charge),(0,0))
        skull.update_beam(.1,self.enemies)
        self.assertLess(target.hp,original)
        self.gs.obstacles[11,8] = game.Obstacle(11,8,"Indestructible")
        original = target.hp
        skull.update_beam(.2,self.enemies)
        self.assertEqual(target.hp,original)
        self.assertIn((11,8),self.gs.obstacles)

    def test_beam_save_resume_downing_and_no_target_timeout(self):
        skull = self.skull()
        target = self.enemy()
        skull.update_beam(.35,self.enemies)
        skull.persist()
        left,credit = skull.beam_left,skull.beam_credit
        summons.start_level(game,self.gs,self.player)
        skull = self.gs.companions[0]
        self.assertEqual((skull.beam_left,skull.beam_credit),(left,credit))
        skull.update_beam(.1,self.enemies)
        self.assertIs(skull.beam_target,target)
        self.enemies.clear()
        skull.update_beam(3,[])
        self.assertEqual(skull.beam_left,0)
        self.assertEqual(skull.beam_cd,12)
        self.enemy()
        skull.beam_cd = 0
        skull.update_beam(.1,self.enemies)
        skull.take_damage(99999)
        self.assertEqual(skull.beam_left,0)
        self.assertIsNone(skull.beam_end)

    def test_beam_coexists_with_normal_attacks_and_procession(self):
        skull = self.skull()
        target = self.enemy()
        target.is_boss = True
        skull.charge = summons.PROCESSION_KILL_THRESHOLD
        skull.update(1/60,self.enemies)
        self.assertGreater(skull.beam_left,0)
        self.assertGreater(skull.cast_left,0)
        self.assertEqual(len(skull.shots),5)
        summons.enter_shop(game)
        self.assertEqual(game.META["skull_combat"]["beam_left"],0)
        self.gs.current_level=1
        summons.start_level(game,self.gs,self.player)
        self.assertEqual(self.gs.companions[0].beam_left,0)

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
