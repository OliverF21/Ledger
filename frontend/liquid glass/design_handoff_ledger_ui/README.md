# Handoff: Ledger — Personal Finance Dashboard UI

## Overview
This package contains the **UI design** for **Ledger**, a single-user personal finance dashboard that connects to Plaid, categorizes spending, and surfaces dashboards (net worth, spending, budgets, trends). The design covers six screens in a dark, cool-minimal "fintech" aesthetic (Linear / Mercury influence).

This handoff documents **the look and behavior of the front end only**. The backend (FastAPI, Plaid sync, encryption, etc.) is specified in your separate build brief — this README is the visual/interaction source of truth the UI should match.

## About the Design Files
The files in this bundle are **design references created in HTML** — prototypes that show the intended look, layout, and interactions. They are **not production code to copy directly**. They use a small custom streaming-template runtime (`support.js`, `.dc.html`), which is **not** your target stack.

**Your task:** recreate these designs in the project's intended environment — **React + TypeScript + Vite + Tailwind CSS + Recharts** (per the build brief). Use real components, real chart libraries, and real state. Treat the HTML as a pixel reference, not a structure to port.

To preview the design: open `Ledger App.dc.html` in a browser. The left sidebar nav switches between all six screens. `Ledger Overview.dc.html` shows two early design directions side by side — **Direction A (sidebar + cards) was chosen**; that is the one built out in `Ledger App.dc.html`. You can ignore Direction B.

## Fidelity
**High-fidelity (hifi).** Colors, typography, spacing, and component treatments are final. Recreate the UI pixel-faithfully using Tailwind + your component library. Exact values are listed under Design Tokens.

---

## Design Tokens

### Colors
| Token | Hex | Usage |
|---|---|---|
| `bg/app` | `#0d0f14` | App background (main canvas) |
| `bg/sidebar` | `#0b0d11` | Sidebar background |
| `bg/card` | `#11141a` | Card / panel background |
| `bg/card-alt` | `#101319` | Inputs, search field |
| `bg/inset` | `#161a21` / `#161a22` | Chips, pills, active nav, progress tracks |
| `bg/track` | `#1a1e27` / `#15181e` / `#161a21` | Progress-bar tracks |
| `bg/avatar-tile` | `#1a1e27` | Transaction merchant avatar tile |
| `border/default` | `#1c2029` | Card borders |
| `border/subtle` | `#181b22` / `#161920` / `#15181e` | Dividers, sidebar border, table row separators |
| `border/input` | `#20242d` / `#232834` | Input + chip borders |
| `text/primary` | `#e9ebf0` | Primary text |
| `text/heading` | `#eef0f4` | Active nav / strong headings |
| `text/secondary` | `#c2c7cf` | Secondary text |
| `text/muted` | `#9aa0ad` / `#9298a4` | Muted labels, inactive nav |
| `text/faint` | `#7d828e` / `#6b7280` | Captions, table meta |
| `text/faintest` | `#5c626f` | Axis labels, uppercase section labels |
| `accent` | `#5b8def` | Primary accent (brand blue) — buttons, active states, primary chart line/area |
| `accent/on` | `#06070a` | Text/icon color on accent fills |
| `positive` | `#4ec38a` | Income, gains, under-budget |
| `negative` | `#e7705f` | Overspend, credit balances, over-budget |
| `warning` | `#d9a85b` | Pending, re-auth, sandbox badge |
| `cat/teal` | `#4fc4c4` | Category color — Dining |
| `cat/violet` | `#8a7df0` | Category color — Shopping |
| `cat/green` | `#4ec38a` | Category color — Transport/Travel |
| `cat/slate` | `#565c69` | Category color — Other/Utilities/Subscriptions |

Accent is the only brand hue; it is also exposed as a **theme tweak** (alternatives shown: `#5b8def`, `#4ec38a`, `#8a7df0`, `#d98a5b`). Implement accent as a CSS variable / Tailwind theme color so it can be swapped centrally.

