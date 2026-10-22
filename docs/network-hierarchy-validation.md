# Organic network: phase batching and six-point validation

> Historical validation record. Superseded media were removed during the palette cleanup; recover those files from checkpoint `0aa3e05`. Current retained captures and measurements are indexed in `evidence/README.md` (archived).

Checkpoint: `neurosurvivor-organic-network-batched-breathing`.

## Acceptance status

**Five criteria are verified. Criterion 6 is partial: seed coverage and stability
pass, but full browser performance is not yet acceptable.** The measurable
network-layer improvement below must not be confused with whole-game FPS.

| Checklist | Status and evidence |
| --- | --- |
| 1. Continuous, naturally curved vessels | Verified: smooth sampled curves and tangent-attached tributaries; no tile-to-tile line assembly. Attachment direction agreement exceeds 0.995 in the geometry checks. |
| 2. Varied width, brightness, length, curvature | Verified: trunk/secondary/capillary hierarchy, varying radii and intensity, uneven junction placement. See actual-scale branching capture. |
| 3. Branches can terminate or fade | Verified: terminal strengths reach zero and radii taper; some capillaries dim before their ends. |
| 4. Smooth asynchronous breathing | Verified: eight independent phase groups and separately phased nodes; some brighten while others dim. Consecutive 17 ms samples change alpha by at most 3. No traveling dots. |
| 5. Fixed to the ground during camera movement | Verified: pixel-exact translated overlap at two animation times for both regular and SDL2 blending; no material-cache misses during warmed camera motion. |
| 6. Multiple seeds and performant browser/Pygame rendering | **Partial.** Seeds 12, 41, 98, 337, 901 pass across the four regions and renderer paths. Branch drawing is faster on both runtimes, but the complete browser scene remains slow. |

## What was preserved and finished

The map-seeded generator, wall-aware routes, illustrated junctions, natural
fades, immutable initial-wall layout, and save/resume integration were already
implemented when this continuation resumed. They were preserved. The approved
stone, seven wall cutouts, background, collision and gameplay systems were not
redesigned or regenerated.

The earlier fixed-size phase-tile experiment had already been removed after
increasing overdraw. The workspace contained individual stamps and a batched
blit call, but no completed spatial phase grouping. This checkpoint crops those
stamps and merges nearby equal-phase images only when their bounding area stays
within 110% of the members' combined area and within 420 x 280 pixels. Static
art is cached; each frame computes eight opacity values, culls offscreen groups,
and submits visible groups in one C-level blit call. Nodes retain their own phases.

Paired measurements select regular alpha on desktop and SDL2 alpha in WebAssembly.
The regular-alpha path was faster locally but slower in Chrome; that rejected
browser variant is retained only in the reproducible comparison tool.

## Measured performance

`tools/benchmark_network_batches.py` alternates measurement order on the same
geometry, seed 947, 1280 x 720 viewport, with 80 warmed samples per mode. It
compares the previous individual SDL2/RLE branch stamps with the final batches.
It measures **branches only**, excluding floor, nodes, background, actors and UI.

| Runtime / region | Before mean | Final mean | Before / final p95 | Visible draws |
| --- | ---: | ---: | ---: | ---: |
| Chrome, software / Wind | 16.82 ms | 9.69 ms | 17.9 / 10.9 ms | 190 -> 123 |
| Chrome, software / Forest | 16.57 ms | 9.54 ms | 21.2 / 11.8 ms | 226 -> 137 |
| Chrome, GPU allowed / Wind | 17.01 ms | 9.67 ms | 18.7 / 10.5 ms | 190 -> 123 |
| Chrome, GPU allowed / Forest | 19.39 ms | 11.18 ms | 21.7 / 13.1 ms | 226 -> 137 |
| Pygame / Wind | 9.22 ms | 1.57 ms | 14.26 / 3.32 ms | 190 -> 123 |
| Pygame / Forest | 16.06 ms | 3.43 ms | 19.06 / 4.49 ms | 226 -> 137 |

Whole-scene fixed-fixture results **do not establish an overall improvement**.
The earlier unbatched Chrome software means were 79.60 / 73.64 / 94.98 / 103.49 ms
for center / edge / moving edge / Forest. The completed SDL2 batch path measured
99.35 / 79.68 / 106.35 / 140.50 ms (p95 128.4 / 133.2 / 133.4 / 175.0).
These were separate runs with substantial timing variability; the within-run
paired branch comparison is the evidence for the optimization's benefit.
Cold construction still took approximately 4.9 seconds for Wind and 3.4 seconds
for Forest in that browser fixture. No claim of smooth 30/60 FPS is made.

The final playable Chrome movement scenario reported 270 diagnostic frames,
all six movement directions, no Python/JavaScript errors and no dead runtime.
Average frame time was **134.16 ms**, p95 **136.4 ms**, worst hitch **4.28 seconds**.
The combined environment/background render pass averaged **93.04 ms**, remaining
the dominant measured cost. The profiler groups floor, network, rim and backdrop
work together, so it does not justify blaming a single component. Further work
should split that pass before making additional rendering changes.

The dense desktop capture passed 565 real level-loop frames with 72 enemies,
beam and Procession active. Its 43.46-second test duration includes fixture and
screenshot work; it is not a clean dense-combat FPS benchmark.

## Checks and evidence

- Five vessel/asset tests and seven focused environment tests passed. The
  camera test was rerun after adding explicit coverage for both blend paths.
- Save/load testing follows the actual resume function after wall destruction;
  the original layout and seed remain unchanged.
- Earlier 67 passing summon checks were reused; unrelated combat code was not changed.
- Both final playable APK and TAR bundles byte-match 55 runtime/source/image
  files, including the real `main.py`. External Desktop source folders are not
  required. The benchmark runs in separate diagnostic bundles.
- `git diff --check` passes.

All captures below come from the game renderer. The composition previews use a
seeded generated map and controlled review camera/times; the combat capture uses
the running level loop. The animation contains 32 actual frames across 6.4 seconds.

- `evidence/network-hierarchy/refined-center.png` (archived)
- `evidence/network-hierarchy/refined-abyss.png` (archived)
- `evidence/network-hierarchy/refined-branching.png` (archived)
- `evidence/network-hierarchy/refined-breathing.webp` (archived)
- `evidence/network-hierarchy/dense-combat.png` (archived)
- [Raw measured results](evidence/network-hierarchy/performance.json)

Previous checkpoints remain intact. This checkpoint is local; nothing was pushed,
merged or deployed. Visual acceptance against the concept remains the user's
judgment; passing these tests is not a claim of pixel-identical concept art.
