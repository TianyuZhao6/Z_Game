# Current Game — Product Requirements Document

Version: 1.0 draft | Updated: 2026-10-31 | Project: Z_Game

This document defines the current native desktop game, the requirements needed to finish it, and the deferred feature backlog. It is documentation only. It does not authorize implementation, asset replacement, balance changes, or removal of existing gameplay.

## 1. Product definition

A single-player, isometric survival action game set within a surreal neural world. The player controls a healing-agent character, survives escalating enemy waves, collects resources, and assembles a run-specific build through level-up choices, purchased props, turrets, and an evolving autonomous companion. Positioning and build choices drive play; basic shooting is automatic, with manually targeted skills for intervention and escape.

The repository's narrative frames each run as a fictional treatment cycle within a deteriorating brain. Memory, neural connections, and corruption inform the world and enemy themes. This is a fictional game premise, not a claim about medical treatment. The exact narrative and ending scripts remain a design task.

Branding is unresolved: README uses **NEURONVIVOR**, reference artwork uses **NEUROSURVIVOR**, and the current window-title constant is **NEUROSURIVER**. Use Z_Game as the project identifier until one player-facing name is approved.

Intended audience: players who enjoy short survival encounters, automatic-attack combat, tactical movement, and synergistic builds. Audience assumptions and target session length require playtesting; no audience research is claimed here.

### Product pillars

1. Readable survival combat: players can recognize threats, escape routes, damage, and recovery opportunities.
2. Meaningful builds: offense, defense, economy, ground effects, and summons produce distinct decisions and interactions.
3. A coherent neural world: organic stone, rooted ruins, branching illumination, and a layered abyss share a consistent visual language.
4. Reliable run continuity: purchases, upgrades, resources, and saved progress behave predictably across menus, levels, restart, and resume.
5. Responsive desktop play: input, combat, audio, and transitions remain usable during dense encounters.

## 2. Scope and authority

The latest user direction and root `AGENTS.md` take precedence over historical notes. Runtime source establishes current behavior; it does not automatically establish final product intent. `ui/Props` supplies detailed prop designs and the current map description. Conflicts and undecided behavior must remain visible instead of being silently resolved by this PRD.

### Current delivery scope

- Native/local desktop game, with Windows as the current development environment. Support for other desktop operating systems requires a separate packaging and validation decision.
- Region 04 — **Fractured Depths** is the only environment in active art and asset scope. Add other region descriptions and production assets only after their art and assets are finalized.
- Preserve the selected `region04-shimmer` baseline from checkpoint `5184282`, including its geometry and rendering until a specific refinement is requested.
- Retain existing gameplay, actors, approved environment assets, deterministic seeds, obstacle handling, world alignment, cached illumination, and save compatibility.
- Existing runtime biome modifiers and identifiers remain compatibility behavior. Region 04 is the environment-art designation; this PRD does not equate it with the fourth entry in a gameplay-biome list or remove the other modifiers.
- Browser development, browser builds, browser optimization, and browser acceptance are outside this milestone. Historical browser sections in `Props` do not create desktop release gates.

Multiplayer, online accounts, cloud saves, monetization, mobile/console ports, and a new engine are outside this PRD's delivery scope. Controller support is a future product decision, not an established feature.

### Status and priority vocabulary

| Label | Meaning |
| --- | --- |
| Present | A corresponding runtime path exists in the inspected source. This does not imply current-session testing or final acceptance. |
| Partial | Supporting code or design exists, but end-to-end behavior, completeness, or presentation still needs verification/work. |
| Required | A completion requirement proposed by this PRD; not a claim of implementation. |
| Deferred | Documented future concept outside the immediate desktop/Region 04 milestone. |
| Decision | Product behavior or a final value needs an explicit choice. |
| P0 | Protect the playable baseline: core loop, correctness, save integrity, readability, and stability. |
| P1 | Complete and polish the desktop product after baseline correctness. |
| P2 | Expand content after its mechanics, art, and assets are approved. |

Priorities are planning recommendations. They are not a request to implement every historical proposal before accepting the current environment milestone.

## 3. Player journey and run structure

The primary journey is: launch → title/instructions/settings → new run or continue → timed combat → level-up choices during combat → level result → shop → next-domain selection → next level. Pause provides inspection and navigation without consuming combat time. Failure presents retry/home choices; current retry behavior is distinct from starting an entirely fresh run.

| ID | Requirement | Status / priority | Acceptance condition |
| --- | --- | --- | --- |
| RUN-01 | Launch into an understandable title screen with New Run/Start, Continue when valid, Instructions, Settings, and Exit. | Present / P0 | Every visible action reaches its intended state; unavailable Continue is clearly disabled or absent. |
| RUN-02 | A fresh run resets run-owned currency, props, player progression, summon ownership/harvest, shop state, and run counters while retaining intended preferences. | Present / P0 | Starting again cannot inherit combat power, debt, rewards, or companion progression from the previous run. |
| RUN-03 | Ordinary stages use timed survival; current limits are 45 seconds normally and 60 seconds on boss stages. | Present / P0 | Timer, combat state, and result agree; pause and level-up selection do not spend stage time. |
| RUN-04 | Health depletion causes failure with a clear result and recovery path. | Present / P0 | Death is resolved once; rewards and purchases are not duplicated through retry/home transitions. |
| RUN-05 | Completed stages lead through result and shop into the next stage, retaining the intended run build. | Present / P0 | Continue works from both a combat snapshot and a pending shop without skipping or replaying settlement. |
| RUN-06 | Define campaign length, final encounter, post-final behavior, and whether an endless mode exists. | Decision / P1 | One approved progression specification determines the end of a run and subsequent menu options. |
| RUN-07 | Define whether defeating a boss is required to clear its stage. | Decision / P1 | Instruction text, timer behavior, rewards, and narrative agree with the chosen rule. |

