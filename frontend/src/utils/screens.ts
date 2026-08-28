/** The app's top-level routes, keyed by their URL hash. Lives outside App.tsx
 *  so the sidebar can type its navigation callback against the same union
 *  without importing the component. */
export type ScreenType =
  | 'overview'
  | 'transactions'
  | 'spending'
  | 'budgets'
  | 'investments'
  | 'trends'
  | 'subscriptions'
  | 'advisor'
  | 'settings'

export const VALID_SCREENS: ScreenType[] = [
  'overview', 'transactions', 'spending', 'budgets', 'investments',
  'trends', 'subscriptions', 'advisor', 'settings',
]
