import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import yfinance as yf
import datetime as dt
from pathlib import Path

## PyPortfolioOpt
import pypfopt as ppo
from pypfopt import risk_models, BlackLittermanModel, EfficientFrontier, objective_functions
from pypfopt.black_litterman import market_implied_prior_returns, market_implied_risk_aversion
from pypfopt import plotting
from pypfopt.expected_returns import mean_historical_return

import csv
import io
import sqlite3
import urllib.request

FRED_DGS3MO = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO"

def trailing_rf(default=0.05) -> float:
    """Latest 3-month T-bill yield from FRED, as a decimal."""
    try:
        with urllib.request.urlopen(FRED_DGS3MO, timeout=10) as resp:
            text = resp.read().decode()
        latest = None
        for row in csv.DictReader(io.StringIO(text)):
            raw = row.get("DGS3MO", ".")
            if raw and raw != ".":
                latest = float(raw)
        return latest / 100.0 if latest is not None else default
    except Exception:
        return default

rf_rate = trailing_rf()

#########################################################
## live portfolio import
#########################################################
conn = sqlite3.connect('##PATH TO LEDGER.DB##')

account_value = conn.execute("""
    SELECT SUM(a.current_balance)
    FROM accounts a
    JOIN items i ON i.id = a.item_id
    WHERE a.type = 'investment'
      AND i.item_id NOT IN ('manual_import', 'test_item', 'crypto_wallet')
""").fetchone()[0]

holdings = pd.read_sql_query("""
    SELECT s.ticker_symbol AS ticker, s.type AS security_type,
    SUM(h.institution_value) AS value
    FROM holdings h
    JOIN securities s ON s.id = h.security_id
    JOIN accounts a ON a.id = h.account_id
    JOIN items i ON i.id = a.item_id
    WHERE a.type = 'investment'
      AND s.ticker_symbol IS NOT NULL
      AND IFNULL(s.is_cash_equivalent, 0) = 0
      AND i.item_id NOT IN ('manual_import', 'test_item', 'crypto_wallet')
    GROUP BY s.ticker_symbol, s.type
""", conn)
values = holdings.set_index("ticker")["value"]
weights = values / values.sum()

tickers = list(weights.index)
placeholders = ",".join("?" * len(tickers))
sql_price = pd.read_sql_query(
    f"SELECT ticker, price_date, close_price FROM market_prices WHERE ticker IN ({placeholders})",
    conn,
    params=tickers,
)
spy = pd.read_sql_query(
    "SELECT price_date, close_price FROM market_prices WHERE ticker = 'SPY'",
    conn,
)
conn.close()
#########################################################
## sort by price date, drop values which add no value
sql_price["price_date"] = pd.to_datetime(sql_price["price_date"])
spy["price_date"] = pd.to_datetime(spy["price_date"])
sql_price = sql_price.sort_values("price_date")
spy = spy.sort_values("price_date")

## pivot into dates × tickers, holdings only
LOOKBACK_YEARS = 3

close_df = sql_price.pivot(index="price_date", columns="ticker", values="close_price")
close_df = close_df[close_df.columns.intersection(weights.index)]
end = close_df.index.max()
start = end - pd.DateOffset(years=LOOKBACK_YEARS)
close_df = close_df.loc[start:end]
min_obs = max(252, int(0.95 * len(close_df)))
close_df = close_df.loc[:, close_df.count() >= min_obs]
close_df = close_df.dropna()
spy = spy.loc[spy["price_date"].between(close_df.index.min(), close_df.index.max())]
print(f"lookback {close_df.index.min().date()} → {close_df.index.max().date()} ({len(close_df)} days, {close_df.shape[1]} tickers)")



weights = weights.reindex(close_df.columns).dropna()
weights = weights / weights.sum()

covariance_matrix = risk_models.CovarianceShrinkage(close_df).ledoit_wolf()


