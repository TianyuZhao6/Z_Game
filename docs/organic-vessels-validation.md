# Organic vessels and reference-derived structures — October 21, 2026

> Historical validation record. Superseded media were removed during the palette cleanup; recover those files from checkpoint `0aa3e05`. Current retained captures and measurements are indexed in `evidence/README.md` (archived).

## Delivered implementation

The approved stone floor, abyss/parallax, region identities, map generator,
collision rules, companion designs, and combat effects remain in place.
Six supplied reference sheets were inspected. The flattened sheets were used
to reconstruct transparent production cutouts with the built-in image tool;
these are not claimed to be pixel-exact extractions of their backgrounds.
Sixteen individual PNGs, source hashes, slicing rectangles, exact prompts,
and usage are in `assets/sprites/environment/neural-parts-v2/manifest.json`.
Seven structure cutouts and four node cutouts are actively rendered. Loose
rubble and four short energy motifs remain optional inventory, not collision
objects or pieces spliced together to construct the long vessels.

Long continuous splines, offset Y connections, tangent-matched tributaries,
variable widths, and tapered fine branches replace the old short network
segments. Illustrated nodes sit at real junctions. Cached illumination
breathes, and sparse pulses follow the actual sampled curves. The broad,
quiet spaces between arteries keep the floor readable during combat.

Seven wall forms include dark masonry, three rooted basalt silhouettes, and
three pale cracked masonry profiles. Original one-cell colliders are retained.
A regression test caught a one-pixel anchor mismatch; the new cutouts now use
the existing `1 + wall extrusion` anchor contract. No artwork was regenerated
during final validation.

## Verification

- Four vessel/asset checks: continuous parent attachments, matching tangents,
  tapered branches, curved world-spanning routes, one connected network,
  deterministic art-local randomness, transparent distinct cutouts.
- Fourteen environment checks, including five map seeds (12, 41, 98, 337,
  901), four regions, desktop/full-web/lightweight renderer paths, camera
  positions, platform coverage, parallax, wall depth/alpha, real projectile
  damage/destruction, collision, save/effect compatibility, and animation.
  All seven wall forms occur across the five generated layouts.
- The cache test confirms zero additional network texture, illustrated node,
  or wall sprite cache misses during warmed camera movement and animation.
- All 67 summon regression checks pass, including beams, Procession,
  terrain depth, save/resume, region effects, wall blocking and destruction.
- Actual level-loop stress runs: Wind 72 enemies, Forest lightweight 69,
  Fire 69, Mountain 72; 565 frames each. Procession and beams execute in the
  tier-six fixtures. Existing Tornado/Aegis-enabled fixtures remain active.
- Actual edge movement: native Wind and lightweight Forest, 565 frames each,
  including horizontal, vertical, diagonal movement and the parallax abyss.
- Chrome ran the playable bundle for the 45-second Wind scenario: 540
  reported Python frames, all six WASD movement phases, no Python/JS errors.
  This is a normal browser combat scenario, not the native 72-enemy stress run.
- Both APK and TAR browser bundles were rebuilt and byte-checked against
  the current environment modules, real `main.py`, and all sixteen part PNGs.
  Runtime loading requires no files from the user's Desktop reference folders.

The environment suite passed before the anchor correction; the affected
anchor, wall-depth and alpha tests were rerun after it. The cache and seven-form
checks also passed. Completed tests were not repeatedly run without a change.

## Performance and limitations

Same fixed render fixture as the preceding checkpoint: 1280×720, full quality,
seed 947, 84 walls, six enemies, one Eidolon, 60 warmed frames per scene,
no recording and no game profiler. Prior measurements are the saved preceding
checkpoint results, not a simultaneous A/B run.

| Scene | Previous Chrome software, mean ms | Current Chrome software, mean ms | Current GPU allowed, mean ms |
| --- | ---: | ---: | ---: |
| Center | 47.97 | 53.56 | 54.37 |
| Edge | 49.17 | 52.74 | 52.66 |
| Moving edge | 71.79 | 73.24 | 72.58 |
| Forest | 71.22 | 75.18 | 74.29 |

Current native means were 19.47 / 18.87 / 31.15 / 21.76 ms respectively.
The actual profiled Chrome movement/combat run averaged 72.13 ms, p95 77.92 ms.
Its worst sample was about 3.01 seconds; cold construction and other gameplay
transitions are separate from sustained warmed frame cost.

Initial browser construction is slower: approximately 3.95–4.01 seconds for
the first scene and 2.17–2.18 seconds when the Forest network is first built,
versus approximately 1.7 and 0.18 seconds in the preceding fixture. The warm
cost increase is modest, but the startup/region-construction hitch remains a
known limitation. Geometry caches cover four regions; the large raster cache
retains only the current region to bound memory, so revisiting a region can
rebuild its raster. Camera motion does not invalidate it.

These are headless Chrome measurements. GPU-allowed results were similar, but
this does not establish foreground browser smoothness or a 60-FPS claim.
No art quality, effects, background depth, or gameplay rules were reduced to
improve the benchmark. No repeated per-frame generation/resizing defect was
found; further general browser optimization remains separate work.

## Saved real-renderer evidence

- `evidence/organic-vessels/refined-center.png`: unobstructed central review.
- `evidence/organic-vessels/refined-branching.png`: actual-size branch/node viewport.
- `evidence/organic-vessels/random-map-98.png`: second generated layout and walls.
- `evidence/organic-vessels/refined-abyss.png`: platform edge and shared backdrop.
- `evidence/organic-vessels/dense-combat.png`: real level-loop combat and Procession.
- `evidence/organic-vessels/refined-breathing.webp`: 6.4-second lighting/pulse cycle.
- `evidence/organic-vessels/edge-movement.webp`: actual movement and parallax.

Quiet review frames use controlled camera, actor placement, and time in the
real renderer. Combat/movement captures execute the actual level loop. None
are generated concept paintings. Local raw diagnostics remain in
`build/diagnostics/organic-vessels-browser/` and `organic-vessels-perf/`;
test logs are under `TEMP/organic-vessels-*.log`.

Checkpoint name: `neurosurvivor-organic-vessels-wall-assets-validated`.
The preceding stable checkpoint `c18c24d` and intervening user cleanup
`6d9fad6` remain in Git history. No remote publication is part of this work.
