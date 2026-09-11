// Tool registry for the QA/One hub shell.
// Mirrors the engine registry in services/api (engine id = route slug).
// Each tool maps to an engine; the pipeline chains several engines.

import type { IconName } from "./icons";

export interface ToolDef {
  id: string;
  name: string;
  description: string;
  href: string;
  icon: IconName;
}

/**
 * The pipeline is the product; the tools are its individual steps. Nav groups
 * follow the QA workflow in order, so the sidebar reads as the process rather
 * than an alphabetical dump of sixteen equal items.
 */
export interface ToolGroup {
  id: string;
  label: string;
  tools: ToolDef[];
}

/** Flagship entry. Declared before the groups because the "decide" group
 * includes it, and module-level consts cannot be referenced before init. */
export const PIPELINE: ToolDef = {
  id: "pipeline",
  name: "Pipeline",
  description: "Requirement to release verdict — the full QA flow",
  href: "/pipeline",
  icon: "pipeline",
};

export const TOOL_GROUPS: ToolGroup[] = [
  {
    id: "author",
    label: "author",
    tools: [
      {
        id: "intake",
        name: "Intake",
        description: "Normalize a requirement from any source",
        href: "/tools/intake",
        icon: "intake",
      },
      {
        id: "requirement-doctor",
        name: "Requirement Doctor",
        description: "Diagnose requirement quality, confirm fixes",
        href: "/tools/requirement-doctor",
        icon: "doctor",
      },
      {
        id: "test-cases",
        name: "Test Cases",
        description: "Requirement to structured, reviewable test cases",
        href: "/tools/test-cases",
        icon: "cases",
      },
    ],
  },
  {
    id: "automate",
    label: "automate",
    tools: [
      {
        id: "codegen",
        name: "CodeGen",
        description: "Approved cases to a grounded Playwright suite",
        href: "/tools/codegen",
        icon: "codegen",
      },
      {
        id: "executor",
        name: "Test Runner",
        description: "Run a suite in the sandbox, stream results",
        href: "/tools/executor",
        icon: "runner",
      },
      {
        id: "api-testing",
        name: "API Tester",
        description: "Risk-scored API tests + execution",
        href: "/tools/api-testing",
        icon: "api",
      },
    ],
  },
  {
    id: "analyse",
    label: "analyse",
    tools: [
      {
        id: "failure-triage",
        name: "Failure Triage",
        description: "Logs & screenshots to evidence-cited root cause",
        href: "/tools/failure-triage",
        icon: "triage",
      },
      {
        id: "visual",
        name: "Visual Regression",
        description: "Compare screenshots, catch UI regressions",
        href: "/tools/visual",
        icon: "visual",
      },
      {
        id: "a11y",
        name: "Accessibility",
        description: "WCAG scan of a page",
        href: "/tools/a11y",
        icon: "a11y",
      },
      {
        id: "etl",
        name: "ETL QA",
        description: "English data rules to runnable pytest",
        href: "/tools/etl",
        icon: "etl",
      },
    ],
  },
  {
    id: "decide",
    label: "decide",
    tools: [
      PIPELINE,
      {
        id: "release-gate",
        name: "Release Gate",
        description: "GO/NO-GO from run evidence",
        href: "/tools/release-gate",
        icon: "release",
      },
      {
        id: "leakage",
        name: "Defect Leakage",
        description: "Post-release missed-defect analysis",
        href: "/tools/leakage",
        icon: "leakage",
      },
    ],
  },
  {
    id: "intel",
    label: "intelligence",
    tools: [
      {
        id: "rag",
        name: "RAG Explorer",
        description: "Visible retrieve-then-generate over documents",
        href: "/tools/rag",
        icon: "rag",
      },
      {
        id: "agent-security",
        name: "Agent Security",
        description: "Validate agent tool calls against the expected path",
        href: "/tools/agent-security",
        icon: "security",
      },
      {
        id: "prompt-eval",
        name: "Prompt Eval",
        description: "Golden-set + red-team testing of prompts",
        href: "/tools/prompt-eval",
        icon: "prompt",
      },
    ],
  },
];

/** Flat list for lookups and simple iterations. */
export const TOOLS: ToolDef[] = TOOL_GROUPS.flatMap((g) => g.tools);