def market_cap(ticker: str):
    yahoo = ticker.replace(".", "-")  # BRK.B -> BRK-B
    try:
        t = yf.Ticker(yahoo)
        cap = t.fast_info.get("marketCap")
        if cap:
            return cap
        # ETFs have no marketCap in fast_info — AUM is the right proxy for
        # their weight in the reverse-optimized market prior. Without this,
        # every ETF (including VOO) gets market_caps=0 and is excluded from
        # "the market" the BL prior is built from.
        return t.info.get("totalAssets")
    except Exception:
        return None

mcaps = pd.Series(
    {t: market_cap(t) for t in covariance_matrix.columns},
    dtype="float64",
)
print(mcaps[mcaps.isna()])  # still-missing after the AUM fallback — true zero-cap

delta = market_implied_risk_aversion(
    spy.set_index("price_date")["close_price"],
    risk_free_rate=rf_rate,
)


hist = mean_historical_return(close_df)
etf_tickers = holdings.loc[
    holdings["security_type"].str.lower() == "etf", "ticker"
]
viewdict = hist.reindex(etf_tickers).dropna().to_dict()
assert viewdict, "need at least one ETF view"


bl = BlackLittermanModel(
    cov_matrix=covariance_matrix,
    pi="market",
    market_caps=mcaps.fillna(0),
    risk_aversion=delta,
    absolute_views=viewdict,
    tau=0.05,
    omega="idzorek",
    # Low confidence: these views are raw trailing means (noisy, backward-
    # looking), not real theses — Idzorek's method pulls the posterior back
    # toward the market prior in proportion to (1 - confidence).
    view_confidences=[0.3] * len(viewdict),
)

ret_bl = bl.bl_returns()
cov_bl = bl.bl_cov()

# Attribution: how much of each posterior return came from the market prior
# (pi, cap-weighted) vs. the spillover of view confidence through the
# covariance matrix — the two things that changed vs. the old unconstrained
# script (mcap ETF/AUM fallback and idzorek/0.3 confidence, respectively).
pi_series = pd.Series(np.asarray(bl.pi).flatten(), index=ret_bl.index)
mkt_weight = (mcaps.fillna(0) / mcaps.fillna(0).sum()).reindex(ret_bl.index)
print("\nBL attribution (market weight, prior pi, posterior return, view pull = posterior - pi):")
print(
    pd.DataFrame({
        "mkt_weight": mkt_weight,
        "prior_pi": pi_series,
        "posterior_ret_bl": ret_bl,
        "view_pull": ret_bl - pi_series,
    })
    .sort_values("posterior_ret_bl", ascending=False)
    .to_string(float_format=lambda x: f"{x:.2%}")
)

# weight_bounds caps any single name to fight corner solutions from noisy BL
# posterior returns — defined here (rather than next to the EfficientFrontier
# calls below) so the sector feasibility check below can reuse the same value.
MAX_POSITION = 0.10

# ---- Sector diversification: floor + cap per sector. ----
# Placeholder values for now — SECTOR_FLOOR/SECTOR_CAP are applied uniformly
# to every sector below. Later these become per-sector, user-adjustable
# (sliders), so sector_lower/sector_upper are already built as one value per
# sector rather than a single global constant, ready to take per-sector
# input instead of a broadcast scalar.
SECTOR_FLOOR = 0.02
SECTOR_CAP = 0.40
COMMODITIES_BUCKET = "commodities"


def _norm_sector_name(name) -> str:
    return str(name).lower().replace("_", "").replace(" ", "").replace("-", "")


