# Region 04 palette refinement — 2026-10-22

> Historical palette decision. The user's later standing direction in AGENTS.md is desktop-only: Wind cyan-blue, Forest purple, Fire red, Stone pale gold/yellow. See the [current desktop review](region04-desktop-shimmer-validation.md).

The previous cyan treatment still looked mint-like in gameplay. The renderer derived most light colors from one region tint and used a separate formula for node artwork. The current implementation separates the colors of the base trace, inner energy, outer glow, node core, node glow, and ambient halo. This gives each biome an explicit palette without rebuilding source art or changing vessel geometry.

## Visual choices

`NETWORK_PALETTES` in `zgame/neural_environment.py` maps existing save/gameplay region keys to immutable `NetworkPalette` values. Wind stays airy blue, Forest jade-green, Fire coral, and Mountain cold blue. These are source configurations read when cached materials are constructed; runtime palette editing is not exposed.

Region 04 uses:

| Layer | RGB | Purpose |
|---|---|---|
| Base | 43, 110, 200 | Cool trace that remains visible when illumination dims |
| Inner energy | 62, 174, 255 | Saturated cold blue, reducing the previous mint appearance |
| Outer glow | 42, 112, 245 | Restrained electric-blue halo |
| Node core | 225, 246, 255 | Near-white highlights at selected major junctions |
| Node glow | 69, 155, 255 | Blue separation around the brightest cores |
| Ambient halo | 107, 87, 182 | Faint lavender at the outer edge only |

Major nodes retain their existing positions and ranks. Their compact core and illumination range are stronger than ordinary junctions. Minor junctions remain smaller and dimmer. Node source images are converted to grayscale before tinting, so cyan from the original art cannot contaminate the Fire or Forest palette. Fallback nodes also use the same palette.

The existing 4.3–6.7-second breathing, independent phases, tapered branch strengths, world alignment, obstacle handling, seeds, and geometry are unchanged. All branch color layers are baked into the existing stamp; no additional per-frame draw passes or particles were introduced. Platform art, walls, actors, background, gameplay, and UI were not changed.

## Evidence and checks

See the [current evidence index](evidence/README.md). The same seed, layout, camera and real animation times compare the previous palette at `0aa3e05` with this revision. Source topology equality is asserted against that checkpoint. Dim/intermediate/peak are 3022/4534/6045 ms for a selected 6.045-second group; other branches remain asynchronous.

Visual review of the current dim, peak, and combat captures shows cooler blue vessels, concentrated white-blue major nodes, and lower-contrast secondary branches. The dim base remains visible. This is a refinement toward the supplied reference, not a claim that the full game screenshot is identical to the concept art. Final aesthetic acceptance remains with the user.

Five targeted environment tests passed: palette recoloring with identical alpha coverage, visible dim/peak difference, cache reuse during motion, world alignment, and transparent asynchronous phase batches. Palette tests hold geometry fixed, verify all four regions produce distinct material colors, and check that node centers use their own palette rather than baked blue.

The actual desktop level-loop fixture passed 565 frames with 72 enemies, camera movement, and overlapping beam/Procession effects. Two real projectile updates destroyed wall `(24,18)`. The original network obstacle footprint and geometry identity remained unchanged on every update. The new combat image and clip were retained; duplicate temporary captures were removed afterward.

## Comparable desktop performance

Paired native renderer measurements, 1280×720, 80 warm samples per scene, alternating old/new order. Mean milliseconds:

| Scene | Before complete render | After complete render | Before network | After network |
|---|---:|---:|---:|---:|
| Fixed camera | 17.225 | 17.178 | 2.355 | 2.319 |
| Moving camera | 18.454 | 18.545 | 2.169 | 2.188 |
| Moving, 72 static actors | 19.655 | 19.789 | 2.163 | 2.191 |

The changes are within ordinary run variation and show no material new network overhead. In the separate live 72-enemy run, complete rendering averaged 27.991 ms (p95 33.693); network rendering averaged 1.417 ms (p95 1.753). Background/environment averaged 19.572 ms. Rendering still misses a stable 60 FPS budget, with environment cost dominant.

These tests use the actual native renderer with an SDL dummy display, excluding screenshot encoding. They are not OS presentation or complete update-plus-display FPS measurements. Browser validation remains deferred. The original six-item checklist's performance item remains partial; the new palette pass does not close that limitation.

## Cleanup and recoverability

Removed 146 old generated TEMP files (114.94 MiB), 23 superseded tracked evidence images/videos (51.71 MiB), nine small scratch scripts, three duplicate newly generated before-images, and 3,005 empty test directories. Retained current evidence, immediate pre-palette peak comparison, historical performance measurements, parallax evidence, unrelated summon work, save data, and audio analysis. Historical reports now indicate archived media rather than linking to removed files. Removed tracked files remain in `0aa3e05`.

Runtime change: `zgame/neural_environment.py`. Test/tool changes: `tools/verify_environment_runtime.py`, `tools/review_region04_illumination.py`. The topology generator `zgame/vessel_network.py` is unchanged. Additional changes are this report, evidence/index/cleanup records, the environment asset README, and archive annotations in the four earlier environment/network validation documents.
