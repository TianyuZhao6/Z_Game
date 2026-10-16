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
  6 px magenta body, 3 px core, faint 11 px envelope. No spiral or side rays.
- Walls have double their old visual height, with two staggered masonry courses.
  Caps rise above the original ground footprint; depth sorting uses the base,
  not the raised cap. Lightweight rendering no longer shortens these walls.
  Collision, obstacle HP, map layout and navigation are unchanged.

## Shadow Procession

New casts store normalized viewport positions and velocities. Each update maps
those paths to the current player-centered camera for both contact damage and
drawing. Delayed entries therefore appear at the current screen boundary.
Resize adapts the paths; teleport reanchors them without sweeping damage across
the intervening map. Same-level save/load retains normalized paths and remaining
time; old world-space saved casts finish compatibly, then subsequent casts use
viewport space.

Charge update: 15 combined player weapon/prop and Eidolon projectile/beam kills
charge one cast; at least five enemies
or a boss/Bandit enables release; 24 crossings finish within three seconds;
shared 0.3-second contact gap; 1.5x cast-time shot damage; spectral wall passage,
destructible-wall damage, no Shadow Procession kill recharge. Player kills do not
increase Soul Harvest. Released casts finish on downing
without awarding harvest or charge to the downed companion.

## Beam and other preserved mechanics

Stage 3 beam automatically locks a target within seven tiles for three seconds,
then cools down for twelve seconds. Damage is 3x current projectile damage per
second, including harvest. Normal fire continues. Walls block the ray and
destructible walls take damage. Target death/out-of-range permits retargeting
without restarting duration. Downing stops the beam; same-level saves restore
duration/cooldown and a target hint. Beam kills grant both harvest and skill charge.

Movement-facing, homing, harvest caps, health, regeneration, downing,
progression, shop economy and saves remain intact. No new summon or skill added.

## Cleanup

Removed the unused `assets/sprites/summons/skull-directions.png` and
`skull-directions-prompt.md`. Both are recoverable from Git/checkpoint.
Kept `skull-atlas.png` because its ghost quadrant is still used.
Historical checkpoint evidence is retained for recovery/reference; current
captures supersede the prior Option B presentation captures.

## Verification

52 summon/integration checks pass, including combined kill charging, compact
two-bar HUD, all evolution avatars in both real
shop screens, visible size ratios, compact collision, edge/corner culling,
smooth beam pixels, viewport-relative damage, resize, active-cast disk save/load
and recast, old-save compatibility, wall height/ground anchoring and unchanged
wall physics. The existing 9 projectile and 13 game-state scenarios also pass.

The actual level-loop runner passed five scenarios, 565 rendered frames each (all stages, Mist, Hell,
Wind/tornado, lightweight rendering, boss encounter and downed snapshot resume).
It checks moving-camera path alignment every active-cast frame and captures
entry/mid/exit states. Test fixtures seed purchases/charge and protect the player;
normal AI, navigation, damage and rendering run. This is scripted local Python
gameplay, not a human/manual or live-browser playtest.

Current captures are under `docs/evidence/option-b-*.png`,
`docs/evidence/eidolon-procession.png`, and `docs/evidence/eidolon-shop.png`.
Additional generated shop/procession captures are under `TEMP/summon-playtest`.
Source compilation and whitespace checks also pass. No user save is modified.
