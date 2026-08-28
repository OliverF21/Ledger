const INSTITUTION_COLORS = [
  '#1d4ed8', '#0a7d4b', '#7c3aed', '#b45309', '#0e7490',
  '#be185d', '#15803d', '#c2410c', '#4338ca', '#0369a1',
]

function fallbackColor(name: string | null): string {
  if (!name) return '#374151'
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) | 0
  return INSTITUTION_COLORS[Math.abs(hash) % INSTITUTION_COLORS.length]
}

/** Up to two letters: "Chase Sapphire" → "CS", "Coinbase" → "CO". */
function initials(name: string | null): string {
  const words = (name ?? '').trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return '?'
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[1][0]).toUpperCase()
}

interface InstitutionAvatarProps {
  name: string | null
  logo?: string | null
  color?: string | null
  size?: number
  className?: string
}

/**
 * Institution mark. Uses the bank's own logo when Plaid gives us one;
 * otherwise a tinted initials chip. The V2 treatment darkens the brand colour
 * into a gradient and adds a hairline light border so the chip belongs to the
 * same glass family as everything around it.
 */
export default function InstitutionAvatar({
  name,
  logo,
  color,
  size = 24,
  className = '',
}: InstitutionAvatarProps) {
  const base = color || fallbackColor(name)

  return (
    <div
      className={`relative shrink-0 overflow-hidden flex items-center justify-center ${className}`}
      style={{
        width: size,
        height: size,
        borderRadius: Math.max(6, Math.round(size * 0.29)),
        background: `linear-gradient(150deg, ${base}, ${base}55)`,
        border: '1px solid rgba(255,255,255,0.18)',
      }}
      aria-hidden
    >
      {logo ? (
        <img
          src={logo}
          alt=""
          className="absolute inset-0 w-full h-full object-cover"
          style={{ transform: 'scale(1.15)' }}
        />
      ) : (
        <span
          className="font-bold leading-none text-white"
          style={{ fontSize: Math.max(9, Math.round(size * 0.42)) }}
        >
          {initials(name)}
        </span>
      )}
    </div>
  )
}
