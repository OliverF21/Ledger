"""
Transaction management endpoints.
- GET /transactions: List transactions with filtering
- POST /transactions/import: Import transactions from CSV
- PUT /transactions/{id}/category: Update transaction category
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional
import csv
import io

from app.analytics_shared import month_bounds
from app.categorization import apply_category_to_transactions, find_similar_transactions
from app.csv_import import REQUIRED_COLUMNS, get_or_create_manual_item, import_rows
from app.database import get_db
from app.enrichment import parse_enrichment_json
from app.errors import log_and_raise
from app.models import Transaction, Account, User

router = APIRouter(prefix="/transactions", tags=["transactions"])


class TransactionEnrichment(BaseModel):
    counterparties: list[dict] | None = None
    location: dict | None = None
    pfc_confidence: str | None = None
    category_icon_url: str | None = None
    description_raw: str | None = None


class TransactionResponse(BaseModel):
    id: int
    account_id: int
    account_name: str | None
    merchant: str
    amount: float          # effective amount (split applied)
    original_amount: float # raw Plaid amount before split
    user_split_pct: float | None
    date: date
    category_user: str | None
    category_plaid: str | None
    category_plaid_detailed: str | None = None
    merchant_logo_url: str | None = None
    payment_channel: str | None = None
    enrichment: TransactionEnrichment | None = None
    pending: bool = False
    manual_override: bool = False
    hidden: bool = False


def _transaction_response(txn: Transaction, account_name: str | None) -> TransactionResponse:
    extra = parse_enrichment_json(txn.enrichment_json) or {}
    enrichment = TransactionEnrichment(
        counterparties=extra.get("counterparties"),
        location=extra.get("location"),
        pfc_confidence=extra.get("pfc_confidence"),
        category_icon_url=extra.get("category_icon_url"),
        description_raw=extra.get("description_raw"),
    )
    if not any([
        enrichment.counterparties,
        enrichment.location,
        enrichment.pfc_confidence,
        enrichment.category_icon_url,
        enrichment.description_raw,
    ]):
        enrichment = None

    return TransactionResponse(
        id=txn.id,
        account_id=txn.account_id,
        account_name=account_name,
        merchant=txn.merchant,
        amount=round(float(txn.amount) * float(txn.user_split_pct or 1), 2),
        original_amount=round(float(txn.amount), 2),
        user_split_pct=float(txn.user_split_pct) if txn.user_split_pct is not None else None,
        date=txn.date,
        category_user=txn.category_user,
        category_plaid=txn.category_plaid,
        category_plaid_detailed=txn.category_plaid_detailed,
        merchant_logo_url=txn.merchant_logo_url,
        payment_channel=txn.payment_channel,
        enrichment=enrichment,
        pending=bool(txn.pending or False),
        manual_override=bool(txn.manual_override or False),
        hidden=bool(txn.hidden or False),
    )


class TransactionsListResponse(BaseModel):
    transactions: list[TransactionResponse]
    total: int


class UpdateCategoryRequest(BaseModel):
    category: str


class SplitRequest(BaseModel):
    pct: float  # 0.0–1.0, e.g. 0.5 for splitting 50/50


class ImportStats(BaseModel):
    transactions_imported: int
    accounts_created: list[str]
    errors: int
    skipped: int


class ImportCSVResponse(BaseModel):
    success: bool
    message: str
    stats: ImportStats


@router.get("", response_model=TransactionsListResponse)
async def list_transactions(
    skip: int = 0,
    limit: int = 100,
    month: Optional[str] = Query(None, description="YYYY-MM, optional month filter"),
    exclude_hidden: bool = Query(False, description="Omit user-hidden transactions"),
    db: Session = Depends(get_db)
):
    """List non-removed transactions with pagination. Hidden transactions are included unless exclude_hidden=true."""
    try:
        query = (
            db.query(Transaction, Account.name.label("account_name"))
            .outerjoin(Account, Transaction.account_id == Account.id)
            .filter(Transaction.removed == False)
        )
        if exclude_hidden:
            query = query.filter(Transaction.hidden == False)
        if month:
            year, mon = int(month[:4]), int(month[5:7])
            start, end = month_bounds(year, mon)
            query = query.filter(Transaction.date >= start, Transaction.date < end)

        rows = (
            query
            .order_by(Transaction.date.desc(), Transaction.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        total = db.query(Transaction).filter(Transaction.removed == False).count()
        result = [
            _transaction_response(txn, account_name)
            for txn, account_name in rows
        ]
        return TransactionsListResponse(transactions=result, total=total)
    except Exception as e:
        log_and_raise(e, status_code=400)


@router.put("/{transaction_id}/category")
async def update_transaction_category(
    transaction_id: int,
    request: UpdateCategoryRequest,
    db: Session = Depends(get_db)
):
    """Update a transaction's category and mark as manually overridden."""
    try:
        transaction = db.query(Transaction).filter(
            Transaction.id == transaction_id
        ).first()

        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")

        transaction.category_user = request.category
        transaction.manual_override = True
        transaction.updated_at = datetime.utcnow()
        db.commit()

        return {
            "success": True,
            "category": transaction.display_category,
            "manual_override": transaction.manual_override
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


class SimilarTransaction(BaseModel):
    id: int
    merchant: str
    date: date
    amount: float
    category_user: str | None
    category_plaid: str | None


class SimilarTransactionsResponse(BaseModel):
    merchant: str
    count: int
    transactions: list[SimilarTransaction]


@router.get("/{transaction_id}/similar", response_model=SimilarTransactionsResponse)
async def get_similar_transactions(transaction_id: int, db: Session = Depends(get_db)):
    """
    Other transactions sharing this one's merchant name that haven't been
    manually categorized -- candidates for a bulk recategorize.
    """
    try:
        txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not txn:
            raise HTTPException(status_code=404, detail="Transaction not found")

        similar = find_similar_transactions(db, txn.merchant, exclude_id=transaction_id)
        return SimilarTransactionsResponse(
            merchant=txn.merchant,
            count=len(similar),
            transactions=[
                SimilarTransaction(
                    id=t.id,
                    merchant=t.merchant,
                    date=t.date,
                    amount=float(t.amount),
                    category_user=t.category_user,
                    category_plaid=t.category_plaid,
                )
                for t in similar
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        log_and_raise(e, status_code=400)


class BulkCategorizeRequest(BaseModel):
    transaction_ids: list[int]
    category: str


class BulkCategorizeResponse(BaseModel):
    success: bool
    updated: int


@router.post("/bulk-categorize", response_model=BulkCategorizeResponse)
async def bulk_categorize(req: BulkCategorizeRequest, db: Session = Depends(get_db)):
    """Apply a category to a set of transactions at once (e.g. all matches of 'similar')."""
    try:
        category = req.category.strip()
        if not category:
            raise HTTPException(status_code=400, detail="category is required")
        updated = apply_category_to_transactions(db, req.transaction_ids, category)
        db.commit()
        return BulkCategorizeResponse(success=True, updated=updated)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


@router.post("/{transaction_id}/toggle-hide")
async def toggle_hide(transaction_id: int, db: Session = Depends(get_db)):
    """Toggle the hidden flag on a transaction."""
    try:
        txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not txn:
            raise HTTPException(status_code=404, detail="Transaction not found")
        txn.hidden = not bool(txn.hidden)
        txn.updated_at = datetime.utcnow()
        db.commit()
        return {"success": True, "hidden": bool(txn.hidden)}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


@router.put("/{transaction_id}/split")
async def set_split(transaction_id: int, request: SplitRequest, db: Session = Depends(get_db)):
    """Set the user's fractional share of a transaction amount."""
    try:
        if not (0.0 < request.pct <= 1.0):
            raise HTTPException(status_code=400, detail="pct must be between 0 (exclusive) and 1 (inclusive)")
        txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
        if not txn:
            raise HTTPException(status_code=404, detail="Transaction not found")
        txn.user_split_pct = request.pct if request.pct < 1.0 else None
        txn.updated_at = datetime.utcnow()
        db.commit()
        return {"success": True, "user_split_pct": float(txn.user_split_pct) if txn.user_split_pct else None}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)


@router.post("/import", response_model=ImportCSVResponse)
async def import_transactions_csv(
    file: UploadFile = File(...),
    user_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Import transactions from CSV file.
    Expected CSV columns: Date, Description, Amount, Category, Card, Flow
    """
    try:
        # Validate user exists
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

        manual_item = get_or_create_manual_item(db, user_id)

        # Read and parse CSV
        contents = await file.read()
        csv_file = io.StringIO(contents.decode('utf-8-sig'))
        reader = csv.DictReader(csv_file)

        if not reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV file is empty")

        missing_cols = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
        if missing_cols:
            raise HTTPException(
                status_code=400,
                detail=f"Missing columns: {', '.join(missing_cols)}"
            )

        stats = import_rows(db, reader, manual_item)
        db.commit()

        return ImportCSVResponse(
            success=True,
            message=f"Successfully imported {stats['transactions_imported']} transactions",
            stats=ImportStats(**stats)
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_and_raise(e, status_code=400)
