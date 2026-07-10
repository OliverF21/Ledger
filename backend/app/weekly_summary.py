"""
Weekly spending summary: computation + HTML rendering.

Leads with *budget pace* — the insight that budgets are monthly but this email
is weekly, so the useful signal is "you're 40% through the month but have used
65% of your Dining budget." Pace = (budget used %) − (month elapsed %):
positive means spending faster than the month is passing (on track to overrun),
negative means comfortably under pace.

Reuses get_budget_items() so budget spend numbers match the app exactly, and
mirrors the app's spending rules for the trailing-week recap (excludes removed,
pending, hidden, and transfer/loan-payment categories; applies user_split_pct).

Pure and side-effect-free except for read-only DB queries; sending lives in
send_weekly_summary() at the bottom, which is the scheduler/route entrypoint.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.analytics_shared import is_excluded_from_spending, month_bounds, rollup_category_key
from app.email_sender import get_resend_api_key, send_email
from app.models import Transaction, User
from app.routes.budgets import get_budget_items

logger = logging.getLogger("ledger")

# How many top categories to list in the week recap.
TOP_CATEGORY_COUNT = 5


@dataclass(frozen=True)
class BudgetPaceItem:
    category: str
    spent: float
    limit: float
    color: str
    used_pct: float          # spent / limit, as 0-100+ (can exceed 100)
    pace_delta: float        # used_pct - month_elapsed_pct; >0 = ahead of pace
    projected: float         # spent extrapolated to full month at current rate

    @property
    def status(self) -> str:
        if self.spent > self.limit:
            return "over"
        if self.pace_delta > 10:
            return "ahead"      # spending faster than the month is passing
        if self.pace_delta < -10:
            return "under"      # comfortably below pace
        return "on_track"


@dataclass(frozen=True)
class CategorySpend:
    category: str
    amount: float


@dataclass(frozen=True)
class WeeklySummary:
    name: str | None          # friendly display name for the greeting, if set
    week_start: date
    week_end: date            # inclusive last day of the trailing 7-day window
    week_total: float
    prev_week_total: float
    top_categories: list[CategorySpend]

    month_key: str
    month_elapsed_pct: float
    budgets: list[BudgetPaceItem]
    total_spent: float
    total_limit: float

    @property
    def wow_change_pct(self) -> float | None:
        """Week-over-week change as a percentage, or None if no prior baseline."""
        if self.prev_week_total <= 0:
            return None
        return (self.week_total - self.prev_week_total) / self.prev_week_total * 100

    @property
    def has_budgets(self) -> bool:
        return bool(self.budgets)


def _format_category(raw: str) -> str:
    """
    Human-readable label for a raw Plaid PFC category constant, e.g.
    "TRANSPORTATION" -> "Transportation", "FOOD_AND_DRINK" -> "Food & Drink".
    Ports the generic fallback branch of frontend/src/utils/categories.ts's
    formatCategory() (underscore -> space, title-case, "And" -> "&"); skips
    porting its hand-curated OVERRIDES map since that only refines
    sub-categories, and rollup_category here only ever returns top-level
    parent keys, for which the fallback alone already matches the override
    table's output exactly.
    """
    if not raw:
        return "Uncategorized"
    segment = raw.split(".")[-1] if "." in raw else raw
    words = segment.lower().replace("_", " ").split(" ")
    titled = " ".join(w.capitalize() for w in words if w)
    return re.sub(r"\bAnd\b", "&", titled)


def _spend_in_window(db: Session, start: date, end: date) -> tuple[float, dict[str, float]]:
    """
    Total effective spend and per-display-category spend for [start, end).
    Mirrors the app's spending rules (positive amounts, exclude transfers/
    loan payments/pending/removed/hidden, apply user split).
    """
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.removed == False,   # noqa: E712
            Transaction.pending == False,   # noqa: E712
            Transaction.hidden == False,    # noqa: E712
            Transaction.amount > 0,
            Transaction.date >= start,
            Transaction.date < end,
        )
        .all()
    )
    total = 0.0
    by_category: dict[str, float] = {}
    for t in txns:
        if is_excluded_from_spending(
            rollup_category_key(t.category_user, t.category_plaid, t.category_plaid_detailed)
        ):
            continue
        eff = float(t.amount) * float(t.user_split_pct or 1)
        total += eff
        cat = t.rollup_category or "Uncategorized"
        by_category[cat] = by_category.get(cat, 0.0) + eff
    return total, by_category


def compute_weekly_summary(db: Session, bdb: Session, today: date | None = None) -> WeeklySummary:
    """
    Build the summary as of `today` (defaults to date.today()). `db` is a
    read-only ledger.db session; `bdb` a budgets.db session.
    """
    today = today or date.today()

    # Trailing 7 days ending yesterday (a full completed week; today is partial).
    week_end = today - timedelta(days=1)          # inclusive
    week_start = week_end - timedelta(days=6)
    prev_start = week_start - timedelta(days=7)

    # Query windows are end-exclusive.
    week_total, week_by_cat = _spend_in_window(db, week_start, week_end + timedelta(days=1))
    prev_total, _ = _spend_in_window(db, prev_start, week_start)

    top = sorted(week_by_cat.items(), key=lambda kv: kv[1], reverse=True)[:TOP_CATEGORY_COUNT]
    top_categories = [CategorySpend(category=_format_category(c), amount=round(a, 2)) for c, a in top]

    # Budget pace, month-to-date.
    month_key = f"{today.year:04d}-{today.month:02d}"
    m_start, m_end = month_bounds(today.year, today.month)
    days_in_month = (m_end - m_start).days
    # Fraction of the month elapsed *through today* (day 1 => 1/N, not 0).
    month_elapsed_pct = min((today.day / days_in_month) * 100, 100.0)

    budget_items = get_budget_items(bdb, db, month_key)
    budgets: list[BudgetPaceItem] = []
    for b in budget_items:
        used_pct = (b.spent / b.limit * 100) if b.limit > 0 else 0.0
        elapsed_frac = month_elapsed_pct / 100 or 1e-9
        budgets.append(BudgetPaceItem(
            category=b.category,
            spent=b.spent,
            limit=b.limit,
            color=b.color,
            used_pct=round(used_pct, 1),
            pace_delta=round(used_pct - month_elapsed_pct, 1),
            projected=round(b.spent / elapsed_frac, 2),
        ))

    # Sort worst-pace first so the email leads with what needs attention.
    budgets.sort(key=lambda x: x.pace_delta, reverse=True)

    user = db.query(User).filter(User.id == 1).first()
    name = (user.display_name if user and user.display_name else None)

    return WeeklySummary(
        name=name,
        week_start=week_start,
        week_end=week_end,
        week_total=round(week_total, 2),
        prev_week_total=round(prev_total, 2),
        top_categories=top_categories,
        month_key=month_key,
        month_elapsed_pct=round(month_elapsed_pct, 1),
        budgets=budgets,
        total_spent=round(sum(b.spent for b in budgets), 2),
        total_limit=round(sum(b.limit for b in budgets), 2),
    )


# ── HTML rendering ────────────────────────────────────────────────────────────
#
# Mirrors the live app's "liquid glass" design tokens (frontend/tailwind.config.js,
# frontend/src/index.css, and the per-category budget card in Budgets.tsx) rather
# than inventing separate email styling. Email clients can't do backdrop-filter
# blur or reliably render CSS gradients (Outlook desktop in particular), so the
# glass-card gradient fill is kept as a best-effort progressive enhancement with
# a solid bgcolor attribute fallback approximating the same surface.

_TEXT_PRIMARY = "#e9ebf0"
_TEXT_HEADING = "#eef0f4"
_TEXT_SECONDARY = "rgba(255,255,255,0.74)"
_TEXT_FAINT = "rgba(255,255,255,0.60)"
_TEXT_FAINTEST = "rgba(255,255,255,0.52)"
_ACCENT = "#5b8def"
_ACCENT_ON = "#06070a"
_POSITIVE = "#4ec38a"
_NEGATIVE = "#e7705f"
_WARNING = "#d9a85b"

# Lucide's "BookOpen" glyph — the app's actual logo mark (Sidebar.tsx), not a
# lettermark. Path data + stroke width (2.25) copied verbatim from
# frontend/node_modules/lucide-react/dist/esm/icons/book-open.js so the email
# renders the identical icon, just inlined as static SVG (email clients can't
# load the lucide-react component).
_BOOK_OPEN_ICON = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
    f'stroke="{_ACCENT_ON}" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" '
    'style="vertical-align:middle;">'
    '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>'
    '<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>'
    '</svg>'
)
_TRACK = "#1a1e27"

# card status pill: mirrors Budgets.tsx's "Over" / "On track" tags exactly
# (text-[11px] px-[6px] py-[2px] rounded-[4px], bg = color at 10% alpha).
# "ahead"/"under" are unique to this email (pace vs. days-elapsed has no
# equivalent in the app, which only tracks spent-vs-limit) but use the same
# pill shape and the app's warning/positive tokens.
_STATUS_STYLE = {
    "over":     (_NEGATIVE, "Over"),
    "ahead":    (_WARNING, "Ahead of pace"),
    "on_track": (_POSITIVE, "On track"),
    "under":    (_POSITIVE, "Under pace"),
}

# Card gradient fill (.glass-card in index.css), with a flat bgcolor fallback
# for clients that ignore CSS gradients.
_CARD_BG_FALLBACK = "#141821"
_CARD_GRADIENT = (
    "linear-gradient(140deg, rgba(255,255,255,0.24), rgba(255,255,255,0.085) 34%, "
    "rgba(255,255,255,0.06) 70%, rgba(255,255,255,0.13))"
)
_CARD_BORDER = "1px solid rgba(255,255,255,0.22)"

# Page background fallback + gradient (.aurora-root in index.css).
_PAGE_BG_FALLBACK = "#050914"
_PAGE_GRADIENT = "linear-gradient(160deg, #07101f 0%, #050914 45%, #010204 100%)"


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _tabular(inner: str, extra: str = "") -> str:
    return f'<span style="font-variant-numeric:tabular-nums;{extra}">{inner}</span>'


def _bar(used_pct: float, elapsed_pct: float, color: str) -> str:
    """
    A budget progress bar matching Budgets.tsx (7px height, 4px radius,
    #1a1e27 track, category color fill / negative when over), plus a thin
    marker at elapsed_pct showing where "on pace" sits today — the one
    element with no app equivalent, since the app doesn't track day-of-month
    pace, only spent-vs-limit.
    """
    fill = min(used_pct, 100)
    over = used_pct > 100
    bar_color = _NEGATIVE if over else color
    marker = min(max(elapsed_pct, 0), 100)
    return (
        f'<div style="position:relative;background:{_TRACK};border-radius:4px;'
        f'height:7px;width:100%;overflow:hidden;">'
        f'<div style="background:{bar_color};height:7px;width:{fill:.1f}%;border-radius:4px;"></div>'
        f'</div>'
        f'<div style="position:relative;height:0;">'
        f'<div style="position:absolute;top:-9px;left:{marker:.1f}%;width:1.5px;'
        f'height:11px;background:rgba(255,255,255,0.5);border-radius:1px;"></div></div>'
    )


def render_html(s: WeeklySummary) -> str:
    """Inline-styled HTML matching the live app's liquid-glass design tokens."""
    # %-d is not portable on Windows; build the range manually instead.
    week_range = f"{s.week_start.strftime('%b')} {s.week_start.day} – {s.week_end.strftime('%b')} {s.week_end.day}"
    greeting_line = f"Hi {s.name}, here's your week" if s.name else "Here's your week"

    wow = s.wow_change_pct
    if wow is None:
        wow_line = f'<span style="color:{_TEXT_FAINT};">No prior-week comparison yet.</span>'
    else:
        arrow = "▲" if wow >= 0 else "▼"
        # Matches the Overview delta-chip convention: less spending = positive/green.
        wow_color = _NEGATIVE if wow >= 0 else _POSITIVE
        wow_line = (
            f'<span style="display:inline-block;padding:3px 8px;border-radius:7px;'
            f'background:{wow_color}21;color:{wow_color};font-weight:600;font-size:12px;">'
            f'{arrow} {abs(wow):.0f}%</span>'
            f'<span style="color:{_TEXT_FAINT};"> vs. the week before ({_money(s.prev_week_total)})</span>'
        )

    # Budget pace rows (the lead section) — one card per category, mirroring
    # the Budgets.tsx per-category card (swatch, name, status pill, bold
    # spent/limit line, progress bar, faint note).
    if s.has_budgets:
        rows = []
        for b in s.budgets:
            color, label = _STATUS_STYLE[b.status]
            if b.status == "over":
                note = f"{_money(b.spent - b.limit)} over budget"
            else:
                note = f"{_money(max(b.limit - b.spent, 0))} remaining · projected {_money(b.projected)} by month end"
            rows.append(f"""
            <tr><td style="padding:0 0 18px;">
              <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                <tr>
                  <td style="padding:0 0 8px;">
                    <span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:{b.color};vertical-align:middle;margin-right:8px;"></span>
                    <span style="font-size:13px;font-weight:600;color:{_TEXT_PRIMARY};vertical-align:middle;">{b.category}</span>
                    <span style="float:right;font-size:11px;font-weight:600;color:{color};background:{color}1a;padding:2px 6px;border-radius:4px;">{label}</span>
                  </td>
                </tr>
                <tr><td style="padding:0 0 8px;font-size:14px;font-weight:700;color:{_TEXT_PRIMARY};">
                  {_tabular(_money(b.spent))}
                  <span style="font-weight:400;color:{_TEXT_FAINT};">{_tabular('/ ' + _money(b.limit))}</span>
                </td></tr>
                <tr><td style="padding:0 0 10px;">{_bar(b.used_pct, s.month_elapsed_pct, b.color)}</td></tr>
                <tr><td style="font-size:11.5px;color:{_TEXT_FAINT};">{note}</td></tr>
              </table>
            </td></tr>""")
        budget_section = f"""
        <p style="font-size:12px;color:{_TEXT_FAINT};margin:0 0 16px;">
          {s.month_elapsed_pct:.0f}% through {date(int(s.month_key[:4]), int(s.month_key[5:7]), 1).strftime('%B')} ·
          {_money(s.total_spent)} of {_money(s.total_limit)} budgeted ·
          the marker on each bar shows where "on pace" sits today
        </p>
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
          {''.join(rows)}
        </table>"""
    else:
        budget_section = (
            f'<p style="font-size:13px;color:{_TEXT_FAINT};">No budgets set for this month yet. '
            f'Add budgets in the app to see pace tracking here.</p>'
        )

    # Week recap top categories — plain list (the app has no fixed per-category
    # color mapping outside of budgets, so top categories that aren't budgeted
    # get no swatch, same as Transactions/Spending views without a budget).
    if s.top_categories:
        cat_rows = "".join(
            f"""<tr>
                  <td style="padding:6px 0;font-size:13px;color:{_TEXT_SECONDARY};border-top:1px solid rgba(255,255,255,0.08);">{c.category}</td>
                  <td style="padding:6px 0;font-size:13px;font-weight:600;color:{_TEXT_PRIMARY};text-align:right;border-top:1px solid rgba(255,255,255,0.08);">{_tabular(_money(c.amount))}</td>
                </tr>"""
            for c in s.top_categories
        )
        recap_table = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
          {cat_rows}
        </table>"""
    else:
        recap_table = f'<p style="font-size:13px;color:{_TEXT_FAINT};">No spending recorded this week.</p>'

    return f"""\
<div style="margin:0;padding:0;background:{_PAGE_BG_FALLBACK};background:{_PAGE_GRADIENT};">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="{_PAGE_BG_FALLBACK}" style="background:{_PAGE_GRADIENT};padding:32px 16px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" bgcolor="{_CARD_BG_FALLBACK}" style="max-width:600px;width:100%;background:{_CARD_GRADIENT};border:{_CARD_BORDER};border-radius:22px;overflow:hidden;font-family:'Hanken Grotesk',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <tr><td style="padding:28px 32px 20px;border-bottom:1px solid rgba(255,255,255,0.16);">
    <table cellpadding="0" cellspacing="0"><tr>
      <td style="width:26px;height:26px;background:{_ACCENT};border-radius:8px;text-align:center;vertical-align:middle;">
        {_BOOK_OPEN_ICON}
      </td>
      <td style="padding-left:9px;font-size:15px;font-weight:700;color:{_TEXT_HEADING};vertical-align:middle;">Ledger</td>
      <td style="padding-left:10px;font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:{_TEXT_FAINTEST};vertical-align:middle;">Weekly Summary</td>
    </tr></table>
    <div style="font-size:20px;color:{_TEXT_HEADING};font-weight:700;margin-top:14px;letter-spacing:-0.01em;">{greeting_line}</div>
    <div style="font-size:13px;color:{_TEXT_FAINT};margin-top:2px;">{week_range}</div>
  </td></tr>

  <tr><td style="padding:20px 32px 4px;">
    <div style="font-size:14px;font-weight:600;color:{_TEXT_PRIMARY};margin-bottom:12px;">Budget pace</div>
    {budget_section}
  </td></tr>

  <tr><td style="padding:4px 32px;"><div style="border-top:1px solid rgba(255,255,255,0.12);margin:8px 0;"></div></td></tr>

  <tr><td style="padding:4px 32px 8px;">
    <div style="font-size:14px;font-weight:600;color:{_TEXT_PRIMARY};margin-bottom:10px;">This week</div>
    <div style="font-size:26px;color:{_TEXT_HEADING};font-weight:700;letter-spacing:-0.01em;">{_tabular(_money(s.week_total))}</div>
    <div style="font-size:12.5px;margin:6px 0 14px;">{wow_line}</div>
    {recap_table}
  </td></tr>

  <tr><td style="padding:20px 32px 28px;">
    <div style="font-size:11px;color:{_TEXT_FAINTEST};">
      Trailing 7 days ({week_range}). Spending excludes transfers, credit-card payments, pending and hidden transactions —
      matching the app. You're receiving this because a weekly summary is configured in Ledger.
    </div>
  </td></tr>
</table>
</td></tr>
</table>
</div>"""


def render_subject(s: WeeklySummary) -> str:
    over = [b for b in s.budgets if b.status == "over"]
    ahead = [b for b in s.budgets if b.status == "ahead"]
    if over:
        lead = f"{len(over)} budget{'s' if len(over) != 1 else ''} over"
    elif ahead:
        lead = f"{len(ahead)} ahead of pace"
    else:
        lead = "on track"
    return f"Ledger weekly: {_money(s.week_total)} spent · {lead}"


# ── Orchestration (scheduler / route entrypoint) ──────────────────────────────

def _config(db: Session) -> tuple[str, str] | None:
    """
    Returns (api_key, recipient) if the weekly email is fully configured, else
    None. The API key is BYOK (app_config, else RESEND_API_KEY env var — see
    email_sender.get_resend_api_key); the on/off toggle and recipient address
    are user-editable in Settings and live on the User row
    (weekly_email_enabled / weekly_email_to).
    """
    api_key = get_resend_api_key()
    if not api_key:
        return None
    user = db.query(User).filter(User.id == 1).first()
    if not user or not user.weekly_email_enabled:
        return None
    to = (user.weekly_email_to or "").strip()
    if not to:
        return None
    return api_key, to


def send_weekly_summary(db: Session, bdb: Session, force: bool = False) -> bool:
    """
    Compute and send the weekly summary email. No-op (returns False) unless
    RESEND_API_KEY is set and the weekly email is enabled with a recipient in
    Settings. `force` is unused here but kept for symmetry with the manual
    send-now route. Returns True on a sent email.
    """
    cfg = _config(db)
    if cfg is None:
        logger.debug("Weekly email skipped: not configured (RESEND_API_KEY / Settings toggle / recipient)")
        return False
    _, to = cfg

    summary = compute_weekly_summary(db, bdb)
    html = render_html(summary)
    subject = render_subject(summary)

    ok = send_email(to=to, subject=subject, html=html)
    if ok:
        logger.info("Weekly summary email sent to %s", to)
    return ok
