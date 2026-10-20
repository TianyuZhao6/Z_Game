"""Shared neural garden materials; region identity belongs to the floor only.

Legacy region IDs deliberately remain save/gameplay keys. Art uses local seeded
randomness and cached surfaces, never the combat RNG or collision grid.
"""
from functools import lru_cache
import math
import random

import pygame

from zgame.paths import asset_candidates, first_existing_path


REGIONS = {
    "Domain of Wind": ("Wind", "风", (70, 161, 224), 6.4),
    "Misty Forest": ("Forest", "林", (87, 170, 133), 7.8),
    "Scorched Hell": ("Fire", "火", (211, 120, 83), 5.6),
    "Bastion of Stone": ("Mountain", "山", (174, 151, 103), 9.2),
}
DEFAULT_REGION = "Domain of Wind"


def region_style(legacy_id):
    return REGIONS.get(legacy_id, REGIONS[DEFAULT_REGION])


def region_name(legacy_id):
    return region_style(legacy_id)[0]


@lru_cache(maxsize=6)
def source_asset(name):
    path = first_existing_path(asset_candidates("sprites", "environment", name))
    return pygame.image.load(path) if path else None


@lru_cache(maxsize=1)
def ground_material():
    source = source_asset("neural-stone-v1.png")
    if source is None:
        return None
    # Preserve plate boundaries instead of erasing them in a tiny intermediate.
    tile = pygame.transform.smoothscale(source, (1024, 512))
    veil = pygame.Surface(tile.get_size(), pygame.SRCALPHA)
    veil.fill((23, 30, 50, 24))
    tile.blit(veil, (0,0))
    return tile


def floor_outline(grid, cell_w, cell_h, x0, y0, info):
    return [(int(-x0), int(info-y0)),
            (int(grid*cell_w/2-x0), int(grid*cell_h/2+info-y0)),
            (int(-x0), int(grid*cell_h+info-y0)),
            (int(-grid*cell_w/2-x0), int(grid*cell_h/2+info-y0))]


@lru_cache(maxsize=2)
def abyss_view(size):
    source = source_asset("neural-abyss.png")
    if source is None:
        return None
    # Overscan permits slow, bounded camera parallax without exposing a seam.
    scale = max((size[0]+160)/source.get_width(),(size[1]+100)/source.get_height())
    result = pygame.transform.smoothscale(source,
        (math.ceil(source.get_width()*scale),math.ceil(source.get_height()*scale)))
    return result.convert() if pygame.display.get_surface() else result


@lru_cache(maxsize=4)
def cliff_strip(cell_w, cell_h, reverse=False):
    source = source_asset("neural-cliff.png")
    if source is None:
        return None
    # The painted rim runs from (2%,14%) to (98%,80%). Align those
    # anchors to twelve cell edges; hanging fibers remain outside collision.
    span_x,span_y = cell_w*6,cell_h*6
    width,height = round(span_x/.96),round(span_y/.66)
    result = pygame.transform.smoothscale(source,(width,height))
    if reverse:
        result = pygame.transform.flip(result,True,False)
    return result,round(width*.02),round(height*.14)


def draw_platform_rim(screen, camx, camy, grid, cell_w, cell_h, info, front=True):
    # Decorative only: the playable outline and pathfinding stay unchanged.
    for reverse in (False,True):
        cached = cliff_strip(cell_w,cell_h,reverse)
        if cached is None:
            continue
        sprite,pad_x,pad_y = cached
        if front:
            start_x = (-1 if not reverse else 1)*grid*cell_w/2
            start_y = info+grid*cell_h/2
        else:
            start_x,start_y = 0,info
        direction = -1 if reverse else 1
        for step in range(0,grid,12):
            span = min(12,grid-step)
            art = sprite
            if span != 12:
                art = pygame.transform.smoothscale(sprite,
                    (round(sprite.get_width()*span/12),round(sprite.get_height()*span/12)))
            x = start_x+direction*step*cell_w/2-camx
            y = start_y+step*cell_h/2-camy
            if reverse:
                x -= art.get_width()-pad_x
            else:
                x -= pad_x
            rect = art.get_rect(topleft=(round(x),round(y-pad_y)))
            if rect.colliderect(screen.get_rect()):
                screen.blit(art,rect)


