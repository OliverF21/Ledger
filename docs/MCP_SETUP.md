# Ledger Analytics MCP

This repo now includes a local read-only MCP server for Claude Desktop.

## What It Exposes

Run the server from the `backend` directory and Claude can call these tools:

- `get_monthly_spending`
- `get_spending_by_category`
- `cash_flow_summary` — income/spending buckets as JSON
- `cash_flow_sankey_data` — **preferred for Sankey** — SQL-backed links + Mermaid chart string Claude renders in chat
- `get_recurring_spend`
- `get_budget_vs_actual`
- `get_investment_performance`
- `search_transactions`

**Advisor (write-intent) tools:**

- `propose_budget` — stages a spend-budget suggestion for you to review and **apply**
  in Ledger's Advisor page. It does **not** change data; it POSTs a pending
  proposal to the running backend (`POST /api/proposals`) using a scoped,
  create-only `PROPOSAL_SERVICE_KEY`. Claude cannot apply proposals — only you
  can, from the app. Requires the backend running and `PROPOSAL_SERVICE_KEY` set
  in `backend/.env`. All other tools stay read-only.
- `propose_goal` — stages a financial goal (emergency fund, sinking fund, invest target)
- `propose_goal_contribution` — stages a monthly contribution change for an existing goal
- `propose_transfer_label` — stages a savings label on a transfer (does **not** set
  `category_user` to the goal name)

**Financial goals (TVM on the backend — Claude must call these, not invent math):**

- `planning_capacity` — leftover income after spending; `recommended_available`
  is `min(current-month residual, lookback average)` for complete months
- `plan_goal` — months-to-goal or required monthly contribution (0% cash, or a
  user-stated annual return as a decimal like `0.07`)
- `plan_goal_from_expenses` — same planner after optional spending cuts
- `list_financial_goals` / `goal_progress` — persisted buckets; progress is opening
  amount plus labeled transfers

See `docs/MCP_FINANCIAL_GOALS_PLAN.md` for the design.

**Chart tools** (inline SVG images — no embed widgets):

- `chart_cash_flow` / `chart_sankey` — ribbon Sankey diagram (like Cash Flow page)

**Data tools for charts Claude can draw itself:**

- `net_worth_data` — net worth history and account breakdown
- `trends_data` — monthly spending vs income series
- `cash_flow_sankey_data` — Sankey link rows, totals, and SVG markup

The server reads from `ledger.db` using short-lived read-only SQLAlchemy sessions and mirrors the app's spending rules:

- excludes `removed`, `pending`, and `hidden` transactions
- applies `user_split_pct` to spending amounts
- prefers `category_user`, then `category_plaid`, then a rolled-up detailed Plaid category
- reuses the backend's additive schema bootstrap once so older local SQLite files pick up any missing columns before queries run

## Local Launch Command

From `backend/`:

```powershell
python -m mcp_server.server
```

## Claude Desktop Config

Add an MCP entry to your Claude Desktop config file on Windows, typically:

`C:\Users\<your-user>\AppData\Roaming\Claude\claude_desktop_config.json`

Example:

```json
{
  "mcpServers": {
    "ledger-analytics": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "D:\\Ledger\\ledger\\backend"
    }
  }
}
```

If you use a specific Python interpreter or virtual environment, replace `"python"` with that full path.

## Start Analyzing In Claude Desktop

1. Quit Claude Desktop if it is open.
2. Add the JSON config above.
3. Start Claude Desktop again.
4. Open a new chat and ask things like:
   - `What did I spend the most on last month?`
   - `Which subscriptions look recurring?`
   - `How am I doing against my June budget?`
   - `What is my current investment performance over the last 6 months?`
   - `Show me a chart of my net worth over the last year`
   - `Chart my spending trends for the last 6 months`
   - `Show a Sankey of my June cash flow` (uses `cash_flow_sankey_data`, Claude draws the Mermaid chart)
   - `Based on my last 3 months, how long to save a $10k emergency fund if I already have $2,400?`
   - `If I cut restaurants $150, how does that change the timeline?`
   - `What monthly investment would reach $50k in 5 years at a 5% assumed return?`

