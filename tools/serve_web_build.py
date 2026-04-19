from __future__ import annotations

import argparse
import json
import time
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class DiagStore:
    def __init__(self) -> None:
        self.latest: dict[str, dict] = {}
        self.posts: dict[str, list[dict]] = {}

    def _scenario_name(self, payload: dict, default: str = "") -> str:
        py = payload.get("py") or {}
        session = py.get("session") or {}
        scenario = str(session.get("scenario") or payload.get("scenario_name") or "").strip().lower()
        if scenario:
            return scenario
        location = str(payload.get("location") or "")
        try:
            parsed = urllib.parse.urlparse(location)
            params = urllib.parse.parse_qs(parsed.query or "")
            scenario = str((params.get("scenario") or [""])[-1] or "").strip().lower()
        except Exception:
            scenario = ""
        return scenario or str(default or "default")

    def record(self, payload: dict, default_scenario: str = "") -> dict:
        scenario = self._scenario_name(payload, default=default_scenario)
        stamped = dict(payload)
        stamped["_server"] = {
            "received_at_s": round(time.time(), 3),
            "scenario": scenario,
            "size_bytes": len(json.dumps(payload, ensure_ascii=False)),
        }
        self.latest[scenario] = stamped
        history = self.posts.setdefault(scenario, [])
        history.append({
            "received_at_s": stamped["_server"]["received_at_s"],
            "size_bytes": stamped["_server"]["size_bytes"],
            "py_frames": int((((payload.get("py") or {}).get("summary") or {}).get("frames") or 0)),
            "js_frames": int((((payload.get("js") or {}).get("frames")) or 0)),
        })
        if len(history) > 512:
            del history[:-512]
        return stamped

    def reset(self, scenario: str | None = None) -> None:
        if scenario:
            key = str(scenario).strip().lower()
            self.latest.pop(key, None)
            self.posts.pop(key, None)
            return
        self.latest.clear()
        self.posts.clear()

    def status(self, scenario: str | None = None) -> dict:
        if scenario:
            key = str(scenario).strip().lower()
            latest = self.latest.get(key)
            return {
                "scenario": key,
                "has_latest": latest is not None,
                "posts": len(self.posts.get(key, [])),
                "latest_server": (latest or {}).get("_server", {}),
            }
        return {
            "scenarios": sorted(self.latest.keys()),
            "post_counts": {key: len(val) for key, val in self.posts.items()},
        }


class ZGameWebHandler(SimpleHTTPRequestHandler):
    server_version = "ZGameWebServer/1.0"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _diag_query(self) -> tuple[str, dict[str, list[str]]]:
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path, urllib.parse.parse_qs(parsed.query or "")

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path, query = self._diag_query()
        store: DiagStore = getattr(self.server, "diag_store")
        if path == "/__zgame_diag/latest":
            scenario = str((query.get("scenario") or [""])[-1] or "").strip().lower()
            if scenario:
                payload = store.latest.get(scenario)
                self._write_json(200, payload or {"scenario": scenario, "missing": True})
                return
            self._write_json(200, {"scenarios": store.latest})
            return
        if path == "/__zgame_diag/status":
            scenario = str((query.get("scenario") or [""])[-1] or "").strip().lower()
            self._write_json(200, store.status(scenario or None))
            return
        if path == "/__zgame_diag/reset":
            scenario = str((query.get("scenario") or [""])[-1] or "").strip().lower()
            store.reset(scenario or None)
            self._write_json(200, {"ok": True, "scenario": scenario or ""})
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path, query = self._diag_query()
        if path != "/__zgame_diag":
            self.send_error(404, "Unsupported POST path")
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except Exception:
            length = 0
        raw = self.rfile.read(max(0, length))
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(payload, dict):
                raise TypeError("payload must be a JSON object")
        except Exception as exc:
            self._write_json(400, {"ok": False, "error": str(exc)})
            return
        scenario = str((query.get("scenario") or [""])[-1] or "").strip().lower()
        store: DiagStore = getattr(self.server, "diag_store")
        recorded = store.record(payload, default_scenario=scenario)
        self._write_json(200, {"ok": True, "scenario": recorded.get("_server", {}).get("scenario", "")})


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the built web bundle.")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on.")
    parser.add_argument(
        "--dir",
        default=str(Path(__file__).resolve().parents[1] / "build" / "web"),
        help="Directory to serve.",
    )
    args = parser.parse_args()

    root = Path(args.dir).resolve()
    handler = partial(ZGameWebHandler, directory=str(root))
    httpd = ThreadingHTTPServer(("127.0.0.1", int(args.port)), handler)
    httpd.diag_store = DiagStore()
    print(f"Serving {root} on http://127.0.0.1:{int(args.port)}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
