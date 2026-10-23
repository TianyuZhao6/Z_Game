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
    target=max(3,round(grid*grid/21))
    for _ in range(target*100):
        point=(rng.uniform(1.2,grid-1.2),rng.uniform(1.2,grid-1.2))
        local=min(math.dist(point,c) for c in clusters)
        separation=2.4 if local<5 else 3.6
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
        if root(i)!=root(j) and max(degrees[i],degrees[j])<3:
            components[root(i)]=root(j)
            edges.append((i,j))
            degrees[i]+=1
            degrees[j]+=1
    # A few broad anastomoses reconnect neighboring trees. Reject short
    # triangles and high-degree hubs so this remains a sparse vessel field.
    neighbors=[set() for _ in nodes]
    for i,j in edges:
        neighbors[i].add(j); neighbors[j].add(i)
    additions=0
    for distance,i,j in sorted(candidates,key=lambda item:item[0]*rng.uniform(.8,1.4)):
        if (j in neighbors[i] or neighbors[i]&neighbors[j] or
                max(degrees[i],degrees[j])>=3 or not 3.8<distance<7):
            continue
        edges.append((i,j)); neighbors[i].add(j); neighbors[j].add(i)
        degrees[i]+=1; degrees[j]+=1; additions+=1
        if additions>=max(1,len(nodes)//7): break
    # Extract long routes from the connected forest. Importance belongs to a
    # continuous route, not an arbitrary short edge between two bright dots.
    remaining={tuple(sorted(edge)) for edge in edges}
    adjacency=[[] for _ in nodes]
    for i,j in edges:
        adjacency[i].append(j); adjacency[j].append(i)
    routes=[]
    while remaining:
        best=[]; best_score=-1
        def walk(route,length):
            nonlocal best,best_score
            horizontal=[nodes[n][0]-nodes[n][1] for n in route]
            if max(horizontal)-min(horizontal)>21:
                return
            if len(route)>1:
                span=math.dist(nodes[route[0]],nodes[route[-1]])
                score=length*.35+span
                if score>best_score:
                    best,best_score=route,score
            if length>min(23,grid*.75):
                return
            at=route[-1]
            for nxt in adjacency[at]:
                if nxt in route or tuple(sorted((at,nxt))) not in remaining:
                    continue
                if len(route)>1:
                    a,b,c=nodes[route[-2]],nodes[at],nodes[nxt]
                    incoming=_unit(b[0]-a[0],b[1]-a[1])
                    outgoing=_unit(c[0]-b[0],c[1]-b[1])
                    if sum(x*y for x,y in zip(incoming,outgoing))<-.15:
                        continue
                walk(route+[nxt],length+math.dist(nodes[at],nodes[nxt]))
        for start in sorted({n for edge in remaining for n in edge}):
            walk([start],0)
        routes.append(best)
        remaining.difference_update(tuple(sorted(edge)) for edge in zip(best,best[1:]))
    phases=[rng.uniform(0,math.tau) for _ in nodes]
    paths=[]
    def make(a,d,radius,kind,phase,parent=-1,attachment=-1,tangent=None,terminal=False,end_tangent=None):
        length=math.dist(a,d)
        tx,ty=_unit(d[0]-a[0],d[1]-a[1])
        nx,ny=-ty,tx
        bend=rng.uniform(-.28,.28)*length
        steps=max(40,math.ceil(length*17))
        wander=rng.uniform(.015,.045)
        wave=rng.uniform(0,math.tau)
        for flexibility in (1,.5,.15,0):
            start=tangent or (tx,ty)
            end=end_tangent or (tx,ty)
            handle=length*(.10+.22*flexibility)
            b=(a[0]+start[0]*handle+nx*bend*flexibility*(tangent is None),
               a[1]+start[1]*handle+ny*bend*flexibility*(tangent is None))
            c=(d[0]-end[0]*handle+nx*bend*flexibility*(end_tangent is None),
               d[1]-end[1]*handle+ny*bend*flexibility*(end_tangent is None))
            raw=_cubic(a,b,c,d,steps)
            points=tuple((x+nx*math.sin(k/steps*math.pi)**3*math.sin(k/steps*math.tau*2+wave)*wander*flexibility,
                          y+ny*math.sin(k/steps*math.pi)**3*math.sin(k/steps*math.tau*2+wave)*wander*flexibility)
                         for k,(x,y) in enumerate(raw))
            if all(point_clear(p,grid,occupied) for p in points):
                break
        else:
            return None
        intensity=rng.uniform(.65,.95) if kind!='capillary' else rng.uniform(.35,.7)
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
    junction_tangents={}; junction_phases={}; major_nodes=set(); major_centers=[]
    for route in routes:
        length=sum(math.dist(nodes[a],nodes[b]) for a,b in zip(route,route[1:]))
        center=tuple(sum(nodes[n][axis] for n in route)/len(route) for axis in (0,1))
        main=(length>=min(10,grid*.55) and len(major_centers)<max(1,round(grid*grid/300))
              and all(math.dist(center,c)>5 for c in major_centers))
        if main: major_centers.append(center)
        kind='trunk' if main else 'secondary'
        radius=rng.uniform(1.1,1.65) if main else rng.uniform(.45,.85)
        phase=phases[route[0]]
        tangents=[]
        for k,node in enumerate(route):
            prev=nodes[route[max(0,k-1)]]; following=nodes[route[min(len(route)-1,k+1)]]
            tangent=_unit(following[0]-prev[0],following[1]-prev[1])
            if k in (0,len(route)-1) and node in junction_tangents:
                shared=junction_tangents[node]
                sign=1 if sum(a*b for a,b in zip(shared,tangent))>=0 else -1
                tangent=tuple(sign*v for v in shared)
            tangents.append(tangent)
            junction_tangents.setdefault(node,tangent)
            junction_phases.setdefault(node,phase)
            if main and degrees[node]>=3:
                major_nodes.add(node)
        pieces=[]
        for k,(i,j) in enumerate(zip(route,route[1:])):
            piece=make(nodes[i],nodes[j],radius,kind,phase,tangent=tangents[k],end_tangent=tangents[k+1])
            if piece is not None:
                pieces.append(piece)
            elif pieces:
                paths.append(_join_vessels(pieces)); pieces=[]
        if pieces:
            joined=_join_vessels(pieces)
            # Graph leaves dissolve as well; they do not end at a bright dot.
            if degrees[route[-1]]==1 or degrees[route[0]]==1:
                joined=_fade_tip(joined,start=degrees[route[0]]==1,end=degrees[route[-1]]==1)
            paths.append(joined)
    # Fewer, longer offshoots. Secondaries leave a main route tangentially;
    # sparse terminals grow from those branches, never a fourth level.
    route_count=len(paths)
    branch_nodes=[]
    for parent_index in range(route_count):
        parent=paths[parent_index]
        arc=sum(math.dist(a,b) for a,b in zip(parent.points,parent.points[1:]))
        count=max(1,round(arc/rng.uniform(2.4,3.6))) if parent.main else int(rng.random()<.6)
        for _ in range(count):
            at=rng.randrange(5,len(parent.points)-5)
            a=parent.points[at]
            tx,ty=_unit(parent.points[at+1][0]-parent.points[at-1][0],
                        parent.points[at+1][1]-parent.points[at-1][1])
            side=rng.choice((-1,1))
            extent=rng.uniform(1.2,3.3) if parent.main else rng.uniform(.6,1.4)
            d=(a[0]+tx*extent-ty*side*extent*.55,a[1]+ty*extent+tx*side*extent*.55)
            path=make(a,d,rng.uniform(.45,.8) if parent.main else rng.uniform(.15,.3),
                      'secondary' if parent.main else 'capillary',parent.phase+rng.uniform(.15,.5),
                      parent_index,at,(tx,ty),True)
            if path is None:
                continue
            child_index=len(paths)
            paths.append(path)
            if parent.main and rng.random()<.45:
                branch_nodes.append(Node(*a,1,parent.phase+.18))
            if parent.main and rng.random()<.38:
                at=len(path.points)//2
                a=path.points[at]
                tx,ty=_unit(path.points[at+1][0]-path.points[at-1][0],path.points[at+1][1]-path.points[at-1][1])
                extent=rng.uniform(.65,1.4)
                d=(a[0]+tx*extent+ty*side*extent*.5,a[1]+ty*extent-tx*side*extent*.5)
                twig=make(a,d,rng.uniform(.18,.35),'capillary',path.phase+.4,child_index,at,(tx,ty),True)
                if twig is not None:
                    paths.append(twig)
    # Only real junctions receive a soma. Quiet bends and fading endpoints
    # should read as continuous stone veins, not a string of repeated stars.
    hubs=tuple(Node(*p,2 if i in major_nodes and i%3!=0 else 1,junction_phases[i])
               for i,p in enumerate(nodes) if degrees[i]>=3 and i in junction_phases)+tuple(branch_nodes)
    return tuple(paths),hubs


def _join_vessels(pieces):
    first=pieces[0]
    points=first.points+tuple(v for p in pieces[1:] for v in p.points[1:])
    distances=[0.]
    for a,b in zip(points,points[1:]): distances.append(distances[-1]+math.dist(a,b))
    radius=max(first.radii)
    # One continuous envelope across joins, avoiding a width/brightness reset
    # at every old graph vertex. Geometry sampling remains untouched.
    radii=tuple(radius*(.78+.17*math.sin(d*.83+first.phase)+.05*math.sin(d*2.1)) for d in distances)
    strengths=tuple(.75+.22*math.sin(d*.45+first.phase)**2 for d in distances)
    return first._replace(points=points,radii=radii,strengths=strengths)


def _fade_tip(path,start=False,end=True):
    n=len(path.points)
    fade=tuple(min(1.,(n-1-k)/max(1,n*.12) if end else 1.,
                   k/max(1,n*.12) if start else 1.) for k in range(n))
    return path._replace(radii=tuple(max(.015,r*f**.85) for r,f in zip(path.radii,fade)),
                         strengths=tuple(s*f for s,f in zip(path.strengths,fade)),terminal=True)


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
