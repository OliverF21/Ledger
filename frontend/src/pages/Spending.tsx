import { useState, useEffect, useRef, useCallback } from 'react'
import { apiFetch } from '../api/client'
import { CHART_POSITIVE, CHART_TEXT } from '../utils/chartTheme'
import { formatCategory } from '../utils/categories'
import { useOnSyncComplete } from '../hooks/useSync'
import { getMonthOptions } from '../utils/months'

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const MONTH_OPTIONS = getMonthOptions(12)

// ── Types ──────────────────────────────────────────────────────────────────────

interface FlowTxn { merchant: string; amount: number; date: string }

interface FlowNode { id: string; label: string; amount: number; color: string; top_transactions?: FlowTxn[] }

interface CashFlowData {
  month: string
  total_income: number
  total_spending: number
  savings: number
  income_sources: FlowNode[]
  spending_categories: FlowNode[]
}

// ── Layout ─────────────────────────────────────────────────────────────────────

// Label colour for a node the pointer has dimmed. Dark enough to recede, light
// enough that the row is still locatable.
const SANKEY_DIMMED = '#2b3242'

const NODE_W    = 20   // width of income-source / expense bars
const TUNNEL_W  = 40   // width of the center income tunnel
const RIGHT_PAD = 172  // horizontal space reserved for right labels — wide enough for "Credit Card Payment"-length labels
const LABEL_GAP = 8
const LABEL_MARGIN = 8  // safety margin kept clear before the SVG edge so text never bleeds past the page
const PAD_Y     = 22   // top/bottom padding inside the SVG
const MIN_SVG_H = 580  // minimum chart height (px)
const MIN_INCOME_BAND_H = 32 // min band height on the left — keeps labels readable without breaking flow geometry
const MIN_OUTCOME_BAND_H = 32 // same readable floor for expense/savings bands on the right
const INCOME_GAP = 8         // vertical gap between income bands + stream slices
const OUTCOME_GAP = 8        // vertical gap between expense/savings bands + stream slices
const LEFT_COL_X = 130 // fixed far-left column for income source bars + labels
const TUNNEL_FLOW_BIAS = 0.40  // amalgamation bar position across the flow span (0=left, 1=right)
// Available horizontal room for label text on each side before it would run past the SVG edge.
const LEFT_LABEL_MAX_W  = LEFT_COL_X - LABEL_GAP - LABEL_MARGIN
const RIGHT_LABEL_MAX_W = RIGHT_PAD - LABEL_GAP - LABEL_MARGIN

/** Truncate with an ellipsis once text would overflow its reserved label column. */
function truncateLabel(text: string, maxWidth: number, fontSize = 13): string {
  const avgCharW = fontSize * 0.56
  const maxChars = Math.max(3, Math.floor(maxWidth / avgCharW))
  if (text.length <= maxChars) return text
  return `${text.slice(0, maxChars - 1).trimEnd()}…`
}

interface LNode {
  id: string; label: string; amount: number; color: string
  x: number; y: number; h: number; labelCy: number
  slotTop: number; slotH: number; side: 'left' | 'right'
  top_transactions: FlowTxn[]
}
interface LLink { id: string; color: string; sx: number; sy0: number; sy1: number; tx: number; ty0: number; ty1: number; straightTop?: boolean }

/**
 * Right column: band heights track outflow share (mirrors left income layout).
 * Ribbons fan from proportional tunnel slices into these bands — same curve language as income.
 */
function stackOutcomeBands(
  items: FlowNode[],
  avail: number,
  nodeX: number,
  totalAmount: number,
): LNode[] {
  if (!items.length) return []

  const gaps = Math.max(0, items.length - 1) * OUTCOME_GAP
  const flowArea = avail - gaps
  const minTotal = items.length * MIN_OUTCOME_BAND_H
  const extra = Math.max(0, flowArea - minTotal)
  const heights = items.map(item => MIN_OUTCOME_BAND_H + (item.amount / totalAmount) * extra)

  const nodes: LNode[] = []
  let y = PAD_Y
  for (let i = 0; i < items.length; i++) {
    const h = heights[i]
    nodes.push({
      ...items[i],
      x: nodeX,
      y,
      h,
      labelCy: y + h / 2,
      slotTop: y,
      slotH: h,
      side: 'right',
      top_transactions: items[i].top_transactions ?? [],
    })
    y += h + (i < items.length - 1 ? OUTCOME_GAP : 0)
  }
  return nodes
}

