"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { ArtifactView } from "@/components/artifact-view";
import { Badge, type BadgeTone } from "@/components/badge";
import { useEngineCatalog } from "@/components/engine-catalog-provider";
import { GitHubPusher } from "@/components/github-pusher";
import { JiraIssueFetcher } from "@/components/jira-issue-fetcher";
import { Icon, type IconName } from "@/lib/icons";
import { engineDescription, engineName } from "@/lib/engine-catalog";
import { CHAIN_STAGES, CHECK_STAGES, resumeTarget, stageDef } from "@/lib/stages";
import type { StageId } from "@/lib/stages";
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
 * The flagship pipeline: a requirement flows through a chain of AI agents
 * (intake → doctor → test cases → codegen → run → triage → release)
 * automatically, each agent's output feeding the next. The page polls a status
 * endpoint so the rows update live.
 *
 * The page is a run monitor and answers four questions, in order of urgency:
 *
 *   where am I?           → the run list and the progress bar
 *   what's happening now? → the running agent, with live elapsed time
 *   what did I get?       → each agent's summary, expandable to full output
 *   why did it stop?      → the failed agent's row, with editable input + resume
 *
 * A raw event log is deliberately NOT one of these. Everything it carried is
 * already expressed at higher fidelity by one of the four, so a permanently
 * visible log beside them would be the same information twice. The ordered
 * trail still has forensic value, so it survives as a collapsed "Event trail".
 */

// Stage ids and engine wiring come from lib/stages; the labels come from the
// engine catalog. Nothing here names a stage.
type Stage = StageId;
type ChainStage = StageId;

/** The engine behind a stage, used to look its name up in the catalog. */
function engineFor(stage: string): string {
  return stageDef(stage)?.engine ?? stage;
}

/** Stage ids in execution order — what the tracker and the run list iterate. */
const CHAIN_IDS: ChainStage[] = CHAIN_STAGES.map((s) => s.stage);

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
  intake: [{ key: "source", label: "Source", placeholder: "text | url | jira | github | confluence | pdf" }],
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
        const d = payload.diagnosis as
          | { quality_score?: number; findings?: unknown[] }
          | undefined;
        if (d?.quality_score == null) return "Check complete";
        // The findings count is the useful half of this: a bare score is a
        // number with no action attached.
        const n = d.findings?.length ?? 0;
        return `Score ${d.quality_score}/100 · ${n} finding${n === 1 ? "" : "s"}`;
      }
      case "test_plan": {
        const total = (payload.summary as { total_criteria?: number } | undefined)?.total_criteria;
        return total != null ? `${total} criteria planned` : "Plan ready";
      }
      case "eval_plan":
      case "eval_cases":
      case "eval_code": {
        const s = payload.summary as { passed?: number; total?: number } | undefined;
        const total = s?.total ?? 0;
        // Zero metrics means the gate measured nothing — reporting "all 0
        // metrics passed" would read as success when it is a wiring failure.
        if (total === 0) return "no metrics ran";
        const passed = s?.passed ?? 0;
        const failed = total - passed;
        return failed > 0
          ? `${passed}/${total} metrics passed · ${failed} failed`
          : `all ${total} metrics passed`;
      }
      case "test_cases": {
        const c = payload.count as number | undefined;
        return c != null ? `${c} cases · traceable` : "Cases ready";
      }
      case "codegen": {
        const files = (payload.files as { tests?: unknown[] } | undefined)?.tests;
        return files ? `Suite with ${files.length} file(s)` : "Suite generated";
      }
      case "run": {
        const results = (payload.results as { status?: string }[] | undefined) ?? [];
        const passed = results.filter((r) => r.status === "passed").length;
        const attempts = (payload.attempts as unknown[] | undefined) ?? [];
        const fixed = (payload.auto_fixed as unknown[] | undefined) ?? [];
        const base = results.length
          ? `${passed}/${results.length} passed`
          : "Run complete";
        if (fixed.length) return `${base} · ${fixed.length} auto-repaired`;
        if (attempts.length > 1) return `${base} · ${attempts.length} attempts`;
        return base;
      }
      case "triage": {
        const tf = payload.total_failures as number | undefined;
        return tf != null ? `${tf} failure(s) clustered` : "Triage ready";
      }
      case "release": {
        const v = payload.verdict as string | undefined;
        const conf = (payload.confidence as { score?: number } | undefined)?.score;
        if (!v) return "Decision ready";
        return conf != null ? `${v} · ${conf}% confidence` : `Verdict ${v}`;
      }
      default:
        return "";
    }
  } catch {
    return "";
  }
}

