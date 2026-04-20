from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import websocket


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build" / "web"
DEFAULT_OUT_DIR = ROOT / "build" / "diagnostics"
SERVER_SCRIPT = ROOT / "tools" / "serve_web_build.py"


@dataclass(frozen=True)
class Scenario:
    name: str
    duration_s: int
    params: dict[str, str]
    notes: str = ""


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        name="menu_transition_short",
        duration_s=12,
        params={
            "start": "1",
            "diag": "1",
            "profile": "1",
            "diagexport": "90",
            "scenario": "menu_transition_short",
            "transition": "1",
            "level": "0",
            "god": "1",
        },
        notes="Start-menu to level transition check using the real in-level transition path.",
    ),
    Scenario(
        name="wind_long",
        duration_s=45,
        params={
            "start": "1",
            "diag": "1",
            "profile": "1",
            "diagexport": "90",
            "scenario": "wind_long",
            "biome": "wind",
            "level": "2",
            "god": "1",
        },
        notes="Non-boss wind biome run focused on hurricane progression and late-session pacing.",
    ),
    Scenario(
        name="mist_long",
        duration_s=45,
        params={
            "start": "1",
            "diag": "1",
            "profile": "1",
            "diagexport": "90",
            "scenario": "mist_long",
            "biome": "mist",
            "level": "2",
            "god": "1",
        },
        notes="Non-boss mist biome run focused on fog/filter progression over time.",
    ),
    Scenario(
        name="hell_long",
        duration_s=45,
        params={
            "start": "1",
            "diag": "1",
            "profile": "1",
            "diagexport": "90",
            "scenario": "hell_long",
            "biome": "hell",
            "level": "2",
            "god": "1",
        },
        notes="Non-boss scorched hell biome run focused on paint/fire accumulation.",
    ),
    Scenario(
        name="wind_boss_long",
        duration_s=55,
        params={
            "start": "1",
            "diag": "1",
            "profile": "1",
            "diagexport": "90",
            "scenario": "wind_boss_long",
            "biome": "wind",
            "level": "4",
            "god": "1",
        },
        notes="Boss-heavy wind biome run to compare biome cost plus boss-phase overhead.",
    ),
)


def find_free_port(preferred: int) -> int:
    for port in (preferred, preferred + 1, preferred + 2):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def choose_chrome() -> Path:
    candidates = (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    )
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("Chrome executable not found in standard install paths.")


def start_server(port: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(SERVER_SCRIPT), "--port", str(port), "--dir", str(BUILD_DIR)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def wait_http(url: str, *, timeout_s: float = 20.0) -> None:
    deadline = time.time() + timeout_s
    last_error = None
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=1.5)
            if resp.status_code == 200:
                return
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Server did not respond with HTTP 200 for {url}: {last_error}")


