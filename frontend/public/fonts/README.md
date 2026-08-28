# Bundled fonts

Self-hosted rather than pulled from the Google Fonts CDN at runtime. Three
reasons, in order of how much they matter here:

1. **Ledger ships as a desktop app.** A packaged build can't count on reaching
   `fonts.googleapis.com` — offline, behind a proxy, or under a restrictive
   CSP the request just fails and every screen silently falls back to a system
   face. The design is built on this typeface; it shouldn't be optional.
2. **No third-party request from a personal-finance app.** Every page load
   otherwise tells Google's CDN that someone opened their budget (see
   PRIVACY.md).
3. **The real variable range.** The CDN request the design handoff uses
   (`wght@400;500;600;700;800;900`) serves *static* instances, so the 550 and
   650 weights the design calls for round to the nearest hundred. These files
   are the variable builds — `font-weight: 400 900` — so intermediate weights
   render as drawn.

| File | Family | Axis | Subset |
| --- | --- | --- | --- |
| `schibsted-grotesk-latin.woff2` | Schibsted Grotesk | `wght 400..900` | latin |
| `schibsted-grotesk-latin-ext.woff2` | Schibsted Grotesk | `wght 400..900` | latin-ext |
| `jetbrains-mono-latin.woff2` | JetBrains Mono | `wght 400..700` | latin |

Both families are licensed under the SIL Open Font License 1.1, which permits
redistribution as part of a larger work:

- Schibsted Grotesk — https://github.com/schibsted/schibsted-grotesk
- JetBrains Mono — https://github.com/JetBrains/JetBrainsMono

Fetched from the Google Fonts CDN (Schibsted Grotesk v7, JetBrains Mono v24).
The `@font-face` declarations, including the `unicode-range` subsetting that
decides which file loads, live at the top of `src/index.css`.
