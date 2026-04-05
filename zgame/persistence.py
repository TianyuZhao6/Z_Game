from __future__ import annotations

import base64
import copy
import json
import os
import shutil
import sys
import zlib
from datetime import datetime
from typing import Optional

from zgame import runtime_state as rs


def _state(game):
    return rs.runtime(game)


def _meta(game):
    return rs.meta(game)


def _sanitize_loaded_save(game, data: Optional[dict]) -> Optional[dict]:
    if not isinstance(data, dict):
        return None
    if hasattr(game, "_sanitize_resume_save_data"):
        try:
            return game._sanitize_resume_save_data(data)
        except Exception as exc:
            print(f"[Save] Save sanitizer failed: {exc}", file=sys.stderr)
            return None
    return data


def web_storage(game):
    if not game.IS_WEB:
        return None
    try:
        import platform as web_platform

        return getattr(getattr(web_platform, "window", None), "localStorage", None)
    except Exception:
        return None


def _web_primary_key(game) -> str:
    return str(getattr(game, "WEB_SAVE_STORAGE_KEY", "z_game_save_v2") or "z_game_save_v2")


def _web_backup_key(game) -> str:
    return f"{_web_primary_key(game)}:backup"


def _web_meta_key(game) -> str:
    return f"{_web_primary_key(game)}:meta"


def _web_legacy_keys(game) -> tuple[str, ...]:
    legacy = getattr(game, "WEB_SAVE_STORAGE_LEGACY_KEYS", ()) or ()
    return tuple(str(key) for key in legacy if key)


def _encode_web_payload(data: dict) -> str:
    raw_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    raw_bytes = raw_json.encode("utf-8")
    compressed = zlib.compress(raw_bytes, level=9)
    if len(compressed) + 48 < len(raw_bytes):
        encoding = "zlib+base64"
        payload = base64.b64encode(compressed).decode("ascii")
    else:
        encoding = "json"
        payload = raw_json
    envelope = {
        "version": 2,
        "saved_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "encoding": encoding,
        "payload": payload,
        "json_bytes": len(raw_bytes),
    }
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))


def _decode_web_payload(raw: object) -> Optional[dict]:
    if raw is None:
        return None
    text = str(raw)
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except Exception:
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("payload"), str):
        version = int(parsed.get("version", 0) or 0)
        if version >= 2:
            encoding = str(parsed.get("encoding", "") or "").lower()
            payload = parsed.get("payload", "")
            try:
                if encoding == "zlib+base64":
                    decoded = zlib.decompress(base64.b64decode(payload.encode("ascii"))).decode("utf-8")
                    data = json.loads(decoded)
                elif encoding == "json":
                    data = json.loads(payload)
                else:
                    return None
            except Exception:
                return None
            return data if isinstance(data, dict) else None
    return parsed if isinstance(parsed, dict) else None


def web_storage_stats(game) -> dict[str, object]:
    storage = web_storage(game)
    info = {
        "backend": "localStorage",
        "has_save": False,
        "used_bytes": 0,
        "keys": [],
    }
    if storage is None:
        info["backend"] = "unavailable"
        return info
    keys = [_web_primary_key(game), _web_backup_key(game), _web_meta_key(game), *_web_legacy_keys(game)]
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        try:
            raw = storage.getItem(key)
        except Exception:
            raw = None
        if not raw:
            continue
        info["has_save"] = True
        info["keys"].append(key)
        info["used_bytes"] = int(info["used_bytes"]) + (len(key) + len(str(raw))) * 2
    return info


