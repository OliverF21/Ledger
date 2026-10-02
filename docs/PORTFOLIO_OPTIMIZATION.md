# Portfolio optimization

Technical specification of the allocation optimizer as implemented. It describes
the estimator, the objectives, the constraints, and the annualization
conventions the code actually uses. It is not a derivation of a new method,
and it is not investment advice. Suggested weights are the output of a
constrained numerical solve on a model of past prices.

The engine lives in:

| Piece | Module |
| --- | --- |
| Orchestration, objectives, gating | `backend/app/services/optimization_service.py` |
| Covariance shrinkage, Black–Litterman, penalty scales | `backend/app/services/portfolio_math_service.py` |
| Frontier sweep and random cloud | `backend/app/services/efficient_frontier_service.py` |
| Sector and ticker bounds | `backend/app/services/sector_constraint_service.py` |
| Prices, weights, reported return / volatility / Sharpe | `backend/app/services/price_matrix_service.py` |
| Risk-free rate | `backend/app/risk_free_rate.py` |
| HTTP | `GET /api/investments/risk/optimize`, `backend/app/routes/portfolio_risk.py` |
| Preferences and constraint CRUD | `backend/app/routes/optimization_settings.py` |
| MCP | `portfolio_optimization` in `backend/mcp_server/server.py` |

There is one optimizer. `User.optimization_advanced_enabled` does not select
a weaker fallback. Off means the function returns before it reads prices.
On means the full pipeline below. Portfolio-level Sharpe, VaR, beta, and
drawdown on the Investments tab are a separate calculation in
`risk_service.py` and are not inputs to this solve.

---

## 1. What is being optimized

The decision variable is a vector of portfolio weights $w \in \mathbb{R}^n$
on the tickers that survive the data screens in §3. Each $w_i$ is a fraction
of the market value of that included book. Cash, unpriced symbols, and
tickers dropped for short history are outside $w$. They are not a residual
bucket the solver can allocate to.

The solve is a rebalance of today's included market value. Suggested dollars
are $w_i$ times that total. They are not a forecast of future wealth.

Two constrained problems are solved independently from the same estimates
and the same bounds:

1. **Max Sharpe.** Maximize the annualized Sharpe ratio of $w$, minus a
   concentration penalty.
2. **Max quadratic utility.** Maximize mean–variance utility at the
   market-implied risk aversion, minus its own concentration penalty.

A third family of solves traces the constrained efficient frontier: maximum
annualized mean return at each target volatility. A Dirichlet sample of
long-only portfolios is drawn only as a chart backdrop. It is not optimized
and it ignores the user's caps.

The top-level fields `tickers`, `suggested_expected_return_pct`,
`suggested_volatility_pct`, and `suggested_sharpe` are the **max-Sharpe**
result. `objectives` contains both solves. `sector_breakdown.weight_pct` is
also the max-Sharpe book's sector exposure.

---

## 2. Notation and units

Everything inside the estimator is in **decimal daily simple returns** until
an objective or a reported statistic annualizes it. Percent fields in the
API are those decimals times 100.

| Symbol | Meaning | Unit in the solver |
| --- | --- | --- |
| $r_{t,i}$ | Simple return of ticker $i$ between successive valid closes | decimal per observation |
| $\mu$ | Sample mean of $r_{\cdot,i}$, then the Black–Litterman posterior mean $\mu_{BL}$ | decimal per observation |
| $\Sigma$ | Shrunk covariance of $r$, then the posterior covariance $\Sigma_{BL}$ | variance per observation |
| $w$ | Weights | fractions, sum to 1 |
| $r_{f}$ | 3-month Treasury yield | decimal per year |
| $\delta$ | Risk aversion | 1 / (annual variance) |
| $\tau$ | Prior uncertainty scalar | ${0.05}$, dimensionless |
| $c$ | View confidence | ${0.3}$ for every ETF view |

Annualization assumes each retained observation is one trading session and
that sessions are i.i.d.:

$$
\mu_{\mathrm{ann}}(w) = 252\, w^\top \mu
$$

$$
\sigma_{\mathrm{ann}}(w) = \sqrt{252}\, \sqrt{w^\top \Sigma w}
$$

$$
\mathrm{Var}_{\mathrm{ann}}(w) = 252\, w^\top \Sigma w
$$

Mean and variance scale with time. Volatility scales with $\sqrt{\text{time}}$.
The factor is ${252}$, not ${365}$. `MarketPrice` rows for equities and ETFs
are trading days. Using calendar days would inflate return by about
${365/252}$ and volatility by about $\sqrt{365/252}$. The constant is
`TRADING_DAYS_PER_YEAR` in `portfolio_math_service.py`. Risk metrics that
run on a calendar-day balance snapshot correctly use ${365}$; that constant
must not be reused here.

Returns are arithmetic, not compounded. The engine does **not** report
$(1+\mu)^{252}-1$, and it does not use log returns.

---

## 3. Universe and price panel

`build_optimization_suggestion` runs only when advanced mode is on.

