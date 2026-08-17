# backend/tests/test_optimization_service.py
from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

from cryptography.fernet import Fernet

# optimization_service imports get_cached_risk_free_rate -> app_config ->
# app.security, which raises at import time if ENCRYPTION_KEY is unset. Match
# the same workaround used by other tests that transitively touch
# app.security (e.g. tests/test_risk_free_rate.py, tests/test_risk_service.py)
# so this file passes when run standalone, not just as part of the full suite.
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Account, Base, Holding, Item, MarketPrice, Security, User  # noqa: E402
from app.services.optimization_service import build_optimization_suggestion  # noqa: E402


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'opt.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _setup_two_ticker_portfolio(db):
    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db.add(item)
    db.flush()
    account = Account(item_id=item.id, plaid_account_id="acc-1", name="Brokerage", type="investment", current_balance=Decimal("2000"))
    db.add(account)
    db.flush()

    sec_a = Security(plaid_security_id="sec-A", ticker_symbol="TICKA", type="equity")
    sec_b = Security(plaid_security_id="sec-B", ticker_symbol="TICKB", type="equity")
    db.add_all([sec_a, sec_b])
    db.flush()

    # Equal-dollar starting weights: 50/50.
    db.add(Holding(account_id=account.id, security_id=sec_a.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))
    db.add(Holding(account_id=account.id, security_id=sec_b.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))

    # TICKA: steady uptrend, low volatility. TICKB: flat with noise. A high-Sharpe
    # optimizer should shift weight toward TICKA relative to the 50/50 start.
    start = date.today() - timedelta(days=60)
    a_prices = [100 + i * 0.5 for i in range(60)]
    b_prices = [100 + (5 if i % 2 == 0 else -5) for i in range(60)]
    for i in range(60):
        day = start + timedelta(days=i)
        db.add(MarketPrice(ticker="TICKA", price_date=day, close_price=Decimal(str(a_prices[i]))))
        db.add(MarketPrice(ticker="TICKB", price_date=day, close_price=Decimal(str(b_prices[i]))))
    db.commit()
    return account


def test_optimization_shifts_weight_toward_higher_sharpe_asset(db_session):
    _setup_two_ticker_portfolio(db_session)
    # This test is about core optimizer direction (favor the higher-Sharpe
    # asset), not the position-cap feature (which has its own dedicated
    # test: test_basic_mode_matches_position_cap_and_single_objective).
    # Disable the cap explicitly (100% = unreachable ceiling for 2 assets)
    # so relax_position_cap_if_needed's default-10%-relaxed-to-~52.63%-for-
    # n=2 behavior doesn't clip the optimizer's desired >60% allocation to
    # TICKA and turn this into an accidental cap test.
    user = db_session.query(User).filter_by(id=1).one()
    user.optimization_position_cap_pct = 100.0
    db_session.commit()

    data = build_optimization_suggestion(db_session, lookback_days=90)

    assert not data.insufficient_data
    assert len(data.tickers) == 2
    weight_by_ticker = {t.ticker: t for t in data.tickers}
    assert weight_by_ticker["TICKA"].current_weight_pct == pytest.approx(50.0, abs=0.5)
    assert weight_by_ticker["TICKB"].current_weight_pct == pytest.approx(50.0, abs=0.5)
    # TICKA is a steady uptrend (high Sharpe), TICKB is flat/noisy (near-zero
    # Sharpe) -> the optimizer should suggest materially more than 50% in TICKA.
    assert weight_by_ticker["TICKA"].suggested_weight_pct > 60.0

    weights_sum = sum(t.suggested_weight_pct for t in data.tickers)
    assert weights_sum == pytest.approx(100.0, abs=0.1)
    for t in data.tickers:
        assert 0.0 <= t.suggested_weight_pct <= 100.0

    assert data.suggested_sharpe is not None and data.current_sharpe is not None
    assert data.suggested_sharpe >= data.current_sharpe - 0.01  # optimizer must not do worse


def test_optimization_drops_unpriceable_ticker_and_uses_remaining(db_session):
    # Three-ticker portfolio where TICKC has a holding but zero MarketPrice
    # rows (e.g. yfinance couldn't resolve it). The optimizer should drop
    # TICKC and still produce a valid suggestion over TICKA/TICKB rather than
    # reporting insufficient_data for the whole book.
    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db_session.add(item)
    db_session.flush()
    account = Account(item_id=item.id, plaid_account_id="acc-1", name="Brokerage", type="investment", current_balance=Decimal("3000"))
    db_session.add(account)
    db_session.flush()

    sec_a = Security(plaid_security_id="sec-A", ticker_symbol="TICKA", type="equity")
    sec_b = Security(plaid_security_id="sec-B", ticker_symbol="TICKB", type="equity")
    sec_c = Security(plaid_security_id="sec-C", ticker_symbol="TICKC", type="equity")
    db_session.add_all([sec_a, sec_b, sec_c])
    db_session.flush()

    db_session.add(Holding(account_id=account.id, security_id=sec_a.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))
    db_session.add(Holding(account_id=account.id, security_id=sec_b.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))
    # TICKC is held but has NO MarketPrice rows at all -- unresolvable ticker.
    db_session.add(Holding(account_id=account.id, security_id=sec_c.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))

    start = date.today() - timedelta(days=60)
    a_prices = [100 + i * 0.5 for i in range(60)]
    b_prices = [100 + (5 if i % 2 == 0 else -5) for i in range(60)]
    for i in range(60):
        day = start + timedelta(days=i)
        db_session.add(MarketPrice(ticker="TICKA", price_date=day, close_price=Decimal(str(a_prices[i]))))
        db_session.add(MarketPrice(ticker="TICKB", price_date=day, close_price=Decimal(str(b_prices[i]))))
    db_session.commit()

    data = build_optimization_suggestion(db_session, lookback_days=90)

    assert not data.insufficient_data
    tickers_present = {t.ticker for t in data.tickers}
    assert tickers_present == {"TICKA", "TICKB"}


