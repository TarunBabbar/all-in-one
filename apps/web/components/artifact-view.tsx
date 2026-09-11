"use client";

/* Human-readable artifact renderer.
 *
 * Engine payloads are JSON — that is a storage/API format, not UI. This
 * component detects what kind of artifact it is looking at (release decision,
 * doctor diagnosis, test cases, run results, triage clusters, generated POM
 * framework, intake requirement…) and renders it readably. Unknown shapes get
 * a generic summary. Every view keeps a collapsible "Raw JSON" accordion so no
 * information is lost.
 */

import { useState, type ReactNode } from "react";

import { Icon, type IconName } from "@/lib/icons";

type Unknown = Record<string, unknown>;

function asObj(v: unknown): Unknown | null {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Unknown) : null;
}
function asArr(v: unknown): unknown[] | null {
  return Array.isArray(v) ? v : null;
}
function asStr(v: unknown): string {
  return typeof v === "string" ? v : "";
}
function asNum(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : typeof v === "string" && v !== "" && !Number.isNaN(Number(v)) ? Number(v) : null;
}

/* --------------------------------- atoms --------------------------------- */

type Tone = "ok" | "bad" | "warn" | "accent" | "info" | "neutral";

const TONE_CLASS: Record<Tone, string> = {
  ok: "border-[var(--ok)]/25 bg-[var(--ok-soft)] text-[var(--ok)]",
  bad: "border-[var(--bad)]/25 bg-[var(--bad-soft)] text-[var(--bad)]",
  warn: "border-[var(--warn)]/30 bg-[var(--warn-soft)] text-[var(--warn)]",
  accent: "border-[var(--accent-line)] bg-[var(--accent-soft)] text-[var(--accent-strong)]",
  info: "border-[var(--info)]/25 bg-[var(--info-soft)] text-[var(--info)]",
  neutral: "border-[var(--line)] bg-[var(--bg-sunken)] text-[var(--ink-soft)]",
};

