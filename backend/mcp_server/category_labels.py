"""
Human-readable category labels — mirrors frontend/src/utils/categories.ts
and frontend/src/utils/plaidCategories.ts (Plaid PFC v2 taxonomy).
"""

from __future__ import annotations

# Legacy / friendly overrides used by format_category. Keys may be PFC codes
# (dot or underscore) or already-human labels that should pass through unchanged.
_OVERRIDES: dict[str, str] = {
    "FOOD_AND_DRINK": "Food & Drink",
    "FOOD_AND_DRINK.GROCERIES": "Groceries",
    "FOOD_AND_DRINK.RESTAURANTS": "Dining Out",
    "FOOD_AND_DRINK.FAST_FOOD": "Fast Food",
    "FOOD_AND_DRINK.COFFEE": "Coffee",
    "FOOD_AND_DRINK.ALCOHOL_AND_BARS": "Bars & Alcohol",
    "TRANSPORTATION": "Transportation",
    "TRANSPORTATION.GAS": "Gas",
    "TRANSPORTATION.PARKING": "Parking",
    "TRANSPORTATION.PUBLIC_TRANSIT": "Public Transit",
    "TRANSPORTATION.TAXIS_AND_RIDE_SHARES": "Rideshare",
    "TRAVEL": "Travel",
    "TRAVEL.FLIGHTS": "Flights",
    "TRAVEL.LODGING": "Lodging",
    "TRAVEL.RENTAL_CARS": "Rental Cars",
    "SHOPPING": "Shopping",
    "SHOPPING.CLOTHING_AND_ACCESSORIES": "Clothing & Accessories",
    "SHOPPING.ELECTRONICS": "Electronics",
    "SHOPPING.SPORTING_GOODS": "Sporting Goods",
    "GENERAL_MERCHANDISE": "Shopping",
    "RENT_AND_UTILITIES": "Rent & Utilities",
    "RENT_AND_UTILITIES.RENT": "Rent",
    "RENT_AND_UTILITIES.GAS_AND_ELECTRICITY": "Gas & Electric",
    "RENT_AND_UTILITIES.INTERNET_AND_CABLE": "Internet & Cable",
    "RENT_AND_UTILITIES.TELEPHONE": "Phone",
    "RENT_AND_UTILITIES.WATER": "Water",
    "ENTERTAINMENT": "Entertainment",
    "ENTERTAINMENT.STREAMING_SERVICES": "Streaming",
    "ENTERTAINMENT.MUSIC_AND_AUDIO": "Music",
    "ENTERTAINMENT.VIDEO_GAMES": "Video Games",
    "PERSONAL_CARE": "Personal Care",
    "PERSONAL_CARE.GYMS_AND_FITNESS_CENTERS": "Gym & Fitness",
    "PERSONAL_CARE.HAIR_AND_BEAUTY": "Hair & Beauty",
    "MEDICAL": "Medical",
    "MEDICAL.PHARMACIES_AND_SUPPLEMENTS": "Pharmacy",
    "MEDICAL.DOCTOR_VISITS": "Doctor",
    "HOME_IMPROVEMENT": "Home Improvement",
    "LOAN_PAYMENTS": "Loan Payments",
    "LOAN_PAYMENTS.CREDIT_CARD_PAYMENT": "Credit Card Payment",
    "LOAN_PAYMENTS.MORTGAGE_PAYMENT": "Mortgage",
    "BANK_FEES": "Bank Fees",
    "INCOME": "Income",
    "INCOME.WAGES": "Wages",
    "INCOME.INTEREST_EARNED": "Interest",
    "TRANSFER_IN": "Transfer In",
    "TRANSFER_OUT": "Transfer Out",
    "TRANSFER": "Transfer",
    "GOVERNMENT_AND_NON_PROFIT": "Government",
    "EDUCATION": "Education",
    "EDUCATION.TUITION": "Tuition",
    "PETS": "Pets",
    "GIFTS_AND_DONATIONS": "Gifts & Donations",
    "BUSINESS_SERVICES": "Business Services",
    "GENERAL_SERVICES": "General Services",
    "GENERAL_SERVICES.AUTOMOTIVE": "Auto Services",
    # Pass-throughs for already-human labels (format_category only — must NOT
    # be reverse-indexed into _KEY_BY_LABEL or they overwrite real PFC keys).
    "Paycheck": "Paycheck",
    "Dining Out": "Dining Out",
    "Savings": "Savings",
}

