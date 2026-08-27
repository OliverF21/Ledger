# Spec: MCP Financial Goals Planning (with Claude)

Status: draft  
Related: `docs/MCP_SETUP.md`, `docs/CASH_FLOW_SAVINGS_INVESTMENTS.md`, Advisor proposals (`propose_budget`), Cash Flow / Budgets / Investments analytics

## Problem

Claude Desktop can already ask Ledger’s MCP server about spending, budgets, cash flow, and investments — but it cannot answer the planning question users actually care about:

> “Given how I spend today, how much do I need to save or invest each month, and for how long, to reach *this* goal?”

Today that answer requires Claude to improvise from several tools (`cash_flow_summary`, `monthly_spending_summary`, `budget_status`, `investment_performance`, `net_worth_data`) without a shared calculator, assumptions, or persisted goal. Results are inconsistent, hard to re-check, and cannot be staged as Advisor proposals.

There is also no first-class **financial goal** entity in Ledger (no emergency fund / sinking fund / debt payoff / invest-by-date target). Budgets cap *spending*; they are not savings or investment targets. The cash-flow draft already flags “savings/investing targets as non-spend goals” as future work.

## Goals

1. Let Claude help users **analyze current expenses and surplus** and produce a clear plan: **how much per month × for how long** to reach a goal.
2. Keep planning math in Ledger (deterministic, testable), not improvised in the model.
3. Stay consistent with existing MCP conventions: **read-only analytics by default**; mutations only via **write-intent proposals** the user Applies in Advisor.
4. Reuse Cash Flow / budget / investment builders so REST and MCP share one source of truth.
5. Support both **ephemeral what-if** planning and (later) **persisted goals** with progress.

## Non-goals (for v1)

- Moving money, auto-transfers, or brokerage order placement
- Tax-optimized advice, product recommendations, or fiduciary “you should buy X”
- Full double-entry goal accounting or shared household goals
- Replacing the Budgets or Investments pages
- Claude applying proposals (Apply/Dismiss stays human-only)
- Guaranteeing investment return outcomes (returns are scenario inputs, not forecasts sold as fact)

---

## User stories

1. **Surplus → timeline:** “I want $10k emergency fund. At my current leftover income, how long will that take?”
2. **Cut spend → accelerate:** “If I cut dining and subscriptions by $200/mo, when do I hit $10k?”
3. **Target date → required contribution:** “I need $5k for a trip in 8 months. How much must I save monthly, and can I afford it?”
4. **Invest path:** “I want $50k invested in 5 years. At 0% / 5% / 7% assumed annual return, what monthly contribution do I need given my surplus?”
5. **Stage a change:** “Propose a $400/mo savings contribution and a dining budget cut so I can Apply them in Advisor.”

---

## Definitions

| Term | Meaning in Ledger |
| --- | --- |
| **Goal** | Named target amount (and optional date) the user wants to reach by saving and/or investing |
| **Surplus / capacity** | Money available to allocate after typical spending — derived from cash flow residual and/or budget headroom (see Capacity model) |
| **Contribution** | Planned monthly amount toward the goal (cash savings and/or investment funding) |
| **Horizon** | Months until the goal is funded under stated assumptions |
| **Scenario** | A what-if run: target + mode + contribution/horizon + return assumption + capacity baseline |
| **Persisted goal** | Stored goal row (progress tracked over time); optional in v1, required for “list my goals” |

### Goal kinds (v1 taxonomy)

| Kind | Typical funding | Notes |
| --- | --- | --- |
| `emergency_fund` | Cash savings | Prefer 0% return assumption |
| `sinking_fund` | Cash savings | Vacation, car, wedding, etc. |
| `debt_payoff` | Extra payment capacity | Target = remaining balance; “return” unused |
| `invest` | Brokerage / retirement funding | Optional assumed annual return (user-supplied) |
| `custom` | Either | Catch-all |

Align kinds with cash-flow **Savings** vs **Investments** sinks once `CASH_FLOW_SAVINGS_INVESTMENTS.md` ships; until then, treat residual surplus as capacity and label plans as save vs invest explicitly.

---

## Capacity model (how much can they put toward a goal?)

Planning tools must expose a transparent **capacity** breakdown so Claude explains *why* a plan is feasible or not.

### Inputs (reuse existing builders)

