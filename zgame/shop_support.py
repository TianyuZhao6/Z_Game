from __future__ import annotations

import random


def _state(game) -> dict:
    return game.__dict__


def build_shop_catalog(game):
    meta = game.META
    catalog = [
        {
            "id": "coin_magnet",
            "name": "Coin Magnet",
            "key": "magnet",
            "cost": 10,
            "rarity": 1,
            "max_level": 5,
            "desc": "Increase your coin pickup radius.",
            "apply": lambda: meta.update(coin_magnet_radius=meta.get("coin_magnet_radius", 0) + 60),
        },
        {
            "id": "carapace",
            "name": "Carapace",
            "desc": "Gain a small protective shield.",
            "cost": 6,
            "rarity": 1,
            "apply": lambda: meta.update(carapace_shield_hp=int(meta.get("carapace_shield_hp", 0)) + 20),
        },
        {
            "id": "aegis_pulse",
            "name": "Aegis Pulse",
            "desc": "Periodically release a hexagonal force field that damages nearby enemies when shield exists.",
            "cost": 28,
            "rarity": 3,
            "max_level": 5,
            "apply": lambda: meta.update(aegis_pulse_level=min(5, int(meta.get("aegis_pulse_level", 0)) + 1)),
        },
        {
            "id": "bone_plating",
            "name": "Bone Plating",
            "desc": "Every 6s gain 2 HP plating; max out at 5 buys to unlock full-hit negation, -2% speed.",
            "cost": 12,
            "rarity": 2,
            "max_level": 5,
            "apply": lambda: meta.update(
                bone_plating_level=min(5, int(meta.get("bone_plating_level", 0)) + 1),
                speed_mult=max(0.30, float(meta.get("speed_mult", 1.0)) * 0.98),
            ),
        },
        {
            "id": "auto_turret",
            "name": "Auto-Turret",
            "key": "auto_turret",
            "cost": 14,
            "rarity": 2,
            "max_level": 5,
            "desc": "Summons an orbiting auto-turret that fires at nearby enemies.",
            "apply": lambda: meta.update(auto_turret_level=min(5, meta.get("auto_turret_level", 0) + 1)),
        },
        {
            "id": "piercing_rounds",
            "name": "Piercing Rounds",
            "desc": "Bullets can pierce +1 enemy.",
            "cost": 12,
            "rarity": 1,
            "max_level": 5,
            "apply": lambda: meta.update(pierce_level=min(5, int(meta.get("pierce_level", 0)) + 1)),
        },
        {
            "id": "ricochet_scope",
            "name": "Ricochet Scope",
            "desc": "Bullets that hit walls or enemies can bounce toward the nearest enemy.",
            "cost": 14,
            "rarity": 2,
            "max_level": 3,
            "apply": lambda: meta.update(ricochet_level=min(3, int(meta.get("ricochet_level", 0)) + 1)),
        },
        {
            "id": "shrapnel_shells",
            "name": "Shrapnel Shells",
            "desc": "On enemy death, 25/35/45% spawn 3-4 shrapnel splashes dealing 40% of lethal damage.",
            "cost": 16,
            "rarity": 3,
            "max_level": 3,
            "apply": lambda: meta.update(shrapnel_level=min(3, int(meta.get("shrapnel_level", 0)) + 1)),
        },
        {
            "id": "explosive_rounds",
            "name": "Explosive Rounds",
            "desc": "On bullet kill, explode for 25/35/45% bullet dmg in a small radius (bosses half).",
            "cost": 18,
            "rarity": 2,
            "max_level": 3,
            "apply": lambda: meta.update(
                explosive_rounds_level=min(3, int(meta.get("explosive_rounds_level", 0)) + 1)
            ),
        },
        {
            "id": "dot_rounds",
            "name": "D.O.T. Rounds",
            "desc": "On hit, apply a stacking DoT based on base bullet dmg (0.5s ticks, bosses -30%).",
            "cost": 20,
            "rarity": 2,
            "max_level": 3,
            "apply": lambda: meta.update(dot_rounds_level=min(3, int(meta.get("dot_rounds_level", 0)) + 1)),
        },
        {
            "id": "curing_paint",
            "name": "Curing Paint",
            "desc": "While moving, leave curing ink footprints that damage enemies standing on them (0.5s ticks).",
            "cost": 12,
            "rarity": 2,
            "max_level": 3,
            "apply": lambda: meta.update(curing_paint_level=min(3, int(meta.get("curing_paint_level", 0)) + 1)),
        },
        {
            "id": "ground_spikes",
            "name": "Ground Spikes",
            "desc": "While moving, leave spikes that hit once and slow 5% for 1.0s; -4% move speed per buy.",
            "cost": 18,
            "rarity": 2,
            "max_level": 3,
            "apply": lambda: meta.update(
                ground_spikes_level=min(3, int(meta.get("ground_spikes_level", 0)) + 1),
                speed_mult=max(0.30, float(meta.get("speed_mult", 1.0)) * 0.96),
            ),
        },
        {
            "id": "mark_vulnerability",
            "name": "Mark of Vulnerability",
            "desc": "Every 5/4/3s mark a priority enemy for 5/6/7s; marked take +15/22/30% damage.",
            "cost": 22,
            "rarity": 3,
            "max_level": 3,
            "apply": lambda: meta.update(vuln_mark_level=min(3, int(meta.get("vuln_mark_level", 0)) + 1)),
        },
        {
            "id": "golden_interest",
            "name": "Golden Interest",
            "desc": "Earn interest on unspent coins after shopping (5/10/15/20%, cap 30/50/70/90).",
            "cost": 12,
            "rarity": 2,
            "max_level": game.GOLDEN_INTEREST_MAX_LEVEL,
            "apply": lambda: meta.update(
                golden_interest_level=min(
                    game.GOLDEN_INTEREST_MAX_LEVEL, int(meta.get("golden_interest_level", 0)) + 1
                )
            ),
        },
        {
            "id": "wanted_poster",
            "name": "Wanted Poster",
            "desc": "Consumable: next 2 levels, the first Bandit kill pays a bounty.",
            "cost": 15,
            "rarity": 2,
            "apply": game.use_wanted_poster,
        },
        {
            "id": "shady_loan",
            "name": "Shady Loan",
            "desc": "Risky loan: upfront gold now, pay it back over a few waves or lose max HP.",
            "cost": 0,
            "rarity": 3,
            "max_level": game.SHADY_LOAN_MAX_LEVEL,
            "apply": game.purchase_shady_loan,
        },
        {
            "id": "bandit_radar",
            "name": "Bandit Radar",
            "desc": "Bandits spawn slowed & highlighted (8/12/16/20% for 2/3/4/5s).",
            "cost": 18,
            "rarity": 2,
            "max_level": 4,
            "apply": lambda: meta.update(bandit_radar_level=min(4, int(meta.get("bandit_radar_level", 0)) + 1)),
        },
        {
            "id": "lockbox",
            "name": "Lockbox",
            "desc": "Protect a slice of your coins from bandits and other losses (25/40/55/70%).",
            "cost": 14,
            "rarity": 2,
            "max_level": game.LOCKBOX_MAX_LEVEL,
            "apply": lambda: meta.update(
                lockbox_level=min(game.LOCKBOX_MAX_LEVEL, int(meta.get("lockbox_level", 0)) + 1)
            ),
        },
        {
            "id": "coupon",
            "name": "Coupon",
            "desc": "Permanently reduce 5% all shop prices this run.",
            "cost": 10,
            "rarity": 1,
            "max_level": game.COUPON_MAX_LEVEL,
            "apply": lambda: meta.update(coupon_level=min(game.COUPON_MAX_LEVEL, int(meta.get("coupon_level", 0)) + 1)),
        },
        {
            "id": "stationary_turret",
            "name": "Stationary Turret",
            "desc": "Adds a stationary turret that spawns at a random clear spot on the map each level.",
            "cost": 14,
            "rarity": 1,
            "max_level": 99,
            "apply": lambda: meta.update(stationary_turret_count=int(meta.get("stationary_turret_count", 0)) + 1),
        },
        {
            "id": "reroll",
            "name": "Reroll",
            "key": "reroll",
            "cost": 3,
            "apply": "reroll",
        },
    ]
    _state(game)["_pause_shop_catalog"] = catalog
    return catalog