function Chip({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-[5px] border px-2 py-[2px] text-[10.5px] font-medium ${TONE_CLASS[tone]}`}
      style={{ fontFamily: "var(--font-mono)" }}
    >
      {children}
    </span>
  );
}

/**
 * The raw payload is a fallback, not the point of the view. Serializing it on
 * every render is wasted work (these payloads get large, and the pipeline
 * re-renders on every poll), so the JSON is produced only once opened.
 */
function RawJson({ payload }: { payload: Unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="mt-4 overflow-hidden rounded-[var(--r-md)] border border-[var(--line)] bg-[var(--bg-inset)]"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary className="flex cursor-pointer select-none items-center gap-1.5 px-3 py-2 text-[11px] font-bold uppercase tracking-[0.06em] text-[var(--ink-faint)] transition-colors hover:text-[var(--ink-soft)]">
        <Icon
          name="arrow"
          size={12}
          className="chev transition-transform duration-200"
        />
        Raw JSON
      </summary>
      {open && (
        <pre className="qa-fade max-h-80 overflow-auto border-t border-[var(--line)] p-3 font-mono text-[11px] leading-relaxed text-[var(--ink-soft)]">
          {JSON.stringify(payload, null, 2)}
        </pre>
      )}
    </details>
  );
}

function TextBlock({ text, maxH }: { text: string; maxH?: string }) {
  return (
    <div
      className={`whitespace-pre-wrap break-words rounded-[var(--r-md)] border border-[var(--line)] bg-[var(--bg-inset)] p-3 text-[13px] leading-relaxed text-[var(--ink-soft)] ${
        maxH ? "overflow-auto" : ""
      }`}
      style={maxH ? { maxHeight: maxH } : undefined}
    >
      {text || <span className="italic text-[var(--ink-faint)]">(empty)</span>}
    </div>
  );
}

const STAT_TONE: Record<string, string> = {
  ok: "text-[var(--ok)]",
  bad: "text-[var(--bad)]",
  warn: "text-[var(--warn)]",
};

function Stat({
  label,
  value,
  strong,
  tone,
}: {
  label: string;
  value: string | number;
  strong?: boolean;
  tone?: Tone;
}) {
  const valueClass =
    (tone && STAT_TONE[tone]) ||
    (strong ? "text-[var(--accent-strong)]" : "text-[var(--ink)]");
  return (
    <div className="flex min-w-[62px] flex-col rounded-[var(--r-md)] border border-[var(--line)] bg-[var(--bg)] px-2.5 py-1.5">
      <span className={`text-[17px] font-extrabold leading-none tabular-nums ${valueClass}`}>
        {value}
      </span>
      <span className="mt-1 text-[9.5px] font-bold uppercase tracking-[0.06em] text-[var(--ink-faint)]">
        {label}
      </span>
    </div>
  );
}

function Section({
  title,
  aside,
  children,
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mt-4 first:mt-0">
      <div className="mb-2 flex items-baseline justify-between gap-3 border-b border-[var(--line-soft)] pb-1.5">
        <h4 className="text-[10.5px] font-bold uppercase tracking-[0.08em] text-[var(--ink-soft)]">
          {title}
        </h4>
        {aside}
      </div>
      {children}
    </section>
  );
}

/* ------------------------------ renderers ------------------------------- */

function RequirementView({ p }: { p: Unknown }) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-bold text-[var(--ink)]">{asStr(p.title)}</h3>
        <Chip tone="accent">{asStr(p.source) || "text"}</Chip>
        {asNum(p.word_count) != null && <Chip>normalized</Chip>}
      </div>
      <Section title="Requirement">
        <TextBlock text={asStr(p.text)} />
      </Section>
      <div className="mt-3 flex gap-2">
        {asNum(p.word_count) != null && <Stat label="words" value={asNum(p.word_count) ?? 0} />}
        {asNum(p.char_count) != null && <Stat label="chars" value={asNum(p.char_count) ?? 0} />}
      </div>
      <RawJson payload={p} />
    </div>
  );
}

function DoctorView({ p }: { p: Unknown }) {
  const diagnosis = asObj(p.diagnosis) ?? p;
  const score = asNum(diagnosis.quality_score) ?? null;
  const findings = asArr(diagnosis.findings) ?? [];
  const enhanced = asStr(p.enhanced_text);
  const sev: Record<string, "bad" | "warn" | "accent" | "neutral"> = {
    critical: "bad",
    high: "warn",
    medium: "accent",
    low: "neutral",
  };
  return (
    <div>
      <div className="flex flex-wrap items-center gap-4">
        {score != null && (
          <div className="flex items-center gap-3">
            <div className="h-2.5 w-40 overflow-hidden rounded-full bg-[var(--bg-sunken)]">
              <div
                className={`h-full rounded-full ${score >= 80 ? "bg-[var(--ok)]" : score >= 55 ? "bg-[var(--warn)]" : "bg-[var(--bad)]"}`}
                style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
              />
            </div>
            <span className="text-2xl font-extrabold tabular-nums text-[var(--ink)]">{score}</span>
            <span className="text-xs font-semibold text-[var(--ink-faint)]">/ 100 quality</span>
          </div>
        )}
      </div>
      {findings.length > 0 && (
        <Section title={`Findings (${findings.length})`}>
          <ul className="space-y-1.5">
            {findings.map((f, i) => {
              const o = asObj(f);
              const s = o ? asStr(o.severity).toLowerCase() : "";
              return (
                <li key={i} className="flex items-start gap-2 rounded-lg border border-[var(--line)]/70 bg-[var(--bg)] px-3 py-2">
                  <span className="mt-1">
                    <Chip tone={sev[s] ?? "neutral"}>{s || "info"}</Chip>
                  </span>
                  <span className="text-sm leading-relaxed text-[var(--ink-soft)]">{asStr(o?.message)}</span>
                  {asNum(o?.penalty) != null && <span className="ml-auto shrink-0 text-[11px] font-bold text-[var(--ink-faint)]">-{asNum(o?.penalty)} pts</span>}
                </li>
              );
            })}
          </ul>
        </Section>
      )}
      {enhanced && (
        <Section title="Enhanced requirement">
          <TextBlock text={enhanced} maxH="56" />
        </Section>
      )}
      <RawJson payload={p} />
    </div>
  );
}

function CasesView({ p }: { p: Unknown }) {
  const cases = (asArr(p.cases) ?? []).slice(0, 60);
  const byType: Record<string, number> = {};
  const byPrio: Record<string, number> = {};
  for (const c of cases) {
    const o = asObj(c);
    const t = asStr(o?.type) || "case";
    byType[t] = (byType[t] ?? 0) + 1;
    const pr = asStr(o?.priority) || "any";
    byPrio[pr] = (byPrio[pr] ?? 0) + 1;
  }
  const prioTone: Record<string, "bad" | "warn" | "ok" | "neutral"> = { P0: "bad", P1: "warn", P2: "ok", P3: "neutral" };
  const typeTone: Record<string, "accent" | "neutral" | "bad" | "warn" | "ok"> = {
    security: "bad",
    negative: "warn",
    edge: "accent",
    functional: "ok",
    accessibility: "neutral",
    api: "accent",
  };
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <Stat label="cases" value={cases.length} />
        {Object.entries(byType).map(([t, n]) => (
          <Chip key={t} tone={typeTone[t] ?? "neutral"}>
            {t} × {n}
          </Chip>
        ))}
        {Object.entries(byPrio).map(([pr, n]) => (
          <Chip key={pr} tone={prioTone[pr] ?? "neutral"}>
            {pr} × {n}
          </Chip>
        ))}
      </div>
      <Section title="Test cases">
        <ul className="space-y-2">
          {cases.map((c, i) => {
            const o = asObj(c);
            const id = asStr(o?.id) || `TC-${String(i + 1).padStart(4, "0")}`;
            const title = asStr(o?.title) || "Untitled case";
            const type = asStr(o?.type);
            const prio = asStr(o?.priority);
            const expected = asStr(o?.expected);
            const steps = asArr(o?.steps);
            return (
              <li key={id} className="rounded-lg border border-[var(--line)]/70 bg-[var(--bg)] px-3 py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[11px] font-bold text-[var(--accent-strong)]">{id}</span>
                  {type && <Chip tone={typeTone[type] ?? "neutral"}>{type}</Chip>}
                  {prio && <Chip tone={prioTone[prio] ?? "neutral"}>{prio}</Chip>}
                  {asStr(o?.severity) && <Chip>{asStr(o?.severity)}</Chip>}
                </div>
                <p className="mt-1.5 text-sm font-semibold leading-snug text-[var(--ink)]">{title}</p>
                {expected && (
                  <p className="mt-1 text-xs leading-relaxed text-[var(--ink-soft)]">
                    <span className="font-semibold text-[var(--ink-faint)]">Expected: </span>
                    {expected}
                  </p>
                )}
                {steps && steps.length > 0 && (
                  <details className="mt-1.5">
                    <summary className="cursor-pointer text-[11px] font-bold text-[var(--ink-faint)] hover:text-[var(--ink-soft)]">
                      {steps.length} step{steps.length === 1 ? "" : "s"}
                    </summary>
                    <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-xs text-[var(--ink-soft)]">
                      {steps.map((s, si) => (
                        <li key={si}>{asStr(s)}</li>
                      ))}
                    </ol>
                  </details>
                )}
              </li>
            );
          })}
        </ul>
      </Section>
      <RawJson payload={p} />
    </div>
  );
}

function RunResultsView({ p }: { p: Unknown }) {
  const results = asArr(p.results) ?? [];
  const statusOf = (r: Unknown) => asStr(r.status) || "unknown";
  const counts: Record<string, number> = {};
  for (const r of results) {
    const s = statusOf(asObj(r) ?? {});
    counts[s] = (counts[s] ?? 0) + 1;
  }
  const failed = (counts.failed ?? 0) + (counts.broken ?? 0) + (counts.error ?? 0);
  const passed = counts.passed ?? 0;
  const tone: Record<string, "ok" | "bad" | "warn" | "neutral"> = {
    passed: "ok",
    failed: "bad",
    broken: "bad",
    error: "bad",
    skipped: "warn",
    timedout: "bad",
    unknown: "neutral",
  };
  const dotColor: Record<string, string> = {
    ok: "var(--ok)",
    bad: "var(--bad)",
    warn: "var(--warn)",
    neutral: "var(--ink-faint)",
  };
  return (
    <div>
      {results.length === 0 && (
        <p className="text-sm text-[var(--ink-faint)]">No tests were executed{asStr(p.error) ? ` — ${asStr(p.error)}` : ""}.</p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Stat label="total" value={results.length} />
        {passed > 0 && <Stat label="passed" value={passed} strong />}
        {failed > 0 && <Stat label="failed" value={failed} strong />}
        {counts.skipped != null && counts.skipped > 0 && <Stat label="skipped" value={counts.skipped} />}
        {results.length > 0 && (
          <Chip tone={failed === 0 ? "ok" : "bad"}>{failed === 0 ? "All green" : "Failures found"}</Chip>
        )}
      </div>
      {results.length > 0 && (
        <Section title="Per-test results">
          <ul className="space-y-1.5">
            {results.map((r, i) => {
              const o = asObj(r);
              const st = statusOf(o ?? {});
              const err = asStr(o?.error);
              const dur = asNum(o?.duration_ms);
              const file = asStr(o?.file);
              return (
                <li key={i} className="rounded-lg border border-[var(--line)]/70 bg-[var(--bg)] px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: dotColor[tone[st] ?? "neutral"] }} />
                    <span className="min-w-0 flex-1 truncate text-sm font-medium text-[var(--ink)]">{asStr(o?.title) || `Test ${i + 1}`}</span>
                    <Chip tone={tone[st] ?? "neutral"}>{st}</Chip>
                    {dur != null && <span className="shrink-0 text-[11px] tabular-nums text-[var(--ink-faint)]">{dur} ms</span>}
                  </div>
                  {file && <p className="mt-0.5 pl-4 font-mono text-[10px] text-[var(--ink-faint)]">{file}</p>}
                  {err && <p className="mt-1 rounded bg-[var(--bad)]/5 px-2 py-1 font-mono text-[11px] leading-relaxed text-[var(--bad)]">{err}</p>}
                </li>
              );
            })}
          </ul>
        </Section>
      )}
      <RawJson payload={p} />
    </div>
  );
}

function TriageView({ p }: { p: Unknown }) {
  const verdicts = asArr(p.verdicts) ?? [];
  const total =
    asNum(p.total_failures) ??
    verdicts.reduce<number>((acc, v) => acc + (asNum(asObj(v)?.count) ?? 0), 0);
  return (
    <div>
      <div className="flex items-center gap-2">
        <Stat label="failures" value={total} />
        <Stat label="root causes" value={verdicts.length} />
      </div>
      {verdicts.length === 0 && <p className="mt-2 text-sm text-[var(--ink-faint)]">No failures to triage.</p>}
      <Section title="Root causes">
        <ul className="space-y-2">
          {verdicts.map((v, i) => {
            const o = asObj(v);
            const conf = asNum(o?.confidence);
            const count = asNum(o?.count) ?? 1;
            const evidence = asArr(o?.evidence) ?? [];
            return (
              <li key={i} className="rounded-lg border border-[var(--line)]/70 bg-[var(--bg)] px-3 py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-bold text-[var(--ink)]">{asStr(o?.classification) || "unclassified"}</span>
                  {conf != null && (
                    <span className={`text-xs font-extrabold ${conf >= 60 ? "text-[var(--ok)]" : conf >= 45 ? "text-[var(--warn)]" : "text-[var(--bad)]"}`}>
                      {conf}% confidence
                    </span>
                  )}
                  <Chip>{count} failure{count === 1 ? "" : "s"}</Chip>
                  <Chip tone="neutral">{asStr(o?.status) || "supported"}</Chip>
                </div>
                {asStr(o?.cluster) && (
                  <p className="mt-1.5 rounded bg-[var(--bg-sunken)]/50 px-2 py-1 font-mono text-[11px] leading-relaxed text-[var(--ink-soft)]">
                    {asStr(o?.cluster)}
                  </p>
                )}
                {evidence.length > 0 && (
                  <ul className="mt-1.5 space-y-1">
                    {evidence.map((e, ei) => {
                      const eo = asObj(e);
                      return (
                        <li key={ei} className="text-xs text-[var(--ink-soft)]">
                          <span className="font-mono text-[10px] font-bold text-[var(--accent-strong)]">{asStr(eo?.evidence_id)}</span>{" "}
                          {asStr(eo?.claim)}
                          {asStr(eo?.quote) && <span className="text-[var(--ink-faint)]"> — “{asStr(eo?.quote)}”</span>}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </Section>
      <RawJson payload={p} />
    </div>
  );
}

/**
 * One generated file. The source is rendered only once the row is opened —
 * a full framework bundle is a dozen files of TypeScript, and keeping all of
 * that in the DOM for every collapsed artifact is pure cost.
 */
function FileEntry({ name, content }: { name: string; content: string }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-[var(--r-sm)] border border-[var(--line)] bg-[var(--bg)]">
      <details onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-[12px]">
          <Icon name="arrow" size={11} className="chev shrink-0 text-[var(--ink-faint)]" />
          <span className="truncate font-mono font-semibold text-[var(--ink)]">{name}</span>
          <span className="ml-auto shrink-0 font-mono text-[10px] tabular-nums text-[var(--ink-faint)]">
            {(content.length / 1024).toFixed(1)} KB
          </span>
        </summary>
        {open && (
          <pre className="qa-fade max-h-64 overflow-auto border-t border-[var(--line)] p-2.5 font-mono text-[11px] leading-relaxed text-[var(--ink-soft)]">
            {content}
          </pre>
        )}
      </details>
    </li>
  );
}

function CodegenView({ p }: { p: Unknown }) {
  const bundle = asObj(p.bundle) ?? {};
  const filesTree = asObj(p.files);
  const grounding = asObj(p.grounding_report);
  const counts = asObj(grounding?.counts) ?? {};

  // Two shapes reach here: the current publish bundle ({ path: source }) and
  // the older nested tree ({ tests: [{ name, content }] }). Normalize both to
  // [path, source] pairs, dropping anything that is not a string so the file
  // tree below is typed rather than guessed.
  const bundleEntries: [string, string][] = [];
  for (const [path, source] of Object.entries(bundle)) {
    if (typeof source === "string" && source.length > 0) bundleEntries.push([path, source]);
  }

  const treeEntries: [string, string][] = [];
  if (filesTree) {
    for (const entries of Object.values(filesTree)) {
      if (!Array.isArray(entries)) continue;
      for (const entry of entries) {
        const o = asObj(entry);
        const name = asStr(o?.name);
        const content = asStr(o?.content);
        if (name && content) treeEntries.push([name, content]);
      }
    }
  }

  const fileEntries = bundleEntries.length ? bundleEntries : treeEntries;

  const byDir: Record<string, [string, string][]> = { ".": [] };
  for (const [name, content] of fileEntries) {
    const idx = name.lastIndexOf("/");
    const dir = idx > 0 ? name.slice(0, idx) : ".";
    byDir[dir] = byDir[dir] ?? [];
    byDir[dir].push([idx > 0 ? name.slice(idx + 1) : name, content]);
  }
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="accent">Playwright · TypeScript POM</Chip>
        {asStr(p.base_url) && <Chip>{asStr(p.base_url)}</Chip>}
        <Stat label="files" value={fileEntries.length} />
        {asNum(p.total_cases) != null && <Stat label="cases" value={asNum(p.total_cases) ?? 0} />}
      </div>
      {counts && Object.keys(counts).length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(counts).map(([tier, n]) => {
            const tone = tier === "run_verified" ? "ok" : tier === "dom_verified" ? "accent" : "warn";
            return (
              <Chip key={tier} tone={tone as "ok" | "accent" | "warn"}>
                {tier} × {String(n)}
              </Chip>
            );
          })}
        </div>
      )}
      <Section title="Generated framework">
        <div className="space-y-1.5">
          {Object.entries(byDir)
            .sort(([a], [b]) => (a === "." ? -1 : b === "." ? 1 : a.localeCompare(b)))
            .map(([dir, files]) => (
              <div key={dir}>
                <p className="font-mono text-[11px] font-bold text-[var(--ink-faint)]">{dir === "." ? "/" : dir + "/"}</p>
                <ul className="mt-1 space-y-1">
                  {files.map(([name, content]) => (
                    <FileEntry key={dir + "/" + name} name={name} content={content} />
                  ))}
                </ul>
              </div>
            ))}
        </div>
      </Section>
      <RawJson payload={p} />
    </div>
  );
}

function ReleaseView({ p }: { p: Unknown }) {
  const verdict = asStr(p.verdict).toUpperCase();
  const go = verdict === "GO";
  const reason = asStr(p.reason);
  const evidence = asObj(p.evidence) ?? {};
  const checks = asObj(p.checks) ?? {};
  const criteria = asObj(p.criteria) ?? {};
  const stat = (k: string) => asNum(evidence[k]);
  return (
    <div>
      <div
        className={`flex flex-col items-center rounded-xl border px-4 py-5 ${
          go ? "border-[var(--ok)]/40 bg-[var(--ok)]/10" : "border-[var(--bad)]/40 bg-[var(--bad)]/10"
        }`}
      >
        <span className={`text-4xl font-extrabold tracking-tight ${go ? "text-[var(--ok)]" : "text-[var(--bad)]"}`}>{verdict}</span>
        {reason && <p className="mt-2 max-w-xl text-center text-sm text-[var(--ink-soft)]">{reason}</p>}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {stat("total") != null && <Stat label="total" value={stat("total") ?? 0} />}
        {stat("passed") != null && <Stat label="passed" value={stat("passed") ?? 0} strong />}
        {stat("failed") != null && <Stat label="failed" value={stat("failed") ?? 0} />}
        {stat("skipped") != null && <Stat label="skipped" value={stat("skipped") ?? 0} />}
        {stat("pass_percent") != null && <Stat label="pass %" value={`${stat("pass_percent") ?? 0}%`} />}
        {stat("high_priority_failures") != null && <Stat label="high-prio fails" value={stat("high_priority_failures") ?? 0} />}
      </div>
      {Object.keys(checks).length > 0 && (
        <Section title="Criteria checks">
          <ul className="space-y-1">
            {Object.entries(checks).map(([k, ok]) => (
              <li key={k} className="flex items-center gap-2 text-sm">
                <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-black ${ok ? "bg-[var(--ok)]/15 text-[var(--ok)]" : "bg-[var(--bad)]/10 text-[var(--bad)]"}`}>
                  {ok ? "✓" : "✕"}
                </span>
                <span className="font-mono text-xs text-[var(--ink-soft)]">{k}</span>
                {asNum(criteria[k]) != null && <span className="text-xs text-[var(--ink-faint)]">(threshold {asNum(criteria[k])})</span>}
              </li>
            ))}
          </ul>
        </Section>
      )}
      <RawJson payload={p} />
    </div>
  );
}

