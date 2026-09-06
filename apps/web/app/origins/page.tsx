import type { Metadata } from "next";

import { OriginsExplorer } from "./origins-explorer";
import { API_URL, type Origin } from "@/lib/types";

export const metadata: Metadata = {
  title: "Origins — all 41 projects | QA/One",
  description:
    "Every AI Tester Blueprint 3x submission credited and linked, mapped to the platform engines it informed.",
};

async function getOrigins(): Promise<{ origins: Origin[]; error: string | null }> {
  try {
    const res = await fetch(`${API_URL}/origins`, { cache: "no-store" });
    if (!res.ok) {
      return { origins: [], error: `API returned ${res.status}` };
    }
    const origins: Origin[] = await res.json();
    return { origins, error: null };
  } catch {
    return {
      origins: [],
      error: `Could not reach API at ${API_URL}. Start it with docker compose up.`,
    };
  }
}

export default async function OriginsPage() {
  const { origins, error } = await getOrigins();

  return (
    <main className="min-h-screen bg-[#0e0f13] text-zinc-100">
      <header className="border-b border-white/10 px-6 py-10">
        <p className="text-xs font-semibold uppercase tracking-widest text-orange-400">
          QA/One · Origins
        </p>
        <h1 className="mt-2 text-4xl font-bold tracking-tight">
          The 41 projects behind this platform
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-zinc-400">
          Every AI Tester Blueprint 3x submission is credited here with its
          repo and live demo. Each project is tagged with the platform engine
          it informed — this is the attribution layer for the merged ideas.
        </p>
      </header>

      {error ? (
        <div className="px-6 py-16">
          <div className="rounded-lg border border-red-900/60 bg-red-950/40 p-4 text-sm text-red-200">
            {error}
          </div>
        </div>
      ) : (
        <OriginsExplorer origins={origins} />
      )}
    </main>
  );
}