# Plaid PFC v2 detailed key → picker label (mirrors frontend plaidCategories.ts).
# Used for reverse lookup so recategorizing to "Restaurants" resolves to Food & Drink.
_PLAID_V2_DETAILED_LABELS: dict[str, str] = {
    "INCOME_DIVIDENDS": "Dividends",
    "INCOME_INTEREST_EARNED": "Interest Earned",
    "INCOME_RETIREMENT_PENSION": "Retirement / Pension",
    "INCOME_TAX_REFUND": "Tax Refund",
    "INCOME_UNEMPLOYMENT": "Unemployment",
    "INCOME_WAGES": "Wages",
    "INCOME_SALARY": "Salary",
    "INCOME_CONTRACTOR": "Contract / Gig Income",
    "INCOME_OTHER_INCOME": "Other Income",
    "TRANSFER_IN_CASH_ADVANCES_AND_LOANS": "Cash Advances & Loans",
    "TRANSFER_IN_DEPOSIT": "Deposit",
    "TRANSFER_IN_INVESTMENT_AND_RETIREMENT_FUNDS": "Investment / Retirement Transfer In",
    "TRANSFER_IN_SAVINGS": "Savings Transfer In",
    "TRANSFER_IN_ACCOUNT_TRANSFER": "Account Transfer In",
    "TRANSFER_IN_OTHER_TRANSFER_IN": "Other Transfer In",
    "TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS": "Investment / Retirement Transfer Out",
    "TRANSFER_OUT_SAVINGS": "Savings Transfer Out",
    "TRANSFER_OUT_WITHDRAWAL": "Withdrawal",
    "TRANSFER_OUT_ACCOUNT_TRANSFER": "Account Transfer Out",
    "TRANSFER_OUT_TRANSFER_OUT_FROM_APPS": "App Transfer Out",
    "TRANSFER_OUT_OTHER_TRANSFER_OUT": "Other Transfer Out",
    "LOAN_PAYMENTS_CAR_PAYMENT": "Car Payment",
    "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT": "Credit Card Payment",
    "LOAN_PAYMENTS_PERSONAL_LOAN_PAYMENT": "Personal Loan Payment",
    "LOAN_PAYMENTS_MORTGAGE_PAYMENT": "Mortgage",
    "LOAN_PAYMENTS_STUDENT_LOAN_PAYMENT": "Student Loan Payment",
    "LOAN_PAYMENTS_OTHER_PAYMENT": "Other Loan Payment",
    "BANK_FEES_ATM_FEES": "ATM Fees",
    "BANK_FEES_FOREIGN_TRANSACTION_FEES": "Foreign Transaction Fees",
    "BANK_FEES_INSUFFICIENT_FUNDS": "Insufficient Funds Fee",
    "BANK_FEES_INTEREST_CHARGE": "Interest Charge",
    "BANK_FEES_OVERDRAFT_FEES": "Overdraft Fees",
    "BANK_FEES_OTHER_BANK_FEES": "Other Bank Fees",
    "ENTERTAINMENT_CASINOS_AND_GAMBLING": "Casinos & Gambling",
    "ENTERTAINMENT_MUSIC_AND_AUDIO": "Music",
    "ENTERTAINMENT_SPORTING_EVENTS_AMUSEMENT_PARKS_AND_MUSEUMS": "Events, Parks & Museums",
    "ENTERTAINMENT_TV_AND_MOVIES": "TV & Movies",
    "ENTERTAINMENT_VIDEO_GAMES": "Video Games",
    "ENTERTAINMENT_OTHER_ENTERTAINMENT": "Other Entertainment",
    "FOOD_AND_DRINK_BEER_WINE_AND_LIQUOR": "Beer, Wine & Liquor",
    "FOOD_AND_DRINK_COFFEE": "Coffee",
    "FOOD_AND_DRINK_FAST_FOOD": "Fast Food",
    "FOOD_AND_DRINK_GROCERIES": "Groceries",
    "FOOD_AND_DRINK_RESTAURANT": "Restaurants",
    "FOOD_AND_DRINK_VENDING_MACHINES": "Vending Machines",
    "FOOD_AND_DRINK_OTHER_FOOD_AND_DRINK": "Other Food & Drink",
    "GENERAL_MERCHANDISE_BOOKSTORES_AND_NEWSSTANDS": "Books & Newsstands",
    "GENERAL_MERCHANDISE_CLOTHING_AND_ACCESSORIES": "Clothing & Accessories",
    "GENERAL_MERCHANDISE_CONVENIENCE_STORES": "Convenience Stores",
    "GENERAL_MERCHANDISE_DEPARTMENT_STORES": "Department Stores",
    "GENERAL_MERCHANDISE_DISCOUNT_STORES": "Discount Stores",
    "GENERAL_MERCHANDISE_ELECTRONICS": "Electronics",
    "GENERAL_MERCHANDISE_GIFTS_AND_NOVELTIES": "Gifts & Novelties",
    "GENERAL_MERCHANDISE_OFFICE_SUPPLIES": "Office Supplies",
    "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES": "Online Marketplaces",
    "GENERAL_MERCHANDISE_PET_SUPPLIES": "Pet Supplies",
    "GENERAL_MERCHANDISE_SPORTING_GOODS": "Sporting Goods",
    "GENERAL_MERCHANDISE_SUPERSTORES": "Superstores",
    "GENERAL_MERCHANDISE_TOBACCO_AND_VAPE": "Tobacco & Vape",
    "GENERAL_MERCHANDISE_OTHER_GENERAL_MERCHANDISE": "Other Merchandise",
    "HOME_IMPROVEMENT_FURNITURE": "Furniture",
    "HOME_IMPROVEMENT_HARDWARE": "Hardware",
    "HOME_IMPROVEMENT_REPAIR_AND_MAINTENANCE": "Repair & Maintenance",
    "HOME_IMPROVEMENT_SECURITY": "Home Security",
    "HOME_IMPROVEMENT_OTHER_HOME_IMPROVEMENT": "Other Home Improvement",
    "MEDICAL_DENTAL_CARE": "Dental Care",
    "MEDICAL_EYE_CARE": "Eye Care",
    "MEDICAL_NURSING_CARE": "Nursing Care",
    "MEDICAL_PHARMACIES_AND_SUPPLEMENTS": "Pharmacy",
    "MEDICAL_PRIMARY_CARE": "Primary Care",
    "MEDICAL_VETERINARY_SERVICES": "Veterinary",
    "MEDICAL_OTHER_MEDICAL": "Other Medical",
    "PERSONAL_CARE_GYMS_AND_FITNESS_CENTERS": "Gym & Fitness",
    "PERSONAL_CARE_HAIR_AND_BEAUTY": "Hair & Beauty",
    "PERSONAL_CARE_LAUNDRY_AND_DRY_CLEANING": "Laundry & Dry Cleaning",
    "PERSONAL_CARE_OTHER_PERSONAL_CARE": "Other Personal Care",
    "GENERAL_SERVICES_ACCOUNTING_AND_FINANCIAL_PLANNING": "Accounting & Financial Planning",
    "GENERAL_SERVICES_AUTOMOTIVE": "Auto Services",
    "GENERAL_SERVICES_CHILDCARE": "Childcare",
    "GENERAL_SERVICES_CONSULTING_AND_LEGAL": "Consulting & Legal",
    "GENERAL_SERVICES_EDUCATION": "Education",
    "GENERAL_SERVICES_INSURANCE": "Insurance",
    "GENERAL_SERVICES_POSTAGE_AND_SHIPPING": "Postage & Shipping",
    "GENERAL_SERVICES_STORAGE": "Storage",
    "GENERAL_SERVICES_OTHER_GENERAL_SERVICES": "Other Services",
    "GOVERNMENT_AND_NON_PROFIT_DONATIONS": "Donations",
    "GOVERNMENT_AND_NON_PROFIT_GOVERNMENT_DEPARTMENTS_AND_AGENCIES": "Government Services",
    "GOVERNMENT_AND_NON_PROFIT_TAX_PAYMENT": "Tax Payment",
    "GOVERNMENT_AND_NON_PROFIT_OTHER_GOVERNMENT_AND_NON_PROFIT": "Other Government / Non-Profit",
    "OTHER_OTHER": "Other",
    "TRANSPORTATION_BIKES_AND_SCOOTERS": "Bikes & Scooters",
    "TRANSPORTATION_GAS": "Gas",
    "TRANSPORTATION_PARKING": "Parking",
    "TRANSPORTATION_PUBLIC_TRANSIT": "Public Transit",
    "TRANSPORTATION_TAXIS_AND_RIDE_SHARES": "Rideshare & Taxis",
    "TRANSPORTATION_TOLLS": "Tolls",
    "TRANSPORTATION_OTHER_TRANSPORTATION": "Other Transportation",
    "TRAVEL_FLIGHTS": "Flights",
    "TRAVEL_LODGING": "Lodging",
    "TRAVEL_RENTAL_CARS": "Rental Cars",
    "TRAVEL_OTHER_TRAVEL": "Other Travel",
    "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY": "Gas & Electric",
    "RENT_AND_UTILITIES_INTERNET_AND_CABLE": "Internet & Cable",
    "RENT_AND_UTILITIES_RENT": "Rent",
    "RENT_AND_UTILITIES_SEWAGE_AND_WASTE_MANAGEMENT": "Sewage & Waste",
    "RENT_AND_UTILITIES_TELEPHONE": "Phone",
    "RENT_AND_UTILITIES_WATER": "Water",
    "RENT_AND_UTILITIES_OTHER_UTILITIES": "Other Utilities",
}

