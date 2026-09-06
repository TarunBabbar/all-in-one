"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  approveStage,
  createProject,
  getPipelineState,
  runStage,
  type PipelineState,
  type StageResult,
} from "@/lib/api";

const STAGES = ["intake", "doctor", "test_cases", "codegen", "run", "triage", "release"] as const;
type Stage = (typeof STAGES)[number];

const DEMO_REQUIREMENT =
  "As a user, I should be able to search for products by keyword and filter " +
  "the results by category and price range. When no results match, the app " +
  "must show an empty state with a clear message and a reset-filters button. " +
  "Search must handle special characters and invalid input without errors.";

const LABELS: Record<Stage, { name: string; desc: string }> = {
  intake: { name: "Intake", desc: "Capture the requirement" },
  doctor: { name: "Requirement Doctor", desc: "Score + findings, approve or edit" },
  test_cases: { name: "Test Cases", desc: "Typed, prioritized cases" },
  codegen: { name: "CodeGen", desc: "Playwright suite" },
  run: { name: "Run", desc: "Sandboxed execution" },
  triage: { name: "Triage", desc: "Evidence-cited root causes" },
  release: { name: "Release", desc: "GO/NO-GO verdict" },
};

const ENGINE_RE: Partial<Record<Stage, string>> = {
  intake: "intake",
  doctor: "requirement-doctor",
  test_cases: "test-cases",
  codegen: "codegen",
  run: "executor",
  triage: "failure-triage",
  visual: "visual",
  release: "release-gate",
};

