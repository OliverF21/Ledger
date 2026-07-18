import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'

export interface CryptoHolding {
  symbol: string
  contract_address: string
  decimals: number
  balance: number
  usd_value: number
}

export interface CryptoWallet {
  id: number
  address: string
  label: string | null
  chain: string
  usd_total: number
  last_synced_at: string | null
  last_error: string | null
  holdings: CryptoHolding[]
}

export interface CryptoWalletsResponse {
  wallets: CryptoWallet[]
  alchemy_configured: boolean
}

export function useCryptoWallets() {
  const [data, setData] = useState<CryptoWalletsResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const refetch = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiFetch('/api/crypto/wallets')
      if (!res.ok) throw new Error('Failed to load wallets')
      setData(await res.json())
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refetch()
  }, [refetch])

  return { data, loading, refetch }
}
