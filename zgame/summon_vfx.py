"""Presentation-only summon effects; no gameplay randomness or hit testing."""
from functools import lru_cache
import math

import pygame

DEATH_DURATION = 1.3
TRAIL_SECONDS = .28
ORB_RADIUS = 9  # Presentation only; projectile contact radius remains unchanged.
VISUAL_SIZES = (96, 144, 216)
HOVER_HEIGHT = 38
PROCESSION_TRAIL_LENGTH = 2.4  # Skull sprite lengths, presentation only.


@lru_cache(maxsize=8)
def procession_wake(size, phase):
    """Right-facing spectral wake: broken tile smoke and narrow energy ribbons.

    Deterministic decoration must never consume the combat random stream.
    Fixed animation phases keep the staggered wakes inexpensive to render.
    """
    length = round(size*PROCESSION_TRAIL_LENGTH)
    height = round(size*.95)
    layer = pygame.Surface((length+16,height+16),pygame.SRCALPHA)
    cy = layer.get_height()/2
    # Broad translucent stream, interrupted by the facets below rather than a
    # solid laser cone. The remote end dissolves into widely spaced fragments.
    for strand in range(3):
        points=[]
        for step in range(25):
            t=step/24
            x=8+t*length
            spread=t*size*.09
            y=cy+math.sin(t*15+strand*2+phase*.7)*spread+(strand-1)*size*.08*t
            points.append((x,y))
        for step in range(1,len(points)):
            t=step/(len(points)-1)
            alpha=int(90*t**1.5)
            color=(161,57,203,alpha) if strand!=1 else (209,50,135,alpha)
            pygame.draw.line(layer,color,points[step-1],points[step],max(2,int(size*.22*t)))
    # Staggered isometric fragments leave black gaps like the approved concept.
    for i in range(170):
        seed=(i*73+i*i*19)%997
        t=.04+.94*((i*37)%211)/210
        x=8+t*length
        spread=size*(.02+.18*t)
        wave=math.sin(t*18+phase*.7)*size*.04*t
        y=cy+((seed%101)/50-1)*spread+wave
        w=size*(.045+(seed%7)*.012)*(.2+.8*t)
        h=w*.52
        alpha=int((70+seed%100)*t**1.5)
        palette=((146,64,199),(200,114,231),(247,83,161),(45,18,65))
        color=(*palette[i%4],alpha)
        pygame.draw.polygon(layer,color,((x-w,y),(x,y-h),(x+w,y),(x,y+h)))
    # Three broken, flowing highlights give direction without becoming beams.
    for strand in range(3):
        for step in range(2,30):
            if (step+strand*3)%7==0:
                continue
            pts=[]
            for j in (step,step+1):
                t=j/31
                x=8+t*length
                y=cy+(strand-1)*size*.08*t+math.sin(t*20+strand*2+phase*.7)*size*.04*t
                pts.append((x,y))
            t=step/31
            color=(255,129,207,int(160*t)) if strand==1 else (210,155,255,int(125*t))
            pygame.draw.line(layer,color,*pts,max(1,round(size*.018*t)))
    return layer


@lru_cache(maxsize=96)
def oriented_procession_wake(size, phase, direction):
    return pygame.transform.rotate(procession_wake(size,phase),-direction*360/64)


def procession_heading(velocity):
    angle=math.atan2(velocity[1],velocity[0])
    sector=round(angle*64/math.tau)%64
    return sector,pygame.Vector2(math.cos(sector*math.tau/64),math.sin(sector*math.tau/64))


def draw_procession_wake(screen, head, velocity, size, age, remaining, phase):
    direction=pygame.Vector2(velocity)
    if direction.length_squared()<.01 or age<=0 or remaining<=0:
        return
    sector,axis=procession_heading(velocity)
    # Match placement to the cached rotation, avoiding an offset at its tip.
    length=round(size*PROCESSION_TRAIL_LENGTH)
    center=pygame.Vector2(head)-axis*(length/2)
    art=oriented_procession_wake(size,phase%4,sector)
    dest=art.get_rect(center=(round(center.x),round(center.y)))
    if not screen.get_rect().colliderect(dest):
        return
    # Shared cached pixels are never mutated; alpha is a per-blit surface flag.
    art.set_alpha(round(255*min(1,age/.3,remaining/.35)))
    screen.blit(art,dest)


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
    pygame.draw.circle(surf,(103,25,193,alpha//3),center,radius)
    pygame.draw.circle(surf,(151,43,226,alpha),center,max(1,radius-3))
    pygame.draw.circle(surf,(211,133,255,alpha),center,max(1,radius//3))
    return surf


def draw_orb(screen, points):
    """Saturated violet orb with a bounded, curved, alpha-tapered tail."""
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
            pygame.draw.line(layer,(121,32,204,int(135*t)),a,b,5 if t>.55 else 2)
            pygame.draw.line(layer,(179,71,239,int(190*t*t)),a,b,2)
            if i%3==0:
                # Small side motes, never a wide bloom cloud.
                p = (round(a.x+math.sin(i*2.4)*3),round(a.y+math.cos(i*1.7)*3))
                pygame.draw.circle(layer,(155,48,224,int(150*t)),p,1)
        screen.blit(layer,bounds)
    head = mote(ORB_RADIUS,220)
    screen.blit(head,head.get_rect(center=points[-1]))


@lru_cache(maxsize=96)
def shield_outline(art):
    """Cached silhouette shell including disconnected horns/tendrils, not a box."""
    mask = pygame.mask.from_surface(art,32)
    size = art.get_width()+6,art.get_height()+6
    shell = pygame.mask.Mask(size)
    for dx,dy in ((-3,0),(3,0),(0,-3),(0,3),(-2,-2),(2,-2),(-2,2),(2,2)):
        shell.draw(mask,(3+dx,3+dy))
    shell.erase(mask,(3,3))
    return shell.to_surface(setcolor=(90,180,255,255),unsetcolor=(0,0,0,0))


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
