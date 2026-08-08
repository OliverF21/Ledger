"""
Shared constants/helpers for spending & budget analytics.
Kept in one place so analytics.py and budgets.py can't drift out of sync.
"""

from datetime import date

CATEGORY_COLORS = [
    '#5b8def', '#4fc4c4', '#8a7df0', '#4ec38a', '#d9a85b',
    '#e7705f', '#f0a87d', '#7fb0ff', '#a8d8a8', '#565c69',
]

# Excluded from SPENDING (positive/debit transactions).
# Prevents double-counting credit card payments and internal transfers.
EXCLUDED_FROM_SPENDING = {
    "LOAN_PAYMENTS",   # credit card payments, loan payments
    "TRANSFER_IN",     # incoming transfers (already counted when charged)
    "TRANSFER_OUT",    # outgoing transfers
    "TRANSFER",
}

# TRANSFER_OUT subcategories that still count as cash-flow outflows.
# Kept as an allowlist so other TRANSFER_OUT_* keys remain excluded via the
# TRANSFER_OUT primary above (prefix match in _matches_excluded_primary).
TRANSFER_OUT_SPENDING_SUBCATEGORIES = {
    "TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS",
}

# Excluded from INCOME (negative/credit transactions).
# Credit card payments can appear as credits on the card side — not real income.
EXCLUDED_FROM_INCOME = {
    "LOAN_PAYMENTS",
}

# TRANSFER_IN subcategories that count as real income (P2P, direct deposits).
# Other TRANSFER_IN subcategories are internal account moves and excluded.
TRANSFER_IN_INCOME_SUBCATEGORIES = {
    "TRANSFER_IN_DEPOSIT",
    "TRANSFER_IN_OTHER_TRANSFER_IN",
}

# Valid budget category_key values. The 16 canonical Plaid PFC primaries plus the
# three extra keys the budget suggester assigns (SUGGESTED_ALLOCATIONS). Used to
# reject ambiguous AI budget proposals at create time so a bad category never
# lands as an orphan budget that no spending aggregates against.
PLAID_PFC_PRIMARIES = {
    "INCOME", "TRANSFER_IN", "TRANSFER_OUT", "LOAN_PAYMENTS", "BANK_FEES",
    "ENTERTAINMENT", "FOOD_AND_DRINK", "GENERAL_MERCHANDISE", "HOME_IMPROVEMENT",
    "MEDICAL", "PERSONAL_CARE", "GENERAL_SERVICES", "GOVERNMENT_AND_NON_PROFIT",
    "TRANSPORTATION", "TRAVEL", "RENT_AND_UTILITIES",
}
# SHOPPING is Plaid PFC v1; GENERAL_MERCHANDISE is the v2 replacement. Kept in
# KNOWN_CATEGORY_KEYS so legacy budgets/proposals still validate.
KNOWN_CATEGORY_KEYS = PLAID_PFC_PRIMARIES | {"SHOPPING", "EDUCATION", "PETS"}

# Human display labels for category keys (matches the budget suggester's labels).
# Used to normalize AI budget proposals so an applied budget reads "Food & Drink",
# not the raw "FOOD_AND_DRINK" key.
CATEGORY_KEY_LABELS = {
    "INCOME": "Income",
    "TRANSFER_IN": "Transfer In",
    "TRANSFER_OUT": "Transfer Out",
    "LOAN_PAYMENTS": "Loan Payments",
    "BANK_FEES": "Bank Fees",
    "ENTERTAINMENT": "Entertainment",
    "FOOD_AND_DRINK": "Food & Drink",
    "GENERAL_MERCHANDISE": "Shopping",
    "HOME_IMPROVEMENT": "Home Improvement",
    "MEDICAL": "Medical",
    "PERSONAL_CARE": "Personal Care",
    "GENERAL_SERVICES": "General Services",
    "GOVERNMENT_AND_NON_PROFIT": "Government & Non-Profit",
    "TRANSPORTATION": "Transportation",
    "TRAVEL": "Travel",
    "RENT_AND_UTILITIES": "Rent & Utilities",
    "SHOPPING": "Shopping",  # legacy v1 alias — rolls up to GENERAL_MERCHANDISE
    "EDUCATION": "Education",
    "PETS": "Pets",
}

