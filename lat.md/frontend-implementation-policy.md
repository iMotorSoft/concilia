# Frontend Implementation Policy

This policy governs Astro 7 + Svelte 5 frontend development in Concilia.

## Stack

- **Astro 7** (islands architecture, static-first)
- **Svelte 5** (runes mode, `client:load`/`client:visible` islands)
- **TypeScript** (strict mode)
- **Tailwind CSS** (utility-first, no custom CSS unless justified)

## Project Structure

```
clientA/
├── src/
│   ├── pages/              # .astro route pages
│   ├── layouts/            # .astro layouts
│   ├── components/
│   │   ├── agui/           # Reconciliation UI (islands)
│   │   │   ├── cards/      # Result cards (1a1, N1, SICOM, etc)
│   │   │   └── ...
│   │   ├── ui/             # Generic reusable (Button, Dialog, etc)
│   │   └── global.js       # Public config facade
│   ├── lib/                # Utilities, API client, stores
│   └── styles/             # Global CSS, Tailwind
├── public/                 # Static assets
├── e2e/                    # Playwright tests
└── astro.config.mjs
```

## Island Hydration

| Directive | Use Case |
|-----------|----------|
| `client:load` | Immediate interactivity (wizard, upload) |
| `client:visible` | Below-fold cards, lazy charts |
| `client:idle` | Non-critical (tooltips, animations) |
| `client:media` | Responsive islands |

**No `client:only`** — all islands server-render first.

## State Management

- **Svelte 5 runes** (`$state`, `$derived`, `$effect`) — primary
- **Context API** — cross-island shared state (wizard, auth)
- **No external stores** (Redux, Pinia, etc.) without ADR

## API Client

- Single `lib/api.ts` with typed `fetch` wrapper
- Auto-injects `X-Request-ID`, handles 401/403/5xx
- SSE client in `lib/sse.ts` (reconnection, `Last-Event-ID`)

## Styling

- Tailwind utility classes only
- Design tokens in `tailwind.config.mjs` (colors, spacing, radii)
- **No** `@apply` in component styles (use component variants)
- Dark mode via `class` strategy (not `media`)

## Accessibility

- Semantic HTML first
- `aria-*` where native semantics insufficient
- Focus visible (`focus-visible` polyfill)
- Color contrast AA minimum
- Playwright a11y audit in CI (`pnpm test:a11y`)

## Build & Validation

```bash
pnpm check      # TypeScript + Astro check
pnpm build      # Production build
pnpm test:e2e   # Playwright (requires credentials)
pnpm test:a11y  # Axe-core audit
```

## Forbidden

- Direct `fetch` in components (use `lib/api.ts`)
- `<script>` tags in `.astro` (use islands)
- `document.querySelector` in Svelte (use `bind:this`)
- Global CSS (except `src/styles/global.css` reset)
- `any` type (strict TS)