**Lookback.** Default ${1095}$ calendar days (three years). The argument is
clamped to $[90, 1825]$. The Investments page always requests ${1095}$.
The window is `[today − lookback, today]` on `MarketPrice.close_price`.

**Accounts.** Investment accounts for user 1, excluding Plaid items that
the crypto sync owns. Holdings are joined to `Security.ticker_symbol`.

**Screens, in order.**

1. At least two held tickers. Otherwise `insufficient_data`.
2. Drop tickers with no `MarketPrice` row in the window (`priceable_tickers`).
   Still need two.
3. Build the price matrix on the **union** of dates, not the intersection.
   A name that listed recently does not truncate every other history.
   Missing closes are NaN.
4. Need at least `MIN_LOOKBACK_ROWS` (${30}$) dates in that union.
5. Drop any ticker with fewer than ${30}$ finite closes. Each drop is a
   `clip_log` entry. Still need two names after the drop.

**Current weights.** For each included ticker, sum
`scaled_holding_market_value` across holdings. If the account's gross
holdings exceed its net balance (margin), each holding is scaled by
$\text{net} / \text{gross}$. Weights are those dollars divided by the
included total. A non-positive total yields zeros.

**Simple returns.** For each ticker, walk closes in date order and skip
non-finite or zero prices. The return on a new valid close $p$ after the
previous valid close $p_{\text{prev}}$ is

$$
r = \frac{p}{p_{\text{prev}}} - 1
$$

and it is written on the row of the gap immediately before $p$. Interior
gaps stay NaN. That avoids turning a missing equity close (a weekend row
that exists only because another asset traded) into a NaN that also deletes
the next real close-to-close return.

Consequence for mixed calendars: an equity Friday-to-Monday move is one
observation, while a crypto name on the same union may contribute a return
on Saturday and Sunday. Pairwise covariance uses only dates where both
names are observed, but every observation is still annualized as if it were
one of ${252}$ sessions. A book of listed equities and ETFs does not have
this mismatch. A book mixed with weekend-priced assets does.

---

## 4. Covariance: Ledoit–Wolf shrinkage

Implemented by `ledoit_wolf_shrinkage`. This is the constant-correlation
shrinkage estimator of Ledoit and Wolf, in the simplified single-parameter
form used for portfolio construction. It is **not** the full finite-sample
bias-corrected estimator from Ledoit & Wolf (2003), *Improved estimation of
the covariance matrix of stock returns*.

### 4.1 Pairwise sample covariance

Let $x_{t,i}$ be the return of asset $i$ on date $t$, and let the pair
$(i,j)$ be observed on the set $T_{ij}$ of dates where both are finite,
with $t_{ij} = \lvert T_{ij}\rvert$. Means are the pair's own means, not a global mean:

$$
\bar x_i^{(ij)} = \frac{1}{t_{ij}} \sum_{t \in T_{ij}} x_{t,i}
$$

$$
S_{ij} = \frac{1}{t_{ij}} \sum_{t \in T_{ij}}
  \bigl(x_{t,i} - \bar x_i^{(ij)}\bigr)
  \bigl(x_{t,j} - \bar x_j^{(ij)}\bigr)
$$

The divisor is $t_{ij}$, the maximum-likelihood convention, not $t_{ij}-1$.
If $t_{ij} = 0$, the entry stays ${0}$. On a fully dense panel this is the
usual $X^\top X / T$ after demeaning.

### 4.2 Constant-correlation target

Let $v_i = S_{ii}$ and $\sigma_i = \sqrt{v_i}$. Correlations use a floor
so a constant or halted series cannot produce ${0/0}$:

$$
\sigma_i^{\mathrm{safe}} = \max(\sigma_i,\, 10^{-12})
$$

$$
R_{ij} = \frac{S_{ij}}{\sigma_i^{\mathrm{safe}}\, \sigma_j^{\mathrm{safe}}}
$$

The grand correlation (diagonal of ones removed) is

$$
\bar\rho = \frac{\sum_{i,j} R_{ij} - n}{n(n-1)} \quad (n > 1),\quad \text{else } 0.
$$

The target $F$ is

$$
F_{ij} = \bar\rho\, \sigma_i \sigma_j \quad (i \neq j), \qquad F_{ii} = v_i.
$$

The outer product uses the **unfloored** $\sigma$. A true zero-variance
asset therefore has a zero row and column in $F$ except its own zero
diagonal. $\bar\rho$ is not projected into $[-1,1]$. With unequal
pairwise windows it can fall slightly outside that interval. That value is
still what the target uses.

### 4.3 Shrinkage intensity

For demeaned pair observations $y_{t,i}, y_{t,j}$,

$$
\hat\pi_{ij}
  = \frac{1}{t_{ij}}\sum_{t \in T_{ij}} y_{t,i}^2 y_{t,j}^2
    \;-\; S_{ij}^2
  = \frac{1}{t_{ij}}\sum_{t \in T_{ij}} \bigl(y_{t,i} y_{t,j} - S_{ij}\bigr)^2.
$$

$$
\hat\pi = \sum_{i,j} \hat\pi_{ij}, \qquad
\hat\rho = \lVert F - S \rVert_F^2, \qquad
\hat\kappa = \hat\pi / \hat\rho \text{ if } \hat\rho > 0 \text{ else } 0.
$$