# Collapse legacy Plaid v1 shopping keys and common display aliases onto v2 primary.
_SHOPPING_LABEL_ALIASES = {
    "shopping",
    "general merchandise",
    "general merch",
}

# Human display labels (as set on category_user by CategoryPicker, which sends
# a Plaid detailed/primary *label* rather than its key) that represent internal
# transfers or loan/credit-card payments. Without this, a transaction whose
# category_user is "Credit Card Payment" or "Transfer In" never round-trips
# back into PFC-key form, so is_excluded_from_spending/income silently fails to
# exclude it and it leaks into spending/income totals as real activity.
_EXCLUDED_DISPLAY_LABELS = {
    "loan payments": "LOAN_PAYMENTS",
    "car payment": "LOAN_PAYMENTS_CAR_PAYMENT",
    "credit card payment": "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT",
    "personal loan payment": "LOAN_PAYMENTS_PERSONAL_LOAN_PAYMENT",
    "mortgage": "LOAN_PAYMENTS_MORTGAGE_PAYMENT",
    "student loan payment": "LOAN_PAYMENTS_STUDENT_LOAN_PAYMENT",
    "other loan payment": "LOAN_PAYMENTS_OTHER_PAYMENT",
    "transfer in": "TRANSFER_IN",
    "transfers in": "TRANSFER_IN",
    "cash advances & loans": "TRANSFER_IN_CASH_ADVANCES_AND_LOANS",
    "deposit": "TRANSFER_IN_DEPOSIT",
    "investment / retirement transfer in": "TRANSFER_IN_INVESTMENT_AND_RETIREMENT_FUNDS",
    "savings transfer in": "TRANSFER_IN_SAVINGS",
    "account transfer in": "TRANSFER_IN_ACCOUNT_TRANSFER",
    "other transfer in": "TRANSFER_IN_OTHER_TRANSFER_IN",
    "transfer out": "TRANSFER_OUT",
    "transfers out": "TRANSFER_OUT",
    "investment / retirement transfer out": "TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS",
    "savings transfer out": "TRANSFER_OUT_SAVINGS",
    "withdrawal": "TRANSFER_OUT_WITHDRAWAL",
    "account transfer out": "TRANSFER_OUT_ACCOUNT_TRANSFER",
    "app transfer out": "TRANSFER_OUT_TRANSFER_OUT_FROM_APPS",
    "other transfer out": "TRANSFER_OUT_OTHER_TRANSFER_OUT",
}


def _exclusion_key(category: str | None) -> str:
    """PFC-key form of category for exclusion matching, resolving display labels
    (e.g. "Credit Card Payment") set via CategoryPicker back to their PFC key."""
    if not category:
        return ""
    mapped = _EXCLUDED_DISPLAY_LABELS.get(category.strip().lower())
    if mapped:
        return mapped
    return normalize_category_key(category).upper().replace(".", "_")


def _matches_excluded_primary(category: str, excluded_primaries: set[str]) -> bool:
    """True when category is an excluded primary or one of its detailed/sub keys."""
    upper = _exclusion_key(category)
    if not upper:
        return False
    if upper in excluded_primaries:
        return True
    return any(upper.startswith(f"{primary}_") for primary in excluded_primaries)


def is_excluded_from_spending(category: str | None) -> bool:
    """Spending totals exclude loan/CC payments and transfers at any category depth.

    Investment / retirement funding transfers are an intentional exception so
    Cash Flow can show money leaving spendable cash for brokerage/retirement.
    """
    upper = _exclusion_key(category)
    if upper in TRANSFER_OUT_SPENDING_SUBCATEGORIES:
        return False
    return _matches_excluded_primary(category or "", EXCLUDED_FROM_SPENDING)


def most_specific_category_key(
    category_user: str | None,
    category_plaid: str | None,
    category_plaid_detailed: str | None,
) -> str:
    """Prefer user override, then Plaid detailed, then primary.

    Exclusion allowlists (investment transfer-out, deposit transfer-in) need the
    detailed key. Rolling up to the primary first would make every TRANSFER_OUT_*
    look like TRANSFER_OUT and defeat the allowlist.
    """
    if category_user:
        return normalize_category_key(category_user)
    if category_plaid_detailed:
        return normalize_category_key(category_plaid_detailed)
    if category_plaid:
        return normalize_category_key(category_plaid)
    return ""