Current timer expiration is a success condition, including the boss-stage timer path. Do not describe boss defeat as a mandatory clear requirement until that rule changes. Current level configuration supports continued progression; a completed finite campaign and narrative ending system are not established by the inspected flow.

## 4. Controls, camera, and player combat

### Input contract

| Action | Current interaction | Completion requirement |
| --- | --- | --- |
| Movement | WASD by default, mapped to the isometric view; diagonal input is normalized. | Consistent movement in all directions, collision sliding, and no movement through blocking terrain. |
| Basic attack | Automatic target selection and fire within range. Nearby breakable obstacles can take priority. | The target and projectile behavior must be understandable; no burst of stored shots when a target appears after idle time. |
| Blast | Q by default enters targeting; left-click confirms a valid point. Current cooldown: 10 seconds. | Show area/range, validity, cast feedback, and cooldown. Invalid casts must not spend the cooldown. |
| Teleport | E by default enters targeting; left-click confirms a valid destination. Current cooldown: 6 seconds. | Show destination validity; never place the player inside a blocking obstacle or outside playable bounds. |
| Pause | Escape opens the pause flow; targeting cancellation must remain consistent with that flow. | Explain cancel-versus-pause behavior and verify it in instructions and gameplay. |
| Rebinding | Settings exposes movement, Blast, and Teleport bindings. | Bindings persist and update prompts; reject or explain conflicts and reserved keys. |
| Menus | Mouse selection and existing keyboard handling. | All required actions remain reachable at supported desktop resolutions. |

### Combat requirements

- **COM-01 — P0, Present:** Keep automatic fire, range/cadence limits, enemy and wall collision, and projectile ownership. Fast projectiles must not skip intervening targets or walls.
- **COM-02 — P0, Present:** Support direct damage, critical hits, shields, HP, contact invulnerability, healing, vulnerability, damage over time, and source-specific effects. Resolve enemy death, rewards, and kill attribution once.
- **COM-03 — P0, Present:** Preserve piercing, ricochet, shrapnel, explosions, turrets, spikes, and paint interactions. Secondary effects need explicit propagation limits and must not create recursive proc loops.
- **COM-04 — P0, Present:** Separate player-bullet effects from summon and environmental damage. An effect inherits another system's stats or triggers only when its specification explicitly grants that interaction.
- **COM-05 — P0, Present:** Display HP, shield state, skill cooldowns, damage/hit feedback, and relevant status changes. Critical warnings remain visible during dense effects and boss encounters.
- **COM-06 — P0, Present:** Camera transforms, actor depth sorting, aim previews, world coordinates, collision footprints, and ground effects must agree. Decorative sprite size must not silently change collision.
- **COM-07 — P1, Required:** Consolidate damage-order and stacking rules into one maintained specification. Include mitigation, shield overflow, damage-over-time rounding, boss modifiers, kill attribution, and simultaneous-hit ordering.

Acceptance: movement and aiming work in all directions and near walls; hits do not double-award kills; shields and HP change correctly; every cast has clear feedback; dense overlapping effects preserve player and threat readability.

## 5. Progression, pickups, and build identity

The runtime contains XP progression, queued level-up choices, collectible items, coins/spoils, and healing pickups. Player level is separate from stage number, wave number, prop level, and Eidolon evolution; UI must distinguish these concepts.

| ID | Requirement | Status / priority |
| --- | --- | --- |
| PROG-01 | Award source-appropriate XP and process all earned level-ups without losing queued choices. | Present / P0 |
| PROG-02 | Show four sampled choices where eligible: +1 damage, +5% fire rate, +10% range, +5% speed, +5 max HP with healing, or +2 percentage points crit. Respect effective stat caps. | Present / P0 |
| PROG-03 | Apply chosen upgrades once, show the resulting value, and preserve them within the run. | Present / P0 |
| PROG-04 | Coins and healing pickups use correct collection radius, values, caps, ownership, and cleanup. Heal only up to the applicable maximum. | Present / P0 |
| PROG-05 | Preserve collectible/main-block and run item counters without implying that collecting every item is the current stage-clear condition. | Present / P0 |
| PROG-06 | Distinguish temporary level buffs, run-owned upgrades, consumable resources, and permanent preferences. Do not imply unimplemented progression between runs. | Required / P0 |
| PROG-07 | Give props readable path labels, icons, and consistent card colors in shop and pause. | Partial / P1 |
| PROG-08 | Define path completion rewards, higher-tier unlock conditions, and any combinations that affect endings. | Deferred / P2 |

Acceptance: choosing an upgrade updates live stats and pause information consistently; capped options do not offer ineffective purchases/choices; save/reload and level transitions do not compound multipliers or duplicate pickups.

