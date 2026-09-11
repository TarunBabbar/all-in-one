"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/lib/icons";
import { DEFAULT_THEME, THEMES, THEME_STORAGE_KEY, applyTheme } from "@/lib/theme";

/**
 * Theme picker.
 *
 * Reads the *document* rather than any React state, because the theme is set
 * before hydration by the inline script in <head>. Reading it on mount is
 * therefore the only source of truth that agrees with what is already painted;
 * initialising from a constant here would briefly disagree with the DOM.
 */
export function ThemeSwitcher() {
  // Null until mounted: rendering a selection before we have read the DOM would
  // show the wrong one highlighted for a frame.
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    setActive(document.documentElement.getAttribute("data-theme") ?? DEFAULT_THEME);
  }, []);

  const choose = (id: string) => {
    applyTheme(id);
    setActive(id);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, id);
    } catch {
      // Storage can be unavailable (private mode, quota). The theme still
      // applies for this session; only persistence is lost.
    }
  };

  return (
    <div role="radiogroup" aria-label="Theme" className="grid gap-2 sm:grid-cols-2">
      {THEMES.map((theme) => {
        const selected = active === theme.id;
        return (
          <button
            key={theme.id}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => choose(theme.id)}
            className={`press flex items-start gap-3 rounded-[var(--r-md)] border px-3 py-2.5 text-left transition-colors ${
              selected
                ? "border-[var(--accent-line)] bg-[var(--accent-soft)]"
                : "border-[var(--line)] bg-[var(--bg)] hover:border-[var(--line-strong)] hover:bg-[var(--bg-hover-elev)]"
            }`}
          >
            {/* Swatches are literal hex, not tokens: they must show what each
                theme looks like while a *different* theme is active. */}
            <span aria-hidden className="flex shrink-0 overflow-hidden rounded-[var(--r-sm)] border border-[var(--line-strong)]">
              {theme.swatches.map((hex) => (
                <span key={hex} className="h-7 w-3.5" style={{ background: hex }} />
              ))}
            </span>

            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5">
                <span className="text-[13px] font-semibold text-[var(--ink)]">
                  {theme.name}
                </span>
                {selected && <Icon name="check" size={12} className="text-[var(--accent)]" />}
              </span>
              <span className="mt-0.5 block text-[11.5px] leading-tight text-[var(--ink-faint)]">
                {theme.description}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