1. **Cash-flow residual** — today’s `savings = max(income − spending, 0)` from `build_cash_flow` / `cash_flow_summary` (rename mentally to “unallocated surplus” when the cash-flow spec ships).
2. **Lookback average** — median/mean monthly residual over N months (default 3) from trends / monthly summaries, to dampen one-off months.
3. **Budget headroom** — sum of `(limit − spent)` for under-budget categories from `budget_status` (optional; only when budgets exist).
4. **Already allocated** — explicit savings/investment transfers in the period (0 until cash-flow allocation classifier exists; then include them so we do not double-count).
5. **Manual override** — Claude or user can pass `assumed_monthly_contribution` to ignore derived capacity for pure amortization math.

### Output shape

```text
capacity = {
  residual_this_month,
  residual_lookback_avg,
  budget_headroom,          # optional
  recommended_available,    # policy pick: min(lookback_avg, residual) or lookback_avg
  notes[]                   # e.g. "March had unusually high income"
}
```

**Policy (v1):** default `recommended_available` = lookback average residual (last 3 complete months). If lookback is empty, fall back to current-month residual. Never invent income.

---

## Planning math (deterministic)

All formulas live in a shared service (e.g. `app/services/goals_planning_service.py`) so MCP and any future REST endpoint stay aligned.

### Modes

| Mode | Inputs | Outputs |
| --- | --- | --- |
| `time_to_goal` | target, current, monthly contribution, optional annual return | months, end date, schedule summary |
| `required_contribution` | target, current, months (or target date), optional annual return | monthly contribution, affordability vs capacity |
| `what_if_cut` | target + spending cuts (category → Δ$/mo) | new capacity, new horizon or new required contribution |

### Cash / 0% return (emergency, sinking, debt)

```text
remaining = max(target − current, 0)
months   = ceil(remaining / contribution)           # contribution > 0
required = remaining / months                       # months > 0
```

### Invest path with assumed return

Use standard future-value of an ordinary annuity (monthly compounding):

```text
r = annual_return / 12
FV = current*(1+r)^n + contribution * ((1+r)^n − 1) / r     # r > 0
# solve for n or contribution as needed; r = 0 falls back to cash formulas
```

**Guardrails:**

- Cap assumed annual return (e.g. 0–12%) and label it clearly as **user assumption**, not a Ledger forecast.
- Return schedules as tables Claude can narrate (month index, balance, contribution cumulative).
- Round money to cents; months up with `ceil` for “how long.”
- If `contribution > recommended_available`, mark `affordable=false` and suggest cut size or longer horizon.

---

## Phased delivery

### Phase 1 — Read-only planning tools (ship first)

No new DB tables. Claude calls tools; Ledger does the math.

**New MCP tools**

| Tool | Purpose |
| --- | --- |
| `planning_capacity` | Capacity breakdown for a month / lookback window |
| `plan_goal` | Core planner: mode + target + current + contribution/horizon + return → plan result |
| `plan_goal_from_expenses` | Convenience: pull capacity + category spend, then run `plan_goal` (optional spending-cut deltas) |

**Optional chart**

| Tool | Purpose |
| --- | --- |
| `chart_goal_plan` | Inline SVG: balance over time under the plan (same visual pattern as `chart_cash_flow`) |

**Example Claude flow**

1. `planning_capacity(lookback_months=3)` → ~$650/mo available  
2. `spending_by_category` / `budget_status` → dining & subs are fat  
3. `plan_goal_from_expenses(target=10000, current=2000, mode=time_to_goal, cuts=[{dining: -150}, {subs: -50}])`  
4. Claude narrates: “With $850/mo, you hit $10k in ~10 months; without cuts, ~13 months.”

### Phase 2 — Persisted goals + progress

Add `FinancialGoal` in `budgets.db` (user intent, not Plaid truth), beside `Budget` / `Proposal`.

**Suggested fields**

| Field | Type | Notes |
| --- | --- | --- |
| `id` | int PK | |
| `name` | str | “Emergency fund” |
| `kind` | enum | see taxonomy |
| `target_amount` | float | |
| `current_amount` | float | manual or linked later |
| `target_date` | date \| null | |
| `monthly_contribution` | float \| null | planned |
| `annual_return_assumption` | float \| null | invest only |
| `status` | enum | `active` / `paused` / `completed` / `dismissed` |
| `created_at` / `updated_at` | timestamps | |

**New MCP tools**

