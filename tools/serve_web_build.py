from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


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
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    httpd = ThreadingHTTPServer(("127.0.0.1", int(args.port)), handler)
    print(f"Serving {root} on http://127.0.0.1:{int(args.port)}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