$$
\hat\delta^\star = \max\bigl(0,\, \min(1,\, \hat\kappa / T_{\mathrm{eff}})\bigr).
$$

$T_{\mathrm{eff}}$ is the **smallest positive** $t_{ij}$. The classical
formula assumes one shared $T$. Using the shortest overlap can only
increase shrinkage, which is the conservative direction when some pairs are
short. On a dense panel $T_{\mathrm{eff}} = T$.

The shrunk matrix, still at the daily horizon, is

$$
\Sigma_{\mathrm{daily}}
  = \hat\delta^\star F + (1-\hat\delta^\star)\, S.
$$

The function then multiplies by ${252}$ and returns an annualized matrix,
matching the usual `CovarianceShrinkage.ledoit_wolf()` scaling. The
optimizer **divides by ${252}$ immediately**, so every later step sees
$\Sigma_{\mathrm{daily}}$. Shrinkage itself is computed before that
rescaling. Intensity is invariant to a common scale factor, but the code
estimates it on the daily matrix, which is the intended one.

### 4.4 Diagonal floor before any inversion

A zero-variance asset has an entire zero row and column, so $\tau\Sigma$
is singular and `numpy.linalg.inv` fails. Before the Black–Litterman calls
the diagonal is replaced by

$$
\Sigma_{ii} \leftarrow \max(\Sigma_{ii},\, 10^{-10}).
$$

Off-diagonals are left alone. Raising a diagonal by a positive amount adds
a positive semidefinite rank-one update, so a matrix that was positive
semidefinite stays positive semidefinite. ${10^{-10}}$ is far below any
real daily variance. The floored matrix is the $\Sigma$ used for the
prior, the views, the posterior, both objectives, and the frontier.

---

## 5. Risk-free rate and risk aversion

### 5.1 Risk-free rate

$r_f$ is the latest non-missing FRED `DGS3MO` observation (3-month Treasury
yield, percent per year), cached in `app_config`. The nightly job refreshes
it. If nothing is cached, the fallback is ${5.0}$ percent.

The yield is used as a flat annual decimal $r_f = \text{DGS3MO}/100$.
There is no conversion from a discount bill to a continuously compounded
rate, and no daily $r_f/252$ subtracted inside the covariance. Subtraction
happens after the portfolio mean has been annualized (§8).

### 5.2 Market-implied $\delta$

The benchmark is SPY over the same calendar window, loaded as its own price
column. Fewer than two SPY closes raises `ValueError` (the HTTP layer turns
that into a 500). SPY does not need to be held.

Daily SPY returns are `Series.pct_change()` on that column. Because the
column contains only SPY's own dates, consecutive rows are consecutive
stored closes. Variance is **pandas sample variance** (`ddof = 1`), which
differs from the Ledoit–Wolf divisor $T$:

$$
\mu_{\mathrm{SPY}} = \overline{r}_{\mathrm{SPY}} \cdot 252
$$

$$
\sigma^2_{\mathrm{SPY}} = \mathrm{Var}_{\mathrm{sample}}(r_{\mathrm{SPY}}) \cdot 252
$$

$$
\delta = \frac{\mu_{\mathrm{SPY}} - r_f}{\sigma^2_{\mathrm{SPY}}}.
$$

This is the standard reverse-optimization identity: $\delta$ is the risk
aversion of a mean–variance investor whose unconstrained optimum is the
market portfolio. The same number is used twice: to build the equilibrium
prior, and as the curvature of quadratic utility.

### 5.3 Unusable $\delta$

If $\delta$ is non-finite or $\delta < 0.1$, it is replaced by ${2.5}$
and a `clip_log` reason is recorded.

A non-positive $\delta$ is not a small investor. It happens whenever SPY's
trailing annualized mean sits at or below $r_f$ (a lookback that covers a
drawdown). Two formulas then change sign:

- Utility's ${-\tfrac12 \delta\, w^\top\Sigma w}$ starts **rewarding**
  variance.
- The prior $\pi = \delta \Sigma w_{\mathrm{mkt}}$ says every asset's
  equilibrium premium is negative.

$\delta < 0.1$ is the near-zero case: the sign is right, but utility
collapses toward pure return maximization and $\pi$ collapses toward ${0}$.
Getting under ${0.1}$ requires roughly a ${0.2\%}$ annual excess return on a
${15\%}$ volatility benchmark. ${2.5}$ is the usual textbook "typical
investor" value and sits in the range a normal SPY window produces here
(about ${2}$ to ${4}$).

$\delta$ is a prior about risk preference. A trailing window that includes
a bear market is a poor measurement of that preference, so the substitution
is intentional.

---

## 6. Black–Litterman

The posterior is the He & Litterman (1999) precision-weighted blend of an
equilibrium prior and a set of views. Linear algebra only; the solver comes
later. $\tau = 0.05$ is the conventional He–Litterman scalar. It is not
estimated. It means the covariance of the unknown mean is ${5\%}$ of
$\Sigma$: the equilibrium mean is treated as informative.

