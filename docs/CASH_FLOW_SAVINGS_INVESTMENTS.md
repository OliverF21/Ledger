# Spec: Cash Flow Savings vs Investments vs Transfers

Status: draft  
Related: Cash Flow page (`#spending`), `build_cash_flow`, Plaid PFC transfer taxonomy, Investments tab

## Problem

Cash Flow today has a right-side node labeled **Savings**, but that number is not "money moved to savings." It is leftover income after spending:

```text
savings = max(income − spending, 0)
```

At the same time, real money movement between accounts is mostly invisible on that chart:

- `TRANSFER_OUT_SAVINGS` / `TRANSFER_IN_SAVINGS` are excluded from spending/income
- `TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS` / `TRANSFER_IN_INVESTMENT_AND_RETIREMENT_FUNDS` are excluded
- Internal account transfers are excluded
- Brokerage activity in `investment_transactions` never enters cash flow at all

So three different ideas get blurred:

1. **Internal transfers** — money already inside the Ledger universe, just changing pockets
2. **Savings allocation** — deliberately parking cash in a savings/emergency/cash reserve
3. **Investing allocation** — deliberately putting money into brokerage / retirement / markets

Users (and the chart) need those to mean different things.

## Goals

1. Keep Cash Flow readable as: money in → uses of money.
2. Show **Savings** and **Investments** as distinct allocation sinks when the user actually moved money that way.
3. Never count normal transfers as spending or income.
4. Avoid double-counting with the Investments tab (holdings / buys / sells).
5. Prefer Plaid categories + account type when possible; allow manual recategorization when Plaid is wrong.

## Non-goals (for this change)

- Replacing the Investments page (holdings, performance, investment transaction history)
- Tracking unrealized gains/losses on the Cash Flow chart
- Building a full double-entry ledger
- Auto-detecting every ACH/P2P edge case on day one

---

## Definitions

### 1. Transfer (neutral movement)

Money moving between accounts Ledger already tracks, or between the user’s own wallets, with **no change in net worth intent** and **no consumption**.

Examples:

- Checking → checking / savings / credit payment within linked accounts
- Credit card payment (`LOAN_PAYMENTS_*`)
- App-to-app moves that are really the same person (`TRANSFER_OUT_TRANSFER_OUT_FROM_APPS` when internal)
- Brokerage settlement of a sale that lands back in a linked cash account, when we already track that brokerage

**Cash Flow rule:** do not show as income or spending. Optionally hide entirely, or show in a collapsed “Transfers” footnote later. Not a Sankey sink in v1.

### 2. Savings (cash reserve allocation)

Money the user is **setting aside as cash**, still essentially cash-like: HYSA, emergency fund, sinking funds, “move $500 to savings.”

This is an **allocation of surplus**, not a purchase.

Examples:

- Checking → linked savings account (`TRANSFER_OUT_SAVINGS` / account subtype `savings`)
- Manual category like `Savings` / `Emergency Fund` on an outflow the user wants treated as saving
- Residual unallocated surplus (today’s synthetic Savings node), renamed so it is not confused with explicit savings transfers

**Cash Flow rule:** show as its own right-side sink: **Savings**.

### 3. Investments (capital allocation)

Money the user is **putting to work in markets / retirement / brokerage**, leaving the spendable cash system.

Examples:

- Checking → brokerage / IRA / 401(k) contribution (`TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS`)
- ACH to an external broker Ledger does not fully track, categorized as investing
- Employer contribution is income-side (or ignored if not in bank feed); employee deferral from paycheck may appear as a transfer out

**Cash Flow rule:** show as a separate right-side sink: **Investments**.  
Do **not** merge this into Savings. Do **not** treat brokerage buys/sells inside an already-funded brokerage as Cash Flow spending (that is portfolio activity).

---

## How to tell them apart

Decision order for an outflow (positive Plaid amount):

```text
1. Is it a loan payment / credit card payment?
     → Transfer (excluded). Not Savings. Not Investments.

2. Is it a transfer into investment / retirement funds,
   or to an account with type=investment / known brokerage?
     → Investments allocation.

3. Is it a transfer into savings,
   or to an account with subtype=savings / user category Savings?
     → Savings allocation.

4. Is it an internal account transfer (same household, both ends linked)?
     → Transfer (excluded).

5. Otherwise if it is TRANSFER_OUT_* we cannot classify:
     → Transfer (excluded) by default; allow manual recategorize to Savings or Investments.

6. Otherwise:
     → Spending (Food, Rent, etc.).
```

Decision order for an inflow (negative Plaid amount):

```text
1. Wages / salary / paycheck / tax refund / etc.
     → Income.

2. Transfer back from brokerage / retirement to a depository account.
     → Not income. Treat as Investments withdrawal (reduce Investments allocation
       for the month, or show as a separate inflow bucket "From investments"
       that does not inflate earned income). Preferred v1: exclude from earned
       income; optionally surface under a non-income "Transfers from investments"
       detail later.

3. Transfer from savings account into checking.
     → Not income. Savings withdrawal (reduces Savings allocation for the month).

4. Internal account transfer in.
     → Excluded.

5. External deposit / other transfer in that looks like real money entering the system.
     → Income only when category is DEPOSIT / OTHER_TRANSFER_IN / clear earned income.
       Keep current allowlist behavior unless tests prove otherwise.
```

