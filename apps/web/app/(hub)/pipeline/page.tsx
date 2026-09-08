"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { GitHubPusher } from "@/components/github-pusher";
import { JiraIssueFetcher } from "@/components/jira-issue-fetcher";
import {
  createProject,
  getArtifact,
  getPipelineStatus,
  resumePipeline,
  startPipeline,
  stopPipeline,
  type GithubFile,
  type LogEntry,
  type PipelineStatus,
  type StageStatus,
} from "@/lib/api";

/**
 * The flagship pipeline. A requirement flows through a chain of AI agents
 * (intake → doctor → test cases → codegen → run → triage → release) fully
 * automatically — each agent's output is stored and feeds the next. The page
 * polls a status endpoint so you watch the agents light up live, with a log
 * pane streaming underneath. On failure the chain stops at the failed agent;
 * edit its inputs and resume from there.
 */

// Matches services/api PIPELINE_STAGES order. `visual` is optional/skippable.
const STAGES = [
  "intake",
  "doctor",
  "test_cases",
  "codegen",
  "run",
  "triage",
  "visual",
  "release",
] as const;
type Stage = (typeof STAGES)[number];

const LABELS: Record<Stage, { name: string; icon: string; desc: string }> = {
  intake: { name: "Intake", icon: "📥", desc: "Normalize the requirement" },
  doctor: { name: "Doctor", icon: "🩺", desc: "Quality score + findings" },
  test_cases: { name: "Test Cases", icon: "🧪", desc: "Typed, prioritized cases" },
  codegen: { name: "CodeGen", icon: "⚙️", desc: "Playwright TS suite" },
  run: { name: "Run", icon: "🏃", desc: "Sandboxed execution" },
  triage: { name: "Triage", icon: "🔍", desc: "Cluster root causes" },
  visual: { name: "Visual", icon: "👁️", desc: "Regression check (optional)" },
  release: { name: "Release", icon: "🚦", desc: "GO / NO-GO verdict" },
};

// Editable inputs exposed per agent (mirrors OVERRIDABLE_INPUTS on the API).
// Placeholders are filled from the env-backed server defaults when available.
interface FieldDef {
  key: string;
  label: string;
  placeholder?: string;
  type?: "text" | "url" | "number";
  envDefaultKey?: "base_url" | "runner_url";
}
const STAGE_FIELDS: Partial<Record<Stage, FieldDef[]>> = {
  intake: [{ key: "source", label: "Source hint", placeholder: "text | url | jira | github | confluence | pdf" }],
  codegen: [
    { key: "base_url", label: "Base URL for the app under test", type: "url", envDefaultKey: "base_url" },
  ],
  run: [
    { key: "base_url", label: "Base URL for the app under test", type: "url", envDefaultKey: "base_url" },
    { key: "runner_url", label: "Runner URL (Playwright worker)", type: "url", envDefaultKey: "runner_url" },
  ],
};

const DEMO_REQUIREMENT =
  "As a user, I should be able to search for products by keyword and filter " +
  "the results by category and price range. When no results match, the app " +
  "must show an empty state with a clear message and a reset-filters button. " +
  "Search must handle special characters and invalid input without errors.";

const DONE = new Set(["approved"]);
const PENDING = new Set(["not_started", "draft"]);

function githubFilesFromCodegen(payload: Record<string, unknown> | undefined): GithubFile[] {
  if (!payload) return [];
  // Publish-ready bundle ({ filename: content }) — a self-contained folder
  // (package.json + config + spec + README) the user can run after pushing.
  const bundle = payload.bundle as Record<string, string> | undefined;
  if (bundle && typeof bundle === "object") {
    return Object.entries(bundle)
      .filter(([, content]) => typeof content === "string" && content.length > 0)
      .map(([name, content]) => ({ path: name, content }));
  }
  const files = (payload as { files?: { tests?: { name?: string; content?: string }[] } })
    .files?.tests;
  if (!Array.isArray(files)) return [];
  return files
    .filter((f) => f.content)
    .map((f) => ({ path: f.name ?? "qa.spec.ts", content: f.content as string }));
}

function githubFilesFromRelease(payload: Record<string, unknown> | undefined): GithubFile[] {
  if (!payload) return [];
  return [{ path: "release-decision.json", content: JSON.stringify(payload, null, 2) }];
}

/** Pull the first http(s) URL out of requirement text (mirrors API detect_target_url). */
function detectUrl(text: string): string {
  const t = (text || "").trim();
  const prefix = /^url\s*:\s*(\S+)/i.exec(t);
  if (prefix) return prefix[1].replace(/[.,;]+$/, "");
  const m = /https?:\/\/[^\s)\]},;'"<>]+/i.exec(t);
  return m ? m[0].replace(/[.,;]+$/, "") : "";
}

