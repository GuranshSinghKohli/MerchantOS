# ADR 0019 — Approved frontend UI stack and design direction

- **Status:** Accepted
- **Date:** 2026-08-26
- **Extends:** [0001](0001-monorepo-and-service-layout.md) (Next.js lives in `apps/web`)
- **Does not supersede** 0001
- **Does not start Phase 4**

## Context

Phase 4 will build the merchant dashboard. The web app already has Next.js 15, React 19, TypeScript, and Tailwind CSS 3.4. The rest of the UI stack and the visual direction were unspecified. Latest shadcn/ui defaults new projects to Tailwind v4; upgrading Tailwind now would be a CSS-framework major bump on a working skeleton.

## Decision

`apps/web` uses this stack only. Do not add alternative UI kits, animation libraries, chart libraries, client state libraries, or CSS frameworks.

| Layer | Package | Notes |
|-------|---------|-------|
| Core (already present) | `next`, `react`, `react-dom`, TypeScript, `tailwindcss` | Keep Tailwind **3.4**. Do not upgrade to v4 in this ADR. |
| Components | [shadcn/ui](https://ui.shadcn.com) (copy-in, New York) | Add components in Phase 4 via `pnpm dlx shadcn@latest add -c apps/web`. Do not run `init` with defaults that migrate to Tailwind v4. |
| Icons | `lucide-react` | |
| Toasts | `sonner` | shadcn deprecated its toast in favor of Sonner. |
| Theme | `next-themes` | Light/dark. Wire `ThemeProvider` in Phase 4. |
| Animation | `motion` | Page/layout/entrance/hover-tap only. Honor `prefers-reduced-motion`. No parallax, custom cursors, or magnetic chrome. |
| Server/async UI data | `@tanstack/react-query` | Client polling only (ask-run, sync). Server Components remain the default first paint. |
| Tables | `@tanstack/react-table` **v8** | Latest npm is v9; v8 matches current shadcn data-table recipes. |
| Charts | `recharts` | |
| Forms | `react-hook-form`, `zod`, `@hookform/resolvers` | Resolver is the official RHF↔Zod bridge (not listed separately in the product brief). |
| Utilities | `date-fns`, `clsx`, `tailwind-merge`, `class-variance-authority` | CVA is required by shadcn. `react-is@19.2.8` satisfies Recharts' React 19 peer. |

Design direction: premium production B2B. Inspiration is Shopify Admin, Linear, and Vercel — clean hierarchy, strong typography, responsive layouts, accessible components, subtle motion, polished loading/empty/error states, keyboard access, light and dark.

The web app still talks only to MerchantOS `/api/v1`. It never calls Shopify.

## Alternatives

- Tailwind v4 + latest shadcn defaults — rejected until Phase 4 needs it; keep the existing v3 skeleton
- TanStack Table v9 — rejected for now (shadcn recipes are v8)
- Framer Motion package name `framer-motion` — rejected; use `motion`
- MUI / Chakra / Mantine / Radix Themes / chart.js / Zustand — rejected as alternatives

## Tradeoffs

shadcn on Tailwind 3 requires a v3 `components.json` and care not to accept a CLI Tailwind v4 migration. Table v8 will need a later ADR if Phase 4 standardizes on v9.

## Consequences

`docs/architecture.md` §10. Phase 4 implements screens; this ADR only locks dependencies and direction.
