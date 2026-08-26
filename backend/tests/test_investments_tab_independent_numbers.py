"""
Independent numerical audit of the Investments tab.

Recomputes money-weighted return (Excel-style XIRR), CAGR, and max-Sharpe
allocation from textbook formulas on raw snapshots/prices — without calling
the production helpers for the expected values — then compares those numbers
to `build_risk_metrics` / `build_optimization_suggestion` and to the JSON the
Investments page fetches (`GET /investments/risk/metrics` and `/optimize`).
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

from cryptography.fernet import Fernet

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from scipy.optimize import brentq, minimize  # noqa: E402
from sqlalchemy import create_engine, func  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import (  # noqa: E402
    Account,
    BalanceSnapshot,
    Base,
    Holding,
    InvestmentTransaction,
    Item,
    MarketPrice,
    Security,
    User,
)
from app.routes.portfolio_risk import AllocationWeight, OptimizationResponse, RiskMetricsResponse  # noqa: E402
from app.services.optimization_service import build_optimization_suggestion  # noqa: E402
from app.services.returns_service import build_cagr, build_mwr_xirr, build_twr_series  # noqa: E402
from app.services.risk_service import build_risk_metrics  # noqa: E402


# ── Independent calculators (deliberately not imported from app.services) ─────


def _independent_xirr(dated_amounts: list[tuple[date, float]]) -> float:
    """Excel XIRR: rate r that zeros NPV with Actual/365 day-count."""
    t0 = dated_amounts[0][0]

    def npv(rate: float) -> float:
        return sum(amt / ((1 + rate) ** ((d - t0).days / 365.0)) for d, amt in dated_amounts)

    return brentq(npv, -0.99, 10.0) * 100


def _independent_cagr(start_index: float, end_index: float, days: int) -> float:
    """Geometric annualization of a growth index over `days` calendar days."""
    return ((end_index / start_index) ** (365.0 / days) - 1) * 100


def _independent_twr(values_by_date: dict[date, float], flows_by_date: dict[date, float]) -> list[tuple[date, float]]:
    """Modified-Dietz TWR: same-day external flow excluded from that day's return."""
    dates = sorted(values_by_date)
    growth = 1.0
    series = [(dates[0], 1.0)]
    prev = values_by_date[dates[0]]
    for d in dates[1:]:
        value = values_by_date[d]
        flow = flows_by_date.get(d, 0.0)
        if prev > 0:
            growth *= 1.0 + (value - flow - prev) / prev
        series.append((d, growth))
        prev = value
    return series


def _independent_max_sharpe(
    mean_daily: np.ndarray,
    cov: np.ndarray,
    periods_per_year: float,
    rf_pct: float,
) -> np.ndarray:
    n = len(mean_daily)

    def neg_sharpe(w: np.ndarray) -> float:
        ret = float(np.dot(w, mean_daily)) * periods_per_year
        vol = float(np.sqrt(w @ cov @ w)) * np.sqrt(periods_per_year)
        if vol == 0:
            return 0.0
        return -(ret - rf_pct / 100) / vol

    result = minimize(
        neg_sharpe,
        np.full(n, 1.0 / n),
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1}],
    )
    return result.x if result.success else np.full(n, 1.0 / n)


def _closed_form_tangency(mean_daily: np.ndarray, cov: np.ndarray, periods_per_year: float, rf_pct: float) -> np.ndarray:
    """Unconstrained tangency portfolio, clipped to long-only and renormalized.

    Σ_ann^{-1}(μ_ann − rf) ∝ Σ^{-1}(μ_daily − rf / periods_per_year).
    """
    rf_daily = (rf_pct / 100.0) / periods_per_year
    raw = np.linalg.solve(cov, mean_daily - rf_daily)
    clipped = np.maximum(raw, 0.0)
    if clipped.sum() <= 0:
        return np.full_like(raw, 1.0 / len(raw))
    return clipped / clipped.sum()


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db_session():
    # Per-test in-memory DB so cases that share ticker/item ids cannot leak.
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.add(User(id=1, username="default_user"))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _brokerage(db, *, balance: str = "1000", item_id: str = "item-1") -> Account:
    item = Item(user_id=1, item_id=item_id, access_token_encrypted="x")
    db.add(item)
    db.flush()
    acc = Account(
        item_id=item.id,
        plaid_account_id="acc-1",
        name="Brokerage",
        type="investment",
        current_balance=Decimal(balance),
    )
    db.add(acc)
    db.flush()
    return acc


