# Current Game — Product Requirements Document

Version: 1.1 draft | Updated: 2026-11-03 | Project: Z_Game

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

### 6.1. Purpose and shop requirements

Props turn currency earned during combat into a distinct build: stronger projectiles, persistent ground damage, shield sustain, allied attackers, or economic risk and reward. Purchases must offer a readable benefit and tradeoff before the player spends currency. In this section, "props" means purchasable gameplay items; Region 04 scenery and environment assets are specified in section 9.

The catalog and values below are a source-reviewed snapshot as of 2026-11-03, not final balance or evidence of completed gameplay acceptance. Preserve current behavior until a change is explicitly approved. Where older descriptions in `Props` disagree with the current catalog or effect code, record the discrepancy instead of silently changing the game.

- **SHOP-01 — P0, Present:** Offer a randomized catalog with rarity, current cost, description, ownership/level, and purchase eligibility. Keep four normal offers and the separate reroll mechanism readable.
- **SHOP-02 — P0, Present:** Preserve offer locks, rerolls, level/ownership price scaling, coupon discounts, caps, and shop save state. A completed transaction changes money and ownership exactly once.
- **SHOP-03 — P0, Present:** Display insufficient funds and maximum level clearly; locked/capped items cannot create a dead-end shop. An offer must produce the behavior stated on its card.
- **SHOP-04 — P0, Present:** Preserve interest, debt, protected currency, bounty windows, and Bandit interactions. Settlement order and shop re-entry must not produce duplicate payouts or repayments.
- **SHOP-05 — P0, Present:** Preserve the eligible Eidolon guarantee on every third distinct level's shop visit, including rerolls. If all four normal offers are locked, the temporary extra offer must preserve those locks. At Eidolon's cap, use ordinary eligible offers.
- **SHOP-06 — P1, Required:** Show current/next values, meaningful tradeoffs, debt remaining, relevant payout limits, path identity, and consumable duration in concise player-facing language.
- **SHOP-07 — P1, Decision:** Reconcile the proposed four-sided die domain-selection flow in `Props` with the current hidden-card picker. Define what the player chooses, when the domain is revealed, and what confirmation means.

### 6.2. Catalog, acquisition, and ownership

All 21 props below are present in `zgame/shop_support.py`. Base costs use earned in-game currency; the final card price includes scaling and discounts. Rarity is the catalog's numeric tier, not a guaranteed drop probability. Reroll is a separate shop action and does not occupy a build slot.

| Family | Item / stable ID | Base cost | Rarity | Current limit and purchase result |
| --- | --- | ---: | ---: | --- |
| Ballistic | Piercing Rounds / `piercing_rounds` | 12 | 1 | Level 5; add one piercing charge per purchase. |
| Ballistic | Ricochet Scope / `ricochet_scope` | 14 | 2 | Level 3; add one ricochet charge per purchase. |
| Ballistic | Shrapnel Shells / `shrapnel_shells` | 16 | 3 | Level 3; improve fragment trigger chance. |
| Ballistic | Explosive Rounds / `explosive_rounds` | 18 | 2 | Level 3; improve kill-explosion damage and radius. |
| Status | D.O.T. Rounds / `dot_rounds` | 20 | 2 | Level 3; improve tick damage, duration, and stack capacity. |
| Status / ballistic | Mark of Vulnerability / `mark_vulnerability` | 22 | 3 | Level 3; improve mark frequency, damage amplification, and duration. |
| Ground effects | Curing Paint / `curing_paint` | 12 | 2 | Level 3; improve footprint damage, lifetime, and radius. |
| Ground effects | Ground Spikes / `ground_spikes` | 18 | 2 | Level 3; improve hazard damage, lifetime, and active limit; reduce movement speed. |
| Defense | Carapace / `carapace` | 6 | 1 | No catalog purchase cap; add 20 reserve shield HP. |
| Defense | Bone Plating / `bone_plating` | 12 | 2 | Level 5; improve plating regeneration; reduce movement speed. |
| Defense | Aegis Pulse / `aegis_pulse` | 28 | 3 | Level 5; improve shield-enabled pulses. |
| Economy | Coin Magnet / `coin_magnet` | 10 | 1 | Level 5; add 60 px to pickup reach per level. |
| Economy | Coupon / `coupon` | 10 | 1 | Level 4; increase the run's shop discount. |
| Economy | Golden Interest / `golden_interest` | 12 | 2 | Level 4; increase interest rate and payout cap. |
| Economy / lucky | Shady Loan / `shady_loan` | 0* | 3 | Three active debt tiers; add money, debt, and one repayment step. |
| Economy | Lockbox / `lockbox` | 14 | 2 | Level 4; increase the protected share of current currency. |
| Economy / status | Bandit Radar / `bandit_radar` | 18 | 2 | Level 4; strengthen and extend the Bandit spawn slow. |
| Economy / lucky | Wanted Poster / `wanted_poster` | 15 | 2 | No catalog purchase cap; add two upcoming level activations to the bounty window. |
| Allied damage | Auto-Turret / `auto_turret` | 14 | 2 | Level 5; add one orbiting turret per level. |
| Allied damage | Stationary Turret / `stationary_turret` | 14 | 1 | Owned-count cap 99; add one placement attempt per upcoming level. |
| Companion | Eidolon / `evolving_skull` | 18 | 2 | Level 6; first purchase equips one companion; later purchases evolve that actor. |
| Shop action | Reroll / `reroll` | 3 | — | Repeatable while affordable; refresh unlocked offers. |

