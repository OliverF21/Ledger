import { ChevronRight } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { CATEGORY_GROUPS } from '../utils/plaidCategories'
import { formatCategory } from '../utils/categories'

interface CategoryPickerProps {
  draft: string
  customCategories?: string[]
  initialExpandedPrimary?: string | null
  onSelect: (category: string) => void
}

export default function CategoryPicker({
  draft,
  customCategories = [],
  initialExpandedPrimary = null,
  onSelect,
}: CategoryPickerProps) {
  const query = draft.trim().toLowerCase()

  const filteredGroups = useMemo(() => {
    return CATEGORY_GROUPS.map(group => {
      const primaryMatches = !query || group.label.toLowerCase().includes(query)
      const matchingSubs = group.subcategories.filter(
        sub => !query || sub.label.toLowerCase().includes(query) || primaryMatches,
      )
      if (!query) {
        return { ...group, visible: true, subs: group.subcategories }
      }
      if (primaryMatches || matchingSubs.length > 0) {
        return {
          ...group,
          visible: true,
          subs: primaryMatches ? group.subcategories : matchingSubs,
        }
      }
      return { ...group, visible: false, subs: [] as typeof group.subcategories }
    }).filter(g => g.visible)
  }, [query])

  const filteredCustom = useMemo(() => {
    if (!customCategories.length) return []
    return customCategories.filter(c => !query || c.toLowerCase().includes(query))
  }, [customCategories, query])

  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const initial = new Set<string>()
    if (initialExpandedPrimary) initial.add(initialExpandedPrimary)
    return initial
  })

  useEffect(() => {
    if (query) {
      setExpanded(new Set(filteredGroups.map(g => g.primary)))
    } else if (initialExpandedPrimary) {
      setExpanded(new Set([initialExpandedPrimary]))
    } else {
      setExpanded(new Set())
    }
  }, [query, initialExpandedPrimary, filteredGroups])

  const toggle = (primary: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(primary)) next.delete(primary)
      else next.add(primary)
      return next
    })
  }

  const hasResults = filteredGroups.length > 0 || filteredCustom.length > 0

  if (!hasResults) {
    return (
      <div className="px-[10px] py-[12px] text-[12px] text-ledger-text-faint">
        No matching categories. Press Enter to save a custom label.
      </div>
    )
  }

  return (
    <div className="max-h-[280px] overflow-y-auto">
      {filteredGroups.map(group => {
        const isOpen = expanded.has(group.primary)
        const primarySelected = group.label === draft.trim()
        return (
          <div key={group.primary} className="border-b border-white/6 last:border-0">
            <div className="flex items-stretch">
              <button
                type="button"
                onClick={() => toggle(group.primary)}
                className="flex items-center gap-[6px] px-[10px] py-[8px] text-ledger-text-faint hover:text-ledger-text-secondary hover:bg-white/4 transition-colors"
                aria-expanded={isOpen}
                aria-label={isOpen ? `Collapse ${group.label}` : `Expand ${group.label}`}
              >
                <ChevronRight
                  className={`w-[12px] h-[12px] transition-transform ${isOpen ? 'rotate-90' : ''}`}
                  strokeWidth={2.2}
                />
              </button>
              <button
                type="button"
                onClick={() => onSelect(group.label)}
                className={`flex-1 flex items-center justify-between gap-3 px-[4px] pr-[10px] py-[8px] text-left text-[12px] transition-colors ${
                  primarySelected
                    ? 'bg-white/16 text-ledger-text-primary'
                    : 'text-ledger-text-secondary hover:bg-white/6 hover:text-ledger-text-primary'
                }`}
              >
                <span className="font-medium truncate">{group.label}</span>
                <span className="text-[10px] uppercase tracking-[0.08em] text-ledger-text-faintest">
                  All
                </span>
              </button>
            </div>

            {isOpen && (
              <div className="pb-[4px]">
                {group.subs.map(sub => {
                  const isSelected = sub.label === draft.trim()
                  return (
                    <button
                      key={sub.key}
                      type="button"
                      onClick={() => onSelect(sub.label)}
                      className={`w-full flex items-center justify-between gap-3 pl-[34px] pr-[10px] py-[7px] text-left text-[12px] transition-colors ${
                        isSelected
                          ? 'bg-white/16 text-ledger-text-primary'
                          : 'text-ledger-text-muted hover:bg-white/6 hover:text-ledger-text-primary'
                      }`}
                    >
                      <span className="truncate">{sub.label}</span>
                      <span className="text-[10px] uppercase tracking-[0.08em] text-ledger-text-faintest">
                        Apply
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}

      {filteredCustom.length > 0 && (
        <div className="border-t border-white/10">
          <div className="px-[10px] py-[7px] text-[10px] uppercase tracking-[0.12em] text-ledger-text-faintest">
            Your categories
          </div>
          {filteredCustom.map(category => {
            const isSelected = category === draft.trim()
            return (
              <button
                key={category}
                type="button"
                onClick={() => onSelect(category)}
                className={`w-full flex items-center justify-between gap-3 px-[10px] py-[8px] text-left text-[12px] transition-colors ${
                  isSelected
                    ? 'bg-white/16 text-ledger-text-primary'
                    : 'text-ledger-text-secondary hover:bg-white/6 hover:text-ledger-text-primary'
                }`}
              >
                <span className="truncate">{formatCategory(category)}</span>
                <span className="text-[10px] uppercase tracking-[0.08em] text-ledger-text-faintest">
                  Apply
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