function stageSummary(stage: Stage, payload: Record<string, unknown> | null | undefined): string {
  if (!payload) return "";
  try {
    switch (stage) {
      case "intake": {
        const wc = payload.word_count as number | undefined;
        return wc ? `${wc} words normalized` : "Requirement captured";
      }
      case "doctor": {
        const d = payload.diagnosis as { quality_score?: number } | undefined;
        return d?.quality_score != null ? `Score ${d.quality_score}/100` : "Diagnosis ready";
      }
      case "test_cases": {
        const c = payload.count as number | undefined;
        return c != null ? `${c} cases · prioritized` : "Cases ready";
      }
      case "codegen": {
        const files = (payload.files as { tests?: unknown[] } | undefined)?.tests;
        return files ? `Suite with ${files.length} file(s)` : "Suite generated";
      }
      case "run": {
        const results = (payload.results as { status?: string }[] | undefined) ?? [];
        const passed = results.filter((r) => r.status === "passed").length;
        return results.length ? `${passed}/${results.length} passed` : "Run complete";
      }
      case "triage": {
        const tf = payload.total_failures as number | undefined;
        return tf != null ? `${tf} failure(s) clustered` : "Triage ready";
      }
      case "release": {
        const v = payload.verdict as string | undefined;
        return v ? `Verdict ${v}` : "Decision ready";
      }
      default:
        return "";
    }
  } catch {
    return "";
  }
}

export default function PipelinePage() {
  const params = useSearchParams();
  const projectParam = params.get("project");
  const [loadedProject, setLoadedProject] = useState<string | null>(null);

  useEffect(() => {
    if (projectParam) setLoadedProject(projectParam);
  }, [projectParam]);

  return <PipelineBody key={loadedProject ?? "new"} initialProjectId={loadedProject} />;
}

