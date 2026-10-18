# First-playable summon checkpoint

Historical checkpoint record. The current Eidolon sizing, avatars, viewport-relative
Procession, beam and taller walls are documented in `summon-option-b.md`.
Old screenshots below intentionally record the earlier recovery version.

## Scope and integration

Continued the existing `zgame/summons.py` implementation. Homing volleys, harvest,
downing, regeneration and the three-second procession were retained, not rebuilt.
The unfinished work was end-to-end validation, presentation checks, documented
tuning defaults and a recoverable checkpoint. Shop, enemy, persistence and
renderer hooks were already present when the continuation request arrived.

- **Shop:** Evolving Skull is a rarity-2, $18 base-price card in the existing
  catalog. Purchases advance L1–6, evolving at L3/L6. A shop button equips/stores
  it; turrets do not consume companion slots. Guaranteed offer on every third
  distinct level-shop visit, also on rerolls; capped cards are excluded. Four
  locked cards are retained with a temporary fifth guaranteed offer.
- **Combat:** ordinary enemies can target a closer visible skull, with switching
  hysteresis. Melee, hostile projectiles and relevant enemy specials damage its
  independent HP. It does not inherit the player's shields, crit or weapon props.
  Boss/Bandit targeting is unchanged. Enemy shields absorb summon hits. The Mist
  boss retains projectile evasion. Kill rewards, Bandit bounties and twin enrage
  are resolved once. Physical body/ordinary shots stop at walls; procession does not.
- **Persistence:** run-owned level, equipped state, harvest and combat record live
  in META, included in progress saves and full snapshots. Same-level reconstruction
  restores HP/downing, charge, projectiles and unfinished procession. Actual next
  level reconstructs full HP and clears charge; harvest survives unless downed.
  Fresh run clears everything. Existing older saves without summons still work.
- **Visuals:** approved forms are integrated from `assets/sprites/summons/skull-atlas.png`.
  Large companion art, compact collision body, bobbing, HP/harvest/charge label,
  DOWN transparency and REGEN label. Pale procession skulls have roughly 45%
  opacity and fading tile trails. Both standard and lightweight renderers use
  the same simulation; offscreen contacts are not culled.
- **Growth:** L1/L2/L3–5/L6 volleys are 1/3/3/5. Harvest starts at L3, adds one
  percentage point per personal kill, caps at 100%/200%, preserves health ratio,
  and does not bank excess. Only L6 normal-attack kills fill the separate 15-kill
  charge. Skill kills cannot recharge; no overlapping casts.

## First-pass balance

HP by level: 80, 95, 120, 145, 175, 220. Per-shot damage: 10, 11, 14, 17, 20, 24.
Volley interval 1.25s; range 7 tiles; projectile lifetime 3.5s. Regenerate 2% of
maximum HP per second after five damage-free seconds. Procession: 24 crossings,
three seconds total, 1.5x cast-time damage per contact, shared 0.3s hit spacing.
These are named tuning constants, not final balance. Dedicated investment is
strong; player movement/fighting is still needed. No unrelated prop rebalancing.

## Verification

- `python tools/verify_summon_runtime.py`: 32 checks, including both actual shop
  screens, purchases, equip toggle, damage isolation, shield absorption, enemy
  variants, boss targeting, save-file round trips, downed reload, transitions,
  harvest, trigger rules, retargeting, compact navigation, offscreen damage,
  shared hit spacing, active-cast resume, cleanup, both renderers and alpha.
- `python tools/verify_bullet_runtime.py`: existing nine scenarios pass.
- `python tools/verify_game_state_runtime.py`: existing thirteen scenarios pass,
  including shields/Aegis, damage, pickups, paint, DoT, navigation and fog.
- `python tools/playtest_summon.py`: scripted input through the actual level loop,
  not a separate simulation. Five scenarios, 565 rendered frames each: Bloombone;
  Soulflame/Mist; Rift/Hell with downing and actual snapshot resume; lightweight
  renderer/Wind with a tornado; Rift/twin-boss stage. Normal AI, movement,
  projectiles, player weapon props, wall damage, level timer and renders run.
  Charge is seeded to exercise the ultimate; the player is protected to finish
  the test timeline. Cinematics/result prompts are skipped. This is automated
  headless gameplay validation, not a human/manual or real-browser playtest.
- 200-enemy summon-only benchmark: three simulated seconds took 0.532s locally,
  approximately 2.96ms per update. This does not measure total game FPS or browser speed.
- Actual rendered captures: `docs/evidence/summon-standard.png` and
  `docs/evidence/summon-lite.png`; additional frames regenerate under
  `TEMP/summon-playtest`. Run with `--visible` to watch the scripted scenarios.

## Corrections made during validation

Preserved the lightweight browser enemy-movement path while adding companion
target selection, rather than forcing all enemies onto expensive full movement.
Confirmed full snapshot META includes companion progression. Added target-switch
hysteresis and cleared stale routes on switches. Retained Mist projectile
evasion. Fixed the Bandit test fixture to use the existing Bandit factory and
dismissed unattended success prompts in the test runner; neither required a
gameplay rewrite. Existing regression suites found no failing scenarios.

## Remaining validation and limitations

Only this companion is implemented; other summon designs remain deferred. The
three-slot limit is reserved, not an implementation of three different species.
The companion now uses authored directional views plus bobbing; it does not yet
have separate frame-by-frame idle, attack, or turning animations.
Human feel/balance testing and a real browser/Pyodide run remain. Random crossing
coverage intentionally does not guarantee every target is hit. Summon state is
preserved by the existing progress-save workflow even though that workflow
restarts the map; full snapshots preserve the encounter more closely. The
existing general snapshot format is not a complete serialization of all boss
AI/biome effects; this change does not replace that system.

This is a local first-playable checkpoint, not a deployment. No user save files
were used by the tests; disk-save checks use isolated temporary directories.
Checkpoint branch: `codex/summon-first-playable`, based on `web-demo` at
`9f58f9d`. The previous branch is retained; nothing is pushed or deployed.

## Movement-facing and terrain art follow-up (2026-10-15)

Superseded companion presentation and additional beam rules are documented in
`summon-option-b.md` (2026-10-16). The map/wall changes below remain unchanged.

All three evolutions face their actual movement using eight camera-relative
views. Upright front/profile/rear art replaces the fixed image. Facing updates
after wall collision resolution, holds while idle/blocked, uses a small angular
hysteresis to prevent flicker, and survives same-level saves. Old saves default
to facing forward. Collision size, navigation, damage and skill rules are unchanged.

The native terrain renderer now draws dark beveled stone slabs with restrained
grain, chips and sparse carved wards. Permanent walls use blue-gray banded stone
and an inset seal; breakable walls use warm fractured masonry. Low prism walls
replace the old tall pillar overlay. Both renderers share cached deterministic
materials, without consuming gameplay randomness. Damage tints are quantized
and the lightweight wall cache refreshes on damage as well as removal.

Validation: 32 summon/art checks + 9 bullet checks + 13 game-state checks passed.
All five actual-level-loop scenarios passed (565 frames each); each asserts at
least three facing directions occurred. The lightweight scenario now enables
the real web render/cache flags during rendering. This still runs on desktop
Python, not in a browser. Human visual/feel approval remains with the player.

New real runtime captures: `docs/evidence/summon-facing-front.png`,
`docs/evidence/summon-facing-rear.png`, and `docs/evidence/summon-terrain-lite.png`.
These are unedited automated gameplay captures, not generated mockups.
