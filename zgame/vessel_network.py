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
    strengths: tuple = ()
    phase: float = 0.0
    kind: str = "secondary"
    terminal: bool = False


def _unit(dx,dy):
    length=max(.00001,math.hypot(dx,dy))
    return dx/length,dy/length


def _cubic(a,b,c,d,steps):
    return tuple(((1-t)**3*a[0]+3*(1-t)**2*t*b[0]+3*(1-t)*t*t*c[0]+t**3*d[0],
                  (1-t)**3*a[1]+3*(1-t)**2*t*b[1]+3*(1-t)*t*t*c[1]+t**3*d[1])
                 for t in (i/steps for i in range(steps+1)))


def layout_seed(blocked):
    value=91417
    for x,y in sorted(blocked):
        value=((value ^ (int(x)*73856093 ^ int(y)*19349663))*16777619)&0xffffffff
    return value


def breathing_profile(phase):
    """Fixed illumination parameters; independent of geometry and frame rate."""
    return (5.5+1.2*math.sin(phase*1.7),
            172+44*(.5+.5*math.sin(phase*2.31+.6)))


def branch_alpha(phase,ticks):
    period,amplitude=breathing_profile(phase)
    return round(24+amplitude*(.5+.5*math.sin(ticks*.001*math.tau/period+phase)))


def point_clear(point,grid,blocked,margin=.20):
    x,y=point
    if not (.7<x<grid-.7 and .7<y<grid-.7):
        return False
    gx,gy=math.floor(x),math.floor(y)
    return not any((i,j) in blocked and i-margin<x<i+1+margin and j-margin<y<j+1+margin
                   for i in range(gx-1,gx+2) for j in range(gy-1,gy+2))


class Node(NamedTuple):
    x: float
    y: float
    rank: int
    phase: float