# Primary key → display label (also used for reverse lookup).
_PLAID_V2_PRIMARY_LABELS: dict[str, str] = {
    "INCOME": "Income",
    "TRANSFER_IN": "Transfers In",
    "TRANSFER_OUT": "Transfers Out",
    "LOAN_PAYMENTS": "Loan Payments",
    "BANK_FEES": "Bank Fees",
    "ENTERTAINMENT": "Entertainment",
    "FOOD_AND_DRINK": "Food & Drink",
    "GENERAL_MERCHANDISE": "Shopping",
    "HOME_IMPROVEMENT": "Home Improvement",
    "MEDICAL": "Medical",
    "PERSONAL_CARE": "Personal Care",
    "GENERAL_SERVICES": "Services",
    "GOVERNMENT_AND_NON_PROFIT": "Government & Non-Profit",
    "OTHER": "Other",
    "TRANSPORTATION": "Transportation",
    "TRAVEL": "Travel",
    "RENT_AND_UTILITIES": "Rent & Utilities",
}

# Extra human aliases that are not the canonical v2 picker label.
_LABEL_ALIASES: dict[str, str] = {
    "dining out": "FOOD_AND_DRINK_RESTAURANT",
    "restaurants": "FOOD_AND_DRINK_RESTAURANT",
    "bars & alcohol": "FOOD_AND_DRINK_BEER_WINE_AND_LIQUOR",
    "rideshare": "TRANSPORTATION_TAXIS_AND_RIDE_SHARES",
    "streaming": "ENTERTAINMENT_TV_AND_MOVIES",
    "doctor": "MEDICAL_PRIMARY_CARE",
    "interest": "INCOME_INTEREST_EARNED",
    "government": "GOVERNMENT_AND_NON_PROFIT",
    "transfer in": "TRANSFER_IN",
    "transfer out": "TRANSFER_OUT",
    "general services": "GENERAL_SERVICES",
}


