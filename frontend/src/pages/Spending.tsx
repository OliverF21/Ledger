import { useState, useEffect, useRef, useCallback } from 'react'
import { apiFetch } from '../api/client'
import { formatCategory } from '../utils/categories'
import { drillFromCashFlowNode, openTransactionsForCategory } from '../utils/cashFlowDrill'
import { useOnSyncComplete } from '../hooks/useSync'
import { getMonthOptions } from '../utils/months'

function fmt(n: number) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const MONTH_OPTIONS = getMonthOptions(12)

// ── Types ──────────────────────────────────────────────────────────────────────

interface FlowTxn { merchant: string; amount: number; date: string }

interface FlowNode {
  id: string
  label: string
  amount: number
  color: string
  top_transactions?: FlowTxn[]
  parent_id?: string | null
  parent_label?: string | null
}

interface CashFlowData {
  month: string
  total_income: number
  total_spending: number
  savings: number
  income_sources: FlowNode[]
  spending_categories: FlowNode[]
  allocation_nodes?: FlowNode[]
}

// ── Layout ─────────────────────────────────────────────────────────────────────

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
const BRANCH_TUNNEL_BIAS = 0.18 // shift the account left so a parent column fits before the leaves
const PARENT_SPAN = 156 // parent label + bar, sitting just left of the leaf column
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
  slotTop: number; slotH: number; side: 'left' | 'right' | 'mid'
  top_transactions: FlowTxn[]
  parent_id: string | null
  parent_label: string | null
}
interface LLink {
  id: string
  group: string
  color: string
  sx: number; sy0: number; sy1: number; tx: number; ty0: number; ty1: number
  straightTop?: boolean
}

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
      parent_id: items[i].parent_id ?? null,
      parent_label: items[i].parent_label ?? null,
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
      parent_id: null,
      parent_label: null,
    })
    y += h + (i < items.length - 1 ? INCOME_GAP : 0)
  }
  return nodes
}

const INVESTMENTS_NODE_ID = 'Investments'
const SAVINGS_NODE_ID = '__savings__'
const UNALLOCATED_NODE_ID = '__unallocated__'
const SAVINGS_COLOR = '#74d8a8'

function isAllocationNode(id: string): boolean {
  return id === SAVINGS_NODE_ID
    || id === INVESTMENTS_NODE_ID
    || id === UNALLOCATED_NODE_ID
    || id.startsWith('goal:')
}

/** PFC keys still go through the shared formatter. Bucket names such as
 *  "Groceries" or "Other Transportation" are already display text — formatting
 *  them again prefixes the parent ("Food & Drink · Groceries") and the Sankey
 *  column truncates it. */
function spendingBandLabel(raw: string): string {
  const trimmed = raw.trim()
  if (/^[A-Z0-9_.]+$/.test(trimmed)) return formatCategory(trimmed)
  return trimmed
}

function allocationLabel(n: FlowNode): string {
  if (n.id === SAVINGS_NODE_ID) return 'HYSA'
  if (n.id === UNALLOCATED_NODE_ID) return 'Savings'
  if (n.id.startsWith('goal:')) return n.label
  return spendingBandLabel(n.label)
}

function buildLayout(data: CashFlowData, W: number, H: number) {
  const avail = H - PAD_Y * 2
  const totalIncome = data.total_income || 1

  const rightItems: FlowNode[] = [
    ...data.spending_categories,
    ...(data.allocation_nodes ?? []).filter(n => n.amount > 0.01),
  ]
  const totalOutflow = rightItems.reduce((sum, item) => sum + item.amount, 0) || 1

  const branched = rightItems.some(item => item.parent_id)
  const leftNodeX = LEFT_COL_X
  const rightNodeX = W - RIGHT_PAD - NODE_W
  const flowStart = leftNodeX + NODE_W
  const flowEnd = rightNodeX
  // Parents sit between the account and the leaves, so the account shifts left.
  const tunnelBias = branched ? BRANCH_TUNNEL_BIAS : TUNNEL_FLOW_BIAS
  const tunnelX = Math.floor(flowStart + (flowEnd - flowStart) * tunnelBias - TUNNEL_W / 2)

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
        group: src.id,
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

  const { rightLinks, parentNodes } = branchRightLinks(rightNodes, tunnelX, tunnelY, tunnelH, rightNodeX, totalOutflow)

  return { leftNodes, rightNodes, parentNodes, leftLinks, rightLinks, tunnelX, tunnelY, tunnelH }
}

