import type { ReactNode } from "react";

import HubLayout from "@/components/hub-layout";
import { getEngineCatalog } from "@/lib/engine-catalog";

export default async function HubGroupLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  // Read the engine names once, server-side, so the sidebar, tool pages and
  // pipeline all render the same labels from one source — and so those labels
  // are already in the first HTML rather than arriving after a fetch.
  const catalog = await getEngineCatalog();

  return <HubLayout catalog={catalog}>{children}</HubLayout>;
}