def _is_pfc_key(key: str) -> bool:
    """True for PFC codes like FOOD_AND_DRINK or FOOD_AND_DRINK.COFFEE — not 'Dining Out'."""
    normalized = key.strip().replace(".", "_")
    return bool(normalized) and normalized.isupper() and all(
        c.isalnum() or c == "_" for c in normalized
    )


_NORMALIZED_OVERRIDES: dict[str, str] = {}
_KEY_BY_LABEL: dict[str, str] = {}


def _index_label(label: str, pfc_key: str, *, prefer_existing: bool = False) -> None:
    """Map a human label → underscore PFC key. Optionally keep the first mapping."""
    if not label or not pfc_key:
        return
    lower = label.strip().lower()
    if prefer_existing and lower in _KEY_BY_LABEL:
        return
    _KEY_BY_LABEL[lower] = pfc_key.replace(".", "_")


for key, value in _OVERRIDES.items():
    _NORMALIZED_OVERRIDES[key] = value
    _NORMALIZED_OVERRIDES[key.replace(".", "_")] = value
    if _is_pfc_key(key):
        norm_key = key.replace(".", "_")
        _index_label(value, norm_key)
        _index_label(key, norm_key)
        _index_label(norm_key, norm_key)

for key, value in _PLAID_V2_PRIMARY_LABELS.items():
    _NORMALIZED_OVERRIDES.setdefault(key, value)
    _index_label(value, key, prefer_existing=True)
    _index_label(key, key, prefer_existing=True)

