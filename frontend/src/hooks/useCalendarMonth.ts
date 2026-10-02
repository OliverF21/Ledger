import { useEffect, useRef, useState } from 'react'
import { currentMonthValue, getMonthOptions, type MonthOption } from '../utils/months'

/** YYYY-MM that advances when the calendar month changes, including in a tab left open. */
export function useCalendarMonth(): string {
  const [month, setMonth] = useState(currentMonthValue)

  useEffect(() => {
    const tick = () => {
      const next = currentMonthValue()
      setMonth(current => (current === next ? current : next))
    }
    tick()
    document.addEventListener('visibilitychange', tick)
    const id = window.setInterval(tick, 60_000)
    return () => {
      document.removeEventListener('visibilitychange', tick)
      window.clearInterval(id)
    }
  }, [])

  return month
}

/**
 * Month dropdown for a screen that stays mounted.
 *
 * Options are built when the screen renders, not when its module is first
 * imported. A session opened in September otherwise keeps a frozen list whose
 * newest entry is September, so an October budget is invisible until a reload
 * re-imports the module.
 */
export function useRollingMonth(count: number): {
  monthOptions: MonthOption[]
  selectedMonth: string
  setSelectedMonth: (month: string) => void
} {
  const calendarMonth = useCalendarMonth()
  // Built from today's date on each render, so a session left open from
  // September picks up October without a reload.
  const monthOptions = getMonthOptions(count)
  const [selectedMonth, setSelectedMonthState] = useState(currentMonthValue)
  const picked = useRef(false)

  useEffect(() => {
    if (picked.current) return
    setSelectedMonthState(current => (current === calendarMonth ? current : calendarMonth))
  }, [calendarMonth])

  const setSelectedMonth = (month: string) => {
    picked.current = true
    setSelectedMonthState(month)
  }

  return { monthOptions, selectedMonth, setSelectedMonth }
}
