import pygame
import random
import math

# --- 1. NEON GLOW PARTICLE SYSTEM ---
# This system pre-renders "glow balls" so it runs very fast (60+ FPS)
# even with hundreds of particles.

class GlowCache:
    """Caches generated glow surfaces so we don't draw circles every frame."""
    cache = {}

    @staticmethod
    def get_glow_surf(radius, color):
        """
        Returns a surface with a soft, transparent radial gradient.
        Color should be (R, G, B).
        """
        key = (radius, color)
        if key in GlowCache.cache:
            return GlowCache.cache[key]

        # Create a surface with per-pixel alpha
        size = radius * 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        
        # Draw concentric circles with decreasing alpha to simulate a glow
        # We start transparent and get more opaque towards the center
        # For a "Neon" look, we actually want the center to be white-ish
        steps = 10
        for i in range(steps):
            prog = i / steps
            current_r = int(radius * (1 - prog))
            if current_r <= 0: break
            
            # Alpha gets stronger in the middle
            alpha = int(255 * (prog ** 2)) * 0.3 
            
            # Interpolate towards white in the center for "hot" look
            r = min(255, color[0] + int((255 - color[0]) * (prog**2)))
            g = min(255, color[1] + int((255 - color[1]) * (prog**2)))
            b = min(255, color[2] + int((255 - color[2]) * (prog**2)))
            
            pygame.draw.circle(surf, (r, g, b, int(alpha)), (radius, radius), current_r)

        GlowCache.cache[key] = surf
        return surf

class Particle:
    def __init__(self, x, y, vx, vy, color, life, size, decay_mode="shrink"):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.life_max = life
        self.life = life
        self.size_max = size
        self.size = size
        self.decay_mode = decay_mode # "shrink" or "fade"

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        
        # Drag/Friction (optional, feels better for explosions)
        self.vx *= 0.95
        self.vy *= 0.95

        # Update visual property based on life
        ratio = max(0, self.life / self.life_max)
        if self.decay_mode == "shrink":
            self.size = int(self.size_max * ratio)
        
        return self.life > 0

    def draw(self, screen, offset_x=0, offset_y=0):
        if self.size < 1: return
        
        # Get the cached glow image
        glow = GlowCache.get_glow_surf(self.size, self.color)
        
        # Center the blit
        dest = (self.x - self.size - offset_x, self.y - self.size - offset_y)
        
        # BLEND_ADD is the magic flag. It adds pixel values together.
        # Dark Background + Additive Color = NEON LIGHT.
        screen.blit(glow, dest, special_flags=pygame.BLEND_ADD)

class ParticleSystem:
    def __init__(self):
        self.particles = []

    def spawn_explosion(self, x, y, color, count=10):
        for _ in range(count):
            angle = random.uniform(0, 6.28)
            speed = random.uniform(50, 250)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            life = random.uniform(0.3, 0.8)
            size = random.randint(4, 12)
            self.particles.append(Particle(x, y, vx, vy, color, life, size))

    def spawn_trail(self, x, y, color):
        """Call this every frame behind the player or bullet"""
        # Low speed, short life
        self.particles.append(Particle(
            x + random.uniform(-2, 2), 
            y + random.uniform(-2, 2), 
            random.uniform(-10, 10), 
            random.uniform(-10, 10), 
            color, 
            0.3, 
            6, 
            decay_mode="shrink"
        ))

    def update(self, dt):
        # Update and keep only alive particles
        self.particles = [p for p in self.particles if p.update(dt)]

    def draw(self, screen, cam_x=0, cam_y=0):
        for p in self.particles:
            p.draw(screen, cam_x, cam_y)


# --- 2. 9-SLICE UI RENDERER ---
# This allows you to make UI boxes that look good at any size.

def draw_9_slice(surface, rect, color, border_radius=10):
    """
    Procedurally draws a sci-fi UI box without needing an image asset.
    It simulates a "glass" panel with a glowing border.
    """
    # 1. Background (Dark semi-transparent)
    # We create a temp surface to handle alpha properly
    bg = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    
    # Dark blue-ish background (The "Glass")
    pygame.draw.rect(bg, (10, 20, 30, 200), bg.get_rect(), border_radius=border_radius)
    
    # 2. Border (The "Neon Edge")
    # Brighter version of the input color
    border_color = color
    pygame.draw.rect(bg, border_color, bg.get_rect(), width=2, border_radius=border_radius)
    
    # 3. Accents (The "Tech" look)
    # Draw thicker corners or lines to make it look designed
    w, h = rect.width, rect.height
    corner_len = 15
    
    # Top-Left Corner Bracket
    pygame.draw.line(bg, (255, 255, 255), (0, corner_len), (0, border_radius+2), 3) # vertical
    
    # Bottom-Right Corner Bracket
    pygame.draw.line(bg, (255, 255, 255), (w-2, h-corner_len), (w-2, h-border_radius-2), 3)
    
    surface.blit(bg, rect)


# --- 3. DEMO LOOP (Run this file to test) ---
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()
    
    particles = ParticleSystem()
    
    # Colors (Neuron Theme)
    CYAN = (0, 255, 255)
    PURPLE = (180, 0, 255)
    GREEN = (50, 255, 100)

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        mx, my = pygame.mouse.get_pos()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            if event.type == pygame.MOUSEBUTTONDOWN:
                # Left click: Cyan Explosion
                if event.button == 1:
                    particles.spawn_explosion(mx, my, CYAN, count=30)
                # Right click: Purple Explosion
                elif event.button == 3:
                    particles.spawn_explosion(mx, my, PURPLE, count=30)

        # Update
        particles.update(dt)
        particles.spawn_trail(mx, my, GREEN) # Mouse trail

        # Draw
        # 1. Dark background is ESSENTIAL for Additive Blending to pop
        screen.fill((10, 10, 15)) 
        
        # 2. Draw Particles
        particles.draw(screen)
        
        # 3. Draw UI
        ui_rect = pygame.Rect(50, 50, 300, 100)
        draw_9_slice(screen, ui_rect, CYAN)
        
        # Text inside UI
        font = pygame.font.SysFont("Consolas", 24)
        txt = font.render("SYSTEM: NEURAL LINK ACTIVE", True, (200, 255, 255))
        screen.blit(txt, (70, 85))

        pygame.display.flip()

    pygame.quit()