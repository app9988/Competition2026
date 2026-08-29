"""One-command launcher for the Shopping Copilot demo.

    python run_demo.py            # start on http://127.0.0.1:8000 and open the browser
    python run_demo.py --port 8123
    python run_demo.py --no-open

Checks its prerequisites first and prints a plain-language fix for each problem,
so a failed start never leaves you guessing.
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent          # solution/
CATALOG = HERE.parent / "techjam-conversational-search" / "data" / "catalog.jsonl"


def fail(msg: str, fix: str) -> None:
    print(f"\n  [X] {msg}\n      -> {fix}\n")
    sys.exit(1)


def port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-open", action="store_true", help="do not launch a browser")
    args = ap.parse_args()

    print("Shopping Copilot - demo launcher")
    print("=" * 52)

    if sys.version_info < (3, 10):
        fail(f"Python {sys.version_info.major}.{sys.version_info.minor} is too old.",
             "Python 3.10 or newer is required.")
    print(f"  [ok] Python {sys.version_info.major}.{sys.version_info.minor}")

    try:
        import uvicorn  # noqa: F401
        import fastapi  # noqa: F401
    except ImportError as e:
        fail(f"Missing package: {e.name}",
             "Install the demo dependencies:  pip install fastapi uvicorn")
    print("  [ok] fastapi + uvicorn")

    if not CATALOG.exists():
        fail(f"Catalog not found at {CATALOG}",
             "Download catalog.jsonl.gz from the competition GitHub Release, "
             "decompress it, and place it at that path.")
    print(f"  [ok] catalog ({CATALOG.stat().st_size / 1e6:.1f} MB)")

    if port_busy(args.port):
        fail(f"Port {args.port} is already in use.",
             f"Either open http://127.0.0.1:{args.port} (it may already be running), "
             f"or start on another port:  python run_demo.py --port {args.port + 1}")
    print(f"  [ok] port {args.port} is free")

    url = f"http://127.0.0.1:{args.port}"
    print("=" * 52)
    print("  Building in-memory indexes over 50,000 products.")
    print("  This takes ~20-40 s on first start. The page opens automatically.")
    print(f"  URL: {url}      (Ctrl+C to stop)")
    print("=" * 52 + "\n")

    if not args.no_open:
        def open_when_ready() -> None:
            for _ in range(120):
                time.sleep(1)
                if port_busy(args.port):
                    time.sleep(1.5)          # let startup finish before the first request
                    webbrowser.open(url)
                    return
        threading.Thread(target=open_when_ready, daemon=True).start()

    sys.path.insert(0, str(HERE))
    import uvicorn
    uvicorn.run("server.app:app", host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
