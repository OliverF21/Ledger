"""
Weekly summary email: manual preview + send-now.

- GET  /weekly-email/preview : render the current week's summary as HTML
                               (returns the exact email body for a browser preview)
- POST /weekly-email/send    : compute and send the email right now via Resend

Both are useful for testing the content without waiting for the Monday cron.
The scheduled send lives in app/scheduler.py.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.budgets_db import get_budgets_db
from app.database import get_db
from app.errors import log_and_raise
from app.weekly_summary import (
    _config,
    compute_weekly_summary,
    render_html,
    send_weekly_summary,
)

router = APIRouter(prefix="/weekly-email", tags=["weekly-email"])


@router.get("/preview", response_class=HTMLResponse)
async def preview_weekly_email(
    db: Session = Depends(get_db),
    bdb: Session = Depends(get_budgets_db),
):
    """Render the current week's summary email as HTML (no send)."""
    try:
        summary = compute_weekly_summary(db, bdb)
        return HTMLResponse(content=render_html(summary))
    except Exception as e:
        log_and_raise(e)


@router.post("/send")
async def send_weekly_email_now(
    db: Session = Depends(get_db),
    bdb: Session = Depends(get_budgets_db),
):
    """Send the weekly summary immediately. 400 if the transport isn't configured."""
    if _config(db) is None:
        raise HTTPException(
            status_code=400,
            detail="Weekly email not configured. Add a Resend API key and enable it with a recipient in Settings.",
        )
    try:
        ok = send_weekly_summary(db, bdb, force=True)
        if not ok:
            raise HTTPException(status_code=502, detail="Email delivery failed. Check server logs.")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise(e)