# ── Independent solver sanity ─────────────────────────────────────────────────


def test_independent_xirr_matches_microsoft_excel_example():
    # https://support.microsoft.com/office/xirr-function-de6232d9-1819-4e2c-82b5-4ad4733747b2
    flows = [
        (date(2008, 1, 1), -10000.0),
        (date(2008, 3, 1), 2750.0),
        (date(2008, 10, 30), 4250.0),
        (date(2009, 2, 15), 3250.0),
        (date(2009, 4, 1), 2750.0),
    ]
    assert _independent_xirr(flows) == pytest.approx(37.3362533, abs=0.01)


# ── Money-weighted return (XIRR) vs Investments tab ───────────────────────────


def test_mwr_no_cash_flow_matches_independent_and_cagr(db_session):
    acc = _brokerage(db_session)
    d0, d1 = date(2025, 1, 1), date(2026, 1, 1)
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=1000, snapshot_date=d0))
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=1100, snapshot_date=d1))
    db_session.commit()

    expected = _independent_xirr([(d0, -1000.0), (d1, 1100.0)])
    got = build_mwr_xirr(db_session, [acc.id], d0, d1)
    series = build_twr_series(db_session, [acc.id], d0, d1)
    cagr = build_cagr(series)

    assert expected == pytest.approx(10.0, abs=0.05)
    assert got == pytest.approx(expected, abs=0.05)
    assert cagr == pytest.approx(expected, abs=0.05)


def test_mwr_mid_deposit_matches_independent_not_naive_cagr(db_session):
    """A mid-year deposit that then earns 10% must not look like a 120% CAGR."""
    acc = _brokerage(db_session, balance="2200")
    d0, d_mid, d1 = date(2025, 1, 1), date(2025, 7, 1), date(2026, 1, 1)
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=1000, snapshot_date=d0))
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=2000, snapshot_date=d_mid))
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=2200, snapshot_date=d1))
    db_session.add(InvestmentTransaction(
        account_id=acc.id, plaid_investment_transaction_id="mid-dep",
        name="deposit", type="cash", subtype="deposit", amount=-1000, date=d_mid,
    ))
    db_session.commit()

    values = {d0: 1000.0, d_mid: 2000.0, d1: 2200.0}
    flows = {d_mid: 1000.0}
    twr = _independent_twr(values, flows)
    days = (d1 - d0).days
    expected_cagr = _independent_cagr(twr[0][1], twr[-1][1], days)
    expected_mwr = _independent_xirr([(d0, -1000.0), (d_mid, -1000.0), (d1, 2200.0)])
    naive_balance_cagr = ((2200 / 1000) ** (365.0 / days) - 1) * 100

    series = build_twr_series(db_session, [acc.id], d0, d1)
    got_cagr = build_cagr(series)
    got_mwr = build_mwr_xirr(db_session, [acc.id], d0, d1)

    assert twr[-1][1] == pytest.approx(1.10, abs=0.001)
    assert expected_cagr == pytest.approx(10.0, abs=0.05)
    assert naive_balance_cagr == pytest.approx(120.0, abs=0.5)
    assert got_cagr == pytest.approx(expected_cagr, abs=0.05)
    assert got_mwr == pytest.approx(expected_mwr, abs=0.05)
    # Money-weighted > time-weighted here: more capital sat in the growing half.
    assert got_mwr > got_cagr
    assert got_mwr == pytest.approx(13.44, abs=0.05)


