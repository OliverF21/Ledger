import { usePlaidHostedLink } from '../hooks/usePlaidHostedLink'

interface PlaidLinkProps {
  onSuccess: () => void
  onError?: (error: string) => void
}

/** Guidance shown while the hosted Plaid flow is open in the system browser. */
function WaitingHint({ onReopen, onCancel }: { onReopen: () => void; onCancel: () => void }) {
  return (
    <div className="text-[11px] text-ledger-text-faint leading-snug space-y-1">
      <p>
        A secure Plaid window opened in your browser. Finish connecting there —
        this updates automatically when you’re done.
      </p>
      <div className="flex gap-3">
        <button type="button" onClick={onReopen} className="text-ledger-accent hover:opacity-70 transition-opacity">
          Didn’t open? Reopen
        </button>
        <button type="button" onClick={onCancel} className="text-ledger-text-faint hover:opacity-70 transition-opacity">
          Cancel
        </button>
      </div>
    </div>
  )
}

/** Link a new bank/brokerage institution via Plaid Hosted Link. */
export default function PlaidLinkButton({ onSuccess, onError }: PlaidLinkProps) {
  const { status, error, start, reopen, cancel } = usePlaidHostedLink({ onSuccess, onError })
  const busy = status === 'starting' || status === 'waiting'

  return (
    <div className="space-y-[10px]">
      <button
        type="button"
        onClick={() => void start()}
        disabled={busy}
        className="w-full ghost-add flex items-center justify-center h-10 px-4 font-semibold text-[12.5px] disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {status === 'starting'
          ? 'Opening…'
          : status === 'waiting'
            ? 'Finish in your browser…'
            : '+ Link new account'}
      </button>
      {status === 'waiting' && <WaitingHint onReopen={reopen} onCancel={cancel} />}
      {error && <p className="text-[11px] text-ledger-negative leading-snug">{error}</p>}
    </div>
  )
}

interface PlaidUpdateProps extends PlaidLinkProps {
  itemId: number
  label?: string
  className?: string
}

/** Re-authenticate an existing Item via Plaid Hosted Link (update mode). */
export function PlaidUpdateButton({
  itemId,
  onSuccess,
  onError,
  label = 'Update connection',
  className,
}: PlaidUpdateProps) {
  const { status, start, reopen } = usePlaidHostedLink({ onSuccess, onError })
  const cls =
    className ??
    'text-[11.5px] text-ledger-accent hover:opacity-70 transition-opacity disabled:opacity-40 font-medium'

  // While the hosted flow is open, the button re-opens the tab if it was lost.
  if (status === 'waiting') {
    return (
      <button type="button" onClick={reopen} className={cls}>
        Finish in browser…
      </button>
    )
  }

  return (
    <button
      type="button"
      onClick={() => void start(itemId)}
      disabled={status === 'starting'}
      className={cls}
    >
      {status === 'starting' ? 'Opening…' : label}
    </button>
  )
}
