# Validated Eidolon revision — 2026-10-16

## Scope and recovery

Continued the existing implementation, without rebuilding companion combat or
regenerating approved art. The previous known-good version remains on
`codex/checkpoint-before-option-b-20261016` at `4e736a2`.
The final revision also includes the user's additional taller-wall request.

## Presentation

- Visible stage heights: approximately 96 / 144 / 216 px, compensating for
  different atlas-row padding. Stage 1 exceeds the player's nominal 89 px
  sprite height; later stages grow about 1.5x. Collision remains 0.44 tile.
- Both renderers use stage-aware culling margins, including hovering art and UI.
- HUD: Eidolon +X% harvest label, HP bar, then purple skill-charge bar. No
  numeric charge text or REGEN suffix. Charge is dim before stage 3, bright when full.
- Shop name is Eidolon. Both shop screens use the three exact supplied avatars,
  selecting the evolution granted by the next purchase. Save identifier remains
  `evolving_skull` for compatibility.
- The eye beam is a single straight ray, supersampled for smooth edges:
  9 px magenta body, 4 px core, faint 16 px envelope. No spiral or side rays.
- Walls have double their old visual height, with two staggered masonry courses.
  Caps rise above the original ground footprint; depth sorting uses the base,
  not the raised cap. Lightweight rendering no longer shortens these walls.
  Collision, obstacle HP, map layout and navigation are unchanged.

## Shadow Procession

Directional pass: the approved right-facing ghost art and wake share the same
64-sector heading derived from the screen-space velocity. Left-going heads are
mirrored before diagonal tilting, keeping crowns above jaws instead of upside
down; their noses still follow the route. The wake attaches 0.24 sprite-lengths behind the head center, under its
existing rear wisps. It is now 2.4 sprite-lengths long (formerly 3.25), relatively
solid at the front and narrower/fainter at the rear. Four deterministic phases
and bounded rotation caches avoid combat RNG and particle-object allocation.
Trails remain cosmetic. Current capture: `evidence/eidolon-upright-procession.png`.

36 predetermined sweeps emit evenly over a 2.5-second window
(50% more skulls than the previous 24).
Six screen-space angles (28, 34, 42, 48, 58, 62 degrees) cover all four diagonal
quadrants, with distributed interior crossing points. Routes start/end beyond
viewport edges and travel at 0.52 viewport diagonals/second (another 20% slower
than the previous 0.65). Heads never reverse,
bounce or clamp to an edge; finished rows are removed promptly. Late emissions
finish their crossing after the emission window, then a hidden five-second cooldown begins.

New casts store normalized viewport positions and velocities. Each update maps
those paths to the current player-centered camera for both contact damage and
drawing. Delayed entries therefore appear at the current screen boundary.
Resize adapts the paths; teleport reanchors them without sweeping damage across
the intervening map. Same-level save/load retains normalized paths and remaining
time; old world-space saved casts finish compatibly, then subsequent casts use
viewport space.

The configurable `PROCESSION_KILL_THRESHOLD` defaults to 40. Combined player
weapon/prop and Eidolon kills (including beam and Procession) count once through
the existing death guard. Each successful cast clears all charge, including
surplus, so the purple meter empties. Only new kills refill it; that new progress survives save/load.
casts never stack during emission, the final crossing drain, or cooldown. Kill progress continues during cooldown; remaining cooldown persists in same-level saves and resets at level transitions. No cooldown indicator is added. Existing >=5
enemies or boss/Bandit encounter gate remains. Player kills do not grant harvest.
Level transitions/downing/fresh runs still reset progress. Released casts finish
on downing, without harvest or charge rewards for the downed companion.
Contact damage stays 1.5x cast-time shot damage, 0.8-tile radius, shared 0.3-second
hit spacing, and spectral wall passage with damage to destructible walls only.

## Beam and other preserved mechanics

Regular homing orbs now have a 9 px visual radius (formerly 6), a deeper
saturated violet body and a slightly thicker curved trail. Travel speed is
60% of normal bullet speed (formerly 75%, a 20% reduction). Fire interval,
damage, homing, lifetime and the 3 px collision padding are unchanged.

Stage 3 beam automatically locks a target within seven tiles for three seconds,
then cools down for twelve seconds. Damage is 3x current projectile damage per
second, including harvest. Normal fire continues. Walls block the ray and
destructible walls take damage. Target death/out-of-range permits retargeting
without restarting duration. Downing stops the beam; same-level saves restore
duration/cooldown and a target hint. Beam kills grant both harvest and skill charge.

Movement-facing, homing, harvest caps, health, regeneration, downing,
progression, shop economy and saves remain intact. No new summon or skill added.

## Summon biome buffs

Eidolon reads the active level biome, independently of player weapon stats.
Scorched Hell doubles its normal shots, beam and Procession damage exactly once.
Domain of Wind gives its navigation the same 12% movement-speed bonus as the player.
Bastion of Stone grants a non-regenerating shield worth 50% of level-entry maximum
HP. Damage depletes shield before HP; overflow reaches HP and shield hits reset
the regeneration delay. A cached blue outline follows the current sprite's full
silhouette, including disconnected horns, and disappears when depleted/downed.
The existing two-bar HUD is unchanged. Shield capacity and remainder persist
through same-level saves (including zero); harvest never refills them. A new
Stone level grants a fresh shield, other levels remove it. Legacy saves without
shield fields receive the entry shield once. Mist's XP bonus stays player-owned.
No enemy/player biome rules, turret systems or environmental hazard behavior changed.
Capture: `evidence/eidolon-stone-shield.png`.

## Cleanup

Removed the unused `assets/sprites/summons/skull-directions.png` and
`skull-directions-prompt.md`. Both are recoverable from Git/checkpoint.
Kept `skull-atlas.png` because its ghost quadrant is still used.
Historical checkpoint evidence is retained for recovery/reference; current
captures supersede the prior Option B presentation captures.

## Verification

67 summon/integration checks pass, including empty-on-cast HUD and post-cast refill, biome damage, shield absorption/save/
transition behavior, all-stage silhouette outlines, temporary Wind speed, upright mirrored heads, larger/deeper
orbs and reduced shot speed, diagonal route families, emission/
exit lifecycle, shared head/tail rotation and rear anchor, tapered trail bounds,
fade/cache behavior, unchanged rendering RNG, 40-kill trigger and saved progress, compact
two-bar HUD, all evolution avatars in both real
shop screens, visible size ratios, compact collision, edge/corner culling,
smooth beam pixels, viewport-relative damage, resize, active-cast disk save/load
and recast, old-save compatibility, wall height/ground anchoring and unchanged
wall physics. The existing 9 projectile and 13 game-state scenarios also pass.

The actual level-loop runner passed six scenarios, 565 rendered frames each (all stages, Mist, Hell, Stone,
Wind/tornado, lightweight rendering, boss encounter and downed snapshot resume).
It checks moving-camera path alignment every active-cast frame and captures
entry/mid/exit states. Test fixtures seed purchases/charge and protect the player;
normal AI, navigation, damage and rendering run. This is scripted local Python
gameplay, not a human/manual or live-browser playtest.

Current captures are under `docs/evidence/option-b-*.png`,
`docs/evidence/eidolon-procession.png`, and `docs/evidence/eidolon-shop.png`.
Additional generated shop/procession captures are under `TEMP/summon-playtest`.
Source compilation and whitespace checks also pass. No user save is modified.