### Typography
- **UI font:** `Hanken Grotesk` (Google Fonts), weights 400/500/600/700/800. Humanist, friendly. `-webkit-font-smoothing: antialiased`.
- **Numerals:** all monetary/numeric values use `font-variant-numeric: tabular-nums`. There is an optional **Sans/Mono numerals** theme tweak — Mono switches numerals to `JetBrains Mono`. Tabular numerals are required either way so columns align.
- **Scale (px):** hero net worth 38; large stat 25–26; section/card titles 14 (600); body 13–14; meta/caption 11.5–13; uppercase eyebrow labels 11 (letter-spacing 0.06–0.08em, uppercase, `#5c626f`).
- Headings use `letter-spacing: -0.01em` to `-0.02em` on large numbers.

### Spacing & Shape
- **Card radius:** 14px. **Buttons/inputs/chips:** 9px. **Pills/tags:** 6–7px. **Nav items:** 9px. **Avatar tiles:** 8–9px.
- **Card padding:** 18–22px. **Page padding:** 24px 28px. **Header padding:** 18px 28px.
- **Grid gaps:** 18px between cards/rows; 12px inside table rows.
- **Sidebar width:** 232px fixed. **Progress bar height:** 6–8px, radius 4–5px.
- **Borders:** 1px solid throughout. No drop shadows on inner cards (flat). The top-level app may sit on `#0d0f14` with no shadow; the standalone comparison mock uses `box-shadow: 0 40px 90px -40px rgba(0,0,0,0.8)` for the floating frame only.

### Icons
Simple 1.5–2px stroke icons, 16–17px, `stroke: currentColor`. Use **Lucide** (or similar) equivalents: grid (Overview), list (Transactions), clock-in-circle (Spending), bar-chart (Budgets), line-up (Trends), gear (Settings), search, refresh-cw (Sync), chevron-down, arrow-right, download, arrow-up.

---

## App Shell (persistent chrome)

**Layout:** full-viewport flex row. Left **sidebar** (232px fixed) + **main** (flex-1, column).

### Sidebar (`#0b0d11`, right border `#181b22`, padding 22px 16px)
- **Logo:** 26px accent rounded square (radius 8) containing a 9px black diamond (rotated square), + "Ledger" wordmark (16px/700).
- **Nav list:** 6 items, gap 3px. Each item: flex, gap 11px, padding 9px 11px, radius 9px, 14px text, icon + label.
  - **Active item:** background `#161a22`, text `#eef0f4`, weight 600, plus a 3px accent vertical bar pinned to the left edge (`left:-16px`, top/bottom 9px, radius `0 3px 3px 0`).
  - **Inactive item:** text `#9298a4`, weight 500, transparent background. Hover → background `#121519`, text `#cfd3da`.
- **Linked accounts** (bottom, pushed down with `margin-top:auto`, top border `#181b22`, padding-top 14): uppercase 11px label "Linked accounts", then rows of a 22px colored tile + 13px account name. Sample: Chase Checking (`#1d4ed8`), Robinhood Gold (`#0b0c0f` w/ `#2a2e38` border), Marcus Savings (`#0a7d4b`).

### Header (main top, padding 18px 28px, bottom border `#161920`)
- **Left:** screen title (18px/700) + subtitle (13px, `#7d828e`). Both change per screen (see screens).
- **Right:** search field (200px, `#101319` bg, `#20242d` border, search icon + "Search"), accent **Sync** button (refresh icon + "Sync", `#06070a` text), and a 36px circular avatar ("A", linear-gradient `135deg,#3a4252,#222632`).

### Body
- Scroll container, padding 24px 28px. Renders the active screen.

---

## Screens / Views

> All six screens share the shell above. Titles/subtitles per screen:
> - Overview → "Good morning, Alex" / "Monday, June 30 · last synced 14 min ago"
> - Transactions → "Transactions" / "1,284 transactions · 5 accounts"
> - Spending → "Spending" / "June 2026 · by category"
> - Budgets → "Budgets" / "June 2026 · $4,182 of $5,400 used"
> - Trends → "Trends" / "Last 6 months"
> - Settings → "Settings" / "Manage categories, rules & alerts"

