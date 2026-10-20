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
    "Domain of Wind": ("Wind", "风", (102, 175, 206), 6.4),
    "Misty Forest": ("Forest", "林", (87, 170, 133), 7.8),
    "Scorched Hell": ("Fire", "火", (211, 120, 83), 5.6),
    "Bastion of Stone": ("Mountain", "山", (174, 151, 103), 9.2),
}
DEFAULT_REGION = "Domain of Wind"


def region_style(legacy_id):
    return REGIONS.get(legacy_id, REGIONS[DEFAULT_REGION])


def region_name(legacy_id):
    return region_style(legacy_id)[0]


@lru_cache(maxsize=2)
def source_asset(name):
    path = first_existing_path(asset_candidates("sprites", "environment", name))
    return pygame.image.load(path) if path else None


@lru_cache(maxsize=1)
def ground_material():
    source = source_asset("neural-stone-v1.png")
    if source is None:
        return None
    # Deliberate three-pixel clusters, including on the browser renderer.
    tile = pygame.transform.smoothscale(source, (256, 128))
    tile = pygame.transform.scale(tile, (768, 384))
    veil = pygame.Surface(tile.get_size(), pygame.SRCALPHA)
    veil.fill((28, 35, 53, 100))
    tile.blit(veil, (0,0))
    return tile


def floor_outline(grid, cell_w, cell_h, x0, y0, info):
    return [(int(-x0), int(info-y0)),
            (int(grid*cell_w/2-x0), int(grid*cell_h/2+info-y0)),
            (int(-x0), int(grid*cell_h+info-y0)),
            (int(-grid*cell_w/2-x0), int(grid*cell_h/2+info-y0))]


def paint_floor(surface, grid, cell_w, cell_h, x0, y0, info):
    """One continuous material across cells, with a quiet abyss outside the rim."""
    width, height = surface.get_size()
    surface.fill((16, 19, 34))
    # Soft depth behind the playable plane, independent of the selected region.
    for y in range(0, height, 4):
        t = y / max(1, height)
        pygame.draw.rect(surface, (int(19+14*t), int(22+10*t), int(39+19*t)), (0,y,width,4))
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
    # The lip adds depth without introducing any new collision geometry.
    pygame.draw.polygon(surface, (26,25,43), [(x,y+16) for x,y in outline])
    surface.blit(ground, (0,0))
    pygame.draw.lines(surface, (60,58,84), False, [outline[1],outline[2],outline[3]], 2)


@lru_cache(maxsize=4)
def network_paths(grid, region):
    """Connected jittered mesh in world tile coordinates, not per-tile decals."""
    rng = random.Random(91417)
    spacing = 5.4
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
            bend = rng.uniform(-.75,.75)
            steps = 9 if name in ("Wind","Forest") else 4
            pts = []
            for i in range(steps+1):
                t = i/steps
                sway = math.sin(math.pi*t)*bend
                if name == "Wind":
                    sway += math.sin(t*math.tau)*.25
                if name == "Fire":
                    sway += (rng.uniform(-.35,.35) if 0<i<steps else 0)
                pts.append((a[0]+dx*t-dy/length*sway, a[1]+dy*t+dx/length*sway))
            paths.append((tuple(pts), True))
            # Dim rootlike tributaries; the same calm density in all regions.
            n = 2 if name == "Forest" else 1
            for k in range(n):
                mid = pts[(k+1)*steps//(n+1)]
                side = -1 if rng.random()<.5 else 1
                tip = (mid[0]-dy/length*side*1.25+dx*.12,
                       mid[1]+dx/length*side*1.25+dy*.12)
                branch = (mid, ((mid[0]+tip[0])*.5+.13,(mid[1]+tip[1])*.5-.1), tip)
                paths.append((branch,False))
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
            pygame.draw.lines(layer, (*color,16), False, pts, 9)
            pygame.draw.lines(layer, (*color,34), False, pts, 5)
    for pts,main in projected:
        pygame.draw.lines(layer, (*color,158 if main else 45), False, pts, 2 if main else 1)
        if main:
            pygame.draw.circle(layer, (*color,185), pts[0], 2)
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
    layer.set_alpha(round(158+35*math.sin(ticks*.001*math.tau/period)), pygame.RLEACCEL)
    # Source crop keeps both desktop and browser work bounded by the viewport.
    dest = pygame.Rect(round(cache["x0"]-camx),round(cache["y0"]-camy),*layer.get_size())
    visible = dest.clip(screen.get_rect())
    if visible.width and visible.height:
        screen.blit(layer, visible.topleft, visible.move(-dest.x,-dest.y),
                    special_flags=pygame.BLEND_ALPHA_SDL2)


@lru_cache(maxsize=128)
def illustrated_wall(width, height, wall_h, color, seed):
    atlas = source_asset("neural-walls-v2.png")
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
    art = pygame.transform.smoothscale(art, (max(1,width//2),max(1,target[1]//2)))
    art = pygame.transform.scale(art, target)
    if fragile:
        damage = min(1.0, max(.4, color[0]/147))
        tint = round(255*damage)
        art.fill((tint,tint,tint,255), special_flags=pygame.BLEND_RGBA_MULT)
    result = pygame.Surface((width+2,height+wall_h+2),pygame.SRCALPHA)
    pygame.draw.ellipse(result, (9,12,23,100), (2,wall_h+height//2,width-2,height//2))
    result.blit(art,(1,1))
    if pygame.display.get_surface() is not None:
        result = result.convert_alpha()
    result.set_alpha(255, pygame.RLEACCEL)
    return result,(width+2)//2,1+wall_h
