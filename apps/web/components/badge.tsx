import type { ReactNode } from "react";

/**
 * Small mono pill used for status and provenance labels ("Flagship tool",
 * "Complete", "4/4 passed"). Mono keeps them visually distinct from prose and
 * signals they are system state rather than copy.
 */
export type BadgeTone = "neutral" | "accent" | "ok" | "warn" | "bad";

const TONE: Record<BadgeTone, string> = {
  neutral: "border-[var(--line-strong)] text-[var(--ink-soft)]",
  accent: "border-[var(--accent-line)] bg-[var(--accent-soft)] text-[var(--accent)]",
  ok: "border-[var(--ok)]/35 bg-[var(--ok-soft)] text-[var(--ok)]",
  warn: "border-[var(--warn)]/35 bg-[var(--warn-soft)] text-[var(--warn)]",
  bad: "border-[var(--bad)]/35 bg-[var(--bad-soft)] text-[var(--bad)]",
};

export function Badge({
  tone = "neutral",
  dot,
  children,
}: {
  tone?: BadgeTone;
  /** Show a leading dot in the current color — reads as a live indicator. */
  dot?: boolean;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-[6px] border px-2.5 py-[5px] text-[11px] font-medium tracking-[0.02em] ${TONE[tone]}`}
      style={{ fontFamily: "var(--font-mono)" }}
    >
      {dot && (
        <span
          aria-hidden
          className="h-1.5 w-1.5 shrink-0 rounded-full bg-current"
        />
      )}
      {children}
    </span>
  );
}
