"""
SQLAlchemy ORM models for Ledger.
Defines User, Item, Account, Transaction, Category, CategoryRule, BalanceSnapshot.
"""

from datetime import datetime, date
from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, ForeignKey, Text, Numeric, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    """Single user account (hardcoded to id=1 for now, extensible for multi-user later)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(255), unique=True, nullable=False, default="default_user")
    # NULL password_hash = no account created yet (setup mode); set on registration.
    # Additively patched onto existing DBs by database._ensure_columns(). See auth.py.
    password_hash = Column(Text, nullable=True)
    # Hashed recovery code (same scrypt hashing as password_hash), shown to the
    # user exactly once — at registration, and again each time it's regenerated
    # or consumed by a reset. NULL means no recovery code has been set (e.g. an
    # account created before this feature existed); "forgot password" then has
    # no path but wiping the local app-data dir. See routes/auth.py.
    recovery_code_hash = Column(Text, nullable=True)
    # Account recovery email — separate from weekly_email_to (the weekly-digest
    # recipient, which may legitimately differ or be unset). Optional; used only
    # to receive a password-reset code, never to authenticate anything by itself.
    email = Column(String(255), nullable=True)
    # Hash of the currently outstanding email reset code (same scrypt format as
    # recovery_code_hash), plus its expiry. Both NULL when no reset is pending.
    reset_code_hash = Column(Text, nullable=True)
    reset_code_expires_at = Column(DateTime, nullable=True)
    # Friendly display name captured at registration; personalizes the homepage
    # header and the weekly summary email. Falls back to username when unset.
    display_name = Column(String(255), nullable=True)
    # Alert preferences. Note: _ensure_columns()'s ALTER TABLE ADD COLUMN carries no
    # DEFAULT clause, so these land NULL on existing rows despite the default= below
    # (which only applies to newly-inserted rows) - callers must coalesce NULL to the
    # documented default themselves, not assume the ORM default has taken effect.
    alert_budget_exceeded_enabled = Column(Boolean, default=True)
    alert_large_txn_enabled = Column(Boolean, default=False)
    alert_large_txn_threshold = Column(Numeric(19, 4), default=500)
    # JSON list of alert keys already delivered to ALERT_WEBHOOK_URL (see
    # app/notifications.py); pruned to currently-active alerts on each cycle.
    alerts_webhook_state = Column(Text, nullable=True)
    # Weekly budget-pace summary email (see app/weekly_summary.py). Requires
    # RESEND_API_KEY (env, a send-only API key) in addition to this toggle +
    # recipient — both must be set for the scheduler to actually send.
    weekly_email_enabled = Column(Boolean, default=False)
    weekly_email_to = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    items = relationship("Item", back_populates="user", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    category_rules = relationship("CategoryRule", back_populates="user", cascade="all, delete-orphan")


class AppConfig(Base):
    """Key/value runtime configuration stored in the main DB (desktop BYOK).

    Secret values (e.g. the Plaid secret) are Fernet-encrypted via
    app.security before storage; is_secret marks them for decrypt-on-read.
    """
    __tablename__ = "app_config"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=False, nullable=False)


class Item(Base):
    """
    Plaid Item: represents a single Plaid connection (one bank/institution).
    Stores encrypted access token.
    """
    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_id = Column(String(255), unique=True, nullable=False)  # Plaid's item ID
    institution_name = Column(String(255), nullable=True)  # e.g., "Chase", "Bank of America"
    institution_id = Column(String(64), nullable=True)  # Plaid institution_id, e.g. ins_56
    institution_logo = Column(Text, nullable=True)  # data:image/png;base64,... from Plaid
    institution_color = Column(String(16), nullable=True)  # brand hex, e.g. #095aa6
    access_token_encrypted = Column(Text, nullable=False)  # Fernet-encrypted, never decrypted except for API calls
    last_sync_cursor = Column(Text, nullable=True)  # Plaid's sync cursor for incremental sync
    last_synced_at = Column(DateTime, nullable=True)
    # ok | login_required | error — set by sync_engine after each sync attempt.
    sync_status = Column(String(32), nullable=True, default="ok")
    last_sync_error = Column(Text, nullable=True)  # truncated Plaid/user message on failure
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="items")
    accounts = relationship("Account", back_populates="item", cascade="all, delete-orphan")


# ── Crypto wallets (read-only, non-Plaid) ─────────────────────────────────────


class Account(Base):
    """
    Bank/credit account (checking, savings, credit card, etc.).
    One Item can have multiple Accounts.
    """
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    plaid_account_id = Column(String(255), nullable=False)  # Plaid's account ID
    name = Column(String(255), nullable=False)  # e.g., "Checking Account", "Visa Card"
    type = Column(String(50), nullable=False)  # "depository", "credit", "investment", etc.
    subtype = Column(String(50), nullable=True)  # "checking", "savings", "credit card", etc.
    current_balance = Column(Numeric(19, 4), nullable=True)  # Last known balance from Plaid
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    item = relationship("Item", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account", cascade="all, delete-orphan")
    balance_snapshots = relationship("BalanceSnapshot", back_populates="account", cascade="all, delete-orphan")
    holdings = relationship("Holding", back_populates="account", cascade="all, delete-orphan")
    investment_transactions = relationship("InvestmentTransaction", back_populates="account", cascade="all, delete-orphan")


class Transaction(Base):
    """
    Individual transaction (debit, credit, purchase, etc.).
    Stores both Plaid's auto-categorization and user's manual overrides.
    """
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    plaid_transaction_id = Column(String(255), nullable=True, unique=True)  # Plaid's transaction ID (if from Plaid)
    merchant = Column(String(255), nullable=False)  # e.g., "Starbucks #1234"
    amount = Column(Numeric(19, 4), nullable=False)  # Positive for expenses/debits, negative for income/deposits
    date = Column(Date, nullable=False)  # Transaction date (not datetime; Plaid provides dates)
    category_plaid = Column(String(255), nullable=True)  # Plaid PFC primary, e.g. FOOD_AND_DRINK
    category_plaid_detailed = Column(String(255), nullable=True)  # Plaid PFC detailed, e.g. FOOD_AND_DRINK_RESTAURANTS
    merchant_logo_url = Column(String(512), nullable=True)  # 100x100 merchant logo from Plaid
    payment_channel = Column(String(20), nullable=True)  # online | in store | other
    original_description = Column(String(512), nullable=True)  # bank memo when Plaid provides it
    transaction_code = Column(String(64), nullable=True)  # Plaid transaction_code (transfer, purchase, …)
    enrichment_json = Column(Text, nullable=True)  # counterparties, payment_meta, location, confidence, icons
    category_user = Column(String(255), nullable=True)  # User-defined category override
    manual_override = Column(Boolean, default=False)  # True if user manually changed category
    pending = Column(Boolean, default=False)  # True if transaction is still pending
    removed = Column(Boolean, default=False)  # True if Plaid marked it as removed
    hidden = Column(Boolean, default=False, nullable=False)  # User-hidden from all views
    user_split_pct = Column(Numeric(5, 4), nullable=True)  # e.g., 0.5 = user's 50% share
    notes = Column(Text, nullable=True)  # User notes
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="transactions")

    @property
    def display_category(self):
        """Returns user-defined category if set, otherwise Plaid category."""
        return self.category_user or self.category_plaid_detailed or self.category_plaid

    @property
    def rollup_category(self):
        """Primary category for charts/aggregates (ignores enrichment sub-labels)."""
        from app.analytics_shared import rollup_category_key
        return rollup_category_key(
            self.category_user,
            self.category_plaid,
            self.category_plaid_detailed,
            "Uncategorized",
        )


class Category(Base):
    """User-defined spending category (e.g., "Groceries", "Dining Out", "Gas")."""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)  # e.g., "Groceries"
    description = Column(Text, nullable=True)
    color = Column(String(7), nullable=True)  # Hex color for charts, e.g., "#FF6B6B"
    icon = Column(String(50), nullable=True)  # Icon name or emoji, e.g., "🛒"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="categories")
    rules = relationship("CategoryRule", back_populates="category", cascade="all, delete-orphan")


class CategoryRule(Base):
    """
    Rule to auto-categorize transactions based on merchant name pattern.
    Example: merchant_pattern="Starbucks.*" → category="Dining Out"
    """
    __tablename__ = "category_rules"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    merchant_pattern = Column(String(255), nullable=False)  # Regex pattern, e.g., "Amazon.*"
    description_pattern = Column(String(255), nullable=True)  # Optional regex vs. original_description; AND'd with merchant_pattern when set
    priority = Column(Integer, nullable=True)  # Explicit match order (lower first); NULL falls back to id order
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="category_rules")
    category = relationship("Category", back_populates="rules")


class BalanceSnapshot(Base):
    """
    Daily snapshot of account balance for net-worth tracking.
    Plaid doesn't provide historical balances, so we take daily snapshots.
    """
    __tablename__ = "balance_snapshots"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    balance = Column(Numeric(19, 4), nullable=False)  # Balance at end of day
    snapshot_date = Column(Date, nullable=False)  # Date of snapshot
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="balance_snapshots")


class CryptoWallet(Base):
    """Self-custody wallet address tracked read-only for net worth."""
    __tablename__ = "crypto_wallets"
    __table_args__ = (UniqueConstraint("user_id", "address", name="uq_crypto_wallet_user_address"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    address = Column(String(42), nullable=False)  # checksummed or lowercased 0x…
    label = Column(String(255), nullable=True)
    chain = Column(String(64), nullable=False, default="robinhood-mainnet")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("Account")
    holdings = relationship(
        "CryptoHolding",
        back_populates="wallet",
        cascade="all, delete-orphan",
    )


class CryptoHolding(Base):
    """Per-token balance for a crypto wallet (detail only; net worth uses Account.current_balance)."""
    __tablename__ = "crypto_holdings"
    __table_args__ = (
        UniqueConstraint("wallet_id", "contract_address", name="uq_crypto_holding_wallet_contract"),
    )

    id = Column(Integer, primary_key=True)
    wallet_id = Column(Integer, ForeignKey("crypto_wallets.id"), nullable=False)
    symbol = Column(String(32), nullable=False)
    # Empty string for native ETH (UNIQUE treats NULLs as distinct on SQLite).
    contract_address = Column(String(42), nullable=False, default="")
    decimals = Column(Integer, nullable=False, default=18)
    balance = Column(Numeric(36, 18), nullable=False, default=0)
    usd_value = Column(Numeric(19, 4), nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    wallet = relationship("CryptoWallet", back_populates="holdings")


class Security(Base):
    """Plaid security metadata (not user-specific beyond the security_id key)."""
    __tablename__ = "securities"

    id = Column(Integer, primary_key=True)
    plaid_security_id = Column(String(255), unique=True, nullable=False)
    ticker_symbol = Column(String(32), nullable=True)  # e.g. "AAPL"
    name = Column(String(512), nullable=True)
    type = Column(String(64), nullable=True)  # equity, etf, cryptocurrency, cash, etc.
    subtype = Column(String(64), nullable=True)
    close_price = Column(Numeric(19, 4), nullable=True)
    close_price_as_of = Column(Date, nullable=True)
    iso_currency_code = Column(String(3), nullable=True)
    is_cash_equivalent = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    holdings = relationship("Holding", back_populates="security")
    investment_transactions = relationship("InvestmentTransaction", back_populates="security")


class MarketPrice(Base):
    """
    Daily close price for a ticker symbol, backfilled from an external market-data
    provider (yfinance — see app/price_provider.py). Plaid only ever gives the
    latest close (Security.close_price), so this table is what makes historical
    return/risk calculations (volatility, Sharpe, VaR, drawdown, beta) possible.
    Keyed by ticker string rather than security_id: benchmark tickers (SPY,
    BTC-USD) have no corresponding Security row since nothing holds them.
    """
    __tablename__ = "market_prices"
    __table_args__ = (UniqueConstraint("ticker", "price_date", name="uq_market_price_ticker_date"),)

    id = Column(Integer, primary_key=True)
    ticker = Column(String(32), nullable=False)
    price_date = Column(Date, nullable=False)
    close_price = Column(Numeric(19, 6), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Holding(Base):
    """User's position in a security within an investment account."""
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("account_id", "security_id", name="uq_holding_account_security"),)

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    security_id = Column(Integer, ForeignKey("securities.id"), nullable=False)
    quantity = Column(Numeric(19, 6), nullable=False)
    institution_price = Column(Numeric(19, 4), nullable=True)  # Price per share from institution
    institution_value = Column(Numeric(19, 4), nullable=True)  # Total market value
    cost_basis = Column(Numeric(19, 4), nullable=True)  # May be null (Robinhood)
    iso_currency_code = Column(String(3), nullable=True)
    unofficial_currency_code = Column(String(32), nullable=True)  # Crypto
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="holdings")
    security = relationship("Security", back_populates="holdings")


class InvestmentTransaction(Base):
    """Buy/sell/dividend/fee activity within an investment account."""
    __tablename__ = "investment_transactions"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    security_id = Column(Integer, ForeignKey("securities.id"), nullable=True)  # Null for cash movements
    plaid_investment_transaction_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(512), nullable=False)  # e.g. "buy AAPL"
    type = Column(String(64), nullable=False)  # buy, sell, dividend, fee, etc.
    subtype = Column(String(64), nullable=True)
    amount = Column(Numeric(19, 4), nullable=False)  # Signed per Plaid convention
    quantity = Column(Numeric(19, 6), nullable=True)
    price = Column(Numeric(19, 4), nullable=True)
    fees = Column(Numeric(19, 4), nullable=True)
    date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="investment_transactions")
    security = relationship("Security", back_populates="investment_transactions")