/* ------------------------------ time helpers ------------------------------ */

/** Compact duration: 0.8s, 12s, 4m 05s. */
function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  if (ms < 1000) return `${(ms / 1000).toFixed(1)}s`;
  const totalSec = Math.round(ms / 1000);
  if (totalSec < 60) return `${totalSec}s`;
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}m ${String(sec).padStart(2, "0")}s`;
}

/** Fixed to the minute — exact seconds matter while something is running, not
 * for a list of things that already finished. */
function formatClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Ticks once a second while `active`, so a running stage shows real elapsed
 * time. This is what a log's timestamps used to imply, said directly. */
function useElapsed(startedAt: string | null | undefined, active: boolean): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active || !startedAt) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active, startedAt]);
  if (!startedAt) return null;
  const start = new Date(startedAt).getTime();
  if (Number.isNaN(start)) return null;
  return (active ? now : Date.now()) - start;
}

/**
 * `useSearchParams` is a dynamic API: it cannot be resolved during the static
 * prerender Next runs at build time, so any component that calls it must sit
 * behind a Suspense boundary or the page fails to export. The boundary also
 * gives the route a real loading state on first paint.
 */
export default function PipelinePage() {
  return (
    <Suspense fallback={<PipelineLoading />}>
      <PipelinePageInner />
    </Suspense>
  );
}

function PipelineLoading() {
  return (
    <div className="mx-auto max-w-[900px]">
      <div className="mb-4 h-6 w-40 animate-pulse rounded-[6px] bg-[var(--bg-elev)]" />
      <div className="mb-7 h-9 w-64 animate-pulse rounded-[8px] bg-[var(--bg-elev)]" />
      <div className="space-y-5">
        <div className="h-24 animate-pulse rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)]" />
        <div className="h-28 animate-pulse rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)]" />
      </div>
    </div>
  );
}

function PipelinePageInner() {
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const started = CHAIN_IDS.some((s) => stageState(s) !== "not_started");
  const doneCount = CHAIN_IDS.filter((s) => DONE.has(stageState(s))).length;
  const blockedStage = CHAIN_IDS.find((s) => stageState(s) === "blocked") ?? null;
  const appUrl = String(status?.inputs?.app_url ?? "");
  const progress = Math.round((doneCount / CHAIN_IDS.length) * 100);
  const phase = running ? "running" : blockedStage ? "failed" : doneCount === CHAIN_IDS.length ? "complete" : started ? "paused" : "idle";

  return (
    <div className="mx-auto max-w-[900px]">
      <div className="mb-4 flex flex-wrap gap-2">
        <Badge tone="accent" dot>
          Flagship tool
        </Badge>
        {projectId && <PhaseBadge phase={phase} />}
      </div>

      <h1 className="text-[34px] font-semibold leading-tight text-[var(--ink)]">
        AI QA Pipeline
      </h1>
      <p className="mb-7 mt-2.5 max-w-[62ch] text-[14.5px] leading-relaxed text-[var(--ink-soft)]">
        One requirement goes in — seven agents run end to end, streaming live.
        If an agent fails, the run stops there so you can fix its input and
        resume.
      </p>

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
        <div>
          <ProjectCard
            name={projectName || "QA project"}
            appUrl={appUrl}
          />

          <StageTracker
            stages={CHAIN_IDS}
            stageState={stageState}
            doneCount={doneCount}
            progress={progress}
            running={running}
            busy={busy}
            onCancel={cancelRun}
          />

          {error && (
            <div className="qa-rise mb-6 flex items-start gap-2 rounded-[var(--r-md)] border border-[var(--bad)]/30 bg-[var(--bad-soft)] p-3 text-[13px] text-[var(--bad)]">
              <Icon name="alert" size={15} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* The run itself: one ordered row per agent. This is the only
              representation of the chain — status, timing and output live
              together, in execution order. */}
          <RunList
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

          <RunLegend />

          {/* Forensics, not a monitor: the ordered event trail stays available
              but collapsed, and only advertises itself when it has entries. */}
          {log.length > 0 && (
            <div className="mt-6">
              <EventTrail log={log} />
            </div>
          )}
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
    <div className="grid gap-4 lg:grid-cols-[1fr_1.5fr]">
      <div className="rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)] px-5 py-5">
        <p className="field-label mb-2.5">project name</p>
        <input
          value={name}
          onChange={(e) => onName(e.target.value)}
          placeholder="My QA project"
          className="w-full rounded-[var(--r-md)] border border-[var(--line-strong)] bg-[var(--bg)] px-3 py-2.5 text-[13px] outline-none transition-colors placeholder:text-[var(--ink-faint)] focus:border-[var(--accent)]"
        />
        <p className="mt-3 text-[12px] leading-relaxed text-[var(--ink-faint)]">
          Each run is stored under this project — reopen it any time from the
          dashboard to watch the full chain.
        </p>
      </div>

      <div className="rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)] px-5 py-5">
        <p className="field-label mb-2.5">requirement</p>
        <textarea
          value={requirement}
          onChange={(e) => onRequirement(e.target.value)}
          rows={7}
          className="w-full resize-y rounded-[var(--r-md)] border border-[var(--line-strong)] bg-[var(--bg)] px-3 py-2.5 text-[12px] leading-relaxed outline-none transition-colors placeholder:text-[var(--ink-faint)] focus:border-[var(--accent)]"
          style={{ fontFamily: "var(--font-mono)" }}
          placeholder={"Paste a requirement, Jira story, PRD…\n\nTip: include the app URL (e.g. https://www.saucedemo.com) — the pipeline will target it automatically."}
        />
        {detectUrl(requirement) ? (
          <div className="mt-2.5 flex items-center gap-2 rounded-[var(--r-md)] border border-[var(--ok)]/30 bg-[var(--ok-soft)] px-3 py-2">
            <Icon name="link" size={13} className="shrink-0 text-[var(--ok)]" />
            <span className="text-[12px] text-[var(--ink-soft)]">
              App under test:{" "}
              <span
                className="font-semibold text-[var(--ok)]"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {detectUrl(requirement)}
              </span>
            </span>
          </div>
        ) : (
          <p className="mt-2.5 text-[12px] leading-relaxed text-[var(--ink-faint)]">
            No URL detected yet — the app under test falls back to the
            configured default. Paste a URL in the requirement to target a
            specific site.
          </p>
        )}
        <div className="mt-3">
          <JiraIssueFetcher onFetched={(_issue, text) => onRequirement(text)} />
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] pt-4">
          <p className="text-[12px] text-[var(--ink-faint)]">
            Leave empty to load the demo requirement fixture.
          </p>
          <button
            onClick={onStart}
            disabled={busy}
            className="press inline-flex shrink-0 items-center gap-2 rounded-[var(--r-md)] bg-[var(--accent)] px-4 py-2.5 text-[13px] font-semibold text-[var(--accent-ink)] transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
          >
            {busy ? "Creating…" : "Start pipeline"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------ run chrome ------------------------------- */

function PhaseBadge({ phase }: { phase: string }) {
  const map: Record<string, { label: string; tone: BadgeTone; pulse?: boolean }> = {
    running: { label: "Running", tone: "accent", pulse: true },
    failed: { label: "Failed", tone: "bad" },
    complete: { label: "Complete", tone: "ok" },
    paused: { label: "Paused", tone: "warn" },
    idle: { label: "Idle", tone: "neutral" },
  };
  const m = map[phase] ?? map.idle;
  return (
    <Badge tone={m.tone} dot>
      <span className={m.pulse ? "qa-pulse" : undefined}>{m.label}</span>
    </Badge>
  );
}

/** Who this run belongs to and what it is pointed at. */
function ProjectCard({ name, appUrl }: { name: string; appUrl: string }) {
  return (
    <div className="mb-5 rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)] px-5 py-4">
      <p className="field-label mb-2">project</p>
      <p
        className="text-[20px] font-semibold leading-tight text-[var(--ink)]"
        style={{ fontFamily: "var(--font-display)" }}
      >
        {name}
      </p>
      {appUrl && (
        <p className="mt-1.5 flex items-center gap-2 text-[12.5px] text-[var(--ink-soft)]">
          <Icon name="link" size={13} className="shrink-0 text-[var(--ink-faint)]" />
          <span
            className="truncate border-b border-dotted border-[var(--ink-faint)]"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {appUrl}
          </span>
        </p>
      )}
    </div>
  );
}

/**
 * Position in the run as a row of segments — one per agent, so the bar is a
 * map as well as a progress reading. The running segment animates an
 * indeterminate sweep (background-position, so it never touches layout).
 */
function StageTracker({
  stages,
  stageState,
  doneCount,
  progress,
  running,
  busy,
  onCancel,
}: {
  stages: readonly ChainStage[];
  stageState: (s: Stage) => string;
  doneCount: number;
  progress: number;
  running: boolean;
  busy: boolean;
  onCancel: () => void;
}) {
  const catalog = useEngineCatalog();
  return (
    <div className="mb-6 rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)] px-5 pb-4 pt-5">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[13.5px] text-[var(--ink-soft)]">
          <b className="font-semibold text-[var(--ink)]">
            {doneCount} of {stages.length}
          </b>{" "}
          agents complete
        </p>
        <div className="flex items-center gap-3">
          <span
            className="text-[13px] font-semibold text-[var(--ok)]"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {progress}%
          </span>
          {running && (
            <button
              onClick={onCancel}
              disabled={busy}
              className="press inline-flex items-center gap-1.5 rounded-[var(--r-sm)] border border-[var(--bad)]/35 px-2.5 py-1 text-[11.5px] font-semibold text-[var(--bad)] transition-colors hover:bg-[var(--bad-soft)] disabled:opacity-50"
            >
              <Icon name="close" size={11} />
              Stop
            </button>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1">
        {stages.map((s) => {
          const state = stageState(s);
          const done = DONE.has(state);
          const isRunning = state === "running";
          const isBlocked = state === "blocked";
          return (
            <span
              key={s}
              title={`${engineName(catalog, engineFor(s))} — ${state.replace("_", " ")}`}
              className={`h-1.5 flex-1 rounded-[3px] ${
                done
                  ? "bg-[var(--ok)]"
                  : isBlocked
                    ? "bg-[var(--bad)]"
                    : isRunning
                      ? "bg-[var(--warn)]"
                      : "bg-[var(--bg-sunken)]"
              }`}
            >
              {isRunning && (
                <span
                  aria-hidden
                  className="block h-full w-full rounded-[3px]"
                  style={{
                    backgroundImage:
                      "linear-gradient(90deg, var(--warn) 0%, var(--warn) 55%, rgba(245,184,76,0.15) 55%)",
                    backgroundSize: "200% 100%",
                    animation: "qa-indeterminate 1.4s linear infinite",
                  }}
                />
              )}
            </span>
          );
        })}
      </div>

      <div className="mt-2.5 flex items-center">
        {stages.map((s, i) => (
          <span
            key={s}
            className={`flex-1 text-center text-[10px] leading-tight text-[var(--ink-faint)] ${
              i === 0 ? "text-left" : i === stages.length - 1 ? "text-right" : ""
            }`}
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {engineName(catalog, engineFor(s))}
          </span>
        ))}
      </div>
    </div>
  );
}

function RunLegend() {
  const items = [
    { color: "var(--ok)", label: "Complete" },
    { color: "var(--warn)", label: "Running" },
    { color: "var(--bad)", label: "Failed — stops the run" },
    { color: "var(--pending)", label: "Pending" },
  ];
  return (
    <div className="mt-8 flex flex-wrap gap-6 border-t border-[var(--line)] pt-5">
      {items.map((it) => (
        <span
          key={it.label}
          className="flex items-center gap-2 text-[12px] text-[var(--ink-faint)]"
        >
          <span
            aria-hidden
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ background: it.color }}
          />
          {it.label}
        </span>
      ))}
    </div>
  );
}

/* ------------------------------- the run list ------------------------------ */

/**
 * One ordered row per agent. This replaces what used to be three separate
 * views of the same seven stages (a horizontal chain, a two-column card grid,
 * and a raw log). A pipeline is strictly sequential, so the honest layout is a
 * single vertical list read top to bottom, where each row carries its own
 * status, timing, output summary, and — when it fails — the controls to fix and
 * resume it in place.
 */

type RowTone = "ok" | "accent" | "bad" | "warn" | "muted";

function rowVisual(state: string): { label: string; tone: RowTone } {
  if (DONE.has(state)) return { label: "complete", tone: "ok" };
  if (state === "running") return { label: "running", tone: "warn" };
  if (state === "blocked") return { label: "failed", tone: "bad" };
  if (state === "awaiting_approval") return { label: "review", tone: "warn" };
  return { label: "pending", tone: "muted" };
}

/** The circular node on the spine, one per agent. Running gets a spinner
 * rather than a glyph, so motion alone communicates "in progress". */
const NODE_TONE: Record<RowTone, string> = {
  ok: "border-[var(--ok)]/40 bg-[var(--ok-soft)] text-[var(--ok)]",
  accent: "border-[var(--accent-line)] bg-[var(--accent-soft)] text-[var(--accent)]",
  bad: "border-[var(--bad)]/40 bg-[var(--bad-soft)] text-[var(--bad)]",
  warn: "border-[var(--warn)]/40 bg-[var(--warn-soft)] text-[var(--warn)]",
  muted: "border-[var(--line-strong)] bg-[var(--bg-sunken)] text-[var(--ink-faint)]",
};

const PILL_TONE: Record<RowTone, string> = {
  ok: "bg-[var(--ok-soft)] text-[var(--ok)]",
  accent: "bg-[var(--accent-soft)] text-[var(--accent)]",
  bad: "bg-[var(--bad-soft)] text-[var(--bad)]",
  warn: "bg-[var(--warn-soft)] text-[var(--warn)]",
  muted: "bg-[var(--pending-soft)] text-[var(--ink-faint)]",
};

function StatusPill({ tone, label }: { tone: RowTone; label: string }) {
  return (
    <span
      className={`rounded-[5px] px-2 py-[3px] text-[10.5px] font-semibold ${PILL_TONE[tone]}`}
      style={{ fontFamily: "var(--font-mono)" }}
    >
      {label}
    </span>
  );
}

function NodeGlyph({ tone, running }: { tone: RowTone; running: boolean }) {
  if (running) {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" className="qa-spin" aria-hidden>
        <circle
          cx="8"
          cy="8"
          r="6"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeDasharray="28"
          strokeDashoffset="10"
        />
      </svg>
    );
  }
  if (tone === "ok") return <Icon name="check" size={17} strokeWidth={2} />;
  if (tone === "bad") return <Icon name="close" size={16} strokeWidth={2} />;
  return null;
}

/** How long this agent took, or has been taking. A running row ticks. */
function StageTiming({
  startedAt,
  updatedAt,
  active,
}: {
  startedAt?: string | null;
  updatedAt?: string | null;
  active: boolean;
}) {
  const elapsed = useElapsed(startedAt, active);
  if (elapsed == null) return null;
  const done = !active && updatedAt && startedAt;
  const ms = done ? new Date(updatedAt).getTime() - new Date(startedAt).getTime() : elapsed;
  return (
    <span
      className="shrink-0 text-[12px] tabular-nums text-[var(--ink-faint)]"
      style={{ fontFamily: "var(--font-mono)" }}
      title={startedAt ? `Started ${formatClock(startedAt)}` : undefined}
    >
      {formatDuration(ms)}
    </span>
  );
}

function RunList({
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
  onResume: (s: ChainStage) => void;
  defaults?: { base_url?: string; runner_url?: string };
  artifactCacheKey: string | null;
}) {
  const completed = CHAIN_IDS.filter((s) => DONE.has(stageState(s))).length;

  if (!started) {
    return (
      <div className="rounded-[var(--r-lg)] border border-dashed border-[var(--line-strong)] px-6 py-10 text-center">
        <Icon name="pipeline" size={24} className="mx-auto block text-[var(--ink-faint)]" />
        <p className="mt-2.5 text-[13px] font-semibold text-[var(--ink-soft)]">
          {running ? "Starting the agent chain…" : "The agent chain has not run yet."}
        </p>
      </div>
    );
  }

  return (
    <section aria-label="Agent run">
      <div className="mb-3.5 flex items-baseline justify-between">
        <h2
          className="text-[15px] font-semibold text-[var(--ink)]"
          style={{ fontFamily: "var(--font-display)" }}
        >
          Agents
        </h2>
        <span
          className="text-[12px] tabular-nums text-[var(--ink-faint)]"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          {completed} / {CHAIN_IDS.length} complete
        </span>
      </div>

      {/* Each agent is its own card on a shared vertical spine, so the list
          reads as one chain rather than a stack of unrelated panels. */}
      <ol>
        {CHAIN_IDS.map((s, i) => (
          <RunRow
            key={`${artifactCacheKey}-${s}`}
            stage={s}
            ordinal={i + 1}
            isLast={i === CHAIN_IDS.length - 1}
            state={stageState(s)}
            startedAt={stages[s]?.started_at}
            updatedAt={stages[s]?.updated_at}
            artifactId={stages[s]?.output_artifact_id ?? null}
            error={stages[s]?.error ?? null}
            requirement={requirement}
            onRequirement={onRequirement}
            overrides={overrides}
            onOverride={onOverride}
            busy={busy}
            running={running}
            onResume={() => onResume(resumeTarget(s))}
            defaults={defaults}
          />
        ))}
      </ol>
    </section>
  );
}

function RunRow({
  stage,
  ordinal,
  isLast,
  state,
  startedAt,
  updatedAt,
  artifactId,
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
  stage: ChainStage;
  ordinal: number;
  isLast: boolean;
  state: string;
  startedAt?: string | null;
  updatedAt?: string | null;
  artifactId: string | null;
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
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const catalog = useEngineCatalog();

  const { label, tone } = rowVisual(state);
  const isDone = DONE.has(state);
  const isRunning = state === "running";
  const isBlocked = state === "blocked";

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
        if (!cancelled) setArtifactError("Could not load this agent's output");
      });
    return () => {
      cancelled = true;
    };
  }, [artifactId, loaded]);

  const summary = stageSummary(stage, payload);
  // A failed gate is fixed by editing the input of the stage it checks, so the
  // requirement editor appears on the gates too.
  const canEditRequirement =
    stage === "doctor" ||
    stage === "test_plan" ||
    stage === "eval_plan" ||
    stage === "test_cases" ||
    stage === "eval_cases" ||
    stage === "codegen" ||
    stage === "run";
  const fields = STAGE_FIELDS[stage] ?? [];
  const isGate = CHECK_STAGES.has(stage);
  const regenerateFrom = isGate
    ? engineName(catalog, engineFor(resumeTarget(stage)))
    : "";
  const stageEngine = engineFor(stage);

  return (
    <li
      className="relative grid grid-cols-[44px_1fr] gap-[18px] pb-[26px] last:pb-0"
      aria-current={isRunning ? "step" : undefined}
    >
      {/* Spine — one continuous line down the chain, hidden after the last
          agent so the list does not trail off into nothing. */}
      {!isLast && (
        <span
          aria-hidden
          className="absolute bottom-[-2px] left-[22px] top-[44px] w-px bg-[var(--line-strong)]"
        />
      )}

      {/* Node */}
      <span
        className={`relative z-10 flex h-11 w-11 items-center justify-center rounded-full border ${NODE_TONE[tone]}`}
      >
        <NodeGlyph tone={tone} running={isRunning} />
      </span>

      {/* Card */}
      <div
        className={`min-w-0 rounded-[var(--r-lg)] border bg-[var(--bg-elev)] px-[18px] py-4 ${
          isBlocked
            ? "border-[var(--bad)]/40"
            : isRunning
              ? "border-[var(--warn)]/35"
              : "border-[var(--line)]"
        }`}
      >
        <div className="mb-1.5 flex flex-wrap items-center gap-2.5">
          <span
            className="text-[11.5px] tabular-nums text-[var(--ink-faint)]"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {String(ordinal).padStart(2, "0")}
          </span>
          <h3
            className={`text-[15.5px] font-semibold ${
              tone === "muted" ? "text-[var(--ink-soft)]" : "text-[var(--ink)]"
            }`}
            style={{ fontFamily: "var(--font-display)" }}
          >
            {engineName(catalog, stageEngine)}
          </h3>
          <StatusPill tone={tone} label={label} />
          <span className="ml-auto">
            <StageTiming startedAt={startedAt} updatedAt={updatedAt} active={isRunning} />
          </span>
        </div>

        <p className="mb-2.5 text-[13px] leading-relaxed text-[var(--ink-soft)]">
          {engineDescription(catalog, stageEngine)}
        </p>

        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* The one fact worth reading at a glance. */}
          {isRunning ? (
            <span className="text-[13px] text-[var(--ink-faint)]">
              Evaluating results…
            </span>
          ) : summary ? (
            <span className="qa-fade text-[13px] text-[var(--ink)]">{summary}</span>
          ) : (
            <span className="text-[13px] text-[var(--ink-faint)]">Waiting</span>
          )}

          {isDone && payload && (
            <button
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
              className="press inline-flex shrink-0 items-center gap-1.5 rounded-[7px] border border-[var(--line-strong)] px-2.5 py-1.5 text-[12.5px] font-semibold text-[var(--ink-soft)] transition-colors hover:border-[var(--accent)] hover:text-[var(--ink)]"
            >
              {expanded ? "Hide output" : "View output"}
              <Icon
                name="arrow"
                size={12}
                className={`transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
              />
            </button>
          )}
        </div>

          {artifactError && (
            <p className="mt-2 flex items-center gap-1.5 text-[12px] text-[var(--bad)]">
              <Icon name="alert" size={12} />
              {artifactError}
            </p>
          )}

          {/* Expanded output. The content stays mounted so the reveal animates
              in both directions; collapsed means height 0, not unmounted, so
              `inert` is what keeps it out of the tab order and a11y tree. */}
          {isDone && payload && (
            <div className="qa-collapse" data-open={expanded}>
              <div>
                <div
                  className="mt-3.5 rounded-[var(--r-md)] border border-[var(--line)] bg-[var(--bg-inset)] p-3.5"
                  inert={!expanded}
                >
                  <ArtifactView payload={payload} />
                </div>
              </div>
            </div>
          )}

          {/* Actions that belong to this agent's result. */}
          {isDone && payload && stage === "codegen" && (
            <div className="mt-3">
              <GitHubPusher
                files={githubFilesFromCodegen(payload)}
                defaultPrefix="qa-one/suites"
                buttonLabel="Push suite"
              />
            </div>
          )}
          {isDone && payload && stage === "release" && <ReleaseSummary payload={payload} />}

          {/* Failure is fixed where it happened: error, the inputs to correct,
              and resume — inline, not in a separate panel elsewhere. */}
          {isBlocked && (
            <div className="mt-3.5 space-y-3 rounded-[var(--r-md)] border border-[var(--bad)]/30 bg-[var(--bg-inset)] p-3.5">
              {error && (
                <div className="rounded-[var(--r-sm)] border border-[var(--bad)]/20 bg-[var(--bad-soft)] p-2.5">
                  <p className="field-label mb-1.5 text-[var(--bad)]">error</p>
                  <p
                    className="text-[11.5px] leading-relaxed text-[var(--ink-soft)]"
                    style={{ fontFamily: "var(--font-mono)" }}
                  >
                    {error}
                  </p>
                </div>
              )}

              {canEditRequirement && (
                <div>
                  <label className="field-label block">requirement text</label>
                  <textarea
                    value={requirement}
                    onChange={(e) => onRequirement(e.target.value)}
                    rows={3}
                    className="mt-1.5 w-full resize-y rounded-[var(--r-sm)] border border-[var(--line-strong)] bg-[var(--bg)] px-2.5 py-2 text-[11.5px] outline-none focus:border-[var(--accent)]"
                    style={{ fontFamily: "var(--font-mono)" }}
                  />
                </div>
              )}

              {fields.length > 0 && (
                <div className="grid gap-3 sm:grid-cols-2">
                  {fields.map((f) => {
                    const envVal = f.envDefaultKey ? defaults?.[f.envDefaultKey] : undefined;
                    // Empty override means "use the resolved default" — the
                    // server filters empty overrides the same way.
                    const effective = overrides[stage]?.[f.key] || envVal || "";
                    return (
                      <div key={f.key}>
                        <label className="field-label flex items-center gap-1.5">
                          {f.label}
                          {f.key === "runner_url" && (
                            <span className="rounded bg-[var(--bg-sunken)] px-1.5 py-px text-[9px] tracking-normal text-[var(--ink-faint)]">
                              internal
                            </span>
                          )}
                        </label>
                        <input
                          type={f.type ?? "text"}
                          value={effective}
                          onChange={(e) => onOverride(stage, f.key, e.target.value)}
                          placeholder={f.placeholder ?? ""}
                          className="mt-1.5 w-full rounded-[var(--r-sm)] border border-[var(--line-strong)] bg-[var(--bg)] px-2.5 py-2 text-[11.5px] outline-none focus:border-[var(--accent)]"
                          style={{ fontFamily: "var(--font-mono)" }}
                        />
                        {f.key === "base_url" && (
                          <p className="mt-1 text-[10.5px] leading-relaxed text-[var(--ink-faint)]">
                            Detected from the requirement&apos;s URL. Change only to retarget.
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] pt-3">
                <p className="text-[11.5px] leading-relaxed text-[var(--ink-faint)]">
                  {isGate
                    ? `This gate failed, so resuming regenerates the ${regenerateFrom} from your edited requirement.`
                    : "Earlier agents stay complete — only this agent and the ones after it rerun."}
                </p>
                <button
                  onClick={onResume}
                  disabled={busy || running}
                  className="press inline-flex shrink-0 items-center gap-1.5 rounded-[var(--r-md)] bg-[var(--accent)] px-3.5 py-2 text-[12.5px] font-semibold text-[var(--accent-ink)] transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
                >
                  <Icon name="runner" size={12} />
                  {busy
                    ? "Resuming…"
                    : isGate
                      ? `Regenerate ${regenerateFrom}`
                      : "Resume from here"}
                </button>
              </div>
            </div>
          )}
      </div>
    </li>
  );
}

/* --------------------------------- outputs --------------------------------- */

/** The release verdict is the conclusion of the run, so it gets its own
 * treatment rather than folding into the generic artifact view. */
function ReleaseSummary({ payload }: { payload: Record<string, unknown> }) {
  const p = payload as { verdict?: string; reason?: string };
  const go = p.verdict === "GO";
  return (
    <div className="mt-3">
      <div
        className={`flex items-center gap-3 rounded-[var(--r-md)] border px-4 py-3 ${
          go ? "border-[var(--ok)]/35 bg-[var(--ok-soft)]" : "border-[var(--bad)]/35 bg-[var(--bad-soft)]"
        }`}
      >
        <span
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[13px] font-black tracking-tight text-white ${
            go ? "bg-[var(--ok)]" : "bg-[var(--bad)]"
          }`}
        >
          {go ? "GO" : "NO-GO"}
        </span>
        <div className="min-w-0">
          <p
            className={`text-[13px] font-semibold ${go ? "text-[var(--ok)]" : "text-[var(--bad)]"}`}
            style={{ fontFamily: "var(--font-display)" }}
          >
            {go ? "Cleared to release" : "Not cleared to release"}
          </p>
          {p.reason && (
            <p className="mt-0.5 text-[12.5px] leading-relaxed text-[var(--ink-soft)]">{p.reason}</p>
          )}
        </div>
      </div>
      <div className="mt-3">
        <GitHubPusher
          files={githubFilesFromRelease(payload)}
          defaultPrefix="qa-one/reports"
          buttonLabel="Push report"
        />
      </div>
    </div>
  );
}

/* -------------------------------- event trail ------------------------------- */

/**
 * The ordered event stream, collapsed at the foot of the page. It exists for
 * forensics — reconstructing exactly what happened and when — not for watching
 * the run. Everything it would tell you at a glance is already on the agent
 * rows above, and the live status line covers "what is happening right now".
 */
function EventTrail({ log }: { log: LogEntry[] }) {
  const levelDot: Record<string, string> = {
    error: "bg-[var(--bad)]",
    success: "bg-[var(--ok)]",
    warn: "bg-[var(--warn)]",
    info: "bg-[var(--ink-faint)]",
  };

  return (
    <details className="overflow-hidden rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)]">
      <summary className="flex cursor-pointer select-none flex-wrap items-center gap-2 px-4 py-2.5 text-[11.5px] font-bold text-[var(--ink-soft)] transition-colors hover:bg-[var(--bg-hover-elev)]">
        <Icon name="arrow" size={12} className="chev" />
        Event trail
        <span className="font-mono text-[11px] font-normal tabular-nums text-[var(--ink-faint)]">
          {log.length} event{log.length === 1 ? "" : "s"}
        </span>
        <span className="ml-auto hidden text-[11px] font-normal text-[var(--ink-faint)] sm:block">
          Timestamped record of the run
        </span>
      </summary>
      <ol className="max-h-80 overflow-auto border-t border-[var(--line)] bg-[var(--bg-inset)] px-4 py-3">
        {log.map((entry) => (
          <li
            key={entry.id}
            className="flex items-baseline gap-2.5 py-[3px] font-mono text-[11px] leading-relaxed"
          >
            <span className="shrink-0 tabular-nums text-[var(--ink-faint)]">
              {new Date(entry.created_at).toLocaleTimeString()}
            </span>
            <span
              aria-hidden
              className={`h-1.5 w-1.5 shrink-0 translate-y-[-1px] rounded-full ${
                levelDot[entry.level] ?? levelDot.info
              }`}
            />
            {entry.stage && (
              <span className="shrink-0 rounded bg-[var(--bg-sunken)] px-1.5 text-[var(--ink-soft)]">
                {entry.stage}
              </span>
            )}
            <span className="text-[var(--ink-soft)]">{entry.message}</span>
          </li>
        ))}
      </ol>
    </details>
  );
}
