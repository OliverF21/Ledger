import { apiFetch } from './client'

export type PlaidConfig = {
  client_id: string | null
  env: string
  redirect_uri: string | null
  has_secret: boolean
  configured: boolean
  wizard_done: boolean
}

export type PlaidConfigUpdate = {
  client_id?: string
  env?: string
  secret?: string
  redirect_uri?: string
}

export async function getPlaidConfig(): Promise<PlaidConfig> {
  const r = await apiFetch('/api/settings/plaid-config')
  if (!r.ok) throw new Error('Failed to load Plaid config')
  return r.json()
}

export async function putPlaidConfig(body: PlaidConfigUpdate): Promise<PlaidConfig> {
  const r = await apiFetch('/api/settings/plaid-config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error('Failed to save Plaid config')
  return r.json()
}

export async function testPlaidConfig(body: PlaidConfigUpdate): Promise<{ ok: boolean; message: string }> {
  const r = await apiFetch('/api/settings/plaid-config/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error('Test request failed')
  return r.json()
}

export async function markWizardDone(): Promise<void> {
  await apiFetch('/api/settings/wizard-done', { method: 'PUT' })
}

export type SyncConfig = {
  frequency_hours: number
}

export async function getSyncConfig(): Promise<SyncConfig> {
  const r = await apiFetch('/api/settings/sync-config')
  if (!r.ok) throw new Error('Failed to load sync settings')
  return r.json()
}

export async function putSyncConfig(frequency_hours: number): Promise<SyncConfig> {
  const r = await apiFetch('/api/settings/sync-config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ frequency_hours }),
  })
  if (!r.ok) throw new Error('Failed to save sync settings')
  return r.json()
}

export type WeeklyEmailPrefs = {
  enabled: boolean
  email: string | null
  transport_configured: boolean
  has_resend_key: boolean
  from_address: string | null
}

export type WeeklyEmailUpdate = {
  enabled?: boolean
  email?: string
  resend_api_key?: string
  from_address?: string
}

export async function getWeeklyEmailPrefs(): Promise<WeeklyEmailPrefs> {
  const r = await apiFetch('/api/settings/weekly-email')
  if (!r.ok) throw new Error('Failed to load weekly email settings')
  return r.json()
}

export async function putWeeklyEmailPrefs(body: WeeklyEmailUpdate): Promise<WeeklyEmailPrefs> {
  const r = await apiFetch('/api/settings/weekly-email', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || 'Failed to save weekly email settings')
  return data
}

export type AdvisorConfig = {
  configured: boolean
  service_key: string | null
  config_snippet: string
}

export async function getAdvisorConfig(): Promise<AdvisorConfig> {
  const r = await apiFetch('/api/settings/advisor-config')
  if (!r.ok) throw new Error('Failed to load AI Advisor config')
  return r.json()
}

export async function generateAdvisorKey(): Promise<AdvisorConfig> {
  const r = await apiFetch('/api/settings/advisor-config/generate', { method: 'POST' })
  if (!r.ok) throw new Error('Failed to generate AI Advisor key')
  return r.json()
}

export async function importData(source_dir: string, confirm_overwrite = false):
  Promise<{ imported_items: number; restart_required: boolean }> {
  const r = await apiFetch('/api/settings/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_dir, confirm_overwrite }),
  })
  if (r.status === 409) throw new Error('Target already has data. Confirm overwrite to continue.')
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Import failed')
  return r.json()
}

// ── Recovery code (account security) ────────────────────────────────────────

export async function getRecoveryCodeStatus(): Promise<{ configured: boolean }> {
  const r = await apiFetch('/api/settings/security/recovery-code')
  if (!r.ok) throw new Error('Failed to load recovery code status')
  return r.json()
}

export async function generateRecoveryCode(): Promise<{ recovery_code: string }> {
  const r = await apiFetch('/api/settings/security/recovery-code', { method: 'POST' })
  if (!r.ok) throw new Error('Failed to generate a recovery code')
  return r.json()
}
