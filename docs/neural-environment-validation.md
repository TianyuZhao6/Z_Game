# Neural environment — validated desktop/browser checkpoint

Validated 2026-10-20. Checkpoint name: `neural-environment-validated-browser-desktop`.
Continues `4e469b9` (Map updated); earlier commits are preserved.

## Preserved baseline

The approved quiet blue-gray floor, independently breathing connected network,
pixelated environment textures, and tall walls remain unchanged. Solid walls use
dark reinforced faces; breakable walls use pale cracked stone. Wall extrusion is
109 pixels (approximately twice the visible player body), with unchanged collision
footprints. Accepted assets are `neural-stone-v1.png` and `neural-walls-v2.png` in
`assets/sprites/environment/`; the earlier v1 wall source remains archived there.
No artwork was regenerated during final validation.

| Region | Ground network | Preserved gameplay / save identifier |
| --- | --- | --- |
| Wind / 风 | Silver-blue flowing paths | Wind hazards; `Domain of Wind` |
| Forest / 林 | Jade branching paths | Forest fog; `Misty Forest` |
| Fire / 火 | Muted ember angular paths | Fire trails; `Scorched Hell` |
| Mountain / 山 | Muted gold rigid paths | Stone shields; `Bastion of Stone` |

The shared environment, random layout generation, three Eidolon forms, eye beam,
Shadow Procession, movement, tornado, Aegis Pulse, progression, timers, shop,
economy and existing save keys are retained.

## Completed work retained from the preceding implementation

- Corrected the stale wall-height assertion and isolated the wall-cache test from
  leaked menu transition state. The latter was a test fixture issue.
- Corrected browser wall sorting to compare camera-relative wall and actor depth.
- Added the diagnostic overlay's document-body startup guard.
- Retained off-screen wall culling, converted/cached surfaces and accelerated
  network compositing. Measured wall rendering fell from about 16 ms to 3–4 ms
  in the earlier browser profile; this is not a 60 FPS guarantee.

## Only new regression correction

The wall sprite RLE acceleration setting made partially transparent edge/shadow
pixels become opaque black when assembled into the lightweight renderer's RGBA
wall cache. Removed that setting from wall sprites only. The optimized direct
blit, culling and network acceleration remain. A new test compares every cached
alpha pixel with its source for both wall types after a direct render, preventing
this regression from returning.

## Validation

| Coverage | Result |
| --- | --- |
| `python tools/verify_summon_runtime.py` | Fresh run: all 67 pass |
| `python tools/verify_environment_runtime.py` | Fresh run: all 8 pass, including transparency regression |
| Bullet / game-state suites | Reused completed results: 9 / 13 scenarios pass |
| Six real level-loop scenarios | Reused: all pass; three forms, movement, beam, Procession, boss and downed resume |
| Four dense region scenarios | Reused: all pass, 69–72 enemies, 565 frames each |
| Affected Forest lightweight loop | Fresh run: pass, 69 enemies, 565 frames |
| Random layouts | Five seeds × four regions × three camera positions, desktop and lightweight rendering |
| Damage / destruction | Real projectiles change wall appearance, invalidate caches, remove destroyed walls and release collision |
| Camera / occlusion | Full browser and desktop sampled wall pixels agree; conditional player marker and below-viewport wall-cap culling pass in all three renderer paths |
| Ground / network | Shared ground parity; network varies with time without changing/rebuilding floor, four distinct treatments, map-wide coverage and boundary clipping |
| Saves | Copy of existing save loaded successfully; four legacy region keys round-trip; source save bytes unchanged |
| Final web bundle | `python -m pygbag --build .` and `python tools/postbuild_web_assets.py` complete |

Previous real headless Chrome runs passed in all four regions with no reported
Python or JavaScript runtime errors. The final rebuilt bundle was checked again
in Forest: runtime alive, 540 observed Python frames, three diagnostic posts,
empty Python/JavaScript errors. Summarized browser evidence is retained beside
this report in `evidence/neural-environment-browser-validation.json`.

## Capture review and remaining limits

- `evidence/neural-environment-wind-beam.png`: retained actual gameplay capture;
  cyan player, red-purple Eidolon and beam remain distinct against restrained
  floor/network detail. Joined modular walls retain readable type differences.
- `evidence/neural-environment-forest-lite.png`: refreshed affected gameplay
  capture after transparency correction. Fog and combat effects remain active;
  wall edges retain alpha and the player/core and Eidolon remain identifiable.

No remaining functional regression was found in the covered scenarios. Dense
combat can still overlap characters with effects and damage numbers; these
existing effects were deliberately preserved. Lightweight compositing and fog
can produce shading differences, so parity does not mean identical full frames.
Headless browser performance remains roughly 37–44 ms average per frame in the
recorded runs (final Forest 44.289 ms), with startup warmup/hitches. This is ready
for manual desktop/browser testing, not a claim of smooth 60 FPS on every device.
No further performance work, publishing or deployment was performed.

Local detailed logs remain in `TEMP/environment-*.log`; browser raw reports are in
`build/diagnostics/neural_environment_final/` and
`build/diagnostics/neural_environment_checkpoint/`. These temporary/build paths
are not required to run the committed project.
