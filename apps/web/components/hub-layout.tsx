import Link from "next/link";

import { TOOLS } from "@/lib/tools";

function ToolLink({ href, icon, name }: { href: string; icon: string; name: string }) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-zinc-400 transition hover:bg-white/5 hover:text-zinc-100"
    >
      <span className="text-base leading-none">{icon}</span>
      <span className="truncate">{name}</span>
    </Link>
  );
}

export default function HubLayout({
  children,
  active,
}: Readonly<{ children: React.ReactNode; active?: string }>) {
  return (
    <div className="flex min-h-screen bg-[#0e0f13] text-zinc-100">
      {/* Sidebar */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-white/10 bg-[#111318]">
        <div className="border-b border-white/10 px-4 py-4">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-lg font-extrabold tracking-tight">
              QA<span className="text-orange-400">/One</span>
            </span>
          </Link>
          <p className="mt-1 text-[11px] text-zinc-500">
            Consolidated AI QA workspace
          </p>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
          <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">
            Tools
          </p>
          {TOOLS.map((t) => (
            <ToolLink
              key={t.id}
              href={t.href}
              icon={t.icon}
              name={t.name}
            />
          ))}
        </nav>

        <div className="border-t border-white/10 px-4 py-3">
          <div className="flex items-center justify-between text-[11px] text-zinc-500">
            <span>LLM</span>
            <span className="rounded bg-emerald-400/10 px-1.5 py-0.5 font-medium text-emerald-400">
              mock
            </span>
          </div>
          <Link
            href="/origins"
            className="mt-2 block text-[11px] text-zinc-600 hover:text-zinc-400"
          >
            Credits · 41 hackathon projects →
          </Link>
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <main className="flex-1 px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