function GenericView({ p }: { p: Unknown }) {
  const scalars = Object.entries(p).filter(
    ([, v]) => v == null || (["string", "number", "boolean"].includes(typeof v) && !(typeof v === "string" && v.length > 400)),
  );
  // Narrowed via type predicates: filtering alone leaves the entries typed as
  // unknown, so the length checks and item mapping below would not compile.
  const arrays = Object.entries(p).filter(
    (entry): entry is [string, unknown[]] => Array.isArray(entry[1]),
  );
  const objects = Object.entries(p).filter(
    (entry): entry is [string, Unknown] =>
      entry[1] != null && typeof entry[1] === "object" && !Array.isArray(entry[1]),
  );
  return (
    <div>
      {scalars.length > 0 && (
        <dl className="space-y-1.5">
          {scalars.map(([k, v]) => (
            <div key={k} className="flex gap-3 rounded-lg border border-[var(--line)]/60 bg-[var(--bg)] px-3 py-1.5 text-sm">
              <dt className="w-32 shrink-0 font-mono text-[11px] font-bold uppercase tracking-wide text-[var(--ink-faint)]">{k}</dt>
              <dd className="min-w-0 break-words text-[var(--ink-soft)]">{typeof v === "boolean" ? String(v) : typeof v === "number" ? String(v) : v == null ? <i className="text-[var(--ink-faint)]">null</i> : (v as string)}</dd>
            </div>
          ))}
        </dl>
      )}
      {arrays.map(([k, v]) => (
        <Section key={k} title={`${k} (${v.length})`}>
          {v.length === 0 ? (
            <p className="text-sm text-[var(--ink-faint)]">Empty list.</p>
          ) : (
            <ul className="space-y-1">
              {v.slice(0, 12).map((item, i) => {
                if (typeof item === "string") return <li key={i} className="rounded bg-[var(--bg-sunken)]/40 px-2 py-1 text-xs text-[var(--ink-soft)]">{item}</li>;
                if (item && typeof item === "object") {
                  const o = item as Unknown;
                  const label = [o.title, o.name, o.message, o.status, o.classification].find((x) => typeof x === "string" && x);
                  return (
                    <li key={i} className="rounded-lg border border-[var(--line)]/60 bg-[var(--bg)] px-2.5 py-1.5 text-xs text-[var(--ink-soft)]">
                      {label ? asStr(label) : `item ${i + 1}`}
                      {asStr(o.error) && <span className="text-[var(--bad)]"> — {asStr(o.error)}</span>}
                    </li>
                  );
                }
                return <li key={i} className="text-xs text-[var(--ink-faint)]">item {i + 1}</li>;
              })}
              {v.length > 12 && <li className="text-[11px] font-bold text-[var(--ink-faint)]">+ {v.length - 12} more…</li>}
            </ul>
          )}
        </Section>
      ))}
      {objects.length > 0 && (
        <Section title="Details">
          <p className="text-xs text-[var(--ink-soft)]">
            {objects.map(([k, o]) => (
              <span key={k} className="mr-3">
                <span className="font-mono font-bold text-[var(--accent-strong)]">{k}</span> · {Object.keys(o).join(", ")}
              </span>
            ))}
          </p>
        </Section>
      )}
      <RawJson payload={p} />
    </div>
  );
}