def _normalize_sector_weightings(raw) -> dict:
    """funds_data.sector_weightings has varied shape across yfinance versions
    (dict, list of single-key dicts, Series) — handle all of them. If this
    keeps coming back empty for an ETF that should have sector data, print
    the raw value at the call site to see the actual shape returned."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, (list, tuple)):
        items = [kv for item in raw if isinstance(item, dict) for kv in item.items()]
    else:
        try:
            items = raw.squeeze().to_dict().items()
        except Exception:
            return {}
    return {_norm_sector_name(k): float(v) for k, v in items}


def sector_exposure(ticker: str, is_etf: bool) -> dict:
    """{sector_name: fraction of dollar value}, summing to ~1. ETFs with no
    equity sector exposure (GLD, SLV, ...) fall into a single Commodities
    bucket rather than being exempt, since that bucket gets its own
    floor/cap (and later, slider) too."""
    yahoo = ticker.replace(".", "-")
    try:
        t = yf.Ticker(yahoo)
        if is_etf:
            weightings = _normalize_sector_weightings(t.funds_data.sector_weightings)
            return weightings if weightings else {COMMODITIES_BUCKET: 1.0}
        sector = t.info.get("sector")
        return {_norm_sector_name(sector): 1.0} if sector else {}
    except Exception:
        return {}


security_type_by_ticker = holdings.set_index("ticker")["security_type"].to_dict()
sector_rows = {
    tkr: sector_exposure(tkr, security_type_by_ticker.get(tkr, "").lower() == "etf")
    for tkr in ret_bl.index
}
unclassified = [tkr for tkr, row in sector_rows.items() if not row]
print(f"\nUnclassified (no floor/cap applied — fetch failed): {unclassified}")

sector_names = sorted({s for row in sector_rows.values() for s in row})
sector_matrix = pd.DataFrame(0.0, index=ret_bl.index, columns=sector_names)
for tkr, row in sector_rows.items():
    for s, frac in row.items():
        sector_matrix.loc[tkr, s] = frac

sector_lower = pd.Series(SECTOR_FLOOR, index=sector_names)
sector_upper = pd.Series(SECTOR_CAP, index=sector_names)
print("\nSector floors/caps (placeholder — will be per-sector slider input):")
print(
    pd.DataFrame({"lower": sector_lower, "upper": sector_upper})
    .to_string(float_format=lambda x: f"{x:.1%}")
)

# Feasibility check: max exposure to each sector if every ticker holding any
# of it were pushed to MAX_POSITION (0.10), ignoring the sum-to-1 budget and
# every other sector's floor. This is a necessary-not-sufficient upper bound
# — if it's already below the floor, the floor is provably unreachable and
# the real solve will be infeasible no matter what the optimizer picks.
max_achievable = (sector_matrix * MAX_POSITION).sum(axis=0)
print(f"\nMax achievable exposure per sector ({MAX_POSITION:.0%} per-asset cap, in isolation):")
print(
    pd.DataFrame({"max_achievable": max_achievable, "floor": sector_lower})
    .to_string(float_format=lambda x: f"{x:.1%}")
)

# Auto-clip any floor that exceeds what's actually reachable given the
# per-asset cap, rather than handing cvxpy an unsatisfiable constraint (as
# happened with basicmaterials: 1.7% max vs. a 2% floor). SAFETY_MARGIN
# leaves slack so the solver isn't pinned against the exact boundary. This
# matters even more once floors are slider-driven — a user can pick any
# value, and the solve should degrade gracefully instead of crashing.
SAFETY_MARGIN = 0.95
clip_target = max_achievable * SAFETY_MARGIN
needs_clip = sector_lower > clip_target
if needs_clip.any():
    print(
        f"\nClipping floor to achievable capacity for: "
        f"{dict(zip(sector_lower[needs_clip].index, clip_target[needs_clip].round(4)))}"
    )
    sector_lower = sector_lower.where(~needs_clip, clip_target).clip(lower=0)


def add_sector_bands(ef):
    exposure = sector_matrix.reindex(ef.tickers).fillna(0).values  # tickers x sectors
    for j in range(len(sector_names)):
        col, lo, hi = exposure[:, j], sector_lower.iloc[j], sector_upper.iloc[j]
        ef.add_constraint(lambda w, col=col, lo=lo: col @ w >= lo)
        ef.add_constraint(lambda w, col=col, hi=hi: col @ w <= hi)
    return ef


# L2 regularization: penalizes concentration (Σwᵢ², i.e. HHI) directly in the
# objective, on top of the per-asset cap and sector floors above — neither of
# those bounds how much of the portfolio sits in just the top few positions.
# gamma is a return/Sharpe-vs-concentration trade-off price (same scale as
# expected returns here, ~0.02-0.68), not a bounded 0-1 parameter — starting
# at pypfopt's own default; tune from here once you see the resulting
# effective N (1/Σwᵢ²) and Sharpe.
CONCENTRATION_GAMMA = 1


def add_concentration_penalty(ef):
    ef.add_objective(objective_functions.L2_reg, gamma=CONCENTRATION_GAMMA)
    return ef


# Separate EF instances: pypfopt cannot switch objectives on the same object.
# max_quadratic_utility takes risk_aversion (δ), not the T-bill rate.
# NOTE: concentration penalty is intentionally NOT applied here. pypfopt's
# max_sharpe() uses an internal auxiliary-variable substitution (Cornuejols-
# Tütüncü) to linearize the fractional Sharpe objective, and user-added
# objectives (L2_reg included) don't get rescaled by that substitution —
# pypfopt itself warns this combination "may not work as intended." Confirmed
# here: it produced a non-tangent CAL and a cloud escaping the frontier.
# max_quadratic_utility (below) has no such transformation, so it's safe there.
ef_sharpe = EfficientFrontier(ret_bl, cov_bl, weight_bounds=(0, MAX_POSITION))
add_sector_bands(ef_sharpe)
suggested_weights_sharpe = ef_sharpe.max_sharpe(risk_free_rate=rf_rate)
ret_s, vol_s, sharpe_s = ef_sharpe.portfolio_performance(risk_free_rate=rf_rate)

ef_quad = EfficientFrontier(ret_bl, cov_bl, weight_bounds=(0, MAX_POSITION))
add_sector_bands(ef_quad)
add_concentration_penalty(ef_quad)
suggested_weights_quadratic = ef_quad.max_quadratic_utility(risk_aversion=delta)
ret_q, vol_q, sharpe_q = ef_quad.portfolio_performance(risk_free_rate=rf_rate)

w_sharpe = pd.Series(ef_sharpe.clean_weights())
w_quad = pd.Series(ef_quad.clean_weights())

effective_n_sharpe = 1 / (w_sharpe**2).sum()
effective_n_quad = 1 / (w_quad**2).sum()
print(
    f"\nConcentration (gamma={CONCENTRATION_GAMMA}): "
    f"effective N sharpe={effective_n_sharpe:.1f}, quad={effective_n_quad:.1f}, "
    f"nonzero sharpe={int((w_sharpe > 1e-4).sum())}, quad={int((w_quad > 1e-4).sum())}"
)

plotting.plot_covariance(covariance_matrix)

mu = ret_bl.values
S = cov_bl.loc[ret_bl.index, ret_bl.index].values
n_assets = len(mu)


def sample_capped_portfolios(alpha, n_draws, cap=MAX_POSITION):
    """Dirichlet draws, rejecting any that violate the same per-asset cap the
    optimizer uses — keeps the cloud comparable to the frontier line. Highly
    concentrated (low-alpha) draws mostly violate the cap and get rejected,
    so alpha is kept moderate here rather than corner-seeking."""
    w = np.random.dirichlet(alpha * np.ones(n_assets), n_draws)
    return w[w.max(axis=1) <= cap]


w_rand = np.vstack([
    sample_capped_portfolios(1.0, 40000),
    sample_capped_portfolios(3.0, 40000),
])
rand_rets = w_rand @ mu
rand_vols = np.sqrt(np.einsum("ij,jk,ik->i", w_rand, S, w_rand))
rand_sharpe = (rand_rets - rf_rate) / rand_vols

w_cur = weights.reindex(ret_bl.index).fillna(0).to_numpy()
w_cur = w_cur / w_cur.sum()
cur_ret = float(w_cur @ mu)
cur_vol = float(np.sqrt(w_cur @ S @ w_cur))

# Same Ledoit-Wolf estimator as the optimizer, with SPY in the matrix so
# β = (w' Σ e_spy) / Σ_spy,spy matches the risk model (still vs SPY, like δ).
px_beta = close_df[ret_bl.index].copy()
px_beta["SPY"] = spy.set_index("price_date")["close_price"].reindex(px_beta.index)
px_beta = px_beta.dropna()
cov_with_spy = risk_models.CovarianceShrinkage(px_beta).ledoit_wolf()
var_spy = float(cov_with_spy.loc["SPY", "SPY"])
cov_to_spy = cov_with_spy.reindex(index=ret_bl.index)["SPY"]


def portfolio_beta(w) -> float:
    w = pd.Series(np.asarray(w), index=ret_bl.index)
    return float(cov_to_spy.dot(w) / var_spy)


beta_s = portfolio_beta(ef_sharpe.weights)
beta_q = portfolio_beta(ef_quad.weights)


def metrics_box(ret, vol, beta, sharpe) -> str:
    return (
        f"E(R)    {ret:6.1%}\n"
        f"Std     {vol:6.1%}\n"
        f"Beta    {beta:6.2f}\n"
        f"Sharpe  {sharpe:6.2f}"
    )

## calculate the efficient frontier
# No concentration penalty here either — this line needs to match what
# max_sharpe() (ef_sharpe) actually solves for the CAL to be tangent. As a
# side effect, the Max Quadratic Utility marker (which DOES carry the
# penalty) will now sit visibly inside/below this raw frontier — that's
# real and expected: it's the return cost of the diversification preference,
# not a bug.
fig, ax_tmp = plt.subplots()
ef_plot = EfficientFrontier(ret_bl, cov_bl, weight_bounds=(0, MAX_POSITION))
add_sector_bands(ef_plot)
plotting.plot_efficient_frontier(ef_plot, ax=ax_tmp, show_assets=False)
front_vol = np.asarray(ax_tmp.get_lines()[0].get_xdata())
front_ret = np.asarray(ax_tmp.get_lines()[0].get_ydata())
plt.close(fig)
i_min = int(np.argmin(front_vol))
vol_min, ret_min = float(front_vol[i_min]), float(front_ret[i_min])

## Dynamic axis scaling: zoom to where the data actually is. x stays anchored
# at 0 (the CAL and risk-free point need that origin to be meaningful), but y
# is free to crop the dead space between 0 and wherever the real content
# starts — the risk-free dot already renders with clip_on=False, so raising
# y_min above rf_rate doesn't hide it, just pushes it toward the bottom edge.
# Key reference points (chosen/min-vol/current) get an explicit floor/ceiling
# rather than being one vote among ~50k cloud points in a percentile — with
# that many points, a handful of individually-important markers barely move
# a percentile cutoff at all.
asset_vol = np.sqrt(np.diag(S))
ZOOM_PCTL = 99.5
AXIS_PAD_X = 0.06
AXIS_PAD_Y = 0.30  # looser than X — a tight y-crop hides the (0, rf) CAL
# anchor below the frame, making a genuinely-tangent line look arbitrary.
key_vols = np.array([vol_s, vol_q, vol_min, cur_vol])
key_rets = np.array([ret_s, ret_q, ret_min, cur_ret])
bulk_vols = np.concatenate([front_vol, rand_vols, asset_vol])
bulk_rets = np.concatenate([front_ret, rand_rets, mu])

x_hi = max(np.percentile(bulk_vols, ZOOM_PCTL), key_vols.max())
y_hi = max(np.percentile(bulk_rets, ZOOM_PCTL), key_rets.max())
y_lo = min(np.percentile(bulk_rets, 100 - ZOOM_PCTL), key_rets.min())

y_range = y_hi - y_lo
x_max = x_hi * (1 + AXIS_PAD_X)
y_max = y_hi + y_range * AXIS_PAD_Y
y_min = y_lo - y_range * AXIS_PAD_Y
cal_vol = np.array([0.0, x_max])
cal_ret = rf_rate + (ret_s - rf_rate) / vol_s * cal_vol

# draw the panel
def draw_panel(ax, title, h_vol, h_ret, h_color, h_label, box):
    ax.plot(front_vol, front_ret, color="black", linestyle="-.", label="Efficient frontier")
    ax.scatter(asset_vol, mu, s=30, color="k", zorder=3, label="Assets")
    for ticker, vol, ret in zip(ret_bl.index, asset_vol, mu):
        ax.annotate(ticker, (vol, ret), textcoords="offset points", xytext=(4, 4), fontsize=7)
    ax.scatter(
        rand_vols, rand_rets, c=rand_sharpe, cmap="viridis_r", s=1, alpha=0.35, zorder=0,
    )
    ax.plot(cal_vol, cal_ret, color="blue", linestyle="-", label="CAL")
    ax.scatter(
        [0], [rf_rate], marker="o", s=50, c="gray", zorder=5, clip_on=False, label="Risk-free rate",
    )
    ax.scatter(vol_min, ret_min, marker="^", s=90, c="green", zorder=5, label="Minimum volatility")
    ax.scatter(cur_vol, cur_ret, marker="^", s=90, c="purple", zorder=5, label="Current portfolio")
    ax.scatter(h_vol, h_ret, marker="^", s=110, c=h_color, zorder=6, label=h_label)
    ax.set_title(title)
    ax.set_xlabel("Annualized Volatility")
    ax.set_xlim(0, x_max)
    ax.set_ylim(y_min, y_max)
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1))
    ax.text(
        0.02, 0.98, box, transform=ax.transAxes, va="top", ha="left",
        family="monospace", fontsize=9,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.9),
    )


fig, (ax_s, ax_q) = plt.subplots(1, 2, figsize=(17.5, 6.5), sharey=True)
draw_panel(
    ax_s, "Max Sharpe", vol_s, ret_s, "red", "Maximum Sharpe ratio",
    metrics_box(ret_s, vol_s, beta_s, sharpe_s),

)
draw_panel(
    ax_q, f"Max quadratic utility (δ={delta:.2f})", vol_q, ret_q, "orange",
    "Maximum quadratic utility",
    metrics_box(ret_q, vol_q, beta_q, sharpe_q),

)
ax_s.set_ylabel("Annualized Returns")
# Legends placed fully outside each panel (left panel's legend in the left
# margin, right panel's in the right margin) rather than a fixed in-plot
# corner — an in-plot corner that's empty today can (and did) end up on top
# of real data once the axis zoom changes. tight_layout() must run first;
# subplots_adjust() afterward reserves the margin space the external
# legends need, which tight_layout doesn't know to leave room for.
fig.tight_layout()
ax_s.legend(loc="center right", bbox_to_anchor=(-0.02, 0.5), fontsize=8)
ax_q.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
fig.subplots_adjust(left=0.12, right=0.88, wspace=0.35)
plt.show()

investable = values.reindex(weights.index).sum()

export_df = pd.DataFrame({
    "expected_return": ret_bl,
    "original_weight": weights,
    "original_dollar": values.reindex(weights.index),
    "sharpe_weight": w_sharpe,
    "max_sharpe_sharpe": sharpe_s,
    "quad_sharpe": sharpe_q,
    "sharpe_dollar": w_sharpe * investable,
    "quad_weight": w_quad,
    "quad_dollar": w_quad * investable,
}).fillna(0)

out_path = Path.home() / "Downloads" / "portfolio_optimization.csv"
export_df.rename_axis("ticker").reset_index().to_csv(out_path, index=False)


