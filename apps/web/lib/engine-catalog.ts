import { API_URL } from "./api";

/**
 * The engine catalog is the single source of truth for what each tool is
 * called. Names live with the engine (`services/api/app/engines/*.py`) and are
 * read from `GET /engines`, so a rename happens once and cannot disagree with
 * itself across the sidebar, the tool page and the pipeline.
 *
 * The web layer owns only presentation — grouping, order, icon and route.
 */

export interface EngineInfo {
  id: string;
  name: string;
  description: string;
  uses_llm?: boolean;
  uses_runner?: boolean;
}

export type EngineCatalog = Record<string, EngineInfo>;

/** A readable label derived from an id, used only when the API is unreachable. */
export function humanizeEngineId(id: string): string {
  return id
    .split("-")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Read the catalog from the API.
 *
 * Cached briefly rather than fetched per request: a name changes roughly never,
 * and this keeps the routes statically renderable. An unreachable API returns
 * an empty catalog rather than throwing — names are presentation, so a down
 * API must degrade to id-derived labels instead of blanking the navigation.
 */
export async function getEngineCatalog(): Promise<EngineCatalog> {
  try {
    const res = await fetch(`${API_URL}/engines`, {
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(2500),
    });
    if (!res.ok) return {};
    const list = (await res.json()) as EngineInfo[];
    if (!Array.isArray(list)) return {};
    const catalog: EngineCatalog = {};
    for (const engine of list) {
      if (!engine?.id) continue;
      catalog[engine.id] = {
        ...engine,
        name: engine.name?.trim() || humanizeEngineId(engine.id),
        description: engine.description ?? "",
      };
    }
    return catalog;
  } catch {
    return {};
  }
}

/** Look up an engine's name, falling back to its id when the catalog is empty. */
export function engineName(catalog: EngineCatalog, id: string): string {
  return catalog[id]?.name ?? humanizeEngineId(id);
}

/** Look up an engine's description, with no invented fallback. */
export function engineDescription(catalog: EngineCatalog, id: string): string {
  return catalog[id]?.description ?? "";
}