for key, value in _PLAID_V2_DETAILED_LABELS.items():
    # Index for reverse lookup only — leave format_category overrides alone so
    # unknown detailed keys still render as "Parent · Sub" (e.g. Income · Salary).
    _index_label(value, key, prefer_existing=True)
    _index_label(key, key, prefer_existing=True)

for alias, pfc_key in _LABEL_ALIASES.items():
    _index_label(alias, pfc_key, prefer_existing=True)


def label_to_pfc_key(label: str) -> str | None:
    """Map a human category label (e.g. 'Restaurants') back to a PFC key."""
    if not label:
        return None
    return _KEY_BY_LABEL.get(label.strip().lower())


_INCOME_SUB_LABEL_ALIASES = {
    "salary": "Salary",
    "paycheck": "Paycheck",
}

# Plaid primaries for deriving "Parent · Sub" from unknown detailed keys.
_PFC_PRIMARIES = (
    ("GENERAL_MERCHANDISE", "Shopping"),
    ("RENT_AND_UTILITIES", "Rent & Utilities"),
    ("FOOD_AND_DRINK", "Food & Drink"),
    ("HOME_IMPROVEMENT", "Home Improvement"),
    ("LOAN_PAYMENTS", "Loan Payments"),
    ("PERSONAL_CARE", "Personal Care"),
    ("GENERAL_SERVICES", "General Services"),
    ("GOVERNMENT_AND_NON_PROFIT", "Government & Non-Profit"),
    ("TRANSFER_IN", "Transfers In"),
    ("TRANSFER_OUT", "Transfers Out"),
    ("BANK_FEES", "Bank Fees"),
    ("ENTERTAINMENT", "Entertainment"),
    ("TRANSPORTATION", "Transportation"),
    ("TRAVEL", "Travel"),
    ("MEDICAL", "Medical"),
    ("INCOME", "Income"),
)


def _hierarchical_label_for_detailed_key(detailed: str) -> str | None:
    normalized = detailed.strip().upper().replace(".", "_")
    if normalized in _PLAID_V2_DETAILED_LABELS:
        # Prefer Parent · Sub when we know the primary.
        for primary, primary_label in _PFC_PRIMARIES:
            prefix = f"{primary}_"
            if normalized.startswith(prefix):
                return f"{primary_label} · {_PLAID_V2_DETAILED_LABELS[normalized]}"
        return _PLAID_V2_DETAILED_LABELS[normalized]
    for primary, primary_label in _PFC_PRIMARIES:
        prefix = f"{primary}_"
        if normalized.startswith(prefix):
            suffix = normalized[len(prefix):]
            sub = suffix.replace("_", " ").title().replace(" And ", " & ")
            return f"{primary_label} · {sub}"
    return None


def format_category(raw: str | None) -> str:
    if not raw:
        return "Uncategorized"
    trimmed = raw.strip()
    normalized = trimmed.upper().replace(".", "_")
    if trimmed in _NORMALIZED_OVERRIDES:
        return _NORMALIZED_OVERRIDES[trimmed]
    if normalized in _NORMALIZED_OVERRIDES:
        return _NORMALIZED_OVERRIDES[normalized]

    hierarchical = _hierarchical_label_for_detailed_key(trimmed)
    if hierarchical:
        return hierarchical

    income_sub = _INCOME_SUB_LABEL_ALIASES.get(trimmed.lower())
    if income_sub:
        return f"Income · {income_sub}"

    if "." in trimmed:
        segment = trimmed.split(".")[-1]
    elif trimmed.isupper() and "_" in trimmed:
        parts = trimmed.split("_")
        segment = "_".join(parts[2:]) if len(parts) > 2 else trimmed
    else:
        segment = trimmed

    words = segment.lower().replace("_", " ").split()
    titled = " ".join(word.capitalize() for word in words)
    return titled.replace(" And ", " & ")
