"""
Human-readable category labels — mirrors frontend/src/utils/categories.ts.
"""

from __future__ import annotations

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
    "Paycheck": "Paycheck",
    "Dining Out": "Dining Out",
    "Savings": "Savings",
}

_NORMALIZED_OVERRIDES: dict[str, str] = {}
_KEY_BY_LABEL: dict[str, str] = {}
for key, value in _OVERRIDES.items():
    _NORMALIZED_OVERRIDES[key] = value
    _NORMALIZED_OVERRIDES[key.replace(".", "_")] = value
    norm_key = key.replace(".", "_")
    _KEY_BY_LABEL[value.lower()] = norm_key
    _KEY_BY_LABEL[key.lower()] = norm_key
    _KEY_BY_LABEL[norm_key.lower()] = norm_key


def label_to_pfc_key(label: str) -> str | None:
    """Map a human category label (e.g. 'Flights') back to a PFC key (e.g. TRAVEL_FLIGHTS)."""
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
