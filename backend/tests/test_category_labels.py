from mcp_server.category_labels import format_category


def test_format_category_maps_plaid_codes():
    assert format_category("FOOD_AND_DRINK") == "Food & Drink"
    assert format_category("RENT_AND_UTILITIES") == "Rent & Utilities"
    assert format_category("TRANSFER_IN") == "Transfer In"
    assert format_category("TRANSPORTATION_TAXIS_AND_RIDE_SHARES") == "Rideshare"


def test_format_category_income_salary_hierarchical():
    assert format_category("INCOME_SALARY") == "Income · Salary"
    assert format_category("income_salary") == "Income · Salary"
    assert format_category("Salary") == "Income · Salary"