*Shady Loan's catalog base cost is zero, but the current shared price function floors the payable cost at one coin. This discrepancy must be resolved before describing the offer as free; this PRD does not change that behavior.*

**PROP-01 — P0, Required:** Distinguish permanent-for-the-run levels, remaining consumable resources, owned actor counts, and active debt state. Do not present all of them as identical upgrade tracks. Carapace's displayed canonical level is derived from remaining reserve in 20-HP units, Wanted Poster tracks its remaining window, and Shady Loan tracks an active cycle. Those values can decrease without selling an item.

**PROP-02 — P0, Required:** Apply a purchase once, update its live benefit, remove the purchased offer and its lock, refresh the displayed currency and ownership, and preserve the result when leaving or saving the shop. If all normal slots are exhausted, the current shop generates another set. Purchases should never be mistaken for persistent account unlocks; ordinary prop ownership belongs to the current run.

**PROP-03 — P1, Decision:** Selling, refunds, inventory capacity, and manual placement are not established features of the current prop shop. Do not design dependent mechanics around them until their rules are approved. Companion equip/store behavior is separate and is covered in section 7.

### 6.3. Build paths and identity

Path tags help players recognize a build and compare offers. The current path score sums each tagged item's canonical level/count; dual-tagged items contribute to both paths. Scores are not counts of distinct pieces. The UI thresholds are 2 for **online** and 4 for **full**, so one level-4 item can reach full. Consumable depletion or debt resolution can reduce a score.

| Path | Current contributors | Presentation and intended role |
| --- | --- | --- |
| Ballistic | Piercing, Ricochet, Shrapnel, Explosive, Mark | Orange; projectile reach and kill conversion. |
| Turret | Auto-Turret, Stationary Turret | Cyan; supporting firing positions. |
| Shield | Carapace, Bone Plating, Aegis | Blue; damage absorption and shield-enabled offense. |
| Status | D.O.T., Curing Paint, Ground Spikes, Mark, Radar | Green; lingering damage, vulnerability, and control. |
| Economy | Magnet, Coupon, Interest, Lockbox, Radar, Wanted, Loan | Gold; collection, spending, protection, and risk. |
| Summoner | Eidolon | Violet; an evolving mobile ally. |
| Lucky | Wanted, Loan | Pink; risk/reward identity shared with economy. |

**PROP-04 — P1, Required:** Show path name as well as color, owned state, and the effect of the proposed purchase. Path colors identify item families and do not replace the approved ground-network palettes. Current path thresholds provide build labels; they must not promise damage bonuses, unlocks, or set effects that are not implemented. Proposed distinct-piece sets are separate in section 6.10.

