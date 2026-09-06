"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { TOOLS } from "@/lib/tools";

function ToolLink({
  href,
  icon,
  name,
  active,
}: {
  href: string;
  icon: string;
  name: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition ${
        active
          ? "bg-[var(--accent-soft-2)] font-semibold text-[var(--accent-strong)]"
          : "text-[var(--ink-soft)] hover:bg-[var(--bg-hover)] hover:text-[var(--ink)]"
      }`}
    >
      <span className="text-base leading-none">{icon}</span>
      <span className="truncate">{name}</span>
    </Link>
  );
}

export default function HubLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();

  const activeTool = TOOLS.find(
    (t) => pathname === t.href || pathname.startsWith(`${t.href}/`),
  );

  return (
    <div className="flex min-h-screen bg-[var(--bg)] text-[var(--ink)]">
      {/* Sidebar */}
      <aside className="flex w-60 shrink-0 flex-col border-r bg-[var(--bg-sunken)]">
        <div className="border-b px-4 py-4">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-lg font-extrabold tracking-tight">
              QA<span className="text-[var(--accent)]">/One</span>
            </span>
          </Link>
          <p className="mt-1 text-[11px] text-[var(--ink-faint)]">
            AI QA workspace
          </p>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
          <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--ink-faint)]">
            Tools
          </p>
          {TOOLS.map((t) => (
            <ToolLink
              key={t.id}
              href={t.href}
              icon={t.icon}
              name={t.name}
              active={activeTool?.id === t.id}
            />
          ))}
        </nav>

        <div className="border-t px-4 py-3">
          <Link
            href="/settings"
            className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition ${
              pathname === "/settings"
                ? "bg-[var(--accent-soft-2)] font-semibold text-[var(--accent-strong)]"
                : "text-[var(--ink-soft)] hover:bg-[var(--bg-hover)] hover:text-[var(--ink)]"
            }`}
          >
            <span className="text-base leading-none">⚙️</span>
            <span className="truncate">Settings</span>
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
