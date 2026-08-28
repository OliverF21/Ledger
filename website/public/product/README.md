# Product shots

Replace these files in place. The scroll walk reads screens by filename.

| File | Used as |
| --- | --- |
| `overview.png` | First walk screen and Open Graph |
| `transactions.png` | Transactions / scheduled sync screen |
| `budgets.png` | Budgets screen |
| `investments.png` | Risk and optimization screen |
| `advisor.png` | MCP / Advisor screen |
| `macbook.png` | MacBook Pro mockup frame (black screen; UI shots overlay inside) |
| `macbook-deck.png` | Legacy texture from the old 3D model (unused) |
| `walk.mp4` | Optional. Set `site.features.video` to `/product/walk.mp4` to play in the MacBook instead of stills |

Capture from the live app at 16:10 if you can. Do not overlay captions on the PNG; captions live in `src/content/site.ts`.

If you swap `macbook.png`, update the screen inset tokens in `src/design/tokens.css` (`--mb-screen-*`).