def test_mwr_last_day_deposit_is_not_a_gain(db_session):
    acc = _brokerage(db_session, balance="1100")
    d0, d1 = date(2025, 1, 1), date(2026, 1, 1)
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=1000, snapshot_date=d0))
    db_session.add(BalanceSnapshot(account_id=acc.id, balance=1100, snapshot_date=d1))
    db_session.add(InvestmentTransaction(
        account_id=acc.id, plaid_investment_transaction_id="last-dep",
        name="deposit", type="cash", subtype="deposit", amount=-100, date=d1,
    ))
    db_session.commit()

    expected = _independent_xirr([(d0, -1000.0), (d1, -100.0), (d1, 1100.0)])
    got = build_mwr_xirr(db_session, [acc.id], d0, d1)
    assert expected == pytest.approx(0.0, abs=0.05)
    assert got == pytest.approx(expected, abs=0.05)


def test_cagr_is_annualized_twr_not_raw_balance_ratio(db_session):
    acc = _brokerage(db_session)
    d0 = date.today() - timedelta(days=180)
    values = []
    v = 1000.0
    for i in range(181):
        values.append((d0 + timedelta(days=i), v))
        v *= 1.0003  # mild daily drift, no cash flows
    for day, bal in values:
        db_session.add(BalanceSnapshot(account_id=acc.id, balance=round(bal, 4), snapshot_date=day))
    db_session.commit()

    series = build_twr_series(db_session, [acc.id], d0, date.today())
    got = build_cagr(series)
    days = (series[-1].date - series[0].date).days
    expected = _independent_cagr(series[0].growth_index, series[-1].growth_index, days)
    naive = ((values[-1][1] / values[0][1]) ** (365.0 / days) - 1) * 100

    assert got == pytest.approx(expected, abs=0.05)
    # No external flows → TWR CAGR == naive balance CAGR.
    assert got == pytest.approx(naive, abs=0.05)
    risk = build_risk_metrics(db_session, lookback_days=365)
    assert risk.cagr_pct == pytest.approx(round(expected, 2), abs=0.02)
    assert risk.mwr_pct == pytest.approx(round(build_mwr_xirr(db_session, [acc.id], d0, date.today()), 2), abs=0.02)


# ── Max-Sharpe vs Investments tab ─────────────────────────────────────────────


def _weekday_prices(start: date, n_calendar_days: int, rng: np.random.Generator) -> tuple[list[date], np.ndarray, np.ndarray]:
    """Simulate two tickers on weekdays only (yfinance-like)."""
    dates: list[date] = []
    aaa: list[float] = []
    bbb: list[float] = []
    a = b = 100.0
    # Mildly correlated but both long-run positive excess return vs 5% rf.
    for i in range(n_calendar_days):
        day = start + timedelta(days=i)
        if day.weekday() >= 5:
            continue
        shock_a = rng.normal(0.00045, 0.008)
        shock_b = rng.normal(0.00070, 0.014)
        a *= 1.0 + shock_a
        b *= 1.0 + shock_b
        dates.append(day)
        aaa.append(a)
        bbb.append(b)
    return dates, np.array(aaa), np.array(bbb)


