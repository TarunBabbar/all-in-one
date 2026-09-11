// Tool routing and grouping.
//
// Names and descriptions are NOT here — they live with the engine in
// `services/api/app/engines/*.py` and are read from GET /engines. This file
// owns only the things the API has no opinion about: which group a tool sits
// in, what order, which icon, and which route.

import type { IconName } from "./icons";

export interface ToolDef {
  /** Engine id — the join key into the engine catalog. */
  id: string;
  href: string;
  icon: IconName;
}

export interface ToolGroup {
  id: string;
  /** Lowercase, like a config key: this is a label, not a title. */
  label: string;
  tools: ToolDef[];
}

/** Flagship entry. Declared before the groups because the "decide" group
 * includes it, and module-level consts cannot be referenced before init. */
export const PIPELINE: ToolDef = {
  id: "pipeline",
  href: "/pipeline",
  icon: "pipeline",
};

/**
 * Groups follow the QA workflow in order, so the sidebar reads as the process
 * rather than an alphabetical dump of sixteen equal items.
 */
export const TOOL_GROUPS: ToolGroup[] = [
  {
    id: "author",
    label: "author",
    tools: [
      { id: "intake", href: "/tools/intake", icon: "intake" },
      { id: "requirement-doctor", href: "/tools/requirement-doctor", icon: "doctor" },
      { id: "test-cases", href: "/tools/test-cases", icon: "cases" },
    ],
  },
  {
    id: "automate",
    label: "automate",
    tools: [
      { id: "codegen", href: "/tools/codegen", icon: "codegen" },
      { id: "executor", href: "/tools/executor", icon: "runner" },
      { id: "api-testing", href: "/tools/api-testing", icon: "api" },
    ],
  },
  {
    id: "analyse",
    label: "analyse",
    tools: [
      { id: "failure-triage", href: "/tools/failure-triage", icon: "triage" },
      { id: "visual", href: "/tools/visual", icon: "visual" },
      { id: "a11y", href: "/tools/a11y", icon: "a11y" },
      { id: "etl", href: "/tools/etl", icon: "etl" },
    ],
  },
  {
    id: "decide",
    label: "decide",
    tools: [
      PIPELINE,
      { id: "release-gate", href: "/tools/release-gate", icon: "release" },
      { id: "leakage", href: "/tools/leakage", icon: "leakage" },
    ],
  },
  {
    id: "intel",
    label: "intelligence",
    tools: [
      { id: "rag", href: "/tools/rag", icon: "rag" },
      { id: "agent-security", href: "/tools/agent-security", icon: "security" },
      { id: "prompt-eval", href: "/tools/prompt-eval", icon: "prompt" },
    ],
  },
];

/** Flat list for lookups and simple iterations. */
export const TOOLS: ToolDef[] = TOOL_GROUPS.flatMap((g) => g.tools);

/** Non-pipeline tools, i.e. the ones that have a /tools route. */
export const TOOL_ROUTES: ToolDef[] = TOOLS.filter((t) => t.id !== "pipeline");