### 6.4. Projectile, status, and ground-effect requirements

Values separated by slashes correspond to successive item levels. Damage percentages below use the current player bullet-base damage unless stated otherwise; they are effect coefficients, not guaranteed final damage after all modifiers. Tile-relative measurements use the existing world cell size. Final balance remains subject to playtesting.

| Prop | Current effect and scaling | Required behavior and presentation |
| --- | --- | --- |
| Piercing Rounds | One additional piercing charge per level, up to five. | Make remaining projectile continuation distinct from ricochet. Verify combined charges and collision order; one overlap must not damage the same target repeatedly without a valid new hit. |
| Ricochet Scope | One additional ricochet charge per level, up to three. | Redirect only toward eligible targets using current targeting rules. Handle no available target and an exhausted charge pool without a stuck projectile. |
| Shrapnel Shells | Eligible lethal player hits have a 25% / 35% / 45% chance to emit 3–4 fragments. Each fragment uses 40% of HP actually removed by the lethal hit, rounded with a minimum of one damage; range is half the player's range and speed is 85% of bullet speed. | Explain that this is an on-kill chance, not extra bullets on every shot. Fragments start without pierce/ricochet charges and cannot generate further shrapnel. Overkill and absorbed damage must not inflate the HP-loss basis. |
| Explosive Rounds | Eligible player-source kills explode for 25% / 35% / 45% damage in a 0.65 / 0.80 / 0.95-tile radius. Boss coefficient is 50% of that damage. | One death may produce only one explosion from this effect. Preserve the existing queued chain handling; do not describe it as an unconditional ban on all chains. Radius, damage feedback, and boss reduction must agree. |
| D.O.T. Rounds | Tick every 0.5 s for 10% / 16% / 22% damage per stack, lasting 2.5 / 3 / 3.5 s. Stack caps are 1 / 1 / 2. Boss coefficient is 70%. | At the cap, a new application replaces the oldest stack. Show a recognizable status indicator and preserve fractional damage accumulation rather than rounding weak ticks away. |
| Mark of Vulnerability | Apply a mark every 5 / 4 / 3 s; marked enemies take 15% / 22% / 30% extra damage for 5 / 6 / 7 s. Choose an unmarked living boss first, otherwise an elite, otherwise another enemy; selection within a priority group is random. | The mark must be visible without obscuring enemy telegraphs. Multiple enemies can be marked as timers overlap; this is not permission to stack the same vulnerability bonus repeatedly on one target. |
| Curing Paint | Footprints use a 0.25-s spawn interval and 0.50-tile movement-distance setting. Radius is 0.60 tile × 1.15 / 1.30 / 1.50; lifetime is 2 / 3 / 4 s. Base ticks are 4% / 6% / 8% every 0.5 s, with a 70% boss coefficient. | This is damaging ground coverage, not healing. Preserve the existing kill-based growth factor, `1 + 0.002 × floor(kills / 10)`, and current footprint intensity/overlap rules. State sustained coverage separately from raw tick coefficients. |
| Ground Spikes | Spawn settings are 0.35 s and 0.75 tile of travel. Damage is 30% / 40% / 50%; lifetime 3 / 4 / 5 s; active limit 6 / 10 / 14; trigger radius 0.28 tile. A hit slows movement by 5% for 1 s. Each purchase multiplies the player's speed multiplier by 0.96, subject to its 0.30 floor. | Spikes are one-hit hazards. Show the movement penalty before purchase and the active hazard footprint in combat. Expiry, consumption, and replacement at the active limit must release their gameplay state. |

**PROP-05 — P0, Required:** Define eligible damage sources for every hit, kill, status, and proc. Current player-source fragments may still interact with D.O.T. and explosions even though recursive shrapnel is blocked. Do not assume all secondary attacks inherit every player prop, or that every secondary effect is prohibited from triggering another effect.

