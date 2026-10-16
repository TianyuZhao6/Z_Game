"""Presentation-only summon effects; no gameplay randomness or hit testing."""
from functools import lru_cache
import math

import pygame

DEATH_DURATION = 1.3
TRAIL_SECONDS = .28
VISUAL_SIZES = (96, 144, 216)
HOVER_HEIGHT = 38


def stage_index(level):
    return 2 if level >= 6 else 1 if level >= 3 else 0


def canvas_size(level):
    # Each atlas row has different transparent padding. Calibrate by visible
    # silhouette, so evolution grows the creature rather than empty canvas.
    stage = stage_index(level)
    return round(VISUAL_SIZES[stage] / (.80,.93,.83)[stage])


def eye_offset(size, facing, bob=0, stage=2):
    # Normalized central mask/eye anchors in the five atlas yaw views.
    column = facing if facing <= 4 else 8-facing
    anchors = (
        ((.54,.58),(.76,.57),(.85,.56),(.79,.55),(.50,.52)),
        ((.54,.54),(.77,.53),(.85,.51),(.80,.51),(.50,.50)),
        ((.56,.41),(.78,.41),(.88,.40),(.83,.40),(.50,.39)),
    )
    x, y = anchors[stage][column]
    if facing > 4:
        x = 1-x
    inner = int(size*.94)
    pad = (size-inner)//2
    return (pad+x*inner-size/2, -HOVER_HEIGHT+bob-size+pad+y*inner)


@lru_cache(maxsize=12)
def mote(radius, alpha=180):
    radius = max(1, radius)
    surf = pygame.Surface((radius*2+2,radius*2+2),pygame.SRCALPHA)
    center = radius+1, radius+1
    pygame.draw.circle(surf,(150,52,225,alpha//5),center,radius)
    pygame.draw.circle(surf,(201,103,252,alpha//2),center,max(1,radius-2))
    pygame.draw.circle(surf,(246,206,255,alpha),center,max(1,radius-4))
    return surf


def draw_orb(screen, points):
    """Restrained orb with a bounded, curved, alpha-tapered particle tail."""
    if not points:
        return
    # Limit the visible tail in screen space without affecting the trajectory.
    tail = [pygame.Vector2(points[-1])]
    length = 0.0
    for raw in reversed(points[:-1]):
        p = pygame.Vector2(raw)
        gap = p.distance_to(tail[-1])
        if gap < .3:
            continue
        if length+gap > 52:
            tail.append(tail[-1].lerp(p,(52-length)/gap))
            break
        tail.append(p)
        length += gap
    tail.reverse()
    if len(tail)>1:
        bounds = pygame.Rect(min(p.x for p in tail)-8,min(p.y for p in tail)-8,
                             max(p.x for p in tail)-min(p.x for p in tail)+17,
                             max(p.y for p in tail)-min(p.y for p in tail)+17)
        layer = pygame.Surface(bounds.size,pygame.SRCALPHA)
        for i in range(1,len(tail)):
            t = i/(len(tail)-1)
            a,b = tail[i-1]-bounds.topleft,tail[i]-bounds.topleft
            pygame.draw.line(layer,(161,65,222,int(85*t)),a,b,3 if t>.55 else 1)
            pygame.draw.line(layer,(217,143,255,int(155*t*t)),a,b,1)
            if i%3==0:
                # Small side motes, never a wide bloom cloud.
                p = (round(a.x+math.sin(i*2.4)*3),round(a.y+math.cos(i*1.7)*3))
                pygame.draw.circle(layer,(187,88,239,int(120*t)),p,1)
        screen.blit(layer,bounds)
    head = mote(6)
    screen.blit(head,head.get_rect(center=points[-1]))


@lru_cache(maxsize=96)
def dissolve_frame(art, phase):
    """Fragment the actual current view gently; no generic explosion sprite."""
    size = art.get_width()
    layer = pygame.Surface((size+32,size+32),pygame.SRCALPHA)
    t = max(0,min(1,phase))
    if t>=1:
        return layer
    for y in range(0,size,4):
        for x in range(0,size,4):
            seed = (x*73+y*151+x*y*17)%101
            release = .12+.46*seed/100
            drift = max(0,(t-release)/(1-release))
            fade = max(0,1-t*.65-drift*.8)
            if fade<=0:
                continue
            tile = art.subsurface((x,y,min(4,size-x),min(4,size-y))).copy()
            tile.set_alpha(int(255*fade))
            # Early inward collapse, then slow sparse rising spectral fragments.
            dx = (size/2-x)*t*.12 + math.sin(seed)*drift*9
            dy = t*5-drift*(7+seed%8)
            layer.blit(tile,(round(16+x+dx),round(16+y+dy)))
            if drift>.1 and seed%7==0 and art.get_at((x,y)).a>150:
                color = (239,49,118,int(150*fade)) if seed%2 else (157,49,222,int(150*fade))
                pygame.draw.circle(layer,color,(round(16+x+dx),round(16+y+dy-3)),1)
    return layer


def draw_beam(screen, origin, end):
    """Focused eye-ray: soft narrow envelope, thick magenta body, bright core."""
    a,b = pygame.Vector2(origin),pygame.Vector2(end)
    clip = screen.get_rect().inflate(16,16).clipline(a,b)
    if not clip:
        return
    a,b = map(pygame.Vector2,clip)
    bounds = pygame.Rect(min(a.x,b.x)-8,min(a.y,b.y)-8,abs(a.x-b.x)+17,abs(a.y-b.y)+17)
    # Supersample one straight segment, then filter down. Thick integer-pixel
    # lines produced a staircase at shallow angles, especially in the lite view.
    scale = 2
    layer = pygame.Surface((bounds.w*scale,bounds.h*scale),pygame.SRCALPHA)
    a,b = (a-bounds.topleft)*scale,(b-bounds.topleft)*scale
    pygame.draw.line(layer,(166,39,206,55),a,b,11*scale)
    pygame.draw.line(layer,(235,64,172,180),a,b,6*scale)
    pygame.draw.line(layer,(255,220,249,250),a,b,3*scale)
    pygame.draw.circle(layer,(255,158,225,155),b,5*scale)
    pygame.draw.circle(layer,(255,236,252,240),b,2*scale)
    screen.blit(pygame.transform.smoothscale(layer,bounds.size),bounds)