### Signal sources (priority)

| Priority | Signal | Notes |
| --- | --- | --- |
| 1 | `category_user` | Manual override wins |
| 2 | Plaid detailed category | `TRANSFER_OUT_SAVINGS`, `TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS`, etc. |
| 3 | Destination / source account | `Account.type` / `subtype` of the *other* side when known |
| 4 | Merchant / memo heuristics | Later; optional rules engine |
| 5 | Synthetic residual | Only after all explicit allocations |

Plaid is often wrong on transfers. Manual recategorization into **Savings** or **Investments** (as allocation labels, not spend categories) must be first-class.

---

## Proposed Cash Flow model

### Sankey shape (v1)

```text
[Income sources] → [Income pool] → [Spending categories]
                                 → [Savings]        // explicit cash set-aside + residual
                                 → [Investments]    // explicit investing contributions
```

Optional later:

```text
                                 → [Transfers]      // collapsed, not in main tunnel
```

### Amount math

Let:

- `EarnedIncome` = income after exclusions (current income pool, tightened so brokerage/savings withdrawals are not income)
- `Spending` = consumption categories only
- `SavingsAllocated` = sum of classified savings outflows − savings inflows (floor at 0 for the sink size, or show net; see open questions)
- `InvestedAllocated` = sum of classified investment contributions − investment withdrawals back to cash (same netting question)
- `Residual` = `EarnedIncome − Spending − SavingsAllocated − InvestedAllocated`

Then:

| Node | Value |
| --- | --- |
| Spending categories | as today |
| **Savings** | `SavingsAllocated + max(Residual, 0)` **or** split into two nodes (see below) |
| **Investments** | `InvestedAllocated` (never absorbs residual by default) |

**Recommendation:** do **not** dump unexplained leftover into Investments. Residual cash belongs with **Savings** (or a third node named **Unallocated**). Investing should only grow when we have evidence of an investment transfer.

Better UX split (preferred if the chart can spare a node):

| Node | Meaning |
| --- | --- |
| **Savings** | Explicit transfers to savings / cash reserves only |
| **Investments** | Explicit transfers to brokerage / retirement only |
| **Unallocated** | `max(EarnedIncome − Spending − Savings − Investments, 0)` |

If we keep a single "Savings" label for residual (compatibility with today’s chart), rename the header copy carefully:

- Header: `Left over $X` or `Unallocated $X`
- Node: prefer **Unallocated** over **Savings** once explicit Savings exists

### What must never happen

- Credit card payment counted as Spending or Savings
- Checking → savings counted as Spending
- Checking → brokerage counted as Savings
- Brokerage buy of VTI counted as Cash Flow Spending (that is Investments-tab activity)
- Brokerage withdrawal counted as Paycheck / earned income
- Residual leftover auto-labeled Investments

---

## Mapping from current Plaid categories

### Excluded transfers (stay out of spending/income)

| Detailed key | Treatment |
| --- | --- |
| `TRANSFER_OUT_ACCOUNT_TRANSFER` | Transfer |
| `TRANSFER_IN_ACCOUNT_TRANSFER` | Transfer |
| `TRANSFER_OUT_TRANSFER_OUT_FROM_APPS` | Transfer by default; allow override |
| `LOAN_PAYMENTS_*` | Transfer / debt service, excluded from spending as today |

### Savings allocation

| Signal | Treatment |
| --- | --- |
| `TRANSFER_OUT_SAVINGS` | Savings allocation (+) |
| `TRANSFER_IN_SAVINGS` | Savings withdrawal (−), not income |
| Account subtype `savings` as destination | Savings allocation when categorized as transfer |
| User category `Savings`, `Emergency Fund`, etc. | Savings allocation |

### Investments allocation

| Signal | Treatment |
| --- | --- |
| `TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS` | Investments allocation (+) |
| `TRANSFER_IN_INVESTMENT_AND_RETIREMENT_FUNDS` | Investments withdrawal (−), not earned income |
| Destination `Account.type == investment` | Investments allocation when transfer-like |
| User category `Investments`, `Brokerage`, `Retirement`, `401k`, `IRA` | Investments allocation |

### Still income (examples)

| Signal | Treatment |
| --- | --- |
| `INCOME_*`, Paycheck, Salary | Income |
| `TRANSFER_IN_DEPOSIT`, `TRANSFER_IN_OTHER_TRANSFER_IN` | Income (keep current allowlist unless proven noisy) |
| Dividends paid as cash into checking with `INCOME_DIVIDENDS` | Income (cash received). Dividends reinvested only inside brokerage stay on Investments tab. |

### Still ignored by Cash Flow

| Data | Treatment |
| --- | --- |
| `investment_transactions` buys/sells/fees | Investments tab only |
| Holdings value changes | Net worth / Investments tab only |