**PROP-06 — P0, Required:** Audit source attribution across player bullets, fragments, explosions, ground effects, turrets, and Eidolon. Auto-Turret explicitly emits turret-source bullets, while Stationary Turret's current creation call relies on the default bullet source. Their inheritance must be reconciled before the UI promises uniform turret behavior. Record this as a current consistency gap, not an approved balance change.

**PROP-07 — P0, Required:** Process each death, coin reward, bounty, and eligible kill effect once, including simultaneous damage and chained kills. Cleanup must remove dead targets and expired hazards from effect processing. Visual culling must not remove damage that the simulation still owes.

### 6.5. Defense and allied damage

| Prop | Current effect and scaling | Required behavior and presentation |
| --- | --- | --- |
| Carapace | Each purchase adds 20 reserve shield HP. The reserve is spent when absorbing damage. There is no catalog purchase cap. | Display remaining HP rather than implying permanent maximum-shield growth or free replenishment every level. Purchase history and remaining protection are different values. |
| Bone Plating | Regenerate 2 / 4 / 6 / 8 / 10 plating HP every 6 s; level entry resets the accumulated plating and regeneration timer. Each purchase multiplies the movement-speed multiplier by 0.98, subject to its 0.30 floor. At level 5, positive plating can negate the remaining hit while consuming up to two plating HP. | Show regeneration, speed cost, and the level-5 rule independently. Define and verify any reserve cap across gameplay and saves before promising one; the regeneration loop alone does not establish a storage cap. |
| Aegis Pulse | Requires positive base shield, Carapace reserve, or plating. Radius is 100 / 120 / 140 / 160 / 180 px; nominal damage per wave is 30% / 45% / 60% / 80% / 100% of player maximum HP. Cooldown is 4 / 3.375 / 2.75 / 2.125 / 1.5 s. Wave count is 1 / 2 / 3 / 3 / 3, spaced 0.35 s apart. | Show when the effect is inactive for lack of shielding. Distinguish damaging waves from decorative rings, and apply existing domain modifiers consistently rather than displaying nominal coefficients as final damage. |
| Auto-Turret | Owned level determines orbiting turret count, one through five. Turrets follow the player and select nearby living enemies within their effective range. | Recreate the correct count on level entry without duplicating actors. Expose count, attack interval, range, and actual damage; do not imply purchases raise per-turret damage unless the source does so. |
| Stationary Turret | Owned count supplies placements each level. Current placement searches up to 40 candidate tiles per turret, skips occupied obstacle tiles, and registers a successfully placed turret as an obstacle. | Keep navigation and shots consistent with the placed footprint. A failed placement must not silently erase ownership. Define player feedback for crowded maps; 99 is a catalog cap, not proof that every layout can host 99 turrets. |
| Eidolon | One unique actor evolves from Bloombone to Soulflame to Rift Skull through six purchases. It has its own health, harvesting, skills, and equip/store state. | Use section 7 for level stats and ability requirements. Preserve the `evolving_skull` save ID; upgrading must not create an extra Eidolon or consume turret capacity. |

**PROP-08 — P0, Required:** Preserve and explain the current player damage-absorption order: base shield, Bone Plating, Carapace reserve, then HP. Test the level-5 plating exception with partial shielding and large hits. Do not substitute a proposed temporary-shield system for the existing reserves.

**PROP-09 — P1, Required:** Show actual compounded movement penalties when Bone Plating and Ground Spikes coexist. Maintain readable ally silhouettes and projectile ownership against Region 04's subdued ground network, obstacles, and enemy attacks. Ally effects must not require changes to the approved environment geometry or lighting baseline.

### 6.6. Economy, debt, and Bandit interactions

