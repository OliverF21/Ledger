# Instructions for Claude Code / Cursor: Ledger "Liquid Glass" Redesign

## Scope — read this first

Apply the visual redesign described below to **the entire app** —
`Sidebar.tsx`, `Header.tsx`, `Overview.tsx`, `Transactions.tsx`, `Spending.tsx`,
`Budgets.tsx`, `Investments.tsx`, `Trends.tsx`, `Subscriptions.tsx`,
`Settings.tsx`, `AlertsPanel.tsx`, `index.css`, `tailwind.config.js`.

**EXCLUDE the pie/donut chart entirely.** In `Overview.tsx` and `Spending.tsx`,
do **not** touch the `<PieChart>`, `<Pie>`, `<Cell>`, `<Sector>` elements, their
props (`innerRadius`, `outerRadius`, `paddingAngle`, `activeIndex`,
`activeShape`, `onMouseEnter/Leave/Click`), the category color values they
render, or the hover/click interaction logic around `hoveredSlice` /
`selectedSlice`. You may restyle the **card container** the chart sits inside
(background, border, radius, shadow — same treatment as every other card),
but the chart itself, its colors, and its behavior must remain byte-for-byte
as they are today. If in doubt, leave a chart-related line alone.

Everything else — page backgrounds, card surfaces, sidebar, header, buttons,
inputs, chips, badges, progress bars, typography colors — is in scope.

---

## The visual system to implement

This is a dark "liquid glass" aesthetic: a vivid, slowly-drifting aurora of
color sits behind everything; UI surfaces are luminous frosted panels that
let that color glow through, with bright top-edge highlights and soft
depth shadows — not flat dark cards with thin borders.

### 1. Page background (replaces `bg-ledger-bg` / `#0d0f14` flat fill)

Add a fixed full-viewport background layer behind the app shell:

```css
/* base */
background: linear-gradient(160deg, #0a0a16 0%, #060710 45%, #020204 100%);
```

Inside it, an absolutely-positioned, blurred, animated aurora layer:

```css
position: absolute;
inset: -30%;
filter: blur(40px);
animation: drift 40s ease-in-out infinite alternate;
background:
  radial-gradient(760px 660px at 16% 20%, rgba(120,150,255,0.62), transparent 62%),
  radial-gradient(820px 720px at 84% 10%, rgba(90,224,206,0.52), transparent 60%),
  radial-gradient(780px 840px at 60% 96%, rgba(190,140,255,0.58), transparent 60%),
  radial-gradient(620px 620px at 4% 94%, rgba(255,150,120,0.34), transparent 60%),
  radial-gradient(640px 640px at 98% 82%, rgba(255,140,200,0.34), transparent 60%);
```

```css
@keyframes drift {
  0%   { transform: translate(-4%, -3%) rotate(-3deg) scale(1.12); }
  100% { transform: translate(4%, 3%) rotate(3deg) scale(1.18); }
}
```

Add both to `index.css` (base layer + keyframes) and mount the aurora div once
at the root of the app shell (e.g. in `App.tsx`, as a fixed sibling behind
everything else, `z-index: 0`; give the real app shell `position: relative;
z-index: 1`).

### 2. Glass panel recipe (replaces every `bg-ledger-card border border-ledger-border`)

Every card, the sidebar, the header, chips/pills, and buttons use this fill:

```css
background: linear-gradient(140deg,
  rgba(255,255,255,0.24),
  rgba(255,255,255,0.085) 34%,
  rgba(255,255,255,0.06) 70%,
  rgba(255,255,255,0.13));
border: 1px solid rgba(255,255,255,0.22);
box-shadow:
  inset 0 1px 0 rgba(255,255,255,0.55),
  inset 0 0 30px rgba(255,255,255,0.06),
  0 20px 50px -28px rgba(10,10,40,0.55),
  0 0 46px rgba(150,170,255,0.10);
border-radius: 22px; /* cards. use 26px for the sidebar, 9px for buttons/chips */
```

Add this as a Tailwind component class (e.g. `.glass-card`) or a set of CSS
custom properties in `tailwind.config.js` / `index.css` so it can be reused
via `className="glass-card"` rather than repeating the raw values everywhere.

Smaller surfaces (search input, filter chips, dropdown chips, table header)
use the same gradient/border but a smaller radius (9px) and no shadow.

Secondary text colors should be lifted for legibility on glass — swap
`text-ledger-text-faint` etc. to `rgba(255,255,255,0.60)` / `0.52` / `0.74`
tiers rather than the flat hex values currently in `tailwind.config.js`.

### 3. Floating rounded sidebar (replaces the full-height rectangle)

The sidebar and main content no longer sit flush against the viewport edges.
Wrap them with `padding: 16px; gap: 16px;` on their flex row container, and
give the sidebar its own glass treatment with a **26px radius** (not 14px)
so it reads as a floating card, not a bar:

```css
/* sidebar */
border-radius: 26px;
border: 1px solid rgba(255,255,255,0.20);
background: linear-gradient(160deg, rgba(255,255,255,0.14), rgba(255,255,255,0.04));
backdrop-filter: blur(30px) saturate(150%);
-webkit-backdrop-filter: blur(30px) saturate(150%);
box-shadow:
  inset 0 1px 0 rgba(255,255,255,0.5),
  inset 0 0 30px rgba(255,255,255,0.05),
  0 24px 60px -22px rgba(0,0,0,0.75),
  0 0 46px rgba(150,170,255,0.10);
```

Give the main content column the same rounding (26px) and a subtle border
(`rgba(255,255,255,0.14)`) so both floating panels read as one composition.

**Nav item spacing:** let the nav list grow to fill the space between the
logo and the "Linked accounts" footer, and center it vertically with a more
open gap (`flex:1; display:flex; flex-direction:column; justify-content:
center; gap:12px;`) rather than the current tightly-packed top-aligned list.

`backdrop-filter` blur is safe on the sidebar (single surface, not stacked).
Do **not** add real `backdrop-filter` blur to every card in the scrolling
content — stacking many blurred layers inside a scroll container is
unreliable across browsers/GPUs. The gradient-fill recipe in §2 already
reads as frosted glass because the aurora behind it is pre-blurred; that's
sufficient and is the reliable approach used throughout.

### 4. Header

Same glass treatment as cards, with a bottom border. Buttons ("Link Account",
"Sync") get the glass-chip and accent-filled treatments respectively (Sync
stays a solid accent-colored pill — the one deliberately opaque, high-contrast
element in the header, same as today).

### 5. Alerts

`AlertsPanel` gets the same glass-card treatment, single row per alert,
warning-colored icon (`#d9a85b` for large-transaction, `ledger-negative` for
budget-exceeded) — no structural change to when/what it renders.

---

## What NOT to change

- Any Recharts `<PieChart>` / `<Pie>` / `<Cell>` / `<Sector>` markup, props,
  or interaction handlers (see Scope above).
- Data fetching, hooks (`useAnalytics`, `useAccounts`, `useBudgets`, etc.),
  routing/state logic, and copy/labels.
- The `AreaChart` / line-chart data and structure in the Net Worth card —
  only its container gets the glass treatment; the gradient fill on the
  chart line itself (`#5b8def` accent stop) stays as-is.

## Visual reference

Open `Ledger App.dc.html` in this folder in a browser — it is the pixel
reference for the redesign, built with real current data from this app
(nav order: Overview, Transactions, Cash Flow, Budgets, Investments, Trends,
Subscriptions, Settings). `Ledger Overview.dc.html` shows earlier direction
exploration for context only. `support.js` is the prototype runtime — not
part of your stack, do not port it.
