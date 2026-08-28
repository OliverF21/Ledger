"""
Ledger Backend - Personal Finance Dashboard
FastAPI application entry point
"""

import os

# App-data bootstrap MUST run before importing any module that reads env at
# import time (app.security raises without ENCRYPTION_KEY; app.database builds
# its engine from DATABASE_URL at import). No-op unless LEDGER_DESKTOP or
# LEDGER_USE_APPDATA is set.
from app.bootstrap import bootstrap_desktop
bootstrap_desktop()

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Import database initialization
from app.budgets_db import init_budgets_db
from app.database import init_db, SessionLocal
from app.models import User

# Import routes
from app.routes import plaid, transactions, analytics, budgets, categories, settings, subscriptions, investments, portfolio_risk, weekly_email, proposals, crypto, goals
from app.routes import auth as auth_routes

from app.auth import require_auth
from app.plaid_service import PlaidService
from app.scheduler import init_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager for startup and shutdown events
    """
    # Startup
    # Desktop BYOK: never block launch on missing/invalid Plaid config.
    # validate_config() now only logs a warning (see plaid_service.py).
    PlaidService.validate_config()
    init_db()
    init_budgets_db()

    # Create default user if it doesn't exist
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == 1).first()
        if not user:
            user = User(id=1, username="default_user")
            db.add(user)
            db.commit()
    finally:
        db.close()

    # Start background scheduler
    init_scheduler()

    print("[OK] Ledger backend started")
    # Make it obvious which SQLite files are open (dev + desktop debugging).
    try:
        from app.database import DATABASE_URL
        from app.budgets_db import BUDGETS_DB_URL

        print(f"[DB] ledger:  {DATABASE_URL}")
        print(f"[DB] budgets: {BUDGETS_DB_URL}")
    except Exception as exc:  # pragma: no cover — never block startup on logging
        print(f"[DB] (could not report paths: {exc})")

    yield

    # Shutdown
    shutdown_scheduler()
    print("[SHUTDOWN] Ledger backend shutting down")


# Create FastAPI app
app = FastAPI(
    title="Ledger API",
    description="Personal Finance Dashboard - Powered by Plaid",
    version="0.1.0",
    lifespan=lifespan
)

# Configure CORS. CORS_ORIGINS is a comma-separated list of extra allowed
# origins (e.g. your production domain) layered on top of the local dev
# defaults -- unset by default, so behavior is unchanged until you set it.
_dev_origins = [
    "http://localhost:5173",  # Frontend dev
    "http://localhost:5174",  # Frontend dev (fallback port)
    "http://localhost:3000",  # Alternative frontend dev
]
_extra_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_dev_origins + _extra_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth + setup endpoints are intentionally unauthenticated (login/first-run).
app.include_router(auth_routes.router, prefix="/api")

# Include API routers (all require a valid Bearer token or X-API-Key)
_auth = [Depends(require_auth)]
app.include_router(plaid.router, prefix="/api", dependencies=_auth)
app.include_router(transactions.router, prefix="/api", dependencies=_auth)
app.include_router(analytics.router, prefix="/api", dependencies=_auth)
app.include_router(budgets.router, prefix="/api", dependencies=_auth)
app.include_router(categories.router, prefix="/api", dependencies=_auth)
app.include_router(settings.router, prefix="/api", dependencies=_auth)
app.include_router(subscriptions.router, prefix="/api", dependencies=_auth)
app.include_router(investments.router, prefix="/api", dependencies=_auth)
app.include_router(portfolio_risk.router, prefix="/api", dependencies=_auth)
app.include_router(crypto.router, prefix="/api", dependencies=_auth)
app.include_router(goals.router, prefix="/api", dependencies=_auth)
app.include_router(weekly_email.router, prefix="/api", dependencies=_auth)

# Proposals carry per-route auth (create = MCP service key; the rest = user
# session), so they are mounted WITHOUT the blanket require_auth dependency.
app.include_router(proposals.router, prefix="/api")


# ── Serve the built frontend (single-port deployment) ─────────────────────────
#
# When frontend/dist exists (produced by `npm run build`), FastAPI serves the
# SPA so the whole app runs as ONE service on :8000 — same-origin, no CORS, no
# separate Vite process. In dev (no dist) the SPA routes are skipped and "/"
# returns an API status payload, while the Vite dev server on :5173 proxies /api.
import sys

# Under PyInstaller (frozen) the bundle ships frontend/dist under sys._MEIPASS;
# in dev it sits at ../frontend/dist relative to this file.
if getattr(sys, "frozen", False):
    _DIST_DIR = os.path.join(sys._MEIPASS, "frontend", "dist")  # type: ignore[attr-defined]
else:
    _DIST_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
_SERVE_SPA = os.path.isdir(_DIST_DIR)
_INDEX_HTML = os.path.join(_DIST_DIR, "index.html")

if _SERVE_SPA:
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    _ASSETS_DIR = os.path.join(_DIST_DIR, "assets")
    if os.path.isdir(_ASSETS_DIR):
        app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")


@app.get("/", include_in_schema=False)
async def root():
    """Serve the SPA homepage when built; otherwise a small API status payload."""
    if _SERVE_SPA:
        # index.html references hashed /assets/*.js filenames that change on every
        # build; a cached index.html silently pins the webview to a stale JS
        # bundle after an app update (WebKit's HTTP cache persists across desktop
        # app reinstalls/updates, since it's keyed by bundle id, not app content).
        return FileResponse(_INDEX_HTML, headers={"Cache-Control": "no-store"})
    return {
        "status": "ok",
        "service": "Ledger API",
        "version": "0.1.0",
        "docs_url": "/docs",
    }


@app.get("/health", tags=["root"])
async def health(response: Response):
    """Detailed health check"""
    # The frontend relies on the `desktop` flag below being current on every
    # call (see openExternal.ts) — never let the webview's HTTP cache serve a
    # stale copy of it.
    response.headers["Cache-Control"] = "no-store"
    return {
        "status": "healthy",
        "database": "connected",  # TODO: Verify actual DB connection
        "scheduler": "running",   # TODO: Verify scheduler status
        # Lets the frontend tell desktop and browser apart without depending on
        # Tauri's JS bridge injection (unreliable for the External-URL window
        # this app loads — see usePlaidHostedLink's use of this).
        "desktop": os.environ.get("LEDGER_DESKTOP", "").strip().lower() in {"1", "true", "yes"},
    }


if _SERVE_SPA:
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_catch_all(full_path: str):
        """Serve any static file that exists (favicon, etc.), else index.html so
        client-side hash routing works on a hard refresh. /api, /docs, /health,
        and /assets are matched by their explicit routes first."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = os.path.normpath(os.path.join(_DIST_DIR, full_path))
        # Guard against path traversal escaping the dist directory.
        if candidate.startswith(os.path.normpath(_DIST_DIR)) and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_INDEX_HTML, headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    import uvicorn

    # Desktop mode: bind loopback only so the local API is never reachable from
    # other devices on the network. Non-desktop default stays 0.0.0.0.
    _desktop = os.environ.get("LEDGER_DESKTOP", "").strip().lower() in {"1", "true", "yes"}
    _bind_host = os.environ.get("LEDGER_BIND_HOST") or ("127.0.0.1" if _desktop else "0.0.0.0")
    _port = int(os.environ.get("PORT", "8000"))

    uvicorn.run(
        "main:app",
        host=_bind_host,
        port=_port,
        reload=not _desktop,
        log_level="info",
    )
