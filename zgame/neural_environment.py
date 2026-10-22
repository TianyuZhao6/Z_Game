"""Shared neural garden materials; region identity belongs to the floor only.

Legacy region IDs deliberately remain save/gameplay keys. Art uses local seeded
randomness and cached surfaces, never the combat RNG or collision grid.
"""
from functools import lru_cache
import math
import sys

import pygame

from zgame.vessel_network import network_geometry, ribbon, branch_alpha

from zgame.paths import asset_candidates, first_existing_path


REGIONS = {
    "Domain of Wind": ("Wind", "风", (45, 145, 235), 6.4),
    "Misty Forest": ("Forest", "林", (87, 170, 133), 7.8),
    "Scorched Hell": ("Fire", "火", (211, 120, 83), 5.6),
    "Bastion of Stone": ("Mountain", "山", (174, 151, 103), 9.2),
}
DEFAULT_REGION = "Domain of Wind"


def region_style(legacy_id):
    return REGIONS.get(legacy_id, REGIONS[DEFAULT_REGION])


def region_name(legacy_id):
    return region_style(legacy_id)[0]


@lru_cache(maxsize=32)
def source_asset(name):
    path = first_existing_path(asset_candidates("sprites", "environment", name))
    return pygame.image.load(path) if path else None


@lru_cache(maxsize=1)
def ground_material():
    source = source_asset("neural-stone-v1.png")
    if source is None:
        return None
    # Preserve plate boundaries instead of erasing them in a tiny intermediate.
    tile = pygame.transform.smoothscale(source, (1536, 768))
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
def abyss_view(size, grid, cell_w, cell_h):
    source = source_asset("neural-abyss.png")
    if source is None:
        return None
    # Cover the complete playable camera range, rather than saturating motion
    # with tanh. No tiling/reset is necessary anywhere around this platform.
    pad_x = grid*cell_w*.14+160
    pad_y = grid*cell_h*.14+160
    scale = max((size[0]+pad_x)/source.get_width(),(size[1]+pad_y)/source.get_height())
    result = pygame.transform.smoothscale(source,
        (math.ceil(source.get_width()*scale),math.ceil(source.get_height()*scale)))
    return result.convert() if pygame.display.get_surface() else result


def abyss_camera_offset(size, camx, camy, grid, cell_h, info, depth):
    # All layers use the same world center, at different depth ratios.
    return ((camx+size[0]*.5)*depth,
            (camy+size[1]*.5-info-grid*cell_h*.5)*depth)


@lru_cache(maxsize=2)
def distant_formation(reverse=False):
    source = source_asset("neural-cliff.png")
    if source is None:
        return None
    image = pygame.transform.smoothscale(source,(860,430))
    if reverse:
        image = pygame.transform.flip(image,True,False)
    # Atmospheric distance: preserve the cutout, soften its dark contrast and
    # keep its buds much dimmer than gameplay signals.
    image.fill((175,168,205,160),special_flags=pygame.BLEND_RGBA_MULT)
    return image


@lru_cache(maxsize=2)
def atmosphere_glow(size):
    small = pygame.Surface((96,96),pygame.SRCALPHA)
    for radius in range(47,0,-1):
        pygame.draw.circle(small,(166,139,199,round(18*(1-radius/48)**2)),(48,48),radius)
    return pygame.transform.smoothscale(small,size)


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


def _draw_abyss_layers(screen, camx, camy, grid, cell_w, cell_h, info, ticks):
    size = screen.get_size()
    art = abyss_view(size,grid,cell_w,cell_h)
    if art is not None:
        dx,dy = abyss_camera_offset(size,camx,camy,grid,cell_h,info,.14)
        x = round((size[0]-art.get_width())*.5-dx)
        y = round((size[1]-art.get_height())*.5-dy)
        screen.blit(art,(x,y))
        glow = atmosphere_glow((280,280))
        glow.set_alpha(round(140+90*math.sin(ticks*math.tau/13)))
        screen.blit(glow,(round(x+art.get_width()*.835-140),round(y+art.get_height()*.16-140)))
    dx,dy = abyss_camera_offset(size,camx,camy,grid,cell_h,info,.40)
    for i,(wx,wy) in enumerate(((-1450,450),(1450,500),(300,-1000))):
        image = distant_formation(bool(i%2))
        if image is None:
            continue
        rect = image.get_rect(center=(round(size[0]*.5+wx*.40-dx),
                                      round(size[1]*.5+wy*.40-dy)))
        if rect.colliderect(screen.get_rect()):
            screen.blit(image,rect)
    # Slow haze is independent of camera displacement; it complements rather
    # than substitutes for the genuine positional parallax above.
    haze = atmosphere_glow((720,280))
    hx,hy = abyss_camera_offset(size,camx,camy,grid,cell_h,info,.24)
    haze.set_alpha(round(130+35*math.sin(ticks*.19)))
    screen.blit(haze,(round(size[0]*.48-hx+32*math.sin(ticks*.08)),
                      round(size[1]*.52-hy+12*math.sin(ticks*.11))))
    draw_platform_rim(screen,camx,camy,grid,cell_w,cell_h,info,front=False)


