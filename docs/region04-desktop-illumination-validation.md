# Region 04 desktop neural illumination validation

> Historical validation record. Superseded media were removed during the palette cleanup; recover those files from checkpoint `0aa3e05`. Current retained captures and measurements are indexed in `evidence/README.md` (archived).

Validated 2026-10-22. Scope: native desktop ground-network illumination. Browser work is deferred.

The cyan-blue network now has visible, asynchronous illumination changes while preserving the existing vessel layout. Checklist items 1–5 are verified against rendered evidence and runtime checks. Item 6 remains partial: network rendering is inexpensive, but the complete scene does not meet the desktop 60 FPS budget. The remaining measured cost is primarily the existing background/environment composition.

## Checkpoint state and preserved work

The inspected branch is `main`. History is linear: `5d8cc16` → `4b0be8f` → `8ee35ad`. The working tree was clean at this final review. No checkout, reset, amendment, merge, or publication was performed. The implementation is saved in `4b0be8f`; the additional desktop evidence, instrumentation, and validation are saved in `8ee35ad`. This report is an additive documentation checkpoint on top of those commits.

The continuation's reported work was already present: longer breathing cycles, cyan Region 04, brighter junctions, cached-node blending optimization, and the 72-enemy validation. Those changes were preserved rather than reimplemented. The outstanding work here was to review the three existing visual states, reconcile the performance results with the actual desktop target, and record an honest checklist.

## Root causes and current behavior

Previously, animated alpha varied only from 155 to 245, with a high minimum and a small range. The outer glow was then attenuated by low source alpha, branch strength, and the floor beneath it. The visible change was weak. Region 04 also deliberately selected the old Mountain gold palette; that color was not a blending defect.

The saved implementation keeps a faint static vessel base and modulates cached inner light and glow separately. Connected phase groups have periods of 4.3–6.7 seconds, different amplitudes, and different phases. Secondary and capillary illumination use 52% and 36% hierarchy weights. Major junctions have a stronger compact center. Region 04 uses cyan-blue `(48, 155, 225)`; other region palettes are unchanged. Only illumination changes over time, not geometry.

The measured desktop node bottleneck came from cached PNG surface channel format taking a slow alpha-blending path. Converting the cached node surface to display alpha format once preserved its pixels and reduced node compositing from roughly 6.8 ms to 0.6 ms. That completed optimization was not repeated in this final review.

## Visual evidence

All images below use the actual game renderer at 1280×720, seed 41, the same layout and camera `(-671, 465)`. The central primary vessel near screen point `(878, 375)` has a 6.045-second period. Labels describe that group's phase; other groups remain asynchronous.

| State | Real animation time | Previous renderer | Current renderer |
|---|---:|---|---|
| Dim | 3022 ms | `evidence/region04-illumination/before-dim.png` (archived) | `evidence/region04-illumination/after-dim.png` (archived) |
| Intermediate | 4534 ms | `evidence/region04-illumination/before-rising.png` (archived) | `evidence/region04-illumination/after-rising.png` (archived) |
| Peak | 6045 ms | `evidence/region04-illumination/before-peak.png` (archived) | [Peak](evidence/region04-illumination/after-peak.png) |

`evidence/region04-illumination/breathing.webp` (archived): 80 frames sampled every 100 ms, eight seconds, one play to avoid a false discontinuity between unrelated periods. `evidence/region04-illumination/live-combat.png` (archived) and `evidence/region04-illumination/live-camera.webp` (archived) show the effect with actual actors and effects. The latter is a condensed gameplay capture, not a timing reference for the breathing period.

Visual review confirms the dim base remains visible; the central vessel and junctions become noticeably brighter at peak; other groups change in different directions at the same times. Cyan illumination remains subordinate to the player and combat. Curved branching, tapering terminals, darker spaces, and obstacle occlusion remain intact. This validates the requested network behavior, not pixel-for-pixel equivalence to the concept painting or final user aesthetic approval.

## Desktop performance

Paired tests used the same seed, camera trajectories, 1280×720 viewport, and native Pygame renderer, alternating before/after order with 80 warm samples per scene. The comparison baseline is `5d8cc16`. Values are mean / p95 milliseconds.

| Scene | Before complete render | After complete render | Before network | After network |
|---|---:|---:|---:|---:|
| Fixed camera, 6 enemies | 23.569 / 29.211 | 17.472 / 23.017 | 8.475 / 9.071 | 2.392 / 2.954 |
| Moving camera, 6 enemies | 24.996 / 26.423 | 18.865 / 20.042 | 8.273 / 8.755 | 2.223 / 2.752 |
| Moving camera, 72 static actors | 26.210 / 27.487 | 20.061 / 21.623 | 8.333 / 8.949 | 2.236 / 2.623 |