---

## Relationship to other surfaces

| Surface | Role |
| --- | --- |
| **Cash Flow** | This month’s earned money and how it was used: spend, save, invest |
| **Budgets** | Caps on *spending* categories. Do not budget Transfers. Savings/investing targets are goal **labels**, not spend budgets |
| **Goals tab** | Named buckets; labeled transfers count as progress *and* as Cash Flow sinks |
| **Net worth** | Stock of assets/liabilities over time (includes savings balances + brokerage holdings + crypto) |
| **Investments tab** | Portfolio composition and investment_transactions |
| **Overview** | Can summarize “saved $X / invested $Y this month” using the same allocator |

Cash Flow answers: “Where did this month’s paycheck go?”  
Investments tab answers: “What do I hold, and what did the portfolio do?”  
Net worth answers: “What am I worth over time?”

---

## UI / copy changes

1. Replace today’s sole **Savings** sink with:
   - **Named goal sinks** for labeled transfers (Vacation, Emergency fund, Retirement, …)
   - Generic **Savings** / **Investments** only for unlabeled allocation transfers
   - **Unallocated** for residual leftover (never a goal)
2. Header line should not say “Saved $X” if $X is only residual. Prefer:
   - `Spent $A · Vacation $B · Emergency $C · Saved $D · Invested $E · Left $F`
   (named sinks that have activity this month; collapse unused labels)
3. Clicking a named sink or Savings / Investments should list the underlying transfer transactions (labeled vs unlabeled).
4. Category picker: add clear allocation labels (or a small “Treat as” control):
   - Spending (default for merchants)
   - Savings
   - Investments
   - Transfer (exclude)
   Plus **goal label** (Vacation, …) on savings/investment transfers — orthogonal to the above, drives the named sink.

---

## Implementation sketch (not part of this approval, just guidance)

1. Introduce an allocation classifier next to `is_excluded_from_spending` / `is_excluded_from_income`, e.g. `classify_cash_flow_txn(txn) -> income | spending | savings | investments | transfer | ignore`.
2. Teach `build_cash_flow` to emit separate nodes for savings / investments / unallocated.
3. Keep MCP Sankey + Spending page in sync.
4. Add fixtures covering:
   - paycheck + rent + groceries + transfer to HYSA + transfer to brokerage
   - credit card payment excluded
   - savings → checking not income
   - brokerage → checking not income
   - residual leftover ≠ Investments
5. Docs: update ARCHITECTURE cash-flow note once behavior ships.

Likely touch points:

- `backend/app/analytics_shared.py`
- `backend/app/services/analytics_service.py` (`build_cash_flow`)
- `frontend/src/pages/Spending.tsx`
- `backend/mcp_server/sankey.py`
- category picker / labels if allocation categories become first-class

---

## Open questions

1. **Netting:** For a month with $1,000 to brokerage and $200 back from brokerage, is Investments sink `$800` net, or show `$1000` out and handle the `$200` separately?
2. **Unallocated node:** **locked** — always show Unallocated for residual leftover once named/generic allocation sinks exist. Do not fold leftover into Savings.
3. **External brokers:** If the brokerage is not linked, is merchant/memo enough to mark Investments, or require manual category?
4. **Paycheck 401(k) deferrals:** Often invisible in bank feeds. Out of scope unless they appear as transfers.
5. **Crypto buys from checking:** Treat as Investments allocation, Spending, or a fourth sink? Recommendation: Investments (or “Assets”) if user-directed capital allocation; otherwise manual.
6. **Budgets / goals:** **locked** — do not add an “Investments $500/mo” spend budget. Targets are goal **labels**. Labeled transfers become named Cash Flow sinks; unlabeled keep generic Savings/Investments.

---

## Acceptance criteria

- Cash Flow can show **Savings** and **Investments** as different sinks in the same month.
- A labeled savings transfer (e.g. Vacation) appears as a **named sink**, not generic Savings.
- Unlabeled checking → HYSA still increases generic Savings, not Spending, not Investments, not a goal.
- A checking → brokerage transfer increases Investments (or a named invest goal if labeled), not Savings, not Spending.
- Residual leftover is **Unallocated**, never a goal and never Investments.
- A credit card payment does not appear in Spending, Savings, or Investments.
- A savings → checking or brokerage → checking transfer does not appear as earned income.
- Residual leftover never appears under Investments unless explicitly classified.
- Investments tab holdings/buys remain the source of truth for portfolio detail; Cash Flow only shows funding allocations.
- Existing spend/income category rollups (e.g. Restaurants → Food & Drink) keep working.

## Current vs target (summary)

| Concept | Today | Target |
| --- | --- | --- |
| Savings node | Residual `income − spend` | Explicit savings transfers (+ optional residual/unallocated) |
| Investments on Cash Flow | Absent | Explicit funding transfers as their own sink |
| Transfers | Excluded (good) but undifferentiated | Still excluded from spend/income; classified into savings / investments / internal |
| Brokerage activity | Investments tab only | Still Investments tab; Cash Flow only sees cash funding/withdrawals |
