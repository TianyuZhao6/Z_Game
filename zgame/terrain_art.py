"""Cached, deterministic stone materials. Decoration never uses combat RNG.

All surfaces retain the existing isometric tile footprint and wall anchors;
these details do not create obstacles or change their collision rectangles.
"""
from functools import lru_cache

import pygame


def variant(gx, gy):
    return ((gx * 73) ^ (gy * 151) ^ (gx * gy * 17)) % 16


def shade(color, factor=1.0, lift=0):
    return tuple(max(0, min(255, int(c * factor + lift))) for c in color[:3])


def mix(a, b, t):
    return (round(a[0] + (b[0]-a[0])*t), round(a[1] + (b[1]-a[1])*t))


@lru_cache(maxsize=64)
def floor_tile(width, height, seed):
    surf = pygame.Surface((width+2, height+2), pygame.SRCALPHA)
    cx, cy = (width+2)//2, (height+2)//2
    outer = [(cx, 1), (width+1, cy), (cx, height+1), (1, cy)]
    inner = [(cx, 3), (width-3, cy), (cx, height-1), (5, cy)]
    base = shade((30, 37, 47), lift=(seed % 5)-2)
    pygame.draw.polygon(surf, (15, 20, 28), outer)
    pygame.draw.polygon(surf, base, inner)
    # A restrained bevel catches light on the upper edges, not a bright grid.
    pygame.draw.lines(surf, shade(base, 1.25), False, [inner[3], inner[0], inner[1]], 1)
    pygame.draw.lines(surf, shade(base, .72), False, [inner[1], inner[2], inner[3]], 1)

    def point(u, v):
        return round(cx+(u-v)*width*.43), round(4+(u+v)*(height-6)*.5)

    # Short chips and fine grain follow the tile plane; no random frame noise.
    for i in range(9):
        u = .12 + ((seed*31+i*37) % 73)/100
        v = .12 + ((seed*13+i*23) % 73)/100
        p = point(u, v)
        pygame.draw.line(surf, shade(base, lift=3 if i%3 else -4), p,
                         (p[0]+1+i%3, p[1]), 1)
    if seed in (2, 7, 11):
        pts = [point(.15, .46), point(.36, .49), point(.43, .65), point(.68, .68)]
        pygame.draw.lines(surf, shade(base, .62), False, pts, 1)
    if seed == 0:
        # Faint carved ward: ground detail, deliberately much dimmer than shots.
        pts = [point(.32,.5), point(.5,.3), point(.69,.5), point(.5,.7), point(.32,.5)]
        pygame.draw.lines(surf, (43, 62, 69), False, pts, 1)
        pygame.draw.line(surf, (43, 62, 69), point(.5,.42), point(.5,.58), 1)
    return surf


@lru_cache(maxsize=256)
def wall_tile(width, height, wall_h, color, seed, style="prism"):
    """Warm fractured masonry versus cool banded permanent stone."""
    pad_top = max(0, int(height*1.8)-height//2) if style == "hybrid" else 0
    surf = pygame.Surface((width+2, height+wall_h+pad_top+2), pygame.SRCALPHA)
    cx, top_y = (width+2)//2, pad_top+1
    top = [(cx, top_y), (width+1, top_y+height//2),
           (cx, top_y+height), (1, top_y+height//2)]
    warm = color[0] > color[2]
    base = shade(color, lift=(seed%3-1)*3)
    dark = shade(base, .35)
    # Two visibly stacked masonry courses with staggered vertical joints.
    for a, b, factor in ((top[3], top[2], .53), (top[2], top[1], .72)):
        face = [a, b, (b[0], b[1]+wall_h), (a[0], a[1]+wall_h)]
        pygame.draw.polygon(surf, shade(base, factor), face)
        for course in (.5, .94):
            y = round(wall_h*course)
            pygame.draw.line(surf, dark, (a[0],a[1]+y), (b[0],b[1]+y), 2)
            pygame.draw.line(surf, shade(base, factor, 7), (a[0],a[1]+y+1), (b[0],b[1]+y+1), 1)
        for row, t in enumerate((.33, .68)):
            p = mix(a, b, t)
            pygame.draw.line(surf, dark, (p[0],p[1]+round(row*wall_h*.5)),
                             (p[0],p[1]+round((row+1)*wall_h*.5)), 1)
        pygame.draw.line(surf, shade(base,.32), face[2], face[3], 2)
    # Thick cap, softly faceted center, chipped edge highlights.
    pygame.draw.polygon(surf, shade(base,.77), top)
    center = (cx, top_y+height//2)
    inset = [mix(p, center, .12) for p in top]
    pygame.draw.polygon(surf, base, inset)
    pygame.draw.polygon(surf, shade(base,1.06), [inset[0],inset[1],center,inset[3]])
    pygame.draw.lines(surf, shade(base,1.15,8), False, [top[3],top[0],top[1]], 2)
    pygame.draw.lines(surf, shade(base,.5), False, [top[1],top[2],top[3]], 1)
    for i in range(6):
        p = mix(inset[i%4], center, .3+(seed+i*7)%5*.1)
        pygame.draw.line(surf, shade(base, lift=9 if i%2 else -9), p, (p[0]+3,p[1]+1), 1)
    if warm:
        # Broken, branching cap fissure remains recognizable even at full HP.
        crack = [mix(top[0],center,.18), (cx-5+seed%5, center[1]-3),
                 (cx+4,center[1]+3), mix(center,top[2],.92)]
        pygame.draw.lines(surf, shade(base,.35), False, crack, 2)
        pygame.draw.lines(surf, shade(base,1.15,8), False,
                          [(x+2,y) for x,y in crack], 1)
        pygame.draw.line(surf, dark, crack[2], mix(center,top[1],.7), 1)
    else:
        # Inlaid diamond seal signals reinforcement, distinct from cracks.
        seal = [(cx,center[1]-6), (cx+11,center[1]),
                (cx,center[1]+6), (cx-11,center[1])]
        pygame.draw.polygon(surf, shade(base,.6), seal)
        pygame.draw.lines(surf, shade(base,1.1,12), True, seal, 1)
        pygame.draw.line(surf, (109,151,162), (cx-3,center[1]), (cx+3,center[1]), 1)
    if style == "hybrid":
        # Preserve this optional legacy silhouette with a carved cap.
        pillar = pygame.Rect(0,0,max(4,int(width*.35)),max(4,int(height*1.8)))
        pillar.midbottom = center
        pygame.draw.rect(surf, shade(base,.8), pillar, border_radius=4)
        pygame.draw.line(surf, shade(base,1.2), pillar.topleft, pillar.bottomleft, 2)
        pygame.draw.rect(surf, dark, pillar.inflate(-8,-12), 1, border_radius=2)
    # Raise the cap, never extend the taller wall down into the next floor tile.
    # Anchor remains on the ground footprint for both cached and sorted renders.
    return surf, cx, top_y+wall_h
