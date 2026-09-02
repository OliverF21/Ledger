import { useCallback, useEffect, useRef, useState } from 'react'
import type { ToastTone } from '../utils/syncToast'

export const TOAST_EVENT = 'ledger:toast'

export interface ToastInput {
  tone: ToastTone
  title: string
  detail?: string
}

export interface Toast extends ToastInput {
  id: number
}

let nextId = 1

export function showToast(toast: ToastInput) {
  window.dispatchEvent(new CustomEvent(TOAST_EVENT, { detail: toast }))
}

const DEFAULT_DURATION_MS = 5600
const MAX_VISIBLE = 3

export function useToasts(durationMs = DEFAULT_DURATION_MS) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timers = useRef(new Map<number, number>())

  const clearTimer = useCallback((id: number) => {
    const handle = timers.current.get(id)
    if (handle != null) {
      window.clearTimeout(handle)
      timers.current.delete(id)
    }
  }, [])

  const dismiss = useCallback((id: number) => {
    clearTimer(id)
    setToasts(prev => prev.filter(toast => toast.id !== id))
  }, [clearTimer])

  const scheduleDismiss = useCallback((id: number) => {
    clearTimer(id)
    timers.current.set(id, window.setTimeout(() => dismiss(id), durationMs))
  }, [clearTimer, dismiss, durationMs])

  useEffect(() => {
    const onToast = (event: Event) => {
      const input = (event as CustomEvent<ToastInput>).detail
      if (!input?.title) return
      const toast: Toast = { ...input, id: nextId++ }
      setToasts(prev => [...prev.slice(-(MAX_VISIBLE - 1)), toast])
      scheduleDismiss(toast.id)
    }
    window.addEventListener(TOAST_EVENT, onToast)
    return () => window.removeEventListener(TOAST_EVENT, onToast)
  }, [scheduleDismiss])

  useEffect(() => () => {
    timers.current.forEach(handle => window.clearTimeout(handle))
    timers.current.clear()
  }, [])

  const pause = useCallback((id: number) => clearTimer(id), [clearTimer])
  const resume = useCallback((id: number) => scheduleDismiss(id), [scheduleDismiss])

  return { toasts, dismiss, pause, resume }
}
