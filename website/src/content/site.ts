/* All visible marketing copy, nav, and screenshot paths.
   Swap product shots by replacing files in /public/product and/or changing
   the paths below. Do not put string literals in section components. */

export const site = {
  name: "Ledger",
  github: "https://github.com/OliverF21/Ledger",
  releasesLatest: "https://github.com/OliverF21/Ledger/releases/latest",
  sourceInstall: "https://github.com/OliverF21/Ledger#running-from-source",
  mcpDocs: "https://github.com/OliverF21/Ledger/blob/main/docs/MCP_SETUP.md",

  meta: {
    title: "Ledger - personal finance on your computer",
    description:
      "A local personal finance dashboard. Link banks with your own Plaid keys. Data stays on your machine.",
  },

  nav: [
    { label: "Features", href: "#features" },
    { label: "Download", href: "#download" },
    { label: "GitHub", href: "https://github.com/OliverF21/Ledger", external: true },
  ] as const,

  shots: {
    hero: "/product/overview.png",
    product: "/product/overview.png",
    netWorth: "/product/overview.png",
    budgets: "/product/overview.png",
    activity: "/product/overview.png",
  },

  hero: {
    lines: ["Your money stays", "on your machine."],
    headline: "Your money stays on your machine.",
    subtext:
      "A personal finance app that lives on your computer. You bring the Plaid keys.",
    githubLabel: "GitHub",
    shotAlt: "Ledger Overview. Net worth, spending, and budgets.",
  },

  localFirst: {
    headline: "Runs on your computer. Not in our cloud.",
    facts: [
      { title: "Local SQLite", body: "Transactions and budgets sit in app-data on disk." },
      { title: "Your Plaid keys", body: "Ledger never holds a bank connection for you." },
      { title: "Local MCP", body: "Claude Desktop talks to a read-only server on this machine. You Apply or Dismiss every proposal." },
    ],
  },

  product: {
    caption: "Overview. Net worth, spending, and budgets in one place.",
  },

  features: {
    id: "features",
    headline: "See the month before it gets away from you.",
    cells: [
      {
        key: "netWorth",
        title: "Net worth",
        body: "Daily snapshots across banks, brokerages, and optional crypto wallets.",
        shot: "netWorth" as const,
        objectPosition: "left top",
        pictured: true,
        tint: "none" as const,
      },
      {
        key: "budgets",
        title: "Budgets",
        body: "Category limits that carry into the next month, with overage alerts.",
        shot: "budgets" as const,
        objectPosition: "right bottom",
        pictured: true,
        tint: "none" as const,
      },
      {
        key: "sync",
        title: "Automated transaction pulling",
        body: "New transactions come in on a schedule, every six hours by default. Sync now is still there when you want them sooner.",
        shot: "activity" as const,
        objectPosition: "left bottom",
        pictured: false,
        tint: "cool" as const,
      },
      {
        key: "risk",
        title: "Risk and optimization",
        body: "Volatility, Sharpe, drawdown, VaR, and beta on holdings you already have, plus a max-Sharpe mix you can take or leave.",
        shot: "product" as const,
        objectPosition: "center",
        pictured: false,
        tint: "mint" as const,
      },
      {
        key: "mcp",
        title: "MCP for Claude Desktop",
        body: "A local, read-only Model Context Protocol server. It can propose a budget. Only you Apply or Dismiss it in Advisor.",
        shot: "product" as const,
        objectPosition: "center",
        pictured: false,
        tint: "teal" as const,
      },
      {
        key: "activity",
        title: "Activity",
        body: "Search, recategorize, split, hide, export CSV, and catch recurring charges.",
        shot: "activity" as const,
        objectPosition: "left bottom",
        pictured: true,
        tint: "none" as const,
      },
    ],
  },

  how: {
    headline: "From download to a linked bank.",
    steps: [
      {
        title: "Install",
        body: "Grab the macOS disk image or the Windows installer. No Python or Node required.",
      },
      {
        title: "Add your Plaid keys",
        body: "Free Plaid account. Start in Sandbox, then switch to real banks in Settings.",
      },
      {
        title: "Link a bank",
        body: "Plaid Link runs locally. After that, transactions pull on a schedule. Access tokens stay encrypted on disk.",
      },
    ],
  },

  download: {
    id: "download",
    headline: "Get the latest build.",
    body: "The first launch will warn you. The app is unsigned open-source freeware. Only install from GitHub Releases.",
    macNote: {
      title: "macOS",
      body: "Allow it under Privacy & Security, Open Anyway. If Finder says the app is damaged, that is Gatekeeper on an unsigned download. Strip the quarantine flag, then open it.",
      code: "xattr -cr /Applications/Ledger.app",
    },
    winNote: {
      title: "Windows",
      body: "SmartScreen says Windows protected your PC. Click More info, then Run anyway.",
    },
    linuxNote: {
      title: "Linux",
      body: "No packaged build yet. Run from source.",
    },
    otherPlatformsLabel: "All releases",
  },

  close: {
    headline: "Install Ledger.",
  },

  footer: {
    license: "MIT",
    links: [
      { label: "GitHub", href: "https://github.com/OliverF21/Ledger" },
      { label: "Releases", href: "https://github.com/OliverF21/Ledger/releases/latest" },
      { label: "MCP", href: "https://github.com/OliverF21/Ledger/blob/main/docs/MCP_SETUP.md" },
      {
        label: "Disclaimer",
        href: "https://github.com/OliverF21/Ledger/blob/main/DISCLAIMER.md",
      },
      {
        label: "Privacy",
        href: "https://github.com/OliverF21/Ledger/blob/main/PRIVACY.md",
      },
    ],
  },
} as const;

export type Site = typeof site;
export type ShotKey = keyof typeof site.shots;
export type FeatureCell = (typeof site.features.cells)[number];