### 6.1 Market portfolio

$$
w_{\mathrm{mkt},i}
  = \frac{m_i}{\sum_j m_j}
$$

$m_i$ is `TickerClassification.market_cap_or_aum` (market cap for stocks,
AUM for ETFs). A missing classification or a null value contributes ${0}$.
If every $m_i$ is ${0}$, $w_{\mathrm{mkt}}$ is equal weight ${1/n}$. That
changes only the prior. Sector bounds read the same table independently.

### 6.2 Equilibrium prior

$$
\pi = \delta\, \Sigma\, w_{\mathrm{mkt}}.
$$

$\Sigma$ and $\pi$ are daily, because $\Sigma$ was divided back by
${252}$ and $\delta$ was computed from annual excess return over annual
variance. The identity

$$
\pi_{\mathrm{annual}} = \delta\, (252\,\Sigma)\, w_{\mathrm{mkt}}
  = 252\, \pi
$$

is what the later $\times 252$ on means recovers. Reverse optimization is
the statement that $w_{\mathrm{mkt}}$ satisfies the unconstrained
first-order condition $\pi_{\mathrm{annual}} - \delta \Sigma_{\mathrm{annual}} w = 0$.

### 6.3 Views

Views exist only for tickers classified `asset_class == "etf"`. Each such
ticker $i$ is one **absolute** view:

$$
P_{k,i} = 1,\quad P_{k,j} = 0 \ (j \neq i), \qquad
Q_k = \overline{r}_i = \operatorname{nanmean}_t(r_{t,i}).
$$

$Q_k$ is that ETF's own historical daily mean, not a user forecast and not
a relative view against the market. Confidence is fixed at $c = 0.3$ for
every ETF view. Individual stocks have no view. Their posterior means move
only because $\Sigma$ couples them to the ETFs.

If the book contains no ETF, there is nothing to blend: $\mu_{BL} = \pi$
and $\Sigma_{BL} = \Sigma$ (the floored daily covariance). That path does
**not** add $\tau\Sigma$ of mean uncertainty. The with-views path does
(§6.5). A no-ETF book is therefore scored on a slightly tighter covariance
than the same book would be if a single ETF view were present.

### 6.4 View uncertainty (the confidence formula this code calls Idzorek)

`idzorek_omega` builds a diagonal $\Omega$. Views are treated as
independent. For view row $p_k$,

$$
v_k = p_k^\top (\tau \Sigma)\, p_k
$$

$$
c_k \leftarrow \min\bigl(1-10^{-6},\, \max(10^{-6},\, c_k)\bigr)
$$

$$
\Omega_{kk} = \max\Bigl(v_k \bigl(\tfrac{1}{c_k} - 1\bigr),\; 10^{-10}\Bigr)
  = \max\Bigl(\frac{1-c_k}{c_k}\, v_k,\; 10^{-10}\Bigr).
$$

So $\Omega_{kk}$ is the prior variance of that view portfolio, scaled by
$(1-c)/c$. At the ETF confidence $c = 0.3$,

$$
\frac{1-c}{c} = \frac{0.7}{0.3} \approx 2.333,
$$

and the view's precision ${1/\Omega_{kk}}$ is $c/(1-c) \approx 0.429$ times
the prior precision ${1/v_k}$. The view is **weaker** than the equilibrium
prior. ${30\%}$ confidence is not a ${30/70}$ mix of weights, and it is not
"30% of the way from $\pi$ to $Q$" once assets are correlated.

On a one-asset book, or more generally whenever $\Sigma$ is diagonal and
the view is one-hot, the posterior mean of that asset does collapse to the
convex combination

$$
\mu_i = (1-c)\,\pi_i + c\, Q_i.
$$

With a real covariance the update is the matrix blend in §6.5. Other assets
move, and asset $i$ is not exactly $(1-c)\pi_i + c Q_i$.

The ${10^{-10}}$ floor exists because a view on a zero-variance asset has
$v_k = 0$, which would make $\Omega$ singular. The floor does not move
a normal view: $\tau$ times a daily variance is orders of magnitude larger.

This is the closed-form confidence scaling implemented by PyPortfolioOpt and
labeled Idzorek in that library. It is **not** Idzorek's original 2005
procedure, which solves for the $\Omega$ that makes the active weight
equal to $c$ times the fully confident active weight. The code never
computes those implied weights.

### 6.5 Posterior

$$
M = (\tau\Sigma)^{-1} + P^\top \Omega^{-1} P
$$

$$
\mu_{BL} = M^{-1}\bigl[(\tau\Sigma)^{-1}\pi + P^\top \Omega^{-1} Q\bigr]
$$

$$
\Sigma_{BL} = \Sigma + M^{-1}.
$$

$M$ is the posterior precision of the **mean**. $M^{-1}$ is the
covariance of that mean estimate, not of returns. Adding it to $\Sigma$
is the predictive covariance of returns: the investor bears both the assets'
own variance and the leftover uncertainty about the mean. As
$\Omega \to \infty$, the view terms vanish and $\mu_{BL} \to \pi$. As
$\Omega \to 0$, the views dominate and $P\mu_{BL} \to Q$.