/* ------------------------------- dispatch -------------------------------- */

type Kind = { label: string; icon: IconName; note?: string };

/** Name the artifact and surface its one most useful fact in the header, so a
 * collapsed stage still reads as a document rather than a blob. */
function describe(p: Unknown): { kind: Kind; body: ReactNode } {
  // release decision — verdict + evidence
  if (asStr(p.verdict) && (asStr(p.reason) || asObj(p.evidence))) {
    const verdict = asStr(p.verdict).replace("_", "-").toUpperCase();
    return { kind: { label: "Release decision", icon: "release", note: verdict }, body: <ReleaseView p={p} /> };
  }
  // requirement doctor — diagnosis + optional enhanced rewrite
  if (asObj(p.diagnosis) || ("quality_score" in p && asArr(p.findings))) {
    const d = asObj(p.diagnosis) ?? p;
    const score = asNum(d.quality_score);
    return {
      kind: {
        label: "Requirement diagnosis",
        icon: "doctor",
        note: score != null ? `quality ${score}/100` : undefined,
      },
      body: <DoctorView p={p} />,
    };
  }
  // generated POM framework
  if (asObj(p.bundle) || asObj(p.files) || ("files" in p && asArr(p.files))) {
    const n = asObj(p.bundle) ? Object.keys(asObj(p.bundle) as Unknown).length : null;
    return {
      kind: {
        label: "Generated framework",
        icon: "codegen",
        note: [asStr(p.framework) || "playwright-pom", n ? `${n} files` : null]
          .filter(Boolean)
          .join(" · "),
      },
      body: <CodegenView p={p} />,
    };
  }
  // test case generation
  if (asArr(p.cases)) {
    const n = (asArr(p.cases) as unknown[]).length;
    return {
      kind: { label: "Test cases", icon: "cases", note: `${n} case${n === 1 ? "" : "s"}` },
      body: <CasesView p={p} />,
    };
  }
  // triage — root-cause clusters
  if (asArr(p.clusters) || asArr(p.verdicts)) {
    const v = asArr(p.verdicts);
    return {
      kind: {
        label: "Failure triage",
        icon: "triage",
        note: v ? `${v.length} root cause${v.length === 1 ? "" : "s"}` : undefined,
      },
      body: <TriageView p={p} />,
    };
  }
  // executor results
  if (asArr(p.results)) {
    const results = asArr(p.results) as unknown[];
    return {
      kind: {
        label: "Test run results",
        icon: "runner",
        note: `${results.length} test${results.length === 1 ? "" : "s"}`,
      },
      body: <RunResultsView p={p} />,
    };
  }
  // intake requirement
  if ("text" in p && "word_count" in p && asNum(p.word_count) != null) {
    return {
      kind: {
        label: "Requirement",
        icon: "intake",
        note: `${asNum(p.word_count)} words`,
      },
      body: <RequirementView p={p} />,
    };
  }
  return { kind: { label: "Output", icon: "stack" }, body: <GenericView p={p} /> };
}

export function ArtifactView({ payload }: { payload: Unknown }) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return <p className="text-sm text-[var(--ink-faint)]">No output.</p>;
  }
  const { kind, body } = describe(payload);
  return (
    <div className="qa-fade">
      <header className="mb-3 flex items-center gap-2 border-b border-[var(--line-soft)] pb-2">
        <Icon name={kind.icon} size={14} className="shrink-0 text-[var(--ink-faint)]" />
        <span className="text-[10.5px] font-bold uppercase tracking-[0.08em] text-[var(--ink-soft)]">
          {kind.label}
        </span>
        {kind.note && (
          <span className="ml-auto truncate font-mono text-[10.5px] text-[var(--ink-faint)]">
            {kind.note}
          </span>
        )}
      </header>
      {body}
    </div>
  );
}
