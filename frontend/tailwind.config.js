/** @type {import('tailwindcss').Config} */

// Ledger's design tokens. Dark-only by design (see CLAUDE.md) and tuned for
// dense financial data: every neutral is tinted with the same cool hue as the
// accent so surfaces read as one material, and every text step is opaque so its
// contrast does not drift when it sits on a different surface.
//
// Radius scale is concentric, outermost to innermost:
//   shell/sidebar 18 → card 14 → well 10 → chip 8 → pill (interactive only)
// Nested elements always step down. Pick from this scale, never an arbitrary
// value, so panels and the controls inside them stay visually related.

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
        // ── Surfaces (ascending elevation) ──────────────────────────────────
        'ledger-bg': '#0a0c11',
        'ledger-sidebar': '#0c0f15',
        'ledger-shell': '#0e1116',
        'ledger-card': '#13171e',
        'ledger-card-alt': '#171b24',
        'ledger-inset': '#101319',
        'ledger-well': '#0d1015',
        'ledger-track': '#1b2029',
        'ledger-hover': '#1c212b',
        'ledger-active': '#222834',

        // ── Hairlines ───────────────────────────────────────────────────────
        'ledger-border-subtle': '#171b23',
        'ledger-border': '#20252f',
        'ledger-border-input': '#282e3a',
        'ledger-border-strong': '#333b4a',

        // ── Text (opaque, so contrast holds on any surface above) ───────────
        'ledger-text-heading': '#f3f5f9',
        'ledger-text-primary': '#e5e8ef',
        'ledger-text-secondary': '#c5cbd8',
        'ledger-text-muted': '#a4acbb',
        'ledger-text-faint': '#969eab',
        'ledger-text-faintest': '#858d9a',

        // ── Accent (one accent, locked across every page) ───────────────────
        'ledger-accent': '#5b8def',
        'ledger-accent-hover': '#7ba5f5',
        'ledger-accent-press': '#4676d8',
        'ledger-accent-text': '#a9c5fb',
        'ledger-accent-soft': '#182338',
        'ledger-accent-border': '#2e4677',
        'ledger-accent-on': '#06070a',

        // ── Semantic (money direction and alert state) ──────────────────────
        'ledger-positive': '#4ec38a',
        'ledger-positive-soft': '#12241d',
        'ledger-positive-border': '#255741',
        'ledger-negative': '#e7705f',
        'ledger-negative-soft': '#2a1715',
        'ledger-negative-border': '#6b3129',
        'ledger-warning': '#d9a85b',
        'ledger-warning-soft': '#261e10',
        'ledger-warning-border': '#5d4622',

        // ── Categorical data series ─────────────────────────────────────────
        // Ordered for donut/stack legibility: adjacent entries differ in both
        // hue and lightness so neighbouring slices stay separable.
        'ledger-data-1': '#5b8def',
        'ledger-data-2': '#4fc4c4',
        'ledger-data-3': '#8a7df0',
        'ledger-data-4': '#4ec38a',
        'ledger-data-5': '#d9a85b',
        'ledger-data-6': '#e7705f',
        'ledger-data-7': '#f0a87d',
        'ledger-data-8': '#7fb0ff',
        'ledger-data-9': '#9ed3a8',
        'ledger-data-10': '#b98ae0',

        // Retained aliases so existing category maps keep resolving.
        'ledger-cat-teal': '#4fc4c4',
        'ledger-cat-violet': '#8a7df0',
        'ledger-cat-green': '#4ec38a',
        'ledger-cat-slate': '#5d6472',
      },
      fontFamily: {
        sans: ['Hanken Grotesk', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        // Dense-dashboard scale. Line-height and tracking travel with the size
        // so a label or a stat reads the same wherever it is used.
        'micro': ['10.5px', { lineHeight: '1.3', letterSpacing: '0.07em' }],
        'label': ['11.5px', { lineHeight: '1.35', letterSpacing: '0.01em' }],
        'meta': ['12px', { lineHeight: '1.4' }],
        'body': ['13px', { lineHeight: '1.5' }],
        'title': ['14px', { lineHeight: '1.35', letterSpacing: '-0.005em' }],
        'section': ['17px', { lineHeight: '1.25', letterSpacing: '-0.012em' }],
        'stat': ['26px', { lineHeight: '1.1', letterSpacing: '-0.022em' }],
        'heronet': ['40px', { lineHeight: '1.04', letterSpacing: '-0.03em' }],
      },
      letterSpacing: {
        'caps': '0.07em',
        'tightest': '-0.03em',
      },
      borderRadius: {
        'shell': '18px',
        'card': '14px',
        'well': '10px',
        'btn': '9px',
        'chip': '8px',
        'pill': '999px',
        'avatar': '8px',
      },
      boxShadow: {
        // Tinted to the background hue rather than pure black, and no outer
        // glow: depth comes from a dark cast plus a single top hairline.
        'elev-1': '0 1px 2px rgba(4,6,11,0.55)',
        'elev-2': '0 4px 14px -4px rgba(4,6,11,0.62), 0 1px 2px rgba(4,6,11,0.45)',
        'elev-3': '0 20px 48px -20px rgba(3,5,10,0.80), 0 2px 6px rgba(3,5,10,0.52)',
        'hair-top': 'inset 0 1px 0 rgba(255,255,255,0.045)',
        'focus': '0 0 0 2px #0a0c11, 0 0 0 4px rgba(91,141,239,0.55)',
      },
      transitionTimingFunction: {
        'out-quint': 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  darkMode: 'class',
  plugins: [],
}