## 6. Shop, economy, and props

### Shop requirements

- **SHOP-01 — P0, Present:** Offer a randomized catalog with rarity, current cost, description, ownership/level, and purchase eligibility. Keep four normal offers and the separate reroll mechanism readable.
- **SHOP-02 — P0, Present:** Preserve offer locks, rerolls, level/ownership price scaling, coupon discounts, caps, and shop save state. A completed transaction changes money and ownership exactly once.
- **SHOP-03 — P0, Present:** Display insufficient funds and maximum level clearly; locked/capped items cannot create a dead-end shop. An offer must produce the behavior stated on its card.
- **SHOP-04 — P0, Present:** Preserve interest, debt, protected currency, bounty windows, and Bandit interactions. Settlement order and shop re-entry must not produce duplicate payouts or repayments.
- **SHOP-05 — P0, Present:** Preserve the eligible Eidolon guarantee on every third distinct level's shop visit, including rerolls. If all four normal offers are locked, the temporary extra offer must preserve those locks. At Eidolon's cap, use ordinary eligible offers.
- **SHOP-06 — P1, Required:** Show current/next values, meaningful tradeoffs, debt remaining, relevant payout limits, path identity, and consumable duration in concise player-facing language.
- **SHOP-07 — P1, Decision:** Reconcile the proposed four-sided die domain-selection flow in `Props` with the current hidden-card picker. Define what the player chooses, when the domain is revealed, and what confirmation means.

### Current purchasable catalog

These entries are present in `zgame/shop_support.py`; their exact live balance takes precedence over stale roster rows. Reroll is a shop action, not an equipped combat prop.

| Family | Present item | Core role |
| --- | --- | --- |
| Ballistic | Piercing Rounds | Continue a shot through additional enemies. |
| Ballistic | Ricochet Scope | Redirect shots after eligible collisions. |
| Ballistic | Shrapnel Shells | Spawn fragments on eligible kills. |
| Ballistic | Explosive Rounds | Add an explosion on eligible bullet kills. |
| Status | D.O.T. Rounds | Apply stacking damage over time. |
| Status | Mark of Vulnerability | Mark a priority enemy for increased damage taken. |
| Ground effects | Curing Paint | Leave damaging curing footprints while moving. |
| Ground effects | Ground Spikes | Leave one-hit slowing hazards with a movement tradeoff. |
| Defense | Carapace | Purchase reserve shielding. |
| Defense | Bone Plating | Regenerate plating with a maximum-level benefit and movement tradeoff. |
| Defense | Aegis Pulse | Emit damaging pulses while shielded. |
| Economy | Coin Magnet | Increase pickup reach. |
| Economy | Coupon | Reduce prices within the current run. |
| Economy | Golden Interest | Reward unspent currency with capped interest. |
| Economy | Shady Loan | Exchange future repayment risk for immediate money. |
| Economy | Lockbox | Protect part of the currency pool from applicable losses. |
| Bandit interaction | Bandit Radar | Highlight and slow newly spawned Bandits. |
| Bandit interaction | Wanted Poster | Activate the existing limited bounty opportunity. |
| Allied damage | Auto-Turret | Orbit the player and attack nearby targets. |
| Allied damage | Stationary Turret | Add persistent-in-level allied firing positions on clear tiles. |
| Companion | Eidolon | Evolve a unique autonomous companion through six purchased levels. |
| Shop action | Reroll | Refresh eligible unlocked offers at the current cost. |

Before adding any prop, specify its unique role, acquisition, price/rarity, maximum level, scaling, trigger, target filters, cooldown, effect lifetime, stacking, boss behavior, source ownership, anti-loop limits, persistence, visuals, audio, and short/long tooltip. `Props` remains the detailed catalog; this PRD is the product-level checklist.

Acceptance: test each present item's acquisition, upgrade, cap, live effect, pause display, and save/resume; cover insufficient funds, all offers locked, capped catalog entries, repeated shop entry, debt default, bounty redemption, and combined economy effects.

## 7. Allied actors and Eidolon

Auto-Turrets and Stationary Turrets are present and retain their existing count, placement, targeting, and collision rules. They do not consume mobile-companion slots. Their visuals must remain distinct from enemies and their projectiles.

Eidolon is the implemented mobile companion. Its shop/save identifier remains `evolving_skull`. The three-companion loadout is a design capacity, not evidence that three different companions are currently implemented. First purchase auto-equips Eidolon; duplicate purchases upgrade the same actor, up to level 6. Between levels, it can be stored or equipped.

| Level | Form | Base max HP | Base shot damage | Shots per volley | Harvest cap | Unlock |
| --- | --- | ---: | ---: | ---: | --- | --- |
| 1 | Bloombone | 80 | 10 | 1 | None | Homing volley |
| 2 | Bloombone | 95 | 11 | 3 | None | Expanded volley |
| 3 | Soulflame | 120 | 14 | 3 | +100% damage/max HP | Soul Harvest |
| 4 | Soulflame | 145 | 17 | 3 | +100% | Base-stat improvement |
| 5 | Soulflame | 175 | 20 | 3 | +100% | Base-stat improvement |
| 6 | Rift Skull | 220 | 24 | 5 | +200% | Shadow Procession and eye beam |

These are current first-playable values, not final balance.