Both objectives, the current-book score, and the frontier use
$(\mu_{BL}, \Sigma_{BL})$. The historical sample mean is **not** the
number the current portfolio is scored on. It enters only as $Q$ for ETF
views. Current and suggested Sharpe are therefore the same estimator. They
can still disagree with the Sharpe on the risk-metrics card, which is a
time-weighted return on total account equity, including cash.

---

## 7. Constraints

The feasible set is a long-only simplex cut by a position cap and optional
sector and ticker bounds. Shorting is not allowed: the default lower bound
is ${0}$.

### 7.1 Position cap

The user setting `optimization_position_cap_pct` defaults to ${10}$. A null
column (rows created before the column existed) is treated as ${10}$. In
fraction form, $c_{\mathrm{cap}} = \text{percent}/100$.

If $n \cdot c_{\mathrm{cap}} < 1$, no long-only vector can sum to ${1}$
while respecting the cap. The cap is raised rather than failing the solve:

$$
c_{\min} = \frac{1/n}{0.95}, \qquad
c_{\mathrm{eff}} = \min(1,\, c_{\min})
  \quad\text{when } c_{\mathrm{cap}} < c_{\min}.
$$

${0.95}$ is `SAFETY_MARGIN`. Dividing by it places the equal-weight book
$w_i = 1/n$ strictly inside the cap ($n \cdot c_{\mathrm{eff}} = 1/0.95
\approx 1.053$ when that value is below $1$). The relaxation is returned
as `cap_relaxed` with the requested cap, the effective cap, and the reason
`"too few holdings for cap"`. The API field `position_cap_pct` is the
**effective** cap.

### 7.2 Ticker bounds

Default box: ${0 \le w_i \le c_{\mathrm{eff}}}$.

A `TickerConstraint` row **replaces** that box with the row's own floor and
cap. It is not intersected with the global cap. A ticker the user set to
${25\%}$ is allowed to reach ${25\%}$ even when the global cap is ${10\%}$.

Floors and caps are stored as percents and divided by ${100}$. New rows are
rejected unless ${0 \le \mathrm{floor} \le \mathrm{cap} \le 100}$. A legacy
inverted row is collapsed with $\mathrm{floor} \leftarrow \min(\mathrm{floor}, \mathrm{cap})$ so SciPy does not receive an inverted bound. There is no
automatic clip when the sum of ticker floors exceeds ${1}$. That problem is
infeasible; the solve fails and §9's equal-weight fallback applies.

### 7.3 Sector exposure

`TickerClassification.sector_weights_json` is a map from sector name to
fraction. Stocks are typically one sector at ${1}$. ETFs are look-through
fractions. The exposure matrix $E$ is $n \times s$, columns sorted by
sector name, $E_{ij}$ the fraction of ticker $i$ in sector $j$. A
ticker with no classification is a zero row: it satisfies no sector floor.

Sector exposure of a book is $E^\top w$. A sector with no
`SectorConstraint` row is unbounded in $[0,1]$. A sector with a row
contributes two inequalities. Names are normalized with the same function
the classifier uses, so a constraint can match a column.

### 7.4 Unreachable sector floors

The maximum weight sector $j$ can receive, under ${0 \le w_i \le c_{\mathrm{eff}}}$
and $\sum w_i = 1$, is a linear program. The optimum is greedy: sort
tickers by $E_{ij}$ descending and fill each up to the cap until the
weights sum to ${1}$. Call that value $a_j$.

A requested floor above ${0.95\, a_j}$ is lowered to ${0.95\, a_j}$, and the
clip is logged (`requested_floor`, `clipped_to`). The ${0.95}$ margin keeps
the floor inside the feasible set instead of sitting on a vertex that SLSQP
then rejects. If the stored cap is below that clipped floor, the cap is
raised to the floor and logged. A floor on a sector that does not appear in
$E$ at all is logged as clipped to ${0}$; there is no bound to enforce.

`sector_breakdown.floor_pct` and `cap_pct` are these **post-clip** bounds,
not the raw user request.

The greedy max uses the global effective cap for every ticker. It does not
see per-ticker overrides. A ticker allowed above the global cap can make a
sector more reachable than $a_j$, and a ticker capped below it can make a
sector less reachable. The clip can therefore be slightly conservative or
slightly optimistic when ticker overrides exist.

### 7.5 Constraint list passed to the solver

Equality:

$$
\sum_{i=1}^{n} w_i - 1 = 0.
$$

For each constrained sector, SciPy inequalities in $g(w) \ge 0$ form:

$$
(E^\top w)_j - L_j \ge 0, \qquad U_j - (E^\top w)_j \ge 0.
$$

Box bounds are SLSQP `bounds`, not extra inequalities. The frontier helper
receives only the sector inequalities and adds the sum-to-one equality
itself, so the equality is not duplicated.

---

## 8. Objectives

Both problems start at $w^{(0)} = (1/n,\ldots,1/n)$ and call
`scipy.optimize.minimize` with `method="SLSQP"`. No analytic Jacobian, no
custom tolerance, and no custom iteration cap are passed. Gradients are
finite differences. Defaults are SciPy's (roughly `ftol = 1e-6`, on the
order of ${100}$ iterations).