| Prop | Current effect and scaling | Required explanation |
| --- | --- | --- |
| Coin Magnet | +60 px pickup reach per level; +300 px at level 5. | Show added reach or the resulting total with a clear label. The bonus is not the player's entire pickup radius. |
| Coupon | 5% / 10% / 15% / 20% discount within the run. | Show the actual rounded payable price, including the minimum price. Recalculate affected offers and reroll cost immediately after purchase. |
| Golden Interest | On shop exit, pay `floor(current coins × 5% × level)`, capped at 30 / 50 / 70 / 90 coins. | Show expected payout and cap; spending before exit reduces the interest basis. Interest is settled before loan repayment in the current exit flow. |
| Lockbox | Protect 25% / 40% / 55% / 70% of the currency held immediately before an applicable loss, rounded down. | Protection is recomputed for each event; it is not a separate permanent bank balance. Ordinary voluntary purchases still spend coins. Protection can leave loan debt unpaid and therefore does not prevent default. |
| Bandit Radar | On Bandit spawn, apply an 8% / 12% / 16% / 20% slow for 2 / 3 / 4 / 5 s, with tracking feedback. | Distinguish a temporary spawn slow from permanent enemy slowdown. Keep the Bandit readable among normal enemies. |
| Wanted Poster | Each purchase adds two upcoming level activations. Level entry consumes one remaining activation and arms the bounty for that level. A qualifying Bandit kill pays `30 + stolen_total` bounty and clears the remaining window. | Show remaining activations and whether the current level is armed. The bounty is separate from ordinary stolen-coin return. Do not call this three independent bounty charges or a permanent leveled stat. |
| Shady Loan | Active tiers grant 80 / 120 / 160 coins while adding 96 / 144 / 192 debt. Each purchase adds one repayment step and grants purchase-level grace. | Present the loan grant, payable purchase cost, total debt, active tier, remaining steps, and default consequence together. This is a debt cycle, not a permanent three-level passive. |

**Loan settlement contract — P0, Present behavior with acceptance still required:**

1. Purchasing during an active debt cycle increases its tier up to three and adds the corresponding grant, debt, and one step. At active tier three with debt outstanding, further purchases are capped. Resolving the cycle permits a later loan; the cap is not a lifetime purchase limit.
2. The purchase level is a grace period. Closing its shop must not immediately collect a repayment or consume a repayment step.
3. At a later regular repayment step, request 25% / 30% / 35% of available coins, rounded down and capped at 50 / 80 / 110. Limit the request to available coins and remaining debt, then apply Lockbox protection.
4. At the final step, attempt to collect all remaining debt rather than using the regular percentage/cap. Available funds and Lockbox protection still limit the actual payment.
5. Any debt remaining after that final collection causes default: reduce maximum HP by 30% / 35% / 40% for the active tier, with maximum HP never below one, and clear the debt cycle. Record the default outcome and update carried player health consistently.
6. Successful repayment clears the active cycle. Historical last-tier/status data is distinct from currently owned prop level.

The current code uses fields named "waves" for repayment and bounty windows, but the relevant transitions are level entry/shop exit. Player-facing copy must identify the actual transition rather than confusing it with a timed enemy spawn wave. A single-tier loan with only one remaining step goes directly from its grace period to final collection at the next eligible settlement.

**PROP-10 — P0, Required:** Make settlement order explicit: resolve the shop-exit interest payout before calculating the loan payment. Protect against duplicate payouts or collections if the following domain picker is canceled, the shop reopens, or the session resumes. These are acceptance requirements, not a claim that every re-entry path has already passed.

**PROP-11 — P1, Required:** Explain outcomes with a short receipt: balance before settlement, interest earned, requested debt payment, amount actually paid, protection applied, debt remaining, and any default penalty. For example, Lockbox level 4 protects 70 of 100 coins from one applicable loss; it does not guarantee those same 70 coins remain protected through every later event. With 100 coins and Interest level 2, interest adds 10 before a subsequent loan calculation uses the resulting balance.

### 6.7. Pricing, offers, locks, and rerolls

For ordinary items, the present pricing calculation is:

`scaled = round(base cost × 1.12^stage index × (1 + 0.02 × stage index) × 1.15^owned level)`

`payable = max(1, round(scaled × (1 − 0.05 × Coupon level)))`