function StageBadge({ state }: { state: string }) {
  const map: Record<string, string> = {
    approved: "bg-[var(--ok)] text-white",
    awaiting_approval: "bg-[var(--warn)] text-white",
    blocked: "bg-[var(--bad)] text-white",
    changes_requested: "bg-[var(--warn)] text-white",
    not_started: "bg-[var(--bg-sunken)] text-[var(--ink-faint)]",
    draft: "bg-[var(--bg-sunken)] text-[var(--ink-faint)]",
  };
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${map[state] ?? map.not_started}`}
    >
      {state.replace("_", " ")}
    </span>
  );
}

export default function PipelinePage() {
  const params = useSearchParams();
  const projectParam = params.get("project");
  const [loadedProject, setLoadedProject] = useState<string | null>(null);

  useEffect(() => {
    if (projectParam) {
      setLoadedProject(projectParam);
    }
  }, [projectParam]);

  return <PipelineBody initialProjectId={loadedProject} />;
}

function PipelineBody({ initialProjectId }: { initialProjectId: string | null }) {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [name, setName] = useState("My QA project");
  const [state, setState] = useState<PipelineState | null>(null);
  const [requirement, setRequirement] = useState("");
  const [active, setActive] = useState<Stage | null>(null);
  const [results, setResults] = useState<Partial<Record<Stage, StageResult>>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async (pid: string) => {
    setState(await getPipelineState(pid));
  };

  // Load an existing project when the URL carries ?project=<id>.
  useEffect(() => {
    if (initialProjectId) {
      setProjectId(initialProjectId);
      refresh(initialProjectId).catch(() => setError("Could not load project"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialProjectId]);

  const start = async () => {
    setError(null);
    setBusy(true);
    try {
      const project = await createProject(name || "My QA project");
      setProjectId(project.id);
      // Seed the demo requirement when the user left the box empty so the
      // pipeline has something to run end-to-end on first use.
      const text = requirement.trim();
      if (!text) {
        setRequirement(DEMO_REQUIREMENT);
      }
      setResults({});
      await refresh(project.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const stageState = (s: Stage) => state?.stages[s]?.state ?? "not_started";

  const canRun = (s: Stage) => {
    const idx = STAGES.indexOf(s);
    const earlierApproved = STAGES.slice(0, idx).every((k) => stageState(k) === "approved");
    return earlierApproved && stageState(s) !== "approved";
  };

  const run = async (s: Stage) => {
    if (!projectId) return;
    setError(null);
    setBusy(true);
    setActive(s);
    try {
      const pid = projectId;
      const engine = ENGINE_RE[s] ?? "demo";
      let input: Record<string, unknown> = {};

      // Chain artifact outputs between stages so the flow is end-to-end.
      if (s === "intake") {
        input = { text: requirement, source: "text" };
      } else if (s === "doctor" || s === "test_cases") {
        input = { text: requirement };
      } else if (s === "codegen") {
        const cases = (results.test_cases?.payload as { cases?: unknown[] } | undefined)?.cases;
        input = cases ? { cases } : {};
      } else if (s === "run") {
        const codegenP = results.codegen?.payload as
          | { files?: { name: string; content: string }[]; base_url?: string }
          | undefined;
        input = codegenP?.files
          ? { files: codegenP.files, base_url: codegenP.base_url ?? "http://localhost:3000" }
          : {};
      } else if (s === "triage") {
        const runP = results.run?.payload as { results?: unknown[] } | undefined;
        input = runP?.results ? { results: runP.results } : {};
      } else if (s === "release") {
        // Release consumes the run results (evidence).
        const runP = results.run?.payload as { results?: unknown[] } | undefined;
        input = runP?.results ? { results: runP.results } : {};
      } else if (s === "visual") {
        // No screenshots in the demo path — the visual stage is optional and
        // skipped when skipped; if run without inputs it reports needs-metadata.
        input = {};
      }

      const r = await runStage(pid, s, engine, input);
      setResults((prev) => ({ ...prev, [s]: r }));
      // Capture requirement text surfaced by intake for downstream stages.
      if (s === "intake" && r.payload?.text) {
        setRequirement(r.payload.text as string);
      }
      await refresh(pid);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      setActive(null);
    }
  };

  const approve = async (s: Stage) => {
    if (!projectId) return;
    setError(null);
    setBusy(true);
    try {
      await approveStage(projectId, s);
      await refresh(projectId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const showPayload = (r: StageResult | undefined) => {
    if (!r?.payload) return null;
    return (
      <pre className="mt-3 max-h-48 overflow-auto rounded bg-[var(--bg-sunken)] p-3 text-xs text-[var(--ink-soft)]">
        {JSON.stringify(r.payload, null, 2)}
      </pre>
    );
  };

  const releasePayload = (results.release?.payload ?? {}) as {
    verdict?: string;
    reason?: string;
  };

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-[var(--accent)]">
          Flagship tool
        </p>
        <h1 className="mt-1 text-3xl font-bold tracking-tight">Pipeline</h1>
        <p className="mt-2 text-sm leading-relaxed text-[var(--ink-soft)]">
          Requirement → release verdict, with an approval gate at every stage.
        </p>
      </header>

      {!projectId ? (
        <div className="space-y-4">
          <div className="rounded-xl border bg-[var(--bg-elev)] p-6 shadow-sm">
            <label className="block text-sm font-semibold">Project name</label>
            <div className="mt-2 flex gap-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="flex-1 rounded-md border bg-[var(--bg)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
              />
            </div>
          </div>

          <div className="rounded-xl border bg-[var(--bg-elev)] p-6 shadow-sm">
            <label className="block text-sm font-semibold">Requirement</label>
            <textarea
              value={requirement}
              onChange={(e) => setRequirement(e.target.value)}
              rows={5}
              className="mt-2 w-full rounded-md border bg-[var(--bg)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
              placeholder="Paste a requirement, Jira story, PRD…"
            />
            <div className="mt-3 flex items-center justify-between gap-2">
              <p className="text-xs text-[var(--ink-faint)]">
                Leave empty to load the demo requirement fixture.
              </p>
              <button
                onClick={start}
                disabled={busy}
                className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-[#fdfaf4] hover:bg-[var(--accent-strong)] disabled:opacity-50"
              >
                {busy ? "Creating…" : "Start pipeline"}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-[var(--ink-faint)]">
              Project: <span className="font-semibold text-[var(--ink)]">{name}</span>
            </p>
            <StageBadge state={state?.current_stage ?? "not_started"} />
          </div>

          {/* Stepper */}
          <div className="flex flex-wrap items-center gap-2">
            {STAGES.map((s, i) => {
              const done = stageState(s) === "approved";
              return (
                <span
                  key={s}
                  className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${
                    done
                      ? "border-[var(--ok)]/40 bg-[var(--ok)]/10 text-[var(--ok)]"
                      : "border bg-[var(--bg-elev)] text-[var(--ink-faint)]"
                  }`}
                >
                  <span
                    className={`flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-bold ${
                      done ? "bg-[var(--ok)] text-white" : "bg-[var(--bg-sunken)]"
                    }`}
                  >
                    {done ? "✓" : i + 1}
                  </span>
                  {LABELS[s].name}
                </span>
              );
            })}
          </div>

          {error && (
            <div className="rounded-lg border border-[var(--bad)]/40 bg-[var(--bad)]/10 p-3 text-sm text-[var(--bad)]">
              {error}
            </div>
          )}

          {/* Requirement box: editable until test cases run */}
          {stageState("intake") === "approved" && stageState("test_cases") !== "approved" && (
            <div className="rounded-xl border bg-[var(--bg-elev)] p-4 shadow-sm">
              <label className="text-sm font-semibold">Requirement</label>
              <textarea
                value={requirement}
                onChange={(e) => setRequirement(e.target.value)}
                rows={4}
                className="mt-2 w-full rounded-md border bg-[var(--bg)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
                placeholder="Paste a requirement, Jira story, PRD…"
              />
            </div>
          )}

          {/* Stage cards */}
          <div className="space-y-3">
            {STAGES.map((s) => {
              const st = stageState(s);
              const awaiting = st === "awaiting_approval";
              const approved = st === "approved";
              const res = results[s];
              return (
                <div
                  key={s}
                  className={`rounded-lg border p-4 shadow-sm ${
                    approved
                      ? "border-[var(--ok)]/30 bg-[var(--ok)]/5"
                      : "border bg-[var(--bg-elev)]"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold">{LABELS[s].name}</p>
                      <p className="text-xs text-[var(--ink-faint)]">{LABELS[s].desc}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <StageBadge state={st} />
                      {awaiting && (
                        <button
                          onClick={() => approve(s)}
                          disabled={busy}
                          className="rounded-md bg-[var(--ok)] px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-40"
                        >
                          Approve
                        </button>
                      )}
                      {!approved && (
                        <button
                          onClick={() => run(s)}
                          disabled={busy || !canRun(s)}
                          className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-xs font-semibold text-[#fdfaf4] hover:bg-[var(--accent-strong)] disabled:opacity-40"
                        >
                          {busy && active === s ? "Running…" : "Run stage"}
                        </button>
                      )}
                    </div>
                  </div>
                  {showPayload(res)}
                </div>
              );
            })}
          </div>

          {/* Final verdict */}
          {stageState("release") === "approved" && releasePayload.verdict && (
            <div
              className={`rounded-xl border p-6 text-center ${
                releasePayload.verdict === "GO"
                  ? "border-[var(--ok)]/40 bg-[var(--ok)]/10"
                  : "border-[var(--bad)]/40 bg-[var(--bad)]/10"
              }`}
            >
              <p className="text-4xl font-extrabold tracking-tight">{releasePayload.verdict}</p>
              <p className="mt-2 text-sm text-[var(--ink-soft)]">{releasePayload.reason}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}