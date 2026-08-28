/**
 * Shared surface primitives for the Ledger V2 design language.
 *
 * Everything here is presentational — no data fetching, no app state. Pages
 * compose these rather than re-deriving the glass/typography recipes, which
 * is what keeps one screen from drifting away from the rest.
 */
import type { CSSProperties, ReactNode } from 'react'

/* ── Type scale ───────────────────────────────────────────────────────────
   The uppercase micro-label above a figure or a section. Two sizes: `md`
   (10px/0.18em) heads a page section, `sm` (9.5px/0.16em) heads a stat
   inside a card. Anything smaller stops being readable on a glass fill. */

export function Eyebrow({
  children,
  size = 'md',
  className = '',
}: {
  children: ReactNode
  size?: 'sm' | 'md'
  className?: string
}) {
  const scale = size === 'sm'
    ? 'text-[9.5px] tracking-[0.16em]'
    : 'text-[10px] tracking-[0.18em]'
  return (
    <div className={`${scale} uppercase font-semibold whitespace-nowrap text-ledger-text-eyebrow ${className}`}>
      {children}
    </div>
  )
}

/* ── Surfaces ─────────────────────────────────────────────────────────── */

export function GlassCard({
  children,
  className = '',
  style,
  rise = true,
}: {
  children: ReactNode
  className?: string
  style?: CSSProperties
  /** Play the mount entrance. Turn off for cards rendered inside a list that
   *  re-renders often, where a repeated rise reads as a flicker. */
  rise?: boolean
}) {
  return (
    <div className={`glass-card overflow-hidden ${rise ? 'ledger-rise' : ''} ${className}`} style={style}>
      {children}
    </div>
  )
}

/** The small flat tile used for stats, table wrappers and inline controls. */
export function Chip({
  children,
  className = '',
  style,
}: {
  children: ReactNode
  className?: string
  style?: CSSProperties
}) {
  return <div className={`glass-chip ${className}`} style={style}>{children}</div>
}

/** Eyebrow + figure, the five-across row on the risk card and elsewhere. */
export function StatTile({
  label,
  value,
  hint,
  tone = 'neutral',
  className = '',
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'neutral' | 'positive' | 'negative'
  className?: string
}) {
  const toneClass =
    tone === 'positive' ? 'text-ledger-positive-soft'
      : tone === 'negative' ? 'text-ledger-negative-soft'
      : ''
  return (
    <Chip className={`px-3 py-2.5 min-w-0 ${className}`}>
      <div className="text-[9.5px] uppercase tracking-[0.14em] font-semibold text-ledger-text-faint truncate">
        {label}
      </div>
      <div className={`mt-1 text-[15px] font-bold tabular-nums tracking-tight ${toneClass}`}>{value}</div>
      {hint && <div className="mt-1 text-[10px] text-ledger-text-faint leading-snug">{hint}</div>}
    </Chip>
  )
}

/* ── Controls ─────────────────────────────────────────────────────────── */

/** Segmented control (6M/1Y, Security/Type). The selected tab is the only
 *  solid-white surface, matching the primary-CTA treatment at chip scale. */
