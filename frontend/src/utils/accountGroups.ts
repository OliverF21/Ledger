export type AssetGroup = 'checking' | 'saving' | 'investing' | 'retirement' | 'other'

export interface AssetAccount {
  id: number
  name: string
  type: string
  subtype: string | null
  balance: number
}

export const ASSET_GROUP_ORDER: AssetGroup[] = ['checking', 'saving', 'investing', 'retirement', 'other']

export const ASSET_GROUP_LABELS: Record<AssetGroup, string> = {
  checking: 'Checking',
  saving: 'Saving',
  investing: 'Investing',
  retirement: 'Retirement',
  other: 'Other',
}

const RETIREMENT_SUBTYPES = new Set([
  '401a', '401k', '403b', '457b', 'ira', 'keogh', 'lira', 'lif', 'lrif', 'lrsp',
  'pension', 'prif', 'rdsp', 'resp', 'retirement', 'rlif', 'roth', 'roth 401k',
  'rrif', 'rrsp', 'sarsep', 'sep ira', 'simple ira', 'sipp', 'tfsa',
])

const SAVINGS_SUBTYPES = new Set([
  'savings', 'cd', 'money market', 'cash management', 'hsa', 'paypal', 'prepaid',
  '529', 'education savings account',
])

const CHECKING_SUBTYPES = new Set(['checking', 'spending'])

export function classifyAssetAccount(account: AssetAccount): AssetGroup {
  const type = account.type.toLowerCase()
  const subtype = (account.subtype ?? '').toLowerCase()

  if (type === 'investment') {
    if (
      RETIREMENT_SUBTYPES.has(subtype)
      || subtype.includes('ira')
      || subtype.includes('401')
      || subtype.includes('403')
      || subtype.includes('457')
    ) {
      return 'retirement'
    }
    return 'investing'
  }

  if (type === 'depository') {
    if (CHECKING_SUBTYPES.has(subtype) || subtype.includes('check')) return 'checking'
    if (SAVINGS_SUBTYPES.has(subtype) || subtype.includes('saving')) return 'saving'
    return 'checking'
  }

  if (type === 'brokerage') return 'investing'

  return 'other'
}

export function groupAssetAccounts(accounts: AssetAccount[]) {
  const groups = new Map<AssetGroup, AssetAccount[]>()

  for (const group of ASSET_GROUP_ORDER) {
    groups.set(group, [])
  }

  for (const account of accounts) {
    const group = classifyAssetAccount(account)
    groups.get(group)!.push(account)
  }

  return ASSET_GROUP_ORDER
    .map(group => ({
      group,
      label: ASSET_GROUP_LABELS[group],
      accounts: groups.get(group) ?? [],
      total: (groups.get(group) ?? []).reduce((sum, account) => sum + account.balance, 0),
    }))
    .filter(entry => entry.accounts.length > 0)
}