/**
 * Left column: band heights track income share (parallel ribbons into the tunnel).
 * Tiny sources get a minimum band height so labels stay legible; chart grows if needed.
 */
function stackIncomeBands(
  items: FlowNode[],
  avail: number,
  nodeX: number,
  totalAmount: number,
): LNode[] {
  if (!items.length) return []

  const gaps = Math.max(0, items.length - 1) * INCOME_GAP
  const flowArea = avail - gaps
  const minTotal = items.length * MIN_INCOME_BAND_H
  const extra = Math.max(0, flowArea - minTotal)
  const heights = items.map(item => MIN_INCOME_BAND_H + (item.amount / totalAmount) * extra)

  const nodes: LNode[] = []
  let y = PAD_Y
  for (let i = 0; i < items.length; i++) {
    const h = heights[i]
    nodes.push({
      ...items[i],
      x: nodeX,
      y,
      h,
      labelCy: y + h / 2,
      slotTop: y,
      slotH: h,
      side: 'left',
      top_transactions: items[i].top_transactions ?? [],
    })
    y += h + (i < items.length - 1 ? INCOME_GAP : 0)
  }
  return nodes
}

const INVESTMENTS_NODE_ID = 'Investments'
const SAVINGS_NODE_ID = '__savings__'
const SAVINGS_COLOR = CHART_POSITIVE

function isAllocationNode(id: string): boolean {
  return id === SAVINGS_NODE_ID || id === INVESTMENTS_NODE_ID
}

function buildLayout(data: CashFlowData, W: number, H: number) {
  const avail = H - PAD_Y * 2
  const totalIncome = data.total_income || 1

  // Keep Investments with Savings as allocation sinks (after consumptive spend),
  // matching how Savings is appended rather than mixed into expense sort order.
  const investmentItem = data.spending_categories.find(c => c.id === INVESTMENTS_NODE_ID)
  const spendItems = data.spending_categories.filter(c => c.id !== INVESTMENTS_NODE_ID)
  const rightItems: FlowNode[] = [
    ...spendItems,
    ...(investmentItem && investmentItem.amount > 0.01 ? [investmentItem] : []),
    ...(data.savings > 0.01
      ? [{ id: SAVINGS_NODE_ID, label: 'Savings', amount: data.savings, color: SAVINGS_COLOR, top_transactions: [] }]
      : []),
  ]
  const totalOutflow = rightItems.reduce((sum, item) => sum + item.amount, 0) || 1

  const leftNodeX = LEFT_COL_X
  const rightNodeX = W - RIGHT_PAD - NODE_W
  const flowStart = leftNodeX + NODE_W
  const flowEnd = rightNodeX
  // Income inputs stay far left; amalgamation tunnel sits toward the middle of the flow.
  const tunnelX = Math.floor(flowStart + (flowEnd - flowStart) * TUNNEL_FLOW_BIAS - TUNNEL_W / 2)

  const tunnelH = avail
  const tunnelY = PAD_Y

  const leftNodes = stackIncomeBands(data.income_sources, avail, leftNodeX, totalIncome)

  const rightNodes = stackOutcomeBands(rightItems, avail, rightNodeX, totalOutflow)

  // Left ribbons: one stream per band; gaps stay visible (not filled by adjacent flows)
  const leftLinks: LLink[] = []
  {
    const tunnelGaps = Math.max(0, leftNodes.length - 1) * INCOME_GAP
    const tunnelFlow = tunnelH - tunnelGaps
    let offset = 0
    for (let i = 0; i < leftNodes.length; i++) {
      const src = leftNodes[i]
      const rh = Math.max((src.amount / totalIncome) * tunnelFlow, 1)
      leftLinks.push({
        id: src.id,
        color: src.color,
        sx: leftNodeX + NODE_W,
        sy0: src.y,
        sy1: src.y + src.h,
        tx: tunnelX,
        ty0: tunnelY + offset,
        ty1: tunnelY + offset + rh,
        straightTop: i === 0,
      })
      offset += rh + (i < leftNodes.length - 1 ? INCOME_GAP : 0)
    }
  }

  // Right ribbons: proportional tunnel slices → outcome bands; gaps stay visible
  const rightLinks: LLink[] = []
  {
    const tunnelGaps = Math.max(0, rightNodes.length - 1) * OUTCOME_GAP
    const tunnelFlow = tunnelH - tunnelGaps
    let offset = 0
    for (let i = 0; i < rightNodes.length; i++) {
      const tgt = rightNodes[i]
      const rh = Math.max((tgt.amount / totalOutflow) * tunnelFlow, 1)
      rightLinks.push({
        id: tgt.id,
        color: tgt.id === SAVINGS_NODE_ID ? SAVINGS_COLOR : tgt.color,
        sx: tunnelX + TUNNEL_W,
        sy0: tunnelY + offset,
        sy1: tunnelY + offset + rh,
        tx: rightNodeX,
        ty0: tgt.y,
        ty1: tgt.y + tgt.h,
      })
      offset += rh + (i < rightNodes.length - 1 ? OUTCOME_GAP : 0)
    }
  }

  return { leftNodes, rightNodes, leftLinks, rightLinks, tunnelX, tunnelY, tunnelH }
}

