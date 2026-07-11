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

// ── Email-based password reset ──────────────────────────────────────────────

export type ResetOptions = {
  email_available: boolean
  masked_email: string | null
}

export async function getResetOptions(): Promise<ResetOptions> {
  const r = await apiFetch('/api/auth/reset-options')
  if (!r.ok) throw new Error('Failed to load reset options')
  return r.json()
}

export async function requestResetCode(): Promise<{ sent: boolean }> {
  const r = await apiFetch('/api/auth/forgot-password', { method: 'POST' })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || 'Failed to send the reset email')
  return data
}

export async function resetPasswordWithEmailCode(code: string, new_password: string):
  Promise<{ token: string; username: string; recovery_code: string | null }> {
  const r = await apiFetch('/api/auth/reset-password-email', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, new_password }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || 'Could not reset the password. Check your code.')
  return data
}

// ── Recovery email (account security) ───────────────────────────────────────

export async function getRecoveryEmailStatus(): Promise<{ email: string | null }> {
  const r = await apiFetch('/api/settings/security/email')
  if (!r.ok) throw new Error('Failed to load recovery email status')
  return r.json()
}

export async function putRecoveryEmail(email: string): Promise<{ email: string | null }> {
  const r = await apiFetch('/api/settings/security/email', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || 'Failed to save recovery email')
  return data
}

// ── Password-reset email transport (BYOK Resend key, separate from weekly email) ──

export async function getResetEmailKeyStatus(): Promise<{ configured: boolean }> {
  const r = await apiFetch('/api/settings/security/reset-email-key')
  if (!r.ok) throw new Error('Failed to load reset-email key status')
  return r.json()
}

export async function putResetEmailKey(resend_api_key: string): Promise<{ configured: boolean }> {
  const r = await apiFetch('/api/settings/security/reset-email-key', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resend_api_key }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(data.detail || 'Failed to save the Resend key')
  return data
}
