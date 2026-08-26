
import { useState, useEffect } from 'react'
import { X, Pencil, ArrowUp, ArrowDown, Heart, ExternalLink, KeyRound, Copy } from 'lucide-react'
import { apiFetch } from '../api/client'
import {
  getPlaidConfig, putPlaidConfig, testPlaidConfig, getSyncConfig, putSyncConfig,
  getWeeklyEmailPrefs, putWeeklyEmailPrefs,
  getRecoveryCodeStatus, generateRecoveryCode,
  getRecoveryEmailStatus, putRecoveryEmail,
  getAlchemyConfig, putAlchemyConfig,
} from '../api/plaidConfig'
import { type AccountItem } from '../hooks/useAccounts'
import { useCryptoWallets } from '../hooks/useCryptoWallets'
import { useSync } from '../hooks/useSync'
import PlaidLink, { PlaidUpdateButton } from '../components/PlaidLink'
import InstitutionAvatar from '../components/InstitutionAvatar'
import { PLAID_CATEGORY_LABELS } from '../utils/plaidCategories'

interface RuleItem {
  id: number
  merchant_pattern: string
  category_name: string
  category_color: string | null
}

interface SyncStatus {
  last_synced_at: string | null
  item_count: number
  environment: string
  items?: ItemSyncInfo[]
}

interface ItemSyncInfo {
  id: number
  institution_name: string | null
  sync_status: string
  last_sync_error: string | null
  last_synced_at: string | null
}

