"""
SVG Sankey renderer for MCP cash-flow visualizations.

Ports the layout from frontend/src/pages/Spending.tsx so Claude renders the same
income → tunnel → spending/savings ribbon diagram as the OpenTrack Cash Flow page.
"""

from __future__ import annotations

import base64
import html
from dataclasses import dataclass

from app.services.analytics_service import CashFlowData, CashFlowNodeItem
from mcp_server.category_labels import format_category

NODE_W = 20
TUNNEL_W = 40
LABEL_GAP = 8
PAD_Y = 22
MIN_SVG_H = 580
MIN_INCOME_BAND_H = 32
MIN_OUTCOME_BAND_H = 32
INCOME_GAP = 8
OUTCOME_GAP = 8
TUNNEL_FLOW_BIAS = 0.40
LEFT_COL_X = 130
RIGHT_PAD = 172
MIN_FLOW_W = 360
MIN_CHART_W = 720
SAVINGS_COLOR = "#4ec38a"
SAVINGS_ID = "__savings__"
UNALLOCATED_ID = "__unallocated__"
INVESTMENTS_ID = "Investments"
INCOME_HUB = "Income pool"
DEFICIT_NODE = "Deficit"


def _right_items(flow: CashFlowData) -> list[CashFlowNodeItem]:
    """Consumptive spend first, then named sinks / unlabeled savings / Unallocated."""
    return list(flow.spending_categories) + list(flow.allocation_nodes or [])


def _is_allocation_id(node_id: str) -> bool:
    return (
        node_id == SAVINGS_ID
        or node_id == UNALLOCATED_ID
        or node_id == INVESTMENTS_ID
        or node_id.startswith("goal:")
    )


@dataclass(frozen=True)
class SankeyLink:
    source: str
    target: str
    value: float


@dataclass(frozen=True)
class CashFlowSankeyPayload:
    month: str
    total_income: float
    total_spending: float
    savings: float
    spending_pct: float
    savings_pct: float
    income_sources: list[CashFlowNodeItem]
    uses: list[CashFlowNodeItem]
    sankey_links: list[SankeyLink]
    mermaid: str


def _mermaid_label(value: str) -> str:
    cleaned = value.replace('"', '""').strip() or "Unknown"
    if any(char in cleaned for char in ',\n\r'):
        return f'"{cleaned}"'
    return cleaned


def _sankey_row(source: str, target: str, amount: float) -> str:
    if amount <= 0:
        return ""
    return f"{_mermaid_label(source)},{_mermaid_label(target)},{round(amount, 2)}"


def build_cash_flow_sankey_payload(flow: CashFlowData) -> CashFlowSankeyPayload:
    """Build Sankey link rows and a Mermaid chart string from ledger cash-flow data."""
    uses: list[CashFlowNodeItem] = _right_items(flow)

    links: list[SankeyLink] = []
    mermaid_rows: list[str] = ["sankey-beta", ""]

    for source in flow.income_sources:
        label = format_category(source.label)
        links.append(SankeyLink(source=label, target=INCOME_HUB, value=source.amount))
        row = _sankey_row(label, INCOME_HUB, source.amount)
        if row:
            mermaid_rows.append(row)

    for use in uses:
        label = format_category(use.label)
        links.append(SankeyLink(source=INCOME_HUB, target=label, value=use.amount))
        row = _sankey_row(INCOME_HUB, label, use.amount)
        if row:
            mermaid_rows.append(row)

    deficit = round(flow.total_spending - flow.total_income, 2)
    if deficit > 0.01:
        links.append(SankeyLink(source=DEFICIT_NODE, target=INCOME_HUB, value=deficit))
        row = _sankey_row(DEFICIT_NODE, INCOME_HUB, deficit)
        if row:
            mermaid_rows.append(row)

    if len(mermaid_rows) <= 2:
        mermaid = "sankey-beta\n\nNo data,No flow,1"
    else:
        mermaid = "\n".join(mermaid_rows)

    spending_pct = round(flow.total_spending / flow.total_income * 100, 1) if flow.total_income > 0 else 0.0
    savings_pct = round(flow.savings / flow.total_income * 100, 1) if flow.total_income > 0 else 0.0

    return CashFlowSankeyPayload(
        month=flow.month,
        total_income=flow.total_income,
        total_spending=flow.total_spending,
        savings=flow.savings,
        spending_pct=spending_pct,
        savings_pct=savings_pct,
        income_sources=flow.income_sources,
        uses=uses,
        sankey_links=links,
        mermaid=mermaid,
    )


