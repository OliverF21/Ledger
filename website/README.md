# Ledger website

Marketing site for Ledger. Deploy this folder on Vercel.

## Vercel

1. Import the GitHub repo.
2. Set **Root Directory** to `website`.
3. Framework: Next.js. Build command `npm run build`, output `.next`.

Optional env: `NEXT_PUBLIC_SITE_URL` (canonical URL for Open Graph). The download button reads the latest GitHub Release in [`src/release/github.ts`](src/release/github.ts) (cached 1 hour).

## Local

```bash
cd website
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Updating the live site

Three files. Do not hunt through components for hex or copy.

### Tokens

[`src/design/tokens.css`](src/design/tokens.css) is the whole palette, radius, glass, and glow. Values started from `Ledger_Overview.dc.html`. Change `--canvas`, `--positive`, `--radius-frame`, `--cta-top` here.

### Copy and screenshot paths

[`src/content/site.ts`](src/content/site.ts) holds headlines, nav, feature blurbs, and `shots.*` paths.

### Product shots

Drop replacement captures into [`public/product/`](public/product/). Keep the filename.

| File | Used as |
| --- | --- |
| `overview.png` | Hero canvas, product frame, bento crops |

When you have dedicated screens, add `budgets.png` / `activity.png` and point `site.shots.budgets` and `site.shots.activity` at them.

See [`public/product/README.md`](public/product/README.md) for sizes.

## Design source

- Screenshot: Overview mock (glass charcoal, mint net-worth line, white Sync button)
- HTML spec: `Ledger Overview.dc.html` (Schibsted Grotesk, 24px frames, 11px buttons)