@lru_cache(maxsize=4)
def network_geometry(grid,region,seed=91417,blocked=()):
    """A seeded spatial graph, independent of tiles, camera and combat RNG."""
    rng=random.Random(seed)
    occupied=set(blocked)
    nodes=[]
    clusters=[(rng.uniform(3,grid-3),rng.uniform(3,grid-3)) for _ in range(4)]
    target=round(grid*grid/15)
    for _ in range(target*100):
        point=(rng.uniform(1.2,grid-1.2),rng.uniform(1.2,grid-1.2))
        local=min(math.dist(point,c) for c in clusters)
        separation=2.0 if local<5 else 3.0
        if point_clear(point,grid,occupied,.45) and all(math.dist(point,n)>separation for n in nodes):
            nodes.append(point)
        if len(nodes)>=target:
            break
    # Short clear connections form a spanning forest; wall-separated pockets
    # may remain separate instead of sending an artificial line through stone.
    candidates=[]
    for i,a in enumerate(nodes):
        for j in range(i):
            b=nodes[j]
            distance=math.dist(a,b)
            if distance>9:
                continue
            steps=max(2,math.ceil(distance*8))
            if all(point_clear((a[0]+(b[0]-a[0])*k/steps,a[1]+(b[1]-a[1])*k/steps),grid,occupied)
                   for k in range(steps+1)):
                candidates.append((distance*rng.uniform(.92,1.08),j,i))
    components=list(range(len(nodes)))
    def root(i):
        while components[i]!=i:
            components[i]=components[components[i]]
            i=components[i]
        return i
    edges=[]
    degrees=[0]*len(nodes)
    for _,i,j in sorted(candidates):
        if root(i)!=root(j) and max(degrees[i],degrees[j])<4:
            components[root(i)]=root(j)
            edges.append((i,j))
            degrees[i]+=1
            degrees[j]+=1
    # Promote well-connected routes, rather than assigning every line trunk status.
    ranked=sorted(range(len(edges)),key=lambda k:degrees[edges[k][0]]+degrees[edges[k][1]],reverse=True)
    trunks=set(ranked[:max(1,round(len(edges)*.22))])
    phases=[rng.uniform(0,math.tau) for _ in nodes]
    paths=[]
    def make(a,d,radius,kind,phase,parent=-1,attachment=-1,tangent=None,terminal=False):
        length=math.dist(a,d)
        tx,ty=_unit(d[0]-a[0],d[1]-a[1])
        nx,ny=-ty,tx
        bend=rng.uniform(-.28,.28)*length
        steps=max(40,math.ceil(length*17))
        wander=rng.uniform(.025,.10)
        wave=rng.uniform(0,math.tau)
        for flexibility in (1,.5,.15,0):
            start=tangent or (tx,ty)
            b=(a[0]+start[0]*length*.30+nx*bend*flexibility*(tangent is None),
               a[1]+start[1]*length*.30+ny*bend*flexibility*(tangent is None))
            c=(d[0]-tx*length*.30+nx*bend*flexibility,
               d[1]-ty*length*.30+ny*bend*flexibility)
            raw=_cubic(a,b,c,d,steps)
            points=tuple((x+nx*math.sin(k/steps*math.pi)**3*math.sin(k/steps*math.tau*2+wave)*wander*flexibility,
                          y+ny*math.sin(k/steps*math.pi)**3*math.sin(k/steps*math.tau*2+wave)*wander*flexibility)
                         for k,(x,y) in enumerate(raw))
            if all(point_clear(p,grid,occupied) for p in points):
                break
        else:
            return None
        intensity=rng.choice((1.,.75,.55,.35)) if kind!='trunk' else rng.uniform(.65,1)
        imperfect=terminal and rng.random()<.30
        radii=[]
        strengths=[]
        for k in range(steps+1):
            t=k/steps
            taper=(1-t)**.85 if terminal else .76+.24*abs(2*t-1)**3
            radii.append(max(.015,radius*taper*(1+.16*math.sin(t*math.tau*2.3+wave))))
            fade=(1-t)**.65 if terminal else 1
            if imperfect:
                fade*=1-.9*math.exp(-((t-.65)/.075)**2)
            strengths.append(intensity*fade*(.72+.28*math.sin(t*math.tau*1.7+wave)**2))
        return Vessel(points,tuple(radii),kind=='trunk',parent,attachment,
                      tuple(strengths),phase,kind,terminal)
    for index,(i,j) in enumerate(edges):
        main=index in trunks
        path=make(nodes[i],nodes[j],rng.uniform(1.45,2.1) if main else rng.uniform(.65,1.25),
                  'trunk' if main else 'secondary',phases[i])
        if path is not None:
            paths.append(path)
    # Local trees branch from existing curves, with shared initial tangents.
    for parent_index in range(len(paths)):
        parent=paths[parent_index]
        for _ in range(rng.randint(2,4) if region=='Forest' else rng.randint(1,3)):
            at=rng.randrange(5,len(parent.points)-5)
            a=parent.points[at]
            tx,ty=_unit(parent.points[at+1][0]-parent.points[at-1][0],
                        parent.points[at+1][1]-parent.points[at-1][1])
            side=rng.choice((-1,1))
            extent=rng.uniform(.65,2.0)
            d=(a[0]+tx*extent-ty*side*extent*.8,a[1]+ty*extent+tx*side*extent*.8)
            path=make(a,d,rng.uniform(.32,.72),'capillary',parent.phase+rng.uniform(.3,.8),
                      parent_index,at,(tx,ty),True)
            if path is None:
                continue
            child_index=len(paths)
            paths.append(path)
            if rng.random()<.65:
                at=len(path.points)//2
                a=path.points[at]
                tx,ty=_unit(path.points[at+1][0]-path.points[at-1][0],path.points[at+1][1]-path.points[at-1][1])
                d=(a[0]+tx*.7+ty*side*.5,a[1]+ty*.7-tx*side*.5)
                twig=make(a,d,rng.uniform(.18,.35),'capillary',path.phase+.4,child_index,at,(tx,ty),True)
                if twig is not None:
                    paths.append(twig)
    hubs=tuple(Node(*p,2 if degrees[i]>=3 else (1 if degrees[i]==2 else 0),phases[i])
               for i,p in enumerate(nodes) if degrees[i])
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
