import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-[#0e0f13] px-6 text-center text-zinc-100">
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-orange-400">
          AI Tester Blueprint 3x · 41 projects merged
        </p>
        <h1 className="mt-3 text-5xl font-extrabold tracking-tight">
          QA/One
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-sm leading-relaxed text-zinc-400">
          One AI QA workspace consolidated from the entire hackathon cohort —
          test generation, Playwright execution, failure triage, visual
          regression, and release gates. Phase 0: every origin project is
          credited below.
        </p>
      </div>

      <div className="flex gap-4">
        <Link
          href="/origins"
          className="rounded-lg bg-orange-500 px-5 py-2.5 text-sm font-semibold text-black hover:bg-orange-400"
        >
          Browse all 41 origins
        </Link>
      </div>
    </main>
  );
}
