"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Icon } from "@/lib/icons";
import { API_URL } from "@/lib/api";
import { TOOLS, TOOL_GROUPS, type ToolDef } from "@/lib/tools";

/* ---------------------------------------------------------------------------
 * Navigation
 *
 * Sixteen equal items in one list is a dump, not an information architecture.
 * Tools are grouped in the order the work actually happens — author the tests,
 * automate them, analyse the results, decide on the release — so scanning the
 * sidebar teaches the process.
 * ------------------------------------------------------------------------ */

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavItem({ tool, active }: { tool: ToolDef; active: boolean }) {
  return (
    <Link
      href={tool.href}
      aria-current={active ? "page" : undefined}
      className={`flex items-center gap-2.5 rounded-[var(--r-md)] border px-2.5 py-2 text-[13.5px] transition-colors duration-150 ${
        active
          ? "border-[var(--accent-line)] bg-[var(--accent-soft)] text-[var(--ink)]"
          : "border-transparent text-[var(--ink-soft)] hover:bg-[var(--bg-sunken)] hover:text-[var(--ink)]"
      }`}
    >
      <Icon
        name={tool.icon}
        size={15}
        className={`shrink-0 ${
          active ? "text-[var(--accent)]" : "text-[var(--ink-faint)]"
        }`}
      />
      <span className="truncate">{tool.name}</span>
    </Link>
  );
}

function Brand({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <Link
      href="/"
      onClick={onNavigate}
      className="flex items-center gap-2.5 rounded-[var(--r-md)]"
    >
      <span
        aria-hidden
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[7px] bg-[var(--accent)] text-[14px] font-bold text-[var(--accent-ink)]"
        style={{ fontFamily: "var(--font-display)" }}
      >
        Q
      </span>
      <span className="flex min-w-0 flex-col leading-tight">
        <span
          className="text-[14px] font-semibold text-[var(--ink)]"
          style={{ fontFamily: "var(--font-display)" }}
        >
          QA<span className="text-[var(--accent)]">/One</span>
        </span>
        <span className="text-[11px] text-[var(--ink-faint)]">AI QA workspace</span>
      </span>
    </Link>
  );
}

/** Honest system status — pings the API health route on mount and on window
 * focus, so it reflects reality instead of claiming a permanent green light. */
function ApiStatus() {
  const [state, setState] = useState<"checking" | "up" | "down">("checking");

  useEffect(() => {
    let alive = true;
    const ping = async () => {
      try {
        const res = await fetch(`${API_URL}/health`, { cache: "no-store" });
        if (alive) setState(res.ok ? "up" : "down");
      } catch {
        if (alive) setState("down");
      }
    };
    ping();
    window.addEventListener("focus", ping);
    return () => {
      alive = false;
      window.removeEventListener("focus", ping);
    };
  }, []);

  const copy = {
    checking: "Connecting…",
    up: "Connected",
    down: "API offline",
  }[state];
  const dot = {
    checking: "bg-[var(--ink-faint)] qa-pulse",
    up: "bg-[var(--ok)]",
    down: "bg-[var(--bad)]",
  }[state];
  const ring = {
    checking: "transparent",
    up: "var(--ok-soft)",
    down: "var(--bad-soft)",
  }[state];

  return (
    <span
      className="flex items-center gap-2.5 text-[12.5px] text-[var(--ink-soft)]"
      title={copy}
      role="status"
      aria-live="polite"
    >
      <span
        aria-hidden
        className={`h-[7px] w-[7px] shrink-0 rounded-full ${dot}`}
        style={{ boxShadow: `0 0 0 3px ${ring}` }}
      />
      <span className="truncate">{copy}</span>
    </span>
  );
}

