"""
Subscription/recurring-transaction detection endpoint.
- GET /subscriptions: detected recurring series (see app/subscriptions.py)
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import log_and_raise
from app.subscriptions import TRAILING_MONTHS, detect_recurring_series

router = APIRouter(tags=["subscriptions"])


class SubscriptionItem(BaseModel):
    merchant: str
    category: str
    cadence: str
    average_amount: float
    last_date: str
    next_expected_date: str
    occurrence_count: int


class SubscriptionsResponse(BaseModel):
    subscriptions: list[SubscriptionItem]


@router.get("/subscriptions", response_model=SubscriptionsResponse)
async def get_subscriptions(
    months: int = Query(TRAILING_MONTHS, ge=3, le=24),
    db: Session = Depends(get_db),
):
    """Detected recurring (subscription-like) charges over the trailing window."""
    try:
        results = detect_recurring_series(db, months=months)
        return SubscriptionsResponse(subscriptions=[
            SubscriptionItem(
                merchant=r.merchant,
                category=r.category,
                cadence=r.cadence,
                average_amount=r.average_amount,
                last_date=r.last_date.isoformat(),
                next_expected_date=r.next_expected_date.isoformat(),
                occurrence_count=r.occurrence_count,
            )
            for r in results
        ])
    except Exception as e:
        log_and_raise(e)