- **SUM-01 — P0, Present:** Autonomous following, obstacle-aware movement, target selection, homing volleys, and retreat below 25% HP. Ordinary attacks use a 7-tile range and 1.25-second volley interval. Body and normal shots respect walls.
- **SUM-02 — P0, Present:** Use independent summon damage/HP scaling. Player weapon damage, crit, and bullet-only props do not automatically apply to Eidolon.
- **SUM-03 — P0, Present:** From level 3, each eligible personal enemy kill grants one percentage point of Soul Harvest damage/max-HP bonus up to the current cap. Preserve HP percentage when max HP increases. Player kills do not grant harvest.
- **SUM-04 — P0, Present:** Preserve harvest across levels, storage, and same-run saves; retain it on evolution without adding free stacks. Downing and fresh runs clear harvest.
- **SUM-05 — P0, Present:** At level 6, Shadow Procession charges from 40 eligible combined player/Eidolon kills while active. Cast automatically with at least five living enemies or a living boss/Bandit; clear charge on successful cast.
- **SUM-06 — P0, Present:** Procession emits 36 spectral crossings across 2.5 seconds around the moving viewport. Contact damage is 1.5 times cast-time shot damage with a shared 0.3-second per-target gap. Spectral skulls cross walls and damage breakable walls. Another cast waits for all crossings plus a five-second cooldown.
- **SUM-07 — P0, Present:** The final-form eye beam attacks for three seconds at three times current shot damage per second, then cools down for 12 seconds. Walls block it; destructible walls take damage. It operates independently of volleys and Procession.
- **SUM-08 — P0, Present:** Regenerate 2% max HP per second after five damage-free seconds. At zero HP remain downed until the next level, with upgrades retained. Same-level resume must not revive the companion.
- **SUM-09 — P0, Present:** A released Procession can finish after downing; downed-owner kills cannot restore harvest or charge. Downing interrupts the eye beam. New levels reset Procession charge.
- **SUM-10 — P0, Present:** Preserve approved forms, eight-direction facing, exact approved shop avatars, compact collision body, and HUD: Eidolon +harvest%, HP bar, skill bar, and DOWN state. Visual horns, trails, and halos do not add collision or damage.
- **SUM-11 — P1, Required:** Make stored/equipped/downed state and next-level recovery understandable in the companion UI. Complete the wider roster UI only when additional companions are approved.

Acceptance: exercise each evolution, full harvest caps, downing, storage, reconstruction, same-level resume, wall interactions, moving-camera Procession, beam retargeting, concurrent attacks, and kill attribution. Maintain approved existing visuals until a specific change is requested.

## 8. Enemies, encounters, and hazards

The runtime supports basic pursuers, fast/strong/tank variants, ranged/spitter attackers, explosive enemies, buffers, shielders, splitting enemies, charging Ravagers, special mist/corruption enemies, and Coin Bandits. Exact spawn eligibility and weights belong to the active threat tables, not to the existence of an enemy class alone.

Boss code includes Memory Devourer, Mistweaver with clones/fog behavior, and a level-15 twin Memory Devourer encounter with survivor enrage. Boss stages are scheduled every five levels in the current configuration. The final narrative boss, The Empty Crown, is a proposal from README rather than an established shipped encounter.

| ID | Requirement | Status / priority | Acceptance condition |
| --- | --- | --- | --- |
| EN-01 | Budget-based waves scale threat, composition, elites, HP, damage, and movement with progression. | Present / P0 | Valid spawns, bounded active populations, and a reproducible difficulty curve without unavoidable spawn damage. |
| EN-02 | Distinct enemy roles have identifiable silhouettes, behaviors, and warning cues. | Present/Partial / P0 | Players can distinguish charging, ranged, explosive, shielded, support, and stealing threats during combat. |
| EN-03 | Navigation respects collision, destruction, and appropriate actor size; permitted boss wall-crushing remains explicit. | Present / P0 | Actors do not become permanently trapped or clip through walls without an intentional ability. |
| EN-04 | Preserve enemy coin absorption/growth, relevant XP transfer, split-child behavior, and ordinary drops. | Present / P0 | Source ownership and death guards prevent duplicated growth, rewards, or split events. |
| EN-05 | Bandits communicate arrival, stealing/escape pressure, and bounty/recovery opportunities. | Present / P0 | Lockbox, Radar, Wanted Poster, death, and escape resolve consistently and display the outcome. |
| EN-06 | Bosses provide readable health, phase changes, telegraphs, attacks, and twin enrage feedback. | Present / P0 | Boss attacks remain avoidable/readable; both fresh-entry and resumed fights preserve intended encounter rules. |
| EN-07 | Acid pools, hostile paint, fire effects, fog, wind hazards, slows, and damage-over-time distinguish hazards from cosmetic effects. | Present / P0 | Telegraph, collision, lifetime, and actual damage area agree; visual culling does not cancel gameplay. |
| EN-08 | Define the final boss roster, unlock schedule, stage-clear rules, and rewards as a complete campaign. | Decision / P1 | Every planned stage has an approved objective, encounter definition, and reward/exit state. |

Each future enemy needs a role, unlock point, spawn cost, base/scaled stats, AI states, attacks, telegraphs, damage windows, collision size, rewards, animation set, sound cues, and save-state policy before implementation.

