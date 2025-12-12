# Z_Game

## 目录结构

- core/: 游戏逻辑
- ui/: UI 渲染
- assets/: 图片资源
- main.py: 启动入口

## 运行方式

1. 安装 pygame：`pip install pygame`
2. 补全 assets/ 下图片
3. 运行 `python main.py`rs

# NEURONVIVOR  
*Alzheimer's Memory Survivor*

> A roguelike "survivor" game that takes place inside the brain of an Alzheimer's patient.  
> You are an experimental therapy protocol fighting to keep neurons alive long enough to reach remission.

---

## World View

Everything in **NEURONVIVOR** happens inside a single human brain.

The patient has Alzheimer’s disease. Neurons are dying, memories are fracturing, and misfolded proteins spread like monsters through fragile neural networks.

You play as a composite **healing agent** – a mix of:

- Experimental drugs  
- Nanobot swarms  
- Neurotransmitter boosters  
- Cognitive training protocols  

Each run is one **treatment cycle** injected into the patient’s brain.  
Every enemy, boss, and map is a stylized representation of real Alzheimer’s pathology:  
plaques, tangles, neuroinflammation, collapsing memory networks.

Your goal is not just to “win a game” but to buy this brain more time –  
or, in the rarest cases, push it all the way into **Remission**.

---

## Core Gameplay

**NEURONVIVOR** is a top-down, wave-based roguelike built in Python / Pygame, inspired by “survivor” style games.

### Basic Loop

1. **Enter a Brain Domain**  
   - Each stage is a different neural region (memory circuits, language centers, spatial networks, etc.).  
   - Enemies spawn in waves, representing disease spreading through that network.

2. **Survive the Swarm**  
   - Move to dodge, kite, and control the flow of enemies.  
   - Your attacks and skills are mostly automated or semi-auto; your main job is **positioning, pathing, and build choice**.

3. **Collect Resources & Props**  
   - Defeated enemies drop coins / nutrients and sometimes props.  
   - Between waves or at certain checkpoints, you enter a **Shop** where you buy or upgrade props (equipment) that define your build.

4. **Face Boss Nodes**  
   - Each major brain region is guarded by a boss that embodies a symptom cluster  
     (e.g., Memory collapse, language breakdown, spatial confusion).  
   - Defeating a boss stabilizes that region and unlocks higher-tier props in certain paths.

5. **Repeat, Scale, and Decide**  
   - As you go deeper, enemies evolve, props get more synergistic, and your choices lock you into **paths**.  
   - The final confrontation determines which **ending** you unlock.

---

## Objectives

### Short-term

- Survive each wave.  
- Choose props that synergize with your current build and the enemies you’re facing.  
- Manage your economy: when to save, when to invest, when to reroll for better options.

### Long-term

- **Stabilize** as many brain regions as you can across a run.  
- Unlock and climb multiple **build paths (protocols)** to higher-tier equipment.  
- Reach the final boss with a strong multi-path build and push the disease into:
  - **Remission** (rare true ending), Condition (example):
                  Defeat The Empty Crown, AN
                  Have reached a threshold in 2+ specific prop paths 
                  (e.g., ≥4 items from Immuno path + ≥4 from Reserve path), 
                  representing combined advancetherapy + cognitive reserve.
  - **Stabilization** (more common but still a success), or  
  - One of several **collapse endings** if the treatment fails at different stages.
   based on the player's build, the same path will unlock the higher value props,
   and when unlocking two or more specific paths to concur the final boss reach 
   the rare true end - Remission. Normal defeating the final boss, but the props 
   unlock did not meet the requiremnt will reveal normal ending - Stablization. 
   If player died in the game play reveal the ending - Slient Collapse, 
   If player kills the first boss, then can not make to the second, die in middle, reveal another ending.

---

## Build Paths (Protocols)

Props = the items/equipment you buy in the shop or gain from bosses.  
They’re grouped into “flows” / **protocols** that describe different playstyles **and** different real-world treatment metaphors.

Below are the core paths currently planned/implemented, based on the `Props` design.

### 1. Ballistic Protocol – 弹道流 (Pierce / Ricochet / Shrapnel)

**Fantasy:** You focus on raw firing geometry: bullets as neural impulses carving paths through corrupted tissue.

**Examples (from props):**

- **Piercing Rounds** – Bullets pass through multiple enemies, keeping damage high across each hit.  
- **Ricochet Rounds** – Shots bounce between enemies, great for dense swarms.  
- **Shrapnel** – On hit or kill, bullets fragment into extra projectiles that clear crowds.

**Playstyle:**  
High DPS, high range, rewards good positioning.  
Works great with on-hit effects and control props.

**In-world metaphor:**  
Sharper, more focused electrical signals detonating clusters of pathology before they spread.

---

### 2. Turret Protocol – 炮台流 (Auto / Stationary)

**Fantasy:** Install semi-autonomous “micro-treatment stations” inside the brain.

**Examples:**