def store_web_save(game, data: Optional[dict]) -> None:
    storage = web_storage(game)
    if storage is None:
        return
    primary_key = _web_primary_key(game)
    backup_key = _web_backup_key(game)
    meta_key = _web_meta_key(game)
    try:
        if data is None:
            storage.removeItem(primary_key)
            storage.removeItem(backup_key)
            storage.removeItem(meta_key)
        else:
            previous = storage.getItem(primary_key)
            encoded = _encode_web_payload(data)
            if previous:
                storage.setItem(backup_key, str(previous))
            else:
                storage.removeItem(backup_key)
            storage.setItem(primary_key, encoded)
            storage.setItem(
                meta_key,
                json.dumps(
                    {
                        "version": 2,
                        "saved_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                        "used_bytes": web_storage_stats(game).get("used_bytes", 0),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
    except Exception:
        pass


def load_web_save(game) -> Optional[dict]:
    storage = web_storage(game)
    if storage is None:
        return None
    for key in (_web_primary_key(game), _web_backup_key(game), *_web_legacy_keys(game)):
        try:
            raw = storage.getItem(key)
        except Exception:
            raw = None
        data = _decode_web_payload(raw)
        if isinstance(data, dict):
            return data
    return None


def atomic_write_json(path: str, data: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def exportable_save_data(game) -> Optional[dict]:
    state = _state(game)
    cached = state.get("_web_save_cache")
    if isinstance(cached, dict):
        return copy.deepcopy(cached)
    data = load_save(game)
    if isinstance(data, dict):
        return copy.deepcopy(data)
    return None


def web_download_text(game, filename: str, text: str) -> tuple[bool, str]:
    if not game.IS_WEB:
        return False, "Web download is only available in the browser build."
    try:
        import platform as web_platform

        window = getattr(web_platform, "window", None)
        document = getattr(window, "document", None) if window else None
        body = getattr(document, "body", None) if document else None
        if window is None or document is None or body is None:
            return False, "Browser download API is unavailable."
        anchor = document.createElement("a")
        anchor.href = "data:application/json;charset=utf-8," + window.encodeURIComponent(text)
        anchor.download = filename
        anchor.style.display = "none"
        body.appendChild(anchor)
        anchor.click()
        try:
            anchor.remove()
        except Exception:
            body.removeChild(anchor)
        return True, f"Downloaded {filename}"
    except Exception as exc:
        return False, f"Export failed: {exc}"


def export_current_save(game) -> tuple[bool, str]:
    data = exportable_save_data(game)
    if not isinstance(data, dict):
        return False, "No save is available to export."
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"z_game_save_{stamp}.json"
    if game.IS_WEB:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        return web_download_text(game, filename, payload)
    try:
        os.makedirs(game.EXPORT_DIR, exist_ok=True)
        out_path = os.path.join(game.EXPORT_DIR, filename)
        atomic_write_json(out_path, data)
        return True, f"Exported to {out_path}"
    except Exception as exc:
        return False, f"Export failed: {exc}"


def save_progress(game, current_level: int, max_wave_reached: int | None = None, pending_shop: bool = False):
    state = _state(game)
    meta = _meta(game)
    meta_for_save = meta.to_dict()
    try:
        if bool(pending_shop) or bool(state.get("_in_shop_ui", False)):
            meta_for_save["spoils"] = int(meta.get("spoils", 0))
        else:
            if int(state.get("_baseline_for_level", -999)) == int(current_level):
                if "_coins_at_level_start" in state:
                    meta_for_save["spoils"] = int(state["_coins_at_level_start"])
                items_base = state.get("_items_run_baseline", {})
                try:
                    base_spawn = int(items_base.get("spawned", state.get("_run_items_spawned_start", meta.get("run_items_spawned", 0))))
                except Exception:
                    base_spawn = int(meta.get("run_items_spawned", 0))
                try:
                    base_collect = int(items_base.get("collected", state.get("_run_items_collected_start", meta.get("run_items_collected", 0))))
                except Exception:
                    base_collect = int(meta.get("run_items_collected", 0))
                meta_for_save["run_items_spawned"] = max(0, int(base_spawn))
                meta_for_save["run_items_collected"] = max(0, int(base_collect))
    except Exception:
        pass

    baseline_bundle = {}
    if "_baseline_for_level" in state:
        try:
            baseline_bundle["level"] = int(state["_baseline_for_level"])
        except Exception:
            pass
    if "_coins_at_level_start" in state:
        try:
            baseline_bundle["coins"] = int(state["_coins_at_level_start"])
        except Exception:
            pass
    if isinstance(state.get("_player_level_baseline"), dict):
        baseline_bundle["player"] = dict(state["_player_level_baseline"])
    if isinstance(state.get("_items_run_baseline"), dict):
        try:
            item_baseline = dict(state["_items_run_baseline"])
            if "count_this_level" in item_baseline and item_baseline["count_this_level"] is not None:
                item_baseline["count_this_level"] = int(item_baseline["count_this_level"])
            baseline_bundle["items"] = item_baseline
        except Exception:
            pass
    if isinstance(state.get("_consumable_baseline"), dict):
        try:
            baseline_bundle["consumables"] = dict(state["_consumable_baseline"])
        except Exception:
            pass

    data = {
        "mode": "progress",
        "current_level": int(current_level),
        "meta": meta_for_save,
        "carry_player": state.get("_carry_player_state", None),
        "pending_shop": bool(pending_shop),
        "biome": state.get("_next_biome") or state.get("_last_biome"),
    }

    slots_cache = state.get("_shop_slot_ids_cache") or state.get("_shop_slots_cache")
    if slots_cache and isinstance(slots_cache, list):
        ids_only = []
        for slot in slots_cache:
            if isinstance(slot, dict):
                ids_only.append(slot.get("id") or slot.get("name"))
            else:
                ids_only.append(slot)
        slots_cache = ids_only
    reroll_cache = state.get("_shop_reroll_id_cache") or state.get("_shop_reroll_cache")
    if reroll_cache and isinstance(reroll_cache, dict):
        reroll_cache = reroll_cache.get("id") or reroll_cache.get("name")
    if slots_cache is not None or reroll_cache is not None:
        data["shop_cache"] = {"slots": slots_cache, "reroll": reroll_cache}
    if max_wave_reached is not None:
        data["max_wave_reached"] = int(max_wave_reached)
    if baseline_bundle:
        data["baseline"] = baseline_bundle

    if game.IS_WEB:
        state["_web_save_cache"] = copy.deepcopy(data)
        store_web_save(game, state["_web_save_cache"])
        return
    try:
        atomic_write_json(game.SAVE_FILE, data)
    except Exception as exc:
        print("save_progress error:", exc)


def capture_snapshot(game, game_state, player, enemies, current_level: int, chosen_enemy_type: str = "basic", bullets=None) -> dict:
    state = _state(game)
    return {
        "mode": "snapshot",
        "version": 3,
        "meta": {
            "current_level": int(current_level),
            "chosen_enemy_type": str(chosen_enemy_type or "basic"),
            "biome": getattr(game_state, "biome_active", state.get("_next_biome")),
        },
        "snapshot": {
            "player": {
                "x": float(player.x),
                "y": float(player.y),
                "speed": player.speed,
                "size": player.size,
                "fire_cd": float(getattr(player, "fire_cd", 0.0)),
                "hp": int(getattr(player, "hp", game.PLAYER_MAX_HP)),
                "max_hp": int(getattr(player, "max_hp", game.PLAYER_MAX_HP)),
                "hit_cd": float(getattr(player, "hit_cd", 0.0)),
                "level": int(getattr(player, "level", 1)),
                "xp": int(getattr(player, "xp", 0)),
                "bone_plating_hp": int(getattr(player, "bone_plating_hp", 0)),
                "bone_plating_cd": float(getattr(player, "_bone_plating_cd", game.BONE_PLATING_GAIN_INTERVAL)),
                "aegis_pulse_cd": float(getattr(player, "_aegis_pulse_cd", 0.0)),
            },
            "enemies": [
                {
                    "x": float(enemy.x),
                    "y": float(enemy.y),
                    "attack": int(getattr(enemy, "attack", 10)),
                    "speed": int(getattr(enemy, "speed", 2)),
                    "type": str(getattr(enemy, "type", "basic")),
                    "hp": int(getattr(enemy, "hp", 30)),
                    "max_hp": int(getattr(enemy, "max_hp", getattr(enemy, "hp", 30))),
                    "spawn_elapsed": float(getattr(enemy, "_spawn_elapsed", 0.0)),
                    "attack_timer": float(getattr(enemy, "attack_timer", 0.0)),
                }
                for enemy in enemies
            ],
            "obstacles": [
                {
                    "x": int(ob.rect.x // game.CELL_SIZE),
                    "y": int((ob.rect.y - game.INFO_BAR_HEIGHT) // game.CELL_SIZE),
                    "type": ob.type,
                    "health": None if ob.health is None else int(ob.health),
                    "main": bool(getattr(ob, "is_main_block", False)),
                }
                for ob in game_state.obstacles.values()
            ],
            "items": [
                {"x": int(item.x), "y": int(item.y), "is_main": bool(item.is_main)}
                for item in game_state.items
            ],
            "decorations": [[int(dx), int(dy)] for (dx, dy) in getattr(game_state, "decorations", [])],
            "bullets": [
                {
                    "x": float(bullet.x),
                    "y": float(bullet.y),
                    "vx": float(bullet.vx),
                    "vy": float(bullet.vy),
                    "traveled": float(bullet.traveled),
                }
                for bullet in (bullets or [])
                if getattr(bullet, "alive", True)
            ],
            "time_left": float(state.get("_time_left_runtime", game.LEVEL_TIME_LIMIT)),
        },
    }


def save_snapshot(game, snapshot: dict) -> None:
    state = _state(game)
    if game.IS_WEB:
        state["_web_save_cache"] = copy.deepcopy(snapshot)
        store_web_save(game, state["_web_save_cache"])
        return
    try:
        atomic_write_json(game.SAVE_FILE, snapshot)
    except Exception as exc:
        print(f"[Save] Failed to write snapshot: {exc}", file=sys.stderr)


def load_save(game) -> Optional[dict]:
    state = _state(game)
    if game.IS_WEB:
        cached = state.get("_web_save_cache")
        if isinstance(cached, dict):
            clean_cached = _sanitize_loaded_save(game, cached)
            if isinstance(clean_cached, dict):
                state["_web_save_cache"] = copy.deepcopy(clean_cached)
                return copy.deepcopy(clean_cached)
            state.pop("_web_save_cache", None)
            return None
        loaded = load_web_save(game)
        if isinstance(loaded, dict):
            clean_loaded = _sanitize_loaded_save(game, loaded)
            if isinstance(clean_loaded, dict):
                state["_web_save_cache"] = copy.deepcopy(clean_loaded)
                return copy.deepcopy(clean_loaded)
        return None
    try:
        if not os.path.exists(game.SAVE_FILE):
            return None
        try:
            with open(game.SAVE_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            print(f"[Save] Failed to read save file: {exc}", file=sys.stderr)
            try:
                bad_path = game.SAVE_FILE + ".bak"
                shutil.move(game.SAVE_FILE, bad_path)
            except Exception:
                try:
                    os.remove(game.SAVE_FILE)
                except Exception:
                    pass
            return None
        if not isinstance(data, dict):
            return None
        if "mode" not in data:
            data["mode"] = "meta"
        if data["mode"] == "meta":
            data.setdefault("current_level", 0)
        elif data["mode"] == "snapshot":
            data.setdefault("meta", {})
            data["meta"].setdefault("current_level", 0)
            data["meta"].setdefault("chosen_enemy_type", "basic")
            data.setdefault("snapshot", {})
        data = _sanitize_loaded_save(game, data)
        if not isinstance(data, dict):
            return None

        try:
            baseline = data.get("baseline")
            if isinstance(baseline, dict):
                if "level" in baseline:
                    state["_baseline_for_level"] = int(baseline["level"])
                if "coins" in baseline:
                    state["_coins_at_level_start"] = int(baseline["coins"])
                if isinstance(baseline.get("items"), dict):
                    try:
                        item_base = baseline.get("items", {})
                        spawn = int(item_base.get("spawned", 0))
                        collect = int(item_base.get("collected", 0))
                        count_this_level = item_base.get("count_this_level", None)
                        if count_this_level is not None:
                            try:
                                count_this_level = int(count_this_level)
                            except Exception:
                                count_this_level = None
                        state["_items_run_baseline"] = {
                            "spawned": spawn,
                            "collected": collect,
                            "count_this_level": count_this_level,
                        }
                    except Exception:
                        pass
                if isinstance(baseline.get("consumables"), dict):
                    try:
                        consumables = baseline.get("consumables", {})
                        state["_consumable_baseline"] = {
                            "carapace_shield_hp": int(consumables.get("carapace_shield_hp", 0)),
                            "wanted_poster_waves": int(consumables.get("wanted_poster_waves", 0)),
                            "wanted_active": bool(consumables.get("wanted_active", False)),
                        }
                    except Exception:
                        pass
                if isinstance(baseline.get("player"), dict):
                    player_base = dict(baseline["player"])
                    if "meta_stats" not in player_base and isinstance(data.get("meta"), dict):
                        meta = data["meta"]
                        try:
                            range_base = game.clamp_player_range(player_base.get("range_base", meta.get("base_range", game.PLAYER_RANGE_DEFAULT)))
                            range_val = game.clamp_player_range(player_base.get("range", range_base))
                            range_mult_est = range_val / range_base if range_base else meta.get("range_mult", 1.0)
                        except Exception:
                            range_mult_est = meta.get("range_mult", 1.0)
                        player_base["meta_stats"] = {
                            "dmg": int(meta.get("dmg", 0)),
                            "firerate_mult": float(meta.get("firerate_mult", 1.0)),
                            "range_mult": float(meta.get("range_mult", range_mult_est)),
                            "speed_mult": float(meta.get("speed_mult", 1.0)),
                            "crit": float(meta.get("crit", 0.0)),
                            "maxhp": int(meta.get("maxhp", 0)),
                        }
                    state["_player_level_baseline"] = player_base
        except Exception as exc:
            print(f"[Save] Baseline hydrate failed: {exc}", file=sys.stderr)

        try:
            cache = data.get("shop_cache")
            if isinstance(cache, dict):
                slots = cache.get("slots")
                reroll = cache.get("reroll")
                if slots is not None:
                    state["_shop_slot_ids_cache"] = slots
                if reroll is not None:
                    state["_shop_reroll_id_cache"] = reroll
                state["_resume_shop_cache"] = True
        except Exception:
            pass
        return data
    except Exception as exc:
        print(f"[Save] Failed to read save file: {exc}", file=sys.stderr)
        return None


def clear_level_start_baseline(game) -> None:
    state = _state(game)
    for key in (
        "_baseline_for_level",
        "_coins_at_level_start",
        "_coins_at_shop_entry",
        "_player_level_baseline",
        "_items_run_baseline",
        "_consumable_baseline",
        "_items_counted_level",
        "_restart_from_shop",
    ):
        state.pop(key, None)


def capture_level_start_baseline(game, level_idx: int, player, game_state=None):
    state = _state(game)
    meta = _meta(game)
    state["_baseline_for_level"] = int(level_idx)
    if state.get("_baseline_for_level", None) != level_idx or "_coins_at_level_start" not in state:
        state["_coins_at_level_start"] = int(meta.get("spoils", 0))
    state["_player_level_baseline"] = {
        "level": int(getattr(player, "level", 1)),
        "xp": int(getattr(player, "xp", 0)),
        "xp_to_next": int(getattr(player, "xp_to_next", game.player_xp_required(1))),
        "bullet_damage": int(getattr(player, "bullet_damage", meta.get("base_dmg", 0) + meta.get("dmg", 0))),
        "max_hp": int(getattr(player, "max_hp", meta.get("base_maxhp", 0) + meta.get("maxhp", 0))),
        "hp": int(getattr(player, "hp", meta.get("base_maxhp", 0) + meta.get("maxhp", 0))),
        "biome": getattr(game_state, "biome_active", state.get("_next_biome")),
        "fire_rate_mult": float(getattr(player, "fire_rate_mult", 1.0)),
        "range": game.clamp_player_range(getattr(player, "range", game.PLAYER_RANGE_DEFAULT)),
        "range_base": game.clamp_player_range(getattr(player, "range_base", game.PLAYER_RANGE_DEFAULT)),
        "crit_chance": float(getattr(player, "crit_chance", game.CRIT_CHANCE_BASE)),
        "crit_mult": float(getattr(player, "crit_mult", game.CRIT_MULT_BASE)),
        "speed": float(getattr(player, "speed", game.PLAYER_SPEED)),
        "meta_stats": {
            "dmg": int(meta.get("dmg", 0)),
            "firerate_mult": float(meta.get("firerate_mult", 1.0)),
            "range_mult": float(meta.get("range_mult", 1.0)),
            "speed_mult": float(meta.get("speed_mult", 1.0)),
            "crit": float(meta.get("crit", 0.0)),
            "maxhp": int(meta.get("maxhp", 0)),
        },
    }
    try:
        base_spawn = int(state.get("_run_items_spawned_start", meta.get("run_items_spawned", 0)))
    except Exception:
        base_spawn = int(meta.get("run_items_spawned", 0))
    try:
        base_collect = int(state.get("_run_items_collected_start", meta.get("run_items_collected", 0)))
    except Exception:
        base_collect = int(meta.get("run_items_collected", 0))
    level_items = None
    if game_state is not None:
        try:
            level_items = int(getattr(game_state, "items_total", len(getattr(game_state, "items", []))))
        except Exception:
            try:
                level_items = len(getattr(game_state, "items", []))
            except Exception:
                level_items = None
    state["_items_run_baseline"] = {
        "spawned": base_spawn,
        "collected": base_collect,
        "count_this_level": level_items,
    }
    state["_consumable_baseline"] = {
        "carapace_shield_hp": int(meta.get("carapace_shield_hp", 0)),
        "wanted_poster_waves": int(meta.get("wanted_poster_waves", 0)),
        "wanted_active": bool(meta.get("wanted_active", False)),
    }


def restore_level_start_baseline(game, level_idx: int, player, game_state):
    state = _state(game)
    meta = _meta(game)
    if int(state.get("_baseline_for_level", -999999)) != int(level_idx):
        return
    state.pop("_restart_from_shop", None)
    if "_coins_at_level_start" in state:
        meta["spoils"] = int(state["_coins_at_level_start"])
    elif "_coins_at_shop_entry" in state:
        meta["spoils"] = int(state["_coins_at_shop_entry"])
    else:
        meta["spoils"] = 0

    items_base = state.get("_items_run_baseline", None)
    if isinstance(items_base, dict):
        base_spawn = int(items_base.get("spawned", meta.get("run_items_spawned", 0)))
        base_collect = int(items_base.get("collected", meta.get("run_items_collected", 0)))
        level_items = items_base.get("count_this_level", None)
    else:
        base_spawn = int(state.get("_run_items_spawned_start", meta.get("run_items_spawned", 0)))
        base_collect = int(state.get("_run_items_collected_start", meta.get("run_items_collected", 0)))
        level_items = None
    if level_items is None:
        try:
            level_items = int(getattr(game_state, "items_total", len(getattr(game_state, "items", []))))
        except Exception:
            try:
                level_items = len(getattr(game_state, "items", []))
            except Exception:
                level_items = 0
    try:
        level_items = int(level_items)
    except Exception:
        level_items = 0
    meta["run_items_spawned"] = max(0, int(base_spawn) + max(0, int(level_items)))
    meta["run_items_collected"] = max(0, int(base_collect))
    state["_run_items_spawned_start"] = int(base_spawn)
    state["_run_items_collected_start"] = int(base_collect)
    state["_items_counted_level"] = int(level_idx)

    if hasattr(game_state, "spoils_gained"):
        game_state.spoils_gained = 0
    if hasattr(game_state, "_bandit_stolen"):
        game_state._bandit_stolen = 0
    if hasattr(game_state, "level_coin_delta"):
        game_state.level_coin_delta = 0
    if hasattr(game_state, "bandit_spawned_this_level"):
        game_state.bandit_spawned_this_level = False

    player_baseline = state.get("_player_level_baseline", None)
    if isinstance(player_baseline, dict):
        meta_stats = player_baseline.get("meta_stats", {})
        if not isinstance(meta_stats, dict):
            try:
                range_base = game.clamp_player_range(player_baseline.get("range_base", getattr(player, "range_base", game.PLAYER_RANGE_DEFAULT)))
                range_val = game.clamp_player_range(player_baseline.get("range", range_base))
                range_mult_est = range_val / range_base if range_base else meta.get("range_mult", 1.0)
            except Exception:
                range_mult_est = meta.get("range_mult", 1.0)
            meta_stats = {
                "dmg": int(meta.get("dmg", 0)),
                "firerate_mult": float(player_baseline.get("fire_rate_mult", meta.get("firerate_mult", 1.0))),
                "range_mult": float(meta.get("range_mult", range_mult_est)),
                "speed_mult": float(meta.get("speed_mult", 1.0)),
                "crit": float(meta.get("crit", 0.0)),
                "maxhp": int(meta.get("maxhp", 0)),
            }
        for key in ("dmg", "firerate_mult", "range_mult", "speed_mult", "crit", "maxhp"):
            if key in meta_stats:
                meta[key] = meta_stats[key]
        player.level = int(player_baseline.get("level", 1))
        player.xp = int(player_baseline.get("xp", 0))
        player.xp_to_next = int(player_baseline.get("xp_to_next", game.player_xp_required(player.level)))
        player.bullet_damage = int(player_baseline.get("bullet_damage", player.bullet_damage))
        player.max_hp = int(player_baseline.get("max_hp", player.max_hp))
        player.hp = min(player.max_hp, int(player_baseline.get("hp", player.max_hp)))
        player.fire_rate_mult = float(player_baseline.get("fire_rate_mult", meta.get("firerate_mult", getattr(player, "fire_rate_mult", 1.0))))
        player.range_base = game.clamp_player_range(player_baseline.get("range_base", getattr(player, "range_base", game.PLAYER_RANGE_DEFAULT)))
        player.range = game.compute_player_range(player.range_base, float(meta.get("range_mult", 1.0)))
        player.crit_chance = float(player_baseline.get("crit_chance", getattr(player, "crit_chance", game.CRIT_CHANCE_BASE)))
        player.crit_mult = float(player_baseline.get("crit_mult", getattr(player, "crit_mult", game.CRIT_MULT_BASE)))
        player.speed = float(player_baseline.get("speed", getattr(player, "speed", game.PLAYER_SPEED)))
        if player_baseline.get("biome") is not None:
            game_state.biome_active = player_baseline.get("biome")
        player.levelup_pending = 0

    consumables = state.get("_consumable_baseline")
    if isinstance(consumables, dict):
        if "carapace_shield_hp" in consumables:
            carapace_hp = max(0, int(consumables.get("carapace_shield_hp", 0)))
            meta["carapace_shield_hp"] = carapace_hp
            player.carapace_hp = carapace_hp
            player._hud_shield_vis = carapace_hp / float(max(1, player.max_hp)) if carapace_hp > 0 else 0.0
        if "wanted_poster_waves" in consumables:
            meta["wanted_poster_waves"] = max(0, int(consumables.get("wanted_poster_waves", 0)))
        if "wanted_active" in consumables:
            meta["wanted_active"] = bool(consumables.get("wanted_active", False))
            game_state.wanted_wave_active = bool(meta.get("wanted_active", False))


def has_save(game) -> bool:
    state = _state(game)
    if game.IS_WEB:
        return isinstance(state.get("_web_save_cache"), dict) or isinstance(load_web_save(game), dict)
    return os.path.exists(game.SAVE_FILE)


def clear_save(game) -> None:
    state = _state(game)
    if game.IS_WEB:
        state["_web_save_cache"] = None
        store_web_save(game, None)
        return
    try:
        if os.path.exists(game.SAVE_FILE):
            os.remove(game.SAVE_FILE)
    except Exception as exc:
        print(f"[Save] Failed to delete save file: {exc}", file=sys.stderr)
