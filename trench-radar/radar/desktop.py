"""Desktop entry point (TrenchRadar.exe): dashboard + scheduler in one process.

Data and settings live in a per-user folder, not next to the exe:
  Windows: %LOCALAPPDATA%\\TrenchRadar   macOS/Linux: ~/.trench-radar
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    d = Path(base) / "TrenchRadar" if base else Path.home() / ".trench-radar"
    d.mkdir(parents=True, exist_ok=True)
    return d


def free_port(preferred: int) -> int:
    for port in (preferred, *range(preferred + 1, preferred + 20)):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("no free port between %d and %d" % (preferred, preferred + 19))


def keep_awake() -> bool:
    """Stop Windows from going to sleep while the app runs; collection stops when the PC sleeps.
    The display may still turn off. Closing a laptop lid follows its own power setting."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        return bool(ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED))
    except Exception:
        return False


def main() -> None:
    d = data_dir()
    env = d / "settings.env"
    if not env.exists():
        bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / ".env.example"
        if bundled.exists():
            shutil.copy(bundled, env)
    os.environ.setdefault("RADAR_DB", str(d / "radar.db"))
    os.environ["DASHBOARD_HOST"] = "127.0.0.1"          # the exe is local-only by design

    import logging

    import uvicorn

    from .api import create_app
    from .config import load_settings

    awake = keep_awake()
    settings = load_settings(env)
    port = free_port(settings.dashboard_port)
    url = f"http://127.0.0.1:{port}/"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print("=" * 64, flush=True)
    print(" TRENCH//RADAR  -  research only, no trading or launches", flush=True)
    print(f" Dashboard: {url}", flush=True)
    print(f" Data + settings: {d}", flush=True)
    print(f"   edit {env.name} there to add API keys, then restart", flush=True)
    print(" Keep this window open to keep collecting. Close it to stop.", flush=True)
    if awake:
        print(" Windows won't sleep while this runs (the screen can still turn off).", flush=True)
    print(" Live data: every pump.fun launch and trade, read from the Solana chain", flush=True)
    print(" (uses about 0.3 MB/s of download). 'chain/pump_stream ok' each minute", flush=True)
    print(" means it is listening. reddit / x_api are optional extras.", flush=True)
    print("=" * 64, flush=True)
    threading.Thread(target=lambda: (time.sleep(2.5), webbrowser.open(url)), daemon=True).start()
    uvicorn.run(create_app(settings, with_scheduler=True), host="127.0.0.1", port=port,
                log_level="warning", log_config=None)


if __name__ == "__main__":
    main()