Separate actual level-loop combat ran 565 frames with 72 enemies, overlapping player/enemy effects, and camera movement. Its 545 warm render samples measured:

| Component | Mean ms | p95 ms |
|---|---:|---:|
| Complete render | 27.977 | 33.458 |
| Neural network, inclusive | 1.474 | 1.923 |
| Network glow composite | 0.507 | 0.704 |
| Network node composite | 0.395 | 0.528 |
| Background/environment, inclusive | 19.803 | 21.542 |
| Actors including walls | 1.759 | 2.864 |
| Walls | 0.678 | 1.290 |
| Effects pass | 0.040 | 0.093 |
| UI | 0.419 | 0.519 |

Some effects are drawn in actor/other passes; the effects-pass number is not the entire cost of every combat effect. Inclusive categories overlap and must not be added as disjoint costs.

The paired profile isolates abyss composition at about 9–10 ms, versus about 2.2 ms for the network. That existing environment rendering is the principal remaining measured bottleneck. It was left unchanged to respect scope. The desktop loop targets 60 FPS (`zgame/app_flow.py`), a 16.67 ms budget; even render-only timings exceed that budget. No claim of stable 60 FPS is made.

These are actual native renderer measurements using SDL's dummy display, not OS presentation or complete update-plus-display FPS. Simulation in the live fixture uses fixed 1/60 dt. Screenshot encoding is excluded from render samples. Cold material/scene construction still costs about 885 ms in the after fixture; topology was already loaded for scene selection, so this is not a full startup or generation benchmark. Network geometry and materials are reused during steady-state animation.

Raw evidence: [paired profile](evidence/region04-illumination/desktop-profile.json), [live profile](evidence/region04-illumination/live-validation.json), [capture metadata](evidence/region04-illumination/capture-times.json). Browser performance and its previously reported slow frame remain unvalidated here.

## Gameplay and regression evidence

Six vessel tests and seven selected environment-runtime tests passed. They cover deterministic geometry, varied breathing periods, transparent phase batching, unchanged caches during animation/movement, camera translation, five random seeds, wall destruction, and actual save/resume behavior. Native tests of alternate blend paths do not constitute browser validation.

The live level-loop test passed with 72 enemies and overlapping beam/Procession effects. Two real projectile updates destroyed the nearby fragile wall at `(24, 18)`. The initial obstacle footprint remained preserved for network generation, and network geometry identity stayed unchanged on every update. The fixed-camera fixture's topology also equals the `5d8cc16` generator output. Visual captures show the network beneath walls and actors.

## Six-item checklist

| Item | Status | Evidence and limits |
|---|---|---|
| 1. Continuous naturally curved vessels | Completed and visually verified | Existing smooth branching preserved; reviewed fixed and combat captures. |
| 2. Varied width, brightness, length, curvature | Completed and visually verified | Existing geometry retained; primary/secondary hierarchy and varying illumination visible. |
| 3. Naturally fading endpoints | Completed and visually verified | Existing tapered terminals retained and visible; no unnecessary new branches. |
| 4. Smooth asynchronous breathing | Completed and visually verified | Real-time eight-second fixed-camera sequence plus dim/intermediate/peak frames; faint base persists; groups use different periods/phases. |
| 5. Ground alignment during movement | Completed and visually verified | Moving-camera combat evidence, translation tests, obstacle occlusion, and unchanged topology through destruction/save-resume. |
| 6. Multiple seeds and acceptable performance | Partially implemented | Five seeds validated and native network overhead reduced. Complete scene misses 60 FPS; existing environment cost remains unresolved. OS presentation and browser performance are not verified. |

Items 1, 3, and 5 were established before this illumination refinement. Items 2 and 4 required the saved illumination changes; this final continuation reviewed their existing evidence. Item 6 remains open rather than being marked complete because tests passed.

## Exact files changed since 5d8cc16

Runtime: `zgame/neural_environment.py`, `zgame/vessel_network.py`.

Tools/tests: `tools/review_region04_illumination.py`, `tools/playtest_region04_illumination.py`, `tools/verify_environment_runtime.py`, `tools/verify_vessel_network.py`.

Documentation: `assets/sprites/environment/README.md`, this report.

Evidence in `docs/evidence/region04-illumination/`: `before-dim.png`, `before-rising.png`, `before-peak.png`, `after-dim.png`, `after-rising.png`, `after-peak.png`, `breathing.webp`, `capture-times.json`, `desktop-profile.json`, `live-combat.png`, `live-camera.webp`, `live-validation.json`.

No platform, wall, background, character, or boss artwork was regenerated. No unrelated mechanics or UI were modified. The final review added this report only; all saved implementation and evidence checkpoints remain recoverable.