function PipelineBody({ initialProjectId }: { initialProjectId: string | null }) {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("");
  const [requirement, setRequirement] = useState("");
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [overrides, setOverrides] = useState<Record<string, Record<string, string>>>({});
  const [log, setLog] = useState<LogEntry[]>([]);
  const [showLog, setShowLog] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  const stages = status?.stages ?? {};
  const running = status?.running ?? false;
  const stageState = useCallback(
    (s: Stage) => stages[s]?.state ?? "not_started",
    [stages],
  );

  const syncStatus = useCallback(async (pid: string) => {
    const s = await getPipelineStatus(pid);
    setStatus(s);
    setLog((prev) => {
      const known = new Set(prev.map((l) => l.id));
      const fresh = s.log.filter((l) => !known.has(l.id));
      return fresh.length ? [...prev, ...fresh] : prev;
    });
    setRequirement((req) => req || String(s.inputs?.requirement ?? ""));
    const ov = s.inputs?.overrides as Record<string, Record<string, string>> | undefined;
    if (ov) setOverrides((prev) => ({ ...prev, ...ov }));
  }, []);

  // Load an existing project.
  useEffect(() => {
    if (!initialProjectId) return;
    let cancelled = false;
    setProjectId(initialProjectId);
    setBusy(true);
    syncStatus(initialProjectId)
      .catch(() => setError("Could not load project"))
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialProjectId]);

  // Poll while a chain is running so nodes + log stream live.
  useEffect(() => {
    if (!projectId || !running) return;
    const tick = async () => {
      try {
        await syncStatus(projectId!);
      } catch {
        // transient poll error — keep polling
      }
    };
    tick();
    const timer = setInterval(tick, 1200);
    return () => clearInterval(timer);
  }, [projectId, running, syncStatus]);

  // Auto-scroll the log to the newest line.
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [log.length]);

  // Keep the running node in view as it advances.
  useEffect(() => {
    if (!running || !trackRef.current) return;
    const idx = STAGES.findIndex((s) => stageState(s) === "running");
    if (idx < 0) return;
    const node = trackRef.current.children[idx] as HTMLElement | undefined;
    node?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  }, [running, stageState]);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const project = await createProject(projectName.trim() || "My QA project");
      setProjectId(project.id);
      setProjectName(project.name);
      const text = requirement.trim() || DEMO_REQUIREMENT;
      setRequirement(text);
      setLog([]);
      setStatus(null);
      await startPipeline(project.id, { requirement: text, source: "text" });
      await syncStatus(project.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const patchOverride = (s: Stage, key: string, value: string) => {
    setOverrides((prev) => {
      const stageOv = { ...(prev[s] ?? {}) };
      if (value.trim() === "") delete stageOv[key];
      else stageOv[key] = value;
      return { ...prev, [s]: stageOv };
    });
  };

  const resumeFrom = async (s: Stage) => {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      await resumePipeline(projectId, s, { requirement, overrides });
      await syncStatus(projectId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const cancelRun = async () => {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      await stopPipeline(projectId);
      await syncStatus(projectId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const started = STAGES.some((s) => stageState(s) !== "not_started");
  const doneCount = STAGES.filter((s) => DONE.has(stageState(s))).length;
  const activeCount = STAGES.filter((s) => stageState(s) === "running").length;
  const blockedStage = STAGES.find((s) => stageState(s) === "blocked") ?? null;
  const appUrl = String(status?.inputs?.app_url ?? "");
  const progress = Math.round((doneCount / STAGES.length) * 100);
  const phase = running ? "running" : blockedStage ? "failed" : doneCount === STAGES.length ? "complete" : started ? "paused" : "idle";

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-[var(--accent-soft-2)] px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-[var(--accent-strong)]">
            Flagship tool
          </span>
          {projectId && <PhasePill phase={phase} />}
        </div>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-[var(--ink)]">
          AI QA Pipeline
        </h1>
        <p className="mt-1 text-sm leading-relaxed text-[var(--ink-soft)]">
          One requirement in — a chain of AI agents runs end to end, streaming
          live. If an agent fails, the run stops there so you can fix its input
          and resume.
        </p>
      </header>

      {!projectId ? (
        <StartScreen
          name={projectName}
          onName={setProjectName}
          requirement={requirement}
          onRequirement={setRequirement}
          busy={busy}
          onStart={start}
        />
      ) : (
        <div className="space-y-5">
          {/* Project + run HUD */}
          <RunHud
            projectName={projectName || "QA project"}
            appUrl={appUrl}
            phase={phase}
            running={running}
            busy={busy}
            doneCount={doneCount}
            total={STAGES.length}
            progress={progress}
            blockedStage={blockedStage}
            log={log}
            onCancel={cancelRun}
            onToggleLog={() => setShowLog((v) => !v)}
            showLog={showLog}
          />

          {error && (
            <div className="qa-rise rounded-lg border border-[var(--bad)]/40 bg-[var(--bad)]/10 p-3 text-sm text-[var(--bad)]">
              ✗ {error}
            </div>
          )}

          {/* Agent track */}
          <div className="overflow-x-auto rounded-2xl border bg-[var(--bg-elev)] p-5 shadow-sm">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs font-bold uppercase tracking-widest text-[var(--ink-faint)]">
                Agent chain
              </p>
              <TrackLegend stageState={stageState} />
            </div>
            <div ref={trackRef} className="flex min-w-max items-stretch gap-0">
              {STAGES.map((s, i) => (
                <TrackSegment
                  key={s}
                  stage={s}
                  index={i}
                  total={STAGES.length}
                  state={stageState(s)}
                  running={running}
                />
              ))}
            </div>
          </div>

          {/* Live activity strip */}
          {running && <ActivityStrip log={log} currentStage={STAGES.find((s) => stageState(s) === "running") ?? null} />}

          {/* Agent outputs / failure panel */}
          <StageOutputs
            stages={stages}
            stageState={stageState}
            running={running}
            started={started}
            requirement={requirement}
            onRequirement={setRequirement}
            overrides={overrides}
            onOverride={patchOverride}
            busy={busy}
            onResume={resumeFrom}
            defaults={status?.defaults}
            artifactCacheKey={projectId}
          />

          {showLog && <PipelineLog logRef={logRef} log={log} running={running} />}
        </div>
      )}
    </div>
  );
}

/* ---------------------------------- start ---------------------------------- */

function StartScreen({
  name,
  onName,
  requirement,
  onRequirement,
  busy,
  onStart,
}: {
  name: string;
  onName: (v: string) => void;
  requirement: string;
  onRequirement: (v: string) => void;
  busy: boolean;
  onStart: () => void;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
      <div className="rounded-2xl border bg-[var(--bg-elev)] p-6 shadow-sm">
        <span className="text-2xl">📦</span>
        <label className="mt-3 block text-sm font-semibold text-[var(--ink)]">Project name</label>
        <input
          value={name}
          onChange={(e) => onName(e.target.value)}
          placeholder="My QA project"
          className="mt-2 w-full rounded-lg border bg-[var(--bg)] px-3 py-2.5 text-sm outline-none transition focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]"
        />
        <p className="mt-3 text-xs leading-relaxed text-[var(--ink-faint)]">
          Each pipeline run is stored under this project — reopen it anytime
          from the dashboard to watch the full chain.
        </p>
      </div>

      <div className="rounded-2xl border bg-[var(--bg-elev)] p-6 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <label className="text-sm font-semibold text-[var(--ink)]">Requirement</label>
          <span className="rounded-full bg-[var(--bg-sunken)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--ink-faint)]">
            input
          </span>
        </div>
        <textarea
          value={requirement}
          onChange={(e) => onRequirement(e.target.value)}
          rows={7}
          className="mt-2 w-full resize-y rounded-lg border bg-[var(--bg)] px-3 py-2.5 font-mono text-xs leading-relaxed outline-none transition focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]"
          placeholder={"Paste a requirement, Jira story, PRD…\n\nTip: include the app URL (e.g. https://www.saucedemo.com) — the pipeline will target it automatically."}
        />
        {detectUrl(requirement) ? (
          <div className="mt-2 flex items-center gap-2 rounded-lg border border-[var(--ok)]/30 bg-[var(--ok)]/5 px-3 py-2">
            <span className="text-xs">🎯</span>
            <span className="text-xs text-[var(--ink-soft)]">
              App under test: <span className="font-mono font-bold text-[var(--ok)]">{detectUrl(requirement)}</span>
            </span>
          </div>
        ) : (
          <p className="mt-2 text-xs text-[var(--ink-faint)]">
            No URL detected yet — the app under test will fall back to the
            configured default. Paste a URL in the requirement to target a
            specific site.
          </p>
        )}
        <div className="mt-3">
          <JiraIssueFetcher onFetched={(_issue, text) => onRequirement(text)} />
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-[var(--ink-faint)]">
            Leave empty to load the demo requirement fixture.
          </p>
          <button
            onClick={onStart}
            disabled={busy}
            className="group inline-flex items-center gap-2 rounded-lg bg-[var(--accent)] px-5 py-2.5 text-sm font-bold text-[#fdfaf4] shadow-sm transition hover:bg-[var(--accent-strong)] disabled:opacity-50"
          >
            {busy ? "Creating…" : "▶ Start pipeline"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------- HUD ---------------------------------- */

function PhasePill({ phase }: { phase: string }) {
  const map: Record<string, { label: string; cls: string; dot: string }> = {
    running: { label: "Running", cls: "bg-[var(--accent-soft)] text-[var(--accent-strong)] border-[var(--accent)]/30", dot: "bg-[var(--accent)] animate-pulse" },
    failed: { label: "Failed", cls: "bg-[var(--bad)]/10 text-[var(--bad)] border-[var(--bad)]/30", dot: "bg-[var(--bad)]" },
    complete: { label: "Complete", cls: "bg-[var(--ok)]/10 text-[var(--ok)] border-[var(--ok)]/30", dot: "bg-[var(--ok)]" },
    paused: { label: "Paused", cls: "bg-[var(--warn)]/10 text-[var(--warn)] border-[var(--warn)]/30", dot: "bg-[var(--warn)]" },
    idle: { label: "Idle", cls: "bg-[var(--bg-sunken)] text-[var(--ink-faint)] border-[var(--line)]", dot: "bg-[var(--ink-faint)]" },
  };
  const m = map[phase] ?? map.idle;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest ${m.cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${m.dot}`} />
      {m.label}
    </span>
  );
}

function RunHud({
  projectName,
  appUrl,
  phase,
  running,
  busy,
  doneCount,
  total,
  progress,
  blockedStage,
  log,
  onCancel,
  onToggleLog,
  showLog,
}: {
  projectName: string;
  appUrl: string;
  phase: string;
  running: boolean;
  busy: boolean;
  doneCount: number;
  total: number;
  progress: number;
  blockedStage: Stage | null;
  log: LogEntry[];
  onCancel: () => void;
  onToggleLog: () => void;
  showLog: boolean;
}) {
  const barColor =
    phase === "failed"
      ? "bg-[var(--bad)]"
      : phase === "complete"
        ? "bg-[var(--ok)]"
        : phase === "running"
          ? "bg-[var(--accent)]"
          : "bg-[var(--line-strong)]";

  return (
    <div className="qa-rise overflow-hidden rounded-2xl border bg-[var(--bg-elev)] shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--ink-faint)]">Project</p>
          <p className="truncate text-base font-bold text-[var(--ink)]">{projectName}</p>
          {appUrl && (
            <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-[var(--ink-soft)]">
              <span>🎯</span>
              <span className="truncate font-mono text-[var(--ok)]">{appUrl}</span>
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {running && (
            <button
              onClick={onCancel}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--bad)]/40 px-3 py-1.5 text-xs font-bold text-[var(--bad)] transition hover:bg-[var(--bad)]/10 disabled:opacity-50"
            >
              <span className="inline-block h-2 w-2 rounded-sm bg-[var(--bad)]" /> Stop run
            </button>
          )}
          <button
            onClick={onToggleLog}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line-strong)] px-3 py-1.5 text-xs font-bold text-[var(--ink-soft)] transition hover:bg-[var(--bg-hover)]"
          >
            {showLog ? "Hide log" : "Show log"}
          </button>
        </div>
      </div>

      {/* Progress */}
      <div className="px-5 pb-4">
        <div className="mb-1.5 flex items-center justify-between text-[11px]">
          <span className="font-semibold text-[var(--ink-soft)]">
            {doneCount}/{total} agents done
          </span>
          <span className="font-bold tabular-nums text-[var(--ink-soft)]">{progress}%</span>
        </div>
        <div className="h-2.5 w-full overflow-hidden rounded-full bg-[var(--bg-sunken)]">
          <div
            className={`h-full rounded-full transition-all duration-700 ${barColor} ${
              phase === "running" ? "relative overflow-hidden" : ""
            }`}
            style={{ width: `${Math.max(progress, phase === "running" ? 4 : 0)}%` }}
          >
            {phase === "running" && <span className="qa-scan absolute inset-y-0 w-1/3 bg-white/40" />}
          </div>
        </div>
        {blockedStage && (
          <p className="mt-2 text-xs text-[var(--bad)]">
            ✕ Stopped at <span className="font-bold">{LABELS[blockedStage].name}</span> — fix the
            input below and resume.
          </p>
        )}
        {log.length === 0 && running && (
          <p className="mt-2 text-xs text-[var(--ink-faint)]">Warming up the agent chain…</p>
        )}
      </div>
    </div>
  );
}

function TrackLegend({ stageState }: { stageState: (s: Stage) => string }) {
  const anyRunning = STAGES.some((s) => stageState(s) === "running");
  const anyFailed = STAGES.some((s) => stageState(s) === "blocked");
  return (
    <div className="flex flex-wrap items-center gap-3 text-[10px] font-semibold uppercase tracking-wide text-[var(--ink-faint)]">
      <span className="flex items-center gap-1.5">
        <span className="flex h-3 w-3 items-center justify-center rounded-full bg-[var(--ok)] text-[7px] text-white">✓</span> done
      </span>
      {anyRunning && (
        <span className="flex items-center gap-1.5">
          <span className="relative flex h-3 w-3">
            <span className="qa-sonar absolute inline-flex h-full w-full rounded-full bg-[var(--accent)] opacity-60" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-[var(--accent)]" />
          </span> running
        </span>
      )}
      {anyFailed && (
        <span className="flex items-center gap-1.5">
          <span className="flex h-3 w-3 items-center justify-center rounded-full bg-[var(--bad)] text-[7px] text-white">✕</span> failed
        </span>
      )}
      <span className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-full border border-dashed border-[var(--line-strong)]" /> optional
      </span>
    </div>
  );
}

/* --------------------------------- track --------------------------------- */

function TrackSegment({
  stage,
  index,
  total,
  state,
  running,
}: {
  stage: Stage;
  index: number;
  total: number;
  state: string;
  running: boolean;
}) {
  const isDone = DONE.has(state);
  const isRunning = state === "running";
  const isBlocked = state === "blocked";
  const isAwaiting = state === "awaiting_approval";
  const isPending = PENDING.has(state);
  const isVisual = stage === "visual";

  return (
    <div className="flex items-center">
      {/* Node */}
      <div className="flex w-[104px] flex-col items-center px-1">
        <div className="relative">
          {/* status ring */}
          <div
            className={`flex h-14 w-14 items-center justify-center rounded-2xl border-2 text-xl transition-all duration-500 ${
              isDone
                ? "border-[var(--ok)] bg-[var(--ok)]/10 shadow-[0_0_0_3px_rgba(47,125,79,0.12)]"
                : isRunning
                  ? "border-[var(--accent)] bg-[var(--accent-soft)] shadow-[0_0_0_3px_rgba(193,87,58,0.15)]"
                  : isBlocked
                    ? "border-[var(--bad)] bg-[var(--bad)]/10 shadow-[0_0_0_3px_rgba(185,28,28,0.12)]"
                    : isAwaiting
                      ? "border-[var(--warn)] bg-[var(--warn)]/10"
                      : isVisual
                        ? "border-dashed border-[var(--line-strong)] bg-[var(--bg-sunken)]/40"
                        : "border-[var(--line)] bg-[var(--bg-sunken)]/50"
            }`}
          >
            <span className={isPending ? "opacity-45 grayscale-[0.4]" : ""}>{LABELS[stage].icon}</span>

            {/* running sonar */}
            {isRunning && (
              <span className="pointer-events-none absolute inset-0 flex items-center justify-center">
                <span className="qa-sonar absolute h-14 w-14 rounded-2xl bg-[var(--accent)] opacity-30" />
              </span>
            )}
            {isDone && (
              <span className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border-2 border-[var(--bg-elev)] bg-[var(--ok)] text-[10px] font-black text-white shadow">
                ✓
              </span>
            )}
            {isBlocked && (
              <span className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border-2 border-[var(--bg-elev)] bg-[var(--bad)] text-[10px] font-black text-white shadow">
                ✕
              </span>
            )}
          </div>
        </div>

        <p className={`mt-2 text-center text-[11px] font-bold leading-tight ${isPending ? "text-[var(--ink-faint)]" : "text-[var(--ink)]"}`}>
          {LABELS[stage].name}
        </p>
        <p className="mt-0.5 h-4 text-center text-[9px] leading-tight text-[var(--ink-faint)]">
          {isRunning ? (
            <span className="font-bold uppercase tracking-wide text-[var(--accent-strong)]">working…</span>
          ) : isBlocked ? (
            <span className="font-bold uppercase tracking-wide text-[var(--bad)]">failed</span>
          ) : isDone ? (
            "done"
          ) : isVisual ? (
            "optional"
          ) : (
            LABELS[stage].desc
          )}
        </p>

        <span
          className={`mt-1 rounded-full px-2 py-0.5 text-[9px] font-bold tabular-nums ${
            isDone
              ? "bg-[var(--ok)]/15 text-[var(--ok)]"
              : isRunning
                ? "bg-[var(--accent)]/15 text-[var(--accent-strong)]"
                : isBlocked
                  ? "bg-[var(--bad)]/15 text-[var(--bad)]"
                  : "bg-[var(--bg-sunken)] text-[var(--ink-faint)]"
          }`}
        >
          {String(index + 1).padStart(2, "0")}
        </span>
      </div>

      {/* Connector to next */}
      {index < total - 1 && <Connector state={state} nextState={stateOfNext(index, total, stage)} />}
    </div>
  );
}

/** tiny helper — we don't have next stage state here, so connector derives color from current segment. */
function stateOfNext(_index: number, _total: number, _stage: Stage): string {
  return "";
}

function Connector({ state, nextState }: { state: string; nextState: string }) {
  void nextState;
  const done = DONE.has(state);
  const blocked = state === "blocked";
  const runningNow = state === "running";
  return (
    <div className="mx-1 flex w-7 shrink-0 items-center pb-7">
      <div
        className={`h-1 w-full rounded-full ${
          blocked
            ? "bg-[var(--bad)]"
            : done || runningNow
              ? "qa-flow-line text-[var(--ok)] bg-[var(--ok)]"
              : "bg-[var(--line)]"
        }`}
        style={done || runningNow ? { backgroundImage: undefined } : undefined}
      />
      <svg className="-ml-1.5 h-3 w-3 shrink-0" viewBox="0 0 12 12" aria-hidden>
        <path
          d="M0 6h9M6 2l4 4-4 4"
          fill="none"
          stroke={blocked ? "var(--bad)" : done || runningNow ? "var(--ok)" : "var(--line-strong)"}
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

function ActivityStrip({ log, currentStage }: { log: LogEntry[]; currentStage: Stage | null }) {
  const recent = log.slice(-3).reverse();
  return (
    <div className="qa-rise flex items-start gap-3 overflow-hidden rounded-2xl border border-[var(--accent)]/25 bg-gradient-to-r from-[var(--accent-soft)]/70 via-[var(--bg-elev)] to-[var(--bg-elev)] px-4 py-3">
      <span className="relative mt-1 flex h-3 w-3 shrink-0">
        <span className="qa-sonar absolute inline-flex h-full w-full rounded-full bg-[var(--accent)]" />
        <span className="relative inline-flex h-3 w-3 rounded-full bg-[var(--accent)]" />
      </span>
      <div className="min-w-0 flex-1">
        {currentStage ? (
          <p className="text-xs font-bold text-[var(--accent-strong)]">
            {LABELS[currentStage].icon} {LABELS[currentStage].name} —{" "}
            {LABELS[currentStage].desc}
          </p>
        ) : (
          <p className="text-xs font-bold text-[var(--accent-strong)]">Agents are executing…</p>
        )}
        {recent.length > 0 && (
          <p className="mt-0.5 truncate text-xs text-[var(--ink-soft)]">
            <span className="mr-1 text-[var(--ink-faint)]">
              {new Date(recent[0].created_at).toLocaleTimeString()}
            </span>
            {recent[0].message}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-end gap-0.5 self-center">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--accent)] [animation-delay:-0.2s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--accent)] [animation-delay:-0.1s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--accent)]" />
      </div>
    </div>
  );
}

/* --------------------------------- outputs --------------------------------- */

function StageOutputs({
  stages,
  stageState,
  running,
  started,
  requirement,
  onRequirement,
  overrides,
  onOverride,
  busy,
  onResume,
  defaults,
  artifactCacheKey,
}: {
  stages: Record<string, StageStatus>;
  stageState: (s: Stage) => string;
  running: boolean;
  started: boolean;
  requirement: string;
  onRequirement: (v: string) => void;
  overrides: Record<string, Record<string, string>>;
  onOverride: (s: Stage, key: string, value: string) => void;
  busy: boolean;
  onResume: (s: Stage) => void;
  defaults?: { base_url?: string; runner_url?: string };
  artifactCacheKey: string | null;
}) {
  const visible = STAGES.filter(
    (s) => s !== "visual" && !PENDING.has(stageState(s)),
  );
  const blocked = STAGES.find((s) => stageState(s) === "blocked") ?? null;

  if (!started) {
    return (
      <div className="rounded-2xl border border-dashed bg-[var(--bg-elev)]/60 p-8 text-center">
        <p className="text-3xl">🎬</p>
        <p className="mt-2 text-sm font-semibold text-[var(--ink-soft)]">
          {running ? "Starting the agent chain…" : "Start the pipeline to run the agent chain."}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-bold uppercase tracking-widest text-[var(--ink-faint)]">
          Agent outputs
        </p>
        {visible.length > 0 && (
          <span className="rounded-full bg-[var(--bg-sunken)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[var(--ink-faint)]">
            {visible.length} available
          </span>
        )}
      </div>

      {blocked && (
        <BlockedPanel
          stage={blocked}
          error={stages[blocked]?.error ?? null}
          requirement={requirement}
          onRequirement={onRequirement}
          overrides={overrides}
          onOverride={onOverride}
          busy={busy}
          running={running}
          onResume={() => onResume(blocked)}
          defaults={defaults}
        />
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        {STAGES.map((s) => {
          if (s === "visual") return null;
          const st = stageState(s);
          if (PENDING.has(st)) return null;
          return (
            <StageCard
              key={`${artifactCacheKey}-${s}`}
              stage={s}
              state={st}
              artifactId={stages[s]?.output_artifact_id ?? null}
            />
          );
        })}
      </div>
    </div>
  );
}

function StageCard({
  stage,
  state,
  artifactId,
}: {
  stage: Stage;
  state: string;
  artifactId: string | null;
}) {
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const isRunning = state === "running";
  const isDone = DONE.has(state);
  const isAwaiting = state === "awaiting_approval";

  useEffect(() => {
    if (!artifactId || loaded) return;
    let cancelled = false;
    getArtifact(artifactId)
      .then((a) => {
        if (!cancelled) {
          setPayload(a.payload);
          setLoaded(true);
        }
      })
      .catch(() => {
        if (!cancelled) setArtifactError("Could not load output");
      });
    return () => {
      cancelled = true;
    };
  }, [artifactId, loaded]);

  const summary = stageSummary(stage, payload);
  const statusTone = isDone
    ? "border-[var(--ok)]/40 bg-[var(--ok)]/[0.04]"
    : isAwaiting
      ? "border-[var(--warn)]/40 bg-[var(--warn)]/[0.04]"
      : isRunning
        ? "border-[var(--accent)]/40 bg-[var(--accent)]/[0.04]"
        : "border bg-[var(--bg-elev)]";

  return (
    <div className={`qa-rise overflow-hidden rounded-2xl border shadow-sm ${statusTone}`}>
      <div className="flex items-start justify-between gap-3 p-4">
        <div className="flex items-start gap-3">
          <span
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-lg ${
              isDone
                ? "bg-[var(--ok)]/15"
                : isAwaiting
                  ? "bg-[var(--warn)]/15"
                  : isRunning
                    ? "bg-[var(--accent)]/15"
                    : "bg-[var(--bg-sunken)]"
            }`}
          >
            {LABELS[stage].icon}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-bold text-[var(--ink)]">{LABELS[stage].name}</p>
              {isDone && (
                <span className="rounded-full bg-[var(--ok)]/15 px-2 py-0.5 text-[9px] font-black uppercase tracking-wide text-[var(--ok)]">
                  complete
                </span>
              )}
              {isAwaiting && (
                <span className="rounded-full bg-[var(--warn)]/15 px-2 py-0.5 text-[9px] font-black uppercase tracking-wide text-[var(--warn)]">
                  review
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-[var(--ink-faint)]">{LABELS[stage].desc}</p>
            {isRunning ? (
              <p className="mt-1.5 flex items-center gap-1.5 text-[11px] font-bold text-[var(--accent-strong)]">
                <span className="relative flex h-2 w-2">
                  <span className="qa-sonar absolute inline-flex h-full w-full rounded-full bg-[var(--accent)]" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--accent)]" />
                </span>
                running
              </p>
            ) : summary ? (
              <p className="mt-1 text-xs font-semibold text-[var(--ink-soft)]">{summary}</p>
            ) : null}
          </div>
        </div>

        {isDone && payload && (
          <button
            onClick={() => setExpanded((e) => !e)}
            className="shrink-0 rounded-lg border border-[var(--line-strong)] px-2.5 py-1.5 text-[11px] font-bold text-[var(--ink-soft)] transition hover:bg-[var(--bg-hover)]"
          >
            {expanded ? "Hide JSON" : "JSON"}
          </button>
        )}
      </div>

      {isDone && expanded && payload && (
        <div className="border-t border-[var(--line)]/70 px-4 py-3">
          <pre className="max-h-72 overflow-auto rounded-xl bg-[#141210] p-3 font-mono text-[11px] leading-relaxed text-[#e7e2d8]">
            {JSON.stringify(payload, null, 2)}
          </pre>
        </div>
      )}
      {isDone && artifactError && (
        <p className="px-4 pb-3 text-xs text-[var(--bad)]">✗ {artifactError}</p>
      )}

      {stage === "codegen" && isDone && payload && (
        <div className="border-t border-[var(--line)]/70 px-4 py-3">
          <GitHubPusher files={githubFilesFromCodegen(payload)} defaultPrefix="qa-one/suites" buttonLabel="Push suite" />
        </div>
      )}
      {stage === "release" && isDone && payload && <ReleaseSummary payload={payload} />}
    </div>
  );
}

function ReleaseSummary({ payload }: { payload: Record<string, unknown> }) {
  const p = payload as { verdict?: string; reason?: string };
  const go = p.verdict === "GO";
  return (
    <div className="border-t border-[var(--line)]/70 px-4 py-3">
      <div
        className={`flex items-center justify-between gap-3 rounded-xl border px-4 py-3 ${
          go ? "border-[var(--ok)]/40 bg-[var(--ok)]/10" : "border-[var(--bad)]/40 bg-[var(--bad)]/10"
        }`}
      >
        <div className="flex items-center gap-3">
          <span
            className={`flex h-10 w-10 items-center justify-center rounded-full text-lg font-black text-white ${
              go ? "bg-[var(--ok)]" : "bg-[var(--bad)]"
            }`}
          >
            {go ? "GO" : "NO-GO"}
          </span>
          <div>
            <p className={`text-sm font-black uppercase tracking-wide ${go ? "text-[var(--ok)]" : "text-[var(--bad)]"}`}>
              {p.verdict ?? "NO_GO"}
            </p>
            {p.reason && <p className="mt-0.5 text-xs text-[var(--ink-soft)]">{p.reason}</p>}
          </div>
        </div>
      </div>
      <div className="mt-2">
        <GitHubPusher files={githubFilesFromRelease(payload)} defaultPrefix="qa-one/reports" buttonLabel="Push report" />
      </div>
    </div>
  );
}

/* ------------------------------- failure panel ------------------------------- */

function BlockedPanel({
  stage,
  error,
  requirement,
  onRequirement,
  overrides,
  onOverride,
  busy,
  running,
  onResume,
  defaults,
}: {
  stage: Stage;
  error: string | null;
  requirement: string;
  onRequirement: (v: string) => void;
  overrides: Record<string, Record<string, string>>;
  onOverride: (s: Stage, key: string, value: string) => void;
  busy: boolean;
  running: boolean;
  onResume: () => void;
  defaults?: { base_url?: string; runner_url?: string };
}) {
  const editableRequirement =
    stage === "doctor" || stage === "test_cases" || stage === "codegen" || stage === "run";
  const fields = STAGE_FIELDS[stage] ?? [];

  return (
    <div className="qa-rise overflow-hidden rounded-2xl border border-[var(--bad)]/40 bg-[var(--bad)]/[0.04] shadow-sm">
      <div className="flex items-start gap-3 border-b border-[var(--bad)]/15 px-5 py-4">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--bad)] text-base font-black text-white shadow">
          ✕
        </span>
        <div className="min-w-0">
          <p className="text-sm font-black text-[var(--bad)]">
            Pipeline stopped at {LABELS[stage].name}
          </p>
          <p className="mt-0.5 text-xs text-[var(--ink-soft)]">
            The chain pauses at a failed agent instead of pushing bad output
            downstream. Fix the input and resume — earlier agents stay done.
          </p>
        </div>
      </div>

      <div className="space-y-4 px-5 py-4">
        {error && (
          <div className="rounded-xl border border-[var(--bad)]/25 bg-[#141210] p-3 font-mono text-[11px] leading-relaxed text-[#f0b9b9]">
            {error}
          </div>
        )}

        {editableRequirement && (
          <div>
            <label className="text-[10px] font-black uppercase tracking-widest text-[var(--ink-faint)]">
              Requirement text
            </label>
            <textarea
              value={requirement}
              onChange={(e) => onRequirement(e.target.value)}
              rows={4}
              className="mt-1.5 w-full resize-y rounded-lg border bg-[var(--bg)] px-3 py-2 font-mono text-xs outline-none transition focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]"
            />
          </div>
        )}

        {fields.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2">
            {fields.map((f) => {
              const envVal = f.envDefaultKey ? defaults?.[f.envDefaultKey] : undefined;
              return (
                <div key={f.key}>
                  <label className="text-[10px] font-black uppercase tracking-widest text-[var(--ink-faint)]">
                    {f.label}
                  </label>
                  <input
                    type={f.type ?? "text"}
                    value={overrides[stage]?.[f.key] ?? ""}
                    onChange={(e) => onOverride(stage, f.key, e.target.value)}
                    placeholder={f.placeholder ?? envVal ?? ""}
                    className="mt-1.5 w-full rounded-lg border bg-[var(--bg)] px-3 py-2 font-mono text-xs outline-none transition focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)]"
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="flex justify-end border-t border-[var(--bad)]/15 bg-[var(--bg-elev)]/50 px-5 py-3">
        <button
          onClick={onResume}
          disabled={busy || running}
          className="inline-flex items-center gap-2 rounded-lg bg-[var(--accent)] px-5 py-2 text-sm font-bold text-[#fdfaf4] shadow-sm transition hover:bg-[var(--accent-strong)] disabled:opacity-50"
        >
          {busy ? "Resuming…" : "▶ Resume from here"}
        </button>
      </div>
    </div>
  );
}

/* ----------------------------------- log ----------------------------------- */

function PipelineLog({
  logRef,
  log,
  running,
}: {
  logRef: React.RefObject<HTMLDivElement | null>;
  log: LogEntry[];
  running: boolean;
}) {
  const levelColor = (level: string) => {
    if (level === "error") return "text-[#f0b9b9]";
    if (level === "success") return "text-[#8fd0a8]";
    if (level === "warn") return "text-[#e5c07b]";
    return "text-[#b9b2a6]";
  };

  return (
    <div className="qa-rise overflow-hidden rounded-2xl border bg-[var(--bg-elev)] shadow-sm">
      <div className="flex items-center justify-between border-b border-[var(--line)] bg-[#141210] px-4 py-2.5">
        <p className="flex items-center gap-2 text-[11px] font-black uppercase tracking-widest text-[#8a8378]">
          <span className="flex gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-[#f0574f]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#e5c07b]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#8fd0a8]" />
          </span>
          Run log
        </p>
        {running && (
          <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-[#c1573a]">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--accent)]" />
            streaming
          </span>
        )}
      </div>
      <div
        ref={logRef}
        className="h-72 overflow-auto bg-[#141210] px-4 py-3 font-mono text-[11px] leading-relaxed"
      >
        {log.length === 0 && (
          <p className="text-[#8a8378]">No events yet — start the pipeline.</p>
        )}
        {log.map((entry, i) => {
          const ts = new Date(entry.created_at).toLocaleTimeString();
          const last = i === log.length - 1 && running;
          return (
            <div
              key={entry.id}
              className={`flex gap-2 whitespace-pre-wrap py-0.5 ${last ? "text-[#fdfaf4]" : ""} ${!last ? "opacity-90" : ""}`}
            >
              <span className="shrink-0 text-[#5c5649]">{ts}</span>
              {entry.stage && (
                <span className="shrink-0 rounded bg-white/5 px-1.5 text-[#8a8378]">{entry.stage}</span>
              )}
              <span className={levelColor(entry.level)}>{entry.message}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
