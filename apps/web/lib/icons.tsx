import type { ReactNode, SVGProps } from "react";

/**
 * Inline stroke icon set.
 *
 * Emoji were doing this job before and they read as placeholder: they render
 * differently on every OS, carry their own color, and cannot inherit weight or
 * optical size. These are single-path-family strokes on a 24 grid, drawn at
 * 1.6 weight so they match the type instead of shouting over it.
 */

export type IconName =
  | "pipeline"
  | "intake"
  | "doctor"
  | "plan"
  | "gate"
  | "cases"
  | "codegen"
  | "runner"
  | "triage"
  | "visual"
  | "api"
  | "a11y"
  | "etl"
  | "release"
  | "leakage"
  | "rag"
  | "security"
  | "prompt"
  | "settings"
  | "search"
  | "check"
  | "close"
  | "alert"
  | "arrow"
  | "clock"
  | "stack"
  | "bolt"
  | "link";

const PATHS: Record<IconName, ReactNode> = {
  // Workflow — two nodes joined
  pipeline: (
    <>
      <rect x="3" y="3" width="7.5" height="7.5" rx="2" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2" />
      <path d="M6.75 10.5v3A3.75 3.75 0 0 0 10.5 17.25h3" />
    </>
  ),
  // Inbox tray
  intake: (
    <>
      <path d="M3.5 13h4l1.5 2.5h6L16.5 13h4" />
      <path d="M6 13 7.75 5h8.5L18 13v5.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 18.5Z" />
    </>
  ),
  // Vital line
  doctor: (
    <>
      <path d="M3 12.5h3.2l2.1-5.4 3.1 10 2.4-5.4H21" />
    </>
  ),
  // Checklist
  cases: (
    <>
      <path d="m3.5 7 1.5 1.5L8 5.5" />
      <path d="m3.5 13 1.5 1.5L8 11.5" />
      <path d="m3.5 19 1.5 1.5L8 17.5" />
      <path d="M11.5 7.5H21" />
      <path d="M11.5 13.5H21" />
      <path d="M11.5 19.5H21" />
    </>
  ),
  // Document with a folded corner — a written plan
  plan: (
    <>
      <path d="M13.5 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5Z" />
      <path d="M13.5 3v5.5H19" />
      <path d="M8.5 13h7" />
      <path d="M8.5 16.5h4.5" />
    </>
  ),
  // Gate — a check passing through a threshold
  gate: (
    <>
      <path d="M4 6.5h16" />
      <path d="M4 17.5h16" />
      <path d="m8.5 11 2.5 2.5 4.5-5" />
    </>
  ),
  // Angle brackets + slash
  codegen: (
    <>
      <path d="m8.5 8.5-4 3.5 4 3.5" />
      <path d="m15.5 8.5 4 3.5-4 3.5" />
      <path d="m13.5 5.5-3 13" />
    </>
  ),
  // Play
  runner: (
    <>
      <path d="M7.5 5.25v13.5L19 12Z" />
    </>
  ),
  // Magnifier
  triage: (
    <>
      <circle cx="10.75" cy="10.75" r="6.25" />
      <path d="m15.5 15.5 4.5 4.5" />
    </>
  ),
  // Framed image
  visual: (
    <>
      <rect x="3" y="4.75" width="18" height="14.5" rx="2.25" />
      <circle cx="8.5" cy="10" r="1.6" />
      <path d="m3.8 17.5 4.7-4.7 3.6 3.6 2.9-2.9 5.2 5.2" />
    </>
  ),
  // Connector
  api: (
    <>
      <path d="M12 3v5.5" />
      <path d="M8 8.5h8v3.25A4 4 0 0 1 12 15.75a4 4 0 0 1-4-4Z" />
      <path d="M12 15.75V21" />
    </>
  ),
  // Accessibility figure
  a11y: (
    <>
      <circle cx="12" cy="5" r="1.9" />
      <path d="M4.75 9.25h14.5" />
      <path d="M12 9.25v5.5" />
      <path d="m8.5 21 3.5-6.25L15.5 21" />
    </>
  ),
  // Datastore
  etl: (
    <>
      <ellipse cx="12" cy="6" rx="7" ry="3" />
      <path d="M5 6v12c0 1.66 3.13 3 7 3s7-1.34 7-3V6" />
      <path d="M5 12c0 1.66 3.13 3 7 3s7-1.34 7-3" />
    </>
  ),
  // Signal stack
  release: (
    <>
      <rect x="7.25" y="3" width="9.5" height="18" rx="3" />
      <circle cx="12" cy="7.5" r="1.25" />
      <circle cx="12" cy="12" r="1.25" />
      <circle cx="12" cy="16.5" r="1.25" />
    </>
  ),
  // Drop
  leakage: (
    <>
      <path d="M12 3.5c3.6 4.1 6 6.6 6 9.6a6 6 0 0 1-12 0c0-3 2.4-5.5 6-9.6Z" />
    </>
  ),
  // Open book
  rag: (
    <>
      <path d="M4 5.5A2 2 0 0 1 6 3.5h13.5v14.75H6a2 2 0 0 0-2 2Z" />
      <path d="M4 20.25a2 2 0 0 1 2-2h13.5" />
    </>
  ),
  // Verified shield
  security: (
    <>
      <path d="M12 3 5.25 6v5.75c0 4.2 3.1 7.6 6.75 9.25 3.65-1.65 6.75-5.05 6.75-9.25V6Z" />
      <path d="m9.25 12 1.9 1.9 3.6-3.8" />
    </>
  ),
  // Target
  prompt: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="12" cy="12" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  // Sliders
  settings: (
    <>
      <path d="M4 7.5h9" />
      <circle cx="16.5" cy="7.5" r="2.4" />
      <path d="M20 16.5h-9" />
      <circle cx="7.5" cy="16.5" r="2.4" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m15.75 15.75 4.25 4.25" />
    </>
  ),
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  close: (
    <>
      <path d="M6.5 6.5l11 11" />
      <path d="M17.5 6.5l-11 11" />
    </>
  ),
  alert: (
    <>
      <path d="M12 4.5 2.75 20h18.5Z" />
      <path d="M12 10v4.25" />
      <path d="M12 17.25h.01" />
    </>
  ),
  arrow: (
    <>
      <path d="M4.5 12h14" />
      <path d="m13 6.5 5.5 5.5-5.5 5.5" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.25" />
      <path d="M12 7.25V12.5l3.5 2" />
    </>
  ),
  stack: (
    <>
      <path d="m12 3.5 8.5 4.5L12 12.5 3.5 8Z" />
      <path d="m3.5 13 8.5 4.5L20.5 13" />
    </>
  ),
  bolt: <path d="M13.5 3 5.5 13.5h6L10.5 21l8-10.5h-6Z" />,
  link: (
    <>
      <path d="M10.5 13.5a3.5 3.5 0 0 0 5 0l3-3a3.5 3.5 0 0 0-5-5l-1.5 1.5" />
      <path d="M13.5 10.5a3.5 3.5 0 0 0-5 0l-3 3a3.5 3.5 0 0 0 5 5l1.5-1.5" />
    </>
  ),
};

export function Icon({
  name,
  size = 18,
  className,
  strokeWidth = 1.6,
  ...rest
}: { name: IconName; size?: number; strokeWidth?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
      {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}
