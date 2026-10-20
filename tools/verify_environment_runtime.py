"""Environment integration checks using real renderers, collisions and saves."""
import copy
import hashlib
import math
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pygame
import ZGame as game
from zgame import neural_environment as art, persistence, render_runtime
from zgame.browser import _normalize_diag_biome


def pixels(surface):
    return hashlib.sha256(pygame.image.tobytes(surface, "RGBA")).hexdigest()


class EnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1280, 720))

    def setUp(self):
        self.meta = copy.deepcopy(game.META)
        self.view = game.VIEW_W, game.VIEW_H
        self.level = getattr(game,"current_level",0)
        game.reset_run_state()
        game.clear_menu_transition_state()
        game.VIEW_W, game.VIEW_H = 1280, 720
        game.current_level = 0
        self.player = game.Player((8, 8))
        self.state = game.GameState({}, [], [], [])
        self.state.current_level = 0
        self.state.biome_active = "Domain of Wind"

    def tearDown(self):
        game.META.clear()
        game.META.update(self.meta)
        game.VIEW_W, game.VIEW_H = self.view
        game.current_level = self.level

    def render(self, lite=False, ticks=1000, camera=None, web_full=False):
        screen = pygame.display.get_surface()
        renderer = game.render_game_iso_web_lite if lite else game.render_game_iso
        with patch.object(game, "IS_WEB", lite or web_full), patch.object(render_runtime, "IS_WEB", lite or web_full), \
             patch.object(game, "WEB_ENABLE_FOG", False), patch.object(pygame.time, "get_ticks", return_value=ticks):
            renderer(screen, self.state, self.player, [], [], [], override_cam=camera, copy_frame=False)
        return screen.copy()

    def test_full_browser_wall_depth_matches_desktop_after_camera_moves(self):
        self.state.obstacles[9,9] = game.Obstacle(9,9,"Indestructible")
        self.state.obstacles[10,9] = game.Obstacle(10,9,"Destructible",health=20)
        for pos in ((8,8),(10,10),(8,10),(10,8)):
            self.player = game.Player(pos)
            camera = game.calculate_iso_camera(*self.player.rect.center)
            native = self.render(camera=camera)
            browser = self.render(camera=camera,web_full=True)
            sx,sy = game.iso_world_to_screen(9,9,0,*camera)
            area = pygame.Rect(round(sx-50),round(sy-110),100,140).clip(native.get_rect())
            self.assertEqual(pixels(native.subsurface(area)),pixels(browser.subsurface(area)),pos)

    def test_player_marker_only_when_foreground_wall_covers_the_core(self):
        for lite,web_full in ((False,False),(True,False),(False,True)):
            self.state.obstacles.clear()
            for pos,wall,expected in (((8,8),False,False),((8,8),True,True),((10,10),True,False)):
                self.player = game.Player(pos)
                if wall:
                    self.state.obstacles[9,9] = game.Obstacle(9,9,"Indestructible")
                with patch.object(pygame.draw,"circle",wraps=pygame.draw.circle) as circles:
                    self.render(lite,web_full=web_full)
                marker = any(call.args[1] == (151,219,233) and call.args[3] == 3
                             for call in circles.call_args_list)
                self.assertEqual(marker,expected,(lite,web_full,pos))

    def test_wall_cap_is_visible_when_its_foot_is_below_the_viewport(self):
        sx,sy = game.iso_world_to_screen(9,9,0,0,0)
        camera = (sx-640,sy-780)
        for lite,web_full in ((False,False),(True,False),(False,True)):
            self.state.obstacles.clear()
            clear = self.render(lite,camera=camera,web_full=web_full)
            self.state.obstacles[9,9] = game.Obstacle(9,9,"Indestructible")
            wall = self.render(lite,camera=camera,web_full=web_full)
            area = pygame.Rect(620,690,40,25)
            self.assertNotEqual(pixels(clear.subsurface(area)),pixels(wall.subsurface(area)))

    def test_real_projectiles_damage_destroy_and_unblock_in_both_renderers(self):
        for lite in (False, True):
            with self.subTest(lite=lite):
                self.state = game.GameState({}, [], [], [])
                wall = game.Obstacle(10, 8, "Destructible", health=game.OBSTACLE_HEALTH)
                self.state.obstacles[10, 8] = wall
                self.player = game.Player((9, 8))
                start = self.player.x, self.player.y
                game.collide_and_slide_circle(self.player, self.state.obstacles.values(), 130, 0)
                self.assertLessEqual(self.player.rect.centerx, wall.rect.left-self.player.radius+1)
                self.player.x, self.player.y = start
                self.player.rect.topleft = (start[0], start[1]+game.INFO_BAR_HEIGHT)
                healthy = self.render(lite)
                original_key = self.state._web_wall_layer_cache["key"] if lite else None
                hp = wall.health
                hits = 0
                while (10, 8) in self.state.obstacles:
                    bullet = game.Bullet(*wall.rect.center, 0, 0, max_dist=400, damage=10)
                    bullet.update(0.0, self.state, [], self.player)
                    hits += 1
                    self.assertFalse(bullet.alive)
                    self.assertEqual(wall.health, hp-hits*game.BULLET_DAMAGE_BLOCK)
                    if hits == 1:
                        damaged = self.render(lite)
                        self.assertNotEqual(pixels(healthy), pixels(damaged))
                        if lite:
                            self.assertNotEqual(original_key, self.state._web_wall_layer_cache["key"])
                    self.assertLess(hits, 30)
                self.assertEqual(hits, math.ceil(hp/game.BULLET_DAMAGE_BLOCK))
                removed = self.render(lite)
                self.assertNotEqual(pixels(damaged), pixels(removed))
                if lite:
                    self.assertIsNone(self.state._web_wall_layer_cache["surface"])
                # Render against a fresh empty-state control: no ghost wall remains.
                self.state = game.GameState({}, [], [], [])
                control = self.render(lite)
                cam = game.calculate_iso_camera(*self.player.rect.center)
                sx,sy = game.iso_world_to_screen(10,8,0,*cam)
                # Ignore reward coins at the foot and HUD counters; compare the
                # space that the raised wall body previously occupied.
                body = pygame.Rect(round(sx-25),round(sy-80),50,60)
                self.assertEqual(pixels(removed.subsurface(body)),pixels(control.subsurface(body)))
                game.collide_and_slide_circle(self.player, self.state.obstacles.values(), 130, 0)
                self.assertGreater(self.player.rect.centerx, wall.rect.right)
                permanent = game.Obstacle(10,8,"Indestructible")
                self.state.obstacles[10,8] = permanent
                bullet = game.Bullet(*permanent.rect.center,0,0,max_dist=400,damage=1000)
                bullet.update(0.0,self.state,[],self.player)
                self.assertFalse(bullet.alive)
                self.assertIs(self.state.obstacles[10,8],permanent)

    def test_network_breathes_without_rebuilding_or_pulsing_ground(self):
        random_before = random.getstate()
        self.render()
        cache = game._iso_floor_cache
        floor_hash = pixels(cache["surface"])
        signatures = set()
        for legacy in art.REGIONS:
            self.state.biome_active = legacy
            first = self.render(ticks=1000)
            layer = art.network_surface(game.GRID_SIZE, game.ISO_CELL_W, game.ISO_CELL_H,
                game.INFO_BAR_HEIGHT, cache["surface"].get_size(), cache["x0"], cache["y0"], legacy)
            second = self.render(ticks=4000)
            self.assertNotEqual(pixels(first), pixels(second))
            self.assertEqual(floor_hash, pixels(cache["surface"]))
            self.assertIs(cache, game._iso_floor_cache)
            self.assertIs(layer, art.network_surface(game.GRID_SIZE,game.ISO_CELL_W,game.ISO_CELL_H,
                game.INFO_BAR_HEIGHT,cache["surface"].get_size(),cache["x0"],cache["y0"],legacy))
            self.assertEqual(layer.get_at((0, 0)).a, 0)
            signatures.add(pixels(layer))
            # Coverage is global, rather than a patch around the player.
            for gx,gy in ((5,5),(5,30),(30,5),(30,30),(18,18)):
                sx,sy = game.iso_world_to_screen(gx,gy,0,0,0)
                box = pygame.Rect(int(sx-cache["x0"]-160),int(sy-cache["y0"]-80),320,160).clip(layer.get_rect())
                self.assertGreater(pygame.mask.from_surface(layer.subsurface(box),20).count(),0)
        self.assertEqual(len(signatures),4)
        self.assertEqual(random_before,random.getstate())

    def test_random_layouts_cameras_and_renderer_ground_parity(self):
        for seed in (12,41,98,337,901):
            random.seed(seed)
            obs,items,pos,_,_,decor = game.generate_game_entities(game.GRID_SIZE,70,10,6,game.MAIN_BLOCK_HEALTH)
            self.state = game.GameState(obs,[],[],decor)
            self.player = game.Player(pos)
            before = [(key,ob.rect.copy(),ob.health) for key,ob in obs.items()]
            for region in art.REGIONS:
                self.state.biome_active = region
                for camera in (None,(-700,150),(650,400)):
                    self.render(camera=camera)
                    self.render(True,camera=camera)
            self.assertEqual(before,[(key,ob.rect,ob.health) for key,ob in self.state.obstacles.items()])
        # Clear scene isolates the shared floor/network from UI and actor differences.
        self.state = game.GameState({},[],[],[])
        for region in art.REGIONS:
            self.state.biome_active = region
            native,lite = self.render(),self.render(True)
            self.assertEqual(pixels(native.subsurface((100,100,250,150))),
                             pixels(lite.subsurface((100,100,250,150))))

    def test_legacy_regions_roundtrip_with_effects_and_existing_save_is_untouched(self):
        save = Path(game.SAVE_FILE)
        original = save.read_bytes() if save.exists() else None
        with tempfile.TemporaryDirectory(prefix="neural-save-") as folder:
            target = Path(folder)/"save.json"
            if original:
                target.write_bytes(original)
                with patch.object(game,"SAVE_FILE",str(target)):
                    existing = persistence.load_save(game)
                self.assertIsInstance(existing,dict)
                self.assertEqual(target.read_bytes(),original)
                clean = game._sanitize_resume_save_data(existing)
                self.assertIsNotNone(clean)
                saved_region = clean.get("biome",clean.get("meta",{}).get("biome"))
                if saved_region is not None:
                    self.assertIn(saved_region,art.REGIONS)
                    resumed = game._apply_resume_save_data(existing)
                    self.assertEqual(game._next_biome,saved_region)
                    self.assertEqual(game.current_level,game._resume_level_from_save(resumed))
                    restored_state = game.GameState({},[],[],[])
                    restored_player = game.Player((8,8))
                    game.apply_domain_buffs_for_level(restored_state,restored_player)
                    self.assertEqual(restored_state.biome_active,saved_region)
                    self.assertEqual(art.region_name(restored_state.biome_active),
                                     art.region_name(saved_region))
            for region in art.REGIONS:
                self.state = game.GameState({},[],[],[])
                self.player = game.Player((8,8))
                game._next_biome = region
                base_damage = self.player.bullet_damage
                game.apply_domain_buffs_for_level(self.state,self.player)
                if region == "Misty Forest":
                    self.assertTrue(self.state._fog_biome_forced)
                    self.assertEqual(self.player.xp_gain_mult,1.3)
                elif region == "Domain of Wind":
                    self.assertTrue(self.state.hurricanes)
                    self.assertEqual(self.player._biome_speed_mult,1.12)
                elif region == "Scorched Hell":
                    self.assertEqual(self.player.bullet_damage,base_damage*2)
                    self.assertEqual(self.state.biome_enemy_contact_mult,2)
                else:
                    self.assertEqual(self.player.shield_hp,round(self.player.max_hp*.5))
                payload = game.capture_snapshot(self.state,self.player,[],0)
                with patch.object(game,"SAVE_FILE",str(target)):
                    persistence.save_snapshot(game,payload)
                    restored = persistence.load_save(game)
                self.assertEqual(restored["meta"]["biome"],region)
                self.assertEqual(_normalize_diag_biome(art.region_name(region)),region)
                self.assertEqual(restored["snapshot"]["player"]["hp"],self.player.hp)
        if original is not None:
            self.assertEqual(save.read_bytes(),original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
