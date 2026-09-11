import type { Metadata } from "next";
import type { ReactNode } from "react";

import { THEME_INIT_SCRIPT } from "@/lib/theme";
import "./globals.css";

export const metadata: Metadata = {
  title: "QA/One — AI QA Workspace",
  description:
    "AI QA workspace: test generation, Playwright execution, failure triage, visual regression, and release gates.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Must run before first paint. A saved theme applied in an effect
            would arrive a frame late and flash the default — the thing this
            exists to prevent.

            It writes data-theme onto <html>, which the server HTML cannot have:
            the server has no idea which theme this browser chose. React reports
            that as a hydration mismatch, so <html> carries
            suppressHydrationWarning — the difference is the intended design,
            not state that failed to reconcile.

            The alternative is a cookie, so the server can render the attribute
            itself and there is no difference to suppress. That is cleaner in
            principle, but reading a cookie in the root layout opts every route
            out of static rendering, which is a real cost to pay for one
            cosmetic attribute. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        {/* Loaded as a stylesheet rather than through next/font so the build
            stays offline-capable. Space Grotesk carries headings, IBM Plex Mono
            carries machine output, Inter carries prose. */}
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
