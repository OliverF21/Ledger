import { useCallback } from 'react'
import { AlertCircle, AlertTriangle, Check, X } from 'lucide-react'
import { useOnSyncComplete } from '../hooks/useSync'
import { showToast, useToasts } from '../hooks/useToasts'
import type { Toast } from '../hooks/useToasts'
import { syncToastFromResult } from '../utils/syncToast'

const TONE: Record<Toast['tone'], { icon: typeof Check; color: string; well: string }> = {
  success: {
    icon: Check,
    color: '#74d8a8',
    well: 'rgba(116,216,168,0.14)',
  },
  warning: {
    icon: AlertTriangle,
    color: '#e6bd79',
    well: 'rgba(230,189,121,0.14)',
  },
  error: {
    icon: AlertCircle,
    color: '#f4907f',
    well: 'rgba(244,144,127,0.14)',
  },
}

/**
 * App-wide toast stack. Listens for `ledger:toast` and for Plaid sync
 * completion so a finished sync is announced without a blocking dialog.
 */
export default function ToastHost() {
  const { toasts, dismiss, pause, resume } = useToasts()

  useOnSyncComplete(useCallback((result) => {
    showToast(syncToastFromResult(result))
  }, []))

  if (toasts.length === 0) return null

  return (
    <div
      className="fixed bottom-5 right-5 z-[60] flex flex-col-reverse gap-2 w-[min(360px,calc(100vw-28px))] pointer-events-none"
      aria-live="polite"
      aria-relevant="additions"
    >
      {toasts.map(toast => {
        const tone = TONE[toast.tone]
        const Icon = tone.icon
        return (
          <div
            key={toast.id}
            role="status"
            onMouseEnter={() => pause(toast.id)}
            onMouseLeave={() => resume(toast.id)}
            className="pointer-events-auto glass-card overflow-hidden rounded-[16px] px-[13px] py-[11px] ledger-rise-fast"
          >
            <div className="flex items-start gap-[10px]">
              <span
                className="mt-[1px] flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-[8px]"
                style={{ background: tone.well, color: tone.color }}
              >
                <Icon className="w-[13px] h-[13px]" strokeWidth={2.4} />
              </span>
              <div className="min-w-0 flex-1 pt-[1px]">
                <p className="text-[13px] font-semibold leading-tight text-white">
                  {toast.title}
                </p>
                {toast.detail && (
                  <p className="mt-[3px] text-[12px] leading-snug text-ledger-text-secondary">
                    {toast.detail}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                aria-label="Dismiss notification"
                className="shrink-0 -mr-[2px] -mt-[2px] w-[22px] h-[22px] rounded-[6px] flex items-center justify-center text-ledger-text-faint hover:text-white hover:bg-white/[0.08]"
              >
                <X className="w-[12px] h-[12px]" strokeWidth={2.2} />
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
