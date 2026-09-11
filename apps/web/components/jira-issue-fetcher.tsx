"use client";

import { useState } from "react";

import { fetchJiraIssue, type JiraIssue } from "@/lib/api";
import { Badge } from "@/components/badge";
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
    <div className="rounded-[var(--r-md)] border border-[var(--line)] bg-[var(--bg-sunken)] p-3">
      <p className="field-label mb-2 flex items-center gap-1.5">
        <Icon name="link" size={12} />
        Load from Jira
      </p>
      <div className="flex gap-2">
        <input
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="PROJ-123"
          aria-label="Jira issue key"
          className="w-40 rounded-[var(--r-md)] border border-[var(--line-strong)] bg-[var(--bg)] px-2.5 py-1.5 text-[12.5px] text-[var(--ink)] outline-none transition-colors placeholder:text-[var(--ink-faint)] focus:border-[var(--accent)]"
          style={{ fontFamily: "var(--font-mono)" }}
        />
        <button
          onClick={fetch}
          disabled={busy || !key.trim()}
          className="press inline-flex shrink-0 items-center gap-1.5 rounded-[var(--r-md)] border border-[var(--line-strong)] px-3 py-1.5 text-[12.5px] font-semibold text-[var(--ink-soft)] transition-colors hover:border-[var(--accent)] hover:text-[var(--ink)] disabled:opacity-40"
        >
          <Icon name={busy ? "clock" : "search"} size={12} />
          {busy ? "Fetching…" : "Fetch"}
        </button>
      </div>
      {issue && (
        <p className="qa-fade mt-2 flex flex-wrap items-center gap-1.5 text-[12px] text-[var(--ink-soft)]">
          <Badge tone="ok" dot>
            loaded
          </Badge>
          <span
            className="font-semibold text-[var(--ink)]"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {issue.key}
          </span>
          <span className="truncate">{issue.summary}</span>
        </p>
      )}
      {error && (
        <p className="mt-2 text-[12px] leading-relaxed text-[var(--bad)]">
          {error}
        </p>
      )}
    </div>
  );
}