def category_key_for_income_rules(
    category_user: str | None,
    category_plaid: str | None,
    category_plaid_detailed: str | None,
) -> str:
    """Most specific category for income rules (needs PFC detail to split transfer subtypes)."""
    return most_specific_category_key(category_user, category_plaid, category_plaid_detailed)


def category_key_for_spending_rules(
    category_user: str | None,
    category_plaid: str | None,
    category_plaid_detailed: str | None,
) -> str:
    """Most specific category for spending exclusion (needs detail to greenlight investments)."""
    return most_specific_category_key(category_user, category_plaid, category_plaid_detailed)


def is_excluded_from_income(category: str | None) -> bool:
    if _matches_excluded_primary(category or "", EXCLUDED_FROM_INCOME):
        return True
    upper = _exclusion_key(category)
    if upper == "TRANSFER_IN":
        # Primary only — treat as income (external inflow when Plaid omits detail).
        return False
    if upper.startswith("TRANSFER_IN_"):
        return upper not in TRANSFER_IN_INCOME_SUBCATEGORIES
    return False


def normalize_category_key(key: str) -> str:
    """Map legacy SHOPPING (PFC v1) and label aliases onto GENERAL_MERCHANDISE (PFC v2)."""
    if not key:
        return key
    if key.lower() in _SHOPPING_LABEL_ALIASES:
        return "GENERAL_MERCHANDISE"
    normalized = key.upper().replace(".", "_")
    if normalized == "SHOPPING":
        return "GENERAL_MERCHANDISE"
    if normalized.startswith("SHOPPING_"):
        return normalized.replace("SHOPPING_", "GENERAL_MERCHANDISE_", 1)
    return key


def display_label_for_key(key: str) -> str:
    """Human label for a category key, falling back to Title Case of the key."""
    if key in CATEGORY_KEY_LABELS:
        return CATEGORY_KEY_LABELS[key]
    return key.replace("_", " ").title()


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Returns (start, end) dates for a calendar month, end exclusive."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def parent_from_pfc_detailed(detailed: str) -> str:
    """Strip Plaid PFC detailed suffix to primary (e.g. FOOD_AND_DRINK_FAST_FOOD → FOOD_AND_DRINK)."""
    if "." in detailed:
        return detailed.split(".")[0]
    # Match against known primaries directly rather than guessing a word count —
    # primaries range from 1 word (ENTERTAINMENT) to 3 (FOOD_AND_DRINK), and a
    # fixed-length slice misreads e.g. ENTERTAINMENT_VIDEO_GAMES as ENTERTAINMENT_VIDEO.
    for primary in sorted(PLAID_PFC_PRIMARIES, key=len, reverse=True):
        if detailed == primary or detailed.startswith(f"{primary}_"):
            return primary
    parts = detailed.split("_")
    for n in (3, 2, 1):
        if len(parts) > n:
            return "_".join(parts[:n])
    return detailed


def rollup_category_key(
    category_user: str | None,
    category_plaid: str | None,
    category_plaid_detailed: str | None,
    default: str = "Uncategorized",
) -> str:
    """Canonical bucket for charts/aggregates.

    Plaid-enriched transactions roll up to the PFC primary (e.g. ENTERTAINMENT).
    User overrides at subcategory level (e.g. "Dining Out") keep their own bucket.
    Labels and keys for the same primary always merge ("Entertainment" == ENTERTAINMENT).
    """
    if category_user:
        raw = category_user
    elif category_plaid:
        raw = category_plaid
    elif category_plaid_detailed:
        raw = parent_from_pfc_detailed(category_plaid_detailed)
    else:
        return default

    raw = normalize_category_key(raw)
    resolved = resolve_category_to_pfc_key(raw)
    if not resolved:
        return raw or default

    if resolved in PLAID_PFC_PRIMARIES or resolved in KNOWN_CATEGORY_KEYS:
        return normalize_category_key(resolved)

    from mcp_server.category_labels import format_category

    if category_user:
        stripped = category_user.strip()
        # Keep the label the user picked (e.g. "Dining Out", "Paycheck"), not a
        # derived hierarchy like "Income · Paycheck".
        if stripped and not stripped.isupper():
            return stripped

    return format_category(resolved)