@lru_cache(maxsize=1)
def abyss_scene(size, camx, camy, grid, cell_w, cell_h, info, atmosphere_step):
    # Reuse the whole opaque composition while the camera rests. Slow haze
    # and thirteen-second illumination need only ten updates per second.
    # Camera coordinates are part of the key: movement is never throttled.
    frame = pygame.Surface(size)
    _draw_abyss_layers(frame,camx,camy,grid,cell_w,cell_h,info,atmosphere_step*.1)
    return frame.convert() if pygame.display.get_surface() else frame


def draw_abyss(screen, camx, camy, grid, cell_w, cell_h, info):
    camera_key=(screen.get_size(),camx,camy,grid,cell_w,cell_h,info)
    atmosphere_step=pygame.time.get_ticks()//100
    moved=camera_key != getattr(draw_abyss,'_last_camera',None)
    draw_abyss._last_camera=camera_key
    if moved:
        # A moving view cannot reuse the composition. Paint directly instead
        # of allocating/converting a full-screen surface and copying it again.
        _draw_abyss_layers(screen,camx,camy,grid,cell_w,cell_h,info,atmosphere_step*.1)
        return
    frame = abyss_scene(*camera_key,atmosphere_step)
    screen.blit(frame,(0,0))


def view_inside_platform(size, camx, camy, grid, cell_w, cell_h, info):
    """The convex platform can fully cover a view, avoiding hidden backdrop work."""
    for x,y in ((0,0),(size[0]-1,0),(0,size[1]-1),(size[0]-1,size[1]-1)):
        sx,sy = x+camx,y+camy-info
        gx,gy = sy/cell_h+sx/cell_w,sy/cell_h-sx/cell_w
        if not (1 < gx < grid-1 and 1 < gy < grid-1):
            return False
    return True


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


NETWORK_PHASES = 8
# Paired profiling favors pygame's regular blitter on desktop, but SDL2's
# alpha-modulated path in WebAssembly. Both draw the same cached RGBA artwork.
NETWORK_BLEND = pygame.BLEND_ALPHA_SDL2 if sys.platform == 'emscripten' else 0


def batch_network_stamps(stamps):
    """Merge nearby equal-phase art only when its bounds stay inexpensive.

    Large fixed tiles waste alpha-blending work on transparent space. These
    cropped, variable bounds never grow beyond 110% of their input area.
    Geometry stays untouched; only the breathing phase is quantized once.
    """
    groups = [[] for _ in range(NETWORK_PHASES)]
    for image, (x, y), phase in stamps:
        bounds = image.get_bounding_rect()
        if not bounds.width or not bounds.height:
            continue
        rect = bounds.move(x, y)
        phase_index = round(phase / math.tau * NETWORK_PHASES) % NETWORK_PHASES
        groups[phase_index].append((image.subsurface(bounds), rect))
    result = []
    for phase_index, members in enumerate(groups):
        batches = []
        for image, rect in sorted(members, key=lambda item: -item[1].w * item[1].h):
            best = None
            for index, (box, area, parts) in enumerate(batches):
                union = box.union(rect)
                cost = union.w * union.h
                if (union.w <= 420 and union.h <= 280
                        and cost <= (area + rect.w * rect.h) * 1.10
                        and box.inflate(48, 48).colliderect(rect)):
                    if best is None or cost < best[0]:
                        best = cost, index, union
            if best is None:
                batches.append((rect, rect.w * rect.h, [(image, rect)]))
            else:
                _, index, union = best
                box, area, parts = batches[index]
                batches[index] = union, area + rect.w * rect.h, parts + [(image, rect)]
        for box, _, parts in batches:
            image = pygame.Surface(box.size, pygame.SRCALPHA)
            image.blits([(part, rect.move(-box.x, -box.y)) for part, rect in parts], doreturn=False)
            if pygame.display.get_surface():
                image = image.convert_alpha()
            result.append((image, box.topleft, phase_index * math.tau / NETWORK_PHASES))
    return tuple(result)


