import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "QA/One — Consolidated AI QA Platform",
  description:
    "One workspace merging the 41 AI Tester Blueprint 3x hackathon projects: test generation, Playwright execution, failure triage, visual regression, and release gates.",
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
