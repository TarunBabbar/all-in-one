"use client";

import { useState } from "react";

import { GitHubPusher } from "@/components/github-pusher";
import { JiraIssueFetcher } from "@/components/jira-issue-fetcher";
import { runEngine, type EngineRunResult, type GithubFile, type JiraIssue } from "@/lib/api";
import { TOOL_FORMS, type ToolField } from "@/lib/tool-forms";

// Tools whose primary input is a free-text requirement: show "Load from Jira".
const REQUIREMENT_TOOLS = new Set(["intake", "requirement-doctor", "test-cases"]);
// Tools whose output is code/files: show "Push to GitHub".
const FILE_OUTPUT_TOOLS = new Set(["codegen", "executor", "etl", "a11y"]);

function parseField(field: ToolField, raw: string): unknown {
  if (raw.trim() === "") return undefined;
  switch (field.type) {
    case "number":
      return Number(raw);
    case "json":
      return JSON.parse(raw);
    case "checkbox":
      return raw === "on";
    default:
      return raw;
  }
}

export function ToolWorkspace({ toolId }: { toolId: string }) {
  const def = TOOL_FORMS[toolId];
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries((def?.fields ?? []).map((f) => [f.name, f.default ?? ""])),
  );
  const [output, setOutput] = useState<EngineRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!def) {
    return (
      <div className="rounded-lg border bg-[var(--bg-elev)] p-6 text-sm text-[var(--ink-faint)]">
        No workspace defined for this tool yet.
      </div>
    );
  }

  const run = async () => {
    setError(null);
    setBusy(true);
    try {
      const input: Record<string, unknown> = {};
      for (const f of def.fields) {
        const v = parseField(f, values[f.name] ?? "");
        if (v !== undefined) input[f.name] = v;
      }
      const res = await runEngine(def.engine, input);
      setOutput(res);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onJiraFetched = (_issue: JiraIssue, text: string) => {
    const textField = def.fields.find((f) => f.name === "text");
    if (textField) {
      setValues((v) => ({ ...v, text }));
    }
  };

  // Derive pushable files from the output payload.
  const pushFiles: GithubFile[] = (() => {
    if (!output) return [];
    const p = output.payload;
    // codegen / executor emit { files: [{ name, content }] } or [{ path, content }]
    const nested = (p as { files?: { name?: string; content?: string }[] }).files;
    if (Array.isArray(nested)) {
      return nested
        .filter((f) => f.content)
        .map((f) => ({ path: f.name ?? "artifact.txt", content: f.content as string }));
    }
    // a11y / etl / release: emit a report payload — offer it as a JSON file.
    const json = JSON.stringify(p, null, 2);
    return json ? [{ path: `${toolId}-output.json`, content: json }] : [];
  })();

  const showJira = REQUIREMENT_TOOLS.has(toolId);
  const showPush = FILE_OUTPUT_TOOLS.has(toolId) && pushFiles.length > 0;

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <header>
        <p className="text-xs font-semibold uppercase tracking-widest text-[var(--accent)]">
          Tool
        </p>
        <h1 className="mt-1 text-3xl font-bold tracking-tight">{def.title}</h1>
        <p className="mt-2 text-sm leading-relaxed text-[var(--ink-soft)]">
          {def.description}
        </p>
      </header>

      <div className="rounded-xl border bg-[var(--bg-elev)] p-5 shadow-sm">
        <div className="space-y-3">
          {def.fields.map((f) => (
            <div key={f.name}>
              <label className="text-xs font-semibold uppercase tracking-wide text-[var(--ink-faint)]">
                {f.label}
              </label>
              {f.type === "textarea" ? (
                <textarea
                  value={values[f.name] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                  rows={4}
                  className="mt-1 w-full rounded-md border bg-[var(--bg)] px-3 py-2 font-mono text-xs outline-none focus:border-[var(--accent)]"
                />
              ) : f.type === "json" ? (
                <textarea
                  value={values[f.name] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                  rows={4}
                  placeholder='[{"title": "…", "status": "passed"}]'
                  className="mt-1 w-full rounded-md border bg-[var(--bg)] px-3 py-2 font-mono text-xs outline-none focus:border-[var(--accent)]"
                />
              ) : f.type === "checkbox" ? (
                <div className="mt-1">
                  <input
                    type="checkbox"
                    checked={(values[f.name] ?? "") === "on"}
                    onChange={(e) =>
                      setValues((v) => ({ ...v, [f.name]: e.target.checked ? "on" : "" }))
                    }
                    className="h-4 w-4 accent-[var(--accent)]"
                  />
                </div>
              ) : (
                <input
                  value={values[f.name] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                  placeholder={f.placeholder}
                  className="mt-1 w-full rounded-md border bg-[var(--bg)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
                />
              )}
            </div>
          ))}
        </div>

        {showJira && (
          <div className="mt-4">
            <JiraIssueFetcher onFetched={onJiraFetched} />
          </div>
        )}

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={run}
            disabled={busy}
            className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-[#fdfaf4] hover:bg-[var(--accent-strong)] disabled:opacity-50"
          >
            {busy ? "Running…" : "Run"}
          </button>
          {error && <span className="text-sm text-[var(--bad)]">{error}</span>}
        </div>
      </div>

      {output && (
        <div className="rounded-xl border bg-[var(--bg-elev)] p-5 shadow-sm">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--ink-faint)]">
            Output · {output.kind}
          </p>
          <pre className="max-h-96 overflow-auto rounded bg-[var(--bg-sunken)] p-3 text-xs text-[var(--ink-soft)]">
            {JSON.stringify(output.payload, null, 2)}
          </pre>
          {showPush && (
            <div className="mt-3">
              <GitHubPusher
                files={pushFiles}
                defaultPrefix={`qa-one/${toolId}`}
                buttonLabel="Push to repo"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
