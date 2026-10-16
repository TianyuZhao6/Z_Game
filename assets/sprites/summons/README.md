# Evolving Skull atlas

`skull-atlas.png` is the integrated transparent 2x2 atlas. Quadrants in reading order:
Bloombone, Soulflame, Rift Skull, Shadow Procession. Runtime slices the atlas,
scales with nearest-neighbor sampling, and applies procession translucency/fades.
The companion sprite canvas is 2.8 tiles; its physical body is only 0.44 tile.

Generated using the built-in image-generation tool, guided by the approved
floating-skull comparison. No existing game assets were overwritten.

## Generation prompt

Use case: stylized-concept. Create ONE production game sprite atlas on genuine
transparent background, square canvas, exactly 2 by 2 equal square cells, no
borders, no text, no ground, no shadows. Input is design reference only. Each
cell contains one complete isolated floating skull centered with generous 12%
transparent margin, no overlap between cells. Match the reference's small
pixel-art sprites rather than its painted big portraits. Top-left: Bloombone,
reference B, crimson organic bone petals, violet tendrils, pale skull. Top-right:
Soulflame, reference A, separated jaw, living violet flame mane, red eyes.
Bottom-left: Rift Skull, reference C, fragmented pale bone horns and separated
jaw around ONE crimson eye with purple spectral tissue. Bottom-right: Shadow
Procession attack sprite, open-mouthed skull facing right, pale lavender-white
and soft rose, translucent spectral bone with clearly visible mouth and teeth,
no long trail (trails rendered by game). All skulls approximately equal visible
scale, crisp limited-palette pixel-art, readable at 96 pixels. The first three
have solid bone and distinct silhouette; fourth lighter ghostly. Preserve
organic supernatural identity; no metal, no robots. Exact equal quadrant layout
is essential for runtime atlas slicing.
