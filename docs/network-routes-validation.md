# Desktop ground-network geometry refinement

Continued from `5184282` on the existing working tree. This pass changes the network generator and its rendering only. The user's latest request explicitly supersedes the earlier geometry freeze. The agreed biome mapping remains Wind cyan-blue, Forest purple, Fire red, Stone pale gold/yellow; the alternative presets in the pasted brief were not substituted after the user confirmed this choice.

## What changed

The old generator promoted individual short edges to trunk status. Each edge had independent curvature and width variation, and the node atlas added decorative tendrils unrelated to the connections. This produced repeated little junction motifs and weak large-scale flow.

The new generator assembles the seeded, obstacle-aware graph into long cubic routes. Adjacent segments share tangents and a continuous width/brightness envelope. A few sparse reconnections create broader connections without a uniform mesh. On a 36-cell map, four spatially separated routes receive primary emphasis. Secondary routes and irregular tangent offshoots supply finer branches; branch depth stops at three. Graph leaves and terminal offshoots fade. Blocked areas still constrain routes and can separate pockets.

Node textures are restricted to the local soma; their unrelated curly filaments are removed at render-cache construction. Selected major junctions retain hot glints and restrained halos. The existing static base and asynchronous 4.3–6.7-second breathing remain. Wind now uses a colder blue base/inner energy treatment, while the other biome palettes retain their confirmed colors. All palettes share the same generator.

Long curves initially cost more to composite because their bounding images contained substantial transparent space. Nonoverlapping cropped patches now remove this waste before the existing phase batching. A pixel comparison at three opacity levels verifies that this optimization adds no seams and changes no rendered pixels.

## Actual desktop captures

Same floor, walls, camera, map seed, and gameplay state:

- [Before](evidence/network-routes/before-peak.png) / [after](evidence/network-routes/after-peak.png).
- Current Wind: [dim](evidence/network-routes/after-dim.png), [intermediate](evidence/network-routes/after-rising.png), [peak](evidence/network-routes/after-peak.png).
- [Eight-second breathing capture](evidence/network-routes/breathing.webp), [pixel measurements](evidence/network-routes/breathing-metrics.json), [timing metadata](evidence/network-routes/capture-times.json).
- [Four agreed biome palettes](evidence/network-routes/biome-palettes.png).
- Five actual seeded layouts: [12](evidence/network-routes/seed-12.png), [41](evidence/network-routes/seed-41.png), [98](evidence/network-routes/seed-98.png), [337](evidence/network-routes/seed-337.png), [901](evidence/network-routes/seed-901.png).
- [Wind combat](evidence/network-routes/live-combat.png) and [live regression results](evidence/network-routes/live-validation.json).

The comparison uses map seed 41, network seed 1521970205, and camera (-671, 465). The chosen central route group has a 5.959-second period; captures use 745, 2235, and 3725 ms. Other groups remain asynchronous. Node (100, 340) ranges from RGB sum 334 to 723 over the clip; node (778, 366) ranges from 272 to 723; their minima occur at different times. These are screen-pixel sums, not calibrated luminance. This demonstrates temporal variation, not automatic artistic approval.

The five seeded captures show 3–4 major routes intersecting the viewport. Most route widths fall within the requested 384–896 px band at a 1280 px viewport. Seed 337 has narrower 283/352 px routes because of orientation and obstacles. Camera position and level size can change the visible count; it is not enforced by moving the network with the camera. One-time generation was approximately 110–117 ms for these layouts. See [seed measurements](evidence/network-routes/seed-metrics.json).

## Validation and performance

Six geometry tests and eight focused desktop integration checks passed. They cover five deterministic seeds, global coverage, longer routes, tangent continuity, three-level branching, tapering, width continuity, obstacle avoidance, combat-RNG isolation, smooth asynchronous alpha, cache reuse, palette coverage, exact cropped-cache pixels, camera alignment, and save/resume after wall destruction. Test logs are included beside the captures.

Fresh actual level-loop validation completed 565 frames with up to 72 enemies, Wind effects, camera movement, summon effects and real projectile wall destruction. Two projectile hits removed wall (24, 18); network topology stayed identical on every update. No player save was loaded or overwritten.

Paired native renderer timings, 1280×720, 80 warm samples per version/scene, alternating order:

| Scene | Before total render | Current total render | Before network | Current network |
| --- | ---: | ---: | ---: | ---: |
| Still | 17.448 ms | 16.866 ms | 2.337 ms | 1.772 ms |
| Moving camera | 18.748 ms | 18.051 ms | 2.220 ms | 1.556 ms |
| 72 static actors | 20.068 ms | 19.267 ms | 2.202 ms | 1.566 ms |

Current dense network p95 is 1.917 ms; total-render p95 is 20.618 ms. Initial cold render is 511.684 ms versus 723.909 ms before. In the separate moving live-combat test, network mean/p95 is 0.927/1.325 ms and total render is 29.014/35.341 ms, with background drawing averaging 18.802 ms. These different scenarios must not be treated as a single direct comparison.

These captures and timings use native Pygame with SDL's dummy display. They exercise production drawing and the real combat loop, but do not measure window presentation or whole-loop FPS. Steady 60 FPS remains unverified; environment/background work is still the dominant measured cost. No unrelated environment optimization was introduced. [Full paired profile](evidence/network-routes/desktop-profile.json).

## Six-item checklist

| Requirement | Assessment |
| --- | --- |
| 1. Smooth, continuous vessels | Implemented; connected routes and tangent offshoots verified. Full concept-style acceptance remains a visual judgment. |
| 2. Varied thickness, brightness, length and curvature | Implemented and tested; fine-branch distribution and final resemblance still need user review. Narrower-than-target routes occur in one seeded view. |
| 3. Natural fading endpoints | Verified in geometry tests and captures; both graph leaves and small terminal branches taper. |
| 4. Smooth asynchronous breathing | Full cycle captured and measured, with static geometry and independent phases. Final gameplay-scale perceptual approval remains open. |
| 5. Ground alignment and occlusion | Verified by camera pixel checks, obstacle tests, actual movement and wall destruction. |
| 6. Seeds and runtime behavior | Five seeds and cache behavior verified; network rendering improved. Total desktop frame budget remains unresolved. |

## Exact changed files

- `zgame/vessel_network.py` — route assembly, hierarchy, tangents and terminal fades.
- `zgame/neural_environment.py` — cropped cache patches, local soma mask, base visibility, hierarchy and Wind colors.
- `tools/verify_vessel_network.py` — new route-scale/coverage/depth/width expectations.
- `tools/verify_environment_runtime.py` — exact-pixel long-cache regression check.
- `tools/review_region04_illumination.py` — genuine baseline geometry binding, Wind/region selection, five seeded captures and metrics.
- `tools/playtest_region04_illumination.py` — configurable desktop review region.
- `AGENTS.md` and `assets/sprites/environment/README.md` — updated geometry direction and implementation notes.
- `docs/evidence/README.md`, this report, and `docs/evidence/network-routes/` — current evidence and measured limitations.

The pre-existing deletion of `docs/evidence/region04-palette/live-camera.webp` remains outside this change. No platform, wall, cliff, background, enemy, boss, gameplay UI, or save data was edited.
