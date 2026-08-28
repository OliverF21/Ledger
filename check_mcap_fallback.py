"""
Diagnostic script: checks why ETFs (VOO, QQQ, GLD, ...) are landing at
market_cap=0 in example_portfolio_optimization.py despite the AUM fallback
added to market_cap(). Isolates the yfinance fetch from the rest of the BL
pipeline so failures show up directly instead of being silently swallowed
and turned into NaN -> 0.

Run standalone: python check_mcap_fallback.py
"""
import sqlite3

import pandas as pd
import yfinance as yf

conn = sqlite3.connect('/Users/oliver/Library/Application Support/Ledger/ledger.db')
holdings = pd.read_sql_query("""
    SELECT s.ticker_symbol AS ticker, s.type AS security_type
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
conn.close()

etf_tickers = sorted(holdings.loc[holdings["security_type"].str.lower() == "etf", "ticker"])
all_tickers = sorted(holdings["ticker"])
print(f"{len(all_tickers)} tickers total, {len(etf_tickers)} flagged as ETF: {etf_tickers}")


# ---- Test 1 + 2: isolate the fetch per ETF, log exceptions instead of swallowing them ----
def market_cap(ticker: str, verbose: bool = False):
    yahoo = ticker.replace(".", "-")
    try:
        t = yf.Ticker(yahoo)
        cap = t.fast_info.get("marketCap")
        if verbose:
            print(f"  {ticker}: fast_info.marketCap = {cap!r}")
        if cap:
            return cap
        total_assets = t.info.get("totalAssets")
        if verbose:
            print(f"  {ticker}: info.totalAssets   = {total_assets!r}")
            if total_assets is None:
                # show what IS in .info so we can spot the right key name
                candidates = [k for k in t.info.keys() if "asset" in k.lower() or "aum" in k.lower()]
                print(f"  {ticker}: info keys matching 'asset'/'aum': {candidates or 'none found'}")
        return total_assets
    except Exception as e:
        print(f"  {ticker}: EXCEPTION — {e!r}")
        return None


print("\n=== Per-ETF fetch detail ===")
for ticker in etf_tickers:
    print(f"{ticker}:")
    market_cap(ticker, verbose=True)

# ---- Test 3: full mcaps series, ETFs sorted, so we can see nonzero-but-wrong-scale values too ----
print("\n=== mcaps for all tickers (ETFs only, sorted) ===")
mcaps = pd.Series({t: market_cap(t) for t in all_tickers}, dtype="float64")
print(mcaps.loc[etf_tickers].sort_values(ascending=False))

still_missing = mcaps[mcaps.isna()]
print(f"\nStill NaN after fallback ({len(still_missing)}): {list(still_missing.index)}")

# ---- Test 4: implied market weight — is VOO's AUM actually material vs individual stock caps? ----
w_mkt = mcaps.fillna(0) / mcaps.fillna(0).sum()
print("\n=== Implied market weight (top 10) ===")
print(w_mkt.sort_values(ascending=False).head(10))