def test_optimization_matches_independent_calendar_span_sharpe(db_session):
    acc = _brokerage(db_session, balance="2000")
    sec_a = Security(plaid_security_id="sec-A", ticker_symbol="AAA", type="equity")
    sec_b = Security(plaid_security_id="sec-B", ticker_symbol="BBB", type="equity")
    db_session.add_all([sec_a, sec_b])
    db_session.flush()
    db_session.add(Holding(
        account_id=acc.id, security_id=sec_a.id, quantity=Decimal("10"),
        institution_price=Decimal("100"), institution_value=Decimal("1000"),
    ))
    db_session.add(Holding(
        account_id=acc.id, security_id=sec_b.id, quantity=Decimal("10"),
        institution_price=Decimal("100"), institution_value=Decimal("1000"),
    ))

    start = date.today() - timedelta(days=364)
    rng = np.random.default_rng(42)
    dates, aaa, bbb = _weekday_prices(start, 365, rng)
    for i, d in enumerate(dates):
        db_session.add(MarketPrice(ticker="AAA", price_date=d, close_price=Decimal(str(round(float(aaa[i]), 6)))))
        db_session.add(MarketPrice(ticker="BBB", price_date=d, close_price=Decimal(str(round(float(bbb[i]), 6)))))
    db_session.commit()

    prices = np.column_stack([aaa, bbb])
    returns = prices[1:] / prices[:-1] - 1
    mean = returns.mean(axis=0)
    cov = np.cov(returns, rowvar=False, ddof=1)
    span = (dates[-1] - dates[0]).days
    k = (len(returns)) / (span / 365.0)
    # Hard-coded 365 would be the old (wrong for weekday prices) factor.
    assert k == pytest.approx(252, abs=20)
    assert abs(k - 365) > 50

    rf = 5.0  # DEFAULT_RISK_FREE_RATE_PCT — nothing cached in this fixture
    current_w = np.array([0.5, 0.5])
    indep_suggested = _independent_max_sharpe(mean, cov, k, rf)
    closed = _closed_form_tangency(mean, cov, k, rf)

    data = build_optimization_suggestion(db_session, lookback_days=365)
    assert not data.insufficient_data
    by_ticker = {t.ticker: t for t in data.tickers}

    assert by_ticker["AAA"].current_weight_pct == pytest.approx(50.0, abs=0.05)
    assert by_ticker["BBB"].current_weight_pct == pytest.approx(50.0, abs=0.05)

    assert by_ticker["AAA"].suggested_weight_pct == pytest.approx(indep_suggested[0] * 100, abs=0.5)
    assert by_ticker["BBB"].suggested_weight_pct == pytest.approx(indep_suggested[1] * 100, abs=0.5)
    # Long-only not binding on this seed → SLSQP matches the closed-form tangency.
    assert indep_suggested == pytest.approx(closed, abs=0.02)

    cur_ret = float(np.dot(current_w, mean)) * k * 100
    cur_vol = float(np.sqrt(current_w @ cov @ current_w)) * np.sqrt(k) * 100
    assert data.current_expected_return_pct == pytest.approx(cur_ret, abs=0.05)
    assert data.current_volatility_pct == pytest.approx(cur_vol, abs=0.05)

    # The old 365-day annualization would inflate current expected return.
    inflated = float(np.dot(current_w, mean)) * 365 * 100
    assert abs(inflated - cur_ret) > 1.0
    assert data.current_expected_return_pct != pytest.approx(inflated, abs=0.2)

    sug_w = np.array([by_ticker["AAA"].suggested_weight_pct, by_ticker["BBB"].suggested_weight_pct]) / 100
    assert sug_w.sum() == pytest.approx(1.0, abs=0.002)


# ── JSON the Investments tab actually renders ─────────────────────────────────


