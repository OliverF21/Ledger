// Recharts takes colours as props, not classes. Keep chart chrome next to the
// surfaces so tooltips and axes match the rest of the app.

export const CHART_SURFACE = {
  card: '#0e151e',
  cardAlt: '#0e151e',
  inset: '#111820',
  bg: '#070b12',
  border: 'rgba(255,255,255,0.08)',
  borderStrong: 'rgba(255,255,255,0.12)',
} as const

export const CHART_TEXT = {
  primary: '#f0f2f5',
  secondary: '#c5cbd4',
  muted: '#8b95a5',
  faint: '#6b7380',
  faintest: '#565e6b',
} as const

export const CHART_ACCENT = '#4d8dff'
export const CHART_POSITIVE = '#3dd68c'
export const CHART_NEGATIVE = '#ff6b7a'
export const CHART_WARNING = '#e8b86d'

export const CATEGORY_PALETTE = [
  '#4d8dff', '#3dd68c', '#8a7df0', '#4fc4c4', '#e8b86d',
  '#ff6b7a', '#f0a87d', '#7fb0ff', '#a8d8a8', '#c084fc',
] as const

export const CATEGORY_FALLBACK = '#565c69'

export const tooltipStyle = {
  backgroundColor: CHART_SURFACE.card,
  border: `1px solid ${CHART_SURFACE.border}`,
  borderRadius: '8px',
  boxShadow: '0 12px 32px rgba(0,0,0,0.45)',
  fontSize: '12px',
} as const

export const tooltipLabelStyle = {
  color: CHART_TEXT.faint,
  fontSize: '11px',
  marginBottom: '2px',
} as const

export const tooltipItemStyle = {
  color: CHART_TEXT.primary,
} as const

export const AXIS_STROKE = 'rgba(255,255,255,0.28)'
export const GRID_STROKE = 'rgba(255,255,255,0.04)'