def load_locked_ids(game) -> list[str]:
    state = _state(game)
    meta = game.META
    saved_locked = meta.get("locked_shop_ids")
    if isinstance(saved_locked, list):
        seen = set()
        initial_locked = []
        for lock_id in saved_locked:
            if isinstance(lock_id, str) and lock_id not in seen:
                seen.add(lock_id)
                initial_locked.append(lock_id)
    else:
        initial_locked = []
    locked_ids = state.get("_locked_shop_ids")
    if locked_ids is None:
        locked_ids = list(initial_locked)
        state["_locked_shop_ids"] = locked_ids
    else:
        locked_ids[:] = list(initial_locked)
    persist_locked_ids(game, locked_ids)
    return locked_ids


def persist_locked_ids(game, locked_ids: list[str]) -> None:
    seen = set()
    ordered = []
    for lock_id in locked_ids:
        if isinstance(lock_id, str) and lock_id not in seen:
            seen.add(lock_id)
            ordered.append(lock_id)
    game.META["locked_shop_ids"] = ordered


def prop_level(game, item) -> int | None:
    return game.prop_level_from_meta(item.get("id"), game.META)


def owned_live_text(game, item, level: int | None) -> str:
    return game.detailed_prop_tooltip_text(item, level)


def prop_max_level(item):
    return item.get("max_level", None)


