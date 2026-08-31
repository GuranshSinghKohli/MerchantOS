import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "MerchantOS",
  description: "AI-native commerce OS for Shopify merchants. The model recommends. You approve.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen font-sans">
        {/*
          THESIS: Daily merchant operations desk, not an AI landing page.
          OWN-WORLD: Zinc paper/ink, one teal accent, hairline borders, system sans.
          STORY: The merchant sees trusted store numbers and why they moved.
          FIRST VIEWPORT: Sidebar + store header + date range + four KPIs.
          FORM: Shopify Admin / Linear / Vercel operate-mode canon (ADR 0019).
          FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
        */}
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
