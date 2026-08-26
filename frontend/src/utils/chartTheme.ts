// Recharts takes colours as props, not classes. Keep chart chrome next to the
// glass surfaces so tooltips and axes match the rest of the app.

export const CHART_SURFACE = {
  card: 'rgba(18, 21, 30, 0.94)',
  cardAlt: 'rgba(16, 19, 27, 0.96)',
  inset: '#161a21',
  bg: '#0d0f14',
  border: 'rgba(255,255,255,0.14)',
  borderStrong: 'rgba(255,255,255,0.22)',
} as const

export const CHART_TEXT = {
  primary: '#e9ebf0',
  secondary: 'rgba(255,255,255,0.74)',
  muted: 'rgba(255,255,255,0.66)',
  faint: 'rgba(255,255,255,0.60)',
  faintest: 'rgba(255,255,255,0.52)',
} as const

export const CHART_ACCENT = '#5b8def'
export const CHART_POSITIVE = '#4ec38a'
export const CHART_NEGATIVE = '#e7705f'
export const CHART_WARNING = '#d9a85b'

export const CATEGORY_PALETTE = [
  '#5b8def', '#4fc4c4', '#8a7df0', '#4ec38a', '#d9a85b',
  '#e7705f', '#f0a87d', '#7fb0ff', '#a8d8a8', '#c084fc',
] as const

export const CATEGORY_FALLBACK = '#565c69'

export const tooltipStyle = {
  backgroundColor: CHART_SURFACE.cardAlt,
  border: `1px solid ${CHART_SURFACE.border}`,
  borderRadius: '12px',
  boxShadow: '0 20px 50px -28px rgba(10,10,40,0.55)',
  fontSize: '12px',
  backdropFilter: 'blur(16px)',
} as const

export const tooltipLabelStyle = {
  color: CHART_TEXT.faint,
  fontSize: '11px',
  marginBottom: '2px',
} as const

export const tooltipItemStyle = {
  color: CHART_TEXT.primary,
} as const

export const AXIS_STROKE = 'rgba(255,255,255,0.42)'
export const GRID_STROKE = '#0d0f14'