/** Account → parent, then parent → dining / groceries / the other leaves. */
function branchRightLinks(
  rightNodes: LNode[],
  tunnelX: number,
  tunnelY: number,
  tunnelH: number,
  rightNodeX: number,
  totalOutflow: number,
): { rightLinks: LLink[]; parentNodes: LNode[] } {
  const rightLinks: LLink[] = []
  const parentNodes: LNode[] = []
  if (!rightNodes.length) return { rightLinks, parentNodes }

  const tunnelGaps = Math.max(0, rightNodes.length - 1) * OUTCOME_GAP
  const tunnelFlow = tunnelH - tunnelGaps
  const slices: { node: LNode; y0: number; y1: number }[] = []
  let offset = 0
  for (let i = 0; i < rightNodes.length; i++) {
    const node = rightNodes[i]
    const rh = Math.max((node.amount / totalOutflow) * tunnelFlow, 1)
    slices.push({ node, y0: tunnelY + offset, y1: tunnelY + offset + rh })
    offset += rh + (i < rightNodes.length - 1 ? OUTCOME_GAP : 0)
  }

  let index = 0
  while (index < slices.length) {
    const head = slices[index]
    const parentId = head.node.parent_id
    if (!parentId) {
      const color = isAllocationNode(head.node.id) && (head.node.id === SAVINGS_NODE_ID || head.node.id === UNALLOCATED_NODE_ID)
        ? SAVINGS_COLOR
        : head.node.color
      rightLinks.push({
        id: head.node.id,
        group: head.node.id,
        color,
        sx: tunnelX + TUNNEL_W,
        sy0: head.y0,
        sy1: head.y1,
        tx: rightNodeX,
        ty0: head.node.y,
        ty1: head.node.y + head.node.h,
      })
      index += 1
      continue
    }

    const start = index
    while (index < slices.length && slices[index].node.parent_id === parentId) index += 1
    const group = slices.slice(start, index)
    const children = group.map(entry => entry.node)
    const parentAmount = children.reduce((sum, child) => sum + child.amount, 0) || 1
    const parentY = children[0].y
    const parentBottom = children[children.length - 1].y + children[children.length - 1].h
    const parentH = Math.max(parentBottom - parentY, 1)
    const parentX = rightNodeX - PARENT_SPAN
    const largest = children.reduce((best, child) => child.amount > best.amount ? child : best, children[0])
    parentNodes.push({
      id: parentId,
      label: head.node.parent_label || parentId,
      amount: parentAmount,
      color: largest.color,
      x: parentX,
      y: parentY,
      h: parentH,
      labelCy: parentY + parentH / 2,
      slotTop: parentY,
      slotH: parentH,
      side: 'mid',
      top_transactions: [],
      parent_id: null,
      parent_label: null,
    })
    rightLinks.push({
      id: parentId,
      group: parentId,
      color: largest.color,
      sx: tunnelX + TUNNEL_W,
      sy0: group[0].y0,
      sy1: group[group.length - 1].y1,
      tx: parentX,
      ty0: parentY,
      ty1: parentBottom,
    })
    const childGaps = Math.max(0, children.length - 1) * OUTCOME_GAP
    const flowH = Math.max(parentH - childGaps, 1)
    let childOffset = 0
    for (let c = 0; c < children.length; c++) {
      const child = children[c]
      const rh = Math.max((child.amount / parentAmount) * flowH, 1)
      rightLinks.push({
        id: child.id,
        group: parentId,
        color: child.color,
        sx: parentX + NODE_W,
        sy0: parentY + childOffset,
        sy1: parentY + childOffset + rh,
        tx: child.x,
        ty0: child.y,
        ty1: child.y + child.h,
      })
      childOffset += rh + (c < children.length - 1 ? OUTCOME_GAP : 0)
    }
  }

  return { rightLinks, parentNodes }
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

function NodeGroup({ n, chartW, tunnelX, nodeVis, formatLabel, amountPrefix, amountClass, onHover, onOpen }: {
  n: LNode
  chartW: number
  tunnelX: number
  nodeVis: (id: string) => boolean
  formatLabel: (n: LNode) => string
  amountPrefix: string
  amountClass: string
  onHover: (id: string | null) => void
  onOpen?: (n: LNode) => void
}) {
  const labelX = n.side === 'left' ? n.x - LABEL_GAP : n.x + NODE_W + LABEL_GAP
  const textAnchor = n.side === 'left' ? 'end' : 'start'
  const labelMaxW = n.side === 'left' ? LEFT_LABEL_MAX_W : RIGHT_LABEL_MAX_W
  const label = truncateLabel(formatLabel(n), labelMaxW)
  const hit =
    n.side === 'left'
      ? { x: 0, y: n.slotTop - 2, width: tunnelX - 4, height: n.slotH + 4 }
      : { x: n.x - 6, y: n.slotTop - 2, width: chartW - (n.x - 6), height: n.slotH + 4 }

  return (
    <g
      onMouseEnter={() => onHover(n.id)}
      onMouseLeave={() => onHover(null)}
      onDoubleClick={onOpen ? () => onOpen(n) : undefined}
      style={{ cursor: onOpen ? 'pointer' : 'default' }}
    >
      {onOpen && <title>Double-click to view these transactions</title>}
      <rect x={n.x} y={n.y} width={NODE_W} height={n.h} fill={n.color} rx={3}
        opacity={nodeVis(n.id) ? 1 : 0.08} style={{ transition: 'opacity 0.15s', pointerEvents: 'none' }} />
      {n.slotH >= 22 ? (
        <>
          <text x={labelX} y={n.labelCy - 6}
            textAnchor={textAnchor} fontSize={13}
            fill={nodeVis(n.id) ? '#d4dae4' : '#2a3040'}
            fontWeight={nodeVis(n.id) ? 500 : 400}
            style={{ transition: 'fill 0.15s', userSelect: 'none', pointerEvents: 'none' }}
          >{label}</text>
          <text x={labelX} y={n.labelCy + 11}
            textAnchor={textAnchor} fontSize={12}
            fill={nodeVis(n.id) ? amountClass : '#2a3040'}
            style={{ transition: 'fill 0.15s', userSelect: 'none', pointerEvents: 'none' }}
          >{amountPrefix}${fmt(n.amount)}</text>
        </>
      ) : (
        <text x={labelX} y={n.labelCy + 4}
          textAnchor={textAnchor} fontSize={11}
          fill={nodeVis(n.id) ? '#d4dae4' : '#2a3040'}
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
  const [expanded, setExpanded] = useState(false)
  const [data, setData] = useState<CashFlowData | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncRefresh, setSyncRefresh] = useState(0)
  const [hovered, setHovered] = useState<string | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [svgW, setSvgW] = useState(0)

  useOnSyncComplete(useCallback(() => setSyncRefresh(n => n + 1), []))

  const leftCount = data?.income_sources.length ?? 0
  // Count every right-hand band the layout draws. Savings alone under-counts
  // goals and investments, and expanded view then clips the bottom ribbons.
  const allocationCount = (data?.allocation_nodes ?? []).filter(n => n.amount > 0.01).length
  const rightCount = data ? data.spending_categories.length + allocationCount : 0
  const incomeMinH = leftCount > 0
    ? leftCount * MIN_INCOME_BAND_H + Math.max(0, leftCount - 1) * INCOME_GAP + PAD_Y * 2
    : MIN_SVG_H
  const outcomeMinH = rightCount > 0
    ? rightCount * MIN_OUTCOME_BAND_H + Math.max(0, rightCount - 1) * OUTCOME_GAP + PAD_Y * 2
    : MIN_SVG_H
  const SVG_H = Math.max(incomeMinH, outcomeMinH, MIN_SVG_H)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setHovered(null)
    const detail = expanded ? '&expanded=true' : ''
    apiFetch(`/api/analytics/cash-flow?month=${selectedMonth}${detail}`)
      .then(r => {
        if (!r.ok) throw new Error(`cash-flow ${r.status}`)
        return r.json()
      })
      .then(next => { if (!cancelled) setData(next) })
      .catch(() => { if (!cancelled) setData(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [selectedMonth, expanded, syncRefresh])

  const onResize = useCallback(() => {
    if (wrapRef.current) setSvgW(wrapRef.current.clientWidth)
  }, [])
  useEffect(() => {
    onResize()
    const ro = new ResizeObserver(onResize)
    if (wrapRef.current) ro.observe(wrapRef.current)
    return () => ro.disconnect()
  }, [onResize])

  const layout = data && svgW > 0 ? buildLayout(data, svgW, SVG_H) : null
  const spendingIds = new Set((data?.spending_categories ?? []).map(node => node.id))

  const openCategory = useCallback((node: LNode) => {
    const label = node.id.startsWith('other:')
      ? `Other · ${node.parent_label ? spendingBandLabel(node.parent_label) : formatCategory(node.id.slice('other:'.length))}`
      : node.side === 'left'
        ? formatCategory(node.label)
        : node.side === 'mid'
          ? spendingBandLabel(node.label)
          : allocationLabel(node)
    openTransactionsForCategory(selectedMonth, drillFromCashFlowNode(node), label)
  }, [selectedMonth])

  // Highlighting: hover an income source → dim other income things; hover expense → dim other expenses.
  // Hovering a left node keeps right ribbons visible (income flows to all expenses via tunnel).
  // Hovering a right node keeps left ribbons visible.
  const leftNodeIds  = layout ? new Set(layout.leftNodes.map(n => n.id))  : new Set<string>()
  const rightNodeIds = layout ? new Set(layout.rightNodes.map(n => n.id)) : new Set<string>()
  const parentNodeIds = layout ? new Set(layout.parentNodes.map(n => n.id)) : new Set<string>()
  const hoverIsLeft  = hovered && leftNodeIds.has(hovered)
  const hoverIsRight = hovered && (rightNodeIds.has(hovered) || parentNodeIds.has(hovered))
  const hoverIsTunnel = hovered === '__tunnel__'
  const hoveredParent = layout
    ? (layout.rightNodes.find(n => n.id === hovered)?.parent_id
      ?? (hovered && parentNodeIds.has(hovered) ? hovered : null))
    : null

  const nodeVis = (id: string, parentId?: string | null) => {
    if (!hovered || hoverIsTunnel) return true
    if (hovered === id) return true
    if (hoveredParent && (id === hoveredParent || parentId === hoveredParent)) return true
    return false
  }
  const leftRibbonVis = (srcId: string) => {
    if (!hovered || hoverIsTunnel || hoverIsRight) return true
    return hovered === srcId
  }
  const rightRibbonVis = (link: LLink) => {
    if (!hovered || hoverIsTunnel || hoverIsLeft) return true
    return hovered === link.id || hovered === link.group || hoveredParent === link.group
  }

  const allocationNodes = data?.allocation_nodes ?? []
  const allocated = allocationNodes
    .filter(n => n.id !== UNALLOCATED_NODE_ID)
    .reduce((sum, n) => sum + n.amount, 0)
  const unallocated = data
    ? (allocationNodes.find(n => n.id === UNALLOCATED_NODE_ID)?.amount ?? data.savings)
    : 0
  const consumptiveSpending = data?.total_spending ?? 0
  const deficit = data ? Math.max(0, data.total_spending - data.total_income) : 0

  const hoveredNode: LNode | null = hovered && layout && hovered !== '__tunnel__'
    ? (layout.leftNodes.find(n => n.id === hovered)
      ?? layout.rightNodes.find(n => n.id === hovered)
      ?? layout.parentNodes.find(n => n.id === hovered)
      ?? null)
    : null

  return (
    <div className="flex flex-col gap-[16px]">
      {/* Controls */}
      <div className="flex items-center gap-[12px] flex-wrap">
        <select
          value={selectedMonth}
          onChange={e => setSelectedMonth(e.target.value)}
          className="glass-chip px-[10px] py-[8px] text-ledger-text-primary text-[13px] cursor-pointer focus:outline-none"
        >
          {MONTH_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <button
          type="button"
          aria-pressed={expanded}
          title="Break activities out of their parent, such as Food & Drink into dining and groceries"
          onClick={() => setExpanded(on => !on)}
          className={`glass-chip px-[10px] py-[8px] text-[13px] cursor-pointer transition-colors hover:border-white/40 ${
            expanded ? 'border-white/60 text-ledger-text-primary' : 'text-ledger-text-secondary'
          }`}
        >
          Expanded view
        </button>

        {data && (
          <div className="flex gap-[20px] ml-[6px] text-[13px]">
            <span className="text-ledger-text-faint">
              Income <span className="text-ledger-positive font-semibold">${fmt(data.total_income)}</span>
            </span>
            <span className="text-ledger-text-faint">
              Spending <span className="text-ledger-text-secondary font-semibold">${fmt(consumptiveSpending)}</span>
            </span>
            {allocated > 0.01 && (
              <span className="text-ledger-text-faint">
                Allocated <span className="text-white font-semibold">${fmt(allocated)}</span>
              </span>
            )}
            {deficit > 0
              ? <span className="text-ledger-negative font-semibold">−${fmt(deficit)} over</span>
              : <span className="text-ledger-text-faint">Savings <span className="text-ledger-positive font-semibold">${fmt(unallocated)}</span></span>
            }
          </div>
        )}
      </div>

      {/* Sankey card */}
      <div className="glass-card p-[14px]">
        <div ref={wrapRef} className="relative" style={{ width: '100%' }}>
          {loading ? (
            <div className="flex items-center justify-center text-ledger-text-faint text-[13px]" style={{ height: SVG_H }}>Loading…</div>
          ) : !layout ? (
            <div className="flex items-center justify-center text-ledger-text-faint text-[13px]" style={{ height: SVG_H }}>No data for this month</div>
          ) : (
            <>
            <svg width={svgW} height={SVG_H} style={{ display: 'block', overflow: 'visible' }}>
              <defs>
                <linearGradient id="tg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor="rgba(255,255,255,0.42)" stopOpacity="0.95" />
                  <stop offset="100%" stopColor="rgba(232,238,248,0.16)" stopOpacity="0.95" />
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
              {layout.rightLinks.map((l, i) => (
                <path key={`${l.group}-${l.id}-${i}`}
                  d={ribbon(l.sx, l.sy0, l.sy1, l.tx, l.ty0, l.ty1)}
                  fill={l.color}
                  opacity={rightRibbonVis(l) ? 0.28 : 0.03}
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
                  textAnchor="middle" fontSize={10} fill="rgba(255,255,255,0.46)" letterSpacing="0.10em"
                  style={{ userSelect: 'none' }}
                >INCOME</text>
                <text
                  x={layout.tunnelX + TUNNEL_W / 2} y={layout.tunnelY + layout.tunnelH + 14}
                  textAnchor="middle" fontSize={11} fill="rgba(255,255,255,0.46)"
                  style={{ userSelect: 'none' }}
                >${fmt(data!.total_income)}</text>
              </g>

              {/* Left income-source nodes */}
              {layout.parentNodes.map(n => (
                <g
                  key={n.id}
                  onMouseEnter={() => setHovered(n.id)}
                  onMouseLeave={() => setHovered(null)}
                  onDoubleClick={() => openCategory(n)}
                  style={{ cursor: 'pointer' }}
                >
                  <title>Double-click to view these transactions</title>
                  <rect x={n.x} y={n.y} width={NODE_W} height={n.h} fill={n.color} rx={3}
                    opacity={nodeVis(n.id) ? 1 : 0.08} style={{ transition: 'opacity 0.15s', pointerEvents: 'none' }} />
                  <text x={n.x - LABEL_GAP} y={n.labelCy - (n.h >= 28 ? 6 : 4)}
                    textAnchor="end" fontSize={12}
                    fill={nodeVis(n.id) ? '#d4dae4' : '#2a3040'}
                    fontWeight={500}
                    style={{ userSelect: 'none', pointerEvents: 'none' }}
                  >{truncateLabel(spendingBandLabel(n.label), PARENT_SPAN - NODE_W - LABEL_GAP - 8, 12)}</text>
                  {n.h >= 28 && (
                    <text x={n.x - LABEL_GAP} y={n.labelCy + 11}
                      textAnchor="end" fontSize={11}
                      fill={nodeVis(n.id) ? '#9aa2b2' : '#2a3040'}
                      style={{ userSelect: 'none', pointerEvents: 'none' }}
                    >${fmt(n.amount)}</text>
                  )}
                  <rect
                    x={n.x - (PARENT_SPAN - NODE_W)}
                    y={n.y}
                    width={PARENT_SPAN}
                    height={n.h}
                    fill="transparent"
                    pointerEvents="all"
                  />
                </g>
              ))}

              {layout.leftNodes.map(n => (
                <NodeGroup
                  key={n.id}
                  n={n}
                  chartW={svgW}
                  tunnelX={layout.tunnelX}
                  nodeVis={id => nodeVis(id)}
                  formatLabel={n => formatCategory(n.label)}
                  amountPrefix="+"
                  amountClass="#74d8a8"
                  onHover={setHovered}
                  onOpen={openCategory}
                />
              ))}

              {/* Right expense / allocation nodes */}
              {layout.rightNodes.map(n => (
                <NodeGroup
                  key={n.id}
                  n={n}
                  chartW={svgW}
                  tunnelX={layout.tunnelX}
                  nodeVis={id => nodeVis(id, layout.rightNodes.find(n => n.id === id)?.parent_id)}
                  formatLabel={n => allocationLabel(n)}
                  amountPrefix=""
                  amountClass={isAllocationNode(n.id) ? (n.id === SAVINGS_NODE_ID || n.id === UNALLOCATED_NODE_ID ? SAVINGS_COLOR : n.color) : '#9aa2b2'}
                  onHover={setHovered}
                  onOpen={spendingIds.has(n.id) ? openCategory : undefined}
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
