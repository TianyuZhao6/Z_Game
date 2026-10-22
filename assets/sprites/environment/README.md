# Active neural-world artwork

This directory contains the environment art and the reference-derived asset inventory.

| File | Role |
| --- | --- |
| `neural-stone-v1.png` | Illustrated mineral cortex; retains its source detail at runtime |
| `neural-parts-v2/` | Seven active wall cutouts, four active neural nodes, and five optional extracted motifs; see its manifest |
| `neural-walls.png` | Previous two-cutout wall atlas, retained as the missing-asset fallback |
| `neural-abyss.png` | Shared distant dendritic world, rendered with slow camera parallax outside the platform |
| `neural-cliff.png` | Alpha cliff strip with hanging fibers and peripheral growth |

The animated network uses an unevenly spaced, map-seeded spatial graph in
`zgame/vessel_network.py`. Nearby junctions connect through wall-aware curves.
A minority of routes become thicker trunks; secondary connections feed
tapered, dimming capillaries and split ends. Illustrated somas emphasize the
junction hierarchy. Gentle width/wander variation and local dim interruptions
keep the curves from looking like uniformly painted wires.

The renderer caches tightly bounded branch stamps, with supersampling only
during construction. Nearby stamps share eight independently breathing phase
groups, merged only when the combined bounds stay small. Stone luminance
modulates the light above a subtle dark groove. Groups and individual nodes
breathe on roughly 2.85–4.15 second cycles. Offscreen groups are skipped; visible
groups use one batched blit call, with regular alpha on desktop and the measured
faster SDL2 alpha path in WebAssembly. There are no traveling dots.
Camera motion changes position only.
The initial obstacle layout determines a deterministic art seed; both are saved
with snapshots so destruction and reload cannot rearrange the network. Existing
saves derive their initial layout from remaining walls on their first load.
Wind, Forest, Fire and Mountain retain their palette identities and gameplay
effects. The approved walls, floor material, and background are unchanged.

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