export function SegmentedToggle<T extends string>({
  options,
  value,
  onChange,
  className = '',
}: {
  options: readonly { value: T; label: string }[]
  value: T
  onChange: (next: T) => void
  className?: string
}) {
  return (
    <div className={`flex gap-[5px] ${className}`}>
      {options.map(option => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`text-[11.5px] font-semibold px-[9px] py-[4px] rounded-[7px] border transition-colors ${
              active
                ? 'bg-white text-ledger-accent-on border-white'
                : 'bg-white/[0.06] text-white/56 border-white/[0.13] hover:text-white'
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

/** Two-value unit switch rendered as one joined pill (%/$ on the VaR table). */
export function UnitToggle<T extends string>({
  options,
  value,
  onChange,
}: {
  options: readonly { value: T; label: string }[]
  value: T
  onChange: (next: T) => void
}) {
  return (
    <div className="flex rounded-[7px] overflow-hidden border border-white/[0.15]">
      {options.map(option => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`text-[10px] font-semibold px-2 py-[2px] transition-colors ${
              active ? 'bg-[rgba(130,169,242,0.22)] text-white' : 'text-white/50 hover:text-white/80'
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export function Switch({
  checked,
  onChange,
  label,
  id,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  label: string
  id?: string
}) {
  return (
    <div className="flex items-center gap-2.5">
      <span id={id} className="text-[12px] font-semibold text-ledger-text-secondary">{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={id}
        onClick={() => onChange(!checked)}
        className="w-[34px] h-[20px] rounded-full p-[2px] flex box-border border border-white/20 transition-colors"
        style={{ background: checked ? '#5484da' : 'rgba(255,255,255,0.14)' }}
      >
        <span
          className="w-[14px] h-[14px] rounded-full bg-white transition-transform"
          style={{
            boxShadow: '0 2px 5px rgba(0,0,0,0.4)',
            transform: checked ? 'translateX(14px)' : 'translateX(0)',
          }}
        />
      </button>
    </div>
  )
}

/* ── Indicators ───────────────────────────────────────────────────────── */

/** Signed percentage pill with a direction arrow — the badge beside a hero
 *  figure. `positive` is passed rather than inferred so callers can invert it
 *  where down is good (spending trends). */
export function ChangeBadge({
  positive,
  children,
  className = '',
}: {
  positive: boolean
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 text-[11.5px] font-bold px-[9px] py-[3px] pl-[6px] rounded-[8px] whitespace-nowrap ${className}`}
      style={{
        color: positive ? '#74d8a8' : '#f4907f',
        background: positive ? 'rgba(120,220,170,0.13)' : 'rgba(244,144,127,0.13)',
        border: `1px solid ${positive ? 'rgba(120,220,170,0.28)' : 'rgba(244,144,127,0.28)'}`,
      }}
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
        {positive
          ? <><path d="M12 19V5" /><path d="M6 11l6-6 6 6" /></>
          : <><path d="M12 5v14" /><path d="M18 13l-6 6-6-6" /></>}
      </svg>
      {children}
    </span>
  )
}

/** Small neutral tag — transaction categories, activity types. */
export function Tag({
  children,
  color,
  className = '',
}: {
  children: ReactNode
  /** Tint the tag to a category colour; omit for the neutral grey default. */
  color?: string
  className?: string
}) {
  const tinted = color
    ? { color, background: `${color}22`, borderColor: `${color}4d` }
    : undefined
  return (
    <span
      className={`inline-block text-[10px] font-semibold px-2 py-[3px] rounded-[7px] whitespace-nowrap border ${
        color ? '' : 'text-ledger-text-secondary bg-white/[0.08] border-white/[0.14]'
      } ${className}`}
      style={tinted}
    >
      {children}
    </span>
  )
}

/** Horizontal progress bar. `height` 6 for a section total, 4 for a row. */
export function ProgressBar({
  pct,
  color = '#ffffff',
  height = 4,
  glow = false,
}: {
  pct: number
  color?: string
  height?: number
  glow?: boolean
}) {
  const clamped = Math.max(0, Math.min(100, pct))
  return (
    <div
      className="rounded-full bg-white/[0.09] overflow-hidden w-full"
      style={{ height }}
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full rounded-full transition-[width] duration-500 ease-out"
        style={{
          width: `${clamped}%`,
          background: `linear-gradient(90deg, ${color}8c, ${color})`,
          boxShadow: glow ? `0 0 14px ${color}8c` : undefined,
        }}
      />
    </div>
  )
}

/** Circular initials chip used for institutions, merchants and avatars. */
export function InitialsChip({
  initials,
  color,
  size = 28,
  radius = 9,
}: {
  initials: string
  /** Base colour to tint the chip; omit for neutral white glass. */
  color?: string
  size?: number
  radius?: number
}) {
  return (
    <div
      className="flex-shrink-0 flex items-center justify-center font-bold"
      style={{
        width: size,
        height: size,
        borderRadius: radius,
        fontSize: Math.max(9, size * 0.38),
        color: color ?? 'rgba(255,255,255,0.85)',
        background: color
          ? `linear-gradient(150deg, ${color}4d, ${color}14)`
          : 'linear-gradient(150deg, rgba(255,255,255,0.22), rgba(255,255,255,0.06))',
        border: `1px solid ${color ? `${color}47` : 'rgba(255,255,255,0.2)'}`,
      }}
    >
      {initials}
    </div>
  )
}

/* ── States ───────────────────────────────────────────────────────────── */

export function EmptyState({
  title,
  body,
  action,
  className = '',
}: {
  title: string
  body?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={`flex flex-col items-center justify-center text-center px-6 py-10 ${className}`}>
      <div className="text-[14px] font-semibold text-ledger-text-primary">{title}</div>
      {body && <div className="mt-1.5 text-[12.5px] text-ledger-text-faint max-w-[380px] leading-relaxed">{body}</div>}
      {action && <div className="mt-3.5">{action}</div>}
    </div>
  )
}

export function LoadingRow({ label = 'Loading…', className = '' }: { label?: string; className?: string }) {
  return (
    <div className={`flex items-center justify-center py-8 text-[12.5px] text-ledger-text-faint ${className}`}>
      {label}
    </div>
  )
}