def resolve_category_to_pfc_key(category: str) -> str:
    """Resolve a display label or PFC key string to underscore-form PFC key."""
    if not category:
        return category
    stripped = category.strip()
    from mcp_server.category_labels import label_to_pfc_key

    mapped = label_to_pfc_key(stripped)
    if mapped:
        return mapped.upper().replace(".", "_")
    mapped = _EXCLUDED_DISPLAY_LABELS.get(stripped.lower())
    if mapped:
        return mapped.upper().replace(".", "_")
    for key, label in CATEGORY_KEY_LABELS.items():
        if label.lower() == stripped.lower():
            return key
    return normalize_category_key(stripped).upper().replace(".", "_")


def budget_parent_key(
    category_user: str | None,
    category_plaid: str | None,
    category_plaid_detailed: str | None,
) -> str | None:
    """PFC primary key for budget spent aggregation, respecting user overrides."""
    category = rollup_category_key(category_user, category_plaid, category_plaid_detailed)
    if not category or category == "Uncategorized":
        return None
    resolved = resolve_category_to_pfc_key(category)
    if not resolved:
        return None
    if resolved in PLAID_PFC_PRIMARIES or resolved in KNOWN_CATEGORY_KEYS:
        return normalize_category_key(resolved)
    parent = parent_from_pfc_detailed(resolved)
    return normalize_category_key(parent)


def display_rollup_category(
    category_user: str | None,
    category_plaid: str | None,
    category_plaid_detailed: str | None,
    default: str = "Uncategorized",
) -> str:
    """Bucket for cash-flow charts.

    `rollup_category_key` deliberately keeps a manual subcategory override
    (e.g. "Gas") in its own bucket for budgets/MCP reporting, but that means
    it never merges with the "Transportation" bucket Plaid-categorized
    transactions land in, showing as a separate, confusing bar. When the
    override resolves to a known PFC subcategory, roll it up to that
    subcategory's primary so charts show one umbrella bucket; truly custom
    labels (e.g. "Paycheck") that don't map to the PFC taxonomy have no
    primary to roll up to, so they're kept as-is.

    Investment / retirement funding transfers are kept as their own "Investments"
    sink instead of collapsing into TRANSFER_OUT (which is otherwise excluded).
    """
    for raw in (category_user, category_plaid_detailed, category_plaid):
        if raw and _exclusion_key(raw) in TRANSFER_OUT_SPENDING_SUBCATEGORIES:
            return "Investments"

    category = rollup_category_key(category_user, category_plaid, category_plaid_detailed, default)
    if not category or category == default:
        return default

    resolved = resolve_category_to_pfc_key(category)
    if resolved and (resolved in PLAID_PFC_PRIMARIES or resolved in KNOWN_CATEGORY_KEYS):
        return normalize_category_key(resolved)

    from mcp_server.category_labels import label_to_pfc_key

    # Prefer an explicit taxonomy mapping for the stored label (e.g. "Restaurants"
    # → FOOD_AND_DRINK_RESTAURANT → FOOD_AND_DRINK) over freeform uppercase-ification.
    mapped = None
    if category_user:
        stripped = category_user.strip()
        if stripped and not stripped.isupper():
            mapped = label_to_pfc_key(stripped)
    if not mapped and category and not category.isupper():
        mapped = label_to_pfc_key(category)

    detailed = None
    if mapped:
        detailed = normalize_category_key(mapped).upper().replace(".", "_")
    elif resolved:
        detailed = normalize_category_key(resolved).upper().replace(".", "_")

    if detailed:
        parent = parent_from_pfc_detailed(detailed)
        if parent in PLAID_PFC_PRIMARIES or parent in KNOWN_CATEGORY_KEYS:
            # Only roll up when we actually hit the taxonomy (mapped label or a
            # real detailed PFC key), not arbitrary text that uppercased oddly.
            if mapped or detailed != parent:
                return normalize_category_key(parent)

    return category
