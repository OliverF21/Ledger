import { useId } from 'react'
import { alphaColor } from '../../utils/color'

const SIZES = {
  sm: 34,
  lg: 72,
} as const

/** Donut-weight cool-white spinner. Matches the spending/allocation annulus
 *  (thick track, rounded caps, ~270° arc) in chrome colors, not category ones. */
export function LedgerLoader({
  size = 'lg',
  label = 'Loading…',
}: {
  size?: keyof typeof SIZES
  label?: string | null
}) {
  const px = SIZES[size]
  const gid = useId().replace(/:/g, '')
  const glowId = `${gid}-glow`
  const arcId = `${gid}-arc`

  // ViewBox 72, mid-radius 26, stroke 9 → same ~14% thickness as the chart donut.
  const r = 26
  const stroke = 9
  const circ = 2 * Math.PI * r
  const arc = circ * 0.75
  const bloom = Math.round(px * 0.42)

  return (
    <div
      className="relative flex flex-col items-center gap-4 text-ledger-text-primary"
      role="status"
      aria-label={label ?? 'Loading'}
    >
      <div className="relative" style={{ width: px, height: px }}>
        <div
          className="absolute left-1/2 top-1/2 pointer-events-none rounded-full"
          style={{
            width: bloom,
            height: bloom,
            transform: 'translate(-50%, -50%)',
            background: `radial-gradient(circle, ${alphaColor('#e8eef8', 0.28)} 0%, ${alphaColor('#e8eef8', 0)} 72%)`,
            filter: `blur(${Math.round(px * 0.12)}px)`,
          }}
        />
        <div className="ledger-loader-spin absolute inset-0">
          <svg width={px} height={px} viewBox="0 0 72 72" className="block" fill="none">
            <defs>
              <linearGradient id={arcId} x1="18" y1="8" x2="58" y2="62" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="#ffffff" />
                <stop offset="100%" stopColor="#dbe4f2" />
              </linearGradient>
              <filter id={glowId} x="-40%" y="-40%" width="180%" height="180%">
                <feGaussianBlur in="SourceGraphic" stdDeviation="1.4" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            <circle cx="36" cy="36" r={r} stroke="rgba(255,255,255,0.12)" strokeWidth={stroke} />
            <circle
              cx="36"
              cy="36"
              r={r}
              stroke={`url(#${arcId})`}
              strokeWidth={stroke}
              strokeLinecap="round"
              strokeDasharray={`${arc} ${circ - arc}`}
              transform="rotate(-80 36 36)"
              filter={`url(#${glowId})`}
            />
          </svg>
        </div>
      </div>
      {label && (
        <div className="text-[13px] text-ledger-text-faint">{label}</div>
      )}
    </div>
  )
}