Stage index is zero-based and Coupon level is capped at four. Use the game's existing rounding behavior at both stages. "Owned level" is the canonical value for that prop, including reserve/window/count-based values; it is not always the number of previous purchases. Reroll uses its base cost and Coupon discount with the same one-coin minimum, without ordinary stage/ownership scaling in the current price function. Do not infer an escalating reroll schedule from unused tuning constants.

- **PROP-12 — P0, Required:** The displayed price, affordability state, amount deducted, and saved balance must agree. Buying Coupon must refresh prices; a zero-base item must not display a free purchase if the shared function charges one coin.
- **PROP-13 — P0, Required:** Keep four normal offers, a separate reroll action, and up to four preserved locks. Rerolls retain valid locks and exclude capped candidates. Rarity weights vary with stage; do not publish invented fixed odds. The selection fallback for a small eligible pool may repeat candidates, so uniqueness must not be promised without revising that behavior.
- **PROP-14 — P0, Required:** Preserve the existing Eidolon guarantee on every third distinct level's shop visit, including rerolls while eligible. If all four offers are locked, use the temporary fifth offer without replacing a lock. Do not let repeatedly opening one level's shop count as additional levels.
- **PROP-15 — P1, Required:** Explain lock state, cap state, unaffordable state, and empty purchased slots independently. Provide clear feedback for a rejected purchase without taking money or advancing item state.

### 6.8. Item cards, feedback, and content requirements

The compact shop card must communicate name, icon, rarity, path labels, actual price, current ownership/resource state, next purchase result, and any immediate drawback. The expanded detail view must provide trigger, target, damage basis, cooldown, duration, stacking/cap, boss differences, and relevant interactions. Put health penalties, movement penalties, debt, and consumable expiry ahead of flavor copy. Keep essential rules available even if the compact tooltip must truncate text.

**PROP-16 — P1, Required:** Use different state labels where appropriate: "Level 2 → 3," "Shield reserve 15 → 35 HP," "Turrets 2 → 3," "Bounty window +2 levels," and "Borrow 80; add 96 debt." The Loan card must separately show its actual purchase price and repayment deadline. At a cap, show "Max" rather than a misleading next value.

**PROP-17 — P1, Required:** The pause/build summary must use the same values as the shop and combat state. Show passive levels, actor counts, remaining shield resources, bounty activation, loan debt/steps, and path scores. A depleted consumable must not remain displayed as a fully active permanent bonus.

**PROP-18 — P1, Required:** Maintain an asset entry for each prop: stable ID, player-facing name, family icon, rarity treatment, shop/pause icon, combat indicator where applicable, activation/impact/expiry feedback, sound cue, and fallback status. Distinguish purchase success, insufficient funds, upgrade, cap, loan payment/default, and bounty redemption. Missing bespoke art must not make the item unidentifiable or hide its state.

**PROP-19 — P1, Required:** Convey statuses through text/shape as well as color. Dense shrapnel, paint, spikes, pulses, and allied shots must preserve player visibility, enemy attack warnings, and obstacle boundaries. Specify effect limits and audio concurrency without changing damage or rewards to match the number of rendered effects. Review these on native desktop scenes when implementation is tested.

### 6.9. Data, save, and lifecycle contract

Each prop specification must contain the following before it is implemented or substantially revised:

| Area | Required definition |
| --- | --- |
| Identity and acquisition | Stable save/catalog ID; name; role; path tags; rarity; base price; offer eligibility; cap; first purchase versus repeat purchase. |
| Effect | Eligible trigger and damage source; target filters; range/shape; value per level; rounding; cooldown; duration; stacking/replacement; boss behavior; movement or health tradeoff. |
| Interactions | Which effects can trigger other effects; attribution of kills/rewards; order of damage modifiers and shields; chain termination; interaction with domain modifiers. |
| Lifecycle | When the effect starts; what persists between levels; what expires; equip/store behavior where relevant; failure retry, restart, new-run, and load behavior. |
| Persistence | Owned level/count; remaining consumable resources; active economy state; any combat snapshot state; defaults for older saves; valid ranges and migration behavior. |
| Presentation | Short and expanded descriptions; current/next values; icons; VFX and sound; disabled/max/depleted states; pause summary and settlement feedback. |
| Acceptance | Acquisition, upgrade, cap, effect, interaction, transition, save/load, and worst-case load scenarios with expected results. |