function Sidebar({ pathname }: { pathname: string }) {
  const settingsActive = isActive(pathname, "/settings");

  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] flex-col border-r border-[var(--line)] bg-[var(--bg-elev)] px-3.5 pb-4 pt-5 lg:flex">
      <div className="mb-4 flex items-center border-b border-[var(--line)] px-2 pb-5 pt-1">
        <Brand />
      </div>

      <nav aria-label="Tools" className="flex-1 overflow-y-auto">
        {TOOL_GROUPS.map((group) => (
          <div key={group.id} className="mb-4 last:mb-0">
            <p className="field-label px-2.5 pb-1.5">{group.label}</p>
            <div className="space-y-0.5">
              {group.tools.map((t) => (
                <NavItem key={t.id} tool={t} active={isActive(pathname, t.href)} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="mt-auto flex items-center gap-2.5 border-t border-[var(--line)] pt-3.5">
        <ApiStatus />
      </div>

      <Link
        href="/settings"
        aria-current={settingsActive ? "page" : undefined}
        className={`mt-1 flex items-center gap-2.5 rounded-[var(--r-md)] border px-2.5 py-2 text-[13.5px] transition-colors duration-150 ${
          settingsActive
            ? "border-[var(--accent-line)] bg-[var(--accent-soft)] text-[var(--ink)]"
            : "border-transparent text-[var(--ink-soft)] hover:bg-[var(--bg-sunken)] hover:text-[var(--ink)]"
        }`}
      >
        <Icon
          name="settings"
          size={15}
          className={`shrink-0 ${
            settingsActive ? "text-[var(--accent)]" : "text-[var(--ink-faint)]"
          }`}
        />
        <span className="truncate">Settings</span>
      </Link>
    </aside>
  );
}

/** Small screens get the same destinations in a horizontal rail under the
 * brand bar, so no tool becomes unreachable on a narrow viewport. */
function MobileNav({ pathname }: { pathname: string }) {
  return (
    <div className="sticky top-0 z-30 border-b border-[var(--line)] bg-[var(--bg-elev)]/95 backdrop-blur-sm lg:hidden">
      <div className="flex h-14 items-center justify-between gap-3 px-4">
        <Brand />
        <Link
          href="/settings"
          aria-label="Settings"
          className={`flex h-8 w-8 items-center justify-center rounded-[var(--r-md)] border transition-colors ${
            isActive(pathname, "/settings")
              ? "border-[var(--accent-line)] bg-[var(--accent-soft)] text-[var(--accent)]"
              : "border-[var(--line)] text-[var(--ink-soft)] hover:bg-[var(--bg-sunken)]"
          }`}
        >
          <Icon name="settings" size={16} />
        </Link>
      </div>
      <nav aria-label="Tools" className="flex gap-1.5 overflow-x-auto px-4 pb-2.5">
        {TOOLS.map((t) => {
          const active = isActive(pathname, t.href);
          return (
            <Link
              key={t.id}
              href={t.href}
              aria-current={active ? "page" : undefined}
              className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px] transition-colors ${
                active
                  ? "border-[var(--accent-line)] bg-[var(--accent-soft)] text-[var(--ink)]"
                  : "border-[var(--line)] bg-[var(--bg-sunken)] text-[var(--ink-soft)]"
              }`}
            >
              <Icon name={t.icon} size={14} />
              {t.name}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

/** Breadcrumb derived from the route — the last known tool name, or the
 * first path segment when the route is not a registered tool. */
function Topbar({ pathname }: { pathname: string }) {
  const tool = TOOLS.find((t) => isActive(pathname, t.href));
  const segment =
    tool?.name ??
    (pathname.split("/").filter(Boolean)[0] ?? "Overview");
  const crumb = segment.charAt(0).toUpperCase() + segment.slice(1);

  return (
    <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-3.5 sm:px-9">
      <p
        className="truncate text-[12.5px] text-[var(--ink-faint)]"
        style={{ fontFamily: "var(--font-mono)" }}
      >
        QA/One / <b className="font-medium text-[var(--ink-soft)]">{crumb}</b>
      </p>
      <span
        aria-hidden
        className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-full text-[12px] font-bold text-white"
        style={{
          background: "linear-gradient(135deg, #7c7cff, #4a3fd6)",
          fontFamily: "var(--font-display)",
        }}
      >
        Q
      </span>
    </div>
  );
}

export default function HubLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--ink)]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-[var(--r-md)] focus:bg-[var(--bg-elev)] focus:px-3 focus:py-2 focus:text-[13px] focus:font-semibold focus:shadow-[var(--shadow-lg)]"
      >
        Skip to content
      </a>

      <Sidebar pathname={pathname} />

      <div className="lg:pl-[248px]">
        <MobileNav pathname={pathname} />
        <Topbar pathname={pathname} />
        <main id="main" className="px-4 py-7 pb-20 sm:px-9">
          {children}
        </main>
      </div>
    </div>
  );
}
