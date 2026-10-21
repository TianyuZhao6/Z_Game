# Neural-world reference refinement

The target is the user's **Image 1 / Balanced World**: mineral cortex, branching
signals, thick rooted ruins, open combat space, and a large lavender neural abyss.
This revision replaces the previous environment validation sheet as the current
art review. It is an implemented art pass for review, not a claim of exact visual
identity with the hand-composed concept.

## In-game changes

- Removed the upper-right region badge from desktop and lightweight rendering.
- Restored the illustrated floor's plate boundaries and varied stone sizes.
  The earlier tiny intermediate image and heavy dark veil hid those details.
- Replaced the coarse network with curved axons, secondary dendrites and tiny
  forks. Soft halos, a 5.6–9.2 second breathing cycle, and independently phased
  synapses animate above the static surface. Art randomness stays separate from
  gameplay randomness.
- Reworked the preferred v1 wall material into tile-shaped cutouts, preserving
  roots and small synaptic buds. The stone cap and vertical extrusion are mapped
  separately, so adjacent 2:1 caps join without compressing a long panel into a
  thin fence. The collision footprint remains unchanged; decorative
  roots may extend beyond the footprint. Pale cracked walls are breakable; dark
  intact walls are permanent.
- Added a shared illustrated abyss with camera-relative parallax and hanging cliff
  fibers at the platform rim. It becomes visible when the camera reaches an edge;
  the center remains a continuous playable floor. Fully covered backgrounds are
  skipped and opaque floor interiors avoid unnecessary alpha compositing.
- New maps use 6.5% baseline obstacle coverage instead of 14%, with short wall
  runs and a consistent material within each run. Remainder blocks form more
  runs instead of scattered single pillars. Existing level-requested obstacle
  minimums still apply. **Saved maps retain their existing layout; start a new
  run to assess the new generation.**

Wind / 风 remains silver-blue; Forest / 林 jade; Fire / 火 ember; Mountain / 山
muted gold. These differences belong to the ground network. Fog, wind hazards,
fire trails, shields, Eidolon forms, Procession, beam, controls, progression,
economy and legacy save identifiers are preserved.

## Wall variety and living-background follow-up

The wall-run remainder correction was already present when this follow-up began;
it was preserved without further generator edits. Ground artwork, breathing
networks, region effects and combat systems were also retained.

Existing wall cutouts now supply four spatial height families: 50%, 78%, 100%
and 118% of the original 109-pixel extrusion. Endpoints are slightly lower;
corners rise slightly. Cap notches and mirrored orientations break repetition.
Most blocks suppress bright buds; selected blocks retain the small luminous
plants. The cap keeps its original tile proportions independently of body height.
Solid and fragile materials and their damage states still use the existing atlas.

Selection is derived at render time from grid coordinates and neighbor topology,
not a new saved random value. Nearby coordinates share a height family. Loading
a saved map or iterating its walls in another order cannot reroll the artwork.
Destroying a neighbor can expose an endpoint, but preserves the height family.

The existing abyss illustration now moves at 14% of the camera displacement,
without the previous saturating offset. Reused, dimmed cliff cutouts form a
middle layer at 40%; haze follows at 24%; the actual platform rim and hanging
roots remain anchored to world coordinates at 100%. The far image is oversized
to cover the complete playable camera range without tiling or reset. Hidden
backgrounds are still skipped in interior views, and static art remains cached.
When the camera rests, the composed abyss is cached between ten-per-second
atmosphere updates. Every camera change invalidates it immediately, so parallax
motion is not throttled. Wall-bud suppression uses native mask/blend operations
to avoid Python per-pixel work when new or damaged variants enter the cache.
A 13-second illumination cycle and slow drifting haze supply restrained idle
motion. Hanging roots are not independently animated in this pass.

In the actual native edge capture pair, the camera moved (+146,+247) pixels.
The far background consequently moves approximately (-20,-35), the middle
formations (-58,-99), and the platform (-146,-247). Integer raster placement
introduces at most a one-pixel rounding step. The player moved using normal
movement/collision handling; the captures were not manually repositioned.

## Review evidence

| File in `docs/evidence/` | What it demonstrates |
| --- | --- |
| `neural-refined-abyss.png` | Real renderer at the edge of a generated map: backdrop, cliff, wall volume and network |
| `neural-refined-center.png` | The same generated map's open central area |
| `neural-refined-breathing.webp` | Captured 6.4-second frame sequence showing network/synapse breathing |
| `neural-refined-combat.png` | Actual dense level-loop combat with the Eidolon and existing abilities |
| `neural-parallax-a.png`, `neural-parallax-b.png` | Actual edge gameplay before and after camera movement |
| `neural-parallax-motion.webp` | Eight-second actual gameplay sequence, sampled at four frames/second |
| `neural-parallax-motion.json` | Camera and player coordinates for the comparison pair |

The first two review views use controlled actor positions and no enemies/items
to inspect the artwork. They use normal generated collision geometry and the
actual renderer, not a painted replacement screenshot. The separate combat
capture comes from the running level loop. Use
`python tools/preview_environment.py --reference-review` to reproduce the art
views, or `python tools/playtest_summon.py --environment-stress` for combat.
Use `python tools/playtest_summon.py --edge-motion` for the moving edge captures.
The movement fixture starts near an edge; all subsequent movement, wall collision,
enemies, projectiles, companion AI and rendering run through the normal level loop.

