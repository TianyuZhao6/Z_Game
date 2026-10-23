# Desktop neural palette and shimmer validation — 2026-10-22

## Restored as the selected baseline — 2026-10-23

The user selected this version over the later route and fine-branch revisions. Restored `zgame/neural_environment.py`, `zgame/vessel_network.py`, the review/playtest tools, both network verification tools, and the environment asset README from `5184282`. Source comparison confirmed an exact checkpoint match (normalizing Windows line endings). No unrelated game systems, artwork, saves, or prior evidence deletions were reverted.

Fresh desktop captures in `TEMP/shimmer-restored/` match this folder's original `after-dim.png`, `after-rising.png`, and `after-peak.png` pixel-for-pixel. Six geometry tests and seven desktop network integration tests passed, covering asynchronous illumination, cache reuse, camera anchoring, palette coverage, and layout preservation after wall destruction/save resume. Project instructions now designate this version as the baseline for the next refinement. Restoration is left uncommitted.

The current direction is native desktop only. The user's latest palette decision supersedes the older cyan Region 04 requirement: Wind is cyan-blue, Forest purple, Fire red, and Stone pale gold/yellow. These preferences are saved in the root `AGENTS.md` for future work.

## Checkpoint and scope

Work continued on `main` from `d7ecf82`, without resetting history. The ancestry is `5d8cc16` → `4b0be8f` → `8ee35ad` → `0aa3e05` → `d7ecf82`. The new checkpoint containing this report is an additive child of `d7ecf82`.

The topology generator, deterministic seeds, obstacle handling, world alignment, breathing periods/phases, and cached native-format node blending were already implemented and retained. No walls, platform artwork, background, actors, gameplay rules, or saves were changed. The pre-existing deletion of `docs/evidence/region04-palette/live-camera.webp` is intentionally excluded from this checkpoint.

## Changes in this pass

- Updated all four network palettes. Stone retains the internal `Bastion of Stone` / `Mountain` identifiers.
- Reduced ordinary trunk/secondary/capillary illumination, while selectively brightening short existing curve sections near major hubs. Most sections remain subdued.
- Added tiny stationary glint centers and sparse ambient fringes to major nodes. All accents are baked into existing cached surfaces; animation still changes opacity only.
- Captured the current colors, full breathing cycle, and desktop combat; updated palette and geometry-preservation checks.

Production changes are confined to `zgame/neural_environment.py`. Supporting changes are `tools/review_region04_illumination.py`, `tools/verify_environment_runtime.py`, `AGENTS.md`, `assets/sprites/environment/README.md`, the evidence index, the historical palette report annotation, this report, and `docs/evidence/region04-shimmer/`.

## Visual evidence

[Four palettes in the actual renderer](evidence/region04-shimmer/biome-palettes.png).

Identical seed 41 and camera: [before dim](evidence/region04-shimmer/before-dim.png), [before intermediate](evidence/region04-shimmer/before-rising.png), [before peak](evidence/region04-shimmer/before-peak.png); [current dim](evidence/region04-shimmer/after-dim.png), [current intermediate](evidence/region04-shimmer/after-rising.png), [current peak](evidence/region04-shimmer/after-peak.png). The baseline uses the previous cyan Stone palette; the current images intentionally use gold.

The [eight-second breathing capture](evidence/region04-shimmer/breathing.webp) contains 80 actual renderer frames at 100 ms intervals. The selected vessel group has a 6.045-second period; stills use 3022, 4534, and 6045 ms. Other groups retain independent phases, so “dim” does not mean every light is dim simultaneously. Geometry matches the checkpoint.

[Node pixel measurements](evidence/region04-shimmer/breathing-metrics.json) show a full rise and fall: the visible node at (400, 620) ranges from RGB sum 373 to 726, with its minimum near 3922–4022 ms; (659, 378) ranges from 366 to 726 with a minimum at 4222 ms; (1033, 652) ranges from 410 to 726 with a minimum at 5722 ms. These are screen-pixel sums, not calibrated luminance. Occluded node positions remain nearly flat, as expected. Stills show concentrated hot centers and quieter surrounding vessels. The clip is provided for final perceptual review; numerical variation alone does not establish aesthetic acceptance.

## Desktop measurements

Paired, alternating native-renderer samples at 1280×720, 80 warm samples per scene/version, same seed and camera path. Dense here means 72 static actors. SDL uses the dummy display driver: these are rendering costs, not measured window-refresh FPS or full simulation-loop time.

| Scene | Before render mean | Current render mean | Before network mean | Current network mean |
| --- | ---: | ---: | ---: | ---: |
| Still | 17.568 ms | 17.500 ms | 2.371 ms | 2.327 ms |
| Moving camera | 19.125 ms | 19.189 ms | 2.306 ms | 2.235 ms |
| 72 static actors | 20.490 ms | 20.644 ms | 2.343 ms | 2.306 ms |

The small differences are within ordinary timing variation; this is not evidence of a meaningful speedup. Current dense render p95 is 22.335 ms, network p95 2.803 ms. Current dense background rendering is 15.552 ms, including the network and approximately 10.479 ms of abyss drawing; actors account for 3.402 ms, including 2.080 ms of walls. Nested measurements must not be summed. The recorded floor-build counter is retained state, not a new build every sample. The initial cold frame is 735.726 ms versus 659.379 ms before, and remains a startup limitation.

The fresh real level-loop test passed 565 frames with up to 72 enemies, camera movement, beam/Procession effects, and a nearby wall destroyed by two real projectile hits. Network topology remained identical on every update; initial obstacle coverage was preserved. [Combat capture](evidence/region04-shimmer/live-combat.png), [results](evidence/region04-shimmer/live-validation.json).

Across 545 warm live-combat renders, network mean/p95 was 1.585/2.235 ms and total render mean/p95 was 29.791/37.072 ms. Background mean was 20.726 ms. This moving edge-of-map fight differs from the paired static scene and is reported separately. Simulation used fixed 1/60 steps; these figures are not whole-loop FPS. A steady 60 FPS desktop target is **not verified**. Remaining dominant costs are outside the network, principally environment/background drawing; they were not changed in this scoped rendering pass.

## Six-item status

| Requirement | Current assessment |
| --- | --- |
| 1. Smooth, continuous vessels | Completed and visually verified in the fixed desktop captures; existing geometry retained. |
| 2. Varied widths, brightness, curvature | Rendering refinement implemented; palette separation, selective nodes, dim branches visible in captures. Final artistic acceptance remains open. |
| 3. Natural fading endpoints | Completed and visually verified in captures; existing taper retained. |
| 4. Smooth asynchronous breathing | Implemented and measured through a full cycle; animation supplied for final perceptual validation. Not closed solely on numeric tests. |
| 5. Ground alignment and occlusion | Desktop regression verified: camera/alignment checks plus fresh moving combat and wall destruction. |
| 6. Deterministic seeds and desktop performance | Partially verified: seeds 12, 41, 98, 337, 901 pass locality/geometry checks; network overhead remains low, but total desktop rendering still exceeds the 16.67 ms budget in representative scenes. |

Five focused tests passed after the final palette mapping: visible dim-to-peak energy, recoloring without coverage changes, sparse highlights across five seeds, cache reuse during animation/camera movement, and world anchoring. Earlier in this same pass, seven checks also covered transparency/local breathing and random-layout renderer parity. Automated checks do not close the outstanding visual acceptance or whole-frame performance requirements.