@lru_cache(maxsize=1)
def network_material(grid, cell_w, cell_h, info, size, x0, y0, region, seed=91417, blocked=()):
    """Cache tight branch stamps; only their opacity changes during play."""
    underlay = pygame.Surface(size,pygame.SRCALPHA)
    color = region_style(region)[2]
    core = tuple(min(255,round(c*1.12+18)) for c in color)
    paths,_ = network_geometry(grid,region_name(region),seed,blocked)
    stamps=[]
    # Use the actual stone material's luminance to break up emissive coverage.
    texture=pygame.transform.grayscale(ground_material())
    texture.fill((142,142,142),special_flags=pygame.BLEND_RGB_ADD)
    tw,th=texture.get_size()
    for path in paths:
        points=tuple(((x-y)*cell_w*.5-x0,(x+y)*cell_h*.5+info-y0) for x,y in path.points)
        margin=math.ceil(max(path.radii)*8*cell_w/82)+3
        left=math.floor(min(p[0] for p in points))-margin
        top=math.floor(min(p[1] for p in points))-margin
        width=math.ceil(max(p[0] for p in points))-left+margin
        height=math.ceil(max(p[1] for p in points))-top+margin
        stamp=pygame.Surface((width*2,height*2),pygame.SRCALPHA)
        local=tuple(((x-left)*2,(y-top)*2) for x,y in points)
        # A quiet mineral groove anchors the light underneath the surface.
        pygame.draw.polygon(underlay,(12,24,40,38),ribbon(points,path.radii,2.4))
        pygame.draw.polygon(underlay,(*color,24),ribbon(points,path.radii,1.25))
        for multiplier,alpha in ((7,9),(3.5,27),(1.7,62),(.65,210)):
            outline=ribbon(local,path.radii,multiplier*cell_w/82*2)
            n=len(local)
            left_edge,right_edge=outline[:n],outline[n:][::-1]
            for k in range(n-1):
                strength=(path.strengths[k]+path.strengths[k+1])*.5
                ink=(*(core if multiplier<1 else color),round(alpha*strength))
                pygame.draw.polygon(stamp,ink,(left_edge[k],left_edge[k+1],right_edge[k+1],right_edge[k]))
        stamp=pygame.transform.smoothscale(stamp,(width,height))
        material=pygame.Surface((width,height))
        for row in range(top//th,(top+height)//th+1):
            for col in range(left//tw,(left+width)//tw+1):
                material.blit(texture,(col*tw-left,row*th-top))
        stamp.blit(material,(0,0),special_flags=pygame.BLEND_RGB_MULT)
        # Clip light at the real platform boundary and obstacle footprints.
        mask=pygame.Surface((width,height),pygame.SRCALPHA)
        pygame.draw.polygon(mask,(255,255,255,255),floor_outline(grid,cell_w,cell_h,x0+left,y0+top,info))
        for gx,gy in blocked:
            diamond=[((x-y)*cell_w*.5-x0-left,(x+y)*cell_h*.5+info-y0-top)
                     for x,y in ((gx,gy),(gx+1,gy),(gx+1,gy+1),(gx,gy+1))]
            pygame.draw.polygon(mask,(0,0,0,0),diamond)
        stamp.blit(mask,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        if pygame.display.get_surface():
            stamp=stamp.convert_alpha()
        stamps.append((stamp,(left,top),path.phase))
    mask=pygame.Surface(size,pygame.SRCALPHA)
    pygame.draw.polygon(mask,(255,255,255,255),floor_outline(grid,cell_w,cell_h,x0,y0,info))
    underlay.blit(mask,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
    if pygame.display.get_surface():
        underlay=underlay.convert_alpha()
    underlay.set_alpha(255,pygame.RLEACCEL)
    return underlay,batch_network_stamps(stamps)


@lru_cache(maxsize=1)
def network_surface(grid, cell_w, cell_h, info, size, x0, y0, region, seed=91417, blocked=()):
    return network_material(grid,cell_w,cell_h,info,size,x0,y0,region,seed,blocked)[0]


@lru_cache(maxsize=16)
def illustrated_node(region, index):
    names = ('node-small','node-medium','node-large','node-damaged')
    source = source_asset('neural-parts-v2/'+names[index]+'.png')
    if source is None:
        return synapse_glow(region), (18,18)
    # Grayscale keeps the supplied energy's luminance/alpha while allowing
    # all four region palettes, including warm fire and mountain light.
    image = pygame.transform.grayscale(source)
    color = tuple(min(255,round(c*1.22+20)) for c in region_style(region)[2])
    image.fill((*color,255),special_flags=pygame.BLEND_RGBA_MULT)
    width = (100,120,140,110)[index]
    height = round(width*2/3)
    image = pygame.transform.smoothscale(image,(width,height))
    # Original soma coordinates within each uniform atlas cell. Position the
    # soma on the spline crossing, not the center of its asymmetric tendrils.
    anchors = ((225,315),(206,295),(212,302),(223,308))
    anchor = (round(anchors[index][0]*width/384),round(anchors[index][1]*height/512))
    pygame.draw.circle(image,(170,225,248,240),anchor,2 if index==2 else 1)
    return image,anchor


def draw_network(screen, cache, grid, cell_w, cell_h, info, region, camx, camy, ticks, state=None):
    seed=getattr(state,'network_seed',91417)
    blocked=getattr(state,'network_obstacles',())
    args=(grid,cell_w,cell_h,info,cache['surface'].get_size(),cache['x0'],cache['y0'],region,seed,blocked)
    underlay=network_surface(*args)
    _,stamps=network_material(*args)
    offset=(round(cache['x0']-camx),round(cache['y0']-camy))
    screen.blit(underlay,offset,special_flags=pygame.BLEND_ALPHA_SDL2)
    viewport=screen.get_rect()
    blits=[]
    alphas={i*math.tau/NETWORK_PHASES: branch_alpha(i*math.tau/NETWORK_PHASES,ticks)
            for i in range(NETWORK_PHASES)}
    for image,(x,y),phase in stamps:
        rect=image.get_rect(topleft=(x+offset[0],y+offset[1]))
        if not rect.colliderect(viewport):
            continue
        # Choose the measured fast path for this runtime; no per-frame RLE
        # encoding, geometry generation, texture work, or surface allocation.
        image.set_alpha(alphas[phase])
        blits.append((image,rect,None,NETWORK_BLEND))
    screen.blits(blits,doreturn=False)
    _,hubs=network_geometry(grid,region_name(region),seed,blocked)
    for node in hubs:
        x,y=node.x,node.y
        sx,sy=round((x-y)*cell_w*.5-camx),round((x+y)*cell_h*.5+info-camy)
        if not viewport.inflate(160,100).collidepoint(sx,sy):
            continue
        index=node.rank if node.rank else (3 if int(node.phase*10)%5==0 else 0)
        image,anchor=illustrated_node(region,index)
        image.set_alpha(branch_alpha(node.phase-.25,ticks))
        screen.blit(image,(sx-anchor[0],sy-anchor[1]))


@lru_cache(maxsize=4)
def synapse_glow(region):
    color = region_style(region)[2]
    glow = pygame.Surface((36,36),pygame.SRCALPHA)
    for radius in range(18,0,-1):
        alpha = round(105*(1-radius/19)**2)
        pygame.draw.circle(glow,(*color,alpha),(18,18),radius)
    pygame.draw.circle(glow,(190,225,245,200),(18,18),1)
    return glow


def wall_variant(gx, gy, obstacles):
    """Stable spatial families plus topology; never consume gameplay RNG.

    Nearby cells share a height family, so runs remain coherent. The family
    depends on world position, not surviving neighbors, and survives save/load.
    Bits: 0..1 detail, 2 facing, 3..4 height, 5 corner, 6 end, 7 bare roots.
    """
    from zgame.terrain_art import variant
    nx = sum((gx+d,gy) in obstacles for d in (-1,1))
    ny = sum((gx,gy+d) in obstacles for d in (-1,1))
    detail = variant(gx,gy)
    family = variant(gx//7,gy//7)%4
    endpoint = nx+ny<=1
    corner = nx>0 and ny>0
    decorated = detail%5==0 or (endpoint and detail%2==0)
    return ((detail%4) | (4 if ny>nx else 0) | (family<<3)
            | (32 if corner else 0) | (64 if endpoint else 0)
            | (0 if decorated else 128))


def wall_extrusion(wall_h, seed):
    scale = (1.0,.50,.78,1.18)[(seed>>3)&3]
    return max(32,round(wall_h*scale)+(6 if seed&32 else 0)-(8 if seed&64 else 0))


def structure_name(fragile, seed):
    """Solid single-tile cutouts; loose rubble is not a blocking obstacle."""
    family = (seed>>3)&3
    if fragile:
        return ('masonry-stump' if family==1 else
                ('masonry-chipped' if seed&1 else 'masonry-fragile'))
    if seed&64 or (seed&32 and seed&1):
        return ('basalt-low','basalt-rooted','basalt-spire','basalt-rooted')[family]
    return 'masonry-dark'


def structure_wall(width, height, wall_h, color, seed):
    fragile = color[0] > color[2]
    source = source_asset('neural-parts-v2/'+structure_name(fragile,seed)+'.png')
    if source is None:
        return None
    bounds = source.get_bounding_rect(min_alpha=20)
    art = source.subsurface(bounds)
    extrusion = wall_extrusion(wall_h,seed)
    # Reserve the lower half-diamond for the actual footprint. Roots may
    # overhang it, but the raised stone remains aligned with the one-cell hitbox.
    roots_h = max(5,round(height*.28))
    out_w = round(width*1.25)
    result = pygame.transform.smoothscale(art,(out_w,extrusion+height+roots_h))
    if seed&4:
        result = pygame.transform.flip(result,True,False)
    if seed&128:
        result.fill((205,205,218,255),special_flags=pygame.BLEND_RGBA_MULT)
    if fragile:
        tint = round(255*min(1.0,max(.4,color[0]/147)))
        result.fill((tint,tint,tint,255),special_flags=pygame.BLEND_RGBA_MULT)
    return (result.convert_alpha() if pygame.display.get_surface() else result,
            out_w//2,1+extrusion)


@lru_cache(maxsize=256)
def illustrated_wall(width, height, wall_h, color, seed):
    derived = structure_wall(width,height,wall_h,color,seed)
    if derived is not None:
        return derived
    atlas = source_asset("neural-walls.png")
    if atlas is None:
        return None
    fragile = color[0] > color[2]
    idx = 1 if fragile else 0
    cw = atlas.get_width()//2
    cell = atlas.subsurface((idx*cw,0,cw,atlas.get_height()))
    bounds = cell.get_bounding_rect(min_alpha=20)
    art = cell.subsurface(bounds)
    wall_h = wall_extrusion(wall_h,seed)
    # Map the stone cap (80% of the cutout width) onto the actual diamond.
    # Roots overhang; they must not shrink the collision-sized stone body.
    # Scale cap and extrusion separately so neighboring tops meet at 2:1.
    out_w = round(width/0.80)
    cap_end = round(art.get_height()*.38)
    roots_start = round(art.get_height()*.93)
    roots_h = max(5,round(height*.28))
    result = pygame.Surface((out_w+2,wall_h+height+roots_h+2),pygame.SRCALPHA)
    for source_y,source_h,dest_y,dest_h in (
        (0,cap_end,1,height),
        (cap_end,roots_start-cap_end,1+height,wall_h),
        (roots_start,art.get_height()-roots_start,1+height+wall_h,roots_h)):
        strip = art.subsurface((0,source_y,art.get_width(),source_h))
        result.blit(pygame.transform.smoothscale(strip,(out_w,dest_h)),(1,dest_y))
    if seed & 4:
        result = pygame.transform.flip(result, True, False)
    if seed&128:
        # Suppress bright buds on most blocks using the existing cutout;
        # native mask/blend operations avoid Python pixel loops on browser
        # cache misses (newly exposed endpoints and damaged wall variants).
        body = result.subsurface((0,height,result.get_width(),result.get_height()-height))
        buds = pygame.mask.from_threshold(body,(205,176,229,255),(65,75,60,255))
        tint = buds.to_surface(setcolor=(128,128,128,255),unsetcolor=(255,255,255,255))
        body.blit(tint,(0,0),special_flags=pygame.BLEND_RGB_MULT)
        result.fill((255,255,255,89),(0,height+wall_h+1,result.get_width(),roots_h+1),
                    special_flags=pygame.BLEND_RGBA_MULT)
    # End and weathered cap chips alter silhouette, not the ground footprint.
    if seed&64 or ((seed>>3)&3)==3:
        cx = (out_w+2)//2
        notch = 5+(seed&3)*2
        pygame.draw.polygon(result,(0,0,0,0),
            [(cx-notch,0),(cx+notch,0),(cx+notch//2,8),(cx-3,5)])
    if fragile:
        damage = min(1.0, max(.4, color[0]/147))
        tint = round(255*damage)
        result.fill((tint,tint,tint,255), special_flags=pygame.BLEND_RGBA_MULT)
    if pygame.display.get_surface() is not None:
        result = result.convert_alpha()
    # Walls also composite into an RGBA cache. RLE's SDL2 blit path can
    # turn their translucent edge/shadow pixels opaque on that destination.
    return result,(out_w+2)//2,1+wall_h
