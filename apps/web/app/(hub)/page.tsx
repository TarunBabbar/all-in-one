import Link from "next/link";

import { API_URL, type Project } from "@/lib/api";
import { TOOLS } from "@/lib/tools";

async function getProjects(): Promise<Project[]> {
  try {
    const res = await fetch(`${API_URL}/projects`, { cache: "no-store" });
    if (!res.ok) return [];
    return (await res.json()) as Project[];
  } catch {
    return [];
  }
}

export default async function Home() {
  const pipeline = TOOLS.find((t) => t.id === "pipeline");
  const tools = TOOLS.filter((t) => t.id !== "pipeline" && t.id !== "intake");
  const projects = await getProjects();

  return (
    <div className="mx-auto max-w-5xl">
      <header className="mb-8">
        <p className="text-xs font-semibold uppercase tracking-widest text-[var(--accent)]">
          AI QA workspace
        </p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">QA/One</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[var(--ink-soft)]">
          Run your QA flow end to end — from a raw requirement to a release
          verdict — plus focused tools for every step.
        </p>
      </header>

      {/* Flagship: Pipeline */}
      <section className="mb-8">
        <div className="rounded-xl border border-[var(--accent-soft-2)] bg-[var(--bg-elev)] p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">
                {pipeline?.icon} Flagship
              </p>
              <h2 className="mt-1 text-xl font-bold">{pipeline?.name}</h2>
              <p className="mt-1 max-w-lg text-sm text-[var(--ink-soft)]">
                {pipeline?.description}. Paste a requirement and watch it flow
                through diagnosis, test cases, code generation, execution,
                failure triage, and a GO/NO-GO release verdict — with an
                approval gate at every step.
              </p>
            </div>
            <Link
              href={pipeline?.href ?? "/pipeline"}
              className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-[#fdfaf4] hover:bg-[var(--accent-strong)]"
            >
              Start a pipeline →
            </Link>
          </div>
        </div>
      </section>

      {/* Recent projects */}
      {projects.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-[var(--ink-faint)]">
            Recent projects
          </h2>
          <div className="overflow-hidden rounded-xl border bg-[var(--bg-elev)] shadow-sm">
            {projects.slice(0, 5).map((p) => (
              <Link
                key={p.id}
                href={`/pipeline?project=${p.id}`}
                className="flex items-center justify-between border-b px-4 py-3 text-sm transition last:border-b-0 hover:bg-[var(--bg-hover)]"
              >
                <span className="font-medium text-[var(--ink)]">{p.name}</span>
                <span className="text-xs text-[var(--ink-faint)]">
                  {new Date(p.created_at).toLocaleString()}
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* All tools */}
      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-[var(--ink-faint)]">
          Tools
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {tools.map((t) => (
            <Link
              key={t.id}
              href={t.href}
              className="group rounded-xl border bg-[var(--bg-elev)] p-4 shadow-sm transition hover:border-[var(--accent-soft-2)] hover:bg-[var(--bg-hover)]"
            >
              <span className="text-xl">{t.icon}</span>
              <h3 className="mt-2 font-semibold text-[var(--ink)] group-hover:text-[var(--accent-strong)]">
                {t.name}
              </h3>
              <p className="mt-1 text-xs leading-relaxed text-[var(--ink-soft)]">
                {t.description}
              </p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
