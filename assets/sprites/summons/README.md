# Eidolon assets

- `skull-option-b.png`: active five-column, three-stage directional atlas. Views
  are front, front-right, right, rear-right, rear; runtime mirrors left views.
  The approved bone masks, red-purple tendrils and synaptic nodes are unchanged.
  Its image-generation provenance is in `skull-option-b-prompt.md`.
- `eidolon-shop-avatars.png`: exact user-supplied three-avatar screenshot.
  `shop_avatar` selects each square card without its separators; both shops use
  the corresponding evolution avatar under the name **Eidolon**.
- `skull-atlas.png`: retained because its fourth quadrant is the active spectral
  Shadow Procession skull. Other quadrants are unused. Do not delete this file
  merely because it predates Option B.

Visible companion heights target 96 / 144 / 216 pixels. Per-row transparent
padding is compensated while preserving fixed directional anchors. Collision
remains 0.44 tile. Beam, orb tails and dissolution are native Pygame effects.

Shadow Procession stores normalized viewport paths and resolves both drawing
and damage around the current player each frame. Existing world-space saved
casts are supported until they expire; all new casts use viewport space.

The unused `skull-directions.png` and its prompt were removed after checking
runtime references. They remain recoverable from the pre-Option-B Git checkpoint.
