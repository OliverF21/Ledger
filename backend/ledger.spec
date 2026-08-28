# PyInstaller spec for the bundled Ledger desktop backend (onedir).
# Build from backend/:  pyinstaller ledger.spec --noconfirm
#
# Produces dist/ledger-backend/ — a standalone FastAPI+uvicorn backend that
# serves the bundled frontend/dist and needs no venv. The Tauri shell launches
# dist/ledger-backend/ledger-backend.

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Bundle the built SPA so main.py's single-port serving works when frozen
# (main.py resolves it under sys._MEIPASS/frontend/dist).
datas = [("../frontend/dist", "frontend/dist")]
datas += collect_data_files("certifi")  # TLS bundle for outbound Plaid HTTPS

# Dynamic imports PyInstaller's static analysis can miss.
hiddenimports = []
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("app")            # routes/services/etc.
hiddenimports += collect_submodules("sqlalchemy.dialects.sqlite")
hiddenimports += collect_submodules("apscheduler")
hiddenimports += collect_submodules("yfinance")
hiddenimports += collect_submodules("curl_cffi")
hiddenimports += collect_submodules("scipy")
hiddenimports += collect_submodules("numpy")
hiddenimports += collect_submodules("keyring")
hiddenimports += collect_submodules("keyring.backends")
hiddenimports += collect_submodules("jaraco")
try:
    hiddenimports += collect_submodules("win32ctypes")  # keyring WinVault on Windows
except Exception:
    pass
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]

a = Analysis(
    ["desktop_main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ledger-backend",
    console=True,        # keep stdout/stderr for the shell to observe
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,    # native arch (arm64 here)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="ledger-backend",
)
