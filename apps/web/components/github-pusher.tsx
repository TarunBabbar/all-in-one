"use client";

import { useState } from "react";

import { pushFilesToGithub, type GithubFile } from "@/lib/api";

/**
 * Push generated artifacts (a Playwright suite, a report, exports) to the
 * connected GitHub repo. Shows per-file results.
 */
export function GitHubPusher({
  files,
  defaultPrefix,
  buttonLabel,
}: {
  files: GithubFile[];
  defaultPrefix?: string;
  buttonLabel?: string;
}) {
  const [prefix, setPrefix] = useState(defaultPrefix ?? "generated");
  const [message, setMessage] = useState("chore: add generated QA artifact");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<
    { path: string; ok: boolean; commit_sha?: string; error?: string }[] | null
  >(null);

  const push = async () => {
    if (!files.length) return;
    setBusy(true);
    setError(null);
    setResults(null);
    try {
      const res = await pushFilesToGithub(files, {
        prefix: prefix.trim() || undefined,
        message: message.trim() || undefined,
      });
      setResults(res.results);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const okCount = results?.filter((r) => r.ok).length ?? 0;

  return (
    <div className="rounded-lg border border-[var(--line)] bg-[var(--bg-sunken)]/60 p-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--ink-faint)]">
        🐙 Push to GitHub ({files.length} file{files.length === 1 ? "" : "s"})
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={prefix}
          onChange={(e) => setPrefix(e.target.value)}
          placeholder="folder"
          className="w-36 rounded-md border bg-[var(--bg)] px-2 py-1.5 text-xs outline-none focus:border-[var(--accent)]"
          title="Target folder in the repo"
        />
        <button
          onClick={push}
          disabled={busy || !files.length}
          className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-xs font-semibold text-[#fdfaf4] hover:bg-[var(--accent-strong)] disabled:opacity-40"
        >
          {busy ? "Pushing…" : buttonLabel ?? "Push files"}
        </button>
        {results && (
          <span className={`text-xs ${okCount === results.length ? "text-[var(--ok)]" : "text-[var(--bad)]"}`}>
            {okCount}/{results.length} pushed
          </span>
        )}
      </div>
      {error && <p className="mt-2 text-xs text-[var(--bad)]">✗ {error}</p>}
      {results && (
        <ul className="mt-2 space-y-0.5">
          {results.map((r) => (
            <li key={r.path} className="flex items-center justify-between text-xs">
              <span className="truncate font-mono text-[var(--ink-soft)]">{r.path}</span>
              <span className={r.ok ? "text-[var(--ok)]" : "text-[var(--bad)]"}>
                {r.ok ? "✓ pushed" : `✗ ${r.error ?? "failed"}`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