### 8.1 Concentration penalty

The user slider `optimization_concentration_strength` is $s \in [0,1]$,
default ${0.5}$ (null columns included). It maps to two penalties because
the objectives have different units:

$$
\gamma_S = s \cdot 2.0, \qquad \gamma_U = s \cdot 0.3.
$$

At the default, $\gamma_S = 1$ and $\gamma_U = 0.15$. The scales were
chosen so that at full strength the penalty is visible against a Sharpe of
order ${0.1}$–${3}$ and a utility of order ${0.01}$–${0.5}$, without
swamping either one. They are calibration constants, not estimated
parameters.

The penalty is the squared Euclidean norm, which on a portfolio is the
Herfindahl–Hirschman index:

$$
H(w) = \sum_{i=1}^{n} w_i^2 = \lVert w \rVert_2^2.
$$

On the simplex, $H$ is minimized at equal weight ($H = 1/n$) and
maximized at a vertex ($H = 1$). Effective $N$ is ${1/H}$. Adding
$\gamma H(w)$ to a **minimization** objective pulls the solution toward
equal weight. The pull is a ridge: the unconstrained stationarity condition
gains a term proportional to $w$, and the sum-to-one constraint is what
stops the ridge from driving every weight to zero.

The penalty changes which $w$ is chosen. It is **not** included in the
Sharpe, return, or volatility that the API reports. Those are
`portfolio_stats` on the solved weights.

### 8.2 Max Sharpe

The quantity being maximized is the annualized Sharpe ratio. SciPy
minimizes its negative, plus the penalty:

$$
\mu_{\mathrm{ann}} = 252\, w^\top \mu_{BL}
$$

$$
\sigma_{\mathrm{ann}} = \sqrt{252}\, \sqrt{w^\top \Sigma_{BL} w}
$$

$$
\operatorname{Sharpe}(w)
  = \frac{\mu_{\mathrm{ann}} - r_f}{\sigma_{\mathrm{ann}}}
  \quad (\sigma_{\mathrm{ann}} > 0)
$$

$$
f_S(w) = -\operatorname{Sharpe}(w) + \gamma_S\, H(w).
$$

If $\sigma_{\mathrm{ann}} = 0$, the objective returns ${0}$ (as if Sharpe
were ${0}$, before the penalty). A literally zero-volatility book is not
treated as infinite Sharpe.

Sharpe is a ratio of a linear function to a convex function. With box
constraints, sector inequalities, and the $H(w)$ term, the problem is not
a convex program. SLSQP returns a local solution from the equal-weight
start, not a certified global maximum. The unconstrained tangency portfolio
has the closed form $\Sigma^{-1}(\mu - r_f \mathbf{1})$, up to scaling.
That closed form is not used. The caps are the reason.

Reported Sharpe uses the same formula with no $\gamma_S$. Return and
volatility are $\mu_{\mathrm{ann}}\times 100$ and $\sigma_{\mathrm{ann}}\times 100$.

### 8.3 Max quadratic utility

Mean–variance utility at risk aversion $\delta$, in annual units:

$$
U(w) = 252\, w^\top \mu_{BL}
  - \tfrac12\, \delta\, \bigl(252\, w^\top \Sigma_{BL} w\bigr).
$$

$$
f_U(w) = -U(w) + \gamma_U\, H(w).
$$

The $\tfrac12$ is the convention that makes the unconstrained first-order
condition

$$
\mu_{\mathrm{ann}} - \delta\, \Sigma_{\mathrm{ann}} w = 0,
$$

which is the same condition $\pi = \delta\Sigma w_{\mathrm{mkt}}$ was
built from. $\delta$ is already an annual coefficient (§5.2). It is not
multiplied or divided by ${252}$.

Variance is multiplied by ${252}$, not by $\sqrt{252}$. The square root
belongs only in the Sharpe denominator, because Sharpe uses a standard
deviation. Utility penalizes variance.

Annualization here is load-bearing. $\gamma_U$ was calibrated against an
annual utility of order ${0.01}$–${0.5}$. Leaving $U$ in daily units makes
it about ${252}$ times too small, the penalty dominates, and the utility
solve collapses to equal weight.

Without the penalty and the inequality constraints, this objective is
concave (linear mean, convex variance, $\delta > 0$). The $H(w)$ term
is also convex, so ${-U + \gamma_U H}$ stays convex when $\delta > 0$.
The guarded substitution in §5.3 is what keeps $\delta > 0$. Sector
inequalities and the simplex are convex. Ticker bounds are convex. So the
utility problem, as passed to SLSQP, is a convex nonlinear program **if**
$\Sigma_{BL}$ is positive semidefinite, which the shrinkage-plus-diagonal-floor
construction maintains. Convexity does not by itself give a global
certificate from SLSQP, but it means a successful local solve is the global
solution of $f_U$.