## 9. Region 04 environment and asset requirements

Fractured Depths is a continuous cracked-stone combat platform suspended above a violet neural abyss. Root-bound walls, hanging cliff fibers, branching ground illumination, distant formations, and sparse lilac growth form the current visual foundation. See [Props](Props) for the full map description.

| Asset group | Required role | Current boundary |
| --- | --- | --- |
| A1 — Cracked slate ground | Readable, mostly flat stone floor with irregular slabs and fine fractures. | Preserve the approved production floor and world alignment. |
| A2 — Neural synapses | Branching ground conduits, selected major junctions, subdued secondary branches, and sparse glints/halos. | Preserve `5184282` geometry; asynchronous light breathing only. The reference's cyan/growth wording does not override current palette/motion decisions. |
| A3 — Pale breakable wall | Pale masonry, clear damage states, destruction feedback. | Keep current wall assets and collision footprints. |
| A4 — Permanent root-wall | Dark stone and knotted roots distinguish solid obstacles. | Keep approved height families, root overhang, and depth ordering. |
| A5 — Cavern cliff/root rim | Clearly bounded platform above the abyss. | Decorative cliff roots do not create hidden walkable paths or collision. |
| A6 — Distant abyss pillars | Layered depth, distant formations, violet light, haze, and camera parallax. | Preserve the approved backdrop and cached behavior. |
| A7 — Neural lotus landmark | A memorable distant violet bloom with radiating branches in the reference. | Reference role; do not claim a separately completed lotus asset or replace the approved background. |
| A8 — Lilac biolights | Sparse edge growth and rooted rubble. | Preserve combat readability; decorative additions must not add unannounced collision. |

**ENV-01 — P0, Present:** Procedural layouts must provide usable player routes, valid spawns, readable obstacle groups, and correct handling of wall removal. Preserve saved layouts rather than regenerating them merely to match a newer art pass.

**ENV-02 — P0, Present:** Network layout must remain deterministic and stable after wall destruction, camera movement, and save/resume. Seed and initial obstacle context must survive persistence.

**ENV-03 — P0, Present:** Preserve approved ground-network palettes: Wind cyan-blue, Forest purple, Fire red, Stone pale gold/yellow. `Bastion of Stone` / `Mountain` are retained identifiers. These are existing modifier/palette settings, not authorization to produce additional regional asset sets.

**ENV-04 — P0, Required:** Judge illumination in actual desktop scenes through a full breathing cycle, including dim, rising, peak, and falling states. Most branches remain subdued; no uniform neon, traveling particles, or moving geometry.

**ENV-05 — P1, Required:** Maintain an asset inventory with source/provenance, production path, transparency, dimensions, anchors, collision relationship, animation frames, and active/fallback/reference status. Missing optional art may use a controlled fallback; a release must include all required assets.

Additional regions remain deferred until each region's art and asset set are finalized. Do not reintroduce the removed five-region atlas descriptions as active production requirements.

## 10. UI, onboarding, and accessibility

| Surface | Present foundation | Completion requirement |
| --- | --- | --- |
| Intro/title | Neural-themed animated/menu presentation and music. | Clear title, responsive transitions, understandable start/continue distinction, and an approved skip/intro policy. |
| Instructions | Movement, survival timer, auto-fire, Bandits, shop, and pause guidance. | Add targeted-skill instructions, rebinding-aware prompts, shield/HP meaning, pickups, and companion basics. |
| Gameplay HUD | Health, shields, XP/progression, timer, resources, skills, bosses, and companion feedback. | Readable hierarchy at supported resolutions; urgent information survives dense effects and tall-wall occlusion. |
| Level-up | Paused choice overlay. | Legible eligible choices, correct caps, and no time loss or duplicated selections. |
| Shop | Offers, pricing, ownership, locks/rerolls, companion toggle, next-stage flow. | Current/next values, path labels, disabled reasons, debt/payout information, and clear navigation. |
| Pause | Player stats, owned props, descriptions, and run navigation. | Distinguish base values from bonuses; show companion and temporary-state information consistently. |
| Settings | BGM/effects volume, controls, and save export. | Persist intended preferences, handle unavailable audio gracefully, and confirm meaningful actions. |
| Results | Stage success/failure and follow-up actions. | Clear outcome, earned resources/progression where applicable, and unambiguous Retry, New Run, Home, and Exit semantics. |

- **UI-01 — P0, Required:** No required text, buttons, tooltips, or panels may clip or become unreachable at the approved minimum resolution and OS display scale. Those targets remain to be selected.
- **UI-02 — P0, Required:** Use text, shape, and icons alongside color for enemy warnings, prop paths, cooldown readiness, and downed states.
- **UI-03 — P1, Required:** Provide accessible text contrast, readable font sizes, predictable focus, and clear selection/disabled states. Audit keyboard access to critical menu actions.
- **UI-04 — P1, Decision:** Specify reduced flashes, reduced screen motion, text scaling, and other accessibility settings to include in the desktop release. These are not established current options.
- **UI-05 — P1, Decision:** Select supported languages and a text-storage/localization strategy. Existing mixed-language source comments do not establish multilingual player-facing support.

Acceptance: a first-time player can start, understand the timer objective, move, use both skills, choose an upgrade, purchase an item, pause, and resume without external explanation. Validate instructions with the actual behavior, not solely by reviewing their wording.