- **Auto-Turret** – A small turret that follows you and fires at nearby enemies.  
- **Stationary Turret** (concept) – Set-and-forget turrets that lock down choke points.

**Playstyle:**  
You create **zones of denial**. Great for players who like to lure waves into prepared killboxes or play more defensively.

**In-world metaphor:**  
Localized infusion pumps or nanobot nests set up in strategic neural hubs.

---

### 3. Shield / Bastion Protocol – 护盾流 (Carapace, Bone Plating, Aegis)

**Fantasy:** You don’t just heal; you reinforce.  
This path builds protective layers around neurons and turns defense into offense.

**Key props:**

- **Carapace** – A one-time big shield that soaks a lethal hit.  
- **Bone Plating** – Small layers of armor that come back over time, encouraging tanky play.  
- **Aegis Pulse** – While any shield is active, periodically emits a **hexagonal pulse** that damages nearby enemies.  
- **Mirror Shell** – Reflects a portion of ranged damage back to attackers while shielded.

**Playstyle:**  
Bruiser / fortress. You walk into swarms, let them crash on your shields, and destroy them with pulses and thorns.

**In-world metaphor:**  
Glial barriers, controlled neuroinflammation, and neuroprotective drugs that create safe pockets where neurons can breathe.

---

### 4. Economy / Metabolic Protocol – 经济流 (Coin, Coupon, Reroll)

**Fantasy:** You optimize the brain’s **energy and resource economy**, turning every drop of nutrients or money into long-term power.

**Key props:**

- **Spoil Splitter** – Coins you pick up sometimes duplicate themselves.  
- **Black Market Pass** – The next shop turns into a “black market” with better deals and higher-rarity props (but higher prices).  
- **VIP Punchcard** – Grants cashback on your spending in future shops.  
- Basic **Coin / Coupon / Reroll** tools that define your early econ.

**Playstyle:**  
Slow start, explosive late game.  
Perfect if you like planning, greed, and chaining shop combos so one run spirals into absurd power.

**In-world metaphor:**  
Improved blood flow, better glucose delivery, and systemic health changes that give the brain more “budget” to keep cells alive.

---

### 5. Field Control Protocol – 控场流 / 状态流 (Slow, Freeze, Shock)

**Fantasy:** You sculpt the battlefield, turning zones of the brain into safe havens or lethal traps.

**Key props:**

- **Time Dilation Boots** – Standing still briefly slows enemies in a radius around you.  
- **Phantom Dash** (if dash exists) – Dashing through enemies damages and slows them.  
- **Sticky Tar Flask** – Leaves slowing puddles that apply minor damage over time.  
- **Frost Brand** – Hits can “chill” enemies, slowing them; hitting chilled targets deals extra damage.  
- **Shock Relay** – Every N-th hit chains lightning to nearby enemies.

**Playstyle:**  
Less raw DPS, more **map control**.  
You kite enemies through slowed zones, stack status effects, and let your Ballistic or Turret protocols clean up.

**In-world metaphor:**  
Modulating microglial activity and neurotransmitters to control how fast (or slow) pathological processes can propagate.

---

### 6. Experimental Protocols – 仆从流 / 赌狗流 / 状态扩展 (WIP / Late-game)

These are higher-risk, higher-reward systems that will gradually come online as the core is stable:

- **Summoner / Minion Path (仆从流)**  
  - Summon helper entities that fight with you and level alongside your character.  
- **Gamble Path (赌狗流)**  
  - “Lucky / Risk / Chance” props with heavy variance: huge buffs with big drawbacks.  
- **Deep Status Path (状态流)**  
  - Leaving persistent “trails” of status fields behind you, layering burns, shocks, or debuffs on enemies that step in.

These are designed for advanced players who already understand the main protocols and want to push wild synergies.

---

## Multiple Endings

Your choices of **build path** and **how far you get** determine the patient’s fate.

Planned endings include:

- **Remission (True Ending)**  
  - Rare. Requires defeating the final boss *and* fully activating multiple key protocols in one run.  
  - The disease halts, some function returns. The brain briefly clears.

- **Stabilization (Normal Win)**  
  - You defeat the final boss but don’t meet the strict synergy requirements.  
  - Progression slows; the patient’s condition stabilizes at a fixed level.

- **Silent Collapse**  
  - Early death, before stabilizing any major region.  
  - Decline continues quietly; nothing seems “dramatic” on the outside, but the mind fades.

- **Intermediate Collapse Endings**  
  - Die after beating only the first boss, or somewhere between later bosses, and you’ll unlock different “partial success” narratives:  
    - **Some memories saved, language lost**  
    - **Speech preserved, spatial maps broken**  
    - **Body stable, identity gone**  

Each ending is a short vignette from outside the brain, reflecting what your internal battle achieved – or failed to change.

---

## Status

`NEURONVIVOR` is an in-development Pygame project.  
Current focus:

- Locking down core movement and combat feel  
- Implementing the main prop categories described above  
- Wiring boss fights and endings to build paths

Feedback on balance, theme, and readability is very welcome.