### 1. Overview
**Purpose:** at-a-glance financial health. Vertical stack (gap 18px) of three rows:
- **Row 1 — `grid 2fr / 1fr`:**
  - *Net worth card:* label "Net worth" (13px muted), value **$128,450.62** (38px/700, `-0.02em`), delta chip `+2.4%` (positive bg `rgba(78,195,138,0.13)`, up-arrow icon) + "+$2,980 this month" (faint). Top-right range toggle (`6M` active accent pill / `1Y` inset pill). Below: a **soft-gradient area line chart** (net worth over 6 months, accent line + accent→transparent vertical gradient fill, end-point dot). X-axis month labels Jan–Jun.
  - *Spending-by-category donut card:* label + "June · $4,182". A **donut** (5 segments: Groceries accent / Dining teal / Shopping violet / Transport green / Other slate) with center "$4.2k / spent", and a legend list (colored 8px square + name + right-aligned amount).
- **Row 2 — `grid repeat(3,1fr)` KPI cards:** "Spending this month" $4,182 (↓8% vs last, positive), "Income this month" $5,200 (On track · 1 deposit), "Savings rate" 24% (↑3 pts, positive). Each: 12.5px label, 25px/700 value, 12px sub.
- **Row 3 — `grid 2fr / 1fr`:**
  - *Recent transactions card:* header "Recent transactions" + accent "View all" (navigates to Transactions). 4 rows: 32px merchant avatar tile (initials), name + "account · date" sub, category chip, right-aligned amount (income green & `+`).
  - *Budgets card:* header "Budgets" + "June". 5 rows: label (+ "· over" in negative when over) + "spent / budget" + a progress bar (accent fill; over-budget = full + negative fill). Dining shown over (`$640 / $500`, 100% red).

### 2. Transactions
**Purpose:** browse / filter / recategorize the full ledger.
- **Filter bar (flex, wrap):** search field (flex-1, "Search merchant, note…"), dropdown chips "All accounts ▾", "Category ▾", "Jun 2026 ▾" (each `#101319`/`#20242d`, chevron), and an **Export CSV** button (download icon, inset style) pushed right.
- **Table card:** header row (`grid 2.4fr 1.2fr 1.2fr 0.9fr 1fr`, uppercase 11.5px faint): Merchant · Category · Account · Date · Amount(right).
  - **Rows** (10 sample): avatar tile (30px) + merchant name; under name a **"Pending"** (warning) or **"Split · 2 categories"** (violet) sub-label where applicable. Category shown as an **editable chip** (chip + down-chevron — clicking opens a category picker). Account (muted), date (faint tabular), amount (right, 14px/600; income green).
  - Sample data includes: Whole Foods (Groceries, pending), Blue Bottle (Dining), Costco (Groceries, **split**), Payroll +$5,200 (Income), Netflix, Uber, Amazon, PG&E, Spotify, Delta.
  - **Footer:** "Showing 10 of 1,284" + Prev/Next pager.

### 3. Spending
**Purpose:** category breakdown for a period.
- **Filter row:** "June 2026 ▾" + "All accounts ▾" dropdown chips.
- **`grid 1fr / 2fr`:**
  - *Donut card* (left): large 180px donut (same 5-color scheme), center "$4,182 / total spent", below "↓ 8% vs. May · $4,540" (positive).
  - *Category table* (right): header (Category · Share · vs last · Amount). 7 rows: colored 9px square + name; a horizontal share bar (width = % of top category, category color); "vs last" delta (positive/negative colored); right amount. Categories: Groceries $812, Dining $640, Shopping $520, Travel $430, Transport $310, Utilities $240, Subscriptions $96.

### 4. Budgets
**Purpose:** set and track per-category budgets.
- **Summary card:** `grid repeat(3,1fr) auto`. Total budget $5,400 · Spent $4,182 · Remaining $1,218 (positive) · **+ Add budget** accent button.
- **Budget cards** (`grid repeat(3,1fr)`, 6 cards): header = colored square + name + status tag ("On track" positive tag / "Over" negative tag). Big "spent / budget" (22px/700, budget portion faint). Progress bar (8px, accent; over = full negative). Note line ("$88 left · 10 days" or "$140 over budget"). Dining is the over-budget example.

### 5. Trends
**Purpose:** spending/net-worth over time.
- **Controls:** segmented toggle "Spending"(active accent)/"Net worth"; segmented "6M"(active)/"12M".
- **Multi-line chart card:** title "Spending by category" + legend (3 colored line swatches: Groceries accent, Dining teal, Shopping violet). A **line chart with faint horizontal gridlines**, 3 category lines (accent line also has a soft gradient area fill), month labels Jan–Jun.
- **Per-category sparkline cards** (`grid repeat(3,1fr)`): Groceries $812 (avg $760), Dining $640 (avg $520, negative), Shopping $520 (avg $580, positive) — each with a tiny line sparkline in the category color.

