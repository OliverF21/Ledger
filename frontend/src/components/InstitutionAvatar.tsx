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

interface InstitutionAvatarProps {
  name: string | null
  logo?: string | null
  color?: string | null
  size?: number
  className?: string
}

export default function InstitutionAvatar({
  name,
  logo,
  color,
  size = 22,
  className = '',
}: InstitutionAvatarProps) {
  const label = name || '?'
  const bg = color || fallbackColor(name)

  return (
    <div
      className={`relative rounded-[6px] shrink-0 overflow-hidden ${className}`}
      style={{ width: size, height: size, backgroundColor: bg }}
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
        <div className="absolute inset-0 flex items-center justify-center font-bold text-white leading-none">
          <span style={{ fontSize: Math.max(9, Math.round(size * 0.45)) }}>
            {label.charAt(0).toUpperCase()}
          </span>
        </div>
      )}
    </div>
  )
}