def prop_at_cap(game, item) -> bool:
    meta = game.META
    if item.get("id") == "shady_loan":
        level = int(meta.get("shady_loan_level", 0))
        debt = int(meta.get("shady_loan_remaining_debt", 0))
        active = meta.get("shady_loan_status") == "active"
        return active and debt > 0 and level >= game.SHADY_LOAN_MAX_LEVEL
    if item.get("id") == "wanted_poster":
        return False
    max_level = prop_max_level(item)
    if max_level is None:
        return False
    level = prop_level(game, item)
    return level is not None and level >= max_level


def rarity_weights_for_level(level_idx_zero_based: int) -> dict[int, float]:
    level_num = max(1, int(level_idx_zero_based) + 1)
    curves = {
        1: [(1, 100.0), (3, 70.0), (5, 45.0), (7, 25.0), (9, 15.0), (10, 10.0)],
        2: [(1, 15.0), (2, 20.0), (3, 25.0), (5, 35.0), (7, 33.0), (9, 20.0), (10, 15.0)],
        3: [(1, 3.0), (3, 6.0), (4, 12.0), (6, 25.0), (8, 32.0), (10, 35.0)],
        4: [(1, 0.0), (2, 0.0), (3, 5.0), (5, 12.0), (7, 22.0), (9, 35.0), (10, 40.0)],
        5: [(1, 0.0), (7, 0.0), (8, 1.0), (10, 5.0)],
    }
    weights = {rarity: _interp_weight(level_num, points) for rarity, points in curves.items()}
    if level_num < 8:
        weights[5] = 0.0
    return weights


def _interp_weight(level_num: int, points: list[tuple[int, float]]) -> float:
    if not points:
        return 0.0
    if level_num <= points[0][0]:
        return float(points[0][1])
    for (l0, v0), (l1, v1) in zip(points, points[1:]):
        if level_num <= l1:
            t = (level_num - l0) / float(max(1, l1 - l0))
            return v0 + (v1 - v0) * t
    return float(points[-1][1])


def roll_offers(game, catalog, locked_ids: list[str]):
    level_idx = int(_state(game).get("current_level", 0))
    rarity_weights = rarity_weights_for_level(level_idx)
    pool = [card for card in catalog if card.get("id") != "reroll" and not prop_at_cap(game, card)]
    locked_cards = []
    for lock_id in locked_ids:
        for card in pool:
            if card.get("id") == lock_id:
                locked_cards.append(card)
                break
    pool = [card for card in pool if card.get("id") not in locked_ids]
    offers = locked_cards[:4]
    if len(offers) < 4 and pool:
        weighted_pool = [card for card in pool if rarity_weights.get(int(card.get("rarity", 1)), 0.0) > 0]
        source_pool = weighted_pool or pool
        available_by_rarity: dict[int, list] = {}
        for card in source_pool:
            rarity = int(card.get("rarity", 1))
            available_by_rarity.setdefault(rarity, []).append(card)
        remaining_cards = list(source_pool)
        while len(offers) < 4 and remaining_cards:
            rarities = [rarity for rarity, cards in available_by_rarity.items() if cards]
            weights = [rarity_weights.get(rarity, 0.0) for rarity in rarities]
            if not rarities:
                break
            if all(weight <= 0 for weight in weights):
                choice = random.choice(remaining_cards)
            else:
                filtered = [(rarity, weight) for rarity, weight in zip(rarities, weights) if weight > 0]
                if filtered:
                    rarities, weights = zip(*filtered)
                choice_rarity = random.choices(list(rarities), weights=list(weights), k=1)[0]
                cards_for_rarity = available_by_rarity.get(choice_rarity) or []
                if not cards_for_rarity:
                    available_by_rarity.pop(choice_rarity, None)
                    continue
                choice = random.choice(cards_for_rarity)
            offers.append(choice)
            if choice in remaining_cards:
                remaining_cards.remove(choice)
            chosen_rarity = int(choice.get("rarity", 1))
            cards_for_rarity = available_by_rarity.get(chosen_rarity)
            if cards_for_rarity and choice in cards_for_rarity:
                cards_for_rarity.remove(choice)
            if cards_for_rarity == []:
                available_by_rarity.pop(chosen_rarity, None)
    offers = offers[:4]
    if len(offers) < 4:
        fallback_pool = [card for card in catalog if card.get("id") != "reroll"]
        random.shuffle(fallback_pool)
        for card in fallback_pool:
            if len(offers) >= 4:
                break
            if card in offers or prop_at_cap(game, card):
                continue
            offers.append(card)
        fallback_pool = [card for card in fallback_pool if not prop_at_cap(game, card)] or fallback_pool
        while len(offers) < 4 and fallback_pool:
            offers.append(random.choice(fallback_pool))
    offers.append(next(card for card in catalog if card.get("id") == "reroll"))
    return offers


def is_reroll_item(item) -> bool:
    return (
        item.get("id") == "reroll"
        or item.get("key") == "reroll"
        or item.get("name") in ("Reroll Offers", "Reroll")
    )


def split_offers(current):
    slots = [card for card in current if not is_reroll_item(card)]
    reroll = next((card for card in current if is_reroll_item(card)), None)
    return slots, reroll