The two solves share bounds, sector inequalities, $\mu_{BL}$, and
$\Sigma_{BL}$. They differ in $f_S$ versus $f_U$ and in $\gamma$.
They are expected to land on different weights. Utility has an explicit
taste for variance through $\delta$. Sharpe is scale-free and will accept
more volatility when the excess-return ratio improves. Neither solve is a
constrained version of the other.

### 8.4 What "current" means

The current book is scored with `portfolio_stats` on
$(\mu_{BL}, \Sigma_{BL}, r_f)$, not on sample means. Expected return,
volatility, and Sharpe for current and for both suggestions are the same
model. A higher suggested Sharpe means the solved weights beat the current
weights inside that model, subject to the constraints. It is not a
backtest.

---

## 9. Solver failure

If SLSQP returns `success=False`, the weights for that objective are the
equal-weight start ${1/n}$, and `clip_log` records that these are not
optimized weights, plus the solver message. The endpoint still has to
return an allocation, so the fallback is labeled rather than omitted.

The frontier does the opposite: a failed target-volatility solve is dropped.
Substituting equal weight there would draw a point that the constraints do
not achieve.

Typical causes of `success=False` are an infeasible ticker-floor sum, a
sector bound the clip did not fully repair, or a numerical failure of the
non-convex Sharpe or frontier problem.

---

## 10. Efficient frontier

`sweep_efficient_frontier` runs after both objectives. Inputs are
$\mu_{BL}$, $\Sigma_{BL}$, the ticker bounds, and the sector
inequalities. The concentration penalty is **not** applied. The frontier is
mean versus volatility, not penalized utility.

All solves stay in daily units. Only the emitted points are annualized.

**Step 1.** Minimum-volatility portfolio:

$$
\min_w \sqrt{w^\top \Sigma_{BL} w}
$$

subject to the same bounds and sector constraints. If this fails, the
frontier is empty.

**Step 2.** Maximum-return portfolio, $\max_w w^\top \mu_{BL}$ under the
same constraints. Its daily volatility is the top of the sweep,
$\sigma_{\max}$. If this fails, the frontier is empty.

**Step 3.** Twenty targets (the default `n_points`)

$$
\sigma_k \in \operatorname{linspace}(\sigma_{\min},\, \sigma_{\max},\, 20).
$$

For each $k$, solve

$$
\max_w \; w^\top \mu_{BL}
  \quad\text{s.t.}\quad
  \sqrt{w^\top \Sigma_{BL} w} = \sigma_k
$$

plus the sum-to-one equality, sector inequalities, and ticker bounds. The
volatility constraint is an equality on a convex function, so the feasible
set is not convex. Each point is an independent SLSQP run from equal
weight. Failures are omitted. The curve can have gaps, and a local solution
need not be monotone in return.

Emitted point, rounded to three decimal percent:

$$
\text{volatility\_pct} = 100\cdot \sigma_k \cdot \sqrt{252}
$$

$$
\text{return\_pct} = 100\cdot 252\cdot (w^\top \mu_{BL}).
$$

The objective markers use `portfolio_stats`, which annualizes the same way,
so a marker and a frontier point are on one scale. A marker is not required
to lie on the curve. Max Sharpe and max utility include the concentration
penalty and, for Sharpe, a different objective than "max return at this
volatility."

---

## 11. Random portfolio cloud

`sample_random_portfolios` draws ${1500}$ long-only weights for the chart
only. Half are $\mathrm{Dirichlet}(1,\ldots,1)$, which is uniform on the
simplex. Half are $\mathrm{Dirichlet}(0.2,\ldots,0.2)$, which piles mass
on the vertices so single-asset books show up. The generator is
`numpy.random.default_rng()` with no seed. The cloud changes from request
to request.

No position cap, no sector constraint, no ticker floor. The cloud is the
unconstrained long-only set the caps cut down, not a second frontier.
Return, volatility, and Sharpe use the same annualization and $r_f$ as
§8.2, rounded to three decimals. The MCP tool drops this array. It has no
information beyond the frontier and the two objectives.

---

## 12. Reported numbers

`portfolio_stats` returns

$$
\bigl(100\,\mu_{\mathrm{ann}},\; 100\,\sigma_{\mathrm{ann}},\; \operatorname{Sharpe}\bigr)
$$

with Sharpe `None` when volatility is ${0}$.

| Field | Rounding | Which solve |
| --- | --- | --- |
| Weight percents, objective return, volatility, Sharpe | 2 decimal places | each objective |
| Suggested dollars | cents | weight times today's included value |
| Frontier and cloud coordinates | 3 decimal places | §10 and §11 |
| `position_cap_pct` | 2 decimal places | effective cap, percent |
| Sector `weight_pct` | full float, then JSON | ${100\,(E^\top w)_{j}}$ at **max-Sharpe** $w$ |

Rounded weights need not sum to exactly ${100}$.

`data_points` is the number of union dates in the price matrix, before
per-ticker drops.

`insufficient_data` means advanced mode was on and the universe failed a
screen in §3. `advanced_enabled=false` means the engine did not run.
Those two states are different: the UI hides the optimizer when the flag
is off, and it shows a "not enough history" state when the flag is on but
the data screen failed.

---

