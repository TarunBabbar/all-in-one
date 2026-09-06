import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "QA/One — Consolidated AI QA Workspace",
  description:
    "AI QA workspace: test generation, Playwright execution, failure triage, visual regression, and release gates.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