def test_optimization_insufficient_data_with_fewer_than_two_tickers(db_session):
    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db_session.add(item)
    db_session.flush()
    account = Account(item_id=item.id, plaid_account_id="acc-1", name="Brokerage", type="investment")
    db_session.add(account)
    db_session.commit()

    data = build_optimization_suggestion(db_session, lookback_days=90)
    assert data.insufficient_data is True
    assert data.tickers == []


# Number of tickers needed so a 10% position cap is NOT auto-relaxed by
# relax_position_cap_if_needed (n_tickers * cap must clear 1.0 with its 0.95
# safety margin -- n=10 still relaxes the cap to ~10.53%, n=11 is the first
# n where 10% survives untouched). 12 gives comfortable margin above that
# boundary.
_GOOD_TICKERS = ["TICKG1", "TICKG2"]
_FLAT_TICKERS = [f"TICKF{i:02d}" for i in range(1, 11)]


@pytest.fixture
def seeded_price_history(db_session):
    """Seeds db_session with a 12-ticker portfolio (2 steady-uptrend 'good'
    tickers + 10 flat/oscillating tickers) and 60 days of overlapping
    MarketPrice history for all of them. Enough tickers that a 10% position
    cap stays binding (see note above) rather than being relaxed away.

    Empirically (verified by running the optimizer uncapped against this
    fixture and inspecting the weights), it is NOT the "good" tickers that
    push past 10% -- TICKG1/TICKG2 have far higher standalone Sharpe than
    any flat ticker, but they're ~99.99% correlated with each other and
    have no offsetting asset anywhere in the universe, so they add little
    diversification value. Every flat ticker's price oscillates by a fixed
    dollar amount on a deterministic per-ticker parity schedule ((i + k) %
    2), which gives it a small positive expected return (an up-swing and
    the matching down-swing aren't equal in percentage terms off a fixed
    dollar band) and makes every pair of flat tickers either exactly +1 or
    exactly -1 correlated depending on parity -- exactly the combination
    (anti-correlated, positive-expected-return legs that cancel variance
    when combined) a mean-variance optimizer is most eager to exploit. So
    it's several of the FLAT tickers (currently TICKF01/04/07/10) that pile
    up past 10% when uncapped, and sit pinned exactly at the ceiling in the
    capped test below -- not the good ones. The cap still genuinely binds
    (cap_relaxed comes back None; those tickers sit exactly at 10%), so the
    test isn't vacuous -- it's just exercising a less obvious mechanism
    (correlation-driven risk cancellation) than "good assets get capped"
    would suggest.

    Mirrors _setup_two_ticker_portfolio's story-per-ticker style, generalized
    to N tickers via loops. Return value (the ticker list) isn't needed by
    the current caller but is handed back in case a future test wants it."""
    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db_session.add(item)
    db_session.flush()
    account = Account(item_id=item.id, plaid_account_id="acc-1", name="Brokerage", type="investment", current_balance=Decimal("12000"))
    db_session.add(account)
    db_session.flush()

    tickers = _GOOD_TICKERS + _FLAT_TICKERS
    securities = {t: Security(plaid_security_id=f"sec-{t}", ticker_symbol=t, type="equity") for t in tickers}
    db_session.add_all(securities.values())
    db_session.flush()

    for t in tickers:
        db_session.add(Holding(account_id=account.id, security_id=securities[t].id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))

    start = date.today() - timedelta(days=60)
    for i in range(60):
        day = start + timedelta(days=i)
        for j, t in enumerate(_GOOD_TICKERS):
            price = 100 + i * (0.5 + 0.1 * j)
            db_session.add(MarketPrice(ticker=t, price_date=day, close_price=Decimal(str(price))))
        for k, t in enumerate(_FLAT_TICKERS):
            sign = 1 if (i + k) % 2 == 0 else -1
            price = 100 + sign * (4 + k % 3)
            db_session.add(MarketPrice(ticker=t, price_date=day, close_price=Decimal(str(price))))
    db_session.commit()
    return tickers


def test_basic_mode_matches_position_cap_and_single_objective(db_session, seeded_price_history):
    user = db_session.query(User).filter_by(id=1).one()
    user.optimization_advanced_enabled = False
    user.optimization_position_cap_pct = 10.0
    db_session.commit()

    result = build_optimization_suggestion(db_session)

    assert result.advanced_enabled is False
    assert len(result.objectives) == 1
    assert result.objectives[0].name == "max_sharpe"
    assert result.frontier_points is None
    assert result.sector_breakdown is None
    for weight in (tw.suggested_weight_pct for tw in result.tickers):
        assert weight <= 10.0 + 1e-6
