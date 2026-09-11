"use client";

import { createContext, useContext, type ReactNode } from "react";

import {
  humanizeEngineId,
  type EngineCatalog,
  type EngineInfo,
} from "@/lib/engine-catalog";

/**
 * Carries the engine catalog to client components.
 *
 * The catalog is fetched once, server-side, by the hub layout and handed down
 * here, so names are present in the first HTML — no flash of unlabelled
 * navigation while a request is in flight.
 */

const EngineCatalogContext = createContext<EngineCatalog>({});

export function EngineCatalogProvider({
  catalog,
  children,
}: {
  catalog: EngineCatalog;
  children: ReactNode;
}) {
  return (
    <EngineCatalogContext.Provider value={catalog}>
      {children}
    </EngineCatalogContext.Provider>
  );
}

/** The whole catalog, for components that render several engines. */
export function useEngineCatalog(): EngineCatalog {
  return useContext(EngineCatalogContext);
}

/** One engine's name and description, with an id-derived fallback. */
export function useEngine(id: string): EngineInfo {
  const catalog = useContext(EngineCatalogContext);
  const found = catalog[id];
  return (
    found ?? {
      id,
      name: humanizeEngineId(id),
      description: "",
    }
  );
}
