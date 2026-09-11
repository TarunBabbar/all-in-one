"use client";

import { useState } from "react";

import { ArtifactView } from "@/components/artifact-view";
import { Badge } from "@/components/badge";
import { GitHubPusher } from "@/components/github-pusher";
import { JiraIssueFetcher } from "@/components/jira-issue-fetcher";
import { Icon } from "@/lib/icons";
import { runEngine, type EngineRunResult, type GithubFile, type JiraIssue } from "@/lib/api";
import { TOOLS } from "@/lib/tools";
import { TOOL_FORMS, type ToolField } from "@/lib/tool-forms";

// Tools whose primary input is a free-text requirement: offer "Load from Jira".
const REQUIREMENT_TOOLS = new Set(["intake", "requirement-doctor", "test-cases"]);
// Tools whose output is code/files: offer "Push to GitHub".
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

const INPUT_CLASS =
  "mt-1.5 w-full rounded-[var(--r-md)] border border-[var(--line-strong)] bg-[var(--bg)] px-2.5 py-2 text-[12.5px] text-[var(--ink)] outline-none transition-colors placeholder:text-[var(--ink-faint)] focus:border-[var(--accent)]";

/**
 * The workspace for a single engine: give it inputs, run it, read the result.
 * Deliberately mirrors the pipeline page's vocabulary — same eyebrows, same
 * card treatment, same artifact renderer — so moving between a focused tool and
 * the full chain does not feel like two different products.
 */