**PROP-20 — P0, Required:** Save ownership separately from transient effect instances. Persistent level/count must not cause a second purchase effect when reconstructing a player or spawning allies. Persist the shop's offers/locks and economy cycle consistently with its balance. Preserve stable IDs, including legacy Eidolon naming.

**PROP-21 — P0, Required:** Restore the intended retry baseline for consumable shielding and bounty state, alongside ordinary prop levels and player multipliers. A fresh run must reset run-only benefits and debt according to the game-wide reset rules. Loading older saves must neither award free items nor preserve an impossible active debt state.

**PROP-22 — P0, Required:** Audit combat snapshot coverage for active statuses, footprints, spikes, pulses, turrets, and companion state before promising exact mid-combat continuation. Define whether each timer/effect resumes or is deliberately reconstructed. Section 12's persistence requirements apply; presence of a save field alone does not establish full effect fidelity.

### 6.10. Proposed props and set bonuses

The following are design backlog from `Props`, not additions to the current purchasable roster. Section 13 remains the broader deferred-feature list. A proposal needs a completed item contract, approved balance, assets, and acceptance evidence before it becomes a release requirement.

| Deferred group | Named proposals | Required design resolution |
| --- | --- | --- |
| Projectile and elemental builds | Bleeding Edge, Explosive Crits, Razor Focus, Frost Brand, Shock Relay | Define critical-hit interactions, bleed/chill/chain rules, boss resistance, and how each differs from existing D.O.T. or Explosive Rounds. |
| Defense and retaliation | Guardian Charm, Blood Pact, Retaliation Thorns, Shield Capacitor, Mirror Shell, Shardstorm, Retaliation Core | Define damage/health costs, shield ownership, reflection eligibility, trigger cooldowns, and protection against retaliation loops. |
| Economy | Black Market Pass, VIP Punchcard, Spoil Splitter | Specify offer access, discount stacking, payout timing, and interaction with Coupon, Interest, Lockbox, and loans. |
| Movement and ground control | Time Dilation Boots, Sticky Tar Flask, Cleanse Step, Paint Converter, Phantom Dash | Specify movement/status behavior and ground-effect conversion. Phantom Dash depends on an approved dash mechanic and input flow. |
| Companions and summon support | Threadweaver, Bulwark Golem, Mender Sprite, Ember Hound, Frost Raven, Pack Tactics | Define roles, capacity/equip rules, targeting, survival/revival, scaling, and save data alongside Eidolon. |

`Props` also proposes **Ballistic Engine** (Piercing + Ricochet, with Shrapnel as a third piece), **Fortress Loop** (Carapace + Bone Plating, with Aegis), **Predator Economy** (Wanted + Radar, with Lockbox), and **Cold Circuit** (Frost Brand + Shock Relay, with D.O.T.). These named bonuses must not be inferred from the current online/full path labels.

**PROP-23 — P2, Deferred:** Before implementing sets, approve exact two-/three-piece bonuses, distinct-item counting, consumable depletion behavior, activation/deactivation timing, and a visible set summary. Resolve whether percentage changes add percentage points or multiply a rate, and cap any proc chance appropriately. Cold Circuit also depends on props absent from the current catalog. Selling-related set recomputation is out of scope until selling exists.

### 6.11. Prop acceptance matrix

These are required future checks for the desktop build, not tests executed as part of this documentation update. Every catalog item needs an acquisition-to-effect check; the combined scenarios below cover failures that individual item checks miss.

