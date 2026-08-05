from mcp_server.category_labels import format_category, label_to_pfc_key


def test_format_category_maps_plaid_codes():
    assert format_category("FOOD_AND_DRINK") == "Food & Drink"
    assert format_category("RENT_AND_UTILITIES") == "Rent & Utilities"
    assert format_category("TRANSFER_IN") == "Transfer In"
    assert format_category("TRANSPORTATION_TAXIS_AND_RIDE_SHARES") == "Rideshare"


def test_format_category_income_salary_hierarchical():
    assert format_category("INCOME_SALARY") == "Income · Salary"
    assert format_category("income_salary") == "Income · Salary"
    assert format_category("Salary") == "Income · Salary"


def test_label_to_pfc_key_maps_picker_subcategories():
    assert label_to_pfc_key("Restaurants") == "FOOD_AND_DRINK_RESTAURANT"
    assert label_to_pfc_key("Dining Out") == "FOOD_AND_DRINK_RESTAURANTS"
    assert label_to_pfc_key("Coffee") == "FOOD_AND_DRINK_COFFEE"
    assert label_to_pfc_key("Rideshare & Taxis") == "TRANSPORTATION_TAXIS_AND_RIDE_SHARES"
    assert label_to_pfc_key("Food & Drink") == "FOOD_AND_DRINK"
    # Pass-through human labels must not poison reverse lookup.
    assert label_to_pfc_key("Paycheck") is None
