"use client";

import { useState } from "react";

import { fetchJiraIssue, type JiraIssue } from "@/lib/api";
import { Icon } from "@/lib/icons";

/**
 * Fetch a Jira issue by key and hand its text to the parent (used wherever a
 * requirement is entered, e.g. pipeline intake and requirement tools).
 */
export function JiraIssueFetcher({
  onFetched,
}: {
  onFetched: (issue: JiraIssue, text: string) => void;
}) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issue, setIssue] = useState<JiraIssue | null>(null);

  const fetch = async () => {
    const k = key.trim();
    if (!k) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetchJiraIssue(k);
      setIssue(res.issue);
      const text = `${res.issue.summary}\n\n${res.issue.description}`.trim();
      onFetched(res.issue, text);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border border-[var(--line)] bg-[var(--bg-sunken)]/60 p-3">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--ink-faint)]">
        <Icon name="intake" size={13} />
        Load from Jira
      </p>
      <div className="flex gap-2">
        <input
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="PROJ-123"
          className="w-40 rounded-md border bg-[var(--bg)] px-2 py-1.5 text-sm outline-none focus:border-[var(--accent)]"
        />
        <button
          onClick={fetch}
          disabled={busy || !key.trim()}
          className="press rounded-[var(--r-md)] bg-[var(--accent)] px-3 py-1.5 text-[12px] font-bold text-[var(--accent-ink)] transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-40"
        >
          {busy ? "Fetching…" : "Fetch issue"}
        </button>
      </div>
      {issue && (
        <p className="mt-2 text-xs text-[var(--ink-soft)]">
          ✓ <span className="font-semibold">{issue.key}</span> · {issue.summary}{" "}
          <span className="text-[var(--ink-faint)]">
            ({issue.issue_type} · {issue.status})
          </span>
        </p>
      )}
      {error && <p className="mt-2 text-xs text-[var(--bad)]">✗ {error}</p>}
    </div>
  );
}
