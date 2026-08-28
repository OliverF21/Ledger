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
        // ── Canvas ──────────────────────────────────────────────────────────
        // V2 sits on a darker root shell than the old #0d0f14 so the aurora
        // blobs and the frosted card edges have something to read against.
        'ledger-bg': '#07080a',
        'ledger-bg-deep': '#06070a',
        'ledger-sidebar': '#0b0d11',
        'ledger-card': '#11141a',
        'ledger-card-alt': '#101319',
        'ledger-inset': '#161a21',
        'ledger-track': 'rgba(255,255,255,0.09)',
        'ledger-border': 'rgba(255,255,255,0.14)',
        'ledger-border-subtle': 'rgba(255,255,255,0.08)',
        'ledger-border-input': 'rgba(255,255,255,0.16)',
        'ledger-border-strong': 'rgba(255,255,255,0.24)',

        // ── Text ────────────────────────────────────────────────────────────
        'ledger-text-primary': '#f2f4f8',
        'ledger-text-heading': '#ffffff',
        'ledger-text-secondary': 'rgba(255,255,255,0.70)',
        'ledger-text-muted': 'rgba(255,255,255,0.60)',
        'ledger-text-faint': 'rgba(255,255,255,0.46)',
        'ledger-text-faintest': 'rgba(255,255,255,0.36)',
        'ledger-text-eyebrow': 'rgba(255,255,255,0.34)',

        // ── Semantic ────────────────────────────────────────────────────────
        // V2 shifts the accent from the old saturated #5b8def to the softer
        // periwinkle used by the charts, and pairs every signal colour with a
        // lighter "-soft" tint used for large figures on glass.
        'ledger-accent': '#82a9f2',
        'ledger-accent-deep': '#5484da',
        'ledger-accent-on': '#0a0c10',
        'ledger-positive': '#74d8a8',
        'ledger-positive-soft': '#b6ebcd',
        'ledger-negative': '#f4907f',
        'ledger-negative-soft': '#f5b3a4',
        'ledger-warning': '#e6bd79',

        // ── Category palette (donut / legend cycling order) ─────────────────
        'ledger-cat-blue': '#82a9f2',
        'ledger-cat-teal': '#63cfcc',
        'ledger-cat-gold': '#e6bd79',
        'ledger-cat-coral': '#f4907f',
        'ledger-cat-violet': '#a196fa',
        'ledger-cat-slate': '#adb8cb',
        'ledger-cat-green': '#74d8a8',
        'ledger-cat-sky': '#95c8ff',
      },
      fontFamily: {
        sans: ['Schibsted Grotesk', 'Hanken Grotesk', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        'hero': ['68px', { lineHeight: '0.92', letterSpacing: '-0.05em', fontWeight: '700' }],
        'hero-sm': ['44px', { lineHeight: '0.95', letterSpacing: '-0.04em', fontWeight: '700' }],
        'donut': ['30px', { lineHeight: '1', letterSpacing: '-0.04em', fontWeight: '700' }],
        'donut-sm': ['26px', { lineHeight: '1', letterSpacing: '-0.04em', fontWeight: '700' }],
        'page': ['24px', { lineHeight: '1.1', letterSpacing: '-0.035em', fontWeight: '700' }],
        'heronet': '38px',
        'stat': '25px',
        'title': '14px',
      },
      borderRadius: {
        'card': '24px',
        'panel': '16px',
        'chip': '12px',
        'nav': '11px',
        'btn': '9px',
        'pill': '7px',
        'avatar': '8px',
      },
      letterSpacing: {
        'eyebrow': '0.18em',
        'eyebrow-tight': '0.14em',
      },
      transitionTimingFunction: {
        'rail': 'cubic-bezier(.22,.8,.2,1)',
      },
    },
  },
  darkMode: 'class',
  plugins: [],
}