def test_investments_tab_payload_matches_independent_mwr_cagr_and_optimizer(db_session):
    """The page's useInvestmentsRisk / useInvestmentsOptimization hooks JSON-decode
    RiskMetricsResponse / OptimizationResponse. Serialize those models the same
    way FastAPI does and compare to independent XIRR, CAGR, and max-Sharpe."""
    acc = _brokerage(db_session, balance="2000", item_id="item-tab")
    # History the risk card uses. Grow from $1000, then park a $200 deposit
    # at day 60 so money-weighted and time-weighted returns diverge.
    d0 = date.today() - timedelta(days=120)
    mid = d0 + timedelta(days=60)
    v = 1000.0
    for i in range(121):
        day = d0 + timedelta(days=i)
        if day == mid:
            v += 200.0
        db_session.add(BalanceSnapshot(account_id=acc.id, balance=round(v, 4), snapshot_date=day))
        v *= 1.0004
    db_session.add(InvestmentTransaction(
        account_id=acc.id, plaid_investment_transaction_id="api-mid-dep",
        name="deposit", type="cash", subtype="deposit", amount=-200, date=mid,
    ))

    sec_a = Security(plaid_security_id="sec-A", ticker_symbol="AAA", type="equity")
    sec_b = Security(plaid_security_id="sec-B", ticker_symbol="BBB", type="equity")
    db_session.add_all([sec_a, sec_b])
    db_session.flush()
    db_session.add(Holding(
        account_id=acc.id, security_id=sec_a.id, quantity=Decimal("10"),
        institution_price=Decimal("100"), institution_value=Decimal("1000"),
    ))
    db_session.add(Holding(
        account_id=acc.id, security_id=sec_b.id, quantity=Decimal("10"),
        institution_price=Decimal("100"), institution_value=Decimal("1000"),
    ))
    start = date.today() - timedelta(days=364)
    rng = np.random.default_rng(7)
    dates, aaa, bbb = _weekday_prices(start, 365, rng)
    for i, d in enumerate(dates):
        db_session.add(MarketPrice(ticker="AAA", price_date=d, close_price=Decimal(str(round(float(aaa[i]), 6)))))
        db_session.add(MarketPrice(ticker="BBB", price_date=d, close_price=Decimal(str(round(float(bbb[i]), 6)))))
    db_session.commit()

    service_metrics = build_risk_metrics(db_session, lookback_days=365)
    service_opt = build_optimization_suggestion(db_session, lookback_days=365)
    metrics = RiskMetricsResponse(**vars(service_metrics)).model_dump()
    optimize = OptimizationResponse(
        tickers=[AllocationWeight(**vars(w)) for w in service_opt.tickers],
        current_expected_return_pct=service_opt.current_expected_return_pct,
        current_volatility_pct=service_opt.current_volatility_pct,
        current_sharpe=service_opt.current_sharpe,
        suggested_expected_return_pct=service_opt.suggested_expected_return_pct,
        suggested_volatility_pct=service_opt.suggested_volatility_pct,
        suggested_sharpe=service_opt.suggested_sharpe,
        data_points=service_opt.data_points,
        insufficient_data=service_opt.insufficient_data,
    ).model_dump()

    lookback_start = date.today() - timedelta(days=365)
    lookback_end = date.today()
    series = build_twr_series(db_session, [acc.id], lookback_start, lookback_end)
    days = (series[-1].date - series[0].date).days
    indep_cagr = _independent_cagr(series[0].growth_index, series[-1].growth_index, days)
    assert metrics["cagr_pct"] == pytest.approx(indep_cagr, abs=0.05)

    rows = (
        db_session.query(BalanceSnapshot.snapshot_date, func.sum(BalanceSnapshot.balance))
        .filter(BalanceSnapshot.account_id == acc.id)
        .group_by(BalanceSnapshot.snapshot_date)
        .all()
    )
    totals = {d: float(v) for d, v in rows if lookback_start <= d <= lookback_end}
    snap_dates = sorted(totals)
    dated = [(snap_dates[0], -totals[snap_dates[0]]), (mid, -200.0), (snap_dates[-1], totals[snap_dates[-1]])]
    indep_mwr = _independent_xirr(dated)
    assert metrics["mwr_pct"] == pytest.approx(indep_mwr, abs=0.05)
    assert metrics["twr_pct"] == pytest.approx((series[-1].growth_index / series[0].growth_index - 1) * 100, abs=0.05)

    assert optimize["insufficient_data"] is False
    opt_by = {t["ticker"]: t for t in optimize["tickers"]}
    svc_by = {t.ticker: t for t in service_opt.tickers}
    assert opt_by["AAA"]["suggested_weight_pct"] == pytest.approx(svc_by["AAA"].suggested_weight_pct, abs=0.011)
    assert opt_by["BBB"]["suggested_weight_pct"] == pytest.approx(svc_by["BBB"].suggested_weight_pct, abs=0.011)
    assert sum(t["suggested_weight_pct"] for t in optimize["tickers"]) == pytest.approx(100.0, abs=0.05)
    assert optimize["current_sharpe"] == pytest.approx(service_opt.current_sharpe, abs=0.011)
    assert optimize["suggested_sharpe"] == pytest.approx(service_opt.suggested_sharpe, abs=0.011)
    assert optimize["suggested_sharpe"] >= optimize["current_sharpe"] - 0.02
