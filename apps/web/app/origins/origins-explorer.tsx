"use client";

import { useMemo, useState } from "react";

import type { Origin } from "@/lib/types";

const TAG_LABELS: Record<string, string> = {
  intake: "Intake",
  "requirement-doctor": "Req Doctor",
  "test-cases": "Test Cases",
  codegen: "CodeGen",
  execution: "Execution",
  "failure-triage": "Failure Triage",
  visual: "Visual",
  a11y: "A11y",
  "api-testing": "API Testing",
  etl: "ETL / Data",
  "release-gate": "Release Gate",
  leakage: "Leakage",
  rag: "RAG",
  "agent-security": "Agent Security",
  "prompt-eval": "Prompt Eval",
  career: "Career",
  talent: "Talent",
  unrelated: "Unrelated",
  unverifiable: "Unverifiable",
};

export function OriginsExplorer({ origins }: { origins: Origin[] }) {
  const [query, setQuery] = useState("");
  const [activeTag, setActiveTag] = useState<string | null>(null);

  const allTags = useMemo(() => {
    const counts = new Map<string, number>();
    for (const o of origins) {
      for (const t of o.tags) counts.set(t, (counts.get(t) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [origins]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return origins.filter((o) => {
      if (activeTag && !o.tags.includes(activeTag)) return false;
      if (!q) return true;
      return [o.name, o.project, o.one_liner, o.note ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
  }, [origins, query, activeTag]);

  return (
    <div className="px-6 py-6">
      {/* Search + filter bar */}
      <div className="sticky top-0 z-10 -mx-6 border-b border-white/10 bg-[#0e0f13]/95 px-6 py-4 backdrop-blur">
        <div className="flex flex-wrap items-center gap-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name, project, idea…"
            className="w-72 rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none placeholder:text-zinc-500 focus:border-orange-400/60"
          />
          <div className="flex flex-wrap gap-1.5">
            <button
              onClick={() => setActiveTag(null)}
              className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                activeTag === null
                  ? "border-orange-400 bg-orange-400/20 text-orange-300"
                  : "border-white/10 bg-white/5 text-zinc-400 hover:border-white/25"
              }`}
            >
              All ({origins.length})
            </button>
            {allTags.map(([tag, count]) => (
              <button
                key={tag}
                onClick={() => setActiveTag(activeTag === tag ? null : tag)}
                className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                  activeTag === tag
                    ? "border-orange-400 bg-orange-400/20 text-orange-300"
                    : "border-white/10 bg-white/5 text-zinc-400 hover:border-white/25"
                }`}
              >
                {TAG_LABELS[tag] ?? tag} ({count})
              </button>
            ))}
          </div>
          <span className="ml-auto text-xs text-zinc-500">
            {filtered.length} of {origins.length}
          </span>
        </div>
      </div>

      {/* Grid */}
      <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {filtered.map((o) => (
          <article
            key={o.rank}
            className="flex flex-col rounded-xl border border-white/10 bg-white/[0.03] p-5 transition hover:border-orange-400/40"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wider text-orange-400">
                  #{String(o.rank).padStart(2, "0")} · {o.name}
                </p>
                <h2 className="mt-1 truncate text-base font-semibold">
                  {o.project}
                </h2>
              </div>
            </div>

            <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-zinc-400">
              {o.one_liner}
            </p>

            <div className="mt-3 flex flex-wrap gap-1.5">
              {o.tags.map((t) => (
                <span
                  key={t}
                  className="rounded bg-orange-400/10 px-1.5 py-0.5 text-[11px] font-medium text-orange-300/90"
                >
                  {TAG_LABELS[t] ?? t}
                </span>
              ))}
            </div>

            {o.note && (
              <p className="mt-3 border-t border-white/5 pt-3 text-xs leading-relaxed text-zinc-500">
                {o.note}
              </p>
            )}

            <div className="mt-auto flex gap-2 pt-4">
              <a
                href={o.repo}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium hover:border-white/30"
              >
                GitHub
              </a>
              {o.live && (
                <a
                  href={o.live}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium hover:border-white/30"
                >
                  Live demo ↗
                </a>
              )}
            </div>
          </article>
        ))}
      </div>

      {filtered.length === 0 && (
        <p className="py-16 text-center text-sm text-zinc-500">
          No projects match that filter.
        </p>
      )}
    </div>
  );
}
