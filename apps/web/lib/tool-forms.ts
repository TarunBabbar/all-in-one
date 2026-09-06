// Per-engine tool form definitions. Each entry describes the input fields a
// standalone tool workspace shows, mapped to the engine's expected payload.
// The generic tools/[tool] page renders these + posts to /engines/{id}/run.

export interface ToolField {
  name: string; // payload key
  label: string;
  type: "text" | "textarea" | "json" | "number" | "checkbox";
  placeholder?: string;
  default?: string;
  required?: boolean;
}

export interface ToolFormDef {
  engine: string;
  title: string;
  description: string;
  fields: ToolField[];
}

export const TOOL_FORMS: Record<string, ToolFormDef> = {
  intake: {
    engine: "intake",
    title: "Intake",
    description: "Normalize a requirement from text, URL, Jira, or PRD into a structured artifact.",
    fields: [
      { name: "text", label: "Raw requirement", type: "textarea", required: true },
      { name: "source", label: "Source hint (text/url/jira/…)", type: "text", default: "text" },
    ],
  },
  "requirement-doctor": {
    engine: "requirement-doctor",
    title: "Requirement Doctor",
    description: "Score requirement quality, list findings, and (optionally) enhance with accepted fixes.",
    fields: [
      { name: "text", label: "Requirement", type: "textarea", required: true },
    ],
  },
  "test-cases": {
    engine: "test-cases",
    title: "Test Case Generator",
    description: "Turn a requirement into typed, prioritized, reviewable test cases.",
    fields: [{ name: "text", label: "Requirement", type: "textarea", required: true }],
  },
  codegen: {
    engine: "codegen",
    title: "Playwright CodeGen",
    description: "Generate a grounded Playwright suite from approved test cases (JSON).",
    fields: [
      { name: "cases", label: "Test cases (JSON array)", type: "json" },
      { name: "base_url", label: "Base URL", type: "text", default: "http://localhost:3000" },
    ],
  },
  "failure-triage": {
    engine: "failure-triage",
    title: "Failure Triage",
    description: "Cluster failures into root causes with evidence-cited, guard-verified diagnoses.",
    fields: [
      { name: "results", label: "Run results (JSON array)", type: "json" },
    ],
  },
  visual: {
    engine: "visual",
    title: "Visual Regression",
    description: "Compare legacy vs new screenshots. Supply findings/diff metadata.",
    fields: [
      { name: "diff_percent", label: "Diff percent (0-100)", type: "number" },
      { name: "findings", label: "Findings (JSON array)", type: "json" },
    ],
  },
  a11y: {
    engine: "a11y",
    title: "Accessibility",
    description: "WCAG 2.0/2.1 scan of an HTML snippet.",
    fields: [{ name: "html", label: "HTML to scan", type: "textarea", required: true }],
  },
  "api-testing": {
    engine: "api-testing",
    title: "API Tester",
    description: "Risk-scored endpoint analysis + test ideas + optional live request.",
    fields: [
      { name: "method", label: "Method", type: "text", default: "GET" },
      { name: "url", label: "URL", type: "text", required: true },
      { name: "execute", label: "Execute live request", type: "checkbox" },
    ],
  },
  etl: {
    engine: "etl",
    title: "ETL / Data QA",
    description: "Plain-English data rules -> runnable pytest against an injected schema.",
    fields: [
      { name: "rules", label: "Rules (JSON array of strings)", type: "json" },
      { name: "schema", label: "Schema (JSON)", type: "json" },
    ],
  },
  "release-gate": {
    engine: "release-gate",
    title: "Release Gate",
    description: "GO/NO-GO from run results against configurable criteria.",
    fields: [{ name: "results", label: "Run results (JSON array)", type: "json" }],
  },
  leakage: {
    engine: "leakage",
    title: "Defect Leakage",
    description: "Classify post-release defects and propose preventive tests.",
    fields: [{ name: "defects", label: "Defects (JSON array)", type: "json" }],
  },
  rag: {
    engine: "rag",
    title: "RAG Explorer",
    description: "Visible retrieve-then-generate over a document.",
    fields: [
      { name: "document", label: "Document text", type: "textarea", required: true },
      { name: "query", label: "Question", type: "text" },
      { name: "top_k", label: "Top-K chunks", type: "number", default: "3" },
    ],
  },
  "agent-security": {
    engine: "agent-security",
    title: "Agent Security",
    description: "Validate agent tool calls against the expected path.",
    fields: [
      { name: "expected_path", label: "Expected path (JSON)", type: "json" },
      { name: "actual_trace", label: "Actual trace (JSON)", type: "json" },
    ],
  },
  executor: {
    engine: "executor",
    title: "Test Runner",
    description: "Dispatch a generated suite (files JSON) to the sandboxed Playwright runner.",
    fields: [
      { name: "files", label: "Suite files (JSON: [{name, content}])", type: "json" },
      { name: "base_url", label: "Base URL", type: "text", default: "http://localhost:3000" },
    ],
  },
  "prompt-eval": {
    engine: "prompt-eval",
    title: "Prompt Eval",
    description: "Golden-set + red-team testing of prompts.",
    fields: [{ name: "rows", label: "Test rows (JSON array)", type: "json" }],
  },
};
