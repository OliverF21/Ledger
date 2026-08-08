from app.analytics_shared import (
    budget_parent_key,
    category_key_for_income_rules,
    category_key_for_spending_rules,
    display_rollup_category,
    is_excluded_from_income,
    is_excluded_from_spending,
    normalize_category_key,
    resolve_category_to_pfc_key,
    rollup_category_key,
)


def test_normalize_shopping_aliases():
    assert normalize_category_key("SHOPPING") == "GENERAL_MERCHANDISE"
    assert normalize_category_key("SHOPPING.ELECTRONICS") == "GENERAL_MERCHANDISE_ELECTRONICS"
    assert normalize_category_key("SHOPPING_ELECTRONICS") == "GENERAL_MERCHANDISE_ELECTRONICS"
    assert normalize_category_key("Shopping") == "GENERAL_MERCHANDISE"
    assert normalize_category_key("General Merchandise") == "GENERAL_MERCHANDISE"
    assert normalize_category_key("FOOD_AND_DRINK") == "FOOD_AND_DRINK"


def test_rollup_collapses_legacy_shopping():
    assert rollup_category_key(None, "SHOPPING", None) == "GENERAL_MERCHANDISE"
    assert rollup_category_key("General Merch", None, None) == "GENERAL_MERCHANDISE"


def test_rollup_merges_primary_label_and_pfc_key():
    assert rollup_category_key("Entertainment", None, None) == "ENTERTAINMENT"
    assert rollup_category_key(None, "ENTERTAINMENT", None) == "ENTERTAINMENT"
    assert rollup_category_key("Food & Drink", None, None) == "FOOD_AND_DRINK"
    assert rollup_category_key(None, "FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES") == "FOOD_AND_DRINK"


def test_rollup_keeps_detailed_user_override_bucket():
    assert rollup_category_key("Dining Out", "FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES") == "Dining Out"
    assert rollup_category_key("Video Games", "ENTERTAINMENT", "ENTERTAINMENT_VIDEO_GAMES") == "Video Games"
    assert rollup_category_key("Restaurants", "GENERAL_MERCHANDISE", None) == "Restaurants"


def test_display_rollup_merges_subcategory_into_primary():
    """Cash-flow charts should bucket Food subcategories under Food & Drink."""
    assert display_rollup_category("Restaurants", "GENERAL_MERCHANDISE", None) == "FOOD_AND_DRINK"
    assert display_rollup_category("Dining Out", "FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES") == "FOOD_AND_DRINK"
    assert display_rollup_category("Coffee", None, None) == "FOOD_AND_DRINK"
    assert display_rollup_category("Gas", "GENERAL_MERCHANDISE", None) == "TRANSPORTATION"
    assert display_rollup_category("Rideshare & Taxis", None, None) == "TRANSPORTATION"
    # Custom labels with no PFC mapping stay as-is.
    assert display_rollup_category("Paycheck", None, None) == "Paycheck"


