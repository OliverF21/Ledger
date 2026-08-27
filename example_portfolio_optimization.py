import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import yfinance as yf
import datetime as dt
from pathlib import Path

## PyPortfolioOpt
import pypfopt as ppo
from pypfopt import risk_models, BlackLittermanModel, EfficientFrontier
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
conn = sqlite3.connect('/Users/oliver/Library/Application Support/Ledger/ledger.db')

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
        return yf.Ticker(yahoo).fast_info.get("marketCap")
    except Exception:
        return None

mcaps = pd.Series(
    {t: market_cap(t) for t in covariance_matrix.columns},
    dtype="float64",
)
print(mcaps[mcaps.isna()])  # ETFs usually land here; prior treats them as 0 cap

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
)

ret_bl = bl.bl_returns()
cov_bl = bl.bl_cov()

# Separate EF instances: pypfopt cannot switch objectives on the same object.
# max_quadratic_utility takes risk_aversion (δ), not the T-bill rate.
ef_sharpe = EfficientFrontier(ret_bl, cov_bl)
suggested_weights_sharpe = ef_sharpe.max_sharpe(risk_free_rate=rf_rate)
ret_s, vol_s, sharpe_s = ef_sharpe.portfolio_performance(risk_free_rate=rf_rate)

ef_quad = EfficientFrontier(ret_bl, cov_bl)
suggested_weights_quadratic = ef_quad.max_quadratic_utility(risk_aversion=delta)
ret_q, vol_q, sharpe_q = ef_quad.portfolio_performance(risk_free_rate=rf_rate)

w_sharpe = pd.Series(ef_sharpe.clean_weights())
w_quad = pd.Series(ef_quad.clean_weights())

plotting.plot_covariance(covariance_matrix)

mu = ret_bl.values
S = cov_bl.loc[ret_bl.index, ret_bl.index].values
n_assets = len(mu)
w_rand = np.vstack([
    np.random.dirichlet(np.ones(n_assets), 6000),
    np.random.dirichlet(0.2 * np.ones(n_assets), 6000),
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


fig, ax_tmp = plt.subplots()
ef_plot = EfficientFrontier(ret_bl, cov_bl)
plotting.plot_efficient_frontier(ef_plot, ax=ax_tmp, show_assets=False)
front_vol = np.asarray(ax_tmp.get_lines()[0].get_xdata())
front_ret = np.asarray(ax_tmp.get_lines()[0].get_ydata())
plt.close(fig)
i_min = int(np.argmin(front_vol))
vol_min, ret_min = float(front_vol[i_min]), float(front_ret[i_min])

asset_vol = np.sqrt(np.diag(S))
x_max = np.quantile(rand_vols, 0.995) * 1.05
y_max = max(rand_rets.max(), ret_s, ret_q) * 1.05
cal_vol = np.array([0.0, x_max])
cal_ret = rf_rate + (ret_s - rf_rate) / vol_s * cal_vol


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
    ax.set_xlabel("Annualised Volatility")
    ax.set_xlim(0, x_max)
    ax.set_ylim(0, y_max)
    ax.text(
        0.02, 0.98, box, transform=ax.transAxes, va="top", ha="left",
        family="monospace", fontsize=9,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.9),
    )


fig, (ax_s, ax_q) = plt.subplots(1, 2, figsize=(14.5, 6.5), sharey=True)
draw_panel(
    ax_s, "Max Sharpe", vol_s, ret_s, "red", "Maximum Sharpe ratio",
    metrics_box(ret_s, vol_s, beta_s, sharpe_s),

)
draw_panel(
    ax_q, f"Max quadratic utility (δ={delta:.2f})", vol_q, ret_q, "orange",
    "Maximum quadratic utility",
    metrics_box(ret_q, vol_q, beta_q, sharpe_q),

)
ax_s.set_ylabel("Annualised Returns")
fig.tight_layout()
ax_s.legend(loc="lower right", fontsize=8)
ax_q.legend(loc="lower right", fontsize=8)
plt.show()

investable = values.reindex(weights.index).sum()

export_df = pd.DataFrame({
    "expected_return": ret_bl,
    "original_weight": weights,
    "original_dollar": values.reindex(weights.index),
    "sharpe_weight": w_sharpe,
    "sharpe_dollar": w_sharpe * investable,
    "quad_weight": w_quad,
    "quad_dollar": w_quad * investable,
}).fillna(0)

out_path = Path.home() / "Downloads" / "portfolio_optimization.csv"
export_df.rename_axis("ticker").reset_index().to_csv(out_path, index=False)