| ID / priority | Scenario | Pass condition |
| --- | --- | --- |
| PROP-A01 / P0 | Buy each item at first level, intermediate levels, and its limit; attempt purchase without funds. | One debit and one benefit per successful transaction; correct cap/resource state; rejected purchases leave state unchanged. |
| PROP-A02 / P0 | Buy Coupon with other offers locked; reroll; exhaust normal offers; reload the shop. | Prices, locks, offers, eligibility, currency, and ownership remain consistent without granting free rerolls or purchases. |
| PROP-A03 / P0 | Reach a guaranteed Eidolon shop with zero through four locks and with Eidolon capped. | Eligible guarantee survives rerolls; four locks remain intact; capped Eidolon is excluded; same-level re-entry does not advance the guarantee counter. |
| PROP-A04 / P0 | Combine Piercing, Ricochet, Shrapnel, Explosive, D.O.T., and Mark against clustered enemies and a boss. | Correct charge consumption, source eligibility, stack replacement, boss coefficients, and one death/reward per enemy; chains terminate. |
| PROP-A05 / P0 | Keep paint/spikes active while moving, pausing, reaching effect limits, and transitioning levels. | Correct damage/slow/lifetime, no repeated one-hit spike triggers, no unintended stationary spawning, and no stale collision/damage state. |
| PROP-A06 / P0 | Take small and large hits with mixed shield reserves, including level-5 Bone Plating; let all reserves expire. | Correct absorption order and plating exception; Carapace falls by actual consumption; Aegis eligibility and wave damage match the remaining protection. |
| PROP-A07 / P0 | Run Interest, Coupon, Lockbox, and all Loan tiers through grace, regular repayment, final repayment, and default. | Correct calculation order, actual price, debt/step updates, protected losses, and maximum-HP penalty; receipts match saved state. |
| PROP-A08 / P0 | Cancel the post-shop picker, reopen, save/load, or retry near a settlement. | No duplicate interest, loan collections, bounty activations, or purchase effects; intended retry baseline is restored. |
| PROP-A09 / P0 | Kill a wanted Bandit through player, turret, ground-effect, and companion damage; allow another window to expire. | Each supported kill path gives the intended bounty and stolen-coin return exactly once, clears the window correctly, and does not grant expired rewards. |
| PROP-A10 / P0 | Enter successive levels with both turret types and Eidolon; use a crowded layout. | Counts/evolution persist, actors are not duplicated, stationary placement respects navigation, and placement failures preserve ownership. |
| PROP-A11 / P1 | Compare shop, expanded details, pause summary, combat feedback, and saved state at representative resolutions. | Matching current/next values and resource labels; readable costs/penalties; path labels do not imply unimplemented bonuses. |
| PROP-A12 / P1 | Stress a high-level mixed build in the approved Region 04 desktop scene. | Readable actors and enemy telegraphs, bounded effect processing, correct damage/rewards under visual limits, and compliance with the game's performance targets. |

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
| --- | --- | --- | --- | --- |
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
| [Player/entity core](../zgame/entity_core.py) | Bone Plating regeneration and level-entry reset behavior. |
| [Shop catalog](../zgame/shop_support.py), [shop UI](../zgame/shop_ui.py) | Present purchasable roster, caps, offers, locks, rerolls, and domain picker. |
| [Summons](../zgame/summons.py), [summon VFX](../zgame/summon_vfx.py), [turrets](../zgame/turrets.py) | Allied actors, current Eidolon balance, abilities, persistence, and presentation. |
| [Menu flow](../zgame/menu_flow.py), [screens](../zgame/screens.py), [persistence](../zgame/persistence.py) | User journey, settings, results, saves, and export. |
| [Audio runtime](../zgame/audio_runtime.py), [asset paths](../zgame/paths.py), [requirements](../requirements.txt) | Playback, resource resolution, and dependency foundations. |
| [Environment assets](../assets/sprites/environment/README.md), [desktop shimmer report](../docs/region04-desktop-shimmer-validation.md) | Asset inventory, selected environment behavior, historical visuals and performance limits. |

Update this PRD when an approved decision changes scope or a feature's state. A feature moves from Present/Partial to accepted only with relevant functional evidence and, for art, actual desktop visual review. Keep detailed tuning in the maintained feature specification/source rather than duplicating conflicting formulas across documents.