## 11. Audio and audiovisual feedback

The project contains background music, effects playback, mixer initialization/fallback logic, volume settings, and audio analysis used by neural/menu presentation.

- **AUD-01 — P0, Present:** Music and effects volume controls must affect their intended channels and survive supported transitions without unexpected volume resets.
- **AUD-02 — P0, Present:** Menu/combat music and important skill effects must start, stop, pause, or resume consistently. Re-entering a menu must not create stacked tracks or leaking playback resources.
- **AUD-03 — P0, Required:** An unavailable audio device or optional analysis dependency must not make the game unplayable; communicate actionable startup failures when required resources are missing.
- **AUD-04 — P1, Required:** Maintain a sound inventory for player attacks/skills, impacts, pickups, purchases, level-ups, enemy telegraphs, boss phases, companion evolution/downing, results, and UI actions. Mark missing cues explicitly.
- **AUD-05 — P1, Required:** Mix dense encounters so warnings and important feedback remain distinguishable; essential information also has a visual cue.

Acceptance: repeated gameplay/menu transitions do not duplicate audio; settings apply immediately as intended; mute works; audio failure leaves a responsive visual game; asset distribution rights are recorded.

## 12. Saves, restart, and state integrity

Desktop persistence uses JSON with atomic replacement. The source includes progress saves, versioned combat snapshots, input sanitization, pending-shop restoration, level-start baselines, and save export. Not every transient combat field is visibly represented in the general snapshot format; complete resume fidelity requires a field-by-field audit.

| ID | Requirement | Status / priority | Acceptance condition |
| --- | --- | --- | --- |
| SAVE-01 | Preserve run stage, player progression, currency, props, consumables/debt, biome state, shop offers/locks, and equipped companion progression. | Present / P0 | Load restores the same meaningful choices and values without reapplying bonuses. |
| SAVE-02 | Resume in-level state according to an explicit snapshot contract. | Partial / P0 | Position, HP, timer, obstacles/items, network context, enemies, bullets, companion state, and any omitted transient fields have a tested restore/reset policy. |
| SAVE-03 | Audit boss phases, enemy shields/statuses, active player skills, hazards/paint, wave timing, and projectile metadata for resume fidelity. | Required / P0 | Each field is saved or intentionally reset with a documented player impact; resume cannot duplicate rewards or bypass core encounter rules. |
| SAVE-04 | Distinguish Retry Level, Continue, Home, Exit, and New Run. Restore the correct baseline for retries. | Present/Partial / P0 | Repeating a stage cannot farm purchases, currency, consumables, XP, or companion growth through unintended state carryover. |
| SAVE-05 | Validate malformed/old saves and preserve recoverable data where possible. | Present/Partial / P0 | Bad fields do not crash launch; unsupported versions and corruption have clear recovery behavior. |
| SAVE-06 | Export the current save with a useful filename and reported destination. | Present / P1 | Exported content represents current progress and can be inspected; import UI is a separate decision. |
| SAVE-07 | Define autosave/checkpoint timing, visible save feedback, and write-failure handling. | Required / P0 | The player knows the practical resume point; failed writes do not silently appear successful. |

Keep save identifiers stable. Renaming a display label must not change legacy keys. A data migration must be specified before introducing incompatible fields or removing a saved feature. No cloud save, multiple-slot UI, or permanent account progression is assumed.

## 13. Narrative, endings, and deferred content

The following are retained as a backlog, not implemented release claims. Each must pass concept review and receive an implementation/asset specification before entering a milestone.

| Area | Deferred features from existing notes | Dependency |
| --- | --- | --- |
| Narrative endings | Remission, Stabilization, Silent Collapse, intermediate-collapse vignettes, The Empty Crown final encounter. | Approved campaign structure, boss-clear rules, path conditions, scripts, art/audio, and result routing. |
| Build-path progression | Higher-tier path unlocks, complete-path rewards, multi-path combinations. | One consistent path taxonomy and explicit thresholds/rewards; current props alone do not prove unlock logic exists. |
| Offense/status/crit | Bleeding Edge, Explosive Crits, Razor Focus, Frost Brand, Shock Relay. | Unique roles, proc rules, balance, feedback, and persistence. |
| Defense | Guardian Charm, Blood Pact, Retaliation Thorns, Shield Capacitor, Mirror Shell, Shardstorm, Retaliation Core. | Shield/damage order, caps, anti-loop rules, and clear risk/reward. |
| Economy | Black Market Pass, VIP Punchcard, Spoil Splitter. | Transaction order, payout limits, non-recursive reward generation, and shop UI. |
| Movement/control/paint | Time Dilation Boots, Sticky Tar Flask, Cleanse Step, Paint Converter; Phantom Dash only if a dash mechanic is approved. | Distinct gameplay roles and ground-effect/readability budgets. Teleport does not establish a dash feature. |
| Additional companions | Threadweaver, Bulwark Golem, Mender Sprite, Ember Hound, Frost Raven, Pack Tactics. | Individual design review, supernatural art, evolution progression, roster/loadout UI, and summon interaction rules. |
| Additional regions | Future environments after Region 04. | Finalized art and production assets before restoring region descriptions to active scope. |