## Verification

- All **67 summon/render tests** and **13 environment tests** pass.
- Bullet (9) and game-state (13) scenario suites pass.
- Five generated layouts remain connected; camera depth, tall-wall occlusion,
  wall damage/removal, transparency, network animation, floor/backdrop parity,
  four region treatments and legacy saves are covered. New checks verify
  deterministic height/decoration diversity, fewer than 15% isolated blocks on
  each of five maps, actual layer-blit displacement, idle background motion, and
  backdrop coverage at all platform corners at 1280×720 and 1920×1080.
- Both native and lightweight edge-movement scenarios pass, 565 frames each.
  Horizontal, vertical and diagonal input, actual camera displacement, and
  companion movement/attacks are checked.
- All four dense live level-loop scenarios pass: 565 frames each with 69–72
  enemies, real movement, combat, hazards and the existing summon abilities.
- The web bundle is rebuilt, with the four active environment images verified
  byte-for-byte against the source. Old wall atlases are absent from the bundle.
- Actual Chrome runs complete without Python/JavaScript runtime errors in Wind,
  Forest, and a longer Wind run receiving six horizontal/vertical/diagonal WASD
  phases. Browser results are saved in
  `evidence/neural-refined-browser-validation.json`.
- Final headless frame timings: Wind 89.397 ms average / 118.815 ms p95;
  Forest 84.037 / 82.795 ms; longer moving Wind 117.933 / 143.760 ms.
  These are slower than the earlier 44.73 / 56.019 ms average Wind/Forest
  measurements. Native mask operations reduced cold wall-variant stalls, and
  stationary background composition now caches, but a browser performance
  parity claim is **not** supported. Smooth browser frame pacing remains an
  unresolved limitation; these tests are functional validation, not a 60 FPS
  performance pass. Runs are not an isolated hardware-controlled benchmark.

The new silhouette families improve variation, but roots and cap rhythms still
repeat within formations. This is an asset-reuse pass, not bespoke rock sculpting.
The map is still procedurally generated and walls remain modular; its composition
will vary from Image 1. Dense effects and damage numbers can temporarily cover
the player, as before. Headless browser timings are diagnostic, not a 60 FPS
guarantee or a substitute for manual visual approval.

## Asset cleanup and provenance

The active set is documented in
`assets/sprites/environment/README.md`. The built-in image tool generated the
abyss, cliff and corrected wall cutouts from the approved reference; the original
v1 wall sheet also served as the wall material reference. Exact prompts are in
`assets/sprites/environment/generation-prompts.json`.

Removed the unused v1/v2 wall atlases, old environment-only screenshots, old
browser summary and superseded validation document from the active checkout.
They remain recoverable in checkpoint `35a3943`. Other feature evidence, existing
saves, and previous commits were preserved. No publication or deployment.

## Final checkpoint review — 2026-10-21

The continuation reused the completed captures, 67 summon checks, four dense
combat scenarios, edge-movement runs and six-phase Chrome input run. Only the
13 affected environment checks were rerun after the focused rendering change;
all passed. The final direct/cached paths produce identical pixels, so existing
captures remain representative. No new art or gameplay changes were introduced.

A matched render-only fixture (`tools/benchmark_environment_render.py`) compared
1280×720/full quality, seed 947, 84 walls, six enemies and one Eidolon. Each scene
has nine warmup frames and 60 measured frames. Animation times/camera steps are
identical; there is no screenshot recording or gameplay profiler. Native uses
SDL's dummy/software display; browser tests use headless Chrome. GPU-allowed
means the disabling flag was omitted, not proof of hardware acceleration.

| Scene | Native after (ms) | Chrome software before → after (ms) | Chrome GPU allowed after (ms) |
| --- | ---: | ---: | ---: |
| Center | 15.727 | 49.812 → 47.965 | 47.543 |
| Stationary edge | 16.865 | 51.222 → 49.168 | 49.653 |
| Moving edge | 29.765 | 77.795 → 71.790 | 70.210 |
| Forest fog | 18.341 | 74.488 → 71.215 | 70.317 |

The one focused optimization draws background layers directly on a moving
camera, avoiding a full-screen temporary allocation, format conversion and
extra copy. Stationary composition caching and all depth/illumination remain.
Native moving-edge mean decreased from 33.093 to 29.765 ms. Browser improvement
is modest; ordinary run-to-run timing variation is also present.

This is not solely a cold-cache or recording artifact: warmed render-only Chrome
still takes about 48–72 ms. The earlier live diagnostics' later halves averaged
106.33 ms (Wind) and 76.93 ms (Forest), so their costs were sustained beyond
startup. The fixed scene is lighter than live combat, so their difference cannot
be attributed entirely to profiler overhead. First-frame browser cold setup is
about 1.7–1.8 seconds. Interactive, non-headless FPS has not been established.
Detailed before/after data is in `evidence/neural-performance-review.json`.

The implementation and rebuilt playable bundle are ready for manual testing,
with browser frame pacing and residual modular repetition explicitly retained
as limitations. Previous checkpoints remain available. This checkpoint is named
`neurosurvivor-neural-environment-parallax-wall-variants`; no push or deployment.