function ribbon(sx: number, sy0: number, sy1: number, tx: number, ty0: number, ty1: number) {
  const cx = (sx + tx) / 2
  return `M${sx} ${sy0} C${cx} ${sy0},${cx} ${ty0},${tx} ${ty0} L${tx} ${ty1} C${cx} ${ty1},${cx} ${sy1},${sx} ${sy1} Z`
}

/** Primary income stream: flat top, curved bottom that tiles with the stream below. */
function ribbonStraightTop(sx: number, sy0: number, sy1: number, tx: number, ty0: number, ty1: number) {
  const cx = (sx + tx) / 2
  return `M${sx} ${sy0} L${tx} ${ty0} L${tx} ${ty1} C${cx} ${ty1},${cx} ${sy1},${sx} ${sy1} Z`
}

function fmtShortDate(iso: string) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function FlowTooltip({ node }: { node: LNode }) {
  if (!node.top_transactions.length) return null
  const left = node.side === 'left'
    ? node.x + NODE_W + 14
    : Math.max(8, node.x - 236)

  return (
    <div
      className="absolute z-20 pointer-events-none w-[228px] px-[12px] py-[10px] rounded-[16px] border shadow-[0_24px_60px_-28px_rgba(0,0,0,0.88),0_0_28px_rgba(110,130,255,0.08),inset_0_1px_0_rgba(255,255,255,0.10)]"
      style={{
        top: node.labelCy,
        left,
        transform: 'translateY(-50%)',
        background: 'linear-gradient(165deg, rgba(24,27,37,0.96), rgba(16,19,27,0.94) 55%, rgba(12,14,20,0.98))',
        borderColor: 'rgba(255,255,255,0.14)',
      }}
    >
      <div className="text-[10px] text-ledger-text-faintest font-semibold mb-[6px] uppercase tracking-[0.08em]">
        Top transactions
      </div>
      {node.top_transactions.map((t, i) => (
        <div
          key={i}
          className="flex items-baseline justify-between gap-2 py-[5px] border-t border-white/8 first:border-0 first:pt-0"
        >
          <div className="min-w-0">
            <div className="text-[12px] text-ledger-text-secondary truncate">{t.merchant}</div>
            <div className="text-[10px] text-ledger-text-faintest">{fmtShortDate(t.date)}</div>
          </div>
          <span className={`text-[12px] font-medium shrink-0 ${node.side === 'left' ? 'text-ledger-positive' : 'text-ledger-text-primary'}`}>
            {node.side === 'left' ? '+' : ''}${fmt(t.amount)}
          </span>
        </div>
      ))}
    </div>
  )
}

