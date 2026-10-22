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
from zgame.vessel_network import network_geometry


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
                self.assertGreater(sum(a*b for a,b in zip(tangent,outgoing)),.998)
                if not path.main:
                    self.assertLess(path.radii[-1],path.radii[0]*.1)
                    self.assertTrue(all(a>=b for a,b in zip(path.radii,path.radii[1:])))

    def test_routes_curve_across_world_and_connect_to_one_network(self):
        paths,hubs=network_geometry(36,'Wind')
        roots=[i for i,p in enumerate(paths) if p.parent<0]
        adjacent={i:set() for i in roots}
        for i in roots:
            p=paths[i]
            self.assertLess(p.points[0][0],0)
            self.assertGreater(p.points[-1][0],36)
            chord=math.dist(p.points[0],p.points[-1])
            length=sum(math.dist(a,b) for a,b in zip(p.points,p.points[1:]))
            self.assertGreater(length/chord,1.05,'Artery is too straight')
            # Dense samples keep the projected route smooth at normal zoom.
            self.assertLess(max(math.dist(a,b) for a,b in zip(p.points,p.points[1:])),.09)
        for p in paths:
            if p.main and p.parent>=0:
                matches=[i for i in roots if p.points[-1] in paths[i].points]
                self.assertEqual(len(matches),1,'A connector has a detached end')
                adjacent[p.parent].add(matches[0])
                adjacent[matches[0]].add(p.parent)
        reached={roots[0]}
        pending=list(reached)
        while pending:
            for neighbor in adjacent[pending.pop()]-reached:
                reached.add(neighbor)
                pending.append(neighbor)
        self.assertEqual(reached,set(roots))
        self.assertGreater(len(hubs),20)

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
