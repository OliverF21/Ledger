"""
Import historical transaction data from CSV into Ledger database
Usage: python import_historical_data.py path/to/historical_transaction_data.csv [--user-id 1]

Expected CSV columns: Date, Description, Amount, Category, Card, Flow
- Date: MM/DD/YYYY format
- Description: Merchant name
- Amount: Dollar amount (can include $ and commas)
- Category: User category
- Card: Account/card name (creates if not exists)
- Flow: "Expense", "Income", or "Savings"

Parsing/import rules live in app.csv_import so this CLI and the
POST /transactions/import API route can't drift apart.
"""

import sys
import csv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import models
from app.models import User, Base
from app.csv_import import REQUIRED_COLUMNS, get_or_create_manual_item, import_rows


def import_transactions_from_csv(csv_path, user_id=1):
    """
    Import transactions from CSV file into the database.
    Creates accounts (cards) as needed and links to a manual Item.
    """

    # Get database URL from env
    database_url = os.getenv('DATABASE_URL', 'sqlite:///ledger.db')
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
        echo=False,
    )
    Session = sessionmaker(bind=engine)
    session = Session()

    print(f"📂 Reading CSV: {csv_path}")
    print(f"💾 Database: {database_url}")
    print(f"👤 User ID: {user_id}")

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    # Ensure user exists
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        print(f"⚠️  User {user_id} not found. Creating...")
        user = User(id=user_id, username=f"user_{user_id}")
        session.add(user)
        session.commit()

    print("🔗 Resolving manual Item for imported transactions...")
    manual_item = get_or_create_manual_item(session, user_id)

    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            if not reader.fieldnames:
                print("❌ CSV file is empty or invalid")
                sys.exit(1)

            missing_cols = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
            if missing_cols:
                print(f"❌ Missing required columns: {', '.join(missing_cols)}")
                print(f"   Found columns: {', '.join(reader.fieldnames)}")
                sys.exit(1)

            stats = import_rows(session, reader, manual_item, log=print)
            session.commit()

            print("\n" + "=" * 80)
            print(f"📊 Import Summary:")
            print(f"   ✓ Transactions: {stats['transactions_imported']}")
            print(f"   ✓ Accounts (Cards): {len(stats['accounts_created'])}")
            print(f"   ⊘ Skipped: {stats['skipped']}")
            print(f"   ✗ Errors: {stats['errors']}")
            if stats['accounts_created']:
                print(f"   Cards created: {sorted(stats['accounts_created'])}")
            print("=" * 80)

    except FileNotFoundError:
        print(f"❌ File not found: {csv_path}")
        sys.exit(1)
    except Exception as e:
        session.rollback()
        print(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python import_historical_data.py <path_to_csv> [--user-id USER_ID]")
        print("\nExample:")
        print("  python import_historical_data.py ./historical_transactions.csv")
        print("  python import_historical_data.py ./data.csv --user-id 1")
        sys.exit(1)

    csv_path = sys.argv[1]
    user_id = 1

    # Parse optional user-id argument
    if len(sys.argv) > 2 and sys.argv[2] == '--user-id':
        try:
            user_id = int(sys.argv[3])
        except (IndexError, ValueError):
            print("Error: --user-id requires an integer value")
            sys.exit(1)

    import_transactions_from_csv(csv_path, user_id)
