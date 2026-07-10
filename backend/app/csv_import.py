"""
Shared CSV transaction import logic, used by both the /transactions/import
API route and the import_historical_data.py CLI script so the parsing
rules (amount sign, account inference, dedupe) can't drift between them.

Expected CSV columns: Date, Description, Amount, Category, Card, Flow
- Date: MM/DD/YYYY
- Amount: dollar amount, may include $ and commas
- Flow: "Expense", "Income", or "Savings"
- Card: account/card name (created under a "manual_import" Item if new)
"""

from datetime import datetime
from typing import Callable, Iterable

from sqlalchemy.orm import Session

from app.models import Account, Item, Transaction

REQUIRED_COLUMNS = ['Date', 'Description', 'Amount', 'Category', 'Card', 'Flow']


def get_or_create_manual_item(db: Session, user_id: int) -> Item:
    """Find or create the synthetic Item that manual/CSV-imported accounts hang off of."""
    manual_item = db.query(Item).filter(
        Item.user_id == user_id,
        Item.item_id == "manual_import",
    ).first()
    if not manual_item:
        manual_item = Item(
            user_id=user_id,
            item_id="manual_import",
            institution_name="Manual Import",
            access_token_encrypted="",  # Not used for manual imports
        )
        db.add(manual_item)
        db.flush()
    return manual_item


def import_rows(
    db: Session,
    rows: Iterable[dict],
    manual_item: Item,
    log: Callable[[str], None] = lambda _msg: None,
) -> dict:
    """
    Import transaction rows (as produced by csv.DictReader) into the DB.
    Creates an Account per distinct Card name under manual_item as needed.
    Does not commit -- caller controls the transaction boundary.

    `log` is called with a one-line status message per row (callers that
    don't care, e.g. the API route, can leave it as a no-op).

    Returns stats: transactions_imported, accounts_created, errors, skipped.
    """
    stats = {"transactions_imported": 0, "accounts_created": [], "errors": 0, "skipped": 0}

    for row_num, row in enumerate(rows, start=2):  # start=2 to account for the header row
        try:
            date_str = row['Date'].strip()
            description = row['Description'].strip()
            amount_str = row['Amount'].strip().replace('$', '').replace(',', '')
            category = row['Category'].strip()
            card_name = row['Card'].strip()
            flow = row['Flow'].strip()

            if not all([date_str, description, amount_str, card_name, flow]):
                stats["skipped"] += 1
                log(f"Row {row_num}: skipped (missing required fields)")
                continue

            try:
                amount = float(amount_str)
            except ValueError:
                raise ValueError(f"Invalid amount: {amount_str}")

            if flow == 'Expense':
                amount = -abs(amount)
            elif flow == 'Income':
                # Match Plaid convention: credits (income) are negative in the DB.
                amount = -abs(amount)
            elif flow == 'Savings':
                pass  # keep sign as-is
            else:
                raise ValueError(f"Invalid flow: {flow} (must be Expense, Income, or Savings)")

            try:
                txn_date = datetime.strptime(date_str, '%m/%d/%Y').date()
            except ValueError:
                raise ValueError(f"Invalid date format: {date_str} (expected MM/DD/YYYY)")

            account = db.query(Account).filter(
                Account.item_id == manual_item.id,
                Account.name == card_name,
            ).first()

            if not account:
                account_type = 'credit' if any(
                    x in card_name.lower() for x in ['card', 'credit', 'amex', 'visa', 'capital', 'apple']
                ) else 'depository'

                account = Account(
                    item_id=manual_item.id,
                    name=card_name,
                    type=account_type,
                    subtype='credit card' if account_type == 'credit' else 'checking',
                    plaid_account_id=f'manual_{card_name.lower().replace(" ", "_")}',
                )
                db.add(account)
                db.flush()
                if card_name not in stats["accounts_created"]:
                    stats["accounts_created"].append(card_name)

            db.add(Transaction(
                account_id=account.id,
                merchant=description,
                amount=amount,
                date=txn_date,
                category_user=category if category else None,
                pending=False,
                removed=False,
                manual_override=True,
            ))
            stats["transactions_imported"] += 1
            log(f"Row {row_num}: {txn_date} | {description} | ${amount:.2f} | {category} | {card_name}")

        except (ValueError, KeyError) as e:
            stats["errors"] += 1
            log(f"Row {row_num}: error parsing - {e}")
        except Exception as e:
            stats["errors"] += 1
            log(f"Row {row_num}: unexpected error - {e}")

    return stats