Threadweaver's mechanical appearance was rejected and its design is deferred. Do not treat that historical draft as approved art. Other summon drafts likewise require distinct tactical roles and their own approved forms; they must not simply duplicate Eidolon's attacks under new colors.

## 14. Technical, performance, and distribution requirements

The current production entry point is `main.py`, loading `ZGame.py` and the extracted `zgame` systems. Python/Pygame remains the desktop implementation. Prototype files, `unity_draft`, and older `core`/UI scaffolding are not evidence that a second production game must be completed.

| ID | Requirement | Status / priority |
| --- | --- | --- |
| TECH-01 | Maintain a reproducible desktop dependency setup and one documented launch path, with required assets resolved independently of the user's shell working directory. | Partial / P0 |
| TECH-02 | Separate simulation results from optional rendering density. Cached art, spatial queries, and VFX limits must not silently remove damage, rewards, or status effects. | Present/Required / P0 |
| TECH-03 | Preserve deterministic environment generation and saved layout context. Art randomness must not perturb gameplay randomness. | Present / P0 |
| TECH-04 | Avoid unbounded projectile, particle, damage-text, pickup, trail, hazard, and cache growth. Release expired actors and surfaces. | Present/Required / P0 |
| TECH-05 | Keep actionable error logs and graceful startup/failure handling. Distinguish missing required assets from optional fallback conditions. | Partial / P0 |
| TECH-06 | Choose the minimum desktop hardware, operating-system versions, supported display sizes/scales, and a representative maximum-load scene. | Decision / P0 |
| TECH-07 | Target smooth 60 FPS desktop play; measure complete update/render/present frame time, p95/p99 stalls, cold startup, and input responsiveness on the selected hardware. | Required; target unverified / P1 |
| TECH-08 | Produce a self-contained desktop distribution with versioning, dependency/license inventory, asset credits, writable save location, and clean install/update behavior. | Required / P1 |
| TECH-09 | Verify the distribution on a clean machine without the developer's project paths or Python environment. | Required / P1 |
| TECH-10 | Document local diagnostics and balance metrics; external telemetry requires a separate product/privacy decision. | Required / P1 |

The retained desktop shimmer report shows representative render costs above a 16.67 ms frame budget. Network rendering was relatively inexpensive; environment/background work remained a larger cost. Those measurements are historical and are not proof of a current 60 FPS release. Performance work must preserve approved visual behavior and be evaluated on actual desktop scenes.

## 15. Validation and release acceptance

This PRD was prepared by reading source and existing documentation. No game, build, benchmark, or test suite was run for this documentation task. Existing reports are historical evidence, not fresh validation.

### Acceptance matrix

| Gate | Required evidence |
| --- | --- |
| Full player journey | Desktop launch → new run → skills → level-up → result → shop → next stage → save → quit → continue; also pause/home/retry/failure paths. |
| Combat correctness | Direct/projectile/area/DoT/summon damage, shields, wall hits, status expiry, critical hits, single death/reward resolution, and proc-chain bounds. |
| Progression/economy | Purchase/cap/discount/lock/reroll cases, XP choices, pickup limits, debt/interest/bounty settlement, and no re-entry/retry duplication. |
| Encounters | Representative enemy families, Bandit theft/escape/death, boss phases, twin enrage, telegraphs, hazards, and their save/resume rules. |
| Summons | All Eidolon levels, harvest caps/lifetime, storage/downing/reconstruction, beam, moving-viewport Procession, and turret placement/targeting. |
| Environment | Actual center/edge scenes, multiple seeds, camera movement, tall-wall occlusion, destruction, save/resume alignment, and a complete asynchronous breathing cycle. |
| UI/accessibility | Supported resolutions/scales, readable text/contrast, icons plus color, bindings, targeting instructions, disabled states, and menu accessibility. |
| Persistence | Fresh and older saves, malformed data, interrupted/failed writes, pending-shop saves, repeated resumes, and restart baselines. |
| Stability/performance | Representative dense combat and at least a 30-minute desktop session; no crashes, accumulating state, or uncontrolled memory growth. Record frame-time distributions and hardware. |
| Distribution | Clean-machine launch, bundled assets/audio, writable saves, version identification, credits/licenses, export, and safe update behavior. |

Existing verification tools include `tools/verify_bullet_runtime.py`, `tools/verify_game_state_runtime.py`, `tools/verify_summon_runtime.py`, `tools/verify_environment_runtime.py`, and `tools/verify_vessel_network.py`. Desktop preview/playtest tools and the retained captures support visual review. Their existence is not an acceptance result; use only the relevant native desktop paths when future verification is authorized.

Automated correctness checks alone cannot close visual acceptance. Review actual rendered scenes through a full breathing cycle. The user retains final artistic acceptance of Region 04.

Suggested product measures for future playtests: first-run instruction comprehension, successful use of both skills, deaths by source/stage, time to first upgrade, shop purchase/skip distribution, build diversity, boss engagement, summon contribution/downing, save-resume success, frame-time distribution, and crash-free session length. Numerical targets require baseline data; none are invented here.

## 16. Proposed delivery sequence