### 6. Settings
**Purpose:** manage connections, rules, alerts, sync. `grid 1fr/1fr`, max-width 1000px.
- **Linked accounts card:** rows with 30px colored tile + name + status ("Healthy · synced 14m ago" positive / "Re-auth needed" warning → accent "Reconnect" action). "+ Link new account" inset button. *(Robinhood Gold Card shown in re-auth state — see Platform Notes.)*
- **Categorization rules card:** rows of `merchant → category` (text → arrow icon → category chip): "Whole Foods → Groceries", "Uber * → Transport", "SQ * Blue Bottle → Dining". "+ New rule" button.
- **Alerts card:** toggle rows — "Budget exceeded" (toggle **on** = accent), "Large transaction" (with a `$500` threshold value chip), "Webhook" (toggle **off** = `#23262f` track, grey knob).
- **Sync card:** "Frequency: Every 6 hours ▾", "Plaid environment: Sandbox" (warning badge), "Last sync: Jun 30 · 09:42", accent **Sync now** button.

---

## Interactions & Behavior
- **Sidebar nav** sets the active screen; the active item shows the inset background + accent left-bar, and the header title/subtitle update. "View all" on the Overview transactions card also navigates to Transactions.
- **Toggle switches** (Settings): 40×23 track, 17px knob; on = accent track + dark knob, off = `#23262f` track + grey knob.
- **Dropdown chips** (filters, category on a transaction row) should open menus — in the prototype they are static affordances; implement as real popovers/menus.
- **Recategorize:** clicking a transaction's category chip opens a category picker; a manual change must be flagged so the next Plaid sync does **not** overwrite it (per build brief).
- **Hover:** inactive nav items lighten; buttons/chips can use a subtle brightness/bg hover. Keep transitions ~120ms.
- **Theme tweaks:** accent color (swap CSS var) and Sans/Mono numerals are global toggles — wire to a settings/theme context.
- **Charts:** use **Recharts** (build brief) — Area for net-worth/category-area with a vertical `linearGradient` (accent at ~0.28 opacity → 0), Line for trend lines, and a donut via `PieChart`+`Pie innerRadius`. Keep gridlines faint (`#15181e`), no axis lines, tabular numeral tooltips.

## State Management
- `activeScreen` (enum: overview | transactions | spending | budgets | trends | settings).
- Theme: `accent` color, `numerals` ('Sans' | 'Mono').
- Data (from backend/Plaid): accounts[], transactions[] (with `pending`, `splits[]`, `categoryOverride`), categories[], budgets[] (category, limit, spent), netWorthSnapshots[], rules[], alertSettings, syncMeta.
- Filters per screen: date range, account, category, search query, amount range; pagination cursor for the transactions table.

## Assets
- **Fonts:** Hanken Grotesk + JetBrains Mono (Google Fonts) — already referenced; self-host in production.
- **Icons:** stroke icons (Lucide-equivalent). No raster assets.
- **Account/merchant logos:** the prototype uses solid colored tiles + initials as placeholders. Swap for real institution logos (Plaid returns institution logos/colors) where available.

## Files
- `Ledger App.dc.html` — the full six-screen app, Direction A (the design to build). Open in a browser to explore; click the sidebar to switch screens.
- `Ledger Overview.dc.html` — early exploration: Direction A vs Direction B side by side. Reference only; **Direction A was chosen.**
- `support.js` — runtime for the prototype files. Not part of the target stack; do not port.

## Platform Notes (from the build brief — surface in UI accordingly)
- **Historical balances:** Plaid does not provide historical balances by default. Net-worth-over-time must be built from **daily balance snapshots** stored by a scheduled job; the trend chart reflects stored snapshots, not Plaid history.
- **Robinhood Gold Card:** linkability depends on Plaid supporting it as an institution and on product/OAuth availability — treat as **not guaranteed**. The Settings "Re-auth needed" state models the common OAuth re-authentication flow; design degrades gracefully if the institution is unsupported.
- **Plaid environment:** default **Sandbox** (badge shown). Production requires Plaid approval.