def start_chrome(chrome_path: Path, user_data_dir: Path, url: str, debug_port: int) -> subprocess.Popen[bytes]:
    cmd = [
        str(chrome_path),
        "--headless=new",
        "--disable-gpu",
        "--remote-allow-origins=*",
        "--autoplay-policy=no-user-gesture-required",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,720",
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={user_data_dir}",
        url,
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_cdp_target(port: int, *, timeout_s: float = 20.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last_error = None
    while time.time() < deadline:
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/json/list", timeout=2)
            targets = resp.json()
            for target in targets:
                if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                    return target
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for Chrome DevTools target on port {port}: {last_error}")


def connect_cdp(target: dict[str, Any]) -> websocket.WebSocket:
    ws = websocket.create_connection(str(target["webSocketDebuggerUrl"]), timeout=5)
    ws.settimeout(0.25)
    for idx, method in ((1, "Page.enable"), (2, "Runtime.enable"), (3, "Log.enable")):
        ws.send(json.dumps({"id": idx, "method": method}))
    return ws


def drain_cdp_events(
    ws: websocket.WebSocket | None,
    *,
    latest_py_export: dict[str, Any] | None,
    console_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if ws is None:
        return latest_py_export
    while True:
        try:
            raw = ws.recv()
        except websocket.WebSocketTimeoutException:
            break
        except Exception:
            break
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        method = str(msg.get("method") or "")
        if method == "Runtime.consoleAPICalled":
            args = list((msg.get("params") or {}).get("args") or [])
            values = [str(arg.get("value", "")) for arg in args if "value" in arg]
            joined = " ".join(values).strip()
            if joined.startswith("__ZGAME_PY_DIAG__"):
                text = joined[len("__ZGAME_PY_DIAG__"):].strip()
                try:
                    parsed = json.loads(text)
                except Exception:
                    parsed = None
                if isinstance(parsed, dict):
                    latest_py_export = parsed
            elif joined:
                console_events.append({"type": "console", "text": joined[:400]})
        elif method == "Runtime.exceptionThrown":
            details = (msg.get("params") or {}).get("exceptionDetails") or {}
            text = str(details.get("text") or "")
            exc = details.get("exception") or {}
            desc = str(exc.get("description") or "")
            console_events.append({"type": "exception", "text": (desc or text)[:400]})
        elif method == "Page.javascriptDialogOpening":
            text = str((msg.get("params") or {}).get("message") or "")
            console_events.append({"type": "dialog", "text": text[:400]})
        elif method == "Log.entryAdded":
            entry = (msg.get("params") or {}).get("entry") or {}
            text = str(entry.get("text") or "")
            level = str(entry.get("level") or "")
            if text:
                console_events.append({"type": f"log:{level}", "text": text[:400]})
    return latest_py_export


def scenario_url(base_url: str, scenario: Scenario) -> str:
    params = dict(scenario.params)
    params["duration"] = str(scenario.duration_s)
    return base_url + "?" + urllib.parse.urlencode(params)


def server_json(url: str) -> dict[str, Any]:
    last_error = None
    for _ in range(3):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Server JSON request failed for {url}: {last_error}")


def reset_server_diag(base_url: str, scenario_name: str) -> None:
    server_json(urllib.parse.urljoin(base_url, f"/__zgame_diag/reset?scenario={urllib.parse.quote(scenario_name)}"))


def fetch_server_diag(base_url: str, scenario_name: str) -> dict[str, Any]:
    return server_json(urllib.parse.urljoin(base_url, f"/__zgame_diag/latest?scenario={urllib.parse.quote(scenario_name)}"))


def fetch_server_status(base_url: str, scenario_name: str) -> dict[str, Any]:
    return server_json(urllib.parse.urljoin(base_url, f"/__zgame_diag/status?scenario={urllib.parse.quote(scenario_name)}"))


def mean(values: list[float]) -> float:
    return float(sum(values) / max(1, len(values))) if values else 0.0


def percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (max(0, min(100, int(p))) / 100.0) * (len(ordered) - 1)
    lo = int(idx)
    hi = min(len(ordered) - 1, lo + 1)
    frac = idx - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def segment_samples(samples: list[dict[str, Any]], segment: str) -> list[dict[str, Any]]:
    if not samples:
        return []
    n = len(samples)
    third = max(1, n // 3)
    if segment == "early":
        return samples[:third]
    if segment == "mid":
        return samples[third:min(n, third * 2)]
    return samples[max(0, n - third):]


def summarize_segment(samples: list[dict[str, Any]]) -> dict[str, float]:
    frame_ms = [float(s.get("frame_ms", 0.0) or 0.0) for s in samples]
    update_ms = [float(s.get("update_ms", 0.0) or 0.0) for s in samples]
    render_ms = [float(s.get("render_ms", 0.0) or 0.0) for s in samples]
    gap_ms = [float(s.get("browser_gap_ms", 0.0) or 0.0) for s in samples]
    return {
        "frames": float(len(samples)),
        "avg_frame_ms": round(mean(frame_ms), 3),
        "avg_update_ms": round(mean(update_ms), 3),
        "avg_render_ms": round(mean(render_ms), 3),
        "avg_browser_gap_ms": round(mean(gap_ms), 3),
        "p95_frame_ms": round(percentile(frame_ms, 95), 3),
    }


def count_growth(samples: list[dict[str, Any]], key: str) -> dict[str, float]:
    if not samples:
        return {"early": 0.0, "late": 0.0, "delta": 0.0}
    early = segment_samples(samples, "early")
    late = segment_samples(samples, "late")
    early_vals = [float((s.get("counts", {}) or {}).get(key, 0) or 0) for s in early]
    late_vals = [float((s.get("counts", {}) or {}).get(key, 0) or 0) for s in late]
    early_avg = mean(early_vals)
    late_avg = mean(late_vals)
    return {
        "early": round(early_avg, 3),
        "late": round(late_avg, 3),
        "delta": round(late_avg - early_avg, 3),
    }


def summarize_render_subpasses(samples: list[dict[str, Any]]) -> list[dict[str, float | str]]:
    buckets: dict[str, list[float]] = {}
    for sample in samples:
        counts = sample.get("counts") or {}
        if not isinstance(counts, dict):
            continue
        for key, value in counts.items():
            if not (isinstance(key, str) and key.startswith("r_") and key.endswith("_ms")):
                continue
            if "_build_" in key:
                continue
            if not isinstance(value, (int, float)):
                continue
            buckets.setdefault(key, []).append(float(value))
    out = []
    for key, values in buckets.items():
        out.append(
            {
                "name": key,
                "avg_ms": round(mean(values), 3),
                "p95_ms": round(percentile(values, 95), 3),
                "max_ms": round(max(values) if values else 0.0, 3),
            }
        )
    out.sort(key=lambda item: float(item.get("avg_ms", 0.0)), reverse=True)
    return out


def summarize_render_build_costs(samples: list[dict[str, Any]]) -> list[dict[str, float | str]]:
    buckets: dict[str, list[float]] = {}
    for sample in samples:
        counts = sample.get("counts") or {}
        if not isinstance(counts, dict):
            continue
        for key, value in counts.items():
            if not (isinstance(key, str) and key.startswith("r_") and key.endswith("_ms")):
                continue
            if "_build_" not in key:
                continue
            if not isinstance(value, (int, float)):
                continue
            buckets.setdefault(key, []).append(float(value))
    out = []
    for key, values in buckets.items():
        out.append(
            {
                "name": key,
                "avg_ms": round(mean(values), 3),
                "p95_ms": round(percentile(values, 95), 3),
                "max_ms": round(max(values) if values else 0.0, 3),
            }
        )
    out.sort(key=lambda item: float(item.get("avg_ms", 0.0)), reverse=True)
    return out


def summarize_counter_growth(samples: list[dict[str, Any]]) -> list[dict[str, float | str]]:
    numeric_keys: set[str] = set()
    for sample in samples:
        counts = sample.get("counts") or {}
        if not isinstance(counts, dict):
            continue
        for key, value in counts.items():
            if not isinstance(key, str):
                continue
            if key.startswith("r_") or key in {"rendered", "hp", "lvl", "wave", "mist", "hell", "wind", "fog"}:
                continue
            if isinstance(value, (int, float)):
                numeric_keys.add(key)
    growth = []
    for key in sorted(numeric_keys):
        stat = count_growth(samples, key)
        if stat["late"] <= max(0.5, stat["early"]) and stat["delta"] <= 0.0:
            continue
        growth.append(
            {
                "name": key,
                "early": stat["early"],
                "late": stat["late"],
                "delta": stat["delta"],
            }
        )
    growth.sort(key=lambda item: float(item.get("delta", 0.0)), reverse=True)
    return growth


def build_root_cause_candidates(export_data: dict[str, Any]) -> list[dict[str, Any]]:
    py = export_data.get("py") or {}
    samples = list(py.get("samples") or [])
    if not samples:
        return [{"candidate": "no_samples", "confidence": "low", "basis": "No Python profiler frame samples were exported."}]
    early = summarize_segment(segment_samples(samples, "early"))
    late = summarize_segment(segment_samples(samples, "late"))
    counts = {
        key: count_growth(samples, key)
        for key in ("sp", "heal", "txt", "fx", "ghost", "paint", "wind", "acid", "tg", "en", "mist", "hell")
    }
    transition_events = [e for e in (py.get("events") or []) if str(e.get("kind", "")).startswith("transition:")]
    js = export_data.get("js") or {}
    js_p95 = float(((js.get("gap_percentiles_ms") or {}).get("p95")) or 0.0)
    out: list[dict[str, Any]] = []
    if late["avg_render_ms"] > max(early["avg_render_ms"] * 1.2, late["avg_update_ms"] * 1.15):
        out.append({
            "candidate": "render_cost",
            "confidence": "medium",
            "basis": f"Late render avg {late['avg_render_ms']:.2f}ms exceeds early render avg {early['avg_render_ms']:.2f}ms and dominates update cost.",
        })
    if late["avg_update_ms"] > max(early["avg_update_ms"] * 1.2, late["avg_render_ms"] * 1.15):
        out.append({
            "candidate": "update_cost",
            "confidence": "medium",
            "basis": f"Late update avg {late['avg_update_ms']:.2f}ms exceeds early update avg {early['avg_update_ms']:.2f}ms and dominates render cost.",
        })
    if js_p95 > max(5.0, late["avg_frame_ms"] * 1.1):
        out.append({
            "candidate": "browser_event_loop_cadence",
            "confidence": "medium",
            "basis": f"Browser rAF p95 gap {js_p95:.2f}ms is materially above Python frame-time average {late['avg_frame_ms']:.2f}ms.",
        })
    growth_hits = [name for name, stat in counts.items() if stat["late"] > max(1.0, stat["early"] * 1.4)]
    if growth_hits and late["avg_frame_ms"] > early["avg_frame_ms"] * 1.15:
        out.append({
            "candidate": "object_accumulation",
            "confidence": "medium",
            "basis": f"Growing counts in {', '.join(growth_hits)} align with late-session frame-time growth.",
        })
    stall_events = [e for e in transition_events if str(e.get("kind")) == "transition:stall"]
    if stall_events:
        out.append({
            "candidate": "transition_state_progression",
            "confidence": "high",
            "basis": f"{len(stall_events)} transition stall events were recorded during the run.",
        })
    if not out:
        out.append({
            "candidate": "mixed_or_inconclusive",
            "confidence": "low",
            "basis": "No single dominant regression signature stood out from the collected metrics.",
        })
    return out


def build_recommendations(scenario_name: str, export_data: dict[str, Any]) -> list[str]:
    recommendations: list[str] = []
    candidates = build_root_cause_candidates(export_data)
    names = {c["candidate"] for c in candidates}
    samples = list(((export_data.get("py") or {}).get("samples")) or [])
    render_hotspots = summarize_render_subpasses(samples)
    top_render = render_hotspots[0]["name"] if render_hotspots else ""
    if "transition_state_progression" in names:
        recommendations.append("Cache or pre-prime the transition target surface before activation and verify progress events against the browser cadence trace.")
    if "render_cost" in names:
        if top_render:
            recommendations.append(f"Target the hottest render-phase subpass first (`{top_render}` in this run) before touching gameplay behavior.")
        else:
            recommendations.append("Target the hottest render-phase subpass from the recorded phase timings before touching gameplay behavior.")
    if "update_cost" in names:
        recommendations.append("Split the hottest update-phase subsystem into lower-frequency buckets and re-run the same scenario unchanged.")
    if "object_accumulation" in names:
        recommendations.append("Audit the late-session counters that grew materially and merge or cap only transient carriers with no gameplay value.")
    if "browser_event_loop_cadence" in names:
        recommendations.append("Compare Python frame percentiles against JS rAF gaps before changing gameplay code; reduce bursty work that starves the browser loop.")
    if "mist" in scenario_name:
        recommendations.append("Mist scenario: inspect fog mask rebuild cadence, mask size quantization, and lantern invalidation frequency first.")
    if "wind" in scenario_name:
        recommendations.append("Wind scenario: inspect hurricane update cost separately from draw cost; both are already split in the profiler data.")
    if "hell" in scenario_name:
        recommendations.append("Hell scenario: inspect paint-active growth and scorched-hell refresh paths before AI or spawn changes.")
    return recommendations


def run_scenario(chrome_path: Path, scenario: Scenario, base_url: str, debug_port: int) -> dict[str, Any]:
    url = scenario_url(base_url, scenario)
    reset_server_diag(base_url, scenario.name)
    user_data_dir = Path(tempfile.mkdtemp(prefix=f"zgame-browser-diag-{scenario.name}-"))
    proc = start_chrome(chrome_path, user_data_dir, url, debug_port)
    export_data: dict[str, Any] = {}
    status: dict[str, Any] = {}
    posts_seen = 0
    observed_py_frames = 0
    observed_js_frames = 0
    saw_runtime_export = False
    started_at = time.time()
    latest_py_export: dict[str, Any] | None = None
    console_events: list[dict[str, Any]] = []
    ws = None
    try:
        try:
            target = wait_cdp_target(debug_port)
            ws = connect_cdp(target)
        except Exception as exc:
            console_events.append({"type": "cdp", "text": str(exc)[:400]})
        while time.time() < (started_at + float(scenario.duration_s)):
            latest_py_export = drain_cdp_events(ws, latest_py_export=latest_py_export, console_events=console_events)
            try:
                status = fetch_server_status(base_url, scenario.name)
                posts_seen = max(posts_seen, int(status.get("posts", 0) or 0))
                export_candidate = fetch_server_diag(base_url, scenario.name)
                if export_candidate and (not export_candidate.get("missing")):
                    export_data = export_candidate
                    py = export_candidate.get("py") or {}
                    py_summary = py.get("summary") or {}
                    observed_py_frames = max(observed_py_frames, int(py_summary.get("frames", 0) or 0))
                    observed_js_frames = max(observed_js_frames, int(((export_candidate.get("js") or {}).get("frames")) or 0))
                    if observed_py_frames > 0 or observed_js_frames > 0:
                        saw_runtime_export = True
            except Exception:
                pass
            if proc.poll() is not None:
                break
            time.sleep(1.0)
        time.sleep(2.0)
        latest_py_export = drain_cdp_events(ws, latest_py_export=latest_py_export, console_events=console_events)
        try:
            status = fetch_server_status(base_url, scenario.name)
            posts_seen = max(posts_seen, int(status.get("posts", 0) or 0))
        except Exception:
            pass
        try:
            export_candidate = fetch_server_diag(base_url, scenario.name)
            if export_candidate and (not export_candidate.get("missing")):
                export_data = export_candidate
                py = export_candidate.get("py") or {}
                py_summary = py.get("summary") or {}
                observed_py_frames = max(observed_py_frames, int(py_summary.get("frames", 0) or 0))
                observed_js_frames = max(observed_js_frames, int(((export_candidate.get("js") or {}).get("frames")) or 0))
                if observed_py_frames > 0 or observed_js_frames > 0:
                    saw_runtime_export = True
        except Exception:
            pass
        if isinstance(latest_py_export, dict):
            export_data["py"] = latest_py_export
            py_summary = latest_py_export.get("summary") or {}
            observed_py_frames = max(observed_py_frames, int(py_summary.get("frames", 0) or 0))
            if observed_py_frames > 0:
                saw_runtime_export = True
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        exit_code = proc.poll()
        shutil.rmtree(user_data_dir, ignore_errors=True)
    export_data.setdefault("scenario", {})
    export_data["scenario"] = {
        "name": scenario.name,
        "duration_s": scenario.duration_s,
        "notes": scenario.notes,
        "url": url,
        "browser_runtime_path": bool(saw_runtime_export),
        "server_posts": int(posts_seen),
        "observed_py_frames": int(observed_py_frames),
        "observed_js_frames": int(observed_js_frames),
    }
    export_data["harness"] = {
        "started_at": round(started_at, 3),
        "finished_at": round(time.time(), 3),
        "chrome_exit_code": exit_code,
        "server_status": status,
        "real_browser_runtime_exercised": bool(saw_runtime_export),
        "console_events": console_events[-24:],
    }
    return export_data


def generate_report(all_exports: list[dict[str, Any]], out_dir: Path) -> tuple[Path, Path]:
    summary: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "root": str(ROOT),
        "build_dir": str(BUILD_DIR),
        "scenarios": [],
        "overall_candidates": [],
        "next_steps": [],
    }
    md_lines = [
        "# Browser Runtime Validation Report",
        "",
        "Measured on the actual pygbag web bundle through headless Chrome, with the running page publishing diagnostic captures back to the local test server.",
        "",
        "## Scenarios Executed",
        "",
    ]
    overall_candidate_names: list[str] = []
    overall_recommendations: list[str] = []
    for export_data in all_exports:
        scenario = export_data.get("scenario") or {}
        py = export_data.get("py") or {}
        js = export_data.get("js") or {}
        samples = list(py.get("samples") or [])
        segment_summary = {
            "early": summarize_segment(segment_samples(samples, "early")),
            "mid": summarize_segment(segment_samples(samples, "mid")),
            "late": summarize_segment(segment_samples(samples, "late")),
        }
        render_hotspots = summarize_render_subpasses(samples)
        render_build_costs = summarize_render_build_costs(samples)
        counter_growth = summarize_counter_growth(samples)
        candidates = build_root_cause_candidates(export_data)
        recommendations = build_recommendations(str(scenario.get("name", "")), export_data)
        overall_candidate_names.extend(c["candidate"] for c in candidates)
        overall_recommendations.extend(recommendations)
        transition_events = [e for e in (py.get("events") or []) if str(e.get("kind", "")).startswith("transition:")]
        scenario_summary = {
            "scenario": scenario,
            "py_summary": py.get("summary") or {},
            "js_summary": {
                "frames": js.get("frames", 0),
                "gap_percentiles_ms": js.get("gap_percentiles_ms", {}),
                "worst_gap_ms": js.get("worst_gap_ms", 0),
                "hitch_counts": js.get("hitch_counts", {}),
                "longest_hitch_streak_33": js.get("longest_hitch_streak_33", 0),
            },
            "transition_events": transition_events,
            "segments": segment_summary,
            "render_hotspots": render_hotspots,
            "render_build_costs": render_build_costs,
            "counter_growth": counter_growth,
            "candidates": candidates,
            "recommendations": recommendations,
            "py_dead": bool(export_data.get("py_dead", False)),
            "py_error": export_data.get("py_error", ""),
            "js_error": export_data.get("js_error", ""),
            "user_agent": export_data.get("user_agent", ""),
            "harness": export_data.get("harness", {}),
        }
        summary["scenarios"].append(scenario_summary)
        py_summary = py.get("summary") or {}
        late_growth_line = (
            ", ".join(f"{item['name']} (+{item['delta']})" for item in counter_growth[:5])
            if counter_growth
            else "none material"
        )
        hottest_render_line = (
            f"`{render_hotspots[0]['name']}` avg `{render_hotspots[0]['avg_ms']}` ms p95 `{render_hotspots[0]['p95_ms']}` ms"
            if render_hotspots
            else "`n/a`"
        )
        warmup_build_line = (
            f"`{render_build_costs[0]['name']}` avg `{render_build_costs[0]['avg_ms']}` ms p95 `{render_build_costs[0]['p95_ms']}` ms"
            if render_build_costs
            else "`n/a`"
        )
        md_lines.extend(
            [
                f"### `{scenario.get('name', 'unknown')}`",
                "",
                f"- URL: `{scenario.get('url', '')}`",
                f"- Runtime path exercised: `browser={scenario.get('browser_runtime_path', False)}`  `py_dead={bool(export_data.get('py_dead', False))}`  `posts={scenario.get('server_posts', 0)}`",
                f"- Python frame pacing: avg `{py_summary.get('avg_frame_ms', 0)}` ms, p95 `{(py_summary.get('frame_percentiles_ms') or {}).get('p95', 0)}` ms, p99 `{(py_summary.get('frame_percentiles_ms') or {}).get('p99', 0)}` ms, worst `{py_summary.get('worst_hitch_ms', 0)}` ms",
                f"- Browser rAF pacing: p95 `{(js.get('gap_percentiles_ms') or {}).get('p95', 0)}` ms, p99 `{(js.get('gap_percentiles_ms') or {}).get('p99', 0)}` ms, worst `{js.get('worst_gap_ms', 0)}` ms",
                f"- Hitch counters: py `{(py_summary.get('hitch_counts') or {})}`  js `{(js.get('hitch_counts') or {})}`",
                f"- Transition findings: `{len(transition_events)}` events, stalls `{len([e for e in transition_events if e.get('kind') == 'transition:stall'])}`",
                f"- Early/Mid/Late avg frame ms: `{segment_summary['early']['avg_frame_ms']}` / `{segment_summary['mid']['avg_frame_ms']}` / `{segment_summary['late']['avg_frame_ms']}`",
                f"- Hottest render subpass: {hottest_render_line}",
                f"- Background/build warmup cost: {warmup_build_line}",
                f"- Late-growing counters: {late_growth_line}",
                f"- Measured candidates: {', '.join(c['candidate'] for c in candidates)}",
            ]
        )
        if export_data.get("py_error") or export_data.get("js_error"):
            md_lines.append(f"- Errors: py=`{export_data.get('py_error', '')[:180]}` js=`{export_data.get('js_error', '')[:180]}`")
        md_lines.append("- Recommendations:")
        for rec in recommendations:
            md_lines.append(f"  - {rec}")
        md_lines.append("")
    ordered_candidates: list[str] = []
    for name in overall_candidate_names:
        if name not in ordered_candidates:
            ordered_candidates.append(name)
    ordered_recommendations: list[str] = []
    for rec in overall_recommendations:
        if rec not in ordered_recommendations:
            ordered_recommendations.append(rec)
    summary["overall_candidates"] = ordered_candidates
    summary["next_steps"] = ordered_recommendations
    md_lines.extend(
        [
            "## Overall Root-Cause Summary",
            "",
            "Measured results, not assumptions:",
            "",
            *(f"- {name}" for name in ordered_candidates),
            "",
            "## Prioritized Next Steps",
            "",
            *(f"{idx + 1}. {rec}" for idx, rec in enumerate(ordered_recommendations[:8])),
            "",
            "## Verification Scope",
            "",
            "- Actual browser/web runtime path: exercised through headless Chrome against the built `build/web` bundle.",
            "- Data collection path: the live browser page posted Python and JS profiler exports back to the local server during execution.",
            "- Caveat: this is still headless automation, so visible-browser subjective smoothness should be spot-checked manually after each targeted optimization pass.",
        ]
    )
    json_path = out_dir / "browser_runtime_diag_report.json"
    md_path = out_dir / "browser_runtime_diag_report.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run browser runtime diagnostics against the web build.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--server-port", type=int, default=8765)
    parser.add_argument("--chrome-debug-port", type=int, default=9222)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    chrome = choose_chrome()
    server_port = find_free_port(int(args.server_port))
    server = start_server(server_port)
    try:
        wait_http(f"http://127.0.0.1:{server_port}/")
        all_exports: list[dict[str, Any]] = []
        base_url = f"http://127.0.0.1:{server_port}/"
        for scenario in SCENARIOS:
            debug_port = find_free_port(int(args.chrome_debug_port))
            export_data = run_scenario(chrome, scenario, base_url, debug_port)
            raw_path = raw_dir / f"{scenario.name}.json"
            raw_path.write_text(json.dumps(export_data, ensure_ascii=False, indent=2), encoding="utf-8")
            all_exports.append(export_data)
        json_path, md_path = generate_report(all_exports, out_dir)
        print(json.dumps({"json_report": str(json_path), "markdown_report": str(md_path)}, indent=2))
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except Exception:
                server.kill()


if __name__ == "__main__":
    main()