If Claude starts but the tools do not appear, verify the `cwd` is the `backend` folder and that `python -m mcp_server.server` runs successfully there.

## Remote Access Over Tailscale

Claude Desktop's `claude_desktop_config.json` supports local `stdio` servers, not raw remote HTTP URLs. For a private Tailscale-only setup, the practical pattern is:

1. Run the MCP server on your home machine over HTTP.
2. Reach that HTTP endpoint from your travel machine over Tailscale.
3. Use `mcp-remote` locally on the travel machine as a `stdio` bridge for Claude Desktop.

### 1. Run The MCP Server At Home Over HTTP

From `backend/` on the home machine:

```powershell
$env:FASTMCP_TRANSPORT="http"
$env:FASTMCP_HOST="0.0.0.0"
$env:FASTMCP_PORT="8000"
python -m mcp_server.server
```

FastMCP will expose the MCP endpoint at:

`http://<home-machine-ip>:8000/mcp`

If you want to keep it limited to your tailnet, prefer binding to the machine's Tailscale IP instead of `0.0.0.0` when possible.

### 2. Point Claude Desktop At The Tailscale Endpoint

On the travel machine, configure Claude Desktop to launch the `mcp-remote` bridge:

```json
{
  "mcpServers": {
    "ledger-analytics-remote": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://100.x.y.z:8000/mcp",
        "--transport",
        "http-only"
      ]
    }
  }
}
```

Replace `100.x.y.z` with the home machine's Tailscale IP or MagicDNS hostname.

### Important Tailscale Note

The Claude Desktop **Connectors UI** is for remote MCP servers that Anthropic's cloud can reach over public HTTPS. A Tailscale-only private address will usually **not** work there, because Anthropic cannot reach your private tailnet.

For Tailscale/private access:

- use the local JSON config plus `mcp-remote`
- keep the server private on your tailnet

For a true internet-hosted connector:

- host the MCP server on public HTTPS
- add authentication
- register it through Claude Desktop's Connectors UI instead

## Example Prompts

Once Claude Desktop picks up the server, prompts like these should work well:

- `What did I spend the most on last month?`
- `Show my largest dining transactions in June 2026.`
- `Break down spending from 2026-06-01 through 2026-06-30 by category.`
- `Show my recurring subscriptions from the last 12 months.`
- `How far over or under budget am I this month?`
- `Summarize my investment performance and biggest positions.`
- `Chart my net worth over the last 6 months.`
- `Show a Sankey of my June 2026 cash flow`
- `Where did my money go last month? Show the flow diagram.`
- `Based on my last 3 months, how long to save a $10k emergency fund if I already have $2,400?`
- `Propose a $10k emergency fund at $500/mo and a dining budget cut that frees that capacity.`
- `Propose labeling that $500 Ally transfer as Vacation.`

## Chart Tools

`chart_cash_flow` and `chart_sankey` return an **inline SVG image** in the tool result (no Prefab / MCP App embed). For net worth and trends, use `net_worth_data` and `trends_data` — Claude can chart the JSON in chat.

## Notes

- `budgets.db` is queried by `get_budget_vs_actual`, `list_financial_goals`, and
  `goal_progress` (read-only).
- `propose_budget` stages proposals (via the backend API, not a direct write) in
  the `proposals` table. `propose_goal`, `propose_goal_contribution`, and
  `propose_transfer_label` use the same create-only path.
- The server is `stdio`-based and does not open an HTTP port. `propose_*` tools
  make an outbound HTTP call — to the Ledger backend on
  `LEDGER_API_URL` (default `http://127.0.0.1:8000`), so that backend must be
  running. The read tools work directly against the SQLite files regardless.
