/* All visible marketing copy, nav, and screenshot paths.
   Swap product shots by replacing files in /public/product and/or changing
   the paths below. Do not put string literals in section components. */

export const site = {
  name: "Ledger",
  github: "https://github.com/OliverF21/Ledger",
  releasesLatest: "https://github.com/OliverF21/Ledger/releases/latest",
  sourceInstall: "https://github.com/OliverF21/Ledger#running-from-source",

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
    headline: "Your money stays on your machine.",
    subtext:
      "A personal finance app that lives on your computer. You bring the Plaid keys.",
    githubLabel: "GitHub",
  },

  localFirst: {
    headline: "Runs on your computer. Not in our cloud.",
    facts: [
      { title: "Local SQLite", body: "Transactions and budgets sit in app-data on disk." },
      { title: "Your Plaid keys", body: "Ledger never holds a bank connection for you." },
      { title: "No Ledger servers", body: "Updates come from GitHub Releases. That is it." },
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
      },
      {
        key: "budgets",
        title: "Budgets",
        body: "Category limits that carry into the next month, with overage alerts.",
        shot: "budgets" as const,
        objectPosition: "right bottom",
      },
      {
        key: "activity",
        title: "Activity",
        body: "Search, recategorize, split, hide, and export CSV.",
        shot: "activity" as const,
        objectPosition: "left bottom",
      },
      {
        key: "investments",
        title: "Investments",
        body: "Holdings and performance when Plaid Investments is enabled.",
        shot: "product" as const,
        objectPosition: "center",
      },
      {
        key: "subscriptions",
        title: "Subscriptions",
        body: "Recurring charges detected from the transaction stream.",
        shot: "product" as const,
        objectPosition: "right center",
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
        body: "Plaid Link runs locally. Access tokens are encrypted on disk, not sent to a Ledger server.",
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
