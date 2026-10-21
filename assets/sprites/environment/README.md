# Active neural-world artwork

This directory contains only the environment art consumed by the current renderer.

| File | Role |
| --- | --- |
| `neural-stone-v1.png` | Illustrated mineral cortex; retains its source detail at runtime |
| `neural-walls.png` | Two alpha cutouts: reinforced dark stone and fragile pale stone; roots and synaptic buds derived from the preferred v1 style |
| `neural-abyss.png` | Shared distant dendritic world, rendered with slow camera parallax outside the platform |
| `neural-cliff.png` | Alpha cliff strip with hanging fibers and peripheral growth |

The animated branching network is drawn in `zgame/neural_environment.py`, not
baked into the floor. Wind, Forest, Fire and Mountain change only its palette,
branch treatment and breathing timing; legacy save/gameplay identifiers remain.

Wall geometry maps the stone cap onto a 2:1 tile diamond independently from its
vertical extrusion. Coordinate-stable low/medium/full/tall variants use 50%,
78%, 100% and 118% of the 109-pixel base, with endpoint/corner adjustments and
selective luminous buds. Decorative roots may overhang that footprint.
Cliff art never changes collision or pathfinding. The backdrop is visible when
the camera sees past the platform; interior combat views remain open floor. The far painting follows 14% of camera
displacement; dimmed existing cliff cutouts follow 40%, haze 24%, and the rim
100%. Cached illumination/haze overlays add subtle idle motion. Stationary
background compositions refresh at 10 Hz; camera movement updates immediately. No new source
art was generated for the wall-variety/parallax follow-up.

The three new assets were generated with the built-in image tool using the
approved Balanced World reference. Exact prompts are in `generation-prompts.json`.
The earlier v1/v2 wall sheets and superseded environment captures were removed
from the active checkout for clarity; they remain recoverable in commit `35a3943`.
This does not remove the current neural-stone-v1 source.
