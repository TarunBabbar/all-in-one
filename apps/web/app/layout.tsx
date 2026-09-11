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
    <html lang="en">
      <head>
        {/* Must run before first paint. A saved theme applied in an effect
            would arrive a frame late and flash the default. */}
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
