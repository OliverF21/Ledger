"""PyInstaller entrypoint for the bundled desktop backend.

The Tauri shell launches this binary. It forces desktop mode + a loopback bind
before importing `main` (whose module-level `bootstrap_desktop()` reads these),
then runs uvicorn. Kept separate from `main.py` so the dev workflow
(`uvicorn main:app` / `python main.py`) is unchanged.
"""

import os

os.environ.setdefault("LEDGER_DESKTOP", "1")
os.environ.setdefault("PORT", "17384")
os.environ.setdefault("LEDGER_BIND_HOST", "127.0.0.1")

import uvicorn  # noqa: E402
from main import app  # noqa: E402  (import triggers bootstrap_desktop())


def run() -> None:
    host = os.environ.get("LEDGER_BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "17384"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