function NodeGroup({ n, chartW, tunnelX, nodeVis, formatLabel, amountPrefix, amountClass, onHover }: {
  n: LNode
  chartW: number
  tunnelX: number
  nodeVis: (id: string) => boolean
  formatLabel: (n: LNode) => string
  amountPrefix: string
  amountClass: string
  onHover: (id: string | null) => void
}) {
  const labelX = n.side === 'left' ? n.x - LABEL_GAP : n.x + NODE_W + LABEL_GAP
  const textAnchor = n.side === 'left' ? 'end' : 'start'
  const labelMaxW = n.side === 'left' ? LEFT_LABEL_MAX_W : RIGHT_LABEL_MAX_W
  const label = truncateLabel(formatLabel(n), labelMaxW)
  const tunnelRight = tunnelX + TUNNEL_W
  const hit =
    n.side === 'left'
      ? { x: 0, y: n.slotTop - 2, width: tunnelX - 4, height: n.slotH + 4 }
      : { x: tunnelRight + 4, y: n.slotTop - 2, width: chartW - tunnelRight - 4, height: n.slotH + 4 }

  return (
    <g onMouseEnter={() => onHover(n.id)} onMouseLeave={() => onHover(null)} style={{ cursor: 'default' }}>
      <rect x={n.x} y={n.y} width={NODE_W} height={n.h} fill={n.color} rx={3}
        opacity={nodeVis(n.id) ? 1 : 0.08} style={{ transition: 'opacity 0.15s', pointerEvents: 'none' }} />
      {n.slotH >= 22 ? (
        <>
          <text x={labelX} y={n.labelCy - 6}
            textAnchor={textAnchor} fontSize={13}
            fill={nodeVis(n.id) ? CHART_TEXT.secondary : SANKEY_DIMMED}
            fontWeight={nodeVis(n.id) ? 500 : 400}
            style={{ transition: 'fill 0.15s', userSelect: 'none', pointerEvents: 'none' }}
          >{label}</text>
          <text x={labelX} y={n.labelCy + 11}
            textAnchor={textAnchor} fontSize={12}
            fontFamily="JetBrains Mono, monospace"
            fill={nodeVis(n.id) ? amountClass : SANKEY_DIMMED}
            style={{ transition: 'fill 0.15s', userSelect: 'none', pointerEvents: 'none' }}
          >{amountPrefix}${fmt(n.amount)}</text>
        </>
      ) : (
        <text x={labelX} y={n.labelCy + 4}
          textAnchor={textAnchor} fontSize={11}
          fill={nodeVis(n.id) ? CHART_TEXT.secondary : SANKEY_DIMMED}
          style={{ userSelect: 'none', pointerEvents: 'none' }}
        >{formatLabel(n)}</text>
      )}
      {/* Full-row hit target on top so labels and nearby whitespace both trigger hover */}
      <rect x={hit.x} y={hit.y} width={hit.width} height={hit.height} fill="transparent" pointerEvents="all" />
    </g>
  )
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function Spending() {
  const [selectedMonth, setSelectedMonth] = useState(MONTH_OPTIONS[0].value)
  const [data, setData] = useState<CashFlowData | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncRefresh, setSyncRefresh] = useState(0)
  const [hovered, setHovered] = useState<string | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [svgW, setSvgW] = useState(0)

  useOnSyncComplete(useCallback(() => setSyncRefresh(n => n + 1), []))

  const leftCount = data?.income_sources.length ?? 0
  const rightCount = data ? data.spending_categories.length + (data.savings > 0.01 ? 1 : 0) : 0
  const incomeMinH = leftCount > 0
    ? leftCount * MIN_INCOME_BAND_H + Math.max(0, leftCount - 1) * INCOME_GAP + PAD_Y * 2
    : MIN_SVG_H
  const outcomeMinH = rightCount > 0
    ? rightCount * MIN_OUTCOME_BAND_H + Math.max(0, rightCount - 1) * OUTCOME_GAP + PAD_Y * 2
    : MIN_SVG_H
  const SVG_H = Math.max(incomeMinH, outcomeMinH, MIN_SVG_H)

  useEffect(() => {
    setLoading(true)
    apiFetch(`/api/analytics/cash-flow?month=${selectedMonth}`)
      .then(r => r.json()).then(setData).catch(() => setData(null)).finally(() => setLoading(false))
  }, [selectedMonth, syncRefresh])

  const onResize = useCallback(() => {
    if (wrapRef.current) setSvgW(wrapRef.current.clientWidth)
  }, [])
  useEffect(() => {
    onResize()
    const ro = new ResizeObserver(onResize)
    if (wrapRef.current) ro.observe(wrapRef.current)
    return () => ro.disconnect()
  }, [onResize])

  const hasFlow = Boolean(
    data && (
      data.income_sources.length > 0
      || data.spending_categories.length > 0
      || data.total_income > 0.01
      || data.total_spending > 0.01
    ),
  )
  const layout = data && hasFlow && svgW > 0 ? buildLayout(data, svgW, SVG_H) : null

  // Highlighting: hover an income source → dim other income things; hover expense → dim other expenses.
  // Hovering a left node keeps right ribbons visible (income flows to all expenses via tunnel).
  // Hovering a right node keeps left ribbons visible.
  const leftNodeIds  = layout ? new Set(layout.leftNodes.map(n => n.id))  : new Set<string>()
  const rightNodeIds = layout ? new Set(layout.rightNodes.map(n => n.id)) : new Set<string>()
  const hoverIsLeft  = hovered && leftNodeIds.has(hovered)
  const hoverIsRight = hovered && rightNodeIds.has(hovered)
  const hoverIsTunnel = hovered === '__tunnel__'

  const nodeVis = (id: string) => {
    if (!hovered || hoverIsTunnel) return true
    return hovered === id
  }
  const leftRibbonVis = (srcId: string) => {
    if (!hovered || hoverIsTunnel || hoverIsRight) return true
    return hovered === srcId
  }
  const rightRibbonVis = (tgtId: string) => {
    if (!hovered || hoverIsTunnel || hoverIsLeft) return true
    return hovered === tgtId
  }

  const deficit = data ? Math.max(0, data.total_spending - data.total_income) : 0
  const invested = data
    ? (data.spending_categories.find(c => c.id === INVESTMENTS_NODE_ID)?.amount ?? 0)
    : 0
  const consumptiveSpending = data ? Math.max(0, data.total_spending - invested) : 0

  const hoveredNode: LNode | null = hovered && layout && hovered !== '__tunnel__' && hovered !== SAVINGS_NODE_ID
    ? (layout.leftNodes.find(n => n.id === hovered) ?? layout.rightNodes.find(n => n.id === hovered) ?? null)
    : null

  return (
    <div className="flex flex-col gap-[16px]">
      {/* Controls */}
      <div className="flex items-center gap-[12px]">
        <select
          value={selectedMonth}
          onChange={e => setSelectedMonth(e.target.value)}
          className="glass-chip px-[10px] py-[8px] text-ledger-text-primary text-[13px] cursor-pointer focus:outline-none"
        >
          {MONTH_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>

        {/* This is the page's summary, so it reads at metric weight. It used to
            be the smallest text on the screen, set inline beside the month
            picker. */}
        {data && (
          <div className="inset-panel flex divide-x divide-ledger-border-input ml-[6px]">
            {[
              { label: 'Income', value: `$${fmt(data.total_income)}`, tone: 'text-ledger-positive' },
              { label: 'Spending', value: `$${fmt(consumptiveSpending)}`, tone: 'text-ledger-text-primary' },
              ...(invested > 0.01
                ? [{ label: 'Invested', value: `$${fmt(invested)}`, tone: 'text-ledger-accent-text' }]
                : []),
              deficit > 0
                ? { label: 'Over', value: `−$${fmt(deficit)}`, tone: 'text-ledger-negative' }
                : { label: 'Saved', value: `$${fmt(data.savings)}`, tone: 'text-ledger-positive' },
            ].map(item => (
              <div key={item.label} className="px-3.5 py-1.5">
                <div className="metric-label">{item.label}</div>
                <div className={`text-[15px] font-semibold font-mono leading-tight mt-[1px] ${item.tone}`}>
                  {item.value}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Sankey card */}
      <div className="glass-card p-[14px]">
        <div ref={wrapRef} className="relative" style={{ width: '100%' }}>
          {loading ? (
            <div className="flex items-center justify-center text-ledger-text-faint text-[13px] py-16">Loading…</div>
          ) : !layout ? (
            <div className="flex flex-col items-center justify-center text-center py-16 px-6">
              <div className="text-[14px] font-semibold mb-1.5">No cash flow this month</div>
              <div className="text-[13px] text-ledger-text-faint max-w-[360px]">
                Link an account or import a CSV to see income and spending here.
              </div>
            </div>
          ) : (
            <>
            <svg width={svgW} height={SVG_H} style={{ display: 'block', overflow: 'visible' }}>
              <defs>
                <linearGradient id="tg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor="#4b74b4" stopOpacity="0.95" />
                  <stop offset="100%" stopColor="#1d2c46" stopOpacity="0.95" />
                </linearGradient>
              </defs>

              {/* Left ribbons (income → tunnel) */}
              {layout.leftLinks.map(l => (
                <path key={l.id}
                  d={l.straightTop
                    ? ribbonStraightTop(l.sx, l.sy0, l.sy1, l.tx, l.ty0, l.ty1)
                    : ribbon(l.sx, l.sy0, l.sy1, l.tx, l.ty0, l.ty1)}
                  fill={l.color}
                  opacity={leftRibbonVis(l.id) ? 0.28 : 0.03}
                  style={{ transition: 'opacity 0.15s', cursor: 'default' }}
                  onMouseEnter={() => setHovered(l.id)}
                  onMouseLeave={() => setHovered(null)}
                />
              ))}

              {/* Right ribbons (tunnel → expenses) */}
              {layout.rightLinks.map(l => (
                <path key={l.id}
                  d={ribbon(l.sx, l.sy0, l.sy1, l.tx, l.ty0, l.ty1)}
                  fill={l.color}
                  opacity={rightRibbonVis(l.id) ? 0.28 : 0.03}
                  style={{ transition: 'opacity 0.15s', cursor: 'default' }}
                  onMouseEnter={() => setHovered(l.id)}
                  onMouseLeave={() => setHovered(null)}
                />
              ))}

              {/* Center income tunnel */}
              <g onMouseEnter={() => setHovered('__tunnel__')} onMouseLeave={() => setHovered(null)} style={{ cursor: 'default' }}>
                <rect
                  x={layout.tunnelX} y={layout.tunnelY}
                  width={TUNNEL_W} height={layout.tunnelH}
                  fill="url(#tg)" rx={4}
                  opacity={!hovered || hoverIsTunnel ? 1 : 0.20}
                  style={{ transition: 'opacity 0.15s' }}
                />
                <text
                  x={layout.tunnelX + TUNNEL_W / 2} y={layout.tunnelY - 6}
                  textAnchor="middle" fontSize={10} fill={CHART_TEXT.faint} letterSpacing="0.07em" fontWeight={600}
                  style={{ userSelect: 'none' }}
                >INCOME</text>
                <text
                  x={layout.tunnelX + TUNNEL_W / 2} y={layout.tunnelY + layout.tunnelH + 14}
                  textAnchor="middle" fontSize={11} fill={CHART_TEXT.muted} fontFamily="JetBrains Mono, monospace"
                  style={{ userSelect: 'none' }}
                >${fmt(data!.total_income)}</text>
              </g>

              {/* Left income-source nodes */}
              {layout.leftNodes.map(n => (
                <NodeGroup
                  key={n.id}
                  n={n}
                  chartW={svgW}
                  tunnelX={layout.tunnelX}
                  nodeVis={nodeVis}
                  formatLabel={n => formatCategory(n.label)}
                  amountPrefix="+"
                  amountClass={CHART_POSITIVE}
                  onHover={setHovered}
                />
              ))}

              {/* Right expense / allocation nodes */}
              {layout.rightNodes.map(n => (
                <NodeGroup
                  key={n.id}
                  n={n}
                  chartW={svgW}
                  tunnelX={layout.tunnelX}
                  nodeVis={nodeVis}
                  formatLabel={n => n.id === SAVINGS_NODE_ID ? 'Savings' : formatCategory(n.label)}
                  amountPrefix=""
                  amountClass={isAllocationNode(n.id) ? (n.id === SAVINGS_NODE_ID ? SAVINGS_COLOR : n.color) : CHART_TEXT.muted}
                  onHover={setHovered}
                />
              ))}
            </svg>
            {hoveredNode && <FlowTooltip node={hoveredNode} />}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
