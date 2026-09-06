import { notFound } from "next/navigation";

import { ToolWorkspace } from "@/components/tool-workspace";
import { TOOLS } from "@/lib/tools";

export const metadata = {
  title: "Tool | QA/One",
};

export default async function ToolPage({
  params,
}: {
  params: Promise<{ tool: string }>;
}) {
  const { tool: toolId } = await params;
  const tool = TOOLS.find((t) => t.id === toolId);

  if (!tool || tool.id === "pipeline") {
    notFound();
  }

  return <ToolWorkspace toolId={tool.id} />;
}
