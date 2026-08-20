# backend/tests/test_optimization_service.py
from __future__ import annotations

import json
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

from app.models import (  # noqa: E402
    Account,
    Base,
    Holding,
    Item,
    MarketPrice,
    SectorConstraint,
    Security,
    TickerClassification,
    User,
)
import numpy as np  # noqa: E402

from app.services.optimization_service import (  # noqa: E402
    TRADING_DAYS_PER_YEAR,
    build_optimization_suggestion,
    neg_utility_bl,
)


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
    the current caller but is handed back in case a future test wants it.

    Also seeds SPY (mild uptrend + day-to-day zigzag noise, unrelated to the
    12 held tickers) over the same window even though nothing here holds it
    -- advanced mode (Task 10+) always fetches SPY as its market-implied-
    risk-aversion benchmark, per price_sync_service.py's BENCHMARK_TICKERS
    guarantee that SPY is always synced. Without it, price_matrix(db,
    ["SPY"], ...) would return empty and advanced mode would have no
    benchmark to compute delta from. The zigzag noise is deliberate, not
    decorative: a PURELY linear (noise-free) price series -- like
    _GOOD_TICKERS' own formula below -- has near-zero day-to-day return
    VARIANCE even though its mean return is normal, and
    market_implied_risk_aversion divides annualized return BY annualized
    variance. Verified empirically while building this fixture: a noise-
    free linear SPY series produced delta ~6.25 MILLION (vs. a realistic
    ~2-4), which blew up every downstream Black-Litterman number into
    nonsense and silently broke SLSQP convergence. The zigzag keeps SPY's
    variance on a realistic scale (annualized ~5%) while preserving a
    normal positive trend."""
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
        db_session.add(MarketPrice(ticker="SPY", price_date=day, close_price=Decimal(str(400 + i * 0.3 + (3 if i % 2 == 0 else -3)))))
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


# Sector names are deliberately spread alphabetically before AND after
# "healthcare" (communication < consumerdiscretionary < consumerstaples <
# energy < financials < healthcare < industrials < materials < realestate <
# technology < utilities) rather than making healthcare the first or last
# sector. That placement matters: if the sector-constraint loop in
# optimization_service.py had the classic late-binding-closure bug (every
# constraint lambda silently sharing the loop's FINAL `j` instead of its own
# sector's), every constraint would incorrectly apply to "utilities" (the
# last sector alphabetically) instead of its intended sector -- so
# healthcare's floor would silently go unenforced and
# test_advanced_mode_uses_black_litterman_and_sector_constraints below would
# only pass "by accident" if healthcare's unconstrained-optimal weight
# happened to already clear 2% on its own. Putting healthcare (and energy,
# used by the second sanity-check test below) in the middle of the sorted
# order means that failure mode is directly observable: with the bug, only
# "utilities" would be constrained and healthcare/energy would not.
#
# TICKF10 is the sole ETF (diversified across technology/financials/
# utilities, no healthcare or energy) so the Black-Litterman absolute-view
# path (Step 3.5-3.7) actually executes rather than trivially falling back
# to the no-views case. It's deliberately one of the FLAT tickers, not
# TICKG1/TICKG2: TICKG1/TICKG2's price formula (seeded_price_history above)
# is a perfectly linear day-over-day trend with no noise, which gives them
# near-zero return VARIANCE even though their mean return is normal
# (verified empirically while building this fixture -- see the SPY-zigzag
# comment above for the same underlying issue). That's harmless for basic
# mode (which never inverts the covariance matrix) but numerically toxic
# for Black-Litterman: using a near-zero-variance asset as the view ticker
# drives idzorek_omega's uncertainty to an artificially tiny value
# regardless of the 0.3 confidence passed in (Idzorek's Ω scales with the
# view portfolio's OWN tau*cov variance, which is ~0 here), which in turn
# swings the posterior to unrealistic extremes and silently breaks SLSQP
# convergence (result.success=False, falling back to the equal-weight
# `initial` guess -- every sector coming back at exactly 1/12 regardless of
# any constraint, which was observed while building this fixture and would
# have made both sector-floor tests below pass vacuously rather than for
# the right reason). market_cap_or_aum is spread evenly across all 12
# tickers (rather than concentrated in any one, as an earlier version of
# this fixture did with TICKG1/TICKG2) for the same reason: concentrating
# weight in a near-zero-variance ticker would let it dominate the
# market-cap-weighted prior too.
#
# TICKF06 (not TICKF01) is the sole healthcare-classified ticker, and
# TICKF08 (not TICKF03) is the sole energy-classified ticker -- chosen by
# empirically probing every flat ticker's UNCONSTRAINED optimal weight
# under this fixture (before picking which one plays which sector role).
# Most flat/good tickers land pinned at the 10% position cap regardless of
# sector, because _FLAT_TICKERS' price formula makes same-parity tickers
# perfectly +1-correlated and opposite-parity tickers perfectly
# -1-correlated (see seeded_price_history's own docstring) -- a mean-
# variance optimizer treats that as an irresistible hedge and wants as
# much of ~9 of the 12 tickers as the cap allows, independent of which
# sector floor (if any) they carry. Only TICKF02, TICKF06, and TICKF08
# consistently land BELOW the cap naturally (~5%, ~0%, and ~5%
# respectively, verified stable across every choice of ETF ticker) --
# TICKF06 and TICKF08 were picked from that set specifically so the floor
# constraints below have real work to do instead of being trivially
# satisfied by a ticker that was already going to sit at 10% anyway.
# Energy's floor is set to 8% (not a smaller value) in the tests below
# because TICKF08's own natural weight is ~5%, not ~0% -- an 8% floor is
# comfortably above that, so it's unambiguously the floor (not noise)
# pushing energy's weight up.
_SECTOR_BY_TICKER = {
    "TICKG1": "technology",
    "TICKG2": "financials",
    "TICKF01": "consumerstaples",
    "TICKF02": "industrials",
    "TICKF03": "realestate",
    "TICKF04": "utilities",
    "TICKF05": "materials",
    "TICKF06": "healthcare",
    "TICKF07": "communication",
    "TICKF08": "energy",
    "TICKF09": "consumerdiscretionary",
}
_ETF_TICKER = "TICKF10"


@pytest.fixture
def seeded_ticker_classifications(db_session, seeded_price_history):
    """TickerClassification rows for every ticker seeded_price_history
    creates (see _SECTOR_BY_TICKER's docstring above for the reasoning
    behind the ETF choice, sector assignments, and even market-cap
    weighting)."""
    classifications = [
        TickerClassification(
            ticker=_ETF_TICKER,
            asset_class="etf",
            sector_weights_json=json.dumps({"technology": 0.4, "financials": 0.3, "utilities": 0.3}),
            market_cap_or_aum=Decimal("6000000000"),
        ),
    ]
    for i, (ticker, sector) in enumerate(_SECTOR_BY_TICKER.items()):
        classifications.append(
            TickerClassification(
                ticker=ticker,
                asset_class="equity",
                sector_weights_json=json.dumps({sector: 1.0}),
                market_cap_or_aum=Decimal(str(5_000_000_000 + i * 300_000_000)),
            )
        )
    db_session.add_all(classifications)
    db_session.commit()
    return classifications


def test_advanced_mode_uses_black_litterman_and_sector_constraints(db_session, seeded_price_history, seeded_ticker_classifications):
    user = db_session.query(User).filter_by(id=1).one()
    user.optimization_advanced_enabled = True
    db_session.commit()
    db_session.add(SectorConstraint(user_id=1, sector="healthcare", floor_pct=2.0, cap_pct=40.0))
    db_session.commit()

    result = build_optimization_suggestion(db_session)

    assert result.advanced_enabled is True
    assert result.sector_breakdown is not None
    healthcare_row = next(r for r in result.sector_breakdown if r["sector"] == "healthcare")
    assert healthcare_row["weight_pct"] >= 2.0 - 0.5  # allow for solver tolerance, not full safety-margin clip


def test_advanced_mode_enforces_multiple_independent_sector_floors(db_session, seeded_price_history, seeded_ticker_classifications):
    # Sanity check called for explicitly in the task brief's self-review
    # step: two DIFFERENT sectors with two DIFFERENT floors must both be
    # independently enforced -- not just whichever one happens to be last
    # alphabetically. This is a stronger, more direct guard against the
    # late-binding-closure bug than the single-sector test above (which
    # could in principle still pass "by accident" under the bug if
    # healthcare's natural weight already cleared 2% on its own). Energy's
    # floor is 8% (not a smaller value): verified empirically (see
    # _SECTOR_BY_TICKER's docstring above) that TICKF08/energy's own
    # unconstrained-optimal weight is ~5%, so an 8% floor is comfortably
    # above that -- unambiguously the floor doing the work, not solver
    # noise -- whereas healthcare's ~0% natural weight makes even the
    # brief-specified 2% floor genuinely binding on its own.
    user = db_session.query(User).filter_by(id=1).one()
    user.optimization_advanced_enabled = True
    db_session.commit()
    db_session.add(SectorConstraint(user_id=1, sector="healthcare", floor_pct=2.0, cap_pct=40.0))
    db_session.add(SectorConstraint(user_id=1, sector="energy", floor_pct=8.0, cap_pct=40.0))
    db_session.commit()

    result = build_optimization_suggestion(db_session)

    breakdown_by_sector = {r["sector"]: r for r in result.sector_breakdown}
    assert breakdown_by_sector["healthcare"]["weight_pct"] >= 2.0 - 0.5
    assert breakdown_by_sector["energy"]["weight_pct"] >= 8.0 - 0.5


def test_advanced_mode_handles_zero_variance_ticker_without_crashing(db_session):
    # Regression test for a review finding carried forward from Task 5:
    # black_litterman_posterior's own np.linalg.inv(tau * cov) raises
    # LinAlgError: Singular matrix if cov contains ANY zero-variance asset
    # (ledoit_wolf_shrinkage's own test suite establishes zero-variance
    # tickers -- e.g. stale, halted, or constant-price securities -- as a
    # real, expected input, and a PSD covariance matrix with one
    # zero-variance asset forces that whole row/column to exactly zero,
    # independent of idzorek_omega's existing guard, which only protects
    # omega's OWN inversion). TICKZERO has a perfectly constant price
    # (return == 0 every day), so its row/column of the shared Ledoit-Wolf
    # covariance is exactly zero. TICKA is classified as an ETF so the
    # Black-Litterman absolute-view path (and therefore
    # black_litterman_posterior itself) actually executes rather than
    # trivially skipping BL -- without that, this test would not exercise
    # the code path it's meant to guard.
    user = db_session.query(User).filter_by(id=1).one()
    user.optimization_advanced_enabled = True
    db_session.commit()

    item = Item(user_id=1, item_id="item-1", access_token_encrypted="x")
    db_session.add(item)
    db_session.flush()
    account = Account(item_id=item.id, plaid_account_id="acc-1", name="Brokerage", type="investment", current_balance=Decimal("2000"))
    db_session.add(account)
    db_session.flush()

    sec_a = Security(plaid_security_id="sec-A", ticker_symbol="TICKA", type="equity")
    sec_z = Security(plaid_security_id="sec-Z", ticker_symbol="TICKZERO", type="equity")
    db_session.add_all([sec_a, sec_z])
    db_session.flush()

    db_session.add(Holding(account_id=account.id, security_id=sec_a.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))
    db_session.add(Holding(account_id=account.id, security_id=sec_z.id, quantity=Decimal("10"), institution_price=Decimal("100"), institution_value=Decimal("1000")))

    db_session.add(TickerClassification(ticker="TICKA", asset_class="etf", sector_weights_json=json.dumps({"technology": 1.0}), market_cap_or_aum=Decimal("1000000000")))
    db_session.add(TickerClassification(ticker="TICKZERO", asset_class="equity", sector_weights_json=json.dumps({"cash": 1.0}), market_cap_or_aum=Decimal("500000000")))

    start = date.today() - timedelta(days=60)
    for i in range(60):
        day = start + timedelta(days=i)
        db_session.add(MarketPrice(ticker="TICKA", price_date=day, close_price=Decimal(str(100 + i * 0.5))))
        db_session.add(MarketPrice(ticker="TICKZERO", price_date=day, close_price=Decimal("50.00")))  # constant -> exactly zero variance
        db_session.add(MarketPrice(ticker="SPY", price_date=day, close_price=Decimal(str(400 + i * 0.3 + (3 if i % 2 == 0 else -3)))))
    db_session.commit()

    result = build_optimization_suggestion(db_session, lookback_days=90)  # must not raise LinAlgError

    assert result.insufficient_data is False
    assert result.advanced_enabled is True
    tickers_present = {t.ticker for t in result.tickers}
    assert tickers_present == {"TICKA", "TICKZERO"}


def test_advanced_mode_handles_ticker_with_no_classification_row(db_session, seeded_price_history):
    # Regression test pinning a behavior a reviewer verified only by READING
    # the code, not by a test: a held, priceable ticker with NO
    # TickerClassification row at all -- genuinely absent from the table,
    # not a row with an empty/null sector_weights_json -- must not crash
    # advanced mode. Three call sites in the advanced branch each handle
    # this the same way, all traced by reading optimization_service.py and
    # sector_constraint_service.py:
    #   1. market_caps: `classification_by_ticker[t]...if t in
    #      classification_by_ticker...else 0.0` -> the ticker gets 0 market
    #      weight in the Black-Litterman prior (a plain delta*cov@w product,
    #      well-defined for any weight vector including zero entries).
    #   2. etf_indices: `classification_by_ticker.get(t) is not None and
    #      ...asset_class == "etf"` -> None short-circuits False, so the
    #      ticker is silently excluded from the ETF-views pool rather than
    #      raising a KeyError.
    #   3. build_sector_exposure_matrix (sector_constraint_service.py):
    #      `weights_by_ticker.get(ticker, {})` -> an absent ticker defaults
    #      to an empty dict, leaving its entire exposure-matrix row at 0 for
    #      every sector, rather than a KeyError.
    # This test exercises all three with a real solve instead of relying on
    # the code-reading argument alone.
    #
    # Reuses seeded_price_history (12 held+priced tickers, with TICKF10
    # pre-destined to be the sole ETF per _SECTOR_BY_TICKER's docstring
    # above) but does NOT use the seeded_ticker_classifications fixture,
    # since that fixture classifies every single ticker -- instead builds
    # the same rows inline, deliberately skipping TICKF01 so it alone ends
    # up with zero classification rows.
    user = db_session.query(User).filter_by(id=1).one()
    user.optimization_advanced_enabled = True
    db_session.commit()

    unclassified_ticker = "TICKF01"
    assert unclassified_ticker in seeded_price_history  # sanity: it's actually held+priced

    classifications = [
        TickerClassification(
            ticker=_ETF_TICKER,
            asset_class="etf",
            sector_weights_json=json.dumps({"technology": 0.4, "financials": 0.3, "utilities": 0.3}),
            market_cap_or_aum=Decimal("6000000000"),
        ),
    ]
    for i, (ticker, sector) in enumerate(_SECTOR_BY_TICKER.items()):
        if ticker == unclassified_ticker:
            continue  # deliberately left with NO TickerClassification row
        classifications.append(
            TickerClassification(
                ticker=ticker,
                asset_class="equity",
                sector_weights_json=json.dumps({sector: 1.0}),
                market_cap_or_aum=Decimal(str(5_000_000_000 + i * 300_000_000)),
            )
        )
    db_session.add_all(classifications)
    db_session.commit()

    # Confirm the setup actually produced the intended gap before exercising
    # the code under test -- otherwise a fixture typo could silently turn
    # this into a vacuous test that passes for the wrong reason.
    assert db_session.query(TickerClassification).filter_by(ticker=unclassified_ticker).first() is None

    result = build_optimization_suggestion(db_session)  # must not raise

    assert result.insufficient_data is False
    assert result.advanced_enabled is True
    tickers_present = {t.ticker for t in result.tickers}
    assert unclassified_ticker in tickers_present
    unclassified_weight = next(t for t in result.tickers if t.ticker == unclassified_ticker)
    assert 0.0 <= unclassified_weight.suggested_weight_pct <= 100.0

    weights_sum = sum(t.suggested_weight_pct for t in result.tickers)
    assert weights_sum == pytest.approx(100.0, abs=0.1)

    # sector_breakdown must still compute cleanly (no KeyError/crash) with
    # every reported sector weight a sane percentage -- the unclassified
    # ticker's all-zero exposure row simply contributes nothing to any
    # sector, rather than blowing up the matrix build.
    assert result.sector_breakdown is not None
    for row in result.sector_breakdown:
        assert 0.0 <= row["weight_pct"] <= 100.0 + 1e-6


def test_advanced_mode_returns_both_objectives_with_different_weights(db_session, seeded_price_history, seeded_ticker_classifications):
    user = db_session.query(User).filter_by(id=1).one()
    user.optimization_advanced_enabled = True
    user.optimization_concentration_strength = 0.5
    db_session.commit()

    result = build_optimization_suggestion(db_session)

    names = {o.name for o in result.objectives}
    assert names == {"max_sharpe", "max_quadratic_utility"}
    sharpe_weights = next(o for o in result.objectives if o.name == "max_sharpe").tickers
    utility_weights = next(o for o in result.objectives if o.name == "max_quadratic_utility").tickers
    assert sharpe_weights != utility_weights  # different objectives should generally diverge

    # Task 12 review fix round: assert on frontier_points' actual content
    # through the FULL integration path (a real build_optimization_suggestion
    # call wiring mu_bl/sigma_bl, ticker bounds, and sector_scipy_constraints
    # into sweep_efficient_frontier), not just the basic-mode `is None` check
    # elsewhere in this file. This is the only place in this test file that
    # would catch a future regression that broke the sweep call's wiring --
    # e.g. accidentally passing mean_returns/cov (the basic-mode inputs)
    # instead of mu_bl/sigma_bl, or advanced_constraints (which already
    # contains its own sum-to-one equality constraint) instead of
    # sector_scipy_constraints.
    assert result.frontier_points is not None
    assert len(result.frontier_points) > 0
    for point in result.frontier_points:
        assert set(point.keys()) == {"volatility_pct", "return_pct"}
    frontier_vols = [p["volatility_pct"] for p in result.frontier_points]
    assert frontier_vols == sorted(frontier_vols)  # non-decreasing, matching sweep_efficient_frontier's own contract


def test_concentration_strength_zero_produces_no_penalty(db_session, seeded_price_history, seeded_ticker_classifications):
    user = db_session.query(User).filter_by(id=1).one()
    user.optimization_advanced_enabled = True
    user.optimization_concentration_strength = 0.0
    db_session.commit()
    baseline = build_optimization_suggestion(db_session)

    user.optimization_concentration_strength = 1.0
    db_session.commit()
    concentrated_penalty = build_optimization_suggestion(db_session)

    def effective_n(objective_tickers):
        w = np.array([t.suggested_weight_pct for t in objective_tickers]) / 100
        return 1 / (w ** 2).sum() if (w ** 2).sum() > 0 else 0

    baseline_n = effective_n(next(o for o in baseline.objectives if o.name == "max_sharpe").tickers)
    penalized_n = effective_n(next(o for o in concentrated_penalty.objectives if o.name == "max_sharpe").tickers)
    assert penalized_n >= baseline_n  # higher strength should never concentrate MORE


# ─── Quadratic-utility objective: annualization ─────────────────────────────

def test_neg_utility_bl_annualizes_both_terms_hand_computed():
    """Pins neg_utility_bl's exact annualization against a hand-worked
    example, in the style of test_portfolio_math_service.py's formula tests.

    mu_bl/sigma_bl are DAILY (build_optimization_suggestion divides `cov`
    back to daily terms before every BL call), so BOTH terms annualize by
    x TRADING_DAYS_PER_YEAR -- returns because means scale linearly with
    time, variance because the variance of an i.i.d. sum does too. `delta`
    is already an annual coefficient (annual excess return / annual
    variance) and must NOT be rescaled.

        w             = [0.6, 0.4]
        mu_bl         = [0.001, 0.0005]                 (daily)
        sigma_bl      = diag(0.0004, 0.0001)            (daily)
        delta         = 3.0                             (annual, unscaled)
        gamma_utility = 0.15

        w'mu          = 0.6*0.001 + 0.4*0.0005 = 0.0008
        annual return = 0.0008 * 365           = 0.292
        w'Sigma w     = 0.36*0.0004 + 0.16*0.0001 = 0.00016
        annual var    = 0.00016 * 365          = 0.0584
        utility       = 0.292 - 0.5*3.0*0.0584 = 0.2044
        penalty       = 0.15 * (0.36 + 0.16)   = 0.078
        returned      = -0.2044 + 0.078        = -0.1264
    """
    assert TRADING_DAYS_PER_YEAR == 365  # the arithmetic above is pinned to this

    weights = np.array([0.6, 0.4])
    mu_bl = np.array([0.001, 0.0005])
    sigma_bl = np.diag([0.0004, 0.0001])

    result = neg_utility_bl(weights, mu_bl, sigma_bl, delta=3.0, gamma_utility=0.15)

    assert result == pytest.approx(-0.1264, abs=1e-9)


def test_neg_utility_bl_scales_variance_linearly_not_by_sqrt():
    """Guards the specific mistake the annualization fix had to avoid:
    reaching for sqrt(TRADING_DAYS_PER_YEAR) on the variance term because
    neg_sharpe_bl uses a sqrt. neg_sharpe_bl's sqrt is there because its
    denominator is a standard DEVIATION; quadratic utility penalizes
    VARIANCE directly, which scales linearly with time.

    Isolate the variance term by zeroing mu_bl and gamma_utility, so the
    returned value is exactly 0.5*delta*annual_variance.
    """
    weights = np.array([1.0, 0.0])
    sigma_bl = np.diag([0.0004, 0.0001])

    result = neg_utility_bl(
        weights, mu_bl=np.zeros(2), sigma_bl=sigma_bl, delta=2.0, gamma_utility=0.0,
    )

    linear = 0.5 * 2.0 * 0.0004 * TRADING_DAYS_PER_YEAR          # 0.146
    sqrt_scaled = 0.5 * 2.0 * 0.0004 * np.sqrt(TRADING_DAYS_PER_YEAR)  # 0.00764
    assert result == pytest.approx(linear, abs=1e-9)
    assert result != pytest.approx(sqrt_scaled, abs=1e-6)


def test_quadratic_utility_objective_is_not_collapsed_to_equal_weights(
    db_session, seeded_price_history, seeded_ticker_classifications,
):
    """Regression test for the missing annualization in neg_utility_bl.

    GAMMA_UTILITY_SCALE = 0.3 is calibrated against an ANNUAL-scale utility
    (portfolio_math_service.py's own comment: "utility ~O(0.01-0.5)"). While
    the objective was computed on raw DAILY mu_bl/sigma_bl it ran ~1/365th of
    that scale, so the concentration penalty dominated by ~2 orders of
    magnitude and this solve collapsed toward pure equal-weighting -- making
    the two "differentiated" objectives effectively one.

    The comparison is against the max-Sharpe objective solved from IDENTICAL
    inputs in the same run -- which was already annualized and so is
    unaffected by this fix -- rather than an absolute pp threshold, so it
    stays meaningful if the fixture's price series ever drift. Measured on
    this fixture at the default concentration_strength=0.5 (12 tickers,
    equal weight = 8.33%), max deviation from equal weight:

        objective              before fix   after fix
        max_sharpe               7.803pp      7.803pp   (unaffected)
        max_quadratic_utility    0.427pp      1.107pp
        utility / sharpe           5.5%        14.2%

    Note the bug bites in two compounding ways, which is why the
    unannualized figure is so small: the ~1/365 scale both lets the
    concentration penalty dominate the objective AND drops the whole
    objective near SLSQP's absolute `ftol`, so the solver converges almost
    immediately, barely off its equal-weight starting point.
    """
    user = db_session.query(User).filter_by(id=1).one()
    user.optimization_advanced_enabled = True
    user.optimization_concentration_strength = 0.5
    db_session.commit()

    result = build_optimization_suggestion(db_session)

    def max_deviation_from_equal_weight(name):
        objective = next(o for o in result.objectives if o.name == name)
        weights = np.array([t.suggested_weight_pct for t in objective.tickers])
        return float(np.abs(weights - 100.0 / len(weights)).max())

    sharpe_dispersion = max_deviation_from_equal_weight("max_sharpe")
    utility_dispersion = max_deviation_from_equal_weight("max_quadratic_utility")

    assert sharpe_dispersion > 0  # sanity: the reference objective isn't itself flat
    assert utility_dispersion / sharpe_dispersion >= 0.10, (
        f"quadratic-utility solve looks collapsed toward equal weights: "
        f"{utility_dispersion:.3f}pp vs max_sharpe's {sharpe_dispersion:.3f}pp "
        f"on identical inputs"
    )

    # ...and it must not have collapsed onto the max-Sharpe solve's answer
    # either -- the two objectives are meant to disagree.
    sharpe_objective = next(o for o in result.objectives if o.name == "max_sharpe")
    utility_objective = next(o for o in result.objectives if o.name == "max_quadratic_utility")
    assert [t.suggested_weight_pct for t in sharpe_objective.tickers] != [
        t.suggested_weight_pct for t in utility_objective.tickers
    ]
