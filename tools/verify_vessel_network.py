"""Check connected, curved vessels and the production cutout asset contract."""
import math
import os
from pathlib import Path
import random
import sys
import unittest

os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pygame
from zgame import neural_environment as art
from zgame.vessel_network import network_geometry, point_clear, branch_alpha, layout_seed, breathing_profile


def direction(a,b):
    x,y=b[0]-a[0],b[1]-a[1]
    length=math.hypot(x,y)
    return x/length,y/length


class VesselTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((320,240))

    def test_branches_are_attached_tangent_continuous_and_tapered(self):
        for region in ('Wind','Forest','Fire','Mountain'):
            paths,_=network_geometry(36,region)
            for path in paths:
                if path.parent<0:
                    continue
                parent=paths[path.parent]
                at=path.attachment
                self.assertEqual(path.points[0],parent.points[at])
                tangent=direction(parent.points[at-1],parent.points[at+1])
                outgoing=direction(path.points[0],path.points[1])
                self.assertGreater(sum(a*b for a,b in zip(tangent,outgoing)),.995)
                if not path.main:
                    self.assertLess(path.radii[-1],path.radii[0]*.1)
                    self.assertEqual(path.strengths[-1],0)

    def test_breathing_has_long_varied_cycles_and_a_visible_energy_range(self):
        profiles=[breathing_profile(i*math.tau/8) for i in range(8)]
        self.assertGreater(max(p[0] for p in profiles)-min(p[0] for p in profiles),1)
        self.assertGreater(max(p[1] for p in profiles)-min(p[1] for p in profiles),20)
        for i,(period,amplitude) in enumerate(profiles):
            self.assertTrue(4<=period<=7)
            phase=i*math.tau/8
            samples=[branch_alpha(phase,t) for t in range(0,14000,17)]
            self.assertLessEqual(min(samples),25)
            self.assertGreaterEqual(max(samples),190)
            self.assertLessEqual(max(abs(a-b) for a,b in zip(samples,samples[1:])),3)

    def test_seeded_graph_has_local_hierarchy_and_global_coverage(self):
        signatures=set()
        for seed in (12,41,98,337,901):
            paths,hubs=network_geometry(36,'Wind',seed)
            signatures.add(tuple((n.x,n.y) for n in hubs))
            self.assertGreater(len(hubs),8)
            self.assertEqual({p.kind for p in paths},{'trunk','secondary','capillary'})
            roots=[p for p in paths if p.parent<0]
            majors=[p for p in roots if p.main]
            lengths=[sum(math.dist(a,b) for a,b in zip(p.points,p.points[1:])) for p in majors]
            self.assertGreater(len(majors),3)
            self.assertGreater(sum(lengths)/len(lengths),14,'Main routes must span multiple old graph edges')
            spans=[(max(x-y for x,y in p.points)-min(x-y for x,y in p.points))*41 for p in majors]
            self.assertGreater(sum(384<=span<=1000 for span in spans),len(majors)*.35)
            curved=sum(sum(math.dist(a,b) for a,b in zip(p.points,p.points[1:]))>
                       math.dist(p.points[0],p.points[-1])*1.005 for p in roots)
            self.assertGreater(curved/len(roots),.65)
            self.assertGreater(max(max(p.radii) for p in paths)/min(max(p.radii) for p in paths),5)
            self.assertGreater(max(max(p.strengths) for p in paths)/min(max(p.strengths) for p in paths),2.5)
            for x,y in ((5,5),(5,30),(30,5),(30,30),(18,18)):
                self.assertLess(min(math.dist((x,y),p) for path in paths for p in path.points[::5]),5)
            for path in paths:
                depth=1; parent=path.parent
                while parent>=0:
                    depth+=1; parent=paths[parent].parent
                self.assertLessEqual(depth,3)
                # Interior joins must not reset width, creating repeated beads.
                self.assertLess(max(abs(a-b) for a,b in zip(path.radii,path.radii[1:])),.3)
        self.assertEqual(len(signatures),5,'Map seeds must generate genuinely different networks')

    def test_wall_aware_routes_and_unmoving_asynchronous_breathing(self):
        blocked=tuple((18,y) for y in range(3,33))
        paths,hubs=network_geometry(36,'Forest',layout_seed(blocked),blocked)
        for path in paths:
            self.assertTrue(all(point_clear(p,36,set(blocked)) for p in path.points))
        self.assertTrue(all(point_clear((n.x,n.y),36,set(blocked),.4) for n in hubs))
        self.assertGreater(len({branch_alpha(p.phase,1000) for p in paths}),20)
        changes=[branch_alpha(p.phase,1800)-branch_alpha(p.phase,1600) for p in paths]
        self.assertLess(min(changes),0)
        self.assertGreater(max(changes),0,'Some branches must brighten while others dim')
        self.assertTrue(all(abs(branch_alpha(p.phase,1016)-branch_alpha(p.phase,1000))<4 for p in paths))
        self.assertIs(paths,network_geometry(36,'Forest',layout_seed(blocked),blocked)[0])

    def test_generation_is_deterministic_without_touching_combat_rng(self):
        before=random.getstate()
        first=network_geometry(36,'Forest')
        network_geometry.cache_clear()
        self.assertEqual(first,network_geometry(36,'Forest'))
        self.assertEqual(before,random.getstate())

    def test_cutouts_are_transparent_distinct_and_used_by_walls(self):
        names={art.structure_name(fragile,seed) for fragile in (False,True) for seed in range(256)}
        self.assertEqual(len(names),7)
        signatures=set()
        for name in names:
            source=art.source_asset('neural-parts-v2/'+name+'.png')
            self.assertIsNotNone(source,name)
            mask=pygame.mask.from_surface(source,20)
            self.assertGreater(mask.count(),500)
            self.assertLess(mask.count(),source.get_width()*source.get_height()*.85)
            self.assertEqual(source.get_at((0,0)).a,0)
            signatures.add(pygame.image.tobytes(source,'RGBA'))
        self.assertEqual(len(signatures),7)
        for region in art.REGIONS:
            for index in range(4):
                image,anchor=art.illustrated_node(region,index)
                self.assertTrue(image.get_rect().collidepoint(anchor))
                self.assertGreater(pygame.mask.from_surface(image,15).count(),20)


if __name__=='__main__':
    unittest.main(verbosity=2)
