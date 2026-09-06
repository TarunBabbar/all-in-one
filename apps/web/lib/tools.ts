// Tool registry for the QA/One hub shell.
// Mirrors the engine registry in services/api (engine id = route slug).
// Each tool maps to an engine; the pipeline chains several engines.

export interface ToolDef {
  id: string;
  name: string;
  description: string;
  href: string;
  icon: string; // emoji glyph for now; swap to lucide when added
}

export const TOOLS: ToolDef[] = [
  {
    id: "pipeline",
    name: "Pipeline",
    description: "Requirement to release verdict — the full QA flow",
    href: "/pipeline",
    icon: "🛤️",
  },
  {
    id: "requirement-doctor",
    name: "Requirement Doctor",
    description: "Diagnose requirement quality, confirm fixes",
    href: "/tools/requirement-doctor",
    icon: "🩺",
  },
  {
    id: "test-cases",
    name: "Test Case Generator",
    description: "Requirement to structured, reviewable test cases",
    href: "/tools/test-cases",
    icon: "🧪",
  },
  {
    id: "codegen",
    name: "Playwright CodeGen",
    description: "Approved cases to a grounded Playwright suite",
    href: "/tools/codegen",
    icon: "⚙️",
  },
  {
    id: "runner",
    name: "Test Runner",
    description: "Run a suite in the sandbox, stream results",
    href: "/tools/runner",
    icon: "▶️",
  },
  {
    id: "failure-triage",
    name: "Failure Triage",
    description: "Logs & screenshots to evidence-cited root cause",
    href: "/tools/failure-triage",
    icon: "🔍",
  },
  {
    id: "visual",
    name: "Visual Regression",
    description: "Compare screenshots, catch UI regressions",
    href: "/tools/visual",
    icon: "🖼️",
  },
  {
    id: "api-testing",
    name: "API Tester",
    description: "Risk-scored API tests + execution",
    href: "/tools/api-testing",
    icon: "🔌",
  },
  {
    id: "a11y",
    name: "Accessibility",
    description: "WCAG scan of a page",
    href: "/tools/a11y",
    icon: "♿",
  },
  {
    id: "etl",
    name: "ETL QA",
    description: "English data rules to runnable pytest",
    href: "/tools/etl",
    icon: "🗄️",
  },
  {
    id: "release-gate",
    name: "Release Gate",
    description: "GO/NO-GO from run evidence",
    href: "/tools/release-gate",
    icon: "🚦",
  },
  {
    id: "leakage",
    name: "Defect Leakage",
    description: "Post-release missed-defect analysis",
    href: "/tools/leakage",
    icon: "🕳️",
  },
];
