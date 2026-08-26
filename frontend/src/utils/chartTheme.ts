// Chart theming, kept next to the design tokens rather than inline per page.
//
// Recharts takes colours as props, not classes, so chart chrome cannot read the
// Tailwind theme. Before this module every page hardcoded its own tooltip
// background, axis stroke and category palette, which meant a token change left
// the charts on the previous surface colour. Import from here instead so chart
// chrome moves with the tokens.
//
// Values mirror `tailwind.config.js`. Keep them in step.

/** Surfaces and hairlines, mirroring the `ledger-*` colour tokens. */
export const CHART_SURFACE = {
  card: '#13171e',
  cardAlt: '#171b24',
  inset: '#101319',
  bg: '#0a0c11',
  border: '#20252f',
  borderStrong: '#333b4a',
} as const

/** Text steps, mirroring the `ledger-text-*` tokens. */
export const CHART_TEXT = {
  primary: '#e5e8ef',
  secondary: '#c5cbd8',
  muted: '#a4acbb',
  faint: '#969eab',
  faintest: '#858d9a',
} as const

export const CHART_ACCENT = '#5b8def'
export const CHART_POSITIVE = '#4ec38a'
export const CHART_NEGATIVE = '#e7705f'
export const CHART_WARNING = '#d9a85b'

/**
 * Categorical series colours. Adjacent entries differ in both hue and
 * lightness so neighbouring donut slices and stacked bars stay separable.
 */
export const CATEGORY_PALETTE = [
  '#5b8def', '#4fc4c4', '#8a7df0', '#4ec38a', '#d9a85b',
  '#e7705f', '#f0a87d', '#7fb0ff', '#9ed3a8', '#b98ae0',
] as const

/** Fallback for a slice with no assigned colour. */
export const CATEGORY_FALLBACK = '#5d6472'

/** Shared Recharts `<Tooltip>` chrome. */
export const tooltipStyle = {
  backgroundColor: CHART_SURFACE.cardAlt,
  border: `1px solid ${CHART_SURFACE.borderStrong}`,
  borderRadius: '10px',
  boxShadow: '0 20px 48px -20px rgba(3,5,10,0.80)',
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

/** Axis tick/line colour. Deliberately quiet: axes frame data, not compete. */
export const AXIS_STROKE = CHART_TEXT.faintest
export const GRID_STROKE = CHART_SURFACE.border