## 13. Product surface

Preferences, all on user 1:

| Setting | Range | Default | Effect |
| --- | --- | --- | --- |
| Advanced optimization | on/off | off | Gates the entire engine |
| Position cap | $(0, 100]$ percent in the API; the slider uses 2–50 | 10 | Default upper bound on each ticker, subject to §7.1 |
| Diversification | $[0, 1]$ | 0.5 | $s$ in §8.1 |
| Sector floor and cap | ${0 \le \mathrm{floor} \le \mathrm{cap} \le 100}$ | none | §7.3–7.4 |
| Ticker floor and cap | same | none | Replaces the global cap for that ticker |

Changing a slider does not re-solve. The Investments page solves when it
loads and when the user presses **Run optimization**, always with a
${1095}$-day lookback. The chart is the frontier, with markers for max
Sharpe, max quadratic utility, and the current book, plus the random cloud.
The allocation table follows the selected objective. A warning lists
`cap_relaxed` and `clip_log` (dropped tickers, $\delta$ substitution,
clipped sector floors, failed solves).

`GET /api/investments/risk/optimize?lookback_days=` accepts 90–1825.
Constraint writes that invert floor and cap return HTTP 422. Reads still
return legacy inverted rows so they can be repaired.

The MCP tool `portfolio_optimization` calls the same function with the
default lookback and returns both objectives, the frontier, the sector
breakdown, and `clip_log`. It omits the random cloud.

---

## 14. Accuracy limits

These are properties of this implementation, not things the UI papers over.

**The mean is a model, not a forecast.** $\mu_{BL}$ mixes a
market-cap-weighted reverse optimization with the trailing daily mean of
each ETF, at ${30\%}$ confidence and $\tau = 0.05$. Stocks are pulled
along only by covariance. A three-year window is long enough to stabilize
the estimate relative to a one-year window, and still a single regime.

**Arithmetic ${252}$ scaling.** Mean $\times 252$ and variance $\times 252$
ignore compounding, autocorrelation, and overnight versus session effects.
Sharpe is that annualized excess return divided by $\sqrt{252}$ times
daily volatility.

**Sample-size conventions differ by one.** Ledoit–Wolf divides by $T$.
SPY's variance inside $\delta$ divides by $T-1$. On a three-year window
the relative gap is about ${1/750}$.

**No-view covariance omits $\tau\Sigma$.** Documented in §6.3.

**Shrinkage is the simplified Ledoit–Wolf intensity.** No higher-order
bias correction. Pairwise $T$ and an unprojected $\bar\rho$ are the
ragged-history behavior.

**Local optimum for Sharpe and for the frontier.** Utility is convex under
the conditions in §8.3. Sharpe is not. Both start at equal weight. A
different start could produce a different Sharpe book. Failed Sharpe solves
are replaced by equal weight and labeled.

**Constraint repair is approximate.** Sector feasibility uses the global
cap and a ${5\%}$ margin, and it ignores per-ticker overrides. Ticker floors
that sum past ${100\%}$ are not repaired.

**Mixed trading calendars.** §3. Weekend rows from one asset change which
close-to-close gaps another asset records, and every gap is still one
"day" in the ${252}$ factor.

**The random cloud is not a confidence interval.** It is an unseeded
Dirichlet sample of the uncapped simplex, drawn from the same
$(\mu_{BL}, \Sigma_{BL})$. It does not represent estimation error.

**Displayed Sharpe ignores the diversification penalty** that helped choose
the weights. Comparing the two objectives by their reported Sharpe compares
the ratio, not the utility and not the penalized objective.

**Valuation basis.** Weights use margin-scaled holding values. Suggested
dollars reprice those weights at today's included total. Prices inside
$\mu$ and $\Sigma$ are `MarketPrice` closes, which can differ from the
broker mark used for the dollar weights.

---

## 15. Worked shape of one run

For a book that passes the data screens, with advanced mode on:

1. Build the union price panel and pairwise simple returns.
2. $\Sigma \leftarrow \Sigma_{\mathrm{LW, daily}}$, then floor the diagonal at ${10^{-10}}$.
3. $\delta \leftarrow (\mu_{\mathrm{SPY}} - r_f) / \sigma^2_{\mathrm{SPY}}$, or ${2.5}$ if unusable.
4. $\pi \leftarrow \delta \Sigma w_{\mathrm{mkt}}$.
5. If any holding is an ETF, blend $\pi$ with that ETF's trailing daily mean at confidence ${0.3}$, $\tau = 0.05$. Else $(\mu_{BL}, \Sigma_{BL}) = (\pi, \Sigma)$.
6. Relax the position cap if $n$ times the cap is below ${1}$. Clip sector floors to ${95\%}$ of the greedy maximum. Apply ticker overrides.
7. Minimize $f_S$ and $f_U$ with SLSQP from equal weights.
8. Score the current weights and both solutions with annualized mean, $\sqrt{252}$ volatility, and Sharpe.
9. Sweep twenty max-return solves between the minimum and maximum feasible daily volatility.
10. Draw the unseeded Dirichlet cloud.

A run with the flag off stops before step 1.
