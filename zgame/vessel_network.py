"""Continuous world-space vessels. Geometry is deterministic and art-only."""
from functools import lru_cache
import math
import random
from typing import NamedTuple


class Vessel(NamedTuple):
    points: tuple
    radii: tuple
    main: bool
    parent: int = -1
    attachment: int = -1


def _unit(dx,dy):
    length=max(.00001,math.hypot(dx,dy))
    return dx/length,dy/length


def _cubic(a,b,c,d,steps):
    return tuple(((1-t)**3*a[0]+3*(1-t)**2*t*b[0]+3*(1-t)*t*t*c[0]+t**3*d[0],
                  (1-t)**3*a[1]+3*(1-t)**2*t*b[1]+3*(1-t)*t*t*c[1]+t**3*d[1])
                 for t in (i/steps for i in range(steps+1)))


def _trunk(knots):
    """One Catmull-Rom route, with exactly shared derivatives at every join."""
    padded=[(2*knots[0][0]-knots[1][0],2*knots[0][1]-knots[1][1]),*knots,
            (2*knots[-1][0]-knots[-2][0],2*knots[-1][1]-knots[-2][1])]
    points=[]
    for i in range(1,len(padded)-2):
        p,a,d,q=padded[i-1:i+3]
        b=(a[0]+(d[0]-p[0])/6,a[1]+(d[1]-p[1])/6)
        c=(d[0]-(q[0]-a[0])/6,d[1]-(q[1]-a[1])/6)
        steps=max(30,math.ceil((math.dist(a,b)+math.dist(b,c)+math.dist(c,d))*24))
        segment=_cubic(a,b,c,d,steps)
        points.extend(segment if not points else segment[1:])
    return tuple(points)


@lru_cache(maxsize=4)
def network_geometry(grid,region):
    rng=random.Random(91417)
    count=math.ceil(grid/8)+2
    paths=[]
    # Meandering arteries cross the entire world. Offset connecting vessels
    # form open, irregular loops rather than a lattice of four-way crossings.
    for row in range(count):
        knots=[]
        for col in range(count+1):
            x=-6+col*8
            y=-5+row*8+math.sin(col*1.9+row*2.3)*2.6+rng.uniform(-.5,.5)
            knots.append((x,y))
        points=_trunk(knots)
        radii=tuple(1.1+.36*math.sin(i/(len(points)-1)*math.tau*1.4+row)
                    for i in range(len(points)))
        paths.append(Vessel(points,radii,True))
    hubs=[]
    for row in range(count-1):
        upper,lower=paths[row],paths[row+1]
        for column in range(1,count):
            # Alternating positions make three-way junctions, never a
            # straight cross-route through a regular sequence of grid nodes.
            fraction=(column+.20*(row%2))/(count+1)
            at=round(fraction*(len(upper.points)-1))
            to=round((fraction+.055)*(len(lower.points)-1))
            a,d=upper.points[at],lower.points[to]
            ta=_unit(upper.points[at+1][0]-upper.points[at-1][0],
                     upper.points[at+1][1]-upper.points[at-1][1])
            td=_unit(lower.points[to+1][0]-lower.points[to-1][0],
                     lower.points[to+1][1]-lower.points[to-1][1])
            reach=math.dist(a,d)*.55
            b=(a[0]+ta[0]*reach,a[1]+ta[1]*reach)
            c=(d[0]-td[0]*reach,d[1]-td[1]*reach)
            points=_cubic(a,b,c,d,180)
            radii=tuple(.85+.2*math.sin(i/180*math.pi) for i in range(181))
            paths.append(Vessel(points,radii,True,row,at))
            hubs.extend((a,d))
    main_count=len(paths)
    for parent_index in range(main_count):
        trunk=paths[parent_index]
        branch_count=(12 if region=='Forest' else 9) if parent_index<count else 3
        for n in range(branch_count):
            at=round((n+1)/(branch_count+1)*(len(trunk.points)-1))
            start=trunk.points[at]
            tangent=_unit(trunk.points[at+1][0]-trunk.points[at-1][0],
                          trunk.points[at+1][1]-trunk.points[at-1][1])
            side=-1 if (n+parent_index)%2 else 1
            extent=rng.uniform(1.0,2.3)
            normal=(-tangent[1]*side,tangent[0]*side)
            end=(start[0]+tangent[0]*extent+normal[0]*extent*.9,
                 start[1]+tangent[1]*extent+normal[1]*extent*.9)
            # First control point follows the trunk tangent: the tributary
            # grows out of its parent rather than meeting it at a sharp angle.
            b=(start[0]+tangent[0]*extent*.55,start[1]+tangent[1]*extent*.55)
            c=(end[0]-tangent[0]*extent*.45,end[1]-tangent[1]*extent*.45)
            points=_cubic(start,b,c,end,70)
            radii=tuple(.90*(1-i/70)**1.1+.045 for i in range(71))
            branch_index=len(paths)
            paths.append(Vessel(points,radii,False,parent_index,at))
            if n%2==0:
                at=35
                start=points[at]
                tangent=_unit(points[at+1][0]-points[at-1][0],points[at+1][1]-points[at-1][1])
                tip=(start[0]+tangent[0]*.8-normal[0]*.6,
                     start[1]+tangent[1]*.8-normal[1]*.6)
                small=_cubic(start,(start[0]+tangent[0]*.35,start[1]+tangent[1]*.35),
                             (tip[0]-tangent[0]*.25,tip[1]-tangent[1]*.25),tip,32)
                paths.append(Vessel(small,tuple(.28*(1-i/32)+.015 for i in range(33)),
                                    False,branch_index,at))
    hubs=tuple(p for p in hubs if 0<p[0]<grid and 0<p[1]<grid)
    return tuple(paths),hubs


def ribbon(points,radii,multiplier):
    """A smooth variable-width silhouette, not a chain of line sprites."""
    left,right=[],[]
    for i,(x,y) in enumerate(points):
        previous=points[max(0,i-1)]
        following=points[min(len(points)-1,i+1)]
        tx,ty=_unit(following[0]-previous[0],following[1]-previous[1])
        radius=radii[i]*multiplier
        left.append((round(x-ty*radius),round(y+tx*radius)))
        right.append((round(x+ty*radius),round(y-tx*radius)))
    return left+right[::-1]