def draw_abyss(screen, camx, camy, grid, cell_w, cell_h, info):
    art = abyss_view(screen.get_size())
    if art is not None:
        x = (screen.get_width()-art.get_width())//2-int(55*math.tanh(camx/900))
        y = (screen.get_height()-art.get_height())//2-int(35*math.tanh(camy/600))
        screen.blit(art,(x,y))
    draw_platform_rim(screen,camx,camy,grid,cell_w,cell_h,info,front=False)


def paint_floor(surface, grid, cell_w, cell_h, x0, y0, info):
    """Continuous mineral cortex, transparent beyond the playable platform."""
    width, height = surface.get_size()
    surface.fill((0, 0, 0, 0))
    ground = pygame.Surface((width, height), pygame.SRCALPHA)
    tile = ground_material()
    if tile is None:
        ground.fill((39, 46, 65))
    else:
        tw, th = tile.get_size()
        tiles = {(a,b): pygame.transform.flip(tile, bool(a), bool(b)) for a in (0,1) for b in (0,1)}
        for row, y in enumerate(range(0, height, th)):
            for col, x in enumerate(range(0, width, tw)):
                ground.blit(tiles[col%2,row%2], (x,y))
    outline = floor_outline(grid, cell_w, cell_h, x0, y0, info)
    mask = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255,255,255,255), outline)
    ground.blit(mask, (0,0), special_flags=pygame.BLEND_RGBA_MULT)
    surface.blit(ground, (0,0))


@lru_cache(maxsize=4)
def network_paths(grid, region):
    """Organic axons with tapered dendrites; all randomness is art-local."""
    rng = random.Random(91417)
    spacing = 6.0
    count = math.ceil(grid/spacing)+2
    nodes = {}
    for row in range(count):
        for col in range(count):
            nodes[col,row] = ((col-.6)*spacing + rng.uniform(-1.2,1.2),
                              (row-.6)*spacing + rng.uniform(-1.2,1.2))
    paths = []
    name = region_name(region)
    for (col,row), a in nodes.items():
        # Every row connected, alternating cross links: wide open cells.
        neighbors = [(col+1,row)]
        if (col+row)%2 == 0:
            neighbors.append((col,row+1))
        for neighbor in neighbors:
            if neighbor not in nodes:
                continue
            b = nodes[neighbor]
            dx,dy = b[0]-a[0],b[1]-a[1]
            length = max(.01, math.hypot(dx,dy))
            bend = rng.uniform(-1.25,1.25)
            steps = 28
            phase = rng.uniform(0,math.tau)
            pts = []
            for i in range(steps+1):
                t = i/steps
                sway = math.sin(math.pi*t)*bend
                sway += math.sin(math.pi*t)*math.sin(t*math.tau*2+phase)*.22
                if name == "Fire":
                    sway += math.sin(math.pi*t)*math.sin(t*math.tau*5+phase)*.11
                elif name == "Mountain":
                    sway *= .7
                pts.append((a[0]+dx*t-dy/length*sway, a[1]+dy*t+dx/length*sway))
            paths.append((tuple(pts), True))
            # Dim rootlike tributaries; the same calm density in all regions.
            n = 6 if name == "Forest" else 4
            for k in range(n):
                mid = pts[(k+1)*steps//(n+1)]
                side = -1 if rng.random()<.5 else 1
                extent = rng.uniform(.6,1.6)
                tip = (mid[0]-dy/length*side*extent+dx*.12,
                       mid[1]+dx/length*side*extent+dy*.12)
                branch = tuple((mid[0]+(tip[0]-mid[0])*t+math.sin(t*math.pi*2)*.10,
                                mid[1]+(tip[1]-mid[1])*t+math.sin(t*math.pi)*.19)
                               for t in (i/12 for i in range(13)))
                paths.append((branch,False))
                # Tiny forks occur only near a branch, leaving wide quiet gaps.
                for j in (5,9):
                    fork = branch[j]
                    end = (fork[0]+dx/length*.42,fork[1]+dy/length*.42)
                    paths.append(((fork,((fork[0]+end[0])*.5+.08,
                                         (fork[1]+end[1])*.5-.05),end),False))
    return tuple(paths)


@lru_cache(maxsize=1)
def network_surface(grid, cell_w, cell_h, info, size, x0, y0, region):
    layer = pygame.Surface(size, pygame.SRCALPHA)
    color = region_style(region)[2]
    def project(p):
        return (round((p[0]-p[1])*cell_w*.5-x0),
                round((p[0]+p[1])*cell_h*.5+info-y0))
    projected = [(tuple(project(p) for p in path), main) for path,main in network_paths(grid,region)]
    # Draw halos first so crossings never erase a previously drawn core.
    for pts,main in projected:
        if main:
            for radius,alpha in ((14,12),(9,25),(5,55)):
                pygame.draw.circle(layer, (*color,alpha), pts[0], radius)
            pygame.draw.lines(layer, (*color,12), False, pts, 19)
            pygame.draw.lines(layer, (*color,27), False, pts, 9)
            pygame.draw.lines(layer, (*color,62), False, pts, 5)
    for pts,main in projected:
        core = tuple(min(255,int(c*1.12+20)) for c in color)
        pygame.draw.lines(layer, (*core,215 if main else 105), False, pts, 2 if main else 1)
        if main:
            pygame.draw.circle(layer, (*core,240), pts[0], 2)
    mask = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255,255,255,255), floor_outline(grid,cell_w,cell_h,x0,y0,info))
    layer.blit(mask, (0,0), special_flags=pygame.BLEND_RGBA_MULT)
    if pygame.display.get_surface() is not None:
        layer = layer.convert_alpha()
    return layer


