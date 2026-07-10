/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      screens: {
        short: { raw: '(max-height: 860px)' },
        tall: { raw: '(min-height: 960px)' },
      },
      colors: {
        'ledger-bg': '#0d0f14',
        'ledger-sidebar': '#0b0d11',
        'ledger-card': '#11141a',
        'ledger-card-alt': '#101319',
        'ledger-inset': '#161a21',
        'ledger-track': '#1a1e27',
        'ledger-border': '#1c2029',
        'ledger-border-subtle': '#181b22',
        'ledger-border-input': '#20242d',
        'ledger-text-primary': '#e9ebf0',
        'ledger-text-heading': '#eef0f4',
        'ledger-text-secondary': 'rgba(255,255,255,0.74)',
        'ledger-text-muted': 'rgba(255,255,255,0.66)',
        'ledger-text-faint': 'rgba(255,255,255,0.60)',
        'ledger-text-faintest': 'rgba(255,255,255,0.52)',
        'ledger-accent': '#5b8def',
        'ledger-accent-on': '#06070a',
        'ledger-positive': '#4ec38a',
        'ledger-negative': '#e7705f',
        'ledger-warning': '#d9a85b',
        'ledger-cat-teal': '#4fc4c4',
        'ledger-cat-violet': '#8a7df0',
        'ledger-cat-green': '#4ec38a',
        'ledger-cat-slate': '#565c69',
      },
      fontFamily: {
        sans: ['Hanken Grotesk', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        'heronet': '38px',
        'stat': '25px',
        'title': '14px',
      },
      borderRadius: {
        'card': '14px',
        'btn': '9px',
        'pill': '7px',
        'avatar': '8px',
      },
    },
  },
  darkMode: 'class',
  plugins: [],
}
