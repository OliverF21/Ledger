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
    overview: "/product/overview.png",
    budgets: "/product/budgets.png",
    transactions: "/product/transactions.png",
    investments: "/product/investments.png",
    advisor: "/product/advisor.png",
    deck: "/product/macbook-deck.png",
    macbook: "/product/macbook.png",
  },

  hero: {
    lines: ["Your money stays", "on your machine."],
    headline: "Your money stays on your machine.",
    subtext:
      "A personal finance app that lives on your computer. You bring the Plaid keys.",
    githubLabel: "GitHub",
    shotAlt: "Ledger Overview on a MacBook. Net worth, spending, and budgets.",
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

  /* Drop a file at public/product/walk.mp4 and set walk.video to that path
     when you have a product walkthrough. Until then the MacBook screen
     crossfades the stills below on scroll. */
  features: {
    id: "features",
    video: null as string | null,
    scenes: [
      {
        key: "overview",
        title: "Overview",
        body: "One desk for the month. Net worth across banks, brokerages, and optional crypto wallets, with assets, liabilities, and this month's spend in the same view.",
        points: [
          "Daily net worth snapshots",
          "Spending donut and activity feed",
          "Budgets without leaving the page",
        ],
        shot: "overview" as const,
      },
      {
        key: "sync",
        title: "Transactions",
        body: "Plaid pulls new activity on a schedule, every six hours by default. Search, recategorize, split, hide, and export CSV. Recurring charges surface on their own.",
        points: [
          "Scheduled pulling, plus Sync now",
          "Split and recategorize in place",
          "CSV export when you need a copy",
        ],
        shot: "transactions" as const,
      },
      {
        key: "budgets",
        title: "Budgets",
        body: "Category limits that carry into the next month. Progress against dining, groceries, rent, and the rest, with overage alerts before the month gets away from you.",
        points: [
          "Limits roll forward each month",
          "Overage alerts in the app",
          "Same categories as the transaction stream",
        ],
        shot: "budgets" as const,
      },
      {
        key: "risk",
        title: "Investments",
        body: "Holdings and performance when Plaid Investments is enabled. Risk on the book you already hold, plus a suggested mix you can take or leave.",
        points: [
          "Volatility, Sharpe, drawdown, VaR, beta",
          "Max-Sharpe allocation across held tickers",
          "Nothing rebalances until you say so",
        ],
        shot: "investments" as const,
      },
      {
        key: "mcp",
        title: "Advisor",
        body: "A local, read-only MCP for Claude Desktop. Claude can propose a budget change. You Apply or Dismiss it in Ledger. Nothing writes until you do.",
        points: [
          "Runs on this machine, not a Ledger cloud",
          "Read-only analytics tools by default",
          "Proposals wait for Apply or Dismiss",
        ],
        shot: "advisor" as const,
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
export type WalkScene = (typeof site.features.scenes)[number];