def draw_network(screen, cache, grid, cell_w, cell_h, info, region, camx, camy, ticks):
    layer = network_surface(grid,cell_w,cell_h,info,cache["surface"].get_size(),
                            cache["x0"],cache["y0"],region)
    period = region_style(region)[3]
    layer.set_alpha(round(190+60*math.sin(ticks*.001*math.tau/period)), pygame.RLEACCEL)
    # Source crop keeps both desktop and browser work bounded by the viewport.
    dest = pygame.Rect(round(cache["x0"]-camx),round(cache["y0"]-camy),*layer.get_size())
    visible = dest.clip(screen.get_rect())
    if visible.width and visible.height:
        screen.blit(layer, visible.topleft, visible.move(-dest.x,-dest.y),
                    special_flags=pygame.BLEND_ALPHA_SDL2)


@lru_cache(maxsize=128)
def illustrated_wall(width, height, wall_h, color, seed):
    atlas = source_asset("neural-walls-v1.png")
    if atlas is None:
        return None
    fragile = color[0] > color[2]
    idx = (2 if fragile else 0) + seed%2
    cw = atlas.get_width()//4
    cell = atlas.subsurface((idx*cw,0,cw,atlas.get_height()))
    bounds = cell.get_bounding_rect(min_alpha=20)
    art = cell.subsurface(bounds)
    # Preserve exact footprint/ground anchor, but let the cap rise above it.
    target = (width, wall_h+height)
    art = pygame.transform.smoothscale(art, target)
    if seed & 4:
        art = pygame.transform.flip(art, True, False)
    if fragile:
        damage = min(1.0, max(.4, color[0]/147))
        tint = round(255*damage)
        art.fill((tint,tint,tint,255), special_flags=pygame.BLEND_RGBA_MULT)
    result = pygame.Surface((width+2,height+wall_h+2),pygame.SRCALPHA)
    pygame.draw.ellipse(result, (9,12,23,100), (2,wall_h+height//2,width-2,height//2))
    result.blit(art,(1,1))
    if pygame.display.get_surface() is not None:
        result = result.convert_alpha()
    # Walls also composite into an RGBA cache. RLE's SDL2 blit path can
    # turn their translucent edge/shadow pixels opaque on that destination.
    return result,(width+2)//2,1+wall_h
