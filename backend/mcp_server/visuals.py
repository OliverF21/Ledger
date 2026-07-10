"""
Inline image chart responses for the MCP server (no Prefab / MCP Apps).
"""

from __future__ import annotations

import re

from fastmcp.tools.base import ToolResult
from fastmcp.utilities.types import Image
from mcp.types import TextContent

from app.services.analytics_service import CashFlowData


def _svg_for_image(svg: str) -> bytes:
    """Normalize responsive SVG markup for inline image display."""
    match = re.search(r'viewBox="0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)"', svg)
    if match:
        width, height = match.group(1), match.group(2)
        svg = re.sub(r'width="100%"', f'width="{width}"', svg)
        svg = re.sub(r'height="auto"', f'height="{height}"', svg)
    return svg.encode("utf-8")


def cash_flow_chart_result(flow: CashFlowData, svg: str) -> ToolResult:
    """Return a cash-flow Sankey as an inline SVG image plus a short summary."""
    spending_pct = round(flow.total_spending / flow.total_income * 100) if flow.total_income > 0 else 0
    summary = (
        f"Cash flow · {flow.month}\n"
        f"Income: ${flow.total_income:,.2f}\n"
        f"Spending: ${flow.total_spending:,.2f} ({spending_pct}%)\n"
        f"Savings: ${flow.savings:,.2f}"
    )
    return ToolResult(
        content=[
            TextContent(type="text", text=summary),
            Image(data=_svg_for_image(svg), format="svg"),
        ],
        structured_content={
            "month": flow.month,
            "total_income": flow.total_income,
            "total_spending": flow.total_spending,
            "savings": flow.savings,
            "spending_pct": spending_pct,
        },
    )
