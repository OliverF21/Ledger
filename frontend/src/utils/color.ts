// Shared color helpers for chart gradients and glows.
// Extracted from Overview.tsx so the donut/ring gradient technique can be
// reused (e.g. the login page's GradientRing).

export function hexToRgb(hex: string) {
  const normalized = hex.replace('#', '')
  const expanded = normalized.length === 3
    ? normalized.split('').map(char => char + char).join('')
    : normalized

  const value = Number.parseInt(expanded, 16)
  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255,
  }
}

export function alphaColor(base: string, alpha: number) {
  const { r, g, b } = hexToRgb(base)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

export function mixHex(base: string, mixWith: string, weight: number) {
  const a = hexToRgb(base)
  const b = hexToRgb(mixWith)
  const blend = (start: number, end: number) => Math.round(start + (end - start) * weight)

  return `rgb(${blend(a.r, b.r)}, ${blend(a.g, b.g)}, ${blend(a.b, b.b)})`
}
