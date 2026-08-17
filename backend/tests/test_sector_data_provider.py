from unittest.mock import MagicMock, patch

from app.sector_data_provider import fetch_ticker_classification


@patch("app.sector_data_provider.yf.Ticker")
def test_fetch_stock_classification(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.info = {"sector": "Technology", "quoteType": "EQUITY"}
    mock_ticker.fast_info = {"marketCap": 3_000_000_000_000}
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_ticker_classification("AAPL")

    assert result.asset_class == "equity"
    assert result.sector_weights == {"technology": 1.0}
    assert result.market_cap_or_aum == 3_000_000_000_000
    assert result.error is None


@patch("app.sector_data_provider.yf.Ticker")
def test_fetch_etf_classification_with_look_through(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.info = {"quoteType": "ETF", "totalAssets": 400_000_000_000}
    mock_ticker.fast_info = {"marketCap": None}
    mock_ticker.funds_data.sector_weightings = {
        "technology": 0.30, "healthcare": 0.12, "financial_services": 0.13,
    }
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_ticker_classification("VOO")

    assert result.asset_class == "etf"
    assert result.sector_weights["technology"] == 0.30
    assert result.market_cap_or_aum == 400_000_000_000
    assert result.error is None


@patch("app.sector_data_provider.yf.Ticker")
def test_fetch_commodity_etf_falls_back_to_commodities_bucket(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.info = {"quoteType": "ETF", "totalAssets": 60_000_000_000}
    mock_ticker.fast_info = {"marketCap": None}
    mock_ticker.funds_data.sector_weightings = {}
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_ticker_classification("GLD")

    assert result.asset_class == "commodity_etf"
    assert result.sector_weights == {"commodities": 1.0}
    assert result.error is None


@patch("app.sector_data_provider.yf.Ticker")
def test_fetch_unresolvable_ticker_returns_error_not_exception(mock_ticker_cls):
    mock_ticker_cls.side_effect = Exception("No data found for symbol")

    result = fetch_ticker_classification("BADTICKER")

    assert result.error is not None
    assert result.asset_class == "unknown"
    assert result.sector_weights == {}


@patch("app.sector_data_provider.yf.Ticker")
def test_fetch_ticker_with_empty_info_returns_error_not_exception(mock_ticker_cls):
    """Regression test for a real-network finding: yfinance 1.6.0 does NOT raise
    for a delisted/nonexistent ticker. yf.Ticker(...) succeeds and .info comes
    back with no quoteType at all (observed on a real bad symbol: .info ==
    {'trailingPegRatio': None}) instead of raising like test above assumes.
    Without an explicit check, this would silently fall through to an empty
    "equity" classification rather than surfacing as an error.
    """
    mock_ticker = MagicMock()
    mock_ticker.info = {"trailingPegRatio": None}
    mock_ticker.fast_info = {"marketCap": None}
    mock_ticker_cls.return_value = mock_ticker

    result = fetch_ticker_classification("THISISNOTAREALTICKERXYZ123")

    assert result.error is not None
    assert result.asset_class == "unknown"
    assert result.sector_weights == {}
    assert result.market_cap_or_aum is None