| Milestone | Scope | Exit condition |
| --- | --- | --- |
| M0 — Requirements alignment | Resolve naming, win/retry semantics, current source/spec mismatches, and the desktop target. | Decisions recorded and feature statuses agreed; no implied approval of deferred content. |
| M1 — Reliable playable baseline | Core loop, combat, current catalog, Eidolon/turrets, economy, menus, and saves. | P0 correctness and persistence gates pass with the current art preserved. |
| M2 — Region 04 acceptance | Only specifically requested refinements to the selected environment baseline. | Actual desktop visual review, full breathing cycle, world alignment, and accepted art/assets. |
| M3 — Desktop release readiness | Onboarding, UI/accessibility polish, audio completeness, performance, distribution, and release documentation. | Approved platform targets and release acceptance matrix satisfied. |
| M4 — Content expansion | Approved new props, companions, campaign/endings, then additional finalized regional asset sets. | Each addition has explicit scope, assets, balance, persistence, and acceptance evidence. |

No delivery dates, staffing assumptions, paid services, or implementation commitments are established by this document. Narrative/campaign work can be scheduled earlier if the user makes a finite campaign part of the next release.

## 17. Open decisions and known documentation gaps

| Decision/gap | Why it matters | Current handling |
| --- | --- | --- |
| Final game name and narrative terminology | Title, logo, menus, credits, and distribution must agree. | Keep project name Z_Game; record the three existing name variants. |
| Campaign endpoint and boss-clear conditions | Current timer survival differs from README's boss-defeat narrative. | Preserve runtime behavior; treat campaign/endings as unfinished design. |
| Failure retry versus fresh-run rules | Retry currently exists alongside a roguelike premise. | Document/test baseline restoration; decide intended release behavior. |
| Domain-selection UI | `Props` proposes a die; current shop picker uses hidden cards. | No redesign implied by this PRD. |
| Region art versus gameplay modifiers | Only Region 04 is active art scope, while existing modifier IDs remain. | Preserve compatibility and palette decisions; add no other region descriptions. |
| Prop balance conflicts | Some `Props` rows differ from catalog/settlement code, including Shady Loan and Wanted Poster. | Current source describes current behavior; reconcile exact values before final balance approval. |
| Path taxonomy and unlock rewards | README protocol names and `Props` path tags are not a complete implemented unlock system. | Use existing item behavior; defer new progression gates until specified. |
| Snapshot fidelity | General snapshots do not visibly enumerate every boss, hazard, projectile, and skill field. | Require a field-level persistence audit before claiming exact combat resume. |
| Accessibility and display targets | Release-readable UI needs defined resolutions, scale, and input coverage. | Record as requirements/decisions rather than existing options. |
| Performance and hardware baseline | Prior timings do not establish whole-loop 60 FPS. | Select a target machine and validate native presentation under representative load. |
| Desktop package, save location, and update policy | Source execution is not equivalent to a distributable product. | Require clean-machine packaging and compatibility checks. |
| Final asset/audio coverage and rights | A reference sheet is not a completed production inventory. | Maintain active/fallback/reference status and provenance before distribution. |

## 18. Source map and maintenance

| Source | Use in this PRD |
| --- | --- |
| [Project direction](../AGENTS.md) | Desktop scope, palettes, selected baseline, preservation, and visual acceptance. |
| [Props](Props) | Region 04 description, detailed prop/summon designs, pending path/UI requirements, and deferred catalog. |
| [README](../README.md) | Fictional setting, broad product vision, proposed protocols and endings; not implementation proof. |
| [main.py](../main.py), [ZGame.py](../ZGame.py), [app flow](../zgame/app_flow.py) | Launch, constants, skills/upgrades, timed loop, transitions, and restart behavior. |
| [World generation/pathing](../zgame/worldgen_pathing.py), [spawn logic](../zgame/spawn_logic.py) | Layout, routing, stage configuration, threat budgets, and boss scheduling. |
| [Enemy core](../zgame/enemy_core.py), [bosses](../zgame/enemy_subclasses.py), [hazards](../zgame/hazards.py) | Enemy roles, boss mechanics, and hazard foundations. |
| [Player projectiles](../zgame/player_projectiles.py), [game state](../zgame/game_state.py), [paint](../zgame/paint.py) | Combat effects, status/ground systems, and state integration. |
| [Shop catalog](../zgame/shop_support.py), [shop UI](../zgame/shop_ui.py) | Present purchasable roster, caps, offers, locks, rerolls, and domain picker. |
| [Summons](../zgame/summons.py), [summon VFX](../zgame/summon_vfx.py), [turrets](../zgame/turrets.py) | Allied actors, current Eidolon balance, abilities, persistence, and presentation. |
| [Menu flow](../zgame/menu_flow.py), [screens](../zgame/screens.py), [persistence](../zgame/persistence.py) | User journey, settings, results, saves, and export. |
| [Audio runtime](../zgame/audio_runtime.py), [asset paths](../zgame/paths.py), [requirements](../requirements.txt) | Playback, resource resolution, and dependency foundations. |
| [Environment assets](../assets/sprites/environment/README.md), [desktop shimmer report](../docs/region04-desktop-shimmer-validation.md) | Asset inventory, selected environment behavior, historical visuals and performance limits. |

Update this PRD when an approved decision changes scope or a feature's state. A feature moves from Present/Partial to accepted only with relevant functional evidence and, for art, actual desktop visual review. Keep detailed tuning in the maintained feature specification/source rather than duplicating conflicting formulas across documents.