def test_excludes_loan_payment_subcategories_from_spending():
    assert is_excluded_from_spending("LOAN_PAYMENTS")
    assert is_excluded_from_spending("LOAN_PAYMENTS.CREDIT_CARD_PAYMENT")
    assert is_excluded_from_spending("LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
    assert is_excluded_from_spending("LOAN_PAYMENTS_MORTGAGE_PAYMENT")
    assert not is_excluded_from_spending("FOOD_AND_DRINK")
    assert not is_excluded_from_spending("FOOD_AND_DRINK_RESTAURANTS")


def test_excludes_transfer_subcategories_from_spending():
    assert is_excluded_from_spending("TRANSFER_OUT")
    assert is_excluded_from_spending("TRANSFER_OUT_ACCOUNT_TRANSFER")
    assert is_excluded_from_spending("TRANSFER_OUT_SAVINGS")
    assert is_excluded_from_spending("TRANSFER_IN_SAVINGS")


def test_includes_investment_transfer_out_in_spending():
    assert not is_excluded_from_spending("TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS")
    assert not is_excluded_from_spending("TRANSFER_OUT.INVESTMENT_AND_RETIREMENT_FUNDS")
    assert not is_excluded_from_spending("Investment / Retirement Transfer Out")


def test_spending_rules_prefer_detailed_transfer_key():
    """Cash flow must not roll TRANSFER_OUT_INVESTMENT_* up before exclusion."""
    detailed = category_key_for_spending_rules(
        None, "TRANSFER_OUT", "TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS"
    )
    assert detailed == "TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS"
    assert not is_excluded_from_spending(detailed)
    # Primary alone is still excluded.
    assert is_excluded_from_spending(
        category_key_for_spending_rules(None, "TRANSFER_OUT", None)
    )


def test_display_rollup_buckets_investment_transfers():
    assert display_rollup_category(
        None, "TRANSFER_OUT", "TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS"
    ) == "Investments"
    assert display_rollup_category(
        "Investment / Retirement Transfer Out", "TRANSFER_OUT", None
    ) == "Investments"


def test_excludes_loan_payment_subcategories_from_income():
    assert is_excluded_from_income("LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
    assert not is_excluded_from_income("INCOME")


def test_income_rules_prefer_plaid_detailed_for_transfers():
    assert category_key_for_income_rules(
        None, "TRANSFER_IN", "TRANSFER_IN_SAVINGS"
    ) == "TRANSFER_IN_SAVINGS"
    assert is_excluded_from_income(
        category_key_for_income_rules(None, "TRANSFER_IN", "TRANSFER_IN_SAVINGS")
    )
    assert not is_excluded_from_income(
        category_key_for_income_rules(None, "TRANSFER_IN", "TRANSFER_IN_OTHER_TRANSFER_IN")
    )


def test_excludes_internal_transfer_in_from_income():
    assert is_excluded_from_income("TRANSFER_IN_ACCOUNT_TRANSFER")
    assert is_excluded_from_income("TRANSFER_IN.SAVINGS")
    assert is_excluded_from_income("TRANSFER_IN_INVESTMENT_AND_RETIREMENT_FUNDS")
    assert is_excluded_from_income("TRANSFER_IN_CASH_ADVANCES_AND_LOANS")
    assert not is_excluded_from_income("TRANSFER_IN")
    assert not is_excluded_from_income("TRANSFER_IN_DEPOSIT")
    assert not is_excluded_from_income("TRANSFER_IN_OTHER_TRANSFER_IN")


def test_resolve_category_label_to_pfc_key():
    assert resolve_category_to_pfc_key("Flights") == "TRAVEL_FLIGHTS"
    assert resolve_category_to_pfc_key("Food & Drink") == "FOOD_AND_DRINK"
    assert resolve_category_to_pfc_key("GENERAL_MERCHANDISE") == "GENERAL_MERCHANDISE"
    assert resolve_category_to_pfc_key("Restaurants") == "FOOD_AND_DRINK_RESTAURANT"
    assert resolve_category_to_pfc_key("Dining Out") == "FOOD_AND_DRINK_RESTAURANTS"


def test_budget_parent_key_respects_user_override():
    # Flight recategorized from Shopping should count under Travel, not Shopping.
    assert budget_parent_key("Flights", "GENERAL_MERCHANDISE", "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES") == "TRAVEL"
    assert budget_parent_key(None, "GENERAL_MERCHANDISE", None) == "GENERAL_MERCHANDISE"
    assert budget_parent_key("Shopping", "TRAVEL", "TRAVEL_FLIGHTS") == "GENERAL_MERCHANDISE"
    assert budget_parent_key("Travel", None, None) == "TRAVEL"
    assert budget_parent_key("Restaurants", "GENERAL_MERCHANDISE", None) == "FOOD_AND_DRINK"
    assert budget_parent_key("Dining Out", "GENERAL_MERCHANDISE", None) == "FOOD_AND_DRINK"
