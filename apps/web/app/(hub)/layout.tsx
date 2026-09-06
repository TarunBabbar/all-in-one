import type { ReactNode } from "react";

import HubLayout from "@/components/hub-layout";

export default function HubGroupLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return <HubLayout>{children}</HubLayout>;
}
