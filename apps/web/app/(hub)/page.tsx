import Link from "next/link";

import { Badge } from "@/components/badge";
import { Icon } from "@/lib/icons";
import { API_URL, type Project } from "@/lib/api";
import { engineDescription, engineName, getEngineCatalog } from "@/lib/engine-catalog";
import { CHAIN_STAGES } from "@/lib/stages";
import { PIPELINE, TOOL_GROUPS } from "@/lib/tools";

async function getProjects(): Promise<Project[]> {
  try {
    const res = await fetch(`${API_URL}/projects`, { cache: "no-store" });
    if (!res.ok) return [];
    return (await res.json()) as Project[];
  } catch {
    return [];
  }
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diff = Date.now() - then;
  const min = Math.round(diff / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hrs = Math.round(min / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export default async function Home() {
  const [projects, catalog] = await Promise.all([getProjects(), getEngineCatalog()]);

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-4 flex flex-wrap gap-2">
        <Badge tone="accent" dot>
          AI QA workspace
        </Badge>
      </div>

      <h1 className="text-[34px] font-semibold leading-tight text-[var(--ink)]">
        QA<span className="text-[var(--accent)]">/</span>One
      </h1>
      <div className="mb-7 mt-2.5 flex flex-wrap items-end justify-between gap-4">
        <p className="max-w-[62ch] text-[14.5px] leading-relaxed text-[var(--ink-soft)]">
          One requirement in, a release verdict out. Every stage is an agent you
          can inspect, approve, and rerun on its own.
        </p>
        <Link
          href={PIPELINE.href}
          className="press inline-flex shrink-0 items-center gap-2 rounded-[var(--r-md)] bg-[var(--accent)] px-4 py-2.5 text-[13px] font-semibold text-[var(--accent-ink)] transition-colors hover:bg-[var(--accent-strong)]"
        >
          New pipeline
          <Icon name="arrow" size={15} />
        </Link>
      </div>

      {/* Flagship: the pipeline, shown as the chain it actually is */}
      <section className="mb-7 overflow-hidden rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)]">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            <Icon name="pipeline" size={17} className="text-[var(--accent)]" />
            <h2
              className="text-[15px] font-semibold text-[var(--ink)]"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {engineName(catalog, PIPELINE.id)}
            </h2>
            <Badge>{CHAIN_STAGES.length} stages</Badge>
          </div>
          <Link
            href={PIPELINE.href}
            className="text-[12.5px] font-semibold text-[var(--accent)] transition-colors hover:text-[var(--accent-strong)]"
          >
            Open pipeline →
          </Link>
        </div>

        <ol className="flex flex-wrap items-stretch gap-y-3 px-5 py-4">
          {CHAIN_STAGES.map((stage, i) => (
            <li
              key={stage.stage}
              className="qa-rise flex items-center"
              style={{ animationDelay: `${i * 45}ms` }}
            >
              <div className="flex flex-col items-center gap-1.5">
                <span className="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--line-strong)] bg-[var(--bg-sunken)] text-[var(--ink-soft)]">
                  <Icon name={stage.icon} size={15} />
                </span>
                <span
                  className="max-w-[76px] text-center text-[10px] leading-tight text-[var(--ink-faint)]"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  {engineName(catalog, stage.engine)}
                </span>
              </div>
              {i < CHAIN_STAGES.length - 1 && (
                <span
                  aria-hidden
                  className="mx-2 mb-5 h-px w-6 shrink-0 bg-[var(--line-strong)] sm:w-9"
                />
              )}
            </li>
          ))}
        </ol>

        <p className="border-t border-[var(--line)] px-5 py-3 text-[12.5px] leading-relaxed text-[var(--ink-soft)]">
          The requirement is scored before anything is built, every generator is
          followed by a check that must pass, and the release verdict is computed
          from run evidence rather than described by a model. A failed stage stops
          the chain instead of passing weak output downstream.
        </p>
      </section>

      {/* Recent runs — a table, because that is what the data is */}
      <section className="mb-7">
        <div className="mb-3.5 flex items-baseline justify-between">
          <h2
            className="text-[15px] font-semibold text-[var(--ink)]"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Recent runs
          </h2>
          {projects.length > 0 && (
            <span
              className="text-[12px] tabular-nums text-[var(--ink-faint)]"
              style={{ fontFamily: "var(--font-mono)" }}
            >
              {projects.length} project{projects.length === 1 ? "" : "s"}
            </span>
          )}
        </div>

        <div className="overflow-hidden rounded-[var(--r-lg)] border border-[var(--line)] bg-[var(--bg-elev)]">
          {projects.length === 0 ? (
            <div className="px-5 py-8 text-center">
              <p className="text-[13px] font-semibold text-[var(--ink-soft)]">
                No runs yet
              </p>
              <p className="mx-auto mt-1 max-w-sm text-[12.5px] leading-relaxed text-[var(--ink-faint)]">
                Start a pipeline with a requirement or a Jira issue key. Each
                project keeps its own artifacts, so you can reopen a run and
                resume from the stage that stopped.
              </p>
              <Link
                href={PIPELINE.href}
                className="mt-3 inline-flex items-center gap-1.5 rounded-[var(--r-md)] border border-[var(--line-strong)] bg-[var(--bg)] px-3 py-1.5 text-[12.5px] font-semibold text-[var(--ink)] transition-colors hover:bg-[var(--bg-hover-elev)]"
              >
                Start the first run
                <Icon name="arrow" size={14} />
              </Link>
            </div>
          ) : (
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-[var(--line)]">
                  <th className="field-label px-5 py-2.5 font-normal">project</th>
                  <th className="field-label hidden px-4 py-2.5 font-normal sm:table-cell">
                    created
                  </th>
                  <th className="w-[1%] px-5 py-2.5" />
                </tr>
              </thead>
              {/* Rows fade rather than rise: transforms on <tr> are inconsistent
                  across engines, and a table is not the place to find out. */}
              <tbody>
                {projects.slice(0, 6).map((p, i) => (
                  <tr
                    key={p.id}
                    className="qa-fade group border-b border-[var(--line-soft)] last:border-b-0 hover:bg-[var(--bg-sunken)]"
                    style={{ animationDelay: `${Math.min(i * 30, 180)}ms` }}
                  >
                    <td className="px-5 py-2.5">
                      <Link
                        href={`/pipeline?project=${p.id}`}
                        className="text-[13px] font-medium text-[var(--ink)] transition-colors group-hover:text-[var(--accent)]"
                      >
                        {p.name}
                      </Link>
                      <p
                        className="mt-0.5 text-[10.5px] text-[var(--ink-faint)]"
                        style={{ fontFamily: "var(--font-mono)" }}
                      >
                        {p.id.slice(0, 8)}
                      </p>
                    </td>
                    <td className="hidden px-4 py-2.5 align-middle sm:table-cell">
                      <time
                        dateTime={p.created_at}
                        className="text-[12px] text-[var(--ink-soft)]"
                        style={{ fontFamily: "var(--font-mono)" }}
                        title={new Date(p.created_at).toLocaleString()}
                      >
                        {relativeTime(p.created_at)}
                      </time>
                    </td>
                    <td className="px-5 py-2.5 text-right">
                      <Link
                        href={`/pipeline?project=${p.id}`}
                        className="inline-flex items-center gap-1 rounded-[var(--r-sm)] px-2 py-1 text-[12px] font-semibold text-[var(--ink-faint)] transition-colors hover:text-[var(--ink)]"
                      >
                        Resume
                        <Icon name="arrow" size={13} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {/* Tool index — grouped by workflow, divided rather than carded */}
      <section>
        <h2
          className="mb-3.5 text-[15px] font-semibold text-[var(--ink)]"
          style={{ fontFamily: "var(--font-display)" }}
        >
          Tools
        </h2>
        <div className="grid gap-x-10 gap-y-6 sm:grid-cols-2">
          {TOOL_GROUPS.map((group) => (
            <div key={group.id}>
              <p className="field-label mb-2 border-b border-[var(--line)] pb-2">
                {group.label}
              </p>
              <ul>
                {group.tools.map((t, i) => (
                  <li
                    key={t.id}
                    className="qa-rise"
                    style={{ animationDelay: `${Math.min(i * 20, 140)}ms` }}
                  >
                    <Link
                      href={t.href}
                      className="group flex items-center gap-2.5 rounded-[var(--r-md)] border border-transparent px-2.5 py-2 transition-colors hover:border-[var(--line)] hover:bg-[var(--bg-elev)]"
                    >
                      <Icon
                        name={t.icon}
                        size={16}
                        className="shrink-0 text-[var(--ink-faint)] transition-colors group-hover:text-[var(--accent)]"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block text-[13.5px] font-medium leading-tight text-[var(--ink)]">
                          {engineName(catalog, t.id)}
                        </span>
                        <span className="mt-0.5 block truncate text-[11.5px] leading-tight text-[var(--ink-faint)]">
                          {engineDescription(catalog, t.id)}
                        </span>
                      </span>
                      <Icon
                        name="arrow"
                        size={13}
                        className="shrink-0 text-transparent transition-colors group-hover:text-[var(--ink-faint)]"
                      />
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
