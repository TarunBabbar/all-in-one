/**
 * Theme definitions.
 *
 * Themes are pure CSS: each one is a `html[data-theme="…"]` block in
 * globals.css that redefines the colour tokens. Nothing in the component tree
 * knows a theme exists — every surface already reads `var(--…)`, so switching
 * the attribute on <html> repaints the whole app. No provider, no context.
 *
 * The default theme is `dark`, which lives on plain `:root` and therefore has
 * no attribute. A user who never opens Settings carries none of this.
 */

export interface ThemeDef {
  /** Value written to `data-theme`. Empty string means "no attribute" (default). */
  id: string;
  name: string;
  description: string;
  /** Three representative colours for the picker: canvas, surface, accent. */
  swatches: [string, string, string];
}

export const DEFAULT_THEME = "dark";

export const THEME_STORAGE_KEY = "qaone-theme";

export const THEMES: ThemeDef[] = [
  {
    id: "dark",
    name: "Console",
    description: "The default dark theme.",
    swatches: ["#0b0e13", "#12161d", "#7c7cff"],
  },
  {
    id: "paper",
    name: "Paper",
    description: "Warm light theme for bright rooms.",
    swatches: ["#f7f5f0", "#ffffff", "#5b4fd6"],
  },
  {
    id: "nord",
    name: "Nord",
    description: "Cool blue-grey dark theme.",
    swatches: ["#2e3440", "#3b4252", "#88c0d0"],
  },
  {
    id: "contrast",
    name: "Contrast",
    description: "Maximum legibility, low light.",
    swatches: ["#000000", "#0d0d10", "#a5b4ff"],
  },
];

export function isKnownTheme(id: string): boolean {
  return THEMES.some((t) => t.id === id);
}

/** Apply a theme to the document, or clear it for the default. */
export function applyTheme(id: string): void {
  const root = document.documentElement;
  if (!id || id === DEFAULT_THEME) root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", id);
}

/**
 * Runs in <head> before the first paint.
 *
 * This is what prevents the flash: React has not mounted, so a saved theme set
 * in an effect would arrive one frame late and the user would see the default
 * theme blink. The script is inlined rather than fetched so it cannot itself be
 * deferred. Wrapped in try/catch because localStorage throws in private modes,
 * and a theme preference is never worth breaking the page for.
 *
 * The stored value is validated against the real theme ids: a value left over
 * from an older build, or hand-edited in devtools, must fall through to the
 * default rather than set an attribute no stylesheet matches.
 *
 * Built from the constants above so the key and ids cannot drift from the
 * writer.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});var ok=${JSON.stringify(THEMES.filter((t) => t.id !== DEFAULT_THEME).map((t) => t.id))};if(t&&ok.indexOf(t)>-1){document.documentElement.setAttribute("data-theme",t)}}catch(e){}})()`;
