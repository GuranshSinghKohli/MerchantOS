# MerchantOS dashboard visual system (Phase 4)

Built from the shipped UI. Inspiration: Shopify Admin, Linear, Vercel (ADR 0019). Mode: Operate.

- Neutrals: warm paper in light (`hsl(40 14% 97%)`), ink dark (`hsl(240 8% 6%)`)
- One accent: teal for positive movement; rose for decline
- Hairline borders, 10px radius, no glass, no hero gradient
- System sans, tabular numbers on KPIs
- Sidebar rail on desktop; dialog nav on small screens
- Motion: 200ms card entrance, disabled under `prefers-reduced-motion`