function formatSyncTime(iso: string | null): string {
  if (!iso) return 'Never'
  const d = new Date(iso)
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function formatLargeTxnThreshold(value: string): string {
  const amount = Number(value)
  if (!Number.isFinite(amount) || amount <= 0) return '$0+'
  return `$${new Intl.NumberFormat('en-US', {
    minimumFractionDigits: Number.isInteger(amount) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(amount)}+`
}

const KOFI_URL = 'https://ko-fi.com/oliverfichte'

// Group accounts by item_id
function groupByItem(accounts: AccountItem[]): Map<number, AccountItem[]> {
  const map = new Map<number, AccountItem[]>()
  for (const acc of accounts) {
    if (!map.has(acc.item_id)) map.set(acc.item_id, [])
    map.get(acc.item_id)!.push(acc)
  }
  return map
}

interface SettingsProps {
  accounts: AccountItem[]
  loadingAccounts: boolean
  onAccountsChange: () => Promise<void>
}

export default function Settings({ accounts, loadingAccounts, onAccountsChange }: SettingsProps) {
  const { syncing, sync } = useSync()
  const {
    data: cryptoData,
    loading: loadingCrypto,
    refetch: refetchCrypto,
  } = useCryptoWallets()
  const [cryptoAddress, setCryptoAddress] = useState('')
  const [cryptoLabel, setCryptoLabel] = useState('')
  const [addingCrypto, setAddingCrypto] = useState(false)
  const [cryptoError, setCryptoError] = useState<string | null>(null)
  const [removingCryptoId, setRemovingCryptoId] = useState<number | null>(null)
  const [confirmingCryptoRemoveId, setConfirmingCryptoRemoveId] = useState<number | null>(null)
  const [refreshingCrypto, setRefreshingCrypto] = useState(false)
  const [expandedCryptoId, setExpandedCryptoId] = useState<number | null>(null)
  const [alchemyKeyDraft, setAlchemyKeyDraft] = useState('')
  const [alchemyConfigured, setAlchemyConfigured] = useState(false)
  const [savingAlchemyKey, setSavingAlchemyKey] = useState(false)
  const [alchemyKeySaveResult, setAlchemyKeySaveResult] = useState<string | null>(null)
  const [removingItemId, setRemovingItemId] = useState<number | null>(null)
  const [confirmingRemoveItemId, setConfirmingRemoveItemId] = useState<number | null>(null)
  const [removeItemError, setRemoveItemError] = useState<string | null>(null)
  const [rules, setRules] = useState<RuleItem[]>([])
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null)
  const [showRuleForm, setShowRuleForm] = useState(false)
  const [ruleMerchant, setRuleMerchant] = useState('')
  const [ruleCategory, setRuleCategory] = useState('')
  const [savingRule, setSavingRule] = useState(false)
  const [ruleError, setRuleError] = useState<string | null>(null)
  const [ruleSuccess, setRuleSuccess] = useState<string | null>(null)
  const [deletingRuleId, setDeletingRuleId] = useState<number | null>(null)
  const [editingRuleId, setEditingRuleId] = useState<number | null>(null)
  const [editMerchant, setEditMerchant] = useState('')
  const [editCategory, setEditCategory] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [budgetExceededEnabled, setBudgetExceededEnabled] = useState(true)
  const [largeTxnEnabled, setLargeTxnEnabled] = useState(false)
  const [largeTxnThreshold, setLargeTxnThreshold] = useState('500')
  const [showLargeTxnModal, setShowLargeTxnModal] = useState(false)
  const [largeTxnDraft, setLargeTxnDraft] = useState('500')
  const [largeTxnError, setLargeTxnError] = useState<string | null>(null)
  const [savingLargeTxn, setSavingLargeTxn] = useState(false)
  const [weeklyEmailEnabled, setWeeklyEmailEnabled] = useState(false)
  const [weeklyEmailAddress, setWeeklyEmailAddress] = useState('')
  const [weeklyEmailTransportConfigured, setWeeklyEmailTransportConfigured] = useState(true)
  const [showWeeklyEmailModal, setShowWeeklyEmailModal] = useState(false)
  const [weeklyEmailDraft, setWeeklyEmailDraft] = useState('')
  const [weeklyEmailError, setWeeklyEmailError] = useState<string | null>(null)
  const [savingWeeklyEmail, setSavingWeeklyEmail] = useState(false)
  const [sendingTestEmail, setSendingTestEmail] = useState(false)
  const [testEmailResult, setTestEmailResult] = useState<string | null>(null)
  const [weeklyEmailHasResendKey, setWeeklyEmailHasResendKey] = useState(false)
  const [resendApiKeyDraft, setResendApiKeyDraft] = useState('')
  const [weeklyEmailFromAddress, setWeeklyEmailFromAddress] = useState('')
  const [savingResendKey, setSavingResendKey] = useState(false)
  const [resendKeySaveResult, setResendKeySaveResult] = useState<string | null>(null)
  const [syncMessage, setSyncMessage] = useState<string | null>(null)
  const [syncWarnings, setSyncWarnings] = useState<string[]>([])
  const [plaidClientId, setPlaidClientId] = useState('')
  const [plaidEnv, setPlaidEnv] = useState('sandbox')
  const [plaidSecret, setPlaidSecret] = useState('')
  const [plaidHasSecret, setPlaidHasSecret] = useState(false)
  const [plaidLoading, setPlaidLoading] = useState(true)
  const [plaidSaving, setPlaidSaving] = useState(false)
  const [plaidTesting, setPlaidTesting] = useState(false)
  const [plaidTestResult, setPlaidTestResult] = useState<string | null>(null)
  const [plaidTestOk, setPlaidTestOk] = useState<boolean | null>(null)
  const [plaidSaveError, setPlaidSaveError] = useState<string | null>(null)
  const [plaidSaveSuccess, setPlaidSaveSuccess] = useState<string | null>(null)
  const [syncFrequencyHours, setSyncFrequencyHours] = useState(6)
  const [savingSyncFrequency, setSavingSyncFrequency] = useState(false)
  const [recoveryCodeConfigured, setRecoveryCodeConfigured] = useState<boolean | null>(null)
  const [generatingRecoveryCode, setGeneratingRecoveryCode] = useState(false)
  const [freshRecoveryCode, setFreshRecoveryCode] = useState<string | null>(null)
  const [recoveryCodeCopied, setRecoveryCodeCopied] = useState(false)
  const [recoveryCodeError, setRecoveryCodeError] = useState<string | null>(null)
  const [recoveryEmail, setRecoveryEmail] = useState<string | null>(null)
  const [recoveryEmailDraft, setRecoveryEmailDraft] = useState('')
  const [savingRecoveryEmail, setSavingRecoveryEmail] = useState(false)
  const [recoveryEmailError, setRecoveryEmailError] = useState<string | null>(null)
  const [recoveryEmailSaved, setRecoveryEmailSaved] = useState(false)

  useEffect(() => {
    fetchRules()
    fetchSyncStatus()
    fetchAlertPrefs()
    fetchWeeklyEmailPrefs()
    fetchPlaidConfig()
    fetchSyncConfig()
    fetchRecoveryCodeStatus()
    fetchRecoveryEmailStatus()
    fetchAlchemyConfig()
  }, [])

  const fetchRecoveryCodeStatus = async () => {
    try {
      const status = await getRecoveryCodeStatus()
      setRecoveryCodeConfigured(status.configured)
    } catch (error) {
      console.error('Failed to fetch recovery code status:', error)
    }
  }

  const handleGenerateRecoveryCode = async () => {
    setGeneratingRecoveryCode(true)
    setRecoveryCodeError(null)
    setFreshRecoveryCode(null)
    try {
      const result = await generateRecoveryCode()
      setFreshRecoveryCode(result.recovery_code)
      setRecoveryCodeConfigured(true)
    } catch (error) {
      setRecoveryCodeError(error instanceof Error ? error.message : 'Failed to generate a recovery code')
    } finally {
      setGeneratingRecoveryCode(false)
    }
  }

  const copyRecoveryCode = async () => {
    if (!freshRecoveryCode) return
    try {
      await navigator.clipboard.writeText(freshRecoveryCode)
      setRecoveryCodeCopied(true)
      setTimeout(() => setRecoveryCodeCopied(false), 1500)
    } catch {
      /* clipboard unavailable — ignore */
    }
  }

  const fetchRecoveryEmailStatus = async () => {
    try {
      const status = await getRecoveryEmailStatus()
      setRecoveryEmail(status.email)
    } catch (error) {
      console.error('Failed to fetch recovery email status:', error)
    }
  }

  const handleSaveRecoveryEmail = async () => {
    setSavingRecoveryEmail(true)
    setRecoveryEmailError(null)
    setRecoveryEmailSaved(false)
    try {
      const result = await putRecoveryEmail(recoveryEmailDraft.trim())
      setRecoveryEmail(result.email)
      setRecoveryEmailDraft('')
      setRecoveryEmailSaved(true)
      setTimeout(() => setRecoveryEmailSaved(false), 1500)
    } catch (error) {
      setRecoveryEmailError(error instanceof Error ? error.message : 'Failed to save recovery email')
    } finally {
      setSavingRecoveryEmail(false)
    }
  }

  const fetchSyncConfig = async () => {
    try {
      const config = await getSyncConfig()
      setSyncFrequencyHours(config.frequency_hours)
    } catch (error) {
      console.error('Failed to fetch sync frequency:', error)
    }
  }

  const handleSyncFrequencyChange = async (hours: number) => {
    setSavingSyncFrequency(true)
    try {
      const config = await putSyncConfig(hours)
      setSyncFrequencyHours(config.frequency_hours)
    } catch (error) {
      console.error('Failed to save sync frequency:', error)
    } finally {
      setSavingSyncFrequency(false)
    }
  }

  const fetchPlaidConfig = async () => {
    setPlaidLoading(true)
    try {
      const config = await getPlaidConfig()
      setPlaidClientId(config.client_id || '')
      setPlaidEnv(config.env || 'sandbox')
      setPlaidHasSecret(config.has_secret)
    } catch (error) {
      console.error('Failed to fetch Plaid config:', error)
    } finally {
      setPlaidLoading(false)
    }
  }

  const handleTestPlaidConfig = async () => {
    setPlaidTesting(true)
    setPlaidTestResult(null)
    setPlaidTestOk(null)
    try {
      const result = await testPlaidConfig({
        client_id: plaidClientId.trim() || undefined,
        env: plaidEnv,
        secret: plaidSecret.trim() || undefined,
      })
      setPlaidTestOk(result.ok)
      setPlaidTestResult(result.message)
    } catch (error) {
      setPlaidTestOk(false)
      setPlaidTestResult(error instanceof Error ? error.message : 'Test failed')
    } finally {
      setPlaidTesting(false)
    }
  }

  const handleSavePlaidConfig = async () => {
    setPlaidSaving(true)
    setPlaidSaveError(null)
    setPlaidSaveSuccess(null)
    try {
      const body: { client_id?: string; env?: string; secret?: string } = {
        client_id: plaidClientId.trim(),
        env: plaidEnv,
      }
      if (plaidSecret.trim()) {
        body.secret = plaidSecret.trim()
      }
      const config = await putPlaidConfig(body)
      setPlaidClientId(config.client_id || '')
      setPlaidEnv(config.env || 'sandbox')
      setPlaidHasSecret(config.has_secret)
      setPlaidSecret('')
      setPlaidSaveSuccess('Saved.')
    } catch (error) {
      setPlaidSaveError(error instanceof Error ? error.message : 'Failed to save')
    } finally {
      setPlaidSaving(false)
    }
  }

  const fetchWeeklyEmailPrefs = async () => {
    try {
      const data = await getWeeklyEmailPrefs()
      setWeeklyEmailEnabled(data.enabled)
      setWeeklyEmailAddress(data.email || '')
      setWeeklyEmailTransportConfigured(data.transport_configured)
      setWeeklyEmailHasResendKey(data.has_resend_key)
      setWeeklyEmailFromAddress(data.from_address || '')
    } catch (error) {
      console.error('Failed to fetch weekly email prefs:', error)
    }
  }

  const handleSaveResendConfig = async () => {
    setSavingResendKey(true)
    setResendKeySaveResult(null)
    try {
      const body: { resend_api_key?: string; from_address?: string } = {
        from_address: weeklyEmailFromAddress.trim(),
      }
      if (resendApiKeyDraft.trim()) {
        body.resend_api_key = resendApiKeyDraft.trim()
      }
      const data = await putWeeklyEmailPrefs(body)
      setWeeklyEmailTransportConfigured(data.transport_configured)
      setWeeklyEmailHasResendKey(data.has_resend_key)
      setWeeklyEmailFromAddress(data.from_address || '')
      setResendApiKeyDraft('')
      setResendKeySaveResult('Saved.')
    } catch (error) {
      setResendKeySaveResult(error instanceof Error ? error.message : 'Failed to save')
    } finally {
      setSavingResendKey(false)
    }
  }

  const handleToggleWeeklyEmail = async () => {
    if (!weeklyEmailEnabled) {
      // Turning on: always confirm/collect the recipient first, even if one
      // was set before, so a stale address doesn't get silently re-enabled.
      setWeeklyEmailDraft(weeklyEmailAddress)
      setWeeklyEmailError(null)
      setShowWeeklyEmailModal(true)
      return
    }

    setWeeklyEmailEnabled(false)
    try {
      await apiFetch('/api/settings/weekly-email', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: false }),
      })
    } catch (error) {
      console.error('Failed to update weekly email prefs:', error)
      setWeeklyEmailEnabled(true)
    }
  }

  const closeWeeklyEmailModal = () => {
    if (savingWeeklyEmail) return
    setShowWeeklyEmailModal(false)
    setWeeklyEmailDraft(weeklyEmailAddress)
    setWeeklyEmailError(null)
  }

  const handleSaveWeeklyEmail = async () => {
    const email = weeklyEmailDraft.trim()
    if (!email || !email.includes('@')) {
      setWeeklyEmailError('Enter a valid email address')
      return
    }

    setSavingWeeklyEmail(true)
    setWeeklyEmailError(null)
    try {
      const res = await apiFetch('/api/settings/weekly-email', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: true, email }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to save')
      }
      setWeeklyEmailEnabled(data.enabled)
      setWeeklyEmailAddress(data.email || '')
      setShowWeeklyEmailModal(false)
    } catch (error) {
      console.error('Failed to save weekly email settings:', error)
      setWeeklyEmailError(error instanceof Error ? error.message : 'Failed to save')
    } finally {
      setSavingWeeklyEmail(false)
    }
  }

  const handleSendTestEmail = async () => {
    setSendingTestEmail(true)
    setTestEmailResult(null)
    try {
      const res = await apiFetch('/api/weekly-email/send', { method: 'POST' })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Send failed')
      setTestEmailResult('Sent — check your inbox.')
    } catch (error) {
      setTestEmailResult(error instanceof Error ? error.message : 'Send failed')
    } finally {
      setSendingTestEmail(false)
    }
  }

  const fetchAlertPrefs = async () => {
    try {
      const response = await apiFetch('/api/settings/alerts')
      const data = await response.json()
      setBudgetExceededEnabled(data.budget_exceeded_enabled)
      setLargeTxnEnabled(data.large_txn_enabled)
      setLargeTxnThreshold(String(data.large_txn_threshold))
      setLargeTxnDraft(String(data.large_txn_threshold))
    } catch (error) {
      console.error('Failed to fetch alert prefs:', error)
    }
  }

  const handleToggleBudgetExceeded = async () => {
    const next = !budgetExceededEnabled
    setBudgetExceededEnabled(next)
    try {
      await apiFetch('/api/settings/alerts', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ budget_exceeded_enabled: next }),
      })
    } catch (error) {
      console.error('Failed to update alert prefs:', error)
      setBudgetExceededEnabled(!next)
    }
  }

  const handleToggleLargeTxn = async () => {
    if (!largeTxnEnabled) {
      setLargeTxnDraft(largeTxnThreshold)
      setLargeTxnError(null)
      setShowLargeTxnModal(true)
      return
    }

    const next = false
    setLargeTxnEnabled(false)
    try {
      await apiFetch('/api/settings/alerts', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ large_txn_enabled: next }),
      })
    } catch (error) {
      console.error('Failed to update alert prefs:', error)
      setLargeTxnEnabled(true)
    }
  }

  const closeLargeTxnModal = () => {
    if (savingLargeTxn) return
    setShowLargeTxnModal(false)
    setLargeTxnDraft(largeTxnThreshold)
    setLargeTxnError(null)
  }

  const handleSaveLargeTxnRule = async () => {
    const value = parseFloat(largeTxnDraft)
    if (isNaN(value) || value <= 0) {
      setLargeTxnError('Enter a valid amount')
      return
    }

    setSavingLargeTxn(true)
    setLargeTxnError(null)
    try {
      const res = await apiFetch('/api/settings/alerts', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ large_txn_enabled: true, large_txn_threshold: value }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to save rule')
      }

      setLargeTxnEnabled(data.large_txn_enabled)
      setLargeTxnThreshold(String(data.large_txn_threshold))
      setLargeTxnDraft(String(data.large_txn_threshold))
      setShowLargeTxnModal(false)
    } catch (error) {
      console.error('Failed to save large transaction rule:', error)
      setLargeTxnError(error instanceof Error ? error.message : 'Failed to save rule')
    } finally {
      setSavingLargeTxn(false)
    }
  }

  const handleRemoveItem = async (itemId: number) => {
    // Native window.confirm()/alert() are unreliable inside the desktop app's
    // webview (silently no-op rather than showing a dialog), so confirmation
    // is an inline two-click UI (confirmingRemoveItemId) and errors render
    // inline (removeItemError) instead of alert().
    setRemovingItemId(itemId)
    setRemoveItemError(null)
    try {
      const res = await apiFetch(`/api/plaid/item/${itemId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Delete failed')
      setConfirmingRemoveItemId(null)
      await onAccountsChange()
      await fetchSyncStatus()
    } catch (error) {
      console.error('Failed to remove item:', error)
      setRemoveItemError('Failed to remove account. Try again.')
    } finally {
      setRemovingItemId(null)
    }
  }

  const handleAddCryptoWallet = async () => {
    const address = cryptoAddress.trim()
    if (!address) {
      setCryptoError('Paste a public wallet address (0x…)')
      return
    }
    setAddingCrypto(true)
    setCryptoError(null)
    try {
      const res = await apiFetch('/api/crypto/wallets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          address,
          label: cryptoLabel.trim() || null,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Failed to add wallet')
      }
      setCryptoAddress('')
      setCryptoLabel('')
      await refetchCrypto()
    } catch (error) {
      setCryptoError(error instanceof Error ? error.message : 'Failed to add wallet')
    } finally {
      setAddingCrypto(false)
    }
  }

  const handleRemoveCryptoWallet = async (walletId: number) => {
    // Native window.confirm()/alert() are unreliable inside the desktop app's
    // webview (silently no-op rather than showing a dialog), so confirmation
    // is an inline two-click UI (confirmingCryptoRemoveId) and errors render
    // inline (cryptoError) instead of alert().
    setRemovingCryptoId(walletId)
    setCryptoError(null)
    try {
      const res = await apiFetch(`/api/crypto/wallets/${walletId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Delete failed')
      setConfirmingCryptoRemoveId(null)
      await refetchCrypto()
    } catch (error) {
      console.error('Failed to remove crypto wallet:', error)
      setCryptoError('Failed to remove wallet. Try again.')
    } finally {
      setRemovingCryptoId(null)
    }
  }

  const handleRefreshCrypto = async () => {
    setRefreshingCrypto(true)
    setCryptoError(null)
    try {
      const res = await apiFetch('/api/crypto/refresh', { method: 'POST' })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Refresh failed')
      }
      await refetchCrypto()
    } catch (error) {
      setCryptoError(error instanceof Error ? error.message : 'Refresh failed')
    } finally {
      setRefreshingCrypto(false)
    }
  }

  const fetchAlchemyConfig = async () => {
    try {
      const config = await getAlchemyConfig()
      setAlchemyConfigured(config.configured)
    } catch (error) {
      console.error('Failed to load Alchemy config:', error)
    }
  }

  const handleSaveAlchemyKey = async () => {
    if (!alchemyKeyDraft.trim()) {
      setAlchemyKeySaveResult('Paste an Alchemy API key first')
      return
    }
    setSavingAlchemyKey(true)
    setAlchemyKeySaveResult(null)
    try {
      const config = await putAlchemyConfig(alchemyKeyDraft.trim())
      setAlchemyConfigured(config.configured)
      setAlchemyKeyDraft('')
      setAlchemyKeySaveResult('Alchemy key saved')
      await refetchCrypto()
    } catch (error) {
      setAlchemyKeySaveResult(error instanceof Error ? error.message : 'Failed to save key')
    } finally {
      setSavingAlchemyKey(false)
    }
  }

  const fetchRules = async () => {
    try {
      const response = await apiFetch('/api/categorization-rules')
      const data = await response.json()
      setRules(data.rules || [])
    } catch (error) {
      console.error('Failed to fetch rules:', error)
    }
  }

  const handleCreateRule = async () => {
    const merchant_pattern = ruleMerchant.trim()
    const category_name = ruleCategory.trim()
    if (!merchant_pattern || !category_name) {
      setRuleError('Both fields are required')
      return
    }
    setSavingRule(true)
    setRuleError(null)
    setRuleSuccess(null)
    try {
      const res = await apiFetch('/api/categorization-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ merchant_pattern, category_name }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to create rule')
      }
      setRuleMerchant('')
      setRuleCategory('')
      setShowRuleForm(false)
      setRuleSuccess(
        data.applied_to_existing > 0
          ? `Rule created — applied to ${data.applied_to_existing} existing transaction${data.applied_to_existing === 1 ? '' : 's'}.`
          : 'Rule created.'
      )
      await fetchRules()
    } catch (error: any) {
      setRuleError(error.message || 'Failed to create rule')
    } finally {
      setSavingRule(false)
    }
  }

  const handleDeleteRule = async (id: number) => {
    setDeletingRuleId(id)
    try {
      await apiFetch(`/api/categorization-rules/${id}`, { method: 'DELETE' })
      await fetchRules()
    } catch (error) {
      console.error('Failed to delete rule:', error)
    } finally {
      setDeletingRuleId(null)
    }
  }

  const handleStartEdit = (rule: RuleItem) => {
    setEditingRuleId(rule.id)
    setEditMerchant(rule.merchant_pattern)
    setEditCategory(rule.category_name)
    setEditError(null)
  }

  const handleCancelEdit = () => {
    setEditingRuleId(null)
    setEditError(null)
  }

  const handleSaveEdit = async (id: number) => {
    const merchant_pattern = editMerchant.trim()
    const category_name = editCategory.trim()
    if (!merchant_pattern || !category_name) {
      setEditError('Both fields are required')
      return
    }
    setSavingEdit(true)
    setEditError(null)
    try {
      const res = await apiFetch(`/api/categorization-rules/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ merchant_pattern, category_name }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to update rule')
      }
      setEditingRuleId(null)
      await fetchRules()
    } catch (error: any) {
      setEditError(error.message || 'Failed to update rule')
    } finally {
      setSavingEdit(false)
    }
  }

  const handleMoveRule = async (index: number, direction: -1 | 1) => {
    const targetIndex = index + direction
    if (targetIndex < 0 || targetIndex >= rules.length) return
    const reordered = [...rules]
    ;[reordered[index], reordered[targetIndex]] = [reordered[targetIndex], reordered[index]]
    setRules(reordered)
    try {
      await apiFetch('/api/categorization-rules/reorder', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rule_ids: reordered.map(r => r.id) }),
      })
    } catch (error) {
      console.error('Failed to reorder rules:', error)
      await fetchRules()
    }
  }

  const fetchSyncStatus = async () => {
    try {
      const response = await apiFetch('/api/plaid/sync/status')
      const data = await response.json()
      setSyncStatus(data)
    } catch (error) {
      console.error('Failed to fetch sync status:', error)
    }
  }

  const handleSyncNow = async () => {
    setSyncMessage(null)
    setSyncWarnings([])
    try {
      const result = await sync()
      if (result) {
        setSyncMessage(result.message)
        const failures = (result.items ?? []).filter(i => i.status !== 'ok')
        setSyncWarnings(
          failures.map(f => {
            const name = f.institution_name || `Item ${f.item_id}`
            if (f.status === 'login_required') {
              return `${name}: login required — use Update connection`
            }
            return `${name}: ${f.error || 'sync failed'}`
          }),
        )
      }
      await fetchSyncStatus()
      await onAccountsChange()
    } catch (error) {
      console.error('Sync failed:', error)
      setSyncMessage(error instanceof Error ? error.message : 'Sync failed')
    }
  }

  const handleLinkSuccess = async () => {
    await onAccountsChange()
    await fetchSyncStatus()
    try {
      await sync()
      await fetchSyncStatus()
      await onAccountsChange()
    } catch (error) {
      console.error('Post-link sync failed:', error)
    }
  }

  const handleLinkError = (error: string) => {
    alert(`Link error: ${error}`)
  }

  const accountsByItem = Array.from(groupByItem(accounts))
  const itemSyncById = new Map(
    (syncStatus?.items ?? []).map(item => [item.id, item]),
  )

  function itemStatusLabel(itemId: number): { text: string; tone: 'ok' | 'warn' | 'error' } {
    const info = itemSyncById.get(itemId)
    if (!info || info.sync_status === 'ok') {
      return { text: 'Synced', tone: 'ok' }
    }
    if (info.sync_status === 'login_required') {
      return { text: 'Login required', tone: 'warn' }
    }
    return { text: 'Sync error', tone: 'error' }
  }

  return (
    <div className="w-full min-h-full flex flex-col gap-[24px]">
      <div className="grid gap-[24px] xl:grid-cols-[minmax(0,1.55fr)_minmax(340px,0.95fr)] items-start">
        <div className="flex flex-col gap-[24px]">
          {/* Linked Accounts */}
          <div className="glass-card p-[22px]">
            <h3 className="text-[14px] font-semibold mb-[16px]">Linked accounts</h3>

            {removeItemError && (
              <p className="text-[12px] text-ledger-negative mb-[12px]">{removeItemError}</p>
            )}

            {loadingAccounts ? (
              <div className="text-center py-8 text-ledger-text-faint">Loading accounts...</div>
            ) : accounts.length === 0 ? (
              <div className="text-center py-8 text-ledger-text-faint mb-4">No accounts linked yet</div>
            ) : (
              <div className="space-y-[16px] mb-4">
                {accountsByItem.map(([itemId, itemAccounts]) => {
                  const status = itemStatusLabel(itemId)
                  const syncInfo = itemSyncById.get(itemId)
                  return (
                  <div key={itemId}>
                    <div className="flex items-center justify-between mb-[8px] gap-[8px]">
                      <div className="flex items-center gap-[8px] min-w-0">
                        <InstitutionAvatar
                          name={itemAccounts[0].institution_name}
                          logo={itemAccounts[0].institution_logo}
                          color={itemAccounts[0].institution_color}
                          size={20}
                        />
                        <span className="text-[12px] font-semibold text-ledger-text-faint uppercase tracking-wide truncate">
                          {itemAccounts[0].institution_name || 'Unknown Institution'}
                        </span>
                      </div>
                      <div className="flex items-center gap-[10px] shrink-0">
                        <PlaidUpdateButton
                          itemId={itemId}
                          onSuccess={handleLinkSuccess}
                          onError={handleLinkError}
                        />
                        <button
                          onClick={() =>
                            setConfirmingRemoveItemId(prev => prev === itemId ? null : itemId)
                          }
                          disabled={removingItemId === itemId}
                          className="text-[11.5px] text-ledger-negative hover:opacity-70 transition-opacity disabled:opacity-40"
                        >
                          {removingItemId === itemId ? 'Removing…' : 'Remove'}
                        </button>
                      </div>
                    </div>
                    {confirmingRemoveItemId === itemId && (
                      <div className="flex items-center justify-between gap-[10px] mb-[8px] px-[10px] py-[8px] rounded-[8px] border border-ledger-border-subtle bg-ledger-inset/60">
                        <span className="text-[12px] text-ledger-text-secondary">
                          Remove {itemAccounts[0].institution_name || 'this institution'}? This
                          permanently deletes its accounts, transactions, and balance history.
                        </span>
                        <div className="flex items-center gap-[8px] shrink-0">
                          <button
                            type="button"
                            onClick={() => setConfirmingRemoveItemId(null)}
                            className="text-[12px] text-ledger-text-faint hover:text-ledger-text-primary transition-colors"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRemoveItem(itemId)}
                            disabled={removingItemId === itemId}
                            className="text-[12px] font-semibold text-ledger-negative hover:opacity-80 transition-opacity disabled:opacity-40"
                          >
                            {removingItemId === itemId ? 'Removing…' : 'Remove'}
                          </button>
                        </div>
                      </div>
                    )}
                    {syncInfo?.last_sync_error && syncInfo.sync_status !== 'ok' && (
                      <p className="text-[11px] text-ledger-negative mb-[8px] leading-snug">
                        {syncInfo.last_sync_error}
                      </p>
                    )}
                    <div className="space-y-[8px]">
                      {itemAccounts.map((account) => (
                        <div key={account.id} className="flex items-center justify-between p-[12px] border border-ledger-border-subtle rounded-[9px]">
                          <div className="flex items-center gap-[12px] min-w-0">
                            <InstitutionAvatar
                              name={itemAccounts[0].institution_name}
                              logo={itemAccounts[0].institution_logo}
                              color={itemAccounts[0].institution_color}
                              size={30}
                            />
                            <div className="min-w-0">
                              <div className="text-[13px] font-semibold truncate">{account.name}</div>
                              <div className={`text-[12px] ${
                                status.tone === 'ok'
                                  ? 'text-ledger-positive'
                                  : status.tone === 'warn'
                                    ? 'text-ledger-warning'
                                    : 'text-ledger-negative'
                              }`}>
                                {status.tone === 'ok' ? '✓' : '!'} {status.text} · {account.subtype}
                              </div>
                            </div>
                          </div>
                          <div className="text-right shrink-0">
                            <div className="text-[13px] font-semibold">${account.current_balance.toFixed(2)}</div>
                            <div className="text-[11px] text-ledger-text-faint">{account.type}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  )
                })}
              </div>
            )}

            <PlaidLink onSuccess={handleLinkSuccess} onError={handleLinkError} />

            <p className="text-[11.5px] text-ledger-text-faint mt-[12px]">
              Investment accounts show position detail on the <span className="font-semibold text-ledger-text-secondary">Investments</span> tab.
            </p>
          </div>

          {/* Crypto wallets */}
          <div className="glass-card p-[22px]">
            <div className="flex items-center justify-between gap-[12px] mb-[16px]">
              <h3 className="text-[14px] font-semibold">Crypto wallets</h3>
              {(cryptoData?.wallets.length ?? 0) > 0 && (
                <button
                  type="button"
                  onClick={handleRefreshCrypto}
                  disabled={refreshingCrypto || !(alchemyConfigured || cryptoData?.alchemy_configured)}
                  className="text-[11.5px] text-ledger-accent hover:opacity-70 transition-opacity disabled:opacity-40"
                >
                  {refreshingCrypto ? 'Refreshing…' : 'Refresh'}
                </button>
              )}
            </div>

            <div className="mb-[16px] space-y-[8px]">
              <label className="text-[12px] text-ledger-text-faint">
                Alchemy API key{' '}
                {(alchemyConfigured || cryptoData?.alchemy_configured) && (
                  <span className="text-ledger-text-faint">(configured)</span>
                )}
              </label>
              <input
                type="password"
                value={alchemyKeyDraft}
                onChange={(e) => setAlchemyKeyDraft(e.target.value)}
                placeholder={
                  alchemyConfigured || cryptoData?.alchemy_configured
                    ? '••••• (unchanged)'
                    : 'Alchemy API key'
                }
                className="w-full glass-chip px-[10px] py-[7px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
              />
              <p className="text-[11.5px] text-ledger-text-faint leading-snug">
                Create a free Alchemy app with Robinhood Chain Mainnet, then paste the key here.
                Free at dashboard.alchemy.com — stored encrypted on this device.
              </p>
              {alchemyKeySaveResult && (
                <p className="text-[11.5px] text-ledger-text-faint">{alchemyKeySaveResult}</p>
              )}
              <button
                type="button"
                onClick={handleSaveAlchemyKey}
                disabled={savingAlchemyKey}
                className="glass-chip px-[12px] py-[7px] rounded-[8px] text-[12.5px] font-semibold text-ledger-text-primary hover:bg-ledger-hover transition-colors disabled:opacity-50"
              >
                {savingAlchemyKey ? 'Saving…' : 'Save Alchemy key'}
              </button>
            </div>

            {!(alchemyConfigured || cryptoData?.alchemy_configured) && (
              <p className="text-[12px] text-ledger-warning mb-[12px] leading-snug">
                Add an Alchemy API key above to read Robinhood Chain balances.
              </p>
            )}

            {loadingCrypto ? (
              <div className="text-center py-6 text-ledger-text-faint">Loading wallets…</div>
            ) : (cryptoData?.wallets.length ?? 0) === 0 ? (
              <div className="text-center py-6 text-ledger-text-faint mb-2">No crypto wallets yet</div>
            ) : (
              <div className="space-y-[10px] mb-[16px]">
                {cryptoData!.wallets.map((wallet) => (
                  <div
                    key={wallet.id}
                    className="p-[12px] border border-ledger-border-subtle rounded-[9px]"
                  >
                    <div className="flex items-start justify-between gap-[12px]">
                      <button
                        type="button"
                        className="text-left min-w-0 flex-1"
                        onClick={() =>
                          setExpandedCryptoId(expandedCryptoId === wallet.id ? null : wallet.id)
                        }
                      >
                        <div className="text-[13px] font-semibold truncate">
                          {wallet.label || 'Wallet'}
                        </div>
                        <div className="text-[11.5px] text-ledger-text-faint font-mono break-all mt-[2px]">
                          {wallet.address}
                        </div>
                        <div className="text-[12px] text-ledger-text-secondary mt-[6px]">
                          ${wallet.usd_total.toFixed(2)}
                          {wallet.last_synced_at
                            ? ` · synced ${new Date(wallet.last_synced_at).toLocaleString()}`
                            : ''}
                        </div>
                        {wallet.last_error && (
                          <p className="text-[11px] text-ledger-negative mt-[4px] leading-snug">
                            {wallet.last_error}
                          </p>
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          setConfirmingCryptoRemoveId(prev => prev === wallet.id ? null : wallet.id)
                        }
                        disabled={removingCryptoId === wallet.id}
                        className="text-[11.5px] text-ledger-negative hover:opacity-70 transition-opacity disabled:opacity-40 shrink-0"
                      >
                        {removingCryptoId === wallet.id ? 'Removing…' : 'Remove'}
                      </button>
                    </div>
                    {confirmingCryptoRemoveId === wallet.id && (
                      <div className="flex items-center justify-between gap-[10px] mt-[10px] px-[10px] py-[8px] rounded-[8px] border border-ledger-border-subtle bg-ledger-inset/60">
                        <span className="text-[12px] text-ledger-text-secondary">
                          Remove this wallet? This permanently deletes it and its balance history.
                        </span>
                        <div className="flex items-center gap-[8px] shrink-0">
                          <button
                            type="button"
                            onClick={() => setConfirmingCryptoRemoveId(null)}
                            className="text-[12px] text-ledger-text-faint hover:text-ledger-text-primary transition-colors"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRemoveCryptoWallet(wallet.id)}
                            disabled={removingCryptoId === wallet.id}
                            className="text-[12px] font-semibold text-ledger-negative hover:opacity-80 transition-opacity disabled:opacity-40"
                          >
                            {removingCryptoId === wallet.id ? 'Removing…' : 'Remove'}
                          </button>
                        </div>
                      </div>
                    )}
                    {expandedCryptoId === wallet.id && wallet.holdings.length > 0 && (
                      <div className="mt-[10px] pt-[10px] border-t border-ledger-border-subtle space-y-[6px]">
                        {wallet.holdings.map((h) => (
                          <div
                            key={`${h.symbol}-${h.contract_address}`}
                            className="flex justify-between text-[12px]"
                          >
                            <span className="text-ledger-text-secondary">
                              {h.symbol}{' '}
                              <span className="text-ledger-text-faint">
                                {h.balance.toLocaleString(undefined, { maximumFractionDigits: 6 })}
                              </span>
                            </span>
                            <span className="font-medium">${h.usd_value.toFixed(2)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="space-y-[8px]">
              <input
                type="text"
                value={cryptoAddress}
                onChange={(e) => setCryptoAddress(e.target.value)}
                placeholder="Public wallet address (0x…)"
                className="w-full glass-chip px-[10px] py-[7px] text-[13px] font-mono text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
              />
              <input
                type="text"
                value={cryptoLabel}
                onChange={(e) => setCryptoLabel(e.target.value)}
                placeholder="Label (optional)"
                className="w-full glass-chip px-[10px] py-[7px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
              />
              {cryptoError && (
                <p className="text-[12px] text-ledger-negative">{cryptoError}</p>
              )}
              <button
                type="button"
                onClick={handleAddCryptoWallet}
                disabled={addingCrypto}
                className="glass-chip px-[14px] py-[7px] text-[12.5px] font-medium text-ledger-text-primary hover:border-ledger-accent/50 transition-colors disabled:opacity-40"
              >
                {addingCrypto ? 'Adding…' : 'Add wallet'}
              </button>
            </div>

            <p className="text-[11.5px] text-ledger-text-faint mt-[12px]">
              Read-only. Robinhood Chain balances (USDG, curated majors, and Earn/steakUSDG vault
              deposits) are added to net worth. Never paste a private key.
            </p>
            <p className="text-[11.5px] text-ledger-text-faint mt-[6px]">
              Robinhood Earn: paste the address that actually holds vault shares — often an
              ERC-4337 smart account visible on{' '}
              <a
                href="https://robinhoodchain.blockscout.com"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-ledger-text-secondary"
              >
                Blockscout
              </a>
              , not the "public wallet key" shown in the Robinhood app if that address has no
              balance.
            </p>
          </div>

          {/* Plaid */}
          <div className="glass-card p-[22px]">
            <h3 className="text-[14px] font-semibold mb-[16px]">Plaid</h3>

            {plaidLoading ? (
              <div className="text-center py-8 text-ledger-text-faint">Loading…</div>
            ) : (
              <div className="space-y-[12px]">
                <div>
                  <label className="text-[12px] text-ledger-text-faint">Client ID</label>
                  <input
                    type="text"
                    value={plaidClientId}
                    onChange={e => setPlaidClientId(e.target.value)}
                    placeholder="Plaid client ID"
                    className="mt-[4px] w-full glass-chip px-[10px] py-[7px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
                  />
                </div>

                <div>
                  <label className="text-[12px] text-ledger-text-faint">Environment</label>
                  <select
                    value={plaidEnv}
                    onChange={e => setPlaidEnv(e.target.value)}
                    className="mt-[4px] w-full glass-chip px-[10px] py-[7px] text-[13px] text-ledger-text-primary focus:outline-none focus:border-ledger-accent/60"
                  >
                    <option value="sandbox">Sandbox</option>
                    <option value="production">Production</option>
                  </select>
                </div>

                <div>
                  <label className="text-[12px] text-ledger-text-faint">Secret</label>
                  <input
                    type="password"
                    value={plaidSecret}
                    onChange={e => setPlaidSecret(e.target.value)}
                    placeholder={plaidHasSecret ? '••••• (unchanged)' : 'Plaid secret'}
                    className="mt-[4px] w-full glass-chip px-[10px] py-[7px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
                  />
                </div>

                {plaidTestResult && (
                  <p className={`text-[11.5px] ${plaidTestOk ? 'text-ledger-positive' : 'text-ledger-negative'}`}>
                    {plaidTestResult}
                  </p>
                )}
                {plaidSaveError && <p className="text-[11.5px] text-ledger-negative">{plaidSaveError}</p>}
                {plaidSaveSuccess && <p className="text-[11.5px] text-ledger-positive">{plaidSaveSuccess}</p>}

                <div className="flex gap-[8px]">
                  <button
                    onClick={handleTestPlaidConfig}
                    disabled={plaidTesting}
                    className="flex-1 glass-chip rounded-[9px] py-[9px] text-[13px] font-semibold text-ledger-text-primary hover:bg-ledger-hover transition-colors disabled:opacity-50"
                  >
                    {plaidTesting ? 'Testing…' : 'Test connection'}
                  </button>
                  <button
                    onClick={handleSavePlaidConfig}
                    disabled={plaidSaving}
                    className="flex-1 bg-ledger-accent text-ledger-accent-on rounded-[9px] py-[9px] text-[13px] font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
                  >
                    {plaidSaving ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </div>
            )}
          </div>

        </div>

        <div className="flex flex-col gap-[24px]">
          {/* Categorization Rules */}
          <div className="glass-card p-[22px]">
            <h3 className="text-[14px] font-semibold mb-[16px]">Categorization rules</h3>

            {rules.length === 0 ? (
              <div className="text-center py-6 text-ledger-text-faint text-[13px] mb-[12px]">
                No rules yet. Rules automatically categorize transactions by merchant name.
              </div>
            ) : (
              <div className="space-y-[8px] mb-[12px]">
                {rules.map((rule, index) =>
                  editingRuleId === rule.id ? (
                    <div key={rule.id} className="border border-ledger-border-subtle rounded-[9px] p-[12px] space-y-[10px]">
                      <div className="grid gap-[8px] sm:grid-cols-2">
                        <input
                          autoFocus
                          type="text"
                          value={editMerchant}
                          onChange={e => setEditMerchant(e.target.value)}
                          className="glass-chip px-[10px] py-[6px] text-[12px] text-ledger-text-primary focus:outline-none focus:border-ledger-accent/60"
                        />
                        <input
                          type="text"
                          list="plaid-category-suggestions"
                          value={editCategory}
                          onChange={e => setEditCategory(e.target.value)}
                          className="glass-chip px-[10px] py-[6px] text-[12px] text-ledger-text-primary focus:outline-none focus:border-ledger-accent/60"
                        />
                      </div>
                      {editError && <p className="text-[11.5px] text-ledger-negative">{editError}</p>}
                      <div className="flex gap-[8px]">
                        <button
                          onClick={() => handleSaveEdit(rule.id)}
                          disabled={savingEdit}
                          className="flex-1 bg-ledger-accent text-ledger-accent-on rounded-[7px] py-[7px] text-[12.5px] font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
                        >
                          {savingEdit ? 'Saving…' : 'Save'}
                        </button>
                        <button
                          onClick={handleCancelEdit}
                          className="px-[14px] rounded-[7px] border border-ledger-border-input text-[12.5px] text-ledger-text-secondary hover:bg-ledger-inset transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div key={rule.id} className="border border-ledger-border-subtle rounded-[9px] p-[12px] group">
                      <div className="flex items-start justify-between gap-[10px]">
                        <div className="min-w-0 flex-1">
                          <div className="text-[11px] text-ledger-text-faint uppercase tracking-wide mb-[6px]">Merchant</div>
                          <div className="glass-chip px-[10px] py-[7px] text-[12px] text-ledger-text-primary truncate">
                            {rule.merchant_pattern}
                          </div>
                        </div>
                        <div className="flex items-center gap-[4px] opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                          <button
                            title="Move up"
                            onClick={() => handleMoveRule(index, -1)}
                            disabled={index === 0}
                            className="text-ledger-text-faint hover:text-ledger-text-primary transition-colors disabled:opacity-20"
                          >
                            <ArrowUp className="w-[13px] h-[13px]" strokeWidth={2} />
                          </button>
                          <button
                            title="Move down"
                            onClick={() => handleMoveRule(index, 1)}
                            disabled={index === rules.length - 1}
                            className="text-ledger-text-faint hover:text-ledger-text-primary transition-colors disabled:opacity-20"
                          >
                            <ArrowDown className="w-[13px] h-[13px]" strokeWidth={2} />
                          </button>
                          <button
                            title="Edit rule"
                            onClick={() => handleStartEdit(rule)}
                            className="text-ledger-text-faint hover:text-ledger-text-primary transition-colors"
                          >
                            <Pencil className="w-[13px] h-[13px]" strokeWidth={2} />
                          </button>
                          <button
                            title="Delete rule"
                            onClick={() => handleDeleteRule(rule.id)}
                            disabled={deletingRuleId === rule.id}
                            className="text-ledger-text-faint hover:text-ledger-negative transition-colors disabled:opacity-40"
                          >
                            <X className="w-[14px] h-[14px]" strokeWidth={2} />
                          </button>
                        </div>
                      </div>

                      <div className="mt-[10px] flex items-center justify-between gap-[10px]">
                        <span className="text-[11px] text-ledger-text-faint uppercase tracking-wide">Category</span>
                        <span className="flex items-center gap-[6px] text-[11px] glass-chip px-[8px] py-[4px] rounded-[6px] text-ledger-text-primary font-medium shrink-0">
                          {rule.category_color && (
                            <span className="w-[7px] h-[7px] rounded-[2px]" style={{ backgroundColor: rule.category_color }} />
                          )}
                          {rule.category_name}
                        </span>
                      </div>
                    </div>
                  )
                )}
              </div>
            )}

            {ruleSuccess && !showRuleForm && (
              <p className="text-[11.5px] text-ledger-positive mb-[10px]">{ruleSuccess}</p>
            )}

            {showRuleForm ? (
              <div className="border border-ledger-border-subtle rounded-[9px] p-[12px] space-y-[10px]">
                <div className="grid gap-[8px] sm:grid-cols-2">
                  <input
                    autoFocus
                    type="text"
                    value={ruleMerchant}
                    onChange={e => setRuleMerchant(e.target.value)}
                    placeholder="Merchant name or pattern"
                    className="glass-chip px-[10px] py-[6px] text-[12px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
                  />
                  <input
                    type="text"
                    list="plaid-category-suggestions"
                    value={ruleCategory}
                    onChange={e => setRuleCategory(e.target.value)}
                    placeholder="Category"
                    className="glass-chip px-[10px] py-[6px] text-[12px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
                  />
                </div>
                {ruleError && <p className="text-[11.5px] text-ledger-negative">{ruleError}</p>}
                <div className="flex gap-[8px]">
                  <button
                    onClick={handleCreateRule}
                    disabled={savingRule}
                    className="flex-1 bg-ledger-accent text-ledger-accent-on rounded-[7px] py-[7px] text-[12.5px] font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
                  >
                    {savingRule ? 'Saving…' : 'Save rule'}
                  </button>
                  <button
                    onClick={() => { setShowRuleForm(false); setRuleError(null); setRuleMerchant(''); setRuleCategory('') }}
                    className="px-[14px] rounded-[7px] border border-ledger-border-input text-[12.5px] text-ledger-text-secondary hover:bg-ledger-inset transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => { setShowRuleForm(true); setRuleSuccess(null) }}
                className="w-full glass-chip px-[12px] py-[8px] text-[13px] font-semibold text-ledger-text-primary hover:bg-ledger-hover transition-colors"
              >
                + New rule
              </button>
            )}
          </div>

          <div className="flex flex-col gap-[24px] xl:pt-[18px]">
            {/* Alerts */}
            <div className="glass-card p-[22px]">
              <h3 className="text-[14px] font-semibold mb-[16px]">Alerts</h3>

              <div className="space-y-[16px]">
                <div className="flex items-center justify-between">
                  <span className="text-[13px]">Budget exceeded</span>
                  <button
                    onClick={handleToggleBudgetExceeded}
                    className={`w-[40px] h-[23px] rounded-full relative cursor-pointer transition-colors ${budgetExceededEnabled ? 'bg-ledger-accent' : 'bg-ledger-track'}`}
                  >
                    <div className={`w-[17px] h-[17px] rounded-full absolute top-[3px] transition-all ${budgetExceededEnabled ? 'bg-ledger-accent-on right-[3px]' : 'bg-ledger-text-faint left-[3px]'}`} />
                  </button>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-[13px]">Large transaction</span>
                  <div className="flex items-center gap-[8px]">
                    {largeTxnEnabled && (
                      <button
                        onClick={() => {
                          setLargeTxnDraft(largeTxnThreshold)
                          setLargeTxnError(null)
                          setShowLargeTxnModal(true)
                        }}
                        className="glass-chip px-[10px] py-[5px] rounded-[7px] text-[11.5px] font-medium text-ledger-text-primary hover:bg-ledger-hover transition-colors"
                      >
                        {formatLargeTxnThreshold(largeTxnThreshold)}
                      </button>
                    )}
                    <button
                      onClick={handleToggleLargeTxn}
                      className={`w-[40px] h-[23px] rounded-full relative cursor-pointer transition-colors ${largeTxnEnabled ? 'bg-ledger-accent' : 'bg-ledger-track'}`}
                    >
                      <div className={`w-[17px] h-[17px] rounded-full absolute top-[3px] transition-all ${largeTxnEnabled ? 'bg-ledger-accent-on right-[3px]' : 'bg-ledger-text-faint left-[3px]'}`} />
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between opacity-40">
                  <span className="text-[13px]">Webhook <span className="text-[11px] text-ledger-text-faint">(Coming soon)</span></span>
                  <div className="w-[40px] h-[23px] bg-ledger-track rounded-full relative cursor-not-allowed">
                    <div className="w-[17px] h-[17px] bg-ledger-text-faint rounded-full absolute left-[3px] top-[3px]" />
                  </div>
                </div>
              </div>
            </div>

            {/* Weekly summary email */}
            <div className="glass-card p-[22px]">
              <h3 className="text-[14px] font-semibold mb-[4px]">Weekly summary email</h3>
              <p className="text-[12px] text-ledger-text-faint mb-[16px]">
                Budget pace vs. this week's spending, sent every Monday.
              </p>

              <div className="flex items-center justify-between">
                <span className="text-[13px]">Send weekly email</span>
                <div className="flex items-center gap-[8px]">
                  {weeklyEmailEnabled && weeklyEmailAddress && (
                    <button
                      onClick={() => {
                        setWeeklyEmailDraft(weeklyEmailAddress)
                        setWeeklyEmailError(null)
                        setShowWeeklyEmailModal(true)
                      }}
                      className="glass-chip px-[10px] py-[5px] rounded-[7px] text-[11.5px] font-medium text-ledger-text-primary hover:bg-ledger-hover transition-colors"
                    >
                      {weeklyEmailAddress}
                    </button>
                  )}
                  <button
                    onClick={handleToggleWeeklyEmail}
                    className={`w-[40px] h-[23px] rounded-full relative cursor-pointer transition-colors ${weeklyEmailEnabled ? 'bg-ledger-accent' : 'bg-ledger-track'}`}
                  >
                    <div className={`w-[17px] h-[17px] rounded-full absolute top-[3px] transition-all ${weeklyEmailEnabled ? 'bg-ledger-accent-on right-[3px]' : 'bg-ledger-text-faint left-[3px]'}`} />
                  </button>
                </div>
              </div>

              {!weeklyEmailTransportConfigured && (
                <p className="mt-[12px] text-[11.5px] text-ledger-warning">
                  No Resend API key configured — the toggle will save, but no email will actually send until you add one below.
                </p>
              )}

              <div className="mt-[16px] pt-[16px] border-t border-ledger-border/40 space-y-[12px]">
                <div>
                  <label className="text-[12px] text-ledger-text-faint">
                    Resend API key {weeklyEmailHasResendKey && <span className="text-ledger-text-faint">(configured)</span>}
                  </label>
                  <input
                    type="password"
                    value={resendApiKeyDraft}
                    onChange={e => setResendApiKeyDraft(e.target.value)}
                    placeholder={weeklyEmailHasResendKey ? '••••• (unchanged)' : 're_xxxxxxxxxxxx'}
                    className="mt-[4px] w-full glass-chip px-[10px] py-[7px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
                  />
                </div>
                <div>
                  <label className="text-[12px] text-ledger-text-faint">From address (optional)</label>
                  <input
                    type="text"
                    value={weeklyEmailFromAddress}
                    onChange={e => setWeeklyEmailFromAddress(e.target.value)}
                    placeholder="Ledger <onboarding@resend.dev>"
                    className="mt-[4px] w-full glass-chip px-[10px] py-[7px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
                  />
                </div>
                {resendKeySaveResult && (
                  <p className="text-[11.5px] text-ledger-text-faint">{resendKeySaveResult}</p>
                )}
                <button
                  onClick={handleSaveResendConfig}
                  disabled={savingResendKey}
                  className="glass-chip px-[12px] py-[7px] rounded-[8px] text-[12.5px] font-semibold text-ledger-text-primary hover:bg-ledger-hover transition-colors disabled:opacity-50"
                >
                  {savingResendKey ? 'Saving…' : 'Save Resend config'}
                </button>
              </div>

              {weeklyEmailEnabled && (
                <div className="mt-[14px] flex items-center gap-[10px]">
                  <button
                    onClick={handleSendTestEmail}
                    disabled={sendingTestEmail}
                    className="glass-chip px-[12px] py-[7px] rounded-[8px] text-[12.5px] font-semibold text-ledger-text-primary hover:bg-ledger-hover transition-colors disabled:opacity-50"
                  >
                    {sendingTestEmail ? 'Sending…' : 'Send test email now'}
                  </button>
                  {testEmailResult && (
                    <span className="text-[11.5px] text-ledger-text-faint">{testEmailResult}</span>
                  )}
                </div>
              )}
            </div>

            {/* Sync Settings */}
            <div className="glass-card p-[22px]">
              <h3 className="text-[14px] font-semibold mb-[16px]">Sync settings</h3>

              <div className="space-y-[12px]">
                <div>
                  <label className="text-[12px] text-ledger-text-faint">Frequency</label>
                  <select
                    value={syncFrequencyHours}
                    disabled={savingSyncFrequency}
                    onChange={(e) => handleSyncFrequencyChange(Number(e.target.value))}
                    className="mt-[4px] w-full glass-chip px-[12px] py-[8px] text-[13px] text-ledger-text-primary hover:bg-ledger-inset transition-colors disabled:opacity-50"
                  >
                    <option value={0}>Manual</option>
                    <option value={1}>Every hour</option>
                    <option value={6}>Every 6 hours</option>
                    <option value={12}>Every 12 hours</option>
                    <option value={24}>Daily</option>
                  </select>
                </div>

                <div>
                  <label className="text-[12px] text-ledger-text-faint">Plaid environment</label>
                  <div className="mt-[4px] flex items-center gap-[8px]">
                    <span className="text-[12px] glass-chip text-ledger-text-primary px-[8px] py-[4px] rounded-[6px] font-medium capitalize">
                      {plaidEnv}
                    </span>
                  </div>
                </div>

                <div>
                  <label className="text-[12px] text-ledger-text-faint">Last sync</label>
                  <div className="mt-[4px] text-[13px] text-ledger-text-secondary">
                    {syncStatus ? formatSyncTime(syncStatus.last_synced_at) : '—'}
                  </div>
                </div>
              </div>

              <button
                onClick={handleSyncNow}
                disabled={syncing}
                className="mt-[16px] w-full bg-ledger-accent text-ledger-accent-on rounded-[9px] px-[14px] py-[9px] font-semibold text-[13px] hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {syncing ? 'Syncing…' : 'Sync now'}
              </button>
              {syncMessage && (
                <p className={`mt-[10px] text-[12px] ${syncWarnings.length ? 'text-ledger-warning' : 'text-ledger-text-secondary'}`}>
                  {syncMessage}
                </p>
              )}
              {syncWarnings.length > 0 && (
                <ul className="mt-[6px] space-y-[4px]">
                  {syncWarnings.map((warning, i) => (
                    <li key={i} className="text-[11.5px] text-ledger-negative leading-snug">
                      {warning}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Account security: recovery code (the only "forgot password" path) */}
            <div className="glass-card p-[22px]">
              <div className="flex items-center gap-[8px] mb-[6px]">
                <KeyRound className="w-[15px] h-[15px] text-ledger-accent" strokeWidth={2} />
                <h3 className="text-[14px] font-semibold">Recovery code</h3>
              </div>
              <p className="text-[12px] text-ledger-text-faint leading-[1.5] mb-[14px]">
                Since this app has no email, a recovery code is the only way to reset your
                password without wiping your local data. It's shown once, right after you
                generate it.
              </p>

              {recoveryCodeConfigured !== null && (
                <div className="flex items-center gap-[6px] text-[12px] text-ledger-text-secondary mb-[12px]">
                  <span
                    className={`inline-block w-[7px] h-[7px] rounded-full ${recoveryCodeConfigured ? 'bg-ledger-positive' : 'bg-ledger-warning'}`}
                  />
                  {recoveryCodeConfigured ? 'A recovery code is set.' : 'No recovery code is set yet.'}
                </div>
              )}

              {freshRecoveryCode && (
                <div className="mb-[12px] flex flex-col gap-[8px]">
                  <div className="text-[11px] text-ledger-text-faint">
                    Save this now — it won't be shown again:
                  </div>
                  <div className="flex items-center gap-[8px]">
                    <code className="glass-chip rounded-[8px] px-[12px] py-[9px] text-[13px] font-mono text-ledger-text-primary flex-1 text-center">
                      {freshRecoveryCode}
                    </code>
                    <button
                      onClick={copyRecoveryCode}
                      className="glass-chip rounded-[8px] px-[10px] py-[9px] text-[12px] text-ledger-text-secondary hover:text-ledger-accent transition-colors flex items-center gap-[5px]"
                    >
                      <Copy className="w-[12px] h-[12px]" strokeWidth={2} />
                      {recoveryCodeCopied ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                </div>
              )}

              {recoveryCodeError && (
                <p className="text-[12px] text-ledger-negative mb-[10px]">{recoveryCodeError}</p>
              )}

              <button
                onClick={handleGenerateRecoveryCode}
                disabled={generatingRecoveryCode}
                className="w-full glass-chip rounded-[9px] px-[14px] py-[9px] font-semibold text-[13px] text-ledger-text-primary hover:bg-ledger-inset transition-colors disabled:opacity-50"
              >
                {generatingRecoveryCode
                  ? 'Generating…'
                  : recoveryCodeConfigured
                    ? 'Generate a new code (replaces the old one)'
                    : 'Generate recovery code'}
              </button>
            </div>

            {/* Account security: recovery email (enables emailed reset codes) */}
            <div className="glass-card p-[22px]">
              <div className="flex items-center gap-[8px] mb-[6px]">
                <KeyRound className="w-[15px] h-[15px] text-ledger-accent" strokeWidth={2} />
                <h3 className="text-[14px] font-semibold">Recovery email</h3>
              </div>
              <p className="text-[12px] text-ledger-text-faint leading-[1.5] mb-[14px]">
                Set an email to unlock "Email me a code" on the login screen, in addition to
                the recovery code above. Requires the app operator to have configured a
                password-reset email key.
              </p>

              <div className="flex items-center gap-[6px] text-[12px] text-ledger-text-secondary mb-[12px]">
                <span
                  className={`inline-block w-[7px] h-[7px] rounded-full ${recoveryEmail ? 'bg-ledger-positive' : 'bg-ledger-warning'}`}
                />
                {recoveryEmail ? `Recovery email set: ${recoveryEmail}` : 'No recovery email set yet.'}
              </div>

              {recoveryEmailError && (
                <p className="text-[12px] text-ledger-negative mb-[10px]">{recoveryEmailError}</p>
              )}

              <div className="flex items-center gap-[8px]">
                <input
                  type="email"
                  placeholder="you@example.com"
                  value={recoveryEmailDraft}
                  onChange={e => setRecoveryEmailDraft(e.target.value)}
                  className="glass-chip flex-1 px-[14px] py-[9px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faint focus:outline-none focus:border-ledger-accent/60"
                />
                <button
                  onClick={handleSaveRecoveryEmail}
                  disabled={savingRecoveryEmail}
                  className="glass-chip rounded-[9px] px-[14px] py-[9px] font-semibold text-[13px] text-ledger-text-primary hover:bg-ledger-inset transition-colors disabled:opacity-50"
                >
                  {savingRecoveryEmail ? 'Saving…' : recoveryEmailSaved ? 'Saved' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-auto pt-[4px]">
        <div className="glass-card px-[18px] py-[14px]">
          <div className="flex flex-col gap-[12px] sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-[8px] text-[13px] font-semibold text-ledger-text-primary">
                <span className="flex h-[28px] w-[28px] items-center justify-center rounded-chip bg-ledger-inset">
                  <Heart className="h-[14px] w-[14px] text-ledger-accent" strokeWidth={2.2} />
                </span>
                Support Ledger
              </div>
              <p className="mt-[6px] text-[12px] text-ledger-text-faint">
                If the app’s useful, you can tip the project on Ko-fi.
              </p>
            </div>

            <a
              href={KOFI_URL}
              className="group glass-chip inline-flex items-center justify-center gap-[8px] rounded-[12px] border border-white/20 px-[15px] py-[10px] text-[13px] font-semibold text-ledger-text-primary hover:border-ledger-accent/40 hover:bg-white/[0.10]"
            >
              <span>Support me</span>
              <ExternalLink className="h-[13px] w-[13px] text-ledger-text-faint transition-colors group-hover:text-ledger-accent" strokeWidth={2.1} />
            </a>
          </div>
        </div>
      </div>

      <datalist id="plaid-category-suggestions">
        {PLAID_CATEGORY_LABELS.map(label => <option key={label} value={label} />)}
      </datalist>

      {showLargeTxnModal && (
        <div
          className="glass-overlay fixed inset-0 z-50 flex items-center justify-center"
          onClick={e => { if (e.target === e.currentTarget) closeLargeTxnModal() }}
        >
          <div className="glass-modal w-[360px] p-[24px]">
            <div className="flex items-center justify-between mb-[10px]">
              <div>
                <h3 className="text-[15px] font-semibold">Large transaction rule</h3>
                <p className="mt-[4px] text-[12px] text-ledger-text-faint">
                  Alert me when a transaction is larger than this amount.
                </p>
              </div>
              <button
                onClick={closeLargeTxnModal}
                className="text-ledger-text-faint hover:text-ledger-text-primary transition-colors"
              >
                <X className="w-[16px] h-[16px]" />
              </button>
            </div>

            <div className="mt-[18px]">
              <label className="text-[12px] text-ledger-text-faint block mb-[6px]">Threshold</label>
              <div className="relative">
                <span className="absolute left-[12px] top-1/2 -translate-y-1/2 text-[13px] text-ledger-text-faint">$</span>
                <input
                  autoFocus
                  type="text"
                  inputMode="decimal"
                  value={largeTxnDraft}
                  onChange={e => {
                    setLargeTxnDraft(e.target.value.replace(/[^0-9.]/g, ''))
                    if (largeTxnError) setLargeTxnError(null)
                  }}
                  onKeyDown={e => {
                    if (e.key === 'Enter') void handleSaveLargeTxnRule()
                  }}
                  placeholder="500"
                  className="w-full glass-chip pl-[24px] pr-[12px] py-[8px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
                />
              </div>
            </div>

            {largeTxnError && <p className="mt-[10px] text-[12px] text-ledger-negative">{largeTxnError}</p>}

            <div className="mt-[18px] flex gap-[8px]">
              <button
                onClick={closeLargeTxnModal}
                disabled={savingLargeTxn}
                className="flex-1 glass-chip rounded-[9px] py-[9px] text-[13px] font-semibold text-ledger-text-primary hover:bg-ledger-hover transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveLargeTxnRule}
                disabled={savingLargeTxn}
                className="flex-1 bg-ledger-accent text-ledger-accent-on rounded-[9px] py-[9px] text-[13px] font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {savingLargeTxn ? 'Saving…' : 'Save rule'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showWeeklyEmailModal && (
        <div
          className="glass-overlay fixed inset-0 z-50 flex items-center justify-center"
          onClick={e => { if (e.target === e.currentTarget) closeWeeklyEmailModal() }}
        >
          <div className="glass-modal w-[360px] p-[24px]">
            <div className="flex items-center justify-between mb-[10px]">
              <div>
                <h3 className="text-[15px] font-semibold">Weekly summary email</h3>
                <p className="mt-[4px] text-[12px] text-ledger-text-faint">
                  Where should the weekly budget-pace summary go?
                </p>
              </div>
              <button
                onClick={closeWeeklyEmailModal}
                className="text-ledger-text-faint hover:text-ledger-text-primary transition-colors"
              >
                <X className="w-[16px] h-[16px]" />
              </button>
            </div>

            <div className="mt-[18px]">
              <label className="text-[12px] text-ledger-text-faint block mb-[6px]">Email address</label>
              <input
                autoFocus
                type="email"
                value={weeklyEmailDraft}
                onChange={e => {
                  setWeeklyEmailDraft(e.target.value)
                  if (weeklyEmailError) setWeeklyEmailError(null)
                }}
                onKeyDown={e => {
                  if (e.key === 'Enter') void handleSaveWeeklyEmail()
                }}
                placeholder="you@example.com"
                className="w-full glass-chip px-[12px] py-[8px] text-[13px] text-ledger-text-primary placeholder-ledger-text-faintest focus:outline-none focus:border-ledger-accent/60"
              />
            </div>

            {weeklyEmailError && <p className="mt-[10px] text-[12px] text-ledger-negative">{weeklyEmailError}</p>}

            <div className="mt-[18px] flex gap-[8px]">
              <button
                onClick={closeWeeklyEmailModal}
                disabled={savingWeeklyEmail}
                className="flex-1 glass-chip rounded-[9px] py-[9px] text-[13px] font-semibold text-ledger-text-primary hover:bg-ledger-hover transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveWeeklyEmail}
                disabled={savingWeeklyEmail}
                className="flex-1 bg-ledger-accent text-ledger-accent-on rounded-[9px] py-[9px] text-[13px] font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {savingWeeklyEmail ? 'Saving…' : 'Enable'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
