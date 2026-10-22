# Active neural-world artwork

This directory contains the environment art and the reference-derived asset inventory.

| File | Role |
| --- | --- |
| `neural-stone-v1.png` | Illustrated mineral cortex; retains its source detail at runtime |
| `neural-parts-v2/` | Seven active wall cutouts, four active neural nodes, and five optional extracted motifs; see its manifest |
| `neural-walls.png` | Previous two-cutout wall atlas, retained as the missing-asset fallback |
| `neural-abyss.png` | Shared distant dendritic world, rendered with slow camera parallax outside the platform |
| `neural-cliff.png` | Alpha cliff strip with hanging fibers and peripheral growth |

The animated network uses continuous world-space splines in `zgame/vessel_network.py`.
Long meandering arteries connect through offset, tangent-matched Y junctions.
Tributaries and fine forks taper; illustrated somas sit at actual junctions.
The renderer caches variable-width ribbons, with per-curve supersampling only
during construction. Breathing changes cached alpha; small pulses follow the
actual curves. Camera motion does not rebuild network geometry or textures.
Wind, Forest, Fire and Mountain change only network palette, branch treatment
and breathing timing; legacy save/gameplay identifiers remain.

Wall cutouts are anchored to the same one-cell collision footprint. Coordinate-stable low/medium/full/tall variants use 50%,
78%, 100% and 118% of the 109-pixel base, with endpoint/corner adjustments and
selective luminous buds. Decorative roots may overhang that footprint.
Cliff art never changes collision or pathfinding. The backdrop is visible when
the camera sees past the platform; interior combat views remain open floor. The far painting follows 14% of camera
displacement; dimmed existing cliff cutouts follow 40%, haze 24%, and the rim
100%. Cached illumination/haze overlays add subtle idle motion. Stationary
background compositions refresh at 10 Hz; camera movement updates immediately.

The October 21 asset integration derived transparent production cutouts from
the user's flattened `map01`, `map02`, `network01`, and `nw02` sheets using
the built-in image tool. These are reconstructed reference-based assets, not
pixel-exact removals of the original sheet backgrounds. The sixteen parts
were then losslessly sliced with `tools/slice_neural_assets.py`. Exact prompts,
source hashes, atlas rectangles, and active/optional usage are recorded in
`neural-parts-v2/manifest.json`. Source-folder paths are provenance only; all
runtime assets are included here and in both web bundles.

The original abyss, cliff, and two-wall atlas were generated with the built-in
image tool using the approved Balanced World reference. Their exact prompts
are in `generation-prompts.json`.
The earlier v1/v2 wall sheets and superseded environment captures were removed
from the active checkout for clarity; they remain recoverable in commit `35a3943`.
This does not remove the current neural-stone-v1 source.