def build_cash_flow_sankey_html(flow: CashFlowData, svg: str | None = None) -> str:
    """Wrap the ribbon SVG in a responsive dark-themed HTML page for Claude artifacts."""
    diagram = svg if svg is not None else build_cash_flow_sankey_svg(flow)
    title = html.escape(f"Cash flow · {flow.month}")
    spending_pct = round(flow.total_spending / flow.total_income * 100) if flow.total_income > 0 else 0
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #0a0c10;
      color: #d4dae4;
      font-family: Inter, system-ui, sans-serif;
      padding: 16px;
    }}
    .card {{
      background: #11141a;
      border: 1px solid #1c2029;
      border-radius: 14px;
      padding: 14px;
      max-width: 100%;
    }}
    .chart {{
      width: 100%;
      overflow: hidden;
    }}
    .chart svg {{
      display: block;
      width: 100%;
      height: auto;
    }}
    .footer {{
      margin-top: 14px;
      text-align: center;
      font-size: 12px;
      color: #6a7a94;
      line-height: 1.6;
    }}
    .footer strong {{ color: #9aa2b2; font-weight: 500; }}
    .caption {{ font-size: 11px; color: #5c626f; margin-top: 4px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="chart">{diagram}</div>
    <div class="footer">
      <div>Total income: <strong>${flow.total_income:,.0f}</strong>
        &nbsp;&nbsp;Total spending: <strong>${flow.total_spending:,.0f} ({spending_pct}%)</strong></div>
      <div class="caption">Flow width represents relative amount</div>
    </div>
  </div>
</body>
</html>"""


def svg_data_uri(svg: str) -> str:
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


@dataclass(frozen=True)
class _LayoutNode:
    id: str
    label: str
    amount: float
    color: str
    x: float
    y: float
    h: float
    label_cy: float
    side: str


@dataclass(frozen=True)
class _LayoutLink:
    id: str
    color: str
    sx: float
    sy0: float
    sy1: float
    tx: float
    ty0: float
    ty1: float
    straight_top: bool = False


@dataclass(frozen=True)
class _Layout:
    left_nodes: list[_LayoutNode]
    right_nodes: list[_LayoutNode]
    left_links: list[_LayoutLink]
    right_links: list[_LayoutLink]
    tunnel_x: float
    tunnel_y: float
    tunnel_h: float
    width: int
    height: int
    left_label_x: float
    right_label_x: float


def _fmt_amount(value: float) -> str:
    return f"{value:,.2f}"


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _display_label(node_id: str, raw_label: str) -> str:
    if node_id == SAVINGS_ID:
        return "Savings"
    if node_id == UNALLOCATED_ID:
        return "Unallocated"
    if node_id.startswith("goal:"):
        return raw_label
    return format_category(raw_label)


def _truncate_label(text: str, max_width: float, *, font_size: float = 13.0) -> str:
    avg_char_w = font_size * 0.56
    max_chars = max(3, int(max_width / avg_char_w))
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 1].rstrip()}…"


def _label_width(text: str, *, font_size: float = 13.0) -> float:
    return max(len(text), 4) * font_size * 0.58


def _compute_chart_width(
    income_sources: list[CashFlowNodeItem],
    right_items: list[CashFlowNodeItem],
) -> tuple[int, float, float, float, float]:
    left_labels = [
        _truncate_label(_display_label(item.id, item.label), LEFT_COL_X - LABEL_GAP - 8)
        for item in income_sources
    ]
    right_labels = [
        _truncate_label(_display_label(item.id, item.label), RIGHT_PAD - LABEL_GAP - 8)
        for item in right_items
    ]

    left_w = max((_label_width(label) for label in left_labels), default=72.0)
    right_w = max((_label_width(label, font_size=13.0) for label in right_labels), default=96.0)
    if any(item.id in {SAVINGS_ID, UNALLOCATED_ID} for item in right_items):
        right_w = max(right_w, 108.0)

    left_node_x = float(LEFT_COL_X)
    left_label_x = left_node_x - LABEL_GAP
    right_node_x = left_node_x + NODE_W + MIN_FLOW_W + NODE_W
    right_label_x = right_node_x + NODE_W + LABEL_GAP
    width = int(max(MIN_CHART_W, right_label_x + right_w + 16, right_node_x + RIGHT_PAD + NODE_W))
    right_node_x = width - RIGHT_PAD - NODE_W
    right_label_x = right_node_x + NODE_W + LABEL_GAP
    return width, left_label_x, right_label_x, left_node_x, right_node_x


def _stack_income_bands(
    items: list[CashFlowNodeItem],
    avail: float,
    node_x: float,
    total_amount: float,
) -> list[_LayoutNode]:
    if not items:
        return []

    gaps = max(0, len(items) - 1) * INCOME_GAP
    flow_area = avail - gaps
    min_total = len(items) * MIN_INCOME_BAND_H
    extra = max(0.0, flow_area - min_total)
    heights = [
        MIN_INCOME_BAND_H + (item.amount / total_amount) * extra
        for item in items
    ]

    nodes: list[_LayoutNode] = []
    y = float(PAD_Y)
    for index, item in enumerate(items):
        height = heights[index]
        nodes.append(
            _LayoutNode(
                id=item.id,
                label=item.label,
                amount=item.amount,
                color=item.color,
                x=node_x,
                y=y,
                h=height,
                label_cy=y + height / 2,
                side="left",
            )
        )
        y += height + (INCOME_GAP if index < len(items) - 1 else 0)
    return nodes


def _stack_outcome_bands(
    items: list[CashFlowNodeItem],
    avail: float,
    node_x: float,
    total_amount: float,
) -> list[_LayoutNode]:
    if not items:
        return []

    gaps = max(0, len(items) - 1) * OUTCOME_GAP
    flow_area = avail - gaps
    min_total = len(items) * MIN_OUTCOME_BAND_H
    extra = max(0.0, flow_area - min_total)
    heights = [
        MIN_OUTCOME_BAND_H + (item.amount / total_amount) * extra
        for item in items
    ]

    nodes: list[_LayoutNode] = []
    y = float(PAD_Y)
    for index, item in enumerate(items):
        height = heights[index]
        nodes.append(
            _LayoutNode(
                id=item.id,
                label=item.label,
                amount=item.amount,
                color=item.color,
                x=node_x,
                y=y,
                h=height,
                label_cy=y + height / 2,
                side="right",
            )
        )
        y += height + (OUTCOME_GAP if index < len(items) - 1 else 0)
    return nodes


def _ribbon(sx: float, sy0: float, sy1: float, tx: float, ty0: float, ty1: float) -> str:
    cx = (sx + tx) / 2
    return (
        f"M{sx} {sy0} C{cx} {sy0},{cx} {ty0},{tx} {ty0} "
        f"L{tx} {ty1} C{cx} {ty1},{cx} {sy1},{sx} {sy1} Z"
    )


def _ribbon_straight_top(
    sx: float, sy0: float, sy1: float, tx: float, ty0: float, ty1: float
) -> str:
    cx = (sx + tx) / 2
    return (
        f"M{sx} {sy0} L{tx} {ty0} L{tx} {ty1} "
        f"C{cx} {ty1},{cx} {sy1},{sx} {sy1} Z"
    )


def _build_layout(flow: CashFlowData, width: int | None = None) -> _Layout | None:
    right_items = _right_items(flow)
    if not flow.income_sources and not right_items:
        return None

    total_income = flow.total_income or 1.0
    total_outflow = sum(item.amount for item in right_items) or 1.0

    chart_w, left_label_x, right_label_x, left_node_x, right_node_x = _compute_chart_width(
        flow.income_sources, right_items
    )
    if width is not None:
        chart_w = max(chart_w, width)
        right_node_x = chart_w - RIGHT_PAD - NODE_W
        right_label_x = right_node_x + NODE_W + LABEL_GAP

    left_count = len(flow.income_sources)
    right_count = len(right_items)
    income_min_h = (
        left_count * MIN_INCOME_BAND_H + max(0, left_count - 1) * INCOME_GAP + PAD_Y * 2
        if left_count
        else MIN_SVG_H
    )
    outcome_min_h = (
        right_count * MIN_OUTCOME_BAND_H + max(0, right_count - 1) * OUTCOME_GAP + PAD_Y * 2
        if right_count
        else MIN_SVG_H
    )
    height = int(max(income_min_h, outcome_min_h, MIN_SVG_H))
    avail = height - PAD_Y * 2

    flow_start = left_node_x + NODE_W
    flow_end = right_node_x
    tunnel_x = flow_start + (flow_end - flow_start) * TUNNEL_FLOW_BIAS - TUNNEL_W / 2
    tunnel_y = float(PAD_Y)
    tunnel_h = float(avail)

    left_nodes = _stack_income_bands(flow.income_sources, avail, left_node_x, total_income)
    right_nodes = _stack_outcome_bands(right_items, avail, right_node_x, total_outflow)

    left_links: list[_LayoutLink] = []
    tunnel_gaps = max(0, len(left_nodes) - 1) * INCOME_GAP
    tunnel_flow = tunnel_h - tunnel_gaps
    offset = 0.0
    for index, src in enumerate(left_nodes):
        ribbon_h = max((src.amount / total_income) * tunnel_flow, 1.0)
        left_links.append(
            _LayoutLink(
                id=src.id,
                color=src.color,
                sx=left_node_x + NODE_W,
                sy0=src.y,
                sy1=src.y + src.h,
                tx=tunnel_x,
                ty0=tunnel_y + offset,
                ty1=tunnel_y + offset + ribbon_h,
                straight_top=index == 0,
            )
        )
        offset += ribbon_h + (INCOME_GAP if index < len(left_nodes) - 1 else 0)

    right_links: list[_LayoutLink] = []
    tunnel_gaps = max(0, len(right_nodes) - 1) * OUTCOME_GAP
    tunnel_flow = tunnel_h - tunnel_gaps
    offset = 0.0
    for index, tgt in enumerate(right_nodes):
        ribbon_h = max((tgt.amount / total_outflow) * tunnel_flow, 1.0)
        right_links.append(
            _LayoutLink(
                id=tgt.id,
                color=SAVINGS_COLOR if tgt.id in {SAVINGS_ID, UNALLOCATED_ID} else tgt.color,
                sx=tunnel_x + TUNNEL_W,
                sy0=tunnel_y + offset,
                sy1=tunnel_y + offset + ribbon_h,
                tx=right_node_x,
                ty0=tgt.y,
                ty1=tgt.y + tgt.h,
            )
        )
        offset += ribbon_h + (OUTCOME_GAP if index < len(right_nodes) - 1 else 0)

    return _Layout(
        left_nodes=left_nodes,
        right_nodes=right_nodes,
        left_links=left_links,
        right_links=right_links,
        tunnel_x=tunnel_x,
        tunnel_y=tunnel_y,
        tunnel_h=tunnel_h,
        width=chart_w,
        height=height,
        left_label_x=left_label_x,
        right_label_x=right_label_x,
    )


def build_cash_flow_sankey_svg(flow: CashFlowData, width: int | None = None) -> str:
    """Return responsive inline SVG for the cash-flow Sankey diagram."""
    layout = _build_layout(flow, width)
    if layout is None:
        empty_w = MIN_CHART_W
        return (
            f'<svg width="100%" height="auto" viewBox="0 0 {empty_w} {MIN_SVG_H}" '
            f'preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">'
            '<text x="50%" y="50%" text-anchor="middle" fill="#6a7a94" font-size="14">'
            "No income or spending recorded this month."
            "</text></svg>"
        )

    parts = [
        f'<svg width="100%" height="auto" viewBox="0 0 {layout.width} {layout.height}" '
        'preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">',
        "<defs>",
        '<linearGradient id="tg" x1="0" y1="0" x2="0" y2="1">',
        '<stop offset="0%" stop-color="#4a6fa5" stop-opacity="0.95" />',
        '<stop offset="100%" stop-color="#1e2d45" stop-opacity="0.95" />',
        "</linearGradient>",
        "</defs>",
    ]

    for link in layout.left_links:
        path = (
            _ribbon_straight_top(link.sx, link.sy0, link.sy1, link.tx, link.ty0, link.ty1)
            if link.straight_top
            else _ribbon(link.sx, link.sy0, link.sy1, link.tx, link.ty0, link.ty1)
        )
        parts.append(f'<path d="{path}" fill="{_escape(link.color)}" opacity="0.28" />')

    for link in layout.right_links:
        path = _ribbon(link.sx, link.sy0, link.sy1, link.tx, link.ty0, link.ty1)
        parts.append(f'<path d="{path}" fill="{_escape(link.color)}" opacity="0.28" />')

    parts.append(
        f'<rect x="{layout.tunnel_x:.1f}" y="{layout.tunnel_y:.1f}" width="{TUNNEL_W}" '
        f'height="{layout.tunnel_h:.1f}" fill="url(#tg)" rx="4" />'
    )
    parts.append(
        f'<text x="{layout.tunnel_x + TUNNEL_W / 2:.1f}" y="{layout.tunnel_y - 6:.1f}" '
        'text-anchor="middle" font-size="10" fill="#6a7a94" letter-spacing="0.10em">INCOME</text>'
    )
    parts.append(
        f'<text x="{layout.tunnel_x + TUNNEL_W / 2:.1f}" y="{layout.tunnel_y + layout.tunnel_h + 14:.1f}" '
        f'text-anchor="middle" font-size="11" fill="#6a7a94">${_fmt_amount(flow.total_income)}</text>'
    )

    for node in layout.left_nodes:
        parts.append(_render_node(node, layout.left_label_x, layout.right_label_x, flow.total_income))
    for node in layout.right_nodes:
        parts.append(_render_node(node, layout.left_label_x, layout.right_label_x, flow.total_income))

    parts.append("</svg>")
    return "\n".join(parts)


def _render_node(
    node: _LayoutNode,
    left_label_x: float,
    right_label_x: float,
    total_income: float,
) -> str:
    label = _truncate_label(
        _display_label(node.id, node.label),
        (LEFT_COL_X - LABEL_GAP - 8) if node.side == "left" else (RIGHT_PAD - LABEL_GAP - 8),
    )
    label_x = left_label_x if node.side == "left" else right_label_x
    text_anchor = "end" if node.side == "left" else "start"
    amount_prefix = "+" if node.side == "left" else ""
    amount_color = (
        SAVINGS_COLOR
        if node.id in {SAVINGS_ID, UNALLOCATED_ID}
        else ("#4ec38a" if node.side == "left" else "#9aa2b2")
    )

    parts = [
        f'<rect x="{node.x:.1f}" y="{node.y:.1f}" width="{NODE_W}" height="{node.h:.1f}" '
        f'fill="{_escape(node.color)}" rx="3" />',
    ]

    if node.id in {SAVINGS_ID, UNALLOCATED_ID} and total_income > 0:
        share = round(node.amount / total_income * 100)
        parts.append(
            f'<text x="{label_x:.1f}" y="{node.label_cy - 8:.1f}" text-anchor="{text_anchor}" '
            f'font-size="13" fill="{SAVINGS_COLOR}" font-weight="600">{_escape(label)}</text>'
        )
        parts.append(
            f'<text x="{label_x:.1f}" y="{node.label_cy + 10:.1f}" text-anchor="{text_anchor}" '
            f'font-size="14" fill="#d4dae4" font-weight="600">${_fmt_amount(node.amount)}</text>'
        )
        parts.append(
            f'<text x="{label_x:.1f}" y="{node.label_cy + 26:.1f}" text-anchor="{text_anchor}" '
            f'font-size="11" fill="#6a7a94">{share}% of income</text>'
        )
    elif node.h >= 22:
        parts.append(
            f'<text x="{label_x:.1f}" y="{node.label_cy - 6:.1f}" text-anchor="{text_anchor}" '
            f'font-size="13" fill="#d4dae4" font-weight="500">{_escape(label)}</text>'
        )
        parts.append(
            f'<text x="{label_x:.1f}" y="{node.label_cy + 11:.1f}" text-anchor="{text_anchor}" '
            f'font-size="12" fill="{amount_color}">{amount_prefix}${_fmt_amount(node.amount)}</text>'
        )
    else:
        parts.append(
            f'<text x="{label_x:.1f}" y="{node.label_cy + 4:.1f}" text-anchor="{text_anchor}" '
            f'font-size="11" fill="#d4dae4">{_escape(label)}</text>'
        )

    return "\n".join(parts)