export function ToolWorkspace({ toolId }: { toolId: string }) {
  const def = TOOL_FORMS[toolId];
  const meta = TOOLS.find((t) => t.id === toolId);
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries((def?.fields ?? []).map((f) => [f.name, f.default ?? ""])),
  );
  const [output, setOutput] = useState<EngineRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!def) {
    return (
      <div className="mx-auto max-w-3xl rounded-[var(--r-lg)] border border-dashed border-[var(--line-strong)] bg-[var(--bg-elev)] px-6 py-10 text-center">
        <Icon name="alert" size={22} className="mx-auto block text-[var(--ink-faint)]" />
        <p className="mt-2.5 text-[13px] font-semibold text-[var(--ink-soft)]">
          This tool has no workspace yet.
        </p>
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
    if (def.fields.some((f) => f.name === "text")) {
      setValues((v) => ({ ...v, text }));
    }
  };

  // Derive pushable files from the output payload.
  const pushFiles: GithubFile[] = (() => {
    if (!output) return [];
    const p = output.payload;
    // codegen emits a publish-ready bundle ({ filename: content }).
    if (p && typeof p === "object") {
      const bundle = (p as { bundle?: Record<string, string> }).bundle;
      if (bundle && typeof bundle === "object") {
        const entries = Object.entries(bundle).filter(
          ([, content]) => typeof content === "string" && content.length > 0,
        );
        if (entries.length) return entries.map(([name, content]) => ({ path: name, content }));
      }
    }
    // Report-shaped engines get offered as a single JSON artifact.
    const nested = (p as { files?: { name?: string; content?: string }[] }).files;
    if (Array.isArray(nested)) {
      return nested
        .filter((f) => f.content)
        .map((f) => ({ path: f.name ?? "artifact.txt", content: f.content as string }));
    }
    const json = JSON.stringify(p, null, 2);
    return json ? [{ path: `${toolId}-output.json`, content: json }] : [];
  })();

  const showJira = REQUIREMENT_TOOLS.has(toolId);
  const showPush = FILE_OUTPUT_TOOLS.has(toolId) && pushFiles.length > 0;

  const set = (name: string, value: string) =>
    setValues((v) => ({ ...v, [name]: value }));

  return (
    <div className="mx-auto max-w-[900px]">
      <div className="mb-4 flex flex-wrap gap-2">
        <Badge tone="accent" dot>
          Tool
        </Badge>
      </div>

      <h1 className="text-[30px] font-semibold leading-tight text-[var(--ink)]">
        {def.title}
      </h1>
      <p className="mb-7 mt-2.5 max-w-[62ch] text-[14px] leading-relaxed text-[var(--ink-soft)]">
        {def.description}
      </p>

      <div className="space-y-5">
        {/* Input */}
        <section className="overflow-hidden rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)]">
          <div className="border-b border-[var(--line)] px-5 py-3">
            <h2 className="field-label">input</h2>
          </div>

          <div className="space-y-4 px-5 py-4">
            {def.fields.map((f) => (
              <div key={f.name}>
                <label htmlFor={`f-${f.name}`} className="field-label block">
                  {f.label}
                </label>
                {f.type === "textarea" || f.type === "json" ? (
                  <textarea
                    id={`f-${f.name}`}
                    value={values[f.name] ?? ""}
                    onChange={(e) => set(f.name, e.target.value)}
                    rows={f.type === "json" ? 4 : 5}
                    placeholder={f.type === "json" ? '[{"title": "…", "status": "passed"}]' : undefined}
                    className={`${INPUT_CLASS} resize-y text-[11.5px]`}
                    style={{ fontFamily: "var(--font-mono)" }}
                  />
                ) : f.type === "checkbox" ? (
                  <label className="mt-2 flex cursor-pointer items-center gap-2 text-[12.5px] text-[var(--ink-soft)]">
                    <input
                      id={`f-${f.name}`}
                      type="checkbox"
                      checked={(values[f.name] ?? "") === "on"}
                      onChange={(e) => set(f.name, e.target.checked ? "on" : "")}
                      className="h-3.5 w-3.5 accent-[var(--accent)]"
                    />
                    Enabled
                  </label>
                ) : (
                  <input
                    id={`f-${f.name}`}
                    type={f.type === "number" ? "number" : "text"}
                    value={values[f.name] ?? ""}
                    onChange={(e) => set(f.name, e.target.value)}
                    placeholder={f.placeholder}
                    className={INPUT_CLASS}
                  />
                )}
              </div>
            ))}

            {showJira && <JiraIssueFetcher onFetched={onJiraFetched} />}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] px-5 py-3.5">
            <p className="text-[12px] text-[var(--ink-faint)]">
              Runs deterministically where it can; the model only fills in judgement.
            </p>
            <button
              onClick={run}
              disabled={busy}
              className="press inline-flex shrink-0 items-center gap-1.5 rounded-[var(--r-md)] bg-[var(--accent)] px-4 py-2 text-[13px] font-semibold text-[var(--accent-ink)] transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
            >
              <Icon name={busy ? "clock" : "runner"} size={12} />
              {busy ? "Running…" : "Run"}
            </button>
          </div>
        </section>

        {error && (
          <div className="qa-rise flex items-start gap-2 rounded-[var(--r-md)] border border-[var(--bad)]/30 bg-[var(--bad-soft)] p-3.5">
            <Icon name="alert" size={15} className="mt-0.5 shrink-0 text-[var(--bad)]" />
            <div className="min-w-0">
              <p className="field-label text-[var(--bad)]">run failed</p>
              <p
                className="mt-1 text-[11.5px] leading-relaxed text-[var(--ink-soft)]"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {error}
              </p>
            </div>
          </div>
        )}

        {/* Result */}
        {output ? (
          <section className="qa-rise overflow-hidden rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)]">
            <div className="border-b border-[var(--line)] px-5 py-3">
              <h2 className="field-label">output</h2>
            </div>
            <div className="px-5 py-4">
              <ArtifactView payload={output.payload} />
            </div>
            {showPush && (
              <div className="border-t border-[var(--line)] px-5 py-3.5">
                <GitHubPusher
                  files={pushFiles}
                  defaultPrefix={`qa-one/${toolId}`}
                  buttonLabel="Push to repo"
                />
              </div>
            )}
          </section>
        ) : (
          !busy &&
          !error && (
            <div className="rounded-[var(--r-lg)] border border-dashed border-[var(--line-strong)] px-6 py-10 text-center">
              <Icon name={meta?.icon ?? "stack"} size={22} className="mx-auto block text-[var(--ink-faint)]" />
              <p className="mt-2.5 text-[13px] font-semibold text-[var(--ink-soft)]">
                No output yet
              </p>
              <p className="mx-auto mt-1 max-w-md text-[12px] leading-relaxed text-[var(--ink-faint)]">
                Fill the inputs above and run. Results appear here as a readable
                report, with the raw payload available underneath.
              </p>
            </div>
          )
        )}
      </div>
    </div>
  );
}