| Tool | Type |
| --- | --- |
| `list_financial_goals` | Read |
| `goal_progress` | Read — % funded, months ahead/behind vs plan |

Progress can start with user-supplied `current_amount`; later optionally link to a savings account balance or net-worth slice.

### Phase 3 — Write-intent proposals + Advisor UI

Mirror `propose_budget`: MCP never mutates; it POSTs proposals; user Applies in Advisor.

**New proposal kinds**

| Kind | Effect on Apply |
| --- | --- |
| `set_goal` | Create/update a `FinancialGoal` |
| `update_goal_contribution` | Change planned monthly contribution |
| `set_savings_budget` | Optional: non-spend target treated as allocation goal (ties to cash-flow spec open question #6) |

Also allow Claude to continue using `propose_budget` for category cuts that free capacity.

**Touch points**

- `mcp_server/proposals.py` — create helpers  
- `routes/proposals.py` — `SUPPORTED_KINDS`, validate, apply, undo, summaries  
- Advisor UI — today is budget-diff oriented; add goal proposal cards  
- Docs: `MCP_SETUP.md`, `ARCHITECTURE.md`

---

## MCP tool contracts (Phase 1 detail)

### `planning_capacity`

**Params:** `lookback_months` (default 3), optional `month` (YYYY-MM).

**Returns (Pydantic):** residual series, averages, `recommended_available`, notes.

**Tags:** `analytics`, `planning`

### `plan_goal`

**Params:**

| Param | Required | Notes |
| --- | --- | --- |
| `target_amount` | yes | > 0 |
| `current_amount` | no | default 0 |
| `mode` | yes | `time_to_goal` \| `required_contribution` |
| `monthly_contribution` | for time mode | > 0 |
| `months` or `target_date` | for contribution mode | exactly one |
| `annual_return` | no | default 0; clamp 0–0.12 |
| `assumed_monthly_capacity` | no | if omitted, call capacity internally or require caller to pass |

**Returns:** remaining, contribution, months, projected_end_month, `affordable`, capacity snapshot, schedule summary (first/last + milestones), assumption labels.

**Tags:** `analytics`, `planning`

### `plan_goal_from_expenses`

**Params:** same as `plan_goal` plus optional `cuts: list[{category_key|name, monthly_delta}]` (negative = reduce spend).

**Behavior:** compute capacity → apply cuts to `recommended_available` → run planner → include before/after comparison.

**Tags:** `analytics`, `planning`, `spending`

---

## Architecture sketch

```text
Claude Desktop
    │  MCP tools (stdio / Tailscale HTTP)
    ↓
mcp_server/server.py          # thin @mcp.tool wrappers
    ↓
app/services/goals_planning_service.py   # capacity + amortization (NEW)
    ├── analytics_service (cash flow, monthly summary, trends)
    ├── budget status builders
    └── (phase 2) FinancialGoal CRUD in budgets.db

Write path (phase 3 only):
propose_* → POST /api/proposals → Advisor Apply → budgets.db
```

**Principles (unchanged):**

- MCP SQLite sessions stay read-only (`mode=ro`, `query_only`).
- No Anthropic SDK in-repo; Claude hosts the model.
- Shared builders for API and MCP.
- Money movement never exposed.

---

## Implementation sketch (guidance)

1. Add `goals_planning_service.py` with pure functions + dataclass results; unit-test extensively (0% and r>0, affordability, ceil months, clamps).
2. Add Pydantic result models in `mcp_server/schemas.py`.
3. Register Phase 1 tools in `mcp_server/server.py` with rich descriptions/instructions so Claude prefers Ledger math over inventing schedules.
4. Extend FastMCP server `instructions` string with a short “Financial goals” section: when to call which tool, never promise returns, always surface assumptions.
5. Tests: `backend/tests/test_goals_planning.py` + MCP call coverage patterned on `test_mcp_spending.py`.
6. Docs: update `docs/MCP_SETUP.md` tool list and example prompts; link this spec from `ARCHITECTURE.md` MCP section.
7. Phase 2/3 only after Phase 1 feels useful in Claude Desktop.

Likely touch points (Phase 1):

- `backend/app/services/goals_planning_service.py` (new)
- `backend/mcp_server/schemas.py`
- `backend/mcp_server/server.py`
- `backend/mcp_server/visuals.py` (if charting)
- `backend/tests/test_goals_planning.py` (new)
- `docs/MCP_SETUP.md`

---

## Security & product guardrails

- Read-only planning cannot mutate budgets or goals.
- Proposal path remains create-only with `PROPOSAL_SERVICE_KEY`; Apply is local UI.
- Disclaimers in tool descriptions: assumed returns are hypothetical; past performance unused unless we later add an explicit historical helper.
- Do not expose Plaid tokens, proposal keys, or raw DB paths in tool output.
- Single-user Ledger assumption (`user_id=1`) unchanged.

---

## Example prompts (Claude Desktop)

After Phase 1:

- “Based on my last 3 months, how long to save a $10k emergency fund if I already have $2,400?”
- “I want $5,000 for a trip by next June — what monthly savings do I need, and can I afford it without cutting anything?”
- “If I cut restaurants $100 and subscriptions $40, how does that change the timeline for a $15k car fund?”
- “Plan an investing goal of $50k in 5 years at 0%, 5%, and 7% assumed return using my current surplus.”

After Phase 3:

- “Propose a goal for a $10k emergency fund at $500/mo and a dining budget cut that frees that capacity.”

---

## Relationship to other surfaces

| Surface | Role vs goals planning |
| --- | --- |
| **MCP + Claude** | Primary UX for conversational planning (this feature) |
| **Cash Flow** | Supplies surplus / (later) savings vs invest allocations |
| **Budgets** | Spending caps; cuts free capacity; not the goal itself |
| **Investments** | Holdings/performance context; funding plans use assumed return, not live alpha |
| **Net worth** | Optional later source for `current_amount` |
| **Advisor** | Human Apply/Dismiss for staged goal + budget proposals |

Cash Flow answers: “Where did this month’s money go?”  
Budgets answer: “Am I overspending a category?”  
**Goals planning answers:** “Given that, what monthly save/invest pace reaches my target by when?”

---

## Open questions

1. **Default capacity policy:** lookback average vs min(current, lookback) vs percentile — which feels safest for advice?
2. **Debt payoff:** include interest rate amortization in v1, or treat as simple remaining÷payment until a dedicated debt model exists?
3. **Linked balances:** should Phase 2 `current_amount` auto-fill from a chosen savings/brokerage account, or stay manual?
4. **Multiple concurrent goals:** split capacity pro-rata, priority order, or leave allocation entirely to Claude’s narrative?
5. **UI surface:** is Claude-only enough for v1, or does Ledger need a Goals page that calls the same service?
6. **Cash-flow dependency:** ship Phase 1 on residual surplus now, or wait for Savings/Investments sinks so “invest plan” uses real investment transfers?

**Recommendation:** ship Phase 1 on residual surplus immediately; treat Savings vs Investments allocation as an enhancement when that cash-flow spec lands. Keep debt simple (0% interest math) until demand appears. Defer Goals page until persisted goals (Phase 2) exist.

---

## Acceptance criteria

### Phase 1

- Claude can obtain a capacity breakdown grounded in Ledger cash-flow/spending data (not invented).
- `plan_goal` returns months and/or required monthly contribution for save and invest (with explicit return assumption).
- `plan_goal_from_expenses` shows before/after when spending cuts are supplied.
- Plans mark `affordable` against recommended capacity.
- Unit tests cover 0% and positive return, edge cases (already funded, zero contribution, clamp return).
- `MCP_SETUP.md` documents the new tools and example prompts.
- MCP remains unable to mutate DBs.

### Phase 2

- Goals can be listed and progress reported from `budgets.db`.
- Progress math matches the same planner assumptions stored on the goal.

### Phase 3

- `propose_*` goal kinds create pending proposals only.
- Advisor can Apply / Dismiss / Undo goal proposals.
- Claude receives an `apply_url` and cannot apply server-side.

---

## Current vs target (summary)

| Concept | Today | Target |
| --- | --- | --- |
| Goal entity | Absent | Ephemeral plans (P1) → persisted goals (P2) |
| “How long / how much?” | Claude improvises from spend tools | Deterministic `plan_goal*` MCP tools |
| Capacity | Residual buried in cash flow / savings rate | Explicit `planning_capacity` |
| Expense → plan | Manual multi-tool reasoning | `plan_goal_from_expenses` with optional cuts |
| Mutations | `propose_budget` only | + `set_goal` / contribution proposals (P3) |
| Invest timeline | Performance charts only | Contribution schedules under user-stated return assumptions |
