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

    def test_lite_wall_cache_preserves_translucent_edges_after_direct_render(self):
        from zgame import terrain_art
        for kind,color in (("Indestructible",(75,91,119)),("Destructible",(147,135,144))):
            with self.subTest(kind=kind):
                self.state.obstacles.clear()
                self.state.obstacles[10,8] = game.Obstacle(10,8,kind,health=20)
                self.render()  # Exercise the optimized direct blit before cache assembly.
                self.render(lite=True)
                cache = self.state._web_wall_layer_cache
                source,ax,ay = terrain_art.wall_tile(game.ISO_CELL_W,game.ISO_CELL_H,
                    game.ISO_WALL_Z,color,art.wall_variant(10,8,self.state.obstacles),game.WALL_STYLE)
                sx,sy = game.iso_world_to_screen(10,8,0,0,0)
                left,top = int(sx-ax)-cache["x0"],int(sy-ay)-cache["y0"]
                translucent = 0
                for y in range(source.get_height()):
                    for x in range(source.get_width()):
                        alpha = source.get_at((x,y)).a
                        translucent += 0 < alpha < 255
                        self.assertEqual(cache["surface"].get_at((left+x,top+y)).a,alpha,(x,y))
                self.assertGreater(translucent,100)

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

    def test_animation_and_camera_motion_reuse_network_and_sprite_caches(self):
        self.state.obstacles[10,8] = game.Obstacle(10,8,"Destructible",health=20)
        camera = game.calculate_iso_camera(*self.player.rect.center)
        for index in range(4):
            art.illustrated_node(self.state.biome_active,index)
        self.render(ticks=1000,camera=camera)
        counts = (art.network_surface.cache_info().misses,
                  art.network_material.cache_info().misses,
                  art.illustrated_node.cache_info().misses,
                  art.illustrated_wall.cache_info().misses)
        for frame in range(1,9):
            self.render(ticks=1000+frame*130,
                        camera=(camera[0]+frame*3,camera[1]-frame*2))
        self.assertEqual(counts,(art.network_surface.cache_info().misses,
                                art.network_material.cache_info().misses,
                                art.illustrated_node.cache_info().misses,
                                art.illustrated_wall.cache_info().misses))

    def test_phase_batches_preserve_transparency_and_local_breathing(self):
        stamps = []
        for phase in range(art.NETWORK_PHASES):
            for x in (0, 8):
                image = pygame.Surface((24, 24), pygame.SRCALPHA)
                pygame.draw.line(image, (80, 160, 240, 200), (2, 12), (22, 12), 3)
                stamps.append((image, (x, phase*32), phase*math.tau/art.NETWORK_PHASES))
        batches = art.batch_network_stamps(stamps)
        self.assertEqual(len(batches), art.NETWORK_PHASES)
        self.assertEqual(len({phase for _, _, phase in batches}), art.NETWORK_PHASES)
        original = pygame.Surface((48, 260), pygame.SRCALPHA)
        merged = original.copy()
        for image, pos, _ in stamps: original.blit(image, pos)
        for image, pos, _ in batches: merged.blit(image, pos)
        self.assertEqual(pygame.mask.from_surface(original, 0).count(),
                         pygame.mask.from_surface(merged, 0).count())
        self.assertEqual(pixels(original), pixels(merged))
        changes = [art.branch_alpha(phase, 1400)-art.branch_alpha(phase, 1000)
                   for _, _, phase in batches]
        self.assertGreater(max(changes), 10)
        self.assertLess(min(changes), -10)
        for _, _, phase in batches:
            self.assertLessEqual(max(abs(art.branch_alpha(phase, t+17)-art.branch_alpha(phase, t))
                                     for t in range(0, 8000, 17)), 3)

    def test_batched_network_stays_world_anchored_across_camera_motion(self):
        self.render()
        cache = game._iso_floor_cache
        args = (cache, game.GRID_SIZE, game.ISO_CELL_W, game.ISO_CELL_H,
                game.INFO_BAR_HEIGHT, self.state.biome_active)
        a, b = pygame.Surface((700, 500)), pygame.Surface((700, 500))
        for blend in (0, pygame.BLEND_ALPHA_SDL2):
            with patch.object(art, 'NETWORK_BLEND', blend):
                for ticks in (1000, 1733):
                    a.fill((30, 40, 60)); b.fill((30, 40, 60))
                    art.draw_network(a, *args, -350, 350, ticks, self.state)
                    art.draw_network(b, *args, -313, 373, ticks, self.state)
                    self.assertEqual(pixels(a.subsurface((37, 23, 663, 477))),
                                     pixels(b.subsurface((0, 0, 663, 477))))

    def test_region04_energy_visibly_changes_without_losing_the_base(self):
        from zgame.vessel_network import breathing_profile, network_geometry
        from PIL import Image, ImageChops
        path=next(p for p in network_geometry(36,'Mountain')[0] if p.main)._replace(phase=0)
        mid=path.points[len(path.points)//2]
        camera=((mid[0]-mid[1])*game.ISO_CELL_W*.5-320,
                (mid[0]+mid[1])*game.ISO_CELL_H*.5+game.INFO_BAR_HEIGHT-240)
        cache={'surface':pygame.Surface((36*game.ISO_CELL_W+1,36*game.ISO_CELL_H+81)),
               'x0':-18*game.ISO_CELL_W,'y0':0}
        period,_=breathing_profile(0)
        frames=[]
        art.network_material.cache_clear(); art.network_surface.cache_clear()
        with patch.object(art,'network_geometry',return_value=((path,),())):
            for time_in_cycle in (.75,1,1.25):
                target=pygame.Surface((640,480)); target.fill((30,40,60))
                art.draw_network(target,cache,36,game.ISO_CELL_W,game.ISO_CELL_H,
                                 game.INFO_BAR_HEIGHT,'Bastion of Stone',*camera,round(period*1000*time_in_cycle))
                sample=target.subsurface((310,230,20,20))
                frames.append(Image.frombytes('RGB',sample.get_size(),pygame.image.tobytes(sample,'RGB')))
        self.assertGreater(frames[0].getextrema()[2][1],65,'Vessel remains visible at minimum')
        self.assertGreater(ImageChops.difference(frames[0],frames[2]).getextrema()[2][1],35,
                           'Actual composited light needs a perceptible dim/peak difference')
        self.assertLess(frames[0].getextrema()[2][1],frames[1].getextrema()[2][1])
        self.assertLess(frames[1].getextrema()[2][1],frames[2].getextrema()[2][1])
        color=art.region_style('Bastion of Stone')[2]
        self.assertGreater(color[2],color[0]*2,'Region 04 must use cyan-blue instead of gold')
        expected=pygame.Surface((1,1),pygame.SRCALPHA).convert_alpha().get_masks()
        for index in range(4): self.assertEqual(art.illustrated_node('Bastion of Stone',index)[0].get_masks(),expected)
        art.network_material.cache_clear(); art.network_surface.cache_clear()

    def test_saved_network_layout_survives_wall_destruction_and_real_resume(self):
        import asyncio
        import json
        from zgame import app_flow
        from zgame.vessel_network import network_geometry
        wall = game.Obstacle(10,8,"Destructible",health=20)
        state = game.GameState({(10,8):wall},[],[],[])
        original = network_geometry(game.GRID_SIZE,'Wind',state.network_seed,state.network_obstacles)
        del state.obstacles[10,8]
        payload = json.loads(json.dumps(game.capture_snapshot(state,self.player,[],0)))
        restored = []
        factory = game.GameState
        class StopAfterLayout(Exception): pass
        def record(*args,**kwargs):
            result = factory(*args,**kwargs)
            restored.append(result)
            return result
        with patch.object(game,'GameState',side_effect=record), \
             patch.object(game,'Player',side_effect=StopAfterLayout):
            with self.assertRaises(StopAfterLayout):
                asyncio.run(app_flow.run_from_snapshot(game,payload))
        self.assertFalse(restored[0].obstacles)
        self.assertEqual(restored[0].network_obstacles,((10,8),))
        self.assertEqual(original,network_geometry(game.GRID_SIZE,'Wind',
            restored[0].network_seed,restored[0].network_obstacles))

    def test_abyss_is_visible_beyond_transparent_floor_in_all_renderers(self):
        self.player = game.Player((20,4))
        camera = game.calculate_iso_camera(*self.player.rect.center)
        area = pygame.Rect(1000,80,180,150)
        baseline = None
        for region in art.REGIONS:
            self.state.biome_active = region
            for lite,web in ((False,False),(True,False),(False,True)):
                frame = self.render(lite,camera=camera,web_full=web)
                section = frame.subsurface(area)
                signature = pixels(section)
                if baseline is None:
                    baseline = signature
                    colors = {tuple(section.get_at((x,y))) for x in range(0,180,12)
                              for y in range(0,150,12)}
                    self.assertGreater(len(colors),40,"Abyss must contain painted depth, not a flat fill")
                self.assertEqual(signature,baseline,"Ground region must not recolor backdrop or add a badge")
        self.assertEqual(game._iso_floor_cache['surface'].get_at((0,0)).a,0)

    def test_open_layouts_keep_spawn_connected_after_wall_run_generation(self):
        for seed in (12,41,98,337,901):
            random.seed(seed)
            obs,items,pos,_,_,_ = game.generate_game_entities(game.GRID_SIZE,20,10,6,game.MAIN_BLOCK_HEALTH)
            self.assertLess(len(obs)/(game.GRID_SIZE**2),.08)
            blocked = {p for p,ob in obs.items() if ob.type=='Indestructible'}
            reached = {pos}
            pending = [pos]
            while pending:
                x,y = pending.pop()
                for cell in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                    if (0<=cell[0]<game.GRID_SIZE and 0<=cell[1]<game.GRID_SIZE
                            and cell not in blocked and cell not in reached):
                        reached.add(cell)
                        pending.append(cell)
            self.assertGreaterEqual(len(reached)/(game.GRID_SIZE**2-len(blocked)),.98)

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

    def test_wall_families_are_varied_stable_and_do_not_change_collision(self):
        forms = set()
        for seed in (12,41,98,337,901):
            random.seed(seed)
            obs,_,_,_,_,_ = game.generate_game_entities(game.GRID_SIZE,70,10,6,game.MAIN_BLOCK_HEALTH)
            before = [(p,o.rect.copy(),o.health) for p,o in obs.items()]
            rng = random.getstate()
            selected = {p:art.wall_variant(*p,obs) for p in obs}
            forms.update(art.structure_name(o.type == "Destructible",selected[p])
                         for p,o in obs.items())
            restored = dict(reversed(list(obs.items())))
            self.assertEqual(selected,{p:art.wall_variant(*p,restored) for p in restored})
            self.assertGreaterEqual(len({(v>>3)&3 for v in selected.values()}),3)
            self.assertEqual({bool(v&128) for v in selected.values()},{False,True})
            heights = {art.wall_extrusion(game.ISO_WALL_Z,v) for v in selected.values()}
            self.assertGreaterEqual(len(heights),4)
            self.assertLess(min(heights),game.ISO_WALL_Z*.6)
            self.assertGreater(max(heights),game.ISO_WALL_Z)
            isolated = sum(all(q not in obs for q in ((x-1,y),(x+1,y),(x,y-1),(x,y+1))) for x,y in obs)
            self.assertLess(isolated/len(obs),.15)
            # Destroying a neighbor may expose an endpoint, but cannot reroll
            # the remaining formation's height family or decoration detail.
            removed = next(iter(restored))
            del restored[removed]
            for p in restored:
                self.assertEqual(selected[p]&27,art.wall_variant(*p,restored)&27)
            self.assertEqual(before,[(p,o.rect,o.health) for p,o in obs.items()])
            self.assertEqual(rng,random.getstate())
        self.assertEqual(len(forms),7,"All seven source forms must occur across generated maps")

    def test_background_actual_blits_follow_camera_at_distinct_depths(self):
        class RecordedScreen:
            def __init__(self):
                self.surface = pygame.Surface((1280,720))
                self.blits = []
            def get_size(self): return self.surface.get_size()
            def get_rect(self): return self.surface.get_rect()
            def blit(self,source,dest,*args,**kw):
                rect = self.surface.blit(source,dest,*args,**kw)
                self.blits.append((source,tuple(dest)[:2]))
                return rect
        def draw(camera,ticks=1000):
            target = RecordedScreen()
            art._draw_abyss_layers(target,*camera,game.GRID_SIZE,game.ISO_CELL_W,game.ISO_CELL_H,game.INFO_BAR_HEIGHT,ticks*.001)
            return target
        start=(0,0)
        original=draw(start)
        for delta in ((200,0),(0,200),(200,200)):
            moved=draw(delta)
            for sprite,depth in ((art.abyss_view((1280,720),game.GRID_SIZE,game.ISO_CELL_W,game.ISO_CELL_H),.14),
                                 (art.distant_formation(True),.40)):
                a=next(pos for source,pos in original.blits if source is sprite)
                b=next(pos for source,pos in moved.blits if source is sprite)
                for axis in (0,1):
                    self.assertAlmostEqual(b[axis]-a[axis],-delta[axis]*depth,delta=1)
            self.assertNotEqual(pixels(original.surface),pixels(moved.surface))
        self.assertNotEqual(pixels(original.surface),pixels(draw(start,6000).surface))
        self.assertIs(original.blits[0][0],draw(start).blits[0][0])
        args=((1280,720),0,0,game.GRID_SIZE,game.ISO_CELL_W,game.ISO_CELL_H,game.INFO_BAR_HEIGHT)
        cached=art.abyss_scene(*args,10)
        self.assertIs(cached,art.abyss_scene(*args,10))
        self.assertNotEqual(pixels(cached),pixels(art.abyss_scene(*args,60)))
        # Moving/direct and stationary/cached composition must be identical.
        with patch.object(pygame.time,'get_ticks',return_value=1000):
            for camera in ((0,0),(240,180)):
                direct=pygame.Surface((1280,720))
                reused=pygame.Surface((1280,720))
                art.draw_abyss(direct,*camera,game.GRID_SIZE,game.ISO_CELL_W,game.ISO_CELL_H,game.INFO_BAR_HEIGHT)
                art.draw_abyss(reused,*camera,game.GRID_SIZE,game.ISO_CELL_W,game.ISO_CELL_H,game.INFO_BAR_HEIGHT)
                self.assertEqual(pixels(direct),pixels(reused))

    def test_background_covers_camera_extremes_without_tiling_or_gaps(self):
        for size in ((1280,720),(1920,1080)):
            backdrop=art.abyss_view(size,game.GRID_SIZE,game.ISO_CELL_W,game.ISO_CELL_H)
            for gx,gy in ((0,0),(0,36),(36,0),(36,36),(18,18)):
                camx=(gx-gy)*game.ISO_CELL_W*.5-size[0]*.5
                camy=(gx+gy)*game.ISO_CELL_H*.5+game.INFO_BAR_HEIGHT-size[1]*.5
                for shake in (-20,20):
                    dx,dy=art.abyss_camera_offset(size,camx+shake,camy+shake,game.GRID_SIZE,game.ISO_CELL_H,game.INFO_BAR_HEIGHT,.14)
                    rect=backdrop.get_rect(topleft=(round((size[0]-backdrop.get_width())*.5-dx),
                                                   round((size[1]-backdrop.get_height())*.5-dy)))
                    self.assertTrue(rect.contains(pygame.Rect((0,0),size)))

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
