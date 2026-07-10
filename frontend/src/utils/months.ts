export interface MonthOption {
  value: string  // "YYYY-MM"
  label: string  // "January 2026"
}

const MONTH_VALUE_RE = /^\d{4}-\d{2}$/

/**
 * Builds a descending list of recent months as {value, label} options.
 * `startOffset` months back from the current month is the first entry
 * (0 = include the current month, 1 = start from last month).
 */
export function getMonthOptions(count: number, startOffset = 0): MonthOption[] {
  const options: MonthOption[] = []
  const now = new Date()
  for (let i = startOffset; i < startOffset + count; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    const label = d.toLocaleString('en-US', { month: 'long', year: 'numeric' })
    options.push({ value, label })
  }
  return options
}

export function currentMonthValue(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

/** Local-time label for a YYYY-MM value (avoids UTC date-only parsing bugs). */
export function formatMonthLabel(month: string): string {
  const [year, mon] = month.split('-').map(Number)
  const d = new Date(year, mon - 1, 1)
  return d.toLocaleString('en-US', { month: 'long', year: 'numeric' })
}

export function getMonthFromUrl(param = 'month'): string | null {
  const value = new URLSearchParams(window.location.search).get(param)
  return value && MONTH_VALUE_RE.test(value) ? value : null
}

export function setMonthInUrl(month: string, param = 'month'): void {
  const url = new URL(window.location.href)
  url.searchParams.set(param, month)
  window.history.replaceState(null, '', url.toString())
}

function readStoredMonth(storageKey: string): string | null {
  try {
    const stored = localStorage.getItem(storageKey)
    return stored && MONTH_VALUE_RE.test(stored) ? stored : null
  } catch {
    return null
  }
}

export function storeMonth(storageKey: string, value: string): void {
  try {
    localStorage.setItem(storageKey, value)
  } catch {
    // private browsing / storage disabled
  }
}

/**
 * Resolve the overview month: URL param wins, then localStorage, then current month.
 */
export function resolveSelectedMonth(
  storageKey: string,
  options: MonthOption[],
): string {
  const valid = new Set(options.map(o => o.value))
  const fromUrl = getMonthFromUrl()
  if (fromUrl && valid.has(fromUrl)) return fromUrl

  const stored = readStoredMonth(storageKey)
  if (stored && valid.has(stored)) return stored

  const current = currentMonthValue()
  if (valid.has(current)) return current

  return options[0]?.value ?? current
}
