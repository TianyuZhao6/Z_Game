# Desktop fine-branch refinement — 2026-10-23

**Superseded:** the user subsequently selected `region04-shimmer` (`5184282`) as the preferred baseline. The runtime and validation tools have been restored to that version. The following report describes the former experiment, not the current game.

Baseline: restored checkpoint `f195ad8`, explicitly selected by the user. This is an uncommitted visual candidate. No restored artwork or assets were deleted. Browser work is excluded.

Evidence recovery: after user cleanup removed the review folders, the user requested preserving this code revision and recreating only its latest evidence. Screenshots, animation, seed metrics and paired profiling were regenerated. The successful test logs and live-combat outputs were recovered from surviving temporary files for the same unchanged code. Older deleted evidence folders were not restored.

## What changed

The original network routes and junctions are preserved exactly. A minority of existing secondary vessels now have small clusters of tapering terminal branches. A separate seeded selection chooses these additions; it does not replace the original route generator. The capture fixture adds 38 paths to its original 81 paths. All original paths and junctions also match the baseline across seeds 12, 41, 98, 337, and 901.

Fine strokes previously lost visibility through both fractional-pixel width and low opacity. Their cached rendering now uses greater sampling resolution and a tapered pixel-coverage floor. The new branches remain narrower than the major vessels. Geometry is still fixed during illumination and camera motion.

The palette separates secondary, main-energy and active colors. Wind uses the requested cold Azure hierarchy. Forest remains purple, Fire red, and Stone pale gold/yellow. Major junction centers use small soft highlights instead of hard cross-shaped glints. Existing asynchronous breathing and permanent dim vessel layers remain in place.

## Actual renderer evidence

- [Baseline peak](evidence/network-fine-branches/before-peak.png) / [candidate peak](evidence/network-fine-branches/after-peak.png)
- [Dim](evidence/network-fine-branches/after-dim.png), [intermediate](evidence/network-fine-branches/after-rising.png), [peak](evidence/network-fine-branches/after-peak.png)
- [Eight-second breathing animation](evidence/network-fine-branches/breathing.webp), [node pixel samples](evidence/network-fine-branches/breathing-metrics.json)
- [Four biome palettes](evidence/network-fine-branches/biome-palettes.png)
- [Live combat capture](evidence/network-fine-branches/live-combat.png), [live measurements](evidence/network-fine-branches/live-validation.json)
- [Five-seed comparison](evidence/network-fine-branches/seed-metrics.json), [capture metadata](evidence/network-fine-branches/capture-times.json)

The fixed-camera comparison uses the same scene, palette and timestamps in both versions. Dim/intermediate/peak refer to one selected group's 5.96-second cycle; other groups remain asynchronous. These are game-renderer captures, not concept images. The candidate still needs user visual judgment against the approved artwork; passing tests does not establish an exact visual match.

## Validation and performance

Six geometry tests and eight desktop integration checks passed. The live Wind level-loop run completed 565 frames with 72 enemies and overlapping effects. Two real projectile hits destroyed a nearby wall; the initial network blockers and topology remained stable through every update. See [geometry results](evidence/network-fine-branches/geometry-tests.txt) and [desktop results](evidence/network-fine-branches/desktop-tests.txt).

Paired desktop measurements at 1280 × 720 used 80 warm samples, alternating baseline and candidate. Times are milliseconds; they measure rendering, not operating-system presentation or whole-loop FPS.

| Scene | Baseline render mean / p95 | Candidate render mean / p95 | Baseline network mean | Candidate network mean |
| --- | --- | --- | --- | --- |
| Fixed camera | 23.269 / 42.227 | 22.710 / 41.181 | 2.646 | 2.683 |
| Moving camera | 32.685 / 45.242 | 32.334 / 42.161 | 3.573 | 3.648 |
| Dense fixture | 39.700 / 44.254 | 39.650 / 44.527 | 4.280 | 4.441 |

Added network drawing cost is approximately 0.04–0.16 ms in this comparison. Five-seed generation took 130–205 ms and occurs when building the layout cache, not every frame. Both versions measured slower in this recovery run than in the preceding run; the cause was not isolated, and the small total-render differences are not evidence of a speedup. Full measurements: [paired profile](evidence/network-fine-branches/desktop-profile.json).

The separate live combat run averaged 29.136 ms total rendering (p95 35.343 ms). Network rendering averaged 0.950 ms (p95 1.319 ms); floor/background-floor rendering averaged 18.790 ms (p95 21.428 ms), the largest measured component. Whole-game 60 FPS is not verified and remains unresolved. The paired fixture and live run have different scenes and should not be compared as a before/after speedup.

## Six-item status

| Requirement | Verified status |
| --- | --- |
| Smooth, continuous vessels | Original routes preserved; tangent attachment checks pass. Visual match remains subject to review. |
| Varied width, brightness and curvature | Fine branches and color hierarchy refined; screenshots supplied. Final aesthetic acceptance pending. |
| Naturally fading endpoints | Terminal taper/fade checks pass; new branches use the existing endpoint behavior. |
| Smooth asynchronous breathing | Full cycle captured and pixel variation recorded; cache/phase tests pass. Perceptual strength still needs user review. |
| Ground alignment and occlusion | Camera alignment and cache tests pass; live wall destruction leaves topology stable. |
| Deterministic seeds and performance | Five seeds verified, modest measured network overhead. Whole-game frame budget unresolved; desktop only. |

## Files changed

- `zgame/vessel_network.py`: append-only fine branching.
- `zgame/neural_environment.py`: palette roles, fine-stroke coverage, softer node centers.
- `tools/review_region04_illumination.py`: original-route preservation evidence.
- `tools/verify_environment_runtime.py`: exact Wind palette checks.
- `AGENTS.md`: restored-baseline and asset-preservation instructions.
- `assets/sprites/environment/README.md`: rendering and palette documentation.
- `docs/evidence/README.md`, this report and `docs/evidence/network-fine-branches/`: current review evidence.

Platform, walls, backgrounds, actors, boss mechanics, UI and gameplay rules were not changed.
